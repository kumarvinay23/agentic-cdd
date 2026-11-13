"""Scores for the agents a Close room actually runs, and for its two reports.

The databook pipeline is the statement reader, the calculation library, the
period engine, the rule checker, and the publisher. Catalog agents that the
room never runs are not scored. CDD and FDD use the published schedule pages.
The report checker is the v4 findings check. A live model call happens only
when ``AGETIC_CDD_CLOSE_SCORES`` is ``1``. A missing model key skips that call.
"""

from __future__ import annotations

import os
from typing import Any

from agetic_cdd_api.services_report_check import review
from agetic_cdd_api.settings import settings

PASS_SCORE = 8
_AGENTS = (
    "statement_reader",
    "calculation_library",
    "period_engine",
    "rule_checker",
    "publisher",
)


class MissingModelKey(RuntimeError):
    """The live score was requested and the model key is empty."""


def score_room(example: dict[str, Any], *, room: str, expected_statements: list[str]) -> dict[str, Any]:
    """Deterministic scores for one room. No model call."""
    expected = set(expected_statements)
    found = set((example.get("statements") or {}))
    source_ok = all(row.get("passed") for row in example.get("source_subtotal_checks") or [])
    derived_ok = all(int(row.get("failed") or 0) == 0 for row in example.get("derived_vs_source") or [])
    rules_ok = all(row.get("passed") for row in example.get("rules") or [])
    contract_ok = not example.get("contract")
    unmapped_ok = not [row for row in example.get("unmapped") or [] if row.get("row_kind") == "LINE"]
    queue_ok = float(example.get("review_queue_ratio") or 0) <= 0.15
    agent_ok = not example.get("agent_chosen")
    completeness = example.get("completeness") or {}
    completeness_ok = "GOV-05" in completeness and all(_number(value) for value in completeness.values())
    statements_ok = expected <= found
    ties_ok = all(key in example for key in ("cash_tie", "debt_tie", "schedule_vs_book"))
    published = bool(example.get("publish_set"))
    reports = _report_scores(example.get("pages") or [])
    agents = {
        "statement_reader": _pack(
            10 if source_ok and contract_ok else 4,
            10 if statements_ok else 4,
            10 if queue_ok and unmapped_ok else 4,
        ),
        "calculation_library": _pack(
            10 if derived_ok and contract_ok else 4,
            10 if statements_ok else 4,
            10 if derived_ok else 4,
        ),
        "period_engine": _pack(
            10 if derived_ok else 4,
            10 if statements_ok else 4,
            10 if derived_ok and unmapped_ok else 4,
        ),
        "rule_checker": _pack(
            10 if rules_ok else 4,
            10 if ties_ok else 4,
            10 if rules_ok and agent_ok else 4,
        ),
        "publisher": _pack(
            10 if agent_ok else 4,
            10 if completeness_ok else 4,
            10 if agent_ok and completeness_ok and published else 4,
        ),
    }
    return {
        "room": room,
        "agents": agents,
        "reports": reports,
        "agent_selected": list(example.get("agent_chosen") or []),
    }


def live_scores(packet: dict[str, Any]) -> dict[str, Any] | None:
    """Score with the model only when Close scores are requested.

    A missing model key does not call the model. That skip is a failure only
    when ``AGETIC_CDD_CLOSE_SCORES`` is ``1``.
    """
    if os.environ.get("AGETIC_CDD_CLOSE_SCORES", "").strip() != "1":
        return None
    if not settings.gemini_api_key.strip():
        raise MissingModelKey("model key is missing")
    from agetic_cdd_api.services_gemini import generate_json

    result = generate_json(
        system=(
            "Score each agent on quality, coverage, and IC readiness from 0 to 10. "
            "Return JSON with an agents object. Use only the packet. Do not invent figures."
        ),
        user=str(packet),
        temperature=0,
    )
    if result is None:
        raise MissingModelKey("live agent call returned nothing")
    return result


def _report_scores(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """CDD and FDD are the same published pages, scored by the v4 checker."""
    report = _checker_report(pages)
    scored = {}
    for kind in ("cdd", "fdd"):
        result = review(report, report["facts"])
        scored[kind] = {
            "score": int(result["score"]),
            "publish": bool(result["publish"]),
            "returned_pages": [row["page_id"] for row in result["returned_pages"]],
        }
    return scored


def _checker_report(pages: list[dict[str, Any]]) -> dict[str, Any]:
    facts: list[dict[str, Any]] = []
    checker_pages: list[dict[str, Any]] = []
    for index, page in enumerate(pages, start=1):
        figure = _lead(page.get("figures") or [])
        if figure is None:
            continue
        shown = _plain(figure["value"])
        facts.append({
            "name": _label(figure.get("concept_id")),
            "value": float(shown),
            "period": str(figure.get("period_end") or "")[:4],
            "basis": "actual",
        })
        statement = f"{_label(figure.get('concept_id'))} is {shown}."
        comparison = page.get("comparison") if isinstance(page.get("comparison"), dict) else {}
        checker_pages.append({
            "page_id": str(page.get("schedule_id") or index),
            "title": f"{index}. {statement}",
            "body": "",
            "finding": {
                "number": index,
                "statement": statement,
                "impact": "high",
                "confidence": "high",
            },
            "comparison": comparison,
            "chart": _chart(page, comparison),
        })
    for figure in _all_figures(pages):
        shown = _plain(figure["value"])
        facts.append({
            "name": _label(figure.get("concept_id")),
            "value": float(shown),
            "period": str(figure.get("period_end") or "")[:4],
            "basis": "actual",
        })
    title = checker_pages[0]["title"] if checker_pages else ""
    return {
        "pages": checker_pages,
        "facts": facts,
        "executive_summary": {"title": title, "body": "Impact high, confidence high."},
    }


def _chart(page: dict[str, Any], comparison: dict[str, Any]) -> dict[str, Any]:
    if comparison.get("recipe") != "bridge" and comparison.get("chart") != "waterfall":
        return {}
    series = [figure for figure in _all_figures([page]) if figure.get("value") is not None]
    if len(series) < 2:
        return {"chart_type": "waterfall", "categories": ["Start", "End"], "values": []}
    return {
        "chart_type": "waterfall",
        "categories": ["Start", "End"],
        "values": [float(_plain(series[0]["value"])), float(_plain(series[-1]["value"]))],
    }


def _lead(figures: list[dict[str, Any]]) -> dict[str, Any] | None:
    for figure in figures:
        if figure.get("value") is not None:
            return figure
    return None


def _all_figures(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for page in pages:
        rows.extend(figure for figure in page.get("figures") or [] if figure.get("value") is not None)
    return rows


def _label(concept_id: Any) -> str:
    tail = str(concept_id or "figure").split(".")[-1].replace("_", " ")
    return tail[:1].upper() + tail[1:] if tail else "Figure"


def _plain(value: Any) -> str:
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.2f}".rstrip("0").rstrip(".")


def _pack(quality: int, coverage: int, ic_readiness: int) -> dict[str, int]:
    return {"quality": quality, "coverage": coverage, "ic_readiness": ic_readiness}


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def scores_pass(payload: dict[str, Any]) -> list[str]:
    """Reasons a stored score file is below the Close bar. Empty means it passes."""
    faults = []
    agents = payload.get("agents") or {}
    for name in _AGENTS:
        row = agents.get(name) or {}
        for axis in ("quality", "coverage", "ic_readiness"):
            score = row.get(axis)
            if not isinstance(score, int) or score < PASS_SCORE:
                faults.append(f"{name} {axis} is {score}")
    for kind in ("cdd", "fdd"):
        report = (payload.get("reports") or {}).get(kind) or {}
        if int(report.get("score") or 0) < PASS_SCORE or report.get("returned_pages"):
            faults.append(f"{kind} report score {report.get('score')}")
    if payload.get("agent_selected"):
        faults.append("an agent number is selected")
    return faults
