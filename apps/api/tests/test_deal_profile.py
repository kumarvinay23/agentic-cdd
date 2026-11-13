"""A deal profile is read from that deal's documents and confirmed before agents run."""

from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_deal_profile import confirm_profile, publish_databook, refresh_profile, require_confirmed_profile


def test_profiles_stay_on_their_own_deals(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    uk = SimpleNamespace(slug="uk-saas", id="uk")
    india = SimpleNamespace(slug="in-organics", id="in")
    (tmp_path / "uk-saas" / "documents").mkdir(parents=True)
    (tmp_path / "in-organics" / "documents").mkdir(parents=True)
    (tmp_path / "uk-saas" / "documents" / "CIM.txt").write_text(
        "Country: United Kingdom\nCurrency: GBP\nSector: software\n"
        "Business model: subscription\nDeal type: buyout\n"
        "The buyer will acquire Northwind Ltd.\n",
        encoding="utf-8",
    )
    (tmp_path / "in-organics" / "documents" / "CIM.txt").write_text(
        "Country: India\nCurrency: INR\nSector: compost\n"
        "Business model: net lease\nDeal type: minority growth\n"
        "Target is Baytown Travel Pvt Ltd.\n",
        encoding="utf-8",
    )

    uk_detected = refresh_profile(uk)
    in_detected = refresh_profile(india)
    assert uk_detected["confirmed"] is False
    assert uk_detected["fields"]["country"]["value"] == "United Kingdom"
    assert uk_detected["fields"]["currency"]["value"] == "GBP"
    assert uk_detected["fields"]["sector"]["value"] == "saas"
    assert uk_detected["fields"]["deal_type"]["value"] == "buyout"
    assert "Northwind Ltd" in uk_detected["fields"]["legal_entities"]["value"]

    confirmed = confirm_profile(uk, {})
    assert confirmed["confirmed"] is True
    assert confirmed["pack"]["tax_terms"] == "VAT"
    assert confirmed["pack"]["number_format"] == "#,##0.00"
    assert confirmed["pack"]["sector_pack"] == "saas"
    assert confirmed["pack"]["valuation_framing"].startswith("Control")

    again = refresh_profile(uk)
    other = refresh_profile(india)
    assert again["fields"]["currency"]["value"] == "GBP"
    assert again["confirmed"] is True
    assert other["fields"]["country"]["value"] == "India"
    assert other["fields"]["currency"]["value"] == "INR"
    assert other["fields"]["sector"]["value"] == "waste_organics"
    assert other["fields"]["business_model"]["value"] == "net_lease"
    assert other["fields"]["deal_type"]["value"] == "minority_growth"
    assert other["confirmed"] is False
    assert "Baytown Travel Pvt Ltd" in other["fields"]["legal_entities"]["value"]


def test_unconfirmed_profile_blocks_agents(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    deal = SimpleNamespace(slug="open-deal", id="open")
    (tmp_path / "open-deal" / "documents").mkdir(parents=True)
    (tmp_path / "open-deal" / "documents" / "note.txt").write_text(
        "Country: Germany\nCurrency: EUR\nDeal type: recapitalisation\n",
        encoding="utf-8",
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as caught:
        require_confirmed_profile(deal)
    assert caught.value.status_code == 409
    confirm_profile(deal, {"deal_type": "recapitalisation"})
    profile = require_confirmed_profile(deal)
    assert profile["confirmed"] is True
    assert profile["pack"]["tax_terms"] == "VAT"
    assert profile["pack"]["key_terms"] == ["new debt", "dividend recap", "equity rollover"]


@pytest.mark.profile_gate
def test_pipeline_waits_for_confirmation() -> None:
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"email": "admin@ageticcdd.com", "password": "adminpass"},
        )
        headers = {"Authorization": f"Bearer {login.json()['data']['tokens']['accessToken']}"}
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Profile Gate", "slug": f"profile-gate-{uuid4().hex[:8]}", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={"file": ("CIM.txt", BytesIO(b"Country: Canada\nCurrency: USD\nSector: logistics\n"), "text/plain")},
        )
        assert upload.status_code == 200

        blocked = client.post(f"/api/v1/portfolios/{deal_id}/pipeline/run", headers=headers, json={})
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["error"] == "confirm_deal_profile"

        confirmed = client.post(
            f"/api/v1/portfolios/{deal_id}/profile/confirm",
            headers=headers,
            json={"country": "Canada", "currency": "USD", "sector": "logistics", "deal_type": "buyout"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["data"]["confirmed"] is True
        assert confirmed.json()["data"]["pack"]["tax_terms"] == "sales tax"

        started = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert started.status_code == 202


_POLICY = {
    "include_other_operating_income": False,
    "rent_basis": "CASH",
    "bad_debt_in_ebitda": True,
}


def test_unconfirmed_profile_cannot_publish_and_currencies_stay_apart(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("agetic_cdd_api.services_deals.deals_root", lambda: tmp_path)
    _clear_step4()
    from fastapi import HTTPException

    open_deal = SimpleNamespace(slug="open-book", id="step4-open")
    (tmp_path / "open-book" / "documents").mkdir(parents=True)
    with pytest.raises(HTTPException) as blocked:
        publish_databook(open_deal)
    assert blocked.value.status_code == 409

    usd = SimpleNamespace(slug="usd-book", id="step4-usd")
    eur = SimpleNamespace(slug="eur-book", id="step4-eur")
    for slug in ("usd-book", "eur-book"):
        (tmp_path / slug / "documents").mkdir(parents=True)
    confirm_profile(usd, {"currency": "USD"})
    with pytest.raises(HTTPException) as incomplete:
        publish_databook(usd)
    assert incomplete.value.status_code == 409

    confirm_profile(
        usd,
        {
            "currency": "USD",
            "fiscal_year_end": "12-31",
            "latest_actual_month": "2025-12",
            "sector_pack": "payments",
            "ebitda_policy": _POLICY,
        },
    )
    confirm_profile(
        eur,
        {
            "currency": "EUR",
            "fiscal_year_end": "03-31",
            "latest_actual_month": "2025-09-30",
            "sector_pack": "healthcare_clinic",
            "ebitda_policy": {**_POLICY, "rent_basis": "GAAP"},
        },
    )
    assert publish_databook(usd)["databook"]["reporting_currency"] == "USD"
    assert publish_databook(eur)["databook"]["reporting_currency"] == "EUR"

    from agetic_cdd_api.services_fact_repository import get_fact, save_fact

    usd_fact = save_fact(_currency_fact("fact-step4-usd", "step4-usd", "2025-12-31"))
    eur_fact = save_fact(_currency_fact("fact-step4-eur", "step4-eur", "2025-09-30"))
    assert get_fact(usd_fact)["currency"] == "USD"
    assert get_fact(eur_fact)["currency"] == "EUR"


def _clear_step4() -> None:
    import os

    url = os.environ.get("AGETIC_CDD_DATABOOK_DATABASE_URL", "").strip()
    if not url:
        return
    from agetic_cdd_api.services_databook_migrate import psql

    psql(
        url,
        "DELETE FROM fact WHERE deal_id IN ('step4-usd', 'step4-eur'); "
        "DELETE FROM deal WHERE deal_id IN ('step4-usd', 'step4-eur');",
    )


def _currency_fact(fact_id: str, deal_id: str, period_end: str) -> dict:
    return {
        "fact_id": fact_id,
        "deal_id": deal_id,
        "concept_id": "fin.pl.revenue_gross",
        "value": 10,
        "unit_type": "CURRENCY",
        "period_type": "FY",
        "period_start": "2025-01-01",
        "period_end": period_end,
        "months_covered": 12,
        "fiscal_year": 2025,
        "basis": "ACTUAL",
        "status": "SELECTED",
        "evidence_tier": "A",
        "source_location_ids": [f"loc-{deal_id}"],
    }
