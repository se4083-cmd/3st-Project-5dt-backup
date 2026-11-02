from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.model_constraints import idempotency_keys
from app.models import automation_jobs
from app.seed import stable_id
from tests.test_flow import submit


@pytest.mark.parametrize(
    "values",
    [
        {"job_kind": "UNKNOWN"},
        {"job_kind": "HANDOFF"},
        {"job_kind": "HANDOFF", "source_message_id": str(uuid4()), "reason_code": "OTHER"},
        {"reason_code": "OTHER"},
    ],
)
def test_handoff_database_shape(client, headers, app, values):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.update().where(automation_jobs.c.ticket_id == ticket_id).values(**values)
        )


def test_non_create_idempotency_requires_snapshot(client, headers, app):
    ticket_id = submit(client, headers).json()["ticket_id"]
    with pytest.raises(IntegrityError), app.state.session_factory.begin() as session:
        session.execute(
            idempotency_keys.insert().values(
                user_id=stable_id("customer1"),
                key="missing-snapshot",
                request_hash="0" * 64,
                ticket_id=ticket_id,
                operation="REOPEN",
            )
        )
    with app.state.session_factory() as session:
        assert session.scalar(select(idempotency_keys.c.operation)) == "CREATE_TICKET"
