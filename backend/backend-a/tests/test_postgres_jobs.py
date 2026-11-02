from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import utcnow
from app.jobs import claim_jobs, fenced_job_predicate
from app.models import automation_jobs, tickets
from tests.test_flow import submit


@pytest.mark.postgres
def test_postgres_claim_skip_locked_recovery_and_fencing(client, headers, app):
    if app.state.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row locks and leases cannot be verified on SQLite")
    ticket_id = submit(client, headers).json()["ticket_id"]

    def claim(worker):
        with app.state.session_factory.begin() as session:
            return claim_jobs(session, worker, limit=1)

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, ["worker1", "worker2"]))
    assert sorted(map(len, claimed)) == [0, 1]
    first = next(x[0] for x in claimed if x)
    with app.state.session_factory.begin() as session:
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == first["job_id"])
            .values(lease_until=utcnow() - timedelta(seconds=1))
        )
    second = claim("worker3")[0]
    assert second["lease_token"] != first["lease_token"] and second["attempt"] == 2
    with app.state.session_factory.begin() as session:
        assert (
            session.execute(
                select(automation_jobs).where(
                    fenced_job_predicate(first["job_id"], first["lease_token"], 1, 1)
                )
            ).first()
            is None
        )
        session.execute(
            tickets.update().where(tickets.c.ticket_id == ticket_id).values(version=2, cycle_no=2)
        )
        session.execute(
            automation_jobs.update()
            .where(automation_jobs.c.job_id == first["job_id"])
            .values(lease_until=utcnow() - timedelta(seconds=1))
        )
    assert claim("worker4") == []
