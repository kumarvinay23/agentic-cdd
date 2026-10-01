"""DW-4 web research, charts, SSE, decision chain, export."""

from __future__ import annotations

import secrets
from unittest.mock import patch

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_document_runner import (
    _append_chart_markers,
    _extract_share_chart,
    merge_document_section,
    select_web_capabilities,
)
from agetic_cdd_api.services_web_research import filter_by_subject


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal(client: TestClient, headers: dict[str, str], *, name: str) -> str:
    slug = f"dw4-{secrets.token_hex(4)}"
    res = client.post(
        "/api/v1/deals",
        headers=headers,
        json={
            "name": name,
            "slug": slug,
            "industry": "ev",
            "company": "Ola Electric",
        },
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


def test_select_web_capabilities_competitors() -> None:
    caps = select_web_capabilities("Who are the main competitors of Ola Electric?")
    ids = [c["id"] for c in caps]
    assert "gx_x_competitor_table" in ids
    assert all(c.get("src") == "web" for c in caps)


def test_filter_by_subject_drops_off_topic() -> None:
    rows = [
        {
            "title": "Ola Electric EV scooter share",
            "snippet": "Ola Electric holds 32% of India EV 2W",
            "url": "https://example.com/ola",
        },
        {
            "title": "Enterprise SaaS cybersecurity trends",
            "snippet": "Zero-trust for B2B software vendors",
            "url": "https://example.com/saas",
        },
    ]
    kept = filter_by_subject(
        rows, subject="Ola Electric", prompt="Who are the main competitors of Ola Electric?"
    )
    assert len(kept) == 1
    assert "Ola" in kept[0]["title"]


def test_merge_web_source_footer() -> None:
    base = "# Deal\n\n## Sources\n\n<!-- cdd:sources -->\n"
    md, cite_map = merge_document_section(
        base,
        heading="Competitors",
        body="Peers include Ather [1].\n",
        source_titles=["Ather Energy Overview"],
        source_meta={
            "Ather Energy Overview": {
                "origin": "web",
                "url": "https://example.com/ather",
                "domain": "example.com",
            }
        },
    )
    assert cite_map["Ather Energy Overview"] == 1
    assert "**[1]** (web) [Ather Energy Overview](https://example.com/ather) - example.com" in md


def test_extract_share_chart_and_marker() -> None:
    sources = [
        {
            "title": "market.pdf",
            "snippet": "Ola Electric holds 32% share while Ather Energy at 18%.",
            "passages": ["Ola Electric holds 32% share while Ather Energy at 18%."],
        }
    ]
    chart = _extract_share_chart(sources, title="Market Share Trend")
    assert chart is not None
    assert chart["type"] == "bar"
    assert len(chart["series"]) >= 2
    body = _append_chart_markers("Prose here.", [chart])
    assert "[[CHART: Market Share Trend]]" in body
    assert "<!-- cdd:chart" in body
    assert '"type": "bar"' in body


def test_finalize_charts_always_emits_for_share_prompt() -> None:
    from agetic_cdd_api.services_document_runner import _finalize_charts

    charts = _finalize_charts(
        [],
        prompt="What is Ola Electric's market share?",
        caps=[{"id": "mkt_marimekko_segments", "title": "Mkt Marimekko Segments"}],
        sources=[],
    )
    assert len(charts) == 1
    assert charts[0]["title"] == "Market Share Trend"
    assert charts[0].get("placeholder") is True
    body = _append_chart_markers("Share rose.", charts)
    assert "[[CHART: Market Share Trend]]" in body


def test_remount_research_onto_newer_document() -> None:
    from agetic_cdd_api.services_document_runner import remount_research_onto_document

    baseline = (
        "# Deal\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    newer = (
        "# Deal\n\n"
        "## Prior section\n\n"
        "Already written.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n\n"
        "**[1]** (data room) prior.pdf\n"
    )
    result = {
        "content": "I added a section citing [1].",
        "tasks": [],
        "sources": [{"id": 1, "type": "vdr", "title": "market.pdf", "used": True}],
        "document": "## ignored",
        "heading": "Market Share",
        "section_body": "Share rose to 32% [1].\n",
        "source_titles": ["market.pdf"],
        "source_meta": {"market.pdf": {"origin": "internal"}},
        "evidence_sources": [
            {"origin": "internal", "title": "market.pdf", "snippet": "32%"}
        ],
        "cite_map": {"market.pdf": 1},
        "baseline_document": baseline,
    }
    mounted = remount_research_onto_document(newer, result)
    assert "## Prior section" in mounted["document"]
    assert "## Market Share" in mounted["document"]
    assert "**[1]** (data room) prior.pdf" in mounted["document"]
    assert "**[2]** (data room) market.pdf" in mounted["document"]
    assert "Share rose to 32% [2]." in mounted["document"]
    assert mounted["sources"][0]["id"] == 2
    assert "citing [2]" in mounted["content"]


def test_decision_chain_and_export() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal(client, headers, name="DW4 Chain")
        posted = client.post(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
            json={"content": "What is Ola Electric's market share?"},
        )
        assert posted.status_code == 200, posted.text

        chain = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/decision-chain",
            headers=headers,
        )
        assert chain.status_code == 200
        body = chain.json()
        assert body["count"] == 1
        assert "market share" in body["steps"][0]["prompt"].lower()
        assert body["steps"][0]["tasks"]

        export = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/export",
            headers=headers,
        )
        assert export.status_code == 200
        bundle = export.json()
        assert "document" in bundle
        assert len(bundle["messages"]) == 2
        assert bundle["decision_chain"]["count"] == 1


def test_post_message_stream_sse() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id = _create_deal(client, headers, name="DW4 SSE")
        with client.stream(
            "POST",
            f"/api/v1/portfolios/{deal_id}/documents/messages/stream",
            headers=headers,
            json={"content": "What is Ola Electric's market share?"},
        ) as res:
            assert res.status_code == 200
            assert "text/event-stream" in res.headers.get("content-type", "")
            text = "".join(res.iter_text())
        assert "event: status" in text
        assert "event: task" in text
        assert "event: done" in text
        assert '"role": "assistant"' in text


def test_competitor_prompt_runs_web_task() -> None:
    fake_web = [
        {
            "origin": "web",
            "title": "Ola Electric competitors 2024",
            "url": "https://news.example/ola-competitors",
            "domain": "news.example",
            "snippet": "Ola Electric competes with Ather Energy in India EV 2W.",
            "passages": ["Ola Electric competes with Ather Energy in India EV 2W."],
        }
    ]

    def _fake_research(*, prompt, subject, capability, limit=6):
        return fake_web, [f"{subject} competitors"]

    with patch(
        "agetic_cdd_api.services_document_runner.research_web",
        side_effect=_fake_research,
    ):
        with TestClient(app) as client:
            headers = _headers(client)
            deal_id = _create_deal(client, headers, name="DW4 Web")
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
            web_tasks = [t for t in tasks if t.get("tool") == "web"]
            assert web_tasks, tasks
            assert web_tasks[0]["label"] == "Web research"
            assert web_tasks[0]["detail"]["sources"]
            doc = posted.json()["data"]["document"]["document"]
            assert "(web)" in doc
            sources = posted.json()["data"]["assistant"]["sources"]
            assert any(s.get("type") == "web" for s in sources)
