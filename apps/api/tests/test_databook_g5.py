"""G5 — prove library: equity/cash roll, NI cross, notes, draft→final."""

from __future__ import annotations

from agetic_cdd_api.services_databook_harness import run_all_goldens, run_all_traps, run_trap
from agetic_cdd_api.services_databook_models import (
    DealDatabookParams,
    ExtractedRow,
    FailureClass,
    MetricFamily,
    NoteFact,
    ProofLevel,
    SourceBasis,
)
from agetic_cdd_api.services_databook_prove import (
    check_cash_roll,
    check_draft_to_final,
    check_equity_roll_forward,
    check_ni_cross_statement,
    check_notes_vs_statements,
    run_prove_pipeline,
)


def _row(
    row_id: str,
    *,
    metric_key: str,
    fy: int,
    value: float,
    source_name: str = "a.pdf",
    statement: str | None = None,
    source_basis: SourceBasis | None = None,
    ladder_score: int | None = None,
) -> ExtractedRow:
    return ExtractedRow(
        row_id=row_id,
        doc_id="d",
        source_name=source_name,
        caption=metric_key,
        metric_key=metric_key,
        metric_family=MetricFamily.OTHER,
        fiscal_year=fy,
        value=value,
        statement=statement,
        source_basis=source_basis,
        ladder_score=ladder_score,
        dual_agree=True,
    )


def test_equity_roll_holds_on_mismatch() -> None:
    rows = [
        _row("e0", metric_key="total_equity", fy=2023, value=100.0),
        _row("e1", metric_key="total_equity", fy=2024, value=200.0),
        _row("ni", metric_key="net_income", fy=2024, value=40.0),
    ]
    issues, holds = check_equity_roll_forward(rows, params=DealDatabookParams())
    assert holds == {"e0", "e1", "ni"}
    assert issues[0]["check_id"] == "equity_roll"
    assert issues[0]["failure_class"] == FailureClass.SOURCE.value


def test_equity_roll_passes_with_dividends() -> None:
    rows = [
        _row("e0", metric_key="total_equity", fy=2023, value=100.0),
        _row("e1", metric_key="total_equity", fy=2024, value=120.0),
        _row("ni", metric_key="net_income", fy=2024, value=40.0),
        _row("dv", metric_key="dividends", fy=2024, value=20.0),
    ]
    issues, holds = check_equity_roll_forward(rows, params=DealDatabookParams())
    assert not issues and not holds


def test_cash_roll_and_ni_cross() -> None:
    cash_rows = [
        _row("c0", metric_key="cash", fy=2023, value=10.0),
        _row("c1", metric_key="cash", fy=2024, value=25.0),
        _row("ch", metric_key="net_change_in_cash", fy=2024, value=15.0),
    ]
    issues, holds = check_cash_roll(cash_rows, params=DealDatabookParams())
    assert not issues and not holds

    ni_rows = [
        _row("a", metric_key="net_income", fy=2024, value=100.0, statement="income_statement", source_name="is.pdf"),
        _row("b", metric_key="net_income", fy=2024, value=80.0, statement="cash_flow", source_name="cf.pdf"),
    ]
    issues, holds = check_ni_cross_statement(ni_rows, params=DealDatabookParams())
    assert holds == {"a", "b"}
    assert issues[0]["check_id"] == "ni_cross"


def test_notes_and_draft_to_final_hold() -> None:
    rows = [_row("r", metric_key="revenue", fy=2024, value=100.0)]
    notes = [
        NoteFact(
            note_id="n1",
            doc_id="d",
            source_name="notes.pdf",
            caption="Revenue",
            fiscal_year=2024,
            value=120.0,
            metric_key="revenue",
        )
    ]
    issues, holds = check_notes_vs_statements(rows, notes, params=DealDatabookParams())
    assert "r" in holds
    assert issues[0]["check_id"] == "notes_vs_statements"

    draft_rows = [
        _row(
            "d",
            metric_key="revenue",
            fy=2024,
            value=90.0,
            source_basis=SourceBasis.DRAFT,
            ladder_score=40,
            source_name="draft.pdf",
        ),
        _row(
            "a",
            metric_key="revenue",
            fy=2024,
            value=100.0,
            source_basis=SourceBasis.AUDITED,
            ladder_score=100,
            source_name="audit.pdf",
        ),
    ]
    issues, holds = check_draft_to_final(draft_rows, params=DealDatabookParams())
    assert holds == {"d"}
    assert issues[0]["failure_class"] == FailureClass.DEFINITION.value

    annotated, extra, prove_issues = run_prove_pipeline(
        draft_rows,
        blocks=[],
        block_fail_ids=set(),
        hold_ids=set(),
        params=DealDatabookParams(),
    )
    assert "d" in extra
    draft = next(r for r in annotated if r.row_id == "d")
    final = next(r for r in annotated if r.row_id == "a")
    assert draft.proof_level == ProofLevel.L1
    assert final.proof_level in {ProofLevel.L2, ProofLevel.L3}
    assert any(i.get("check_id") == "draft_to_final" for i in prove_issues)


def test_g5_traps_and_golden() -> None:
    traps = {t.trap_id: t for t in run_all_traps()}
    for tid in ("t37", "t38", "t39", "t40", "t41", "t42"):
        assert tid in traps, tid
        assert traps[tid].ok, (tid, traps[tid].message)

    results = run_all_goldens()
    g5 = [f for r in results for f in r.failures if f.code.startswith("G5")]
    assert not g5, g5
    deal_a = next(r for r in results if r.golden_id == "deal_a")
    assert deal_a.ok, deal_a.failures


def test_prove_trap_dispatch() -> None:
    result = run_trap(
        {
            "trap_id": "local-equity-ok",
            "kind": "prove_pass",
            "check": "prove",
            "check_id": "equity_roll",
            "expect_fail": False,
            "rows": [
                {
                    "row_id": "e0",
                    "metric_key": "total_equity",
                    "metric_family": "other",
                    "fiscal_year": 2023,
                    "value": 100.0,
                },
                {
                    "row_id": "e1",
                    "metric_key": "total_equity",
                    "metric_family": "other",
                    "fiscal_year": 2024,
                    "value": 140.0,
                },
                {
                    "row_id": "ni",
                    "metric_key": "net_income",
                    "metric_family": "other",
                    "fiscal_year": 2024,
                    "value": 40.0,
                },
            ],
        }
    )
    assert result.ok, result.message
