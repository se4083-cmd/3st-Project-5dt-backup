"""Offline package/legacy import and typed-error regression tests."""
import copy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from openai import (APIConnectionError, APIStatusError, APITimeoutError,
                    AuthenticationError, PermissionDeniedError, RateLimitError)

from ai.analysis_service import AIAnalysisError, analyze_job_checked
from ai.backend_adapter import analyze_job
from ai.mock_analysis import MockAnalysisClient


def job():
    return dict(job_id="12345678-1234-4234-8234-123456789abc",
                ticket_id="12345678-1234-4234-8234-123456789abd",
                lease_token="12345678-1234-4234-8234-123456789abe",
                lease_owner="worker", cycle_no=1, expected_ticket_version=1,
                automation_generation=1, job_kind="AUTO")


class AnalysisServiceTests(unittest.TestCase):
    def test_mock_success_matches_legacy_and_preserves_job(self):
        for scenario in ("delivery", "human_request", "unknown"):
            with self.subTest(scenario=scenario):
                client = MockAnalysisClient(scenario)
                context = job()
                before = copy.deepcopy(context)
                result = analyze_job_checked(client, "mock", context, client.fixture["inquiry"])
                self.assertIs(result["analysis"]["voc_predicted_is_complaint"], None if scenario == "unknown" else False)
                self.assertEqual(context, before)
                self.assertEqual(result, analyze_job(client, "mock", context, client.fixture["inquiry"]))
                self.assertEqual(set(result), {"job", "category", "analysis", "execution"})
                self.assertTrue({"draft", "allowed", "confidence",
                                 "is_complaint", "handoff"}.isdisjoint(result["analysis"]))
                self.assertEqual(result["analysis"]["review_required"], scenario != "delivery")
                self.assertEqual(result["execution"]["model_version"], "MOCK_ANALYSIS_ONLY")

    def test_invalid_inputs_never_call_client(self):
        client = Mock()
        for context, deployment, inquiry, code in (
            ({**job(), "job_kind": "HANDOFF"}, "mock", "문의", "INVALID_JOB_CONTEXT"),
            (job(), "mock", " " * 2, "INVALID_INQUIRY"),
            (job(), "mock", "문" * 10001, "INVALID_INQUIRY"),
            (job(), " ", "문의", "INVALID_DEPLOYMENT"),
        ):
            with self.subTest(code=code), self.assertRaises(AIAnalysisError) as ctx:
                analyze_job_checked(client, deployment, context, inquiry)
            self.assertEqual(ctx.exception.as_dict(), {"code": code, "retryable": False})
        client.responses.create.assert_not_called()

    def test_sdk_errors_have_safe_codes_without_retry_loop(self):
        request = SimpleNamespace()
        response = lambda status: SimpleNamespace(request=request, status_code=status, headers={})
        errors = [
            (APITimeoutError(request=request), "AI_TIMEOUT", True),
            (APIConnectionError(request=request), "AI_CONNECTION_FAILED", True),
            (RateLimitError("secret", response=response(429), body=None), "AI_RATE_LIMITED", True),
            (AuthenticationError("secret", response=response(401), body=None), "AI_AUTHENTICATION_FAILED", False),
            (PermissionDeniedError("secret", response=response(403), body=None), "AI_PERMISSION_DENIED", False),
            (APIStatusError("secret", response=response(503), body=None), "AI_SERVICE_UNAVAILABLE", True),
            (APIStatusError("secret", response=response(400), body=None), "AI_REQUEST_REJECTED", False),
        ]
        for error, code, retryable in errors:
            with self.subTest(code=code):
                client = Mock()
                client.responses.create.side_effect = error
                with self.assertRaises(AIAnalysisError) as ctx:
                    analyze_job_checked(client, "mock", job(), "문의")
                self.assertEqual(ctx.exception.as_dict(), {"code": code, "retryable": retryable})
                self.assertEqual(str(ctx.exception), code)
                self.assertNotIn("secret", str(ctx.exception))
                client.responses.create.assert_called_once()

    def test_invalid_output_is_not_retried(self):
        client = MockAnalysisClient()
        client.fixture["payload"]["risk_tags"] = ["HUMAN_REQUEST"]
        with self.assertRaises(AIAnalysisError) as ctx:
            analyze_job_checked(client, "mock", job(), client.fixture["inquiry"])
        self.assertEqual(ctx.exception.code, "INVALID_ANALYSIS_RESPONSE")
        self.assertFalse(ctx.exception.retryable)
        self.assertEqual(client.calls, 1)

    def test_stale_context_has_distinct_code(self):
        client = MockAnalysisClient()
        context = job()
        create = client.responses.create
        def changed(**kwargs):
            result = create(**kwargs)
            context["lease_owner"] = "replacement"
            return result
        client.responses.create = changed
        with self.assertRaises(AIAnalysisError) as ctx:
            analyze_job_checked(client, "mock", context, client.fixture["inquiry"])
        self.assertEqual(ctx.exception.code, "STALE_JOB_CONTEXT")
        self.assertFalse(ctx.exception.retryable)

    def test_unexpected_programming_error_is_not_disguised_as_retry(self):
        with patch("ai.analysis_service.analyze_job", side_effect=RuntimeError("bug")):
            with self.assertRaises(RuntimeError):
                analyze_job_checked(Mock(), "mock", job(), "문의")

    def test_mock_requires_exact_fixture_and_never_calls_network(self):
        client = MockAnalysisClient()
        with self.assertRaises(ValueError):
            client.responses.create(input="別の問い合わせ")
        self.assertEqual(client.calls, 0)

    def test_imports_work_from_another_directory_with_repo_on_pythonpath(self):
        import os
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [sys.executable, "-c", "from ai.backend_adapter import analyze_job; "
             "from ai.analysis_service import analyze_job_checked; print('package-ok')"],
            cwd=root.parent, env={**os.environ, "PYTHONPATH": str(root)},
            capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), "package-ok")

    def test_offline_example_does_not_log_lease(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, "-m", "ai.examples.backend_b_analysis"],
                                cwd=root, capture_output=True, text=True, check=True)
        self.assertEqual(len(result.stdout.strip().splitlines()), 4)
        self.assertNotIn("lease_token", result.stdout)
        self.assertNotIn("12345678-1234-4234-8234-123456789abe", result.stdout)


if __name__ == "__main__":
    unittest.main()
