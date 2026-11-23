"""Export consistency + IC brief agent."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agetic_cdd_api import services_deals as deals_mod
from agetic_cdd_api.services_export_consistency import (
    run_export_consistency,
)
from agetic_cdd_api.services_ic_brief import build_ic_brief, load_ic_brief


@pytest.fixture
def deal_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "deals"
    root.mkdir()
    monkeypatch.setattr(deals_mod, "deals_root", lambda: root)
    return root


def _write_agent(root: Path, slug: str, key: str, spec: dict) -> None:
    out = root / slug / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{key}.json").write_text(
        json.dumps(
            {
                "agent_key": key,
                "spec": spec,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def test_export_consistency_flags_kpi_mismatch(deal_root: Path) -> None:
    slug = "consist-1"
    _write_agent(
        deal_root,
        slug,
        "historical_performance",
        {
            "performance_metrics": {
                "revenue_fy2024_usd_m": 11.869,
                "revenue_fy2025_usd_m": 13.412,
                "ebitda_fy2024_usd_m": 1.135,
            }
        },
    )
    _write_agent(
        deal_root,
        slug,
        "company_background",
        {"legal_name": "Compost Crew"},
    )
    _write_agent(
        deal_root,
        slug,
        "market_definition",
        {
            "perimeter": {
                "service": "Organic waste collection",
                "geography": "DMV",
            }
        },
    )
    # Promoted disagrees on FY2025 revenue.
    db = deal_root / slug / "databook"
    db.mkdir(parents=True)
    (db / "promoted.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "revenue": {"2024": 11.869, "2025": 13.282},
                    "ebitda": {"2024": 1.135},
                }
            }
        ),
        encoding="utf-8",
    )

    report = run_export_consistency(slug)
    assert report.issue_count >= 1
    assert any(
        i.metric_key == "revenue" and i.fiscal_year == 2025 for i in report.issues
    )
    assert report.snapshot["legal_name"] == "Compost Crew"
    assert "service=" in (report.snapshot.get("perimeter") or "")
    saved = (deal_root / slug / "outputs" / "export_consistency.json")
    assert saved.is_file()


def test_export_consistency_aligned_when_matching(deal_root: Path) -> None:
    slug = "consist-ok"
    _write_agent(
        deal_root,
        slug,
        "historical_performance",
        {
            "performance_metrics": {
                "revenue_fy2024_usd_m": 11.869,
                "ebitda_fy2024_usd_m": 1.135,
            }
        },
    )
    db = deal_root / slug / "databook"
    db.mkdir(parents=True)
    (db / "promoted.json").write_text(
        json.dumps(
            {
                "metrics": {
                    "revenue": {"2024": 11.869},
                    "ebitda": {"2024": 1.135},
                }
            }
        ),
        encoding="utf-8",
    )
    report = run_export_consistency(slug)
    assert report.ok is True
    assert report.high_count == 0


def test_ic_brief_builds_risks_and_delta(deal_root: Path) -> None:
    slug = "brief-1"
    _write_agent(
        deal_root,
        slug,
        "company_background",
        {"legal_name": "Umoja Health"},
    )
    _write_agent(
        deal_root,
        slug,
        "ic_synthesis",
        {
            "go_no_go": "Proceed with conditions",
            "overall_label": "Proceed with conditions",
        },
    )
    _write_agent(
        deal_root,
        slug,
        "internal_risk",
        {
            "technical_risks": [
                "Reporting quality — monthly pack vs databook gaps remain open",
                "Systems maturity — ERP cutover incomplete",
            ]
        },
    )
    _write_agent(
        deal_root,
        slug,
        "recommendation",
        {
            "conditions_precedent": [
                "Obtain QoE-approved EBITDA bridge",
                "Confirm working-capital peg mechanics",
            ]
        },
    )
    _write_agent(
        deal_root,
        slug,
        "historical_performance",
        {"performance_metrics": {"revenue_fy2024_usd_m": 45.0}},
    )
    db = deal_root / slug / "databook"
    db.mkdir(parents=True)
    (db / "promoted.json").write_text(
        json.dumps({"metrics": {"revenue": {"2024": 45.0}}}),
        encoding="utf-8",
    )

    brief1 = build_ic_brief(slug, polish_llm=False)
    assert brief1.company == "Umoja Health"
    assert brief1.go_no_go and "Proceed" in brief1.go_no_go
    assert len(brief1.top_risks) >= 1
    assert len(brief1.open_items) >= 1
    assert brief1.changes_since_last == ["Initial IC brief"]
    assert load_ic_brief(slug) is not None

    # Second build should surface deltas when risks change.
    _write_agent(
        deal_root,
        slug,
        "internal_risk",
        {
            "technical_risks": [
                "Reporting quality — monthly pack vs databook gaps remain open",
                "Systems maturity — ERP cutover incomplete",
                "Liquidity — revolver headroom tight into FY2026",
            ]
        },
    )
    brief2 = build_ic_brief(slug, polish_llm=False)
    assert any("New risk" in c for c in brief2.changes_since_last)
