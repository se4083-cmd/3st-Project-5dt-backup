"""Finalize approved AUTO replies using Backend A's shared transaction."""

from app.finalization import AutomaticReply, commit_automatic_reply


def finalize_auto_job(session_factory, job: dict, approved_reply: str, worker_id: str):
    """Commit an approved reply, ticket resolution, and job completion atomically."""

    if not isinstance(approved_reply, str) or not approved_reply.strip():
        raise ValueError("Approved reply must not be empty")

    command = AutomaticReply(
        job_id=job["job_id"],
        lease_token=job["lease_token"],
        worker_id=worker_id,
        cycle_no=job["cycle_no"],
        expected_revision=job["expected_ticket_version"],
        automation_generation=job["automation_generation"],
        message=approved_reply,
    )

    with session_factory.begin() as session:
        return commit_automatic_reply(session, command)
