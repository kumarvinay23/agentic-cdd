"""DW-1 Document Workspace API contract tests."""

from __future__ import annotations

import secrets
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.document_capabilities import CAPABILITIES
from agetic_cdd_api.services_deals import deals_root


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def _create_deal(client: TestClient, headers: dict[str, str], *, name: str) -> tuple[str, str]:
    slug = f"doc-deal-{secrets.token_hex(4)}"
    created = client.post(
        "/api/v1/deals",
        headers=headers,
        json={"name": name, "slug": slug, "industry": "ev", "company": "Ola Electric"},
    )
    assert created.status_code == 201, created.text
    return created.json()["data"]["id"], slug


def test_documents_get_put_suggestions_messages_capabilities() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id, slug = _create_deal(client, headers, name="Doc Deal")

        # Default document (not yet persisted)
        doc = client.get(f"/api/v1/portfolios/{deal_id}/documents", headers=headers)
        assert doc.status_code == 200
        body = doc.json()
        assert body["exists"] is False
        assert "Doc Deal - Commercial Due Diligence" in body["document"]
        assert "cdd:sources" in body["document"]

        # Suggestions use company subject
        suggestions = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/suggestions",
            headers=headers,
        )
        assert suggestions.status_code == 200
        cards = suggestions.json()["cards"]
        assert len(cards) == 5
        assert cards[0]["kind"] == "internal"
        assert cards[0]["title"] == "Market Share"
        assert "Ola Electric" in cards[0]["prompt"]
        titles = [c["title"] for c in cards]
        assert titles[:3] == ["Market Share", "Growth Rate", "Competitor Analysis"]
        assert titles[3] in {"EV Penetration", "Market Penetration"}
        assert titles[4] == "Sales Ratio"
        kinds = {c["kind"] for c in cards}
        assert kinds == {"internal", "web", "algo"}
        next_steps = suggestions.json().get("next_steps") or []
        assert len(next_steps) == 4
        assert [s["title"] for s in next_steps] == [
            "Market Overview",
            "Business Model",
            "Growth Strategy",
            "Key Risks",
        ]
        assert "Ola Electric" in next_steps[0]["prompt"]

        copilot = suggestions.json().get("copilot") or {}
        assert copilot.get("mode_label") in {"Smart (recommended)", "Heuristic"}
        assert isinstance(copilot.get("capability_count"), int)
        assert copilot["capability_count"] == len(CAPABILITIES)
        assert "synthesis_enabled" in copilot

        contextual = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/suggestions",
            headers=headers,
            params={
                "after_prompt": (
                    "Research this and add a section to the document: "
                    "What is Ola Electric's market share?"
                )
            },
        )
        assert contextual.status_code == 200
        ctx_steps = contextual.json().get("next_steps") or []
        assert [s["title"] for s in ctx_steps] == [
            "Growth Rate",
            "Competitor Analysis",
            "EV Penetration",
            "Market Overview",
        ]

        # Empty messages
        msgs = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
        )
        assert msgs.status_code == 200
        assert msgs.json() == {"success": True, "data": []}

        # Capabilities catalog (curated subset, DiligenceIQ-shaped)
        caps = client.get(
            f"/api/v1/portfolios/{deal_id}/cdd/capabilities",
            headers=headers,
        )
        assert caps.status_code == 200
        catalog = caps.json()
        assert isinstance(catalog, list)
        assert len(catalog) == len(CAPABILITIES)
        assert catalog[0]["id"] == "mkt_marimekko_segments"
        assert {"id", "kind", "src", "title", "blurb"} <= set(catalog[0].keys())
        ids = {c["id"] for c in catalog}
        assert "gx_x_market_funnel" in ids
        assert "gx_x_competitor_table" in ids

        # Persist document
        markdown = (
            "# Doc Deal - Commercial Due Diligence\n"
            "## Market Share\n"
            "Placeholder section [1].\n"
            "\n"
            "## Sources\n"
            "\n"
            "<!-- cdd:sources -->\n"
            "**[1]** (data room) sample.pdf\n"
        )
        put = client.put(
            f"/api/v1/portfolios/{deal_id}/documents",
            headers=headers,
            json={"document": markdown},
        )
        assert put.status_code == 200
        assert put.json()["exists"] is True
        assert put.json()["document"] == markdown

        again = client.get(f"/api/v1/portfolios/{deal_id}/documents", headers=headers)
        assert again.json()["exists"] is True
        assert again.json()["document"] == markdown

        # POST message runs DW-2 internal research (tasks even if VDR empty)
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
        assert posted.status_code == 200
        payload = posted.json()
        assert payload["success"] is True
        assert payload["data"]["user"]["role"] == "user"
        assert "market share" in payload["data"]["user"]["content"].lower()
        assistant = payload["data"]["assistant"]
        assert assistant["role"] == "assistant"
        assert isinstance(assistant["tasks"], list)
        assert len(assistant["tasks"]) >= 1
        assert assistant["tasks"][0]["tool"] == "internal"
        assert assistant["tasks"][0]["label"] == "Data room"
        assert assistant["tasks"][0]["status"] == "done"
        assert "Run analysis:" in assistant["tasks"][0]["title"]
        assert "market share" in assistant["content"].lower() or "section" in assistant["content"].lower()
        turn_steps = assistant.get("next_steps") or []
        assert len(turn_steps) == 4
        assert turn_steps[0]["title"] == "Growth Rate"
        assert "messages" not in payload["data"]
        assert payload["data"]["document"]["exists"] is True
        # Empty VDR → section still added explaining no passages
        assert "## " in payload["data"]["document"]["document"]

        # Explicit catalog pick forces the requested capability task
        picked = client.post(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
            json={
                "content": "Research this and add a section to the document: Run Profit Margin analysis.",
                "capability_ids": ["margin_bridge"],
            },
        )
        assert picked.status_code == 200
        tasks = picked.json()["data"]["assistant"]["tasks"]
        assert any("Profit Margin" in t.get("title", "") for t in tasks)

        listed = client.get(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
        )
        assert len(listed.json()["data"]) == 4

        # Files on disk under library/
        root = deals_root() / slug / "library"
        assert (root / "document.md").is_file()
        assert (root / "document_messages.json").is_file()
        assert "Market Share" in Path(root / "document.md").read_text(encoding="utf-8")


def test_documents_post_rejects_empty_content() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        deal_id, _slug = _create_deal(client, headers, name="Empty Msg")
        bad = client.post(
            f"/api/v1/portfolios/{deal_id}/documents/messages",
            headers=headers,
            json={"content": "   "},
        )
        assert bad.status_code == 400
        assert "content" in bad.json()["detail"].lower()


def test_documents_404_for_unknown_deal() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        res = client.get("/api/v1/portfolios/does-not-exist/documents", headers=headers)
        assert res.status_code == 404
