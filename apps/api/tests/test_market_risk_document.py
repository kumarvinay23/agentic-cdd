"""Market Risk — DiligenceIQ prompt-book external risks sized to company numbers."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_market_risk import (
    _heuristic_market_risk_spec,
    build_market_risk_spec,
    render_market_risk_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-mr-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _mr_corpus() -> str:
    return (
        "FAME-II subsidy under review; recovery notice issued on prior claims. "
        "OEM counter-attack and competitor pricing pressure in core geography. "
        "Top customer concentration: largest contract is 18% of revenue; "
        "renewal due within 12 months. "
        "Demand cycle: volume fell 22% in the last downturn. "
        "China supply / battery cost spike risk on cell imports. "
        "CCPA class complaint and litigation on the legal register. "
        "Escrow and specific indemnity contemplated for subsidy recovery. "
        "Revenue USD 410M. EBITDA margin approximately 8%."
    )


def _legacy() -> dict:
    return {
        "dd_code": "DD-20",
        "market_risk_items": [
            {
                "risk": "FAME / subsidy reduction",
                "probability": "High",
                "impact": "High",
            },
            {
                "risk": "OEM counter-attack",
                "probability": "Medium",
                "impact": "High",
            },
            {
                "risk": "Customer concentration / non-renewal",
                "probability": "Medium",
                "impact": "Medium",
            },
        ],
        "regulatory_items": [
            {
                "area": "Subsidy claim recovery",
                "status": "Under review",
                "risk_level": "High",
            },
            {
                "area": "Companies Act Compliance",
                "status": "Compliant",
                "risk_level": "Low",
            },
        ],
        "litigation_exposures": [
            "CCPA class complaint pending — reserve under review",
        ],
        "risk_flags": ["Subsidy dependence", "Competitor share pressure"],
        "risk_notes": ["Watch monthly subsidy notices."],
    }


def test_market_risk_prompt_book_listed() -> None:
    system = compose_system("market_risk", sector="EV", geography="India")
    assert "market_risk" in listed_agents()
    assert "external" in system.lower() or "likelihood" in system.lower()
    body = agent_prompt("market_risk")
    assert "Ola" not in body and "SoftBank" not in body
    assert "early-warning" in body.lower() or "early warning" in body.lower()
    assert "escrow" in body.lower() or "structure" in body.lower()
    assert "numeric" in body.lower() or "probabilities" in body.lower()


def test_market_risk_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_market_risk.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"


def test_external_risks_mechanism_exposure_time() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus(),
        sources=["03_Investment_Thesis.pdf", "06_Legal_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
    )
    risks = [r for r in (heur.get("external_risks") or []) if isinstance(r, dict)]
    assert len(risks) >= 3
    real = [r for r in risks if not str(r.get("risk") or "").startswith("Information")]
    assert real
    for r in real[:3]:
        assert r.get("mechanism")
        assert r.get("exposure")
        assert r.get("time_horizon")
        assert r.get("family")


def test_likelihood_from_evidence_no_invented_probability() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        legacy_spec=_legacy(),
    )
    for r in heur.get("external_risks") or []:
        if not isinstance(r, dict):
            continue
        assert r.get("numeric_probability") is None
        arg = str(r.get("likelihood_argument") or "")
        assert arg
        # Must not invent a bare percentage probability
        assert "probability: 70%" not in arg.lower()


def test_bounded_downside_and_unsized() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
    )
    downsides = heur.get("downside_cases") or []
    assert isinstance(downsides, list)
    # Unsized risks still reported with what would size them
    unsized = heur.get("unsized_risks") or []
    assert isinstance(unsized, list)
    for u in unsized:
        if isinstance(u, dict) and not str(u.get("risk") or "").startswith("Information"):
            assert u.get("what_would_size") or u.get("why_unsized")


def test_early_warnings_and_price_vs_structure() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
    )
    warnings = heur.get("early_warnings") or []
    assert any(
        isinstance(w, dict)
        and "Monthly" in str(w.get("early_warning") or "")
        for w in warnings
    )
    pvs = heur.get("price_vs_structure") or []
    assert pvs
    classes = {
        str(p.get("classification") or "")
        for p in pvs
        if isinstance(p, dict)
    }
    assert any("price" in c.lower() or "structure" in c.lower() for c in classes)
    # Subsidy recovery / escrow path should prefer structure
    assert any("structure" in c.lower() for c in classes)


def test_legacy_dual_write() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        legacy_spec=_legacy(),
    )
    items = heur.get("market_risk_items") or []
    assert items
    assert heur.get("regulatory_items") is not None
    assert heur.get("risk_flags") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_render_no_invest() -> None:
    heur = _heuristic_market_risk_spec(
        company="Test3",
        corpus=_mr_corpus() + " We recommend invest.",
        sources=["03_Investment_Thesis.pdf"],
        legacy_spec=_legacy(),
    )
    md = render_market_risk_markdown("Market Risk", heur)
    assert "## 1. External Risks" in md
    assert "## 2. Likelihood from Evidence" in md
    assert "## 3. Quantified Downside" in md
    assert "## 4. Early-Warning" in md
    assert "## 5. Price vs Structure" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Not assigned" in md or "no evidenced basis" in md.lower()


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "market_risk",
        "agentName": "Market Risk",
        "target_company": "Test3",
        "summary": "Market Risk for Test3",
        "sources": ["03_Investment_Thesis.pdf"],
        "spec": _heuristic_market_risk_spec(
            company="Test3",
            corpus=_mr_corpus(),
            sources=["03_Investment_Thesis.pdf"],
            legacy_spec=_legacy(),
        ),
    }
    md = render_agent_document("market_risk", output)
    assert "## 6. Quality & Reliance" in md
    assert "External Risks" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_market_risk_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_mr_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-20"
