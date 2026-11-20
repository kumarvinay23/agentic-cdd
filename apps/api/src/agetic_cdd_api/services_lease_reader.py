"""Fix 7 — lease / contract PDF reader with page bbox lineage.

Reads annual contractual rent from lease PDFs (native text or OCR/page image)
and emits ontology facts with ``source_location.bbox``. Unreadable files return
an empty fact list plus a status reason — never invent zero rent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from agetic_cdd_api.services_fact_repository import Fact
from agetic_cdd_api.services_statement_reader import SourceLocation, _loc

_RENT_PATTERNS = (
    re.compile(
        r"(?i)(?:annual(?:ly)?|per year|yearly)\s*(?:rent|base rent)?[^\d$]{0,24}"
        r"\$\s*([\d,]+(?:\.\d+)?)"
    ),
    re.compile(
        r"(?i)\$\s*([\d,]+(?:\.\d+)?)\s*(?:per year|/year|annually|per annum)"
    ),
    re.compile(
        r"(?i)(?:base rent|annual rent|minimum rent)[^\d$]{0,32}"
        r"\$\s*([\d,]+(?:\.\d+)?)"
    ),
)


def read_lease_document(
    path: Path | str,
    *,
    doc_id: str,
    currency: str = "USD",
    period_end: str | None = None,
) -> tuple[list[Fact], dict[str, SourceLocation]]:
    """Extract lease.rent_contractual (and optional term) with bbox lineage."""
    path = Path(path)
    locs: dict[str, SourceLocation] = {}
    pages = _lease_pages(path)
    if not pages:
        return [], locs

    hit = _find_rent(pages)
    if hit is None:
        return [], locs

    page_no, text, bbox, raw, method = hit
    amount = _to_currency_units(raw)
    if amount is None:
        return [], locs

    lid = _loc(
        locs,
        doc_id,
        f"page {page_no}",
        f"p{page_no}",
        "annual rent",
        "contractual",
        raw,
        steps=["lease_reader"],
        method=method,
        bbox=bbox,
    )
    end = period_end or "2025-12-31"
    facts = [
        Fact(
            "lease.rent_contractual",
            amount,
            "CURRENCY",
            "FY",
            end[:4] + "-01-01",
            end,
            12,
            "ACTUAL",
            {},
            doc_id,
            "B",
            [lid],
            status="SELECTED",
            currency=currency or "USD",
            mapping={"extraction": method, "file": path.name},
        )
    ]
    term = _find_term(pages)
    if term is not None:
        t_page, t_text, t_bbox, years, t_method = term
        t_lid = _loc(
            locs,
            doc_id,
            f"page {t_page}",
            f"p{t_page}",
            "lease term",
            "years",
            str(years),
            steps=["lease_reader"],
            method=t_method,
            bbox=t_bbox,
        )
        facts.append(
            Fact(
                "lease.term_years",
                float(years),
                "YEARS",
                "AS_AT",
                None,
                end,
                0,
                "ACTUAL",
                {},
                doc_id,
                "B",
                [t_lid],
                status="SELECTED",
                mapping={"extraction": t_method, "file": path.name},
            )
        )
    return facts, locs


def lease_status_reason(facts: list[Fact], *, attempted: bool) -> str | None:
    """Honest register reason when lease read yields no publishable rent."""
    if facts:
        return None
    if attempted:
        return "PARTIAL — lease PDF readable but contractual rent not extracted"
    return "FAILED — unreadable lease / no OCR text"


def extract_evidenced_rent_m(path: Path | str) -> tuple[float | None, str | None, list[float] | None]:
    """Deck helper — annual rent in $m, label, and bbox when found."""
    path = Path(path)
    pages = _lease_pages(path)
    hit = _find_rent(pages) if pages else None
    if hit is None:
        return None, None, None
    _page, _text, bbox, raw, _method = hit
    amount = _to_currency_units(raw)
    if amount is None:
        return None, None, bbox
    return amount / 1_000_000.0, path.name[:40], bbox


def _lease_pages(path: Path) -> list[dict[str, Any]]:
    """Return [{page, text, bbox, method}, ...] using PyMuPDF + OCR fallback."""
    try:
        import fitz
    except Exception:
        return _lease_pages_pypdf(path)

    out: list[dict[str, Any]] = []
    try:
        with fitz.open(path) as pdf:
            for index, page in enumerate(pdf):
                blocks = []
                for block in page.get_text("blocks") or []:
                    if len(block) < 5:
                        continue
                    text = " ".join(str(block[4]).split())
                    if not text:
                        continue
                    rect = fitz.Rect(block[0], block[1], block[2], block[3])
                    blocks.append(
                        {
                            "page": index + 1,
                            "text": text,
                            "bbox": _norm_bbox(page, rect),
                            "method": "PDF_TEXT",
                        }
                    )
                if sum(len(b["text"]) for b in blocks) <= 12:
                    from agetic_cdd_api.services_document_graph import ocr_image

                    for item in page.get_images(full=True) or []:
                        try:
                            info = pdf.extract_image(item[0])
                        except Exception:
                            continue
                        blob = info.get("image") if isinstance(info, dict) else None
                        text = ocr_image(blob) if blob else ""
                        if not text:
                            continue
                        bbox = [0.05, 0.05, 0.95, 0.95]
                        try:
                            rects = page.get_image_rects(item[0]) if hasattr(page, "get_image_rects") else []
                            if rects:
                                bbox = _norm_bbox(page, rects[0])
                        except Exception:
                            pass
                        blocks.append(
                            {
                                "page": index + 1,
                                "text": text,
                                "bbox": bbox,
                                "method": "PAGE_IMAGE",
                            }
                        )
                out.extend(blocks)
    except Exception:
        return _lease_pages_pypdf(path)
    return out


def _lease_pages_pypdf(path: Path) -> list[dict[str, Any]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        out = []
        for index, page in enumerate(reader.pages[:12]):
            text = " ".join((page.extract_text() or "").split())
            if text:
                out.append(
                    {
                        "page": index + 1,
                        "text": text,
                        "bbox": [0.0, 0.0, 1.0, 1.0],
                        "method": "PDF_TEXT",
                    }
                )
        return out
    except Exception:
        return []


def _norm_bbox(page: Any, rect: Any) -> list[float]:
    try:
        w = float(page.rect.width) or 1.0
        h = float(page.rect.height) or 1.0
        x0 = max(0.0, min(1.0, float(rect.x0) / w))
        y0 = max(0.0, min(1.0, float(rect.y0) / h))
        x1 = max(0.0, min(1.0, float(rect.x1) / w))
        y1 = max(0.0, min(1.0, float(rect.y1) / h))
        if x1 <= x0:
            x1 = min(1.0, x0 + 0.02)
        if y1 <= y0:
            y1 = min(1.0, y0 + 0.02)
        return [round(x0, 6), round(y0, 6), round(x1, 6), round(y1, 6)]
    except Exception:
        return [0.0, 0.0, 1.0, 1.0]


def _find_rent(pages: list[dict[str, Any]]) -> tuple[int, str, list[float], str, str] | None:
    for block in pages:
        text = block.get("text") or ""
        for pattern in _RENT_PATTERNS:
            m = pattern.search(text)
            if m:
                return (
                    int(block["page"]),
                    text,
                    list(block.get("bbox") or [0.0, 0.0, 1.0, 1.0]),
                    m.group(1),
                    str(block.get("method") or "PDF_TEXT"),
                )
    return None


def _find_term(pages: list[dict[str, Any]]) -> tuple[int, str, list[float], float, str] | None:
    term_re = re.compile(r"(?i)(?:term|initial term|lease term)[^\d]{0,24}(\d{1,2})\s*(?:years?|yrs?)")
    for block in pages:
        text = block.get("text") or ""
        m = term_re.search(text)
        if m:
            return (
                int(block["page"]),
                text,
                list(block.get("bbox") or [0.0, 0.0, 1.0, 1.0]),
                float(m.group(1)),
                str(block.get("method") or "PDF_TEXT"),
            )
    return None


def _to_currency_units(raw: str) -> float | None:
    try:
        value = float(str(raw).replace(",", ""))
    except ValueError:
        return None
    if value < 0:
        return None
    # Store absolute currency units (not $m).
    return value
