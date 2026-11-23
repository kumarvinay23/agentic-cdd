"""Provider-agnostic LLM routing (no live network)."""

from __future__ import annotations

import json
from io import BytesIO
from urllib.error import HTTPError

import pytest

from agetic_cdd_api import services_llm as llm


@pytest.fixture(autouse=True)
def _reset_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.settings, "document_synthesis_llm", True)
    monkeypatch.setattr(llm.settings, "llm_provider", "gemini")
    monkeypatch.setattr(llm.settings, "llm_model", "")
    monkeypatch.setattr(llm.settings, "llm_api_key", "")
    monkeypatch.setattr(llm.settings, "gemini_api_key", "gemini-test-key")
    monkeypatch.setattr(llm.settings, "gemini_model", "gemini-3.6-flash")
    monkeypatch.setattr(llm.settings, "openai_api_key", "openai-test-key")
    monkeypatch.setattr(llm.settings, "openai_model", "gpt-4o-mini")
    monkeypatch.setattr(llm.settings, "openai_base_url", "https://api.openai.com/v1")
    monkeypatch.setattr(llm.settings, "anthropic_api_key", "anthropic-test-key")
    monkeypatch.setattr(llm.settings, "anthropic_model", "claude-sonnet-4-5")


def test_llm_provider_and_model_defaults() -> None:
    assert llm.llm_provider() == "gemini"
    assert llm.llm_model() == "gemini-3.6-flash"
    assert llm.llm_configured() is True


def test_llm_provider_openai_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    monkeypatch.setattr(llm.settings, "llm_model", "gpt-4.1-mini")
    assert llm.llm_provider() == "openai"
    assert llm.llm_model() == "gpt-4.1-mini"
    assert llm.llm_api_key() == "openai-test-key"


def test_llm_status_hides_secrets() -> None:
    status = llm.llm_status()
    assert status["provider"] == "gemini"
    assert status["api_key_set"] is True
    assert "gemini-test-key" not in json.dumps(status)


def test_generate_json_routes_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    captured: dict = {}

    def fake_http(url, payload, *, headers, label):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["label"] = label
        return {
            "choices": [
                {"message": {"content": json.dumps({"ok": True, "provider": "openai"})}}
            ]
        }

    monkeypatch.setattr(llm, "_http_json", fake_http)
    out = llm.generate_json(system="sys", user="user", temperature=0.1)
    assert out == {"ok": True, "provider": "openai"}
    assert captured["label"] == "OpenAI"
    assert captured["url"].endswith("/chat/completions")
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["headers"]["Authorization"].startswith("Bearer ")


def test_generate_json_routes_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.settings, "llm_provider", "anthropic")

    def fake_http(url, payload, *, headers, label):
        assert label == "Anthropic"
        assert "x-api-key" in headers
        return {
            "content": [
                {
                    "type": "text",
                    "text": "```json\n{\"ranked\": []}\n```",
                }
            ]
        }

    monkeypatch.setattr(llm, "_http_json", fake_http)
    out = llm.generate_json(system="sys", user="user")
    assert out == {"ranked": []}


def test_generate_json_routes_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_http(url, payload, *, headers, label):
        assert label == "Gemini"
        assert "generateContent" in url
        assert payload["generationConfig"]["responseMimeType"] == "application/json"
        return {
            "candidates": [
                {"content": {"parts": [{"text": json.dumps({"hello": "world"})}]}}
            ]
        }

    monkeypatch.setattr(llm, "_http_json", fake_http)
    out = llm.generate_json(system="sys", user="user")
    assert out == {"hello": "world"}


def test_gemini_compat_shim_uses_active_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from agetic_cdd_api import services_gemini as gem

    monkeypatch.setattr(llm.settings, "llm_provider", "openai")
    monkeypatch.setattr(
        gem,
        "_generate_json",
        lambda **kwargs: {"via": "openai"},
    )
    assert gem.gemini_configured() is True
    assert gem.generate_json(system="s", user="u") == {"via": "openai"}


def test_request_override_routes_and_records_invocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict = {}

    def fake_http(url, payload, *, headers, label):
        captured["label"] = label
        captured["url"] = url
        captured["model"] = payload.get("model")
        return {
            "choices": [{"message": {"content": json.dumps({"picked": "openai"})}}]
        }

    monkeypatch.setattr(llm, "_http_json", fake_http)
    override = llm.resolve_llm_override(
        {"provider": "openai", "model": "gpt-4o-mini"}, source="body"
    )
    with llm.use_llm_override(override):
        assert llm.llm_provider() == "openai"
        assert llm.llm_model() == "gpt-4o-mini"
        out = llm.generate_json(system="s", user="u")
        inv = llm.llm_last_invocation()
    assert out == {"picked": "openai"}
    assert captured["label"] == "OpenAI"
    assert inv is not None
    assert inv["provider"] == "openai"
    assert inv["model"] == "gpt-4o-mini"
    assert inv["ok"] is True
    assert inv["source"] == "body"
    # Override must not leak after context exits.
    assert llm.llm_provider() == "gemini"


def test_resolve_llm_override_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        llm.resolve_llm_override({"provider": "cohere"})


def test_http_error_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def read(self):
            return b'{"error":"nope"}'

    def boom(*_a, **_k):
        raise HTTPError(
            "https://example.com",
            401,
            "Unauthorized",
            hdrs=None,  # type: ignore[arg-type]
            fp=BytesIO(b'{"error":"nope"}'),
        )

    monkeypatch.setattr(llm.urllib.request, "urlopen", boom)
    assert (
        llm._http_json(
            "https://example.com",
            {},
            headers={"Content-Type": "application/json"},
            label="OpenAI",
        )
        is None
    )
