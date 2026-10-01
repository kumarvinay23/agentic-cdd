from pathlib import Path

from agetic_cdd import __version__
from agetic_cdd.app import app
from agetic_cdd.data import create_deal, portfolio_payload, slugify
from fastapi.testclient import TestClient


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_slugify() -> None:
    assert slugify("Growth Equity Fund IV") == "growth-equity-fund-iv"


def test_portfolio_payload_has_dynamic_active_deals() -> None:
    payload = portfolio_payload()
    assert payload["brand"] == "Agentic CDD"
    expected_active = sum(1 for deal in payload["deals"] if deal["status"] == "ACTIVE")
    assert payload["metrics"]["active_deals"] == expected_active


def test_dashboard_renders() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Portfolio dashboard" in response.text
    assert "Create investment portfolio" in response.text
    assert "Create Dealroom" in response.text


def test_create_deal_creates_folder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd.data.DATA_DIR", tmp_path)
    monkeypatch.setattr("agetic_cdd.data.STORE_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr("agetic_cdd.data.DEALS_DIR", tmp_path / "deals")
    monkeypatch.setattr("agetic_cdd.data.PROJECT_ROOT", tmp_path)

    result = create_deal(
        name="Growth Equity Fund IV",
        description="Primary growth equity portfolio",
        tags=["Tech", "Late-Stage"],
        industry="Technology",
    )

    deal = result["deal"]
    assert deal["slug"] == "growth-equity-fund-iv"
    assert deal["status"] == "NOT-STARTED"
    folder = tmp_path / "deals" / "growth-equity-fund-iv"
    assert folder.is_dir()
    assert (folder / "documents").is_dir()
    assert (folder / "reports").is_dir()
    assert (folder / "deal.json").is_file()
    assert result["portfolio"]["metrics"]["active_deals"] == sum(
        1 for item in result["portfolio"]["deals"] if item["status"] == "ACTIVE"
    )


def test_create_deal_api(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd.data.DATA_DIR", tmp_path)
    monkeypatch.setattr("agetic_cdd.data.STORE_PATH", tmp_path / "portfolio.json")
    monkeypatch.setattr("agetic_cdd.data.DEALS_DIR", tmp_path / "deals")
    monkeypatch.setattr("agetic_cdd.data.PROJECT_ROOT", tmp_path)

    client = TestClient(app)
    response = client.post(
        "/api/deals",
        json={
            "name": "UI Modal Deal",
            "description": "Created from API",
            "tags": "Tech, Software",
            "industry": "Technology",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["deal"]["name"] == "UI Modal Deal"
    assert body["folder"] == "deals/ui-modal-deal"
    assert (tmp_path / "deals" / "ui-modal-deal").is_dir()
    assert body["portfolio"]["metrics"]["active_deals"] == sum(
        1 for deal in body["portfolio"]["deals"] if deal["status"] == "ACTIVE"
    )