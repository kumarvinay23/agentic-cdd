"""Databook domain models (file-backed store)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


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


class DealDatabookParams(BaseModel):
    currency: str = "INR"
    scale: str = "Cr"  # display scale hint; values stored as extracted
    fy_convention: str = "calendar"  # calendar | ending_march
    block_tie_rel_tol: float = 0.005
    series_magnitude_ratio: float = 100.0
    llm_map_enabled: bool = False


class ExtractedRow(BaseModel):
    row_id: str
    doc_id: str
    source_name: str
    caption: str
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


class DatabookMeta(BaseModel):
    version: int = 1
    last_rescan_at: str | None = None
    last_deep_at: str | None = None
    params: DealDatabookParams = Field(default_factory=DealDatabookParams)
    row_count: int = 0
    promoted_count: int = 0
    held_out_count: int = 0
    issue_count: int = 0


class DatabookSummary(BaseModel):
    deal_id: str
    meta: DatabookMeta
    flags: dict[str, int] = Field(default_factory=dict)
    promoted_preview: list[PromotedMetric] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)


DEFAULT_CONFLICT_RULE = (
    "most documents stating it, then that source's coverage of this metric, "
    "then how much of the fact base the source supplies, then how plainly the caption "
    "names the metric, then the most central value"
)

SERIES_DROP_REASON = (
    "value is orders of magnitude below the series centre - a ratio, not the amount"
)
