"""Orchestrate one batch of PostgreSQL AUTO jobs.

The reply generator is injected so the worker can be tested
without an AI service or a PostgreSQL connection.
"""

import logging
from collections.abc import Callable

from .job_claim import claim_auto_jobs
from .job_finalize import finalize_auto_job
from .job_retry import retry_auto_job
from .ai_adapter import AIResultRejected

logger = logging.getLogger(__name__)


def process_auto_jobs(
    session_factory,
    worker_id: str,
    generate_reply: Callable[[dict], str],
    limit: int = 10,
    mock_mode: bool = False,
):
    """Claim jobs and process them individually."""

    if not worker_id or not worker_id.strip():
        raise ValueError("worker_id must not be empty")

    if not callable(generate_reply):
        raise ValueError("generate_reply must be callable")

    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")

    jobs = claim_auto_jobs(
        session_factory,
        worker_id=worker_id,
        limit=limit,
    )

    results = []

    for job in jobs:
        try:
            approved_reply = generate_reply(job)

            if not isinstance(approved_reply, str) or not approved_reply.strip():
                raise ValueError("EMPTY_AI_REPLY")

            if not mock_mode:
                raise AIResultRejected("PRODUCTION_GATE_NOT_CONFIGURED")

            from .mock_ai_provider import verify_mock_reply

            if not verify_mock_reply(job, approved_reply):
                raise AIResultRejected("AUTOMATION_GATE_DENIED")

        except AIResultRejected as exc:
            logger.warning(
                "AI result rejected for job %s: %s",
                job["job_id"],
                exc.code,
            )

            try:
                retry_result = retry_auto_job(
                    session_factory,
                    job,
                    worker_id=worker_id,
                    error_code=exc.code,
                    force_handoff=not exc.retryable,
                )
                results.append(retry_result)

            except Exception:
                logger.exception(
                    "AI rejection handling failed for job %s",
                    job["job_id"],
                )
                results.append(
                    {
                        "job_id": job["job_id"],
                        "status": "REJECTION_HANDLING_FAILED",
                    }
                )

            continue

        except Exception:
            logger.exception(
                "Reply generation failed for job %s",
                job["job_id"],
            )

            try:
                retry_result = retry_auto_job(
                    session_factory,
                    job,
                    worker_id=worker_id,
                    error_code="REPLY_GENERATION_FAILED",
                )
                results.append(retry_result)

            except Exception:
                logger.exception(
                    "Retry recording failed for job %s",
                    job["job_id"],
                )
                results.append(
                    {
                        "job_id": job["job_id"],
                        "status": "RETRY_RECORD_FAILED",
                    }
                )

            continue

        # Do not retry a finalization error blindly.
        # It may indicate a stale lease, ticket version change,
        # global pause, or an uncertain transaction outcome.
        try:
            finalize_auto_job(
                session_factory,
                job,
                approved_reply,
                worker_id,
            )
            results.append(
                {
                    "job_id": job["job_id"],
                    "status": "SUCCEEDED",
                }
            )

        except Exception:
            logger.exception(
                "Finalization failed for job %s",
                job["job_id"],
            )
            results.append(
                {
                    "job_id": job["job_id"],
                    "status": "FINALIZATION_FAILED",
                }
            )

    return results

