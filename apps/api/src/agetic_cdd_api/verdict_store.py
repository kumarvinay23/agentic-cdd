"""Final Verdict Store — 7 decision-grade documents for Phase 5."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from agetic_cdd_api.deep_dive_findings import completeness_of as dd_completeness_of, load_deep_dive_findings
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_vdr import library_dir
from agetic_cdd_api.verdict_roles import STAGE_LABELS, STAGE_ORDER, VERDICT_ROLES, all_verdict_slugs

STORE_FILENAME = "verdict_store.json"
REQUIRED_KEYS = (
    "deal_id",
    "generated_at",
    "stages",
    "agents",
    "completeness",
)
VALID_AGENT_STATUSES = frozenset({"completed", "empty_vdr", "failed", "missing"})
AGENT_ENTRY_KEYS = ("status", "slug", "fv_code", "stage", "name")


def store_path(deal: Deal) -> Path:
    return library_dir(deal) / STORE_FILENAME


def _atomic_write_json(path: Path, store: dict) -> None:
    """Publish JSON via same-directory tempfile + replace (POSIX atomic rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(store, handle, indent=2)
            handle.flush()
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _missing_agent_payload(role) -> dict[str, Any]:
    return {
        "status": "missing",
        "summary": f"{role.name} not run",
        "findings": [],
        "sources": [],
        "spec": {"empty": True, "document": role.spec_output},
        "empty_vdr": False,
    }


def _normalize_agent_payload(role, payload: dict | None) -> dict[str, Any]:
    """Coerce agent output into predictable store field types."""
    base = _missing_agent_payload(role)
    if not isinstance(payload, dict):
        return base
    spec = payload.get("spec")
    if not isinstance(spec, dict):
        spec = {"empty": True, "document": role.spec_output}
    status_value = str(payload.get("status") or base["status"])
    return {
        "status": status_value,
        "summary": payload.get("summary") if payload.get("summary") is not None else base["summary"],
        "findings": list(payload.get("findings") or []),
        "sources": list(payload.get("sources") or []),
        "spec": spec,
        "empty_vdr": bool(payload.get("empty_vdr") or status_value == "empty_vdr"),
    }


def load_verdict_store(deal: Deal) -> dict | None:
    path = store_path(deal)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    if validate_verdict_store(payload):
        return None
    return payload


def write_verdict_store(deal: Deal, store: dict) -> Path:
    errors = validate_verdict_store(store)
    if errors:
        raise ValueError(f"verdict store contract violation: {'; '.join(errors)}")
    path = store_path(deal)
    _atomic_write_json(path, store)
    return path


def completeness_of(
    store: dict | None = None,
    *,
    agents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute completeness from an agents map (or store['agents'])."""
    structurally_valid = True
    if agents is None:
        if not isinstance(store, dict):
            agents = {}
            structurally_valid = False
        elif "agents" not in store:
            agents = {}
            structurally_valid = False
        elif not isinstance(store.get("agents"), dict):
            agents = {}
            structurally_valid = False
        else:
            agents = store["agents"]

    required = all_verdict_slugs()
    present: list[str] = []
    missing: list[str] = []
    failed: list[str] = []
    empty_vdr: list[str] = []
    for slug in required:
        entry = agents.get(slug)
        if not isinstance(entry, dict):
            missing.append(slug)
            continue
        status_value = str(entry.get("status") or "")
        if status_value == "failed":
            failed.append(slug)
            continue
        if status_value == "empty_vdr":
            empty_vdr.append(slug)
            present.append(slug)
            continue
        if status_value != "completed":
            missing.append(slug)
            continue
        present.append(slug)

    stage_ready: dict[str, bool] = {}
    for letter in STAGE_ORDER:
        stage_slugs = [role.slug for role in VERDICT_ROLES if role.stage == letter]
        stage_ready[letter] = all(
            isinstance(agents.get(s), dict)
            and agents[s].get("status") in {"completed", "empty_vdr"}
            for s in stage_slugs
        )

    return {
        "required_agents": required,
        "present_agents": present,
        "missing_agents": missing,
        "failed_agents": failed,
        "empty_vdr_agents": empty_vdr,
        "complete": len(present) == len(required) and not failed and not missing,
        "stage_ready": stage_ready,
        "structurally_valid": structurally_valid,
    }


def validate_verdict_store(store: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(store, dict):
        return ["store is not an object"]

    for key in REQUIRED_KEYS:
        if key not in store:
            errors.append(f"missing key {key}")

    stages = store.get("stages")
    if stages is not None and not isinstance(stages, dict):
        errors.append("stages must be an object")
    elif isinstance(stages, dict):
        for letter in STAGE_ORDER:
            if letter not in stages:
                errors.append(f"stages missing bucket '{letter}'")

    agents = store.get("agents")
    if not isinstance(agents, dict):
        errors.append("agents missing or invalid")
        return errors

    known = set(all_verdict_slugs())
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
        status_value = str(entry.get("status") or "")
        if status_value and status_value not in VALID_AGENT_STATUSES:
            errors.append(f"agent '{slug}' has invalid status '{status_value}'")
        if not isinstance(entry.get("findings"), list):
            errors.append(f"agent '{slug}' findings must be a list")
        if not isinstance(entry.get("sources"), list):
            errors.append(f"agent '{slug}' sources must be a list")
        if not isinstance(entry.get("spec"), dict):
            errors.append(f"agent '{slug}' spec must be an object")

    for slug in agents:
        if slug not in known:
            errors.append(f"agents has unknown slug '{slug}'")

    return errors


def build_verdict_store(
    *,
    deal: Deal,
    generated_at: str,
    agent_outputs: dict[str, dict],
) -> dict[str, Any]:
    agents: dict[str, Any] = {}
    stages: dict[str, Any] = {
        letter: {
            "label": STAGE_LABELS[letter],
            "agent_slugs": [],
        }
        for letter in STAGE_ORDER
    }
    for role in VERDICT_ROLES:
        payload = _normalize_agent_payload(role, agent_outputs.get(role.slug))
        entry = {
            "status": payload["status"],
            "slug": role.slug,
            "fv_code": role.code,
            "stage": role.stage,
            "name": role.name,
            "spec_output": role.spec_output,
            "depends_on": list(role.depends_on),
            "foundation_deps": list(role.foundation_deps),
            "deep_dive_deps": list(role.deep_dive_deps),
            "vdr_ref": role.vdr_ref,
            "summary": payload["summary"],
            "findings": payload["findings"],
            "sources": payload["sources"],
            "spec": payload["spec"],
            "empty_vdr": payload["empty_vdr"],
        }
        agents[role.slug] = entry
        stages[role.stage]["agent_slugs"].append(role.slug)

    store = {
        "deal_id": deal.id,
        "deal_name": deal.name,
        "company": deal.company or deal.name,
        "generated_at": generated_at,
        "stages": stages,
        "agents": agents,
        "completeness": completeness_of(agents=agents),
    }
    errors = validate_verdict_store(store)
    if errors:
        raise ValueError(f"built verdict store failed validation: {'; '.join(errors)}")
    return store


def assert_verdict_context(deal: Deal) -> dict:
    """Raise 409 unless Deep Dive Findings Store is complete and critical-path ready."""
    store = load_deep_dive_findings(deal)
    if not store:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "deep_dive_findings_missing",
                "message": "Final Verdict requires a Deep Dive Findings Store. Re-run Deep Dive.",
                "completeness": None,
            },
        )
    completeness = dd_completeness_of(store)
    if completeness.get("complete") and completeness.get("critical_path_ready"):
        return store
    missing = (
        list(completeness.get("missing_agents") or [])
        + list(completeness.get("failed_agents") or [])
    )
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "error": "deep_dive_findings_incomplete",
            "message": (
                "Final Verdict requires a complete Deep Dive Findings Store "
                "with critical path ready. Re-run Deep Dive."
            ),
            "missing_agents": missing,
            "completeness": completeness,
        },
    )
