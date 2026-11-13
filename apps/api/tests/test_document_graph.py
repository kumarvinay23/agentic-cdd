"""Format set: scanned PDF, image-only slide, workbook, pointer, and Word."""

from __future__ import annotations

import shutil
from io import BytesIO
from pathlib import Path

import fitz
from docx import Document
from openpyxl import Workbook
from pptx import Presentation
from pptx.util import Inches

from agetic_cdd_api.services_document_graph import (
    extraction_coverage,
    read_documents,
    render_bitmap_text,
    source_text,
    stable_signature,
)
from agetic_cdd_api.services_extract import extract_file

SCAN_TEXT = "CIM REVENUE 100"
SLIDE_TEXT = "NORTHWIND"
WORD_TEXT = "Customer concentration is low"
WORD_CELL = "Philadelphia"
SHEET_CELLS = ("Metric", "FY2024", "Revenue", "100")
TABLE_CELLS = ("Price", "12")


def _write_scan(path: Path) -> None:
    png = render_bitmap_text(SCAN_TEXT)
    pdf = fitz.open()
    page = pdf.new_page(width=240, height=40)
    page.insert_image(page.rect, stream=png)
    pdf.save(path)
    pdf.close()


def _write_slides(path: Path) -> None:
    png = render_bitmap_text(SLIDE_TEXT)
    presentation = Presentation()
    blank = presentation.slide_layouts[6]
    picture_slide = presentation.slides.add_slide(blank)
    picture_slide.shapes.add_picture(BytesIO(png), Inches(0.4), Inches(0.4))
    table_slide = presentation.slides.add_slide(blank)
    table = table_slide.shapes.add_table(1, 2, Inches(0.4), Inches(0.4), Inches(4), Inches(0.6)).table
    table.cell(0, 0).text = TABLE_CELLS[0]
    table.cell(0, 1).text = TABLE_CELLS[1]
    presentation.save(path)


def _write_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Revenue"
    sheet["A1"] = SHEET_CELLS[0]
    sheet["B1"] = SHEET_CELLS[1]
    sheet["A2"] = SHEET_CELLS[2]
    sheet["B2"] = int(SHEET_CELLS[3])
    workbook.save(path)


def _write_word(path: Path) -> None:
    document = Document()
    document.add_paragraph(WORD_TEXT)
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = WORD_CELL
    document.save(path)


def _format_set(folder: Path) -> list[Path]:
    folder.mkdir(parents=True, exist_ok=True)
    scan = folder / "CIM.pdf"
    slides = folder / "Market.pptx"
    workbook = folder / "Financials.xlsx"
    pointer = folder / "Pointer.txt"
    word = folder / "Customers.docx"
    _write_scan(scan)
    _write_slides(slides)
    _write_workbook(workbook)
    pointer.write_text("see CIM p1\nsee sheet Revenue\n", encoding="utf-8")
    _write_word(word)
    return [scan, slides, workbook, pointer, word]


def test_format_set_extracts_text_and_cells_and_ignores_rename(tmp_path: Path) -> None:
    paths = _format_set(tmp_path / "vdr")
    corpus = read_documents(paths)
    expected = [SCAN_TEXT, SLIDE_TEXT, WORD_TEXT, WORD_CELL, *SHEET_CELLS, *TABLE_CELLS]
    assert extraction_coverage(corpus, expected) >= 0.99

    cited = source_text(corpus)
    assert "see CIM p1" not in cited
    assert "see sheet Revenue" not in cited

    pointers = {item["text"]: item["resolves_to"] for item in corpus["pointers"]}
    scan = next(doc for doc in corpus["documents"] if doc["filename"] == "CIM.pdf")
    page_block = next(part for part in scan["parts"] if part["level"] == "block" and part["text"] == SCAN_TEXT)
    workbook = next(doc for doc in corpus["documents"] if doc["filename"] == "Financials.xlsx")
    sheet = next(part for part in workbook["parts"] if part["level"] == "sheet")
    assert pointers["see CIM p1"] == page_block["id"]
    assert pointers["see sheet Revenue"] == sheet["id"]
    assert page_block["usable_as_source"] is True
    assert scan["document_type"] == "deal_strategy"
    assert scan["period"] is None
    assert workbook["document_type"] == "financial"
    assert workbook["period"] == "FY2024"
    assert any(part["level"] == "cell" and part["locator"].get("cell") == "B2" for part in workbook["parts"])
    assert any(part.get("image_kind") == "logo" for doc in corpus["documents"] for part in doc["parts"])

    renamed = tmp_path / "renamed"
    renamed.mkdir()
    renamed_paths = []
    for path in paths:
        target = renamed / f"copy-{path.name}"
        shutil.copyfile(path, target)
        renamed_paths.append(target)
    again = read_documents(renamed_paths)
    assert stable_signature(again) == stable_signature(corpus)


def test_extract_file_reads_scan_and_leaves_blank_page_unread(tmp_path: Path) -> None:
    scan = tmp_path / "CIM.pdf"
    _write_scan(scan)
    extracted = extract_file(scan)
    assert SCAN_TEXT in extracted["text"]
    assert extracted["pages"][0]["unread"] is False
    assert extracted["graph"]["id"].startswith("doc_")

    from pypdf import PdfWriter

    blank = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with blank.open("wb") as handle:
        writer.write(handle)
    blank_result = extract_file(blank)
    assert blank_result["pages"][0]["unread"] is True
