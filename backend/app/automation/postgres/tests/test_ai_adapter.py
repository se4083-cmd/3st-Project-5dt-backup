import pytest

from backend.app.automation.postgres.ai_adapter import (
    AIResultRejected,
    validate_ai_result,
)


def valid_result():
    return {
        "draft": "배송 상태를 확인했습니다.",
        "allowed": True,
        "suggestion_id": "suggestion-001",
        "rule_id": "rule-001",
        "evidence_refs": [{"document_id": "policy-001", "version": 1}],
    }


def test_valid_ai_result():
    result = validate_ai_result(valid_result())

    assert result.draft == "배송 상태를 확인했습니다."
    assert result.suggestion_id == "suggestion-001"
    assert result.rule_id == "rule-001"


def test_invalid_ai_result():
    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(None)

    assert exc.value.code == "INVALID_AI_RESULT"
    assert exc.value.retryable is True


def test_empty_ai_reply():
    data = valid_result()
    data["draft"] = "   "

    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(data)

    assert exc.value.code == "EMPTY_AI_REPLY"
    assert exc.value.retryable is True


def test_automation_gate_denied():
    data = valid_result()
    data["allowed"] = False

    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(data)

    assert exc.value.code == "AUTOMATION_GATE_DENIED"
    assert exc.value.retryable is False


def test_suggestion_id_missing():
    data = valid_result()
    data.pop("suggestion_id")

    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(data)

    assert exc.value.code == "SUGGESTION_ID_MISSING"


def test_rule_id_missing():
    data = valid_result()
    data.pop("rule_id")

    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(data)

    assert exc.value.code == "RULE_ID_MISSING"


@pytest.mark.parametrize("evidence", [None, [], "invalid"])
def test_evidence_missing(evidence):
    data = valid_result()
    data["evidence_refs"] = evidence

    with pytest.raises(AIResultRejected) as exc:
        validate_ai_result(data)

    assert exc.value.code == "EVIDENCE_MISSING"
