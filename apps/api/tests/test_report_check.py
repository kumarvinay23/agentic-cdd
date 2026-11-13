"""Seeded v2 errors are caught. A v4 report scores 8 or more."""

from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.services_report_check import review

# Regression answer key. v2 rows are errors the checker must catch.
# v4 rows are the findings a passing report has to show.
V2_ERRORS = (
    "number",
    "period",
    "plan_as_actual",
    "direction",
    "debug",
    "picture",
    "axis",
    "margin_series",
    "bridge",
    "stale_margin",
    "milestone",
)
V4_FINDINGS = (
    "same_months",
    "trading_and_plan",
    "waterfall",
    "graded_summary",
    "finding_title",
    "margin_direction",
)


def _facts(prior: float, latest: float, plan: float) -> list[dict]:
    return [
        {"name": "revenue", "value": prior, "period": "2024", "basis": "actual"},
        {"name": "revenue", "value": latest, "period": "2025", "basis": "actual"},
        {"name": "gross_margin", "value": 30, "period": "2024", "basis": "actual"},
        {"name": "gross_margin", "value": 30, "period": "2025", "basis": "actual"},
        {"name": "ebitda_margin", "value": 10, "period": "2024", "basis": "actual"},
        {"name": "ebitda_margin", "value": 4, "period": "2025", "basis": "actual"},
        {"name": "plan", "value": plan, "period": "2030", "basis": "plan"},
    ]


def _v4_report(prior: float, latest: float, plan: float) -> dict:
    revenue = f"Revenue fell from {prior:g} to {latest:g}."
    margin = "Gross margin held and EBITDA margin fell."
    bridge = f"The plan bridge runs from {latest:g} to {plan:g}."
    context = (
        "Year-to-date is compared with the same months of the prior year. "
        "The trading case and the plan are shown together."
    )
    return {
        "facts": _facts(prior, latest, plan),
        "pages": [
            {
                "page_id": "P1",
                "title": f"1. {revenue}",
                "body": context,
                "finding": {"number": 1, "statement": revenue, "impact": "high", "confidence": "high"},
                "chart": {"chart_type": "line", "categories": ["2024", "2025"], "values": [prior, latest]},
            },
            {
                "page_id": "P2",
                "title": f"2. {margin}",
                "body": margin,
                "finding": {"number": 2, "statement": margin, "impact": "medium", "confidence": "medium"},
                "chart": {
                    "chart_type": "line",
                    "categories": ["2024", "2025"],
                    "series": [
                        {"name": "Gross margin", "values": [30, 30]},
                        {"name": "EBITDA margin", "values": [10, 4]},
                    ],
                },
            },
            {
                "page_id": "P3",
                "title": f"3. {bridge}",
                "body": "The plan bridge is the step from the latest actual to the plan.",
                "finding": {"number": 3, "statement": bridge, "impact": "medium", "confidence": "low"},
                "comparison": {"recipe": "bridge"},
                "chart": {"chart_type": "waterfall", "categories": ["Actual", "Plan"], "values": [latest, plan]},
            },
        ],
        "executive_summary": {
            "title": f"1. {revenue}",
            "body": (
                f"1. {revenue} Impact high, confidence high.\n"
                f"2. {margin} Impact medium, confidence medium.\n"
                f"3. {bridge} Impact low, confidence low."
            ),
        },
    }


def _seed(kind: str) -> tuple[dict, list[dict], str]:
    facts = _facts(10, 8, 14)
    page: dict = {"page_id": "P1", "title": "1. Revenue fell from 10 to 8.", "body": "", "chart": {}}
    expect = {
        "number": ("Revenue was 99.", "not in the fact store"),
        "period": ("Revenue 2020 actual was 8.", "not a period"),
        "plan_as_actual": ("2030 actual revenue was 14.", "is a plan"),
        "direction": ("Revenue grew from 10 to 8.", "direction word"),
        "debug": ("Databook promoted · 4 line(s).", "debug text"),
        "picture": ("", "picture description"),
        "axis": ("", "share one axis"),
        "margin_series": ("", "one series"),
        "bridge": ("The plan bridge is a column.", "waterfall"),
        "stale_margin": ("", "earlier year"),
        "milestone": ("Close Series B is a completed milestone.", "plan item"),
    }
    body, needle = expect[kind]
    page["body"] = body
    if kind == "picture":
        page["title"] = "River Haul logo"
    if kind == "axis":
        page["chart"] = {"categories": ["Household monthly", "Location monthly"], "values": [80, 8]}
    if kind == "margin_series":
        page["chart"] = {"categories": ["Gross margin", "EBITDA margin"], "values": [30, 4]}
    if kind == "bridge":
        page["comparison"] = {"recipe": "bridge"}
        page["chart"] = {"chart_type": "column", "categories": ["Actual", "Plan"], "values": [8, 14]}
    if kind == "stale_margin":
        page["title"] = "EBITDA margin was down in 2023"
        page["body"] = "2025 is the latest year on the page."
    return {"pages": [page], "executive_summary": {"title": "", "body": ""}}, facts, needle


def test_every_seeded_v2_error_is_caught() -> None:
    for kind in V2_ERRORS:
        report, facts, needle = _seed(kind)
        result = review(report, facts)
        assert result["publish"] is False
        assert any(needle in error for error in result["errors"]), kind
        assert result["returned_pages"]


def test_v4_report_scores_at_least_8_on_every_deal() -> None:
    deals = ((10, 8, 14), (6, 5, 9), (12, 9, 15))
    for prior, latest, plan in deals:
        report = _v4_report(prior, latest, plan)
        result = review(report, report["facts"])
        assert result["score"] >= 8
        assert result["publish"] is True
        assert result["returned_pages"] == []
        blob = " ".join(page["title"] + page["body"] for page in report["pages"])
        blob += report["executive_summary"]["body"]
        assert "same months" in blob
        assert "trading case" in blob and "plan" in blob
        assert report["pages"][2]["chart"]["chart_type"] == "waterfall"
        assert "Impact" in blob and "confidence" in blob
        assert report["pages"][0]["finding"]["statement"] in report["pages"][0]["title"]
        assert "Gross margin held and EBITDA margin fell" in blob


def test_review_loop_sends_a_weak_page_back() -> None:
    report = _v4_report(10, 8, 14)
    report["pages"][0]["body"] = "Revenue was 99. Year-to-date is compared with the same months of the prior year."
    first = review(report, report["facts"])
    assert first["publish"] is False
    assert first["returned_pages"][0]["page_id"] == "P1"

    report["pages"][0]["body"] = (
        "Year-to-date is compared with the same months of the prior year. "
        "The trading case and the plan are shown together."
    )
    second = review(report, report["facts"])
    assert second["score"] >= 8
    assert second["publish"] is True

    held = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "rendered_report": {
                "facts": _facts(10, 8, 14),
                "pages": [{"page_id": "P1", "title": "1. Revenue fell from 10 to 8.", "body": "Revenue was 99."}],
                "executive_summary": {"title": "", "body": ""},
            },
        },
    )
    assert held["status"] == "needs_repair"
    assert "review returned" in held["error"]

    published = prepare_completion(
        "revenue_quality",
        {"status": "completed", "sources": ["Accounts.pdf"], "rendered_report": _v4_report(10, 8, 14)},
    )
    assert published["status"] == "completed"
    assert published["report_check"]["score"] >= 8
    assert published["report_check"]["publish"] is True
