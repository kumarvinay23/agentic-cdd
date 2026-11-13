"""Report checker and review loop.

The checker reads the rendered report against the fact store. It checks
numbers, periods and direction words, then lints the pages. A page that
fails goes back. The report is published only when it scores 8 or more
against the v4 findings and no page was returned.
"""

from __future__ import annotations

import re
from typing import Any

PASS_SCORE = 8
_YEAR = re.compile(r"\b(20\d{2})\b")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_FINDING_NO = re.compile(r"(?m)^\s*\d{1,2}\.\s+")
_FROM_TO = re.compile(r"from\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)")
_DEBUG = re.compile(r"period\(s\) from accounts|databook promoted|CIM gap|0 external risk|Internal prior=", re.I)
_PICTURE = re.compile(r"(?i)(?:\b(logo|brand mark|icon)\b$|\bpicture of\b|\bimage of\b)")
_UP = re.compile(r"\b(grew|risen|rose|increased|higher)\b", re.I)
_DOWN = re.compile(r"\b(fell|declined|decreased|lower|below)\b", re.I)
_HOME = re.compile(r"home|household", re.I)
_PLACE = re.compile(r"location|site", re.I)


def review(report: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    """Score the report and send every weak page back."""
    from agetic_cdd_api.services_fact_repository import cited_facts

    facts = list(facts) + [row for row in cited_facts(report) if row not in facts]
    returned: list[dict[str, Any]] = []
    for page in report.get("pages") or []:
        faults = page_faults(page, facts)
        if faults:
            returned.append({"page_id": str(page.get("page_id") or page.get("title") or "page"), "faults": faults})
    summary_faults = _summary_faults(report, facts)
    score = _score(report, facts)
    publish = score >= PASS_SCORE and not returned and not summary_faults
    return {
        "score": score,
        "returned_pages": returned,
        "errors": [fault for row in returned for fault in row["faults"]] + summary_faults,
        "publish": publish,
    }


def page_faults(page: dict[str, Any], facts: list[dict[str, Any]]) -> list[str]:
    """Lint one page and fact-check its words."""
    text = _page_text(page)
    faults = [
        _debug_fault(text),
        _picture_fault(str(page.get("title") or "")),
        _axis_fault(page),
        _margin_chart_fault(page),
        _bridge_fault(page),
        _stale_fault(page),
        _milestone_fault(text),
        _number_fault(text, facts),
        _period_fault(text, facts),
        _direction_fault(text, facts),
    ]
    return [fault for fault in faults if fault]


def ensure_report_check(output: dict[str, Any]) -> str | None:
    """Hold a rendered report that fails the checker or scores under 8."""
    report = output.get("rendered_report")
    if not isinstance(report, dict):
        return None
    facts = report.get("facts") if isinstance(report.get("facts"), list) else []
    result = review(report, facts)
    output["report_check"] = {
        "score": result["score"],
        "returned_pages": result["returned_pages"],
        "publish": result["publish"],
    }
    if result["publish"]:
        return None
    if result["returned_pages"]:
        page_id = result["returned_pages"][0]["page_id"]
        return f"review returned {page_id}: {result['returned_pages'][0]['faults'][0]}"
    if result["errors"]:
        return result["errors"][0]
    return f"report score {result['score']} is below {PASS_SCORE}"


def _score(report: dict[str, Any], facts: list[dict[str, Any]]) -> int:
    text = _report_text(report)
    checks = (
        _number_fault(text, facts) is None,
        _period_fault(text, facts) is None,
        _direction_fault(text, facts) is None,
        _debug_fault(text) is None,
        all(_picture_fault(str(page.get("title") or "")) is None for page in report.get("pages") or []),
        all(_axis_fault(page) is None for page in report.get("pages") or []),
        all(_margin_chart_fault(page) is None for page in report.get("pages") or []),
        all(_bridge_fault(page) is None for page in report.get("pages") or []),
        _scenario_ok(text),
        _graded_ok(report),
    )
    return sum(1 for check in checks if check)


def _summary_faults(report: dict[str, Any], facts: list[dict[str, Any]]) -> list[str]:
    summary = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    text = "\n".join(str(summary.get(key) or "") for key in ("title", "body") if summary.get(key))
    faults = [_number_fault(text, facts), _period_fault(text, facts), _direction_fault(text, facts), _debug_fault(text)]
    return [fault for fault in faults if fault]


def _scenario_ok(text: str) -> bool:
    if re.search(r"year-to-date|\bytd\b", text, re.I) and not re.search(r"same months", text, re.I):
        return False
    plan = re.search(r"\bplan\b", text, re.I) is not None
    trading = re.search(r"\btrading\b", text, re.I) is not None
    if plan or trading:
        return plan and trading
    return True


def _graded_ok(report: dict[str, Any]) -> bool:
    summary = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    body = str(summary.get("body") or "")
    if "Impact" not in body or "confidence" not in body.lower():
        return False
    for page in report.get("pages") or []:
        finding = page.get("finding") if isinstance(page.get("finding"), dict) else {}
        statement = str(finding.get("statement") or "").strip()
        number = str(finding.get("number") or "")
        title = str(page.get("title") or "")
        if statement and statement not in title:
            return False
        if number and re.search(rf"(^|\s){re.escape(number)}[.)]", title) is None:
            return False
    return True


def _number_fault(text: str, facts: list[dict[str, Any]]) -> str | None:
    cleaned = _YEAR.sub(" ", _FINDING_NO.sub("", text or ""))
    for raw in _NUMBER.findall(cleaned):
        if not _known_number(raw, facts):
            return f"{raw} is not in the fact store"
    return None


def _known_number(raw: str, facts: list[dict[str, Any]]) -> bool:
    value = float(raw)
    for fact in facts:
        target = float(fact.get("value"))
        if abs(value - target) <= 0.05 or abs(value - round(target, 1)) <= 0.05:
            return True
    return False


def _period_fault(text: str, facts: list[dict[str, Any]]) -> str | None:
    periods = {str(fact.get("period")): str(fact.get("basis") or "actual") for fact in facts}
    for match in re.finditer(r"\b(20\d{2})\s+actual\b", text or "", re.I):
        year = match.group(1)
        if year not in periods:
            return f"{year} is not a period in the fact store"
        if periods[year] == "plan":
            return f"{year} is a plan, not an actual"
    for year in _YEAR.findall(text or ""):
        if year not in periods:
            return f"{year} is not a period in the fact store"
    return None


def _direction_fault(text: str, facts: list[dict[str, Any]]) -> str | None:
    for sentence in re.split(r"[.\n]", text or ""):
        mismatch = _from_to_mismatch(sentence)
        if mismatch:
            return mismatch
    return _named_direction(text or "", facts)


def _from_to_mismatch(sentence: str) -> str | None:
    match = _FROM_TO.search(sentence)
    if match is None:
        return None
    start, end = float(match.group(1)), float(match.group(2))
    if _UP.search(sentence) and end < start:
        return "direction word does not match the figures"
    if _DOWN.search(sentence) and end > start:
        return "direction word does not match the figures"
    return None


def _named_direction(text: str, facts: list[dict[str, Any]]) -> str | None:
    revenue = _series_move(facts, "revenue")
    if revenue and re.search(r"revenue grew", text, re.I) and revenue[1] < revenue[0]:
        return "direction word does not match the figures"
    if revenue and re.search(r"revenue fell", text, re.I) and revenue[1] > revenue[0]:
        return "direction word does not match the figures"
    ebitda = _series_move(facts, "ebitda_margin")
    if ebitda and re.search(r"ebitda margin fell", text, re.I) and ebitda[1] > ebitda[0]:
        return "EBITDA margin did not fall"
    gross = _series_move(facts, "gross_margin")
    if gross and re.search(r"gross margin held", text, re.I) and abs(gross[1] - gross[0]) > 0.05:
        return "gross margin did not hold"
    return None


def _series_move(facts: list[dict[str, Any]], name: str) -> tuple[float, float] | None:
    rows = [fact for fact in facts if fact.get("name") == name and fact.get("basis") == "actual"]
    rows.sort(key=lambda fact: str(fact.get("period")))
    if len(rows) < 2:
        return None
    return float(rows[-2]["value"]), float(rows[-1]["value"])


def _debug_fault(text: str) -> str | None:
    if _DEBUG.search(text or ""):
        return "debug text must not reach a page"
    return None


def _picture_fault(title: str) -> str | None:
    if _PICTURE.search(title or ""):
        return "a picture description is the page title"
    return None


def _axis_fault(page: dict[str, Any]) -> str | None:
    chart = page.get("chart") if isinstance(page.get("chart"), dict) else {}
    categories = [str(item) for item in chart.get("categories") or []]
    values = [float(item) for item in chart.get("values") or []]
    if len(categories) != len(values) or len(values) < 2:
        return None
    home = [values[index] for index, label in enumerate(categories) if _HOME.search(label)]
    place = [values[index] for index, label in enumerate(categories) if _PLACE.search(label)]
    if not home or not place:
        return None
    smaller = min(value for value in home + place if value)
    if smaller and max(home + place) > 8 * smaller:
        return "a household price and a location price share one axis"
    return None


def _margin_chart_fault(page: dict[str, Any]) -> str | None:
    chart = page.get("chart") if isinstance(page.get("chart"), dict) else {}
    categories = " ".join(str(item).lower() for item in chart.get("categories") or [])
    if "gross margin" not in categories or "ebitda margin" not in categories:
        return None
    series = chart.get("series") or []
    if len(series) <= 1:
        return "gross margin and EBITDA margin are categories of one series"
    return None


def _bridge_fault(page: dict[str, Any]) -> str | None:
    recipe = str((page.get("comparison") or {}).get("recipe") or "")
    text = _page_text(page)
    if recipe != "bridge" and not re.search(r"plan bridge", text, re.I):
        return None
    chart = page.get("chart") if isinstance(page.get("chart"), dict) else {}
    if str(chart.get("chart_type") or "") != "waterfall":
        return "the plan bridge must be a waterfall"
    return None


def _stale_fault(page: dict[str, Any]) -> str | None:
    match = re.search(r"(?i)margin was .+ in (20\d{2})", str(page.get("title") or ""))
    if match is None:
        return None
    year = int(match.group(1))
    later = [int(item) for item in _YEAR.findall(_page_text(page))]
    if any(item > year for item in later):
        return "the snapshot leads with an earlier year's margin"
    return None


def _milestone_fault(text: str) -> str | None:
    if re.search(r"close series", text or "", re.I) and re.search(r"milestone", text or "", re.I):
        return "an uncompleted plan item is listed as a milestone"
    return None


def _page_text(page: dict[str, Any]) -> str:
    return "\n".join(str(page.get(key) or "") for key in ("title", "body", "subtitle") if str(page.get(key) or "").strip())


def _report_text(report: dict[str, Any]) -> str:
    parts = [_page_text(page) for page in report.get("pages") or []]
    summary = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    parts.append("\n".join(str(summary.get(key) or "") for key in ("title", "body") if summary.get(key)))
    return "\n".join(parts)
