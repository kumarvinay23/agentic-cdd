"""W4 pipeline skeleton tests."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.pipeline_catalog import total_agent_count


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
        files={"file": ("CIM.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")},
    )
    assert upload.status_code == 200
    return deal_id


def test_pipeline_get_and_cascade() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="Pipe Deal", slug="pipe-deal")

        listed = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert listed.status_code == 200
        body = listed.json()["data"]
        assert body["totalAgents"] == total_agent_count()
        assert body["completedAgents"] == 0
        assert body["next_phase_id"] == "data_ingestion"
        assert len(body["phases"]) == 5

        blocked = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        )
        assert blocked.status_code == 409

        phase1 = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert phase1.status_code == 202

        after = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        data = after.json()["data"]
        assert data["phases"][0]["status"] == "completed"
        assert data["next_phase_id"] == "foundations"

        output = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/deal_context_and_objectives/output",
            headers=headers,
        )
        assert output.status_code == 200
        assert output.json()["data"]["status"] == "completed"
        assert output.json()["data"]["output"]["stub"] is False
        assert output.json()["data"]["output"]["document_count"] >= 1

        foundations = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        )
        assert foundations.status_code == 202
        after2 = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert after2.json()["data"]["phases"][1]["status"] == "completed"

        agent_out = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/company_background/output",
            headers=headers,
        )
        assert agent_out.status_code == 200
        assert agent_out.json()["data"]["output"]["stub"] is False
        assert agent_out.json()["data"]["file_output"]["agent_key"] == "company_background"

        usage = client.get("/api/v1/me/usage", headers=headers)
        assert usage.status_code == 200
        assert usage.json()["data"]["agent_runs"] >= 8


def test_pipeline_run_next_phase_and_unknown_agent() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="Next Phase Deal", slug="next-phase-deal")

        missing = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/not_a_real_agent/output",
            headers=headers,
        )
        assert missing.status_code == 404

        first = client.post(f"/api/v1/portfolios/{deal_id}/pipeline/run", headers=headers, json={})
        assert first.status_code == 202
        assert first.json()["data"]["phase_id"] == "data_ingestion"

        second = client.post(f"/api/v1/portfolios/{deal_id}/pipeline/run", headers=headers, json={})
        assert second.status_code == 202
        assert second.json()["data"]["phase_id"] == "foundations"


def test_deep_dive_requires_foundation_context() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal_with_doc(client, headers, name="S4 Context Deal", slug="s4-context-deal")

        blocked = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "deep_dive"},
        )
        assert blocked.status_code == 409

        phase1 = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert phase1.status_code == 202
        foundations = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        )
        assert foundations.status_code == 202

        from pathlib import Path
        from agetic_cdd_api.services_deals import ensure_deal_folder

        context = ensure_deal_folder("s4-context-deal") / "library" / "foundation_context.json"
        assert context.is_file()
        context.unlink()

        missing_store = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "deep_dive"},
        )
        assert missing_store.status_code == 409
        detail = missing_store.json()["detail"]
        assert detail["error"] == "foundation_context_incomplete"

        # Restore by re-running Foundations, then Deep Dive is allowed.
        rerun = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        )
        assert rerun.status_code == 202
        allowed = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "deep_dive"},
        )
        assert allowed.status_code == 202
        assert allowed.json()["data"]["phase_id"] == "deep_dive"
