"""FDD Phase 2 — readiness (G0), scope profile, G1 approval."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api.fdd_schemas import (
    ArtefactStatus,
    DEFAULT_SECTIONS_IN_SCOPE,
    G0_PASS_THRESHOLD,
    InputKey,
)
from agetic_cdd_api.services_databook_models import (
    DatabookRelease,
    ProofLevel,
    ReleaseCellStatus,
    ReleasedCell,
    SourceBasis,
    SourceRef,
)
from agetic_cdd_api.services_databook_release import SlugDeal
from agetic_cdd_api.services_databook_store import save_release
from agetic_cdd_api.services_fdd_bridge import GateBlockedError
from agetic_cdd_api.services_fdd_readiness import (
    build_readiness_report,
    scan_and_persist_readiness,
)
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_scope import (
    ScopeValidationError,
    approve_g1,
    default_periods,
    seed_scope_profile,
    update_scope_profile,
    validate_scope_for_g1,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_approval,
    load_manifest,
    load_readiness,
    load_request_list,
    load_scope_profile,
)


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    monkeypatch.setattr(store_mod, "deals_root", lambda: root)
    return root


def _complete_cell(
    *,
    metric_key: str = "revenue",
    fiscal_year: int = 2024,
    value: float = 100.0,
) -> ReleasedCell:
    return ReleasedCell(
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        status=ReleaseCellStatus.PROVEN,
        value=value,
        currency="INR",
        scale="Cr",
        unit="Cr",
        row_id=f"r_{metric_key}_{fiscal_year}",
        sources=["Audited_FS.pdf"],
        captions=[metric_key.replace("_", " ").title()],
        scope="consolidated",
        statement="IS",
        period_end=f"{fiscal_year}-12-31",
        period_length="FY",
        source_basis=SourceBasis.AUDITED,
        source_ref=SourceRef(doc="Audited_FS.pdf", page=1, table="IS", row=1, col=1),
        proof_level=ProofLevel.L2,
    )


def _seed_rich_deal(slug: str, deal_root: Path) -> None:
    root = deal_root / slug
    (root / "documents").mkdir(parents=True, exist_ok=True)
    for name in ("FS_2024.pdf", "CIM.pdf", "mgmt_qa.pdf", "org_chart.pdf"):
        (root / "documents" / name).write_bytes(b"%PDF-1.4 stub")
    (root / "library").mkdir(parents=True, exist_ok=True)
    (root / "library" / "index.json").write_text("{}", encoding="utf-8")
    out = root / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    for key in (
        "historical_performance",
        "company_background",
        "revenue_quality",
        "cost_structure",
        "deal_context_and_objectives",
    ):
        (out / f"{key}.json").write_text(
            json.dumps({"agent_key": key, "ok": True}), encoding="utf-8"
        )
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_ready",
        version=1,
        created_at="2026-10-07T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[
            _complete_cell(metric_key="revenue", value=3140.0),
            _complete_cell(metric_key="ebitda", value=690.0),
        ],
        counts={"proven": 2},
    )
    save_release(deal, release, set_current=True)


def test_score_readiness_threshold() -> None:
    assert G0_PASS_THRESHOLD == 0.9


def test_default_periods_respects_explicit_end_year() -> None:
    assert default_periods(end_year=2025) == ["FY23A", "FY24A", "FY25A"]


def test_validate_materiality_pct_rejects_bad_values() -> None:
    from agetic_cdd_api.fdd_schemas import ScopeProfile

    profile = ScopeProfile(
        profile_id="p1",
        deal_slug="d",
        run_id="r",
        entities_in=["Acme"],
        deal_type="buy-side",
        periods=["FY24A"],
        currency="INR",
        materiality_pct=0.05,
        sections_in_scope=list(DEFAULT_SECTIONS_IN_SCOPE),
    )
    assert validate_scope_for_g1(profile) == []
    bad = profile.model_copy(update={"materiality_pct": 1.5})
    assert "materiality_pct_out_of_range" in validate_scope_for_g1(bad)


def test_readiness_scan_fails_on_empty_deal(deal_root: Path) -> None:
    slug = "empty-ready"
    m = create_run(slug)
    report, requests = build_readiness_report(slug, m.run_id, company=None)
    assert report.g0_blocked
    assert not report.g0_passed
    assert report.score < G0_PASS_THRESHOLD
    assert InputKey.DATABOOK.value in report.blocking_gaps
    assert requests.items


def test_readiness_scan_passes_on_rich_deal(deal_root: Path) -> None:
    slug = "rich-ready"
    _seed_rich_deal(slug, deal_root)
    m = create_run(slug, databook_release_id="rel_ready", databook_release_version=1)
    report, requests, manifest = scan_and_persist_readiness(
        slug,
        m.run_id,
        company="Acme Co",
        description="Buy-side diligence on Acme Co platform business.",
        sector="saas",
    )
    assert report.g0_passed
    assert report.score >= G0_PASS_THRESHOLD
    assert manifest is not None and manifest.g0_passed
    loaded = load_readiness(slug, m.run_id)
    assert loaded is not None and loaded.g0_passed
    req = load_request_list(slug, m.run_id)
    assert req is not None
    # models + management may still appear as optional gaps; required gaps cleared
    required_keys = {
        InputKey.DATABOOK,
        InputKey.AGENTS,
        InputKey.VDR,
        InputKey.ENGAGEMENT_BRIEF,
        InputKey.HOUSE_TEMPLATE,
    }
    by_key = {i.key: i for i in report.inputs}
    for k in required_keys:
        assert by_key[k].present and by_key[k].tier_ok


def test_scope_seed_and_validate(deal_root: Path) -> None:
    slug = "scope-deal"
    m = create_run(slug)
    profile = seed_scope_profile(slug, m.run_id, company="Acme")
    assert profile.entities_in == ["Acme"]
    assert profile.currency == "USD"
    assert profile.materiality_pct == 0.05
    assert set(DEFAULT_SECTIONS_IN_SCOPE).issubset(set(profile.sections_in_scope))
    # Seed has materiality_pct so G1 field validation passes without absolute M
    assert validate_scope_for_g1(profile) == []
    again = seed_scope_profile(slug, m.run_id, company="Other")
    assert again.profile_id == profile.profile_id  # idempotent


def test_scope_update_and_g1_requires_g0(deal_root: Path) -> None:
    slug = "g1-block"
    m = create_run(slug)
    seed_scope_profile(slug, m.run_id, company="Acme")
    update_scope_profile(
        slug,
        m.run_id,
        {"deal_type": "buy-side", "materiality_m": 5.0, "periods": ["FY22A", "FY23A", "FY24A"]},
    )
    with pytest.raises(GateBlockedError, match="G0"):
        approve_g1(slug, m.run_id, decided_by="lead@test", require_g0=True)


def test_g1_approve_after_g0(deal_root: Path) -> None:
    slug = "g1-ok"
    _seed_rich_deal(slug, deal_root)
    m = create_run(slug, databook_release_id="rel_ready", databook_release_version=1)
    scan_and_persist_readiness(
        slug,
        m.run_id,
        company="Acme Co",
        description="Buy-side diligence engagement brief for Acme.",
    )
    seed_scope_profile(slug, m.run_id, company="Acme Co")
    update_scope_profile(
        slug,
        m.run_id,
        {
            "entities_in": ["Acme Co", "Acme Sub"],
            "deal_type": "buy-side",
            "materiality_m": 34.5,
            "sections_in_scope": list(DEFAULT_SECTIONS_IN_SCOPE),
        },
    )
    profile, approval, manifest = approve_g1(
        slug, m.run_id, decided_by="lead@test", note="Perimeter confirmed"
    )
    assert profile.status == ArtefactStatus.APPROVED
    assert profile.approved_by == "lead@test"
    assert approval.gate.value == "G1"
    assert manifest.g1_approved
    assert load_approval(slug, m.run_id, "G1") is not None

    with pytest.raises(ScopeValidationError, match="G1-approved"):
        update_scope_profile(slug, m.run_id, {"notes": "tweak"})

    revised = update_scope_profile(
        slug, m.run_id, {"notes": "revised"}, allow_edit_approved=True
    )
    assert revised.status == ArtefactStatus.DRAFT
    assert load_manifest(slug, m.run_id).g1_approved is False


def test_ensure_run_seeds_phase2(deal_root: Path) -> None:
    slug = "ensure-p2"
    _seed_rich_deal(slug, deal_root)
    manifest, _store, _spec = ensure_phase0_run(
        slug, company="Acme Co", bridge_databook=True
    )
    scope = load_scope_profile(slug, manifest.run_id)
    readiness = load_readiness(slug, manifest.run_id)
    assert scope is not None
    assert readiness is not None
    refreshed = load_manifest(slug, manifest.run_id)
    assert refreshed is not None
    assert "fdd_phase2" in (refreshed.model_versions or {})
