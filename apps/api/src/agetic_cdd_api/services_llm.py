"""Provider-agnostic LLM client for JSON generation.

Defaults come from env (``AGETIC_CDD_LLM_PROVIDER`` / keys / models).
Per-request overrides can be passed from API body or headers and applied via
``use_llm_override`` / ``resolve_llm_override`` — including into background
pipeline workers. ``llm_last_invocation()`` reports which provider was actually
called (no secrets).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

from agetic_cdd_api.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 60
_PROVIDERS = frozenset({"gemini", "openai", "anthropic"})
_DEFAULT_MODELS = {
    "gemini": "gemini-3.6-flash",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
}

# Request/worker-scoped override (body, headers, or explicit pipeline pass-through).
_override_ctx: ContextVar["LlmOverride | None"] = ContextVar(
    "llm_override", default=None
)
_last_invocation_ctx: ContextVar[dict[str, Any] | None] = ContextVar(
    "llm_last_invocation", default=None
)


@dataclass(frozen=True)
class LlmOverride:
    """Optional per-call / per-request LLM selection."""

    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    source: str = "request"

    def as_public_dict(self) -> dict[str, Any]:
        """Safe for API responses — never includes api_key."""
        return {
            "provider": (self.provider or "").strip().lower() or None,
            "model": (self.model or "").strip() or None,
            "api_key_set": bool((self.api_key or "").strip()),
            "source": self.source,
        }


def resolve_llm_override(
    raw: dict[str, Any] | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    source: str = "request",
) -> LlmOverride | None:
    """Build an override from a body/header dict. Returns None if nothing set."""
    data = dict(raw or {})
    prov = provider if provider is not None else data.get("provider") or data.get("llm_provider")
    mod = model if model is not None else data.get("model") or data.get("llm_model")
    key = api_key if api_key is not None else data.get("api_key") or data.get("llm_api_key")
    prov_s = str(prov or "").strip().lower() or None
    mod_s = str(mod or "").strip() or None
    key_s = str(key or "").strip() or None
    if prov_s and prov_s not in _PROVIDERS:
        raise ValueError(
            f"Unsupported LLM provider {prov_s!r}; "
            f"expected one of: {', '.join(sorted(_PROVIDERS))}"
        )
    if not prov_s and not mod_s and not key_s:
        return None
    return LlmOverride(provider=prov_s, model=mod_s, api_key=key_s, source=source)


def get_llm_override() -> LlmOverride | None:
    return _override_ctx.get()


def set_llm_override(override: LlmOverride | None) -> Token:
    """Set override for the current context (caller must reset the token)."""
    return _override_ctx.set(override)


def reset_llm_override(token: Token) -> None:
    _override_ctx.reset(token)


@contextmanager
def use_llm_override(override: LlmOverride | None) -> Iterator[LlmOverride | None]:
    """Apply a request/worker override for the duration of the block."""
    token = set_llm_override(override)
    try:
        yield override
    finally:
        reset_llm_override(token)


def llm_provider() -> str:
    """Active provider id (override → settings; unknown → gemini)."""
    ov = get_llm_override()
    if ov and ov.provider:
        return ov.provider if ov.provider in _PROVIDERS else "gemini"
    raw = str(settings.llm_provider or "gemini").strip().lower()
    return raw if raw in _PROVIDERS else "gemini"


def llm_model() -> str:
    """Resolved model id for the active provider."""
    ov = get_llm_override()
    if ov and ov.model:
        return ov.model
    override = str(settings.llm_model or "").strip()
    if override:
        return override
    provider = llm_provider()
    if provider == "openai":
        return (settings.openai_model or _DEFAULT_MODELS["openai"]).strip()
    if provider == "anthropic":
        return (settings.anthropic_model or _DEFAULT_MODELS["anthropic"]).strip()
    return (settings.gemini_model or _DEFAULT_MODELS["gemini"]).strip()


def llm_api_key() -> str:
    """API key for the active provider (override → provider env → shared)."""
    ov = get_llm_override()
    if ov and ov.api_key:
        return ov.api_key
    shared = str(settings.llm_api_key or "").strip()
    provider = llm_provider()
    if provider == "openai":
        return str(settings.openai_api_key or "").strip() or shared
    if provider == "anthropic":
        return str(settings.anthropic_api_key or "").strip() or shared
    return str(settings.gemini_api_key or "").strip() or shared


def llm_configured(*, require_document_synthesis: bool = True) -> bool:
    """True when the active provider has a key (and synthesis switch is on)."""
    if require_document_synthesis and not bool(settings.document_synthesis_llm):
        return False
    return bool(llm_api_key())


def llm_status() -> dict[str, Any]:
    """Inspectable status for health / UI — no secrets."""
    ov = get_llm_override()
    return {
        "provider": llm_provider(),
        "model": llm_model(),
        "configured": llm_configured(),
        "document_synthesis_llm": bool(settings.document_synthesis_llm),
        "api_key_set": bool(llm_api_key()),
        "override": ov.as_public_dict() if ov else None,
        "supported_providers": sorted(_PROVIDERS),
        "last_invocation": llm_last_invocation(),
    }


def llm_selection(*, source_fallback: str = "settings") -> dict[str, Any]:
    """Public selection snapshot (what will be / was targeted). No secrets."""
    ov = get_llm_override()
    return {
        "provider": llm_provider(),
        "model": llm_model(),
        "configured": llm_configured(require_document_synthesis=False),
        "api_key_set": bool(llm_api_key()),
        "source": ov.source if ov else source_fallback,
    }


def llm_last_invocation() -> dict[str, Any] | None:
    """Last ``generate_json`` call in this context (provider/model/ok). No secrets."""
    return _last_invocation_ctx.get()


def _record_invocation(*, provider: str, model: str, ok: bool, error: str | None = None) -> None:
    ov = get_llm_override()
    _last_invocation_ctx.set(
        {
            "provider": provider,
            "model": model,
            "ok": ok,
            "error": error,
            "source": ov.source if ov else "settings",
            "invoked_at": datetime.now(timezone.utc).isoformat(),
        }
    )


def generate_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    """Call the configured/overridden provider and parse a JSON object response.

    Returns None on missing key, transport errors, or invalid JSON.
    Records ``llm_last_invocation()`` for verification.
    """
    if not llm_api_key():
        provider = llm_provider()
        model = llm_model()
        _record_invocation(
            provider=provider, model=model, ok=False, error="missing_api_key"
        )
        return None

    provider = llm_provider()
    model = llm_model()
    logger.info(
        "LLM generate_json provider=%s model=%s source=%s",
        provider,
        model,
        (get_llm_override().source if get_llm_override() else "settings"),
    )

    if provider == "openai":
        parsed = _openai_generate_json(
            system=system, user=user, temperature=temperature, model=model
        )
    elif provider == "anthropic":
        parsed = _anthropic_generate_json(
            system=system, user=user, temperature=temperature, model=model
        )
    else:
        parsed = _gemini_generate_json(
            system=system, user=user, temperature=temperature, model=model
        )

    _record_invocation(
        provider=provider,
        model=model,
        ok=parsed is not None,
        error=None if parsed is not None else "empty_or_failed",
    )
    return parsed


def _gemini_generate_json(
    *,
    system: str,
    user: str,
    temperature: float,
    model: str,
) -> dict[str, Any] | None:
    api_key = llm_api_key()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }
    raw = _http_json(
        url,
        payload,
        headers={"Content-Type": "application/json"},
        label="Gemini",
    )
    if raw is None:
        return None
    try:
        text = (
            raw.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
    except (TypeError, IndexError, KeyError, AttributeError):
        text = ""
    return _parse_json_object(text, label="Gemini")


def _openai_generate_json(
    *,
    system: str,
    user: str,
    temperature: float,
    model: str,
) -> dict[str, Any] | None:
    api_key = llm_api_key()
    base = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    raw = _http_json(
        url,
        payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        label="OpenAI",
    )
    if raw is None:
        return None
    try:
        text = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
    except (TypeError, IndexError, KeyError, AttributeError):
        text = ""
    return _parse_json_object(text, label="OpenAI")


def _anthropic_generate_json(
    *,
    system: str,
    user: str,
    temperature: float,
    model: str,
) -> dict[str, Any] | None:
    api_key = llm_api_key()
    url = "https://api.anthropic.com/v1/messages"
    system_json = (
        f"{system.rstrip()}\n\n"
        "Return ONLY a single valid JSON object. No markdown fences, no prose."
    )
    payload = {
        "model": model,
        "max_tokens": 4096,
        "temperature": temperature,
        "system": system_json,
        "messages": [{"role": "user", "content": user}],
    }
    raw = _http_json(
        url,
        payload,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        label="Anthropic",
    )
    if raw is None:
        return None
    text_parts: list[str] = []
    for block in raw.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text_parts.append(str(block.get("text") or ""))
    return _parse_json_object("\n".join(text_parts), label="Anthropic")


def _http_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str],
    label: str,
) -> dict[str, Any] | None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.warning("%s HTTP %s: %s", label, exc.code, err_body)
        return None
    except Exception as exc:  # noqa: BLE001 — network/timeouts → heuristic fallback
        logger.warning("%s request failed: %s", label, exc)
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        logger.warning("%s envelope parse failed: %s", label, exc)
        return None
    return parsed if isinstance(parsed, dict) else None


def _parse_json_object(text: str, *, label: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw:
        logger.warning("%s empty response text", label)
        return None
    fenced = re.match(r"^```(?:json)?\s*([\s\S]*?)\s*```$", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            logger.warning("%s JSON parse failed (no object)", label)
            return None
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            logger.warning("%s JSON parse failed: %s", label, exc)
            return None
    if isinstance(parsed, dict):
        return parsed
    logger.warning("%s JSON was not an object", label)
    return None
