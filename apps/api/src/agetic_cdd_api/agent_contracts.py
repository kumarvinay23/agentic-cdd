"""Agent contracts: run state, output schema, and downstream re-runs.

A run is published only after its output matches the contract. Summary agents
read validated findings. A corrected source file re-queues every agent that
used it, and every agent that depends on those agents.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1"
SUMMARY_AGENTS = frozenset({"swot_analysis", "ic_synthesis", "recommendation"})
_PROSE_KEYS = frozenset({"document", "summary", "markdown", "narrative", "body"})
_HELD = frozenset(
    {"needs_repair", "failed", "empty_vdr", "queued", "generated", "pending", "running"}
)
_PUBLISHED = frozenset({"completed", "published", "validated"})
_WORKFLOW_FROM_STATUS = {
    "pending": "queued",
    "queued": "queued",
    "running": "running",
    "generated": "generated",
    "validated": "validated",
    "completed": "published",
    "published": "published",
    "needs_repair": "needs_repair",
    "failed": "needs_repair",
}


def workflow_state_for(status: str, output: dict[str, Any] | None = None) -> str:
    if isinstance(output, dict) and output.get("workflow_state"):
        return str(output["workflow_state"])
    return _WORKFLOW_FROM_STATUS.get(status, "queued")


def _required_fields(agent_key: str) -> tuple[str, ...]:
    if agent_key in SUMMARY_AGENTS:
        return ("module_id", "findings")
    return ("module_id",)


def schema_gap(agent_key: str, output: dict[str, Any]) -> str | None:
    """Why this output fails its schema, or None when the contract matches."""
    version = str(output.get("schema_version") or SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        return f"output schema {version} is not {SCHEMA_VERSION}"
    for field in _required_fields(agent_key):
        if field not in output:
            return f"output schema missing {field}"
        value = output.get(field)
        if field == "findings" and not isinstance(value, list):
            return "output schema findings must be a list of findings"
        if field == "module_id" and not str(value or "").strip():
            return "output schema missing module_id"
    if output.get("used_agent_prose") is True:
        return "summary agent used another agent's prose"
    spec = output.get("spec")
    if isinstance(spec, dict) and spec.get("used_agent_prose") is True:
        return "summary agent used another agent's prose"
    return None


def apply_contract(agent_key: str, output: dict[str, Any]) -> dict[str, Any]:
    """Stamp workflow_state. A schema or prose fault is held as needs_repair."""
    if agent_key in SUMMARY_AGENTS and "findings" not in output:
        output["findings"] = []
    status = str(output.get("status") or "")
    if status in {"failed", "needs_repair"}:
        output["workflow_state"] = "needs_repair"
        return output
    gap = schema_gap(agent_key, output)
    if gap:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = gap
        return output
    from agetic_cdd_api.services_agent_result import ensure_agent_result

    contradiction = ensure_agent_result(agent_key, output)
    if contradiction:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = contradiction
        return output
    from agetic_cdd_api.services_claims import ensure_claims

    claim_gap = ensure_claims(agent_key, output)
    if claim_gap:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = claim_gap
        return output
    from agetic_cdd_api.services_verification import ensure_verification

    verification_gap = ensure_verification(agent_key, output)
    if verification_gap:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = verification_gap
        return output
    from agetic_cdd_api.services_findings import ensure_findings

    findings_gap = ensure_findings(output)
    if findings_gap:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = findings_gap
        return output
    from agetic_cdd_api.services_report_check import ensure_report_check

    report_gap = ensure_report_check(output)
    if report_gap:
        output["status"] = "needs_repair"
        output["workflow_state"] = "needs_repair"
        output["error"] = report_gap
        return output
    output["schema_version"] = SCHEMA_VERSION
    output["workflow_state"] = "published"
    output["status"] = "completed"
    return output


def as_validated_findings(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    """A finding a summary agent may read. Prose and unvalidated runs are omitted."""
    if not isinstance(payload, dict):
        return None
    state = str(payload.get("workflow_state") or "")
    status = str(payload.get("status") or "")
    if state in {"needs_repair", "queued", "generated", "running"}:
        return None
    if status in _HELD:
        return None
    if state not in {"published", "validated"} and status not in _PUBLISHED:
        if not (payload.get("spec") or payload.get("findings")):
            return None
    kept = {key: value for key, value in payload.items() if key not in _PROSE_KEYS}
    return kept or None


def _summary_edges() -> dict[str, tuple[str, ...]]:
    from agetic_cdd_api.agent_document_ic_synthesis import _UPSTREAM_SLUGS as ic_slugs
    from agetic_cdd_api.agent_document_recommendation import _UPSTREAM_SLUGS as rec_slugs
    from agetic_cdd_api.agent_document_swot_analysis import _UPSTREAM_SLUGS as swot_slugs

    return {
        "swot_analysis": tuple(swot_slugs),
        "ic_synthesis": tuple(ic_slugs),
        "recommendation": tuple(rec_slugs),
    }


def _dependency_edges() -> dict[str, tuple[str, ...]]:
    from agetic_cdd_api.deep_dive_roles import depends_on_map
    from agetic_cdd_api.verdict_roles import depends_on_map as verdict_deps

    edges: dict[str, tuple[str, ...]] = {
        key: tuple(deps) for key, deps in depends_on_map().items()
    }
    for key, deps in verdict_deps().items():
        edges[key] = tuple(dict.fromkeys([*edges.get(key, ()), *deps]))
    for key, deps in _summary_edges().items():
        edges[key] = tuple(dict.fromkeys([*edges.get(key, ()), *deps]))
    return edges


def _expand(seeds: set[str]) -> set[str]:
    edges = _dependency_edges()
    affected = set(seeds)
    changed = True
    while changed:
        changed = False
        for agent, upstream in edges.items():
            if agent in affected:
                continue
            if any(item in affected for item in upstream):
                affected.add(agent)
                changed = True
    return affected


def _agents_citing(slug: str, label: str, *, root: Path | None) -> set[str]:
    from agetic_cdd_api.services_step_log import load_steps, trace_to_source

    keys: set[str] = set()
    for step in load_steps(slug, root=root):
        agent_key = str(step.get("agent_key") or "")
        if not agent_key or step.get("kind") not in {"agent", "findings"}:
            continue
        chain = trace_to_source(slug, step_id=str(step["id"]), root=root)
        if any(item.get("kind") == "source" and item.get("label") == label for item in chain):
            keys.add(agent_key)
    return keys


def agents_affected_by(slug: str, source_label: str, *, root: Path | None = None) -> list[str]:
    """Agents that cited this file, plus every agent that depends on them."""
    label = Path(str(source_label or "").strip()).name
    if not slug or not label:
        return []
    cited = _agents_citing(slug, label, root=root)
    if not cited:
        return []
    return sorted(_expand(cited))


def queue_downstream(db: Any, deal: Any, source_label: str, *, root: Path | None = None) -> list[str]:
    """Hold published output for every agent downstream of a corrected fact."""
    from agetic_cdd_api.services_pipeline import (
        read_agent_output_file,
        upsert_run,
        write_agent_output,
    )

    slug = str(getattr(deal, "slug", None) or "")
    affected = agents_affected_by(slug, source_label, root=root)
    reason = f"queued: {Path(str(source_label).strip()).name} changed"
    for agent_key in affected:
        current = read_agent_output_file(deal, agent_key=agent_key) or {}
        if not isinstance(current, dict):
            current = {}
        held = dict(current)
        held["status"] = "queued"
        held["workflow_state"] = "queued"
        held["error"] = reason
        write_agent_output(deal, agent_key=agent_key, output=held)
        upsert_run(
            db,
            deal_id=deal.id,
            agent_key=agent_key,
            status="queued",
            output=held,
            error_message=reason,
        )
    return affected


def apply_corrected_fact(db: Any, deal: Any, source_label: str) -> list[str]:
    """Record the corrected file and re-queue every agent that used it."""
    from agetic_cdd_api.services_step_log import StepLog

    label = Path(str(source_label or "").strip()).name
    slug = str(getattr(deal, "slug", None) or "")
    if not slug or not label:
        return []
    StepLog(slug).add(
        kind="source",
        label=label,
        output=label,
        status="corrected",
        tier="data_room",
        detail="corrected fact",
    )
    return queue_downstream(db, deal, label)
