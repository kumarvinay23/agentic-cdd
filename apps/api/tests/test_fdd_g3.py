"""FDD G3 — automatic model check packs gate exhibits."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FactTableDoc,
    FddFact,
    FigureType,
)
from agetic_cdd_api.services_fdd_checks import (
    G3_HELD_PREFIX,
    apply_g3_to_exhibits,
    run_model_check_packs,
)
from agetic_cdd_api.services_fdd_commentary import draft_section
from agetic_cdd_api.services_fdd_models import (
    NET_DEBT_EXHIBIT_ID,
    NWC_EXHIBIT_ID,
    ensure_phase5b_models,
)
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import (
    load_manifest,
    load_model_checks,
    save_fact_table,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


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


def _bs_fact(metric: str, year: int, value: float) -> FddFact:
    f = _fact(metric, year, value)
    return f.model_copy(
        update={"labels": EightLabels(statement="BS", line=metric.replace("_", " ").title())}
    )


def test_g3_passes_on_sound_models(deal_root: Path) -> None:
    slug = "g3-ok"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="G3Co", prefer_current_release=True
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
                _fact("sga", closed, 18.0),
                _fact("cogs", closed, 60.0),
                _fact("operating_cash_flow", closed, 9.0),
                _fact("capex", closed, -3.0),
                _bs_fact("cash", closed, 3.0),
                _bs_fact("term_loan", closed, 10.0),
                _bs_fact("accounts_receivable", closed, 5.0),
                _bs_fact("inventory", closed, 2.0),
                _bs_fact("accounts_payable", closed, 4.0),
                _bs_fact("total_assets", closed, 50.0),
            ],
        )
    )
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="G3Co", build_qoe=True
    )
    assert summary.get("g3_passed") is True
    assert summary.get("models", {}).get("g3_passed") is True
    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    assert man.g3_passed is True
    assert man.models_built is True

    checks = load_model_checks(slug, manifest.run_id)
    assert checks is not None and checks.g3_passed
    assert not checks.held_back_exhibits

    # Model exhibits CHECKED
    model_ex = [
        e
        for e in store2.exhibits
        if e.exhibit_id.startswith("ex_m")
    ]
    assert model_ex
    assert all(e.status == ArtefactStatus.CHECKED for e in model_ex)


def test_g3_blocks_broken_net_debt(deal_root: Path) -> None:
    slug = "g3-bad-nd"
    store = ExhibitStoreDoc(
        run_id="r1",
        deal_slug=slug,
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id=NET_DEBT_EXHIBIT_ID,
                title="Net debt",
                section_id="SEC-H",
                status=ArtefactStatus.CHECKED,
                cells=[
                    ExhibitCell(
                        cell_id="gross_debt_fy2024",
                        exhibit_id=NET_DEBT_EXHIBIT_ID,
                        label="Gross debt",
                        value=10.0,
                        fact_id="m6:gross_debt:2024",
                        metric_key="gross_debt",
                        fiscal_year=2024,
                        model_id="M6",
                        figure_type=FigureType.REPORTED,
                    ),
                    ExhibitCell(
                        cell_id="cash_fy2024",
                        exhibit_id=NET_DEBT_EXHIBIT_ID,
                        label="Cash",
                        value=3.0,
                        fact_id="m6:cash:2024",
                        metric_key="cash",
                        fiscal_year=2024,
                        model_id="M6",
                        figure_type=FigureType.REPORTED,
                    ),
                    ExhibitCell(
                        cell_id="net_debt_fy2024",
                        exhibit_id=NET_DEBT_EXHIBIT_ID,
                        label="Net debt",
                        value=99.0,  # wrong — should be 7
                        fact_id="m6:net_debt:2024",
                        metric_key="net_debt",
                        fiscal_year=2024,
                        model_id="M6",
                        figure_type=FigureType.CALCULATED,
                    ),
                ],
            )
        ],
    )
    doc = run_model_check_packs(store)
    assert doc.g3_passed is False
    assert NET_DEBT_EXHIBIT_ID in doc.held_back_exhibits
    pack = next(p for p in doc.packs if p.exhibit_id == NET_DEBT_EXHIBIT_ID)
    assert any(c.check_id == "net_debt_formula" and not c.passed for c in pack.checks)

    store2 = apply_g3_to_exhibits(store, doc)
    nd = next(e for e in store2.exhibits if e.exhibit_id == NET_DEBT_EXHIBIT_ID)
    assert nd.status == ArtefactStatus.DRAFT
    assert any(str(f).startswith(G3_HELD_PREFIX) for f in nd.footnotes)


def test_g3_hold_blocks_commentary_section(deal_root: Path) -> None:
    slug = "g3-hold-sec"
    (deal_root / slug).mkdir(parents=True)
    manifest, store, _ = ensure_phase0_run(slug, company="HoldCo", prefer_current_release=True)
    # Plant a broken net-debt exhibit after models would run — simulate G3 fail.
    closed = date.today().year - 1
    store = store.model_copy(
        update={
            "exhibits": list(store.exhibits)
            + [
                Exhibit(
                    exhibit_id=NET_DEBT_EXHIBIT_ID,
                    title="Net debt",
                    section_id="SEC-H",
                    status=ArtefactStatus.DRAFT,
                    footnotes=[f"{G3_HELD_PREFIX}net_debt formula failed"],
                    cells=[
                        ExhibitCell(
                            cell_id=f"net_debt_fy{closed}",
                            exhibit_id=NET_DEBT_EXHIBIT_ID,
                            label="Net debt",
                            value=1.0,
                            fact_id=f"m6:net_debt:{closed}",
                            metric_key="net_debt",
                            fiscal_year=closed,
                            model_id="M6",
                        )
                    ],
                )
            ]
        }
    )
    draft = draft_section(
        "SEC-H",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store,
        company="HoldCo",
    )
    assert draft.held_back is True
    assert draft.held_back_reason and "G3" in draft.held_back_reason


def test_g3_m3_accepts_negative_expense_sign() -> None:
    from agetic_cdd_api.services_fdd_checks import _check_m3_costs
    from agetic_cdd_api.services_fdd_models import COSTS_EXHIBIT_ID

    ex = Exhibit(
        exhibit_id=COSTS_EXHIBIT_ID,
        title="Costs",
        section_id="SEC-D",
        status=ArtefactStatus.CHECKED,
        cells=[
            ExhibitCell(
                cell_id="revenue_fy2024",
                exhibit_id=COSTS_EXHIBIT_ID,
                label="Revenue",
                value=100.0,
                fact_id="m3:revenue:2024",
                metric_key="revenue",
                fiscal_year=2024,
                model_id="M3",
            ),
            ExhibitCell(
                cell_id="cogs_fy2024",
                exhibit_id=COSTS_EXHIBIT_ID,
                label="COGS",
                value=-60.0,  # natural expense sign
                fact_id="m3:cogs:2024",
                metric_key="cogs",
                fiscal_year=2024,
                model_id="M3",
            ),
            ExhibitCell(
                cell_id="cogs_pct_revenue_fy2024",
                exhibit_id=COSTS_EXHIBIT_ID,
                label="COGS %",
                value=60.0,
                fact_id="m3:cogs_pct:2024",
                metric_key="cogs_pct_revenue",
                fiscal_year=2024,
                model_id="M3",
                figure_type=FigureType.CALCULATED,
            ),
        ],
    )
    checks = _check_m3_costs(ex, model_id="M3", exhibit_id=COSTS_EXHIBIT_ID)
    pct = next(c for c in checks if c.check_id.startswith("cogs_pct_revenue"))
    assert pct.passed is True


def test_g3_held_footnote_survives_cap() -> None:
    from agetic_cdd_api.fdd_schemas import ModelCheckPack, ModelChecksDoc
    from agetic_cdd_api.services_fdd_checks import apply_g3_to_exhibits

    feet = [f"note_{i}" for i in range(20)]
    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="cap",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id=NET_DEBT_EXHIBIT_ID,
                title="Net debt",
                section_id="SEC-H",
                status=ArtefactStatus.CHECKED,
                footnotes=feet,
                cells=[
                    ExhibitCell(
                        cell_id="net_debt_fy2024",
                        exhibit_id=NET_DEBT_EXHIBIT_ID,
                        label="Net debt",
                        value=1.0,
                        fact_id="m6:net_debt:2024",
                        metric_key="net_debt",
                        fiscal_year=2024,
                        model_id="M6",
                    )
                ],
            )
        ],
    )
    doc = ModelChecksDoc(
        run_id="r",
        deal_slug="cap",
        updated_at="t",
        packs=[
            ModelCheckPack(
                model_id="M6",
                exhibit_id=NET_DEBT_EXHIBIT_ID,
                checks_passed=False,
                held_back=True,
                held_back_reason="formula failed",
            )
        ],
        g3_passed=False,
        held_back_exhibits=[NET_DEBT_EXHIBIT_ID],
    )
    store2 = apply_g3_to_exhibits(store, doc)
    nd = store2.exhibits[0]
    assert nd.footnotes and str(nd.footnotes[0]).startswith(G3_HELD_PREFIX)
    assert len(nd.footnotes) <= 12


def test_g3_nwc_liabilities_missing_blocks(deal_root: Path) -> None:
    store = ExhibitStoreDoc(
        run_id="r",
        deal_slug="nwc",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id=NWC_EXHIBIT_ID,
                title="NWC",
                section_id="SEC-G",
                status=ArtefactStatus.CHECKED,
                footnotes=["nwc_liabilities_missing"],
                cells=[
                    ExhibitCell(
                        cell_id="accounts_receivable_fy2024",
                        exhibit_id=NWC_EXHIBIT_ID,
                        label="AR",
                        value=5.0,
                        fact_id="m5:ar:2024",
                        metric_key="accounts_receivable",
                        fiscal_year=2024,
                        model_id="M5",
                    ),
                    ExhibitCell(
                        cell_id="nwc_fy2024",
                        exhibit_id=NWC_EXHIBIT_ID,
                        label="NWC",
                        value=5.0,
                        fact_id="m5:nwc:2024",
                        metric_key="nwc",
                        fiscal_year=2024,
                        model_id="M5",
                    ),
                ],
            )
        ],
    )
    doc = run_model_check_packs(store)
    assert doc.g3_passed is False
    assert NWC_EXHIBIT_ID in doc.held_back_exhibits
