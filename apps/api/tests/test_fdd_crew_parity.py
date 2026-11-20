"""Crew-parity: soft-held exhibits, IC findings set, appendix pages."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    EightLabels,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    Finding,
    FindingSeverity,
    FindingSource,
    SlideSpec,
    SlideTable,
)
from agetic_cdd_api.services_fdd_chapters import plan_appendix
from agetic_cdd_api.services_fdd_exhibit_contract import (
    apply_contract_or_hold,
    revenue_stream_contract_from_values,
    slide_may_draw_matrix,
)
from agetic_cdd_api.services_fdd_findings import _from_ic_diligence, assign_findings_register


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
        labels=EightLabels(),
    )


def _store_with_div_and_costs() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="parity",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m6_net_debt",
                title="Net debt",
                cells=[
                    _cell(
                        "ex_m6_net_debt",
                        "div25",
                        metric_key="dividends_payable",
                        value=0.558,
                        fiscal_year=2025,
                    )
                ],
            ),
            Exhibit(
                exhibit_id="ex_m3_costs",
                title="Costs",
                cells=[
                    _cell(
                        "ex_m3_costs",
                        "rent25",
                        metric_key="rent",
                        value=0.312,
                        fiscal_year=2025,
                    )
                ],
            ),
            Exhibit(
                exhibit_id="ex_m5_nwc",
                title="NWC",
                cells=[
                    _cell(
                        "ex_m5_nwc",
                        "ar25",
                        metric_key="accounts_receivable",
                        value=1.2,
                        fiscal_year=2025,
                    ),
                    _cell(
                        "ex_m5_nwc",
                        "inv25",
                        metric_key="inventory",
                        value=0.4,
                        fiscal_year=2025,
                    ),
                    _cell(
                        "ex_m5_nwc",
                        "ap25",
                        metric_key="accounts_payable",
                        value=0.7,
                        fiscal_year=2025,
                    ),
                    _cell(
                        "ex_m5_nwc",
                        "nwc25",
                        metric_key="nwc",
                        value=0.9,
                        fiscal_year=2025,
                    ),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell(
                        "ex_m1_trading",
                        "eb25",
                        metric_key="ebitda",
                        value=0.561,
                        fiscal_year=2025,
                    )
                ],
            ),
        ],
    )


def test_soft_hold_keeps_matrix_and_allows_draw() -> None:
    contract = revenue_stream_contract_from_values(
        contract_id="ex_soft",
        years=(2025,),
        stream_fy={"A": {2025: 10.0}, "B": {2025: 5.0}},
        total_fy={2025: 10.0},
    )
    contract = contract.model_copy(update={"hold_mode": "soft"})
    slide = SlideSpec(
        slide_id="ch_tx_business",
        layout="section_table_obs",
        headline="Revenue by stream",
        table=SlideTable(
            title="Revenue",
            headers=["Stream", "FY25"],
            rows=[["A", "10,000"], ["B", "5,000"], ["Revenue", "10,000"]],
        ),
    )
    held = apply_contract_or_hold(slide, contract, mode="soft")
    assert held is not None
    assert held.exhibit_contract is not None
    assert held.exhibit_contract.footing_status == "failed"
    assert held.exhibit_contract.hold_mode == "soft"
    # Soft hold keeps the matrix and does not paint · HELD on the banner.
    assert held.completeness_state == "complete"
    assert held.table is not None
    assert any("10,000" in str(c) for r in held.table.rows for c in r)
    assert slide_may_draw_matrix(held)
    assert all("ex_" not in str(fn) for fn in (held.footnotes or []))
    assert any("stream mix" in str(fn).lower() for fn in (held.footnotes or []))


def test_ic_diligence_expands_findings_register() -> None:
    store = _store_with_div_and_costs()
    ic = _from_ic_diligence(store, deal_slug="parity")
    assert len(ic) >= 3
    titles = " ".join(f.title.lower() for f in ic)
    assert "dividend" in titles
    assert any("unaudited" in (f.title + f.observation).lower() for f in ic)
    div = next(f for f in ic if "dividend" in f.title.lower())
    assert "$" in (div.quantified_effect or "") or "k" in (div.quantified_effect or "").lower()
    assert "0.558" not in (div.quantified_effect or "")  # raw store units must not leak
    lease = next((f for f in ic if "lease" in f.title.lower()), None)
    if lease is not None:
        assert "0.41" not in (lease.quantified_effect or "") or "$" in (lease.quantified_effect or "")
        assert "FY25 rent ~0.41" != (lease.quantified_effect or "")
    enriched, population = assign_findings_register(
        [
            *ic,
            Finding(
                finding_id="fnd_cost",
                severity=FindingSeverity.HIGH,
                title="Cost growth exceeds revenue",
                implication="Labour pressure",
                ask_management="Confirm plan",
                source=FindingSource.MODEL,
                quantified_effect="+$0.7m",
            ),
        ],
        population_limit=10,
    )
    assert len(population) >= 4
    assert any(f.display_id and "dividend" in f.title.lower() for f in enriched)
    assert all(f.display_id for f in enriched if f.display_id)


def test_receivables_and_loan_enter_population(monkeypatch) -> None:
    """Jul-26 AR roll + loan docs must surface inside the IC population."""
    from agetic_cdd_api.services_fdd_chapter_depth import CashBsPack

    bsp = CashBsPack(deal_slug="parity")
    bsp.ar = {2025: 1.223, "Jul-26": 1.607}
    bsp.dividend_paid = {"Jul-26": 0.186, 2025: 0.372}
    bsp.net_income = {2025: -0.56, "Jul-26": -0.18}
    bsp.dividend_accrual = {2025: 0.363}
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.build_cash_bs_pack",
        lambda *_a, **_k: bsp,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.list_data_room_files",
        lambda *_a, **_k: [
            {"document": "OG Loan Schedules.xlsx", "id": "D01"},
            {"document": "Asset Register.xlsx", "id": "D02"},
        ],
    )
    store = _store_with_div_and_costs()
    ic = _from_ic_diligence(store, deal_slug="parity")
    titles = " ".join(f.title.lower() for f in ic)
    assert "receivable" in titles
    assert "loan" in titles or "asset register" in titles
    _enriched, population = assign_findings_register(ic, population_limit=12)
    by_pop = {
        f.display_id: f
        for f in _enriched
        if f.display_id in population
    }
    pop_titles = " ".join(f.title.lower() for f in by_pop.values())
    assert "receivable" in pop_titles
    assert "loan" in pop_titles or "asset register" in pop_titles


def test_humanize_strips_wrong_period_verdict() -> None:
    from agetic_cdd_api.services_fdd_chapters import _humanize_request_title

    title = _humanize_request_title("Resolve claim ebitda FY2027 (wrong_period)")
    assert "wrong period" not in title.lower()
    assert "wrong_period" not in title.lower()
    assert "FY2027" in title or "fy2027" in title.lower()


def test_appendix_includes_crew_parity_pages() -> None:
    store = _store_with_div_and_costs()
    slides = plan_appendix(
        claims=None,
        deal_slug="",
        store=store,
        requests=["Confirm matching funds"],
    )
    ids = [s.slide_id for s in slides]
    assert "ch_app_monthly_nwc" in ids
    assert "ch_app_fy26_delivery" in ids
    assert "ch_app_funding_ic" in ids
    assert ids.index("ch_app_monthly_nwc") < ids.index("ch_app_glossary")
    assert ids.index("ch_app_fy26_delivery") < ids.index("ch_app_glossary")
    assert ids.index("ch_app_funding_ic") < ids.index("ch_app_glossary")
    nwc = next(s for s in slides if s.slide_id == "ch_app_monthly_nwc")
    assert nwc.table is not None
    assert any("AR" in h or "NWC" in h for h in nwc.table.headers)
    fy26 = next(s for s in slides if s.slide_id == "ch_app_fy26_delivery")
    assert fy26.table is not None
    closed = next(r for r in fy26.table.rows if "FY25 diligence" in r[0])
    assert closed[1] != "—"
    assert "561" in closed[1] or "0.56" in closed[1] or "$" in closed[1]


def test_deck_gate_strips_narrative_bind_from_held_completeness() -> None:
    from agetic_cdd_api.services_fdd_deck_gate import stamp_slide_completeness

    slide = SlideSpec(
        slide_id="ch_tx_business",
        layout="section_table_obs",
        chapter="transaction",
        headline="Revenue by stream",
        completeness_state="held",
        completeness_detail=(
            "ex_tx: period 2024 does not foot; Narrative bind: numbers without fact_id: 13.41"
        ),
        table=SlideTable(headers=["a"], rows=[["1"]]),
    )
    out = stamp_slide_completeness([slide])[0]
    assert "Narrative bind:" not in (out.completeness_detail or "")
    assert "does not foot" in (out.completeness_detail or "")
    assert all("Narrative bind:" not in str(fn) for fn in (out.footnotes or []))
    assert any(str(fn).startswith("Completeness: held") for fn in (out.footnotes or []))
