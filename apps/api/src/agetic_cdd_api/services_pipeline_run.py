"""Generic W4 pipeline stub runner (all 44 agents, left-to-right cascade)."""

from __future__ import annotations

import time
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.db import SessionLocal
from agetic_cdd_api.models import Deal
from agetic_cdd_api.pipeline_catalog import (
    PHASE1_AGENT_KEYS,
    PHASE2_AGENT_KEYS,
    PHASE3_AGENT_KEYS,
    PHASE4_AGENT_KEYS,
    agent_keys_for_phase,
    get_agent_meta,
    phase_by_id,
    previous_phase,
)
from agetic_cdd_api.services_deals import get_deal
from agetic_cdd_api.services_deep_dive import run_deep_dive
from agetic_cdd_api.services_final_verdict import run_final_verdict
from agetic_cdd_api.services_foundations import run_foundations
from agetic_cdd_api.foundation_context import assert_deep_dive_context
from agetic_cdd_api.verdict_store import assert_verdict_context
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import ingest_phase1
from agetic_cdd_api.services_pipeline import (
    completed_agent_keys,
    get_run,
    is_pipeline_busy,
    merge_roadmap_with_runs,
    next_incomplete_phase,
    refresh_deal_pipeline_counters,
    upsert_run,
    write_agent_output,
)
from agetic_cdd_api.services_vdr import list_vdr_docs


def _phase_completed(db: Session, *, deal_id: str, phase: dict) -> bool:
    done = completed_agent_keys(db, deal_id=deal_id)
    keys = agent_keys_for_phase(phase)
    return bool(keys) and all(key in done for key in keys)


def _assert_previous_phase_complete(db: Session, *, deal_id: str, phase: dict) -> None:
    prior = previous_phase(phase)
    if prior and not _phase_completed(db, deal_id=deal_id, phase=prior):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Complete {prior['phaseName']} before running {phase['phaseName']}.",
        )


def _stub_output(*, deal: Deal, agent_key: str) -> dict:
    meta = get_agent_meta(agent_key)
    agent = (meta or {}).get("agent") or {"agentName": agent_key, "description": ""}
    phase = (meta or {}).get("phase") or {}
    stage = (meta or {}).get("stage") or {}
    return {
        "stub": True,
        "agent_key": agent_key,
        "agentName": agent.get("agentName", agent_key),
        "description": agent.get("description", ""),
        "phase_id": phase.get("phase_id"),
        "phaseName": phase.get("phaseName"),
        "stageKey": stage.get("stageKey"),
        "deal_id": deal.id,
        "deal_name": deal.name,
        "summary": (
            f"Fixture output for {agent.get('agentName', agent_key)} on {deal.name}. "
            "Real agent content arrives in W5+."
        ),
        "findings": [],
        "generated_at": utc_now_iso(),
        "output_path": f"outputs/{agent_key}.json",
    }


def _mark_agent_running(db: Session, *, deal: Deal, agent_key: str) -> None:
    upsert_run(db, deal_id=deal.id, agent_key=agent_key, status="running")
    refresh_deal_pipeline_counters(db, deal)
    db.commit()
    time.sleep(0.25)


def _complete_agent(db: Session, *, deal: Deal, agent_key: str, output: dict) -> None:
    upsert_run(db, deal_id=deal.id, agent_key=agent_key, status="running")
    refresh_deal_pipeline_counters(db, deal)
    db.commit()
    write_agent_output(deal, agent_key=agent_key, output=output)
    upsert_run(db, deal_id=deal.id, agent_key=agent_key, status="completed", output=output)
    refresh_deal_pipeline_counters(db, deal)
    db.commit()


def _run_stub_agent(db: Session, *, deal: Deal, agent_key: str) -> None:
    _complete_agent(db, deal=deal, agent_key=agent_key, output=_stub_output(deal=deal, agent_key=agent_key))


def execute_pipeline_keys(db: Session, *, org_id: str, deal_id: str, agent_keys: list[str]) -> None:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    keys = list(dict.fromkeys(agent_keys))
    if not keys:
        return

    phase1_requested = [key for key in keys if key in PHASE1_AGENT_KEYS]
    phase2_requested = [key for key in keys if key in PHASE2_AGENT_KEYS]
    phase3_requested = [key for key in keys if key in PHASE3_AGENT_KEYS]
    phase4_requested = [key for key in keys if key in PHASE4_AGENT_KEYS]
    ingested_phase1 = False
    foundations_done = False
    deep_dive_done = False
    final_verdict_done = False
    live_outputs: dict[str, dict] = {}

    try:
        for key in keys:
            deal = get_deal(db, org_id=org_id, deal_id=deal_id)
            _mark_agent_running(db, deal=deal, agent_key=key)
            if key in PHASE1_AGENT_KEYS and not ingested_phase1:
                live_outputs.update(ingest_phase1(db, deal=deal))
                ingested_phase1 = True
            elif key in PHASE2_AGENT_KEYS and not foundations_done:
                live_outputs.update(run_foundations(db, deal=deal, agent_keys=phase2_requested))
                foundations_done = True
            elif key in PHASE3_AGENT_KEYS and not deep_dive_done:
                live_outputs.update(run_deep_dive(db, deal=deal, agent_keys=phase3_requested))
                deep_dive_done = True
            elif key in PHASE4_AGENT_KEYS and not final_verdict_done:
                live_outputs.update(run_final_verdict(db, deal=deal, agent_keys=phase4_requested))
                final_verdict_done = True
            deal = get_deal(db, org_id=org_id, deal_id=deal_id)
            if key in live_outputs:
                payload = live_outputs[key]
                if payload.get("status") == "failed":
                    write_agent_output(deal, agent_key=key, output=payload)
                    upsert_run(
                        db,
                        deal_id=deal.id,
                        agent_key=key,
                        status="failed",
                        output=payload,
                        error_message=str(payload.get("error") or payload.get("summary") or "blocked"),
                    )
                    refresh_deal_pipeline_counters(db, deal)
                    db.commit()
                else:
                    _complete_agent(db, deal=deal, agent_key=key, output=payload)
            else:
                _run_stub_agent(db, deal=deal, agent_key=key)

        deal = get_deal(db, org_id=org_id, deal_id=deal_id)
        refresh_deal_pipeline_counters(db, deal)
        db.commit()

    except HTTPException:
        deal = db.get(Deal, deal_id)
        if deal:
            refresh_deal_pipeline_counters(db, deal)
            db.commit()
        raise
    except Exception as exc:
        db.rollback()
        deal = db.get(Deal, deal_id)
        if deal:
            for key in keys:
                existing = get_run(db, deal_id=deal.id, agent_key=key)
                if existing and existing.status == "completed":
                    continue
                upsert_run(
                    db,
                    deal_id=deal.id,
                    agent_key=key,
                    status="failed",
                    error_message=str(exc),
                )
            refresh_deal_pipeline_counters(db, deal)
            db.commit()
        raise


def execute_pipeline_keys_background(*, org_id: str, deal_id: str, agent_keys: list[str]) -> None:
    db = SessionLocal()
    try:
        execute_pipeline_keys(db, org_id=org_id, deal_id=deal_id, agent_keys=agent_keys)
    finally:
        db.close()


def schedule_pipeline_run(
    db: Session,
    *,
    org_id: str,
    deal_id: str,
    phase_id: str | None = None,
    agent_key: str | None = None,
) -> dict:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    if is_pipeline_busy(db, deal=deal):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pipeline already running")

    queued: list[str]
    target_phase_id: str | None = phase_id
    cascade_plan: dict | None = None

    if agent_key:
        meta = get_agent_meta(agent_key)
        if not meta:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown agent")
        phase = meta["phase"]
        _assert_previous_phase_complete(db, deal_id=deal.id, phase=phase)
        if agent_key in PHASE1_AGENT_KEYS:
            queued = PHASE1_AGENT_KEYS
        elif agent_key in PHASE3_AGENT_KEYS:
            from agetic_cdd_api.deep_dive_cascade import plan_cascade_rerun

            cascade_plan = plan_cascade_rerun(deal, [agent_key])
            queued = list(cascade_plan.get("agent_keys") or [])
        elif agent_key in PHASE4_AGENT_KEYS:
            from agetic_cdd_api.verdict_cascade import plan_cascade_rerun as plan_verdict_cascade

            cascade_plan = plan_verdict_cascade(deal, [agent_key])
            queued = list(cascade_plan.get("agent_keys") or [])
        else:
            queued = [agent_key]
        target_phase_id = phase["phase_id"]
    elif phase_id:
        phase = phase_by_id(phase_id)
        if not phase:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown phase")
        _assert_previous_phase_complete(db, deal_id=deal.id, phase=phase)
        queued = agent_keys_for_phase(phase)
        target_phase_id = phase["phase_id"]
    else:
        roadmap = merge_roadmap_with_runs(db, deal_id=deal.id)
        nxt = next_incomplete_phase(roadmap)
        if not nxt:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Pipeline already complete")
        _assert_previous_phase_complete(db, deal_id=deal.id, phase=nxt)
        queued = agent_keys_for_phase(nxt)
        target_phase_id = nxt["phase_id"]

    if any(key in PHASE1_AGENT_KEYS for key in queued) and not list_vdr_docs(deal):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload documents before running Data Ingestion",
        )

    queued_phase_ids = []
    for key in queued:
        queued_meta = get_agent_meta(key) or {}
        queued_phase_ids.append((queued_meta.get("phase") or {}).get("phase_id"))
    if target_phase_id == "deep_dive" or "deep_dive" in queued_phase_ids:
        assert_deep_dive_context(deal)
    if target_phase_id == "final_verdict" or "final_verdict" in queued_phase_ids:
        assert_verdict_context(deal)

    for index, key in enumerate(queued):
        upsert_run(
            db,
            deal_id=deal.id,
            agent_key=key,
            status="running" if index == 0 else "pending",
            output={},
        )
    refresh_deal_pipeline_counters(db, deal)
    db.commit()

    response: dict = {
        "queued": True,
        "deal_id": deal.id,
        "phase_id": target_phase_id,
        "agent_keys": queued,
        "started_at": utc_now_iso(),
    }
    if cascade_plan is not None:
        response["cascade"] = cascade_plan
    return response
