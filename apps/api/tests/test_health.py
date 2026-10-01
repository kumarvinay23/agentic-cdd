from fastapi.testclient import TestClient

from agetic_cdd_api.app import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is True
        assert body["product"] == "Agentic CDD"
        assert body["wave"] == "W5"
