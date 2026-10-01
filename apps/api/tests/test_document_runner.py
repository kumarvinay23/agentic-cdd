"""DW-2 document research runner tests."""

from __future__ import annotations

import re
import secrets
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from agetic_cdd_api.app import app
from agetic_cdd_api.services_document_runner import (
    merge_document_section,
    resolve_capabilities,
    select_capabilities,
    _section_heading,
)


def _headers(client: TestClient) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@ageticcdd.com", "password": "adminpass"},
    )
    token = res.json()["data"]["tokens"]["accessToken"]
    return {"Authorization": f"Bearer {token}"}


def test_select_capabilities_market_share() -> None:
    caps = select_capabilities("What is Ola Electric's market share in EV 2W?")
    ids = [c["id"] for c in caps]
    assert "mkt_marimekko_segments" in ids
    assert all(c.get("src") != "web" for c in caps)


def test_select_capabilities_growth() -> None:
    caps = select_capabilities("What is the revenue growth rate of the company?")
    ids = [c["id"] for c in caps]
    assert "growth_trend" in ids


def test_resolve_capabilities_explicit_ids() -> None:
    internal, web = resolve_capabilities(
        "generic prompt",
        capability_ids=["margin_bridge", "gx_x_market_funnel"],
    )
    assert [c["id"] for c in internal] == ["margin_bridge"]
    assert [c["id"] for c in web] == ["gx_x_market_funnel"]


def test_section_heading_strips_prefix() -> None:
    class Fake:
        name = "Test1"
        company = "Ola Electric"

    heading = _section_heading(
        "Research this and add a section to the document: What is Ola Electric's market share?",
        Fake(),  # type: ignore[arg-type]
    )
    assert "market share" in heading.lower()
    assert "Research this" not in heading


def test_merge_document_section_appends_sources() -> None:
    base = (
        "# Deal - Commercial Due Diligence\n\n"
        "Intro.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    md, cite_map = merge_document_section(
        base,
        heading="Market Share",
        body="- Share rose to 32% [1]\n",
        source_titles=["11_Market_Competition_Analysis.pdf"],
    )
    assert "## Market Share" in md
    assert "**[1]** (data room) 11_Market_Competition_Analysis.pdf" in md
    assert cite_map["11_Market_Competition_Analysis.pdf"] == 1
    assert md.index("## Market Share") < md.index("## Sources")


def test_build_cite_map_continues_existing_numbers() -> None:
    from agetic_cdd_api.services_document_runner import build_cite_map, flatten_message_sources

    base = (
        "# Deal\n\n"
        "## Sources\n\n"
        "**[1]** (data room) prior.pdf\n"
    )
    cite_map = build_cite_map(base, ["prior.pdf", "new.pdf"])
    assert cite_map["prior.pdf"] == 1
    assert cite_map["new.pdf"] == 2

    flat = flatten_message_sources(
        [{"title": "new.pdf", "snippet": "x"}, {"title": "missing.pdf", "snippet": "y"}],
        cite_map=cite_map,
    )
    assert [row["id"] for row in flat] == [2]
    assert all(row["title"] != "missing.pdf" for row in flat)


def test_run_research_single_pass_no_duplicate_section() -> None:
    from agetic_cdd_api.services_document_runner import run_document_research

    class FakeDeal:
        id = "d1"
        name = "Deal"
        company = "Acme Inc."
        slug = "fake-slug-no-vdr"

    base = (
        "# Deal - Commercial Due Diligence\n\n"
        "Ask the copilot.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n\n"
        "**[1]** (data room) prior.pdf\n"
    )
    result = run_document_research(
        FakeDeal(),  # type: ignore[arg-type]
        prompt="Research this and add a section to the document: What is Acme Inc. market share?",
        document_markdown=base,
        db=None,
    )
    md = result["document"]
    assert md.count("## Acme Inc. market share") == 1 or md.count("## ") >= 2
    # Exactly one new research heading insertion for this prompt topic
    heading = result["heading"]
    assert md.count(f"## {heading}") == 1
    assert md.count("## Sources") == 1


def test_abbrev_sentence_split_keeps_inc() -> None:
    from agetic_cdd_api.services_document_runner import _split_sentences

    text = (
        "Acme Inc. holds 32 percent market share in the segment. "
        "Rivals include Beta Corp. and Gamma Ltd. in India."
    )
    parts = _split_sentences(text)
    assert any("Acme Inc. holds 32" in p for p in parts)
    assert not any(p.strip() == "holds 32 percent market share in the segment." for p in parts)


def test_post_message_with_vdr_retrieves_passages() -> None:
    market_text = (
        "Market Competition Analysis for Ola Electric. "
        "Ola Electric holds the leading market share position in India's E2W segment "
        "with a market share of 32 percent as of FY2024E showing a strong gain trend. "
        "TVS iQube holds 18 percent and Ather Energy holds 12 percent. "
        "The competitive landscape remains intense across EV two-wheelers.\n"
    )
    with TestClient(app) as client:
        headers = _headers(client)
        slug = f"dw2-{secrets.token_hex(4)}"
        created = client.post(
            "/api/v1/deals",
            headers=headers,
            json={
                "name": "DW2 Deal",
                "slug": slug,
                "industry": "ev",
                "company": "Ola Electric",
            },
        )
        assert created.status_code == 201
        deal_id = created.json()["data"]["id"]

        upload = client.post(
            f"/api/v1/portfolios/{deal_id}/cdd/vdr/upload",
            headers=headers,
            files={
                "file": (
                    "11_Market_Competition_Analysis.txt",
                    BytesIO(market_text.encode("utf-8")),
                    "text/plain",
                )
            },
        )
        assert upload.status_code == 200

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
        assert posted.status_code == 200, posted.text
        data = posted.json()["data"]
        assistant = data["assistant"]
        assert assistant["tasks"]
        task = assistant["tasks"][0]
        assert task["status"] == "done"
        assert task["tool"] == "internal"
        assert "Mkt Marimekko" in task["title"] or "Marimekko" in task["title"]
        assert task["detail"]["sources"], "expected retrieved VDR sources"
        assert any(
            "Market_Competition" in (s.get("title") or "")
            for s in task["detail"]["sources"]
        )
        assert assistant["sources"]
        # Synthesis: fact-bearing chat + prose section (not raw bullets).
        assert "32" in assistant["content"]
        assert "I added a new section" in assistant["content"]
        doc = data["document"]["document"]
        assert "market share" in doc.lower()
        assert "11_Market_Competition_Analysis.txt" in doc
        assert "**[1]**" in doc or "[1]" in doc
        section = doc.split("## Sources")[0]
        assert not re.search(r"(?m)^-\s+", section), "expected prose, not bullet dump"
        assert "32" in section
        assert "[[CHART: Market Share Trend]]" in section
        assert "<!-- cdd:chart" in section

        # Persisted on disk
        from agetic_cdd_api.services_deals import deals_root

        lib = deals_root() / slug / "library"
        assert (lib / "document.md").is_file()
        assert "32" in Path(lib / "document.md").read_text(encoding="utf-8")


def test_synthesize_section_prose_and_assistant() -> None:
    from agetic_cdd_api.services_document_synthesis import synthesize_section

    class Fake:
        name = "Test Deal"
        company = "Ola Electric"

    sources = [
        {
            "title": "11_Market_Competition_Analysis.pdf",
            "snippet": (
                "Ola Electric holds the leading market share position in India's E2W segment "
                "with a market share of 32% as of FY2024E, showing a strong gain trend."
            ),
            "passages": [
                (
                    "Ola Electric holds the leading market share position in India's E2W segment "
                    "with a market share of 32% as of FY2024E, showing a strong gain trend."
                ),
                (
                    "The Indian electric two-wheeler market recorded sales of approximately "
                    "950,000 units in FY2024, representing about 6% EV penetration."
                ),
            ],
        },
        {
            "title": "03_Investment_Thesis.pdf",
            "snippet": "TAM / SAM / SOM Analysis insight snapshot for market sizing.",
            "passages": [
                "EV penetration in the two-wheeler segment stood at about 6% in FY2024."
            ],
        },
    ]
    cite_map = {
        "11_Market_Competition_Analysis.pdf": 2,
        "03_Investment_Thesis.pdf": 1,
    }
    out = synthesize_section(
        prompt="What is Ola Electric's market share in EV 2W?",
        heading="Market Share of Ola Electric in EV 2W",
        sources=sources,
        cite_map=cite_map,
        deal=Fake(),
        tasks=[{"title": "Run analysis: Mkt Marimekko Segments"}],
    )
    assert "32%" in out["body"] or "32" in out["body"]
    assert "[2]" in out["body"]
    assert not out["body"].lstrip().startswith("-")
    assert "32" in out["assistant"]
    assert "Market Share of Ola Electric" in out["assistant"]
    assert "Mkt Marimekko" in out["assistant"]


def test_llm_synthesize_uses_gemini_when_mocked(monkeypatch) -> None:
    from agetic_cdd_api import services_document_synthesis as syn

    class Fake:
        name = "Deal"
        company = "Ola Electric"

    sources = [
        {
            "title": "11_Market_Competition_Analysis.pdf",
            "snippet": "Ola Electric holds 32% market share as of FY2024E with a strong gain trend.",
            "passages": [
                "Ola Electric holds 32% market share as of FY2024E with a strong gain trend."
            ],
        }
    ]
    cite_map = {"11_Market_Competition_Analysis.pdf": 2}

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        lambda **kwargs: {
            "body": (
                "Ola Electric holds the leading market share position in India's E2W "
                "segment at 32% as of FY2024E, with a strong gain trend [2]."
            ),
            "assistant": (
                "I added a section on market share. Ola Electric's EV 2W share is "
                "32% as of FY2024E [2]."
            ),
        },
    )

    out = syn.synthesize_section(
        prompt="What is Ola Electric's market share?",
        heading="Market share",
        sources=sources,
        cite_map=cite_map,
        deal=Fake(),
        tasks=[{"title": "Run analysis: Mkt Marimekko Segments"}],
    )
    assert "32%" in out["body"]
    assert "[2]" in out["body"]
    assert "32%" in out["assistant"]
    assert not out["body"].lstrip().startswith("-")


def test_llm_synthesize_falls_back_when_gemini_fails(monkeypatch) -> None:
    from agetic_cdd_api import services_document_synthesis as syn

    class Fake:
        name = "Deal"
        company = "Ola Electric"

    sources = [
        {
            "title": "11_Market_Competition_Analysis.pdf",
            "snippet": (
                "Ola Electric holds the leading market share position with a market "
                "share of 32% as of FY2024E, showing a strong gain trend."
            ),
            "passages": [
                (
                    "Ola Electric holds the leading market share position with a market "
                    "share of 32% as of FY2024E, showing a strong gain trend."
                )
            ],
        }
    ]
    cite_map = {"11_Market_Competition_Analysis.pdf": 1}

    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.gemini_configured",
        lambda: True,
    )
    monkeypatch.setattr(
        "agetic_cdd_api.services_gemini.generate_json",
        lambda **kwargs: None,
    )

    out = syn.synthesize_section(
        prompt="What is Ola Electric's market share?",
        heading="Market share",
        sources=sources,
        cite_map=cite_map,
        deal=Fake(),
        tasks=[],
    )
    assert "32" in out["body"]
    assert "[1]" in out["body"]


def test_sanitize_cites_drops_unknown() -> None:
    from agetic_cdd_api.services_document_synthesis import _sanitize_cites

    text = "Share is 32% [2] and bogus [99] plus [1]."
    assert _sanitize_cites(text, {1, 2}) == "Share is 32% [2] and bogus plus [1]."

    from agetic_cdd_api.services_document_synthesis import synthesize_section

    class Fake:
        name = "Deal"
        company = "Ola Electric"

    tableish = (
        "Market Share Trend Company FY2022 FY2023 FY2024E Trend "
        "Ola Electric 8% 27% 32% Strong Gain "
        "TVS iQube 12% 17% 18% Steady Growth "
        "Ather Energy 18% 14% 12% Losing Share"
    )
    out = synthesize_section(
        prompt="What is Ola Electric's market share?",
        heading="Ola Electric's market share",
        sources=[
            {
                "title": "11_Market_Competition_Analysis.pdf",
                "snippet": tableish[:200],
                "passages": [tableish],
            }
        ],
        cite_map={"11_Market_Competition_Analysis.pdf": 1},
        deal=Fake(),
        tasks=[{"title": "Run analysis: Mkt Marimekko Segments"}],
    )
    assert "32%" in out["body"]
    assert "Ola Electric" in out["body"]
    assert "Strong Gain" in out["body"] or "strong gain" in out["body"].lower()
    assert "[1]" in out["body"]
    assert "32%" in out["assistant"] or "32" in out["assistant"]

    from agetic_cdd_api.services_document_synthesis import synthesize_section

    class Fake:
        name = "Deal"
        company = None

    out = synthesize_section(
        prompt="What is market share?",
        heading="Market share",
        sources=[],
        cite_map={},
        deal=Fake(),
        tasks=[],
    )
    assert "No supporting passages" in out["body"]
    assert "no supporting passages" in out["assistant"].lower()


def test_source_footer_includes_chunk_citation_hint() -> None:
    from agetic_cdd_api.services_document_runner import (
        _format_source_footer_line,
        merge_document_section,
    )

    base = (
        "# Deal - Commercial Due Diligence\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    meta = {
        "origin": "internal",
        "section_label": "Competitive Landscape",
        "chunk_index": 2,
        "chunk_ids": ["11_Market.pdf::2"],
    }
    line = _format_source_footer_line(1, "11_Market_Competition_Analysis.pdf", meta)
    assert "Competitive Landscape" in line
    assert "chunk 3" in line

    md, _ = merge_document_section(
        base,
        heading="Market Share",
        body="Share is 32% [1].\n",
        source_titles=["11_Market_Competition_Analysis.pdf"],
        source_meta={"11_Market_Competition_Analysis.pdf": meta},
    )
    assert "Competitive Landscape · chunk 3" in md


def test_flatten_message_sources_includes_chunk_fields() -> None:
    from agetic_cdd_api.services_document_runner import flatten_message_sources

    flat = flatten_message_sources(
        [
            {
                "origin": "internal",
                "title": "11_Market.pdf",
                "snippet": "32% share",
                "chunk_ids": ["11_Market.pdf::1"],
                "citations": [{"chunk_id": "11_Market.pdf::1", "chunk_index": 1, "label": "Share trend"}],
                "section_label": "Share trend",
                "chunk_index": 1,
            }
        ],
        cite_map={"11_Market.pdf": 1},
    )
    assert flat[0]["section_label"] == "Share trend"
    assert flat[0]["chunk_index"] == 1
    assert flat[0]["chunk_ids"] == ["11_Market.pdf::1"]


def test_register_source_disambiguates_duplicate_titles() -> None:
    from agetic_cdd_api.services_document_runner import _register_source, _source_meta_map

    registry: dict = {}
    _register_source(
        registry,
        {"origin": "internal", "title": "example.com", "snippet": "internal hit"},
    )
    _register_source(
        registry,
        {"origin": "web", "title": "example.com", "url": "https://example.com", "snippet": "web hit"},
    )
    assert len(registry) == 2
    assert "example.com" in registry
    assert "example.com (web)" in registry
    meta = _source_meta_map(list(registry.values()))
    assert meta["example.com"]["origin"] == "internal"
    assert meta["example.com (web)"]["origin"] == "web"


def test_finalize_charts_empty_caps_and_sources() -> None:
    from agetic_cdd_api.services_document_runner import _finalize_charts

    charts = _finalize_charts(
        [],
        prompt="What is Ola Electric's market share?",
        caps=[],
        sources=[],
    )
    assert len(charts) == 1
    assert charts[0]["title"] == "Market Share Trend"
    assert charts[0]["series"] == []
    assert charts[0]["placeholder"] is True
    assert charts[0]["type"] == "bar"
