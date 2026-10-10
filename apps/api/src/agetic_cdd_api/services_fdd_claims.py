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
            text = f"{item or metric} FY{year} = {value}" + (f" {unit}" if unit else "")
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
        m = _PERF_METRIC_RE.match(str(key))
        if not m:
            continue
        metric_raw = _strip_metric_unit_suffixes(m.group("metric"))
        metric = _resolve_metric_key(metric_raw, metric_raw)
        year = int(m.group("year"))
        out.append(
            ClaimsLedgerEntry(
                claim_id=_claim_id(agent_key, metric, year, "fin"),
                source_agent=agent_key,
                text=f"{key} = {value}",
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


def values_agree(claimed: float, databook: float) -> bool:
    delta = abs(float(claimed) - float(databook))
    scale = max(abs(float(databook)), abs(float(claimed)), 1.0)
    # For typical $M diligence figures, absolute floor catches 0.007–0.030 gaps.
    # Relative tolerance only relaxes for large magnitudes (hundreds+).
    if scale < 50.0:
        return delta <= CLAIMS_ABS_TOLERANCE
    return delta <= max(CLAIMS_ABS_TOLERANCE, CLAIMS_VALUE_TOLERANCE * scale)


def _claim_source_label(claim: ClaimsLedgerEntry) -> str:
    """Human source name for agent claims (QBO/accounts vs generic agent)."""
    agent = (claim.source_agent or "").lower()
    text = (claim.text or "").lower()
    if agent in {"historical_performance", "revenue_quality", "cost_structure"}:
        return "QBO ledger"
    if "qbo" in text or "accounting_records" in text or "accounts extract" in text:
        return "QBO ledger"
    if agent:
        return f"{agent.replace('_', ' ')} claim"
    return "agent claim"


def index_facts(facts: list[FddFact]) -> dict[tuple[str, int], FddFact]:
    idx: dict[tuple[str, int], FddFact] = {}
    for fact in facts:
        idx[(fact.metric_key, int(fact.fiscal_year))] = fact
    return idx


def evaluate_financial_claim(
    claim: ClaimsLedgerEntry, facts_idx: dict[tuple[str, int], FddFact]
) -> ClaimsLedgerEntry:
    if claim.kind != "financial":
        return claim
    if not claim.metric_key or claim.fiscal_year is None or claim.claimed_value is None:
        return claim.model_copy(
            update={
                "test_result": "unverifiable",
                "failed": True,
            }
        )
    # Strict (metric_key, fiscal_year) match — no cross-year fallback.
    fact = facts_idx.get((claim.metric_key, int(claim.fiscal_year)))
    if fact is None:
        return claim.model_copy(
            update={
                "test_result": "unverifiable",
                "failed": True,
            }
        )
    if fact.status == CellStatus.MISSING:
        return claim.model_copy(
            update={
                "test_result": "unverifiable",
                "failed": True,
                "databook_fact_id": fact.fact_id,
                "databook_value": fact.value,
            }
        )
    # Doubtful/draft with a released value: still test the figure and surface gaps
    # (e.g. ledger 13.412 vs workbook 13.282) instead of a blank "unverifiable".
    if fact.status in {CellStatus.DOUBTFUL, CellStatus.DRAFT}:
        if fact.value is None:
            return claim.model_copy(
                update={
                    "test_result": "unverifiable",
                    "failed": True,
                    "databook_fact_id": fact.fact_id,
                }
            )
        if values_agree(claim.claimed_value, fact.value):
            return claim.model_copy(
                update={
                    "test_result": "agrees",
                    "failed": False,
                    "databook_fact_id": fact.fact_id,
                    "databook_value": fact.value,
                }
            )
        return claim.model_copy(
            update={
                "test_result": "contradicted",
                "failed": True,
                "databook_fact_id": fact.fact_id,
                "databook_value": fact.value,
            }
        )
    if fact.value is None:
        return claim.model_copy(
            update={
                "test_result": "unverifiable",
                "failed": True,
                "databook_fact_id": fact.fact_id,
            }
        )
    if values_agree(claim.claimed_value, fact.value):
        return claim.model_copy(
            update={
                "test_result": "agrees",
                "failed": False,
                "databook_fact_id": fact.fact_id,
                "databook_value": fact.value,
            }
        )
    return claim.model_copy(
        update={
            "test_result": "contradicted",
            "failed": True,
            "databook_fact_id": fact.fact_id,
            "databook_value": fact.value,
        }
    )


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
    for claim in claims:
        if claim.kind != "financial" or claim.test_result not in {
            "contradicted",
            "unverifiable",
        }:
            continue
        metric = (claim.metric_key or "figure").replace("_", " ")
        fy = f"FY{claim.fiscal_year}" if claim.fiscal_year else "FY?"
        claimed = claim.claimed_value
        book = claim.databook_value
        claimed_src = _claim_source_label(claim)
        book_src = "investor workbook"
        if claimed is not None and book is not None:
            gap = abs(float(claimed) - float(book))
            title = (
                f"{fy} {metric}: {claimed_src} {float(claimed):.3f} vs "
                f"{book_src} {float(book):.3f} — gap {gap:.3f} "
                f"({claim.test_result})"
            )
        elif book is not None:
            title = (
                f"{fy} {metric}: {book_src} {float(book):.3f} "
                f"({claim.test_result})"
            )
        else:
            title = (
                f"Resolve claim {claim.metric_key or '?'} "
                f"FY{claim.fiscal_year or '?'} ({claim.test_result})"
            )
        dedupe = (_input_key_str(InputKey.DATABOOK), title)
        if dedupe in seen:
            continue
        seen.add(dedupe)
        suggested = _filenames_from_claim(claim)
        items.append(
            RequestListItem(
                request_id=f"req_{uuid.uuid4().hex[:10]}",
                input_key=InputKey.DATABOOK,
                title=title,
                detail=claim.text,
                owner="deal_lead",
                figure_impact=(
                    f"{claimed_src} vs {book_src} — "
                    f"claimed={claim.claimed_value} databook={claim.databook_value}"
                ),
                # Canonical gap prose lives on SEC-K only (other sections point there).
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
    for claim in raw_claims:
        if claim.kind == "financial":
            tested.append(evaluate_financial_claim(claim, facts_idx))
        else:
            # qualitative already stamped narrative_ok / failed on extract
            tested.append(claim)

    modules = score_modules(tested)
    unreliable = [m.source_agent for m in modules if m.unreliable]

    counts = {
        "agrees": sum(1 for c in tested if c.test_result == "agrees"),
        "contradicted": sum(1 for c in tested if c.test_result == "contradicted"),
        "unverifiable": sum(1 for c in tested if c.test_result == "unverifiable"),
        "pending": sum(1 for c in tested if c.test_result == "pending"),
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
        unreliable_modules=unreliable,
        modules=modules,
        claims=tested,
        notes=[
            "Financial claims tested against FDD fact table (metric_key × fiscal_year).",
            "Qualitative claims require cited_pages for narrative_ok.",
            "Agent figures never seed exhibits (R2).",
            f"Module unreliable when fail_rate > {CLAIMS_RELIABILITY_FAIL_THRESHOLD:.0%}.",
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
