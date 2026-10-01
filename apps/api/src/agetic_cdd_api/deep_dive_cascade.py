"""Slice 7 — smart cascade re-run for Phase 3 Deep Dive (left → right only).

When a Deep Dive agent is re-run, downstream consumers in the DAG blast radius
are re-queued; upstream producers are **not** re-run — their last outputs are
hydrated from disk / the Findings Store.
"""

from __future__ import annotations

import json
from typing import Any

from agetic_cdd_api.deep_dive_findings import load_deep_dive_findings
from agetic_cdd_api.deep_dive_roles import (
    all_deep_dive_slugs,
    cascade_blast_radius,
    role_by_slug,
    topo_order,
)
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_pipeline import outputs_dir, read_agent_output_file

# Only successful upstream artifacts may hydrate downstream extractors.
_VALID_UPSTREAM_STATUSES = frozenset({"completed", "empty_vdr"})


def cascade_run_order(seeds: list[str]) -> list[str]:
    """Return topo-ordered slugs to execute: seeds + transitive downstream consumers."""
    known = set(all_deep_dive_slugs())
    seed_list = [s for s in dict.fromkeys(seeds) if s in known]
    if not seed_list:
        return []

    to_run: set[str] = set(seed_list)
    for seed in seed_list:
        to_run.update(cascade_blast_radius(seed))

    ordered = topo_order(list(to_run))
    return [slug for slug in ordered if slug in to_run]


def _upstream_deps(slugs: set[str]) -> set[str]:
    deps: set[str] = set()
    for slug in slugs:
        role = role_by_slug(slug)
        if role is None:
            continue
        deps.update(role.depends_on)
    return deps


def build_output_manifest(deal: Deal) -> dict[str, dict]:
    """Load persisted agent outputs once for cascade planning (batch disk read)."""
    manifest: dict[str, dict] = {}
    root = outputs_dir(deal)
    if root.is_dir():
        for path in root.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(payload, dict):
                manifest[path.stem] = payload

    store = load_deep_dive_findings(deal)
    agents = (store or {}).get("agents") if isinstance(store, dict) else {}
    if isinstance(agents, dict):
        for slug, entry in agents.items():
            if slug not in manifest and isinstance(entry, dict):
                manifest[slug] = entry
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
            if dep not in nodes and dep not in missing:
                stack.append(dep)

    return missing


def plan_cascade_rerun(deal: Deal, seeds: list[str]) -> dict[str, Any]:
    """Build an execution plan for a smart cascade re-run."""
    known = set(all_deep_dive_slugs())
    triggers = [s for s in dict.fromkeys(seeds) if s in known]
    if not triggers:
        return {
            "trigger": [],
            "blast_radius": [],
            "missing_upstream": [],
            "agent_keys": [],
        }

    manifest = build_output_manifest(deal)
    core = set(cascade_run_order(triggers))
    blast = sorted(core - set(triggers))

    missing_set = _get_all_missing_upstream(core, manifest)
    to_run = core | missing_set
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
