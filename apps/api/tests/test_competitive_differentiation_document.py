"""Competitive Differentiation — DiligenceIQ prompt-book advantage tests."""

from __future__ import annotations

from agetic_cdd_api.agent_document_competitive_differentiation import (
    _claim_kind,
    _heuristic_competitive_differentiation_spec,
    _soften_moat_language,
    build_competitive_differentiation_spec,
    render_competitive_differentiation_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-cdiff-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _diff_corpus() -> str:
    return (
        "Management claims a software moat via proprietary OS vs Ather Energy and TVS. "
        "Customer benefit: OTA updates and better UX; metric is NPS gap of 15 points "
        "vs Ather Energy evidenced in the competition pack. "
        "Economic effect: ~8% price premium and higher retention vs peers. "
        "Manufacturing scale is an ordinary capability every large OEM has. "
        "Seller CIM asserts unique brand loyalty without customer evidence. "
        "Replication: a peer would need ~USD 50m and 24–36 months to match software depth; "
        "erosion risk over a 5-year hold if peers close the feature gap. "
        "Technology in use is not IP; patents not evidenced."
    )


def test_competitive_differentiation_prompt_book_listed() -> None:
    system = compose_system("competitive_differentiation", sector="EV", geography="India")
    assert "competitive_differentiation" in listed_agents()
    assert "moat" in system.lower() or "durable" in system.lower()
    body = agent_prompt("competitive_differentiation")
    assert "Ola" not in body and "SoftBank" not in body
    assert "technology" in body.lower()
    assert "intellectual" in body.lower() and "property" in body.lower()


def test_competitive_differentiation_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_competitive_differentiation.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("competitive_differentiation")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_soften_moat_and_claim_kind() -> None:
    soft = _soften_moat_language("This is a durable moat against peers")
    assert "moat" not in soft.lower()
    assert "durable advantage" in soft.lower()
    assert "durable durable" not in soft.lower()
    assert _claim_kind("management believes unique brand") == "management_assertion"
    assert _claim_kind(
        "NPS 15 points higher vs Ather evidenced in pack — demonstrated advantage"
    ) in {"demonstrated_advantage", "management_assertion", "ordinary_capability"}


def test_competitive_differentiation_markdown_follows_prompt_book() -> None:
    heur = _heuristic_competitive_differentiation_spec(
        company="Test3",
        corpus=_diff_corpus(),
        sources=["11_Market_Competition_Analysis.pdf"],
        legacy_spec={
            "differentiators": ["software capabilities superior to peers"],
            "moat_signals": ["software moat narrowing risk"],
        },
    )
    md = render_competitive_differentiation_markdown("Competitive Differentiation", heur)

    assert "## 1. Claimed Advantages" in md
    assert "## 2. Advantage Tests" in md
    assert "## 3." in md  # Capability Separation
    assert "## 4." in md  # Economic
    assert "## 5." in md  # Replication
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    body_lower = md.lower()
    if "moat" in body_lower:
        assert "durable advantage" in body_lower or "reconcile" in body_lower
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("differentiators"), list)


def test_moat_softened_in_normalise() -> None:
    from agetic_cdd_api.agent_document_competitive_differentiation import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs = {
        "sources": ["a.pdf"],
        "legacy_spec": None,
    }
    if "company" in sig.parameters:
        kwargs["company"] = "Test3"
    if "corpus" in sig.parameters:
        kwargs["corpus"] = ""
    if "geography" in sig.parameters:
        kwargs["geography"] = "India"

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Target has an unassailable moat",
            "claimed_advantages": [
                {
                    "claim": "Software moat",
                    "claimed_by": "management",
                    "where_stated": "CIM",
                }
            ],
            "advantage_tests": [
                {
                    "claim": "Software moat",
                    "customer_benefit": "OTA UX",
                    "named_alternative": "Ather Energy",
                    "metric": "NPS",
                    "evidence": "Information request: evidence",
                    "economic_effect": "N/A (data room did not provide it)",
                    "durability": "unknown",
                    "test_result": "UNTESTED",
                }
            ],
            "capability_separation": {},
            "economic_effects": [],
            "replication": [],
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        **kwargs,
    )
    assert "moat" not in str(llm.get("insight_snapshot") or "").lower()
    assert "durable advantage" in str(llm.get("insight_snapshot") or "").lower()


def test_render_agent_document_competitive_differentiation() -> None:
    output = {
        "agentName": "Competitive Differentiation",
        "target_company": "Test3",
        "sources": ["11_Market_Competition_Analysis.pdf"],
        "document": (
            "# Competitive Differentiation\n\n"
            "## 1. Claimed Advantages\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("competitive_differentiation", output)
    assert "## 1. Claimed" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_competitive_differentiation_from_corpus() -> None:
    spec = build_competitive_differentiation_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "11_Market_Competition_Analysis.pdf",
                    "cdl_category": "market_competition",
                    "excerpt": _diff_corpus(),
                }
            ],
            "category_counts": {"market_competition": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_competitive_differentiation_markdown("Competitive Differentiation", spec)
    assert "## 2. Advantage Tests" in md
    assert "## 5." in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
