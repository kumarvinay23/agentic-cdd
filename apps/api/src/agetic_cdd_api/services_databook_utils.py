"""Shared databook string helpers (no classify/coverage imports)."""

from __future__ import annotations

import re
from typing import Any

HINT_SPLIT = re.compile(r"[\s_\-./]+")


def canonicalize_metric_key(key: Any) -> str:
    """Normalize metric labels to underscore form (``gross profit`` → ``gross_profit``)."""
    raw = str(key or "").strip().lower().replace("-", "_")
    parts = [p for p in raw.replace(" ", "_").split("_") if p]
    return "_".join(parts)


def text_matches_hints(blob: str, hints: list[str]) -> bool:
    """True when any hint matches filename/excerpt/basis blob.

    Multi-word hints require all tokens to appear as whole tokens in the blob
    (not raw substrings — avoids ``in`` matching inside ``information``).
    """
    low = (blob or "").lower()
    blob_tokens = {t for t in HINT_SPLIT.split(low) if t}
    for hint in hints:
        h = hint.strip().lower()
        if not h:
            continue
        if h in low:
            return True
        tokens = [t for t in HINT_SPLIT.split(h) if t]
        if len(tokens) > 1 and all(t in blob_tokens for t in tokens):
            return True
    return False
