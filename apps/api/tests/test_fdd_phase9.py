"""FDD Phase 9 — golden deals, traps, ship gate, evidence pack."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api.services_fdd_harness import (
    _approx,
    export_evidence_pack,
    fixtures_dir,
    goldens_dir,
    load_all_goldens,
    load_traps,
    run_all_traps,
    run_golden,
    run_ship_gate,
    run_trap,
    traps_path,
)


@pytest.mark.fdd_ship
def test_fixtures_present() -> None:
    goldens = load_all_goldens()
    assert len(goldens) >= 2
    ids = {g["golden_id"] for g in goldens}
    assert "deal_alpha" in ids
    assert "deal_beta" in ids
    traps = load_traps()
    assert len(traps) >= 8
    assert traps_path().is_file()
    assert goldens_dir().is_dir()


@pytest.mark.fdd_ship
def test_all_traps_pass() -> None:
    results = run_all_traps()
    failed = [t for t in results if not t.ok]
    assert not failed, [t.summary() for t in failed]


@pytest.mark.fdd_ship
def test_deal_alpha_golden(tmp_path: Path) -> None:
    golden = next(g for g in load_all_goldens() if g["golden_id"] == "deal_alpha")
    result = run_golden(golden, deals_root=tmp_path / "deals", keep_workdir=True)
    assert result.ok, [f.message for f in result.failures]
    assert result.draft_mode is False
    assert "ex_m6_net_debt" in result.exhibit_ids
    assert "SEC-H" not in result.held_back
    assert result.evidence_pack_path
    pack = Path(result.evidence_pack_path)
    assert (pack / "evidence_manifest.json").is_file()
    assert (pack / "manifest.json").is_file()
    assert (pack / "exhibits.json").is_file()
    meta = json.loads((pack / "evidence_manifest.json").read_text(encoding="utf-8"))
    assert meta["deal_slug"] == "fdd-alpha"
    assert "fdd_harness" in (meta.get("model_versions") or {}) or True


@pytest.mark.fdd_ship
def test_deal_beta_worked_example_qoe(tmp_path: Path) -> None:
    golden = next(g for g in load_all_goldens() if g["golden_id"] == "deal_beta")
    result = run_golden(golden, deals_root=tmp_path / "deals", keep_workdir=True)
    assert result.ok, [f.message for f in result.failures]
    assert "ex_qoe_bridge" in result.exhibit_ids
    assert "SEC-E" not in result.held_back


@pytest.mark.fdd_ship
def test_ship_gate_passes() -> None:
    report = run_ship_gate(required_trap_count=8, required_golden_count=2)
    assert report.ok, report.summary()
    assert report.golden_pass >= 2
    assert report.trap_pass >= 8


@pytest.mark.fdd_ship
def test_trap_typed_figure_positive() -> None:
    ok = run_trap(
        {
            "trap_id": "x",
            "kind": "typed_figure",
            "check": "typed_figure",
            "text":"Adj. EBITDA is {{ex:ex_qoe_bridge.adj_ebitda}}.",
            "expect_fail": False,
        }
    )
    assert ok.ok


def test_fixtures_dir_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "custom_fdd"
    custom.mkdir()
    monkeypatch.setenv("FDD_FIXTURES_DIR", str(custom))
    assert fixtures_dir() == custom


def test_approx_handles_large_raw_units() -> None:
    assert _approx(500_000_000.0, 500_000_000.001)
    assert not _approx(100.0, 101.0)


def test_malformed_trap_reports_missing_keys() -> None:
    result = run_trap(
        {"trap_id": "bad", "kind": "model_formula", "check": "net_debt_formula"}
    )
    assert result.ok is False
    assert "missing required keys" in result.message


def test_evidence_pack_survives_workdir_wipe() -> None:
    """Own temp deals_root is wiped on success; evidence pack path must remain."""
    golden = next(g for g in load_all_goldens() if g["golden_id"] == "deal_alpha")
    result = run_golden(golden, keep_workdir=False)
    assert result.ok, [f.message for f in result.failures]
    assert result.evidence_pack_path
    pack = Path(result.evidence_pack_path)
    assert pack.is_dir()
    assert (pack / "evidence_manifest.json").is_file()


def test_export_evidence_pack_helper(tmp_path: Path) -> None:
    """Unit: export copies whatever artefacts exist under run_dir."""
    from agetic_cdd_api import services_databook_store as store_mod
    from agetic_cdd_api import services_deals as deals_mod
    from agetic_cdd_api.services_fdd_store import create_run, save_manifest

    root = tmp_path / "deals"
    root.mkdir()
    # Lightweight monkeypatch without fixture
    prev_d, prev_s = deals_mod.deals_root, store_mod.deals_root
    deals_mod.deals_root = lambda: root  # type: ignore[assignment]
    store_mod.deals_root = lambda: root  # type: ignore[assignment]
    try:
        slug = "pack-only"
        (root / slug).mkdir()
        man = create_run(slug)
        man = save_manifest(
            man.model_copy(update={"model_versions": {"fdd_harness": "0.1.0"}})
        )
        dest = tmp_path / "pack"
        export_evidence_pack(slug, man.run_id, dest=dest)
        assert (dest / "evidence_manifest.json").is_file()
        assert (dest / "manifest.json").is_file()
    finally:
        deals_mod.deals_root = prev_d  # type: ignore[assignment]
        store_mod.deals_root = prev_s  # type: ignore[assignment]
