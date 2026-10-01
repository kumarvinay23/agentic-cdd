"""Deep Dive Findings Store — 24 analytical docs for Phase 4 / Phase 5."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agetic_cdd_api.deep_dive_roles import (
    DEEP_DIVE_ROLES,
    FINDINGS_DOC_BY_TRACK,
    TRACK_LABELS,
    all_deep_dive_slugs,
)
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_vdr import library_dir

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

FINDINGS_FILENAME = "deep_dive_findings.json"
REQUIRED_KEYS = (
    "deal_id",
    "generated_at",
    "tracks",
    "agents",
    "completeness",
    "critical_path",
)
# Customers/Ops → Financials gate for Phase 4. Single source of truth.
CRITICAL_PATH_SLUGS: tuple[str, ...] = (
    "buying_behavior",
    "operational_risk",
    "supply_chain_resilience",
    "historical_performance",
    "capital_structure",
)
VALID_AGENT_STATUSES = frozenset({"completed", "empty_vdr", "failed", "missing"})
AGENT_ENTRY_KEYS = ("status", "slug", "dd_code", "track", "name")


def findings_path(deal: Deal) -> Path:
    return library_dir(deal) / FINDINGS_FILENAME


def load_deep_dive_findings(deal: Deal, db: Session | None = None) -> dict | None:
    _ = db  # reserved for future DB-backed reads; disk store today
    path = findings_path(deal)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def write_deep_dive_findings(deal: Deal, store: dict) -> Path:
    path = findings_path(deal)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return path


def completeness_of(
    store: dict | None = None,
    *,
    agents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute completeness from an agents map (or store['agents'])."""
    if agents is None:
        raw = (store or {}).get("agents") if isinstance(store, dict) else None
        agents = raw if isinstance(raw, dict) else {}
    required = all_deep_dive_slugs()
    present: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    empty_vdr: list[str] = []
    for slug in required:
        entry = agents.get(slug)
        if not isinstance(entry, dict):
            missing.append(slug)
            continue
        status = str(entry.get("status") or "")
        if status == "failed":
            failed.append(slug)
            continue
        if status == "empty_vdr":
            empty_vdr.append(slug)
            present.append(slug)
            continue
        if status != "completed":
            missing.append(slug)
            continue
        present.append(slug)

    critical_ready = all(
        isinstance(agents.get(s), dict) and agents[s].get("status") in {"completed", "empty_vdr"}
        for s in CRITICAL_PATH_SLUGS
    )
    return {
        "required_agents": required,
        "present_agents": present,
        "missing_agents": missing,
        "failed_agents": failed,
        "empty_vdr_agents": empty_vdr,
        "complete": len(present) == len(required) and not failed and not missing,
        "critical_path_ready": critical_ready,
    }


def validate_findings_store(store: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(store, dict):
        return ["store is not an object"]

    for key in REQUIRED_KEYS:
        if key not in store:
            errors.append(f"missing key {key}")

    tracks = store.get("tracks")
    if tracks is not None and not isinstance(tracks, dict):
        errors.append("tracks must be an object")
    elif isinstance(tracks, dict):
        for letter in TRACK_LABELS:
            if letter not in tracks:
                errors.append(f"tracks missing bucket '{letter}'")

    critical = store.get("critical_path")
    if critical is not None:
        if not isinstance(critical, dict):
            errors.append("critical_path must be an object")
        else:
            slugs = critical.get("slugs")
            if not isinstance(slugs, list):
                errors.append("critical_path.slugs must be a list")
            elif list(slugs) != list(CRITICAL_PATH_SLUGS):
                errors.append("critical_path.slugs drift from CRITICAL_PATH_SLUGS")

    agents = store.get("agents")
    if not isinstance(agents, dict):
        errors.append("agents missing or invalid")
        return errors

    known = set(all_deep_dive_slugs())
    for slug in known:
        if slug not in agents:
            errors.append(f"agents missing required slug '{slug}'")
            continue
        entry = agents[slug]
        if not isinstance(entry, dict):
            errors.append(f"agent entry '{slug}' must be a dict")
            continue
        for key in AGENT_ENTRY_KEYS:
            if key not in entry:
                errors.append(f"agent '{slug}' missing field '{key}'")
        entry_slug = entry.get("slug")
        if entry_slug is not None and entry_slug != slug:
            errors.append(f"agent '{slug}' has mismatched slug field '{entry_slug}'")
        status = str(entry.get("status") or "")
        if status and status not in VALID_AGENT_STATUSES:
            errors.append(f"agent '{slug}' has invalid status '{status}'")

    for slug in agents:
        if slug not in known:
            errors.append(f"agents has unknown slug '{slug}'")

    return errors


def build_findings_store(
    *,
    deal: Deal,
    generated_at: str,
    agent_outputs: dict[str, dict],
) -> dict[str, Any]:
    agents: dict[str, Any] = {}
    tracks: dict[str, Any] = {
        letter: {
            "label": TRACK_LABELS[letter],
            "documents": list(FINDINGS_DOC_BY_TRACK.get(letter, ())),
            "agent_slugs": [],
        }
        for letter in TRACK_LABELS
    }
    for role in DEEP_DIVE_ROLES:
        payload = agent_outputs.get(role.slug) or {
            "status": "missing",
            "summary": f"{role.name} not run",
            "findings": [],
            "sources": [],
            "spec": {"empty": True, "document": role.spec_output},
        }
        entry = {
            "status": payload.get("status") or "missing",
            "slug": role.slug,
            "dd_code": role.code,
            "track": role.track,
            "name": role.name,
            "src": role.src,
            "depends_on": list(role.depends_on),
            "foundation_deps": list(role.foundation_deps),
            "spec_output": role.spec_output,
            "summary": payload.get("summary"),
            "findings": payload.get("findings") or [],
            "sources": payload.get("sources") or [],
            "spec": payload.get("spec"),
            "empty_vdr": bool(payload.get("empty_vdr") or payload.get("status") == "empty_vdr"),
        }
        agents[role.slug] = entry
        tracks[role.track]["agent_slugs"].append(role.slug)

    store = {
        "deal_id": deal.id,
        "deal_name": deal.name,
        "company": deal.company or deal.name,
        "generated_at": generated_at,
        "tracks": tracks,
        "agents": agents,
        "critical_path": {
            "slugs": list(CRITICAL_PATH_SLUGS),
            "note": "Financials consume Customers + Ops; then feed Phase 4",
        },
        "completeness": completeness_of(agents=agents),
    }
    return store
