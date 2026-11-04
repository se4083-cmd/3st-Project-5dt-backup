"""Aggregate-only retention review. No deletion planner, row payload reads, or executor."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import and_, case, exists, false, func, or_, select, true

from app import audit
from app import models as m
from app.analytics_canonical import digest
from app.analytics_models import analytics_publication, analytics_receipts
from app.automation_control import capability
from app.errors import APIError
from app.model_constraints import idempotency_keys, user_team_scopes
from app.quality_models import evidence as qa_evidence
from app.quality_models import receipts as qa_receipts
from app.quality_models import reply_records as qa_replies
from app.quality_models import revisions as qa_revisions
from app.quality_models import rubrics as qa_rubrics
from app.quality_models import samples as qa_samples
from app.schemas import Input
from app.staff_models import queue_routes
from app.voc_models import plan_teams as voc_teams
from app.voc_models import plans as voc_plans
from app.voc_models import profiles as voc_profiles
from app.voc_models import receipts as voc_receipts
from app.voc_models import ticket_links as voc_links


class ReviewPolicy(Input):
    version: Literal["DEV_RETENTION_V1"] = "DEV_RETENTION_V1"
    raw_days: int = Field(default=30, ge=1, le=3650, strict=True)
    aggregate_days: int = Field(default=90, ge=1, le=3650, strict=True)


class RetentionRequest(Input):
    purpose_code: Literal["RETENTION_REVIEW"]
    as_of: AwareDatetime
    policy: ReviewPolicy = Field(default_factory=ReviewPolicy)
    scope: Literal["TEAM", "GLOBAL"] = "TEAM"
    team_ids: list[UUID] | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("as_of")
    @classmethod
    def utc_as_of(cls, value):
        if value.year < 2000 or value.year > 2100:
            raise ValueError("Unsupported review time")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def scope_filter(self):
        if self.scope == "GLOBAL" and self.team_ids is not None:
            raise ValueError("Global review has no team filter")
        if self.team_ids is not None and len(set(self.team_ids)) != len(self.team_ids):
            raise ValueError("Duplicate teams")
        return self


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TargetReview(Output):
    target: str
    fields: list[str]
    data_class: Literal["RAW_OR_EXTRACT", "AGGREGATE", "REFERENCE_OR_METADATA"]
    inspection: Literal["INSPECTED", "UNSUPPORTED_TEAM_SCOPE"]
    age_basis: str
    cutoff: datetime | None
    inspected_count: int | None
    past_retention_count: int | None
    candidate_count: int | None
    excluded_count: int | None
    blocked_count: int | None
    requires_design_change_count: int | None
    undetermined_count: int | None
    reason_counts: dict[str, int]


class ExternalStore(Output):
    store: str
    status: Literal["NOT_INSPECTED"] = "NOT_INSPECTED"
    reason: str


class RetentionReport(Output):
    dry_run: Literal[True] = True
    execution_status: Literal["PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION"] = (
        "PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION"
    )
    as_of: datetime
    snapshot_at: datetime
    timezone: Literal["UTC"] = "UTC"
    boundary: Literal["anchor < as_of - N * 24 hours; equality retained"] = (
        "anchor < as_of - N * 24 hours; equality retained"
    )
    policy: ReviewPolicy
    policy_status: Literal["DEVELOPMENT_PROPOSAL_NOT_LEGAL_POLICY"] = "DEVELOPMENT_PROPOSAL_NOT_LEGAL_POLICY"
    policy_hash: str
    scope: Literal["TEAM", "GLOBAL"]
    team_ids: list[UUID]
    targets: list[TargetReview]
    not_inspected: list[ExternalStore]
    limitations: list[str]
    result_fingerprint: str
    candidate_ids_available: Literal[False] = False
    business_data_modified: Literal[False] = False
    minimal_audit_added: Literal[True] = True


def scope_for(session, user, body):
    capability(
        session,
        user,
        "RETENTION_GLOBAL_REVIEW" if body.scope == "GLOBAL" else "RETENTION_TEAM_REVIEW",
        admin=True,
    )
    if body.scope == "GLOBAL":
        return [], true()
    allowed = set(
        session.scalars(
            select(user_team_scopes.c.team_id)
            .join(m.teams)
            .where(user_team_scopes.c.user_id == user["user_id"], m.teams.c.active.is_(True))
        )
    )
    selected = set(map(str, body.team_ids)) if body.team_ids is not None else allowed
    if not selected or not selected <= allowed:
        raise APIError(403, "RETENTION_TEAM_SCOPE_DENIED", user["user_id"])

    # A current owner alone cannot authorize records whose historical custody
    # is unknown. Every recorded custodian must be known and inside the scope.
    def outside(table, cols):
        return exists(
            select(1).where(
                table.c.ticket_id == m.tickets.c.ticket_id,
                or_(*(or_(c.is_(None), c.not_in(selected)) for c in cols)),
            )
        ).correlate(m.tickets)

    safe = and_(
        ~exists(
            select(1)
            .select_from(qa_replies)
            .where(
                qa_replies.c.ticket_id == m.tickets.c.ticket_id,
                or_(
                    qa_replies.c.attribution_team_id.is_(None),
                    qa_replies.c.attribution_team_id.not_in(selected),
                ),
            )
        ).correlate(m.tickets),
        ~exists(
            select(1)
            .select_from(qa_replies.join(qa_samples))
            .where(
                qa_replies.c.ticket_id == m.tickets.c.ticket_id, qa_samples.c.review_team_id.not_in(selected)
            )
        ).correlate(m.tickets),
        m.tickets.c.team_id.in_(selected),
        ~outside(m.assignments, [m.assignments.c.team_id]),
        ~outside(queue_routes, [queue_routes.c.team_id]),
        ~outside(
            m.followup_actions, [m.followup_actions.c.origin_team_id, m.followup_actions.c.owner_team_id]
        ),
        ~exists(
            select(1)
            .select_from(
                voc_links.join(m.followup_actions, voc_links.c.action_id == m.followup_actions.c.action_id)
            )
            .where(
                voc_links.c.ticket_id == m.tickets.c.ticket_id,
                or_(
                    m.followup_actions.c.owner_team_id.not_in(selected),
                    m.followup_actions.c.origin_team_id.not_in(selected),
                ),
            )
        ).correlate(m.tickets),
        ~exists(
            select(1)
            .select_from(voc_links.join(voc_plans, voc_links.c.action_id == voc_plans.c.action_id))
            .where(
                voc_links.c.ticket_id == m.tickets.c.ticket_id,
                voc_plans.c.owner_team_id_snapshot.not_in(selected),
            )
        ).correlate(m.tickets),
        ~exists(
            select(1)
            .select_from(voc_links.join(voc_teams, voc_links.c.action_id == voc_teams.c.action_id))
            .where(
                voc_links.c.ticket_id == m.tickets.c.ticket_id,
                voc_teams.c.team_id.not_in(selected),
            )
        ).correlate(m.tickets),
        # Missing old-cycle attribution is not inferred from category/team now.
        or_(
            m.tickets.c.cycle_no == 1,
            select(func.count())
            .select_from(queue_routes)
            .where(
                queue_routes.c.ticket_id == m.tickets.c.ticket_id,
                queue_routes.c.cycle_no.between(1, m.tickets.c.cycle_no),
                queue_routes.c.team_id.in_(selected),
            )
            .correlate(m.tickets)
            .scalar_subquery()
            == m.tickets.c.cycle_no,
        ),
    )
    return sorted(selected), safe


def ticket_guards(as_of):
    t = m.tickets

    def linked(table, *conditions):
        return exists(select(1).where(table.c.ticket_id == t.c.ticket_id, *conditions)).correlate(t)

    return {
        "UNRESOLVED_TICKET": t.c.status.not_in(["RESOLVED", "CANCELLED"]),
        "MANDATORY_FOLLOWUP_OPEN_ANY_CYCLE": linked(
            m.followup_actions,
            m.followup_actions.c.blocks_resolution,
            m.followup_actions.c.status.in_(["OPEN", "IN_PROGRESS"]),
        ),
        "ACTIVE_ASSIGNMENT_ANY_CYCLE": linked(m.assignments, m.assignments.c.ended_at.is_(None)),
        "ACTIVE_JOB_OR_VALID_LEASE": linked(
            m.automation_jobs,
            or_(
                m.automation_jobs.c.status.in_(["PENDING", "RETRY", "RUNNING"]),
                m.automation_jobs.c.lease_until > as_of,
            ),
        ),
        "IDEMPOTENCY_RETRY_REFERENCE": or_(
            linked(idempotency_keys),
            exists(
                select(1)
                .select_from(
                    idempotency_keys.join(
                        m.followup_actions, idempotency_keys.c.followup_id == m.followup_actions.c.action_id
                    )
                )
                .where(m.followup_actions.c.ticket_id == t.c.ticket_id)
            ).correlate(t),
        ),
        "APPROVAL_REFERENCE": linked(m.approvals),
        "AUDIT_REFERENCE": linked(m.audit_events),
        "VOC_IMPROVEMENT_TICKET_REFERENCE": linked(voc_links),
        "QUALITY_CONFIRMED_REPLY_REFERENCE": linked(qa_replies),
        "VOC_COMMAND_RECEIPT_REFERENCE": linked(voc_receipts),
    }


def inspect(
    session,
    *,
    table,
    fields,
    data_class,
    age_basis,
    cutoff=None,
    scoped=true(),
    join=None,
    old=None,
    guards=None,
    design=None,
    unknown=None,
    supported=True,
):
    base = dict(target=table.name, fields=fields, data_class=data_class, age_basis=age_basis, cutoff=cutoff)
    if not supported:
        return TargetReview(
            **base,
            inspection="UNSUPPORTED_TEAM_SCOPE",
            inspected_count=None,
            past_retention_count=None,
            candidate_count=None,
            excluded_count=None,
            blocked_count=None,
            requires_design_change_count=None,
            undetermined_count=None,
            reason_counts={},
        )
    guards, design, unknown = guards or {}, design or {}, unknown or {}
    old = old if old is not None else false()
    blocked = or_(false(), *guards.values())
    redesign = and_(~blocked, or_(false(), *design.values()))
    uncertain = and_(~blocked, ~redesign, or_(false(), *unknown.values()))
    candidate = and_(old, ~blocked, ~redesign, ~uncertain)

    def count(predicate):
        return func.coalesce(func.sum(case((predicate, 1), else_=0)), 0)

    expressions = {
        "inspected_count": func.count(),
        "past_retention_count": count(old),
        "candidate_count": count(candidate),
        "blocked_count": count(and_(old, blocked)),
        "requires_design_change_count": count(and_(old, redesign)),
        "undetermined_count": count(and_(old, uncertain)),
        "excluded_count": count(or_(~old, and_(old, or_(blocked, redesign)))),
    }
    reasons = {"WITHIN_RETENTION_OR_FUTURE": ~old}
    reasons.update({k: and_(old, v) for k, v in {**guards, **design, **unknown}.items()})
    row = (
        session.execute(
            select(
                *(v.label(k) for k, v in expressions.items()),
                *(count(v).label("r_" + k) for k, v in reasons.items()),
            )
            .select_from(join if join is not None else table)
            .where(scoped)
        )
        .mappings()
        .one()
    )
    return TargetReview(
        **base,
        inspection="INSPECTED",
        **{k: int(row[k]) for k in expressions},
        reason_counts={k: int(row["r_" + k]) for k in reasons if row["r_" + k]},
    )


def build_report(session, user, body: RetentionRequest):
    selected, scope = scope_for(session, user, body)
    snapshot = session.info["snapshot_as_of"]
    if body.as_of > snapshot:
        raise APIError(422, "RETENTION_AS_OF_IN_FUTURE")
    raw_cut = body.as_of - timedelta(days=body.policy.raw_days)
    agg_cut = body.as_of - timedelta(days=body.policy.aggregate_days)
    targets = []
    guards = ticket_guards(body.as_of)
    # No content column is selected; JSON copies are inventoried, not fetched.
    for table, fields in [
        (m.messages, ["body"]),
        (m.ai_suggestions, ["draft", "order_snapshot", "evidence_refs", "gate_results"]),
        (m.approvals, ["gate_snapshot"]),
        (m.followup_actions, ["public_note", "internal_note"]),
        (idempotency_keys, ["response_snapshot"]),
        (m.audit_events, ["payload"]),
        (m.tickets, ["issue_tags", "primary_issue", "last_error_code"]),
    ]:
        t = m.tickets
        join = table if table is t else table.join(t, table.c.ticket_id == t.c.ticket_id)
        age_fields = [table.c.created_at]
        if "updated_at" in table.c:
            age_fields.append(table.c.updated_at)
        age_fields += [t.c.updated_at, func.coalesce(t.c.resolved_at, t.c.updated_at)]
        old = and_(*(c < raw_cut for c in age_fields))
        specific = dict(guards)
        design = {}
        unknown = {"RESOLUTION_TIME_UNKNOWN": and_(t.c.status == "RESOLVED", t.c.resolved_at.is_(None))}
        if "cycle_no" in table.c:
            specific["CURRENT_OR_FUTURE_CYCLE"] = or_(
                table.c.cycle_no.is_(None), table.c.cycle_no >= t.c.cycle_no
            )
        if table is m.messages:
            specific["QUALITY_QUESTION_REFERENCE"] = exists(
                select(1).where(qa_replies.c.source_message_id == table.c.message_id)
            ).correlate(table)
            specific["JOB_SOURCE_MESSAGE_REFERENCE"] = exists(
                select(1).where(m.automation_jobs.c.source_message_id == table.c.message_id)
            ).correlate(table)
        if table is m.ai_suggestions:
            specific["SUGGESTION_APPROVAL_REFERENCE"] = exists(
                select(1).where(m.approvals.c.suggestion_id == table.c.suggestion_id)
            ).correlate(table)
            # JSON references are not FK-complete; masked snapshots can be stale.
            unknown["JSON_REFERENCE_AND_LEGAL_HOLD_REVIEW_REQUIRED"] = true()
        if table in (m.approvals, m.followup_actions, idempotency_keys, m.audit_events, t):
            design["WORKFLOW_REFERENCE_RETENTION_NOT_DEFINED"] = true()
        if table is idempotency_keys:
            specific["IDEMPOTENCY_RETRY_REFERENCE"] = true()
        if table is m.audit_events:
            design["AUDIT_RETENTION_NOT_DEFINED"] = true()
        # Classification is a preliminary content retention review, never a
        # row-delete decision. Absence of a modeled hold is not proof of no hold.
        unknown["LEGAL_HOLD_AND_CONTENT_REFERENCE_NOT_MODELLED"] = true()
        targets.append(
            inspect(
                session,
                table=table,
                fields=fields,
                data_class="RAW_OR_EXTRACT",
                age_basis="max(row.created_at, row.updated_at if present, ticket.updated_at, coalesce(ticket.resolved_at,ticket.updated_at))",
                cutoff=raw_cut,
                scoped=scope,
                join=join,
                old=old,
                guards=specific,
                design=design,
                unknown=unknown,
            )
        )
    if body.scope == "GLOBAL":
        # Product followups, null-ticket audits and snapshots are not silently
        # dropped by ticket joins. Independently report unattributable rows.
        for table, fields in [
            (m.followup_actions, ["public_note", "internal_note"]),
            (idempotency_keys, ["response_snapshot"]),
            (m.audit_events, ["payload"]),
        ]:
            item = inspect(
                session,
                table=table,
                fields=fields,
                data_class="RAW_OR_EXTRACT",
                age_basis="row.created_at (ticket_id IS NULL)",
                cutoff=raw_cut,
                scoped=table.c.ticket_id.is_(None),
                old=table.c.created_at < raw_cut,
                guards={
                    "VOC_IMPROVEMENT_PROFILE_REFERENCE": exists(
                        select(1).where(voc_profiles.c.action_id == m.followup_actions.c.action_id)
                    ).correlate(m.followup_actions)
                }
                if table is m.followup_actions
                else {},
                unknown={"NO_TICKET_CUSTODY_OR_POLICY": true()},
            )
            item.target += ":without_ticket"
            targets.append(item)
    # Exact-scope analytics cannot make the entire immutable receipt or shared
    # batch/PK deletable. Team reviews disclose neither counts nor IDs here.
    b = m.analytics_batches
    is_current = or_(
        b.c.is_current, exists(select(1).where(analytics_publication.c.batch_id == b.c.batch_id)).correlate(b)
    )
    published = or_(b.c.published_at.is_not(None), b.c.status == "SUCCEEDED")
    for table, fields, clock, kind in [
        (b, ["manifest", "row_counts", "checksums"], b.c.created_at, "AGGREGATE"),
        (
            analytics_receipts,
            ["payload", "validation_result"],
            analytics_receipts.c.received_at,
            "RAW_OR_EXTRACT",
        ),
        (
            m.analytics_daily,
            ["ticket_count", "duration_sum_seconds", "duration_n"],
            m.analytics_daily.c.created_at,
            "AGGREGATE",
        ),
        (
            m.analytics_product_daily,
            ["ticket_count", "paid_order_count"],
            m.analytics_product_daily.c.created_at,
            "AGGREGATE",
        ),
        (
            m.analytics_product_voc_daily,
            ["episode_count", "unresolved_count"],
            m.analytics_product_voc_daily.c.created_at,
            "AGGREGATE",
        ),
        (
            m.analytics_product_risk,
            ["metrics", "components", "score", "rank"],
            m.analytics_product_risk.c.created_at,
            "AGGREGATE",
        ),
    ]:
        cutoff = raw_cut if kind == "RAW_OR_EXTRACT" else agg_cut
        targets.append(
            inspect(
                session,
                table=table,
                fields=fields,
                data_class=kind,
                age_basis=str(clock) + " (storage clock, not source_as_of/day)",
                cutoff=cutoff,
                join=table if table is b else table.join(b),
                old=clock < cutoff,
                guards={
                    "CURRENT_ANALYTICS_BATCH": is_current,
                    "VOC_PLAN_SOURCE_BATCH_REFERENCE": exists(
                        select(1).where(voc_plans.c.source_batch_id == b.c.batch_id)
                    ).correlate(b),
                },
                design={
                    "PUBLISHED_IMMUTABILITY_TRIGGER": published,
                    "RECEIPT_IMMUTABILITY_TRIGGER": true() if table is analytics_receipts else false(),
                    "BATCH_RECEIPT_FK_AND_REPUBLICATION_DESIGN": true(),
                },
                supported=body.scope == "GLOBAL",
            )
        )
    for table, fields, clock in [
        (
            qa_replies,
            ["reply_sha256", "question_sha256", "suggestion_id", "approval_id"],
            qa_replies.c.committed_at,
        ),
        (qa_evidence, ["document_id", "document_version", "content_hash"], None),
        (qa_samples, ["message_id", "review_team_id", "rubric_version"], qa_samples.c.selected_at),
        (qa_revisions, ["reason_codes", "change_reason"], qa_revisions.c.recorded_at),
        (qa_receipts, ["request_hash"], qa_receipts.c.created_at),
        (voc_profiles, ["product_id", "current_plan_revision"], voc_profiles.c.created_at),
        (
            voc_plans,
            ["improvement_text", "change_reason", "source_batch_id", "source_scope_key"],
            voc_plans.c.created_at,
        ),
        (voc_teams, ["team_id"], None),
        (voc_links, ["ticket_id"], voc_links.c.linked_at),
        (voc_receipts, ["response_snapshot", "request_hash"], voc_receipts.c.created_at),
    ]:
        targets.append(
            inspect(
                session,
                table=table,
                fields=fields,
                data_class="RAW_OR_EXTRACT",
                age_basis=str(clock) if clock is not None else "NO_APPROVED_RETENTION_CLOCK",
                cutoff=raw_cut if clock is not None else None,
                old=clock < raw_cut if clock is not None else false(),
                guards={
                    "QUALITY_WORKFLOW_HISTORY_REFERENCE"
                    if table.name.startswith(("quality_", "automatic_reply_"))
                    else "VOC_WORKFLOW_HISTORY_REFERENCE": true()
                },
                design={
                    "QUALITY_RETENTION_POLICY_NOT_DEFINED"
                    if table.name.startswith(("quality_", "automatic_reply_"))
                    else "VOC_RETENTION_POLICY_NOT_DEFINED": true()
                },
                supported=body.scope == "GLOBAL",
            )
        )
    # Other raw/JSON locations and reference catalogs have no agreed lifetime.
    # Inspect only row counts globally, never their contents or credentials.
    for table, fields in [
        (m.customers, ["profile_masked", "customer_key", "display_name"]),
        (m.orders, ["order_number", "amount"]),
        (m.shipments, ["eta_if_known"]),
        (m.returns, ["reason"]),
        (m.knowledge_documents, ["body", "blob_path", "version"]),
        (m.automation_rules, ["conditions", "version"]),
        (m.users, ["login_name", "password_hash", "allowed_team_ids"]),
        (m.assignments, ["ticket_id", "cycle_no", "team_id"]),
        (m.automation_jobs, ["source_message_id", "error_code", "lease_token"]),
        (queue_routes, ["ticket_id", "cycle_no", "team_id"]),
        (qa_rubrics, ["criteria"]),
    ]:
        targets.append(
            inspect(
                session,
                table=table,
                fields=fields,
                data_class="REFERENCE_OR_METADATA",
                age_basis="NO_APPROVED_RETENTION_CLOCK",
                old=true(),
                guards={
                    "QUALITY_POLICY_EVIDENCE_REFERENCE": exists(
                        select(1).where(qa_evidence.c.document_id == m.knowledge_documents.c.document_id)
                    ).correlate(m.knowledge_documents)
                }
                if table is m.knowledge_documents
                else {},
                unknown={"REFERENCE_OR_PROFILE_RETENTION_NOT_DEFINED": true()},
                supported=body.scope == "GLOBAL",
            )
        )
    not_inspected = [
        ExternalStore(store=s, reason=r)
        for s, r in [
            ("BLOB_AND_EXTERNAL_EXTRACTS", "OUTSIDE_LOCAL_DATABASE_NO_CONNECTION"),
            ("FABRIC_BRONZE_SILVER_GOLD", "OUTSIDE_LOCAL_DATABASE_NO_CONNECTION"),
            ("BACKUPS_REPLICAS_WAL", "NO_BACKUP_OR_PHYSICAL_STORAGE_INSPECTION"),
            ("API_POSTGRES_AND_EXTERNAL_LOGS", "NOT_A_RETENTION_CONTENT_SCAN"),
            ("LOCAL_FILES_EXPORTS_CACHES", "NO_FILESYSTEM_CONTENT_SCAN"),
            (
                "LOCAL_TEAMS_PRODUCTS_SCOPE_CAPABILITIES_PUBLICATION_CONTROL_HISTORY",
                "REFERENCE_METADATA_OUTSIDE_CONTENT_RETENTION_POLICY; NO_CONTENT_SCAN",
            ),
        ]
    ]
    policy_hash = digest(
        {
            **body.policy.model_dump(),
            "clock_contract": "STORAGE_AND_TICKET_ACTIVITY_V1",
            "boundary": "STRICT_UTC_24H",
        }
    )
    payload = dict(
        as_of=body.as_of,
        snapshot_at=snapshot,
        policy=body.policy,
        policy_hash=policy_hash,
        scope=body.scope,
        team_ids=selected,
        targets=targets,
        not_inspected=not_inspected,
        limitations=[
            "NO_ROW_IDS_OR_CONTENT_READS_OR_DELETE_COMMANDS",
            "PAST_RETENTION_IS_AN_AGE_MATCH_NOT_DELETION_ELIGIBILITY",
            "LEGAL_HOLDS_AND_UNSTRUCTURED_JSON_REFERENCES_NOT_FULLY_MODELLED; NO_FINAL_CANDIDATES",
            "REASONS_OVERLAP; CLASSIFICATION_COUNTS_ARE_DISJOINT",
            "UNSUPPORTED_TEAM_TARGETS_HAVE_NULL_COUNTS; HIDDEN_CUSTODY_NOT_COUNTED",
            "REFERENCE_TARGET_PAST_RETENTION_COUNT_IS_ZERO_WITHOUT_AN_APPROVED_CLOCK",
            "FUTURE_EXECUTION_REQUIRES_NEW_AUTHORIZATION_SNAPSHOT_AND_REFERENCE_CHECKS",
            "NOT_LEGAL_COMPLIANCE_OR_FABRIC_B_AI_INTEGRATION_VERIFICATION",
        ],
    )
    # Reference objects are undetermined, not artificially aged by this policy.
    for item in targets:
        if item.data_class == "REFERENCE_OR_METADATA" and item.inspection == "INSPECTED":
            item.past_retention_count = 0
    fingerprint = digest(
        {
            "actor": user["user_id"],
            "as_of": body.as_of.isoformat(),
            "policy_hash": policy_hash,
            "scope": body.scope,
            "teams": selected,
            "targets": [v.model_dump(mode="json") for v in targets],
        }
    )
    audit.record(
        session, user["user_id"], "RETENTION_DRY_RUN", "RETENTION_REVIEW", None, reason=body.purpose_code
    )
    return RetentionReport(**payload, result_fingerprint=fingerprint)
