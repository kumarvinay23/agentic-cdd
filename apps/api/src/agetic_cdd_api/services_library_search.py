"""Per-deal SQLite FTS5 index over library chunks (BM25 lexical retrieval)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_library import load_library_document, load_library_index
from agetic_cdd_api.services_library_chunks import build_document_chunks
from agetic_cdd_api.services_vdr import library_dir

_TOKEN = re.compile(r"[a-z0-9%]{3,}")
_SNIPPET_LEN = 480


def search_db_path(deal: Deal) -> Path:
    return library_dir(deal) / "search.db"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS search_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS chunks (
            rowid INTEGER PRIMARY KEY,
            chunk_id TEXT NOT NULL UNIQUE,
            filename TEXT NOT NULL,
            cdl_category TEXT NOT NULL,
            cdl_secondary TEXT,
            chunk_index INTEGER NOT NULL,
            kind TEXT,
            label TEXT,
            text TEXT NOT NULL
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            text,
            filename UNINDEXED,
            cdl_category UNINDEXED,
            content='chunks',
            content_rowid='rowid',
            tokenize='unicode61'
        );
        """
    )


def _fts_query(text: str) -> str | None:
    tokens = list(dict.fromkeys(_TOKEN.findall((text or "").lower())))[:14]
    if not tokens:
        return None
    return " OR ".join(f'"{token}"' for token in tokens)


def rebuild_search_index(deal: Deal, *, index: dict | None = None) -> dict[str, Any]:
    """Rebuild FTS index from library documents (chunks at ingest or on-the-fly)."""
    index = index or load_library_index(deal)
    if not index:
        return {"chunk_count": 0, "document_count": 0}

    path = search_db_path(deal)
    if path.is_file():
        path.unlink()

    conn = _connect(path)
    try:
        _init_schema(conn)
        conn.execute("DELETE FROM chunks")
        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('delete-all')")

        total_chunks = 0
        for entry in index.get("documents") or []:
            if not isinstance(entry, dict):
                continue
            if entry.get("status") != "ready":
                continue
            filename = str(entry.get("filename") or "")
            if not filename:
                continue
            payload = load_library_document(deal, filename) or {}
            chunks = payload.get("chunks")
            if not isinstance(chunks, list) or not chunks:
                chunks = build_document_chunks(
                    str(payload.get("text") or entry.get("excerpt") or ""),
                    tables=list(payload.get("tables") or []),
                )
            cdl_category = str(entry.get("cdl_category") or "deal_strategy")
            cdl_secondary = entry.get("cdl_secondary")
            for chunk in chunks:
                if not isinstance(chunk, dict):
                    continue
                text = str(chunk.get("text") or "").strip()
                if len(text) < 40:
                    continue
                chunk_index = int(chunk.get("id") or total_chunks)
                chunk_id = f"{filename}::{chunk_index}"
                conn.execute(
                    """
                    INSERT INTO chunks
                        (chunk_id, filename, cdl_category, cdl_secondary, chunk_index, kind, label, text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        filename,
                        cdl_category,
                        cdl_secondary,
                        chunk_index,
                        chunk.get("kind"),
                        chunk.get("label"),
                        text,
                    ),
                )
                total_chunks += 1

        conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
        generated_at = str(index.get("generated_at") or "")
        conn.execute(
            "INSERT OR REPLACE INTO search_meta(key, value) VALUES ('generated_at', ?)",
            (generated_at,),
        )
        conn.execute(
            "INSERT OR REPLACE INTO search_meta(key, value) VALUES ('chunk_count', ?)",
            (str(total_chunks),),
        )
        conn.commit()
        return {
            "chunk_count": total_chunks,
            "document_count": index.get("document_count", 0),
            "generated_at": generated_at,
        }
    finally:
        conn.close()


def ensure_search_index(deal: Deal, *, index: dict | None = None) -> None:
    """Build search.db when missing or stale vs library index."""
    index = index or load_library_index(deal)
    if not index:
        return
    generated_at = str(index.get("generated_at") or "")
    path = search_db_path(deal)
    if not path.is_file():
        rebuild_search_index(deal, index=index)
        return
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT value FROM search_meta WHERE key = 'generated_at'"
        ).fetchone()
        if row is None or str(row["value"]) != generated_at:
            conn.close()
            rebuild_search_index(deal, index=index)
    finally:
        if conn:
            conn.close()


def search_index_stats(deal: Deal) -> dict[str, Any]:
    """Read FTS index metadata for health checks and re-ingest reports."""
    path = search_db_path(deal)
    if not path.is_file():
        return {"chunk_count": 0, "fts_ready": False, "search_db": str(path)}
    conn = _connect(path)
    try:
        meta = {
            str(row["key"]): str(row["value"])
            for row in conn.execute("SELECT key, value FROM search_meta")
        }
        row = conn.execute("SELECT COUNT(*) AS c FROM chunks").fetchone()
        chunk_count = int(row["c"]) if row else int(meta.get("chunk_count") or 0)
        return {
            "chunk_count": chunk_count,
            "fts_ready": chunk_count > 0,
            "generated_at": meta.get("generated_at"),
            "search_db": str(path),
        }
    finally:
        conn.close()


def search_library_chunks(
    deal: Deal,
    *,
    query: str,
    categories: set[str] | None = None,
    limit: int = 24,
    index: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Two-stage lexical search: prefer CDL categories, widen if recall is low.
    Returns chunk hits sorted by BM25 rank (lower is better in sqlite bm25()).
    """
    index = index or load_library_index(deal)
    if not index:
        return []
    ensure_search_index(deal, index=index)
    path = search_db_path(deal)
    if not path.is_file():
        return []

    match = _fts_query(query)
    if not match:
        return []

    hits = _fts_search(path, match=match, categories=categories, limit=limit)
    if len(hits) < 3 and categories:
        hits = _fts_search(path, match=match, categories=None, limit=limit)
        preferred = categories
        for row in hits:
            if row.get("cdl_category") in preferred:
                row["rank"] = float(row.get("rank") or 0) - 2.0
        hits.sort(key=lambda item: float(item.get("rank") or 0))
    return hits


def _fts_search(
    path: Path,
    *,
    match: str,
    categories: set[str] | None,
    limit: int,
) -> list[dict[str, Any]]:
    conn = _connect(path)
    try:
        if categories:
            placeholders = ",".join("?" for _ in categories)
            sql = f"""
                SELECT c.chunk_id, c.filename, c.cdl_category, c.label, c.kind, c.text,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                  AND c.cdl_category IN ({placeholders})
                ORDER BY rank
                LIMIT ?
            """
            params: list[Any] = [match, *sorted(categories), limit]
        else:
            sql = """
                SELECT c.chunk_id, c.filename, c.cdl_category, c.label, c.kind, c.text,
                       bm25(chunks_fts) AS rank
                FROM chunks_fts
                JOIN chunks c ON c.rowid = chunks_fts.rowid
                WHERE chunks_fts MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            params = [match, limit]
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def chunk_index_from_id(chunk_id: str | None) -> int | None:
    if not chunk_id or "::" not in str(chunk_id):
        return None
    try:
        return int(str(chunk_id).rsplit("::", 1)[-1])
    except ValueError:
        return None


def citation_from_hit(hit: dict[str, Any], excerpt: str) -> dict[str, Any]:
    chunk_id = str(hit.get("chunk_id") or "")
    return {
        "chunk_id": chunk_id or None,
        "chunk_index": chunk_index_from_id(chunk_id),
        "label": hit.get("label"),
        "kind": hit.get("kind"),
        "excerpt": excerpt,
    }


def citation_meta_for_source(src: dict[str, Any]) -> dict[str, Any]:
    """Primary section/chunk hints for a grouped internal source row."""
    citations = list(src.get("citations") or [])
    chunk_ids = [str(c) for c in (src.get("chunk_ids") or []) if c]
    section_label: str | None = None
    chunk_index: int | None = None
    for cite in citations:
        if not section_label and cite.get("label"):
            section_label = str(cite["label"])
        if chunk_index is None and cite.get("chunk_index") is not None:
            chunk_index = int(cite["chunk_index"])
    if section_label is None and src.get("section_label"):
        section_label = str(src["section_label"])
    if chunk_index is None and src.get("chunk_index") is not None:
        chunk_index = int(src["chunk_index"])
    return {
        "chunk_ids": chunk_ids,
        "section_label": section_label,
        "chunk_index": chunk_index,
    }


def format_citation_hint(meta: dict[str, Any] | None) -> str | None:
    if not meta:
        return None
    parts: list[str] = []
    label = meta.get("section_label")
    if label:
        parts.append(str(label))
    chunk_index = meta.get("chunk_index")
    if chunk_index is not None:
        parts.append(f"chunk {int(chunk_index) + 1}")
    return " · ".join(parts) if parts else None


def group_chunks_as_sources(
    hits: list[dict[str, Any]],
    *,
    limit: int = 6,
    passages_per_doc: int = 5,
    snippet_len: int = _SNIPPET_LEN,
) -> list[dict[str, Any]]:
    """Group chunk hits into DiligenceIQ-shaped internal source rows."""
    by_file: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for hit in hits:
        filename = str(hit.get("filename") or "")
        if not filename:
            continue
        text = str(hit.get("text") or "").strip()
        if not text:
            continue
        if filename not in by_file:
            by_file[filename] = {
                "origin": "internal",
                "title": filename,
                "snippet": text[:snippet_len],
                "passages": [],
                "cdl_category": hit.get("cdl_category"),
                "chunk_ids": [],
                "citations": [],
            }
            order.append(filename)
        row = by_file[filename]
        if len(row["passages"]) >= passages_per_doc:
            continue
        clipped = text[:snippet_len]
        if clipped not in row["passages"]:
            row["passages"].append(clipped)
            cite = citation_from_hit(hit, clipped)
            row["chunk_ids"].append(cite.get("chunk_id"))
            row["citations"].append(cite)
    out: list[dict[str, Any]] = []
    for filename in order:
        if len(out) >= limit:
            break
        row = by_file[filename]
        if not row["passages"]:
            continue
        row["snippet"] = row["passages"][0]
        cite_meta = citation_meta_for_source(row)
        row["section_label"] = cite_meta.get("section_label")
        row["chunk_index"] = cite_meta.get("chunk_index")
        out.append(row)
    return out
