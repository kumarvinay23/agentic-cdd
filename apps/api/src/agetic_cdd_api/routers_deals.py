"""Deal and usage routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.services_deals import (
    SECTORS,
    create_deal,
    deal_to_dict,
    get_deal,
    list_deals,
    portfolio_metrics,
    usage_for_org,
)

router = APIRouter(tags=["deals"])


class CreateDealBody(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str | None = Field(default=None, max_length=255, pattern=r"^[a-z0-9-]+$")
    description: str = ""
    tags: list[str] | str = Field(default_factory=list)
    industry: str | None = None
    sector: str | None = None
    company: str | None = Field(default=None, max_length=255)

    @field_validator("slug", mode="before")
    @classmethod
    def empty_slug_to_none(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value


def _normalize_tags(tags: list[str] | str) -> list[str]:
    if isinstance(tags, str):
        return [p.strip() for p in tags.split(",") if p.strip()]
    return [str(t).strip() for t in tags if str(t).strip()]


@router.get("/deals")
def deals_list(
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict:
    org_id = auth.organization.id
    # Metrics stay org-wide (SQL); the page is a bounded slice of deals.
    metrics = portfolio_metrics(db, org_id=org_id)
    deals = list_deals(db, org_id=org_id, limit=limit, offset=offset)
    return {
        "success": True,
        "data": deals,
        "metrics": metrics,
        "pagination": {"limit": limit, "offset": offset, "total": metrics["total_deals"]},
    }


@router.post("/deals", status_code=status.HTTP_201_CREATED)
def deals_create(
    body: CreateDealBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    sector = body.sector or body.industry or "generic"
    deal = create_deal(
        db,
        org_id=auth.organization.id,
        name=body.name,
        slug=body.slug,
        description=body.description,
        tags=_normalize_tags(body.tags),
        sector=sector,
        company=body.company,
    )
    return {"success": True, "data": deal}


@router.get("/deals/{deal_id}")
def deals_detail(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return {"success": True, "data": deal_to_dict(deal)}


@router.get("/me/usage")
def me_usage(
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    return {"success": True, "data": usage_for_org(db, org_id=auth.organization.id)}


@router.get("/portfolios/cdd/sectors")
def cdd_sectors(_auth: AuthContext = Depends(get_current_auth)) -> list[dict]:
    return [{"id": s["id"], "label": s["label"], "has_pack": False} for s in SECTORS]
