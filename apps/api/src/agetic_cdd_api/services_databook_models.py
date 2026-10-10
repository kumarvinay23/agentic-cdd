"""Databook domain models (file-backed store)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field


@runtime_checkable
class DealLike(Protocol):
    """Minimal deal identity for file-backed databook IO (ORM Deal or slug stand-in)."""

    id: str
    slug: str | None


class RowStatus(str, Enum):
    CANDIDATE = "candidate"
    HELD_OUT = "held_out"
    DROPPED = "dropped"
    PROMOTED = "promoted"
    VOUCHED = "vouched"


class MetricFamily(str, Enum):
    REVENUE = "revenue"
    UNITS = "units"
    RETENTION = "retention"
    GROWTH = "growth"
    MARGIN = "margin"
    SHARE = "share"
    OTHER = "other"
    UNKNOWN = "unknown"


# Retention / ARR metrics require an allowlisted sector pack to auto-promote.
DEFAULT_SAAS_ONLY_METRICS: tuple[str, ...] = (
    "grr",
    "nrr",
    "arr",
    "logo_churn",
    "revenue_churn",
)
DEFAULT_SAAS_METRIC_PACKS: tuple[str, ...] = ("saas",)


class DealDatabookParams(BaseModel):
    currency: str = "INR"
    scale: str = "Cr"  # display scale hint; values stored as extracted
    fy_convention: str = "calendar"  # calendar | ending_march
    block_tie_rel_tol: float = 0.005
    series_magnitude_ratio: float = 100.0
    # Hold out values ~×1000 / ÷1000 vs series centre (thousand-scale misread).
    scale_step_ratio: float = 1000.0
    scale_step_tol: float = 0.25  # accept ratio in [step*(1-tol), step*(1+tol)]
    llm_map_enabled: bool = False
    # Phase 4 — chart of accounts / sector pack
    sector_pack: str = "generic"  # generic | saas
    # Metrics that only auto-promote when sector_pack ∈ saas_metric_packs.
    saas_only_metrics: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SAAS_ONLY_METRICS)
    )
    saas_metric_packs: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SAAS_METRIC_PACKS)
    )
    # Phase 5 — minimum proof for auto-promote / proven release
    min_proof_level: str = "L2"
    # G2 — optional coverage overrides (else sector defaults / inferred years)
    coverage_keys: list[str] | None = None
    coverage_years: list[int] | None = None
    expected_doc_profile: str | None = None  # generic | saas | None→sector_pack

    def blocks_saas_metric(self, metric_key: str | None) -> bool:
        """True when metric_key is SaaS-only and the active pack is not allowlisted."""
        if not metric_key:
            return False
        only = {m.strip().lower() for m in self.saas_only_metrics if m}
        if metric_key.strip().lower() not in only:
            return False
        pack = (self.sector_pack or "").strip().lower()
        allowed = {p.strip().lower() for p in self.saas_metric_packs if p}
        return pack not in allowed


class SourceRef(BaseModel):
    """Traceability for an extracted cell (doc / table / row / col / rule).

    Phase 2 adds page + optional bbox for click-to-page (S1-8 / AC-5 lite).
    G4 adds crop_ref / crop_status when a page clip has been rendered.
    """

    doc: str | None = None
    page: int | None = None
    table: str | None = None
    row: int | None = None
    col: int | None = None
    rule: str | None = None
    # Axis-aligned crop in page-normalized coords [x0, y0, x1, y1] (0–1), when known.
    bbox: list[float] | None = None
    extract_methods: list[str] = Field(default_factory=list)
    # G4 — rendered crop under databook/crops/ (relative basename or deal-relative path)
    crop_ref: str | None = None
    crop_status: Literal["available", "unavailable", "pending"] | None = None
    crop_reason: str | None = None


class PageKind(str, Enum):
    """How a page/sheet presents content (S1-1)."""

    TEXT = "text"
    SCAN = "scan"
    MIXED = "mixed"
    IMAGE = "image"
    BLANK = "blank"
    UNKNOWN = "unknown"


class PageClass(str, Enum):
    """Financial page / sheet class (S2-7 / G3)."""

    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    EQUITY = "equity"
    NOTE = "note"
    EBITDA_BRIDGE = "ebitda_bridge"
    KPI = "kpi"
    OTHER = "other"
    UNKNOWN = "unknown"


StatementSource = Literal[
    "table_header",
    "table_name",
    "page_class",
    "sheet_name",
    "merged",
    "inferred",
]


class PageRegisterEntry(BaseModel):
    """One page (PDF) or sheet (XLSX) in the deal library."""

    page_id: str
    filename: str
    doc_id: str
    page: int  # 1-based page or sheet index
    kind: PageKind = PageKind.UNKNOWN
    char_count: int = 0
    has_images: bool = False
    sheet_name: str | None = None
    ocr_status: Literal["not_needed", "not_available", "pending"] = "not_needed"
    unread: bool = False  # True when no trustworthy text/grid was obtained
    notes: list[str] = Field(default_factory=list)
    # G3 — financial page class (IS / BS / CF / …)
    page_class: PageClass = PageClass.UNKNOWN
    page_class_source: StatementSource | None = None
    page_class_confidence: float = 0.0
    page_class_notes: list[str] = Field(default_factory=list)


class PageRegister(BaseModel):
    deal_slug: str
    generated_at: str
    entries: list[PageRegisterEntry] = Field(default_factory=list)
    counts: dict[str, Any] = Field(default_factory=dict)


class FileRelevance(str, Enum):
    IN_SCOPE = "in_scope"
    SET_ASIDE = "set_aside"
    UNKNOWN = "unknown"


class FileRole(str, Enum):
    """How the file should participate in financial history."""

    HISTORY_SOURCE = "history_source"
    FORECAST_ONLY = "forecast_only"
    SET_ASIDE = "set_aside"
    SUPPORTING = "supporting"  # notes / bridges — extract allowed but ladder-weak
    UNKNOWN = "unknown"


class SourceBasis(str, Enum):
    AUDITED = "audited"
    DRAFT = "draft"
    MANAGEMENT = "management"
    ADVISER = "adviser"
    DEAL_PAPERS = "deal_papers"
    UNKNOWN = "unknown"


class ActualForecast(str, Enum):
    ACTUAL = "actual"
    FORECAST = "forecast"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class ProofLevel(str, Enum):
    """PDF accuracy-contract proof levels (AC-8). Final release requires L2+."""

    L0 = "L0"  # extracted only / unmapped / unusable
    L1 = "L1"  # mapped candidate — insufficient proof
    L2 = "L2"  # dual-agree + unique + arithmetic/series clear
    L3 = "L3"  # L2 + cross-document agree
    L4 = "L4"  # L3 + HITL vouch


# Numeric rank for comparisons (release gate, promote gate).
PROOF_LEVEL_RANK: dict[ProofLevel, int] = {
    ProofLevel.L0: 0,
    ProofLevel.L1: 1,
    ProofLevel.L2: 2,
    ProofLevel.L3: 3,
    ProofLevel.L4: 4,
}


class FailureClass(str, Enum):
    """S5-13 — why a prove check failed."""

    ENGINE = "engine"
    SOURCE = "source"
    DEFINITION = "definition"
    MISSING = "missing"


# Higher score wins in conflict ranking (signed audit ≫ … ≫ deal papers).
SOURCE_LADDER_SCORE: dict[SourceBasis, int] = {
    SourceBasis.AUDITED: 100,
    SourceBasis.MANAGEMENT: 70,
    SourceBasis.ADVISER: 55,
    SourceBasis.DRAFT: 40,
    SourceBasis.DEAL_PAPERS: 25,
    SourceBasis.UNKNOWN: 50,
}


class FileRegisterEntry(BaseModel):
    """Stage-2 file register row (Phase 1 classify lite)."""

    filename: str
    doc_id: str
    relevance: FileRelevance = FileRelevance.UNKNOWN
    role: FileRole = FileRole.UNKNOWN
    basis: SourceBasis = SourceBasis.UNKNOWN
    ladder_score: int = 50
    actual_forecast: ActualForecast = ActualForecast.UNKNOWN
    cdl_category: str | None = None
    doc_kind: str | None = None
    set_aside_reason: str | None = None
    notes: list[str] = Field(default_factory=list)


class FileRegister(BaseModel):
    deal_slug: str
    generated_at: str
    entries: list[FileRegisterEntry] = Field(default_factory=list)
    counts: dict[str, Any] = Field(default_factory=dict)


class ExtractedRow(BaseModel):
    """Statement-line fact with the eight labels (Phase 3 / AC-1).

    Labels: scope, statement, line (caption), period_end, period_length,
    basis (source_basis), unit (+ currency/scale), source (source_ref).
    """

    row_id: str
    doc_id: str
    source_name: str
    caption: str  # Line label
    metric_key: str | None = None
    metric_family: MetricFamily = MetricFamily.UNKNOWN
    fiscal_year: int | None = None
    period: str | None = None
    value: float
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    assumption: bool = False
    block_id: str | None = None
    status: RowStatus = RowStatus.CANDIDATE
    table_name: str | None = None
    # Eight labels (Phase 3)
    scope: str | None = None
    statement: str | None = None
    period_end: str | None = None
    period_length: str | None = None
    source_ref: SourceRef | None = None
    # Provenance of unit/scale: header wins; caption/map are weaker.
    unit_source: Literal["header", "caption", "map", "assumed"] | None = None
    scale_source: Literal["header", "caption", "map", "assumed"] | None = None
    currency_source: Literal["header", "caption", "map", "assumed"] | None = None
    # Phase 1 classify provenance (copied from file register at extract time).
    source_basis: SourceBasis | None = None
    ladder_score: int | None = None
    actual_forecast: ActualForecast | None = None
    # Phase 4 CoA mapping
    coa_id: str | None = None
    coa_section: str | None = None
    derived: bool = False
    dual_agree: bool | None = None  # CoA dual-agree (Phase 4)
    # Phase 2 — dual independent grid extract (S1-2 / S1-3)
    read_dual_agree: bool | None = None
    extract_methods: list[str] = Field(default_factory=list)
    # Phase 5 proof
    proof_level: ProofLevel | None = None
    proof_checks: list[str] = Field(default_factory=list)
    # G3 — page/table class + statement routing provenance
    page_class: PageClass | None = None
    statement_source: StatementSource | None = None
    statement_mismatch: bool = False


class NoteFact(BaseModel):
    """Prose / sentence figure — never fills a statement line (S1-9 / lesson 10)."""

    note_id: str
    doc_id: str
    source_name: str
    caption: str
    fiscal_year: int | None = None
    value: float
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    excerpt: str | None = None
    reason: str = "prose"
    metric_key: str | None = None
    metric_family: MetricFamily = MetricFamily.UNKNOWN


class NotesStore(BaseModel):
    deal_slug: str
    generated_at: str
    notes: list[NoteFact] = Field(default_factory=list)
    count: int = 0


class StatementBlock(BaseModel):
    block_id: str
    doc_id: str
    source_name: str
    period: str | None = None
    fiscal_year: int | None = None
    line_row_ids: list[str] = Field(default_factory=list)
    printed_subtotal: float | None = None
    computed_sum: float | None = None
    ties: bool | None = None
    outcome: Literal["pass", "fail", "no_table", "unchecked"] = "unchecked"


class ConflictCandidate(BaseModel):
    value: float
    sources: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)
    chosen: bool = False
    stated_by: int = 1
    source_facts: int = 0
    source_total_facts: int = 0
    row_ids: list[str] = Field(default_factory=list)


class DataQualityDropped(BaseModel):
    kind: Literal["dropped"] = "dropped"
    source: str = "series"
    reason: str
    detail: dict[str, Any]


class DataQualityConflict(BaseModel):
    kind: Literal["conflict"] = "conflict"
    metric: str
    fiscal_year: int | None = None
    chosen: float | None = None
    candidates: list[ConflictCandidate] = Field(default_factory=list)
    scope: Literal["across documents", "within one document"]
    rule: str


class DataQualitySummary(BaseModel):
    total: int = 0
    by_kind: dict[str, int] = Field(default_factory=dict)
    needs_review: int = 0


class DataQualityResponse(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    summary: DataQualitySummary = Field(default_factory=DataQualitySummary)


class PromotedMetric(BaseModel):
    metric_key: str
    fiscal_year: int
    value: float
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    row_id: str
    sources: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)
    decision_id: str | None = None
    auto: bool = True
    # Phase 3 labels carried into release
    scope: str | None = None
    statement: str | None = None
    period_end: str | None = None
    period_length: str | None = None
    source_basis: SourceBasis | None = None
    source_ref: SourceRef | None = None
    proof_level: ProofLevel | None = None
    proof_checks: list[str] = Field(default_factory=list)


class ReleaseCellStatus(str, Enum):
    """PDF accuracy-contract statuses for a released databook cell."""

    PROVEN = "proven"
    DOUBTFUL = "doubtful"
    MISSING = "missing"


class DocumentRequest(BaseModel):
    """First-class document / figure request (G2 / AR-5).

    Missing cells point here so FDD / Findings can open an RFI without inventing numbers.
    """

    request_id: str
    doc_kind: str
    label: str
    reason: str
    metric_keys: list[str] = Field(default_factory=list)
    fiscal_years: list[int] = Field(default_factory=list)
    priority: Literal["required", "optional"] = "required"
    status: Literal["open", "satisfied", "waived"] = "open"
    matched_filenames: list[str] = Field(default_factory=list)


class ExpectedDocSpec(BaseModel):
    """One expected VDR document kind for a deal profile (S2-6)."""

    doc_kind: str
    label: str
    required: bool = True
    match_hints: list[str] = Field(default_factory=list)
    covers_metrics: list[str] = Field(default_factory=list)
    covers_years: Literal["all", "latest"] = "all"


class ExpectedDocPresence(BaseModel):
    """Whether an expected doc kind is present in the file register."""

    doc_kind: str
    label: str
    required: bool = True
    present: bool = False
    matched_filenames: list[str] = Field(default_factory=list)
    covers_metrics: list[str] = Field(default_factory=list)


class ExpectedDocsAssessment(BaseModel):
    """Expected-document catalog vs current VDR register (G2)."""

    deal_slug: str
    profile: str = "generic"
    generated_at: str
    docs: list[ExpectedDocPresence] = Field(default_factory=list)
    missing_required: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)


class CoverageSpec(BaseModel):
    """Expected metric×year coverage for honest missing synthesis (AC-3)."""

    keys: list[str] = Field(default_factory=list)
    years: list[int] = Field(default_factory=list)
    source: Literal["params", "expected_docs", "material_default", "golden"] = "material_default"


class ReleasedCell(BaseModel):
    metric_key: str
    fiscal_year: int
    status: ReleaseCellStatus
    value: float | None = None
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    row_id: str | None = None
    sources: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)
    reason: str | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    decision_id: str | None = None
    auto: bool = True
    scope: str | None = None
    statement: str | None = None
    period_end: str | None = None
    period_length: str | None = None
    source_basis: SourceBasis | None = None
    source_ref: SourceRef | None = None
    proof_level: ProofLevel | None = None
    proof_checks: list[str] = Field(default_factory=list)
    # G2 — link missing cells to a first-class document request
    request_id: str | None = None
    document_request: DocumentRequest | None = None


class DatabookRelease(BaseModel):
    """Immutable released databook snapshot (P0). Working store may diverge until next release."""

    release_id: str
    version: int
    created_at: str
    deal_slug: str
    source: Literal["manual", "rescan", "decision", "bootstrap", "import"] = "manual"
    note: str | None = None
    cells: list[ReleasedCell] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    # G2 — coverage honesty + document requests (AR-5)
    coverage: CoverageSpec | None = None
    request_list: list[DocumentRequest] = Field(default_factory=list)
    expected_docs: ExpectedDocsAssessment | None = None


# ---------------------------------------------------------------------------
# Phase 6 — Validation pack + learning (OL-*)
# ---------------------------------------------------------------------------


class ValidationCardKind(str, Enum):
    """Why a cell appears in the post-run validation pack."""

    DOUBTFUL = "doubtful"
    CONFLICT = "conflict"
    MISSING = "missing"
    CALIBRATION = "calibration"  # proven sample for reviewer calibration (OL-4)


class ValidationCard(BaseModel):
    """One review card: labels, alternatives, dependents; page crop (G4)."""

    card_id: str
    kind: ValidationCardKind
    metric_key: str
    fiscal_year: int
    status: ReleaseCellStatus
    value: float | None = None
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    row_id: str | None = None
    sources: list[str] = Field(default_factory=list)
    captions: list[str] = Field(default_factory=list)
    reason: str | None = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    # Eight labels (AC-1 / OL-2)
    scope: str | None = None
    statement: str | None = None
    period_end: str | None = None
    period_length: str | None = None
    source_basis: SourceBasis | None = None
    source_ref: SourceRef | None = None
    proof_level: ProofLevel | None = None
    proof_checks: list[str] = Field(default_factory=list)
    # Dependent metric keys that share the same year / statement (OL-2)
    dependents: list[str] = Field(default_factory=list)
    release_id: str | None = None
    release_version: int | None = None
    # G4 — page crop when rendered; source_ref.page/bbox enable click-to-page
    crop_ref: str | None = None
    crop_status: Literal["available", "unavailable", "pending"] = "unavailable"
    crop_reason: str | None = None
    # G2 — document request for missing cards
    request_id: str | None = None
    document_request: DocumentRequest | None = None

class ValidationPack(BaseModel):
    """Post-run pack: doubtful/conflict/missing + calibration sample of proven (OL-1, OL-4)."""

    deal_slug: str
    release_id: str | None = None
    release_version: int | None = None
    generated_at: str
    cards: list[ValidationCard] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    ready_for_review: bool = False  # True when a current release exists (OL-1)


class MappingMemoryEntry(BaseModel):
    """Learned caption → metric remaps from HITL (OL-7)."""

    memory_id: str
    caption_key: str
    metric_key: str
    family: str | None = None
    statement: str | None = None
    sector_pack: str = "generic"
    source_decision_id: str | None = None
    deal_slug: str | None = None
    hit_count: int = 1
    created_at: str
    updated_at: str


class TrapRecord(BaseModel):
    """Regression trap seeded from a HITL decision (OL-6 → feeds P7 harness)."""

    trap_id: str
    kind: Literal[
        "wrong_metric",
        "wrong_value",
        "wrong_year",
        "scale_misread",
        "exclude_row",
        "confirm_proven",
        "pick_alternative",
    ]
    caption: str | None = None
    metric_key: str | None = None
    fiscal_year: int | None = None
    bad_value: float | None = None
    good_value: float | None = None
    source_name: str | None = None
    source_decision_id: str | None = None
    deal_slug: str | None = None
    note: str | None = None
    created_at: str


class DecisionLineage(BaseModel):
    """Decision → release lineage for OL-5."""

    decision_id: str
    action: str
    at: str | None = None
    actor: str | None = None
    row_id: str | None = None
    release_id: str | None = None
    release_version: int | None = None
    match: dict[str, Any] = Field(default_factory=dict)


class DatabookMeta(BaseModel):
    version: int = 1
    last_rescan_at: str | None = None
    last_deep_at: str | None = None
    params: DealDatabookParams = Field(default_factory=DealDatabookParams)
    row_count: int = 0
    promoted_count: int = 0
    held_out_count: int = 0
    issue_count: int = 0
    current_release_id: str | None = None
    current_release_version: int | None = None
    last_release_at: str | None = None
    release_stale: bool = False
    # Phase 6 learning summaries
    mapping_memory_count: int = 0
    trap_count: int = 0
    last_validation_pack_at: str | None = None


class DatabookSummary(BaseModel):
    deal_id: str
    meta: DatabookMeta
    flags: dict[str, int] = Field(default_factory=dict)
    promoted_preview: list[PromotedMetric] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)
    release: dict[str, Any] | None = None
    file_register: dict[str, Any] | None = None
    page_register: dict[str, Any] | None = None
    validation_pack: dict[str, Any] | None = None


DEFAULT_CONFLICT_RULE = (
    "source ladder (audited ≫ management ≫ adviser ≫ draft ≫ deal papers), "
    "then most documents stating it, then that source's coverage of this metric, "
    "then how much of the fact base the source supplies, then how plainly the caption "
    "names the metric, then the most central value"
)

SERIES_DROP_REASON = (
    "value is orders of magnitude below the series centre - a ratio, not the amount"
)

SCALE_STEP_REASON = (
    "value is ~×1000 or ÷1000 vs the series centre — possible thousand-scale misread"
)
