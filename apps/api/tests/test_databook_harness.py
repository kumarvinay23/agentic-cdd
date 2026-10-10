"""Phase 7 — goldens, traps, and CI ship gate (H-1…H-7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api.databook_ship_gate import main as ship_gate_main
from agetic_cdd_api.services_databook_harness import (
    fixture_root,
    load_traps_fixture,
    run_all_goldens,
    run_all_traps,
    run_golden,
    run_ship_gate,
    run_trap,
)


pytestmark = pytest.mark.databook_ship


def test_fixture_layout_present() -> None:
    root = fixture_root()
    assert (root / "traps.jsonl").is_file()
    goldens = list((root / "goldens").glob("*.json"))
    assert len(goldens) >= 2


def test_trap_suite_has_at_least_32() -> None:
    traps = load_traps_fixture()
    assert len(traps) >= 32
    ids = [t["trap_id"] for t in traps]
    assert len(ids) == len(set(ids)), "duplicate trap_id"


def test_each_trap_passes() -> None:
    failures = [t for t in run_all_traps() if not t.ok]
    assert not failures, "; ".join(f"{t.trap_id}: {t.message}" for t in failures)


def test_goldens_pass_and_are_bit_identical() -> None:
    results = run_all_goldens()
    assert len(results) >= 2
    for g in results:
        assert g.ok, f"{g.golden_id}: " + "; ".join(
            f"[{f.code}] {f.message}" for f in g.failures
        )
        assert g.fingerprint
        # Re-run single golden — fingerprint must be stable (H-6)
        again = run_golden(fixture_root() / "goldens" / f"{g.golden_id}.json")
        assert again.fingerprint == g.fingerprint


def test_g6_full_size_figure_budgets() -> None:
    """H-1 — Deal A ≥195 / Deal B ≥252 history figures (excludes forbid_sources)."""
    from agetic_cdd_api.services_databook_harness import count_golden_figures, load_golden

    a = load_golden(fixture_root() / "goldens" / "deal_a.json")
    b = load_golden(fixture_root() / "goldens" / "deal_b.json")
    assert count_golden_figures(a) >= 195
    assert count_golden_figures(b) >= 252
    ra = run_golden(fixture_root() / "goldens" / "deal_a.json")
    rb = run_golden(fixture_root() / "goldens" / "deal_b.json")
    assert ra.ok and ra.figures >= 195
    assert rb.ok and rb.figures >= 252
    assert ra.min_figures >= 195
    assert rb.min_figures >= 252


def test_ship_gate_passes() -> None:
    report = run_ship_gate()
    assert report.ok
    assert report.trap_pass >= 32
    assert report.golden_fail == 0


def test_ship_gate_cli_exits_zero() -> None:
    assert ship_gate_main([]) == 0


def test_deal_a_contamination_and_coverage() -> None:
    g = run_golden(fixture_root() / "goldens" / "deal_a.json")
    assert g.ok
    assert g.proven >= 2
    codes = {f.code for f in g.failures}
    assert "H-5" not in codes
    assert "H-4" not in codes


def test_single_trap_map_units() -> None:
    r = run_trap(
        {
            "trap_id": "manual",
            "kind": "wrong_metric",
            "check": "map",
            "caption": "Units Sold",
            "expect_metric": "units_sold",
            "forbid_metric": "revenue",
        }
    )
    assert r.ok


def test_synthesize_does_not_overwrite_proven_with_conflict() -> None:
    from agetic_cdd_api.services_databook_harness import synthesize_release_cells
    from agetic_cdd_api.services_databook_models import (
        PromotedMetric,
        ReleaseCellStatus,
    )

    promoted = [
        PromotedMetric(
            metric_key="revenue",
            fiscal_year=2024,
            value=100.0,
            row_id="r1",
            sources=["a.pdf"],
            captions=["Revenue"],
        )
    ]
    conflicts = [
        {
            "metric": "Revenue",
            "fiscal_year": 2024,
            "candidates": [
                {"value": 100.0, "chosen": True, "sources": ["a.pdf"]},
                {"value": 90.0, "chosen": False, "sources": ["b.pdf"]},
            ],
        }
    ]
    cells = synthesize_release_cells(
        [],
        promoted,
        conflicts,
        coverage_keys=["revenue", "ebitda"],
        coverage_years={2023, 2024},
    )
    by_key = {(c.metric_key, c.fiscal_year): c for c in cells}
    proven = by_key[("revenue", 2024)]
    assert proven.status == ReleaseCellStatus.PROVEN
    assert proven.value == 100.0
    assert proven.alternatives  # audit alts attached, not overwritten
    assert by_key[("ebitda", 2023)].status == ReleaseCellStatus.MISSING
    assert by_key[("ebitda", 2024)].status == ReleaseCellStatus.MISSING


def test_synthesize_merges_alternatives_from_multiple_conflicts() -> None:
    from agetic_cdd_api.services_databook_harness import synthesize_release_cells
    from agetic_cdd_api.services_databook_models import PromotedMetric, ReleaseCellStatus

    promoted = [
        PromotedMetric(
            metric_key="revenue",
            fiscal_year=2024,
            value=100.0,
            row_id="r1",
            sources=["a.pdf"],
            captions=["Revenue"],
        )
    ]
    conflicts = [
        {
            "metric": "Revenue",
            "fiscal_year": 2024,
            "candidates": [
                {"value": 100.0, "chosen": True, "sources": ["a.pdf"], "row_id": "r1"},
                {"value": 90.0, "chosen": False, "sources": ["b.pdf"], "row_id": "r2"},
            ],
        },
        {
            "metric": "Revenue",
            "fiscal_year": 2024,
            "candidates": [
                {"value": 100.0, "chosen": True, "sources": ["a.pdf"], "row_id": "r1"},
                {"value": 85.0, "chosen": False, "sources": ["c.pdf"], "row_id": "r3"},
            ],
        },
    ]
    cells = synthesize_release_cells([], promoted, conflicts, coverage_keys=None)
    rev = next(c for c in cells if c.metric_key == "revenue")
    assert rev.status == ReleaseCellStatus.PROVEN
    alt_values = {a.get("value") for a in rev.alternatives}
    assert 90.0 in alt_values
    assert 85.0 in alt_values


def test_normalize_cells_clamps_negative_zero() -> None:
    from agetic_cdd_api.services_databook_harness import (
        cells_fingerprint,
        normalize_cells_for_compare,
    )
    from agetic_cdd_api.services_databook_models import ReleaseCellStatus, ReleasedCell

    neg_zero = ReleasedCell(
        metric_key="revenue",
        fiscal_year=2024,
        status=ReleaseCellStatus.PROVEN,
        value=-0.0,
    )
    pos_zero = ReleasedCell(
        metric_key="revenue",
        fiscal_year=2024,
        status=ReleaseCellStatus.PROVEN,
        value=0.0,
    )
    assert normalize_cells_for_compare([neg_zero]) == normalize_cells_for_compare([pos_zero])
    assert cells_fingerprint([neg_zero]) == cells_fingerprint([pos_zero])


def test_filter_history_docs_honours_explicit_set_aside_flag() -> None:
    from agetic_cdd_api.services_databook_harness import _filter_history_docs

    history, blocked = _filter_history_docs(
        [
            {
                "filename": "Acme_Audited_Financial_Statements_2024.pdf",
                "excerpt": "audited",
            },
            {
                "filename": "Vendor_Report.pdf",
                "excerpt": "vendor diligence",
                "set_aside": True,
            },
        ],
        deal_tokens={"acme"},
    )
    assert len(history) == 1
    assert len(blocked) == 1
    assert blocked[0]["filename"] == "Vendor_Report.pdf"


def test_float_membership_helper() -> None:
    from agetic_cdd_api.services_databook_harness import _float_in

    assert _float_in(12.3, {12.300000000000002})
    assert not _float_in(12.3, {12.4})
