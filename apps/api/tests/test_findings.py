"""Every planned page is present, every title states its finding, and the summary is last."""

import pytest

from agetic_cdd_api.agent_module_registry import prepare_completion
from agetic_cdd_api.services_findings import (
    assemble,
    build_page,
    compare,
    grade_finding,
    summary_is_grounded,
)

_PLAN = [
    {"page_id": "P1", "question": "Did the latest period grow against the prior period and the peak?"},
    {"page_id": "P2", "question": "What share of the total sits with the largest group?"},
    {"page_id": "P3", "question": "Where does the plan sit against the trading run-rate?"},
]


def _pages() -> list[dict]:
    revenue = grade_finding(
        "Revenue fell from 10 to 8, and it remains below the peak of 12.",
        number=1,
        impact="high",
        confidence="high",
    )
    share = grade_finding(
        "The largest group is 40% of the total.",
        number=2,
        impact="medium",
        confidence="medium",
    )
    plan = grade_finding(
        "The plan sits above the trading run-rate.",
        number=3,
        impact="medium",
        confidence="low",
    )
    return [
        build_page(
            "P1",
            _PLAN[0]["question"],
            schedules=["GOV-04"],
            metrics=["revenue"],
            comparison={"recipe": "period_change", "latest": 8, "prior": 10, "peak": 12},
            finding=revenue,
        ),
        build_page(
            "P2",
            _PLAN[1]["question"],
            schedules=["customers"],
            metrics=["concentration"],
            comparison={"recipe": "share", "part": 40, "whole": 100},
            finding=share,
        ),
        build_page(
            "P3",
            _PLAN[2]["question"],
            schedules=["plan"],
            metrics=["plan_vs_trading"],
            comparison={"recipe": "plan_vs_trading", "plan": 15, "ytd": 8, "months": 8},
            finding=plan,
        ),
    ]


def test_every_planned_page_is_present_and_titled_with_its_finding() -> None:
    for _deal in ("north", "harbour", "inland"):
        pages = _pages()
        report = assemble(_PLAN, pages, {"claims": []})
        assert report["ok"] is True
        assert [page["page_id"] for page in report["pages"]] == ["P1", "P2", "P3"]
        for page in report["pages"]:
            finding = page["finding"]
            assert str(finding["number"]) + "." in page["title"]
            assert finding["statement"] in page["title"]
            assert page["chart"] == page["comparison"]["chart"]
        summary = report["executive_summary"]
        assert summary["composed_after"] == ["P1", "P2", "P3"]
        assert summary["title"].startswith("1. Revenue fell from 10 to 8")
        assert "40%" in summary["body"]
        assert summary_is_grounded(summary["body"], [page["finding"] for page in pages], {"claims": []}) is None


def test_charts_follow_the_comparison() -> None:
    assert compare("period_change", {"latest": 8, "prior": 10, "peak": 12})["chart"] == "line"
    assert compare("mix", {"parts": [{"label": "A", "value": 2}, {"label": "B", "value": 3}]})["chart"] == "stacked_bar"
    assert compare("bridge", {"start": 8, "end": 12})["chart"] == "waterfall"
    assert compare("rank", {"rows": [{"label": "B", "value": 1}, {"label": "A", "value": 3}]})["result"]["order"] == ["A", "B"]
    with pytest.raises(ValueError, match="comparison"):
        build_page(
            "P1",
            _PLAN[0]["question"],
            schedules=["GOV-04"],
            metrics=["revenue"],
            comparison={"recipe": "period_change", "latest": 8, "prior": 10, "peak": 12},
            finding=grade_finding("Revenue grew from 10 to 8.", number=1, impact="high", confidence="high"),
        )


def test_missing_page_and_untitled_finding_are_rejected() -> None:
    pages = _pages()
    missing = assemble(_PLAN, pages[:2], {"claims": []})
    assert missing["ok"] is False
    assert "P3" in missing["error"]

    untitled = dict(pages[0])
    untitled["title"] = "Historical Performance"
    rejected = assemble([_PLAN[0]], [untitled], {"claims": []})
    assert rejected["ok"] is False
    assert "finding" in rejected["error"]

    planted = "Revenue reached 99."
    assert summary_is_grounded(planted, [pages[0]["finding"]], {"claims": []})


def test_summary_uses_the_ledger_and_a_gap_page_is_not_published() -> None:
    held = grade_finding(
        "Churn is not in the data room.",
        number=4,
        impact="low",
        confidence="high",
        claim_status="unknown",
    )
    assert held["held"] is True
    assert held["confidence"] == "medium"
    ledger = {
        "schedule": "GOV-04",
        "claims": [{"status": "unknown", "claim_as_stated": "Churn is not in the data room.", "proves_problem": False}],
    }
    pages = _pages()
    report = assemble(_PLAN, pages, ledger)
    assert "Held, not a proven problem: Churn is not in the data room." in report["executive_summary"]["body"]
    assert "proven problem: Churn" in report["executive_summary"]["body"]

    published = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "page_plan": _PLAN,
            "pages": _pages(),
            "claims": ledger["claims"],
        },
    )
    assert published["status"] == "completed"
    assert published["findings_report"]["executive_summary"]["composed_after"] == ["P1", "P2", "P3"]

    incomplete = prepare_completion(
        "revenue_quality",
        {
            "status": "completed",
            "sources": ["Accounts.pdf"],
            "page_plan": _PLAN,
            "pages": _pages()[:2],
        },
    )
    assert incomplete["status"] == "needs_repair"
    assert "P3" in incomplete["error"]
