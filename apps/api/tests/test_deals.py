"""Deal portfolio API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app


def _auth_headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    assert res.status_code == 200
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_create_list_usage() -> None:
    with TestClient(app) as client:
        headers = _auth_headers(client)

        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "name": "Ather Energy",
                "slug": "ather-energy-w2",
                "description": "EV deal",
                "tags": "ev,india",
                "industry": "ev",
            },
        )
        assert created.status_code == 201
        deal = created.json()["data"]
        assert deal["slug"].startswith("ather-energy")
        assert deal["sector"] == "ev"
        assert deal["status"] == "not-started"

        bad_slug = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Bad", "slug": "Not Valid!"},
        )
        assert bad_slug.status_code == 422

        listed = client.get("/api/v1/deals?limit=10&offset=0", headers=headers)
        assert listed.status_code == 200
        body = listed.json()
        assert any(d["id"] == deal["id"] for d in body["data"])
        assert body["metrics"]["total_deals"] >= 1
        assert body["pagination"]["limit"] == 10
        assert body["pagination"]["total"] == body["metrics"]["total_deals"]

        usage = client.get("/api/v1/me/usage", headers=headers)
        assert usage.status_code == 200
        assert "vdr_files" in usage.json()["data"]

        sectors = client.get("/api/v1/portfolios/cdd/sectors", headers=headers)
        assert sectors.status_code == 200
        assert any(s["id"] == "generic" for s in sectors.json())

        detail = client.get(f"/api/v1/deals/{deal['id']}", headers=headers)
        assert detail.status_code == 200
        assert detail.json()["data"]["name"] == "Ather Energy"
