"""Atomic product followup wrappers; no effect calculation or B execution.

Writes: actor -> (linked ticket) -> product -> followup -> profile.
The request session commits; every command savepoint includes audit+receipt.
"""

from sqlalchemy import and_, exists, select

from app import analytics_views, audit, followups
from app import repository as repo
from app.analytics_canonical import digest
from app.automation_control import capability
from app.db import utcnow
from app.errors import APIError, denied
from app.models import followup_actions as actions
from app.models import tickets, users
from app.voc_models import plan_teams, plans, profiles, receipts, ticket_links
from app.voc_schemas import ImprovementReceipt, PlanValues


def authorize(session, user, *, write=False):
    if write:
        fresh = (
            session.execute(
                select(users).where(users.c.user_id == user["user_id"]).with_for_update(key_share=True)
            )
            .mappings()
            .one()
        )
        if not fresh["active"]:
            raise APIError(401, "INVALID_CREDENTIALS")
        user = fresh
    capability(session, user, "VOC_IMPROVEMENT_MANAGE", admin=True)
    return user


def action_for(session, user, action_id, *, write=False, profile=True):
    hint = repo.row(session, actions, actions.c.action_id == action_id, followups.scope(user))
    if not hint:
        raise denied(user["user_id"], "VOC_IMPROVEMENT", action_id)
    if write:
        followups.lock_parent(session, hint["ticket_id"], hint["product_id"])
        hint = (
            session.execute(
                select(actions)
                .where(actions.c.action_id == action_id, followups.scope(user))
                .with_for_update()
            )
            .mappings()
            .first()
        )
        if not hint:
            raise denied(user["user_id"], "VOC_IMPROVEMENT", action_id)
    if hint["product_id"] is None or hint["ticket_id"] is not None or hint["blocks_resolution"]:
        raise APIError(409, "VOC_PRODUCT_FOLLOWUP_REQUIRED")
    p = repo.row(session, profiles, profiles.c.action_id == action_id)
    if profile and not p:
        raise denied(user["user_id"], "VOC_IMPROVEMENT", action_id)
    return hint, p


def visible_plan(user):
    outside = exists(
        select(1).where(
            plan_teams.c.action_id == plans.c.action_id,
            plan_teams.c.revision == plans.c.revision,
            ~followups.team_scope(user, plan_teams.c.team_id),
        )
    ).correlate(plans)
    return and_(~outside, followups.team_scope(user, plans.c.owner_team_id_snapshot))


def plan_for(session, user, action_id, revision):
    return repo.row(
        session, plans, plans.c.action_id == action_id, plans.c.revision == revision, visible_plan(user)
    )


def plan_view(session, p):
    return {
        **{k: v for k, v in p.items() if k != "action_id"},
        "comparison_team_ids": sorted(
            session.scalars(
                select(plan_teams.c.team_id).where(
                    plan_teams.c.action_id == p["action_id"], plan_teams.c.revision == p["revision"]
                )
            )
        ),
    }


def check_ticket(session, user, ticket_id, product_id, *, lock=False):
    query = select(tickets).where(tickets.c.ticket_id == ticket_id, repo.ticket_scope(user))
    if lock:
        query = query.with_for_update()
    ticket = session.execute(query).mappings().first()
    if not ticket:
        raise denied(user["user_id"], "TICKET", ticket_id)
    if ticket["product_id"] is None or ticket["product_id"] != product_id:
        raise APIError(409, "VOC_TICKET_PRODUCT_MISMATCH")
    return ticket


def replay(session, user, key, operation, body, action_id=None):
    request_hash = digest(
        {"operation": operation, "action_id": action_id, "body": body.model_dump(mode="json")}
    )
    old = repo.row(session, receipts, receipts.c.user_id == user["user_id"], receipts.c.key == key)
    if old:
        # Re-authorize even a byte-identical retry before returning the original IDs.
        action, _ = action_for(session, user, old["action_id"])
        if not plan_for(session, user, old["action_id"], old["plan_revision"]):
            raise denied(user["user_id"], "VOC_IMPROVEMENT", old["action_id"])
        if old["ticket_id"]:
            check_ticket(session, user, old["ticket_id"], action["product_id"])
        if old["request_hash"] != request_hash or old["operation"] != operation:
            raise APIError(409, "IDEMPOTENCY_CONFLICT")
        return request_hash, old["response_snapshot"]
    return request_hash, None


def save_receipt(session, user, key, operation, request_hash, result):
    session.execute(
        receipts.insert().values(
            user_id=user["user_id"],
            key=key,
            operation=operation,
            request_hash=request_hash,
            action_id=result["action_id"],
            plan_revision=result["plan_revision"],
            ticket_id=result.get("ticket_id"),
            response_snapshot=result,
            created_at=utcnow(),
        )
    )


def validate_plan(session, user, body, owner_team, product_id, settings):
    for team in body.comparison_team_ids:
        followups.check_team(session, user, str(team))
    if owner_team not in set(map(str, body.comparison_team_ids)):
        raise APIError(422, "VOC_OWNER_TEAM_OUTSIDE_COMPARISON")
    if body.implemented_at and body.implemented_at > utcnow():
        raise APIError(422, "VOC_IMPLEMENTED_AT_IN_FUTURE")
    if body.source_batch_id:
        session.info.setdefault("snapshot_as_of", utcnow())
        source = analytics_views.resolve_snapshot(
            session, user, settings, body.comparison_team_ids, body.source_batch_id
        )
        if source["availability"] != "AVAILABLE" or source["scope_key"] != body.source_scope_key:
            raise APIError(422, "VOC_SOURCE_EXACT_SCOPE_REQUIRED")
        if product_id not in source["manifest"]["product_ids"]:
            raise APIError(422, "VOC_SOURCE_PRODUCT_NOT_PROVIDED")
        # A published source remains valid even after it leaves the current TOP10.


def append_plan(session, user, action, revision, body, kind):
    values = body.model_dump(mode="python", include=set(PlanValues.model_fields))
    teams = values.pop("comparison_team_ids")
    values["source_batch_id"] = str(body.source_batch_id) if body.source_batch_id else None
    session.execute(
        plans.insert().values(
            **values,
            action_id=action["action_id"],
            revision=revision,
            owner_team_id_snapshot=action["owner_team_id"],
            change_kind=kind,
            created_by=user["user_id"],
            created_at=utcnow(),
        )
    )
    session.execute(
        plan_teams.insert(),
        [{"action_id": action["action_id"], "revision": revision, "team_id": str(team)} for team in teams],
    )


def receipt(action, plan_revision, ticket_id=None):
    return ImprovementReceipt(
        action_id=action["action_id"],
        action_revision=action["version"],
        plan_revision=plan_revision,
        ticket_id=ticket_id,
    ).model_dump(mode="json")


def create(session, user, body, key, settings):
    user = authorize(session, user, write=True)
    request_hash, old = replay(session, user, key, "CREATE", body)
    if old:
        return old, True
    with session.begin_nested():
        if body.followup:
            parent, tid, pid = followups.prepare_create(session, user, body.followup)
            made = followups.persist_create(session, user, body.followup, parent, tid, pid)
            action = repo.row(session, actions, actions.c.action_id == made["action_id"])
        else:
            action, existing = action_for(
                session, user, str(body.existing_action_id), write=True, profile=False
            )
            if existing:
                raise APIError(409, "VOC_PROFILE_ALREADY_EXISTS")
            if action["version"] != body.expected_action_revision:
                raise APIError(409, "FOLLOWUP_REVISION_CONFLICT")
        if action["status"] not in followups.ACTIVE:
            raise APIError(409, "FOLLOWUP_TERMINAL")
        validate_plan(session, user, body.plan, action["owner_team_id"], action["product_id"], settings)
        session.execute(
            profiles.insert().values(
                action_id=action["action_id"],
                product_id=action["product_id"],
                current_plan_revision=1,
                created_by=user["user_id"],
                created_at=utcnow(),
            )
        )
        append_plan(session, user, action, 1, body.plan, "INITIAL")
        result = receipt(action, 1)
        audit.record(session, user["user_id"], "VOC_IMPROVEMENT_CREATED", "FOLLOWUP", action["action_id"])
        save_receipt(session, user, key, "CREATE", request_hash, result)
    return result, False


def add_plan(session, user, action_id, body, key, settings):
    user = authorize(session, user, write=True)
    request_hash, old = replay(session, user, key, "PLAN", body, action_id)
    if old:
        return old, True
    with session.begin_nested():
        action, p = action_for(session, user, action_id, write=True)
        check_revisions(action, p, body)
        terminal = action["status"] not in followups.ACTIVE
        if terminal != body.correction:
            raise APIError(409, "VOC_TERMINAL_CORRECTION_REQUIRED" if terminal else "VOC_NOT_TERMINAL")
        if terminal:
            current = plan_for(session, user, action_id, p["current_plan_revision"])
            if not current:
                raise denied(user["user_id"], "VOC_IMPROVEMENT", action_id)
            old_plan = PlanValues.model_validate(
                {k: v for k, v in plan_view(session, current).items() if k in PlanValues.model_fields}
            )
            fields = {
                "issue_code",
                "improvement_text",
                "comparison_team_ids",
                "source_batch_id",
                "source_scope_key",
            }
            if old_plan.model_dump(include=fields) != body.model_dump(include=fields):
                raise APIError(409, "VOC_CORRECTION_FACTS_ONLY")
        validate_plan(session, user, body, action["owner_team_id"], action["product_id"], settings)
        rev = p["current_plan_revision"] + 1
        append_plan(session, user, action, rev, body, "CORRECTION" if terminal else "PLAN")
        session.execute(
            profiles.update().where(profiles.c.action_id == action_id).values(current_plan_revision=rev)
        )
        result = receipt(action, rev)
        audit.record(
            session,
            user["user_id"],
            "VOC_PLAN_CORRECTED" if terminal else "VOC_PLAN_ADDED",
            "FOLLOWUP",
            action_id,
        )
        save_receipt(session, user, key, "PLAN", request_hash, result)
    return result, False


def check_revisions(action, p, body):
    if action["version"] != body.expected_action_revision:
        raise APIError(409, "FOLLOWUP_REVISION_CONFLICT")
    if p["current_plan_revision"] != body.expected_plan_revision:
        raise APIError(409, "VOC_PLAN_REVISION_CONFLICT")


def link_ticket(session, user, action_id, body, key):
    user = authorize(session, user, write=True)
    request_hash, old = replay(session, user, key, "LINK", body, action_id)
    if old:
        return old, True
    with session.begin_nested():
        hint, _ = action_for(session, user, action_id)
        check_ticket(session, user, str(body.ticket_id), hint["product_id"], lock=True)
        action, p = action_for(session, user, action_id, write=True)
        check_revisions(action, p, body)
        if action["status"] not in followups.ACTIVE:
            raise APIError(409, "FOLLOWUP_TERMINAL")
        if not plan_for(session, user, action_id, p["current_plan_revision"]):
            raise denied(user["user_id"], "VOC_IMPROVEMENT", action_id)
        if not repo.row(
            session,
            ticket_links,
            ticket_links.c.action_id == action_id,
            ticket_links.c.ticket_id == str(body.ticket_id),
        ):
            session.execute(
                ticket_links.insert().values(
                    action_id=action_id,
                    ticket_id=str(body.ticket_id),
                    linked_by=user["user_id"],
                    linked_at=utcnow(),
                )
            )
        result = receipt(action, p["current_plan_revision"], str(body.ticket_id))
        audit.record(session, user["user_id"], "VOC_TICKET_LINKED", "FOLLOWUP", action_id)
        save_receipt(session, user, key, "LINK", request_hash, result)
    return result, False


def view(session, user, action, p):
    current = plan_for(session, user, p["action_id"], p["current_plan_revision"])
    return dict(
        action_id=p["action_id"],
        product_id=p["product_id"],
        followup=followups.staff_view(session, action),
        current_plan_revision=p["current_plan_revision"],
        current_plan=plan_view(session, current) if current else None,
        plan_access="AVAILABLE" if current else "COMPARISON_SCOPE_DENIED",
        plan_refresh_required=not current or current["owner_team_id_snapshot"] != action["owner_team_id"],
    )


def list_improvements(session, user, limit, cursor, *, product_id=None, status=None):
    authorize(session, user)
    predicates = [followups.scope(user), exists(select(1).where(profiles.c.action_id == actions.c.action_id))]
    if product_id:
        predicates.append(actions.c.product_id == product_id)
    if status:
        predicates.append(actions.c.status == status)
    rows, cursor = repo.page_rows(
        session, actions, and_(*predicates), actions.c.created_at, actions.c.action_id, limit, cursor
    )
    items = [
        view(session, user, a, repo.row(session, profiles, profiles.c.action_id == a["action_id"]))
        for a in rows
    ]
    audit.record(session, user["user_id"], "VOC_IMPROVEMENT_LIST", "FOLLOWUP", None)
    return {"items": items, "next_cursor": cursor}


def detail(
    session, user, action_id, *, plan_limit=20, plan_before_revision=None, ticket_limit=20, ticket_cursor=None
):
    authorize(session, user)
    action, p = action_for(session, user, action_id)
    query = select(plans).where(plans.c.action_id == action_id, visible_plan(user))
    if plan_before_revision is not None:
        query = query.where(plans.c.revision < plan_before_revision)
    history = list(session.execute(query.order_by(plans.c.revision.desc()).limit(plan_limit + 1)).mappings())
    link_scope = exists(
        select(1).where(
            tickets.c.ticket_id == ticket_links.c.ticket_id,
            tickets.c.product_id == p["product_id"],
            repo.ticket_scope(user),
        )
    )
    links, cursor = repo.page_rows(
        session,
        ticket_links,
        and_(ticket_links.c.action_id == action_id, link_scope),
        ticket_links.c.linked_at,
        ticket_links.c.ticket_id,
        ticket_limit,
        ticket_cursor,
    )
    audit.record(session, user["user_id"], "VOC_IMPROVEMENT_READ", "FOLLOWUP", action_id)
    return {
        **view(session, user, action, p),
        "plans": [plan_view(session, r) for r in history[:plan_limit]],
        "next_plan_before_revision": history[plan_limit - 1]["revision"]
        if len(history) > plan_limit
        else None,
        "tickets": [{"ticket_id": r["ticket_id"], "linked_at": r["linked_at"]} for r in links],
        "next_ticket_cursor": cursor,
    }
