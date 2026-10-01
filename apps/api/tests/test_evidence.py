"""Evidence coverage analyze tests."""

from __future__ import annotations

from io import BytesIO

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.evidence_catalog import REQUIREMENTS, WORKSTREAMS, validate_catalog
from agetic_cdd_api.services_evidence import (
    _FALLBACK_REMEDY,
    _keyword_in,
    _legend_remedy,
    _normalize,
    build_evidence_graph,
)


SAMPLE_FILES = [
    "01_Executive_Summary (1).pdf",
    "01_Executive_Summary (2).pdf",
    "02_Corporate_Overview.pdf",
    "03_Investment_Thesis.pdf",
    "04_Commercial_Due_Diligence.pdf",
    "05_Financial_Due_Diligence.pdf",
    "06_Legal_Due_Diligence.pdf",
    "07_Operational_Due_Diligence.pdf",
    "08_Technical_Due_Diligence.pdf",
    "10_HR_Organizational_Due_Diligence.pdf",
    "11_Market_Competition_Analysis.pdf",
    "12_Manufacturing_Supply_Chain_Review.pdf",
    "13_Valuation_Retention_Comparable_Analysis.pdf",
    "wildfly2.log",
]


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_catalog_is_internally_consistent() -> None:
    validate_catalog()
    assert len(REQUIREMENTS) == 32
    assert len(WORKSTREAMS) == 6


def test_short_keyword_is_whole_word_not_substring() -> None:
    norm = _normalize("pipeline_overview.pdf")
    tokens = frozenset(norm.split())
    assert "ip" not in tokens
    assert not _keyword_in(norm, tokens, "ip")
    assert _keyword_in(norm, tokens, "pipeline")


def test_unknown_status_uses_fallback_remedy() -> None:
    assert _legend_remedy("not_a_real_status") == _FALLBACK_REMEDY


def test_unknown_workstream_does_not_raise() -> None:
    graph = build_evidence_graph(company="Orphan", filenames=[])
    assert len([n for n in graph["nodes"] if n["kind"] == "req"]) == 32
    assert len(graph["workstreams"]) == 6


def test_build_graph_matches_diligenceiq_shape() -> None:
    graph = build_evidence_graph(company="Test2", filenames=SAMPLE_FILES)
    reqs = [n for n in graph["nodes"] if n["kind"] == "req"]
    workstreams = [n for n in graph["nodes"] if n["kind"] == "workstream"]
    assert graph["company"] == "Test2"
    assert len(reqs) == 32
    assert len(workstreams) == 6
    assert len(graph["edges"]) == 38
    counts = graph["scorecard"]["counts"]
    assert counts["have"] == 1
    assert counts["partial"] == 13
    assert counts["web"] == 1
    assert counts["request_vdr"] == 2
    assert counts["primary"] == 15
    assert graph["scorecard"]["readiness"] == 25
    assert graph["scorecard"]["total_reqs"] == 32
    fin = next(n for n in reqs if n["id"] == "fin_history")
    assert fin["status"] == "have"
    assert fin["trail"][0].startswith("file:")
    levers = next(n for n in reqs if n["id"] == "levers_overview")
    assert levers["status"] == "request_vdr"
    contestable = next(n for n in reqs if n["id"] == "contestable_pool")
    assert contestable["status"] == "web"


def test_vdr_analyze_endpoint_persists_graph() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={"name": "Coverage Deal", "slug": "coverage-deal", "industry": "generic"},
        )
        deal_id = created.json()["data"]["id"]

        missing = client.post(f"/api/v1/portfolios/{deal_id}/cdd/vdr/analyze", headers=headers)
        assert missing.status_code == 400

        for name in ("01_Executive_Summary.pdf", "05_Financial_Due_Diligence.pdf", "11_Market_Competition_Analysis.pdf"):
            upload = client.post(
                f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
                headers=headers,
                files={"file": (name, BytesIO(b"%PDF-1.4 test"), "application/pdf")},
            )
            assert upload.status_code == 200

        analyzed = client.post(f"/api/v1/portfolios/{deal_id}/cdd/vdr/analyze", headers=headers)
        assert analyzed.status_code == 200
        body = analyzed.json()
        assert body["status"] == "done"
        assert set(body.keys()) >= {"status", "scorecard", "vdr", "graph"}
        assert body["scorecard"]["total_reqs"] == len(REQUIREMENTS)
        assert len(body["graph"]["workstreams"]) == len(WORKSTREAMS)
        assert body["graph"]["nodes"][0]["kind"] == "root"
        assert "have" in body["graph"]["status_legend"]

        saved = client.get(f"/api/v1/portfolios/{deal_id}/cdd/vdr/graph", headers=headers)
        assert saved.status_code == 200
        assert saved.json()["graph"]["company"] == body["graph"]["company"]

        pipeline = client.get(f"/api/v1/portfolios/{deal_id}/pipeline", headers=headers)
        assert pipeline.json()["data"]["next_phase_id"] == "data_ingestion"
