"""Phase 4 Slice 0 — Final Verdict roles, verdict store, pipeline gate, run stub."""

from __future__ import annotations

import copy
import json
from io import BytesIO
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.pipeline_catalog import PHASE4_AGENT_KEYS
from agetic_cdd_api.verdict_store import (
    assert_verdict_context,
    build_verdict_store,
    completeness_of,
    validate_verdict_store,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal_with_doc(client: TestClient, headers: dict[str, str], *, name: str, slug: str) -> str:
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": name, "slug": slug, "industry": "generic"},
    )
    deal_id = created.json()["data"]["id"]
    upload = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={"file": ("CIM.pdf", BytesIO(b"%PDF-1.4 market sizing TAM SAM"), "application/pdf")},
    )
    assert upload.status_code == 200
    return deal_id


def _run_through_deep_dive(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
    assert client.post(
        f"/api/v1/portfolios/{deal_id}/pipeline/run",
        headers=headers,
        json={"phase_id": "data_ingestion"},
    ).status_code == 202
    assert client.post(
        f"/api/v1/portfolios/{deal_id}/pipeline/run",
        headers=headers,
        json={"phase_id": "foundations"},
    ).status_code == 202
    assert client.post(
        f"/api/v1/portfolios/{deal_id}/pipeline/run",
        headers=headers,
        json={"phase_id": "deep_dive"},
    ).status_code == 202


def test_verdict_dag_valid() -> None:
    from agetic_cdd_api.verdict_roles import (
        VERDICT_ROLES,
        _SLUG_MAP,
        all_verdict_slugs,
        cascade_blast_radius,
        role_by_slug,
        topo_order,
        validate_dag,
    )

    assert validate_dag() == []
    assert len(all_verdict_slugs()) == 7
    assert len(PHASE4_AGENT_KEYS) == 7
    assert set(PHASE4_AGENT_KEYS) == set(all_verdict_slugs())
    assert role_by_slug("not-a-slug") is None
    assert len(_SLUG_MAP) == len(VERDICT_ROLES)
    codes = [role.code for role in VERDICT_ROLES]
    assert codes == [f"FV-{i:02d}" for i in range(1, 8)]

    order = topo_order()
    assert order.index("compensation_alignment") < order.index("precedent_transactions")
    assert order.index("trading_comps") < order.index("valuation_modeling")
    assert order.index("precedent_transactions") < order.index("valuation_modeling")
    assert order.index("valuation_modeling") < order.index("ic_synthesis")
    assert order.index("ic_synthesis") < order.index("recommendation")
    assert order[0] in {"execution_risk", "compensation_alignment", "trading_comps"}

    blast = cascade_blast_radius("valuation_modeling")
    assert "ic_synthesis" in blast
    assert "recommendation" in blast


def test_validate_dag_detects_cycles() -> None:
    from agetic_cdd_api import verdict_roles as vr

    original = vr.VERDICT_ROLES
    cyclic = tuple(
        vr.VerdictRole(
            code=role.code,
            name=role.name,
            slug=role.slug,
            stage=role.stage,
            stage_key=role.stage_key,
            spec_output=role.spec_output,
            depends_on=(
                ("ic_synthesis",)
                if role.slug == "recommendation"
                else (("recommendation",) if role.slug == "ic_synthesis" else role.depends_on)
            ),
            foundation_deps=role.foundation_deps,
            deep_dive_deps=role.deep_dive_deps,
            vdr_ref=role.vdr_ref,
            filename_needles=role.filename_needles,
        )
        for role in original
    )
    try:
        vr.VERDICT_ROLES = cyclic  # type: ignore[misc]
        errors = vr.validate_dag()
        assert any("Cyclic dependency" in e for e in errors)
        assert len(vr.topo_order()) == len(vr.all_verdict_slugs())
    finally:
        vr.VERDICT_ROLES = original  # type: ignore[misc]


def test_verdict_store_validation() -> None:
    class _Deal:
        id = "deal-1"
        name = "Acme"
        company = "Acme Co"

    store = build_verdict_store(deal=_Deal(), generated_at="2026-01-01T00:00:00Z", agent_outputs={})  # type: ignore[arg-type]
    assert store["completeness"] == completeness_of(agents=store["agents"])
    assert validate_verdict_store(store) == []
    assert store["completeness"]["complete"] is False
    assert store["completeness"]["structurally_valid"] is True
    assert set(store["stages"]) == {"A", "B", "C"}

    incomplete_store = completeness_of(store={"deal_id": "x"})
    assert incomplete_store["structurally_valid"] is False
    assert incomplete_store["complete"] is False
    assert len(incomplete_store["missing_agents"]) == 7

    bad = copy.deepcopy(store)
    bad["agents"]["execution_risk"]["status"] = "weird"
    bad["agents"]["compensation_alignment"]["slug"] = "not_comp"
    bad["stages"].pop("B")
    errors = validate_verdict_store(bad)
    assert any("invalid status" in e for e in errors)
    assert any("mismatched slug" in e for e in errors)
    assert any("stages missing bucket 'B'" in e for e in errors)


def test_verdict_store_atomic_write_and_load_validation() -> None:
    from types import SimpleNamespace

    from agetic_cdd_api.verdict_store import load_verdict_store, store_path, write_verdict_store

    class _Deal:
        id = "deal-atomic"
        name = "Atomic"
        company = "Atomic Co"
        slug = "atomic-verdict"

    deal = _Deal()
    store = build_verdict_store(deal=deal, generated_at="2026-01-01T00:00:00Z", agent_outputs={})  # type: ignore[arg-type]
    # Mark one agent completed so we can verify round-trip integrity.
    store["agents"]["execution_risk"]["status"] = "completed"
    store["completeness"] = completeness_of(agents=store["agents"])

    path = write_verdict_store(deal, store)  # type: ignore[arg-type]
    assert path == store_path(deal)  # type: ignore[arg-type]
    loaded = load_verdict_store(deal)  # type: ignore[arg-type]
    assert loaded is not None
    assert loaded["agents"]["execution_risk"]["status"] == "completed"

    path.write_text("{not-json", encoding="utf-8")
    assert load_verdict_store(deal) is None  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="contract violation"):
        write_verdict_store(deal, {"deal_id": "bad"})  # type: ignore[arg-type]


def test_assert_verdict_context_409_without_findings() -> None:
    deal = SimpleNamespace(id="d1", slug="fv-missing-findings")
    with pytest.raises(HTTPException) as exc:
        assert_verdict_context(deal)
    assert exc.value.status_code == 409
    detail = exc.value.detail
    assert detail["error"] == "deep_dive_findings_missing"


def test_final_verdict_run_writes_verdict_store() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="FV Store", slug="fv-store-s0")
        _run_through_deep_dive(client, headers, deal_id)

        run = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "final_verdict"},
        )
        assert run.status_code == 202

        pipe = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert pipe.status_code == 200
        verdict = next(p for p in pipe.json()["data"]["phases"] if p["phase_id"] == "final_verdict")
        assert verdict["status"] == "completed"
        assert verdict["completedAgents"] == 7

        out = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/recommendation/output",
            headers=headers,
        )
        assert out.status_code == 200
        payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
        assert payload["slice"] == "final_verdict_s3"
        assert payload["stub"] is False
        assert payload["fv_code"] == "FV-07"
        assert payload["stage"] == "C"

        from agetic_cdd_api.services_deals import ensure_deal_folder

        store_path = ensure_deal_folder("fv-store-s0") / "library" / "verdict_store.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        assert validate_verdict_store(store) == []
        assert len(store["agents"]) == 7
        assert store["completeness"]["complete"] is True
        assert store["completeness"]["stage_ready"] == {"A": True, "B": True, "C": True}


def test_final_verdict_gate_409_before_deep_dive() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="FV Gate", slug="fv-gate-s0")
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        ).status_code == 202
        assert client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        ).status_code == 202

        blocked = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "final_verdict"},
        )
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        if isinstance(detail, dict):
            assert detail["error"] in {
                "deep_dive_findings_missing",
                "deep_dive_findings_incomplete",
            }
        else:
            assert "Deep Dive" in str(detail)


def test_pipeline_phases_final_verdict_shape() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="FV Phases", slug="fv-phases-s0")
        res = client.get(f"/api/v1/portfolios/{deal_id}/pipeline/phases", headers=headers)
        assert res.status_code == 200
        verdict = next(p for p in res.json()["data"]["phases"] if p["phase_id"] == "final_verdict")
        assert len(verdict["agentList"]) == 7
        assert verdict["agentList"][0]["agent_key"] == "execution_risk"
        assert verdict["agentList"][-1]["agent_key"] == "recommendation"


def test_partial_rerun_hydrates_upstream_context(monkeypatch) -> None:
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Organization
    from agetic_cdd_api.services_deals import get_deal
    from agetic_cdd_api import services_final_verdict as sfv

    upstream_summary = "Comp alignment upstream context for partial rerun test."
    monkeypatch.setattr(
        sfv,
        "read_agent_output_file",
        lambda deal, agent_key: (
            {
                "agent_key": "compensation_alignment",
                "summary": upstream_summary,
                "status": "completed",
            }
            if agent_key == "compensation_alignment"
            else None
        ),
    )
    monkeypatch.setattr(sfv, "load_foundation_context", lambda deal, db=None: {})
    monkeypatch.setattr(sfv, "load_deep_dive_findings", lambda deal, db=None: {})
    monkeypatch.setattr(sfv, "_write_store", lambda *args, **kwargs: {"completeness": {"present_agents": []}})

    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="FV Partial", slug="fv-partial-s0")
        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            events = list(
                sfv.iter_final_verdict_progress(
                    db,
                    deal=deal,
                    agent_keys=["precedent_transactions"],
                )
            )
        finally:
            db.close()

    result = next(e for e in events if e.get("type") == "result")
    payload = (result.get("result") or {})["precedent_transactions"]
    assert any(upstream_summary in bit for bit in payload.get("findings") or [])


def test_iter_final_verdict_events_single_lifecycle_source() -> None:
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Organization
    from agetic_cdd_api.services_deals import get_deal
    from agetic_cdd_api import services_final_verdict as sfv

    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="FV SSE Life", slug="fv-sse-life-s0")
        _run_through_deep_dive(client, headers, deal_id)

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            events = list(
                sfv.iter_final_verdict_events(db, deal=deal, agent_keys=["execution_risk"])
            )
            types = [e.get("type") for e in events]
            log_messages = [str(e.get("message") or "") for e in events if e.get("type") == "log"]
        finally:
            db.close()

    assert types.count("pipeline_started") == 1
    assert types.count("phase_started") == 1
    assert types.count("phase_completed") == 1
    assert not any(msg == "Phase: Final Verdict started" for msg in log_messages)
    assert any("Synthesizing" in msg for msg in log_messages)
