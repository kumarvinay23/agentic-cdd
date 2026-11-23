"""Per-request LLM override helpers (body + headers)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from agetic_cdd_api.llm_request import (
    merge_llm_overrides,
    override_from_body,
    override_from_headers,
)
from agetic_cdd_api.services_llm import LlmOverride


def test_override_from_body_nested_and_flat() -> None:
    nested = override_from_body(
        {"llm": {"provider": "anthropic", "model": "claude-sonnet-4-5"}}
    )
    assert nested is not None
    assert nested.provider == "anthropic"
    assert nested.model == "claude-sonnet-4-5"

    flat = override_from_body(
        {"llm_provider": "openai", "llm_model": "gpt-4o-mini", "llm_api_key": "sk-test"}
    )
    assert flat is not None
    assert flat.provider == "openai"
    assert flat.api_key == "sk-test"


def test_body_wins_over_headers() -> None:
    header = override_from_headers(
        x_agetic_llm_provider="gemini",
        x_agetic_llm_model="gemini-3.6-flash",
    )
    body = override_from_body({"llm": {"provider": "openai", "model": "gpt-4o"}})
    merged = merge_llm_overrides(header, body)
    assert merged is not None
    assert merged.provider == "openai"
    assert merged.model == "gpt-4o"


def test_invalid_provider_raises_http() -> None:
    with pytest.raises(HTTPException) as exc:
        override_from_headers(x_agetic_llm_provider="cohere")
    assert exc.value.status_code == 400


def test_public_dict_hides_api_key() -> None:
    ov = LlmOverride(provider="openai", model="gpt-4o", api_key="sk-secret", source="body")
    pub = ov.as_public_dict()
    assert pub["api_key_set"] is True
    assert "sk-secret" not in str(pub)
