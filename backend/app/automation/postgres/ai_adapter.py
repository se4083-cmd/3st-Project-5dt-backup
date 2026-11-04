"""Validate AI/RAG results before automatic reply finalization."""

from dataclasses import dataclass
from typing import Any


class AIResultRejected(Exception):
    def __init__(self, code: str, retryable: bool = False):
        self.code = code
        self.retryable = retryable
        super().__init__(code)


@dataclass(frozen=True)
class ValidatedAIReply:
    draft: str
    suggestion_id: str
    rule_id: str


def validate_ai_result(result: dict[str, Any]) -> ValidatedAIReply:
    """Validate an AI/RAG result. Never treat a draft alone as approval."""

    if not isinstance(result, dict):
        raise AIResultRejected("INVALID_AI_RESULT", retryable=True)

    draft = result.get("draft")
    if not isinstance(draft, str) or not draft.strip():
        raise AIResultRejected("EMPTY_AI_REPLY", retryable=True)

    if result.get("allowed") is not True:
        raise AIResultRejected("AUTOMATION_GATE_DENIED")

    if not result.get("suggestion_id"):
        raise AIResultRejected("SUGGESTION_ID_MISSING")

    if not result.get("rule_id"):
        raise AIResultRejected("RULE_ID_MISSING")

    evidence_refs = result.get("evidence_refs")
    if not isinstance(evidence_refs, list) or not evidence_refs:
        raise AIResultRejected("EVIDENCE_MISSING")

    return ValidatedAIReply(
        draft=draft.strip(),
        suggestion_id=str(result["suggestion_id"]),
        rule_id=str(result["rule_id"]),
    )
