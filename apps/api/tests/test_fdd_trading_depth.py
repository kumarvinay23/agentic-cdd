"""Trading chapter depth — mix, concentration, EBITDA bridge, YTD compare."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc
from agetic_cdd_api.services_fdd_chapters import plan_trading
from agetic_cdd_api.services_fdd_trading import (
    TradingPack,
    build_trading_pack,
    concentration_rows,
    ebitda_bridge_rows,
    ytd_compare_rows,
)


def _synthetic_pack() -> TradingPack:
    pack = TradingPack(deal_slug="synth", scale="M", years=(2023, 2024, 2025))
    pack.fy = {
        "Residential": {2024: 1.967, 2025: 1.983},
        "Municipal": {2024: 4.243, 2025: 4.794},
        "Commercial": {2024: 4.966, 2025: 5.616},
        "Key Compostables": {2024: 0.312, 2025: 0.695},
        "Compost sales": {2024: 0.250, 2025: 0.180},
        "Other revenue": {2024: 0.130, 2025: 0.143},
        "Revenue": {2024: 11.869, 2025: 13.412},
        "Cost of operations": {2024: 8.097, 2025: 9.329},
        "Gross profit": {2024: 3.772, 2025: 4.082},
        "SG&A (reported)": {2024: 3.273, 2025: 4.231},
        "Labour — operations": {2024: 3.769, 2025: 4.471},
        "Labour — SG&A": {2024: 1.532, 2025: 1.764},
        "Professional fees": {2024: 0.259, 2025: 0.445},
        "Rent": {2024: 0.271, 2025: 0.406},
        "Insurance": {2024: 0.114, 2025: 0.201},
        "Depreciation": {2024: 0.616, 2025: 0.709},
        "EBITDA": {2024: 1.115, 2025: 0.561},
        "Net income": {2024: 0.245, 2025: -0.560},
    }
    pack.revenue_fy = {2024: 11.869, 2025: 13.412}
    pack.ytd = {
        "Residential": {2025: 1.185, 2026: 1.069},
        "Municipal": {2025: 2.772, 2026: 3.286},
        "Commercial": {2025: 3.300, 2026: 3.044},
        "Key Compostables": {2025: 0.322, 2026: 0.531},
        "Compost sales": {2025: 0.142, 2026: 0.054},
        "Other revenue": {2025: 0.096, 2026: 0.070},
        "Revenue": {2025: 7.817, 2026: 8.055},
        "Gross profit": {2025: 2.513, 2026: 2.514},
        "SG&A (reported)": {2025: 2.015, 2026: 2.074},
        "EBITDA": {2025: 0.498, 2026: 0.439},
        "Net income": {2025: -0.130, 2026: -0.181},
    }
    pack.stream_labels = [
        "Residential",
        "Municipal",
        "Commercial",
        "Key Compostables",
        "Compost sales",
        "Other revenue",
    ]
    pack.top_contract_label = "Municipal Account 01"
    pack.dc_billings = 3.078
    pack.dc_share_of_muni = 0.63
    pack.top5_muni_share = 0.881
    pack.top10_commercial_share = 0.226
    pack.top20_commercial_share = 0.337
    return pack


def test_concentration_rows_dc_and_muni() -> None:
    pack = _synthetic_pack()
    rows = concentration_rows(pack, year=2025)
    labels = [r[0] for r in rows]
    assert any("Municipal share" in lab for lab in labels)
    assert any("billings" in lab.lower() for lab in labels)
    dc_share = next(
        v
        for lab, v, k in rows
        if "share of total revenue" in lab.lower() and "municipal share" not in lab.lower()
    )
    assert dc_share == pytest.approx(100.0 * 3.078 / 13.412, rel=1e-3)


def test_ebitda_bridge_explains_fy25_drop() -> None:
    pack = _synthetic_pack()
    bridge = ebitda_bridge_rows(pack)
    assert bridge[0][0].startswith("Reported EBITDA, FY24")
    assert bridge[-1][0].startswith("Reported EBITDA, FY25")
    assert bridge[0][1] == pytest.approx(1.115)
    assert bridge[-1][1] == pytest.approx(0.561)
    gp = next(v for lab, v in bridge if lab.startswith("Gross profit"))
    assert gp == pytest.approx(0.310, abs=1e-3)
    assert any(lab.startswith("Professional fees") for lab, _v in bridge)
    # Bridge re-adds to FY25 within rounding.
    running = float(bridge[0][1] or 0.0)
    for lab, val in bridge[1:-1]:
        running += float(val or 0.0)
    assert running == pytest.approx(float(bridge[-1][1] or 0.0), abs=1e-3)


def test_ytd_compare_revenue_up_ebitda_down() -> None:
    pack = _synthetic_pack()
    rows = ytd_compare_rows(pack)
    rev = next(r for r in rows if r[0] == "Revenue")
    eb = next(r for r in rows if r[0] == "EBITDA")
    assert rev[4] == pytest.approx(3.0, abs=0.1)
    assert eb[4] == pytest.approx(-11.8, abs=0.2)


def test_plan_trading_emits_mix_bridge_ytd(monkeypatch: pytest.MonkeyPatch) -> None:
    pack = _synthetic_pack()
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: pack,
    )
    store = ExhibitStoreDoc(
        run_id="r1", deal_slug="synth", updated_at="", exhibits=[]
    )
    slides = plan_trading(commentary=None, store=store, requests=[])
    ids = [s.slide_id for s in slides]
    assert "ch_trading_margin" in ids
    assert "ch_trading_mix" in ids
    assert "ch_trading_bridge" in ids
    assert "ch_trading_ytd" in ids

    mix = next(s for s in slides if s.slide_id == "ch_trading_mix")
    assert mix.table is not None
    assert any("billings" in r[0].lower() or "municipal" in r[0].lower() for r in mix.table.rows)
    assert "Municipal" in (mix.headline or "")

    bridge = next(s for s in slides if s.slide_id == "ch_trading_bridge")
    assert bridge.table is not None
    assert any("FY24" in r[0] for r in bridge.table.rows)
    assert "fell" in (bridge.headline or "").lower() or "EBITDA" in (bridge.headline or "")

    ytd = next(s for s in slides if s.slide_id == "ch_trading_ytd")
    assert ytd.table is not None
    assert "YTD Jul-25" in ytd.table.headers[1]
    assert "YTD Jul-26" in ytd.table.headers[2]
    assert "up" in (ytd.headline or "").lower()


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "deals" / "test6").is_dir(),
    reason="Test6 deal data not present",
)
def test_build_trading_pack_from_test6() -> None:
    pack = build_trading_pack("test6")
    assert pack.has_streams
    assert pack.revenue_fy.get(2025) == pytest.approx(13.412, abs=0.02)
    assert (pack.fy.get("Municipal") or {}).get(2025) == pytest.approx(4.794, abs=0.01)
    assert pack.dc_billings == pytest.approx(3.078, abs=0.02)
    assert pack.has_bridge
    # YTD Jul-26 from extract; Jul-25 from monthly xlsx when readable.
    assert (pack.ytd.get("Revenue") or {}).get(2026) == pytest.approx(8.055, abs=0.02)
