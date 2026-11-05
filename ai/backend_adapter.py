"""AI analysis boundary for Backend A job rows and Backend B callers.

This result is internal analysis, never a reply accepted by B's generate_reply.
Database freshness, leases, authorization and finalization remain server-owned.
"""

from collections.abc import Mapping
from copy import deepcopy
from uuid import UUID

if __package__:
    from .analysis_errors import AnalysisResponseError, JobContextError, StaleJobContextError
    from .classify_with_signals import VOC_PROMPT_VERSION, PROMPT_VERSION, analyze_inquiry, validate_payload
    from .integration_contract import backend_category, execution_metadata
else:  # Preserve existing ai-directory callers and unittest discovery.
    from analysis_errors import AnalysisResponseError, JobContextError, StaleJobContextError
    from classify_with_signals import VOC_PROMPT_VERSION, PROMPT_VERSION, analyze_inquiry, validate_payload
    from integration_contract import backend_category, execution_metadata


def job_context(job):
    """Take only claimed AUTO identity fields; do not copy source customer data."""
    if not isinstance(job, Mapping) or job.get("job_kind") != "AUTO":
        raise JobContextError("Claimed AUTO job required")
    result = {}
    for key in ("job_id", "ticket_id", "lease_token"):
        value = job.get(key)
        if not isinstance(value, (str, UUID)):
            raise JobContextError(f"Valid {key} required")
        try:
            result[key] = str(UUID(str(value)))
        except ValueError:
            raise JobContextError(f"Valid {key} required") from None
    for key in ("cycle_no", "expected_ticket_version", "automation_generation"):
        value = job.get(key)
        if type(value) is not int or value < 1:
            raise JobContextError(f"Positive {key} required")
        result[key] = value
    owner = job.get("lease_owner")
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 128:
        raise JobContextError("Claimed lease_owner required")
    result.update(lease_owner=owner, job_kind="AUTO")
    return result


def assert_same_job(expected, current):
    """Reject changed identity before handing analysis back to the caller.

    This comparison does not replace A's transactional time/lease/version gates.
    """
    if job_context(expected) != job_context(current):
        raise StaleJobContextError("STALE_JOB_CONTEXT")


def analyze_job(client, deployment, job, inquiry, *, predict_complaint=False):
    """Analyze one claimed job without creating draft, approval or send fields.

    inquiry must come from the caller's authorized current-cycle source message.
    Direct HUMAN/HANDOFF requests must bypass this function in the caller.
    """
    context = job_context(job)
    if type(predict_complaint) is not bool:
        raise ValueError("predict_complaint must be bool")
    if predict_complaint:
        analysis, response = analyze_inquiry(client, deployment, inquiry, predict_complaint=True)
    else:
        analysis, response = analyze_inquiry(client, deployment, inquiry)
    assert_same_job(context, job)
    # Validate again at the boundary; do not trust substituted providers.
    keys = ["category", "summary", "risk_tags", "risk_evidence"]
    if predict_complaint:
        keys.append("voc_predicted_is_complaint")
    if not isinstance(analysis, dict) or any(key not in analysis for key in keys):
        raise AnalysisResponseError("Invalid substituted analysis")
    payload = {key: analysis[key] for key in keys}
    analysis = validate_payload(payload, inquiry, predict_complaint=predict_complaint)
    return {
        "job": context,
        "category": backend_category(analysis["category"]),
        "analysis": deepcopy(analysis),
        "execution": execution_metadata(response, prompt_version=VOC_PROMPT_VERSION if predict_complaint else PROMPT_VERSION),
    }
