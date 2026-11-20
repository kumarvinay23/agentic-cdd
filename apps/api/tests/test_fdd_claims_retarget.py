"""Fix 6 — retargeted claims ledger (agent → document; closed verdicts)."""

from __future__ import annotations

from datetime import date

from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    ClaimsLedgerEntry,
    EightLabels,
    FddFact,
)
from agetic_cdd_api.services_fdd_claims import (
    evaluate_financial_claim,
    index_facts,
    build_claims_ledger,
)


def _fact(
    metric: str,
    year: int,
    value: float,
    *,
    fact_id: str | None = None,
    sources: list[str] | None = None,
    source_ref: dict | None = None,
    line: str | None = None,
) -> FddFact:
    return FddFact(
        fact_id=fact_id or f"db:{metric}:{year}",
        metric_key=metric,
        fiscal_year=year,
        value=value,
        status=CellStatus.PROVEN,
        release_status=CellStatus.PROVEN,
        labels=EightLabels(
            statement="IS",
            line=(line or metric.replace("_", " ").title()),
        ),
        currency="USD",
        scale="M",
        sources=list(sources or ["Monthly management accounts.xlsx"]),
        source_ref=source_ref
        or {"document": "Monthly management accounts.xlsx", "sheet_or_page": "P&L"},
    )


def test_evaluate_sets_subject_target_verdict() -> None:
    closed = date.today().year - 1
    facts = index_facts([_fact("revenue", closed, 13.28)])
    claim = ClaimsLedgerEntry(
        claim_id="c1",
        source_agent="historical_performance",
        text="revenue_fy2025_usd_m = 14.0",
        kind="financial",
        metric_key="revenue",
        fiscal_year=closed,
        claimed_value=14.0,
    )
    out = evaluate_financial_claim(claim, facts)
    assert out.verdict == "contradicted"
    assert out.test_result == "contradicted"
    assert out.source_agent == "historical_performance"
    assert "Monthly management accounts" in out.target_document
    assert out.target_location
    assert out.subject


def test_false_gap_when_agent_says_missing_but_no_fact() -> None:
    closed = date.today().year - 1
    claim = ClaimsLedgerEntry(
        claim_id="c2",
        source_agent="revenue_quality",
        text="revenue missing for FY",
        kind="financial",
        metric_key="revenue",
        fiscal_year=closed,
        claimed_value=0.0,
    )
    out = evaluate_financial_claim(claim, {})
    assert out.verdict == "false_gap"


def test_wrong_period_for_open_year() -> None:
    plan_year = date.today().year + 1
    claim = ClaimsLedgerEntry(
        claim_id="c3",
        source_agent="historical_performance",
        text="plan ebitda",
        kind="financial",
        metric_key="ebitda",
        fiscal_year=plan_year,
        claimed_value=0.9,
    )
    out = evaluate_financial_claim(claim, {})
    assert out.verdict == "wrong_period"
    assert out.failed is False


def test_self_comparison_dropped_from_ledger(monkeypatch, tmp_path) -> None:
    from agetic_cdd_api import services_deals as deals_mod
    from agetic_cdd_api import services_databook_store as store_mod
    from agetic_cdd_api.fdd_schemas import FactTableDoc
    from agetic_cdd_api.services_fdd_store import save_fact_table
    from agetic_cdd_api.services_fdd_render import ensure_phase0_run

    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    slug = "fix6-self"
    (root / slug).mkdir()
    closed = date.today().year - 1
    manifest, _, _ = ensure_phase0_run(slug, company="Self", prefer_current_release=True)
    fact = _fact("revenue", closed, 13.28, fact_id="db:revenue:closed")
    save_fact_table(
        FactTableDoc(
            run_id=manifest.run_id,
            deal_slug=slug,
            updated_at="t",
            facts=[fact],
        )
    )

    def _fake_extract(deal_slug: str, agent: str):
        return [
            ClaimsLedgerEntry(
                claim_id="self1",
                source_agent=agent,
                text=f"restates {fact.fact_id}",
                kind="financial",
                metric_key="revenue",
                fiscal_year=closed,
                claimed_value=13.28,
                cited_pages=[fact.fact_id],
            ),
            ClaimsLedgerEntry(
                claim_id="real1",
                source_agent=agent,
                text="independent claim",
                kind="financial",
                metric_key="revenue",
                fiscal_year=closed,
                claimed_value=14.0,
                cited_pages=["Investor workbook.xlsx"],
            ),
        ]

    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_claims.extract_claims_from_agent",
        _fake_extract,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_claims._CLAIM_AGENTS",
        ("historical_performance",),
    )
    ledger = build_claims_ledger(
        slug, manifest.run_id, open_requests=False, update_manifest=False
    )
    ids = {c.claim_id for c in ledger.claims}
    assert "self1" not in ids
    assert "real1" in ids
    assert ledger.self_comparisons_dropped >= 1
    real = next(c for c in ledger.claims if c.claim_id == "real1")
    assert real.source_agent
    assert real.target_document
    assert real.verdict in {"contradicted", "agrees", "unverifiable"}
