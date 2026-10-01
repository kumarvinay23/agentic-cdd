"""Cost Structure — DiligenceIQ prompt-book GL map / cost behaviour / unit economics."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_cost_structure import (
    _heuristic_cost_structure_spec,
    build_cost_structure_spec,
    render_cost_structure_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-cs-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _cs_corpus() -> str:
    return (
        "Economic Engine Efficiency — BOM cost bridge. "
        "Battery Pack — 38% Electric Motor — 12% Power Electronics — 9% "
        "Chassis & Frame — 8% Body Panels — 6% Tyres — 5% "
        "Wiring Harness — 4% Braking System — 4%. "
        "Gross margin 12.5%. COGS per unit INR 78,400. "
        "CAC INR 12,500. Estimated 3-Year LTV INR 45,000. "
        "Capacity utilisation 68%. "
        "Scale advantage from localisation of battery pack assembly. "
        "Vertical integration of motor production expected to reduce unit cost. "
        "Wage inflation 6% in the labour agreement; plan does not state a fuel "
        "inflation assumption. Margin expansion path references GM target 18%."
    )


def test_cost_structure_prompt_book_listed() -> None:
    system = compose_system("cost_structure", sector="EV", geography="India")
    assert "cost_structure" in listed_agents()
    assert "fixed" in system.lower() and "variable" in system.lower()
    body = agent_prompt("cost_structure")
    assert "Ola" not in body and "SoftBank" not in body
    assert "another sector" in body.lower() or "sector as a benchmark" in body.lower()
    assert "driver" in body.lower()


def test_cost_structure_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_cost_structure.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_gl_map_and_classification() -> None:
    heur = _heuristic_cost_structure_spec(
        company="Test3",
        corpus=_cs_corpus(),
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
    )
    cats = heur.get("operating_categories") or []
    assert cats
    materials = next(
        (c for c in cats if isinstance(c, dict) and "Materials" in str(c.get("category") or "")),
        None,
    )
    assert materials is not None
    assert isinstance(materials.get("share_pct"), (int, float))
    assert float(materials["share_pct"]) >= 38.0

    classification = heur.get("cost_classification") or []
    assert classification
    mat_class = next(
        (
            c for c in classification
            if isinstance(c, dict) and "Materials" in str(c.get("category") or "")
        ),
        None,
    )
    assert mat_class is not None
    assert "Variable" in str(mat_class.get("classification") or "")
    assert "driver" in str(mat_class.get("justification") or "").lower() or mat_class.get("driver")


def test_unit_economics_and_inflation() -> None:
    heur = _heuristic_cost_structure_spec(
        company="Test3",
        corpus=_cs_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
    )
    units = heur.get("unit_economics") or []
    assert any(
        isinstance(u, dict)
        and u.get("cost")
        and not str(u.get("cost")).startswith("Information")
        for u in units
    )
    infl = heur.get("inflation_exposure") or []
    wage = next(
        (r for r in infl if isinstance(r, dict) and "Wage" in str(r.get("category") or "")),
        None,
    )
    assert wage is not None
    assert "6" in str(wage.get("exposure") or "")


def test_no_invest_and_no_sector_benchmark() -> None:
    heur = _heuristic_cost_structure_spec(
        company="Test3",
        corpus=_cs_corpus() + " We recommend invest. Industry average COGS ratio 55%.",
        sources=["03_Investment_Thesis.pdf"],
    )
    md = render_cost_structure_markdown("Cost Structure", heur)
    assert "## 1. Operating Category Map" in md
    assert "## 2. Fixed / Variable / Step" in md
    assert "## 3. Unit Economics" in md
    assert "## 4. Inflation Exposure" in md
    assert "## 5. Efficiency Opportunities" in md
    assert "## 6. Quality & Reliance" in md
    lower = md.lower()
    assert "**recommendation:**" not in lower
    assert "we recommend invest" not in lower
    assert "cross-sector" in lower or "another sector" in lower or "not imported" in lower
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_legacy_dual_write() -> None:
    heur = _heuristic_cost_structure_spec(
        company="Test3",
        corpus=_cs_corpus(),
        sources=["12_Manufacturing_Supply_Chain_Review.pdf"],
        legacy_spec={
            "bom_components": [{"category": "Battery Pack", "share_pct": 38.0}],
            "cost_metrics": {"gross_margin_pct": 12.5},
            "efficiency_notes": ["Scale advantage from localisation."],
        },
    )
    bom = heur.get("bom_components") or []
    assert any(isinstance(b, dict) and b.get("category") == "Battery Pack" for b in bom)
    assert heur.get("cost_metrics", {}).get("gross_margin_pct") == 12.5
    notes = heur.get("efficiency_notes") or []
    assert notes


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "cost_structure",
        "agentName": "Cost Structure",
        "target_company": "Test3",
        "summary": "Cost Structure for Test3",
        "sources": ["05_Financial_Due_Diligence.pdf"],
        "spec": _heuristic_cost_structure_spec(
            company="Test3",
            corpus=_cs_corpus(),
            sources=["05_Financial_Due_Diligence.pdf"],
        ),
    }
    md = render_agent_document("cost_structure", output)
    assert "## 6. Quality & Reliance" in md
    assert "Battery Pack" in md or "Materials" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_cost_structure_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_cs_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        prefer_heuristic=True,
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-13"
