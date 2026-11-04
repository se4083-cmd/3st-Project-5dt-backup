import json
import secrets
from io import BytesIO
from urllib.error import HTTPError, URLError

import pytest

from app.extensions.p1 import voc_provider as provider


@pytest.fixture
def config():
    return provider.VOCSettings(
        _env_file=None,
        provider="AZURE_OPENAI",
        azure_enabled=True,
        azure_endpoint="https://unit.openai.azure.com",
        azure_deployment="test-model",
        azure_api_key=secrets.token_urlsafe(24),
    )


def value(ids=None):
    return {
        "recommendations": [
            {
                "title": "점검 후보",
                "action": "담당자가 원인을 검증하는 실험을 검토하세요.",
                "evidence_ids": ids or ["risk", "repeat", "rate", "trend"],
            }
        ]
    }


def install(monkeypatch, payload=None, error=None):
    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.close()

    class Opener:
        def open(self, request, timeout):
            if error:
                raise error
            assert request.full_url.startswith(
                "https://unit.openai.azure.com/openai/deployments/test-model/chat/completions?"
            )
            assert timeout <= 30
            assert request.headers["Api-key"]
            body = json.loads(request.data)
            assert body["response_format"] == {"type": "json_object"}
            return Response(payload)

    def opener(*handlers):
        assert isinstance(handlers[0], provider.NoRedirect)
        return Opener()

    monkeypatch.setattr(provider, "build_opener", opener)


def test_azure_transport_is_explicit_bounded_and_validates_citations(config, monkeypatch):
    install(
        monkeypatch,
        json.dumps(
            {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value())}}]}
        ).encode(),
    )
    assert provider.generate(config, {"facts": {}}) == value()


@pytest.mark.parametrize(
    "failure,code",
    [
        (HTTPError("https://unit.openai.azure.com", 429, "private body", {}, None), "AI_RATE_LIMITED"),
        (
            HTTPError("https://unit.openai.azure.com", 401, "private key", {}, None),
            "AI_AUTHENTICATION_FAILED",
        ),
        (HTTPError("https://unit.openai.azure.com", 500, "private body", {}, None), "AI_UNAVAILABLE"),
        (HTTPError("https://unit.openai.azure.com", 302, "redirect", {}, None), "AI_UNAVAILABLE"),
        (TimeoutError("private details"), "AI_TIMEOUT"),
        (URLError("private host info"), "AI_UNAVAILABLE"),
    ],
)
def test_upstream_errors_never_expose_raw_messages(config, monkeypatch, failure, code):
    install(monkeypatch, error=failure)
    with pytest.raises(provider.ProviderFailure) as exc:
        provider.generate(config, {})
    assert str(exc.value) == code


@pytest.mark.parametrize(
    "payload,code",
    [
        (b"not json", "AI_INVALID_OUTPUT"),
        (b"x" * 65537, "AI_INVALID_OUTPUT"),
        (
            json.dumps({"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}).encode(),
            "AI_INCOMPLETE_OUTPUT",
        ),
        (
            json.dumps(
                {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": json.dumps(value(["invented"]))}}
                    ]
                }
            ).encode(),
            "AI_INVALID_OUTPUT",
        ),
        (
            json.dumps(
                {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value(["risk"]))}}]}
            ).encode(),
            "AI_EVIDENCE_REFERENCES_REQUIRED",
        ),
    ],
)
def test_bad_or_truncated_output_cannot_be_saved_as_proposal(config, monkeypatch, payload, code):
    install(monkeypatch, payload)
    with pytest.raises(provider.ProviderFailure, match=code):
        provider.generate(config, {})


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://unit.openai.azure.com",
        "https://evil.invalid",
        "https://unit.openai.azure.com/path",
        "https://user:pass@unit.openai.azure.com",
        "https://unit.openai.azure.com:bad",
    ],
)
def test_unapproved_endpoints_rejected_without_transport(config, monkeypatch, endpoint):
    config.azure_endpoint = endpoint
    monkeypatch.setattr(
        provider, "build_opener", lambda *args: pytest.fail("Invalid destination must not be called")
    )
    with pytest.raises(provider.ProviderFailure, match="AZURE_CONFIGURATION_REQUIRED"):
        provider.generate(config, {})


def test_disabled_azure_has_no_fallback(config, monkeypatch):
    config.azure_enabled = False
    monkeypatch.setattr(provider, "build_opener", lambda *args: pytest.fail("Disabled transport"))
    with pytest.raises(provider.ProviderFailure, match="AZURE_CALLS_DISABLED"):
        provider.generate(config, {})
