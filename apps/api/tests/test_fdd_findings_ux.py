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
    assert doc.findings
    assert load_findings(slug, manifest.run_id) is not None
    severities = {f.severity for f in doc.findings}
    assert FindingSeverity.HIGH in severities or FindingSeverity.MODERATE in severities
    assert any(f.source == FindingSource.CLAIM for f in doc.findings)
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


def test_claim_findings_respect_absolute_materiality(deal_root: Path) -> None:
    """Core P&L gaps below 0.03 M stay MODERATE; at/above threshold are HIGH."""
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
                    claim_id="small_eb",
                    text="tiny ebitda gap",
                    kind="financial",
                    metric_key="ebitda",
                    fiscal_year=closed,
                    claimed_value=1.14,
                    databook_value=1.12,
                    test_result="contradicted",
                    failed=True,
                ),
                ClaimsLedgerEntry(
                    claim_id="edge_rev",
                    text="revenue at threshold",
                    kind="financial",
                    metric_key="revenue",
                    fiscal_year=closed,
                    claimed_value=7.56,
                    databook_value=7.53,
                    test_result="contradicted",
                    failed=True,
                ),
                ClaimsLedgerEntry(
                    claim_id="large_gp",
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
    by = {f.evidence_refs[0]: f.severity for f in doc.findings if f.evidence_refs}
    assert by["small_eb"] == FindingSeverity.MODERATE
    assert by["edge_rev"] == FindingSeverity.HIGH
    assert by["large_gp"] == FindingSeverity.HIGH


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
    assert ASSEMBLY_VERSION.startswith("0.3")
    ids = {n.node_id for n in spec.nodes}
    assert "sec_basis" in ids
    assert "sec_integrity" in ids
    assert "sec_toc" in ids
    assert "sec_abbreviations" in ids
    assert "sec_not_evidenced" in ids
    assert "slide_agenda" in ids
    assert "slide_es_dashboard" in ids
    assert "slide_open_items" in ids
    # Slim deck: no raw exhibit appendix slides by default
    assert not any(i.startswith("slide_ex_") for i in ids)
    # Report still has exhibit sections
    assert any(i.startswith("sec_ex_") for i in ids)

    deck = render_stub(kind="deck", spec=spec, store=store2)
    report = render_stub(kind="report", spec=spec, store=store2)
    assert len(deck.pages) <= 20
    assert any(p.title == "Basis of preparation" for p in report.pages)
    assert any("Contents" in (p.title or "") for p in report.pages)
    # Shared figure map identity (R5)
    assert deck.figures == report.figures

    persisted = load_report_spec(slug, manifest.run_id)
    assert persisted is not None
    assert persisted.content_hash == spec.content_hash
