"""Pipeline agent run persistence and roadmap status merge."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal, PipelineAgentRun
from agetic_cdd_api.pipeline_catalog import (
    all_agent_keys,
    build_stub_roadmap,
    get_agent_meta,
    report_agent_keys,
    total_agent_count,
)
from agetic_cdd_api.security import new_id
from agetic_cdd_api.services_deals import ensure_deal_folder


def list_runs(db: Session, *, deal_id: str) -> list[PipelineAgentRun]:
    return db.scalars(
        select(PipelineAgentRun)
        .where(PipelineAgentRun.deal_id == deal_id)
        .order_by(PipelineAgentRun.started_at.asc().nulls_last())
    ).all()


def get_run(db: Session, *, deal_id: str, agent_key: str) -> PipelineAgentRun | None:
    return db.scalar(
        select(PipelineAgentRun).where(
            PipelineAgentRun.deal_id == deal_id,
            PipelineAgentRun.agent_key == agent_key,
        )
    )


def upsert_run(
    db: Session,
    *,
    deal_id: str,
    agent_key: str,
    status: str,
    output: dict | None = None,
    error_message: str | None = None,
) -> PipelineAgentRun:
    row = get_run(db, deal_id=deal_id, agent_key=agent_key)
    now = datetime.now(UTC)
    if not row:
        row = PipelineAgentRun(
            id=new_id(),
            deal_id=deal_id,
            agent_key=agent_key,
            status=status,
        )
        db.add(row)
    row.status = status
    if status == "running":
        row.started_at = now
        row.finished_at = None
        row.error_message = None
    if status in {"completed", "failed"}:
        row.finished_at = now
    if error_message is not None:
        row.error_message = error_message
    if output is not None:
        row.output_json = json.dumps(output)
    db.flush()
    return row


def run_to_dict(run: PipelineAgentRun) -> dict:
    try:
        output = json.loads(run.output_json or "{}")
    except (json.JSONDecodeError, TypeError):
        output = {}
    return {
        "agent_key": run.agent_key,
        "status": run.status,
        "started_at": run.started_at.isoformat().replace("+00:00", "Z") if run.started_at else None,
        "finished_at": run.finished_at.isoformat().replace("+00:00", "Z") if run.finished_at else None,
        "error_message": run.error_message,
        "output": output,
    }


def ingestion_status(db: Session, *, deal: Deal) -> dict:
    from agetic_cdd_api.services_library import library_index_stats
    from agetic_cdd_api.services_vdr import list_vdr_docs

    docs = list_vdr_docs(deal)
    running = any(doc.get("status") in {"parsing", "classified"} for doc in docs)
    completed = bool(docs) and all(doc.get("status") in {"ready", "error"} for doc in docs)
    lib = library_index_stats(deal)
    indexed = int(lib.get("indexed_chunks") or 0)
    return {
        "running": running,
        "completed": completed,
        "processed_chunks": indexed,
        "indexed_chunks": indexed,
        "library_chunk_count": int(lib.get("chunk_count") or 0),
        "fts_ready": bool(lib.get("fts_ready")),
        "document_count": len(docs),
        "library_document_count": int(lib.get("document_count") or 0),
        "ready_count": sum(1 for doc in docs if doc.get("status") == "ready"),
    }


def _diq_agent_status(status: str) -> str:
    if status == "completed":
        return "completed"
    if status in {"running", "pending"}:
        return "running" if status == "running" else "available"
    if status == "failed":
        return "failed"
    return "available"


def _diq_phase_status(phase_status: str, agents: list[dict]) -> str:
    if phase_status == "completed":
        return "completed"
    if any(a.get("status") == "running" for a in agents) or phase_status == "in_progress":
        return "running"
    return "available"


def merge_roadmap_with_runs(db: Session, *, deal_id: str) -> list[dict]:
    runs = {r.agent_key: r.status for r in list_runs(db, deal_id=deal_id)}
    roadmap = build_stub_roadmap(agent_status="idle")
    for phase in roadmap:
        for stage in phase["stages"]:
            for agent in stage["agents"]:
                key = agent["agent_key"]
                if key in runs:
                    agent["status"] = runs[key]
        agents_flat = []
        for stage in phase["stages"]:
            agents_flat.extend(stage["agents"])
        phase["agents"] = agents_flat
        phase["agentList"] = agents_flat
        total = len(agents_flat)
        completed = sum(1 for a in agents_flat if a["status"] == "completed")
        phase["totalAgents"] = total
        phase["completedAgents"] = completed
        phase["status"] = (
            "completed"
            if completed == total and total
            else (
                "in_progress"
                if completed or any(a["status"] == "running" for a in agents_flat)
                else "pending"
            )
        )
        phase["id"] = phase["phase_id"]
        phase["name"] = phase["phaseName"]
    return roadmap


def phases_list_payload(db: Session, *, deal: Deal) -> dict:
    """DiligenceIQ-shaped GET /pipeline/phases payload."""
    roadmap = merge_roadmap_with_runs(db, deal_id=deal.id)
    phases = []
    for phase in roadmap:
        agents = []
        for agent in phase.get("agents") or []:
            agents.append(
                {
                    **agent,
                    "id": agent.get("agent_key"),
                    "name": agent.get("agentName"),
                    "status": _diq_agent_status(str(agent.get("status") or "idle")),
                    "src": agent.get("src") or "algo",
                }
            )
        stages = []
        for stage in phase.get("stages") or []:
            stage_agents = [
                {
                    **agent,
                    "id": agent.get("agent_key"),
                    "name": agent.get("agentName"),
                    "status": _diq_agent_status(str(agent.get("status") or "idle")),
                    "src": agent.get("src") or "algo",
                }
                for agent in stage.get("agents") or []
            ]
            stages.append({**stage, "agents": stage_agents, "agentList": stage_agents})
        phases.append(
            {
                **phase,
                "id": phase["phase_id"],
                "name": phase["phaseName"],
                "status": _diq_phase_status(str(phase.get("status") or "pending"), agents),
                "agents": agents,
                "agentList": agents,
                "stages": stages,
            }
        )
    return {"deal_id": deal.id, "phases": phases}


def outputs_dir(deal: Deal) -> Path:
    path = ensure_deal_folder(deal.slug) / "outputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_agent_output(deal: Deal, *, agent_key: str, output: dict) -> Path:
    path = outputs_dir(deal) / f"{agent_key}.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    try:
        from agetic_cdd_api.services_agent_documents import ensure_agent_document_after_run

        ensure_agent_document_after_run(deal, agent_key)
    except Exception:
        pass
    return path


def read_agent_output_file(deal: Deal, *, agent_key: str) -> dict | None:
    path = outputs_dir(deal) / f"{agent_key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def refresh_deal_pipeline_counters(db: Session, deal: Deal) -> Deal:
    runs = list_runs(db, deal_id=deal.id)
    deal.agents_running = sum(1 for row in runs if row.status == "running")
    reports = set(report_agent_keys())
    deal.reports_ready = sum(1 for row in runs if row.agent_key in reports and row.status == "completed")
    db.flush()
    return deal


def is_pipeline_busy(db: Session, *, deal: Deal) -> bool:
    if deal.agents_running > 0:
        return True
    return any(row.status in {"running", "pending"} for row in list_runs(db, deal_id=deal.id))


def active_run(db: Session, *, deal_id: str):
    runs = list_runs(db, deal_id=deal_id)
    return next((row for row in runs if row.status == "running"), None) or next(
        (row for row in runs if row.status == "pending"), None
    )


def completed_agent_keys(db: Session, *, deal_id: str) -> set[str]:
    return {row.agent_key for row in list_runs(db, deal_id=deal_id) if row.status == "completed"}


def next_incomplete_phase(roadmap: list[dict]) -> dict | None:
    for phase in roadmap:
        if phase["status"] != "completed":
            return phase
    return None


def pipeline_payload(db: Session, *, deal: Deal) -> dict:
    roadmap = merge_roadmap_with_runs(db, deal_id=deal.id)
    total = total_agent_count()
    completed = sum(phase.get("completedAgents", 0) for phase in roadmap)
    next_phase = next_incomplete_phase(roadmap)
    current = active_run(db, deal_id=deal.id)
    current_key = current.agent_key if current else None
    current_meta = get_agent_meta(current_key) if current_key else None
    current_name = None
    if current_meta:
        current_name = (current_meta.get("agent") or {}).get("agentName") or current_key
    elif current_key:
        current_name = current_key
    return {
        "deal_id": deal.id,
        "running": is_pipeline_busy(db, deal=deal),
        "totalAgents": total,
        "completedAgents": completed,
        "completionPercentage": round((completed / total) * 100) if total else 0,
        "next_phase_id": next_phase["phase_id"] if next_phase else None,
        "next_phase_name": next_phase["phaseName"] if next_phase else None,
        "running_agent_key": current_key,
        "running_agent_name": current_name,
        "phases": roadmap,
        "agent_keys": all_agent_keys(),
    }
