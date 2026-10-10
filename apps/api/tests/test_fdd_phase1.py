"""FDD Phase 1 — databook contract bridge, draft mode, release pin."""

from __future__ import annotations

from pathlib import Path

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import CellStatus
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
from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api.services_fdd_bridge import (
    GateBlockedError,
    ReleasePinError,
    _exhibit_meta_for_metric,
    _format_number,
    _scale_header_from_facts,
    assert_g6_allowed,
    assess_databook_contract,
    bridge_release_into_run,
    check_release_pin,
    eight_labels_from_cell,
    facts_from_release,
    g6_allowed,
)
from agetic_cdd_api.fdd_schemas import FddFact, EightLabels
from agetic_cdd_api.services_fdd_render import ensure_phase0_run
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_fact_table,
    load_manifest,
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
    value: float = 3140.0,
    status: ReleaseCellStatus = ReleaseCellStatus.PROVEN,
) -> ReleasedCell:
    return ReleasedCell(
        metric_key=metric_key,
        fiscal_year=fiscal_year,
        status=status,
        value=value if status != ReleaseCellStatus.MISSING else None,
        currency="INR",
        scale="Cr",
        unit="Cr",
        row_id=f"r_{metric_key}_{fiscal_year}",
        sources=["Acme_Audited_Financial_Statements_2024.pdf"],
        captions=[metric_key.replace("_", " ").title()],
        scope="consolidated",
        statement="IS",
        period_end=f"{fiscal_year}-12-31",
        period_length="FY",
        source_basis=SourceBasis.AUDITED,
        source_ref=SourceRef(
            doc="Acme_Audited_Financial_Statements_2024.pdf",
            page=1,
            table="Income Statement",
            row=2,
            col=3,
        ),
        proof_level=ProofLevel.L2 if status == ReleaseCellStatus.PROVEN else ProofLevel.L1,
    )


def _save_release(
    slug: str,
    cells: list[ReleasedCell],
    *,
    release_id: str = "rel_v1",
    version: int = 1,
) -> DatabookRelease:
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id=release_id,
        version=version,
        created_at="2026-10-06T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=cells,
        counts={"proven": sum(1 for c in cells if c.status == ReleaseCellStatus.PROVEN)},
    )
    save_release(deal, release, set_current=True)
    return release


def test_eight_labels_complete_and_incomplete() -> None:
    cell = _complete_cell()
    labels = eight_labels_from_cell(cell)
    assert labels.complete
    thin = ReleasedCell(
        metric_key="revenue",
        fiscal_year=2024,
        status=ReleaseCellStatus.PROVEN,
        value=1.0,
    )
    assert eight_labels_from_cell(thin).missing_fields()


def test_contract_incomplete_without_release(deal_root: Path) -> None:
    a = assess_databook_contract(None, deal_slug="x")
    assert a.draft_mode and not a.complete and not a.g6_allowed
    assert "no_databook_release" in a.reasons


def test_contract_complete_with_labelled_material_cells(deal_root: Path) -> None:
    slug = "complete-deal"
    release = _save_release(
        slug,
        [
            _complete_cell(metric_key="revenue", fiscal_year=2024, value=100),
            _complete_cell(metric_key="ebitda", fiscal_year=2024, value=20),
            _complete_cell(
                metric_key="nrr",
                fiscal_year=2024,
                value=None,
                status=ReleaseCellStatus.MISSING,
            ),
        ],
    )
    # Missing nrr needs labels only when non-missing — strip labels OK
    release.cells[2] = ReleasedCell(
        metric_key="nrr",
        fiscal_year=2024,
        status=ReleaseCellStatus.MISSING,
        value=None,
    )
    a = assess_databook_contract(release, deal_slug=slug)
    assert a.complete
    assert a.g6_allowed
    assert not a.draft_mode


def test_contract_incomplete_when_labels_missing(deal_root: Path) -> None:
    release = DatabookRelease(
        release_id="rel_thin",
        version=1,
        created_at="2026-10-06T00:00:00Z",
        deal_slug="thin",
        cells=[
            ReleasedCell(
                metric_key="revenue",
                fiscal_year=2024,
                status=ReleaseCellStatus.PROVEN,
                value=10.0,
                proof_level=ProofLevel.L2,
            )
        ],
    )
    a = assess_databook_contract(release, deal_slug="thin")
    assert a.draft_mode
    assert a.labels_incomplete >= 1
    assert any(r.startswith("labels_incomplete:") for r in a.reasons)
    assert a.label_gaps
    assert a.label_gaps[0].metric_key == "revenue"
    assert a.label_gaps[0].missing_fields


def test_exhibit_meta_token_match_rejects_pl_noise() -> None:
    assert _exhibit_meta_for_metric("cash_and_equivalents") is not None
    assert _exhibit_meta_for_metric("term_loan") is not None
    assert _exhibit_meta_for_metric("accounts_receivable") is not None
    assert _exhibit_meta_for_metric("deferred_revenue") is not None
    assert _exhibit_meta_for_metric("board_member_lease_expense") is None
    assert _exhibit_meta_for_metric("cash_register_maintenance") is None
    assert _exhibit_meta_for_metric("cash_flow") == (
        "ex_db_cf",
        "Cash flow (databook)",
        "SEC-I",
    )


def test_format_number_uses_decimal_display() -> None:
    assert _format_number(None) == "—"
    assert _format_number(1000.0) == "1,000"
    assert _format_number(1000.5) == "1,000.50"
    assert _format_number(10_000_000_000.05) == "10,000,000,000.05"


def test_scale_header_flags_mixed_units() -> None:
    facts = [
        FddFact(
            fact_id="a",
            metric_key="revenue",
            fiscal_year=2024,
            value=1.0,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(),
            currency="USD",
            scale="thousands",
        ),
        FddFact(
            fact_id="b",
            metric_key="cash",
            fiscal_year=2024,
            value=2.0,
            status=CellStatus.PROVEN,
            release_status=CellStatus.PROVEN,
            labels=EightLabels(),
            currency="EUR",
            scale="units",
        ),
    ]
    header = _scale_header_from_facts(facts, company="Acme")
    assert header is not None
    assert "Mixed Units" in header
    assert "USD" in header and "EUR" in header


def test_bridge_writes_facts_and_exhibits(deal_root: Path) -> None:
    slug = "bridge-deal"
    release = _save_release(
        slug,
        [
            _complete_cell(metric_key="revenue", value=3140.0),
            _complete_cell(metric_key="ebitda", value=620.0),
        ],
    )
    manifest = create_run(slug, databook_release_id=release.release_id, databook_release_version=1)
    manifest, facts, store, assessment = bridge_release_into_run(
        slug, manifest.run_id, release=release, company="Acme"
    )
    assert assessment.complete
    assert not manifest.draft_mode
    assert manifest.contract_complete
    assert not manifest.g6_blocked
    assert manifest.stage.value == "P1"
    assert len(facts.facts) == 2
    assert all(f.fact_id.startswith("db:") for f in facts.facts)
    assert all(not f.draft_flagged for f in facts.facts)
    assert any(e.exhibit_id == "ex_db_is" for e in store.exhibits)
    loaded = load_fact_table(slug, manifest.run_id)
    assert loaded is not None and len(loaded.facts) == 2


def test_bridge_draft_flags_every_figure_when_incomplete(deal_root: Path) -> None:
    slug = "draft-deal"
    release = DatabookRelease(
        release_id="rel_draft",
        version=1,
        created_at="2026-10-06T00:00:00Z",
        deal_slug=slug,
        cells=[
            ReleasedCell(
                metric_key="revenue",
                fiscal_year=2024,
                status=ReleaseCellStatus.PROVEN,
                value=50.0,
                proof_level=ProofLevel.L2,
                statement="IS",
            )
        ],
    )
    save_release(SlugDeal(id=slug, slug=slug), release, set_current=True)
    manifest = create_run(slug, databook_release_id=release.release_id)
    manifest, facts, store, assessment = bridge_release_into_run(
        slug, manifest.run_id, release=release
    )
    assert assessment.draft_mode
    assert manifest.draft_mode and manifest.g6_blocked
    assert all(f.draft_flagged for f in facts.facts)
    assert all(f.status == CellStatus.DRAFT for f in facts.facts)
    assert all(c.draft_flagged for e in store.exhibits for c in e.cells)
    with pytest.raises(GateBlockedError):
        assert_g6_allowed(manifest)
    assert not g6_allowed(manifest)


def test_release_pin_mismatch_refused(deal_root: Path) -> None:
    slug = "pin-deal"
    _save_release(slug, [_complete_cell()], release_id="rel_current", version=2)
    manifest = create_run(
        slug,
        databook_release_id="rel_old",
        databook_release_version=1,
        allow_pinned_release=False,
    )
    with pytest.raises(ReleasePinError, match="≠ current"):
        check_release_pin(manifest)
    # Intentional pin allowed when artefact is absent (no self-check possible)
    check_release_pin(
        manifest.model_copy(update={"allow_pinned_release": True})
    )


def test_release_pin_allow_still_checks_artefact_version(deal_root: Path) -> None:
    """allow_pinned_release skips current-match, not pin↔artefact consistency."""
    slug = "pin-ver"
    _save_release(slug, [_complete_cell()], release_id="rel_old", version=1)
    _save_release(slug, [_complete_cell()], release_id="rel_current", version=2)
    manifest = create_run(
        slug,
        databook_release_id="rel_old",
        databook_release_version=99,  # wrong for rel_old artefact
        allow_pinned_release=True,
    )
    with pytest.raises(ReleasePinError, match="≠ artefact"):
        check_release_pin(manifest)
    # Correct version for non-current release is allowed
    check_release_pin(
        manifest.model_copy(update={"databook_release_version": 1})
    )


def test_ensure_run_prefer_current_advances_stale_pin(deal_root: Path) -> None:
    """Report builders advance a stale pin instead of raising ReleasePinError."""
    slug = "pin-advance"
    _save_release(
        slug,
        [
            _complete_cell(metric_key="revenue", value=10.0),
            _complete_cell(metric_key="ebitda", value=2.0),
        ],
        release_id="v16",
        version=16,
    )
    create_run(
        slug,
        databook_release_id="v16",
        databook_release_version=16,
        allow_pinned_release=False,
    )
    _save_release(
        slug,
        [
            _complete_cell(metric_key="revenue", value=20.0),
            _complete_cell(metric_key="ebitda", value=4.0),
        ],
        release_id="v17",
        version=17,
    )
    # Default path still refuses stale pin
    with pytest.raises(ReleasePinError):
        ensure_phase0_run(slug, bridge_databook=True, prefer_current_release=False)
    # Report path advances to current
    manifest, _store, _spec = ensure_phase0_run(
        slug, bridge_databook=True, prefer_current_release=True
    )
    assert manifest.databook_release_id == "v17"
    assert manifest.databook_release_version == 17


def test_ensure_run_bridges_release(deal_root: Path) -> None:
    slug = "ensure-bridge"
    _save_release(
        slug,
        [
            _complete_cell(metric_key="revenue", value=99.0),
            _complete_cell(metric_key="ebitda", value=11.0),
        ],
    )
    manifest, store, spec = ensure_phase0_run(
        slug, company="Acme", force_new=True, bridge_databook=True
    )
    assert manifest.contract_complete
    assert not manifest.draft_mode
    assert any(e.exhibit_id.startswith("ex_db_") for e in store.exhibits)
    # Hand seed should not remain when facts cover its metrics (revenue)
    assert all(e.exhibit_id != "ex_hist_pl" for e in store.exhibits)
    assert spec.nodes
    again = load_manifest(slug, manifest.run_id)
    assert again is not None
    # ensure_phase0_run bridges (P1), claims (P2), commentary (P6), assemble (P7).
    assert again.stage.value in {"P1", "P2", "P6", "P7"}


def test_phase0_stub_kept_when_facts_do_not_cover_metrics(deal_root: Path) -> None:
    """Stub eviction is conditional — keep hand seed if revenue not in release."""
    from agetic_cdd_api.services_fdd_exhibit import (
        persist_store,
        seed_phase0_hand_built_exhibit,
    )
    from agetic_cdd_api.services_fdd_store import load_exhibit_store

    slug = "keep-stub"
    release = _save_release(
        slug,
        [_complete_cell(metric_key="ebitda", value=11.0)],  # no revenue
    )
    manifest = create_run(slug, databook_release_id=release.release_id)
    store = seed_phase0_hand_built_exhibit(
        load_exhibit_store(slug, manifest.run_id),  # type: ignore[arg-type]
        revenue_fy24=3140.0,
    )
    persist_store(slug, manifest.run_id, store)
    _manifest, _facts, store2, _a = bridge_release_into_run(
        slug, manifest.run_id, release=release, company="Acme Co"
    )
    assert any(e.exhibit_id == "ex_hist_pl" for e in store2.exhibits)
    assert any(e.exhibit_id.startswith("ex_db_") for e in store2.exhibits)
    # Scale header is company · currency/scale (release id only on standards/manifest)
    db_ex = next(e for e in store2.exhibits if e.exhibit_id.startswith("ex_db_"))
    assert db_ex.scale_header is not None
    assert "Acme Co" in db_ex.scale_header
    assert "databook release" not in (db_ex.scale_header or "")
    assert "INR" in (db_ex.scale_header or "") or "Cr" in (db_ex.scale_header or "")


def test_facts_preserve_release_status_under_draft() -> None:
    release = DatabookRelease(
        release_id="r",
        version=1,
        created_at="t",
        deal_slug="d",
        cells=[
            ReleasedCell(
                metric_key="revenue",
                fiscal_year=2024,
                status=ReleaseCellStatus.DOUBTFUL,
                value=None,
                statement="IS",
            )
        ],
    )
    facts = facts_from_release(release, draft_mode=True)
    assert facts[0].release_status == CellStatus.DOUBTFUL
    assert facts[0].status == CellStatus.DRAFT
    assert facts[0].draft_flagged
