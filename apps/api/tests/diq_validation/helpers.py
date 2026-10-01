"""Shared helpers for DIQ Document Workspace validation sequence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agetic_cdd_api.document_topics import (
    covered_topic_keys,
    parse_section_headings,
    topic_key_for_text,
)

# Standard DIQ demo sequence (Test5-shaped prompts).
DIQ_PROMPT_SEQUENCE: tuple[tuple[str, str], ...] = (
    (
        "market_share",
        "Research this and add a section to the document: What is {company}'s market share?",
    ),
    (
        "growth_rate",
        "Research this and add a section to the document: "
        "What is the revenue growth rate of {company}?",
    ),
    (
        "competitor",
        "Research this and add a section to the document: "
        "Who are the main competitors of {company}?",
    ),
)

_TEST5_LIBRARY = (
    Path(__file__).resolve().parents[2] / "data" / "deals" / "test5" / "library" / "documents"
)


@dataclass
class TurnCheck:
    step: str
    prompt: str
    passed: bool
    notes: list[str] = field(default_factory=list)


@dataclass
class DiqValidationReport:
    deal_id: str
    company: str
    document_count: int
    chunk_indexed: bool
    turns: list[TurnCheck] = field(default_factory=list)
    duplicate_topics: list[str] = field(default_factory=list)
    decision_chain_count: int = 0
    passed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_id": self.deal_id,
            "company": self.company,
            "document_count": self.document_count,
            "chunk_indexed": self.chunk_indexed,
            "duplicate_topics": self.duplicate_topics,
            "decision_chain_count": self.decision_chain_count,
            "passed": self.passed,
            "turns": [
                {"step": t.step, "prompt": t.prompt, "passed": t.passed, "notes": t.notes}
                for t in self.turns
            ],
        }


def load_test5_vdr_files() -> list[tuple[str, str]]:
    """Load Test5 library document text as (filename, body) pairs for VDR upload."""
    if not _TEST5_LIBRARY.is_dir():
        return _fallback_vdr_files()
    out: list[tuple[str, str]] = []
    for path in sorted(_TEST5_LIBRARY.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        filename = str(payload.get("filename") or path.stem)
        text = str(payload.get("text") or payload.get("excerpt") or "")
        if text.strip():
            # Upload as .txt so tests stay fast and deterministic.
            txt_name = Path(filename).with_suffix(".txt").name
            out.append((txt_name, text))
    return out or _fallback_vdr_files()


def _fallback_vdr_files() -> list[tuple[str, str]]:
    market = (
        "Market Competition Analysis for Test5. Test5 holds ~32% market share in India's E2W "
        "segment as of FY2024E. TVS iQube holds 18% and Ather Energy holds 12%.\n"
    )
    growth = (
        "Financial profile for Test5. Revenue grew from INR 2.4B to INR 5.1B. "
        "Revenue growth rate YoY reached 112 percent in FY2024.\n"
    )
    thesis = "Investment thesis for Test5. Technology-first positioning and vertical integration.\n"
    return [
        ("11_Market_Competition_Analysis.txt", market),
        ("05_Financial_Due_Diligence.txt", growth),
        ("03_Investment_Thesis.txt", thesis),
    ]


def duplicate_topic_keys(markdown: str) -> list[str]:
    """Return topic keys that appear in more than one ## section."""
    seen: dict[str, str] = {}
    dups: list[str] = []
    for heading in parse_section_headings(markdown):
        key = topic_key_for_text(heading) or normalize_heading_key(heading)
        if key in seen:
            dups.append(key)
        else:
            seen[key] = heading
    return dups


def normalize_heading_key(heading: str) -> str:
    return re.sub(r"\s+", " ", heading.strip().lower())


def parse_chart_payloads(markdown: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in markdown.splitlines():
        raw = line.strip()
        if not raw.startswith("<!-- cdd:chart "):
            continue
        payload = raw.replace("<!-- cdd:chart ", "").replace(" -->", "")
        out.append(json.loads(payload))
    return out


def assert_turn_contract(
    *,
    step: str,
    prompt: str,
    assistant: dict[str, Any],
    document: str,
    user_prompts: list[str] | None = None,
    expect_chart: bool = False,
) -> TurnCheck:
    notes: list[str] = []
    ok = True
    all_prompts = list(user_prompts or [prompt])

    if not assistant.get("content"):
        ok = False
        notes.append("missing assistant content")
    tasks = assistant.get("tasks") or []
    if not tasks:
        ok = False
        notes.append("missing tasks")
    elif not any(t.get("status") == "done" for t in tasks):
        ok = False
        notes.append("no completed tasks")
    if not assistant.get("sources"):
        notes.append("warning: no flattened sources on assistant turn")

    next_steps = assistant.get("next_steps") or []
    if len(next_steps) != 4:
        ok = False
        notes.append(f"expected 4 next_steps, got {len(next_steps)}")
    else:
        titles = [s.get("title") for s in next_steps]
        if len(set(titles)) != len(titles):
            ok = False
            notes.append(f"duplicate next_step titles: {titles}")

    covered = covered_topic_keys(document_markdown=document, user_prompts=all_prompts)
    for step_row in next_steps:
        title = str(step_row.get("title") or "")
        from agetic_cdd_api.document_topics import topic_keys_in_text

        step_topics = topic_keys_in_text(title)
        overlap = step_topics & covered
        if overlap:
            ok = False
            notes.append(f"next_step '{title}' repeats covered topics {sorted(overlap)}")

    if "## Sources" not in document:
        ok = False
        notes.append("document missing ## Sources")

    if expect_chart and "[[CHART:" not in document:
        ok = False
        notes.append("expected [[CHART: …]] marker in document")

    if expect_chart:
        charts = parse_chart_payloads(document)
        if not charts:
            ok = False
            notes.append("expected cdd:chart JSON payload")
        elif not charts[-1].get("title"):
            ok = False
            notes.append("chart missing title")

    if step == "market_share" and tasks:
        if not any(t.get("tool") == "internal" for t in tasks):
            ok = False
            notes.append("market share turn expected internal data-room task")

    if step == "competitor" and tasks:
        if not any(t.get("tool") == "web" for t in tasks):
            notes.append("warning: competitor turn has no web task (web may be stubbed offline)")

    return TurnCheck(step=step, prompt=prompt, passed=ok, notes=notes)
