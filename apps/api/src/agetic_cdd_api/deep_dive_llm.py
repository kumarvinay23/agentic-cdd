"""Optional Gemini refine for Deep Dive specs (heuristic-first hybrid)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from agetic_cdd_api.settings import settings

logger = logging.getLogger(__name__)

# Slice 3 hybrid pilot — prose-heavy Customer agents only.
HYBRID_CUSTOMER_SLUGS: frozenset[str] = frozenset(
    {
        "customer_satisfaction",
        "buying_behavior",
    }
)

_STOP = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "have",
        "been",
        "were",
        "their",
        "there",
        "about",
        "which",
        "while",
        "where",
        "versus",
        "under",
        "over",
        "into",
        "than",
        "then",
        "also",
        "only",
        "more",
        "most",
        "very",
        "such",
        "same",
        "other",
        "between",
    }
)

_SAT_SYSTEM = """You refine commercial due-diligence customer satisfaction specs.
Return ONE JSON object only. Use ONLY facts present in SOURCE_TEXT or HEURISTIC_SPEC.
Do not invent NPS, %, or driver contributions. Prefer concise analyst phrasing.
If unsure, omit the field or reuse heuristic values.
Schema:
{
  "satisfaction_notes": ["string", ...],   // max 4, grounded in source
  "churn_drivers": [{"driver": "string", "contribution_pct": number|null, "severity": "Critical|High|Medium|Low"|null}, ...]
}
Keep contribution_pct identical to HEURISTIC_SPEC when present. You may reorder or clarify driver labels lightly."""

_BUY_SYSTEM = """You refine commercial due-diligence buying / concentration specs.
Return ONE JSON object only. Use ONLY facts present in SOURCE_TEXT or HEURISTIC_SPEC.
Do not invent metrics, HHI, or percentages. Prefer concise analyst phrasing.
Schema:
{
  "concentration_flags": ["string", ...],  // max 5
  "channel_mix": ["string", ...],         // max 3
  "behavior_notes": ["string", ...]       // max 4
}
Numeric claims in these strings must already appear in SOURCE_TEXT or HEURISTIC_SPEC."""


def deep_dive_llm_enabled() -> bool:
    """True when hybrid refine is flagged on and a Gemini key is configured."""
    return bool(settings.deep_dive_llm) and bool(settings.gemini_api_key.strip())


def refine_customer_spec(
    slug: str,
    payload: dict[str, Any],
    *,
    text: str,
) -> dict[str, Any]:
    """LLM-refine satisfaction / buying specs; always safe to call (no-op if disabled)."""
    if slug not in HYBRID_CUSTOMER_SLUGS:
        return payload
    if not deep_dive_llm_enabled():
        return payload
    if payload.get("empty") or not (text or "").strip():
        return payload

    try:
        from agetic_cdd_api.services_gemini import generate_json
    except Exception:  # noqa: BLE001
        return payload

    clipped = (text or "")[:24_000]
    heuristic_slim = _slim_for_prompt(slug, payload)
    system = _SAT_SYSTEM if slug == "customer_satisfaction" else _BUY_SYSTEM
    user = (
        f"AGENT_SLUG: {slug}\n\n"
        f"HEURISTIC_SPEC:\n{json.dumps(heuristic_slim, ensure_ascii=False)}\n\n"
        f"SOURCE_TEXT:\n{clipped}\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.1)
    if not isinstance(parsed, dict) or not parsed:
        logger.info("Deep Dive LLM refine skipped for %s (no/invalid response)", slug)
        return payload

    if slug == "customer_satisfaction":
        merged = _merge_satisfaction(payload, parsed, clipped)
        changed = (
            merged.get("satisfaction_notes") != payload.get("satisfaction_notes")
            or merged.get("churn_drivers") != payload.get("churn_drivers")
        )
    else:
        merged = _merge_buying(payload, parsed, clipped)
        changed = (
            merged.get("concentration_flags") != payload.get("concentration_flags")
            or merged.get("channel_mix") != payload.get("channel_mix")
            or merged.get("behavior_notes") != payload.get("behavior_notes")
        )

    if not changed:
        return payload

    out = dict(merged)
    out["extractor"] = "hybrid_v1"
    out["llm_refined"] = True
    out["metrics"] = payload.get("metrics") or out.get("metrics") or {}
    return out


def _slim_for_prompt(slug: str, payload: dict[str, Any]) -> dict[str, Any]:
    if slug == "customer_satisfaction":
        return {
            "nps": payload.get("nps"),
            "service_satisfaction_pct": payload.get("service_satisfaction_pct"),
            "peer_nps": payload.get("peer_nps") or [],
            "churn_drivers": payload.get("churn_drivers") or [],
            "satisfaction_notes": payload.get("satisfaction_notes") or [],
        }
    return {
        "concentration_flags": payload.get("concentration_flags") or [],
        "channel_mix": payload.get("channel_mix") or [],
        "buying_metrics": payload.get("buying_metrics") or {},
        "behavior_notes": payload.get("behavior_notes") or [],
        "segment_hhi": payload.get("segment_hhi"),
    }


def _grounded_line(line: str, source: str) -> bool:
    """Accept a prose line only if numbers and key tokens appear in source/heuristic blob."""
    text = (line or "").strip()
    if len(text) < 20 or len(text) > 320:
        return False
    hay = source.lower()
    for num in re.findall(r"\d+(?:\.\d+)?", text):
        if num not in hay and num not in source:
            return False
    tokens = [
        t
        for t in re.findall(r"[a-z]{4,}", text.lower())
        if t not in _STOP
    ]
    if not tokens:
        return True
    hits = sum(1 for t in tokens if t in hay)
    need = 2 if len(tokens) <= 4 else 3
    return hits >= min(need, len(tokens))


def _merge_str_list(
    heuristic: list[Any],
    llm_vals: Any,
    *,
    source: str,
    limit: int,
) -> list[str]:
    if not isinstance(llm_vals, list):
        return [str(x) for x in heuristic if str(x).strip()][:limit]
    grounded: list[str] = []
    seen: set[str] = set()
    for item in llm_vals:
        if not isinstance(item, str):
            continue
        cleaned = re.sub(r"\s+", " ", item).strip()
        if not _grounded_line(cleaned, source):
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        grounded.append(cleaned[:280])
        if len(grounded) >= limit:
            break
    if grounded:
        return grounded
    return [str(x) for x in heuristic if str(x).strip()][:limit]


def _merge_satisfaction(
    heuristic: dict[str, Any],
    llm: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    out = dict(heuristic)
    # Numbers stay heuristic-authoritative.
    hay = source + "\n" + json.dumps(heuristic, ensure_ascii=False)
    out["satisfaction_notes"] = _merge_str_list(
        list(heuristic.get("satisfaction_notes") or []),
        llm.get("satisfaction_notes"),
        source=hay,
        limit=4,
    )
    heur_drivers = list(heuristic.get("churn_drivers") or [])
    llm_drivers = llm.get("churn_drivers")
    if isinstance(llm_drivers, list) and llm_drivers:
        by_pct = {
            round(float(d["contribution_pct"]), 1): d
            for d in heur_drivers
            if isinstance(d, dict) and d.get("contribution_pct") is not None
        }
        merged_drivers: list[dict[str, Any]] = []
        for row in llm_drivers:
            if not isinstance(row, dict):
                continue
            driver = str(row.get("driver") or "").strip()
            if len(driver) < 8:
                continue
            pct = row.get("contribution_pct")
            try:
                pct_f = float(pct) if pct is not None else None
            except (TypeError, ValueError):
                pct_f = None
            # Contribution must match a heuristic driver or appear in source.
            if pct_f is not None:
                key = round(pct_f, 1)
                if key not in by_pct and f"{pct_f:g}%" not in source and f"{int(pct_f)}%" not in source:
                    continue
                base = by_pct.get(key) or {}
                severity = row.get("severity") or base.get("severity")
                if severity and str(severity).title() not in {"Critical", "High", "Medium", "Low"}:
                    severity = base.get("severity")
                # Light label refine only if grounded.
                label = driver if _grounded_line(driver, hay) else str(base.get("driver") or driver)
                merged_drivers.append(
                    {
                        "driver": label[:160],
                        "contribution_pct": pct_f,
                        "severity": (str(severity).title() if severity else None),
                    }
                )
            elif _grounded_line(driver, hay):
                merged_drivers.append(
                    {
                        "driver": driver[:160],
                        "contribution_pct": None,
                        "severity": None,
                    }
                )
            if len(merged_drivers) >= 7:
                break
        if merged_drivers:
            out["churn_drivers"] = merged_drivers
    return out


def _merge_buying(
    heuristic: dict[str, Any],
    llm: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    out = dict(heuristic)
    hay = source + "\n" + json.dumps(heuristic, ensure_ascii=False)
    out["concentration_flags"] = _merge_str_list(
        list(heuristic.get("concentration_flags") or []),
        llm.get("concentration_flags"),
        source=hay,
        limit=5,
    )
    out["channel_mix"] = _merge_str_list(
        list(heuristic.get("channel_mix") or []),
        llm.get("channel_mix"),
        source=hay,
        limit=3,
    )
    out["behavior_notes"] = _merge_str_list(
        list(heuristic.get("behavior_notes") or []),
        llm.get("behavior_notes"),
        source=hay,
        limit=4,
    )
    # Metrics / HHI never overridden by LLM.
    return out
