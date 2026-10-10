"""Workbook-vs-ledger basis, net-debt holdback, and gap disclosure."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus, EightLabels, FactTableDoc, FddFact
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    ProofLevel,
    ReleaseCellStatus,
    ReleasedCell,
)
from agetic_cdd_api.services_fdd_bridge import released_cell_to_fact
from agetic_cdd_api.services_fdd_commentary import (
    _material_limitations,
    _request_title_is_open_year,
    _source_gap_limitations,
    draft_section,
)
from agetic_cdd_api.services_fdd_models import ensure_phase5b_models
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import save_fact_table


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def test_bridge_prefers_workbook_ebitda_over_qbo() -> None:
    release = DatabookRelease(
        release_id="rel",
        deal_slug="d",
        version=1,
        created_at="t",
        cells=[],
    )
    cell = ReleasedCell(
        metric_key="ebitda",
        fiscal_year=2025,
        status=ReleaseCellStatus.DOUBTFUL,
        value=0.572,
        sources=["qbo ledger"],
        alternatives=[
            {
                "value": 0.565,
                "sources": ["investor workbook"],
                "chosen": False,
            }
        ],
        proof_level=ProofLevel.L1,
    )
    fact = released_cell_to_fact(cell, release, draft_mode=False)
    assert fact.value == pytest.approx(0.565)
    assert any("qbo" in " ".join(a.get("sources") or []).lower() for a in fact.alternatives)


def test_all_source_gaps_listed(deal_root: Path) -> None:
    slug = "gaps-all"
    (deal_root / slug).mkdir(parents=True)
    manifest, _, _ = ensure_phase0_run(slug, prefer_current_release=True)
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="r25",
                    metric_key="revenue",
                    fiscal_year=2025,
                    value=13.282,
                    status=CellStatus.DOUBTFUL,
                    release_status=CellStatus.DOUBTFUL,
                    labels=EightLabels(statement="IS", line="Revenue"),
                    sources=["investor workbook"],
                    alternatives=[{"value": 13.412, "sources": ["qbo ledger"]}],
                ),
                FddFact(
                    fact_id="r24",
                    metric_key="revenue",
                    fiscal_year=2024,
                    value=11.741,
                    status=CellStatus.DOUBTFUL,
                    release_status=CellStatus.DOUBTFUL,
                    labels=EightLabels(statement="IS", line="Revenue"),
                    sources=["investor workbook"],
                    alternatives=[{"value": 11.869, "sources": ["qbo ledger"]}],
                ),
                FddFact(
                    fact_id="gp25",
                    metric_key="gross_profit",
                    fiscal_year=2025,
                    value=3.952,
                    status=CellStatus.DOUBTFUL,
                    release_status=CellStatus.DOUBTFUL,
                    labels=EightLabels(statement="IS", line="Gross profit"),
                    sources=["investor workbook"],
                    alternatives=[{"value": 4.082, "sources": ["qbo ledger"]}],
                ),
                FddFact(
                    fact_id="gp24",
                    metric_key="gross_profit",
                    fiscal_year=2024,
                    value=3.718,
                    status=CellStatus.DOUBTFUL,
                    release_status=CellStatus.DOUBTFUL,
                    labels=EightLabels(statement="IS", line="Gross profit"),
                    sources=["investor workbook"],
                    alternatives=[{"value": 3.772, "sources": ["qbo ledger"]}],
                ),
            ],
        )
    )
    # Full reconciliation only on SEC-K; other sections get a one-line pointer.
    pointer = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-B")
    assert len(pointer) == 1
    assert pointer[0].item_id == "gap:reconciliation:sec-k"
    assert "key findings" in pointer[0].text.lower() or "sec-k" in pointer[0].text.lower()

    lims = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-K")
    keys = {lim.item_id for lim in lims}
    assert "gap:revenue:2025" in keys
    assert "gap:revenue:2024" in keys
    assert "gap:gross_profit:2025" in keys
    assert "gap:gross_profit:2024" in keys
    for lim in lims:
        assert "qbo" in lim.text.lower() or "ledger" in lim.text.lower()
        assert "gap" in lim.text.lower()
        assert "workbook" in lim.text.lower() or "investor" in lim.text.lower()
        assert "claimed" not in lim.text.lower()
        # Always workbook-first (not ledger-first / contradicted restatement).
        assert lim.text.lower().index("workbook") < lim.text.lower().index("ledger")


def test_sec_h_holds_without_debt_cells(deal_root: Path) -> None:
    slug = "nd-hold"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="NdCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="r",
                    metric_key="revenue",
                    fiscal_year=closed,
                    value=10.0,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="Revenue"),
                    currency="USD",
                    scale="M",
                ),
            ],
        )
    )
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="NdCo", build_qoe=True
    )
    draft = draft_section(
        "SEC-H",
        deal_slug=slug,
        run_id=manifest.run_id,
        store=store2,
        company="NdCo",
    )
    assert draft.held_back is True, draft.held_back_reason
    assert "figures pending" not in (draft.body or "").lower()
    assert "no numeric cells" not in (draft.body or "").lower()


def test_trading_and_qoe_share_workbook_ebitda(deal_root: Path) -> None:
    slug = "eb-basis"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="EbCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="eb",
                    metric_key="ebitda",
                    fiscal_year=closed,
                    value=0.565,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="EBITDA"),
                    currency="USD",
                    scale="M",
                    sources=["investor workbook"],
                    alternatives=[{"value": 0.572, "sources": ["qbo ledger"]}],
                ),
                FddFact(
                    fact_id="r",
                    metric_key="revenue",
                    fiscal_year=closed,
                    value=13.28,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="Revenue"),
                    currency="USD",
                    scale="M",
                    sources=["investor workbook"],
                ),
            ],
        )
    )
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="EbCo", build_qoe=True
    )
    trading = next(ex for ex in store2.exhibits if ex.exhibit_id == "ex_m1_trading")
    eb_cell = next(c for c in trading.cells if c.metric_key == "ebitda")
    assert eb_cell.value == pytest.approx(0.565)
    from agetic_cdd_api.services_fdd_store import load_qoe_workbook

    qoe = load_qoe_workbook(slug, manifest.run_id)
    assert qoe is not None
    assert qoe.adjusted_ebitda_diligence == pytest.approx(0.565)
    lims = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-K")
    assert any("0.572" in lim.text for lim in lims)
    pointer = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-E")
    assert len(pointer) == 1 and "sec-k" in pointer[0].text.lower()
    # Same underlying value must not render as 0.56 in one place and 0.57 in another.
    from agetic_cdd_api.services_fdd_tokens import format_fdd_number

    assert format_fdd_number(0.565) == "0.57"
    assert eb_cell.display == "0.57"


def test_ebitda_claim_gap_named_sources(deal_root: Path) -> None:
    slug = "eb-gap"
    (deal_root / slug).mkdir(parents=True)
    manifest, _, _ = ensure_phase0_run(slug, prefer_current_release=True)
    from agetic_cdd_api.fdd_schemas import ClaimsLedgerDoc, ClaimsLedgerEntry
    from agetic_cdd_api.services_fdd_store import save_claims_ledger

    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="eb",
                    metric_key="ebitda",
                    fiscal_year=2025,
                    value=0.565,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="EBITDA"),
                    sources=["investor workbook"],
                ),
            ],
        )
    )
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="cl_eb",
                    source_agent="historical_performance",
                    text="ebitda_fy2025_usd_m = 0.572",
                    kind="financial",
                    metric_key="ebitda",
                    fiscal_year=2025,
                    claimed_value=0.572,
                    databook_value=0.565,
                    test_result="contradicted",
                    failed=True,
                ),
            ],
        )
    )
    lims = _source_gap_limitations(slug, manifest.run_id, section_id="SEC-K")
    assert any("gap:ebitda:2025" == lim.item_id for lim in lims)
    text = next(lim.text for lim in lims if lim.item_id == "gap:ebitda:2025")
    assert "QBO ledger" in text
    assert "investor workbook" in text
    assert "0.007" in text
    assert text.lower().index("workbook") < text.lower().index("ledger")


def test_open_year_request_titles_skipped_from_key_findings(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import RequestListDoc, RequestListItem
    from agetic_cdd_api.services_fdd_store import save_request_list

    assert _request_title_is_open_year(
        "FY2026 ebitda: investor workbook 0.439 vs QBO ledger 0.859 (contradicted)",
        2025,
    )
    assert not _request_title_is_open_year(
        "FY2025 ebitda: investor workbook 0.565 vs monthly pack 0.572 (contradicted)",
        2025,
    )

    slug = "open-yr"
    (deal_root / slug).mkdir(parents=True)
    manifest, _, _ = ensure_phase0_run(slug, prefer_current_release=True)
    save_request_list(
        RequestListDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            items=[
                RequestListItem(
                    request_id="r1",
                    title=(
                        "FY2026 ebitda: investor workbook 0.439 vs "
                        "QBO ledger 0.859 (contradicted)"
                    ),
                    status="pending",
                    blocking_sections=["SEC-K"],
                ),
                RequestListItem(
                    request_id="r2",
                    title="Facility schedule maturity dates",
                    status="pending",
                    blocking_sections=["SEC-K"],
                ),
            ],
        )
    )
    lims = _material_limitations(slug, manifest.run_id, section_id="SEC-K")
    texts = " | ".join(lim.text for lim in lims)
    assert "FY2026" not in texts
    assert "Facility schedule" in texts


def test_qoe_labels_reported_when_register_empty(deal_root: Path) -> None:
    slug = "qoe-labels"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="QoeCo", prefer_current_release=True
    )
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[
                FddFact(
                    fact_id="eb",
                    metric_key="ebitda",
                    fiscal_year=closed,
                    value=0.565,
                    status=CellStatus.PROVEN,
                    release_status=CellStatus.PROVEN,
                    labels=EightLabels(statement="IS", line="EBITDA"),
                    currency="USD",
                    scale="M",
                    sources=["investor workbook"],
                ),
            ],
        )
    )
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="QoeCo", build_qoe=True
    )
    qoe_ex = next(ex for ex in store2.exhibits if ex.exhibit_id == "ex_qoe_bridge")
    labels = {c.label for c in qoe_ex.cells}
    assert "Reported EBITDA" in labels
    assert not any("adjusted" in (c.label or "").lower() for c in qoe_ex.cells)
    assert not any("pro forma" in (c.label or "").lower() for c in qoe_ex.cells)


def test_held_bs_nwc_debt_cash_unhold_with_vdr_facts(deal_root: Path) -> None:
    """Monthly BS/CF metrics in the fact table should populate F/G/H/I."""
    slug = "held-vdr"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="HeldCo", prefer_current_release=True
    )
    facts = [
        FddFact(
            fact_id="r",
            metric_key="revenue",
            fiscal_year=closed,
            value=13.28,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="IS", line="Revenue"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="eb",
            metric_key="ebitda",
            fiscal_year=closed,
            value=0.565,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="IS", line="EBITDA"),
            currency="USD",
            scale="M",
            sources=["investor workbook"],
        ),
        FddFact(
            fact_id="cash",
            metric_key="cash",
            fiscal_year=closed,
            value=2.668,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="BS", line="Cash"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="ar",
            metric_key="accounts_receivable",
            fiscal_year=closed,
            value=1.223,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="BS", line="AR"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="ap",
            metric_key="accounts_payable",
            fiscal_year=closed,
            value=0.496,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="BS", line="AP"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="ltl",
            metric_key="long_term_liabilities",
            fiscal_year=closed,
            value=2.391,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="BS", line="LTL"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="ocf",
            metric_key="operating_cash_flow",
            fiscal_year=closed,
            value=0.611,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="CF", line="OCF"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="capex",
            metric_key="capex",
            fiscal_year=closed,
            value=-0.432,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="CF", line="Capex"),
            currency="USD",
            scale="M",
        ),
        FddFact(
            fact_id="sga",
            metric_key="sga",
            fiscal_year=closed,
            value=3.2,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(statement="IS", line="SG&A"),
            currency="USD",
            scale="M",
        ),
    ]
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=facts,
        )
    )
    from agetic_cdd_api.services_fdd_bridge import apply_facts_to_store

    store = apply_facts_to_store(store, facts)
    store2, summary = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="HeldCo", build_qoe=True
    )
    assert summary["models"]["sections"]["SEC-F"] is True
    assert summary["models"]["sections"]["SEC-G"] is True
    assert summary["models"]["sections"]["SEC-H"] is True
    assert summary["models"]["sections"]["SEC-I"] is True
    for sid in ("SEC-F", "SEC-G", "SEC-H", "SEC-I", "SEC-D", "SEC-K"):
        draft = draft_section(
            sid,
            deal_slug=slug,
            run_id=manifest.run_id,
            store=store2,
            company="HeldCo",
        )
        assert draft.held_back is False, (sid, draft.held_back_reason, draft.body)


def test_monthly_bs_year_end_extract() -> None:
    """Monthly BS date headers + Account-in-col-1 must yield Dec FY snapshots."""
    from agetic_cdd_api.services_databook_extract import rows_from_table

    table = {
        "name": "Monthly BS",
        "rows": [
            ["", "", "2024", "2025"],
            ["", "Account", "2024-12-31 00:00:00", "2025-12-31 00:00:00"],
            ["", "Cash", "3100000", "2667782.2"],
            ["", "Total Long-term Liabilities", "2758000", "2391201.96"],
            ["", "Accounts Payable", "336000", "496000"],
        ],
    }
    rows = rows_from_table(source_name="Monthly.xlsx", doc_id="m", table=table)
    by = {(r.metric_key, r.fiscal_year): r for r in rows if r.metric_key}
    assert by[("cash", 2025)].value == pytest.approx(2.6677822)
    assert by[("cash", 2025)].scale == "M"
    assert by[("long_term_liabilities", 2025)].value == pytest.approx(2.39120196)
    assert by[("accounts_payable", 2025)].value == pytest.approx(0.496)
