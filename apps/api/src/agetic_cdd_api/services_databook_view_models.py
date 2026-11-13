"""Read-model contracts for ontology-backed Databook `/view` and `/lines`.

Wire shapes match the DiligenceIQ derived-data freeze. No company-specific fields.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


DqKind = Literal["assumed", "conflict", "untyped"]


class DatabookDqIssue(BaseModel):
    n: int
    kind: DqKind
    label: str
    detail: str = ""


class DatabookSeriesCell(BaseModel):
    value: float | None = None
    currency: str = ""
    unit: str | None = None
    source: str = ""
    line_item: str = ""
    statement: str = ""
    raw: str = ""
    suspect: bool = False
    foreign: bool = False
    edited: Any = None
    original: Any = None
    fact_id: str | None = None


class DatabookFileEntry(BaseModel):
    file: str = ""
    path: str = ""
    doc_id: str | None = None
    status: str = ""
    status_reason: str | None = None
    doc_type: str | None = None
    evidence_tier: str | None = None
    extraction: dict[str, Any] = Field(default_factory=dict)
    empty: bool = False
    doc_facts: int = 0


class DatabookTotals(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    rows: int = 0
    mapped_rows: int = 0
    metrics: int = 0
    documents_parsed: int = 0
    candidates: int = 0
    building: int = 0
    checks_failed: int = 0
    suspect_rows: int = 0
    note_rows: int = 0
    model_rows: int = 0


class DatabookViewResponse(BaseModel):
    files: list[DatabookFileEntry] = Field(default_factory=list)
    series: dict[str, dict[str, DatabookSeriesCell]] = Field(default_factory=dict)
    model: dict[str, Any] | None = None
    totals: DatabookTotals = Field(default_factory=DatabookTotals)
    reporting_currency: str = ""
    actual_through: int | None = None
    dq_cells: dict[str, list[DatabookDqIssue]] = Field(default_factory=dict)
    status: Literal["ready", "building", "unpublished"] = "unpublished"
    source: Literal["ontology", "file"] = "ontology"


class DatabookLineRow(BaseModel):
    key: str
    statement: str = ""
    sheet: str = ""
    line_item: str = ""
    period: int
    value: float | None = None
    value_base: float | None = None
    printed: float | None = None
    printed_number: float | None = None
    printed_raw: str = ""
    scale: float = 1.0
    scale_declared: float = 1.0
    scale_source: str = ""
    scale_confidence: str = ""
    scale_applied: bool = False
    kind: str = "money"
    unit: str = ""
    currency: str = ""
    metric: str = ""
    subtotal: bool = False
    note: str = ""
    suspect: bool = False
    forecast: bool | None = None
    source: str = ""
    raw: str = ""
    token: str = ""
    block: str = ""
    dq: list[DatabookDqIssue] = Field(default_factory=list)
    fact_id: str | None = None


class DatabookLinesResponse(BaseModel):
    rows: list[DatabookLineRow] = Field(default_factory=list)
