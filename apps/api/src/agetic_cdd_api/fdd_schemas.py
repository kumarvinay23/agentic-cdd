"""FDD Phase 0 artefact schemas (Appendix A lite).

Exhibit numbers must carry a databook fact id (or explicit hand-built Phase-0
seed id). Agents never seed exhibit figures.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ArtefactStatus(str, Enum):
    DRAFT = "draft"
    CHECKED = "checked"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class FigureType(str, Enum):
    REPORTED = "reported"
    CALCULATED = "calculated"
    ESTIMATED = "estimated"
    JUDGEMENT = "judgement"


class EvidenceTier(str, Enum):
    A = "A"  # ledgers / primary
    B = "B"  # management
    C = "C"  # audited only / weaker


class CellStatus(str, Enum):
    """Inherited from databook release status (Phase 1 binds for real)."""

    PROVEN = "proven"
    DOUBTFUL = "doubtful"
    MISSING = "missing"
    DRAFT = "draft"  # Phase 0 / below-contract


class GateId(str, Enum):
    G0 = "G0"
    G1 = "G1"
    G2 = "G2"
    G3 = "G3"
    G4 = "G4"
    G5 = "G5"
    G6 = "G6"
    G7 = "G7"


class RunStage(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"
    P5 = "P5"
    P6 = "P6"
    P7 = "P7"
    P8 = "P8"
    P9 = "P9"
    P10 = "P10"


# ---------------------------------------------------------------------------
# Core artefacts
# ---------------------------------------------------------------------------


class FddRunManifest(BaseModel):
    """Pinned inputs for one FDD run (PDF §7 orchestration)."""

    model_config = ConfigDict(protected_namespaces=())

    run_id: str
    deal_slug: str
    created_at: str
    updated_at: str | None = None
    status: ArtefactStatus = ArtefactStatus.DRAFT
    stage: RunStage = RunStage.P0
    draft_mode: bool = True  # until Phase 1 contract bridge clears it
    contract_complete: bool = False
    g6_blocked: bool = True  # IN-3 — partner gate unavailable in draft mode
    allow_pinned_release: bool = False  # intentional pin ≠ current is OK
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    model_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    scope_profile_id: str | None = None
    g0_passed: bool = False
    g0_score: float | None = None
    g1_approved: bool = False
    claims_built: bool = False
    unreliable_modules: list[str] = Field(default_factory=list)
    g2_passed: bool = False  # auto — claims ledger reliable (P2 / G2)
    models_built: bool = False
    g3_passed: bool = False  # auto — model check packs (P4 / G3)
    qoe_built: bool = False
    g4_approved: bool = False
    qoe_version: str | None = None
    commentary_built: bool = False
    qa_built: bool = False
    g5_approved: bool = False
    g6_approved: bool = False  # partner challenge (P9)
    snapshot_id: str | None = None
    g7_verified: bool = False
    note: str | None = None
    contract_reasons: list[str] = Field(default_factory=list)


# Default FDD sections (matrix SEC-A…K + ES). SEC-J forecast is opt-in.
DEFAULT_SECTIONS_IN_SCOPE: list[str] = [
    "SEC-A",
    "SEC-B",
    "SEC-C",
    "SEC-D",
    "SEC-E",
    "SEC-F",
    "SEC-G",
    "SEC-H",
    "SEC-I",
    "SEC-K",
    "SEC-ES",
]

OPTIONAL_SECTIONS: list[str] = ["SEC-J"]

# G0 — design default ≥90% of required inputs present at tier C+.
G0_PASS_THRESHOLD = 0.90

# IN-5 defaults (materiality M).
DEFAULT_MATERIALITY_BASIS = "adj_ebitda"
DEFAULT_MATERIALITY_PCT = 0.05  # 5% of adj. EBITDA
MATERIALITY_REVENUE_BAND = (0.005, 0.01)  # 0.5–1% revenue
TRIVIAL_FRACTION_OF_M = 0.05  # trivial < 5% of M


class ScopeProfile(BaseModel):
    """G1 scope profile (Phase 2 / IN-4)."""

    profile_id: str
    deal_slug: str
    run_id: str | None = None
    status: ArtefactStatus = ArtefactStatus.DRAFT
    entities_in: list[str] = Field(default_factory=list)
    entities_out: list[str] = Field(default_factory=list)
    deal_type: str | None = None  # e.g. buy-side / sell-side / carve-out
    periods: list[str] = Field(default_factory=list)  # e.g. FY22A, FY23A, FY24A
    currency: str = "USD"
    scale: str | None = "M"
    materiality_m: float | None = None  # absolute M once known
    materiality_basis: str = DEFAULT_MATERIALITY_BASIS
    materiality_pct: float = DEFAULT_MATERIALITY_PCT
    sections_in_scope: list[str] = Field(
        default_factory=lambda: list(DEFAULT_SECTIONS_IN_SCOPE)
    )
    notes: str | None = None
    updated_at: str | None = None
    approved_at: str | None = None
    approved_by: str | None = None
    approval_id: str | None = None


# Phase 3 — module unreliable when >50% of its tested claims fail.
CLAIMS_RELIABILITY_FAIL_THRESHOLD = 0.50
# Relative tolerance when comparing agent figure to databook fact.
CLAIMS_VALUE_TOLERANCE = 0.005  # 0.5%
# Absolute floor must stay tight so small EBITDA gaps (0.572 vs 0.565) contradict.
CLAIMS_ABS_TOLERANCE = 0.005


class ClaimsLedgerEntry(BaseModel):
    """Agent → claim tested against databook (Phase 3 / R2 / D3)."""

    claim_id: str
    source_agent: str | None = None
    text: str
    kind: Literal["financial", "qualitative"] = "qualitative"
    metric_key: str | None = None
    fiscal_year: int | None = None
    claimed_value: float | None = None
    unit: str | None = None
    databook_fact_id: str | None = None
    databook_value: float | None = None
    test_result: Literal["agrees", "contradicted", "unverifiable", "pending"] = "pending"
    cited_pages: list[str] = Field(default_factory=list)
    narrative_ok: bool = False  # qualitative: True only when cited_pages present
    failed: bool = False  # convenience: contradicted/unverifiable or uncited qualitative


class ModuleReliability(BaseModel):
    """Per-agent reliability from claim test outcomes."""

    source_agent: str
    total: int = 0
    financial_total: int = 0
    failed: int = 0
    fail_rate: float = 0.0
    unreliable: bool = False  # True when fail_rate > CLAIMS_RELIABILITY_FAIL_THRESHOLD


class ClaimsLedgerDoc(BaseModel):
    """Persisted claims ledger for one FDD run."""

    run_id: str
    deal_slug: str
    updated_at: str
    databook_release_id: str | None = None
    claim_count: int = 0
    financial_count: int = 0
    qualitative_count: int = 0
    agrees: int = 0
    contradicted: int = 0
    unverifiable: int = 0
    pending: int = 0
    unreliable_modules: list[str] = Field(default_factory=list)
    modules: list[ModuleReliability] = Field(default_factory=list)
    claims: list[ClaimsLedgerEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EightLabels(BaseModel):
    """Databook accuracy-contract eight labels (AC-1 / IN-2)."""

    scope: str | None = None
    statement: str | None = None
    line: str | None = None
    period_end: str | None = None
    period_length: str | None = None
    basis: str | None = None
    unit: str | None = None
    source: str | None = None

    def missing_fields(self) -> list[str]:
        fields = (
            "scope",
            "statement",
            "line",
            "period_end",
            "period_length",
            "basis",
            "unit",
            "source",
        )
        return [f for f in fields if not getattr(self, f)]

    @property
    def complete(self) -> bool:
        return not self.missing_fields()


class FddFact(BaseModel):
    """One FDD fact bound from a released databook cell (Phase 1)."""

    fact_id: str
    metric_key: str
    fiscal_year: int
    value: float | None = None
    display: str | None = None
    status: CellStatus
    release_status: CellStatus  # pre-draft-flag status from release
    labels: EightLabels = Field(default_factory=EightLabels)
    labels_complete: bool = False
    draft_flagged: bool = False
    currency: str | None = None
    scale: str | None = None
    unit: str | None = None
    row_id: str | None = None
    proof_level: str | None = None
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    source_ref: dict[str, Any] | None = None
    request_id: str | None = None
    sources: list[str] = Field(default_factory=list)
    # Competing release candidates (ledger vs workbook) for gap disclosure.
    alternatives: list[dict[str, Any]] = Field(default_factory=list)


class FactTableDoc(BaseModel):
    """Persisted FDD fact table for one run (Phase 1 bridge output)."""

    run_id: str
    deal_slug: str
    updated_at: str
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    draft_mode: bool = True
    contract_complete: bool = False
    g6_blocked: bool = True
    reasons: list[str] = Field(default_factory=list)
    facts: list[FddFact] = Field(default_factory=list)


class LabelGap(BaseModel):
    """Structured eight-label gap for a material cell (prefer over parsing reasons)."""

    metric_key: str
    fiscal_year: int
    missing_fields: list[str] = Field(default_factory=list)


class DatabookContractAssessment(BaseModel):
    """Whether the pinned/current release meets FDD databook minimum (IN-2/IN-3)."""

    deal_slug: str
    release_id: str | None = None
    release_version: int | None = None
    complete: bool = False
    draft_mode: bool = True
    g6_allowed: bool = False
    cell_count: int = 0
    material_count: int = 0
    labels_incomplete: int = 0
    label_gaps: list[LabelGap] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class ExhibitCell(BaseModel):
    """One numeric cell in the exhibit store — sole figure source for renders."""

    model_config = ConfigDict(protected_namespaces=())

    cell_id: str
    exhibit_id: str
    label: str
    value: float | None = None
    display: str | None = None  # optional pre-formatted string
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    fiscal_year: int | None = None
    metric_key: str | None = None
    fact_id: str  # databook row/fact id or explicit hand-built seed id
    figure_type: FigureType = FigureType.REPORTED
    evidence_tier: EvidenceTier = EvidenceTier.C
    status: CellStatus = CellStatus.DRAFT
    draft_flagged: bool = False  # True when run is in draft mode (IN-3)
    basis_label: str | None = None
    labels: EightLabels | None = None
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    model_id: str | None = None
    model_version: str | None = None
    source_ref: dict[str, Any] | None = None


class Exhibit(BaseModel):
    exhibit_id: str
    title: str
    section_id: str | None = None  # e.g. SEC-B
    status: ArtefactStatus = ArtefactStatus.DRAFT
    scale_header: str | None = None
    cells: list[ExhibitCell] = Field(default_factory=list)
    footnotes: list[str] = Field(default_factory=list)


class ExhibitStoreDoc(BaseModel):
    """Persisted exhibit store for one run."""

    run_id: str
    deal_slug: str
    updated_at: str
    exhibits: list[Exhibit] = Field(default_factory=list)


# Phase 5a — QoE (M4). Treatments match PDF §5 / Appendix B4.
QoeTreatment = Literal[
    "accept",
    "partial",
    "reject",
    "sensitivity",
    "pro_forma",
    "pending",
]
QoeEvidenceStatus = Literal[
    "verified",
    "supported",
    "asserted",
    "adviser_only",
    "pending",
]
QoeCategory = Literal[
    "definitional",
    "non_recurring",
    "non_operating",
    "non_cash",
    "normalisation",
    "reclassification",
    "pro_forma",
    "sensitivity",
]
QoeMaterialityBand = Literal["above_m", "above_trivial", "trivial"]
QoeReviewerDecision = Literal[
    "approved",
    "amended",
    "rejected",
    "deferred",
    "pending",
]


class QoeConsumeRef(BaseModel):
    """One fact amount consumed by a register row (anti double-count)."""

    fact_id: str
    amount: float


class AdjustmentRow(BaseModel):
    """QoE register row (Phase 5a / PDF §5)."""

    adjustment_id: str
    event_key: str
    period: str = "FY25A"
    label: str
    category: QoeCategory = "non_recurring"
    proposed_by: Literal["management", "adviser", "diligence", "library", "agent"] = (
        "diligence"
    )
    management_amount: float | None = None
    diligence_amount: float | None = None
    # Convenience alias used by older stub callers / exhibit seeding.
    amount: float | None = None
    difference: float | None = None
    difference_reason: str | None = None
    treatment: QoeTreatment = "pending"
    evidence_status: QoeEvidenceStatus = "pending"
    evidence_documents: list[str] = Field(default_factory=list)
    source_fact_ids: list[str] = Field(default_factory=list)
    consumes: list[QoeConsumeRef] = Field(default_factory=list)
    rationale: str | None = None
    recurring_status: Literal["non_recurring", "recurring", "uncertain"] | None = None
    cash_impact: Literal["cash", "non_cash", "timing"] | None = None
    materiality_band: QoeMaterialityBand | None = None
    reviewer_decision: QoeReviewerDecision = "pending"
    reviewer_by: str | None = None
    reviewer_at: str | None = None
    reviewer_note: str | None = None
    origin: list[str] = Field(default_factory=list)
    consumed_by: list[str] = Field(default_factory=list)


class QoeBaselinePeriod(BaseModel):
    period: str
    management_reported_ebitda: float | None = None
    diligence_reported_ebitda: float | None = None
    revenue: float | None = None
    revenue_fact_id: str | None = None
    ebitda_fact_id: str | None = None
    basis_note: str | None = None


class QoeBridgeStep(BaseModel):
    step_id: str
    label: str
    amount: float
    running_total: float
    adjustment_id: str | None = None


class QoeBridgePeriod(BaseModel):
    period: str
    reported_ebitda: float
    adjustments_total: float
    adjusted_ebitda: float
    steps: list[QoeBridgeStep] = Field(default_factory=list)


class QoeWalkStep(BaseModel):
    step_id: str
    label: str
    amount: float
    running_total: float
    adjustment_id: str | None = None


class QoeSensitivityItem(BaseModel):
    sensitivity_id: str
    label: str
    amount: float
    direction: Literal["upside", "downside"]
    evidence_status: QoeEvidenceStatus = "pending"
    rationale: str | None = None


class QoeProFormaItem(BaseModel):
    pro_forma_id: str
    label: str
    amount: float
    evidence_status: QoeEvidenceStatus = "pending"
    rationale: str | None = None


class QoeCheckResult(BaseModel):
    check_id: str
    passed: bool
    message: str
    blocking: bool = True


class ModelCheckResult(BaseModel):
    """One automatic model-output check (G3 / P4)."""

    model_config = ConfigDict(protected_namespaces=())

    check_id: str
    passed: bool
    message: str
    blocking: bool = True
    model_id: str | None = None
    exhibit_id: str | None = None


class ModelCheckPack(BaseModel):
    """Check pack for one model exhibit."""

    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    exhibit_id: str
    section_id: str | None = None
    checks: list[ModelCheckResult] = Field(default_factory=list)
    checks_passed: bool = True
    held_back: bool = False
    held_back_reason: str | None = None


class ModelChecksDoc(BaseModel):
    """Persisted G3 model check packs for one FDD run."""

    run_id: str
    deal_slug: str
    updated_at: str
    version: str = "0.1.0"
    status: ArtefactStatus = ArtefactStatus.DRAFT
    packs: list[ModelCheckPack] = Field(default_factory=list)
    checks_passed: bool = False
    g3_passed: bool = False
    held_back_exhibits: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class QoeWorkbookDoc(BaseModel):
    """Persisted QoE workbook for one FDD run (Phase 5a / M4)."""

    run_id: str
    deal_slug: str
    updated_at: str
    version: str = "0.1.0"
    databook_release_id: str | None = None
    databook_release_version: int | None = None
    currency: str = "USD"
    scale: str = "m"
    period: str = "FY25A"
    status: ArtefactStatus = ArtefactStatus.DRAFT
    worked_example: bool = False
    baseline: list[QoeBaselinePeriod] = Field(default_factory=list)
    candidates: list[AdjustmentRow] = Field(default_factory=list)
    # Named register_rows (not ``register``) to avoid BaseModel attribute shadowing.
    register_rows: list[AdjustmentRow] = Field(default_factory=list)
    bridge: list[QoeBridgePeriod] = Field(default_factory=list)
    management_to_diligence_walk: list[QoeWalkStep] = Field(default_factory=list)
    sensitivities: list[QoeSensitivityItem] = Field(default_factory=list)
    pro_forma: list[QoeProFormaItem] = Field(default_factory=list)
    adjusted_ebitda_management: float | None = None
    adjusted_ebitda_diligence: float | None = None
    sensitivity_low: float | None = None
    sensitivity_high: float | None = None
    pro_forma_ebitda: float | None = None
    pro_forma_partly_evidenced_share: float | None = None
    materiality_m: float | None = None
    trivial_threshold: float | None = None
    checks: list[QoeCheckResult] = Field(default_factory=list)
    checks_passed: bool = False
    g4_ready: bool = False
    g4_blockers: list[str] = Field(default_factory=list)
    g4_approved: bool = False
    approval_id: str | None = None
    # Optional |fact value| ceilings for consumption checks (PDF B4).
    fact_ceilings: dict[str, float] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# Phase 6 — sentence tags (PDF §6 / P6).
CommentaryTag = Literal["F", "A", "M", "Q"]

# Fixed confidence vocabulary (AS-3 / PDF §6).
CONFIDENCE_ALLOWED: frozenset[str] = frozenset(
    {
        "confirms",
        "confirm",
        "indicates",
        "indicate",
        "management states",
        "supported",
        "verified",
        "provisional",
        "asserted",
        "evidenced",
        "consistent with",
    }
)

# Words/phrases that must never appear in FDD commentary.
INVEST_ADVICE_FORBIDDEN: frozenset[str] = frozenset(
    {
        "invest",
        "investment recommendation",
        "buy the company",
        "sell the company",
        "do not invest",
        "should invest",
        "must buy",
        "must sell",
        "outperform",
        "underperform",
        "price target",
    }
)

SUPERLATIVES_FORBIDDEN: frozenset[str] = frozenset(
    {
        "best-in-class",
        "world-class",
        "outstanding",
        "excellent",
        "unparalleled",
        "unprecedented",
        "guarantees",
        "certainly",
        "undoubtedly",
        "clearly proves",
    }
)


class CommentarySentence(BaseModel):
    """One tagged commentary sentence (F/A/M/Q)."""

    tag: CommentaryTag
    text: str  # may contain {{ex:…}} tokens
    citation: str | None = None  # exhibit / document / request id


class CommentaryLimitation(BaseModel):
    """Open item above materiality disclosed in the section."""

    item_id: str
    text: str
    above_materiality: bool = True


class CommentaryCheckResult(BaseModel):
    check_id: str
    passed: bool
    message: str
    blocking: bool = True
    severity: Literal["S1", "S2", "S3", "S4"] = "S1"


class SectionDraft(BaseModel):
    """Tagged commentary draft for one FDD section (Phase 6 / P6)."""

    section_id: str
    title: str
    diligence_question: str | None = None
    status: ArtefactStatus = ArtefactStatus.DRAFT
    held_back: bool = False
    held_back_reason: str | None = None
    action_title: str = ""  # ≤1 number token
    sentences: list[CommentarySentence] = Field(default_factory=list)
    body: str = ""  # joined tagged prose (may contain {{ex:…}} tokens)
    tags_used: list[str] = Field(default_factory=list)
    exhibit_ids: list[str] = Field(default_factory=list)
    cell_refs: list[str] = Field(default_factory=list)
    limitations: list[CommentaryLimitation] = Field(default_factory=list)
    checks: list[CommentaryCheckResult] = Field(default_factory=list)
    checks_passed: bool = False


class CommentaryDoc(BaseModel):
    """Persisted P6 commentary pack for one FDD run."""

    run_id: str
    deal_slug: str
    updated_at: str
    version: str = "0.1.0"
    status: ArtefactStatus = ArtefactStatus.DRAFT
    sections: list[SectionDraft] = Field(default_factory=list)
    held_back_sections: list[str] = Field(default_factory=list)
    checks_passed: bool = False
    typed_figure_faults: list[str] = Field(default_factory=list)
    unresolved_tokens: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


IssueSeverity = Literal["S1", "S2", "S3", "S4"]
IssueStatus = Literal["open", "resolved", "waived", "accepted"]
ChallengeStatus = Literal["open", "addressed", "accepted", "withdrawn"]


class Issue(BaseModel):
    """QA issue (Phase 8 / P8) — severity S1 blocker · S2 judgement · S3 disclose · S4 cosmetic."""

    issue_id: str
    check_id: str
    severity: IssueSeverity = "S3"
    message: str
    origin_stage: RunStage | None = None
    cell_ref: str | None = None  # exhibit_id.cell_id
    section_id: str | None = None
    status: IssueStatus = "open"
    blocking: bool = True
    created_at: str | None = None
    resolved_at: str | None = None
    resolved_by: str | None = None
    resolution_note: str | None = None


class QaCheckResult(BaseModel):
    """One catalogue check outcome from a QA scan."""

    check_id: str
    passed: bool
    message: str
    severity: IssueSeverity = "S1"
    blocking: bool = True
    origin_stage: RunStage | None = None
    issue_ids: list[str] = Field(default_factory=list)


class ChallengeItem(BaseModel):
    """Partner / reviewer challenge (Phase 8 / P9)."""

    challenge_id: str
    title: str
    detail: str | None = None
    raised_by: str | None = None
    raised_at: str | None = None
    status: ChallengeStatus = "open"
    linked_issue_ids: list[str] = Field(default_factory=list)
    response: str | None = None
    responded_at: str | None = None
    responded_by: str | None = None


class QaPackDoc(BaseModel):
    """Persisted P8–P9 QA pack: checks, issues, challenges, gate readiness."""

    run_id: str
    deal_slug: str
    updated_at: str
    version: str = "0.1.0"
    status: ArtefactStatus = ArtefactStatus.DRAFT
    checks: list[QaCheckResult] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    challenges: list[ChallengeItem] = Field(default_factory=list)
    open_s1_count: int = 0
    open_s2_count: int = 0
    g5_ready: bool = False
    g5_approved: bool = False
    g5_blockers: list[str] = Field(default_factory=list)
    g6_ready: bool = False
    g6_approved: bool = False
    g6_blockers: list[str] = Field(default_factory=list)
    snapshot_frozen: bool = False
    snapshot_id: str | None = None
    g7_verified: bool = False
    report_hash: str | None = None
    deck_hash: str | None = None
    figures_hash: str | None = None
    exhibit_hash: str | None = None
    commentary_hash: str | None = None
    qoe_hash: str | None = None
    notes: list[str] = Field(default_factory=list)


class SnapshotDoc(BaseModel):
    """Frozen release snapshot for G7 hash verify (P10)."""

    snapshot_id: str
    run_id: str
    deal_slug: str
    frozen_at: str
    frozen_by: str | None = None
    report_hash: str
    deck_hash: str
    figures_hash: str
    exhibit_hash: str
    commentary_hash: str | None = None
    qoe_hash: str | None = None
    manifest_hash: str | None = None
    status: ArtefactStatus = ArtefactStatus.APPROVED
    g7_verified: bool = False
    g7_verified_at: str | None = None
    g7_mismatch: list[str] = Field(default_factory=list)
    note: str | None = None


class Approval(BaseModel):
    """Versioned gate approval artefact."""

    approval_id: str
    gate: GateId
    run_id: str
    deal_slug: str | None = None
    status: ArtefactStatus = ArtefactStatus.DRAFT
    decided_at: str | None = None
    decided_by: str | None = None
    note: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class InputKey(str, Enum):
    """Seven FDD inputs (IN-1)."""

    DATABOOK = "databook"
    AGENTS = "agents"
    VDR = "vdr"
    MODELS = "models"
    MANAGEMENT_ANSWERS = "management_answers"
    ENGAGEMENT_BRIEF = "engagement_brief"
    HOUSE_TEMPLATE = "house_template"


class ReadinessInputItem(BaseModel):
    """One scanned input in the readiness inventory."""

    key: InputKey
    label: str
    required: bool = True
    present: bool = False
    tier: EvidenceTier | None = None  # A/B/C when present; None when missing
    tier_ok: bool = False  # True when present at C+
    detail: str | None = None
    path_hint: str | None = None
    blocking_sections: list[str] = Field(default_factory=list)


class RequestListItem(BaseModel):
    """Missing-doc / gap request from readiness (Phase 2) or claim gaps (Phase 4)."""

    request_id: str
    input_key: InputKey | None = None
    title: str
    detail: str | None = None
    owner: str | None = None
    figure_impact: str | None = None
    blocking_sections: list[str] = Field(default_factory=list)
    status: Literal["pending", "requested", "received", "waived"] = "pending"
    # Phase 4 — link back to the failed financial claim for rescan reconcile.
    claim_id: str | None = None
    metric_key: str | None = None
    fiscal_year: int | None = None
    suggested_filenames: list[str] = Field(default_factory=list)


class RequestListDoc(BaseModel):
    run_id: str
    deal_slug: str
    updated_at: str
    items: list[RequestListItem] = Field(default_factory=list)


class ClaimGap(BaseModel):
    """One failed financial claim that needs VDR / databook evidence (Phase 4)."""

    claim_id: str
    source_agent: str | None = None
    metric_key: str | None = None
    fiscal_year: int | None = None
    claimed_value: float | None = None
    databook_value: float | None = None
    test_result: Literal["contradicted", "unverifiable"]
    text: str = ""
    suggested_filenames: list[str] = Field(default_factory=list)
    request_id: str | None = None


class EvidencePassDoc(BaseModel):
    """Audit record for one P3 evidence retrieval pass (Phase 4)."""

    run_id: str
    deal_slug: str
    updated_at: str
    version: str = "0.1.0"
    mode: Literal["rescan", "reread", "deep", "rebridge"] = "rescan"
    dry_run: bool = False
    filenames: list[str] = Field(default_factory=list)
    gaps_before: list[ClaimGap] = Field(default_factory=list)
    gaps_after: list[ClaimGap] = Field(default_factory=list)
    release_id_before: str | None = None
    release_id_after: str | None = None
    release_version_after: int | None = None
    requests_received: list[str] = Field(default_factory=list)
    claims_rebuilt: bool = False
    notes: list[str] = Field(default_factory=list)


class ReadinessReport(BaseModel):
    """G0 readiness report for one FDD run (Phase 2 / P1)."""

    run_id: str
    deal_slug: str
    updated_at: str
    threshold: float = G0_PASS_THRESHOLD
    required_total: int = 0
    required_present: int = 0
    score: float = 0.0  # required_present / required_total
    g0_passed: bool = False
    g0_blocked: bool = True
    inputs: list[ReadinessInputItem] = Field(default_factory=list)
    blocking_gaps: list[str] = Field(default_factory=list)
    blocking_sections: list[str] = Field(default_factory=list)
    request_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ReportSpecNode(BaseModel):
    """One block in the shared report_spec (drives report + deck)."""

    node_id: str
    kind: Literal["section", "exhibit", "slide", "message"] = "section"
    title: str
    body: str = ""  # tokens allowed
    exhibit_id: str | None = None
    cell_refs: list[str] = Field(default_factory=list)  # exhibit_id.cell_id
    slide_index: int | None = None


class ReportSpec(BaseModel):
    """Single specification for report + deck (R5 / AS-5)."""

    spec_id: str
    run_id: str
    deal_slug: str
    updated_at: str
    title: str = "FDD Report"
    nodes: list[ReportSpecNode] = Field(default_factory=list)
    content_hash: str | None = None


class DependencyEdge(BaseModel):
    from_id: str
    to_id: str
    kind: Literal["cell_to_exhibit", "exhibit_to_section", "section_to_gate", "cell_to_spec"] = (
        "cell_to_spec"
    )


class DependencyGraph(BaseModel):
    """cell → exhibits → sections → gates."""

    run_id: str
    nodes: list[str] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)


class ResolvedToken(BaseModel):
    raw: str
    exhibit_id: str
    cell_id: str
    value: float | None = None
    display: str
    fact_id: str | None = None
    status: CellStatus | None = None


class TokenResolveResult(BaseModel):
    text: str
    bindings: list[ResolvedToken] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)


class StubRenderPage(BaseModel):
    """One PDF page or PPTX slide from the shared report_spec."""

    title: str
    body: str = ""
    kind: Literal["cover", "section", "slide", "message"] = "section"
    exhibit_id: str | None = None


class StubRenderResult(BaseModel):
    """Phase 0 dual-render stub output (shared figures from one spec)."""

    kind: Literal["report", "deck"]
    run_id: str
    figures: dict[str, float | None] = Field(default_factory=dict)
    displays: dict[str, str] = Field(default_factory=dict)
    body: str = ""
    pages: list[StubRenderPage] = Field(default_factory=list)
    content_hash: str | None = None
