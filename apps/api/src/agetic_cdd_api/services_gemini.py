"""Thin Gemini client for Document Workspace synthesis (REST, no extra SDK)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

from agetic_cdd_api.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 45


def gemini_configured() -> bool:
    return bool(settings.gemini_api_key.strip()) and bool(settings.document_synthesis_llm)


def generate_json(
    *,
    system: str,
    user: str,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    """
    Call Gemini generateContent and parse a JSON object response.

    Returns None on missing key, transport errors, or invalid JSON.
    """
    api_key = settings.gemini_api_key.strip()
    if not api_key:
        return None

    model = (settings.gemini_model or "gemini-3.6-flash").strip()
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
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:
            pass
        logger.warning("Gemini HTTP %s: %s", exc.code, body)
        return None
    except Exception as exc:  # noqa: BLE001 — network/timeouts → heuristic fallback
        logger.warning("Gemini request failed: %s", exc)
        return None

    try:
        envelope = json.loads(raw)
        text = (
            envelope.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not text:
            logger.warning("Gemini empty response: %s", raw[:400])
            return None
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        logger.warning("Gemini JSON was not an object")
        return None
    except (json.JSONDecodeError, TypeError, IndexError, KeyError) as exc:
        logger.warning("Gemini parse failed: %s", exc)
        return None
