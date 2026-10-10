"""FDD Phase 3 — claims ledger, databook tests, agent exhibit ban."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.fdd_schemas import (
    CellStatus,
    ExhibitCell,
    EvidenceTier,
    FigureType,
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
from agetic_cdd_api.services_fdd_bridge import bridge_release_into_run
from agetic_cdd_api.services_fdd_claims import (
    AgentExhibitFigureError,
    assert_fact_id_not_agent_sourced,
    build_claims_ledger,
    index_facts,
    evaluate_financial_claim,
    values_agree,
    _claim_id,
)
from agetic_cdd_api.fdd_schemas import ClaimsLedgerEntry, FddFact
from agetic_cdd_api.services_fdd_exhibit import upsert_cell
from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_claims_ledger,
    load_manifest,
    load_request_list,
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


def _write_hp_output(slug: str, deal_root: Path, *, revenue: float = 3140.0) -> None:
    out = deal_root / slug / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "historical_performance.json").write_text(
        json.dumps(
            {
                "agent_key": "historical_performance",
                "summary": "Historical trading shows stable revenue growth over the period.",
                "sources": ["Audited_FS.pdf#p1"],
                "spec": {
                    "pl_lines": [
                        {
                            "line_item": "Revenue",
                            "metric_key": "revenue",
                            "fy2024_value": revenue,
                            "unit": "INR Cr",
                        },
                        {
                            "line_item": "EBITDA",
                            "metric_key": "ebitda",
                            "fy2024_value": 690.0,
                            "unit": "INR Cr",
                        },
                    ],
                    "performance_metrics": {
                        "revenue_fy2024_inr_cr": revenue,
                    },
                    "insight_snapshot": (
                        "Margin expansion remains the primary diligence lead for QoE."
                    ),
                },
            }
        ),
        encoding="utf-8",
    )


def test_values_agree_tolerance() -> None:
    assert values_agree(100.0, 100.4)
    assert not values_agree(100.0, 110.0)
    # Small EBITDA gaps must contradict (was swallowed by 0.05 abs floor).
    assert not values_agree(0.572, 0.565)
    assert not values_agree(7.558, 7.528)


def test_claim_id_is_uuid_hex() -> None:
    cid = _claim_id("historical_performance", "revenue", 2024, "fin")
    assert cid.startswith("cl_")
    assert len(cid) == 15  # cl_ + 12 hex chars
    assert _claim_id("a", "b", 1, "fin") != _claim_id("a", "b", 1, "fin")


def test_strict_year_match_no_cross_year_fallback() -> None:
    claim = ClaimsLedgerEntry(
        claim_id="cl_test",
        source_agent="historical_performance",
        text="Revenue FY2024",
        kind="financial",
        metric_key="revenue",
        fiscal_year=2024,
        claimed_value=100.0,
    )
    facts_idx = index_facts(
        [
            FddFact(
                fact_id="db:rel:r1",
                metric_key="revenue",
                fiscal_year=2022,
                value=100.0,
                status=CellStatus.PROVEN,
                release_status=CellStatus.PROVEN,
            )
        ]
    )
    result = evaluate_financial_claim(claim, facts_idx)
    assert result.test_result == "unverifiable"
    assert result.failed


def test_agent_fact_id_rejected() -> None:
    with pytest.raises(AgentExhibitFigureError):
        assert_fact_id_not_agent_sourced("agent:historical_performance:revenue")
    assert_fact_id_not_agent_sourced("db:rel_v1:r_revenue_2024")
    assert_fact_id_not_agent_sourced("hand:revenue:2024")


def test_upsert_rejects_agent_fact_id(deal_root: Path) -> None:
    store = ExhibitStoreDoc(run_id="r", deal_slug="d", updated_at="t", exhibits=[])
    cell = ExhibitCell(
        cell_id="revenue_fy24",
        exhibit_id="ex_x",
        label="Revenue",
        value=1.0,
        fact_id="agent:hp:revenue",
        figure_type=FigureType.REPORTED,
        evidence_tier=EvidenceTier.C,
        status=CellStatus.DRAFT,
    )
    with pytest.raises(AgentExhibitFigureError):
        upsert_cell(store, cell, exhibit_title="X")


def test_claims_agree_with_release(deal_root: Path) -> None:
    slug = "claims-agree"
    _write_hp_output(slug, deal_root, revenue=3140.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_c1",
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
    m = create_run(slug, databook_release_id="rel_c1", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)

    ledger = build_claims_ledger(slug, m.run_id)
    assert ledger.financial_count >= 2
    assert ledger.agrees >= 2
    assert "historical_performance" not in ledger.unreliable_modules
    fin = [c for c in ledger.claims if c.kind == "financial" and c.metric_key == "revenue"]
    assert fin and fin[0].test_result == "agrees"
    # qualitative with sources → narrative_ok
    quals = [c for c in ledger.claims if c.kind == "qualitative"]
    assert quals
    assert any(c.narrative_ok for c in quals)

    loaded = load_claims_ledger(slug, m.run_id)
    assert loaded is not None and loaded.claim_count == ledger.claim_count
    manifest = load_manifest(slug, m.run_id)
    assert manifest is not None
    assert manifest.claims_built
    assert manifest.stage.value == "P2"


def test_claims_rebuild_does_not_duplicate_requests(deal_root: Path) -> None:
    slug = "claims-dedupe"
    _write_hp_output(slug, deal_root, revenue=9999.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_c3",
        version=1,
        created_at="2026-10-07T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[_complete_cell(metric_key="revenue", value=3140.0)],
        counts={"proven": 1},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_c3", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)

    build_claims_ledger(slug, m.run_id, open_requests=True)
    req1 = load_request_list(slug, m.run_id)
    assert req1 is not None
    n1 = len(req1.items)

    build_claims_ledger(slug, m.run_id, open_requests=True)
    req2 = load_request_list(slug, m.run_id)
    assert req2 is not None
    assert len(req2.items) == n1


def test_claims_contradicted_opens_request(deal_root: Path) -> None:
    slug = "claims-contra"
    _write_hp_output(slug, deal_root, revenue=9999.0)  # agent disagrees
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_c2",
        version=1,
        created_at="2026-10-07T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[_complete_cell(metric_key="revenue", value=3140.0)],
        counts={"proven": 1},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_c2", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)

    ledger = build_claims_ledger(slug, m.run_id, open_requests=True)
    assert ledger.contradicted >= 1
    req = load_request_list(slug, m.run_id)
    assert req is not None
    assert any("contradicted" in (i.title or "") for i in req.items)


def test_claims_unverifiable_without_facts(deal_root: Path) -> None:
    slug = "claims-miss"
    _write_hp_output(slug, deal_root, revenue=100.0)
    m = create_run(slug)
    ledger = build_claims_ledger(slug, m.run_id)
    assert ledger.unverifiable >= 1
    # High fail rate → unreliable module
    assert "historical_performance" in ledger.unreliable_modules
