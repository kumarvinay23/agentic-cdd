"""Customer Segmentation — DiligenceIQ prompt-book concentration & segments."""

from __future__ import annotations

from agetic_cdd_api.agent_document_customer_segmentation import (
    _concentration_calculable,
    _heuristic_customer_segmentation_spec,
    build_customer_segmentation_spec,
    render_customer_segmentation_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-cseg-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _calc_corpus() -> str:
    return (
        "Billing ledger / investor workbook opened with account, parent and location IDs. "
        "Largest customer is 18% of revenue. Top 5 customers = 31% of revenue. "
        "Top 10 customers = 42% of revenue. Population for concentration: parents. "
        "Customer type: Fleet Operator 22%, Urban Professional 38%, Other 15% unclassified "
        "remainder shown separately — reconciles toward accounts total. "
        "Geography: South India 34%, West India 28%. "
        "Largest contract: Metro Fleet Holdings value INR 40 crore, 8% of revenue, "
        "ends 31 Mar 2027, 90-day termination for convenience."
    )


def _unassessed_corpus() -> str:
    return (
        "Management asserts the customer base is highly concentrated with heavy "
        "reliance on a few large relationships. No billing ledger opened."
    )


def test_customer_segmentation_prompt_book_listed() -> None:
    system = compose_system("customer_segmentation", sector="EV", geography="India")
    assert "customer_segmentation" in listed_agents()
    assert "concentration" in system.lower()
    body = agent_prompt("customer_segmentation")
    assert "Ola" not in body and "SoftBank" not in body
    assert "top 1" in body.lower() or "top 10" in body.lower()
    assert "unassessed" in body.lower()
    assert "ledger" in body.lower()


def test_customer_segmentation_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_customer_segmentation.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("customer_segmentation")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_concentration_calculable_helper() -> None:
    ok, notes = _concentration_calculable(
        top_1="18%",
        top_5="31%",
        top_10="42%",
        ledger_status="resolved",
        population="parents",
    )
    assert ok is True
    bad, bad_notes = _concentration_calculable(
        top_1=None,
        top_5=None,
        top_10=None,
        ledger_status="missing",
        population="parents",
        corpus="highly concentrated",
    )
    assert bad is False
    assert "unassessed" in bad_notes.lower() or "ledger" in bad_notes.lower()


def test_customer_segmentation_markdown_calculated() -> None:
    heur = _heuristic_customer_segmentation_spec(
        company="Test3",
        corpus=_calc_corpus(),
        sources=["04_Commercial_Due_Diligence.pdf"],
        legacy_spec={
            "segments": [
                {
                    "name": "Urban Professional",
                    "share_pct": 38.0,
                    "avg_age": "28-35",
                    "use_case": "commute",
                    "key_driver": "TCO",
                }
            ],
            "geo_mix": ["South India 34%"],
            "icp_notes": ["Primary ICP ages 25-40"],
        },
    )
    md = render_customer_segmentation_markdown("Customer Segmentation", heur)

    assert "## 1. Ledger" in md
    assert "## 2. Segmentation" in md
    assert "## 3. Concentration" in md
    assert "## 4. Largest Contracts" in md
    assert "## 5. Population" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    conc = heur.get("concentration") or {}
    assert conc.get("calculable") is True
    assert conc.get("top_10_share_pct")
    assert conc.get("risk_rating") not in (None, "withheld") or isinstance(
        conc.get("risk_rating"), str
    )
    assert isinstance(heur.get("segments"), list)
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_customer_segmentation_unassessed_withholds_risk() -> None:
    heur = _heuristic_customer_segmentation_spec(
        company="Test3",
        corpus=_unassessed_corpus(),
        sources=["03_Investment_Thesis.pdf"],
    )
    md = render_customer_segmentation_markdown("Customer Segmentation", heur)
    conc = heur.get("concentration") or {}
    assert conc.get("calculable") is False
    assert conc.get("risk_rating") in (None, "withheld")
    body = md.lower()
    assert "unassessed" in body
    assert "withheld" in body or "not high risk" in body or "not a high-risk" in body
    assert "**Recommendation:**" not in md


def test_normalise_strips_recommendation_and_forces_withheld() -> None:
    from agetic_cdd_api.agent_document_customer_segmentation import _normalise_llm_spec
    import inspect

    sig = inspect.signature(_normalise_llm_spec)
    kwargs: dict = {"sources": ["a.pdf"], "legacy_spec": None}
    if "corpus" in sig.parameters:
        kwargs["corpus"] = ""

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Customers are highly concentrated — high risk",
            "concentration": {
                "calculable": False,
                "population": "parents",
                "top_1_share_pct": None,
                "top_5_share_pct": None,
                "top_10_share_pct": None,
                "risk_rating": "High",
            },
            "segments_by_axis": [],
            "largest_contracts": [],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "BLOCKED",
        },
        **kwargs,
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    conc = llm.get("concentration") or {}
    assert conc.get("calculable") is False
    assert conc.get("risk_rating") in (None, "withheld")
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()


def test_render_agent_document_customer_segmentation() -> None:
    output = {
        "agentName": "Customer Segmentation",
        "target_company": "Test3",
        "sources": ["04_Commercial_Due_Diligence.pdf"],
        "document": (
            "# Customer Segmentation\n\n"
            "## 1. Ledger & Customer Universe\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("customer_segmentation", output)
    assert "## 1. Ledger" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_customer_segmentation_from_corpus() -> None:
    spec = build_customer_segmentation_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "04_Commercial_Due_Diligence.pdf",
                    "cdl_category": "customer",
                    "excerpt": _calc_corpus(),
                }
            ],
            "category_counts": {"customer": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_customer_segmentation_markdown("Customer Segmentation", spec)
    assert "## 3. Concentration" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-08"
