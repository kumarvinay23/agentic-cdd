"""S5 golden store contract, Ola fixtures, and Test5 VDR integration."""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.foundation_context import validate_foundation_store
from agetic_cdd_api.foundation_extractors import extract_role_spec
from agetic_cdd_api.services_deals import ensure_deal_folder

FIXTURES = Path(__file__).parent / "fixtures" / "s5_ola"
TEST5_DOCS = Path(__file__).resolve().parents[1] / "data" / "deals" / "test5" / "documents"
GOLDEN = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agetic_cdd_api"
    / "foundation_store_contract.json"
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_s5_golden_contract_file_exists() -> None:
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert payload["required_roles"] == ["F-01", "F-02", "F-03", "F-04", "F-05", "F-06"]
    assert "completeness" in payload["required_keys"]


def test_s5_ola_fixture_extractors() -> None:
    cim = (FIXTURES / "cim.txt").read_text(encoding="utf-8")
    process = (FIXTURES / "process_letter.txt").read_text(encoding="utf-8")
    nda = (FIXTURES / "nda.txt").read_text(encoding="utf-8")
    articles = (FIXTURES / "articles.txt").read_text(encoding="utf-8")
    org = (FIXTURES / "org_chart.txt").read_text(encoding="utf-8")

    f01 = extract_role_spec("F-01", cim, sources=["cim.txt"], coverage="full")
    assert 1 <= f01["attractiveness_score"] <= 10
    assert "Ola" in " ".join(f01["investment_drivers"] + f01["must_be_true"]) or f01["attractiveness_score"] >= 5

    f02 = extract_role_spec("F-02", process, sources=["process_letter.txt"], coverage="full", prior_spec=f01)
    assert f02["consumes_f01_score"] == f01["attractiveness_score"]

    f03 = extract_role_spec("F-03", process, sources=["process_letter.txt"], coverage="full")
    assert f03["dates"]
    assert f03["coverage"] == "full"

    f04 = extract_role_spec("F-04", nda, sources=["nda.txt"], coverage="full")
    assert f04["risks"]

    f05 = extract_role_spec("F-05", articles, sources=["articles.txt"], coverage="full")
    assert f05["legal_name"] and "Ola Electric" in f05["legal_name"]
    assert f05["share_classes"]

    f06 = extract_role_spec("F-06", org, sources=["org_chart.txt"], coverage="full", prior_spec=f05)
    assert f06["consumes_f05"] is True
    assert any(row.get("role") == "CEO" for row in f06["c_suite"])


def test_s5_test5_ola_vdr_golden_store() -> None:
    if not TEST5_DOCS.is_dir():
        pytest.skip(f"Test5 VDR not present at {TEST5_DOCS}")
    wanted = [
        "03_Investment_Thesis.pdf",
        "02_Corporate_Overview.pdf",
        "06_Legal_Due_Diligence.pdf",
        "08_Technical_Due_Diligence.pdf",
        "10_HR_Organizational_Due_Diligence.pdf",
        "01_Executive_Summary (2).pdf",
    ]
    files = [TEST5_DOCS / name for name in wanted if (TEST5_DOCS / name).is_file()]
    assert len(files) >= 5, f"Test5 documents missing, found {files}"

    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "S5 Ola Test5", "slug": "s5-ola-test5", "industry": "automotive"},
        )
        deal_id = created.json()["data"]["id"]
        for path in files:
            upload = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (path.name, BytesIO(path.read_bytes()), "application/pdf")},
            )
            assert upload.status_code == 200, path.name

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

        store = json.loads(
            (ensure_deal_folder("s5-ola-test5") / "library" / "foundation_context.json").read_text(
                encoding="utf-8"
            )
        )
        errors = validate_foundation_store(store)
        assert errors == [], errors
        assert store["completeness"]["complete"] is True
        assert "Ola" in str(store.get("target") or store.get("target_company") or "")

        f01 = store["roles"]["F-01"]["spec"]
        f02 = store["roles"]["F-02"]["spec"]
        f06 = store["roles"]["F-06"]
        assert f02["consumes_f01_score"] == f01["attractiveness_score"]
        f06_sources = store["agents_by_role"]["F-06"]["sources"]
        assert any("F-05" in str(item) for item in f06_sources)
        assert f06["spec"]["consumes_f05"] is True
        f05_json = ensure_deal_folder("s5-ola-test5") / "library" / "foundation_roles" / "F-05.json"
        assert f05_json.is_file()
