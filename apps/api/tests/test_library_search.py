"""Tests for library chunking and FTS retrieval."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_library import ingest_vdr_to_library, load_library_document
from agetic_cdd_api.services_library_chunks import build_document_chunks
from agetic_cdd_api.services_library_search import (
    group_chunks_as_sources,
    rebuild_search_index,
    search_db_path,
    search_library_chunks,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_build_document_chunks_splits_long_text() -> None:
    paragraph = (
        "Ola Electric holds the leading market share position in India's E2W segment. "
        * 40
    )
    chunks = build_document_chunks(paragraph)
    assert len(chunks) >= 3
    assert all(len(c["text"]) >= 80 for c in chunks)
    assert chunks[0]["kind"] == "body"


def test_build_document_chunks_includes_tables() -> None:
    chunks = build_document_chunks(
        "Summary paragraph about revenue growth and margin trends in FY2024.",
        tables=[
            {
                "name": "share_table",
                "rows": [
                    ["Company", "Share"],
                    ["Ola Electric", "32%"],
                    ["Ather Energy", "12%"],
                ],
            }
        ],
    )
    kinds = {c["kind"] for c in chunks}
    assert "table" in kinds


def test_fts_prefers_market_doc_among_many_files() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Search Deal", "slug": "search-deal-fts", "industry": "ev", "company": "Ola Electric"},
        )
        deal_id = created.json()["data"]["id"]

        files = {
            "01_Executive_Summary.txt": (
                "Executive summary for the transaction. Leadership and strategic priorities only."
            ),
            "04_Financial_Profile.txt": (
                "Revenue grew from INR 2.4B to INR 5.1B with strong EBITDA margin expansion."
            ),
            "11_Market_Competition_Analysis.txt": (
                "Market Competition Analysis for Ola Electric. "
                "Ola Electric holds the leading market share position in India's E2W segment "
                "with a market share of 32 percent as of FY2024E. "
                "TVS iQube holds 18 percent and Ather Energy holds 12 percent."
            ),
            "06_Legal_Due_Diligence.txt": (
                "Contract review and litigation summary with no market share references."
            ),
        }
        for name, body in files.items():
            res = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (name, BytesIO(body.encode("utf-8")), "text/plain")},
            )
            assert res.status_code == 200, res.text

        run = client.post(
            f"/api/v1/portfolios/{deal_id}/pipeline/run",
            headers=headers,
            json={"phase_id": "data_ingestion"},
        )
        assert run.status_code == 202

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            assert deal is not None
            assert search_db_path(deal).is_file()

            payload = load_library_document(deal, "11_Market_Competition_Analysis.txt")
            assert payload is not None
            assert len(payload.get("chunks") or []) >= 1

            hits = search_library_chunks(
                deal,
                query="What is Ola Electric market share?",
                categories={"market_competition", "deal_strategy"},
                limit=12,
            )
            assert hits
            top_file = hits[0]["filename"]
            assert "Market_Competition" in top_file

            sources = group_chunks_as_sources(hits, limit=3, passages_per_doc=3)
            assert sources
            assert "Market_Competition" in sources[0]["title"]
            assert "32" in " ".join(sources[0]["passages"])
        finally:
            db.close()


def test_group_chunks_as_sources_includes_citations() -> None:
    hits = [
        {
            "filename": "11_Market_Competition_Analysis.pdf",
            "cdl_category": "market_competition",
            "chunk_id": "11_Market_Competition_Analysis.pdf::2",
            "label": "Competitive Landscape",
            "kind": "body",
            "text": "Ola Electric holds 32 percent market share in India E2W FY2024E.",
        }
    ]
    sources = group_chunks_as_sources(hits, limit=3, passages_per_doc=3)
    assert len(sources) == 1
    row = sources[0]
    assert row["chunk_ids"] == ["11_Market_Competition_Analysis.pdf::2"]
    assert row["section_label"] == "Competitive Landscape"
    assert row["chunk_index"] == 2
    assert len(row["citations"]) == 1
    assert row["citations"][0]["kind"] == "body"


def test_format_citation_hint() -> None:
    from agetic_cdd_api.services_library_search import format_citation_hint

    assert format_citation_hint({"section_label": "Market Overview", "chunk_index": 1}) == (
        "Market Overview · chunk 2"
    )
    assert format_citation_hint({"chunk_index": 0}) == "chunk 1"
    assert format_citation_hint({}) is None


def test_rebuild_search_index_from_legacy_document_without_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FakeDeal:
        id = "deal-x"
        name = "Legacy"
        company = "Legacy Co"
        slug = "legacy-deal"

    deal = FakeDeal()

    def fake_library_dir(_deal: FakeDeal):
        return tmp_path / "library"

    def fake_load_library_document(_deal: FakeDeal, filename: str):
        return {
            "text": (
                "Ola Electric market share reached 32 percent in FY2024E across India E2W. "
                "Competitors include Ather Energy and TVS iQube."
            ),
            "tables": [],
        }

    monkeypatch.setattr("agetic_cdd_api.services_library_search.library_dir", fake_library_dir)
    monkeypatch.setattr(
        "agetic_cdd_api.services_library_search.load_library_document",
        fake_load_library_document,
    )

    index = {
        "generated_at": "2026-01-01T00:00:00Z",
        "document_count": 1,
        "documents": [
            {
                "filename": "11_Market_Competition_Analysis.txt",
                "status": "ready",
                "cdl_category": "market_competition",
            }
        ],
    }
    stats = rebuild_search_index(deal, index=index)
    assert stats["chunk_count"] >= 1
    hits = search_library_chunks(
        deal,
        query="market share Ola Electric",
        categories={"market_competition"},
        limit=5,
        index=index,
    )
    assert hits
    assert "32" in hits[0]["text"]
