"""Chunk VDR document text at ingest for lexical retrieval."""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")
_HEADING = re.compile(r"^(?:#{1,3}\s+|[A-Z][A-Z0-9 /&\-]{4,})\s*$")

TARGET_CHARS = 900
OVERLAP_CHARS = 120
MIN_CHUNK_CHARS = 80
TABLE_ROWS_PER_CHUNK = 10


def _clean(text: str) -> str:
    return _WHITESPACE.sub(" ", (text or "").strip())


def _paragraphs(text: str) -> list[str]:
    raw = (text or "").replace("\r\n", "\n")
    parts = [p.strip() for p in re.split(r"\n\s*\n+", raw) if p.strip()]
    if parts:
        return parts
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _split_long_paragraph(paragraph: str, *, target: int, overlap: int) -> list[str]:
    cleaned = _clean(paragraph)
    if len(cleaned) <= target:
        return [cleaned] if cleaned else []
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    out: list[str] = []
    buf: list[str] = []
    size = 0
    for sent in sentences:
        if not sent:
            continue
        if size + len(sent) + 1 > target and buf:
            out.append(_clean(" ".join(buf)))
            tail = _clean(" ".join(buf))[-overlap:]
            buf = [tail, sent] if tail else [sent]
            size = sum(len(x) for x in buf) + max(0, len(buf) - 1)
        else:
            buf.append(sent)
            size += len(sent) + (1 if buf else 0)
    if buf:
        out.append(_clean(" ".join(buf)))
    return [part for part in out if len(part) >= MIN_CHUNK_CHARS or len(out) == 1]


def _table_chunks(tables: list[dict] | None) -> list[dict]:
    out: list[dict] = []
    for table in tables or []:
        if not isinstance(table, dict):
            continue
        name = str(table.get("name") or "table")
        rows = table.get("rows") or []
        if not isinstance(rows, list) or not rows:
            continue
        for i in range(0, len(rows), TABLE_ROWS_PER_CHUNK):
            block = rows[i : i + TABLE_ROWS_PER_CHUNK]
            lines = [" | ".join(str(cell) for cell in row) for row in block if isinstance(row, list)]
            text = _clean(" ".join(lines))
            if len(text) < MIN_CHUNK_CHARS and len(text) < 20:
                continue
            out.append(
                {
                    "kind": "table",
                    "label": name,
                    "text": text[:2400],
                }
            )
    return out


def build_document_chunks(
    text: str,
    *,
    tables: list[dict] | None = None,
    target_chars: int = TARGET_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[dict]:
    """Split document body + tables into retrieval-sized chunks."""
    chunks: list[dict] = []
    current_label: str | None = None

    for paragraph in _paragraphs(text):
        if _HEADING.match(paragraph.strip()):
            current_label = _clean(paragraph.strip("# ").strip())
            continue
        for piece in _split_long_paragraph(paragraph, target=target_chars, overlap=overlap_chars):
            if len(piece) < MIN_CHUNK_CHARS and chunks:
                continue
            chunks.append(
                {
                    "kind": "body",
                    "label": current_label,
                    "text": piece,
                }
            )

    if not chunks and text.strip():
        fallback = _clean(text)
        if fallback:
            chunks.append({"kind": "body", "label": None, "text": fallback[:target_chars * 2]})

    for table_chunk in _table_chunks(tables):
        chunks.append(table_chunk)

    numbered: list[dict] = []
    for idx, chunk in enumerate(chunks):
        numbered.append(
            {
                "id": str(idx),
                "kind": chunk.get("kind") or "body",
                "label": chunk.get("label"),
                "text": str(chunk.get("text") or ""),
            }
        )
    return numbered
