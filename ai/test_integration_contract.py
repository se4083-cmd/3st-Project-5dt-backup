import copy
import hashlib
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from classify_inquiry import classify_inquiry
from classify_with_signals import analyze_inquiry
from integration_contract import (
    backend_category, policy_body_hash, draft_content_hash,
    evidence_refs_from_documents, execution_metadata,
)


class IntegrationTests(unittest.TestCase):
    def test_category_boundary_only(self):
        self.assertEqual(backend_category("UNKNOWN"), "UNCLASSIFIED")
        for category in ("DELIVERY", "RETURN", "REFUND", "PRODUCT", "PAYMENT", "ACCOUNT"):
            self.assertEqual(backend_category(category), category)
        for value in ("unknown", "UNKNOWN text", None, []):
            with self.assertRaises(ValueError):
                backend_category(value)

    def test_full_input_and_tail_evidence(self):
        tail = "상담사와 연결해 주세요."
        inquiry = " " + "가" * (10000 - len(tail) - 2) + tail + " "
        for function in (classify_inquiry, analyze_inquiry):
            payload = {"category": "DELIVERY", "summary": "배송 문의와 사람 연결 요청"}
            if function is analyze_inquiry:
                payload.update(risk_tags=["HUMAN_REQUEST"],
                               risk_evidence=[{"tag": "HUMAN_REQUEST", "quote": tail}])
            response = SimpleNamespace(status="completed", output=[],
                                       output_text=json.dumps(payload), model="actual-model")
            client = Mock()
            client.responses.create.return_value = response
            result, returned = function(client, "configured-deployment", inquiry)
            self.assertIs(returned, response)
            self.assertEqual(client.responses.create.call_args.kwargs["input"], inquiry)
            if function is analyze_inquiry:
                self.assertTrue(result["review_required"])
                self.assertEqual(result["risk_evidence"][0]["quote"], tail)
            for invalid in (inquiry + "x", "", "  ", None):
                client.reset_mock()
                with self.assertRaises(ValueError):
                    function(client, "configured-deployment", invalid)
                client.responses.create.assert_not_called()

    def test_exact_hashes_and_structured_refs(self):
        body = " 정책\r\n본문 e\u0301 \n"
        expected = hashlib.sha256(body.encode("utf-8")).hexdigest()
        self.assertEqual(policy_body_hash(body), expected)
        self.assertEqual(draft_content_hash(body), expected)
        self.assertNotEqual(expected, policy_body_hash(body.strip()))
        document = {"document_id": "12345678-1234-4234-8234-123456789abc",
                    "version": 1, "body": body, "content_hash": expected,
                    "approval_status": "DRAFT_REQUIRES_TEAM_REVIEW", "active": False}
        original = copy.deepcopy(document)
        refs = evidence_refs_from_documents([document])
        self.assertEqual(document, original)
        self.assertIsInstance(refs, list)
        self.assertEqual(set(refs[0]), {"document_id", "version", "content_hash"})
        for invalid in ([{**document, "version": True}],
                        [{**document, "document_id": "COUPANG_REFERENCE"}],
                        [{**document, "body": body.strip()}],
                        [document, document], json.dumps([document]), []):
            with self.assertRaises(ValueError):
                evidence_refs_from_documents(invalid)

    def test_runtime_metadata(self):
        self.assertEqual(execution_metadata(SimpleNamespace(model="actual-model"),
                                           prompt_version="signals_draft_v3"),
                         {"prompt_version": "signals_draft_v3", "model_version": "actual-model"})
        with self.assertRaises(ValueError):
            execution_metadata(SimpleNamespace(model="NONE"), prompt_version="v1")


if __name__ == "__main__":
    unittest.main()
