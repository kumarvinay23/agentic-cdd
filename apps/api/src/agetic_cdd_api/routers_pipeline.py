"""Deal pipeline routes — roadmap, run stubs, agent outputs, DIQ phases + SSE."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.foundation_context import assert_deep_dive_context
from agetic_cdd_api.pipeline_catalog import get_agent_meta, phase_by_id
from agetic_cdd_api.services_deals import get_deal
from agetic_cdd_api.services_deep_dive import iter_deep_dive_events
from agetic_cdd_api.services_final_verdict import iter_final_verdict_events
from agetic_cdd_api.verdict_store import assert_verdict_context
from agetic_cdd_api.services_pipeline import (
    get_run,
    phases_list_payload,
    pipeline_payload,
    read_agent_output_file,
    refresh_deal_pipeline_counters,
    run_to_dict,
    upsert_run,
    write_agent_output,
)
from agetic_cdd_api.services_pipeline_run import (
    execute_pipeline_keys,
    execute_pipeline_keys_background,
    schedule_pipeline_run,
)

router = APIRouter(tags=["pipeline"])


class PipelineRunBody(BaseModel):
    phase_id: str | None = None
    agent_key: str | None = None
    # Re-queue analysis agents from Data Ingestion onward (ignores next_phase).
    restart: bool = False


def _sse_pack(event: dict) -> str:
    etype = str(event.get("type") or "message")
    return f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/portfolios/{deal_id}/pipeline")
def pipeline_get(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return {"success": True, "data": pipeline_payload(db, deal=deal)}


@router.get("/portfolios/{deal_id}/pipeline/phases")
def pipeline_phases_get(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """DiligenceIQ-compatible phases list (status available|completed, agentList, src)."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return {"success": True, "data": phases_list_payload(db, deal=deal)}


@router.post("/portfolios/{deal_id}/pipeline/run", status_code=status.HTTP_202_ACCEPTED)
def pipeline_run(
    deal_id: str,
    background_tasks: BackgroundTasks,
    body: PipelineRunBody | None = None,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    payload = schedule_pipeline_run(
        db,
        org_id=auth.organization.id,
        deal_id=deal_id,
        phase_id=body.phase_id if body else None,
        agent_key=body.agent_key if body else None,
        restart=bool(body.restart) if body else False,
    )
    background_tasks.add_task(
        execute_pipeline_keys_background,
        org_id=auth.organization.id,
        deal_id=deal_id,
        agent_keys=payload["agent_keys"],
    )
    return {"success": True, "data": payload}


def _stream_phase_run(
    *,
    db: Session,
    org_id: str,
    deal_id: str,
    phase_id: str,
) -> Iterator[str]:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    phase = phase_by_id(phase_id)
    if not phase:
        yield _sse_pack({"type": "error", "message": "Unknown phase"})
        return

    try:
        scheduled = schedule_pipeline_run(
            db,
            org_id=org_id,
            deal_id=deal_id,
            phase_id=phase_id,
        )
    except HTTPException as exc:
        detail = exc.detail
        if isinstance(detail, dict):
            yield _sse_pack({"type": "error", **detail})
        else:
            yield _sse_pack({"type": "error", "message": str(detail), "status_code": exc.status_code})
        return

    agent_keys = list(scheduled.get("agent_keys") or [])

    if phase_id == "deep_dive":
        assert_deep_dive_context(deal)
        yield _sse_pack({"type": "keepalive", "message": "connected"})

        for event in iter_deep_dive_events(db, deal=deal, agent_keys=agent_keys):
            etype = event.get("type")
            if etype == "agent_started":
                key = str(event.get("agent_key") or "")
                if key:
                    upsert_run(db, deal_id=deal.id, agent_key=key, status="running")
                    refresh_deal_pipeline_counters(db, deal)
                    db.commit()
            elif etype in {"agent_completed", "agent_failed"}:
                key = str(event.get("agent_key") or "")
                payload = event.get("output") if isinstance(event.get("output"), dict) else None
                if key and payload:
                    write_agent_output(deal, agent_key=key, output=payload)
                    if payload.get("status") == "failed":
                        upsert_run(
                            db,
                            deal_id=deal.id,
                            agent_key=key,
                            status="failed",
                            output=payload,
                            error_message=str(payload.get("error") or payload.get("summary") or "failed"),
                        )
                    else:
                        upsert_run(
                            db,
                            deal_id=deal.id,
                            agent_key=key,
                            status="completed",
                            output=payload,
                        )
                    refresh_deal_pipeline_counters(db, deal)
                    db.commit()

            if etype == "result":
                continue  # keep bulky outputs off the wire
            wire = {k: v for k, v in event.items() if k != "output"}
            yield _sse_pack(wire)
            if etype == "agent_started":
                yield _sse_pack({"type": "keepalive"})
        return

    if phase_id == "final_verdict":
        assert_verdict_context(deal)
        yield _sse_pack({"type": "keepalive", "message": "connected"})

        for event in iter_final_verdict_events(db, deal=deal, agent_keys=agent_keys):
            etype = event.get("type")
            if etype == "agent_started":
                key = str(event.get("agent_key") or "")
                if key:
                    upsert_run(db, deal_id=deal.id, agent_key=key, status="running")
                    refresh_deal_pipeline_counters(db, deal)
                    db.commit()
            elif etype in {"agent_completed", "agent_failed"}:
                key = str(event.get("agent_key") or "")
                payload = event.get("output") if isinstance(event.get("output"), dict) else None
                if key and payload:
                    write_agent_output(deal, agent_key=key, output=payload)
                    if payload.get("status") == "failed":
                        upsert_run(
                            db,
                            deal_id=deal.id,
                            agent_key=key,
                            status="failed",
                            output=payload,
                            error_message=str(payload.get("error") or payload.get("summary") or "failed"),
                        )
                    else:
                        upsert_run(
                            db,
                            deal_id=deal.id,
                            agent_key=key,
                            status="completed",
                            output=payload,
                        )
                    refresh_deal_pipeline_counters(db, deal)
                    db.commit()

            if etype == "result":
                continue
            wire = {k: v for k, v in event.items() if k != "output"}
            yield _sse_pack(wire)
            if etype == "agent_started":
                yield _sse_pack({"type": "keepalive"})
        return

    yield _sse_pack({"type": "keepalive", "message": "connected"})
    execute_pipeline_keys(db, org_id=org_id, deal_id=deal_id, agent_keys=agent_keys)
    yield _sse_pack(
        {
            "type": "pipeline_started",
            "pipeline_id": deal.id,
            "name": f"Phase: {phase['phaseName']}",
        }
    )
    yield _sse_pack(
        {
            "type": "phase_completed",
            "phase_id": phase_id,
            "completedAgents": len(agent_keys),
            "totalAgents": len(agent_keys),
        }
    )
    yield _sse_pack({"type": "pipeline_completed", "success": True, "phase_id": phase_id})
    yield _sse_pack({"type": "done", "success": True})


@router.post("/portfolios/{deal_id}/pipeline/phase/{phase_id}/run")
def pipeline_phase_run_sse(
    deal_id: str,
    phase_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE phase run (DiligenceIQ-compatible). Prefer for Deep Dive."""

    def generate() -> Iterator[str]:
        yield from _stream_phase_run(
            db=db,
            org_id=auth.organization.id,
            deal_id=deal_id,
            phase_id=phase_id,
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/portfolios/{deal_id}/pipeline/{pipeline_id}/phase/{phase_id}/run")
def pipeline_phase_run_sse_aliased(
    deal_id: str,
    pipeline_id: str,
    phase_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """DIQ path shape: /pipeline/{pipeline_id}/phase/{phase_id}/run."""
    _ = pipeline_id

    def generate() -> Iterator[str]:
        yield from _stream_phase_run(
            db=db,
            org_id=auth.organization.id,
            deal_id=deal_id,
            phase_id=phase_id,
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/portfolios/{deal_id}/pipeline/agents/{agent_key}/output")
def pipeline_agent_output(
    deal_id: str,
    agent_key: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    if not get_agent_meta(agent_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    run = get_run(db, deal_id=deal.id, agent_key=agent_key)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent has not been run")
    file_output = read_agent_output_file(deal, agent_key=agent_key)
    meta = get_agent_meta(agent_key) or {}
    return {
        "success": True,
        "data": {
            **run_to_dict(run),
            "agentName": meta.get("agent", {}).get("agentName", agent_key),
            "phase_id": meta.get("phase", {}).get("phase_id"),
            "file_output": file_output,
        },
    }
