"""Persisted deal portfolio store with on-disk deal folders."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
STORE_PATH = DATA_DIR / "portfolio.json"
DEALS_DIR = DATA_DIR / "deals"

INDUSTRIES = [
    "Other / Generic",
    "Technology",
    "Healthcare",
    "Financial Services",
    "Industrial",
    "Consumer",
    "Energy",
    "Real Estate",
]

SEED_DEALS: list[dict[str, Any]] = [
    {
        "name": "Test1",
        "slug": "test1",
        "status": "NOT-STARTED",
        "summary": "Data ingestion - 34 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Other / Generic",
    },
    {
        "name": "Kaapi Machines India",
        "slug": "kaapi-machines-india",
        "status": "ACTIVE",
        "summary": "Data ingestion - 1 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Industrial",
    },
    {
        "name": "Finbox",
        "slug": "finbox",
        "status": "ACTIVE",
        "summary": "Data ingestion - 6 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Financial Services",
    },
    {
        "name": "Abc Electric Latest",
        "slug": "abc-electric-latest",
        "status": "NOT-STARTED",
        "summary": "Data ingestion - 8 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Energy",
    },
    {
        "name": "Merlin Cim",
        "slug": "merlin-cim",
        "status": "NOT-STARTED",
        "summary": "Data ingestion - 18 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Other / Generic",
    },
    {
        "name": "Ola Electric Synthetic Fdd",
        "slug": "ola-electric-synthetic-fdd",
        "status": "NOT-STARTED",
        "summary": "Data ingestion - 5 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Energy",
    },
    {
        "name": "American Casino",
        "slug": "american-casino",
        "status": "ACTIVE",
        "summary": "Data ingestion - 5 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Consumer",
    },
    {
        "name": "Ola Electric",
        "slug": "ola-electric",
        "status": "ACTIVE",
        "summary": "Data ingestion - 5 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Energy",
    },
    {
        "name": "Ather Energy",
        "slug": "ather-energy",
        "status": "ACTIVE",
        "summary": "Data ingestion - 5 documents uploaded, awaiting action.",
        "team": "No team assigned",
        "description": "",
        "tags": [],
        "industry": "Energy",
    },
]


def slugify(value: str) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug or "portfolio"


def _default_store() -> dict[str, Any]:
    return {
        "brand": "Agentic CDD",
        "user_initials": "AT",
        "usage": {
            "agent_runs": 352,
            "vdr_files": 118,
            "uploaded": "55.6 MB",
        },
        "deals": [dict(deal) for deal in SEED_DEALS],
    }


def _ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEALS_DIR.mkdir(parents=True, exist_ok=True)
    if not STORE_PATH.exists():
        _write_store(_default_store())
        for deal in SEED_DEALS:
            _ensure_deal_folder(deal)


def _read_store() -> dict[str, Any]:
    _ensure_storage()
    with STORE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_store(store: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STORE_PATH.open("w", encoding="utf-8") as handle:
        json.dump(store, handle, indent=2)


def _ensure_deal_folder(deal: dict[str, Any]) -> Path:
    folder = DEALS_DIR / deal["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "documents").mkdir(exist_ok=True)
    (folder / "reports").mkdir(exist_ok=True)
    meta_path = folder / "deal.json"
    with meta_path.open("w", encoding="utf-8") as handle:
        json.dump(deal, handle, indent=2)
    return folder


def _compute_metrics(deals: list[dict[str, Any]]) -> dict[str, int]:
    active = sum(1 for deal in deals if deal.get("status") == "ACTIVE")
    reports_ready = sum(
        1
        for deal in deals
        if any((DEALS_DIR / deal["slug"] / "reports").glob("*"))
    )
    return {
        "active_deals": active,
        "agents_running_now": 0,
        "reports_ready": reports_ready,
    }


def portfolio_payload() -> dict[str, Any]:
    store = _read_store()
    deals = store.get("deals", [])
    return {
        "brand": store.get("brand", "Agentic CDD"),
        "user_initials": store.get("user_initials", "AT"),
        "usage": store.get(
            "usage",
            {"agent_runs": 0, "vdr_files": 0, "uploaded": "0 MB"},
        ),
        "metrics": _compute_metrics(deals),
        "deals": deals,
        "industries": INDUSTRIES,
    }


def create_deal(
    *,
    name: str,
    slug: str | None = None,
    description: str = "",
    tags: list[str] | None = None,
    industry: str = "Other / Generic",
) -> dict[str, Any]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise ValueError("Portfolio name is required")

    cleaned_slug = slugify(slug or cleaned_name)
    if not cleaned_slug:
        raise ValueError("Slug is required")

    store = _read_store()
    deals = store.setdefault("deals", [])
    if any(deal.get("slug") == cleaned_slug for deal in deals):
        raise ValueError(f"A deal with slug '{cleaned_slug}' already exists")

    tag_list = [tag.strip() for tag in (tags or []) if tag.strip()]
    summary = description.strip() or "Data ingestion - 0 documents uploaded, awaiting action."
    if len(summary) > 120:
        summary = summary[:117].rstrip() + "..."

    deal = {
        "name": cleaned_name,
        "slug": cleaned_slug,
        "status": "NOT-STARTED",
        "summary": summary,
        "team": "No team assigned",
        "description": description.strip(),
        "tags": tag_list,
        "industry": industry if industry in INDUSTRIES else "Other / Generic",
    }

    folder = _ensure_deal_folder(deal)
    deals.insert(0, deal)
    _write_store(store)

    return {
        "deal": deal,
        "folder": str(folder.relative_to(PROJECT_ROOT)),
        "portfolio": portfolio_payload(),
    }
