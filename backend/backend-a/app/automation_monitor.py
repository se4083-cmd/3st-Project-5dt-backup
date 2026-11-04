"""Prospective AUTO-cycle diagnostics and trusted in-transaction B fact recorder."""

from collections import Counter
from datetime import timedelta
from typing import Literal
from uuid import UUID

from pydantic import Field
from sqlalchemy import and_, exists, func, or_, select

from app import audit
from app.analytics_canonical import digest
from app.automation_control import assert_automatic_allowed, capability
from app.db import utcnow
from app.errors import APIError
from app.models import automation_jobs, tickets
from app.monitor_models import cycles, events, monitor_epoch
from app.quality_metrics import allowed_teams
from app.quality_models import reply_records, revisions, samples
from app.resolution import WorkRejected
from app.schemas import Input


class WorkerOutcome(Input):
    job_id: UUID
    cycle_no: int = Field(ge=1)
    expected_revision: int = Field(ge=1)
    lease_token: UUID
    worker_id: str = Field(min_length=1, max_length=128)
    automation_generation: int = Field(ge=1)
    outcome: Literal["RETRY", "FAILED", "FAILED_HANDOFF", "HANDOFF"]
    reason_code: Literal["RETRY_EXHAUSTED", "POLICY", "LOW_CONFIDENCE", "OTHER", "UNKNOWN"]


def start_cycle(session, ticket_id, cycle, mode, revision, now, *, origin="APPLICATION", origin_auto=None):
    session.execute(
        cycles.insert().values(
            ticket_id=ticket_id,
            cycle_no=cycle,
            entry_mode=mode,
            start_revision=revision,
            started_at=now,
            origin=origin if origin in {"APPLICATION", "SYNTHETIC"} else "UNKNOWN",
            origin_auto_cycle_no=origin_auto,
        )
    )


def record(
    session,
    ticket_id,
    cycle,
    kind,
    revision,
    *,
    key=None,
    job_id=None,
    message_id=None,
    team_id=None,
    reason="NONE",
    writer="A",
    request_hash=None,
):
    # An old ticket is NOT evidence of a fully observed earlier AUTO episode.
    if not session.scalar(
        select(exists().where(cycles.c.ticket_id == ticket_id, cycles.c.cycle_no == cycle))
    ):
        return False
    key = key or kind
    values = dict(
        ticket_id=ticket_id,
        cycle_no=cycle,
        event_key=key,
        kind=kind,
        ticket_revision=revision,
        job_id=job_id,
        message_id=message_id,
        team_id=team_id,
        reason_code=reason,
        writer=writer,
    )
    hashed = request_hash or digest(values)
    old = session.execute(
        select(events.c.request_hash).where(
            events.c.ticket_id == ticket_id, events.c.cycle_no == cycle, events.c.event_key == key
        )
    ).scalar_one_or_none()
    if old:
        if old != hashed:
            raise WorkRejected("MONITOR_FACT_CONFLICT")
        return True
    session.execute(events.insert().values(**values, request_hash=hashed, recorded_at=utcnow()))
    return True


def customer_cycle(session, ticket, new_cycle, mode, revision, now, reason):
    prior = (
        session.execute(
            select(cycles).where(
                cycles.c.ticket_id == ticket["ticket_id"], cycles.c.cycle_no == ticket["cycle_no"]
            )
        )
        .mappings()
        .first()
    )
    origin_auto = prior["cycle_no"] if prior and prior["entry_mode"] == "AUTO" else None
    if origin_auto:
        record(session, ticket["ticket_id"], origin_auto, "RECONTACT", ticket["version"], reason="REOPENED")
        already_transferred = session.scalar(
            select(
                exists().where(
                    events.c.ticket_id == ticket["ticket_id"],
                    events.c.cycle_no == origin_auto,
                    events.c.kind == "TRANSFER",
                )
            )
        )
        if (
            mode == "HUMAN"
            and not already_transferred
            and reason in {"CUSTOMER_REQUEST", "DISSATISFIED", "COMPLEX_ISSUE", "OTHER"}
        ):
            record(session, ticket["ticket_id"], origin_auto, "TRANSFER", ticket["version"], reason=reason)
    start_cycle(
        session,
        ticket["ticket_id"],
        new_cycle,
        mode,
        revision,
        now,
        origin=ticket["data_origin"],
        origin_auto=origin_auto if mode == "HUMAN" else None,
    )


def record_worker_outcome(session, command: WorkerOutcome, *, service_id: str):
    """Internal Python, NOT HTTP. Trusted B authenticates service; caller commits.

    Call BEFORE clearing lease/changing state, while owning the same outer
    transaction. Deferred PG checks require B's resulting job/ticket transition.
    This function never retries, fails, converts, assigns or commits a job.
    """
    import re

    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", service_id):
        raise ValueError("INVALID_SERVICE_ID")
    tid = session.scalar(
        select(automation_jobs.c.ticket_id).where(automation_jobs.c.job_id == str(command.job_id))
    )
    if not tid:
        raise WorkRejected("WORK_NOT_FOUND")
    ticket = (
        session.execute(select(tickets).where(tickets.c.ticket_id == tid).with_for_update()).mappings().one()
    )
    job = (
        session.execute(
            select(automation_jobs).where(automation_jobs.c.job_id == str(command.job_id)).with_for_update()
        )
        .mappings()
        .one()
    )
    kinds = {
        "RETRY": ["RETRY"],
        "FAILED": ["FAILED"],
        "FAILED_HANDOFF": ["FAILED", "TRANSFER"],
        "HANDOFF": ["TRANSFER"],
    }[command.outcome]
    matches = []
    for kind in kinds:
        key = f"RETRY_{job['attempt']}" if kind == "RETRY" else kind
        old = session.scalar(
            select(events.c.request_hash).where(
                events.c.ticket_id == tid, events.c.cycle_no == command.cycle_no, events.c.event_key == key
            )
        )
        expected_hash = digest(
            {"command": command.model_dump(mode="json"), "kind": kind, "service": service_id}
        )
        if old and old != expected_hash:
            raise WorkRejected("MONITOR_FACT_CONFLICT")
        matches.append(bool(old))
    if all(matches):
        return {"recorded": True, "replayed": True, "reason": "ORIGINAL_FACT_NO_EXECUTION_AUTHORITY"}
    if (
        ticket["cycle_no"] != command.cycle_no
        or ticket["version"] != command.expected_revision
        or job["cycle_no"] != command.cycle_no
        or job["expected_ticket_version"] != command.expected_revision
    ):
        raise WorkRejected("STALE_TICKET_REVISION")
    if (
        ticket["requested_mode"] != "AUTO"
        or ticket["status"] not in {"OPEN", "PROCESSING"}
        or job["job_kind"] != "AUTO"
    ):
        raise WorkRejected("AUTOMATION_NOT_ALLOWED")
    if (
        job["status"] != "RUNNING"
        or job["lease_token"] != str(command.lease_token)
        or job["lease_owner"] != command.worker_id
        or not job["lease_until"]
        or job["lease_until"] <= utcnow()
    ):
        raise WorkRejected("INVALID_LEASE")
    assert_automatic_allowed(session, command.automation_generation)
    if job["automation_generation"] != command.automation_generation:
        raise WorkRejected("AUTOMATION_GENERATION_CHANGED")
    if job["lease_until"] <= utcnow():
        raise WorkRejected("INVALID_LEASE")
    with session.begin_nested():
        recorded = False
        for kind in kinds:
            recorded = record(
                session,
                tid,
                command.cycle_no,
                kind,
                command.expected_revision,
                key=f"RETRY_{job['attempt']}" if kind == "RETRY" else kind,
                job_id=job["job_id"],
                team_id=ticket["team_id"],
                reason=command.reason_code,
                writer="B",
                request_hash=digest(
                    {"command": command.model_dump(mode="json"), "kind": kind, "service": service_id}
                ),
            )
        audit.record(session, None, "AUTOMATION_OUTCOME_RECORDED", "TICKET", tid, service=service_id)
        if job["lease_until"] <= utcnow():
            raise WorkRejected("INVALID_LEASE")
    return {
        "recorded": recorded,
        "replayed": False,
        "reason": "RECORDED" if recorded else "PRE_RECORDING_CYCLE_UNKNOWN",
    }


def evaluate_safe(
    *, completed, transferred, recontacted, reviewed, positive, mature, evidence_complete, reporting_complete
):
    if not completed:
        return "NOT_AUTO_COMPLETED"
    if transferred or recontacted:
        return "ADVERSE_FOLLOWUP_OBSERVED"
    if not reviewed:
        return "UNREVIEWED"
    if not positive:
        return "REVIEW_NEGATIVE_OR_UNDETERMINABLE"
    if not mature:
        return "OBSERVATION_IMMATURE"
    if not evidence_complete or not reporting_complete:
        return "INCOMPLETE_OBSERVATION"
    return "PROVISIONALLY_OBSERVED_NOT_OPERATIONAL_CERTIFICATION"


def metrics(session, user, start, end, team_ids=None, include_unattributed=False, origin="APPLICATION"):
    capability(session, user, "QUALITY_METRICS_READ", admin=True)
    allowed = allowed_teams(session, user)
    selected = set(team_ids) if team_ids is not None else allowed
    if not selected <= allowed:
        raise APIError(403, "QUALITY_TEAM_SCOPE_DENIED", user["user_id"])
    if include_unattributed:
        capability(session, user, "QUALITY_UNATTRIBUTED_MANAGE", admin=True)
    if not start < end or end - start > timedelta(days=93):
        raise APIError(422, "MONITOR_PERIOD_INVALID")
    now = session.info["snapshot_as_of"]
    # First explicitly recorded non-null team fact, never current snapshot/audit inference.
    first_team = (
        select(
            events.c.ticket_id,
            events.c.cycle_no,
            events.c.team_id,
            func.row_number()
            .over(
                partition_by=(events.c.ticket_id, events.c.cycle_no),
                order_by=(events.c.recorded_at, events.c.event_key),
            )
            .label("n"),
        )
        .where(events.c.team_id.is_not(None))
        .subquery()
    )
    query = (
        select(cycles, first_team.c.team_id)
        .outerjoin(
            first_team,
            and_(
                first_team.c.ticket_id == cycles.c.ticket_id,
                first_team.c.cycle_no == cycles.c.cycle_no,
                first_team.c.n == 1,
            ),
        )
        .where(cycles.c.started_at >= start, cycles.c.started_at < end, cycles.c.origin == origin)
    )
    visibility = first_team.c.team_id.in_(selected)
    if include_unattributed:
        visibility = or_(visibility, first_team.c.team_id.is_(None))
    rows = list(session.execute(query.where(visibility).limit(10001)).mappings())
    if len(rows) > 10000:
        raise APIError(422, "MONITOR_COHORT_TOO_LARGE_NARROW_PERIOD")
    ids = [(r["ticket_id"], r["cycle_no"]) for r in rows]
    from sqlalchemy import tuple_

    facts = (
        list(
            session.execute(
                select(events).where(tuple_(events.c.ticket_id, events.c.cycle_no).in_(ids))
            ).mappings()
        )
        if ids
        else []
    )
    by_cycle = {}
    for event in facts:
        by_cycle.setdefault((event["ticket_id"], event["cycle_no"]), {})[event["kind"]] = event
    current_states = (
        {
            (r.ticket_id, r.cycle_no): (r.requested_mode, r.job_status)
            for r in session.execute(
                select(
                    tickets.c.ticket_id,
                    tickets.c.cycle_no,
                    tickets.c.requested_mode,
                    automation_jobs.c.status.label("job_status"),
                )
                .outerjoin(
                    automation_jobs,
                    and_(
                        automation_jobs.c.ticket_id == tickets.c.ticket_id,
                        automation_jobs.c.cycle_no == tickets.c.cycle_no,
                    ),
                )
                .where(tuple_(tickets.c.ticket_id, tickets.c.cycle_no).in_(ids))
            )
        }
        if ids
        else {}
    )
    message_ids = [e["message_id"] for e in facts if e["kind"] == "AUTO_COMMITTED"]
    reviews = {}
    if message_ids:
        review_rows = session.execute(
            select(samples.c.message_id, revisions, reply_records.c.provenance_state)
            .join(revisions, revisions.c.sample_id == samples.c.sample_id)
            .join(reply_records)
            .where(
                samples.c.message_id.in_(message_ids),
                samples.c.rubric_version == "DEV_QUALITY_V1",
                samples.c.status != "VOID",
                revisions.c.event_kind == "REVIEW",
            )
            .order_by(revisions.c.revision)
        ).mappings()
        for review in review_rows:
            reviews[review["message_id"]] = review
    statuses, reasons, safe = Counter(), Counter(), Counter()
    committed = failed = auto_count = transfers = human = unreported_terminal = unreported_human = 0
    for row in rows:
        if row["entry_mode"] != "AUTO":
            human += 1
            continue
        f = by_cycle.get((row["ticket_id"], row["cycle_no"]), {})
        current_mode, job_state = current_states.get((row["ticket_id"], row["cycle_no"]), (None, None))
        unreported_terminal += job_state in {"FAILED", "SUCCEEDED", "HANDED_OFF"} and not (
            {"FAILED", "AUTO_COMMITTED", "TRANSFER"} & set(f)
        )
        unreported_human += current_mode == "HUMAN" and "TRANSFER" not in f
        complete = f.get("AUTO_COMMITTED")
        committed += bool(complete)
        failed += "FAILED" in f
        transfers += "TRANSFER" in f
        auto_count += bool(complete) and "TRANSFER" not in f and "FAILED" not in f
        status = (
            "TRANSFERRED"
            if "TRANSFER" in f
            else "FAILED"
            if "FAILED" in f
            else "AUTO_COMPLETED"
            if complete
            else "RETRY_RECORDED"
            if "RETRY" in f
            else "INCOMPLETE_OR_UNREPORTED"
        )
        statuses[status] += 1
        if "TRANSFER" in f:
            reasons[f["TRANSFER"]["reason_code"]] += 1
        review = reviews.get(complete["message_id"]) if complete else None
        safe[
            evaluate_safe(
                completed=bool(complete),
                transferred="TRANSFER" in f,
                recontacted="RECONTACT" in f,
                reviewed=bool(review),
                positive=bool(
                    review
                    and review["accuracy"] == "CORRECT"
                    and review["policy_alignment"] in {"MATCH", "NOT_APPLICABLE"}
                ),
                mature=bool(complete and complete["recorded_at"] + timedelta(days=7) <= now),
                evidence_complete=bool(review and review["provenance_state"] == "COMPLETE"),
                reporting_complete=False,
            )
        ] += 1
    n = len(rows) - human
    legacy = None
    if include_unattributed:
        legacy = session.scalar(
            select(func.count())
            .select_from(tickets)
            .where(
                tickets.c.requested_mode == "AUTO",
                ~exists().where(
                    cycles.c.ticket_id == tickets.c.ticket_id, cycles.c.cycle_no == tickets.c.cycle_no
                ),
                or_(tickets.c.team_id.in_(selected), tickets.c.team_id.is_(None)),
                tickets.c.data_origin == origin,
            )
        )
    audit.record(session, user["user_id"], "AUTOMATION_DIAGNOSTICS_READ", "QUALITY", None)
    return dict(
        as_of=now,
        recording_since=session.scalar(select(monitor_epoch.c.recording_since)),
        response_start=start,
        response_end=end,
        origin=origin,
        team_ids=sorted(selected),
        period_basis="PROSPECTIVE_AUTO_CYCLE_STARTED_AT_[START,END)_CURRENT_SNAPSHOT",
        attribution_basis="FIRST_EXPLICIT_NON_NULL_TEAM_FACT_CURRENT_SCOPE",
        auto_cycle_count=n,
        human_entry_count_excluded=human,
        automatic_completed_count=auto_count,
        automatic_completed_rate=auto_count / n if n else None,
        automatic_reply_committed_count=committed,
        transferred_count=transfers,
        transferred_rate=transfers / n if n else None,
        failed_fact_count=failed,
        statuses=dict(statuses),
        transfer_reasons=dict(reasons),
        safe_observation_states=dict(safe),
        legacy_current_auto_mode_untracked_count=legacy,
        legacy_count_basis="CURRENT_MODE_SNAPSHOT_NOT_A_HISTORICAL_COHORT",
        recording_completeness="PARTIAL_OBSERVED_FACTS_B_REPORTING_NOT_ATTESTED",
        unreported_current_terminal_state_count=unreported_terminal,
        unreported_current_human_state_count=unreported_human,
        excluded_unattributed_count=None,
        excluded_count_reason="NOT_EXPOSED_OUTSIDE_SELECTED_SCOPE; HUMAN_ENTRIES_EXPLICITLY_SEPARATED",
        safe_completion=dict(
            availability="UNAVAILABLE",
            reason="OPERATIONAL_RULE_AND_B_OBSERVATION_NOT_AGREED",
            rate=None,
            rule_version="DEV_SAFE_V1",
            rubric_version="DEV_QUALITY_V1",
            observation_seconds=604800,
            rule_status="DEVELOPMENT_PROPOSAL",
            coverage="A_COMMANDS_RECORDED_B_REPORTING_COMPLETENESS_UNKNOWN",
        ),
    )
