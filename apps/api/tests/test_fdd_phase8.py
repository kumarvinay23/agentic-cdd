"""FDD Phase 8 — QA catalogue, G5–G7, snapshot hash, material-change reset."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_qa import (
    add_challenge,
    approve_g5,
    approve_g6,
    build_qa_pack,
    freeze_snapshot,
    reset_gates_on_material_change,
    respond_challenge,
    seed_s1_agent_figure,
    verify_g7,
)
from agetic_cdd_api.services_fdd_qoe import build_qoe_workbook
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_scope import approve_g1, seed_scope_profile
from agetic_cdd_api.services_fdd_store import (
    load_approval,
    load_manifest,
    load_qa_pack,
    load_snapshot,
    save_manifest,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _seed_run(slug: str, *, company: str = "RetailCo"):
    (deals_mod.deals_root() / slug).mkdir(parents=True, exist_ok=True)
    manifest, store, spec = ensure_phase0_run(
        slug, company=company, revenue_fy24=100.0, prefer_current_release=True
    )
    build_qoe_workbook(slug, manifest.run_id, worked_example=True)
    return manifest, store, spec


def test_qa_scan_passes_clean_run(deal_root: Path) -> None:
    slug = "p8-clean"
    manifest, _store, _spec = _seed_run(slug)
    # Scope with entities so perimeter S1 does not fire
    seed_scope_profile(slug, manifest.run_id, company="RetailCo")
    profile = __import__(
        "agetic_cdd_api.services_fdd_store", fromlist=["load_scope_profile"]
    ).load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    from agetic_cdd_api.services_fdd_store import save_scope_profile

    save_scope_profile(
        profile.model_copy(update={"entities_in": ["RetailCo Ltd"], "entities_out": []})
    )

    doc = build_qa_pack(slug, manifest.run_id)
    assert doc.open_s1_count == 0
    assert doc.g5_ready is True
    assert any(c.check_id == "recon_report_deck" and c.passed for c in doc.checks)
    assert any(c.check_id == "evidence_cells" and c.passed for c in doc.checks)
    assert any(c.check_id == "arithmetic_qoe_bridge" and c.passed for c in doc.checks)

    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    assert man.qa_built is True
    assert man.stage.value == "P8"


def test_seeded_s1_agent_figure_blocks_g5(deal_root: Path) -> None:
    slug = "p8-s1"
    manifest, _store, _spec = _seed_run(slug)
    seed_scope_profile(slug, manifest.run_id, company="X")
    from agetic_cdd_api.services_fdd_store import load_scope_profile, save_scope_profile

    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["X Co"]}))

    seed_s1_agent_figure(slug, manifest.run_id)
    doc = build_qa_pack(slug, manifest.run_id)
    assert doc.open_s1_count >= 1
    assert doc.g5_ready is False
    assert any(
        i.severity == "S1" and "agent:" in i.message.lower() for i in doc.issues
    )

    with pytest.raises(GateBlockedError, match="G5"):
        approve_g5(slug, manifest.run_id, decided_by="lead@test")


def test_g5_approve_freeze_g7_verify(deal_root: Path) -> None:
    slug = "p8-g7"
    manifest, _store, _spec = _seed_run(slug)
    seed_scope_profile(slug, manifest.run_id, company="Y")
    from agetic_cdd_api.services_fdd_store import load_scope_profile, save_scope_profile

    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["Y Co"]}))

    doc = build_qa_pack(slug, manifest.run_id)
    assert doc.g5_ready
    doc, appr, man = approve_g5(slug, manifest.run_id, decided_by="lead@test")
    assert doc.g5_approved is True
    assert appr.gate.value == "G5"
    assert man.g5_approved is True
    assert load_approval(slug, manifest.run_id, "G5") is not None

    snap = freeze_snapshot(slug, manifest.run_id, frozen_by="lead@test")
    assert snap.figures_hash
    assert load_snapshot(slug, manifest.run_id) is not None

    snap2, appr7, man7 = verify_g7(slug, manifest.run_id, decided_by="system")
    assert snap2.g7_verified is True
    assert appr7.gate.value == "G7"
    assert man7.g7_verified is True
    assert man7.stage.value == "P10"


def test_material_change_resets_gates_and_breaks_g7(deal_root: Path) -> None:
    slug = "p8-reset"
    manifest, store, _spec = _seed_run(slug)
    seed_scope_profile(slug, manifest.run_id, company="Z")
    from agetic_cdd_api.services_fdd_store import load_scope_profile, save_scope_profile

    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["Z Co"]}))

    build_qa_pack(slug, manifest.run_id)
    approve_g5(slug, manifest.run_id, decided_by="lead@test")
    freeze_snapshot(slug, manifest.run_id, frozen_by="lead@test")
    verify_g7(slug, manifest.run_id)

    # Material change — reset gates
    reset_gates_on_material_change(slug, manifest.run_id, reason="test edit")
    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    assert man.g5_approved is False
    assert man.g7_verified is False
    assert man.snapshot_id is None

    qa = load_qa_pack(slug, manifest.run_id)
    assert qa is not None
    assert qa.g5_approved is False

    # Re-approve + freeze, then inject S1 and ensure G7 fails on hash mismatch
    build_qa_pack(slug, manifest.run_id)
    approve_g5(slug, manifest.run_id, decided_by="lead@test")
    freeze_snapshot(slug, manifest.run_id, frozen_by="lead@test")
    seed_s1_agent_figure(slug, manifest.run_id)
    # After seed, gates reset; re-scan will have S1. Freeze is superseded.
    # Re-approve path for hash mismatch: restore g5, freeze again, mutate without reset
    build_qa_pack(slug, manifest.run_id)
    # Clear agent trap for a clean G5 then freeze, then mutate store hash only via reset+seed after freeze
    # Simpler: freeze again after clearing isn't needed — verify_g7 after seed_s1 which superseded snap
    with pytest.raises(GateBlockedError):
        # snapshot superseded → g7_verified false; verify still runs against superseded?
        # seed_s1 superseded the snap status but file remains — hashes will mismatch
        verify_g7(slug, manifest.run_id)


def test_claims_check_fails_when_contradicted(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import ClaimsLedgerDoc, ClaimsLedgerEntry
    from agetic_cdd_api.services_fdd_qa import _check_claims_agent_ban
    from agetic_cdd_api.services_fdd_store import create_run, save_claims_ledger

    slug = "p8-claims"
    m = create_run(slug)
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=m.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="c1",
                    text="Revenue is 999",
                    kind="financial",
                    test_result="contradicted",
                    failed=True,
                )
            ],
        )
    )
    check, issues = _check_claims_agent_ban(slug, m.run_id)
    assert check.passed is False
    assert len(issues) == 1
    assert issues[0].severity == "S2"


def test_soft_rescan_preserves_g5_approval(deal_root: Path) -> None:
    slug = "p8-soft"
    manifest, _store, _spec = _seed_run(slug)
    seed_scope_profile(slug, manifest.run_id, company="SoftCo")
    from agetic_cdd_api.services_fdd_store import load_scope_profile, save_scope_profile

    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["SoftCo Ltd"]}))

    build_qa_pack(slug, manifest.run_id)
    approve_g5(slug, manifest.run_id, decided_by="lead@test")
    again = build_qa_pack(slug, manifest.run_id)  # soft rescan, no artefact change
    assert again.g5_approved is True
    assert again.g5_ready is True


def test_stable_issue_id_ignores_message_phrasing() -> None:
    from agetic_cdd_api.services_fdd_qa import _open_issue

    a = _open_issue(
        check_id="evidence_cells",
        severity="S1",
        message="Cell ex.a has value but no fact_id",
        cell_ref_s="ex.a",
        suffix="ex.a",
    )
    b = _open_issue(
        check_id="evidence_cells",
        severity="S1",
        message="Cell ex.a is missing a fact identifier",  # different prose
        cell_ref_s="ex.a",
        suffix="ex.a",
    )
    assert a.issue_id == b.issue_id


def test_g6_blocked_in_draft_and_by_open_challenge(deal_root: Path) -> None:
    slug = "p8-g6"
    manifest, _store, _spec = _seed_run(slug)
    seed_scope_profile(slug, manifest.run_id, company="W")
    from agetic_cdd_api.services_fdd_store import load_scope_profile, save_scope_profile

    profile = load_scope_profile(slug, manifest.run_id)
    assert profile is not None
    save_scope_profile(profile.model_copy(update={"entities_in": ["W Co"]}))

    build_qa_pack(slug, manifest.run_id)
    approve_g5(slug, manifest.run_id, decided_by="lead@test")

    # Draft mode → G6 blocked (IN-3)
    with pytest.raises(GateBlockedError, match="G6"):
        approve_g6(slug, manifest.run_id, decided_by="partner@test")

    # Clear draft / contract so G6 contract gate passes
    man = load_manifest(slug, manifest.run_id)
    assert man is not None
    save_manifest(
        man.model_copy(
            update={
                "draft_mode": False,
                "g6_blocked": False,
                "contract_complete": True,
            }
        )
    )

    # Open challenge blocks G6
    add_challenge(slug, manifest.run_id, title="Challenge EBITDA bridge", raised_by="p")
    with pytest.raises(GateBlockedError, match="challenge"):
        approve_g6(slug, manifest.run_id, decided_by="partner@test")

    qa = load_qa_pack(slug, manifest.run_id)
    assert qa is not None
    ch_id = qa.challenges[0].challenge_id
    respond_challenge(
        slug,
        manifest.run_id,
        ch_id,
        status="accepted",
        response="Accepted — disclosed",
        responded_by="lead@test",
    )
    doc, appr, man2 = approve_g6(slug, manifest.run_id, decided_by="partner@test")
    assert doc.g6_approved is True
    assert appr.gate.value == "G6"
    assert man2.g6_approved is True
    assert man2.stage.value == "P9"
