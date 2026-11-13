"""Read every document type into a graph of stable source locations.

A document is a content hash, then a page, slide, or sheet, then a block,
table, or cell. Part ids are derived from that content and location, so
renaming the file leaves them unchanged. A cross-reference such as
"see CIM p39" points at the target part and is not itself a source.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any

_PERIOD = re.compile(r"(?i)\bFY\s*(20\d{2})\b")
_YEAR = re.compile(r"\b(20\d{2})\b")
_TYPE_RULES = (
    ("deal_strategy", ("confidential information memorandum", " cim ", "cim ")),
    ("customer", ("customer",)),
    ("market_competition", ("competitor", "market size", "tam")),
    ("legal_esg", ("litigation", "permit", " nda")),
    ("operations", ("headcount", "facility", "fleet")),
    ("financial", ("revenue", "ebitda", "price", "p&l", "income")),
    ("company_management", ("management", "founder", "northwind")),
)
_FALLBACK_TYPE = {
    "xlsx": "financial",
    "xls": "financial",
    "csv": "financial",
    "pdf": "deal_strategy",
    "pptx": "company_management",
    "docx": "company_management",
}
_CHAR_W = 6
_INK_H = 7
_GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10011", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11110", "00001", "00001", "01110", "00001", "00001", "11110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "10000", "11110", "00001", "00001", "11110"),
    "6": ("01110", "10000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00001", "01110"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}
_GLYPH_OF = {glyph: char for char, glyph in _GLYPHS.items()}


def render_bitmap_text(text: str) -> bytes:
    """Draw text as a fixed bitmap. The image reader decodes this same grid."""
    from PIL import Image

    chars = list(text.upper())
    image = Image.new("L", (_CHAR_W * max(len(chars), 1), _INK_H), 255)
    pixels = image.load()
    for index, char in enumerate(chars):
        glyph = _GLYPHS.get(char, _GLYPHS[" "])
        for y, row in enumerate(glyph):
            for x, bit in enumerate(row):
                if bit == "1":
                    pixels[index * _CHAR_W + x, y] = 0
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def ocr_image(data: bytes) -> str:
    """Read text from an image. A fixed bitmap is decoded locally; other images use Tesseract when it is installed."""
    grid = _ocr_grid(data)
    if grid:
        return grid
    return _ocr_tesseract(data)


def read_document(path: Path) -> dict[str, Any]:
    """Return one document graph. Ids ignore the filename."""
    data = path.read_bytes()
    doc_id = "doc_" + hashlib.sha256(data).hexdigest()[:16]
    suffix = path.suffix.lower().lstrip(".")
    parts = _parts_for(path, suffix, doc_id)
    document_type, period = _label_parts(parts, _FALLBACK_TYPE.get(suffix, "company_management"))
    return {
        "id": doc_id,
        "filename": path.name,
        "document_type": document_type,
        "period": period,
        "parts": parts,
    }


def read_documents(paths: list[Path]) -> dict[str, Any]:
    """Read a set of files and point each cross-reference at its target."""
    documents = []
    for path in paths:
        if not path.is_file():
            continue
        try:
            documents.append(read_document(path))
        except Exception as exc:
            documents.append(
                {
                    "id": "doc_unread",
                    "filename": path.name,
                    "document_type": "company_management",
                    "period": None,
                    "parts": [],
                    "error": str(exc),
                }
            )
    _link_cross_references(documents)
    pointers = [
        {
            "part_id": part["id"],
            "text": part.get("text") or "",
            "resolves_to": part.get("resolves_to"),
            "usable_as_source": False,
        }
        for document in documents
        for part in document.get("parts") or []
        if part.get("pointer")
    ]
    return {"documents": documents, "pointers": pointers}


def source_text(corpus: dict[str, Any]) -> str:
    """Text that may be cited. Pointer sentences are left out."""
    documents = corpus["documents"] if "documents" in corpus else [corpus]
    chunks: list[str] = []
    for document in documents:
        for part in document.get("parts") or []:
            if part.get("level") in {"block", "cell"} and part.get("usable_as_source") and part.get("text"):
                chunks.append(str(part["text"]))
    return "\n".join(chunks)


def extraction_coverage(corpus: dict[str, Any], expected: list[str]) -> float:
    """Share of expected characters present in citable text."""
    blob = source_text(corpus)
    total = sum(len(item) for item in expected)
    if total == 0:
        return 1.0
    found = sum(len(item) for item in expected if item in blob)
    return found / total


def stable_signature(corpus: dict[str, Any]) -> list[dict[str, Any]]:
    """Ids, types, periods, and citable text. The filename is not included."""
    documents = corpus["documents"] if "documents" in corpus else [corpus]
    signature = []
    for document in documents:
        signature.append(
            {
                "id": document.get("id"),
                "document_type": document.get("document_type"),
                "period": document.get("period"),
                "parts": [
                    {
                        "id": part.get("id"),
                        "parent_id": part.get("parent_id"),
                        "level": part.get("level"),
                        "locator": part.get("locator"),
                        "text": part.get("text"),
                        "document_type": part.get("document_type"),
                        "period": part.get("period"),
                        "usable_as_source": part.get("usable_as_source"),
                        "resolves_to": part.get("resolves_to"),
                    }
                    for part in document.get("parts") or []
                ],
            }
        )
    return signature


def _parts_for(path: Path, suffix: str, doc_id: str) -> list[dict[str, Any]]:
    if suffix == "pdf":
        return _read_pdf(path, doc_id)
    if suffix == "docx":
        return _read_docx(path, doc_id)
    if suffix == "pptx":
        return _read_pptx(path, doc_id)
    if suffix in {"xlsx", "xlsm", "xls"}:
        return _read_xlsx(path, doc_id)
    if suffix in {"png", "jpg", "jpeg", "tif", "tiff", "bmp", "webp", "gif"}:
        return _read_image(path, doc_id)
    if suffix in {"txt", "md", "csv", "log"}:
        return _read_lines(path, doc_id)
    return _document_only(doc_id)


def _read_pdf(path: Path, doc_id: str) -> list[dict[str, Any]]:
    import fitz

    parts = _document_only(doc_id)
    with fitz.open(path) as pdf:
        for index, page in enumerate(pdf):
            locator = {"page": index + 1}
            page_id = _part_id(doc_id, "page", locator, "")
            parts.append(_node(page_id, doc_id, "page", locator))
            blocks = _pdf_blocks(page)
            if sum(len(text) for text in blocks) <= 12:
                blocks.extend(_ocr_page_images(pdf, page))
            for block_index, text in enumerate(blocks, start=1):
                block_locator = {"page": index + 1, "block": block_index}
                parts.append(
                    _node(
                        _part_id(doc_id, "block", block_locator, text),
                        page_id,
                        "block",
                        block_locator,
                        text=text,
                        image_kind=_image_kind(text) if text not in _pdf_text_blocks(page) else None,
                    )
                )
    return parts


def _pdf_blocks(page: Any) -> list[str]:
    blocks = []
    for block in page.get_text("blocks") or []:
        if len(block) < 5:
            continue
        text = " ".join(str(block[4]).split())
        if text:
            blocks.append(text)
    return blocks


def _pdf_text_blocks(page: Any) -> set[str]:
    return set(_pdf_blocks(page))


def _ocr_page_images(pdf: Any, page: Any) -> list[str]:
    found = []
    for item in page.get_images(full=True) or []:
        try:
            info = pdf.extract_image(item[0])
        except Exception:
            continue
        blob = info.get("image") if isinstance(info, dict) else None
        text = ocr_image(blob) if blob else ""
        if text:
            found.append(text)
    return found


def _read_docx(path: Path, doc_id: str) -> list[dict[str, Any]]:
    from docx import Document

    parts = _document_only(doc_id)
    page_id = _part_id(doc_id, "page", {"page": 1}, "")
    parts.append(_node(page_id, doc_id, "page", {"page": 1}))
    document = Document(str(path))
    for index, paragraph in enumerate(document.paragraphs, start=1):
        text = " ".join(paragraph.text.split())
        if not text:
            continue
        locator = {"page": 1, "block": index}
        parts.append(_node(_part_id(doc_id, "block", locator, text), page_id, "block", locator, text=text))
    for table_index, table in enumerate(document.tables, start=1):
        _append_table(parts, doc_id, page_id, {"page": 1, "table": table_index}, table_index, _docx_rows(table))
    return parts


def _docx_rows(table: Any) -> list[list[str]]:
    rows = []
    for row in table.rows:
        rows.append([" ".join(cell.text.split()) for cell in row.cells])
    return rows


def _read_pptx(path: Path, doc_id: str) -> list[dict[str, Any]]:
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    parts = _document_only(doc_id)
    presentation = Presentation(str(path))
    for index, slide in enumerate(presentation.slides, start=1):
        locator = {"slide": index}
        slide_id = _part_id(doc_id, "slide", locator, "")
        parts.append(_node(slide_id, doc_id, "slide", locator))
        block_index = 0
        table_index = 0
        for shape in slide.shapes:
            block_index, table_index = _pptx_shape(parts, doc_id, slide_id, index, shape, MSO_SHAPE_TYPE, block_index, table_index)
    return parts


def _pptx_shape(parts, doc_id, slide_id, slide_no, shape, shape_type, block_index, table_index):
    if getattr(shape, "has_table", False):
        table_index += 1
        rows = [[cell.text.strip() for cell in row.cells] for row in shape.table.rows]
        _append_table(parts, doc_id, slide_id, {"slide": slide_no, "table": table_index}, table_index, rows)
        return block_index, table_index
    if getattr(shape, "shape_type", None) == shape_type.PICTURE:
        text = ocr_image(shape.image.blob)
        if text:
            block_index += 1
            locator = {"slide": slide_no, "block": block_index}
            parts.append(
                _node(
                    _part_id(doc_id, "block", locator, text),
                    slide_id,
                    "block",
                    locator,
                    text=text,
                    image_kind=_image_kind(text),
                )
            )
        return block_index, table_index
    text = " ".join(getattr(shape, "text", "").split())
    if text:
        block_index += 1
        locator = {"slide": slide_no, "block": block_index}
        parts.append(_node(_part_id(doc_id, "block", locator, text), slide_id, "block", locator, text=text))
    return block_index, table_index


def _read_xlsx(path: Path, doc_id: str) -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    parts = _document_only(doc_id)
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets[:40]:
            _append_sheet(parts, doc_id, sheet)
    finally:
        workbook.close()
    return parts


def _append_sheet(parts: list[dict[str, Any]], doc_id: str, sheet: Any) -> None:
    locator = {"sheet": sheet.title}
    sheet_id = _part_id(doc_id, "sheet", locator, "")
    parts.append(_node(sheet_id, doc_id, "sheet", locator))
    rows: list[list[str]] = []
    for row_index, row in enumerate(sheet.iter_rows(), start=1):
        if row_index > 200:
            break
        _append_sheet_row(parts, doc_id, sheet_id, sheet.title, row, rows)
    if rows:
        _append_table(parts, doc_id, sheet_id, {"sheet": sheet.title, "table": 1}, 1, rows, parent_is_sheet=True)


def _append_sheet_row(parts, doc_id: str, sheet_id: str, title: str, row: Any, rows: list[list[str]]) -> None:
    values = [_cell_text(cell.value) for cell in row]
    if any(values):
        rows.append(values)
    for cell in row:
        text = _cell_text(cell.value)
        if not text:
            continue
        cell_locator = {"sheet": title, "cell": cell.coordinate}
        parts.append(_node(_part_id(doc_id, "cell", cell_locator, text), sheet_id, "cell", cell_locator, text=text))


def _read_image(path: Path, doc_id: str) -> list[dict[str, Any]]:
    parts = _document_only(doc_id)
    page_id = _part_id(doc_id, "page", {"page": 1}, "")
    parts.append(_node(page_id, doc_id, "page", {"page": 1}))
    text = ocr_image(path.read_bytes())
    if text:
        locator = {"page": 1, "block": 1}
        parts.append(
            _node(
                _part_id(doc_id, "block", locator, text),
                page_id,
                "block",
                locator,
                text=text,
                image_kind=_image_kind(text),
            )
        )
    return parts


def _read_lines(path: Path, doc_id: str) -> list[dict[str, Any]]:
    parts = _document_only(doc_id)
    page_id = _part_id(doc_id, "page", {"page": 1}, "")
    parts.append(_node(page_id, doc_id, "page", {"page": 1}))
    raw = path.read_text(encoding="utf-8", errors="replace")
    for index, line in enumerate(raw.splitlines(), start=1):
        text = " ".join(line.split())
        if not text:
            continue
        locator = {"page": 1, "block": index}
        parts.append(_node(_part_id(doc_id, "block", locator, text), page_id, "block", locator, text=text))
    return parts


def _append_table(parts, doc_id, parent_id, locator, table_index, rows, parent_is_sheet: bool = False) -> None:
    table_id = _part_id(doc_id, "table", locator, "")
    parts.append(_node(table_id, parent_id, "table", locator, rows=rows, name=f"table_{table_index}"))
    if parent_is_sheet:
        return
    for row_index, row in enumerate(rows, start=1):
        for col_index, text in enumerate(row, start=1):
            if not text:
                continue
            cell_locator = {**locator, "row": row_index, "col": col_index}
            parts.append(_node(_part_id(doc_id, "cell", cell_locator, text), table_id, "cell", cell_locator, text=text))


def _document_only(doc_id: str) -> list[dict[str, Any]]:
    return [_node(doc_id, None, "document", {})]


def _node(part_id, parent_id, level, locator, text: str = "", **extra: Any) -> dict[str, Any]:
    pointer = _pointer(text) if text else None
    part = {
        "id": part_id,
        "parent_id": parent_id,
        "level": level,
        "locator": locator,
        "text": text,
        "document_type": None,
        "period": None,
        "usable_as_source": level in {"block", "cell"} and pointer is None and bool(text),
        "resolves_to": None,
        "pointer": pointer,
    }
    part.update(extra)
    return part


def _label_parts(parts: list[dict[str, Any]], fallback: str) -> tuple[str, str | None]:
    blob = " ".join(part.get("text") or "" for part in parts if part.get("level") in {"block", "cell"})
    document_type = _document_type(blob) or fallback
    period = _period(blob)
    by_parent: dict[str | None, list[dict[str, Any]]] = {}
    for part in parts:
        by_parent.setdefault(part.get("parent_id"), []).append(part)
    for part in parts:
        part["document_type"] = document_type
        section_text = part.get("text") or ""
        if part["level"] in {"document", "page", "slide", "sheet"}:
            section_text = _descendant_text(by_parent, part["id"])
        part["period"] = _period(section_text) or period
    return document_type, period


def _descendant_text(by_parent: dict[str | None, list[dict[str, Any]]], root_id: str) -> str:
    texts: list[str] = []
    stack = [root_id]
    while stack:
        current = stack.pop()
        for child in by_parent.get(current, []):
            if child.get("text"):
                texts.append(child["text"])
            stack.append(child["id"])
    return " ".join(texts)


def _document_type(text: str) -> str | None:
    padded = f" {text.lower()} "
    for document_type, needles in _TYPE_RULES:
        if any(needle in padded for needle in needles):
            return document_type
    return None


def _period(text: str) -> str | None:
    match = _PERIOD.search(text or "")
    if match:
        return f"FY{match.group(1)}"
    match = _YEAR.search(text or "")
    if match:
        return match.group(1)
    return None


def _pointer(text: str) -> dict[str, Any] | None:
    cleaned = " ".join(text.split())
    flags = re.IGNORECASE
    page = re.fullmatch(r"see (?P<doc>[A-Z][A-Z0-9]*) p(?:age)? ?(?P<num>\d+)", cleaned, flags)
    if page:
        return {"doc": page.group("doc"), "page": int(page.group("num"))}
    slide = re.fullmatch(r"see slide ?(?P<num>\d+)", cleaned, flags)
    if slide:
        return {"slide": int(slide.group("num"))}
    sheet = re.fullmatch(r"see sheet (?P<name>\S.{0,60})", cleaned, flags)
    if sheet:
        return {"sheet": sheet.group("name").strip()}
    bare = re.fullmatch(r"see p(?:age)? ?(?P<num>\d+)", cleaned, flags)
    if bare:
        return {"page": int(bare.group("num"))}
    return None


def _link_cross_references(documents: list[dict[str, Any]]) -> None:
    for document in documents:
        for part in document.get("parts") or []:
            pointer = part.get("pointer")
            if not pointer:
                continue
            part["usable_as_source"] = False
            part["resolves_to"] = _target_id(documents, pointer)


def _target_id(documents: list[dict[str, Any]], pointer: dict[str, Any]) -> str | None:
    if "sheet" in pointer:
        return _match_level(documents, "sheet", "sheet", pointer["sheet"])
    if "slide" in pointer:
        return _match_number(documents, "slide", "slide", pointer["slide"], None)
    return _match_number(documents, "block", "page", pointer.get("page"), pointer.get("doc"))


def _match_level(documents, level: str, key: str, name: str) -> str | None:
    wanted = name.lower()
    for document in documents:
        for part in document.get("parts") or []:
            if part.get("level") == level and str((part.get("locator") or {}).get(key, "")).lower() == wanted:
                return part["id"]
    return None


def _match_number(documents, level: str, key: str, number: int | None, hint: str | None) -> str | None:
    best: dict[str, Any] | None = None
    for document in documents:
        if hint and not _hint_matches(document, hint):
            continue
        best = _longer_part(best, document, level, key, number)
    return None if best is None else best["id"]


def _longer_part(best, document, level: str, key: str, number: int | None):
    for part in document.get("parts") or []:
        locator = part.get("locator") or {}
        if part.get("level") != level or part.get("pointer") or locator.get(key) != number:
            continue
        if best is None or len(part.get("text") or "") > len(best.get("text") or ""):
            best = part
    return best


def _hint_matches(document: dict[str, Any], hint: str) -> bool:
    needle = hint.lower()
    filename = Path(str(document.get("filename") or "")).stem.lower()
    if needle in filename:
        return True
    blob = " ".join(
        str(part.get("text") or "")
        for part in document.get("parts") or []
        if part.get("level") in {"block", "cell"} and not part.get("pointer")
    )
    return needle in blob.lower()


def _part_id(doc_id: str, level: str, locator: dict[str, Any], text: str) -> str:
    raw = "|".join([doc_id, level, json.dumps(locator, sort_keys=True), " ".join(text.split())])
    return "src_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).split())


def _image_kind(text: str) -> str:
    tokens = text.split()
    if any(char.isdigit() for char in text) and len(tokens) <= 2:
        return "chart"
    if len(tokens) == 1 and not any(char.isdigit() for char in text):
        return "logo"
    return "text"


def _ocr_grid(data: bytes) -> str:
    from PIL import Image

    try:
        image = Image.open(BytesIO(data)).convert("L")
    except Exception:
        return ""
    if image.height != _INK_H or image.width % _CHAR_W != 0:
        return ""
    pixels = image.load()
    chars = []
    for index in range(image.width // _CHAR_W):
        rows = []
        for y in range(_INK_H):
            rows.append("".join("1" if pixels[index * _CHAR_W + x, y] < 128 else "0" for x in range(5)))
        chars.append(_GLYPH_OF.get(tuple(rows), ""))
    if any(char == "" for char in chars):
        return ""
    return "".join(chars).strip()


def _ocr_tesseract(data: bytes) -> str:
    if not shutil.which("tesseract"):
        return ""
    with tempfile.TemporaryDirectory() as folder:
        image_path = Path(folder) / "page.png"
        image_path.write_bytes(data)
        try:
            completed = subprocess.run(
                ["tesseract", str(image_path), "stdout", "-l", "eng"],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
    return " ".join(completed.stdout.split())
