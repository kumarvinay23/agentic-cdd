"""Cures for remaining Test6 deck gaps after Part C fixes."""

from __future__ import annotations

from types import SimpleNamespace

from agetic_cdd_api.services_fdd_chapters import (
    _clean_claim_text,
    _lease_request_hints,
    _polish_claim_percent_subject,
    plan_appendix,
    plan_bs,
)
from agetic_cdd_api.services_fdd_claims import _format_claim_subject_percent
from agetic_cdd_api.fdd_schemas import ClaimsLedgerEntry, ExhibitStoreDoc


def test_claim_fraction_percent_renders_as_points() -> None:
    text = _polish_claim_percent_subject("EBITDA Margin FY2027 = 0.018 %")
    assert text == "EBITDA Margin FY2027 = 1.8%"
    assert "0.018" not in text

    cleaned = _clean_claim_text("Gross Margin FY2026 = 0.3121 %")
    assert cleaned == "Gross Margin FY2026 = 31.2%"

    claim = ClaimsLedgerEntry(
        claim_id="c1",
        text="margin",
        kind="financial",
        metric_key="ebitda_margin",
        fiscal_year=2027,
        claimed_value=0.018,
        source_agent="historical_performance",
    )
    subject = _format_claim_subject_percent(
        "ebitda_margin FY2027 = 0.018", claim
    )
    assert "1.8%" in subject
    assert "0.018" not in subject


def test_lease_requests_drop_wrong_period_ebitda() -> None:
    hints = _lease_request_hints(
        [
            "R01: Reconcile ebitda FY2027 (wrong period)",
            "R02: Reconcile ebitda FY2028 (wrong period)",
            "R12: Schedule of all leases and site rent",
        ]
    )
    assert len(hints) == 1
    assert "lease" in hints[0].lower()
    assert "FY2027" not in hints[0]

    defaulted = _lease_request_hints(
        ["R01: Reconcile ebitda FY2027 (wrong period)"]
    )
    assert defaulted and "lease" in defaulted[0].lower()


def test_plan_bs_leases_obs_exclude_wrong_period() -> None:
    store = ExhibitStoreDoc(run_id="r1", deal_slug="", updated_at="", exhibits=[])
    slides = plan_bs(
        commentary=None,
        store=store,
        requests=[
            "R01: Reconcile ebitda FY2027 (wrong period)",
            "R02: Reconcile ebitda FY2028 (wrong period)",
        ],
    )
    lease = next(s for s in slides if s.slide_id == "ch_bs_leases")
    blob = "\n".join(lease.observations or [])
    assert "FY2027" not in blob
    assert "lease" in blob.lower() or "held" in blob.lower()


def test_plan_appendix_claim_subjects_use_points() -> None:
    claims = SimpleNamespace(
        claims=[
            ClaimsLedgerEntry(
                claim_id="c1",
                text="EBITDA Margin FY2027 = 0.018 %",
                kind="financial",
                metric_key="ebitda_margin",
                fiscal_year=2027,
                claimed_value=0.018,
                source_agent="historical_performance",
                subject="EBITDA Margin FY2027 = 0.018 %",
                target_document="CC_Investor_Workbook_EXTERNAL.xlsx",
                verdict="wrong_period",
                test_result="wrong_period",
                failed=True,
            )
        ],
        claim_count=1,
        agrees=0,
        contradicted=0,
    )
    slides = plan_appendix(claims=claims, deal_slug="test6")
    blob = "\n".join(
        "|".join(row)
        for s in slides
        if s.table
        for row in (s.table.rows or [])
    )
    assert "1.8%" in blob
    assert "0.018" not in blob
