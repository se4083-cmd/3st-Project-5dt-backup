from datetime import timedelta
from uuid import uuid4

from app import repository
from app.db import utcnow
from app.exception_queue import RouteCommand, record_queue_route
from app.models import ai_suggestions, approvals, automation_rules, knowledge_documents, orders, tickets
from app.seed import stable_id
from app.staff_models import staff_permissions
from tests.phase3_helpers import assign
from tests.test_flow import submit

BASE = "/api/v1/staff"


def grant(app, label, *permissions):
    with app.state.session_factory.begin() as s:
        for permission in permissions:
            s.execute(staff_permissions.insert().values(user_id=stable_id(label), permission=permission))


def route(app, tid, team="team", expected_route_revision=0):
    with app.state.session_factory.begin() as s:
        ticket = repository.row(s, tickets, tickets.c.ticket_id == tid)
        return record_queue_route(
            s,
            tid,
            RouteCommand(
                expected_revision=ticket["version"],
                cycle_no=ticket["cycle_no"],
                expected_route_revision=expected_route_revision,
                team_id=stable_id(team) if team else None,
            ),
            service_id="local-routing-fixture",
        )


def internal_fixture(client, headers, app, *, synthetic=True):
    tid = submit(client, headers, order=stable_id("customer1/order/0")).json()["ticket_id"]
    assign(app, tid)
    return material_fixture(app.state.session_factory, tid, synthetic=synthetic)


def material_fixture(factory, tid, *, synthetic=True):
    now = utcnow()
    did, rid, sid, aid = map(str, (uuid4(), uuid4(), uuid4(), uuid4()))
    origin = "SYNTHETIC" if synthetic else "APPLICATION"
    with factory.begin() as s:
        t = repository.row(s, tickets, tickets.c.ticket_id == tid)
        order = repository.row(s, orders, orders.c.order_id == t["order_id"])
        s.execute(
            automation_rules.insert().values(
                rule_id=rid,
                rule_key="LOCAL_POLICY",
                version=1,
                category="DELIVERY",
                risk_level="LOW",
                requires_approval=True,
                conditions={},
                active=not synthetic,
                data_origin=origin,
            )
        )
        s.execute(
            knowledge_documents.insert().values(
                document_id=did,
                policy_key="LOCAL_POLICY",
                title="PRIVATE_DOC_TITLE",
                version=1,
                source="LOCAL_ONLY",
                blob_path="PRIVATE_CONNECTION",
                content_hash="a" * 64,
                allowed_topics=["DELIVERY"],
                active=not synthetic,
                effective_from=now - timedelta(days=1),
                approval_status="APPROVED",
                body="PRIVATE_POLICY_BODY",
                data_origin=origin,
            )
        )
        s.execute(
            ai_suggestions.insert().values(
                suggestion_id=sid,
                ticket_id=tid,
                cycle_no=t["cycle_no"],
                revision=1,
                category="DELIVERY",
                draft="PRIVATE_DRAFT_PROMPT_TOKEN",
                confidence=0.9,
                evidence_refs=[
                    {
                        "document_id": did,
                        "version": 1,
                        "content_hash": "a" * 64,
                        "raw_prompt": "PRIVATE_NESTED",
                    }
                ],
                order_snapshot={
                    "order_id": t["order_id"],
                    "version": order["version"],
                    "name": "PRIVATE_CUSTOMER",
                    "token": "PRIVATE_TOKEN",
                },
                gate_results={
                    "ownership_valid": True,
                    "policy_valid": True,
                    "fixture_only": synthetic,
                    "raw_prompt": "PRIVATE_PROMPT",
                    "nested": {"password": "PRIVATE_PASSWORD"},
                },
                rule_id=rid,
                rule_version=1,
                template_key="LOCAL_REPLY",
                prompt_version="LOCAL_V1",
                model_version="NONE",
                content_hash="b" * 64,
                data_origin=origin,
            )
        )
        s.execute(
            approvals.insert().values(
                approval_id=aid,
                ticket_id=tid,
                suggestion_id=sid,
                cycle_no=t["cycle_no"],
                ticket_version=t["version"],
                mode="HUMAN",
                decision="APPROVED",
                gate_snapshot={"ownership_valid": True, "raw_token": "PRIVATE_RAW_TOKEN"},
                content_hash="b" * 64,
                reviewed_at=now,
                expires_at=now + timedelta(hours=1),
                data_origin=origin,
            )
        )
    return tid, sid, aid, did, rid
