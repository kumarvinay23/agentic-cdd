"""Remaining FDD chapter depth — Transaction, Cash, BS, Deal, Appendices."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    ClaimsLedgerDoc,
    ClaimsLedgerEntry,
    Exhibit,
    ExhibitCell,
    ExhibitStoreDoc,
    FigureType,
    Finding,
    FindingSeverity,
    FindingSource,
    FindingsDoc,
    RequestListDoc,
    RequestListItem,
)
from agetic_cdd_api.services_fdd_chapter_depth import (
    chunked,
    parse_transaction_terms,
)
from agetic_cdd_api.services_fdd_chapters import (
    DisplayCtx,
    _DISPLAY_CTX,
    _fmt_materiality,
    plan_appendix,
    plan_bs,
    plan_cash,
    plan_chapter_slides,
    plan_deal,
    plan_intro,
    plan_transaction,
)
from agetic_cdd_api.services_fdd_trading import TradingPack


def _cell(
    exhibit_id: str,
    cell_id: str,
    *,
    metric_key: str,
    value: float,
    fiscal_year: int | None = 2025,
) -> ExhibitCell:
    return ExhibitCell(
        cell_id=cell_id,
        exhibit_id=exhibit_id,
        label=metric_key,
        value=value,
        fact_id=f"hand:{metric_key}:{fiscal_year or 'x'}",
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        currency="USD",
        scale="M",
        status=CellStatus.PROVEN,
        figure_type=FigureType.REPORTED,
    )


def _store() -> ExhibitStoreDoc:
    return ExhibitStoreDoc(
        run_id="r1",
        deal_slug="remaining",
        updated_at="",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                cells=[
                    _cell("ex_m1_trading", "r24", metric_key="revenue", value=11.869, fiscal_year=2024),
                    _cell("ex_m1_trading", "r25", metric_key="revenue", value=13.412, fiscal_year=2025),
                    _cell("ex_m1_trading", "e25", metric_key="ebitda", value=0.561, fiscal_year=2025),
                    _cell("ex_m1_trading", "ry", metric_key="revenue_yoy", value=13.0, fiscal_year=2025),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m7_cash",
                title="Cash",
                cells=[
                    _cell("ex_m7_cash", "ocf", metric_key="operating_cash_flow", value=0.611),
                    _cell("ex_m7_cash", "capex", metric_key="capex", value=0.432),
                    _cell("ex_m7_cash", "fcf", metric_key="free_cash_flow", value=0.178),
                    _cell("ex_m7_cash", "nc", metric_key="net_change_in_cash", value=-0.552),
                    _cell("ex_m7_cash", "cash", metric_key="cash", value=2.668),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m6_net_debt",
                title="Net debt",
                cells=[
                    _cell("ex_m6_net_debt", "cash", metric_key="cash", value=2.668),
                    _cell("ex_m6_net_debt", "gd", metric_key="gross_debt", value=2.019),
                    _cell("ex_m6_net_debt", "nd", metric_key="net_debt", value=-0.649),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m5_nwc",
                title="NWC",
                cells=[
                    _cell("ex_m5_nwc", "ar", metric_key="accounts_receivable", value=1.223),
                    _cell("ex_m5_nwc", "inv", metric_key="inventory", value=0.228),
                    _cell("ex_m5_nwc", "ap", metric_key="accounts_payable", value=0.496),
                    _cell("ex_m5_nwc", "nwc", metric_key="nwc", value=0.955),
                ],
            ),
            Exhibit(
                exhibit_id="ex_db_bs",
                title="BS",
                cells=[
                    _cell("ex_db_bs", "div", metric_key="dividends", value=0.372),
                ],
            ),
        ],
    )


def _pack() -> TradingPack:
    pack = TradingPack(deal_slug="remaining", scale="M", years=(2023, 2024, 2025))
    pack.fy = {
        "Residential": {2024: 1.967, 2025: 1.983},
        "Municipal": {2024: 4.243, 2025: 4.794},
        "Commercial": {2024: 4.966, 2025: 5.616},
        "Revenue": {2024: 11.869, 2025: 13.412},
    }
    pack.revenue_fy = {2024: 11.869, 2025: 13.412}
    pack.dc_billings = 3.078
    return pack


def test_chunked_pages() -> None:
    rows = [[str(i)] for i in range(25)]
    pages = chunked(rows, 11)
    assert len(pages) == 3
    assert len(pages[0]) == 11
    assert len(pages[-1]) == 3


def test_plan_transaction_two_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: _pack(),
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.parse_transaction_terms",
        lambda *_a, **_k: type(
            "T",
            (),
            {
                "issuer": "Compost Crew",
                "round_label": "Series B preferred",
                "primary_m": 6.3,
                "secondary_m": 5.0,
                "use_of_proceeds": "Growth and tuck-ins",
                "existing_preferred": "1.0x liq pref, cumulative, participating",
                "control": "CEO 58.4%",
                "valuation_ref": "Series A post-money $17.7m",
                "series_a_raised_m": 5.5,
                "notes": [],
            },
        )(),
    )
    token = _DISPLAY_CTX.set(DisplayCtx())
    try:
        slides = plan_transaction(
            store=_store(), scope=None, requests=[], company="Compost Crew"
        )
    finally:
        _DISPLAY_CTX.reset(token)
    ids = [s.slide_id for s in slides]
    assert ids == ["ch_tx_terms", "ch_tx_business"]
    assert "6.3" in slides[0].headline or "Series B" in slides[0].headline
    assert slides[1].table is not None
    assert any("Municipal" in r[0] for r in slides[1].table.rows)


def test_plan_cash_two_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    from agetic_cdd_api.services_fdd_chapter_depth import CashBsPack

    pack = CashBsPack(deal_slug="remaining")
    pack.cash = {2022: 4.127, 2023: 2.982, 2024: 3.220, 2025: 2.668, "Jul-26": 2.325}
    pack.ocf = {2023: -0.521, 2024: 0.541, 2025: 0.611, "Jul-26": 0.228}
    pack.capex = {2023: 1.141, 2024: 0.596, 2025: 0.432}
    pack.depreciation = {2023: 0.531, 2024: 0.616, 2025: 0.709}
    pack.net_change_cash = {2025: -0.552}
    pack.net_income = {2025: -0.560}
    pack.dividends_payable = {2025: 0.372}
    pack.usda_grant_m = 2.68
    pack.usda_match_m = 2.907
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.build_cash_bs_pack",
        lambda *_a, **_k: pack,
    )
    token = _DISPLAY_CTX.set(DisplayCtx())
    try:
        slides = plan_cash(commentary=None, store=_store(), requests=[])
    finally:
        _DISPLAY_CTX.reset(token)
    assert [s.slide_id for s in slides] == ["ch_cash_1", "ch_cash_2"]
    assert "611" in slides[0].headline or "operating cash" in slides[0].headline.lower()
    assert "Dec-22" in (slides[1].table.headers if slides[1].table else [])
    assert "matching" in slides[1].headline.lower()
    assert "2,907" in slides[1].headline or "2.91" in slides[1].headline.lower()


def test_plan_bs_five_slides(monkeypatch: pytest.MonkeyPatch) -> None:
    from agetic_cdd_api.services_fdd_chapter_depth import CashBsPack

    pack = CashBsPack(deal_slug="remaining")
    pack.cash = {2023: 2.982, 2024: 3.220, 2025: 2.668, "Jul-26": 2.325}
    pack.ar = {2023: 0.918, 2024: 1.200, 2025: 1.223}
    pack.inventory = {2023: 0.055, 2024: 0.203, 2025: 0.228}
    pack.ap = {2023: 0.283, 2024: 0.336, 2025: 0.496}
    pack.dividends_payable = {2023: 0.127, 2024: 0.381, 2025: 0.372, "Jul-26": 0.407}
    pack.net_income = {2023: -1.396, 2024: 0.245, 2025: -0.560, "Jul-26": -0.181}
    pack.dividend_accrual = {2023: 0.127, 2024: 0.254, 2025: 0.363, "Jul-26": 0.221}
    pack.loans_payable = {2025: 2.019, "Jul-26": 1.907}
    pack.financial_debt = {2023: 2.115, 2024: 2.377, 2025: 2.019, "Jul-26": 1.907}
    pack.dividend_paid = {"Jul-26": 0.186}
    pack.rent_fy25 = 0.406
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.build_cash_bs_pack",
        lambda *_a, **_k: pack,
    )
    token = _DISPLAY_CTX.set(DisplayCtx())
    try:
        slides = plan_bs(commentary=None, store=_store(), requests=[])
    finally:
        _DISPLAY_CTX.reset(token)
    ids = [s.slide_id for s in slides]
    assert ids == [
        "ch_bs_summary",
        "ch_bs_net_debt",
        "ch_bs_leases",
        "ch_bs_nwc",
        "ch_bs_equity",
    ]
    debt = next(s for s in slides if s.slide_id == "ch_bs_net_debt")
    assert "1,907" in debt.headline or "1.91" in debt.headline.lower()
    assert debt.table is not None
    assert any("Jul-26" in h for h in debt.table.headers)
    assert any("Vehicle" in r[0] for r in debt.table.rows)
    equity = next(s for s in slides if s.slide_id == "ch_bs_equity")
    assert equity.table is not None
    assert any("Cash dividends paid" in r[0] for r in equity.table.rows)


def test_plan_deal_splits_requests() -> None:
    items = [
        RequestListItem(
            request_id=f"R{i:02d}",
            title=f"Request {i}",
            detail=f"Why {i}",
            blocking_sections=["SEC-B"] if i <= 8 else [],
        )
        for i in range(1, 22)
    ]
    findings = FindingsDoc(
        run_id="r",
        deal_slug="remaining",
        updated_at="",
        findings=[
            Finding(
                finding_id="f1",
                severity=FindingSeverity.HIGH,
                title="Dividend arrears",
                ask_management="Deduct or waive arrears",
                source=FindingSource.MODEL,
            )
        ],
        counts={"high": 1, "moderate": 0, "total": 1},
    )
    slides = plan_deal(
        findings=findings,
        request_list=RequestListDoc(
            run_id="r", deal_slug="remaining", updated_at="", items=items
        ),
        requests=[],
    )
    ids = [s.slide_id for s in slides]
    assert ids[0] == "ch_deal_protections"
    assert "ch_deal_requests_1" in ids and "ch_deal_requests_2" in ids
    assert slides[1].table is not None
    assert "Why it matters" in slides[1].table.headers
    assert "21 information requests" in slides[1].headline
    assert "8 high" in slides[1].headline.lower()
    all_req = []
    for s in slides[1:]:
        if s.table and s.slide_id.startswith("ch_deal_requests"):
            all_req.extend(s.table.rows)
    # Priorities come from blocking_sections — not forced to a Project Crew count.
    assert len(all_req) == 21
    assert sum(1 for r in all_req if r[4] == "High") == 8


def test_plan_appendix_paginates_claims_and_register(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    docs = tmp_path / "deals" / "remaining" / "documents"
    docs.mkdir(parents=True)
    for name in [f"file_{i}.xlsx" for i in range(1, 15)] + ["lease.pdf"]:
        (docs / name).write_text("x")
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth._deals_documents",
        lambda _slug: docs,
    )
    claims = ClaimsLedgerDoc(
        run_id="r",
        deal_slug="remaining",
        updated_at="",
        claim_count=20,
        agrees=5,
        contradicted=3,
        claims=[
            ClaimsLedgerEntry(
                claim_id=f"c{i}",
                text=f"Claim text {i}",
                kind="financial",
                metric_key="revenue",
                fiscal_year=2025,
                claimed_value=13.4,
                databook_value=13.3,
                test_result="contradicted" if i <= 3 else "agrees",
                failed=i <= 3,
                source_agent="Executive Summary",
            )
            for i in range(1, 21)
        ],
    )
    slides = plan_appendix(claims=claims, deal_slug="remaining")
    ids = [s.slide_id for s in slides]
    assert any(i.startswith("ch_app_claims_") for i in ids)
    assert any(i.startswith("ch_app_register_") for i in ids)
    assert "ch_app_inconsistencies" in ids
    assert "ch_app_glossary" in ids


def test_resolve_project_label_from_entity() -> None:
    from agetic_cdd_api.services_fdd_chapters import resolve_project_label

    assert resolve_project_label(company="Acme Logistics LLC") == "Project Acme Logistics"
    assert resolve_project_label(company="Compost Crew") == "Project Compost Crew"
    assert resolve_project_label(company="Baytown Travel Center") == "Project Baytown Travel Center"


def test_plan_intro_period_source_basis_tier() -> None:
    scope = type(
        "S",
        (),
        {
            "materiality_m": 0.03,
            "periods": ["FY23", "FY24", "FY25", "YTD Jul-26", "LTM Jul-26"],
            "currency": "USD",
            "deal_type": "buy-side",
            "entities_in": ["Compost Crew"],
        },
    )()
    token = _DISPLAY_CTX.set(DisplayCtx())
    try:
        slides = plan_intro(
            commentary=None,
            scope=scope,
            company="Compost Crew",
            requests=[],
        )
    finally:
        _DISPLAY_CTX.reset(token)
    assert len(slides) == 1
    assert slides[0].table is not None
    assert slides[0].table.headers == ["Period", "Source", "Basis", "Tier"]
    assert "$30k" in slides[0].headline or "30" in slides[0].headline
    assert _fmt_materiality(0.03) is not None
    assert "0.03" not in (_fmt_materiality(0.03) or "")


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "deals" / "test6" / "documents").is_dir(),
    reason="Test6 documents not present",
)
def test_parse_transaction_terms_test6() -> None:
    terms = parse_transaction_terms("test6", company="Compost Crew")
    assert terms.primary_m == pytest.approx(6.3, abs=0.05)
    assert terms.round_label and "Series B" in terms.round_label


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[1] / "data" / "deals" / "test6" / "documents").is_dir(),
    reason="Test6 documents not present",
)
def test_cash_bs_pack_test6_debt_usda_ltm() -> None:
    from agetic_cdd_api.services_fdd_chapter_depth import build_cash_bs_pack

    pack = build_cash_bs_pack("test6")
    assert pack.financial_debt.get(2025) == pytest.approx(2.019, abs=0.01)
    assert pack.financial_debt.get("Jul-26") == pytest.approx(1.907, abs=0.01)
    assert pack.usda_grant_m == pytest.approx(2.68, abs=0.02)
    assert pack.usda_project_cost_m == pytest.approx(5.591, abs=0.01)
    assert pack.usda_match_m == pytest.approx(2.91, abs=0.05)
    assert pack.ltm_revenue == pytest.approx(13.65, abs=0.05)
    assert pack.ltm_ebitda == pytest.approx(0.496, abs=0.02)


def test_plan_chapter_slides_remaining_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack",
        lambda *_a, **_k: _pack(),
    )
    from agetic_cdd_api.services_fdd_chapter_depth import CashBsPack, TransactionTerms

    pack = CashBsPack(deal_slug="remaining")
    pack.cash = {2022: 4.1, 2023: 3.0, 2024: 3.2, 2025: 2.7, "Jul-26": 2.3}
    pack.ocf = {2025: 0.611, "Jul-26": 0.228}
    pack.capex = {2025: 0.432}
    pack.depreciation = {2025: 0.709}
    pack.net_change_cash = {2025: -0.552}
    pack.net_income = {2025: -0.56}
    pack.dividends_payable = {2025: 0.372, "Jul-26": 0.407}
    pack.ar = {2025: 1.2}
    pack.inventory = {2025: 0.2}
    pack.ap = {2025: 0.5}
    pack.rent_fy25 = 0.4
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.build_cash_bs_pack",
        lambda *_a, **_k: pack,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.parse_transaction_terms",
        lambda *_a, **_k: TransactionTerms(
            issuer="X",
            round_label="Series B preferred",
            primary_m=6.3,
            secondary_m=5.0,
            use_of_proceeds="Growth",
            existing_preferred="cumulative",
            control="CEO",
            valuation_ref="Series A",
        ),
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_chapter_depth.list_data_room_files",
        lambda *_a, **_k: [
            {
                "id": f"D{i:02d}",
                "document": f"doc{i}.xlsx",
                "subject": "X",
                "basis": "management",
                "period_end": "–",
                "tier": "B",
                "use": "In perimeter",
            }
            for i in range(1, 10)
        ],
    )
    findings = FindingsDoc(
        run_id="r",
        deal_slug="remaining",
        updated_at="",
        findings=[
            Finding(
                finding_id="f1",
                severity=FindingSeverity.HIGH,
                title="Cost pressure",
                observation="EBITDA halved",
                implication="Price on LTM",
                ask_management="Explain SG&A",
                source=FindingSource.MODEL,
            )
        ],
        counts={"high": 1, "total": 1},
    )
    claims = ClaimsLedgerDoc(
        run_id="r",
        deal_slug="remaining",
        updated_at="",
        claim_count=2,
        contradicted=1,
        agrees=1,
        claims=[
            ClaimsLedgerEntry(
                claim_id="c1",
                text="bad claim",
                kind="financial",
                metric_key="revenue",
                fiscal_year=2025,
                claimed_value=1.0,
                databook_value=0.9,
                test_result="contradicted",
                failed=True,
            )
        ],
    )
    req = RequestListDoc(
        run_id="r",
        deal_slug="remaining",
        updated_at="",
        items=[
            RequestListItem(
                request_id=f"R{i:02d}",
                title=f"Req {i}",
                blocking_sections=["SEC-B"] if i < 5 else [],
            )
            for i in range(1, 15)
        ],
    )
    slides = plan_chapter_slides(
        company="Compost Crew",
        store=_store(),
        findings=findings,
        claims=claims,
        request_list=req,
    )
    by = {}
    for s in slides:
        by.setdefault(s.chapter, []).append(s.slide_id)
    assert len(by["transaction"]) == 2
    assert len(by["cash"]) == 2
    assert len(by["bs"]) == 5
    assert len(by["deal"]) == 3
    assert len(by["appendix"]) >= 4
