"""Fix 2 — exhibit contract footing gate."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation

from agetic_cdd_api.fdd_schemas import (
    ExhibitContract,
    ExhibitContractRow,
    ExhibitStoreDoc,
    PptxChrome,
    SlideSpec,
    SlideTable,
)
from agetic_cdd_api.services_fdd_chapters import plan_trading
from agetic_cdd_api.services_fdd_exhibit_contract import (
    ExhibitFootingError,
    apply_contract_or_hold,
    assert_exhibit_foots,
    check_exhibit_footing,
    enforce_exhibit_contracts,
    revenue_stream_contract_from_pack,
    revenue_stream_contract_from_values,
    slide_may_draw_matrix,
    stamp_footing_status,
)
from agetic_cdd_api.services_fdd_pptx import write_fdd_presentation
from agetic_cdd_api.services_fdd_trading import TradingPack


def _pack(*, break_fy25: bool = False) -> TradingPack:
    pack = TradingPack(deal_slug="synth", scale="M", years=(2024, 2025))
    pack.fy = {
        "Residential": {2024: 1.967, 2025: 1.983},
        "Municipal": {2024: 4.243, 2025: 4.794},
        "Commercial": {2024: 4.966, 2025: 5.616},
        "Key Compostables": {2024: 0.312, 2025: 0.695},
        "Compost sales": {2024: 0.250, 2025: 0.180},
        "Other revenue": {2024: 0.130, 2025: 0.143},
        "Revenue": {2024: 11.869, 2025: 13.412},
        "Gross profit": {2024: 3.772, 2025: 4.082},
        "EBITDA": {2024: 1.115, 2025: 0.561},
        "SG&A (reported)": {2024: 3.273, 2025: 4.231},
        "Depreciation": {2024: 0.616, 2025: 0.709},
    }
    if break_fy25:
        # Gap-report style over-sum (~$179k).
        pack.fy["Residential"][2025] = 2.162
    pack.revenue_fy = {2024: 11.869, 2025: 13.412}
    pack.stream_labels = [
        "Residential",
        "Municipal",
        "Commercial",
        "Key Compostables",
        "Compost sales",
        "Other revenue",
    ]
    return pack


def test_stream_contract_foots_on_consistent_pack() -> None:
    contract = revenue_stream_contract_from_pack(_pack())
    assert contract is not None
    results = assert_exhibit_foots(contract)
    assert all(r.ok for r in results)
    stamped = stamp_footing_status(contract)
    assert stamped.footing_status == "ok"


def test_stream_contract_fails_on_over_sum() -> None:
    contract = revenue_stream_contract_from_pack(_pack(break_fy25=True))
    assert contract is not None
    results = check_exhibit_footing(contract)
    failed = [r for r in results if not r.ok]
    assert failed
    assert "does not foot" in failed[0].message
    assert failed[0].delta == pytest.approx(0.179, abs=0.01)
    with pytest.raises(ExhibitFootingError):
        assert_exhibit_foots(contract)


def test_apply_contract_or_hold_replaces_matrix() -> None:
    contract = revenue_stream_contract_from_pack(_pack(break_fy25=True))
    assert contract is not None
    slide = SlideSpec(
        slide_id="ch_tx_business",
        layout="section_table_obs",
        chapter="transaction",
        headline="Revenue by stream",
        table=SlideTable(
            title="Revenue by stream",
            headers=["Stream", "FY25"],
            rows=[["Residential", "$2,162k"], ["Revenue", "$13,412k"]],
        ),
    )
    held = apply_contract_or_hold(slide, contract)
    assert held is not None
    assert held.exhibit_contract is not None
    assert held.exhibit_contract.footing_status == "failed"
    assert held.table is not None
    assert any("do not foot" in str(c).lower() for r in held.table.rows for c in r)
    assert "13,412" not in "".join(str(c) for r in held.table.rows for c in r)
    assert not slide_may_draw_matrix(held)


def test_enforce_drops_failed_when_requested() -> None:
    contract = stamp_footing_status(
        revenue_stream_contract_from_values(
            contract_id="ex_bad",
            years=(2025,),
            stream_fy={"A": {2025: 10.0}, "B": {2025: 5.0}},
            total_fy={2025: 10.0},
        )
    )
    assert contract.footing_status == "failed"
    slides = [
        SlideSpec(
            slide_id="bad",
            layout="section_table_obs",
            table=SlideTable(headers=["a"], rows=[["1"]]),
            exhibit_contract=contract,
        ),
        SlideSpec(slide_id="ok", layout="cover", deal_name="x"),
    ]
    kept = enforce_exhibit_contracts(slides, drop_failed=True)
    assert [s.slide_id for s in kept] == ["ok"]


def test_plan_trading_soft_holds_margin_when_streams_do_not_foot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Soft hold keeps GP/EBITDA matrix visible while stamping footing failed."""
    pack = _pack(break_fy25=True)
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: pack,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_facts.resolve_pl_series",
        lambda *_a, **_k: {},
    )
    store = ExhibitStoreDoc(
        run_id="r1", deal_slug="synth", updated_at="", exhibits=[]
    )
    slides = plan_trading(commentary=None, store=store, requests=[])
    margin = next(s for s in slides if s.slide_id == "ch_trading_margin")
    assert margin.exhibit_contract is not None
    assert margin.exhibit_contract.footing_status == "failed"
    assert margin.exhibit_contract.hold_mode == "soft"
    assert margin.completeness_state == "complete"
    assert margin.table is not None
    # Matrix retained (soft) — revenue / EBITDA labels still present.
    blob = " ".join(str(c) for r in margin.table.rows for c in r).lower()
    assert "revenue" in blob or "ebitda" in blob or "gross" in blob
    assert slide_may_draw_matrix(margin)
    assert any("foot" in str(o).lower() for o in (margin.observations or []))
    assert all("ex_" not in str(o) for o in (margin.observations or []))


def test_plan_trading_keeps_margin_when_streams_foot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pack = _pack(break_fy25=False)
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: pack,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_facts.resolve_pl_series",
        lambda *_a, **_k: {},
    )
    store = ExhibitStoreDoc(
        run_id="r1", deal_slug="synth", updated_at="", exhibits=[]
    )
    slides = plan_trading(commentary=None, store=store, requests=[])
    margin = next(s for s in slides if s.slide_id == "ch_trading_margin")
    assert margin.exhibit_contract is not None
    assert margin.exhibit_contract.footing_status == "ok"
    assert margin.table is not None
    assert any(str(r[0]).lower() == "revenue" for r in margin.table.rows)


def test_renderer_refuses_failed_matrix(tmp_path: Path) -> None:
    contract = stamp_footing_status(
        ExhibitContract(
            contract_id="ex_bad",
            total_concept="revenue",
            periods=["2025"],
            rows=[
                ExhibitContractRow(concept="a", values={"2025": 10.0}),
                ExhibitContractRow(concept="b", values={"2025": 5.0}),
            ],
            total_values={"2025": 10.0},
        )
    )
    assert contract.footing_status == "failed"
    slide = SlideSpec(
        slide_id="bad",
        layout="section_table_obs",
        banner="TRADING",
        headline="Should not show $99m",
        table=SlideTable(
            title="Bad matrix",
            headers=["Stream", "FY25"],
            rows=[["A", "$99,000k"], ["Total", "$10,000k"]],
        ),
        exhibit_contract=contract,
    )
    out = tmp_path / "held.pptx"
    write_fdd_presentation(out, [slide], chrome=PptxChrome())
    assert out.is_file()
    prs = Presentation(str(out))
    # Smoke: file opens; numeric matrix text should not survive as the only content.
    texts = []
    for s in prs.slides:
        for shape in s.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
    blob = "\n".join(texts).lower()
    assert "do not foot" in blob or "held" in blob
    assert "$99,000k" not in blob
