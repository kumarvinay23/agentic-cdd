"""FDD Phase 5b — M7 cash conversion / capex workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, EightLabels, FactTableDoc, FddFact
from agetic_cdd_api.services_fdd_commentary import (
    CASH_CONV_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    _Line,
    build_cash_conversion_exhibit,
    ensure_phase5b_models,
)
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import save_fact_table


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _line(metric: str, year: int, value: float) -> _Line:
    return _Line(
        metric_key=metric,
        fiscal_year=year,
        value=value,
        fact_id=f"db:{metric}:{year}",
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
    )


def _fact(metric: str, year: int, value: float, *, statement: str = "CF") -> FddFact:
    return FddFact(
        fact_id=f"db:t:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=CellStatus.PROVEN,
        release_status=CellStatus.PROVEN,
        labels=EightLabels(statement=statement, line=metric.replace("_", " ").title()),
        currency="USD",
        scale="M",
    )


def test_cash_conversion_fcf_and_ratio() -> None:
    closed = date.today().year - 1
    lines = [
        _line("operating_cash_flow", closed, 9.0),
        _line("capex", closed, -3.0),  # signed CF outflow
        _line("ebitda", closed, 12.0),
    ]
    cells, notes = build_cash_conversion_exhibit(lines, year=closed)
    by = {c.metric_key: c for c in cells}
    assert by["operating_cash_flow"].value == pytest.approx(9.0)
    assert by["capex"].value == pytest.approx(3.0)  # absolute spend
    assert by["free_cash_flow"].value == pytest.approx(6.0)
    assert by["cash_conversion"].value == pytest.approx(75.0)
    assert by["fcf_conversion"].value == pytest.approx(50.0)
    assert all(c.model_id == "M7" for c in cells)
    assert all(c.exhibit_id == CASH_CONV_EXHIBIT_ID for c in cells)
    assert not any("missing" in n for n in notes if n.startswith("ocf_"))


def test_cash_conversion_holds_fcf_without_capex() -> None:
    closed = date.today().year - 1
    cells, notes = build_cash_conversion_exhibit(
        [_line("operating_cash_flow", closed, 9.0), _line("ebitda", closed, 12.0)],
        year=closed,
    )
    keys = {c.metric_key for c in cells}
    assert "free_cash_flow" not in keys
    assert "cash_conversion" in keys
    assert any("fcf_held" in n for n in notes)


def test_cash_conversion_aligns_ebitda_to_pack() -> None:
    closed = date.today().year - 1
    pack = "Compost Crew Monthly Financials 23YTD26.xlsx"
    workbook = "CC_Investor_Workbook_EXTERNAL.xlsx"
    lines = [
        _Line(
            metric_key="operating_cash_flow",
            fiscal_year=closed,
            value=0.6105,
            fact_id="db:ocf",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
        _Line(
            metric_key="capex",
            fiscal_year=closed,
            value=0.43,
            fact_id="db:capex",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
            sources=[pack],
        ),
        _Line(
            metric_key="ebitda",
            fiscal_year=closed,
            value=0.565,
            fact_id="db:eb:wb",
            currency="USD",
            scale="M",
            status=CellStatus.DOUBTFUL,
            sources=[workbook],
        ),
        _Line(
            metric_key="ebitda",
            fiscal_year=closed,
            value=0.5718,
            fact_id="db:eb:pack",
            currency="USD",
            scale="M",
            status=CellStatus.DOUBTFUL,
            sources=[pack],
        ),
    ]
    cells, _ = build_cash_conversion_exhibit(lines, year=closed)
    by = {c.metric_key: c for c in cells}
    assert by["ebitda"].value == pytest.approx(0.5718, rel=1e-3)
    assert by["cash_conversion"].value == pytest.approx(106.8, abs=0.5)


def test_ensure_m7_unblocks_sec_i(deal_root: Path) -> None:
    slug = "m7-cash"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="CashCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("operating_cash_flow", closed, 9.0),
                _fact("capex", closed, 3.0),
                _fact("ebitda", closed, 12.0, statement="IS"),
                _fact("revenue", closed, 100.0, statement="IS"),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="CashCo", build_qoe=True
    )
    assert summary.get("models", {}).get("sections", {}).get("SEC-I") is True
    assert any(e.exhibit_id == CASH_CONV_EXHIBIT_ID for e in store2.exhibits)

    draft = draft_section(
        "SEC-I",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="CashCo",
    )
    assert draft.held_back is False, draft.held_back_reason
    assert draft.cell_refs
    assert CASH_CONV_EXHIBIT_ID in draft.exhibit_ids

    doc = build_commentary(slug, manifest.run_id, company="CashCo", update_report_spec=True)
    assert "SEC-I" not in (doc.held_back_sections or [])
