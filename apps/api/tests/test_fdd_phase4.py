"""FDD Phase 4 — evidence retrieval from claim gaps (P3 → release → P2)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agetic_cdd_api import services_databook_store as store_mod
from agetic_cdd_api import services_deals as deals_mod
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
from agetic_cdd_api.services_fdd_claims import build_claims_ledger
from agetic_cdd_api.services_fdd_evidence import (
    list_claim_gaps,
    patch_request_status,
    reconcile_requests_after_claims,
    run_p3_evidence_pass,
)
from agetic_cdd_api.services_fdd_store import (
    create_run,
    load_claims_ledger,
    load_evidence_pass,
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


def test_list_claim_gaps_and_dry_run(deal_root: Path) -> None:
    slug = "p4-gaps"
    _write_hp_output(slug, deal_root, revenue=9999.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_p4a",
        version=1,
        created_at="2026-10-09T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[_complete_cell(metric_key="revenue", value=3140.0)],
        counts={"proven": 1},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_p4a", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)
    build_claims_ledger(slug, m.run_id, open_requests=True)

    gaps = list_claim_gaps(slug, m.run_id, ensure_claims=False)
    assert gaps
    assert any(g.test_result == "contradicted" for g in gaps)
    assert any("Audited_FS.pdf" in g.suggested_filenames for g in gaps)

    dry = run_p3_evidence_pass(slug, m.run_id, deal=deal, mode="rescan", dry_run=True)
    assert dry.dry_run is True
    assert len(dry.gaps_before) == len(gaps)
    assert dry.release_id_before == "rel_p4a"
    # Dry run must not advance stage off P2 claims.
    man = load_manifest(slug, m.run_id)
    assert man is not None
    assert man.stage.value == "P2"


def test_evidence_pass_closes_gap_via_new_release(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "p4-close"
    claimed = 9999.0
    _write_hp_output(slug, deal_root, revenue=claimed)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_p4b_v1",
        version=1,
        created_at="2026-10-09T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[
            _complete_cell(metric_key="revenue", value=3140.0),
            _complete_cell(metric_key="ebitda", value=690.0),
        ],
        counts={"proven": 2},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_p4b_v1", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)
    ledger0 = build_claims_ledger(slug, m.run_id, open_requests=True)
    assert ledger0.contradicted >= 1
    req0 = load_request_list(slug, m.run_id)
    assert req0 is not None and any(i.status == "pending" for i in req0.items)

    def _fake_rescan(d: object) -> SimpleNamespace:
        fixed = DatabookRelease(
            release_id="rel_p4b_v2",
            version=2,
            created_at="2026-10-09T01:00:00Z",
            deal_slug=slug,
            source="rescan",
            cells=[
                _complete_cell(metric_key="revenue", value=claimed),
                _complete_cell(metric_key="ebitda", value=690.0),
            ],
            counts={"proven": 2},
        )
        save_release(SlugDeal(id=slug, slug=slug), fixed, set_current=True)
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_evidence.rescan_databook", _fake_rescan
    )

    result = run_p3_evidence_pass(
        slug,
        m.run_id,
        deal=deal,
        mode="rescan",
        rebridge=True,
        rebuild_claims=True,
    )
    assert result.dry_run is False
    assert result.release_id_after == "rel_p4b_v2"
    assert result.claims_rebuilt is True
    assert len(result.gaps_after) < len(result.gaps_before)
    assert result.requests_received

    ledger1 = load_claims_ledger(slug, m.run_id)
    assert ledger1 is not None
    rev = [
        c
        for c in ledger1.claims
        if c.kind == "financial" and c.metric_key == "revenue"
    ]
    assert rev and rev[0].test_result == "agrees"

    man = load_manifest(slug, m.run_id)
    assert man is not None
    assert man.stage.value == "P2"  # re-entered P2 after P3
    assert man.model_versions.get("fdd_phase4")

    persisted = load_evidence_pass(slug, m.run_id)
    assert persisted is not None
    assert persisted.release_id_after == "rel_p4b_v2"


def test_rebridge_only_and_patch_request(deal_root: Path) -> None:
    slug = "p4-rebridge"
    _write_hp_output(slug, deal_root, revenue=3140.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_p4c",
        version=1,
        created_at="2026-10-09T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[
            _complete_cell(metric_key="revenue", value=3140.0),
            _complete_cell(metric_key="ebitda", value=690.0),
        ],
        counts={"proven": 2},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_p4c", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)
    build_claims_ledger(slug, m.run_id, open_requests=True)

    # Force a pending request then waive via API helper.
    req = load_request_list(slug, m.run_id)
    if req and req.items:
        rid = req.items[0].request_id
        item = patch_request_status(slug, m.run_id, rid, status="waived")
        assert item.status == "waived"

    result = run_p3_evidence_pass(
        slug, m.run_id, deal=deal, mode="rebridge", rebuild_claims=True
    )
    assert result.mode == "rebridge"
    assert result.claims_rebuilt is True
    man = load_manifest(slug, m.run_id)
    assert man is not None and man.stage.value == "P2"


def test_reconcile_marks_received_by_metric_year(deal_root: Path) -> None:
    slug = "p4-reconcile"
    _write_hp_output(slug, deal_root, revenue=3140.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_p4d",
        version=1,
        created_at="2026-10-09T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[
            _complete_cell(metric_key="revenue", value=3140.0),
            _complete_cell(metric_key="ebitda", value=690.0),
        ],
        counts={"proven": 2},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_p4d", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)
    # Start contradicted then fix agent to match so reconcile can fire.
    _write_hp_output(slug, deal_root, revenue=9999.0)
    ledger_bad = build_claims_ledger(slug, m.run_id, open_requests=True)
    assert ledger_bad.contradicted >= 1
    _write_hp_output(slug, deal_root, revenue=3140.0)
    ledger_ok = build_claims_ledger(slug, m.run_id, open_requests=True)
    received = reconcile_requests_after_claims(slug, m.run_id, ledger=ledger_ok)
    assert received
    req = load_request_list(slug, m.run_id)
    assert req is not None
    assert any(i.status == "received" for i in req.items)


def test_job_failure_does_not_stamp_p3_or_rebridge(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slug = "p4-fail"
    _write_hp_output(slug, deal_root, revenue=9999.0)
    deal = SlugDeal(id=slug, slug=slug)
    release = DatabookRelease(
        release_id="rel_p4e",
        version=1,
        created_at="2026-10-09T00:00:00Z",
        deal_slug=slug,
        source="manual",
        cells=[_complete_cell(metric_key="revenue", value=3140.0)],
        counts={"proven": 1},
    )
    save_release(deal, release, set_current=True)
    m = create_run(slug, databook_release_id="rel_p4e", databook_release_version=1)
    bridge_release_into_run(slug, m.run_id, release=release)
    build_claims_ledger(slug, m.run_id, open_requests=True)
    man0 = load_manifest(slug, m.run_id)
    assert man0 is not None and man0.stage.value == "P2"

    def _boom(_d: object) -> None:
        raise RuntimeError("library extract failed")

    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_evidence.rescan_databook", _boom
    )

    result = run_p3_evidence_pass(
        slug, m.run_id, deal=deal, mode="rescan", rebridge=True, rebuild_claims=True
    )
    assert result.claims_rebuilt is False
    assert any("short_circuit_stale_release" in n for n in result.notes)
    assert any("databook_job_error" in n for n in result.notes)
    man1 = load_manifest(slug, m.run_id)
    assert man1 is not None
    assert man1.stage.value == "P2"  # never left stuck on P3
    assert man1.model_versions.get("fdd_phase4")  # attempt still recorded


def test_reread_continues_after_per_file_failure(
    deal_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from agetic_cdd_api.services_fdd_evidence import _run_databook_job

    slug = "p4-reread"
    deal = SlugDeal(id=slug, slug=slug)
    calls: list[str] = []

    def _reread(_db: object, _deal: object, filename: str) -> SimpleNamespace:
        calls.append(filename)
        if filename == "bad.pdf":
            raise RuntimeError("corrupt")
        return SimpleNamespace(ok=True, file=filename)

    monkeypatch.setattr(
        "agetic_cdd_api.services_fdd_evidence.reread_databook_document", _reread
    )
    out = _run_databook_job(
        deal=deal,
        db=object(),
        mode="reread",
        filenames=["bad.pdf", "good.pdf"],
    )
    assert calls == ["bad.pdf", "good.pdf"]
    assert out is not None
    assert getattr(out, "file", None) == "good.pdf"
    assert getattr(out, "_reread_errors", None)


def test_reconcile_normalizes_metric_case(deal_root: Path) -> None:
    from agetic_cdd_api.fdd_schemas import (
        ClaimsLedgerDoc,
        ClaimsLedgerEntry,
        RequestListDoc,
        RequestListItem,
    )
    from agetic_cdd_api.services_fdd_store import save_claims_ledger, save_request_list

    slug = "p4-norm"
    (deal_root / slug).mkdir(parents=True)
    m = create_run(slug)
    save_claims_ledger(
        ClaimsLedgerDoc(
            run_id=m.run_id,
            deal_slug=slug,
            updated_at="t",
            claims=[
                ClaimsLedgerEntry(
                    claim_id="cl_x",
                    text="Revenue FY2024",
                    kind="financial",
                    metric_key="Revenue",
                    fiscal_year=2024,
                    claimed_value=1.0,
                    test_result="agrees",
                )
            ],
        )
    )
    save_request_list(
        RequestListDoc(
            run_id=m.run_id,
            deal_slug=slug,
            updated_at="t",
            items=[
                RequestListItem(
                    request_id="req_1",
                    title="gap",
                    metric_key="revenue",
                    fiscal_year=2024,
                    status="pending",
                )
            ],
        )
    )
    received = reconcile_requests_after_claims(slug, m.run_id)
    assert received == ["req_1"]
