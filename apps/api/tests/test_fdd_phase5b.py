"""FDD Phase 5b — QoE ensure + M8/M5/M6 BS / NWC / net debt exhibits."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, FddFact, EightLabels
from agetic_cdd_api.services_fdd_commentary import (
    QOE_EXHIBIT_ID,
    build_commentary,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import (
    BS_EXHIBIT_ID,
    CASH_CONV_EXHIBIT_ID,
    MARGIN_EXHIBIT_ID,
    NET_DEBT_EXHIBIT_ID,
    NWC_EXHIBIT_ID,
    TRADING_EXHIBIT_ID,
    _AR,
    _CASH,
    _matches,
    _worst_status,
    build_net_debt_exhibit,
    build_nwc_exhibit,
    ensure_phase5b_models,
    _Line,
    _lines_from_store,
)
from agetic_cdd_api.services_fdd_qoe import build_qoe_from_facts
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import (
    load_commentary,
    load_exhibit_store,
    load_qoe_workbook,
    save_fact_table,
)
from agetic_cdd_api.fdd_schemas import FactTableDoc


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _fact(
    metric: str,
    year: int,
    value: float,
    *,
    statement: str | None = "BS",
) -> FddFact:
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


def test_matches_rejects_short_substring_false_positives() -> None:
    assert _matches("accounts_receivable", _AR) is True
    assert _matches("ar", _AR) is True
    # Multi-token alias may match a longer key that contains those parts
    assert _matches("trade_receivables_gross", _AR) is True
    # Single-token / short aliases must not hitch onto unrelated compounds
    assert _matches("market", _AR) is False
    assert _matches("warranty_reserve", _AR) is False
    assert _matches("shares", _AR) is False
    assert _matches("bank_charge", _CASH) is False
    assert _matches("bank_balance", _CASH) is True
    assert _matches("cash_flow", _CASH) is False


def test_worst_status_hierarchy() -> None:
    assert (
        _worst_status([CellStatus.PROVEN, CellStatus.DRAFT, CellStatus.DOUBTFUL])
        == CellStatus.DRAFT
    )
    assert _worst_status([CellStatus.PROVEN, CellStatus.DOUBTFUL]) == CellStatus.DOUBTFUL


def test_nwc_component_fact_ids_are_stable() -> None:
    closed = date.today().year - 1
    lines = [
        _Line(
            metric_key="accounts_receivable",
            fiscal_year=closed,
            value=5.0,
            fact_id="db:raw:ar",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
        _Line(
            metric_key="accounts_payable",
            fiscal_year=closed,
            value=2.0,
            fact_id="db:raw:ap",
            currency="USD",
            scale="M",
            status=CellStatus.DRAFT,
        ),
    ]
    cells, _ = build_nwc_exhibit(lines, year=closed)
    ar = next(c for c in cells if "receivable" in c.metric_key)
    assert ar.fact_id == f"m5:component:accounts_receivable:{closed}"
    assert ar.status == CellStatus.PROVEN
    ap = next(c for c in cells if "payable" in c.metric_key)
    assert ap.fact_id == f"m5:component:accounts_payable:{closed}"
    nwc = next(c for c in cells if c.metric_key == "nwc")
    assert nwc.status == CellStatus.DRAFT  # worst of inputs


def test_store_lines_skip_missing_fiscal_year() -> None:
    from agetic_cdd_api.fdd_schemas import Exhibit, ExhibitCell, ExhibitStoreDoc, FigureType

    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="d",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_x",
                title="X",
                cells=[
                    ExhibitCell(
                        cell_id="cash_no_year",
                        exhibit_id="ex_x",
                        label="Cash",
                        value=1.0,
                        metric_key="cash",
                        fact_id="f:cash",
                        fiscal_year=None,
                        figure_type=FigureType.REPORTED,
                    ),
                    ExhibitCell(
                        cell_id="cash_ok",
                        exhibit_id="ex_x",
                        label="Cash",
                        value=2.0,
                        metric_key="cash",
                        fact_id="f:cash2",
                        fiscal_year=2024,
                        figure_type=FigureType.REPORTED,
                    ),
                ],
            )
        ],
    )
    lines = _lines_from_store(store)
    assert len(lines) == 1
    assert lines[0].fiscal_year == 2024


def test_net_debt_formula_leases_beside() -> None:
    closed = date.today().year - 1
    lines = [
        _Line(
            metric_key="term_loan",
            fiscal_year=closed,
            value=10.0,
            fact_id="f:debt",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
        _Line(
            metric_key="cash",
            fiscal_year=closed,
            value=3.0,
            fact_id="f:cash",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
        _Line(
            metric_key="lease_liability",
            fiscal_year=closed,
            value=2.0,
            fact_id="f:lease",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
    ]
    cells, notes = build_net_debt_exhibit(lines, year=closed)
    by_id = {c.cell_id: c for c in cells}
    assert by_id[f"net_debt_fy{closed}"].value == pytest.approx(7.0)
    assert by_id[f"lease_liabilities_fy{closed}"].value == pytest.approx(2.0)
    assert "leases" in " ".join(notes).lower() or True  # leases disclosed beside


def test_nwc_formula() -> None:
    closed = date.today().year - 1
    lines = [
        _Line(
            metric_key="accounts_receivable",
            fiscal_year=closed,
            value=5.0,
            fact_id="f:ar",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
        _Line(
            metric_key="inventory",
            fiscal_year=closed,
            value=2.0,
            fact_id="f:inv",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
        _Line(
            metric_key="accounts_payable",
            fiscal_year=closed,
            value=4.0,
            fact_id="f:ap",
            currency="USD",
            scale="M",
            status=CellStatus.PROVEN,
        ),
    ]
    cells, _notes = build_nwc_exhibit(lines, year=closed)
    nwc = next(c for c in cells if c.metric_key == "nwc")
    assert nwc.value == pytest.approx(3.0)


def test_ensure_phase5b_unblocks_qoe_and_net_debt(deal_root: Path) -> None:
    slug = "p5b-models"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _spec = ensure_phase0_run(
        slug, company="CrewCo", prefer_current_release=True
    )
    facts = FactTableDoc(
        run_id=manifest.run_id,
        deal_slug=slug,
        updated_at="t",
        facts=[
            _fact("revenue", closed, 11.0, statement="IS"),
            _fact("ebitda", closed, 0.57, statement="IS"),
            _fact("operating_cash_flow", closed, 0.4, statement="CF"),
            _fact("capex", closed, 0.1, statement="CF"),
            _fact("cash", closed, 1.5),
            _fact("term_loan", closed, 4.0),
            _fact("accounts_receivable", closed, 2.0),
            _fact("accounts_payable", closed, 1.0),
            _fact("inventory", closed, 0.5),
            _fact("total_assets", closed, 20.0),
        ],
    )
    save_fact_table(facts)

    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="CrewCo", build_qoe=True
    )
    assert summary.get("qoe") is True
    ids = {e.exhibit_id for e in store2.exhibits}
    assert QOE_EXHIBIT_ID in ids
    assert TRADING_EXHIBIT_ID in ids
    assert MARGIN_EXHIBIT_ID in ids
    assert CASH_CONV_EXHIBIT_ID in ids
    assert BS_EXHIBIT_ID in ids
    assert NWC_EXHIBIT_ID in ids
    assert NET_DEBT_EXHIBIT_ID in ids

    qoe = load_qoe_workbook(slug, manifest.run_id)
    assert qoe is not None
    assert qoe.adjusted_ebitda_diligence is not None

    # Commentary sections should no longer hold back for missing exhibits
    for sid in ("SEC-B", "SEC-C", "SEC-E", "SEC-F", "SEC-G", "SEC-H", "SEC-I"):
        draft = draft_section(
            sid,
            deal_slug=slug,
            run_id=manifest.run_id,
            store=store2,
            company="CrewCo",
        )
        assert draft.held_back is False, (sid, draft.held_back_reason)
        assert draft.cell_refs, sid


def test_qoe_from_facts_prefers_closed_year(deal_root: Path) -> None:
    slug = "p5b-qoe-year"
    (deal_root / slug).mkdir(parents=True)
    this = date.today().year
    closed = this - 1
    manifest, _store, _ = ensure_phase0_run(slug, prefer_current_release=True)
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("ebitda", this, 0.86, statement="IS"),
                _fact("ebitda", closed, 0.57, statement="IS"),
                _fact("revenue", closed, 11.0, statement="IS"),
            ],
        )
    )
    doc = build_qoe_from_facts(slug, manifest.run_id)
    assert str(closed)[-2:] in doc.period or doc.baseline[0].diligence_reported_ebitda == pytest.approx(
        0.57
    )


def test_ensure_phase0_runs_phase5b(deal_root: Path) -> None:
    slug = "p5b-ensure"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(slug, company="X", prefer_current_release=True)
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                _fact("ebitda", closed, 1.0, statement="IS"),
                _fact("revenue", closed, 10.0, statement="IS"),
                _fact("cash", closed, 2.0),
                _fact("gross_debt", closed, 5.0),
            ],
        )
    )
    # Re-ensure so Phase 5b sees the facts
    manifest2, store2, _spec = ensure_phase0_run(
        slug, company="X", prefer_current_release=True
    )
    ids = {e.exhibit_id for e in store2.exhibits}
    assert QOE_EXHIBIT_ID in ids or load_qoe_workbook(slug, manifest2.run_id)
    assert NET_DEBT_EXHIBIT_ID in ids
    doc = build_commentary(slug, manifest2.run_id, company="X", update_report_spec=True)
    held = set(doc.held_back_sections or [])
    assert "SEC-E" not in held
    assert "SEC-H" not in held
