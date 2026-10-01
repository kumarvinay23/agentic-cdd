"""Deal dashboard + VDR tests."""

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


def test_dashboard_and_vdr_upload() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "VDR Deal", "slug": "vdr-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]

        dash = client.get(f"/api/v1/deal-rooms/{deal_id}/dashboard", headers=headers)
        assert dash.status_code == 200
        body = dash.json()["data"]
        assert body["dealRoom"]["name"] == "VDR Deal"
        assert body["workflowCompletion"]["totalAgents"] == total_agent_count()
        assert len(body["workflowRoadmap"]) == 5

        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("CIM.pdf", BytesIO(b"%PDF-1.4 test"), "application/pdf")},
        )
        assert upload.status_code == 200
        assert upload.json()["data"]["deal"]["docs_count"] == 1
        assert upload.json()["data"]["deal"]["status"] == "active"

        listed = client.get(f"/api/v1/portfolios/{deal_id}/cdd/vdr", headers=headers)
        assert listed.status_code == 200
        assert "CIM.pdf" in listed.json()["vdr"]

        downloaded = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/files/CIM.pdf",
            headers=headers,
        )
        assert downloaded.status_code == 200
        assert downloaded.content.startswith(b"%PDF-1.4")
        missing = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/files/missing.pdf",
            headers=headers,
        )
        assert missing.status_code == 404
        traversed = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/files/..%2F..%2Fsecrets.json",
            headers=headers,
        )
        # Single-segment route → 404; sanitized basename → 400. Either rejects traversal.
        assert traversed.status_code in {400, 404}

        health = client.get(f"/api/v1/portfolios/{deal_id}/cdd/health", headers=headers)
        assert health.status_code == 200
        assert health.json()["vdr_files"] == 1

        traversed = client.delete(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/..%2F..%2Fsecrets.json",
            headers=headers,
        )
        assert traversed.status_code in {400, 404}

        deleted = client.delete(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/CIM.pdf",
            headers=headers,
        )
        assert deleted.status_code == 200
        assert deleted.json()["data"]["deal"]["docs_count"] == 0
