"""Phase 1 document analyze tests."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_upload_analyze_classifies_documents() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Analyze Deal", "slug": "analyze-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]

        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("05_Financial_Due_Diligence.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        assert upload.status_code == 200
        doc = upload.json()["data"]["vdr"][0]
        assert doc["status"] == "uploaded"
        assert doc["format"] == "pdf"

        analyze = client.post(f"/api/v1/portfolios/{deal_id}/cdd/analyze", headers=headers)
        assert analyze.status_code == 202
        assert analyze.json()["data"]["queued"] is True

        listed = client.get(f"/api/v1/portfolios/{deal_id}/cdd/vdr", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
        assert body["data"][0]["status"] == "ready"
        assert body["data"][0]["category"] == "Financial"
        assert body["ingestion"]["completed"] is True

        ingestion = client.get(f"/api/v1/portfolios/{deal_id}/cdd/ingestion", headers=headers)
        assert ingestion.status_code == 200
        assert ingestion.json()["data"]["ready_count"] == 1

        dash = client.get(f"/api/v1/deal-rooms/{deal_id}/dashboard", headers=headers)
        assert dash.status_code == 200
        phase1 = dash.json()["data"]["workflowRoadmap"][0]
        completed = [a for a in phase1["agents"] if a["status"] == "completed"]
        assert len(completed) == 0
        assert phase1["status"] == "pending"

        pipeline = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert pipeline.json()["data"]["next_phase_id"] == "data_ingestion"


def test_analyze_requires_documents() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Empty Deal", "slug": "empty-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        analyze = client.post(f"/api/v1/portfolios/{deal_id}/cdd/analyze", headers=headers)
        assert analyze.status_code == 400
