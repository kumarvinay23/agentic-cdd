"""Fix 7 — lease PDF reader emits facts with page bbox; unreadable → honest status."""

from __future__ import annotations

from pathlib import Path

import fitz

from agetic_cdd_api.services_document_register import _status
from agetic_cdd_api.services_lease_reader import (
    extract_evidenced_rent_m,
    lease_status_reason,
    read_lease_document,
)


def _write_text_lease(path: Path, text: str) -> None:
    pdf = fitz.open()
    page = pdf.new_page(width=400, height=200)
    page.insert_text((40, 80), text, fontsize=11)
    pdf.save(path)
    pdf.close()


def test_lease_text_pdf_emits_fact_with_bbox(tmp_path: Path) -> None:
    path = tmp_path / "Office_Lease.pdf"
    _write_text_lease(path, "Annual base rent $561,000 per year. Term 5 years.")
    facts, locs = read_lease_document(path, doc_id="doc_lease1", currency="USD")
    assert facts
    rent = next(f for f in facts if f.concept_id == "lease.rent_contractual")
    assert rent.value == 561000.0
    assert rent.source_location_ids
    loc = locs[rent.source_location_ids[0]]
    assert loc.bbox is not None
    assert len(loc.bbox) == 4
    assert all(0.0 <= float(x) <= 1.0 for x in loc.bbox)
    assert loc.extraction_method in {"PDF_TEXT", "PAGE_IMAGE", "OCR"}


def test_unreadable_image_is_partial_or_failed_not_absent(tmp_path: Path) -> None:
    # Blank-ish scan: OCR may return nothing → register status must be honest.
    path = tmp_path / "blank_lease.pdf"
    pdf = fitz.open()
    pdf.new_page(width=200, height=200)
    pdf.save(path)
    pdf.close()

    facts, _locs = read_lease_document(path, doc_id="doc_blank", currency="USD")
    assert facts == []
    reason = lease_status_reason(facts, attempted=True)
    assert reason and reason.startswith("PARTIAL")

    # Graph parts for an empty PDF page should drive FAILED/PARTIAL via _status.
    from agetic_cdd_api.services_document_graph import read_document

    graph = read_document(path)
    status, status_reason = _status(path, "pdf", list(graph.get("parts") or []), None)
    assert status in {"FAILED", "PARTIAL", "SKIPPED"}
    assert status_reason
    assert status != "READ"


def test_extract_evidenced_rent_m_for_deck(tmp_path: Path) -> None:
    path = tmp_path / "Site_Lease.pdf"
    _write_text_lease(path, "The annually rent is $120,000.")
    rent_m, label, bbox = extract_evidenced_rent_m(path)
    assert rent_m is not None
    assert abs(float(rent_m) - 0.12) < 1e-9
    assert label
    assert bbox is not None
