"""Opt-in typed errors for analysis only; no retry loop or workflow decisions.

Codes are an OpenAI-side integration proposal until Backend B adopts them.
Legacy backend_adapter.analyze_job remains unchanged.
"""

from openai import (
    APIConnectionError, APIStatusError, APITimeoutError,
    AuthenticationError, PermissionDeniedError, RateLimitError,
)

if __package__:
    from .analysis_errors import AnalysisResponseError, JobContextError, StaleJobContextError
    from .backend_adapter import analyze_job, job_context
else:
    from analysis_errors import AnalysisResponseError, JobContextError, StaleJobContextError
    from backend_adapter import analyze_job, job_context


class AIAnalysisError(Exception):
    """Safe, fixed code. retryable is eligibility, never permission to retry."""

    def __init__(self, code, *, retryable):
        self.code = code
        self.retryable = retryable
        super().__init__(code)

    def as_dict(self):
        # Never serialize SDK messages, inquiry, credentials or lease values.
        return {"code": self.code, "retryable": self.retryable}


def analyze_job_checked(client, deployment, job, inquiry, *, predict_complaint=True):
    """Return the legacy success shape; raise AIAnalysisError on known failures.

    Caller configures SDK timeouts/retries, rechecks DB state and owns all
    retry/handoff/finalization. Unknown programming failures propagate.
    """
    try:
        job_context(job)
    except JobContextError:
        raise AIAnalysisError("INVALID_JOB_CONTEXT", retryable=False) from None
    if not isinstance(inquiry, str) or not inquiry.strip() or len(inquiry) > 10000:
        raise AIAnalysisError("INVALID_INQUIRY", retryable=False)
    if not isinstance(deployment, str) or not deployment.strip():
        raise AIAnalysisError("INVALID_DEPLOYMENT", retryable=False)
    if type(predict_complaint) is not bool:
        raise AIAnalysisError("INVALID_ANALYSIS_OPTIONS", retryable=False)
    try:
        if predict_complaint:
            return analyze_job(client, deployment, job, inquiry, predict_complaint=True)
        return analyze_job(client, deployment, job, inquiry, predict_complaint=False)
    except APITimeoutError:
        raise AIAnalysisError("AI_TIMEOUT", retryable=True) from None
    except RateLimitError:
        raise AIAnalysisError("AI_RATE_LIMITED", retryable=True) from None
    except AuthenticationError:
        raise AIAnalysisError("AI_AUTHENTICATION_FAILED", retryable=False) from None
    except PermissionDeniedError:
        raise AIAnalysisError("AI_PERMISSION_DENIED", retryable=False) from None
    except APIConnectionError:
        raise AIAnalysisError("AI_CONNECTION_FAILED", retryable=True) from None
    except APIStatusError as error:
        transient = error.status_code in (408, 409, 429) or error.status_code >= 500
        raise AIAnalysisError("AI_SERVICE_UNAVAILABLE" if transient else "AI_REQUEST_REJECTED",
                              retryable=transient) from None
    except StaleJobContextError:
        raise AIAnalysisError("STALE_JOB_CONTEXT", retryable=False) from None
    except JobContextError:
        raise AIAnalysisError("INVALID_JOB_CONTEXT", retryable=False) from None
    except AnalysisResponseError:
        raise AIAnalysisError("INVALID_ANALYSIS_RESPONSE", retryable=False) from None
