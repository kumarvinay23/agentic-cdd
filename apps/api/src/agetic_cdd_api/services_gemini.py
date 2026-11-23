"""Compat shim: Document Workspace / agents historically imported Gemini helpers.

Prefer ``services_llm`` for new code. These wrappers route through the configured
provider (``AGETIC_CDD_LLM_PROVIDER`` = gemini | openai | anthropic).
"""

from __future__ import annotations

from typing import Any

from agetic_cdd_api.services_llm import (
    generate_json as _generate_json,
    llm_configured,
    llm_model,
    llm_provider,
    llm_status,
)


def gemini_configured() -> bool:
    """True when the active LLM provider is configured for synthesis."""
    return llm_configured(require_document_synthesis=True)


def generate_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    """Provider-agnostic JSON generation (Gemini / OpenAI / Anthropic)."""
    return _generate_json(system=system, user=user, temperature=temperature)


__all__ = [
    "gemini_configured",
    "generate_json",
    "llm_configured",
    "llm_model",
    "llm_provider",
    "llm_status",
]
