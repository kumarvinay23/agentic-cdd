"""Golden VDR eval for Gate-2-miss fin discovery (recovery + false-promote gates)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.services_fin_discovery_eval import (
    MAX_FALSE_PROMOTE_RATE,
    MIN_RECOVERY_RATE,
    MIN_TOP1_HIT_RATE,
    MIN_TRAP_BLOCK_RATE,
    format_eval_report,
    list_golden_paths,
    load_golden,
    run_fin_discovery_eval,
    run_golden_case,
    select_auto_promote_targets,
)


def test_list_and_load_goldens() -> None:
    paths = list_golden_paths()
    assert len(paths) >= 5
    ids = {p.stem for p in paths}
    assert "umoja_opaque_miss" in ids
    assert "trap_cim_only" in ids
    assert "trap_forecast_lbo" in ids
    assert "gate_pass_clean" in ids
    golden = load_golden(paths[0])
    assert golden["id"]
    assert "files" in golden
    assert "assert" in golden


def test_select_auto_promote_targets_skips_traps() -> None:
    ranked = [
        {
            "filename": "CIM_Pack.xlsx",
            "suggested_doc_type": "FIN_INVESTOR_WORKBOOK",
            "confidence": 0.9,
            "risk_flags": ["cim_like"],
        },
        {
            "filename": "hist.xlsx",
            "suggested_doc_type": "FIN_MGMT_ACCOUNTS",
            "confidence": 0.9,
            "risk_flags": [],
        },
    ]
    selected, skipped = select_auto_promote_targets(ranked)
    assert [c["filename"] for c in selected] == ["hist.xlsx"]
    cim_skip = next(s for s in skipped if s["filename"] == "CIM_Pack.xlsx")
    assert str(cim_skip["reason"]).startswith("risk:")
    assert "cim_like" in (cim_skip.get("risk_flags") or [])
    assert any(str(r).startswith("risk:") for r in (cim_skip.get("reasons") or []))


def test_umoja_opaque_miss_recovers(tmp_path: Path) -> None:
    from agetic_cdd_api import services_deals as deals_mod

    golden = load_golden(
        next(p for p in list_golden_paths() if p.stem == "umoja_opaque_miss")
    )
    prev = deals_mod.deals_root
    deals_mod.deals_root = lambda: tmp_path
    try:
        result = run_golden_case(golden, deals_root=tmp_path, use_llm=False)
    finally:
        deals_mod.deals_root = prev

    assert result.passed, result.notes
    assert result.recovered is True
    assert result.false_promote is False
    assert result.top1_hit is True
    assert result.would_promote == ["Umoja_Pack_v3.xlsx"]


def test_trap_cases_do_not_false_promote(tmp_path: Path) -> None:
    from agetic_cdd_api import services_deals as deals_mod

    prev = deals_mod.deals_root
    deals_mod.deals_root = lambda: tmp_path
    try:
        for stem in ("trap_cim_only", "trap_forecast_lbo"):
            golden = load_golden(next(p for p in list_golden_paths() if p.stem == stem))
            result = run_golden_case(golden, deals_root=tmp_path, use_llm=False)
            assert result.passed, (stem, result.notes)
            assert result.false_promote is False
            assert result.recovered is False
            assert result.trap_blocked is True
            assert result.would_promote == []
    finally:
        deals_mod.deals_root = prev


def test_gate_pass_does_not_run_discovery(tmp_path: Path) -> None:
    from agetic_cdd_api import services_deals as deals_mod

    golden = load_golden(
        next(p for p in list_golden_paths() if p.stem == "gate_pass_clean")
    )
    prev = deals_mod.deals_root
    deals_mod.deals_root = lambda: tmp_path
    try:
        result = run_golden_case(golden, deals_root=tmp_path, use_llm=False)
    finally:
        deals_mod.deals_root = prev

    assert result.passed, result.notes
    assert result.discovery_should_run is False
    assert result.discovery_ran is False


@pytest.mark.fin_discovery_eval
def test_fin_discovery_eval_suite_meets_ship_gates() -> None:
    report = run_fin_discovery_eval(use_llm=False)
    text = format_eval_report(report)
    assert report.case_total >= 5, text
    assert report.recovery_rate >= MIN_RECOVERY_RATE, text
    assert report.false_promote_rate <= MAX_FALSE_PROMOTE_RATE, text
    assert report.top1_hit_rate >= MIN_TOP1_HIT_RATE, text
    assert report.trap_block_rate >= MIN_TRAP_BLOCK_RATE, text
    assert report.passed, text
    payload = report.to_dict()
    assert payload["passed"] is True
    assert "cases" in payload
