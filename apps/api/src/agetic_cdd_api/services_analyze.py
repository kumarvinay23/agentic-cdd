"""VDR analyze runner — classify documents without completing Workflow Phase 1."""

from __future__ import annotations

import json

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from agetic_cdd_api.db import SessionLocal
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_deals import get_deal
from agetic_cdd_api.services_ingestion import apply_di01_stub, apply_di02_stub, utc_now_iso
from agetic_cdd_api.services_vdr import library_dir, list_vdr_docs, save_docs


def is_ingestion_running(*, deal: Deal) -> bool:
    """True while Analyze is mid-pass (docs in parsing/classified)."""
    return any(doc.get("status") in {"parsing", "classified"} for doc in list_vdr_docs(deal))


def run_phase1_analyze(db: Session, *, org_id: str, deal_id: str) -> None:
    """Classify VDR documents only — does not complete Workflow Phase 1 agents."""
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    docs = list_vdr_docs(deal)
    if not docs:
        return

    try:
        parsed = apply_di01_stub(docs)
        save_docs(db, deal, parsed)

        deal = get_deal(db, org_id=org_id, deal_id=deal_id)
        classified, routing = apply_di02_stub(list_vdr_docs(deal))
        save_docs(db, deal, classified)

        routing_payload = {
            "deal_id": deal.id,
            "generated_at": utc_now_iso(),
            "documents": routing,
            "master_index": [r["filename"] for r in routing],
        }
        lib = library_dir(deal)
        (lib / "routing.json").write_text(json.dumps(routing_payload, indent=2), encoding="utf-8")
    except Exception as exc:
        db.rollback()
        deal = db.get(Deal, deal_id)
        if deal:
            failed = [{**doc, "status": "error"} for doc in list_vdr_docs(deal)]
            if failed:
                save_docs(db, deal, failed)
        raise exc


def run_phase1_analyze_background(*, org_id: str, deal_id: str) -> None:
    """Background worker: opens its own DB session (never reuse the request session)."""
    db = SessionLocal()
    try:
        run_phase1_analyze(db, org_id=org_id, deal_id=deal_id)
    finally:
        db.close()


def schedule_analyze(db: Session, *, org_id: str, deal_id: str) -> dict:
    deal = get_deal(db, org_id=org_id, deal_id=deal_id)
    docs = list_vdr_docs(deal)
    if not docs:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload documents before analyzing")
    if is_ingestion_running(deal=deal):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Document analysis already in progress")

    save_docs(db, deal, apply_di01_stub(docs))

    return {
        "queued": True,
        "deal_id": deal.id,
        "document_count": len(docs),
        "started_at": utc_now_iso(),
    }
