"""Document Workspace DIQ parity validation matrix (automated).

Run: pytest tests/test_document_workspace_parity.py -v
"""

from __future__ import annotations

import json
import re
import secrets
from io import BytesIO

import pytest
from fastapi.testclient import TestClient

from agetic_cdd_api.app import app

_MARKET_VDR = (
    "Market Competition Analysis for Ola Electric. "
    "Ola Electric holds the leading market share position in India's E2W segment "
    "with a market share of 32 percent as of FY2024E showing a strong gain trend. "
    "TVS iQube holds 18 percent and Ather Energy holds 12 percent.\n"
)

_GROWTH_VDR = (
    "Financial profile for Ola Electric. Revenue grew from INR 2.4B to INR 5.1B. "
    "Revenue growth rate YoY reached 112 percent in FY2024. CAGR momentum remains strong.\n"
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal(client: TestClient, headers: dict[str, str]) -> tuple[str, str]:
    slug = f"parity-{secrets.token_hex(4)}"
    res = client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "name": "Parity Deal",
            "slug": slug,
            "industry": "ev",
            "company": "Ola Electric",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"], slug


def _upload_vdr(client: TestClient, headers: dict[str, str], deal_id: str, text: str, name: str) -> None:
    res = client.post(
        f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
        headers=headers,
        files={"file": (name, BytesIO(text.encode("utf-8")), "text/plain")},
    )
    assert res.status_code == 200, res.text


def _parse_chart_payloads(markdown: str) -> list[dict]:
    out: list[dict] = []
    for line in markdown.splitlines():
        raw = line.strip()
        if not raw.startswith("<!-- cdd:chart "):
            continue
        payload = raw.replace("<!-- cdd:chart ", "").replace(" -->", "")
        out.append(json.loads(payload))
    return out


@pytest.fixture()
def parity_deal() -> tuple[TestClient, dict[str, str], str]:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id, _slug = _create_deal(client, headers)
        _upload_vdr(client, headers, deal_id, _MARKET_VDR, "11_Market_Competition_Analysis.txt")
        _upload_vdr(client, headers, deal_id, _GROWTH_VDR, "04_Financial_Profile.txt")
        yield client, headers, deal_id


def test_parity_empty_workspace_contract(parity_deal: tuple) -> None:
    client, headers, deal_id = parity_deal
    doc = client.get(f"/api/v1/portfolios/{deal_id}/documents", headers=headers)
    assert doc.status_code == 200
    assert "Commercial Due Diligence" in doc.json()["document"]

    suggestions = client.get(
        f"/api/v1/portfolios/{deal_id}/documents/suggestions", headers=headers
    )
    body = suggestions.json()
    assert len(body["cards"]) == 5
    assert len(body["next_steps"]) == 4
    assert body["cards"][0]["title"] == "Market Share"
    assert body["next_steps"][0]["title"] == "Market Overview"
    copilot = body.get("copilot") or {}
    assert copilot.get("mode_label") in {"Smart (recommended)", "Heuristic"}
    assert isinstance(copilot.get("capability_count"), int)
    assert copilot["capability_count"] >= 15

    caps = client.get(f"/api/v1/portfolios/{deal_id}/cdd/capabilities", headers=headers)
    assert caps.status_code == 200
    assert len(caps.json()) >= 15


@pytest.mark.parametrize(
    "prompt,expect_chart_title,expect_tool",
    [
        (
            "Research this and add a section to the document: What is Ola Electric's market share?",
            "Market Share Trend",
            "internal",
        ),
        (
            "Research this and add a section to the document: "
            "What is the revenue growth rate of Ola Electric?",
            "Growth Trend",
            "internal",
        ),
    ],
)
def test_parity_research_turn(
    parity_deal: tuple,
    prompt: str,
    expect_chart_title: str,
    expect_tool: str,
) -> None:
    client, headers, deal_id = parity_deal
    posted = client.post(
        f"/api/v1/portfolios/{deal_id}/documents/messages",
        headers=headers,
        json={"content": prompt},
    )
    assert posted.status_code == 200, posted.text
    data = posted.json()["data"]
    assistant = data["assistant"]
    doc = data["document"]["document"]

    assert assistant["content"]
    assert assistant["tasks"]
    assert any(t.get("tool") == expect_tool for t in assistant["tasks"])
    assert assistant["sources"]
    assert len(assistant.get("next_steps") or []) == 4
    assert "## Sources" in doc
    assert f"[[CHART: {expect_chart_title}]]" in doc

    charts = _parse_chart_payloads(doc)
    assert charts, "expected cdd:chart JSON payload"
    assert charts[-1]["title"] == expect_chart_title
    assert charts[-1].get("unit") == "%"
    assert "type" in charts[-1]


def test_parity_competitor_web_task(parity_deal: tuple) -> None:
    client, headers, deal_id = parity_deal
    posted = client.post(
        f"/api/v1/portfolios/{deal_id}/documents/messages",
        headers=headers,
        json={
            "content": (
                "Research this and add a section to the document: "
                "Who are the main competitors of Ola Electric?"
            )
        },
    )
    assert posted.status_code == 200, posted.text
    tasks = posted.json()["data"]["assistant"]["tasks"]
    assert any(t.get("tool") == "web" for t in tasks)


def test_parity_sse_stream_events(parity_deal: tuple) -> None:
    client, headers, deal_id = parity_deal
    with client.stream(
        "POST",
        f"/api/v1/portfolios/{deal_id}/documents/messages/stream",
        headers=headers,
        json={
            "content": (
                "Research this and add a section to the document: "
                "What is Ola Electric's market share?"
            )
        },
    ) as res:
        assert res.status_code == 200
        text = "".join(res.iter_text())
    assert "event: status" in text
    assert "event: task" in text
    assert "event: done" in text


def test_parity_export_and_decision_chain(parity_deal: tuple) -> None:
    client, headers, deal_id = parity_deal
    client.post(
        f"/api/v1/portfolios/{deal_id}/documents/messages",
        headers=headers,
        json={
            "content": (
                "Research this and add a section to the document: "
                "What is Ola Electric's market share?"
            )
        },
    )
    chain = client.get(
        f"/api/v1/portfolios/{deal_id}/documents/decision-chain", headers=headers
    )
    assert chain.status_code == 200
    assert chain.json()["count"] == 1

    export = client.get(f"/api/v1/portfolios/{deal_id}/documents/export", headers=headers)
    assert export.status_code == 200
    bundle = export.json()
    assert bundle["document"]
    assert bundle["decision_chain"]["count"] == 1
    assert "[[CHART:" in bundle["document"]


def test_parity_chart_series_when_evidence_has_percentages(parity_deal: tuple) -> None:
    client, headers, deal_id = parity_deal
    posted = client.post(
        f"/api/v1/portfolios/{deal_id}/documents/messages",
        headers=headers,
        json={
            "content": (
                "Research this and add a section to the document: "
                "What is Ola Electric's market share?"
            )
        },
    )
    doc = posted.json()["data"]["document"]["document"]
    charts = _parse_chart_payloads(doc)
    chart = charts[-1]
    series = chart.get("series") or []
    # With market VDR uploaded, expect at least two named share points.
    if len(series) >= 2:
        assert chart["type"] == "bar"
        assert all("label" in row and "value" in row for row in series)
    else:
        assert chart.get("placeholder") is True
