"""FDD Phase 5b — M2 revenue / margin walk workbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, EightLabels, FactTableDoc, FddFact
from agetic_cdd_api.services_fdd_commentary import (
    MARGIN_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    _Line,
    build_margin_exhibit,
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


def _fact(metric: str, year: int, value: float) -> FddFact:
    return FddFact(
        fact_id=f"db:t:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=CellStatus.PROVEN,
        release_status=CellStatus.PROVEN,
        labels=EightLabels(statement="IS", line=metric.replace("_", " ").title()),
        currency="USD",
        scale="M",
    )


def test_margin_walk_levels_and_delta_pp() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    lines = [
        _line("revenue", prior, 80.0),
        _line("revenue", closed, 100.0),
        _line("gross_profit", prior, 28.0),  # 35%
        _line("gross_profit", closed, 40.0),  # 40%
        _line("ebitda", prior, 10.0),  # 12.5%
        _line("ebitda", closed, 12.0),  # 12%
    ]
    cells, notes = build_margin_exhibit(lines, years=[closed, prior])
    by = {(c.metric_key, c.fiscal_year): c for c in cells}

    assert by[("gross_margin", closed)].value == pytest.approx(40.0)
    assert by[("gross_margin", prior)].value == pytest.approx(35.0)
    assert by[("gross_margin_delta_pp", closed)].value == pytest.approx(5.0)
    assert by[("ebitda_margin_delta_pp", closed)].value == pytest.approx(-0.5)
    assert by[("revenue_yoy", closed)].value == pytest.approx(25.0)
    assert by[("cogs", closed)].value == pytest.approx(60.0)  # 100 − 40
    assert any(n.startswith("gm_walk:") for n in notes)
    assert all(c.model_id == "M2" for c in cells)
    assert all(c.exhibit_id == MARGIN_EXHIBIT_ID for c in cells)


def test_margin_derives_gp_from_cogs() -> None:
    closed = date.today().year - 1
    cells, _ = build_margin_exhibit(
        [
            _line("revenue", closed, 100.0),
            _line("cogs", closed, 55.0),
        ],
        years=[closed],
    )
    by = {c.metric_key: c for c in cells}
    assert by["gross_profit"].value == pytest.approx(45.0)
    assert by["gross_margin"].value == pytest.approx(45.0)


def test_ensure_m2_unblocks_sec_c(deal_root: Path) -> None:
    slug = "m2-margin"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="MarginCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", prior, 80.0),
                _fact("revenue", closed, 100.0),
                _fact("gross_profit", prior, 28.0),
                _fact("gross_profit", closed, 40.0),
                _fact("ebitda", prior, 10.0),
                _fact("ebitda", closed, 12.0),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="MarginCo", build_qoe=True
    )
    assert summary.get("models", {}).get("sections", {}).get("SEC-C") is True
    assert any(e.exhibit_id == MARGIN_EXHIBIT_ID for e in store2.exhibits)

    draft = draft_section(
        "SEC-C",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="MarginCo",
    )
    assert draft.held_back is False, draft.held_back_reason
    assert draft.cell_refs
    assert MARGIN_EXHIBIT_ID in draft.exhibit_ids

    doc = build_commentary(
        slug, manifest.run_id, company="MarginCo", update_report_spec=True
    )
    assert "SEC-C" not in (doc.held_back_sections or [])
