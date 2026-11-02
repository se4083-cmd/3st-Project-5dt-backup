"""Operational facts over one authorized ticket set, read in a repeatable snapshot."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import and_, select

from app import audit, followups, services
from app import repository as repo
from app.db import utcnow
from app.errors import APIError, denied
from app.followup_schemas import FollowupStaff
from app.model_constraints import user_team_scopes
from app.models import assignments, customers, followup_actions, tickets
from app.schemas import Input, Page, TicketPublic


class ViewPurpose(Input):
    purpose_code: Literal["ACTIVE_SUPPORT", "FOLLOWUP_REVIEW", "QUALITY_REVIEW"]


class AssignmentFact(BaseModel):
    assignment_id: UUID
    team_id: UUID | None
    agent_id: UUID | None
    assigned_at: datetime


class HistoryTicket(TicketPublic):
    category: str
    current_assignment: AssignmentFact | None


class SourceRef(BaseModel):
    ref: str
    ticket_id: UUID
    revision: int
    cycle_no: int


class SafeSummaryInput(BaseModel):
    total_tickets: int
    unresolved_tickets: int
    reopened_tickets: int
    additional_cycles: int
    automated: int
    human: int


class SummaryContract(BaseModel):
    status: Literal["NOT_GENERATED"] = "NOT_GENERATED"
    version: Literal["customer360-v1"] = "customer360-v1"
    cache_fingerprint: str
    external_input: SafeSummaryInput
    sources: list[SourceRef]


class Customer360(BaseModel):
    customer_id: UUID
    as_of: datetime
    scope_policy: Literal["per-ticket-v1"] = "per-ticket-v1"
    total_ticket_count: int
    category_counts: dict[str, int]
    handling_counts: dict[str, int]
    unresolved_ticket_count: int
    reopened_ticket_count: int
    additional_cycle_count: int
    recent_tickets: list[HistoryTicket]
    unresolved_tickets: list[HistoryTicket]
    followup_count: int
    followups: Page[FollowupStaff]
    facts: list[str] = Field(min_length=3, max_length=3)
    summary_contract: SummaryContract


def visible_tickets(session, user, customer_id, purpose):
    followups.require_staff(user)
    if purpose.purpose_code == "QUALITY_REVIEW" and user["role"] != "ADMIN":
        raise APIError(403, "PURPOSE_NOT_ALLOWED", user["user_id"], "CUSTOMER", customer_id)
    if not repo.row(
        session, customers, customers.c.customer_id == customer_id, customers.c.deleted_at.is_(None)
    ):
        raise denied(user["user_id"], "CUSTOMER", customer_id)
    rows = list(
        session.execute(
            select(tickets)
            .where(tickets.c.customer_id == customer_id, repo.ticket_scope(user))
            .order_by(tickets.c.created_at.desc(), tickets.c.ticket_id.desc())
        ).mappings()
    )
    if not rows:
        raise denied(user["user_id"], "CUSTOMER", customer_id)
    return rows


def assignment_rows(session, ticket_ids):
    return list(
        session.execute(
            select(assignments)
            .join(tickets, assignments.c.ticket_id == tickets.c.ticket_id)
            .where(
                tickets.c.ticket_id.in_(ticket_ids),
                assignments.c.cycle_no == tickets.c.cycle_no,
                assignments.c.team_id == tickets.c.team_id,
                assignments.c.ended_at.is_(None),
                assignments.c.assigned_at <= utcnow(),
                tickets.c.status.in_(["ASSIGNED", "IN_PROGRESS", "FOLLOWUP_PENDING", "WAITING_CUSTOMER"]),
            )
            .order_by(assignments.c.assignment_id)
        ).mappings()
    )


def ticket_fact(ticket, assignment_map):
    assignment = assignment_map.get(ticket["ticket_id"])
    return {
        **services.public_ticket(ticket),
        "category": ticket["category"],
        "current_assignment": assignment,
    }


def view(
    session, user, customer_id, purpose, *, kind="overview", limit=20, cursor=None, unresolved_only=False
):
    rows = visible_tickets(session, user, customer_id, purpose)
    ids = [t["ticket_id"] for t in rows]
    owned_followups = and_(followup_actions.c.ticket_id.in_(ids), followups.scope(user))
    if kind == "followups":
        items, next_cursor = repo.page_rows(
            session,
            followup_actions,
            owned_followups,
            followup_actions.c.created_at,
            followup_actions.c.action_id,
            limit,
            cursor,
        )
        result = {"items": [followups.staff_view(session, f) for f in items], "next_cursor": next_cursor}
    else:
        assignments_list = assignment_rows(session, ids)
        by_ticket = {a["ticket_id"]: dict(a) for a in assignments_list}
        if kind == "tickets":
            predicate = tickets.c.ticket_id.in_(ids)
            if unresolved_only:
                predicate = and_(predicate, tickets.c.status.not_in(["RESOLVED", "CANCELLED"]))
            items, next_cursor = repo.page_rows(
                session, tickets, predicate, tickets.c.created_at, tickets.c.ticket_id, limit, cursor
            )
            result = {"items": [ticket_fact(t, by_ticket) for t in items], "next_cursor": next_cursor}
        else:
            all_followups = list(
                session.execute(
                    select(followup_actions)
                    .where(owned_followups)
                    .order_by(followup_actions.c.created_at.desc(), followup_actions.c.action_id.desc())
                ).mappings()
            )
            categories, modes = {}, {"AUTOMATED": 0, "HUMAN": 0}
            unresolved = [t for t in rows if t["status"] not in {"RESOLVED", "CANCELLED"}]
            for t in rows:
                categories[t["category"]] = categories.get(t["category"], 0) + 1
                modes[services.public_ticket(t)["handling_mode"]] += 1
            repeated = sum(t["cycle_no"] > 1 for t in rows)
            extra_cycles = sum(t["cycle_no"] - 1 for t in rows)
            safe_input = {
                "total_tickets": len(rows),
                "unresolved_tickets": len(unresolved),
                "reopened_tickets": repeated,
                "additional_cycles": extra_cycles,
                "automated": modes["AUTOMATED"],
                "human": modes["HUMAN"],
            }
            # Includes scope membership, revisions and exact rendered evidence. No cache is stored.
            evidence = {
                "policy": "per-ticket-v1",
                "principal": {k: user[k] for k in ["user_id", "role", "team_id"]},
                "scopes": sorted(
                    session.scalars(
                        select(user_team_scopes.c.team_id).where(
                            user_team_scopes.c.user_id == user["user_id"]
                        )
                    ).all()
                ),
                "purpose": purpose.purpose_code,
                "tickets": [dict(t) for t in rows],
                "followups": [dict(f) for f in all_followups],
                "assignments": [dict(a) for a in assignments_list],
            }
            # Do not hash credentials: only identity/role/scopes and authorized operational evidence.
            fingerprint = hashlib.sha256(
                json.dumps(evidence, sort_keys=True, default=str, ensure_ascii=False).encode()
            ).hexdigest()
            first = all_followups[:20]
            more = (
                repo.encode_cursor(first[-1]["created_at"], first[-1]["action_id"])
                if len(all_followups) > 20
                else None
            )
            result = {
                "customer_id": customer_id,
                "as_of": session.info.get("snapshot_as_of", utcnow()),
                "total_ticket_count": len(rows),
                "category_counts": categories,
                "handling_counts": modes,
                "unresolved_ticket_count": len(unresolved),
                "reopened_ticket_count": repeated,
                "additional_cycle_count": extra_cycles,
                "recent_tickets": [ticket_fact(t, by_ticket) for t in rows[:5]],
                "unresolved_tickets": [ticket_fact(t, by_ticket) for t in unresolved[:5]],
                "followup_count": len(all_followups),
                "followups": {
                    "items": [followups.staff_view(session, f) for f in first],
                    "next_cursor": more,
                },
                "facts": [
                    f"허용된 티켓 {len(rows)}건 중 미해결 {len(unresolved)}건입니다.",
                    f"자동 경로 {modes['AUTOMATED']}건, 사람 경로 {modes['HUMAN']}건입니다.",
                    f"재문의 티켓 {repeated}건, 추가 회차 {extra_cycles}회입니다.",
                ],
                "summary_contract": {
                    "cache_fingerprint": fingerprint,
                    "external_input": safe_input,
                    "sources": [
                        {
                            "ref": f"T{i + 1}",
                            "ticket_id": t["ticket_id"],
                            "revision": t["version"],
                            "cycle_no": t["cycle_no"],
                        }
                        for i, t in enumerate(rows[:5])
                    ],
                },
            }
    audit.record(
        session, user["user_id"], "CUSTOMER360_READ", "CUSTOMER", customer_id, reason=purpose.purpose_code
    )
    return result
