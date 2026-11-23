"""Resolve per-request LLM overrides from JSON body and/or headers."""

from __future__ import annotations

from typing import Any

from fastapi import Header, HTTPException, status
from pydantic import BaseModel, Field

from agetic_cdd_api.services_llm import LlmOverride, resolve_llm_override

# Public header names (also allowed in CORS).
HEADER_PROVIDER = "X-Agetic-LLM-Provider"
HEADER_MODEL = "X-Agetic-LLM-Model"
HEADER_API_KEY = "X-Agetic-LLM-API-Key"


class LlmOptionsBody(BaseModel):
    """Optional LLM selection nested under ``llm`` or flat on the parent body."""

    provider: str | None = Field(
        default=None, description="gemini | openai | anthropic"
    )
    model: str | None = Field(default=None, description="Model id for the provider")
    api_key: str | None = Field(
        default=None,
        description="Optional one-shot key (not stored; env keys used if omitted)",
    )


def override_from_headers(
    *,
    x_agetic_llm_provider: str | None = None,
    x_agetic_llm_model: str | None = None,
    x_agetic_llm_api_key: str | None = None,
) -> LlmOverride | None:
    try:
        return resolve_llm_override(
            provider=x_agetic_llm_provider,
            model=x_agetic_llm_model,
            api_key=x_agetic_llm_api_key,
            source="header",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


def override_from_body(
    body: Any | None,
    *,
    source: str = "body",
) -> LlmOverride | None:
    """Accept ``llm: {provider, model, api_key}`` or flat ``llm_provider`` fields."""
    if body is None:
        return None
    data: dict[str, Any]
    if isinstance(body, BaseModel):
        data = body.model_dump(exclude_unset=True)
    elif isinstance(body, dict):
        data = dict(body)
    else:
        return None

    nested = data.get("llm")
    if isinstance(nested, BaseModel):
        nested = nested.model_dump(exclude_unset=True)
    if isinstance(nested, dict):
        try:
            return resolve_llm_override(nested, source=source)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            ) from exc

    try:
        return resolve_llm_override(
            {
                "provider": data.get("llm_provider"),
                "model": data.get("llm_model"),
                "api_key": data.get("llm_api_key"),
            },
            source=source,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


def merge_llm_overrides(
    *overrides: LlmOverride | None,
) -> LlmOverride | None:
    """Merge overrides; later non-empty fields win (body over headers typically)."""
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    source = "request"
    any_set = False
    for ov in overrides:
        if ov is None:
            continue
        any_set = True
        source = ov.source or source
        if ov.provider:
            provider = ov.provider
        if ov.model:
            model = ov.model
        if ov.api_key:
            api_key = ov.api_key
    if not any_set:
        return None
    return LlmOverride(
        provider=provider, model=model, api_key=api_key, source=source
    )


def resolve_request_llm(
    body: Any | None = None,
    *,
    x_agetic_llm_provider: str | None = Header(default=None, alias=HEADER_PROVIDER),
    x_agetic_llm_model: str | None = Header(default=None, alias=HEADER_MODEL),
    x_agetic_llm_api_key: str | None = Header(default=None, alias=HEADER_API_KEY),
) -> LlmOverride | None:
    """FastAPI-friendly merge: headers first, body wins on conflicts."""
    header_ov = override_from_headers(
        x_agetic_llm_provider=x_agetic_llm_provider,
        x_agetic_llm_model=x_agetic_llm_model,
        x_agetic_llm_api_key=x_agetic_llm_api_key,
    )
    body_ov = override_from_body(body, source="body")
    # Body wins for fields it sets.
    return merge_llm_overrides(header_ov, body_ov)
