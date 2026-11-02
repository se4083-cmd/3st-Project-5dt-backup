from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError, StatementError

from app.models import analytics_batches, analytics_product_risk, automation_jobs, messages, tickets
from tests.test_flow import submit


@pytest.mark.parametrize(
    "values",
    [{"cycle_no": None}, {"cycle_no": 0}, {"version": 0}, {"status": "IMPOSSIBLE"}, {"status": "RESOLVED"}],
)
def test_ticket_database_constraints(client, headers, app, values):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(tickets.update().where(tickets.c.ticket_id == ticket_id).values(**values))


def test_database_enforces_order_ownership_and_product(client, headers, app):
    from app.seed import stable_id

    ticket_id = submit(client, headers).json()["ticket_id"]
    for values in [
        dict(order_id=stable_id("customer2/order/0"), product_id=stable_id("product")),
        dict(order_id=stable_id("customer1/order/0"), product_id=None),
        dict(order_id=stable_id("customer1/order/0"), product_id=str(uuid4())),
    ]:
        with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
            session.execute(tickets.update().where(tickets.c.ticket_id == ticket_id).values(**values))


@pytest.mark.parametrize(
    "values",
    [
        {"status": "RUNNING"},
        {"status": "UNKNOWN"},
        {"attempt": -1},
        {"expected_ticket_version": None},
        {"lease_token": str(uuid4())},
    ],
)
def test_job_database_constraints(client, headers, app, values):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.update().where(automation_jobs.c.ticket_id == ticket_id).values(**values)
        )


def test_no_duplicate_job_or_public_internal_message(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.insert().values(
                job_id=str(uuid4()), ticket_id=ticket_id, cycle_no=1, expected_ticket_version=1
            )
        )
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            messages.insert().values(
                message_id=str(uuid4()),
                ticket_id=ticket_id,
                cycle_no=1,
                role="AGENT",
                direction="INTERNAL",
                visibility="PUBLIC",
                body="must fail",
            )
        )


def test_single_final_response(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    row = dict(
        ticket_id=ticket_id,
        cycle_no=1,
        role="SYSTEM",
        direction="OUT",
        body="public reply",
        visibility="PUBLIC",
        final_reply=True,
    )
    with app.state.session_factory.begin() as session:
        session.execute(messages.insert().values(message_id=str(uuid4()), **row))
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(messages.insert().values(message_id=str(uuid4()), **row))


def test_risk_nullable_check_cannot_accept_null_eligible_values(app):
    from app.db import utcnow
    from app.seed import stable_id

    batch_id = str(uuid4())
    with app.state.session_factory.begin() as session:
        session.execute(
            analytics_batches.insert().values(
                batch_id=batch_id,
                status="VALIDATED",
                row_counts={},
                checksums={},
                schema_version="test",
                is_current=False,
                manifest={},
            )
        )
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            analytics_product_risk.insert().values(
                batch_id=batch_id,
                scope_key="test",
                product_id=stable_id("product"),
                rule_version="test",
                data_status="ELIGIBLE",
                score=None,
                rank=1,
                risk_band="HIGH",
                metrics={},
                components={},
                window_end=utcnow(),
            )
        )
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            analytics_batches.update().where(analytics_batches.c.batch_id == batch_id).values(is_current=True)
        )


def test_naive_application_timestamps_rejected(app):
    from datetime import datetime

    from app.seed import stable_id

    with pytest.raises(StatementError), app.state.session_factory.begin() as session:
        session.execute(
            tickets.insert().values(
                ticket_id=str(uuid4()),
                customer_id=stable_id("customer1/profile"),
                sla_due_at=datetime(2026, 11, 2),
            )
        )
