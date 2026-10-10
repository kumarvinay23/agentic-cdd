"""G4 — page crops for validation cards (AC-5 / S1-8 / OL-2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.services_databook_crops import (
    ensure_crop,
    resolve_crop_path,
    resolve_source_pdf,
)
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    PageKind,
    PageRegister,
    PageRegisterEntry,
    ReleaseCellStatus,
    ReleasedCell,
    SourceRef,
)
from agetic_cdd_api.services_databook_pack import build_validation_pack


class _Deal:
    def __init__(self, slug: str) -> None:
        self.id = slug
        self.slug = slug


def _write_tiny_pdf(path: Path, text: str = "Revenue FY2024 3140") -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=400, height=300)
    page.insert_text((40, 80), text, fontsize=14, fontname="helv")
    page.insert_text((40, 110), "EBITDA 620", fontsize=14, fontname="helv")
    doc.save(str(path))
    doc.close()


def test_normalize_bbox_clamps_after_pad() -> None:
    from agetic_cdd_api.services_databook_crops import _normalize_bbox

    x0, y0, x1, y1 = _normalize_bbox([0.0, 0.0, 1.0, 1.0])
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0

    x0, y0, x1, y1 = _normalize_bbox([0.5, 0.5, 0.5, 0.5])  # degenerate → expanded
    assert 0.0 <= x0 < x1 <= 1.0
    assert 0.0 <= y0 < y1 <= 1.0
    assert x1 - x0 >= 0.02
    assert y1 - y0 >= 0.01


def test_ensure_crop_from_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fitz = pytest.importorskip("fitz")
    del fitz  # presence check only

    deal = _Deal("g4-pdf")
    docs = tmp_path / "documents"
    docs.mkdir()
    pdf = docs / "Acme_Audited.pdf"
    _write_tiny_pdf(pdf)

    imports = {
        "agetic_cdd_api.services_databook_crops.ensure_deal_folder": lambda _s: tmp_path,
        "agetic_cdd_api.services_databook_crops.databook_dir": lambda _d: tmp_path / "databook",
        "agetic_cdd_api.services_databook_crops.load_page_register": lambda _d: None,
    }
    for target, fn in imports.items():
        monkeypatch.setattr(target, fn)

    (tmp_path / "databook").mkdir(exist_ok=True)
    ref = SourceRef(
        doc="Acme_Audited.pdf",
        page=1,
        table="Income Statement",
        row=2,
        col=1,
        rule="year_column",
        bbox=[0.05, 0.15, 0.7, 0.35],
    )
    result = ensure_crop(deal, ref, caption="Revenue", value=3140.0)
    assert result.crop_status == "available"
    assert result.crop_ref
    assert result.crop_ref.endswith(".png")
    path = resolve_crop_path(deal, result.crop_ref)
    assert path is not None
    assert path.stat().st_size > 100
    assert result.source_ref is not None
    assert result.source_ref.crop_status == "available"


def test_ensure_crop_unread_page_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deal = _Deal("g4-scan")
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.databook_dir",
        lambda _d: tmp_path / "databook",
    )
    (tmp_path / "databook").mkdir(exist_ok=True)
    register = PageRegister(
        deal_slug="g4-scan",
        generated_at="2026-01-01T00:00:00Z",
        entries=[
            PageRegisterEntry(
                page_id="p1",
                filename="scan.pdf",
                doc_id="scan",
                page=1,
                kind=PageKind.SCAN,
                unread=True,
                notes=["OCR not available"],
            )
        ],
    )
    ref = SourceRef(doc="scan.pdf", page=1, bbox=[0.1, 0.1, 0.5, 0.2])
    result = ensure_crop(deal, ref, page_register=register)
    assert result.crop_status == "unavailable"
    assert result.crop_ref is None
    assert result.reason and "unread" in result.reason


def test_ensure_crop_synthetic_without_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fitz")
    deal = _Deal("g4-synth")
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.ensure_deal_folder",
        lambda _s: tmp_path,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.databook_dir",
        lambda _d: tmp_path / "databook",
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.load_page_register",
        lambda _d: None,
    )
    (tmp_path / "databook").mkdir(exist_ok=True)
    (tmp_path / "documents").mkdir(exist_ok=True)
    ref = SourceRef(
        doc="missing.pdf",
        page=1,
        table="P&L",
        row=1,
        col=1,
        rule="year_column",
        bbox=[0.1, 0.2, 0.6, 0.3],
    )
    assert resolve_source_pdf(deal, "missing.pdf") is None
    result = ensure_crop(deal, ref, caption="Revenue", value=72.0)
    assert result.crop_status == "available"
    assert result.crop_ref
    assert resolve_crop_path(deal, result.crop_ref) is not None


def test_validation_pack_stamps_crops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("fitz")
    from agetic_cdd_api import services_databook_store as store

    deal = _Deal("g4-pack")
    docs = tmp_path / "documents"
    docs.mkdir()
    _write_tiny_pdf(docs / "a.pdf")

    monkeypatch.setattr(store, "databook_dir", lambda _d: tmp_path / "databook")
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.ensure_deal_folder",
        lambda _s: tmp_path,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.databook_dir",
        lambda _d: tmp_path / "databook",
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_databook_crops.load_page_register",
        lambda _d: None,
    )
    (tmp_path / "databook").mkdir(exist_ok=True)

    ref = SourceRef(
        doc="a.pdf",
        page=1,
        table="P&L",
        row=1,
        col=1,
        rule="year_column",
        bbox=[0.05, 0.15, 0.8, 0.4],
    )
    cells = [
        ReleasedCell(
            metric_key="revenue",
            fiscal_year=2024,
            status=ReleaseCellStatus.PROVEN,
            value=100.0,
            row_id="r1",
            sources=["a.pdf"],
            captions=["Revenue"],
            source_ref=ref,
            alternatives=[{"value": 110.0, "source_name": "b.pdf"}],
        ),
        ReleasedCell(
            metric_key="ebitda",
            fiscal_year=2024,
            status=ReleaseCellStatus.DOUBTFUL,
            value=20.0,
            row_id="r2",
            sources=["a.pdf"],
            captions=["EBITDA"],
            source_ref=ref.model_copy(update={"row": 2}),
        ),
    ]
    store.save_release(
        deal,  # type: ignore[arg-type]
        DatabookRelease(
            release_id="v1",
            version=1,
            deal_slug="g4-pack",
            created_at="2026-01-01T00:00:00Z",
            cells=cells,
            counts={"proven": 1, "doubtful": 1, "missing": 0},
        ),
        set_current=True,
    )
    pack = build_validation_pack(deal, calibration_limit=0, persist_timestamp=False)  # type: ignore[arg-type]
    assert pack.ready_for_review
    conflict = next(c for c in pack.cards if c.kind.value == "conflict")
    doubtful = next(c for c in pack.cards if c.kind.value == "doubtful")
    assert conflict.crop_status == "available"
    assert conflict.crop_ref
    assert doubtful.crop_status == "available"
    assert (pack.counts.get("crops_available") or 0) >= 2
