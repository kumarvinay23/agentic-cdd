"""Slice 4 — smart cascade re-run for Phase 4 Final Verdict."""

from __future__ import annotations

import uuid
from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_pipeline import read_agent_output_file
from agetic_cdd_api.verdict_cascade import (
    _get_all_missing_upstream,
    _output_available,
    build_output_manifest,
    cascade_run_order,
    frozen_upstream_slugs,
    plan_cascade_rerun,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal_with_doc(client: TestClient, headers: dict[str, str], *, slug: str) -> str:
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": "FV Cascade S4", "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={
            "file": (
                "CIM.pdf",
                BytesIO(b"%PDF-1.4 market sizing TAM SAM"),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 200
    return deal_id


def _run_through_final_verdict(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    for phase in ("data_ingestion", "foundations", "deep_dive", "final_verdict"):
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": phase},
        ).status_code == 202


def test_cascade_run_order_valuation_modeling() -> None:
    order = cascade_run_order(["valuation_modeling"])
    assert order[0] == "valuation_modeling"
    assert "ic_synthesis" in order
    assert "recommendation" in order
    assert order.index("ic_synthesis") < order.index("recommendation")
    assert "trading_comps" not in order
    assert "execution_risk" not in order


def test_cascade_blast_from_trading_comps() -> None:
    order = cascade_run_order(["trading_comps"])
    assert order[0] == "trading_comps"
    assert "valuation_modeling" in order
    assert "ic_synthesis" in order
    assert "recommendation" in order
    assert "precedent_transactions" not in order


def test_cascade_blast_from_compensation_alignment() -> None:
    order = cascade_run_order(["compensation_alignment"])
    assert order[0] == "compensation_alignment"
    assert "precedent_transactions" in order
    assert "valuation_modeling" in order
    assert "ic_synthesis" in order
    assert "recommendation" in order


def test_cascade_blast_from_ic_synthesis() -> None:
    order = cascade_run_order(["ic_synthesis"])
    assert order == ["ic_synthesis", "recommendation"]


def test_frozen_upstream_excludes_rerun_set() -> None:
    order = cascade_run_order(["valuation_modeling"])
    frozen = frozen_upstream_slugs(order)
    assert "trading_comps" in frozen
    assert "precedent_transactions" in frozen
    assert "valuation_modeling" not in frozen
    assert "ic_synthesis" not in frozen


def test_schedule_cascade_returns_blast_metadata() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"fv-cascade-meta-{uuid.uuid4().hex[:8]}"
        deal_id = _create_deal_with_doc(client, headers, slug=slug)
        _run_through_final_verdict(client, headers, deal_id)

        scheduled = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"agent_key": "valuation_modeling"},
        )
        assert scheduled.status_code == 202
        cascade = scheduled.json()["data"]["cascade"]
        assert cascade["trigger"] == ["valuation_modeling"]
        assert "ic_synthesis" in cascade["blast_radius"]
        assert "recommendation" in cascade["blast_radius"]
        assert "valuation_modeling" in cascade["agent_keys"]
        assert "trading_comps" not in cascade["agent_keys"]


def test_cascade_rerun_updates_downstream_preserves_upstream() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"fv-cascade-rerun-{uuid.uuid4().hex[:8]}"
        deal_id = _create_deal_with_doc(client, headers, slug=slug)
        _run_through_final_verdict(client, headers, deal_id)

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Organization
        from agetic_cdd_api.services_deals import get_deal

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            comps_before = read_agent_output_file(deal, agent_key="trading_comps")
            ic_before = read_agent_output_file(deal, agent_key="ic_synthesis")
            assert comps_before and ic_before
            comps_ts = comps_before["generated_at"]
            ic_ts = ic_before["generated_at"]
        finally:
            db.close()

        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"agent_key": "valuation_modeling"},
        ).status_code == 202

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            comps_after = read_agent_output_file(deal, agent_key="trading_comps")
            ic_after = read_agent_output_file(deal, agent_key="ic_synthesis")
            vm_after = read_agent_output_file(deal, agent_key="valuation_modeling")
            assert comps_after["generated_at"] == comps_ts
            assert ic_after["generated_at"] != ic_ts
            assert vm_after.get("cascade", {}).get("orchestrator") == "final_verdict_s4"
            assert ic_after.get("cascade", {}).get("trigger") == "valuation_modeling"
            assert ic_after.get("cascade", {}).get("reason") == "blast_radius"
        finally:
            db.close()


def test_plan_adds_missing_upstream_when_outputs_absent() -> None:
    class _Deal:
        slug = "missing-upstream-fv-s4"
        id = "x"

    plan = plan_cascade_rerun(_Deal(), ["valuation_modeling"])  # type: ignore[arg-type]
    assert "trading_comps" in plan["missing_upstream"]
    assert "precedent_transactions" in plan["missing_upstream"]
    assert "trading_comps" in plan["agent_keys"]
    assert "precedent_transactions" in plan["agent_keys"]


def test_failed_upstream_is_not_valid_for_hydration() -> None:
    manifest = {"trading_comps": {"status": "failed", "generated_at": "t0"}}
    assert _output_available(manifest, "trading_comps") is False


def test_manifest_prefers_valid_store_over_invalid_disk(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from agetic_cdd_api import verdict_cascade as vc

    deal = SimpleNamespace(slug="manifest-prefer-store", id="d1")
    out_dir = tmp_path / "outputs"
    out_dir.mkdir()
    (out_dir / "trading_comps.json").write_text(
        '{"status": "failed", "summary": "partial abort"}',
        encoding="utf-8",
    )

    monkeypatch.setattr(vc, "outputs_dir", lambda _deal: out_dir)
    monkeypatch.setattr(vc, "read_agent_output_file", lambda *_a, **_k: None)
    monkeypatch.setattr(
        vc,
        "load_verdict_store",
        lambda _deal: {
            "agents": {
                "trading_comps": {
                    "status": "completed",
                    "fv_code": "FV-03",
                    "slug": "trading_comps",
                    "spec": {"empty": False},
                }
            }
        },
    )

    manifest = build_output_manifest(deal)  # type: ignore[arg-type]
    assert manifest["trading_comps"]["status"] == "completed"
    assert manifest["trading_comps"]["fv_code"] == "FV-03"


def test_transitive_missing_upstream_chain() -> None:
    """Missing valuation_modeling deps promote compensation_alignment via precedents."""
    core = set(cascade_run_order(["valuation_modeling"]))
    missing = _get_all_missing_upstream(core, {})
    assert "trading_comps" in missing
    assert "precedent_transactions" in missing
    assert "compensation_alignment" in missing


def test_failed_upstream_promoted_on_cascade_plan() -> None:
    class _Deal:
        slug = "failed-upstream-fv-s4"
        id = "x"

    manifest = build_output_manifest(_Deal())  # type: ignore[arg-type]
    manifest["trading_comps"] = {"status": "failed"}
    manifest["precedent_transactions"] = {"status": "completed", "generated_at": "t1"}
    manifest["compensation_alignment"] = {"status": "completed", "generated_at": "t0"}

    missing = _get_all_missing_upstream(set(cascade_run_order(["valuation_modeling"])), manifest)
    assert "trading_comps" in missing
    assert "precedent_transactions" not in missing
    assert "compensation_alignment" not in missing
