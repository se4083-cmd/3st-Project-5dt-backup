"""Claim AUTO jobs through Backend A's shared PostgreSQL contract."""

from app.jobs import claim_jobs


def claim_auto_jobs(session_factory, worker_id: str, limit: int = 10):
    """Claim AUTO jobs and commit leases before returning."""

    with session_factory.begin() as session:
        claimed = claim_jobs(
            session,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=60,
            job_kind="AUTO",
        )

    return claimed
