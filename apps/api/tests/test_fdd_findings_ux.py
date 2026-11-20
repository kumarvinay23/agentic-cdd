"""FDD findings UX — front matter, findings ledger, slim deck assembly."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    ClaimsLedgerDoc,
    ClaimsLedgerEntry,
    EightLabels,
    FactTableDoc,
    FddFact,
    FindingSeverity,
    FindingSource,
)
from agetic_cdd_api.services_fdd_assemble import (
    ASSEMBLY_VERSION,
    assemble_report_spec,
    ensure_commentary_and_assemble,
)
from agetic_cdd_api.services_fdd_findings import build_findings, sort_findings, top_findings
from agetic_cdd_api.services_fdd_models import ensure_phase5b_models
from agetic_cdd_api.services_fdd_render import ensure_phase0_run, render_stub
from agetic_cdd_api.services_fdd_store import (
    load_findings,
    load_report_spec,
    save_claims_ledger,
    save_fact_table,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _fact(metric: str, year: int, value: float, *, status: str = "proven") -> FddFact:
    return FddFact(
        fact_id=f"db:t:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=CellStatus(status),
        release_status=CellStatus(status),
        labels=EightLabels(statement="IS", line=metric.replace("_", " ").title()),
        currency="USD",
        scale="M",
    )


def test_findings_severity_from_claims_and_held(deal_root: Path) -> None:
    slug = "fdd-findings"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(slug, company="FindCo", prefer_current_release=True)
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
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="FindCo", build_qoe=True
    )
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="c1",
                    text="Revenue mismatch",
                    kind="financial",
                    metric_key="revenue",
                    fiscal_year=closed,
                    claimed_value=110.0,
                    databook_value=100.0,
                    test_result="contradicted",
                    failed=True,
                ),
                ClaimsLedgerEntry(
                    claim_id="c2",
                    text="GRR unverifiable",
                    kind="financial",
                    metric_key="grr",
                    fiscal_year=closed,
                    test_result="unverifiable",
                    failed=True,
                ),
            ],
        )
    )
    doc = build_findings(slug, manifest.run_id, store=store2, update_manifest=True)
    assert load_findings(slug, manifest.run_id) is not None
    # Fix 5 — claim contradictions are not findings (stay on claims ledger / RFIs).
    assert not any(f.source == FindingSource.CLAIM for f in doc.findings)
    if doc.findings:
        assert doc.population
        assert all(f.display_id for f in doc.findings)
        top = top_findings(doc.findings, limit=3)
        assert len(top) <= 3
        assert sort_findings(doc.findings)[0].severity in {
            FindingSeverity.HIGH,
            FindingSeverity.MODERATE,
            FindingSeverity.LOW,
            FindingSeverity.INFO,
        }


def test_cost_pressure_finding_when_opex_outgrows_revenue(deal_root: Path) -> None:
    """Labour/SG&A YoY above revenue YoY with falling EBITDA → HIGH finding."""
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        Exhibit,
        ExhibitCell,
        ExhibitStoreDoc,
        FigureType,
    )
    from agetic_cdd_api.services_fdd_findings import _from_cost_pressure

    closed = date.today().year - 1
    prior = closed - 1

    def _cell(
        eid: str,
        mk: str,
        year: int,
        value: float,
        *,
        basis: str | None = None,
        model_id: str | None = None,
    ) -> ExhibitCell:
        return ExhibitCell(
            exhibit_id=eid,
            cell_id=f"{mk}_fy{year}",
            fact_id=f"f:{eid}:{mk}:{year}",
            metric_key=mk,
            fiscal_year=year,
            value=value,
            figure_type=FigureType.CALCULATED,
            status=CellStatus.PROVEN,
            label=mk,
            model_id=model_id or ("M3" if "m3" in eid else "M1"),
            basis_label=basis,
        )

    store = ExhibitStoreDoc(
        deal_slug="cost-pressure",
        run_id="r",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                section_id="SEC-B",
                status=ArtefactStatus.CHECKED,
                cells=[
                    _cell(
                        "ex_m1_trading",
                        "ebitda",
                        prior,
                        1.115,
                        basis="investor workbook",
                    ),
                    _cell(
                        "ex_m1_trading",
                        "ebitda",
                        closed,
                        0.565,
                        basis="investor workbook",
                    ),
                ],
            ),
            Exhibit(
                exhibit_id="ex_m3_costs",
                title="Costs",
                section_id="SEC-D",
                status=ArtefactStatus.CHECKED,
                cells=[
                    _cell(
                        "ex_m3_costs",
                        "revenue",
                        prior,
                        11.869,
                        basis="monthly pack",
                        model_id="M3",
                    ),
                    _cell(
                        "ex_m3_costs",
                        "revenue",
                        closed,
                        13.412,
                        basis="monthly pack",
                        model_id="M3",
                    ),
                    _cell("ex_m3_costs", "labor_yoy", closed, 17.61, model_id="M3"),
                    _cell("ex_m3_costs", "sga_yoy", closed, 29.28, model_id="M3"),
                ],
            ),
        ],
    )
    findings = _from_cost_pressure(store)
    assert len(findings) == 1
    assert findings[0].severity.value == "high"
    obs = findings[0].observation.lower()
    assert "labour grew" in obs
    assert "sg&a grew" in obs
    assert "ebitda fell" in obs
    assert "investor workbook" in obs  # same-basis ebitda pair
    assert "13.12" not in obs  # not the mixed workbook revenue yoy
    assert "13.0" in obs or "13" in obs  # pack revenue growth ~13.0%


def test_cost_pressure_from_trading_pack_when_m3_yoy_missing(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pack labour/SG&A levels restore the HIGH finding after sticky-scale rebuild."""
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        Exhibit,
        ExhibitCell,
        ExhibitStoreDoc,
        FigureType,
    )
    from agetic_cdd_api.services_fdd_findings import _from_cost_pressure
    from agetic_cdd_api.services_fdd_trading import TradingPack

    closed = date.today().year - 1
    prior = closed - 1
    pack = TradingPack(deal_slug="pack-cost", scale="M", years=(prior, closed))
    pack.fy = {
        "Revenue": {prior: 11.869, closed: 13.412},
        "Labour — operations": {prior: 2.0, closed: 2.4},
        "Labour — SG&A": {prior: 1.0, closed: 1.15},
        "SG&A (reported)": {prior: 3.0, closed: 3.9},
        "Depreciation": {prior: 0.2, closed: 0.25},
        "EBITDA (management)": {prior: 1.115, closed: 0.565},
    }

    def _fake_pack(slug: str) -> TradingPack:
        return pack

    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack", _fake_pack
    )

    store = ExhibitStoreDoc(
        deal_slug="pack-cost",
        run_id="r",
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m1_trading",
                title="Trading",
                section_id="SEC-B",
                status=ArtefactStatus.CHECKED,
                cells=[
                    ExhibitCell(
                        exhibit_id="ex_m1_trading",
                        cell_id=f"ebitda_fy{prior}",
                        fact_id=f"f:eb:{prior}",
                        metric_key="ebitda",
                        fiscal_year=prior,
                        value=1.115,
                        figure_type=FigureType.CALCULATED,
                        status=CellStatus.PROVEN,
                        label="ebitda",
                        model_id="M1",
                        basis_label="investor workbook",
                    ),
                    ExhibitCell(
                        exhibit_id="ex_m1_trading",
                        cell_id=f"ebitda_fy{closed}",
                        fact_id=f"f:eb:{closed}",
                        metric_key="ebitda",
                        fiscal_year=closed,
                        value=0.565,
                        figure_type=FigureType.CALCULATED,
                        status=CellStatus.PROVEN,
                        label="ebitda",
                        model_id="M1",
                        basis_label="investor workbook",
                    ),
                ],
            )
        ],
    )
    findings = _from_cost_pressure(store, deal_slug="pack-cost")
    assert len(findings) == 1
    assert findings[0].severity.value == "high"
    assert "cost growth" in findings[0].title.lower()
    assert "labour grew" in findings[0].observation.lower()


def test_cost_pressure_ignores_sticky_claim_ebitda(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sticky claim EBITDA (98097) must not block pack-based cost-growth HIGH."""
    from agetic_cdd_api.fdd_schemas import (
        ArtefactStatus,
        Exhibit,
        ExhibitCell,
        ExhibitStoreDoc,
        FigureType,
        ClaimsLedgerDoc,
        ClaimsLedgerEntry,
    )
    from agetic_cdd_api.services_fdd_findings import _from_cost_pressure
    from agetic_cdd_api.services_fdd_store import save_claims_ledger
    from agetic_cdd_api.services_fdd_trading import TradingPack

    closed = date.today().year - 1
    prior = closed - 1
    slug = "sticky-eb-cost"
    (deal_root / slug).mkdir(parents=True)
    manifest, store, _ = ensure_phase0_run(
        slug, company="StickyEB", prefer_current_release=True
    )
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="cl_sticky",
                    source_agent="historical_performance",
                    text="EBITDA FY2025 = 98097.67 USD M",
                    kind="financial",
                    metric_key="ebitda",
                    fiscal_year=closed,
                    claimed_value=98097.67,
                    test_result="unverifiable",
                    failed=True,
                ),
                ClaimsLedgerEntry(
                    claim_id="cl_ok",
                    source_agent="historical_performance",
                    text="ebitda_fy2024_usd_m = 1.135",
                    kind="financial",
                    metric_key="ebitda",
                    fiscal_year=prior,
                    claimed_value=1.135,
                    databook_value=1.115,
                    test_result="contradicted",
                    failed=True,
                ),
            ],
        )
    )
    pack = TradingPack(deal_slug=slug, scale="M", years=(prior, closed))
    pack.fy = {
        "Revenue": {prior: 11.869, closed: 13.412},
        "Labour — operations": {prior: 2.0, closed: 2.4},
        "Labour — SG&A": {prior: 1.0, closed: 1.15},
        "SG&A (reported)": {prior: 3.0, closed: 3.9},
        "Depreciation": {prior: 0.2, closed: 0.25},
        "EBITDA (management)": {prior: 1.135, closed: 0.572},
    }
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_trading.build_trading_pack", lambda _s: pack
    )
    store = ExhibitStoreDoc(
        deal_slug=slug,
        run_id=manifest.run_id,
        updated_at="t",
        exhibits=[
            Exhibit(
                exhibit_id="ex_m3_costs",
                title="Costs",
                section_id="SEC-D",
                status=ArtefactStatus.CHECKED,
                cells=[
                    ExhibitCell(
                        exhibit_id="ex_m3_costs",
                        cell_id=f"labor_yoy_fy{closed}",
                        fact_id="f:lab",
                        metric_key="labor_yoy",
                        fiscal_year=closed,
                        value=17.61,
                        figure_type=FigureType.CALCULATED,
                        status=CellStatus.PROVEN,
                        label="labor_yoy",
                        model_id="M3",
                    ),
                    ExhibitCell(
                        exhibit_id="ex_m3_costs",
                        cell_id=f"sga_yoy_fy{closed}",
                        fact_id="f:sga",
                        metric_key="sga_yoy",
                        fiscal_year=closed,
                        value=29.28,
                        figure_type=FigureType.CALCULATED,
                        status=CellStatus.PROVEN,
                        label="sga_yoy",
                        model_id="M3",
                    ),
                    # Sticky dust revenue — must be ignored in favour of pack.
                    ExhibitCell(
                        exhibit_id="ex_m3_costs",
                        cell_id=f"revenue_fy{closed}",
                        fact_id="f:rev",
                        metric_key="revenue",
                        fiscal_year=closed,
                        value=0.039,
                        figure_type=FigureType.CALCULATED,
                        status=CellStatus.PROVEN,
                        label="revenue",
                        model_id="M3",
                    ),
                ],
            )
        ],
    )
    findings = _from_cost_pressure(store, deal_slug=slug, run_id=manifest.run_id)
    assert len(findings) == 1
    assert findings[0].severity.value == "high"
    assert "cost growth" in findings[0].title.lower()
    assert "98097" not in findings[0].observation


def test_zero_databook_claim_is_not_a_finding(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import ClaimsLedgerDoc, ClaimsLedgerEntry
    from agetic_cdd_api.services_fdd_findings import _from_claims
    from agetic_cdd_api.services_fdd_store import save_claims_ledger

    slug = "fdd-zero-book"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, _, _ = ensure_phase0_run(
        slug, company="ZeroBook", prefer_current_release=True
    )
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="cl_zero",
                    source_agent="historical_performance",
                    text="Revenue FY2024 = 11.869",
                    kind="financial",
                    metric_key="revenue",
                    fiscal_year=closed - 1,
                    claimed_value=11.869,
                    databook_value=0.0,
                    test_result="contradicted",
                    failed=True,
                ),
                ClaimsLedgerEntry(
                    claim_id="cl_real",
                    source_agent="historical_performance",
                    text="Gross profit FY2024 = 4.5",
                    kind="financial",
                    metric_key="gross_profit",
                    fiscal_year=closed - 1,
                    claimed_value=4.5,
                    databook_value=4.2,
                    test_result="contradicted",
                    failed=True,
                ),
            ],
        )
    )
    findings = _from_claims(slug, manifest.run_id)
    # Fix 5 — no claim rows become findings (including real gaps).
    assert findings == []


def test_claim_findings_no_longer_minted_for_materiality(deal_root: Path) -> None:
    """Fix 5 — contradicted claims stay on the ledger; not the findings register."""
    from agetic_cdd_api.fdd_schemas import ClaimsLedgerDoc, ClaimsLedgerEntry
    from agetic_cdd_api.services_fdd_store import save_claims_ledger

    slug = "fdd-mat"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    manifest, store, _ = ensure_phase0_run(
        slug, company="MatCo", prefer_current_release=True
    )
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="large_gp",
                    source_agent="historical_performance",
                    text="material gp gap",
                    kind="financial",
                    metric_key="gross_profit",
                    fiscal_year=closed,
                    claimed_value=4.08,
                    databook_value=3.95,
                    test_result="contradicted",
                    failed=True,
                ),
            ],
        )
    )
    doc = build_findings(slug, manifest.run_id, store=store, update_manifest=False)
    assert not any(f.source == FindingSource.CLAIM for f in doc.findings)
    assert not any("large_gp" in (f.evidence_refs or []) for f in doc.findings)


def test_assemble_front_matter_and_slim_deck(deal_root: Path) -> None:
    slug = "fdd-ux-assemble"
    (deal_root / slug).mkdir(parents=True)
    closed = date.today().year - 1
    prior = closed - 1
    manifest, store, _ = ensure_phase0_run(slug, company="PackCo", prefer_current_release=True)
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
                _fact("operating_cash_flow", closed, 9.0),
                _fact("capex", closed, 3.0),
                _fact("cash", closed, 5.0),
                _fact("term_loan", closed, 8.0),
            ],
        )
    )
    store2, _ = ensure_phase5b_models(
        slug, manifest.run_id, store=store, company="PackCo", build_qoe=True
    )
    commentary, spec = ensure_commentary_and_assemble(
        slug, manifest.run_id, store=store2, company="PackCo"
    )
    assert commentary is not None
    assert ASSEMBLY_VERSION.startswith("0.")
    ids = {n.node_id for n in spec.nodes}
    assert "sec_basis" in ids
    assert "sec_integrity" in ids
    assert "sec_toc" in ids
    assert "sec_abbreviations" in ids
    assert "sec_not_evidenced" in ids
    # Chapter storyline slides (Phase C) — not the legacy agenda/dashboard ids.
    assert any(i.startswith("slide_ch_") for i in ids)
    # Slim deck: no raw exhibit appendix slides by default
    assert not any(i.startswith("slide_ex_") for i in ids)
    # Report still has exhibit sections
    assert any(i.startswith("sec_ex_") for i in ids)

    deck = render_stub(kind="deck", spec=spec, store=store2)
    report = render_stub(kind="report", spec=spec, store=store2)
    # Chapter storyline is denser than the old slim stub; still shorter than full report.
    assert len(deck.pages) <= 40
    assert len(deck.pages) < len(report.pages)
    assert any(p.title == "Basis of preparation" for p in report.pages)
    assert any("Contents" in (p.title or "") for p in report.pages)
    # Shared figure map identity (R5)
    assert deck.figures == report.figures

    persisted = load_report_spec(slug, manifest.run_id)
    assert persisted is not None
    assert persisted.content_hash == spec.content_hash
