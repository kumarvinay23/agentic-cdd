"""Slice 4 — smart cascade re-run for Phase 4 Final Verdict (left → right only).

When a Final Verdict agent is re-run, downstream consumers in the DAG blast
radius are re-queued; upstream producers are **not** re-run — their last
outputs are hydrated from disk / the Verdict Store.
"""

from __future__ import annotations

import json
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_pipeline import outputs_dir, read_agent_output_file
from agetic_cdd_api.verdict_roles import (
    all_verdict_slugs,
    cascade_blast_radius,
    role_by_slug,
    topo_order,
)
from agetic_cdd_api.verdict_store import load_verdict_store

# Only successful upstream artifacts may hydrate downstream extractors.
_VALID_UPSTREAM_STATUSES = frozenset({"completed", "empty_vdr"})


def _cascade_run_set(seeds: list[str]) -> set[str]:
    """Seeds + transitive downstream consumers (unsorted)."""
    known = set(all_verdict_slugs())
    seed_list = [s for s in dict.fromkeys(seeds) if s in known]
    if not seed_list:
        return set()

    to_run: set[str] = set(seed_list)
    for seed in seed_list:
        to_run.update(cascade_blast_radius(seed))
    return to_run


def cascade_run_order(seeds: list[str]) -> list[str]:
    """Return topo-ordered slugs to execute: seeds + transitive downstream consumers."""
    to_run = _cascade_run_set(seeds)
    if not to_run:
        return []
    return [slug for slug in topo_order(list(to_run)) if slug in to_run]


def _upstream_deps(slugs: set[str]) -> set[str]:
    deps: set[str] = set()
    for slug in slugs:
        role = role_by_slug(slug)
        if role is None:
            continue
        deps.update(role.depends_on)
    return deps


def _payload_schema_ok(payload: dict) -> bool:
    """Require a status plus at least one Phase 4 identity marker."""
    status = payload.get("status")
    if not isinstance(status, str) or not status.strip():
        return False
    return bool(
        payload.get("fv_code")
        or payload.get("agent_key")
        or payload.get("slug")
        or isinstance(payload.get("spec"), dict)
    )


def _should_overlay_manifest(existing: dict | None, incoming: dict) -> bool:
    """Prefer valid on-disk/hydration payloads; never clobber a valid entry with invalid disk."""
    if not _payload_schema_ok(incoming):
        return False
    if existing is None:
        return True
    incoming_ok = incoming.get("status") in _VALID_UPSTREAM_STATUSES
    existing_ok = existing.get("status") in _VALID_UPSTREAM_STATUSES
    if incoming_ok:
        return True
    return not existing_ok


def build_output_manifest(deal: Deal) -> dict[str, dict]:
    """Load persisted agent outputs once for cascade planning.

    Verdict Store is the baseline. Individual disk / hydration payloads overlay
    only when they pass schema checks and do not replace a valid store entry
    with an invalid/partial disk artifact.
    """
    manifest: dict[str, dict] = {}

    store = load_verdict_store(deal)
    agents = (store or {}).get("agents") if isinstance(store, dict) else {}
    if isinstance(agents, dict):
        for slug, entry in agents.items():
            if isinstance(entry, dict) and _payload_schema_ok(entry):
                manifest[slug] = entry

    for slug in all_verdict_slugs():
        stored = read_agent_output_file(deal, agent_key=slug)
        if isinstance(stored, dict) and _should_overlay_manifest(manifest.get(slug), stored):
            manifest[slug] = stored

    root = outputs_dir(deal)
    if root.is_dir():
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if not isinstance(payload, dict):
                continue
            # Only trust schema-valid disk files; require a usable status when
            # overriding an existing store entry.
            if not _should_overlay_manifest(manifest.get(path.stem), payload):
                continue
            if (
                path.stem in manifest
                and payload.get("status") not in _VALID_UPSTREAM_STATUSES
                and manifest[path.stem].get("status") in _VALID_UPSTREAM_STATUSES
            ):
                continue
            manifest[path.stem] = payload

    return manifest


def _output_available(manifest: dict[str, dict], slug: str) -> bool:
    payload = manifest.get(slug)
    if not payload:
        return False
    return payload.get("status") in _VALID_UPSTREAM_STATUSES


def _get_all_missing_upstream(
    nodes: set[str],
    manifest: dict[str, dict],
) -> set[str]:
    """Recursively discover upstream slugs without valid completed artifacts."""
    missing: set[str] = set()
    stack = list(_upstream_deps(nodes) - nodes)
    visited: set[str] = set()

    while stack:
        curr = stack.pop()
        if curr in visited or curr in nodes:
            continue
        visited.add(curr)

        if _output_available(manifest, curr):
            continue

        missing.add(curr)
        for dep in _upstream_deps({curr}):
            if dep not in nodes and dep not in missing and dep not in visited:
                stack.append(dep)

    return missing


def plan_cascade_rerun(deal: Deal, seeds: list[str]) -> dict[str, Any]:
    """Build an execution plan for a smart cascade re-run."""
    known = set(all_verdict_slugs())
    triggers = [s for s in dict.fromkeys(seeds) if s in known]
    if not triggers:
        return {
            "trigger": [],
            "blast_radius": [],
            "missing_upstream": [],
            "agent_keys": [],
        }

    manifest = build_output_manifest(deal)
    core = _cascade_run_set(triggers)
    blast = sorted(core - set(triggers))

    missing_set = _get_all_missing_upstream(core, manifest)
    to_run = core | missing_set
    # Single topo sort after the final execution set is settled.
    agent_keys = [slug for slug in topo_order(list(to_run)) if slug in to_run]
    missing_upstream = [slug for slug in agent_keys if slug in missing_set]

    return {
        "trigger": triggers,
        "blast_radius": blast,
        "missing_upstream": missing_upstream,
        "agent_keys": agent_keys,
    }


def frozen_upstream_slugs(run_order: list[str]) -> set[str]:
    """Upstream slugs required by the plan but not re-executed in this run."""
    rerun = set(run_order)
    return _upstream_deps(rerun) - rerun
