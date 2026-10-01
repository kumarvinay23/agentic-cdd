"""Deal / portfolio helpers and API serialization."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal, PipelineAgentRun
from agetic_cdd_api.schemas_deals import DealOut
from agetic_cdd_api.security import new_id
from agetic_cdd_api.settings import settings

SECTORS = [
    {"id": "generic", "label": "Other / Generic"},
    {"id": "saas", "label": "Software / SaaS"},
    {"id": "healthcare", "label": "Healthcare & Life Sciences"},
    {"id": "payments", "label": "Payments & Fintech"},
    {"id": "ev", "label": "Electric Vehicles (EV)"},
    {"id": "manufacturing", "label": "Industrials & Manufacturing"},
    {"id": "energy", "label": "Energy & Power"},
    {"id": "waste_organics", "label": "Organics & Composting"},
    {"id": "logistics", "label": "Logistics & Freight"},
    {"id": "consumer", "label": "Consumer & Retail"},
    {"id": "finserv", "label": "Financial Services"},
    {"id": "bizservices", "label": "Business Services"},
]

_SECTOR_BY_LABEL = {s["label"].lower(): s["id"] for s in SECTORS}
_SECTOR_BY_ID = {s["id"]: s for s in SECTORS}
_MAX_SLUG_ATTEMPTS = 12


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "deal"


def resolve_sector(industry_or_sector: str) -> str:
    raw = (industry_or_sector or "generic").strip()
    if raw.lower() in _SECTOR_BY_ID:
        return raw.lower()
    return _SECTOR_BY_LABEL.get(raw.lower(), "generic")


def sector_label(sector_id: str) -> str:
    """Human-readable label for a sector id (falls back to title-cased id)."""
    sid = resolve_sector(sector_id)
    meta = _SECTOR_BY_ID.get(sid)
    if meta:
        return str(meta["label"])
    return (sector_id or "generic").replace("_", " ").title()


def deals_root() -> Path:
    """Filesystem root for deal workspaces (independent of DB URL)."""
    root = Path(settings.deals_storage_path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def ensure_deal_folder(slug: str) -> Path:
    path = deals_root() / slug
    (path / "documents").mkdir(parents=True, exist_ok=True)
    (path / "reports").mkdir(parents=True, exist_ok=True)
    return path


def remove_deal_folder_if_unclaimed(db: Session, *, org_id: str, slug: str) -> None:
    """Drop an on-disk workspace only if no deal row claims the slug (orphan from failed create)."""
    claimed = db.scalar(
        select(Deal.id).where(Deal.organization_id == org_id, Deal.slug == slug)
    )
    if claimed:
        return
    path = deals_root() / slug
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)


def next_slug_candidate(db: Session, *, org_id: str, base: str) -> str:
    """Best-effort free slug; UniqueConstraint is the source of truth under concurrency."""
    slug = slugify(base)
    candidate = slug
    n = 1
    while db.scalar(
        select(Deal.id).where(Deal.organization_id == org_id, Deal.slug == candidate)
    ):
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


def _loads_list(raw: str | None) -> list[Any]:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


def deal_to_dict(deal: Deal) -> dict:
    tags = _loads_list(deal.tags_json)
    docs = _loads_list(deal.vdr_docs_json)
    description = deal.description or ""
    created = deal.created_at.isoformat().replace("+00:00", "") if deal.created_at else None
    summary = (
        f"Data ingestion - {deal.docs_count} documents uploaded, awaiting action."
        if deal.docs_count
        else (description.strip() or "No documents uploaded yet.")
    )
    return DealOut(
        id=deal.id,
        slug=deal.slug,
        name=deal.name,
        company=deal.company or deal.name,
        description=description,
        sector=deal.sector,
        cdd_metadata={"cdd_sector": deal.sector},
        tags=tags,
        team=[],
        status=deal.status,
        vdr={"docs": docs},
        docs_count=deal.docs_count,
        agents_running=deal.agents_running,
        reports_ready=deal.reports_ready,
        created_at=created,
        summary=summary,
        team_label="No team assigned",
    ).model_dump()


def list_deals(
    db: Session,
    *,
    org_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    rows = db.scalars(
        select(Deal)
        .where(Deal.organization_id == org_id)
        .order_by(Deal.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [deal_to_dict(d) for d in rows]


def get_deal(db: Session, *, org_id: str, deal_id: str) -> Deal:
    deal = db.scalar(
        select(Deal).where(Deal.organization_id == org_id, Deal.id == deal_id)
    )
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return deal


def get_deal_by_slug(db: Session, *, org_id: str, slug: str) -> Deal:
    deal = db.scalar(
        select(Deal).where(Deal.organization_id == org_id, Deal.slug == slug)
    )
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return deal


def create_deal(
    db: Session,
    *,
    org_id: str,
    name: str,
    slug: str | None,
    description: str,
    tags: list[str],
    sector: str,
    company: str | None = None,
) -> dict:
    name = name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name is required")

    base = slug or name
    tags_json = json.dumps([t.strip() for t in tags if t.strip()])
    sector_id = resolve_sector(sector)
    company_name = (company or name).strip() or name
    description_text = (description or "").strip()

    last_error: Exception | None = None
    for attempt in range(_MAX_SLUG_ATTEMPTS):
        final_slug = (
            next_slug_candidate(db, org_id=org_id, base=base)
            if attempt == 0
            else next_slug_candidate(db, org_id=org_id, base=f"{slugify(base)}-{attempt + 1}")
        )
        try:
            # Create workspace on disk before commit so a failed FS op never leaves an orphan DB row.
            ensure_deal_folder(final_slug)
            deal = Deal(
                id=new_id(),
                organization_id=org_id,
                name=name,
                slug=final_slug,
                company=company_name,
                description=description_text,
                sector=sector_id,
                status="not-started",
                tags_json=tags_json,
                vdr_docs_json="[]",
                docs_count=0,
                agents_running=0,
                reports_ready=0,
                vdr_bytes=0,
            )
            db.add(deal)
            db.commit()
            db.refresh(deal)
            return deal_to_dict(deal)
        except IntegrityError as exc:
            db.rollback()
            remove_deal_folder_if_unclaimed(db, org_id=org_id, slug=final_slug)
            last_error = exc
            continue
        except OSError as exc:
            db.rollback()
            remove_deal_folder_if_unclaimed(db, org_id=org_id, slug=final_slug)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Could not create deal workspace on disk: {exc}",
            ) from exc

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a unique deal slug. Please try a different name.",
    ) from last_error


def usage_for_org(db: Session, *, org_id: str) -> dict:
    completed_runs_subq = (
        select(func.count(PipelineAgentRun.id))
        .join(Deal, Deal.id == PipelineAgentRun.deal_id)
        .where(Deal.organization_id == org_id, PipelineAgentRun.status == "completed")
        .scalar_subquery()
    )
    stmt = select(
        func.coalesce(func.sum(Deal.docs_count), 0),
        func.coalesce(func.sum(Deal.vdr_bytes), 0),
        func.coalesce(func.sum(Deal.agents_running), 0),
        completed_runs_subq,
    ).where(Deal.organization_id == org_id)
    vdr_files, vdr_bytes, agents_running, completed_runs = db.execute(stmt).one()
    return {
        "agent_runs": float(completed_runs or 0),
        "agents_running_now": int(agents_running or 0),
        "vdr_files": int(vdr_files or 0),
        "vdr_bytes": int(vdr_bytes or 0),
    }


def portfolio_metrics(db: Session, *, org_id: str) -> dict:
    stmt = select(
        func.count(Deal.id),
        func.coalesce(
            func.sum(case((Deal.status == "active", 1), else_=0)),
            0,
        ),
        func.coalesce(func.sum(Deal.agents_running), 0),
        func.coalesce(func.sum(Deal.reports_ready), 0),
    ).where(Deal.organization_id == org_id)
    total, active, agents_running, reports_ready = db.execute(stmt).one()
    return {
        "active_deals": int(active or 0),
        "agents_running_now": int(agents_running or 0),
        "reports_ready": int(reports_ready or 0),
        "total_deals": int(total or 0),
    }
