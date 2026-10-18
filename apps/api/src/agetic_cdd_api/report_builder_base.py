"""Abstract report builder — the generation pipeline skeleton.

Every concrete report builder (ops_dashboard, ic_memo, …) subclasses
``ReportBuilder`` and implements the ``build_sections`` and
``export_artifact`` hooks.  The base class drives the stage sequence that
mirrors the live DiligenceIQ SSE events:

    workflows → start → ingest → profile → storyline → build → done

Each stage yields SSE-compatible event dicts that the router streams to
the client.
"""

from __future__ import annotations

import contextvars
import json
import re
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api.report_store import (
    REPORT_TYPES,
    finish_report,
    report_artifact_dir,
    start_report,
)
from agetic_cdd_api.report_decision_chain import build_agent_decision_chain
from agetic_cdd_api.report_storyline import (
    StorylineSection,
    all_source_agents,
    default_storyline,
    storyline_as_dicts,
)
from agetic_cdd_api.services_deals import deals_root, resolve_sector

# Live Sources tab uses storyline slugs; Verdict Store uses some different keys.
_AGENT_OUTPUT_ALIASES: dict[str, tuple[str, ...]] = {
    "recommendations": ("recommendation", "recommendations"),
    "recommendation": ("recommendation", "recommendations"),
    "executive_summary": ("ic_synthesis", "executive_summary"),
    "final_valuation_range": ("valuation_modeling", "final_valuation_range"),
    "valuation_model": ("valuation_modeling", "valuation_model"),
    "sensitivity_analysis": ("valuation_modeling", "sensitivity_analysis", "recommendation"),
    "appendices": ("appendices", "scope_and_methodology"),
}

_VDR_SUFFIXES = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".csv", ".pptx", ".txt",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff",
}
_VDR_POINTER_RE = re.compile(r"(?i)please\s+see")

# Active deal company while a report is generating — used by prose sanitizers.
_REPORT_COMPANY: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "report_company", default=None
)
# Data-room source rows for upgrading generic DOC: tags during report build.
_REPORT_SOURCES: contextvars.ContextVar[list[Any] | None] = contextvars.ContextVar(
    "report_sources", default=None
)

# Keyword hints → sector id when deal metadata is still "generic".
_SECTOR_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("ev", (
        "electric vehicle", "e-scooter", "two-wheeler", "2w market",
        "ev penetration", "ev ", "battery swapping", "electric mobility",
    )),
    ("saas", ("saas", "arr ", "mrr ", "nrr ", "software subscription", "software as a service")),
    ("payments", ("payments", "fintech", "merchant acquiring", "payment gateway")),
    ("healthcare", ("healthcare", "life sciences", "pharma", "biotech", "medtech")),
    ("manufacturing", (
        "manufacturing", "industrials", "factory", "plant capacity",
        "automotive oem", "auto components", "passenger vehicle",
    )),
    ("waste_organics", (
        "compost", "composting", "organics", "organic waste", "food scrap",
        "food scraps", "organics collection", "waste recycling",
    )),
    ("logistics", ("logistics & freight", "freight forwarding", "warehousing", "last-mile delivery")),
    ("energy", ("energy & power", "renewable", "power generation", "oil & gas")),
    ("consumer", ("consumer retail", "e-commerce", "fmcg", "brick-and-mortar")),
    ("finserv", ("financial services", "banking", "insurance", "asset management")),
]


def _infer_sector_from_text(corpus: str) -> str:
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus

    # Prefer organics/composting over bare "Logistics (Hauling)" market labels
    specialized = infer_sector_id_from_corpus(corpus)
    if specialized != "generic":
        return specialized
    t = (corpus or "").lower()
    if not t.strip():
        return "generic"
    scored: list[tuple[int, str]] = []
    for sid, hints in _SECTOR_HINTS:
        score = sum(1 for h in hints if h in t)
        if score:
            scored.append((score, sid))
    if not scored:
        return "generic"
    scored.sort(key=lambda x: (-x[0], x[1]))
    return scored[0][1]


def _is_placeholder_company(name: str, slug: str) -> bool:
    from agetic_cdd_api.services_accounts_extract import is_placeholder_company

    return is_placeholder_company(name, slug)


def _clean_legal_name(raw: Any, *, fallback: str | None = None) -> str | None:
    """Keep a corporate legal name — strip cap-table / invented jurisdiction parentheticals."""
    if raw is None:
        text = ""
    else:
        text = str(raw).strip()
    if not text:
        return fallback
    # "Compost Crew (issuing common equity and options under 2023 Stock Option Plan)"
    text = re.sub(
        r"\s*\((?:issuing|grant(?:ing)?|under).{0,80}(?:stock\s+option|equity|option\s+plan)[^)]*\)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    # "Compost Crew (operating entity under Maryland / D.C. jurisdictions)" — not evidenced
    text = re.sub(
        r"\s*\([^)]*(?:operating entity|organized in|under .{0,40}jurisdiction)[^)]*\)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    # "Compost Crew (registered under Maryland and District of Columbia securities exemptions)"
    text = re.sub(
        r"\s*\([^)]*(?:registered under|securities\s+exemption|securities\s+exemptions)[^)]*\)\s*",
        "",
        text,
        flags=re.I,
    ).strip()
    text = re.sub(r"\s*\(DOC:\s*\[[^\]]+\]\)\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s+", " ", text).strip(" ·|-.,;")
    # Reject if it still looks like a prose clause, not a name
    if re.search(
        r"(?i)issuing common|stock option plan|outstanding shares|jurisdiction|organized in|"
        r"securities\s+exemption|registered under",
        text,
    ):
        return fallback
    if len(text) < 2 or len(text) > 120:
        return fallback
    return text


_CORP_BOILERPLATE_PAREN = re.compile(
    r"\s*\([^)]*(?:"
    r"registered under|securities\s+exemptions?|issuing common equity|"
    r"stock option plan|organized in|operating entity under|"
    r"under .{0,40}jurisdiction"
    r")[^)]*\)",
    re.I,
)
_UNSUPPORTED_ENTITY_SUFFIX = (
    r"(?:Inc\.?|Incorporated|LLC|L\.L\.C\.|Corp\.?|Corporation|Ltd\.?|Limited|"
    r"Benefit\s+Corporation|Public\s+Benefit\s+Corporation)"
)


def strip_corporate_boilerplate(text: str) -> str:
    """Remove invented registration / cap-table parentheticals stuck onto any prose."""
    t = _CORP_BOILERPLATE_PAREN.sub("", str(text or ""))
    return re.sub(r"\s{2,}", " ", t).strip(" ,;")


def strip_unsupported_entity_suffixes(text: str, *, company: str | None = None) -> str:
    """Drop Inc./LLC only when clearly invented; keep Benefit Corporation when present.

    Cap-table titles often read ``Compost Crew Inc., A Benefit Corporation`` —
    those suffixes are evidenced and must survive. Invented jurisdiction
    parentheticals are handled by ``strip_corporate_boilerplate``.
    """
    t = str(text or "")
    if not t:
        return t
    company = (company or "").strip()
    if company and re.search(_UNSUPPORTED_ENTITY_SUFFIX, company, flags=re.I):
        return t  # evidenced on the deal name — keep matching uses
    # Keep Inc. / Benefit Corporation — only strip bare LLC/Ltd when the deal
    # name itself has no corporate suffix (legacy invented-entity hygiene).
    if company and not re.search(r"(?i)\b(?:Inc|LLC|Ltd|Corp|Corporation)\b", company):
        t = re.sub(
            rf"(?i)\b({re.escape(company)})\s+(?:LLC|L\.L\.C\.|Ltd\.?|Limited)\b\.?",
            r"\1",
            t,
        )
    return t


_FINANCIAL_CITE_HINTS = (
    "financial",
    "workbook",
    "p&l",
    "pnl",
    "income",
    "balance",
    "cash flow",
    "cashflow",
    "cim",
    "management account",
    "monthly pack",
    "databook",
    "trading",
    "qbo",
    "ledger",
)


def _cite_source_names(sources: list[Any] | dict[str, Any] | None) -> list[str]:
    """Flatten source rows / report sources dict into unique basenames."""
    from pathlib import Path

    rows: list[Any] = []
    if isinstance(sources, dict):
        rows.extend(sources.get("cited_files") or [])
        rows.extend(sources.get("files") or [])
    elif isinstance(sources, list):
        rows = sources
    names: list[str] = []
    seen: set[str] = set()
    for src in rows:
        raw = ""
        if isinstance(src, str) and src.strip():
            raw = src.strip()
        elif isinstance(src, dict):
            name = src.get("filename") or src.get("name") or src.get("title")
            if isinstance(name, str) and name.strip():
                raw = name.strip()
        if not raw:
            continue
        short = Path(raw).name or raw
        key = short.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(short)
    return names


def agent_cite_source_names(agent: dict[str, Any] | None, *, limit: int = 3) -> list[str]:
    """Filenames from an agent payload for DOC: upgrades."""
    if not isinstance(agent, dict):
        return []
    names: list[str] = []
    seen: set[str] = set()
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    for s in list(agent.get("sources") or []) + list(spec.get("sources") or []):
        raw = ""
        if isinstance(s, str) and s.strip():
            raw = s.strip()
        elif isinstance(s, dict):
            name = s.get("filename") or s.get("name") or s.get("title")
            if isinstance(name, str) and name.strip():
                raw = name.strip()
        if not raw:
            continue
        short = Path(raw).name or raw
        key = short.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(short)
        if len(names) >= limit:
            break
    return names


def ctx_cite_source_names(
    ctx: BuildContext,
    *agent_keys: str,
    limit: int = 3,
) -> list[str]:
    """Collect cite filenames from agents, falling back to the VDR inventory."""
    names: list[str] = []
    seen: set[str] = set()
    for key in agent_keys:
        if not key:
            continue
        resolved_key, agent = _resolve_agent_output(ctx.agent_outputs or {}, key)
        _ = resolved_key
        for n in agent_cite_source_names(agent, limit=limit):
            if n.lower() in seen:
                continue
            seen.add(n.lower())
            names.append(n)
            if len(names) >= limit:
                return names
    if not names and getattr(ctx, "deal_slug", None):
        try:
            inv = _data_room_inventory(str(ctx.deal_slug))
            for f in (inv.get("files") or [])[:limit]:
                n = Path(str(f)).name if f else ""
                if n and n.lower() not in seen:
                    seen.add(n.lower())
                    names.append(n)
                if len(names) >= limit:
                    break
        except Exception:  # noqa: BLE001
            pass
    return names


def upgrade_generic_doc_cites(
    text: str,
    sources: list[Any] | dict[str, Any] | None,
    *,
    limit: int = 3,
) -> str:
    """Replace 'DOC: data room financials' with specific document filenames.

    Prefer short basenames so the committee can reopen the VDR file — never
    leave the generic placeholder, and avoid opaque ``DOC: [n]`` indexes.
    Prefer financial / workbook-looking names when available.
    """
    t = str(text or "")
    if not t or not re.search(r"(?i)DOC:\s*data room financials", t):
        return t
    names = _cite_source_names(sources)
    if not names:
        return t

    def _score(name: str) -> tuple[int, str]:
        low = name.lower()
        hit = any(h in low for h in _FINANCIAL_CITE_HINTS)
        return (0 if hit else 1, low)

    ranked = sorted(names, key=_score)[:limit]
    cites = ", ".join(f"DOC: {n}" for n in ranked)
    # Parenthesised form first, then bare tags.
    t = re.sub(r"(?i)\(DOC:\s*data room financials\)", f"({cites})", t)
    t = re.sub(r"(?i)(?<!\()DOC:\s*data room financials", cites, t)
    return t


def coerce_percent_points(value: float, *, family: str = "", unit: str = "") -> float:
    """Convert ratio-form retention/margins (0.87 / 1.07) to percent points (87 / 107).

    Values already in percent points are left unchanged. Generic — not deal-specific.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return value
    fam = (family or "").lower()
    unt = (unit or "").lower()
    is_pct = (
        unt in {"%", "pp", "pct", "percent", "percent_points"}
        or "margin" in fam
        or fam in {"nrr", "grr", "retention", "wacc"}
        or fam.endswith("_pct")
    )
    if not is_pct:
        return v
    # Retention can exceed 1.0 (NRR 1.07); margins sit in 0–1 as ratios.
    if fam in {"nrr", "grr", "retention"} or "retention" in fam:
        return v * 100.0 if abs(v) <= 3.0 + 1e-9 else v
    if "margin" in fam or fam.endswith("_pct") or unt in {"%", "pp", "pct", "percent"}:
        return v * 100.0 if abs(v) <= 1.5 + 1e-9 else v
    return v


def sanitize_chart_label_paste(text: str) -> str:
    """Rewrite jammed CIM/slide chart chrome into readable clauses.

    Detects ALL-CAPS label runs (CONTRACT POTENTIAL / MODEL ASSUMPTION / …)
    mixed with home counts — never invents figures, only re-punctuates.
    """
    t = str(text or "")
    if not t:
        return t
    caps = re.findall(r"\b[A-Z]{3,}\b", t)
    chartish = bool(
        re.search(
            r"(?i)\b(?:CONTRACT\s+POTENTIAL|MODEL\s+ASSUMPTION|HOMES?\s+TODAY|"
            r"WAITLIST|HOMES?\s+BY\s+\d{4})\b",
            t,
        )
    )
    if not chartish and len(caps) < 4:
        return t
    out = t
    out = re.sub(r"(?i)\bOUR\s+MODEL\s+ASSUMPTION\b", "Model assumption:", out)
    out = re.sub(r"(?i)\bMODEL\s+ASSUMPTION\b", "Model assumption:", out)
    out = re.sub(r"(?i)\bCONTRACT\s+POTENTIAL\b", "Contract potential:", out)
    out = re.sub(r"(?i)\bWAITLIST\s*=\s*", "waitlist ", out)
    out = re.sub(r":\s*:", ": ", out)
    out = re.sub(
        r"(?i)\b([\d,]+)\s+HOMES?\s+TODAY\b",
        r"\1 homes today;",
        out,
    )
    out = re.sub(
        r"(?i)\b([\d,]+)\s+HOMES?\s+BY\s+(\d{4})\b",
        r"\1 homes by \2;",
        out,
    )
    # Drop residual ALL-CAPS chrome tokens (keep mixed-case / numbers / $).
    out = re.sub(r"\b[A-Z]{4,}(?:\s+[A-Z]{4,})+\b", " ", out)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s*;\s*", "; ", out)
    out = re.sub(r"\s*:\s*", ": ", out)
    out = out.strip(" ;.,")
    if out and out[-1] not in ".!?":
        out += "."
    return out


def sanitize_dc_contract_framing(text: str) -> str:
    """Structural cleanup for contract/homes framing — never invents deal-specific figures.

    Relabels dollars using cues already in the same string (FY…A / plan / projected).
    Does not inject baselines that are absent from the text.
    """
    t = str(text or "")
    if not t:
        return t
    t = re.sub(
        r"(?i)municipal\s+revenuely\b",
        "municipal revenue",
        t,
    )
    # Un-nest "homes ($XM (vs $YM …) revenue)" using the same figures in-text.
    t = re.sub(
        r"(?i)([\d,]+)\s*[-–—]\s*([\d,]+)\s+homes?\s*"
        r"\(\s*(\$[\d.]+M)\s*\(\s*vs\s*(\$[\d.]+M)[^)]*\)\s*revenue\s*\)",
        r"\1–\2 homes generating \3 to \4",
        t,
        count=1,
    )
    t = re.sub(
        r"(?i)(\$[\d.]+M)\s*\(\s*vs\s*(\$[\d.]+M)\s+full-contract\s+potential\s*\)\s*revenue",
        r"\1 to \2",
        t,
        count=1,
    )
    t = re.sub(
        r"(?i)generating\s+(\$[\d.]+M)\s*\(\s*vs\s*(\$[\d.]+M)\s+full-contract\s+potential\s*\)",
        r"generating \1 to \2",
        t,
        count=1,
    )
    # If the same string already carries a labeled FY…A / actual dollar AND an
    # unlabeled "~$XM revenue" beside homes, prefer the labeled actual phrase.
    actual = re.search(
        r"(?i)(\$[\d.]+M)\s*(?:\(?\s*)?(FY\d{4}A|FY\d{4}\s+actual)(?:\s+municipal\s+revenue)?",
        t,
    )
    if actual:
        labeled = actual.group(0).strip()
        if not re.search(r"(?i)municipal\s+revenue", labeled):
            labeled = f"{labeled} municipal revenue"
        t = re.sub(
            r"(?i)\(~?\$[\d.]+M\s+revenue\)",
            f"({labeled})",
            t,
            count=1,
        )
        t = re.sub(
            r"(?i)~?\$[\d.]+M\s+revenue(?!\s*\([^)]*FY)(?!\s+FY)",
            labeled,
            t,
            count=1,
        )
    return t


def _sanitize_ownership_totals(text: str) -> str:
    """Re-sum ownership lines from share quantities present in the text.

    Does not invent holders, titles, or totals from another deal. Thin one-holder
    lines stay thin unless the same string already carries the other components.
    """
    t = str(text or "")
    if not t:
        return t
    if not re.search(
        r"(?i)(?:Total evidenced|common equity|cap table|ownership|"
        r"shares?\s+outstanding|\d{1,3}(?:,\d{3}){2,})",
        t,
    ):
        return t
    from agetic_cdd_api.agent_document_company_background import (
        _canonicalize_cap_table_text,
    )

    fixed = _canonicalize_cap_table_text(t)
    return fixed if fixed else t


def sanitize_report_prose(
    text: str,
    *,
    company: str | None = None,
    sources: list[Any] | None = None,
) -> str:
    """Stable report-time cleanup for DC framing, boilerplate, entity suffixes, cites."""
    t = str(text or "")
    if not t:
        return t
    company = company or _REPORT_COMPANY.get()
    cite_sources = sources if sources is not None else _REPORT_SOURCES.get()
    t = strip_corporate_boilerplate(t)
    t = strip_unsupported_entity_suffixes(t, company=company)
    # Keep ledger Job Titles when present in the text; do not invent them.
    t = sanitize_chart_label_paste(t)
    t = sanitize_dc_contract_framing(t)
    t = _sanitize_ownership_totals(t)
    t = upgrade_generic_doc_cites(t, cite_sources)
    # Ownership finding already leads with "Total evidenced…" — drop redundant label
    t = re.sub(
        r"(?i)^(Ownership:\s*)+(Total evidenced common equity/option shares:)",
        r"\2",
        t,
    )
    t = re.sub(
        r"(?i)(Total evidenced common equity/option shares:[^.]*\.)\s*"
        r"(?:Ownership:\s*)?Total evidenced common equity/option shares:[^.]*\.\s*",
        r"\1 ",
        t,
    )
    # Collapse repeated gap notes from re-sanitize loops.
    t = re.sub(
        r"(?i)(\s*Stated common outstanding:\s*[\d,]+\.)(?:\s*Stated common outstanding:\s*[\d,]+\.)+",
        r"\1",
        t,
    )
    t = re.sub(
        r"(?i)(\s*Attributed certificates sum to [\d,]+ \(stated common outstanding [\d,]+\).)"
        r"(?:\s*Attributed certificates sum to [\d,]+ \(stated common outstanding [\d,]+\).)+",
        r"\1",
        t,
    )
    return re.sub(r"\s{2,}", " ", t).strip()


def _recover_legal_name(raw: Any) -> str | None:
    """Pull a clean legal name out of company-background / CIM paste fields."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    m = re.search(r"Legal\s+Name\s+(.+?)(?:\s+CIN\b|\s+Founded\b|\s+Parameter\b|$)", text, re.I)
    if m:
        name = _clean_legal_name(m.group(1))
        if name:
            return name
    cleaned = _clean_legal_name(text)
    if cleaned and len(cleaned) <= 90 and "parameter" not in cleaned.lower() and "insight snapshot" not in cleaned.lower():
        return cleaned
    return None


def _agent_text_blob(agent: dict[str, Any], *, limit: int = 4000) -> str:
    bits: list[str] = []
    for key in ("summary", "agentName", "target_company"):
        val = agent.get(key)
        if isinstance(val, str) and val.strip():
            bits.append(val)
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    for k, v in list(spec.items())[:40]:
        if isinstance(v, str) and v.strip():
            bits.append(v)
        elif isinstance(v, (int, float)):
            bits.append(f"{k}={v}")
        elif isinstance(v, dict):
            bits.append(json.dumps(v, default=str)[:400])
        elif isinstance(v, list):
            bits.append(json.dumps(v[:8], default=str)[:600])
    for item in (agent.get("findings") or [])[:12]:
        if isinstance(item, str):
            bits.append(item)
        elif isinstance(item, dict):
            bits.append(str(item.get("finding") or item.get("note") or item.get("name") or ""))
    blob = "\n".join(bits)
    return blob[:limit]


def _agent_spec(agent: dict[str, Any]) -> dict[str, Any]:
    s = agent.get("spec")
    return s if isinstance(s, dict) else {}


@dataclass
class DealProfile:
    """Lightweight deal profile assembled during the ``profile`` stage."""
    deal_slug: str
    company: str = ""
    sector: str = "generic"
    years: list[int] = field(default_factory=list)
    metrics: list[str] = field(default_factory=list)
    has_segments: bool = False
    has_pricing: bool = False
    has_acquisitions: bool = False


@dataclass
class BuildContext:
    """Mutable context threaded through the build pipeline."""
    deal_slug: str
    report_type: str
    profile: DealProfile | None = None
    storyline: list[StorylineSection] = field(default_factory=list)
    sources: dict[str, Any] = field(default_factory=dict)
    agent_outputs: dict[str, Any] = field(default_factory=dict)
    artifact_path: str | None = None


def _evt(stage: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"stage": stage, "message": message, "t": time.time(), **extra}


def _resolve_agent_output(
    agent_outputs: dict[str, Any], key: str
) -> tuple[str, dict[str, Any]]:
    """Return (resolved_key, payload) for a storyline agent slug."""
    for cand in _AGENT_OUTPUT_ALIASES.get(key, (key,)):
        data = agent_outputs.get(cand)
        if isinstance(data, dict) and data:
            return cand, data
    data = agent_outputs.get(key)
    return key, data if isinstance(data, dict) else {}


def _agent_source_files(agent: dict[str, Any], *, limit: int = 8) -> list[str]:
    files: list[str] = []
    seen: set[str] = set()
    spec = agent.get("spec") if isinstance(agent.get("spec"), dict) else {}
    for s in list(agent.get("sources") or []) + list(spec.get("sources") or []):
        if isinstance(s, str) and s.strip() and s not in seen:
            seen.add(s)
            files.append(s)
        if len(files) >= limit:
            break
    return files


def _data_room_inventory(deal_slug: str) -> dict[str, Any]:
    """Union of on-disk VDR uploads + library / evidence-graph document names."""
    deal_dir = deals_root() / deal_slug
    names: set[str] = set()

    docs_dir = deal_dir / "documents"
    if docs_dir.is_dir():
        for f in docs_dir.iterdir():
            if f.is_file() and not f.name.startswith(".") and f.suffix.lower() in _VDR_SUFFIXES:
                names.add(f.name)

    idx_path = deal_dir / "library" / "index.json"
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text())
            for doc in idx.get("documents") or []:
                if isinstance(doc, dict):
                    name = doc.get("filename") or doc.get("name") or doc.get("original_name")
                    if isinstance(name, str) and name.strip():
                        names.add(name.strip())
                elif isinstance(doc, str) and doc.strip():
                    names.add(doc.strip())
        except (json.JSONDecodeError, OSError):
            pass

    eg_path = deal_dir / "library" / "evidence_graph.json"
    if eg_path.exists():
        try:
            eg = json.loads(eg_path.read_text())
            vdr = eg.get("vdr")
            if isinstance(vdr, list):
                for name in vdr:
                    if isinstance(name, str) and name.strip():
                        names.add(name.strip())
        except (json.JSONDecodeError, OSError):
            pass

    files = sorted(names)
    stubs = [f for f in files if _VDR_POINTER_RE.search(Path(f).name)]
    return {
        "count": len(files),
        "files": files,
        "stub_count": len(stubs),
        "content_count": len(files) - len(stubs),
    }


class ReportBuilder(ABC):
    """Base class for all report builders.

    Subclasses MUST implement:
    - ``build_sections(ctx)`` — populate section content from agent outputs.
    - ``export_artifact(ctx)`` — write the final file and return its path.
    """

    report_type: str

    def __init__(self, deal_slug: str, report_type: str | None = None):
        self.deal_slug = deal_slug
        self.report_type = report_type or getattr(self, "report_type", "")
        self.ctx = BuildContext(deal_slug=deal_slug, report_type=self.report_type)

    # ------------------------------------------------------------------
    # Stage hooks — subclasses may override for richer behaviour
    # ------------------------------------------------------------------

    def discover_workflows(self) -> dict[str, Any]:
        """Read available pipeline agent outputs from the deal's outputs dir."""
        outputs_dir = deals_root() / self.deal_slug / "outputs"
        agents: list[str] = []
        agent_data: dict[str, Any] = {}
        if outputs_dir.is_dir():
            for f in sorted(outputs_dir.glob("*.json")):
                key = f.stem
                agents.append(key)
                try:
                    agent_data[key] = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError):
                    agent_data[key] = {}
        self.ctx.agent_outputs = agent_data
        return {"agents": agents, "count": len(agents)}

    def ingest_data_room(self) -> dict[str, Any]:
        """Reads VDR documents and returns inventory counts."""
        inv = _data_room_inventory(self.deal_slug)
        return {"docs": inv["count"], "files": inv["files"]}

    def build_profile(self) -> DealProfile:
        """Assemble a lightweight company profile from available data."""
        deal_dir = deals_root() / self.deal_slug
        profile = DealProfile(deal_slug=self.deal_slug)

        idx_path = deal_dir / "library" / "index.json"
        if idx_path.exists():
            try:
                idx = json.loads(idx_path.read_text())
                profile.company = idx.get("company", idx.get("name", self.deal_slug))
                profile.sector = resolve_sector(str(idx.get("sector") or "generic"))
            except (json.JSONDecodeError, OSError):
                pass

        # Prefer deal-row metadata when the library index is thin / placeholder.
        try:
            from sqlalchemy import select

            from agetic_cdd_api.db import SessionLocal
            from agetic_cdd_api.models import Deal

            db = SessionLocal()
            try:
                deal = db.scalar(select(Deal).where(Deal.slug == self.deal_slug))
                if deal is not None:
                    if deal.company and (
                        not profile.company or _is_placeholder_company(profile.company, self.deal_slug)
                    ):
                        profile.company = deal.company
                    if deal.sector and (
                        not profile.sector or profile.sector == "generic"
                    ):
                        profile.sector = resolve_sector(deal.sector)
            finally:
                db.close()
        except Exception:
            pass

        if not self.ctx.agent_outputs:
            self.discover_workflows()

        # Recover legal name when the deal card still says Test2 / slug.
        bg = self.ctx.agent_outputs.get("company_background")
        if isinstance(bg, dict):
            legal = _recover_legal_name(_agent_spec(bg).get("legal_name"))
            if legal and _is_placeholder_company(profile.company, self.deal_slug):
                profile.company = legal

        # Infer sector from market / thesis corpus when still generic — and override
        # weak/wrong deal-card sectors when compost/organics evidence is decisive.
        corpus_parts: list[str] = []
        if profile.company:
            corpus_parts.append(str(profile.company))
        inv = _data_room_inventory(self.deal_slug)
        corpus_parts.extend(inv.get("files") or [])
        for key in (
            "market_definition",
            "market_volume_and_growth",
            "strategic_direction",
            "company_background",
            "demand_drivers",
            "ic_synthesis",
            "deal_context_and_objectives",
        ):
            agent = self.ctx.agent_outputs.get(key)
            if isinstance(agent, dict) and agent:
                corpus_parts.append(_agent_text_blob(agent))
        inferred = _infer_sector_from_text("\n".join(corpus_parts))
        if inferred != "generic":
            # Never keep finserv/generic when VDR/company clearly say organics.
            if (
                not profile.sector
                or profile.sector == "generic"
                or (inferred == "waste_organics" and profile.sector in {"finserv", "saas", "generic"})
            ):
                profile.sector = inferred

        hist = self.ctx.agent_outputs.get("historical_performance", {})
        if isinstance(hist, dict):
            metrics = hist.get("metrics")
            if not isinstance(metrics, dict):
                metrics = _agent_spec(hist).get("metrics")
            profile.metrics = list(metrics.keys()) if isinstance(metrics, dict) else []

        if not profile.company:
            profile.company = self.deal_slug
        if not profile.sector:
            profile.sector = "generic"

        self.ctx.profile = profile
        return profile

    def resolve_storyline(self) -> list[StorylineSection]:
        """Return the default storyline (callers may have set a custom one)."""
        if not self.ctx.storyline:
            self.ctx.storyline = default_storyline(self.report_type)
        return self.ctx.storyline

    @abstractmethod
    def build_sections(self, ctx: BuildContext) -> Iterator[dict[str, Any]]:
        """Populate report content section-by-section, yielding SSE events."""
        ...

    @abstractmethod
    def export_artifact(self, ctx: BuildContext) -> str:
        """Write the export file and return its path relative to deal folder."""
        ...

    # ------------------------------------------------------------------
    # Build sources summary (for Sources tab)
    # ------------------------------------------------------------------

    def build_sources(self) -> dict[str, Any]:
        storyline = self.ctx.storyline or self.resolve_storyline()
        if not self.ctx.agent_outputs:
            self.discover_workflows()

        inv = _data_room_inventory(self.deal_slug)
        agent_keys = all_source_agents(storyline)
        cited: list[str] = []
        cited_seen: set[str] = set()
        sections_detail: list[dict[str, Any]] = []

        for s in storyline:
            if not s.included:
                continue
            section_files: list[str] = []
            section_seen: set[str] = set()
            decision_chain: list[dict[str, Any]] = []
            for key in s.agents:
                resolved_key, agent = _resolve_agent_output(self.ctx.agent_outputs, key)
                files = _agent_source_files(agent)
                for f in files:
                    if f not in section_seen:
                        section_seen.add(f)
                        section_files.append(f)
                    if f not in cited_seen:
                        cited_seen.add(f)
                        cited.append(f)
                decision_chain.append(
                    build_agent_decision_chain(
                        agent_key=key,
                        resolved_key=resolved_key,
                        agent=agent,
                        source_files=files,
                    )
                )
            sections_detail.append({
                "title": s.title,
                "agents": s.agents,
                "source_files": section_files[:12],
                "decision_chain": decision_chain,
            })

        # Live chip is "data-room files". Prefer on-disk/index inventory; if agents
        # cite additional VDR filenames not present locally, include them so the
        # Sources tab reflects what the workflow actually grounded on.
        data_room_names = set(inv["files"])
        for f in cited:
            if Path(f).suffix.lower() in _VDR_SUFFIXES:
                data_room_names.add(Path(f).name if "/" in f else f)
        data_room_files = sorted(data_room_names)

        sources = {
            "data_room_files": len(data_room_files) or inv["count"],
            "files": data_room_files or inv["files"],
            "cited_files": cited,
            "cited_file_count": len(cited),
            "web_research": False,
            "workflow_agents": len(agent_keys),
            "agent_keys": agent_keys,
            "sections": sections_detail,
            "analyst_document": False,
        }
        self.ctx.sources = sources
        return sources

    # ------------------------------------------------------------------
    # Main generation loop — yields SSE event dicts
    # ------------------------------------------------------------------

    def generate(self) -> Iterator[dict[str, Any]]:
        """Run the full generation pipeline, yielding SSE events."""

        start_report(self.deal_slug, self.report_type)

        try:
            # 1. workflows
            wf = self.discover_workflows()
            yield _evt("workflows", f"workflow output found: {wf['count']} agent(s)",
                       level="info", workflows={"ran": True, **wf})

            # 2. ingest & profile (resolve company metadata before start event)
            ingest = self.ingest_data_room()
            profile = self.build_profile()
            _REPORT_COMPANY.set((profile.company or "").strip() or None)
            # Prefetch sources so sanitize_report_prose can upgrade DOC: tags mid-build.
            early_sources = self.build_sources()
            _REPORT_SOURCES.set(early_sources or None)

            # 3. start (now has resolved company name)
            rt_label = REPORT_TYPES.get(self.report_type, {}).get("label", self.report_type)
            yield _evt("start", f"Generating {rt_label} for {profile.company or self.deal_slug}",
                       report_type=self.report_type)

            yield _evt("ingest", f"retrieval-augmented extraction ({ingest['docs']} docs)")

            # 4. profile
            yield _evt("profile",
                       f"Company: {profile.company} (sector: {profile.sector})",
                       company=profile.company, sector=profile.sector)

            # 5. storyline
            storyline = self.resolve_storyline()
            enabled = sum(1 for s in storyline if s.included)
            yield _evt("storyline",
                       f"storyline: {enabled} of {len(storyline)} sections enabled",
                       sections=len(storyline))

            # 6. build (delegated to subclass)
            yield _evt("build", f"composing {rt_label}")
            yield from self.build_sections(self.ctx)

            # 7. sources (reuse early prefetch)
            sources = early_sources if early_sources else self.build_sources()
            self.ctx.sources = sources

            # 8. export
            artifact = self.export_artifact(self.ctx)
            self.ctx.artifact_path = artifact

            # 9. done
            finish_report(
                self.deal_slug,
                self.report_type,
                storyline=storyline_as_dicts(storyline),
                sources=sources,
                artifact_path=artifact,
            )
            export_fmt = REPORT_TYPES.get(self.report_type, {}).get("export", "")
            yield _evt("done",
                       f"{rt_label} — {enabled} sections, export: .{export_fmt}")

        except Exception as exc:
            finish_report(self.deal_slug, self.report_type, error=str(exc))
            yield _evt("error", str(exc), level="error")
            raise
