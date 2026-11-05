import copy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from backend_adapter import analyze_job, assert_same_job
from integration_contract import eligible_evidence_refs, policy_body_hash


class BackendAdapterTests(unittest.TestCase):
    def setUp(self):
        self.job = dict(job_id="12345678-1234-4234-8234-123456789abc",
                        ticket_id="12345678-1234-4234-8234-123456789abd",
                        lease_token="12345678-1234-4234-8234-123456789abe",
                        cycle_no=2, expected_ticket_version=3,
                        automation_generation=4, lease_owner="worker", job_kind="AUTO")
        self.client = Mock()
        self.client.responses.create.return_value = SimpleNamespace(
            status="completed", output=[], model="actual-model",
            output_text=json.dumps(dict(category="UNKNOWN", summary="확인 요청",
                                        risk_tags=[], risk_evidence=[])))

    def test_backend_category_and_original_analysis(self):
        original = copy.deepcopy(self.job)
        result = analyze_job(self.client, "deployment", self.job, "확인해주세요")
        self.assertEqual(result["job"], original)
        self.assertEqual(self.job, original)
        self.assertEqual(result["category"], "UNCLASSIFIED")
        self.assertEqual(result["analysis"]["category"], "UNKNOWN")
        self.assertTrue(result["analysis"]["review_required"])
        self.assertEqual(result["execution"]["model_version"], "actual-model")
        self.assertTrue({"allowed", "draft", "suggestion_id", "rule_id"}.isdisjoint(result))

    def test_invalid_job_never_calls_model(self):
        for key, value in (("job_kind", "HANDOFF"), ("cycle_no", True),
                           ("expected_ticket_version", 0), ("lease_token", "bad"),
                           ("automation_generation", None), ("lease_owner", "")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                analyze_job(self.client, "deployment", {**self.job, key: value}, "문의")
        self.client.responses.create.assert_not_called()

    def test_stale_result_rejected(self):
        for key in ("cycle_no", "expected_ticket_version", "automation_generation"):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "STALE"):
                assert_same_job(self.job, {**self.job, key: self.job[key] + 1})
        response = self.client.responses.create.return_value
        def change_lease(**kwargs):
            self.job["lease_owner"] = "replacement-worker"
            return response
        self.client.responses.create.side_effect = change_lease
        with self.assertRaisesRegex(ValueError, "STALE"):
            analyze_job(self.client, "deployment", self.job, "문의")

    def test_policy_activation_is_separate_from_candidate_approval(self):
        document = dict(document_id=self.job["ticket_id"], version=1,
                        body="정책", content_hash=policy_body_hash("정책"),
                        active=True, approval_status="APPROVED", data_origin="APPLICATION",
                        allowed_topics=["RETURN"], effective_from="2026-11-01T00:00:00Z",
                        effective_to="2026-12-01T00:00:00Z")
        def refs(doc):
            return eligible_evidence_refs([doc], category="RETURN",
                                          as_of="2026-11-05T00:00:00Z")
        self.assertEqual(refs(document)[0]["version"], 1)
        for key, value in (("active", False), ("data_origin", "SYNTHETIC"),
                           ("allowed_topics", ["REFUND"]),
                           ("effective_to", "2026-11-05T00:00:00Z"),
                           ("effective_from", "2026-11-06T00:00:00Z"),
                           ("effective_from", "2026-11-01")):
            with self.subTest(key=key), self.assertRaises(ValueError):
                refs({**document, key: value})


if __name__ == "__main__":
    unittest.main()
