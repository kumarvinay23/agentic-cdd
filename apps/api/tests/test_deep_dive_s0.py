"""Phase 3 Slice 0 — Deep Dive roles, findings store, phases API, SSE."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.deep_dive_findings import validate_findings_store
from agetic_cdd_api.pipeline_catalog import PHASE3_AGENT_KEYS


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


def _run_through_foundations(client: TestClient, headers: dict[str, str], deal_id: str) -> None:
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


def test_deep_dive_dag_valid() -> None:
    from agetic_cdd_api.deep_dive_roles import (
        DEEP_DIVE_ROLES,
        all_deep_dive_slugs,
        cascade_blast_radius,
        topo_order,
        validate_dag,
    )

    assert validate_dag() == []
    assert len(all_deep_dive_slugs()) == 24
    assert len(PHASE3_AGENT_KEYS) == 24
    assert set(PHASE3_AGENT_KEYS) == set(all_deep_dive_slugs())
    # Full Genovation codes (incl. letter suffixes) are unique; stems may collide.
    codes = [role.code for role in DEEP_DIVE_ROLES]
    assert len(codes) == len(set(codes))
    assert "DD-09" in codes and "DD-09b" in codes
    order = topo_order()
    assert order[0] in {"market_definition", "market_volume_and_growth", "competitor_identification"}
    assert order.index("market_volume_and_growth") < order.index("market_pricing")
    assert order.index("buying_behavior") < order.index("historical_performance")
    # DD-14 is Ops producer → finance consumers (no reverse edge / cycle).
    assert order.index("supply_chain_resilience") < order.index("revenue_quality")
    assert order.index("supply_chain_resilience") < order.index("capital_structure")
    blast = cascade_blast_radius("supply_chain_resilience")
    assert "revenue_quality" in blast
    assert "cash_flow" in blast
    assert "capital_structure" in blast


def test_validate_dag_detects_cycles() -> None:
    """len(topo_order()) alone must not mask cycles (regression for cycle fallback)."""
    from agetic_cdd_api import deep_dive_roles as ddr

    original = ddr.DEEP_DIVE_ROLES
    # Inject A→B→A among two existing slugs without mutating frozen roles globally:
    # temporarily patch depends_on_map via a synthetic cycle on copies.
    cyclic = tuple(
        ddr.DeepDiveRole(
            code=role.code,
            name=role.name,
            slug=role.slug,
            track=role.track,
            stage_key=role.stage_key,
            src=role.src,
            category=role.category,
            spec_output=role.spec_output,
            depends_on=(
                ("operational_risk",)
                if role.slug == "supply_chain_resilience"
                else (("supply_chain_resilience",) if role.slug == "operational_risk" else role.depends_on)
            ),
            foundation_deps=role.foundation_deps,
            primary_kinds=role.primary_kinds,
            filename_needles=role.filename_needles,
        )
        for role in original
    )
    try:
        ddr.DEEP_DIVE_ROLES = cyclic  # type: ignore[misc]
        errors = ddr.validate_dag()
        assert any("Cyclic dependency" in e for e in errors)
        # Cycle fallback still returns full length — old check would false-pass.
        assert len(ddr.topo_order()) == len(ddr.all_deep_dive_slugs())
    finally:
        ddr.DEEP_DIVE_ROLES = original  # type: ignore[misc]


def test_pipeline_phases_shape_and_src() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="Phases Shape", slug="phases-shape")
        res = client.get(f"/api/v1/portfolios/{deal_id}/pipeline/phases", headers=headers)
        assert res.status_code == 200
        data = res.json()["data"]
        assert len(data["phases"]) == 5
        deep = next(p for p in data["phases"] if p["phase_id"] == "deep_dive")
        assert deep["status"] == "available"
        assert len(deep["agentList"]) == 24
        market = next(a for a in deep["agentList"] if a["agent_key"] == "market_definition")
        assert market["src"] == "algo+web"
        assert market["status"] == "available"
        reports = next(p for p in data["phases"] if p["phase_id"] == "reports")
        assert reports["agentList"][0]["src"] == "report"


def test_findings_store_validation_and_critical_path() -> None:
    import json
    import copy

    from agetic_cdd_api.deep_dive_findings import (
        CRITICAL_PATH_SLUGS,
        build_findings_store,
        completeness_of,
        validate_findings_store,
    )

    class _Deal:
        id = "deal-1"
        name = "Acme"
        company = "Acme Co"

    store = build_findings_store(deal=_Deal(), generated_at="2026-01-01T00:00:00Z", agent_outputs={})  # type: ignore[arg-type]
    assert store["critical_path"]["slugs"] == list(CRITICAL_PATH_SLUGS)
    assert store["completeness"] == completeness_of(agents=store["agents"])
    assert validate_findings_store(store) == []
    assert store["completeness"]["critical_path_ready"] is False  # all missing

    # Stricter checks: bad status + slug drift.
    bad = copy.deepcopy(store)
    bad["agents"]["market_definition"]["status"] = "weird"
    bad["agents"]["buying_behavior"]["slug"] = "not_buying_behavior"
    bad["critical_path"]["slugs"] = list(CRITICAL_PATH_SLUGS)[:-1]
    errors = validate_findings_store(bad)
    assert any("invalid status" in e for e in errors)
    assert any("mismatched slug" in e for e in errors)
    assert any("CRITICAL_PATH_SLUGS" in e for e in errors)


def test_deep_dive_run_writes_findings_store() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="DD Store", slug="dd-store-s0")
        _run_through_foundations(client, headers, deal_id)

        run = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "deep_dive"},
        )
        assert run.status_code == 202

        pipe = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert pipe.status_code == 200
        deep = next(p for p in pipe.json()["data"]["phases"] if p["phase_id"] == "deep_dive")
        assert deep["status"] == "completed"
        assert deep["completedAgents"] == 24

        out = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/market_definition/output",
            headers=headers,
        )
        assert out.status_code == 200
        payload = out.json()["data"]["file_output"] or out.json()["data"]["output"]
        assert payload["slice"] in {
            "deep_dive_s0",
            "deep_dive_s1",
            "deep_dive_s2",
            "deep_dive_s3",
            "deep_dive_s4",
            "deep_dive_s5",
            "deep_dive_s6",
        }
        assert payload["stub"] is False
        if payload["agent_key"] in {
            "market_definition",
            "market_volume_and_growth",
            "market_pricing",
            "demand_drivers",
        }:
            assert payload["slice"] == "deep_dive_s1"

        from agetic_cdd_api.services_deals import ensure_deal_folder
        from pathlib import Path
        import json

        store_path = ensure_deal_folder("dd-store-s0") / "library" / "deep_dive_findings.json"
        assert store_path.is_file()
        store = json.loads(store_path.read_text(encoding="utf-8"))
        assert validate_findings_store(store) == []
        assert len(store["agents"]) == 24
        assert store["completeness"]["complete"] is True
        assert set(store["tracks"]) == {"A", "B", "C", "D", "E", "F"}


def test_deep_dive_events_stream_incrementally() -> None:
    """Progress events must be yielded as each node runs (no end-of-run buffer)."""
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Organization
    from agetic_cdd_api.services_deals import get_deal
    from agetic_cdd_api.services_deep_dive import iter_deep_dive_progress

    seen_started: list[str] = []
    seen_completed: list[str] = []
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="DD Stream", slug="dd-stream-s0")
        _run_through_foundations(client, headers, deal_id)

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            for event in iter_deep_dive_progress(
                db,
                deal=deal,
                agent_keys=["market_pricing"],
            ):
                etype = event.get("type")
                if etype == "agent_started":
                    seen_started.append(str(event.get("agent_key")))
                    if len(seen_started) > 1:
                        # Prior agent must have completed before the next start.
                        assert len(seen_completed) == len(seen_started) - 1
                elif etype in {"agent_completed", "agent_failed"}:
                    seen_completed.append(str(event.get("agent_key")))
                    assert seen_started[-1] == seen_completed[-1]
                elif etype == "result":
                    break
        finally:
            db.close()

    assert "market_pricing" in seen_started
    assert seen_started == seen_completed
    assert len(seen_started) >= 2
    # Cascade re-run: downstream blast (growth_opportunities) without re-running
    # market_volume when a prior completed artifact exists on disk.
    assert "growth_opportunities" in seen_started


def test_deep_dive_sse_smoke() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="DD SSE", slug="dd-sse-s0")
        _run_through_foundations(client, headers, deal_id)

        with client.stream(
            "POST",
            f"/api/v1/portfolios/{deal_id}/pipeline/phase/deep_dive/run",
            headers=headers,
            json={},
        ) as res:
            assert res.status_code == 200
            assert "text/event-stream" in res.headers.get("content-type", "")
            body = "".join(res.iter_text())
        assert "pipeline_started" in body
        assert "Profiling" in body and "fact base" in body
        assert "phase_started" in body
        assert "agent_started" in body
        assert "market_definition" in body
        assert "pipeline_completed" in body or "done" in body

        phases = client.get(f"/api/v1/portfolios/{deal_id}/pipeline/phases", headers=headers)
        deep = next(p for p in phases.json()["data"]["phases"] if p["phase_id"] == "deep_dive")
        assert deep["status"] == "completed"
        assert deep["completedAgents"] == 24


def test_store_entry_as_payload_preserves_structural_tags() -> None:
    from agetic_cdd_api.services_deep_dive import _store_entry_as_payload

    entry = {
        "status": "completed",
        "slug": "competitor_identification",
        "dd_code": "DD-04",
        "track": "B",
        "name": "Competitor Identification",
        "src": "algo+web",
        "slice": "deep_dive_s2",
        "summary": "ok",
        "findings": ["peer A"],
        "sources": ["11.pdf"],
        "spec": {"empty": False, "competitors": []},
        "empty_vdr": False,
    }
    payload = _store_entry_as_payload(entry)
    assert payload["dd_code"] == "DD-04"
    assert payload["track"] == "B"
    assert payload["agent_key"] == "competitor_identification"
    assert payload["agentName"] == "Competitor Identification"
    assert payload["slice"] == "deep_dive_s2"
    assert payload["spec"]["empty"] is False
    assert payload["sources"] == ["11.pdf"]


def test_deep_dive_isolates_agent_exceptions(monkeypatch) -> None:
    """Extractor crash on one node must fail that node and continue the DAG."""
    from agetic_cdd_api.db import SessionLocal
    from agetic_cdd_api.models import Organization
    from agetic_cdd_api.services_deals import get_deal
    from agetic_cdd_api import services_deep_dive as sdd

    def boom(*_args, **_kwargs):
        raise RuntimeError("extractor blew up")

    monkeypatch.setattr(sdd, "_build_agent_output", boom)

    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="DD Fault", slug="dd-fault-s0")
        _run_through_foundations(client, headers, deal_id)

        db = SessionLocal()
        try:
            org = db.query(Organization).first()
            assert org is not None
            deal = get_deal(db, org_id=org.id, deal_id=deal_id)
            events = list(
                sdd.iter_deep_dive_progress(
                    db,
                    deal=deal,
                    agent_keys=["market_definition", "competitor_identification"],
                )
            )
        finally:
            db.close()

    failed = [e for e in events if e.get("type") == "agent_failed"]
    completed_or_failed = [e for e in events if e.get("type") in {"agent_completed", "agent_failed"}]
    result = next(e for e in events if e.get("type") == "result")
    assert len(failed) >= 1
    assert len(completed_or_failed) >= 2  # both nodes still emitted
    outs = result.get("result") or {}
    assert outs["market_definition"]["status"] == "failed"
    assert outs["competitor_identification"]["status"] == "failed"
    assert "extractor blew up" in (outs["market_definition"].get("error") or "")


def test_text_cache_lru_evicts_oldest_when_over_cap() -> None:
    from collections import OrderedDict

    from agetic_cdd_api.services_deep_dive import (
        _CACHE_TOTAL_CHAR_LIMIT,
        _cache_get,
        _cache_put,
    )

    cache: OrderedDict[str, str] = OrderedDict()
    unit = "x" * 400_000
    _cache_put(cache, "01_a.pdf", unit)
    _cache_put(cache, "02_b.pdf", unit)
    _cache_put(cache, "03_c.pdf", unit)
    _cache_put(cache, "04_d.pdf", unit)
    assert "01_a.pdf" not in cache
    assert "04_d.pdf" in cache
    assert sum(len(v) for v in cache.values()) <= _CACHE_TOTAL_CHAR_LIMIT


def test_text_cache_touch_keeps_hot_document() -> None:
    from collections import OrderedDict

    from agetic_cdd_api.services_deep_dive import _cache_get, _cache_put

    cache: OrderedDict[str, str] = OrderedDict()
    unit = "x" * 450_000
    _cache_put(cache, "01_a.pdf", unit)
    _cache_put(cache, "02_b.pdf", unit)
    _cache_get(cache, "01_a.pdf")
    _cache_put(cache, "03_c.pdf", unit)
    assert "01_a.pdf" in cache
    assert "02_b.pdf" not in cache


def test_foundation_snippets_use_normalized_prefix() -> None:
    from agetic_cdd_api.services_deep_dive import _foundation_snippets

    store = {
        "roles": {
            "F-04": {"summary": "Regulatory exposure in two states requires monitoring."},
        }
    }
    lines = _foundation_snippets(store, ("F-04",))
    assert len(lines) == 1
    assert lines[0].startswith("Foundation · F-04:")

