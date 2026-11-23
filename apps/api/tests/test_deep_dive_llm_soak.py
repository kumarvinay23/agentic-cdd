"""Deep Dive LLM soak harness — offline A/B gates."""

from __future__ import annotations

import pytest

from agetic_cdd_api.services_deep_dive_llm_soak import (
    MIN_NUMERIC_LOCK_RATE,
    MIN_REFINE_APPLY_RATE,
    format_soak_report,
    list_golden_paths,
    run_deep_dive_llm_soak,
    score_side,
)


def test_deep_dive_llm_soak_suite_meets_ship_gates() -> None:
    paths = list_golden_paths()
    assert paths, "expected soak goldens under tests/fixtures/deep_dive_llm_soak/goldens"
    report = run_deep_dive_llm_soak(golden_paths=paths, use_live_llm=False)
    assert report.mode == "fixture_llm"
    assert report.case_total >= 2
    assert report.numeric_lock_rate >= MIN_NUMERIC_LOCK_RATE
    assert report.invented_number_rate == 0.0
    assert report.refine_apply_rate >= MIN_REFINE_APPLY_RATE
    assert report.passed, format_soak_report(report)
    for case in report.case_results:
        assert case.off.llm_refined is False
        assert case.on.llm_refined is True
        assert case.on.extractor == "hybrid_v1"
        assert case.numeric_locked is True


def test_score_side_counts_prose_and_fingerprint() -> None:
    payload = {
        "extractor": "hybrid_v1",
        "llm_refined": True,
        "nps": 34.0,
        "service_satisfaction_pct": 52.0,
        "satisfaction_notes": [
            "NPS significantly below category leaders — indicates service experience gap."
        ],
        "churn_drivers": [
            {"driver": "Service Delay & Unresolved Complaints", "contribution_pct": 31}
        ],
    }
    metrics = score_side(
        "customer_satisfaction",
        payload,
        "NPS Score 34 Service Satisfaction 52% Service Delay 31%",
    )
    assert metrics.prose_items >= 2
    assert metrics.prose_chars > 40
    assert metrics.numeric_fingerprint["nps"] == 34.0
    assert metrics.invented_numbers == 0
