"""Orchestrate one batch of PostgreSQL HANDOFF jobs."""

import logging
from collections.abc import Callable

from app.resolution import WorkRejected
from .assignment import AssignmentRejected
from .handoff_claim import claim_handoff_jobs
from .handoff_finalize import finalize_handoff_job
from .handoff_retry import retry_handoff_job

logger = logging.getLogger(__name__)


def process_handoff_jobs(
    session_factory,
    worker_id: str,
    select_agent: Callable[[dict], str | None],
    limit: int = 10,
):
    """Claim HANDOFF jobs and process each independently."""

    if not worker_id or not worker_id.strip():
        raise ValueError("worker_id must not be empty")

    if not callable(select_agent):
        raise ValueError("select_agent must be callable")

    if not 1 <= limit <= 10:
        raise ValueError("limit must be between 1 and 10")

    jobs = claim_handoff_jobs(
        session_factory,
        worker_id=worker_id,
        limit=limit,
    )

    results = []

    for job in jobs:
        try:
            agent_id = select_agent(job)
        except Exception:
            error_code = "AGENT_SELECTION_ERROR"
            logger.exception(
                "Agent selection failed for HANDOFF job %s",
                job["job_id"],
            )
        else:
            if isinstance(agent_id, str) and agent_id.strip():
                error_code = None
            else:
                error_code = "NO_ELIGIBLE_AGENT"
                logger.warning(
                    "No eligible agent for HANDOFF job %s",
                    job["job_id"],
                )

        if error_code is not None:
            try:
                result = retry_handoff_job(
                    session_factory,
                    job,
                    worker_id=worker_id,
                    error_code=error_code,
                )
                results.append(result)
            except WorkRejected as exc:
                logger.exception(
                    "HANDOFF retry rejected for job %s",
                    job["job_id"],
                )
                results.append({
                    "job_id": job["job_id"],
                    "status": "RETRY_RECORD_FAILED",
                })

            except Exception:
                logger.exception(
                    "Retry recording failed for HANDOFF job %s",
                    job["job_id"],
                )
                results.append({
                    "job_id": job["job_id"],
                    "status": "RETRY_RECORD_FAILED",
                })

            continue

        try:
            result = finalize_handoff_job(
                session_factory,
                job,
                worker_id=worker_id,
                agent_id=agent_id,
            )
            results.append(result)

        except AssignmentRejected as exc:
            status_map = {
                "HANDOFF_LEASE_INVALID": "LEASE_INVALID",
                "HANDOFF_CONTEXT_CHANGED": "CONTEXT_CHANGED",
            }

            status = status_map.get(exc.code)

            if status is not None:
                logger.warning(
                    "HANDOFF job rejected: %s (job_id=%s)",
                    exc.code,
                    job["job_id"],
                )
                results.append({
                    "job_id": job["job_id"],
                    "status": status,
                })
            else:
                logger.exception(
                    "HANDOFF assignment rejected for job %s",
                    job["job_id"],
                )
                results.append({
                    "job_id": job["job_id"],
                    "status": "FINALIZATION_FAILED",
                })

        except WorkRejected as exc:
            logger.exception(
                "HANDOFF work rejected for job %s",
                job["job_id"],
            )
            results.append({
                "job_id": job["job_id"],
                "status": "FINALIZATION_FAILED",
            })

        except Exception:
            logger.exception(
                "Finalization failed for HANDOFF job %s",
                job["job_id"],
            )
            results.append({
                "job_id": job["job_id"],
                "status": "FINALIZATION_FAILED",
            })

    return results
