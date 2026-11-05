"""Offline complaint field and typed validation boundary regressions."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from ai.analysis_errors import AnalysisResponseError
from ai.analysis_service import AIAnalysisError, analyze_job_checked
from ai.classify_with_signals import (
    OUTPUT_SCHEMA, VOC_OUTPUT_SCHEMA, VOC_PROMPT_VERSION, validate_payload,
)
from ai.mock_analysis import MockAnalysisClient
from ai.test_analysis_service import job


class VOCPredictionTests(unittest.TestCase):
    def test_disabled_is_unexecuted_null_and_legacy_prompt(self):
        client = MockAnalysisClient("complaint")
        create = client.responses.create
        client.responses.create = Mock(side_effect=create)
        result = analyze_job_checked(client, "mock", job(), client.fixture["inquiry"])
        self.assertIsNone(result["analysis"]["voc_predicted_is_complaint"])
        sent = client.responses.create.call_args.kwargs
        self.assertNotIn("voc_predicted_is_complaint", sent["text"]["format"]["schema"]["properties"])
        self.assertNotEqual(result["execution"]["prompt_version"], VOC_PROMPT_VERSION)

    def test_opt_in_true_false_null_independent_of_review(self):
        for name, prediction, review in (
            ("complaint", True, False), ("delivery", False, False),
            ("human_request", False, True), ("unknown", None, True),
        ):
            with self.subTest(name=name):
                client = MockAnalysisClient(name)
                result = analyze_job_checked(client, "mock", job(), client.fixture["inquiry"],
                                             predict_complaint=True)
                self.assertIs(result["analysis"]["voc_predicted_is_complaint"], prediction)
                self.assertIs(result["analysis"]["review_required"], review)
                self.assertEqual(result["execution"]["prompt_version"], VOC_PROMPT_VERSION)
                self.assertTrue({"is_complaint", "label_status", "allowed", "draft"}.isdisjoint(result["analysis"]))

    def test_only_exact_bool_or_null_and_field_required(self):
        fixture = MockAnalysisClient().fixture
        for value in (0, 1, "true", "false", [], {}):
            with self.subTest(value=value), self.assertRaises(AnalysisResponseError):
                validate_payload({**fixture["payload"], "voc_predicted_is_complaint": value},
                                 fixture["inquiry"], predict_complaint=True)
        with self.assertRaises(AnalysisResponseError):
            validate_payload(fixture["payload"], fixture["inquiry"], predict_complaint=True)

    def test_model_cannot_supply_final_labels(self):
        fixture = MockAnalysisClient().fixture
        for key in ("is_complaint", "label_status"):
            with self.subTest(key=key), self.assertRaises(AnalysisResponseError):
                validate_payload({**fixture["payload"], "voc_predicted_is_complaint": False, key: None},
                                 fixture["inquiry"], predict_complaint=True)

    def test_programming_value_type_key_attribute_errors_propagate(self):
        for error in (ValueError("bug"), TypeError("bug"), KeyError("bug"), AttributeError("bug")):
            with self.subTest(kind=type(error)), patch("ai.analysis_service.analyze_job", side_effect=error):
                with self.assertRaises(type(error)):
                    analyze_job_checked(Mock(), "mock", job(), "문의")

    def test_malformed_responses_are_explicit_response_errors(self):
        payload = json.dumps(MockAnalysisClient().fixture["payload"])
        base = dict(status="completed", output=[], output_text=payload, model="mock")
        broken = [
            {k: v for k, v in base.items() if k != "output"},
            {**base, "output": None},
            {**base, "output": [SimpleNamespace()]},
            {**base, "output": [SimpleNamespace(type="message")]},
            {**base, "output": [SimpleNamespace(type="message", content=[SimpleNamespace()])]},
            {k: v for k, v in base.items() if k != "status"},
            {**base, "status": "incomplete"},
            {**base, "output_text": "not JSON"},
            {**base, "output_text": None},
            {k: v for k, v in base.items() if k != "model"},
        ]
        for fields in broken:
            with self.subTest(fields=list(fields)):
                client = Mock()
                client.responses.create.return_value = SimpleNamespace(**fields)
                with self.assertRaises(AIAnalysisError) as ctx:
                    analyze_job_checked(client, "mock", job(), "문의")
                self.assertEqual(ctx.exception.code, "INVALID_ANALYSIS_RESPONSE")
                self.assertFalse(ctx.exception.retryable)
                client.responses.create.assert_called_once()

    def test_option_validation_and_schema_isolation(self):
        original = deepcopy(OUTPUT_SCHEMA)
        self.assertNotIn("voc_predicted_is_complaint", original["properties"])
        self.assertIn("voc_predicted_is_complaint", VOC_OUTPUT_SCHEMA["required"])
        client = Mock()
        with self.assertRaises(AIAnalysisError) as ctx:
            analyze_job_checked(client, "mock", job(), "문의", predict_complaint=1)
        self.assertEqual(ctx.exception.code, "INVALID_ANALYSIS_OPTIONS")
        client.responses.create.assert_not_called()
        self.assertEqual(OUTPUT_SCHEMA, original)

    def test_backend_revalidates_substituted_analysis_before_indexing(self):
        for analysis in (None, {}, {"category": "DELIVERY"}):
            with self.subTest(analysis=analysis), patch(
                "ai.backend_adapter.analyze_inquiry", return_value=(analysis, SimpleNamespace(model="mock"))
            ):
                with self.assertRaises(AIAnalysisError) as ctx:
                    analyze_job_checked(Mock(), "mock", job(), "문의")
                self.assertEqual(ctx.exception.code, "INVALID_ANALYSIS_RESPONSE")


if __name__ == "__main__":
    unittest.main()
