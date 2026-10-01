"""Auth API tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app


def test_seed_admin_login() -> None:
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@ageticcdd.com", "password": "adminpass"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["success"] is True
        data = body["data"]
        assert data["user"]["email"] == "admin@ageticcdd.com"
        assert data["organization"]["name"]
        assert data["tokens"]["accessToken"]
        assert data["tokens"]["refreshToken"]
        assert "deals.read" in data["permissions"]


def test_login_invalid() -> None:
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@ageticcdd.com", "password": "wrong"},
        )
        assert res.status_code == 401


def test_register_me_logout_refresh() -> None:
    with TestClient(app) as client:
        res = client.post(
            "/api/v1/auth/register",
            json={
                "email": "analyst@example.com",
                "password": "password123",
                "firstName": "Alex",
                "lastName": "Analyst",
                "organizationName": "Example Capital",
            },
        )
        assert res.status_code == 200
        tokens = res.json()["data"]["tokens"]
        headers = {"Authorization": f"Bearer {tokens['accessToken']}"}

        me = client.get("/api/v1/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["data"]["user"]["email"] == "analyst@example.com"

        org = client.get("/api/v1/organizations", headers=headers)
        assert org.status_code == 200
        assert org.json()["data"]["slug"]

        refreshed = client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": tokens["refreshToken"]},
        )
        assert refreshed.status_code == 200
        new_tokens = refreshed.json()["data"]["tokens"]

        out = client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {new_tokens['accessToken']}"},
            json={"refreshToken": new_tokens["refreshToken"]},
        )
        assert out.status_code == 200


def test_refresh_reuse_revokes_family() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@ageticcdd.com", "password": "adminpass"},
        )
        assert login.status_code == 200
        old_refresh = login.json()["data"]["tokens"]["refreshToken"]

        rotated = client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": old_refresh},
        )
        assert rotated.status_code == 200
        new_refresh = rotated.json()["data"]["tokens"]["refreshToken"]

        reuse = client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": old_refresh},
        )
        assert reuse.status_code == 401
        assert "reuse" in reuse.json()["detail"].lower()

        # Child of the rotated family is also revoked after reuse detection.
        follow = client.post(
            "/api/v1/auth/refresh",
            json={"refreshToken": new_refresh},
        )
        assert follow.status_code == 401
