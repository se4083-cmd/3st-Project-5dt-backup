"""Fixture-only AI provider for Backend B integration tests.

This module does not establish production policy authorization.
"""

from backend.app.automation.automation_gate import evaluate_gate, load_json

from .ai_adapter import AIResultRejected, validate_ai_result


def generate_mock_reply(job: dict) -> str:
    """Return a fixture-approved draft or reject automatic processing."""

    ticket_id = job.get("ticket_id")
    cycle_no = job.get("cycle_no")

    if not ticket_id or cycle_no is None:
        raise AIResultRejected("INVALID_JOB_CONTEXT")

    suggestions = load_json("ai_suggestions.json")

    matches = [
        item
        for item in suggestions
        if item.get("ticket_id") == ticket_id
        and item.get("cycle_no") == cycle_no
    ]

    if not matches:
        raise AIResultRejected("AI_SUGGESTION_NOT_FOUND")

    suggestion = max(matches, key=lambda item: item["revision"])

    gate_result = evaluate_gate(ticket_id, cycle_no)

    if gate_result.get("allowed") is not True:
        raise AIResultRejected(
            str(gate_result.get("reason", "AUTOMATION_GATE_DENIED"))
        )

    if (
        gate_result.get("suggestion_id") != suggestion.get("suggestion_id")
        or gate_result.get("rule_id") != suggestion.get("rule_id")
    ):
        raise AIResultRejected("GATE_RESULT_MISMATCH")

    # The allowed flag is derived from the local Gate result,
    # never copied from an AI-generated response.
    validated = validate_ai_result(
        {
            "draft": suggestion.get("draft"),
            "allowed": True,
            "suggestion_id": suggestion.get("suggestion_id"),
            "rule_id": suggestion.get("rule_id"),
            "evidence_refs": suggestion.get("evidence_refs"),
        }
    )

    return validated.draft



def verify_mock_reply(job: dict, reply: str) -> bool:
    """Recheck fixture authorization and exact reply content."""
    if not isinstance(reply, str) or not reply.strip():
        return False

    ticket_id = job.get("ticket_id")
    cycle_no = job.get("cycle_no")

    if not ticket_id or cycle_no is None:
        return False

    gate = evaluate_gate(ticket_id, cycle_no)
    if gate.get("allowed") is not True:
        return False

    suggestions = load_json("ai_suggestions.json")
    matches = [
        item for item in suggestions
        if item.get("ticket_id") == ticket_id
        and item.get("cycle_no") == cycle_no
    ]

    if not matches:
        return False

    suggestion = max(matches, key=lambda item: item["revision"])

    return (
        gate.get("suggestion_id") == suggestion.get("suggestion_id")
        and gate.get("rule_id") == suggestion.get("rule_id")
        and bool(suggestion.get("evidence_refs"))
        and reply.strip() == str(suggestion.get("draft", "")).strip()
    )
