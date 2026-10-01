"""VDR file storage for dealrooms."""

from __future__ import annotations

import json
import re
from pathlib import Path

import anyio
from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_deals import ensure_deal_folder
from agetic_cdd_api.services_ingestion import (
    index_docs,
    loads_docs,
    merge_doc_from_disk,
    new_doc_record,
    utc_now_iso,
)


def _safe_name(filename: str) -> str:
    """Sanitize a document name; reject path separators and traversal attempts."""
    raw = str(filename).strip()
    if not raw or raw in {".", ".."} or "/" in raw or "\\" in raw or raw != Path(raw).name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    name = re.sub(r"[^\w.\- ()\[\]]+", "_", raw).strip(" .")
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    return name


def documents_dir(deal: Deal) -> Path:
    root = ensure_deal_folder(deal.slug)
    docs = root / "documents"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


def library_dir(deal: Deal) -> Path:
    root = ensure_deal_folder(deal.slug)
    lib = root / "library"
    lib.mkdir(parents=True, exist_ok=True)
    return lib


def resolved_document_path(deal: Deal, filename: str) -> Path:
    """Resolve a document path and ensure it stays inside the deal documents folder.

    Rejects path separators / traversal in ``filename`` via ``_safe_name``, then
    verifies the resolved absolute path is still under ``documents/``.
    """
    docs = documents_dir(deal).resolve()
    path = (docs / _safe_name(filename)).resolve()
    if hasattr(path, "is_relative_to"):
        if not path.is_relative_to(docs):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename")
    else:  # pragma: no cover - Python < 3.9
        try:
            path.relative_to(docs)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid filename",
            ) from exc
    return path


def list_vdr_docs(deal: Deal) -> list[dict]:
    return loads_docs(deal.vdr_docs_json)


def _persist_docs(db: Session, deal: Deal, docs: list[dict]) -> Deal:
    deal.vdr_docs_json = json.dumps(docs)
    deal.docs_count = len(docs)
    deal.vdr_bytes = sum(int(d.get("size") or 0) for d in docs)
    if deal.docs_count > 0 and deal.status == "not-started":
        deal.status = "active"
    db.commit()
    db.refresh(deal)
    return deal


def scan_vdr_docs(deal: Deal, *, existing_json: str | None = None) -> list[dict]:
    """Filesystem scan merged with persisted document metadata."""
    previous = index_docs(loads_docs(existing_json or deal.vdr_docs_json))
    docs_path = documents_dir(deal)
    docs: list[dict] = []
    for path in sorted(docs_path.iterdir()):
        if path.is_file() and not path.name.startswith("."):
            docs.append(
                merge_doc_from_disk(
                    filename=path.name,
                    size=path.stat().st_size,
                    previous=previous.get(path.name),
                )
            )
    return docs


def sync_vdr_from_disk(db: Session, deal: Deal) -> Deal:
    return _persist_docs(db, deal, scan_vdr_docs(deal))


async def sync_vdr_from_disk_async(db: Session, deal: Deal) -> Deal:
    docs = await anyio.to_thread.run_sync(scan_vdr_docs, deal)
    return _persist_docs(db, deal, docs)


_UPLOAD_CHUNK = 1024 * 1024


async def _stream_upload_to_path(file: UploadFile, dest: Path) -> int:
    """Write an upload in chunks to avoid holding multi-GB zips in memory."""
    size = 0

    def _open_wb(path: Path):
        return path.open("wb")

    handle = await anyio.to_thread.run_sync(_open_wb, dest)
    try:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK)
            if not chunk:
                break
            size += len(chunk)
            await anyio.to_thread.run_sync(handle.write, chunk)
    finally:
        await anyio.to_thread.run_sync(handle.close)
    return size


def _unlink_if_file(path: Path) -> None:
    if path.is_file():
        path.unlink()


async def upload_vdr_file(db: Session, deal: Deal, file: UploadFile) -> Deal:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename required")
    dest = resolved_document_path(deal, file.filename)
    await _stream_upload_to_path(file, dest)

    # Zip packs expand into extractable VDR members before the library indexes them.
    if dest.suffix.lower() == ".zip":
        from agetic_cdd_api.services_zip_expand import expand_zip_into_vdr

        await anyio.to_thread.run_sync(
            lambda: expand_zip_into_vdr(deal, dest.name, remove_archive=True)
        )

    existing = loads_docs(deal.vdr_docs_json)
    by_name = index_docs(existing)
    now = utc_now_iso()
    for path in documents_dir(deal).iterdir():
        if not path.is_file() or path.name.startswith("."):
            continue
        if path.name not in by_name:
            by_name[path.name] = new_doc_record(
                filename=path.name,
                size=path.stat().st_size,
                uploaded_at=now,
            )
    merged = scan_vdr_docs(deal, existing_json=json.dumps(list(by_name.values())))
    return _persist_docs(db, deal, merged)


def vdr_file_for_download(deal: Deal, filename: str) -> Path:
    path = resolved_document_path(deal, filename)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return path


async def delete_vdr_file(db: Session, deal: Deal, filename: str) -> Deal:
    path = resolved_document_path(deal, filename)
    await anyio.to_thread.run_sync(_unlink_if_file, path)
    return await sync_vdr_from_disk_async(db, deal)


def save_docs(db: Session, deal: Deal, docs: list[dict]) -> Deal:
    return _persist_docs(db, deal, docs)


def vdr_health(deal: Deal) -> dict:
    docs = list_vdr_docs(deal)
    ready = sum(1 for d in docs if d.get("status") == "ready")
    return {
        "ok": True,
        "portfolio": deal.id,
        "engine_reachable": True,
        "has_data_room": True,
        "vdr_synced": True,
        "vdr_files": len(docs),
        "ready_files": ready,
    }
