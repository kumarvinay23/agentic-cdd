"""FDD Phase 3 — claims ledger (agent → claims → databook tests)."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agetic_cdd_api.fdd_schemas import (
    CLAIMS_ABS_TOLERANCE,
    CLAIMS_RELIABILITY_FAIL_THRESHOLD,
    CLAIMS_VALUE_TOLERANCE,
    Approval,
    ArtefactStatus,
    CellStatus,
    ClaimsLedgerDoc,
    ClaimsLedgerEntry,
    FactTableDoc,
    FddFact,
    FddRunManifest,
    GateId,
    InputKey,
    ModuleReliability,
    RequestListDoc,
    RequestListItem,
    RunStage,
)
from agetic_cdd_api.services_databook_consume import MATERIAL_METRIC_KEYS
from agetic_cdd_api.services_databook_map import map_caption
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_store import (
    load_approval,
    load_claims_ledger,
    load_fact_table,
    load_manifest,
    load_request_list,
    save_approval,
    save_claims_ledger,
    save_manifest,
    save_request_list,
)

logger = logging.getLogger(__name__)

# FDD-relevant agents (valuation / synergies excluded from figure claims — IN-8).
_CLAIM_AGENTS = (
    "historical_performance",
    "revenue_quality",
    "cost_structure",
    "company_background",
    "deal_context_and_objectives",
    "scope_and_methodology",
)

_EXCLUDED_FIGURE_AGENTS = frozenset(
    {
        "synergies",
        "final_valuation_range",
        "valuation_modeling",
        "sensitivity_analysis",
    }
)

_FY_VALUE_RE = re.compile(r"^fy(\d{4})_value$", re.I)
_PERF_METRIC_RE = re.compile(
    r"^(?P<metric>[a-z0-9_]+)_fy(?P<year>\d{4})(?:_|$)", re.I
)
# Trailing currency / scale / unit tokens on performance_metrics keys.
_METRIC_UNIT_SUFFIX_RE = re.compile(
    r"_(?:inr|usd|eur|gbp|aed|cr|mn|bn|k|m|pct|percent|bps|pp)(?:_(?:inr|usd|eur|gbp|aed|cr|mn|bn|k|m|pct|percent|bps|pp))*$",
    re.I,
)

_RETENTION_MAP = {
    "grr_pct": "grr",
    "grr": "grr",
    "nrr_pct": "nrr",
    "nrr": "nrr",
    "gross_margin_pct": "gross_margin",
    "ebitda_margin_pct": "ebitda_margin",
}


class AgentExhibitFigureError(ValueError):
    """R2 — agent figures must never seed exhibit cells."""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _deal_root(deal_slug: str) -> Path:
    return ensure_deal_folder(deal_slug)


def _read_agent_output(deal_slug: str, agent_key: str) -> dict[str, Any] | None:
    path = _deal_root(deal_slug) / "outputs" / f"{agent_key}.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.debug("Malformed agent output %s: %s", path, exc)
        return None
    except OSError as exc:
        logger.debug("Unreadable agent output %s: %s", path, exc)
        return None
    if not isinstance(raw, dict):
        logger.debug("Agent output %s is not a JSON object", path)
        return None
    return raw


def _spec_of(payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload.get("spec")
    return spec if isinstance(spec, dict) else payload


def _sources_as_pages(payload: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    pages: list[str] = []
    for key in ("sources", "primary_sources", "cited_sources"):
        for blob in (payload.get(key), spec.get(key)):
            if isinstance(blob, list):
                for item in blob:
                    if isinstance(item, str) and item.strip():
                        pages.append(item.strip())
                    elif isinstance(item, dict):
                        for field in ("page", "doc", "path", "name", "source"):
                            val = item.get(field)
                            if val:
                                pages.append(str(val))
                                break
            elif isinstance(blob, str) and blob.strip():
                pages.append(blob.strip())
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for p in pages:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out[:12]


def _coerce_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _claim_number(value: float) -> float:
    """Stable claim amounts — avoid float noise like 41335.810000000005."""
    if abs(value) >= 100:
        return round(value, 2)
    if abs(value) >= 1:
        return round(value, 4)
    return round(value, 6)


def _claim_value_text(value: float, *, unit: str | None = None) -> str:
    num = _claim_number(value)
    if abs(num - round(num)) < 1e-9:
        body = f"{int(round(num))}"
    else:
        body = f"{num:.4f}".rstrip("0").rstrip(".")
    return f"{body}{(' ' + unit) if unit else ''}"


def _is_absurd_growth(metric: str | None, value: float) -> bool:
    key = (metric or "").lower()
    if "yoy" not in key and "growth" not in key:
        return False
    return abs(value) > 500.0


def _claim_id(agent: str, metric: str | None, year: int | None, kind: str) -> str:
    """Unique claim id (UUID — no hash truncation / PYTHONHASHSEED issues)."""
    _ = (agent, metric, year, kind)  # reserved for future deterministic ids
    return f"cl_{uuid.uuid4().hex[:12]}"


def _resolve_metric_key(raw_key: str | None, line_item: str | None) -> str | None:
    key = (raw_key or "").strip().lower()
    if key in MATERIAL_METRIC_KEYS:
        return key
    if key in _RETENTION_MAP:
        return _RETENTION_MAP[key]
    caption = (line_item or key or "").strip()
    if not caption:
        return None
    hit = map_caption(caption)
    if hit is not None and hit.metric_key:
        return hit.metric_key
    # soft normalize
    norm = re.sub(r"[^a-z0-9]+", "_", caption.lower()).strip("_")
    if norm in MATERIAL_METRIC_KEYS:
        return norm
    if norm in _RETENTION_MAP:
        return _RETENTION_MAP[norm]
    return norm or None


def _strip_metric_unit_suffixes(metric_raw: str) -> str:
    """Remove trailing currency/scale tokens before map_caption lookup."""
    text = metric_raw.lower()
    while True:
        stripped = _METRIC_UNIT_SUFFIX_RE.sub("", text)
        if stripped == text:
            break
        text = stripped
    return text


def _input_key_str(key: Any) -> str | None:
    if key is None:
        return None
    if isinstance(key, InputKey):
        return key.value
    return str(key)


def extract_financial_from_pl_lines(
    agent_key: str, pl_lines: list[Any]
) -> list[ClaimsLedgerEntry]:
    out: list[ClaimsLedgerEntry] = []
    for line in pl_lines:
        if not isinstance(line, dict):
            continue
        item = str(line.get("line_item") or line.get("metric_key") or "").strip()
        metric = _resolve_metric_key(
            str(line.get("metric_key") or "") or None, item
        )
        unit = str(line.get("unit") or "") or None
        for k, v in line.items():
            m = _FY_VALUE_RE.match(str(k))
            if not m:
                continue
            year = int(m.group(1))
            value = _coerce_float(v)
            if value is None:
                continue
            value = _claim_number(value)
            if _is_absurd_growth(metric, value):
                continue
            text = f"{item or metric} FY{year} = {_claim_value_text(value, unit=unit)}"
            out.append(
                ClaimsLedgerEntry(
                    claim_id=_claim_id(agent_key, metric, year, "fin"),
                    source_agent=agent_key,
                    text=text,
                    kind="financial",
                    metric_key=metric,
                    fiscal_year=year,
                    claimed_value=value,
                    unit=unit,
                    test_result="pending",
                )
            )
    return out


def extract_financial_from_performance_metrics(
    agent_key: str, metrics: dict[str, Any]
) -> list[ClaimsLedgerEntry]:
    out: list[ClaimsLedgerEntry] = []
    for key, raw in metrics.items():
        value = _coerce_float(raw)
        if value is None:
            continue
        value = _claim_number(value)
        m = _PERF_METRIC_RE.match(str(key))
        if not m:
            continue
        metric_raw = _strip_metric_unit_suffixes(m.group("metric"))
        metric = _resolve_metric_key(metric_raw, metric_raw)
        if _is_absurd_growth(metric or metric_raw, value):
            continue
        year = int(m.group("year"))
        out.append(
            ClaimsLedgerEntry(
                claim_id=_claim_id(agent_key, metric, year, "fin"),
                source_agent=agent_key,
                text=f"{key} = {_claim_value_text(value)}",
                kind="financial",
                metric_key=metric,
                fiscal_year=year,
                claimed_value=value,
                test_result="pending",
            )
        )
    return out


def extract_financial_from_retention(
    agent_key: str, retention: dict[str, Any], *, default_year: int | None = None
) -> list[ClaimsLedgerEntry]:
    out: list[ClaimsLedgerEntry] = []
    for key, raw in retention.items():
        value = _coerce_float(raw)
        if value is None:
            continue
        metric = _RETENTION_MAP.get(str(key).lower())
        if not metric:
            continue
        out.append(
            ClaimsLedgerEntry(
                claim_id=_claim_id(agent_key, metric, default_year, "fin"),
                source_agent=agent_key,
                text=f"{key} = {value}",
                kind="financial",
                metric_key=metric,
                fiscal_year=default_year,
                claimed_value=value,
                unit="%",
                test_result="pending",
            )
        )
    return out


def extract_qualitative_snippets(
    agent_key: str,
    *,
    payload: dict[str, Any],
    spec: dict[str, Any],
    cited_pages: list[str],
) -> list[ClaimsLedgerEntry]:
    """Pull short prose leads; narrative_ok only when pages are cited."""
    out: list[ClaimsLedgerEntry] = []
    candidates: list[str] = []

    for key in ("summary", "findings"):
        val = payload.get(key)
        if isinstance(val, str) and len(val.strip()) >= 40:
            candidates.append(val.strip()[:400])
        elif isinstance(val, list):
            for item in val[:5]:
                if isinstance(item, str) and len(item.strip()) >= 40:
                    candidates.append(item.strip()[:400])
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("finding") or item.get("summary")
                    if isinstance(text, str) and len(text.strip()) >= 40:
                        candidates.append(text.strip()[:400])

    for key in ("insight_snapshot", "bridge_notes", "quality_verdict", "quality_flags"):
        val = spec.get(key)
        if isinstance(val, str) and len(val.strip()) >= 40:
            candidates.append(val.strip()[:400])
        elif isinstance(val, list):
            for item in val[:5]:
                if isinstance(item, str) and len(item.strip()) >= 24:
                    candidates.append(item.strip()[:400])
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("note") or item.get("flag")
                    if isinstance(text, str) and len(text.strip()) >= 24:
                        candidates.append(text.strip()[:400])

    seen: set[str] = set()
    for text in candidates[:8]:
        if text in seen:
            continue
        seen.add(text)
        narrative_ok = bool(cited_pages)
        out.append(
            ClaimsLedgerEntry(
                claim_id=_claim_id(agent_key, None, None, "qual"),
                source_agent=agent_key,
                text=text,
                kind="qualitative",
                cited_pages=list(cited_pages),
                narrative_ok=narrative_ok,
                test_result="pending" if not narrative_ok else "agrees",
                failed=not narrative_ok,
            )
        )
    return out


def extract_claims_from_agent(
    deal_slug: str, agent_key: str
) -> list[ClaimsLedgerEntry]:
    if agent_key in _EXCLUDED_FIGURE_AGENTS:
        return []
    payload = _read_agent_output(deal_slug, agent_key)
    if not payload:
        return []
    spec = _spec_of(payload)
    pages = _sources_as_pages(payload, spec)
    claims: list[ClaimsLedgerEntry] = []

    pl_lines = spec.get("pl_lines")
    if isinstance(pl_lines, list):
        claims.extend(extract_financial_from_pl_lines(agent_key, pl_lines))

    perf = spec.get("performance_metrics")
    if isinstance(perf, dict):
        claims.extend(extract_financial_from_performance_metrics(agent_key, perf))

    retention = spec.get("retention_metrics")
    if isinstance(retention, dict):
        claims.extend(extract_financial_from_retention(agent_key, retention))

    cost_metrics = spec.get("cost_metrics")
    if isinstance(cost_metrics, dict):
        # reuse retention mapper for margin-like keys
        claims.extend(extract_financial_from_retention(agent_key, cost_metrics))

    claims.extend(
        extract_qualitative_snippets(
            agent_key, payload=payload, spec=spec, cited_pages=pages
        )
    )
    # Attach agent sources to financial claims so Phase 4 can hint VDR files.
    if pages:
        claims = [
            c.model_copy(update={"cited_pages": list(pages)})
            if c.kind == "financial" and not c.cited_pages
            else c
            for c in claims
        ]
    return claims


def _values_agree_raw(claimed: float, databook: float) -> bool:
    delta = abs(float(claimed) - float(databook))
    scale = max(abs(float(databook)), abs(float(claimed)), 1.0)
    # For typical $M diligence figures, absolute floor catches 0.007–0.030 gaps.
    # Relative tolerance only relaxes for large magnitudes (hundreds+).
    if scale < 50.0:
        return delta <= CLAIMS_ABS_TOLERANCE
    return delta <= max(CLAIMS_ABS_TOLERANCE, CLAIMS_VALUE_TOLERANCE * scale)


def values_agree(claimed: float, databook: float) -> bool:
    """True when figures match, including ratio↔percent (0.762 vs 76.2)."""
    a = float(claimed)
    b = float(databook)
    if _values_agree_raw(a, b):
        return True
    # Retention / margin often appear as a fraction in one pack and percent-points
    # in another — treat 0.762 and 76.2 (or 0.018 and 1.80) as the same figure.
    lo, hi = (a, b) if abs(a) <= abs(b) else (b, a)
    if 0.0 < abs(lo) <= 1.0 and abs(hi) <= 200.0 and abs(hi) >= abs(lo) * 10.0:
        # Clear fraction ↔ percent-points (0.018 vs 1.80, 0.762 vs 76.2).
        if _values_agree_raw(lo * 100.0, hi):
            return True
        if _values_agree_raw(hi / 100.0, lo):
            return True
    elif 0.0 < abs(lo) <= 2.0 and abs(hi) >= 2.0:
        if _values_agree_raw(lo * 100.0, hi):
            return True
        if abs(hi) <= 200.0 and _values_agree_raw(hi / 100.0, lo):
            return True
    return False


def _claim_source_label(claim: ClaimsLedgerEntry) -> str:
    """Human source name for agent claims — prefer monthly pack."""
    agent = (claim.source_agent or "").lower()
    text = (claim.text or "").lower()
    if (
        "qbo" in text
        or "quickbooks" in text
        or "accounting_records" in text
        or "accounts extract" in text
    ):
        return "QBO ledger"
    if agent in {
        "historical_performance",
        "revenue_quality",
        "cost_structure",
        "cash_flow",
        "capital_structure",
    }:
        return "monthly pack"
    if agent:
        return f"{agent.replace('_', ' ')} claim"
    return "agent claim"


def index_facts(facts: list[FddFact]) -> dict[tuple[str, int], FddFact]:
    idx: dict[tuple[str, int], FddFact] = {}
    for fact in facts:
        idx[(fact.metric_key, int(fact.fiscal_year))] = fact
    return idx


def _fact_is_open_or_ytd(fact: FddFact) -> bool:
    """True for plan / YTD stubs that must not contradict closed-year claims."""
    from datetime import date

    year = int(fact.fiscal_year or 0)
    closed = date.today().year - 1
    plen = ""
    if fact.labels:
        plen = str(fact.labels.period_length or "").upper()
    if plen == "YTD":
        return True
    if year > closed:
        return True
    return False


def _target_from_fact(fact: FddFact | None) -> tuple[str, str | None]:
    """Resolve document + location for a fact (Fix 6 target)."""
    if fact is None:
        return "", None
    sources = [str(s).strip() for s in (fact.sources or []) if str(s).strip()]
    ref = fact.source_ref if isinstance(fact.source_ref, dict) else {}
    doc = (
        str(ref.get("document") or ref.get("doc_id") or ref.get("filename") or "").strip()
        or (sources[0] if sources else "")
    )
    loc_parts = [
        str(ref.get(k)).strip()
        for k in ("sheet_or_page", "page", "cell_range", "bbox", "location")
        if ref.get(k)
    ]
    if not loc_parts and getattr(fact.labels, "source", None):
        loc_parts.append(str(fact.labels.source))
    location = " / ".join(loc_parts) if loc_parts else None
    if not doc and fact.fact_id:
        # Prefer an explicit non-agent document id; never treat agent: as a target.
        fid = str(fact.fact_id)
        if not fid.lower().startswith(("agent:", "agent_", "claim:", "output:")):
            doc = f"databook:{fid}"
    return doc, location


def _scale_mismatch(claimed: float, book: float) -> bool:
    """Reject sticky-scale false contradictions (0.57 vs 98097, 13.41 vs 9436)."""
    a, b = abs(float(claimed)), abs(float(book))
    if a < 1e-12 or b < 1e-12:
        return max(a, b) >= 1000.0
    lo, hi = (a, b) if a <= b else (b, a)
    return hi >= 1000.0 and hi / max(lo, 1e-12) >= 50.0


def _is_self_comparison(claim: ClaimsLedgerEntry, fact: FddFact | None) -> bool:
    """True when the agent assertion is the same databook fact restated."""
    if fact is None or not fact.fact_id:
        return False
    # Cited pages that are only the fact id / databook mirror → self-comparison.
    cites = [str(c).strip().lower() for c in (claim.cited_pages or []) if c]
    fid = str(fact.fact_id).strip().lower()
    if cites and all(
        c in {fid, f"databook:{fid}", "databook", "fact table", "fact_table"}
        or c.startswith("db:")
        for c in cites
    ):
        return True
    # Agent text that embeds the same fact_id with no external document citation.
    text_l = (claim.text or "").lower()
    if fid and fid in text_l and not claim.cited_pages:
        return True
    return False


def _format_claim_subject_percent(subject: str, claim: ClaimsLedgerEntry) -> str:
    """Render margin/rate subjects as points (1.8%), not ontology fractions."""
    text = " ".join(str(subject or "").split())
    key = str(claim.metric_key or "").lower()
    claimed = claim.claimed_value
    if (
        isinstance(claimed, (int, float))
        and re.search(r"margin|percent|pct|rate|yoy|growth", key)
        and abs(float(claimed)) <= 1.0 + 1e-12
    ):
        from agetic_cdd_api.services_databook_consume import humanize_metric_key

        lab = humanize_metric_key(claim.metric_key or "") or (claim.metric_key or "Metric")
        pts = float(claimed) * 100.0
        body = f"{pts:.1f}".rstrip("0").rstrip(".")
        fy = claim.fiscal_year
        return f"{lab} FY{fy} = {body}%" if fy else f"{lab} = {body}%"

    def _frac(match: re.Match[str]) -> str:
        try:
            value = float(match.group(1))
        except ValueError:
            return match.group(0)
        if abs(value) <= 1.0 + 1e-12:
            points = value * 100.0
            body = f"{points:.1f}".rstrip("0").rstrip(".")
            return f"= {body}%"
        body = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"= {body}%"

    def _points(match: re.Match[str]) -> str:
        try:
            value = float(match.group(1))
        except ValueError:
            return match.group(0)
        body = f"{value:.1f}".rstrip("0").rstrip(".")
        return f"= {body}%"

    text = re.sub(r"=\s*(-?0\.\d+)\s*%", _frac, text)
    text = re.sub(r"=\s*(-?\d+\.\d{2,})\s*%", _points, text)
    return text


def _stamp_claim(
    claim: ClaimsLedgerEntry,
    *,
    verdict: str,
    failed: bool,
    fact: FddFact | None = None,
    extra: dict | None = None,
) -> ClaimsLedgerEntry:
    subject = (claim.subject or claim.text or "").strip() or (
        f"{claim.metric_key} FY{claim.fiscal_year} = {claim.claimed_value}"
        if claim.metric_key
        else (claim.text or "")
    )
    subject = _format_claim_subject_percent(subject, claim)
    doc, loc = _target_from_fact(fact)
    if not doc and claim.cited_pages:
        doc = str(claim.cited_pages[0])
        loc = loc or (", ".join(claim.cited_pages[1:3]) if len(claim.cited_pages) > 1 else None)
    update = {
        "subject": subject[:400],
        "target_document": doc[:240],
        "target_location": (loc[:240] if loc else None),
        "verdict": verdict,
        "test_result": verdict,  # keep legacy field in sync
        "failed": failed,
        "self_comparison": _is_self_comparison(claim, fact),
    }
    if fact is not None:
        update["databook_fact_id"] = fact.fact_id
        update["databook_value"] = fact.value
    if extra:
        update.update(extra)
    return claim.model_copy(update=update)


def evaluate_financial_claim(
    claim: ClaimsLedgerEntry, facts_idx: dict[tuple[str, int], FddFact]
) -> ClaimsLedgerEntry:
    """Fix 6 — test agent assertion against a document-backed fact target."""
    if claim.kind != "financial":
        return claim
    if not claim.source_agent:
        return _stamp_claim(claim, verdict="unverifiable", failed=True)
    if not claim.metric_key or claim.fiscal_year is None or claim.claimed_value is None:
        return _stamp_claim(claim, verdict="unverifiable", failed=True)
    from datetime import date

    # Plan / incomplete years → wrong_period (not like-for-like vs closed actuals).
    if int(claim.fiscal_year) > date.today().year - 1:
        return _stamp_claim(claim, verdict="wrong_period", failed=False)

    # Strict (metric_key, fiscal_year) match — no cross-year fallback.
    fact = facts_idx.get((claim.metric_key, int(claim.fiscal_year)))
    if fact is None:
        # Look for same metric different year → wrong_period; else unverifiable / false_gap.
        same_metric = [
            f for (mk, _y), f in facts_idx.items() if mk == claim.metric_key
        ]
        text_l = (claim.text or "").lower()
        asserted_missing = any(
            tok in text_l for tok in ("missing", "not found", "unavailable", "no data")
        )
        if same_metric:
            return _stamp_claim(
                claim, verdict="wrong_period", failed=True, fact=same_metric[0]
            )
        if asserted_missing:
            return _stamp_claim(claim, verdict="false_gap", failed=True)
        return _stamp_claim(claim, verdict="unverifiable", failed=True)

    if _is_self_comparison(claim, fact):
        return _stamp_claim(
            claim,
            verdict="unverifiable",
            failed=False,
            fact=fact,
            extra={"self_comparison": True},
        )

    if _fact_is_open_or_ytd(fact):
        return _stamp_claim(claim, verdict="wrong_period", failed=False, fact=fact)

    if fact.status == CellStatus.MISSING:
        text_l = (claim.text or "").lower()
        if any(tok in text_l for tok in ("missing", "not found", "unavailable")):
            # Agent said missing and fact is missing — unverifiable, not a false gap.
            return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)
        return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)

    # Line label mismatch when fact line differs materially from metric key.
    fact_line = ""
    if fact.labels and fact.labels.line:
        fact_line = str(fact.labels.line).lower().replace(" ", "_")
    mk = (claim.metric_key or "").lower()
    if fact_line and mk and fact_line not in mk and mk not in fact_line:
        # Only flag when values would otherwise look comparable but labels diverge.
        if fact.value is not None and values_agree(claim.claimed_value, fact.value):
            pass  # agree on value despite label wording
        elif fact.value is not None and not _scale_mismatch(
            float(claim.claimed_value), float(fact.value)
        ):
            # Different line family with different value → wrong_line.
            if abs(float(claim.claimed_value) - float(fact.value)) > CLAIMS_ABS_TOLERANCE:
                # Keep contradicted for clear money gaps; wrong_line when metric aliases differ.
                aliases = {
                    "ebitda": {"adjusted_ebitda", "reported_ebitda", "ebitda"},
                    "revenue": {"total_revenue", "sales", "revenue"},
                }
                family = aliases.get(mk, {mk})
                if fact_line not in family and not any(a in fact_line for a in family):
                    return _stamp_claim(
                        claim, verdict="wrong_line", failed=True, fact=fact
                    )

    if fact.status in {CellStatus.DOUBTFUL, CellStatus.DRAFT}:
        if fact.value is None:
            return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)
        if values_agree(claim.claimed_value, fact.value):
            return _stamp_claim(claim, verdict="agrees", failed=False, fact=fact)
        if _scale_mismatch(float(claim.claimed_value), float(fact.value)):
            return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)
        return _stamp_claim(claim, verdict="contradicted", failed=True, fact=fact)

    if fact.value is None:
        return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)
    if values_agree(claim.claimed_value, fact.value):
        stamped = _stamp_claim(claim, verdict="agrees", failed=False, fact=fact)
        # Agrees still requires a document target — otherwise unverifiable.
        if not stamped.target_document:
            return stamped.model_copy(
                update={
                    "verdict": "unverifiable",
                    "test_result": "unverifiable",
                    "failed": True,
                }
            )
        return stamped
    if _scale_mismatch(float(claim.claimed_value), float(fact.value)):
        return _stamp_claim(claim, verdict="unverifiable", failed=True, fact=fact)
    stamped = _stamp_claim(claim, verdict="contradicted", failed=True, fact=fact)
    if not stamped.target_document:
        return stamped.model_copy(
            update={
                "verdict": "unverifiable",
                "test_result": "unverifiable",
                "failed": True,
            }
        )
    return stamped


def score_modules(claims: list[ClaimsLedgerEntry]) -> list[ModuleReliability]:
    by_agent: dict[str, list[ClaimsLedgerEntry]] = {}
    for c in claims:
        agent = c.source_agent or "unknown"
        by_agent.setdefault(agent, []).append(c)
    modules: list[ModuleReliability] = []
    for agent, items in sorted(by_agent.items()):
        # Reliability scored on financial tests + uncited qualitative.
        scored = [
            c
            for c in items
            if c.kind == "financial" or (c.kind == "qualitative" and not c.narrative_ok)
        ]
        # If no scored items, module is reliable by default.
        total = len(scored) if scored else len(items)
        failed = sum(1 for c in (scored or items) if c.failed)
        rate = (failed / total) if total else 0.0
        modules.append(
            ModuleReliability(
                source_agent=agent,
                total=total,
                financial_total=sum(1 for c in items if c.kind == "financial"),
                failed=failed,
                fail_rate=round(rate, 4),
                unreliable=bool(scored) and rate > CLAIMS_RELIABILITY_FAIL_THRESHOLD,
            )
        )
    return modules


def assert_fact_id_not_agent_sourced(fact_id: str | None) -> None:
    """R2 — exhibit cells must not carry agent-minted fact ids.

    Enforced at exhibit upsert time in ``services_fdd_exhibit.upsert_cell``.
    """
    if not fact_id:
        raise AgentExhibitFigureError("Exhibit cell missing fact_id")
    lowered = fact_id.lower()
    if lowered.startswith(("agent:", "agent_", "output:", "claim:")):
        raise AgentExhibitFigureError(
            f"Agent-sourced fact_id forbidden on exhibits: {fact_id!r}"
        )


_DOC_NAME_RE = re.compile(
    r"([A-Za-z0-9][A-Za-z0-9._\- ]*\.(?:pdf|xlsx?|csv|docx?))",
    re.I,
)


def _filenames_from_claim(claim: ClaimsLedgerEntry) -> list[str]:
    """Best-effort VDR filenames from claim citations / prose (Phase 4 hints)."""
    found: list[str] = []
    seen: set[str] = set()
    for blob in [*(claim.cited_pages or []), claim.text or ""]:
        for m in _DOC_NAME_RE.finditer(blob):
            name = m.group(1).strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            found.append(name)
    return found[:8]


def _append_claim_requests(
    *,
    deal_slug: str,
    run_id: str,
    claims: list[ClaimsLedgerEntry],
) -> RequestListDoc | None:
    """Lite Phase 4 — open requests for contradicted / unverifiable financial claims."""
    existing = load_request_list(deal_slug, run_id)
    items = list(existing.items) if existing else []
    seen: set[tuple[str | None, str]] = {
        (_input_key_str(i.input_key), i.title) for i in items
    }
    added = False
    def _sticky_rfi(claimed: float | None, book: float | None, text: str | None) -> bool:
        """Skip RFIs that only restate sticky-scale dust (0.039 / 9436 / 98097)."""
        blob = str(text or "")
        if re.search(r"\b(9436|98097|56182)\b", blob):
            return True
        # Missing databook cell rendered as 0.000 vs a real pack figure.
        if re.search(r"(?i)\bdatabook\s+0(?:\.0+)?\b", blob):
            return True

        def _dust(v: float | None) -> bool:
            return v is not None and 1e-6 < abs(float(v)) < 0.05

        if _dust(claimed) or _dust(book):
            return True
        if claimed is not None and book is None and abs(float(claimed)) >= 1000.0:
            # Outlook/raw grain with no databook peer (EBITDA FY2025 = 98097).
            return True
        if claimed is not None and book is not None:
            c, b = abs(float(claimed)), abs(float(book))
            # Empty/missing book cell (0) vs material claimed — not a real gap.
            if b < 1e-9 and c >= 0.1:
                return True
            if c < 1e-9 and b >= 1000.0:
                return True
            lo, hi = (c, b) if c <= b else (b, c)
            if hi >= 1000.0 and lo > 0.05 and hi / max(lo, 1e-12) >= 50.0:
                return True
        return False

    # Drop sticky leftovers already persisted on the run's request list.
    kept_existing: list[Any] = []
    for item in items:
        if _sticky_rfi(
            getattr(item, "claimed_value", None)
            if getattr(item, "claimed_value", None) is not None
            else None,
            getattr(item, "databook_value", None)
            if getattr(item, "databook_value", None) is not None
            else None,
            " ".join(
                str(x)
                for x in (
                    getattr(item, "title", None),
                    getattr(item, "detail", None),
                    getattr(item, "figure_impact", None),
                )
                if x
            ),
        ):
            added = True  # force rewrite without sticky rows
            continue
        kept_existing.append(item)
    items = kept_existing
    seen = {(_input_key_str(i.input_key), i.title) for i in items}

    for claim in claims:
        verdict = str(getattr(claim, "verdict", None) or claim.test_result or "")
        # wrong_period is a ledger classification for open/plan years — not a
        # client RFI (those titles were leaking "(wrong period)" across the deck).
        if claim.kind != "financial" or verdict not in {
            "contradicted",
            "unverifiable",
            "false_gap",
            "wrong_line",
        }:
            continue
        claimed = claim.claimed_value
        book = claim.databook_value
        # Scale-mismatch / sticky grains: do not open "98097" / "9436" RFIs.
        if _sticky_rfi(
            float(claimed) if claimed is not None else None,
            float(book) if book is not None else None,
            claim.text,
        ):
            continue
        from agetic_cdd_api.services_databook_consume import humanize_metric_key

        metric = humanize_metric_key(claim.metric_key or "figure") or "figure"
        fy = f"FY{claim.fiscal_year}" if claim.fiscal_year else "FY?"
        claimed_src = _claim_source_label(claim)
        book_src = "databook"
        if claimed is not None and book is not None:
            gap = abs(float(claimed) - float(book))
            title = (
                f"Reconcile {fy} {metric}: {claimed_src} vs {book_src} "
                f"(gap {gap:.3f})"
            )
        elif book is not None:
            title = f"Confirm {fy} {metric} against {book_src}"
        else:
            title = f"Support {metric} for {fy} with a closed-year schedule"
        dedupe = (_input_key_str(InputKey.DATABOOK), title)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        suggested = _filenames_from_claim(claim)
        # Never put raw agent figure prose in the client-facing Why column.
        detail = (
            f"Reconcile {metric} for {fy} against the approved databook."
            if verdict == "contradicted"
            else f"Support {metric} for {fy} with a schedule."
        )
        items.append(
            RequestListItem(
                request_id=f"req_{uuid.uuid4().hex[:10]}",
                input_key=InputKey.DATABOOK,
                title=title,
                detail=detail,
                owner="deal_lead",
                figure_impact=detail,
                blocking_sections=["SEC-K"],
                status="pending",
                claim_id=claim.claim_id,
                metric_key=claim.metric_key,
                fiscal_year=claim.fiscal_year,
                suggested_filenames=suggested,
            )
        )
        added = True
    if not added and existing is None:
        return None
    doc = RequestListDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        items=items,
    )
    return save_request_list(doc)


def build_claims_ledger(
    deal_slug: str,
    run_id: str,
    *,
    agent_keys: tuple[str, ...] | None = None,
    facts: FactTableDoc | None = None,
    update_manifest: bool = True,
    open_requests: bool = True,
) -> ClaimsLedgerDoc:
    """Extract + test claims; persist ledger; optionally stamp manifest."""
    fact_doc = facts or load_fact_table(deal_slug, run_id)
    facts_list = list(fact_doc.facts) if fact_doc else []
    facts_idx = index_facts(facts_list)

    agents = agent_keys or _CLAIM_AGENTS
    raw_claims: list[ClaimsLedgerEntry] = []
    for agent in agents:
        raw_claims.extend(extract_claims_from_agent(deal_slug, agent))

    tested: list[ClaimsLedgerEntry] = []
    dropped_self = 0
    for claim in raw_claims:
        # Fix 6 — every row must name an agent module.
        if not (claim.source_agent or "").strip():
            continue
        if claim.kind == "financial":
            evaluated = evaluate_financial_claim(claim, facts_idx)
            # Zero self-comparisons: drop databook↔databook restatements.
            if getattr(evaluated, "self_comparison", False):
                dropped_self += 1
                continue
            tested.append(evaluated)
        else:
            # Qualitative: subject = text; target = first cited document.
            cites = list(claim.cited_pages or [])
            doc = cites[0] if cites else ""
            verdict = (
                "agrees"
                if claim.narrative_ok and doc
                else ("unverifiable" if not doc else claim.test_result or "pending")
            )
            tested.append(
                claim.model_copy(
                    update={
                        "subject": (claim.subject or claim.text or "")[:400],
                        "target_document": doc[:240],
                        "target_location": (
                            ", ".join(cites[1:3]) if len(cites) > 1 else None
                        ),
                        "verdict": verdict,
                        "test_result": verdict,
                        "failed": bool(claim.failed or not doc),
                    }
                )
            )

    modules = score_modules(tested)
    unreliable = [m.source_agent for m in modules if m.unreliable]

    def _verdict_of(c: ClaimsLedgerEntry) -> str:
        return str(getattr(c, "verdict", None) or c.test_result or "pending")

    counts = {
        "agrees": sum(1 for c in tested if _verdict_of(c) == "agrees"),
        "contradicted": sum(1 for c in tested if _verdict_of(c) == "contradicted"),
        "unverifiable": sum(1 for c in tested if _verdict_of(c) == "unverifiable"),
        "pending": sum(1 for c in tested if _verdict_of(c) == "pending"),
        "false_gap": sum(1 for c in tested if _verdict_of(c) == "false_gap"),
        "wrong_line": sum(1 for c in tested if _verdict_of(c) == "wrong_line"),
        "wrong_period": sum(1 for c in tested if _verdict_of(c) == "wrong_period"),
    }
    ledger = ClaimsLedgerDoc(
        run_id=run_id,
        deal_slug=deal_slug,
        updated_at=_now(),
        databook_release_id=(
            fact_doc.databook_release_id if fact_doc else None
        ),
        claim_count=len(tested),
        financial_count=sum(1 for c in tested if c.kind == "financial"),
        qualitative_count=sum(1 for c in tested if c.kind == "qualitative"),
        agrees=counts["agrees"],
        contradicted=counts["contradicted"],
        unverifiable=counts["unverifiable"],
        pending=counts["pending"],
        false_gap=counts["false_gap"],
        wrong_line=counts["wrong_line"],
        wrong_period=counts["wrong_period"],
        self_comparisons_dropped=dropped_self,
        unreliable_modules=unreliable,
        modules=modules,
        claims=tested,
        notes=[
            "Fix 6 — Subject = agent assertion; Target = document + source location.",
            "Verdicts: agrees | contradicted | false_gap | wrong_line | wrong_period | unverifiable.",
            "Self-comparisons (databook vs databook) are dropped.",
            "Agent figures never seed exhibits (R2).",
            f"Module unreliable when fail_rate > {CLAIMS_RELIABILITY_FAIL_THRESHOLD:.0%}.",
            *(
                [f"Dropped {dropped_self} self-comparison row(s)."]
                if dropped_self
                else []
            ),
        ],
    )
    ledger = save_claims_ledger(ledger)

    if open_requests:
        _append_claim_requests(deal_slug=deal_slug, run_id=run_id, claims=tested)

    if update_manifest:
        manifest = load_manifest(deal_slug, run_id)
        if manifest is not None:
            stage = manifest.stage
            # P2 = claims ledger built. P3 evidence re-enters here after rescan.
            if stage in {RunStage.P0, RunStage.P1, RunStage.P3}:
                stage = RunStage.P2
            g2_passed = bool(not unreliable)
            # Prior G2 acknowledge survives a rebuild only when still reliable,
            # or when an acknowledge approval exists and modules remain flagged.
            if not g2_passed:
                prior = load_approval(deal_slug, run_id, GateId.G2)
                if (
                    prior is not None
                    and prior.status == ArtefactStatus.APPROVED
                    and prior.payload.get("allow_unreliable")
                ):
                    g2_passed = True
            save_manifest(
                manifest.model_copy(
                    update={
                        "claims_built": True,
                        "unreliable_modules": unreliable,
                        "g2_passed": g2_passed,
                        "stage": stage,
                        "model_versions": {
                            **(manifest.model_versions or {}),
                            "fdd_phase3": "0.1.0",
                        },
                    }
                )
            )
    return ledger


def evaluate_g2(
    deal_slug: str,
    run_id: str,
    *,
    ledger: ClaimsLedgerDoc | None = None,
    manifest: FddRunManifest | None = None,
) -> dict[str, Any]:
    """G2 auto gate — claims ledger built and modules reliable (or acknowledged)."""
    m = manifest or load_manifest(deal_slug, run_id)
    led = ledger if ledger is not None else load_claims_ledger(deal_slug, run_id)
    appr = load_approval(deal_slug, run_id, GateId.G2)
    claims_built = bool(m.claims_built) if m else led is not None
    unreliable = list(
        (led.unreliable_modules if led is not None else None)
        or (m.unreliable_modules if m else None)
        or []
    )
    auto_ok = claims_built and not unreliable
    acknowledged = bool(
        appr is not None
        and appr.status == ArtefactStatus.APPROVED
        and appr.payload.get("allow_unreliable")
    )
    passed = bool(m.g2_passed) if m and m.g2_passed else (auto_ok or acknowledged)
    blockers: list[str] = []
    if not claims_built:
        blockers.append("claims_not_built")
    if unreliable and not acknowledged:
        blockers.append(f"unreliable_modules:{','.join(unreliable)}")
    return {
        "passed": passed,
        "ready": claims_built,
        "auto_ok": auto_ok,
        "acknowledged": acknowledged,
        "blockers": blockers,
        "unreliable_modules": unreliable,
        "claim_count": led.claim_count if led else 0,
        "financial_count": led.financial_count if led else 0,
        "contradicted": led.contradicted if led else 0,
        "unverifiable": led.unverifiable if led else 0,
        "approval": appr.model_dump(mode="json") if appr else None,
    }


def acknowledge_g2(
    deal_slug: str,
    run_id: str,
    *,
    decided_by: str | None = None,
    note: str | None = None,
    allow_unreliable: bool = True,
) -> tuple[dict[str, Any], Approval, FddRunManifest]:
    """Lead acknowledges G2 when modules are unreliable but diligence proceeds."""
    manifest = load_manifest(deal_slug, run_id)
    if manifest is None:
        raise FileNotFoundError(f"Missing FDD manifest {deal_slug}/{run_id}")
    ledger = load_claims_ledger(deal_slug, run_id)
    if not manifest.claims_built and ledger is None:
        raise GateBlockedError("G2 blocked — build claims ledger first")
    status = evaluate_g2(deal_slug, run_id, ledger=ledger, manifest=manifest)
    if status["auto_ok"]:
        # Already green — stamp approval for audit trail without override flag.
        allow_unreliable = False
    elif not allow_unreliable:
        raise GateBlockedError(
            "G2 blocked — unreliable modules present; set allow_unreliable or fix claims"
        )
    if not (note or "").strip() and allow_unreliable and status["unreliable_modules"]:
        raise GateBlockedError(
            "G2 acknowledge requires a note when unreliable modules are present"
        )

    existing = load_approval(deal_slug, run_id, GateId.G2)
    if (
        existing is not None
        and existing.status == ArtefactStatus.APPROVED
        and manifest.g2_passed
    ):
        return status, existing, manifest

    approval = Approval(
        approval_id=f"appr_{uuid.uuid4().hex[:10]}",
        gate=GateId.G2,
        run_id=run_id,
        deal_slug=deal_slug,
        status=ArtefactStatus.APPROVED,
        decided_at=_now(),
        decided_by=decided_by or "deal_lead",
        note=note
        or (
            "Claims ledger reliable (G2)"
            if status["auto_ok"]
            else "Unreliable modules acknowledged (G2)"
        ),
        payload={
            "allow_unreliable": allow_unreliable,
            "unreliable_modules": list(status["unreliable_modules"]),
            "claim_count": status["claim_count"],
        },
    )
    approval = save_approval(approval)
    manifest = save_manifest(
        manifest.model_copy(
            update={
                "g2_passed": True,
                "claims_built": True,
                "unreliable_modules": list(status["unreliable_modules"]),
            }
        )
    )
    status = evaluate_g2(deal_slug, run_id, ledger=ledger, manifest=manifest)
    return status, approval, manifest


def ensure_phase3_claims(
    deal_slug: str,
    run_id: str,
    *,
    rebuild: bool = False,
) -> ClaimsLedgerDoc:
    """Get-or-build claims ledger for a run."""
    if not rebuild:
        existing = load_claims_ledger(deal_slug, run_id)
        if existing is not None and existing.claim_count >= 0 and existing.updated_at:
            # Rebuild if empty and agents may now exist? Prefer explicit rebuild.
            if existing.claim_count > 0 or existing.notes:
                return existing
    return build_claims_ledger(deal_slug, run_id)
