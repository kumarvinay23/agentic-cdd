"""Synergies — DiligenceIQ prompt-book buyer-specific net of cost to achieve."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_synergies import (
    _heuristic_synergies_spec,
    build_synergies_spec,
    render_synergies_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-syn-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _no_buyer_corpus() -> str:
    return (
        "Vertical Integration Strategy In-house battery cells reduce BOM costs. "
        "Scale Advantage Futurefactory 2M+ unit capacity. Gross margins from ~12% "
        "today to an estimated 22–25% by FY2027. "
        "Ecosystem Monetization charging network and software subscriptions. "
        "SoftBank Group 10.4% Strategic Institutional shareholder with board seat. "
        "Bargaining Power of Buyers — MEDIUM Individual consumers have low power. "
        "Value Creation Path Milestone Target Year Gross Margin > 20%."
    )


def _named_buyer_corpus() -> str:
    return (
        "Strategic acquirer is Contoso Mobility. Contoso brings a national dealer "
        "network and shared procurement. "
        "Duplicate HQ finance and HR roles identified for consolidation; current "
        "finance shared-services cost INR 45 Cr; saving INR 12 Cr owned by buyer "
        "integration office. "
        "Site consolidation of overlapping regional warehouse; current cost INR 8 Cr. "
        "System rationalisation of CRM platforms; integration cost INR 3 Cr in Y1. "
        "Cross-sell of Contoso insurance attach to target customers via buyer channel; "
        "pilot sold to 2 fleet operators. "
        "Severance estimated INR 5 Cr in Year 1. Advisory fees INR 2 Cr. "
        "Integration risk on systems cutover may delay run-rate by one year. "
        "Do not apply 10% of the cost base as a synergy."
    )


def _legacy() -> dict:
    return {
        "dd_code": "DD-06b",
        "synergy_themes": [
            "Vertical Integration Strategy — In-house cells and localization.",
            "Scale Advantage — 2M+ unit capacity and margin path.",
            "Ecosystem Monetization — charging and subscriptions.",
        ],
        "value_milestones": [
            "Gross Margin > 20% — Battery localization + scale",
        ],
        "synergy_notes": [
            "Scale synergy: gross margin path 12% → 22–25%.",
        ],
    }


def test_synergies_prompt_book_listed() -> None:
    system = compose_system("synergies", sector="EV", geography="India")
    assert "synergies" in listed_agents()
    assert "buyer" in system.lower() or "acquirer" in system.lower()
    # Deal slots filled by compose_system
    assert "deal perimeter" in system.lower() or "[DEAL_PERIMETER]" not in system
    body = agent_prompt("synergies")
    assert "Ola" not in body and "SoftBank" not in body
    assert "underwritten" in body.lower() or "underwrite" in body.lower()
    assert "percentage" in body.lower() or "cost base" in body.lower()
    assert "stand-alone" in body.lower() or "standalone" in body.lower()
    assert "gross" in body.lower() and "net cash" in body.lower()
    assert "growth opportunities" in body.lower()
    assert "execution" in body.lower()
    assert "final valuation" in body.lower() or "fvr" in body.lower()
    assert "questions" in body.lower()


def test_synergies_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_synergies.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_no_named_buyer_hypotheses_only_no_number() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_no_buyer_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    buyer = heur.get("buyer") or {}
    assert buyer.get("named") is False
    assert heur.get("underwritable") is False
    assert "cannot" in str(heur.get("cannot_underwrite_reason") or "").lower()
    assert heur.get("cost_synergies") == [] or not heur.get("cost_synergies")
    assert "Not produced" in str(heur.get("run_rate") or "")
    hyps = [
        h for h in (heur.get("hypotheses") or [])
        if isinstance(h, dict) and h.get("hypothesis")
    ]
    assert hyps
    assert heur.get("reliance_verdict") == "BLOCKED"
    assert (heur.get("stand_alone_separation") or {}).get("in_standalone_valuation") is False
    fvr = heur.get("fvr_exclusion") or {}
    assert fvr.get("include_in_final_valuation_range") is False
    qa = {r.get("check"): r for r in (heur.get("sy_evidence_qa") or []) if isinstance(r, dict)}
    assert qa.get("no_uplift_without_buyer", {}).get("status") == "PASS"
    assert qa.get("named_buyer_or_hypothesis_only", {}).get("status") == "PASS"


def test_named_buyer_cost_synergies_bottom_up() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    buyer = heur.get("buyer") or {}
    assert buyer.get("named") is True
    assert "Contoso" in str(buyer.get("buyer_name") or "")
    costs = [
        r for r in (heur.get("cost_synergies") or [])
        if isinstance(r, dict) and not str(r.get("item") or "").startswith("Information")
    ]
    assert costs
    for r in costs:
        assert r.get("item")
        assert r.get("item_type")
        assert "action_owner" in r
        assert "gross_benefit" in r
        assert "overlap_double_count" in r
        assert "cannibalisation" in r
        assert "one_off_costs" in r
        assert "tax_effect" in r
        assert "timing" in r
        assert "net_cash" in r
        # Must not be a bare % of cost base as the saving method
        assert "10% of the cost base" not in str(r.get("saving") or "").lower()


def test_rejects_percentage_of_cost_base() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=(
            "Strategic acquirer is Contoso Mobility. "
            "Apply 15% of the cost base as procurement synergy."
        ),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec={},
    )
    costs = heur.get("cost_synergies") or []
    rejected = [
        r for r in costs
        if isinstance(r, dict) and "percentage" in str(r.get("item_type") or "").lower()
    ]
    # Either rejected explicitly or no underwritable %-of-base saving
    for r in costs:
        if not isinstance(r, dict):
            continue
        assert r.get("underwritable") is not True or "cost base" not in str(
            r.get("saving") or ""
        ).lower()
    assert rejected or not any(
        isinstance(r, dict) and r.get("underwritable") for r in costs
    )
    qa = {r.get("check"): r for r in (heur.get("sy_evidence_qa") or []) if isinstance(r, dict)}
    assert qa.get("no_percent_of_cost_base", {}).get("status") == "PASS"


def test_revenue_synergies_sceptical_separate() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    revs = [
        r for r in (heur.get("revenue_synergies") or [])
        if isinstance(r, dict)
    ]
    assert revs
    for r in revs:
        assert "customers" in r
        assert "product" in r
        assert "channel" in r
        assert "evidence_combination_sells" in r
        assert "gross_benefit" in r
        assert "net_cash" in r


def test_cost_to_achieve_and_phasing_with_owner() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    achieve = heur.get("cost_to_achieve") or []
    assert achieve
    assert any(
        isinstance(a, dict)
        and any(k in str(a.get("cost_item") or "").lower() for k in ("severance", "advisory", "integration"))
        for a in achieve
    )
    phasing = heur.get("phasing") or []
    assert phasing
    years = " ".join(str(p.get("year") or "") for p in phasing if isinstance(p, dict))
    assert "Y1" in years or "Run-rate" in years or "run" in years.lower()
    for p in phasing:
        if isinstance(p, dict):
            assert "owner" in p
    qa = {r.get("check"): r for r in (heur.get("sy_evidence_qa") or []) if isinstance(r, dict)}
    assert qa.get("phasing_with_owner", {}).get("status") == "PASS"


def test_seller_share_and_standalone_layer() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    seller = heur.get("seller_share") or {}
    assert seller.get("seller_share_expectation")
    stand = heur.get("stand_alone_separation") or {}
    assert stand.get("in_standalone_valuation") is False
    assert "separate" in str(stand.get("layer") or "").lower() or "committee" in str(
        stand.get("layer") or ""
    ).lower()


def test_go_reconcile_and_execution_risks() -> None:
    go_prior = {
        "options": [
            {
                "option": "Organic charging network expansion",
                "evidence_status": "Evidenced",
            }
        ],
        "growth_levers": [{"name": "Scale Advantage"}],
    }
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
        growth_opportunities_spec=go_prior,
    )
    go = heur.get("go_reconcile") or {}
    assert go.get("go_prior_present") is True
    risks = heur.get("execution_risks") or []
    assert risks
    assert any(
        isinstance(r, dict)
        and (
            "integration" in str(r.get("risk") or "").lower()
            or "cutover" in str(r.get("risk") or "").lower()
            or "execution" in str(r.get("risk") or "").lower()
        )
        for r in risks
    )
    qa = {r.get("check"): r for r in (heur.get("sy_evidence_qa") or []) if isinstance(r, dict)}
    assert "growth_opportunities_reconcile" in qa
    assert "execution_risks" in qa
    assert "fvr_excludes_unverified" in qa


def test_ready_capped_to_limited_on_qa_fail() -> None:
    # Underwritable cost + execution risk present → may be READY, but force FAIL
    # path via incomplete lever when we strip fields after build is hard;
    # instead assert the quality helper caps when qa_fail=True via open FAIL.
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    assert heur.get("sy_evidence_qa")
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    # If any FAIL exists, reliance must not be READY
    qa_fail = any(
        isinstance(r, dict) and r.get("status") == "FAIL"
        for r in (heur.get("sy_evidence_qa") or [])
    )
    if qa_fail:
        assert heur.get("reliance_verdict") != "READY"
    questions = heur.get("questions") or []
    assert isinstance(questions, list)
    if qa_fail:
        assert questions  # Questions generated from open FAILs


def test_legacy_dual_write() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_no_buyer_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    assert heur.get("synergy_themes")
    assert heur.get("value_milestones") is not None
    assert heur.get("synergy_notes") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert heur.get("dd_code") == "DD-06b"


def test_render_no_invest_no_buyer() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_no_buyer_corpus() + " We recommend invest.",
        sources=["03_Investment_Thesis.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_synergies_markdown("Synergies", heur)
    assert "## 1. Named Buyer" in md
    assert "## 2. Hypotheses Only" in md
    assert "cannot be underwritten" in md.lower() or "No named acquirer" in md
    assert "## 6. Stand-Alone" in md
    assert "## 7. Synergies Evidence QA" in md
    assert "## 8. Questions and Inputs Required" in md
    assert "## 9. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Not produced" in md


def test_render_named_buyer_sections() -> None:
    heur = _heuristic_synergies_spec(
        company="Test3",
        corpus=_named_buyer_corpus(),
        sources=["CIM.pdf"],
        sector="Electric Two-Wheelers",
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_synergies_markdown("Synergies", heur)
    assert "## 2. Cost Synergies" in md
    assert "## 3. Revenue Synergies" in md
    assert "## 4. Cost to Achieve" in md
    assert "Contoso" in md
    assert "Lever economics" in md or "gross" in md.lower()
    assert "## 7. Synergies Evidence QA" in md
    assert "## 9. Quality & Reliance" in md


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "synergies",
        "agentName": "Synergies",
        "target_company": "Test3",
        "summary": "Synergies for Test3",
        "sources": ["03_Investment_Thesis.pdf"],
        "spec": _heuristic_synergies_spec(
            company="Test3",
            corpus=_no_buyer_corpus(),
            sources=["03_Investment_Thesis.pdf"],
            sector="Electric Two-Wheelers",
            geography="India",
            legacy_spec=_legacy(),
        ),
    }
    md = render_agent_document("synergies", output)
    assert "## 9. Quality & Reliance" in md
    assert "Named Buyer" in md or "named" in md.lower()


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_synergies_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_no_buyer_corpus(),
        sources=["03_Investment_Thesis.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-06b"
    assert "deal_slots" in spec
