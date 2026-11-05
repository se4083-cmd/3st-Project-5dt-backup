"""Run from repository root: python -m ai.examples.backend_b_analysis.

Synthetic IDs only. In live use, the caller must pass the real claimed job and
authorized current inquiry; never reuse these IDs or output internal job data.
"""
import json

from ai.analysis_service import AIAnalysisError, analyze_job_checked
from ai.mock_analysis import MockAnalysisClient


def main():
    job = {
        "job_id": "12345678-1234-4234-8234-123456789abc",
        "ticket_id": "12345678-1234-4234-8234-123456789abd",
        "lease_token": "12345678-1234-4234-8234-123456789abe",
        "lease_owner": "synthetic-worker",
        "cycle_no": 1, "expected_ticket_version": 1,
        "automation_generation": 1, "job_kind": "AUTO",
    }
    for name in ("delivery", "human_request", "unknown"):
        client = MockAnalysisClient(name)
        try:
            result = analyze_job_checked(client, "mock-only", job, client.fixture["inquiry"])
        except AIAnalysisError as error:
            print(json.dumps({"scenario": name, "error": error.as_dict()}, ensure_ascii=False))
        else:
            # Exclude job entirely: lease_token is internal and must not be logged.
            print(json.dumps({"scenario": name, "category": result["category"],
                              "analysis": result["analysis"], "execution": result["execution"]},
                             ensure_ascii=False))


if __name__ == "__main__":
    main()
