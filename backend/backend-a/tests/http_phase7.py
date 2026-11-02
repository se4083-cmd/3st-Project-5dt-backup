"""Actual authenticated HTTP retention preview; local schema fixtures only."""

from tests.phase7_helpers import BODY, archived, business_hashes, grant, target


def run_phase7(factory, request, admin, agent, own):
    path = "/staff/retention/dry-run"
    request("POST", path, headers=admin, json=BODY, status=403)
    grant(factory, permission="RETENTION_TEAM_REVIEW")
    request("POST", path, headers=admin, json=BODY, status=403)
    request("POST", path, headers=agent, json={**BODY, "scope": "TEAM"}, status=403)
    request("POST", path, headers=own, json=BODY, status=403)
    archived(factory, cycle=1)
    scoped = request("POST", path, headers=admin, json={**BODY, "scope": "TEAM"})
    archived(factory, team=None, cycle=1)
    again = request("POST", path, headers=admin, json={**BODY, "scope": "TEAM"})
    if scoped["result_fingerprint"] != again["result_fingerprint"]:
        raise RuntimeError("HTTP_RETENTION_HIDDEN_CUSTODY_LEAK")
    if target(scoped, "analytics_receipts")["inspected_count"] is not None:
        raise RuntimeError("HTTP_RETENTION_TEAM_SHARED_ANALYTICS_LEAK")
    grant(factory)
    before = business_hashes(factory)
    report = request("POST", path, headers=admin, json=BODY)
    if not report["dry_run"] or report["execution_status"] != "PREVIEW_ONLY_NOT_DELETION_AUTHORIZATION":
        raise RuntimeError("HTTP_RETENTION_EXECUTION_STATE")
    if before != business_hashes(factory):
        raise RuntimeError("HTTP_RETENTION_BUSINESS_DATA_CHANGED")
    import json

    if "PRIVATE_RETENTION" in json.dumps(report):
        raise RuntimeError("HTTP_RETENTION_CONTENT_LEAK")
    if any(t["status"] != "NOT_INSPECTED" for t in report["not_inspected"]):
        raise RuntimeError("HTTP_RETENTION_EXTERNAL_SCAN_CLAIM")
    request("POST", path, headers=admin, json={**BODY, "execute": True}, status=422)
    request("POST", path, headers=admin, json={**BODY, "table": "messages"}, status=422)
    return [
        "retention_explicit_team_global_permissions",
        "retention_hidden_custody_and_shared_storage_isolation",
        "retention_inventory_and_blocked_unknown_states",
        "retention_business_content_unchanged",
        "retention_no_execute_or_arbitrary_target",
    ], {
        "retention_policy_hash": report["policy_hash"],
        "retention_dry_run": report["dry_run"],
        "retention_execution_status": report["execution_status"],
        "retention_stores_not_inspected": [r["store"] for r in report["not_inspected"]],
    }
