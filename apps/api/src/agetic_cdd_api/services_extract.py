"""Extract text and tables from VDR files. OCR is out of scope for this slice."""

from __future__ import annotations

import csv
from io import StringIO
from pathlib import Path

MAX_TEXT_CHARS = 80_000
MAX_TABLE_ROWS = 80
MAX_TABLES = 8


def _clip(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def extract_file(path: Path) -> dict:
    """Return {text, tables, page_count, parser, error} for a document on disk."""
    suffix = path.suffix.lower().lstrip(".")
    if not path.is_file():
        return {"text": "", "tables": [], "page_count": 0, "parser": "missing", "error": "File not found"}
    try:
        if suffix in {"txt", "md", "log"}:
            return _extract_text_file(path)
        if suffix == "csv":
            return _extract_csv(path)
        if suffix == "pdf":
            return _extract_pdf(path)
        if suffix == "docx":
            return _extract_docx(path)
        if suffix in {"xlsx", "xls"}:
            return _extract_xlsx(path)
        if suffix == "pptx":
            return _extract_pptx(path)
        return {
            "text": "",
            "tables": [],
            "page_count": 0,
            "parser": "unsupported",
            "error": f"No extractor for .{suffix}" if suffix else "Unknown format",
        }
    except Exception as exc:
        return {"text": "", "tables": [], "page_count": 0, "parser": suffix or "unknown", "error": str(exc)}


def _extract_text_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return {"text": _clip(raw), "tables": [], "page_count": 1, "parser": "text", "error": None}


def _extract_csv(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    rows: list[list[str]] = []
    reader = csv.reader(StringIO(raw))
    for i, row in enumerate(reader):
        if i >= MAX_TABLE_ROWS:
            break
        rows.append([str(cell) for cell in row])
    header = " ".join(rows[0]) if rows else ""
    sample = " ".join(" ".join(row) for row in rows[:12])
    return {
        "text": _clip(f"{header} {sample}"),
        "tables": [{"name": path.name, "rows": rows}] if rows else [],
        "page_count": 1,
        "parser": "csv",
        "error": None,
    }


def _extract_pdf(path: Path) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages[:40]:
        pages.append(page.extract_text() or "")
    text = _clip("\n".join(pages))
    error = None if text.strip() else "No extractable text (scanned PDF requires OCR)"
    return {"text": text, "tables": [], "page_count": len(reader.pages), "parser": "pypdf", "error": error}


def _extract_docx(path: Path) -> dict:
    from docx import Document

    doc = Document(str(path))
    paras = [p.text for p in doc.paragraphs if p.text.strip()]
    tables = []
    for i, table in enumerate(doc.tables[:MAX_TABLES]):
        rows = []
        for row in table.rows[:MAX_TABLE_ROWS]:
            rows.append([cell.text.strip() for cell in row.cells])
        tables.append({"name": f"table_{i + 1}", "rows": rows})
    return {
        "text": _clip("\n".join(paras)),
        "tables": tables,
        "page_count": max(1, len(doc.paragraphs) // 40),
        "parser": "python-docx",
        "error": None,
    }


def _extract_xlsx(path: Path) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    sheet_count = len(wb.worksheets)
    tables = []
    chunks: list[str] = []
    for sheet in wb.worksheets[:MAX_TABLES]:
        rows: list[list[str]] = []
        for i, row in enumerate(sheet.iter_rows(values_only=True)):
            if i >= MAX_TABLE_ROWS:
                break
            cells = ["" if cell is None else str(cell) for cell in row]
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append({"name": sheet.title, "rows": rows})
            chunks.append(sheet.title)
            chunks.append(" ".join(" ".join(r) for r in rows[:8]))
    wb.close()
    return {
        "text": _clip(" ".join(chunks)),
        "tables": tables,
        "page_count": sheet_count,
        "parser": "openpyxl",
        "error": None,
    }


def _extract_pptx(path: Path) -> dict:
    from pptx import Presentation

    pres = Presentation(str(path))
    texts: list[str] = []
    for slide in pres.slides:
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text:
                texts.append(shape.text)
    return {
        "text": _clip("\n".join(texts)),
        "tables": [],
        "page_count": len(pres.slides),
        "parser": "python-pptx",
        "error": None,
    }
