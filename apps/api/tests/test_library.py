"""Central Data Library parse / classify / Phase 1 tests."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_extract import extract_file
from agetic_cdd_api.services_library import (
    classify_cdl,
    load_library_index,
    phase1_agent_output,
    route_agents,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_filename_type_beats_body_keywords() -> None:
    financial_body = "Revenue EBITDA valuation cash flow margin forecast financial statements"
    cases = [
        ("01_Executive_Summary (1).pdf", "deal_strategy"),
        ("02_Corporate_Overview.pdf", "company_management"),
        ("03_Investment_Thesis.pdf", "deal_strategy"),
        ("04_Commercial_Due_Diligence.pdf", "customer"),
        ("05_Financial_Due_Diligence.pdf", "financial"),
        ("06_Legal_Due_Diligence.pdf", "legal_esg"),
        ("07_Operational_Due_Diligence.pdf", "operations"),
        ("08_Technical_Due_Diligence.pdf", "operations"),
        ("10_HR_Organizational_Due_Diligence.pdf", "company_management"),
        ("11_Market_Competition_Analysis.pdf", "market_competition"),
        ("12_Manufacturing_Supply_Chain_Review.pdf", "operations"),
        ("13_Valuation_Retention_Comparable_Analysis.pdf", "financial"),
    ]
    for filename, expected in cases:
        category, _secondary, confidence = classify_cdl(filename=filename, text=financial_body)
        assert category == expected, filename
        assert confidence >= 0.9

    assert route_agents(filename="08_Technical_Due_Diligence.pdf", cdl_category="operations") == [
        "ip_and_technology"
    ]
    assert "management_quality" in route_agents(
        filename="10_HR_Organizational_Due_Diligence.pdf",
        cdl_category="company_management",
    )


def test_phase1_summary_reads_strategy_docs() -> None:
    class FakeDeal:
        id = "deal-1"
        name = "Test3"
        company = "Test3"

    index = {
        "document_count": 2,
        "category_counts": {
            "deal_strategy": 1,
            "company_management": 1,
            "market_competition": 0,
            "customer": 0,
            "operations": 0,
            "legal_esg": 0,
            "financial": 0,
        },
        "documents": [
            {
                "filename": "01_Executive_Summary.pdf",
                "cdl_category": "deal_strategy",
                "excerpt": (
                    "Ola Electric Mobility Limited is one of India's fastest-growing EV makers. "
                    "The company operates Futurefactory in Tamil Nadu."
                ),
            },
            {
                "filename": "02_Corporate_Overview.pdf",
                "cdl_category": "company_management",
                "excerpt": "Headquarters Bengaluru. CEO Bhavish Aggarwal.",
            },
        ],
    }
    output = phase1_agent_output(FakeDeal(), agent_key="deal_context_and_objectives", index=index)
    assert output["stub"] is False
    assert output["target_company"] == "Test3"
    assert "Test3" in output["summary"]
    assert output["findings"][0] == "Target: Test3"
    assert output["gaps"] == [
        "Market / Competition",
        "Customer",
        "Operations",
        "Legal / ESG",
        "Financial",
    ]


def test_extract_and_classify_text(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("Revenue and EBITDA margin improved; cash flow from operations.", encoding="utf-8")
    extracted = extract_file(path)
    assert "EBITDA" in extracted["text"] or "ebitda" in extracted["text"].lower()
    category, _secondary, confidence = classify_cdl(filename="notes.txt", text=extracted["text"])
    assert category == "financial"
    assert confidence > 0.5


def test_phase1_builds_library_from_file_contents() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Library Deal", "slug": "library-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]

        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={
                "file": (
                    "memo.txt",
                    BytesIO(b"Customer churn and NPS declined while retention held."),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 200

        run = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert run.status_code == 202

        listed = client.get(f"/api/v1/portfolios/{deal_id}/cdd/vdr", headers=headers)
        doc = listed.json()["data"][0]
        assert doc["status"] == "ready"
        assert doc["cdl_category"] == "customer"
        assert int(doc["char_count"] or 0) > 0

        output = client.get(
            f"/api/v1/portfolios/{deal_id}/pipeline/agents/deal_context_and_objectives/output",
            headers=headers,
        )
        assert output.status_code == 200
        body = output.json()["data"]["output"]
        assert body["stub"] is False
        assert body["document_count"] == 1
        assert body["category_counts"]["customer"] == 1

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            index = load_library_index(deal)
        finally:
            db.close()
        assert index is not None
        assert index["document_count"] == 1
        assert index["documents"][0]["cdl_category"] == "customer"
        assert int(index["documents"][0].get("chunk_count") or 0) >= 1

        from agetic_cdd_api.services_library_search import search_db_path

        assert search_db_path(deal).is_file()


def test_target_company_infers_from_excerpt_when_company_unset() -> None:
    from agetic_cdd_api.services_library import phase1_agent_output

    class FakeDeal:
        id = "deal-2"
        name = "Unnamed Deal"
        company = None

    index = {
        "document_count": 1,
        "category_counts": {"deal_strategy": 1},
        "documents": [
            {
                "filename": "01_Executive_Summary.pdf",
                "cdl_category": "deal_strategy",
                "excerpt": "Ola Electric Mobility Limited is one of India's fastest-growing EV makers.",
            },
        ],
    }
    output = phase1_agent_output(FakeDeal(), agent_key="deal_context_and_objectives", index=index)
    assert "Ola Electric" in output["target_company"]


def test_safe_stem_unique_for_similar_filenames() -> None:
    from agetic_cdd_api.services_library import _safe_stem

    a = "Financial_Report_Q1_2025_Version_A_Final.pdf"
    b = "Financial_Report_Q1_2025_Version_B_Final.pdf"
    assert _safe_stem(a) != _safe_stem(b)
    assert _safe_stem(a).endswith("_" + __import__("hashlib").md5(a.encode()).hexdigest()[:8])


def test_target_company_prefers_deal_metadata() -> None:
    from agetic_cdd_api.services_library import _target_company

    class FakeDeal:
        company = "Ola Electric Mobility Ltd"
        name = "Test1"

    docs = [{"excerpt": "Prepared by Deloitte GmbH for the transaction."}]
    assert _target_company(FakeDeal(), docs) == "Ola Electric Mobility Ltd"

    class NoCompanyDeal:
        company = None
        name = "FallbackCo"

    assert _target_company(NoCompanyDeal(), docs) == "FallbackCo"


def test_load_library_document_falls_back_to_legacy_stem() -> None:
    import json

    from agetic_cdd_api.services_library import _legacy_stem, load_library_document
    from agetic_cdd_api.services_vdr import library_dir

    class FakeDeal:
        slug = "legacy-stem-deal"

    deal = FakeDeal()
    doc_dir = library_dir(deal) / "documents"  # type: ignore[arg-type]
    doc_dir.mkdir(parents=True, exist_ok=True)
    filename = "05_Financial_Due_Diligence.pdf"
    legacy = doc_dir / f"{_legacy_stem(filename)}.json"
    legacy.write_text(json.dumps({"filename": filename, "text": "legacy payload"}), encoding="utf-8")
    try:
        payload = load_library_document(deal, filename)  # type: ignore[arg-type]
        assert payload is not None
        assert payload["text"] == "legacy payload"
    finally:
        legacy.unlink(missing_ok=True)

