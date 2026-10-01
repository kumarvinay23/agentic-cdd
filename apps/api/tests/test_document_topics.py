"""Tests for document topic deduplication."""

from __future__ import annotations

from agetic_cdd_api.document_topics import covered_topic_keys
from agetic_cdd_api.services_document_runner import merge_document_section
from agetic_cdd_api.services_documents import build_contextual_next_steps


class FakeDeal:
    name = "Test4"
    company = "Test4"


def test_next_steps_exclude_covered_market_share() -> None:
    doc = (
        "# Test4 - Commercial Due Diligence\n\n"
        "## Test4's market share\n"
        "Ola Electric holds 32% share.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    prompts = [
        "Research this and add a section to the document: What is Test4's market share?",
    ]
    steps = build_contextual_next_steps(
        FakeDeal(),  # type: ignore[arg-type]
        last_prompt=prompts[0],
        document_markdown=doc,
        user_prompts=prompts,
    )
    titles = [s["title"] for s in steps]
    assert "Market Share" not in titles
    assert len(steps) == 4
    assert titles[0] == "Growth Rate"


def test_next_steps_exclude_after_growth_rate() -> None:
    doc = (
        "# Test4 - Commercial Due Diligence\n\n"
        "## Test4's market share\n"
        "Share data.\n\n"
        "## The revenue growth rate of Test4\n"
        "Growth data.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    prompts = [
        "Research this and add a section to the document: What is Test4's market share?",
        "Research this and add a section to the document: What is the revenue growth rate of Test4?",
    ]
    steps = build_contextual_next_steps(
        FakeDeal(),  # type: ignore[arg-type]
        last_prompt=prompts[1],
        document_markdown=doc,
        user_prompts=prompts,
    )
    titles = [s["title"] for s in steps]
    assert "Market Share" not in titles
    assert "Growth Rate" not in titles


def test_merge_document_section_replaces_same_topic() -> None:
    base = (
        "# Deal - Commercial Due Diligence\n\n"
        "## Test4's market share\n"
        "Old stale content about share.\n\n"
        "## Sources\n\n"
        "<!-- cdd:sources -->\n"
    )
    md, _cite_map = merge_document_section(
        base,
        heading="Test4's market share",
        body="Updated share narrative with 40% evidence [1].\n",
        source_titles=["11_Market_Competition_Analysis.pdf"],
    )
    assert md.count("## Test4's market share") == 1
    assert "Updated share narrative" in md
    assert "Old stale content" not in md


def test_covered_topic_keys_from_headings_and_prompts() -> None:
    covered = covered_topic_keys(
        document_markdown="## The main competitors of Test4\nBody.",
        user_prompts=[
            "Research this and add a section to the document: What is Test4's market share?"
        ],
    )
    assert "market_share" in covered
    assert "competitor" in covered
