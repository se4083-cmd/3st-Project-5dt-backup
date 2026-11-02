"""Display-only nested allowlist. Raw drafts, prompts and JSONB are never returned."""

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from app import audit, repository
from app.errors import APIError, denied
from app.models import ai_suggestions, approvals, automation_rules, knowledge_documents, orders, tickets
from app.schemas import Input


class DetailPurpose(Input):
    purpose_code: Literal["ACTIVE_SUPPORT", "QUALITY_REVIEW"]
    include_history: bool = False


class StaffOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class GateFacts(StaffOutput):
    ownership_valid: bool | None = None
    policy_valid: bool | None = None
    confidence_valid: bool | None = None
    pii_valid: bool | None = None
    risk_valid: bool | None = None
    no_money_execution: bool | None = None
    fixture_only: bool | None = None
    policy_valid_in_fixture: bool | None = None


class PolicyEvidence(StaffOutput):
    document_id: UUID
    policy_key: str | None
    version: int
    active_at_as_of: bool
    synthetic: bool


class MaskedOrder(StaffOutput):
    state: Literal["VERIFIED_LINK", "STALE_ORDER_SNAPSHOT"]
    masked_order_ref: str
    snapshot_version: int
    current_version: int
    facts_source: Literal["CURRENT_OPERATIONAL_DB"] = "CURRENT_OPERATIONAL_DB"
    order_status: str | None
    payment_status: str | None
    quantity: int


class ApprovalFact(StaffOutput):
    approval_id: UUID
    mode: Literal["SYSTEM", "HUMAN"] | None
    decision: Literal["APPROVED", "REJECTED", "PENDING", "NEEDS_HUMAN"] | None
    record_state: Literal[
        "SYNTHETIC_HISTORY",
        "HISTORICAL_CYCLE",
        "STALE_TICKET_VERSION",
        "EXPIRED",
        "POLICY_INACTIVE",
        "UNVERIFIED_LINKS",
        "NOT_YET_EFFECTIVE",
        "CURRENT_RECORDED",
    ]
    reviewed_at: datetime
    expires_at: datetime
    gates: GateFacts
    usable_for_execution: Literal[False] = False


class ProposalFact(StaffOutput):
    suggestion_id: UUID
    cycle_no: int
    revision: int
    synthetic: bool
    record_state: Literal["CURRENT_CYCLE", "HISTORICAL_CYCLE", "SYNTHETIC_HISTORY", "INVALID_LINK"]
    category: str | None = None
    confidence: float | None = None
    template_key: str | None = None
    prompt_version: str | None = None
    model_version: str | None = None
    rule_version: int | None = None
    rule_active: bool | None = None
    evidence_state: Literal["MISSING", "VERIFIED_REFERENCES", "PARTIAL_OR_INVALID"] = "MISSING"
    evidence: list[PolicyEvidence] = []
    gates: GateFacts | None = None
    masked_order: MaskedOrder | None = None
    order_snapshot_state: Literal["MISSING", "INVALID_LINK", "VERIFIED_LINK", "STALE_ORDER_SNAPSHOT"] = (
        "MISSING"
    )
    approvals: list[ApprovalFact] = []
    invalid_approval_links: bool = False
    approvals_truncated: bool = False
    draft_exposed: Literal[False] = False


class StaffTicketDetail(StaffOutput):
    ticket_id: UUID
    customer_ref: UUID
    cycle_no: int
    revision: int
    as_of: datetime
    material_status: Literal["MISSING", "SYNTHETIC_ONLY", "RECORDED_FACTS"]
    current_proposals: list[ProposalFact]
    historical_proposals: list[ProposalFact]
    history_included: bool
    truncated: bool
    execution_authority: Literal["DISPLAY_ONLY_NOT_AUTHORIZATION"] = "DISPLAY_ONLY_NOT_AUTHORIZATION"


def safe_code(value):
    return (
        value
        if isinstance(value, str)
        and not any(
            word in value.lower() for word in ("password", "secret", "token", "connection", "api_key")
        )
        and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,47}(?:\.[0-9]{1,8}){0,2}", value)
        else None
    )


def gates(value):
    value = value if isinstance(value, dict) else {}
    return GateFacts(**{k: v for k, v in value.items() if k in GateFacts.model_fields and type(v) is bool})


def evidence(session, value, as_of, category):
    if not isinstance(value, list) or not value:
        return [], "MISSING"
    result = []
    invalid = len(value) > 10
    seen = set()
    for item in value[:10]:
        try:
            did = str(UUID(item["document_id"]))
            version = item["version"]
            if type(version) is not int or not 1 <= version <= 10**9:
                raise ValueError()
            document = repository.row(session, knowledge_documents, knowledge_documents.c.document_id == did)
            if (
                not document
                or document["version"] != version
                or document["content_hash"] != item.get("content_hash")
                or did in seen
                or not isinstance(document["allowed_topics"], list)
                or category not in document["allowed_topics"]
            ):
                raise ValueError()
            seen.add(did)
            result.append(
                PolicyEvidence(
                    document_id=did,
                    policy_key=safe_code(document["policy_key"]),
                    version=version,
                    active_at_as_of=bool(
                        document["active"]
                        and document["approval_status"] == "APPROVED"
                        and document["effective_from"] <= as_of
                        and (document["effective_to"] is None or document["effective_to"] > as_of)
                    ),
                    synthetic=document["data_origin"] == "SYNTHETIC",
                )
            )
        except (KeyError, TypeError, ValueError, AttributeError):
            invalid = True
    return result, "PARTIAL_OR_INVALID" if invalid else "VERIFIED_REFERENCES"


def order_fact(session, ticket, value):
    if value is None:
        return None, "MISSING"
    if not isinstance(value, dict) or not ticket["order_id"]:
        return None, "INVALID_LINK"
    try:
        if (
            str(UUID(value["order_id"])) != ticket["order_id"]
            or type(value["version"]) is not int
            or not 1 <= value["version"] <= 10**9
        ):
            raise ValueError()
        row = repository.row(
            session,
            orders,
            orders.c.order_id == ticket["order_id"],
            orders.c.customer_id == ticket["customer_id"],
            orders.c.product_id == ticket["product_id"],
        )
        if not row:
            raise ValueError()
        state = "VERIFIED_LINK" if value["version"] == row["version"] else "STALE_ORDER_SNAPSHOT"
        return MaskedOrder(
            state=state,
            masked_order_ref="****" + row["order_id"][-4:],
            snapshot_version=value["version"],
            current_version=row["version"],
            order_status=row["order_status"]
            if row["order_status"]
            in {"PLACED", "PAID", "SHIPPED", "DELIVERED", "CANCELLED", "COMPLETED", "RETURNED"}
            else None,
            payment_status=row["payment_status"]
            if row["payment_status"] in {"PAID", "PENDING", "FAILED", "REFUNDED", "UNPAID"}
            else None,
            quantity=row["quantity"],
        ), state
    except (ValueError, TypeError, KeyError):
        return None, "INVALID_LINK"


def proposal_fact(session, ticket, row, as_of):
    historical = row["cycle_no"] != ticket["cycle_no"]
    synthetic = row["data_origin"] == "SYNTHETIC"
    rule = repository.row(session, automation_rules, automation_rules.c.rule_id == row["rule_id"])
    valid = bool(
        row["cycle_no"]
        and 1 <= row["cycle_no"] <= ticket["cycle_no"]
        and rule
        and rule["version"] == row["rule_version"]
        and (historical or row["category"] == ticket["category"])
    )
    state = (
        "INVALID_LINK"
        if not valid
        else "SYNTHETIC_HISTORY"
        if synthetic
        else "HISTORICAL_CYCLE"
        if historical
        else "CURRENT_CYCLE"
    )
    item = ProposalFact(
        suggestion_id=row["suggestion_id"],
        cycle_no=row["cycle_no"] or 0,
        revision=row["revision"],
        synthetic=synthetic,
        record_state=state,
    )
    if not valid:
        return item
    item.category = (
        row["category"]
        if row["category"]
        in {"ACCOUNT", "DELIVERY", "PAYMENT", "PRODUCT", "REFUND", "RETURN", "FAQ", "UNCLASSIFIED"}
        else None
    )
    item.confidence = (
        float(row["confidence"]) if row["confidence"] is not None and 0 <= row["confidence"] <= 1 else None
    )
    for name in ("template_key", "prompt_version", "model_version"):
        setattr(item, name, safe_code(row[name]))
    item.rule_version = row["rule_version"]
    item.rule_active = bool(rule["active"])
    item.gates = gates(row["gate_results"])
    item.evidence, item.evidence_state = evidence(session, row["evidence_refs"], as_of, row["category"])
    item.masked_order, item.order_snapshot_state = order_fact(session, ticket, row["order_snapshot"])
    found = list(
        session.execute(
            select(approvals)
            .where(approvals.c.suggestion_id == row["suggestion_id"])
            .order_by(approvals.c.reviewed_at.desc(), approvals.c.approval_id.desc())
            .limit(21)
        ).mappings()
    )
    item.approvals_truncated = len(found) > 20
    for a in found[:20]:
        if a["suggestion_id"] != row["suggestion_id"]:
            continue
        if (
            a["ticket_id"] != ticket["ticket_id"]
            or a["cycle_no"] != row["cycle_no"]
            or a["content_hash"] != row["content_hash"]
        ):
            item.invalid_approval_links = True
            continue
        record = (
            "SYNTHETIC_HISTORY"
            if synthetic or a["data_origin"] == "SYNTHETIC"
            else "HISTORICAL_CYCLE"
            if historical
            else "STALE_TICKET_VERSION"
            if a["ticket_version"] != ticket["version"]
            else "NOT_YET_EFFECTIVE"
            if a["reviewed_at"] > as_of
            else "EXPIRED"
            if a["expires_at"] <= as_of
            else "UNVERIFIED_LINKS"
            if item.evidence_state != "VERIFIED_REFERENCES"
            or (ticket["order_id"] and item.order_snapshot_state != "VERIFIED_LINK")
            else "POLICY_INACTIVE"
            if not rule["active"] or not item.evidence or not all(r.active_at_as_of for r in item.evidence)
            else "CURRENT_RECORDED"
        )
        item.approvals.append(
            ApprovalFact(
                approval_id=a["approval_id"],
                mode=a["mode"] if a["mode"] in {"SYSTEM", "HUMAN"} else None,
                decision=a["decision"]
                if a["decision"] in {"APPROVED", "REJECTED", "PENDING", "NEEDS_HUMAN"}
                else None,
                record_state=record,
                reviewed_at=a["reviewed_at"],
                expires_at=a["expires_at"],
                gates=gates(a["gate_snapshot"]),
            )
        )
    return item


def detail(session, user, ticket_id, body):
    if user["role"] not in {"AGENT", "ADMIN"}:
        raise APIError(403, "STAFF_ROLE_REQUIRED", user["user_id"])
    if body.purpose_code == "QUALITY_REVIEW" and user["role"] != "ADMIN":
        raise APIError(403, "PURPOSE_NOT_ALLOWED", user["user_id"])
    ticket = repository.row(session, tickets, tickets.c.ticket_id == ticket_id, repository.ticket_scope(user))
    if not ticket:
        raise denied(user["user_id"], "TICKET", ticket_id)
    current = list(
        session.execute(
            select(ai_suggestions)
            .where(ai_suggestions.c.ticket_id == ticket_id, ai_suggestions.c.cycle_no == ticket["cycle_no"])
            .order_by(ai_suggestions.c.revision.desc())
            .limit(11)
        ).mappings()
    )
    history = (
        list(
            session.execute(
                select(ai_suggestions)
                .where(
                    ai_suggestions.c.ticket_id == ticket_id, ai_suggestions.c.cycle_no != ticket["cycle_no"]
                )
                .order_by(ai_suggestions.c.cycle_no.desc(), ai_suggestions.c.revision.desc())
                .limit(11)
            ).mappings()
        )
        if body.include_history
        else []
    )
    as_of = session.info["snapshot_as_of"]
    facts = [proposal_fact(session, ticket, r, as_of) for r in current[:10]]
    past = [proposal_fact(session, ticket, r, as_of) for r in history[:10]]
    audit.record(
        session,
        user["user_id"],
        "READ_STAFF_TICKET",
        "TICKET",
        ticket_id,
        reason=body.purpose_code,
        ticket=ticket_id,
        cycle=ticket["cycle_no"],
    )
    all_facts = facts + past
    return StaffTicketDetail(
        ticket_id=ticket_id,
        customer_ref=ticket["customer_id"],
        cycle_no=ticket["cycle_no"],
        revision=ticket["version"],
        as_of=as_of,
        material_status="MISSING"
        if not all_facts
        else "SYNTHETIC_ONLY"
        if all(r.synthetic for r in all_facts)
        else "RECORDED_FACTS",
        current_proposals=facts,
        historical_proposals=past,
        history_included=body.include_history,
        truncated=len(current) > 10 or len(history) > 10,
    )
