"""FTS scale tests — re-ingest and lexical retrieval on 100+ VDR files."""

from __future__ import annotations

import secrets
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.document_capabilities import capability_by_id
from agetic_cdd_api.services_document_runner import retrieve_passages
from agetic_cdd_api.services_library import load_library_index
from agetic_cdd_api.services_library_search import search_db_path, search_library_chunks


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _synthetic_vdr_files(count: int) -> list[tuple[str, str]]:
    """Generate count uniquely named VDR files across CDL categories."""
    patterns: list[tuple[str, str]] = [
        ("11_Market_Competition_{i}.txt", "Ola Electric market share {i} percent FY2024 competition landscape."),
        ("05_Financial_Due_Diligence_{i}.txt", "Revenue growth rate {i} percent YoY EBITDA margin financial profile."),
        ("03_Investment_Thesis_{i}.txt", "Investment thesis growth strategy expansion plan for the target company."),
        ("06_Legal_Due_Diligence_{i}.txt", "Legal compliance contract review litigation summary regulatory matters."),
        ("02_Corporate_Overview_{i}.txt", "Corporate overview management team board biography headquarters."),
        ("04_Commercial_Due_Diligence_{i}.txt", "Customer churn NPS retention cohort commercial diligence findings."),
        ("07_Operational_Due_Diligence_{i}.txt", "Manufacturing supply chain operations capacity supplier review."),
        ("08_Technical_Due_Diligence_{i}.txt", "Software architecture patent technology stack product roadmap."),
    ]
    out: list[tuple[str, str]] = []
    for n in range(count):
        template, body = patterns[n % len(patterns)]
        out.append((template.format(i=n), body.format(i=n)))
    return out


@pytest.mark.fts_scale
def test_reingest_and_fts_retrieval_on_100_plus_files() -> None:
    file_count = 105
    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"fts-scale-{secrets.token_hex(4)}"
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "name": "FTS Scale Deal",
                "slug": slug,
                "industry": "ev",
                "company": "Ola Electric",
            },
        )
        assert created.status_code == 201, created.text
        deal_id = created.json()["data"]["id"]

        for filename, body in _synthetic_vdr_files(file_count):
            res = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (filename, BytesIO(body.encode("utf-8")), "text/plain")},
            )
            assert res.status_code == 200, res.text

        reingest = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/library/reingest",
            headers=headers,
        )
        assert reingest.status_code == 200, reingest.text
        stats = reingest.json()
        assert stats["success"] is True
        assert stats["document_count"] >= file_count
        assert stats["fts_ready"] is True
        assert stats["indexed_chunks"] >= 100, stats

        stats_get = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/library/stats", headers=headers
        )
        assert stats_get.status_code == 200
        body = stats_get.json()["data"]
        assert body["indexed_chunks"] == stats["indexed_chunks"]

        ingestion = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/ingestion", headers=headers
        )
        assert ingestion.json()["data"]["fts_ready"] is True
        assert ingestion.json()["data"]["indexed_chunks"] >= 100

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            assert deal is not None
            assert search_db_path(deal).is_file()
            index = load_library_index(deal)
            assert index is not None

            hits = search_library_chunks(
                deal,
                query="What is Ola Electric market share?",
                categories={"market_competition", "deal_strategy"},
                limit=20,
                index=index,
            )
            assert len(hits) >= 3, "expected FTS hits across 100+ file index"
            assert any("market" in str(h.get("text", "")).lower() for h in hits)

            cap = capability_by_id("mkt_marimekko_segments")
            assert cap is not None
            sources = retrieve_passages(
                deal,
                prompt="Research: What is Ola Electric's market share?",
                capability=cap,
                index=index,
                limit=6,
            )
            assert sources, "retrieve_passages should use FTS-backed chunks"
            assert any("Market_Competition" in s.get("title", "") for s in sources)
        finally:
            db.close()


def test_library_reingest_rebuilds_chunks_and_fts() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"reingest-{secrets.token_hex(4)}"
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Reingest Deal", "slug": slug, "industry": "ev", "company": "Test5"},
        )
        deal_id = created.json()["data"]["id"]
        client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={
                "file": (
                    "11_Market_Competition_Analysis.txt",
                    BytesIO(
                        b"Ola Electric holds 32 percent market share in India E2W FY2024E."
                    ),
                    "text/plain",
                )
            },
        )
        first = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/library/reingest", headers=headers
        )
        assert first.status_code == 200
        assert first.json()["indexed_chunks"] >= 1

        second = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/library/reingest", headers=headers
        )
        assert second.status_code == 200
        assert second.json()["fts_ready"] is True
