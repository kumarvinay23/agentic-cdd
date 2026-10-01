"""Pydantic schemas for deal API payloads."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_serializer


class DealOut(BaseModel):
    """Wire format compatible with DiligenceIQ deal cards (id/uuid/_id + createdAt)."""

    id: str
    slug: str
    name: str
    company: str
    description: str = ""
    sector: str = "generic"
    cdd_metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    team: list[Any] = Field(default_factory=list)
    status: str = "not-started"
    vdr: dict[str, Any] = Field(default_factory=lambda: {"docs": []})
    docs_count: int = 0
    agents_running: int = 0
    reports_ready: int = 0
    created_at: str | None = None
    summary: str = ""
    team_label: str = "No team assigned"

    @model_serializer(mode="wrap")
    def serialize_compat(self, serializer):
        data = serializer(self)
        data.pop("cdd_metadata", None)
        data["metadata"] = self.cdd_metadata
        data["uuid"] = self.id
        data["_id"] = self.id
        data["createdAt"] = self.created_at
        return data
