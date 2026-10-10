"""Regressions for mislabelled / untied FDD figures (review round)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    ExhibitCell,
    FactTableDoc,
    FddFact,
)
from agetic_cdd_api.services_fdd_commentary import (
    _headline_figure_phrase,
    _qoe_has_real_adjustments,
    draft_section,
    sync_qoe_exhibit,
)
from agetic_cdd_api.services_fdd_models import (
    TRADING_EXHIBIT_ID,
    _Line,
    build_cash_conversion_exhibit,
    build_margin_exhibit,
    build_nwc_exhibit,
    build_trading_exhibit,
    ensure_phase5b_models,
)
from agetic_cdd_api.services_fdd_qoe import build_qoe_from_facts
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import save_fact_table, save_qoe_workbook


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _line(
    metric: str,
    year: int,
    value: float,
    *,
    status: CellStatus = CellStatus.PROVEN,
    scale: str = "M",
) -> _Line:
    return _Line(
        metric_key=metric,
        fiscal_year=year,
        value=value,
        fact_id=f"db:{metric}:{year}:{status.value}",
        currency="USD",
        scale=scale,
        status=status,
    )


def _fact(
    metric: str,
    year: int,
    value: float,
    *,
    status: CellStatus = CellStatus.PROVEN,
    statement: str = "IS",
) -> FddFact:
    return FddFact(
        fact_id=f"db:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=status,
        release_status=status,
        labels=EightLabels(statement=statement, line=metric.replace("_", " ").title()),
        currency="USD",
        scale="M",
    )


def test_prefer_proven_revenue_over_doubtful() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    lines = [
        _line("revenue", prior, 12.77, status=CellStatus.DOUBTFUL),
        _line("revenue", prior, 11.74, status=CellStatus.PROVEN),
        _line("revenue", closed, 14.35, status=CellStatus.DOUBTFUL),
        _line("revenue", closed, 13.28, status=CellStatus.PROVEN),
        _line("ebitda", prior, 1.11),
        _line("ebitda", closed, 0.56),
    ]
    cells, _ = build_trading_exhibit(lines, years=[closed, prior])
    by = {(c.metric_key, c.fiscal_year): c for c in cells}
    assert by[("revenue", closed)].value == pytest.approx(13.28)
    assert by[("revenue", prior)].value == pytest.approx(11.74)
    assert by[("revenue_yoy", closed)].value == pytest.approx(
        (13.28 - 11.74) / 11.74 * 100.0, rel=1e-3
    )


def test_yoy_from_loss_is_nm() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    cells, notes = build_trading_exhibit(
        [
            _line("ebitda", prior, -0.2),
            _line("ebitda", closed, 0.3),
            _line("revenue", prior, 10.0),
            _line("revenue", closed, 12.0),
        ],
        years=[closed, prior],
    )
    assert not any(c.metric_key == "ebitda_yoy" for c in cells)
    assert any("prior_loss" in n for n in notes)


def test_margin_ratio_normalised_to_pp() -> None:
    closed = date.today().year - 1
    prior = closed - 1
    cells, _ = build_margin_exhibit(
        [
            _line("revenue", prior, 10.0),
            _line("revenue", closed, 12.0),
            _line("gross_margin", prior, 0.32, scale="%"),
            _line("gross_margin", closed, 0.30, scale="%"),
        ],
        years=[closed, prior],
    )
    by = {(c.metric_key, c.fiscal_year): c for c in cells}
    assert by[("gross_margin", closed)].value == pytest.approx(30.0)
    assert by[("gross_margin_delta_pp", closed)].value == pytest.approx(-2.0)
    assert by[("gross_margin_delta_pp", closed)].scale == "pp"
    assert by[("gross_margin_delta_pp", closed)].currency is None


def test_cash_exhibit_without_ocf_is_empty() -> None:
    closed = date.today().year - 1
    cells, notes = build_cash_conversion_exhibit(
        [_line("ebitda", closed, 0.57)],
        year=closed,
    )
    assert cells == []
    assert any("ocf_missing" in n or "held_ocf" in n for n in notes)


def test_nwc_uses_current_liabilities_fallback() -> None:
    closed = date.today().year - 1
    cells, notes = build_nwc_exhibit(
        [
            _line("accounts_receivable", closed, 1.223),
            _line("current_liabilities", closed, 1.102),
        ],
        year=closed,
    )
    nwc = next(c for c in cells if c.metric_key == "nwc")
    assert nwc.value == pytest.approx(1.223 - 1.102)
    assert "nwc_liabilities_missing" not in notes
    assert any("current_liabilities" in n for n in notes)


def test_headline_does_not_mislike_ebitda_margin_as_ebitda() -> None:
    cell = ExhibitCell(
        cell_id="ebitda_margin_fy2025",
        exhibit_id=TRADING_EXHIBIT_ID,
        label="EBITDA margin",
        value=0.04,
        metric_key="ebitda_margin",
        currency="USD",
        scale="%",
        fiscal_year=2025,
        fact_id="x",
    )
    phrase = _headline_figure_phrase("{{ex:t}}", cell, qoe_pending=False)
    assert "EBITDA margin" in phrase
    assert "USD" not in phrase


def test_seed_qoe_stays_unadjusted(deal_root: Path) -> None:
    slug = "fig-qoe"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="FigCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", closed, 13.28),
                _fact("ebitda", closed, 0.57),
            ],
        )
    )
    qoe = build_qoe_from_facts(slug, manifest.run_id)
    save_qoe_workbook(qoe)
    assert _qoe_has_real_adjustments(qoe) is False
    store = sync_qoe_exhibit(slug, manifest.run_id, store=store)
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="FigCo", build_qoe=False
    )
    draft = draft_section(
        "SEC-E",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="FigCo",
    )
    body = draft.body or ""
    assert "unadjusted" in body.lower() or "QoE pending" in body
    assert "explained in the QoE walk" not in body
    es = draft_section(
        "SEC-ES",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="FigCo",
    )
    title = (es.action_title or "").lower()
    assert "unadjusted" in title or "adjusted" not in title


def test_sec_f_holds_without_bs_lines(deal_root: Path) -> None:
    slug = "fig-bs"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="BsCo", prefer_current_release=True
    )
    # Drop phase-0 stub BS exhibits so the section must rely on real facts.
    store = store.model_copy(
        update={
            "exhibits": [
                ex
                for ex in store.exhibits
                if not (ex.exhibit_id or "").startswith("ex_hist_")
                and ex.exhibit_id not in {"ex_m8_bs", "ex_db_bs"}
            ]
        }
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("revenue", closed, 10.0),
                _fact("ebitda", closed, 1.0),
            ],
        )
    )
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="BsCo", build_qoe=True
    )
    draft = draft_section(
        "SEC-F",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="BsCo",
    )
    assert draft.held_back is True, draft.held_back_reason
    assert "EBITDA margin" not in (draft.body or "")
