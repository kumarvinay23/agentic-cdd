"""A selected fact keeps its concept and source cell when the room is shaken.

Fact ids are assigned on each read. The stable identity is the concept and the
source cell. A fact id that appears in both reads must still point at that pair.
Changing the confirmed reporting currency does not rewrite the stored amount
or the stored currency. The series cell is labeled with the confirmed currency.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from openpyxl import load_workbook

from agetic_cdd_api.services_databook_view import _build_series
from agetic_cdd_api.services_ontology import load_ontology
from agetic_cdd_api.services_statement_reader import read_excel, read_pdf

_ROOM = Path(__file__).resolve().parent / "fixtures" / "close" / "room_01"

# A one-page PDF with an empty content stream. There is no text layer to map.
_BLANK_PDF = b"""%PDF-1.1
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 300]/Contents 4 0 R>>endobj
4 0 obj<</Length 0>>stream
endstream
endobj
trailer<</Root 1 0 R>>
%%EOF
"""


def test_rename_reorder_and_image_pdf_keep_concept_and_source_cell(tmp_path: Path) -> None:
    profile = json.loads((_ROOM / "profile.json").read_text())
    currency = profile["reporting_currency"]
    fye_month = int(profile["fiscal_year_end"][:2])
    original = _ROOM / profile["workbook"]

    before = _selected(original, currency, fye_month)
    shaken = tmp_path / "renamed-statements.xlsx"
    shutil.copy(original, shaken)
    _reorder_sheets(shaken)
    scan = tmp_path / "scan.pdf"
    scan.write_bytes(_BLANK_PDF)

    after = _selected(shaken, currency, fye_month)
    skipped = read_pdf(scan, "doc-scan", load_ontology(), currency, {}, scale=1, fye_month=fye_month)

    assert before["pairs"]
    assert after["pairs"] == before["pairs"]
    for fact_id in before["by_id"].keys() & after["by_id"].keys():
        assert after["by_id"][fact_id] == before["by_id"][fact_id]
    assert skipped["status"] == "SKIPPED"
    assert skipped["facts"] == []


def test_confirmed_currency_changes_the_series_label_only() -> None:
    profile = json.loads((_ROOM / "profile.json").read_text())
    selected = _selected(_ROOM / profile["workbook"], profile["reporting_currency"], int(profile["fiscal_year_end"][:2]))
    concept, _cell, value, currency = next(row for row in selected["pairs"] if row[0] == "fin.pl.revenue")
    stored = {
        "concept_id": concept,
        "value": value,
        "currency": currency,
        "status": "SELECTED",
        "period_type": "FM",
        "period_end": "2025-12-31",
        "fact_id": "fact-stable-revenue",
        "sheet_or_page": "PL",
        "concept_label": "Revenue",
        "file_name": profile["workbook"],
    }
    snapshot = (stored["value"], stored["currency"])
    series, _dq = _build_series([stored], [], {}, "EUR")
    shown = series["revenue"]["2025"]

    assert (stored["value"], stored["currency"]) == snapshot
    assert shown.value == snapshot[0]
    assert shown.currency == "EUR"
    assert shown.foreign is True


def _selected(path: Path, currency: str, fye_month: int) -> dict:
    locs: dict = {}
    facts = read_excel(path, "doc-stable", load_ontology(), currency, locs, scale=1, fye_month=fye_month)
    by_id: dict[str, tuple[str, str]] = {}
    pairs: list[tuple[str, str, float, str]] = []
    for fact in facts:
        if fact.status != "SELECTED" or not fact.source_location_ids:
            continue
        loc = locs[fact.source_location_ids[0]]
        source_cell = f"{loc.sheet_or_page}!{loc.cell_range}"
        by_id[fact.fact_id] = (fact.concept_id, source_cell)
        pairs.append((fact.concept_id, source_cell, fact.value, fact.currency or ""))
    pairs.sort()
    return {"by_id": by_id, "pairs": pairs}


def _reorder_sheets(path: Path) -> None:
    book = load_workbook(path)
    names = list(reversed(book.sheetnames))
    for index, name in enumerate(names):
        current = book.sheetnames.index(name)
        book.move_sheet(name, offset=index - current)
    book.save(path)
