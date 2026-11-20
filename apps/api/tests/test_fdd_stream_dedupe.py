"""Revenue-by-stream must not double-count Compost Sales vs Compost & products."""

from __future__ import annotations

from types import SimpleNamespace

from agetic_cdd_api.services_fdd_exhibit_contract import (
    check_exhibit_footing,
    revenue_stream_contract_from_pack,
)
from agetic_cdd_api.services_fdd_trading import TradingPack, _discover_product_streams


def _row(caption: str, year: int, value: float) -> SimpleNamespace:
    return SimpleNamespace(
        caption=caption,
        fiscal_year=year,
        period_length="FY",
        value=value,
        unit="usd",
        scale="1",
    )


def test_compost_sales_does_not_duplicate_compost_and_products() -> None:
    rows = []
    for y, comps in ((2023, 0.014), (2024, 0.250), (2025, 0.180)):
        rows.append(_row("Compost & products", y, comps * 1_000_000))
        rows.append(_row("Compost Sales", y, comps * 1_000_000))
        rows.append(_row("Residential Sales", y, 1_000_000))
    streams = _discover_product_streams(
        rows,
        years=(2023, 2024, 2025),
        scale="M",
        seed=(("Residential", ("Residential Sales", "Residential")),),
    )
    labels = [lab for lab, _ in streams]
    assert "Compost & products" in labels or any("compost" in lab.lower() for lab in labels)
    # Must not keep both the long product label and the stripped "Compost" stem.
    lower = [lab.lower() for lab in labels]
    if "compost & products" in lower:
        assert "compost" not in lower


def test_soft_hold_skipped_when_streams_foot_to_pack_revenue() -> None:
    from agetic_cdd_api.fdd_schemas import SlideSpec, SlideTable
    from agetic_cdd_api.services_fdd_exhibit_contract import apply_contract_or_hold

    pack = TradingPack(deal_slug="dedupe", scale="M", years=(2024, 2025))
    pack.stream_labels = ["Residential", "Municipal", "Commercial"]
    pack.fy = {
        "Residential": {2024: 1.967, 2025: 1.983},
        "Municipal": {2024: 4.243, 2025: 4.794},
        "Commercial": {2024: 5.659, 2025: 6.635},
        "Revenue": {2024: 11.869, 2025: 13.412},
    }
    pack.revenue_fy = {2024: 11.869, 2025: 13.412}
    contract = revenue_stream_contract_from_pack(pack)
    assert contract is not None
    assert all(r.ok for r in check_exhibit_footing(contract))
    slide = SlideSpec(
        slide_id="ch_tx_business",
        layout="section_table_obs",
        headline="Revenue reached $13.41m in FY25",
        table=SlideTable(headers=["Stream", "FY25"], rows=[["Residential", "1,983"]]),
        observations=["Municipal growth"],
    )
    out = apply_contract_or_hold(slide, contract, mode="soft")
    assert out is not None
    assert out.exhibit_contract is not None
    assert out.exhibit_contract.footing_status == "ok"
    assert not any("does not foot" in str(fn).lower() for fn in (out.footnotes or []))
    assert not any("does not foot" in str(o).lower() for o in (out.observations or []))


def test_stream_contract_foots_without_duplicate_compost() -> None:
    pack = TradingPack(deal_slug="dedupe", scale="M", years=(2023, 2024, 2025))
    pack.stream_labels = [
        "Residential",
        "Municipal",
        "Commercial",
        "Other revenue",
        "Key Compostables",
        "Compost & products",
    ]
    pack.fy = {
        "Residential": {2023: 1.651, 2024: 1.967, 2025: 1.983},
        "Municipal": {2023: 1.720, 2024: 4.243, 2025: 4.794},
        "Commercial": {2023: 4.143, 2024: 4.966, 2025: 5.616},
        "Other revenue": {2023: 0.030, 2024: 0.130, 2025: 0.143},
        "Key Compostables": {2023: 0.0, 2024: 0.312, 2025: 0.695},
        "Compost & products": {2023: 0.014, 2024: 0.250, 2025: 0.180},
        "Revenue": {2023: 7.558, 2024: 11.869, 2025: 13.412},
    }
    pack.revenue_fy = {2023: 7.558, 2024: 11.869, 2025: 13.412}
    contract = revenue_stream_contract_from_pack(pack)
    assert contract is not None
    results = check_exhibit_footing(contract)
    assert all(r.ok for r in results), [r.message for r in results if not r.ok]
    assert all("ex_" not in (r.message or "") for r in results)
