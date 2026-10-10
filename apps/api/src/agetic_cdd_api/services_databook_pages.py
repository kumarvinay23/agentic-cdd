"""Phase 2 — page register (S1-1) and unread / image honesty (S1-4, S1-5).

Classifies each PDF page or spreadsheet sheet as text / scan / mixed / image /
blank without requiring OCR. Scanned and image-only pages are marked unread
so Findings can surface gaps instead of inventing statement rows.

G3 adds financial page classes (IS / BS / CF / equity / note / EBITDA bridge)
and statement routing helpers used at extract time.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_databook_models import (
    DealLike,
    PageClass,
    PageKind,
    PageRegister,
    PageRegisterEntry,
    StatementSource,
)
from agetic_cdd_api.services_databook_store import save_page_register
from agetic_cdd_api.services_ingestion import utc_now_iso
from agetic_cdd_api.services_library import load_library_document, load_library_index

logger = logging.getLogger(__name__)

_IMAGE_SUFFIX = re.compile(r"(?i)\.(png|jpe?g|gif|webp|tiff?|bmp)$")
_UNREAD_KINDS = frozenset({PageKind.SCAN, PageKind.IMAGE, PageKind.BLANK})


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r — using default %s", name, raw, default)
        return default


# Tunable for extractors that emit denser/sparser page text (DATABOOK_PAGE_*).
_BLANK_CHAR_MAX = _env_int("DATABOOK_PAGE_BLANK_CHAR_MAX", 12)
_SCAN_CHAR_MAX = _env_int("DATABOOK_PAGE_SCAN_CHAR_MAX", 80)


def _is_weak_statement(label: str | None) -> bool:
    if not label:
        return True
    return label.strip().lower() in {"table", "financials"}


# "Notes to …" wins over embedded statement titles (e.g. Notes to Statement of Changes in Equity).
_NOTE_PREFIX_RE = re.compile(r"(?i)\bnotes?\s+to\b")

_PAGE_CLASS_RULES: list[tuple[re.Pattern[str], PageClass, float, str]] = [
    (
        re.compile(r"(?i)\b(?:ebitda\s*bridge|bridge\s*to\s*ebitda)\b"),
        PageClass.EBITDA_BRIDGE,
        0.95,
        "ebitda_bridge phrase",
    ),
    # NOTE before EQUITY/IS/BS so "Notes to the … Statement …" stays a note.
    (
        re.compile(
            r"(?i)\b(?:notes?\s*to\s*(?:the\s*)?(?:financial\s*)?statements?|accounting\s*policies)\b"
        ),
        PageClass.NOTE,
        0.96,
        "notes phrase",
    ),
    (
        re.compile(
            r"(?i)\b(?:statement\s*of\s*changes?\s*in\s*(?:equity|shareholders?['']?\s*equity))\b"
        ),
        PageClass.EQUITY,
        0.95,
        "equity statement phrase",
    ),
    (
        re.compile(
            r"(?i)\b(?:p\s*&\s*l|pnl|income\s*statement|profit\s*(?:and|&)\s*loss)\b"
        ),
        PageClass.INCOME_STATEMENT,
        0.92,
        "income statement phrase",
    ),
    (
        re.compile(r"(?i)\b(?:balance\s*sheet|statement\s*of\s*financial\s*position)\b"),
        PageClass.BALANCE_SHEET,
        0.92,
        "balance sheet phrase",
    ),
    (
        re.compile(r"(?i)\b(?:cash\s*flow|statement\s*of\s*cash\s*flows?)\b"),
        PageClass.CASH_FLOW,
        0.92,
        "cash flow phrase",
    ),
    (
        re.compile(r"(?i)\b(?:kpi|operating\s*metrics|key\s*metrics|unit\s*economics)\b"),
        PageClass.KPI,
        0.85,
        "kpi phrase",
    ),
]

# Token boundaries include digits/dots so Sheet_IS_12 / IS12 / BS.1 match.
_SHEET_BOUND = r"(?:^|[_\s.-]|(?<=\d))"
_SHEET_END = r"(?:$|[_\s.-]|(?=\d))"
_SHEET_SHORTCUTS: list[tuple[re.Pattern[str], PageClass, float]] = [
    (
        re.compile(rf"(?i){_SHEET_BOUND}p\s*&\s*l{_SHEET_END}|{_SHEET_BOUND}pnl{_SHEET_END}"),
        PageClass.INCOME_STATEMENT,
        0.88,
    ),
    (re.compile(rf"(?i){_SHEET_BOUND}is{_SHEET_END}"), PageClass.INCOME_STATEMENT, 0.82),
    (re.compile(rf"(?i){_SHEET_BOUND}bs{_SHEET_END}"), PageClass.BALANCE_SHEET, 0.82),
    (re.compile(rf"(?i){_SHEET_BOUND}cf{_SHEET_END}"), PageClass.CASH_FLOW, 0.82),
    (re.compile(rf"(?i){_SHEET_BOUND}pl{_SHEET_END}"), PageClass.INCOME_STATEMENT, 0.78),
]


@dataclass(frozen=True, slots=True)
class PageClassHit:
    page_class: PageClass
    confidence: float
    source: StatementSource
    notes: tuple[str, ...] = ()


def classify_text_to_page_class(text: str) -> PageClassHit:
    """Best-effort financial page class from free text / table title band."""
    blob = (text or "").strip()
    if not blob:
        return PageClassHit(PageClass.UNKNOWN, 0.0, "inferred")
    # Contextual pre-check: "Notes to …" beats an embedded statement title.
    if _NOTE_PREFIX_RE.search(blob):
        return PageClassHit(PageClass.NOTE, 0.97, "table_name", ("notes-to prefix",))
    best: PageClassHit | None = None
    for pattern, cls, score, note in _PAGE_CLASS_RULES:
        if pattern.search(blob):
            hit = PageClassHit(cls, score, "table_name", (note,))
            if best is None or hit.confidence > best.confidence:
                best = hit
    if best is not None:
        return best
    return PageClassHit(PageClass.UNKNOWN, 0.0, "inferred")


def classify_sheet_name(name: str) -> PageClassHit | None:
    """Sheet-name shortcuts when title band is silent."""
    blob = (name or "").strip()
    if not blob:
        return None
    for pattern, cls, score in _SHEET_SHORTCUTS:
        if pattern.search(blob):
            return PageClassHit(cls, score, "sheet_name", ("sheet shortcut",))
    return classify_text_to_page_class(blob) if blob else None


def page_class_to_statement(page_class: PageClass | None) -> str | None:
    """Map page class → statement label for CoA section gate."""
    if page_class is None or page_class == PageClass.UNKNOWN:
        return None
    mapping: dict[PageClass, str | None] = {
        PageClass.INCOME_STATEMENT: "income_statement",
        PageClass.BALANCE_SHEET: "balance_sheet",
        PageClass.CASH_FLOW: "cash_flow",
        PageClass.EQUITY: "equity",
        PageClass.NOTE: "note",
        PageClass.EBITDA_BRIDGE: "ebitda_bridge",
        PageClass.KPI: "kpi",
        PageClass.OTHER: None,
        PageClass.UNKNOWN: None,
    }
    return mapping.get(page_class)


def classify_table_class(
    *,
    table_name: str,
    title_band: str = "",
    page_class_hint: PageClass | None = None,
) -> PageClassHit:
    """Classify a table from its name + optional header band / page hint."""
    blob = " ".join(p for p in (table_name, title_band) if p).strip()
    hit = classify_text_to_page_class(blob)
    if hit.page_class != PageClass.UNKNOWN:
        return hit
    if page_class_hint and page_class_hint != PageClass.UNKNOWN:
        return PageClassHit(page_class_hint, 0.65, "page_class", ("page register hint",))
    sheet_hit = classify_sheet_name(table_name)
    if sheet_hit is not None and sheet_hit.page_class != PageClass.UNKNOWN:
        return sheet_hit
    return PageClassHit(PageClass.UNKNOWN, 0.0, "inferred")


def lookup_page_entry(
    register: PageRegister | None,
    *,
    filename: str,
    page: int | None,
) -> PageRegisterEntry | None:
    """Find a page-register row by filename + 1-based page/sheet index."""
    if register is None or page is None or page < 1:
        return None
    for entry in register.entries:
        if entry.filename == filename and entry.page == page:
            return entry
    return None


def resolve_statement_label(
    *,
    header_statement: str | None,
    page_class: PageClass | None = None,
    table_class: PageClass | None = None,
) -> tuple[str | None, StatementSource, bool]:
    """Pick statement label for CoA routing; flag header vs page-class mismatch."""
    table_stmt = page_class_to_statement(table_class)
    page_stmt = page_class_to_statement(page_class)
    routed = table_stmt or page_stmt
    header = (header_statement or "").strip() or None

    if _is_weak_statement(header):
        if routed:
            source: StatementSource = (
                "page_class" if page_stmt and not table_stmt else "table_name"
            )
            return routed, source, False
        return header or "table", "inferred", False

    if routed and routed != header:
        return header, "table_header", True
    return header, "table_header", False


def _enrich_page_class(entry: PageRegisterEntry) -> PageRegisterEntry:
    """Stamp financial page_class from sheet_name only (not diagnostic notes)."""
    # Kind/OCR notes are human diagnostics — never feed them to financial regexes.
    if not entry.sheet_name:
        return entry
    hit = classify_sheet_name(entry.sheet_name)
    if hit is None or hit.page_class == PageClass.UNKNOWN:
        return entry
    return entry.model_copy(
        update={
            "page_class": hit.page_class,
            "page_class_source": hit.source,
            "page_class_confidence": hit.confidence,
            "page_class_notes": list(hit.notes),
        }
    )


def _deal_slug(deal: DealLike) -> str:
    return str(getattr(deal, "slug", None) or getattr(deal, "id", "") or "")


def _page_id(doc_id: str, page: int) -> str:
    return hashlib.sha1(f"{doc_id}|p{page}".encode()).hexdigest()[:14]


def classify_page_kind(
    *,
    char_count: int,
    has_images: bool,
    is_standalone_image: bool = False,
) -> tuple[PageKind, bool, list[str]]:
    """Return (kind, unread, notes)."""
    notes: list[str] = []
    if is_standalone_image:
        notes.append("Standalone image — OCR not available")
        return PageKind.IMAGE, True, notes
    if char_count <= _BLANK_CHAR_MAX and not has_images:
        notes.append("Blank or near-empty page")
        return PageKind.BLANK, True, notes
    if char_count <= _BLANK_CHAR_MAX and has_images:
        notes.append("Image-only page — OCR not available")
        return PageKind.IMAGE, True, notes
    if char_count <= _SCAN_CHAR_MAX and has_images:
        notes.append("Sparse text with images — treated as scan/mixed; OCR not available")
        return PageKind.MIXED, True, notes
    if char_count <= _SCAN_CHAR_MAX and not has_images:
        notes.append("Very little extractable text — possible scan without OCR")
        return PageKind.SCAN, True, notes
    if has_images:
        return PageKind.MIXED, False, notes
    return PageKind.TEXT, False, notes


def _page_meta_from_payload(
    *,
    filename: str,
    doc_id: str,
    payload: dict[str, Any],
) -> list[PageRegisterEntry]:
    """Build page entries from a library document payload."""
    out: list[PageRegisterEntry] = []
    pages_raw = payload.get("pages")
    if isinstance(pages_raw, list) and pages_raw:
        for item in pages_raw:
            if not isinstance(item, dict):
                continue
            try:
                page_no = int(item.get("page") or 0)
            except (TypeError, ValueError):
                continue
            if page_no < 1:
                continue
            char_count = int(item.get("char_count") or 0)
            has_images = bool(item.get("has_images"))
            kind_raw = str(item.get("kind") or "")
            try:
                kind = PageKind(kind_raw) if kind_raw else None
            except ValueError:
                kind = None
            if kind is None:
                kind, unread, notes = classify_page_kind(
                    char_count=char_count, has_images=has_images
                )
            else:
                unread = bool(item.get("unread"))
                notes = list(item.get("notes") or [])
                unread = unread or kind in _UNREAD_KINDS
            ocr = str(item.get("ocr_status") or "")
            if ocr not in {"not_needed", "not_available", "pending"}:
                ocr = "not_available" if unread else "not_needed"
            out.append(
                PageRegisterEntry(
                    page_id=_page_id(doc_id, page_no),
                    filename=filename,
                    doc_id=doc_id,
                    page=page_no,
                    kind=kind,
                    char_count=char_count,
                    has_images=has_images,
                    sheet_name=str(item["sheet_name"]) if item.get("sheet_name") else None,
                    ocr_status=ocr,  # type: ignore[arg-type]
                    unread=unread,
                    notes=notes,
                )
            )
        return out

    # Fallback: synthesize from page_count + aggregate text / tables
    try:
        page_count = int(payload.get("page_count") or 0)
    except (TypeError, ValueError):
        page_count = 0
    text = str(payload.get("text") or "")
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    error = str(payload.get("error") or "")
    is_image = bool(_IMAGE_SUFFIX.search(filename))
    if is_image:
        kind, unread, notes = classify_page_kind(
            char_count=0, has_images=True, is_standalone_image=True
        )
        out.append(
            PageRegisterEntry(
                page_id=_page_id(doc_id, 1),
                filename=filename,
                doc_id=doc_id,
                page=1,
                kind=kind,
                char_count=0,
                has_images=True,
                ocr_status="not_available",
                unread=True,
                notes=notes,
            )
        )
        return out

    if page_count <= 0:
        page_count = max(1, len(tables) or (1 if text.strip() else 0))
    if page_count <= 0:
        return out

    # Distribute char count evenly when per-page detail is absent
    per = max(0, len(text) // page_count) if page_count else 0
    scanned_hint = "ocr" in error.lower() or "scanned" in error.lower()
    for i in range(1, page_count + 1):
        sheet_name = None
        if i <= len(tables) and isinstance(tables[i - 1], dict):
            sheet_name = str(tables[i - 1].get("name") or "") or None
        char_count = per
        has_images = scanned_hint and per <= _SCAN_CHAR_MAX
        kind, unread, notes = classify_page_kind(
            char_count=char_count, has_images=has_images
        )
        if scanned_hint and kind == PageKind.TEXT and per <= _SCAN_CHAR_MAX:
            kind, unread = PageKind.SCAN, True
            notes = ["Parser reported no extractable text — scanned PDF requires OCR"]
        out.append(
            PageRegisterEntry(
                page_id=_page_id(doc_id, i),
                filename=filename,
                doc_id=doc_id,
                page=i,
                kind=kind,
                char_count=char_count,
                has_images=has_images,
                sheet_name=sheet_name,
                ocr_status="not_available" if unread else "not_needed",
                unread=unread,
                notes=notes,
            )
        )
    return out


def build_page_register(deal: Deal) -> PageRegister:
    """Scan the CDL library and persist a page register for the deal."""
    index = load_library_index(deal) or {}
    entries_raw = index.get("documents") if isinstance(index, dict) else None
    if not isinstance(entries_raw, list):
        entries_raw = []

    pages: list[PageRegisterEntry] = []
    for entry in entries_raw:
        if not isinstance(entry, dict):
            continue
        filename = str(entry.get("filename") or "")
        if not filename:
            continue
        doc_id = str(entry.get("library_stem") or filename)
        payload = load_library_document(deal, filename) or {}
        if not isinstance(payload, dict):
            payload = {}
        # Prefer payload filename when present
        pages.extend(
            _page_meta_from_payload(
                filename=str(payload.get("filename") or filename),
                doc_id=doc_id,
                payload=payload,
            )
        )

    counts: dict[str, Any] = {
        "total": len(pages),
        "unread": sum(1 for p in pages if p.unread),
        "by_kind": {},
    }
    by_kind: dict[str, int] = {}
    for p in pages:
        by_kind[p.kind.value] = by_kind.get(p.kind.value, 0) + 1
    counts["by_kind"] = by_kind

    enriched = [_enrich_page_class(p) for p in pages]
    by_class: dict[str, int] = {}
    for p in enriched:
        by_class[p.page_class.value] = by_class.get(p.page_class.value, 0) + 1
    counts["by_class"] = by_class

    register = PageRegister(
        deal_slug=_deal_slug(deal),
        generated_at=utc_now_iso(),
        entries=enriched,
        counts=counts,
    )
    try:
        save_page_register(deal, register)
    except Exception as exc:  # noqa: BLE001 — persist must not block register return
        logger.error(
            "Failed to save page register for %s: %s",
            _deal_slug(deal),
            exc,
            exc_info=True,
        )
    return register


def page_register_summary(register: PageRegister | None) -> dict[str, Any] | None:
    if register is None:
        return None
    by_class = dict(register.counts.get("by_class") or {})
    if not by_class:
        for e in register.entries:
            if e.page_class != PageClass.UNKNOWN:
                by_class[e.page_class.value] = by_class.get(e.page_class.value, 0) + 1
    return {
        "generated_at": register.generated_at,
        "counts": register.counts,
        "by_class": by_class,
        "page_class_sample": [
            {
                "filename": e.filename,
                "page": e.page,
                "page_class": e.page_class.value,
                "source": e.page_class_source,
                "sheet_name": e.sheet_name,
            }
            for e in register.entries
            if e.page_class != PageClass.UNKNOWN
        ][:12],
        "unread_sample": [
            {
                "filename": e.filename,
                "page": e.page,
                "kind": e.kind.value,
                "notes": e.notes[:2],
            }
            for e in register.entries
            if e.unread
        ][:12],
    }
