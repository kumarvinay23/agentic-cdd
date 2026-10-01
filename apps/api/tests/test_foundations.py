"""Phase 2 Foundations agents read the Central Data Library."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.pipeline_catalog import PHASE2_AGENT_KEYS
from agetic_cdd_api.services_deals import ensure_deal_folder


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_foundations_reads_cdl_sources() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Foundations Deal", "slug": "foundations-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]
        files = [
            (
                "02_Corporate_Overview.txt",
                b"Ola Electric Mobility Limited is headquartered in Bengaluru. Founded in 2017 by Bhavish Aggarwal.",
            ),
            (
                "03_Investment_Thesis.txt",
                b"The investment thesis is vertical integration of EV two-wheelers. TAM for India 2W is USD 24 billion.",
            ),
            (
                "06_Legal_Due_Diligence.txt",
                b"SEBI LODR compliance is current. GST filings are complete. ESG labour audits are underway.",
            ),
            (
                "08_Technical_Due_Diligence.txt",
                b"MoveOS is a Linux-based vehicle OS. Battery IP and OTA updates are core technology assets.",
            ),
            (
                "10_HR_Organizational_Due_Diligence.txt",
                b"CEO Bhavish Aggarwal is founder. CFO tenure since 2021. Succession risk is high for the CEO.",
            ),
        ]
        for name, body in files:
            upload = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (name, BytesIO(body), "text/plain")},
            )
            assert upload.status_code == 200

        phase1 = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert phase1.status_code == 202
        phase2 = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "foundations"},
        )
        assert phase2.status_code == 202

        background = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/company_background/output",
            headers=headers,
        )
        body = background.json()["data"]["output"]
        assert body["stub"] is False
        assert "02_Corporate_Overview.txt" in body["sources"]
        assert "Ola Electric" in body["target_company"] or "Ola Electric" in body["summary"]

        tech = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/ip_and_technology/output",
            headers=headers,
        )
        tech_body = tech.json()["data"]["output"]
        assert tech_body["stub"] is False
        assert "08_Technical_Due_Diligence.txt" in tech_body["sources"]

        for key in PHASE2_AGENT_KEYS:
            res = client.get(
                f"/api/v1/portfolios/{deal_id}/pipeline/agents/{key}/output",
                headers=headers,
            )
            assert res.status_code == 200
            assert res.json()["data"]["output"]["stub"] is False

        assert background.json()["data"]["output"]["foundation_role"] == "F-05"
        assert background.json()["data"]["output"]["depends_on"] == []
        mq = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/management_quality/output",
            headers=headers,
        )
        assert mq.json()["data"]["output"]["depends_on"] == ["F-05"]
        assert mq.json()["data"]["output"]["foundation_role"] == "F-06"

        thesis = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/strategic_direction/output",
            headers=headers,
        )
        thesis_spec = thesis.json()["data"]["output"]["spec"]
        assert thesis_spec["role_code"] == "F-01"
        assert 1 <= thesis_spec["attractiveness_score"] <= 10
        assert len(thesis_spec["investment_drivers"]) == 3
        mq_spec = mq.json()["data"]["output"]["spec"]
        assert mq_spec["role_code"] == "F-06"
        assert mq_spec["consumes_f05"] is True

        store = json.loads(
            (ensure_deal_folder("foundations-deal") / "library" / "foundation_context.json").read_text(
                encoding="utf-8"
            )
        )
        assert store["run_order"] == ["F-01", "F-02", "F-03", "F-04", "F-IP", "F-ESG", "F-05", "F-06"]
        assert store["substages"]["A"] == ["F-01", "F-02", "F-03", "F-04", "F-IP", "F-ESG"]
        assert store["substages"]["B"] == ["F-05", "F-06"]
        assert store["roles"]["F-02"]["slug"] is None
        assert store["roles"]["F-03"]["slug"] is None
        assert store["roles"]["F-06"]["depends_on"] == ["F-05"]
        assert store["target"]
        assert store["substage_a"] == store["substages"]["A"]
        assert store["substage_b"] == store["substages"]["B"]
        assert store["completeness"]["required_roles"] == ["F-01", "F-02", "F-03", "F-04", "F-05", "F-06"]
        assert store["completeness"]["complete"] is True
        assert "F-01" in store["agents_by_role"]

        roles_dir = Path(ensure_deal_folder("foundations-deal") / "library" / "foundation_roles")
        for code in store["run_order"]:
            assert (roles_dir / f"{code}.json").is_file()


def test_s2_skips_f06_when_f05_fails(monkeypatch) -> None:
    from types import SimpleNamespace

    from agetic_cdd_api import services_foundations as sf

    deal = SimpleNamespace(id="d-s2", name="Skip Deal", company="SkipCo", slug="s2-skip-f06")
    index = {
        "documents": [
            {"filename": "Overview.txt", "name": "Overview.txt", "doc_kind": "company"},
        ]
    }
    monkeypatch.setattr(sf, "load_library_index", lambda _deal: index)

    def fake_agent(_deal, *, agent_key: str, index: dict, prior: dict | None = None) -> dict:
        failed = agent_key == "company_background"
        return {
            "stub": False,
            "status": "failed" if failed else "completed",
            "agent_key": agent_key,
            "summary": "f05 failed" if failed else "ok",
            "findings": [],
            "sources": [],
            "foundation_role": "F-05" if agent_key == "company_background" else "F-06",
        }

    monkeypatch.setattr(sf, "_agent_output", fake_agent)
    outputs = sf.run_foundations(None, deal=deal, agent_keys=["company_background", "management_quality"])
    assert outputs["company_background"]["status"] == "failed"
    assert outputs["management_quality"]["status"] == "failed"
    assert outputs["management_quality"]["depends_on"] == ["F-05"]
    assert "F-05" in (outputs["management_quality"].get("error") or "")
