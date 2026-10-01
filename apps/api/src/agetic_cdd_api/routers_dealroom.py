"""Deal room dashboard and VDR routes."""

from __future__ import annotations

import mimetypes
from enum import Enum

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.pipeline_catalog import total_agent_count
from agetic_cdd_api.services_analyze import (
    run_phase1_analyze_background,
    schedule_analyze,
)
from agetic_cdd_api.services_databook import (
    deep_databook,
    get_data_quality,
    get_databook_summary,
    list_databook_findings,
    list_databook_rows,
    rescan_databook,
    reread_databook_document,
)
from agetic_cdd_api.services_databook_consume import (
    filter_material_promoted,
    load_promoted_metrics,
    promoted_csv,
)
from agetic_cdd_api.services_databook_excel import (
    build_editable_workbook,
    import_edited_workbook,
)
from agetic_cdd_api.services_databook_decisions import (
    accept_conflict,
    correct_row,
    drop_row,
    vouch_row,
)
from agetic_cdd_api.services_databook_models import RowStatus
from agetic_cdd_api.services_deals import deal_to_dict, get_deal
from agetic_cdd_api.services_evidence import analyze_vdr, load_evidence_graph
from agetic_cdd_api.services_library import library_index_stats, reingest_deal_library
from agetic_cdd_api.services_pipeline import ingestion_status, merge_roadmap_with_runs
from agetic_cdd_api.services_vdr import (
    delete_vdr_file,
    list_vdr_docs,
    sync_vdr_from_disk,
    upload_vdr_file,
    vdr_file_for_download,
    vdr_health,
)

router = APIRouter(tags=["dealroom"])


class DatabookRowStatusFilter(str, Enum):
    """Allowed ``status`` query values for databook rows (subset of RowStatus)."""

    candidate = RowStatus.CANDIDATE.value
    held_out = RowStatus.HELD_OUT.value
    dropped = RowStatus.DROPPED.value
    promoted = RowStatus.PROMOTED.value
    vouched = RowStatus.VOUCHED.value


@router.get("/deal-rooms/{deal_id}/dashboard")
def deal_dashboard(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Sync handler so VDR scan + roadmap queries run in FastAPI's threadpool."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = sync_vdr_from_disk(db, deal)
    roadmap = merge_roadmap_with_runs(db, deal_id=deal.id)
    total = max(0, int(total_agent_count() or 0))
    completed = sum(p.get("completedAgents", 0) for p in roadmap)
    ready_docs = sum(1 for d in list_vdr_docs(deal) if d.get("status") == "ready")
    return {
        "success": True,
        "data": {
            "dealRoom": {
                "uuid": deal.id,
                "id": deal.id,
                "name": deal.name,
                "status": deal.status,
                "slug": deal.slug,
                "sector": deal.sector,
            },
            "deal": deal_to_dict(deal),
            "workflowCompletion": {
                "totalAgents": total,
                "completedAgents": completed,
                "completionPercentage": round((completed / total) * 100) if total else 0,
            },
            "dataRoomStatus": {
                "processedDocuments": ready_docs,
                "totalDocuments": deal.docs_count,
                "totalSizeBytes": deal.vdr_bytes,
            },
            "assignedTeams": [],
            "workflowRoadmap": roadmap,
            "recentActivity": [],
            "reportStatus": {
                "hasReports": deal.reports_ready > 0,
                "generatedReports": [],
            },
        },
    }


@router.get("/portfolios/{deal_id}/cdd/health")
def cdd_health(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Lightweight VDR health after a disk sync (file counts / ready status)."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = sync_vdr_from_disk(db, deal)
    return vdr_health(deal)


@router.get("/portfolios/{deal_id}/cdd/vdr")
def cdd_vdr_list(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = sync_vdr_from_disk(db, deal)
    docs = list_vdr_docs(deal)
    ingestion = ingestion_status(db, deal=deal)
    return {
        "vdr": [d["filename"] for d in docs],
        "data": docs,
        "ingestion": ingestion,
    }


@router.get("/portfolios/{deal_id}/cdd/ingestion")
def cdd_ingestion_status(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return {"success": True, "data": ingestion_status(db, deal=deal)}


@router.get("/portfolios/{deal_id}/cdd/library/stats")
def cdd_library_stats(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return {"success": True, "data": library_index_stats(deal)}


@router.post("/portfolios/{deal_id}/cdd/library/reingest")
def cdd_library_reingest(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Rebuild library chunks + FTS search index from VDR files on disk."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return reingest_deal_library(db, deal=deal)


@router.post("/portfolios/{deal_id}/cdd/vdr/analyze")
def cdd_vdr_analyze(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    return analyze_vdr(db, org_id=auth.organization.id, deal_id=deal_id)


@router.get("/portfolios/{deal_id}/cdd/vdr/graph")
def cdd_vdr_graph(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    return load_evidence_graph(db, org_id=auth.organization.id, deal_id=deal_id)


@router.post("/portfolios/{deal_id}/cdd/analyze", status_code=status.HTTP_202_ACCEPTED)
def cdd_analyze(
    deal_id: str,
    background_tasks: BackgroundTasks,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Queue Phase-1 VDR classify. Background worker opens a fresh DB session."""
    payload = schedule_analyze(db, org_id=auth.organization.id, deal_id=deal_id)
    background_tasks.add_task(
        run_phase1_analyze_background,
        org_id=auth.organization.id,
        deal_id=deal_id,
    )
    return {"success": True, "data": payload}


@router.get("/portfolios/{deal_id}/cdd/vdr/files/{filename}")
def cdd_vdr_download(
    deal_id: str,
    filename: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> FileResponse:
    """Download a VDR file. ``filename`` is a single path segment (no ``/``); traversal is rejected."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    path = vdr_file_for_download(deal, filename)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@router.post("/portfolios/{deal_id}/cdd/vdr/upload")
async def cdd_vdr_upload(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = await upload_vdr_file(db, deal, file)
    docs = list_vdr_docs(deal)
    return {
        "success": True,
        "data": {
            "deal": deal_to_dict(deal),
            "vdr": docs,
        },
    }


@router.post("/portfolios/{deal_id}/cdd/sync")
def cdd_sync(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Explicit VDR resync from disk (same payload shape as health after sync)."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = sync_vdr_from_disk(db, deal)
    return {"success": True, "data": vdr_health(deal)}


@router.delete("/portfolios/{deal_id}/cdd/vdr/{filename}")
async def cdd_vdr_delete(
    deal_id: str,
    filename: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Delete a VDR file. ``filename`` is a single path segment; traversal is rejected."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    deal = await delete_vdr_file(db, deal, filename)
    return {
        "success": True,
        "data": {"vdr": list_vdr_docs(deal), "deal": deal_to_dict(deal)},
    }


@router.get("/portfolios/{deal_id}/cdd/databook")
def cdd_databook_summary(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    summary = get_databook_summary(deal, ensure=False)
    return {"success": True, "data": summary.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/cdd/databook/rescan")
def cdd_databook_rescan(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    summary = rescan_databook(deal)
    return {"success": True, "data": summary.model_dump(mode="json")}


@router.post("/portfolios/{deal_id}/cdd/databook/deep")
def cdd_databook_deep(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Re-extract all VDR originals into the library, then Rescan (decision replay)."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    summary = deep_databook(db, deal)
    return {"success": True, "data": summary.model_dump(mode="json")}


@router.get("/portfolios/{deal_id}/cdd/databook/rows")
def cdd_databook_rows(
    deal_id: str,
    status: DatabookRowStatusFilter | None = None,
    metric: str | None = Query(default=None, max_length=120),
    material: bool = Query(default=False, description="Only headline FY metrics (revenue, ebitda, …)"),
    min_abs: float | None = Query(default=None, ge=0, description="Drop absolute values below this floor"),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    status_value = status.value if status is not None else None
    rows = list_databook_rows(
        deal,
        status=status_value,
        metric=metric,
        material_only=material,
        min_abs=min_abs,
    )
    return {"success": True, "data": {"items": rows, "total": len(rows)}}


@router.get("/portfolios/{deal_id}/cdd/databook/findings")
def cdd_databook_findings(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    findings = list_databook_findings(deal)
    return {"success": True, "data": {"items": findings, "total": len(findings)}}


@router.get("/portfolios/{deal_id}/cdd/databook/promoted")
def cdd_databook_promoted(
    deal_id: str,
    material: bool = Query(default=False),
    min_abs: float | None = Query(default=None, ge=0),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    metrics = filter_material_promoted(
        load_promoted_metrics(deal),
        material_only=material,
        min_abs=min_abs,
    )
    return {
        "success": True,
        "data": {"metrics": [m.model_dump(mode="json") for m in metrics], "total": len(metrics)},
    }


@router.get("/portfolios/{deal_id}/cdd/databook/promoted.csv")
def cdd_databook_promoted_csv(
    deal_id: str,
    material: bool = Query(default=False),
    min_abs: float | None = Query(default=None, ge=0),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response

    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    metrics = filter_material_promoted(
        load_promoted_metrics(deal),
        material_only=material,
        min_abs=min_abs,
    )
    body = promoted_csv(metrics)
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{deal.slug or deal_id}-promoted.csv"',
        },
    )


@router.get("/portfolios/{deal_id}/cdd/databook/export.xlsx")
def cdd_databook_export_xlsx(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response

    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    body = build_editable_workbook(deal)
    return Response(
        content=body,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{deal.slug or deal_id}-databook.xlsx"',
        },
    )


@router.post("/portfolios/{deal_id}/cdd/databook/import.xlsx")
async def cdd_databook_import_xlsx(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    reason: str | None = Query(default=None, max_length=500),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    name = (file.filename or "").lower()
    if not (name.endswith(".xlsx") or name.endswith(".xlsm")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Upload an .xlsx workbook")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    try:
        result = import_edited_workbook(
            deal,
            content,
            actor=auth.user.email,
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    summary = get_databook_summary(deal, ensure=False)
    return {"success": True, "data": {**result, "summary": summary.model_dump(mode="json")}}


@router.get("/portfolios/{deal_id}/cdd/data-quality")
def cdd_data_quality(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """DiligenceIQ-compatible data-quality projection for Databook verification."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    dq = get_data_quality(deal, ensure=True)
    return dq.model_dump(mode="json")


class DatabookCorrectBody(BaseModel):
    reason: str
    value: float | None = None
    metric_key: str | None = None
    unit: str | None = None
    currency: str | None = None
    scale: str | None = None
    caption: str | None = None


class DatabookReasonBody(BaseModel):
    reason: str


class DatabookAcceptBody(BaseModel):
    reason: str
    metric_key: str
    fiscal_year: int
    value: float
    row_id: str | None = None


class DatabookRereadBody(BaseModel):
    filename: str


@router.post("/portfolios/{deal_id}/cdd/databook/rows/{row_id}/correct")
def cdd_databook_correct(
    deal_id: str,
    row_id: str,
    body: DatabookCorrectBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    result = correct_row(
        deal,
        row_id,
        reason=body.reason,
        actor=auth.user.email,
        value=body.value,
        metric_key=body.metric_key,
        unit=body.unit,
        currency=body.currency,
        scale=body.scale,
        caption=body.caption,
    )
    return {"success": True, "data": result}


@router.post("/portfolios/{deal_id}/cdd/databook/rows/{row_id}/drop")
def cdd_databook_drop(
    deal_id: str,
    row_id: str,
    body: DatabookReasonBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    result = drop_row(deal, row_id, reason=body.reason, actor=auth.user.email)
    return {"success": True, "data": result}


@router.post("/portfolios/{deal_id}/cdd/databook/rows/{row_id}/vouch")
def cdd_databook_vouch(
    deal_id: str,
    row_id: str,
    body: DatabookReasonBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    result = vouch_row(deal, row_id, reason=body.reason, actor=auth.user.email)
    return {"success": True, "data": result}


@router.post("/portfolios/{deal_id}/cdd/databook/conflicts/accept")
def cdd_databook_accept_conflict(
    deal_id: str,
    body: DatabookAcceptBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    result = accept_conflict(
        deal,
        metric_key=body.metric_key,
        fiscal_year=body.fiscal_year,
        value=body.value,
        reason=body.reason,
        actor=auth.user.email,
        row_id=body.row_id,
    )
    return {"success": True, "data": result}


@router.post("/portfolios/{deal_id}/cdd/databook/reread")
def cdd_databook_reread(
    deal_id: str,
    body: DatabookRereadBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    summary = reread_databook_document(db, deal, body.filename)
    return {"success": True, "data": summary.model_dump(mode="json")}
