"""Retrieval benchmark tests — 20-prompt recall matrix on 100+ file VDR.

Run:
  cd apps/api && .venv/bin/pytest tests/test_retrieval_benchmark.py -v
"""

from __future__ import annotations

import secrets
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.retrieval_benchmark import (
    BENCHMARK_CASES,
    MIN_FTS_RECALL,
    MIN_PASSAGE_RECALL,
    run_retrieval_benchmark,
    synthetic_benchmark_vdr,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _setup_benchmark_deal(client: TestClient, headers: dict[str, str], *, file_count: int) -> tuple[str, dict]:
    slug = f"bench-{secrets.token_hex(4)}"
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "name": "Retrieval Benchmark",
            "slug": slug,
            "industry": "ev",
            "company": "Ola Electric",
        },
    )
    assert created.status_code == 201, created.text
    deal_id = created.json()["data"]["id"]

    for filename, body in synthetic_benchmark_vdr(file_count):
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
    return deal_id, reingest.json()


@pytest.mark.retrieval_benchmark
def test_retrieval_benchmark_20_prompts_on_100_plus_files() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id, stats = _setup_benchmark_deal(client, headers, file_count=105)
        assert stats["document_count"] >= 105
        assert stats["fts_ready"] is True
        assert stats["indexed_chunks"] >= 100

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal
        from agetic_cdd_api.services_library import load_library_index

        db = SessionLocal()
        try:
            deal = db.get(Deal, deal_id)
            assert deal is not None
            index = load_library_index(deal)
            assert index is not None
            report = run_retrieval_benchmark(
                deal,
                index,
                company="Ola Electric",
                document_count=stats["document_count"],
                indexed_chunks=stats["indexed_chunks"],
            )
        finally:
            db.close()

    assert report.case_total == len(BENCHMARK_CASES)
    assert report.fts_recall_rate >= MIN_FTS_RECALL, report.to_dict()
    assert report.passage_recall_rate >= MIN_PASSAGE_RECALL, report.to_dict()
    assert report.passed

    failures = [r for r in report.case_results if not (r.fts_recall and r.passage_recall)]
    assert len(failures) <= 2, [f"{f.case_id}: {f.notes}" for f in failures]


@pytest.mark.retrieval_benchmark
def test_retrieval_benchmark_on_existing_slug_if_present() -> None:
    """Optional smoke: run matrix on test5 when present in local DB."""
    with TestClient(app) as client:
        headers = _headers(client)
        deals = client.get("/api/v1/deals", headers=headers).json().get("data") or []
        match = next((d for d in deals if d.get("slug") == "test5"), None)
        if not match:
            pytest.skip("test5 deal not in local database")

        reingest = client.post(
            f"/api/v1/portfolios/{match['id']}/cdd/library/reingest",
            headers=headers,
        )
        assert reingest.status_code == 200
        stats = reingest.json()

        from agetic_cdd_api.db import SessionLocal
        from agetic_cdd_api.models import Deal
        from agetic_cdd_api.services_library import load_library_index

        db = SessionLocal()
        try:
            deal = db.get(Deal, match["id"])
            assert deal is not None
            index = load_library_index(deal)
            assert index is not None
            report = run_retrieval_benchmark(
                deal,
                index,
                company=str(deal.company or deal.name or "Test5"),
                document_count=stats["document_count"],
                indexed_chunks=stats["indexed_chunks"],
            )
        finally:
            db.close()

    assert report.fts_recall_rate >= 0.70
    assert report.passage_recall_rate >= 0.65
