"""G6 — full-size goldens + ship-gate figure budgets (H-1)."""

from __future__ import annotations

from agetic_cdd_api.databook_ship_gate import main as ship_gate_main
from agetic_cdd_api.services_databook_harness import (
    count_golden_figures,
    fixture_root,
    load_golden,
    run_golden,
    run_ship_gate,
)


def test_count_golden_figures_excludes_forbid_sources() -> None:
    golden = {
        "forbid_sources": ["x.pdf"],
        "documents": [
            {
                "filename": "keep.pdf",
                "tables": [{"name": "t", "rows": [["M", "FY2024"], ["Revenue", "1"], ["EBITDA", "2"]]}],
            },
            {
                "filename": "x.pdf",
                "tables": [{"name": "t", "rows": [["M", "FY2024"], ["Revenue", "9"]]}],
            },
        ],
    }
    assert count_golden_figures(golden) == 2


def test_deal_a_and_b_meet_h1_budgets() -> None:
    a = load_golden(fixture_root() / "goldens" / "deal_a.json")
    b = load_golden(fixture_root() / "goldens" / "deal_b.json")
    assert int(a.get("expected_min_figures") or 0) >= 195
    assert int(b.get("expected_min_figures") or 0) >= 252
    assert count_golden_figures(a) >= 195
    assert count_golden_figures(b) >= 252


def test_golden_runner_enforces_min_figures() -> None:
    ra = run_golden(fixture_root() / "goldens" / "deal_a.json")
    rb = run_golden(fixture_root() / "goldens" / "deal_b.json")
    assert ra.ok, ra.failures
    assert rb.ok, rb.failures
    assert ra.figures >= ra.min_figures >= 195
    assert rb.figures >= rb.min_figures >= 252


def test_ship_gate_reports_figures() -> None:
    report = run_ship_gate()
    assert report.ok
    by_id = {g.golden_id: g for g in report.goldens}
    assert by_id["deal_a"].figures >= 195
    assert by_id["deal_b"].figures >= 252
    assert ship_gate_main(["--json"]) == 0
