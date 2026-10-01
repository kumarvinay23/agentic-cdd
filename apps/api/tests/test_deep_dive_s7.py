"""Slice 7 — smart cascade re-run for Phase 3 Deep Dive."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_cascade import (
    _get_all_missing_upstream,
    _output_available,
    build_output_manifest,
    cascade_run_order,
    frozen_upstream_slugs,
    plan_cascade_rerun,
)
from agetic_cdd_api.services_pipeline import read_agent_output_file


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
        json={"name": "Cascade Slice7", "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={
            "file": (
                "CIM.pdf",
                BytesIO(
                    b"%PDF-1.4 market sizing TAM SAM supply chain MRR revenue churn financial P&L"
                ),
                "application/pdf",
            )
        },
    )
    assert upload.status_code == 200
    return deal_id


def _run_through_deep_dive(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    for phase in ("data_ingestion", "foundations", "deep_dive"):
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": phase},
        ).status_code == 202


def test_cascade_run_order_supply_chain_financials() -> None:
    order = cascade_run_order(["supply_chain_resilience"])
    assert order[0] == "supply_chain_resilience"
    assert "revenue_quality" in order
    assert "cash_flow" in order
    assert "capital_structure" in order
    assert order.index("revenue_quality") < order.index("cash_flow")
    assert "buying_behavior" not in order


def test_cascade_blast_includes_growth_opportunities_from_pricing() -> None:
    order = cascade_run_order(["market_pricing"])
    assert order == ["market_pricing", "growth_opportunities"]


def test_frozen_upstream_excludes_rerun_set() -> None:
    order = cascade_run_order(["supply_chain_resilience"])
    frozen = frozen_upstream_slugs(order)
    assert "buying_behavior" in frozen
    assert "supply_chain_resilience" not in frozen


def test_schedule_cascade_returns_blast_metadata() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, slug="cascade-meta-s7")
        _run_through_deep_dive(client, headers, deal_id)

        scheduled = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"agent_key": "supply_chain_resilience"},
        )
        assert scheduled.status_code == 202
        cascade = scheduled.json()["data"]["cascade"]
        assert cascade["trigger"] == ["supply_chain_resilience"]
        assert "revenue_quality" in cascade["blast_radius"]
        assert "supply_chain_resilience" in cascade["agent_keys"]


def test_cascade_rerun_updates_downstream_preserves_upstream() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, slug="cascade-rerun-s7")
        _run_through_deep_dive(client, headers, deal_id)

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Organization
        from agetic_cdd_api.services_deals import get_deal

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            buying_before = read_agent_output_file(deal, agent_key="buying_behavior")
            rev_before = read_agent_output_file(deal, agent_key="revenue_quality")
            assert buying_before and rev_before
            buying_ts = buying_before["generated_at"]
            rev_ts = rev_before["generated_at"]
        finally:
            db.close()

        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"agent_key": "supply_chain_resilience"},
        ).status_code == 202

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            buying_after = read_agent_output_file(deal, agent_key="buying_behavior")
            rev_after = read_agent_output_file(deal, agent_key="revenue_quality")
            sc_after = read_agent_output_file(deal, agent_key="supply_chain_resilience")
            assert buying_after["generated_at"] == buying_ts
            assert rev_after["generated_at"] != rev_ts
            assert sc_after.get("cascade", {}).get("orchestrator") == "deep_dive_s7"
            assert rev_after.get("cascade", {}).get("trigger") == "supply_chain_resilience"
        finally:
            db.close()


def test_plan_adds_missing_upstream_when_outputs_absent() -> None:
    class _Deal:
        slug = "missing-upstream-s7"
        id = "x"

    plan = plan_cascade_rerun(_Deal(), ["market_pricing"])  # type: ignore[arg-type]
    assert "market_volume_and_growth" in plan["missing_upstream"]
    assert "market_volume_and_growth" in plan["agent_keys"]


def test_failed_upstream_is_not_valid_for_hydration() -> None:
    manifest = {"buying_behavior": {"status": "failed", "generated_at": "t0"}}
    assert _output_available(manifest, "buying_behavior") is False


def test_transitive_missing_upstream_chain() -> None:
    """Missing Node B promotes its missing upstream Node A into the batch."""
    core = set(cascade_run_order(["revenue_quality"]))
    missing = _get_all_missing_upstream(core, {})
    assert "buying_behavior" in missing
    assert "supply_chain_resilience" in missing
    assert "market_share_strategy" in missing


def test_failed_upstream_promoted_on_cascade_plan() -> None:
    class _Deal:
        slug = "failed-upstream-s7"
        id = "x"

    manifest = build_output_manifest(_Deal())  # type: ignore[arg-type]
    manifest["buying_behavior"] = {"status": "failed"}
    manifest["supply_chain_resilience"] = {"status": "completed", "generated_at": "t1"}

    missing = _get_all_missing_upstream(set(cascade_run_order(["revenue_quality"])), manifest)
    assert "buying_behavior" in missing
    assert "market_share_strategy" in missing
    assert "supply_chain_resilience" not in missing
