"""Phase 1 classify lite: file register, set-aside gate, source ladder, forecast isolation.

Builds ``file_register.json`` from the CDL library index + filename/excerpt heuristics.
Does not require LLM. Downstream extract skips set-aside files; resolve ranks by ladder.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_models import (
    ActualForecast,
    ExpectedDocsAssessment,
    ExpectedDocPresence,
    ExpectedDocSpec,
    FileRegister,
    FileRegisterEntry,
    FileRelevance,
    FileRole,
    SOURCE_LADDER_SCORE,
    SourceBasis,
)
from agetic_cdd_api.services_databook_store import save_file_register
from agetic_cdd_api.services_databook_utils import text_matches_hints
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import load_library_index

logger = logging.getLogger(__name__)

# --- Set-aside heuristics (filename / path) ---------------------------------
_PERSONAL_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"personal|brokerage[\s_-]*letter|curriculum[\s_-]*vitae|\bcv\b|resume|linkedin|"
    r"passport|driver.?s?[\s_-]*licen[cs]e|family[\s_-]*office[\s_-]*intro"
    r")(?![a-z0-9])"
)
_OTHER_PROPERTY_RE = re.compile(
    r"(?i)\b("
    r"other\s*propert|wrong\s*deal|unrelated\s*lease|third[\s_-]*party\s*lease|"
    r"not\s*this\s*deal|misc\s*settlement"
    r")\b"
)
# Filename tokens that are document vocabulary, not alien company names.
STANDARD_DOC_TOKENS = frozenset(
    {
        "financial",
        "statement",
        "statements",
        "report",
        "annual",
        "audit",
        "audited",
        "draft",
        "management",
        "accounts",
        "consol",
        "consolidated",
        "group",
        "qoe",
        "pack",
        "board",
        "month",
        "monthly",
        "year",
        "yearly",
        "final",
        "signed",
        "quarterly",
        "interim",
        "appendix",
        "schedule",
        "presentation",
        "breakdown",
        "operating",
        "revenue",
        "working",
        "paper",
        "papers",
        "overview",
        "analysis",
        "databook",
        "model",
        "forecast",
        "budget",
        "actual",
        "actuals",
        "history",
        "historical",
        "excel",
        "xlsx",
        "pdf",
        "pptx",
        "docx",
        "sheet",
        "tables",
        "table",
        "bridge",
        "ebitda",
        "pnl",
        "pl",
        "bs",
        "cashflow",
        "cash",
        "flow",
        "version",
        "v1",
        "v2",
        "v3",
        "update",
        "revised",
        "confidential",
        "information",
        "memorandum",
        "cim",
        "data",
        "room",
        "vdr",
        # Transaction / diligence vocabulary — not alien company names.
        "vendor",
        "due",
        "diligence",
        "commercial",
        "project",
        "phase",
        "strategic",
        "transaction",
        "merger",
        "acquisition",
        "supplier",
        "partner",
        "internal",
        "external",
        "review",
        "summary",
        "memo",
        "notes",
        "filing",
        "compliance",
        "regulatory",
    }
)
# Relative forecast periods that must never become history FY columns.
_FORECAST_PERIOD_RE = re.compile(
    r"(?i)^\s*("
    r"year\s*[1-5]|y\s*[1-5]|yr\s*[1-5]|"
    r"forecast(?:\s*year)?\s*[1-5]?|projected|budget\s*year|"
    r"plan\s*year|outer\s*year"
    r")\s*$"
)
# Relative / forward-looking header tokens (not sufficient alone when a history FY is present).
_FORECAST_HEADER_TOKEN_RE = re.compile(
    r"(?i)\b("
    r"year\s*[1-5]|y\s*[1-5]|forecast|projected|budget\s*fy|plan\s*fy"
    r")\b"
)
# History FY markers: FY2024, FY 24, FY24, F.Y.2024 (2- or 4-digit).
_FY_YEAR_RE = re.compile(r"\b(?:fy|f\.?y\.?)\s*(?:(?:19|20)?\d{2})\b", re.I)
_CALENDAR_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
_AUDITED_RE = re.compile(
    r"(?i)\b("
    r"audited|signed\s*audit|independent\s*auditor|statutory\s*audit|"
    r"10[\s_-]?k|20[\s_-]?f|annual\s*report|financial\s*statements\s*\(audited\)"
    r")\b"
)
_DRAFT_RE = re.compile(r"(?i)\b(draft|preliminary|unaudited\s*draft|working\s*draft)\b")
_ADVISER_RE = re.compile(
    r"(?i)\b("
    r"qoe|quality\s*of\s*earnings|cim|confidential\s*information\s*memorandum|"
    r"kpmg|grant\s*thornton|deloitte|ey\b|pwc|adviser|advisor|sell[\s_-]*side"
    r")\b"
)
_DEAL_PAPERS_RE = re.compile(
    r"(?i)\b(spa|share\s*purchase|teaser|process\s*letter|nbo|ioi|term\s*sheet)\b"
)
_MANAGEMENT_RE = re.compile(
    r"(?i)\b("
    r"management\s*accounts|monthly\s*pack|flash\s*report|board\s*pack|"
    r"mis\b|internal\s*pack"
    r")\b"
)
_FORECAST_DOC_RE = re.compile(
    r"(?i)\b(budget|forecast|projection|business\s*plan|lrp|long[\s_-]*range)\b"
)


def deal_identity_tokens(deal: Deal) -> set[str]:
    """Significant tokens from deal name/company for wrong-deal heuristics."""
    tokens: set[str] = set()
    for raw in (deal.company, deal.name, deal.slug):
        if not raw:
            continue
        for part in re.findall(r"[a-zA-Z]{3,}", str(raw).lower()):
            if part in {"the", "and", "ltd", "limited", "inc", "plc", "corp", "company", "deal"}:
                continue
            tokens.add(part)
    return tokens


def is_forecast_period_header(text: str) -> bool:
    """True when a table header is a relative/forecast period, not a history FY."""
    cell = (text or "").strip()
    if not cell:
        return False
    # Relative plan years (Year 1…5) always isolate — even when annotated with FY20xx.
    if re.search(r"(?i)\byear\s*[1-5]\b", cell) or re.search(r"(?i)\by\s*[1-5]\b", cell):
        return True
    if _FORECAST_PERIOD_RE.match(cell):
        return True
    # Explicit calendar/FY year → history column (Budget vs Actual 2023, Forecast FY24).
    if _FY_YEAR_RE.search(cell) or _CALENDAR_YEAR_RE.search(cell):
        return False
    if _FORECAST_HEADER_TOKEN_RE.search(cell):
        return True
    return False


def infer_basis(filename: str, excerpt: str = "", cdl_category: str = "") -> SourceBasis:
    """Infer source ladder basis. Audited wins; adviser beats generic draft tags."""
    blob = f"{filename}\n{excerpt}\n{cdl_category}"
    if _AUDITED_RE.search(blob):
        return SourceBasis.AUDITED
    # QoE_Draft_Report → ADVISER (not DRAFT); adviser packs outrank bare "draft".
    if _ADVISER_RE.search(blob):
        return SourceBasis.ADVISER
    if _DRAFT_RE.search(blob):
        return SourceBasis.DRAFT
    if _DEAL_PAPERS_RE.search(blob):
        return SourceBasis.DEAL_PAPERS
    if _MANAGEMENT_RE.search(blob):
        return SourceBasis.MANAGEMENT
    cat = (cdl_category or "").lower()
    if "financial" in cat or "audit" in cat:
        return SourceBasis.MANAGEMENT
    return SourceBasis.UNKNOWN


def infer_actual_forecast(filename: str, excerpt: str = "") -> ActualForecast:
    blob = f"{filename}\n{excerpt}"
    if _FORECAST_DOC_RE.search(blob) and not _AUDITED_RE.search(blob):
        return ActualForecast.FORECAST
    if _FORECAST_DOC_RE.search(blob) and _AUDITED_RE.search(blob):
        return ActualForecast.MIXED
    return ActualForecast.ACTUAL


def classify_set_aside(
    *,
    filename: str,
    excerpt: str,
    deal_tokens: set[str],
    cdl_category: str = "",
) -> tuple[bool, str | None]:
    """Return (is_set_aside, reason)."""
    blob = f"{filename}\n{excerpt[:2000]}"
    if _PERSONAL_RE.search(blob):
        return True, "Personal / non-deal document"
    if _OTHER_PROPERTY_RE.search(blob):
        return True, "Other-property / wrong-deal marker in filename or excerpt"

    # Wrong-deal lite: filename contains a clear alien company-like token and none of ours.
    name_bits = re.findall(r"[a-zA-Z]{4,}", filename.lower())
    if deal_tokens and name_bits:
        alien = [
            t
            for t in name_bits
            if t not in deal_tokens and t not in STANDARD_DOC_TOKENS
        ]
        ours = [t for t in name_bits if t in deal_tokens]
        # Only fire when filename looks entity-named, our deal tokens are absent,
        # and multiple non-vocabulary tokens remain (avoid vendor/diligence false positives).
        if alien and not ours and len(alien) >= 3 and len(filename) > 24:
            # Require excerpt also lacks deal tokens when excerpt is long enough.
            excerpt_l = excerpt.lower()
            if len(excerpt_l) > 200 and not any(t in excerpt_l for t in deal_tokens):
                return True, "Filename/excerpt lack deal identity tokens (possible wrong-deal)"

    return False, None


def classify_entry(
    entry: dict[str, Any],
    *,
    deal_tokens: set[str],
) -> FileRegisterEntry:
    filename = str(entry.get("filename") or "")
    doc_id = str(entry.get("library_stem") or filename)
    cdl = str(entry.get("cdl_category") or "")
    doc_kind = str(entry.get("doc_kind") or "") or None
    excerpt = str(entry.get("excerpt") or "")

    set_aside, reason = classify_set_aside(
        filename=filename,
        excerpt=excerpt,
        deal_tokens=deal_tokens,
        cdl_category=cdl,
    )
    basis = infer_basis(filename, excerpt, cdl)
    actual_forecast = infer_actual_forecast(filename, excerpt)
    ladder = SOURCE_LADDER_SCORE[basis]
    notes: list[str] = []

    if set_aside:
        relevance = FileRelevance.SET_ASIDE
        role = FileRole.SET_ASIDE
        notes.append(reason or "Set aside")
    elif actual_forecast == ActualForecast.FORECAST:
        relevance = FileRelevance.IN_SCOPE
        role = FileRole.FORECAST_ONLY
        notes.append("Forecast/budget document — excluded from history FY columns")
    else:
        relevance = FileRelevance.IN_SCOPE
        role = FileRole.HISTORY_SOURCE
        if basis == SourceBasis.ADVISER:
            role = FileRole.SUPPORTING
            notes.append("Adviser pack — allowed but lower on source ladder")

    return FileRegisterEntry(
        filename=filename,
        doc_id=doc_id,
        relevance=relevance,
        role=role,
        basis=basis,
        ladder_score=ladder,
        actual_forecast=actual_forecast,
        cdl_category=cdl or None,
        doc_kind=doc_kind,
        set_aside_reason=reason,
        notes=notes,
    )


def build_file_register(deal: Deal) -> FileRegister:
    index = load_library_index(deal) or {}
    entries_raw = index.get("documents") if isinstance(index, dict) else []
    if not isinstance(entries_raw, list):
        entries_raw = []
    tokens = deal_identity_tokens(deal)
    entries: list[FileRegisterEntry] = []
    for raw in entries_raw:
        if not isinstance(raw, dict) or not raw.get("filename"):
            continue
        entries.append(classify_entry(raw, deal_tokens=tokens))

    by_basis: dict[str, int] = {}
    for e in entries:
        by_basis[e.basis.value] = by_basis.get(e.basis.value, 0) + 1
    counts: dict[str, Any] = {
        "total": len(entries),
        "in_scope": sum(1 for e in entries if e.relevance == FileRelevance.IN_SCOPE),
        "set_aside": sum(1 for e in entries if e.relevance == FileRelevance.SET_ASIDE),
        "forecast_only": sum(1 for e in entries if e.role == FileRole.FORECAST_ONLY),
        "history_source": sum(1 for e in entries if e.role == FileRole.HISTORY_SOURCE),
        "by_basis": by_basis,
    }

    register = FileRegister(
        deal_slug=deal.slug or deal.id,
        generated_at=utc_now_iso(),
        entries=sorted(entries, key=lambda e: e.filename.lower()),
        counts=counts,
    )
    save_file_register(deal, register)
    try:
        build_expected_docs_for_deal(deal, register=register, persist=True)
    except Exception as exc:  # noqa: BLE001 — classify must not fail on expected-docs
        logger.warning("Expected-docs assessment failed for %s: %s", deal.slug, exc)
    logger.info(
        "Databook file register for %s: %s",
        deal.slug,
        {k: counts[k] for k in ("total", "in_scope", "set_aside", "forecast_only")},
    )
    return register


def register_by_filename(register: FileRegister | None) -> dict[str, FileRegisterEntry]:
    if register is None:
        return {}
    return {e.filename: e for e in register.entries}


def allows_history_extract(entry: FileRegisterEntry | None) -> bool:
    """Whether extract may emit history FY rows from this file."""
    if entry is None:
        return True  # unclassified → allow (fail-open for empty register)
    if entry.relevance == FileRelevance.SET_ASIDE or entry.role == FileRole.SET_ASIDE:
        return False
    if entry.role == FileRole.FORECAST_ONLY:
        return False
    return True


def ladder_score_for_source(
    source_name: str,
    by_file: dict[str, FileRegisterEntry],
    *,
    row_ladder: int | None = None,
) -> int:
    if row_ladder is not None:
        return int(row_ladder)
    entry = by_file.get(source_name)
    if entry is None and source_name:
        # Path / stem resilience: register keys are bare filenames.
        base = Path(source_name).name
        entry = by_file.get(base)
        if entry is None and base:
            # Stem match when extension differs (e.g. .pdf vs register without ext).
            stem = Path(base).stem.lower()
            for name, candidate in by_file.items():
                if Path(name).stem.lower() == stem:
                    entry = candidate
                    break
    if entry is not None:
        return int(entry.ladder_score)
    return SOURCE_LADDER_SCORE[SourceBasis.UNKNOWN]


# ---------------------------------------------------------------------------
# G2 — Expected-document catalog (S2-6)
# ---------------------------------------------------------------------------

_GENERIC_EXPECTED_DOCS: tuple[ExpectedDocSpec, ...] = (
    ExpectedDocSpec(
        doc_kind="audited_financials",
        label="Audited financial statements",
        required=True,
        match_hints=[
            "audited",
            "financial statements",
            "statutory audit",
            "independent auditor",
            "10-k",
            "20-f",
            "annual report",
        ],
        covers_metrics=[
            "revenue",
            "ebitda",
            "gross_profit",
            "gross_margin",
            "ebitda_margin",
            "yoy_growth",
        ],
    ),
    ExpectedDocSpec(
        doc_kind="management_accounts",
        label="Management accounts / board packs",
        required=True,
        match_hints=[
            "management accounts",
            "management pack",
            "board pack",
            "monthly accounts",
            "flash report",
        ],
        covers_metrics=["revenue", "ebitda", "gross_profit"],
    ),
    ExpectedDocSpec(
        doc_kind="qoe_report",
        label="Quality of earnings (QoE) report",
        required=False,
        match_hints=["qoe", "quality of earnings", "adjusted ebitda"],
        covers_metrics=["ebitda", "ebitda_margin"],
    ),
)

_SAAS_EXPECTED_DOCS: tuple[ExpectedDocSpec, ...] = (
    *_GENERIC_EXPECTED_DOCS,
    ExpectedDocSpec(
        doc_kind="cohort_retention",
        label="Cohort / retention schedule (NRR/GRR)",
        required=True,
        match_hints=[
            "cohort",
            "retention",
            "nrr",
            "grr",
            "net revenue retention",
            "logo retention",
        ],
        covers_metrics=["nrr", "grr"],
    ),
)


def expected_doc_templates(profile: str = "generic") -> list[ExpectedDocSpec]:
    pack = (profile or "generic").strip().lower()
    if pack == "saas":
        return list(_SAAS_EXPECTED_DOCS)
    return list(_GENERIC_EXPECTED_DOCS)


def _entry_match_blob(entry: FileRegisterEntry) -> str:
    parts = [
        entry.filename or "",
        entry.cdl_category or "",
        entry.doc_kind or "",
        entry.basis.value if entry.basis else "",
        entry.role.value if entry.role else "",
        " ".join(entry.notes or []),
        entry.set_aside_reason or "",
    ]
    return " ".join(parts).lower()


def match_register_to_expected(
    entry: FileRegisterEntry,
    spec: ExpectedDocSpec,
) -> bool:
    """True when a register row satisfies an expected-doc template."""
    if entry.relevance == FileRelevance.SET_ASIDE or entry.role == FileRole.SET_ASIDE:
        return False
    blob = _entry_match_blob(entry)
    if text_matches_hints(blob, list(spec.match_hints)):
        return True
    # Basis shortcuts
    if spec.doc_kind == "audited_financials" and entry.basis == SourceBasis.AUDITED:
        return True
    if spec.doc_kind == "management_accounts" and entry.basis == SourceBasis.MANAGEMENT:
        return entry.role in {FileRole.HISTORY_SOURCE, FileRole.SUPPORTING, FileRole.UNKNOWN}
    return False


def assess_expected_docs(
    register: FileRegister | None,
    *,
    deal_slug: str,
    profile: str = "generic",
    generated_at: str | None = None,
) -> ExpectedDocsAssessment:
    """Diff expected-document templates against the current file register."""
    from agetic_cdd_api.services_databook_coverage import assessment_from_presence
    from agetic_cdd_api.services_ingestion import utc_now_iso

    specs = expected_doc_templates(profile)
    entries = list(register.entries) if register is not None else []
    docs: list[ExpectedDocPresence] = []
    for spec in specs:
        matched = [e.filename for e in entries if match_register_to_expected(e, spec)]
        docs.append(
            ExpectedDocPresence(
                doc_kind=spec.doc_kind,
                label=spec.label,
                required=spec.required,
                present=bool(matched),
                matched_filenames=matched,
                covers_metrics=list(spec.covers_metrics),
            )
        )
    return assessment_from_presence(
        deal_slug=deal_slug,
        profile=(profile or "generic").strip().lower(),
        generated_at=generated_at or utc_now_iso(),
        docs=docs,
    )


def build_expected_docs_for_deal(
    deal: Deal,
    *,
    register: FileRegister | None = None,
    profile: str | None = None,
    persist: bool = True,
) -> ExpectedDocsAssessment:
    """Assess expected docs for a deal; optionally persist ``expected_docs.json``."""
    from agetic_cdd_api.services_databook_store import (
        load_file_register,
        load_meta,
        save_expected_docs,
    )

    reg = register if register is not None else load_file_register(deal)
    meta = load_meta(deal)
    params = getattr(meta, "params", None) if meta is not None else None
    resolved = (
        profile
        or getattr(params, "expected_doc_profile", None)
        or getattr(params, "sector_pack", None)
        or "generic"
    )
    assessment = assess_expected_docs(
        reg,
        deal_slug=deal.slug or deal.id,
        profile=str(resolved),
    )
    if persist:
        save_expected_docs(deal, assessment)
    return assessment

