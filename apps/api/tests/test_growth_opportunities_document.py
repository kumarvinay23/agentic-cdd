"""Growth Opportunities — DiligenceIQ prompt-book costed upside options."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_growth_opportunities import (
    _heuristic_growth_opportunities_spec,
    build_growth_opportunities_spec,
    render_growth_opportunities_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-go-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _go_corpus() -> str:
    return (
        "Technology-First Positioning MoveOS differentiates from hardware-only "
        "competitors. OTA updates and connected features. "
        "Vertical Integration Strategy In-house battery cells (Gigafactory), motors, "
        "controllers, and software reduce BOM costs and improve margins. Localization "
        "roadmap targets 85%+ domestic content by FY2027. "
        "Scale Advantage Futurefactory's 2M+ unit capacity creates unmatched cost per "
        "unit economics. As volumes scale, fixed cost amortization improves gross "
        "margins from ~12% today to an estimated 22–25% by FY2027. "
        "Brand Equity Among Youth Strong awareness among 18–35 urban consumers. "
        "Nationwide retail expansion — 600+ experience centers operational as of "
        "H1 FY2024. "
        "Ecosystem Monetization Future revenue from charging network (Hypercharger), "
        "battery swapping, insurance, financing, and software subscriptions creates "
        "ARPU expansion opportunities. "
        "EV penetration in the two-wheeler segment stood at ~6% in FY2024 and is "
        "projected to reach 35–40% by FY2030. "
        "Phase 1 capacity: 1 million units p.a. Phase 2 expansion ongoing — targeting "
        "2 million units p.a. by FY2025. "
        "Revenue > INR 15,000 Cr — Volume + ASP expansion. "
        "Financial Value Creation Path Milestone Target Year."
    )


def _legacy() -> dict:
    return {
        "dd_code": "DD-01b",
        "growth_levers": [
            {
                "name": "Technology-First Positioning",
                "note": "MoveOS software moat with OTA updates.",
            },
            {
                "name": "Vertical Integration Strategy",
                "note": "In-house cells and localization roadmap to FY2027.",
            },
            {
                "name": "Scale Advantage",
                "note": "2M+ unit capacity; gross margins 12% to 22–25%.",
            },
            {
                "name": "Brand Equity Among Youth",
                "note": "High aided recall in core buyer segment.",
            },
            {
                "name": "Ecosystem Monetization",
                "note": "Charging, swapping, insurance, financing, subscriptions.",
            },
        ],
        "market_growth": {
            "tam_cagr_pct": 13.8,
            "sam_cagr_pct": 57.6,
            "ev_penetration_fy2024_pct": 6.0,
        },
        "milestone_targets": [
            "Gross Margin > 20% — Battery localization + scale",
            "Revenue > INR 15,000 Cr — Volume + ASP expansion",
        ],
        "opportunity_notes": [
            "SAM CAGR ~57.6% — structural EV tailwind.",
        ],
    }


def test_growth_opportunities_prompt_book_listed() -> None:
    system = compose_system("growth_opportunities", sector="EV", geography="India")
    assert "growth_opportunities" in listed_agents()
    assert "option" in system.lower() or "upside" in system.lower()
    body = agent_prompt("growth_opportunities")
    assert "Ola" not in body and "SoftBank" not in body
    assert "hypothesis" in body.lower()
    assert "double" in body.lower() or "additional" in body.lower()
    assert "probabilities" in body.lower() or "probability" in body.lower()


def test_growth_opportunities_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_growth_opportunities.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_options_fit_operating_model() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    assert opts
    allowed = {
        "More customers (current footprint)",
        "Adjacent geography",
        "Adjacent service",
        "Price",
        "Acquisition",
    }
    for o in opts:
        assert o.get("option_type") in allowed
        assert o.get("fit_rationale")


def test_options_sized_with_calculation_and_assumptions() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    assert opts
    scale = next(
        (o for o in opts if "scale" in str(o.get("option") or "").lower()),
        None,
    )
    assert scale is not None
    assert scale.get("calculation")
    assert scale.get("assumptions")
    assert scale.get("incremental_margin")
    assert "pp" in str(scale.get("incremental_margin") or "") or "12" in str(
        scale.get("calculation") or ""
    )


def test_requirements_and_timing_present() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    assert opts
    for o in opts:
        assert "capital" in o
        assert "hiring" in o
        assert "capacity_needed" in o
        assert "permits" in o
        assert "systems" in o
        assert o.get("time_to_contribute")


def test_evidence_or_hypothesis_labelled() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    assert opts
    statuses = {o.get("evidence_status") for o in opts}
    assert statuses <= {"Evidenced", "Hypothesis"}
    assert "Evidenced" in statuses
    for o in opts:
        assert o.get("success_probability") is None


def test_base_vs_upside_separated() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    statuses = " ".join(str(o.get("plan_status") or "") for o in opts)
    assert "Inside plan" in statuses or "Additional" in statuses
    assert any(o.get("buyer_funding") for o in opts)


def test_ranked_by_evidence_and_size() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    opts = [
        o for o in (heur.get("options") or [])
        if isinstance(o, dict) and not str(o.get("option") or "").startswith("Information")
    ]
    ranks = [o.get("rank") for o in opts]
    assert ranks == list(range(1, len(opts) + 1))


def test_legacy_dual_write() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    assert heur.get("growth_levers")
    assert heur.get("market_growth") is not None
    assert heur.get("milestone_targets") is not None
    assert heur.get("opportunity_notes") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert heur.get("dd_code") == "DD-01b"


def test_render_no_invest() -> None:
    heur = _heuristic_growth_opportunities_spec(
        company="Test3",
        corpus=_go_corpus() + " We recommend invest.",
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_growth_opportunities_markdown("Growth Opportunities", heur)
    assert "## 1. Available Options" in md
    assert "## 2. Sized Revenue & Margin" in md
    assert "## 3. Requirements & Timing" in md
    assert "## 4. Achievability Evidence" in md
    assert "## 5. Base Case vs Upside" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Not assigned — no evidenced basis" in md


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "growth_opportunities",
        "agentName": "Growth Opportunities",
        "target_company": "Test3",
        "summary": "Growth Opportunities for Test3",
        "sources": ["03_Investment_Thesis.pdf"],
        "spec": _heuristic_growth_opportunities_spec(
            company="Test3",
            corpus=_go_corpus(),
            sources=["03_Investment_Thesis.pdf"],
            sector="Electric Two-Wheelers",
            geography="India",
            legacy_spec=_legacy(),
        ),
    }
    md = render_agent_document("growth_opportunities", output)
    assert "## 6. Quality & Reliance" in md
    assert "Option" in md or "option" in md.lower()


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_growth_opportunities_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_go_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-01b"
