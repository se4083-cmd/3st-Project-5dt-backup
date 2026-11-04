import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "local" / "data"


def load_json(filename: str):
    path = DATA_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_gate(ticket_id: str, cycle_no: int):
    suggestions = load_json("ai_suggestions.json")
    rules = load_json("automation_rules.json")

    matches = [
        item
        for item in suggestions
        if item["ticket_id"] == ticket_id and item["cycle_no"] == cycle_no
    ]

    if not matches:
        return {
            "allowed": False,
            "reason": "AI_SUGGESTION_NOT_FOUND",
        }

    # 가장 최신 revision 선택
    suggestion = max(matches, key=lambda x: x["revision"])

    rule = next(
        (
            item
            for item in rules
            if item["rule_id"] == suggestion["rule_id"]
            and item["version"] == suggestion["rule_version"]
        ),
        None,
    )

    if rule is None:
        return {
            "allowed": False,
            "reason": "AUTOMATION_RULE_NOT_FOUND",
        }

    if not rule["active"]:
        return {
            "allowed": False,
            "reason": "AUTOMATION_RULE_INACTIVE",
        }

    if rule["requires_approval"]:
        return {
            "allowed": False,
            "reason": "APPROVAL_REQUIRED",
        }

    if rule["risk_level"] != "LOW":
        return {
            "allowed": False,
            "reason": "HIGH_RISK",
        }

    if suggestion.get("confidence") is None:
        return {
            "allowed": False,
            "reason": "CONFIDENCE_NOT_AVAILABLE",
        }

    gate_results = suggestion.get("gate_results", {})

    if not gate_results.get("ownership_valid"):
        return {
            "allowed": False,
            "reason": "OWNERSHIP_NOT_VERIFIED",
        }

    if not gate_results.get("policy_valid_in_fixture"):
        return {
            "allowed": False,
            "reason": "POLICY_NOT_VALID",
        }

    if not gate_results.get("no_money_execution"):
        return {
            "allowed": False,
            "reason": "MONEY_EXECUTION_BLOCKED",
        }

    return {
        "allowed": True,
        "reason": "GATE_PASSED",
        "suggestion_id": suggestion["suggestion_id"],
        "rule_id": rule["rule_id"],
    }
