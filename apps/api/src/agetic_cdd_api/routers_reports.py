"""Report generation routes — generate / events / status / download / storyline.

Mirrors the live DiligenceIQ report API shape:

    POST /portfolios/{deal_id}/reports/{report_type}/generate
    GET  /portfolios/{deal_id}/reports/{report_type}/events   (SSE)
    GET  /portfolios/{deal_id}/reports/{report_type}/status
    GET  /portfolios/{deal_id}/reports/{report_type}/download
    GET  /portfolios/{deal_id}/reports                         (catalog)
    GET  /portfolios/{deal_id}/reports/{report_type}/storyline
    PUT  /portfolios/{deal_id}/reports/{report_type}/storyline
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.report_store import (
    REPORT_TYPES,
    get_report,
    list_reports,
    start_report,
    update_storyline,
)
from agetic_cdd_api.report_storyline import (
    StorylineSection,
    default_storyline,
    storyline_as_dicts,
)
from agetic_cdd_api.services_deals import get_deal, deals_root as _deals_root

router = APIRouter(tags=["reports"])

# ---------------------------------------------------------------------------
# Builder registry — concrete builders register themselves here on import.
# ---------------------------------------------------------------------------
_BUILDERS: dict[str, type] = {}


def register_builder(report_type: str, builder_cls: type) -> None:
    _BUILDERS[report_type] = builder_cls


def get_builder(report_type: str, deal_slug: str):
    cls = _BUILDERS.get(report_type)
    if cls is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Builder for '{report_type}' is not yet implemented.",
        )
    return cls(deal_slug)


# ---------------------------------------------------------------------------
# SSE helper
# ---------------------------------------------------------------------------

def _sse_pack(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _resolve_artifact_path(deal_slug: str, artifact: str) -> Path:
    """Resolve artifact path and ensure it stays within the deal folder."""
    deal_dir = (_deals_root() / deal_slug).resolve()
    p = Path(artifact)
    filepath = p.resolve() if p.is_absolute() else (deal_dir / artifact).resolve()
    if not filepath.is_relative_to(deal_dir):
        raise HTTPException(status_code=400, detail="Invalid artifact path.")
    return filepath


# Background generation with event buffering for the SSE events endpoint.
_event_buffers: dict[str, list[dict]] = {}
_event_done: dict[str, bool] = {}
_buf_lock = threading.Lock()


def _generate_background(deal_slug: str, report_type: str) -> None:
    job_key = f"{deal_slug}:{report_type}"
    with _buf_lock:
        _event_buffers[job_key] = []
        _event_done[job_key] = False
    try:
        builder = get_builder(report_type, deal_slug)
        for evt in builder.generate():
            with _buf_lock:
                _event_buffers.setdefault(job_key, []).append(evt)
    except Exception as exc:
        # generate() usually yields an error event then re-raises; keep the
        # worker thread quiet and ensure SSE still gets a terminal error.
        with _buf_lock:
            buf = _event_buffers.setdefault(job_key, [])
            if not any(e.get("stage") == "error" for e in buf):
                buf.append(
                    {
                        "stage": "error",
                        "message": str(exc),
                        "level": "error",
                    }
                )
    finally:
        with _buf_lock:
            _event_done[job_key] = True


async def _iter_buffered_events(job_key: str):
    """Yield SSE lines from the background event buffer until done."""
    import asyncio

    cursor = 0
    try:
        while True:
            with _buf_lock:
                buf = _event_buffers.get(job_key, [])
                done = _event_done.get(job_key, False)
                new_events = buf[cursor:]
                cursor = len(buf)
            for evt in new_events:
                yield _sse_pack(evt)
            if done and cursor >= len(_event_buffers.get(job_key, [])):
                break
            await asyncio.sleep(0.3)
    finally:
        with _buf_lock:
            _event_buffers.pop(job_key, None)
            _event_done.pop(job_key, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/portfolios/{deal_id}/reports")
def report_catalog(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    reports = list_reports(deal.slug)
    return {"success": True, "data": reports}


@router.post("/portfolios/{deal_id}/reports/{report_type}/generate")
def generate_report(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    if report_type not in REPORT_TYPES:
        raise HTTPException(status_code=404, detail=f"Unknown report type: {report_type}")
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)

    job_envelope = start_report(deal.slug, report_type)

    t = threading.Thread(
        target=_generate_background,
        args=(deal.slug, report_type),
        daemon=True,
    )
    t.start()

    return job_envelope


@router.get("/portfolios/{deal_id}/reports/{report_type}/events")
def report_events(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    job_key = f"{deal.slug}:{report_type}"
    return StreamingResponse(
        _iter_buffered_events(job_key),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/portfolios/{deal_id}/reports/{report_type}/status")
def report_status(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    meta = get_report(deal.slug, report_type)
    if not meta:
        return {
            "report_type": report_type,
            "status": "not_generated",
            **(REPORT_TYPES.get(report_type, {})),
        }
    return {
        "report_type": report_type,
        "status": meta.get("status", "not_generated"),
        "job_id": meta.get("job_id"),
        "started_at": meta.get("started_at"),
        "ready_at": meta.get("ready_at"),
        "error": meta.get("error"),
        "artifact_path": meta.get("artifact_path"),
        "content_sha256": meta.get("content_sha256"),
        "artifact_bytes": meta.get("artifact_bytes"),
        "storyline_count": len(meta.get("storyline", [])),
        "stale_databook": bool(meta.get("stale_databook")),
        "stale_release_id": meta.get("stale_release_id"),
        "stale_reason": meta.get("stale_reason"),
        **(REPORT_TYPES.get(report_type, {})),
    }


@router.get("/portfolios/{deal_id}/reports/{report_type}/download")
def download_report(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
):
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    meta = get_report(deal.slug, report_type)
    if not meta or meta.get("status") not in {"ready", "stale"}:
        raise HTTPException(status_code=404, detail="Report not ready for download.")

    artifact = meta.get("artifact_path")
    if not artifact:
        raise HTTPException(status_code=404, detail="No artifact file found.")

    filepath = _resolve_artifact_path(deal.slug, artifact)

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing on disk.")

    export_fmt = REPORT_TYPES.get(report_type, {}).get("export", "bin")
    media_map = {
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "pdf": "application/pdf",
    }
    return FileResponse(
        path=str(filepath),
        media_type=media_map.get(export_fmt, "application/octet-stream"),
        filename=filepath.name,
        headers={
            # Prevent browsers / proxies from serving a prior IC Memo (or any report)
            # after regeneration — especially PDFs which are often aggressively cached.
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/portfolios/{deal_id}/reports/{report_type}/preview")
def preview_report(
    deal_id: str,
    report_type: str,
    sheet: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Return in-browser preview payload (xlsx sheets or docx document blocks)."""
    from agetic_cdd_api.report_preview import preview_docx, preview_pdf, preview_pptx, preview_xlsx

    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    meta = get_report(deal.slug, report_type)
    if not meta or meta.get("status") not in {"ready", "stale"}:
        raise HTTPException(status_code=404, detail="Report not ready for preview.")

    artifact = meta.get("artifact_path")
    if not artifact:
        raise HTTPException(status_code=404, detail="No artifact file found.")

    filepath = _resolve_artifact_path(deal.slug, artifact)
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Artifact file missing on disk.")

    export_fmt = REPORT_TYPES.get(report_type, {}).get("export", "")
    if export_fmt == "xlsx":
        payload = preview_xlsx(filepath, sheet=sheet)
    elif export_fmt == "docx":
        payload = preview_docx(filepath)
    elif export_fmt == "pdf":
        payload = preview_pdf(filepath)
    elif export_fmt == "pptx":
        payload = preview_pptx(filepath)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Preview is not yet supported for .{export_fmt or 'unknown'} reports.",
        )

    return {"success": True, "report_type": report_type, **payload}


@router.get("/portfolios/{deal_id}/reports/{report_type}/storyline")
def get_storyline(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    meta = get_report(deal.slug, report_type)
    if meta and meta.get("storyline"):
        sections = meta["storyline"]
    else:
        sections = storyline_as_dicts(default_storyline(report_type))
    return {"success": True, "report_type": report_type, "sections": sections}


class StorylineUpdateBody(BaseModel):
    sections: list[dict]


@router.put("/portfolios/{deal_id}/reports/{report_type}/storyline")
def put_storyline(
    deal_id: str,
    report_type: str,
    body: StorylineUpdateBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    update_storyline(deal.slug, report_type, body.sections)
    return {"success": True, "sections": body.sections}


@router.get("/portfolios/{deal_id}/reports/{report_type}/sources")
def get_sources(
    deal_id: str,
    report_type: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    """Return Sources-tab payload — recompute when a builder is available."""
    from agetic_cdd_api.report_storyline import StorylineSection

    deal = get_deal(db, deal_id=deal_id, org_id=auth.organization.id)
    meta = get_report(deal.slug, report_type) or {}
    sources = meta.get("sources") or {}

    builder_cls = _BUILDERS.get(report_type)
    if builder_cls is not None:
        try:
            builder = builder_cls(deal.slug)
            builder.discover_workflows()
            stored_sl = meta.get("storyline")
            if isinstance(stored_sl, list) and stored_sl:
                builder.ctx.storyline = [
                    StorylineSection.from_dict(s) for s in stored_sl if isinstance(s, dict)
                ]
            else:
                builder.resolve_storyline()
            sources = builder.build_sources()
        except Exception:
            # Fall back to last persisted snapshot if recompute fails.
            sources = meta.get("sources") or {}

    return {"success": True, "report_type": report_type, "sources": sources}
