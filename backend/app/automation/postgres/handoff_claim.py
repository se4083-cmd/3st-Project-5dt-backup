"""Claim PostgreSQL HANDOFF jobs using Backend A lease contract."""

from app.jobs import claim_jobs


def claim_handoff_jobs(session_factory, worker_id: str, limit: int = 10):
    """Claim HANDOFF jobs and commit leases before processing."""
    with session_factory.begin() as session:
        claimed = claim_jobs(
            session,
            worker_id=worker_id,
            limit=limit,
            lease_seconds=60,
            job_kind="HANDOFF",
        )
    return claimed
