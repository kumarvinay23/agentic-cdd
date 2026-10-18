"""Internal Risk — DiligenceIQ prompt-book day-one inherited issues."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_internal_risk import (
    _heuristic_internal_risk_spec,
    build_internal_risk_spec,
    render_internal_risk_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-ir-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ir_corpus() -> str:
    return (
        "Bank reconciliations not performed for three months. "
        "Approvals missing on journal entries above threshold. "
        "Records incomplete for related-party ledgers. "
        "Cash burn elevated; liquidity headroom under review. "
        "Covenant headroom on senior facilities at 0.4x. "
        "Overdue trade creditors beyond contractual terms. "
        "Dividend distribution made while earnings were weak. "
        "Vehicle-level penetration testing not yet complete. "
        "Sample of purchase approvals tested — inspection passed. "
        "Remediation of control gaps estimated USD 2M within 6 months post-close."
    )


def _management() -> dict:
    return {
        "insight_snapshot": "Management Quality for Test3 — key-person map opened.",
        "key_persons": [
            {
                "person": "Alex Founder (CEO)",
                "what_depends": "Approvals and strategic direction tied to CEO",
                "notice_incentives": "12-month notice; ESOP vesting",
                "source": "(DOC: management agent)",
            },
            {
                "person": "Sam Finance (CFO)",
                "what_depends": "Treasury and lender relationships tied to CFO",
                "notice_incentives": "N/A (data room did not provide it)",
                "source": "(DOC: management agent)",
            },
        ],
        "succession": [
            {
                "role": "CEO",
                "incumbent": "Alex Founder",
                "second_line": "N/A (data room did not provide it)",
                "succession_status": "Succession gap flagged in HR pack",
                "source": "(DOC: management agent)",
            },
        ],
    }


def _capital() -> dict:
    return {
        "insight_snapshot": "Capital Structure — schedule partial.",
        "facilities": [
            {
                "facility": "Senior Term Loan A",
                "covenants_headroom": "Net debt/EBITDA 0.4x headroom",
                "lender": "Bank Syndicate A",
            },
            {
                "facility": "Senior Term Loan B",
                "covenants_headroom": "Information request: covenants / headroom",
            },
        ],
        "cash_split": [
            {
                "bucket": "Freely available",
                "amount": 40.0,
                "counts_against_debt": "Yes",
            },
            {
                "bucket": "Restricted",
                "amount": 12.0,
                "counts_against_debt": "No",
            },
        ],
        "debt_like_items": [
            {
                "item": "Overdue trade creditors",
                "kind": "Overdue trade creditors",
                "amount": 8.0,
            },
        ],
        "schedule_gaps": [],
        "cash_burn_rate_monthly_inr_cr": 85,
    }


def _cash_flow() -> dict:
    return {
        "insight_snapshot": "Cash Flow bridge opened — liquidity headroom thin.",
        "bridge": [
            {"line": "Operating cash", "amount": 12.0},
            {"line": "Working capital outflow", "amount": -8.0},
        ],
        "working_capital": [{"item": "Trade creditors stretch", "note": "Elevated DPO"}],
    }


def _legacy() -> dict:
    return {
        "dd_code": "DD-21",
        "tech_components": [
            {
                "component": "Core Platform",
                "maturity_score": 3.0,
                "key_risk": "Stability issues in older firmware",
            },
            {
                "component": "Mobile App",
                "maturity_score": 4.0,
                "key_risk": "Battery drain reports",
            },
        ],
        "technical_risks": [
            "Cybersecurity: penetration testing not yet complete.",
            "Firmware fragmentation across 5 legacy versions.",
        ],
        "scalability_notes": [
            "Attrition in platform engineering above plan.",
        ],
    }


def test_internal_risk_prompt_book_listed() -> None:
    system = compose_system("internal_risk", sector="EV", geography="India")
    assert "internal_risk" in listed_agents()
    assert "key-person" in system.lower() or "individuals" in system.lower()
    body = agent_prompt("internal_risk")
    assert "Ola" not in body and "SoftBank" not in body
    assert "untested" in body.lower()
    assert "first hundred" in body.lower() or "hundred days" in body.lower()
    assert "management agent" in body.lower()
    assert "root cause" in body.lower()
    assert "manageable" in body.lower()
    assert "deal perimeter" in system.lower() or "as-of" in system.lower()


def test_internal_risk_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_internal_risk.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_key_person_from_management_agent() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    kps = [
        r for r in (heur.get("key_person_exposure") or [])
        if isinstance(r, dict) and not str(r.get("person") or "").startswith("Information")
    ]
    assert len(kps) >= 2
    names = " ".join(str(k.get("person") or "") for k in kps)
    assert "Alex Founder" in names
    assert "Sam Finance" in names
    for k in kps:
        assert k.get("what_depends")
        assert k.get("effect_if_left")


def test_key_person_fallback_from_executives_roster() -> None:
    """Empty key_persons still yields CEO exposure from the MQ executive roster."""
    heur = _heuristic_internal_risk_spec(
        company="Compost Crew",
        corpus=_ir_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec={
            "insight_snapshot": "thin",
            "key_persons": [],
            "executives": [
                {
                    "name": "Ben Parry",
                    "role": "CEO",
                    "criticality": "5",
                    "replaceability": "1",
                }
            ],
            "succession": [],
        },
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    kps = [
        r for r in (heur.get("key_person_exposure") or [])
        if isinstance(r, dict) and not str(r.get("person") or "").startswith("Information")
    ]
    assert len(kps) >= 1
    assert "Parry" in str(kps[0].get("person") or "")


def test_financial_strain_indicators() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    strain = heur.get("financial_strain") or []
    indicators = {
        str(s.get("indicator") or "") for s in strain if isinstance(s, dict)
    }
    assert any("Cash" in i or "liquidity" in i.lower() for i in indicators)
    assert any("Covenant" in i for i in indicators)
    assert any("Creditor" in i for i in indicators)
    assert any("Distribution" in i for i in indicators)


def test_observed_vs_untested_controls() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
    )
    observed = [
        o for o in (heur.get("observed_weaknesses") or [])
        if isinstance(o, dict) and str(o.get("status") or "") == "Observed"
    ]
    assert observed
    tested = heur.get("control_testing") or []
    statuses = {str(t.get("tested") or "") for t in tested if isinstance(t, dict)}
    assert any("Not tested" in s or "Tested" in s for s in statuses)
    # Untested must not be labelled as failed
    for t in tested:
        if isinstance(t, dict) and "not tested" in str(t.get("tested") or "").lower():
            result = str(t.get("result") or "").lower()
            assert "is failed" not in result
            assert "control failed" not in result
            assert "not a failure" in result or "not failed" in result or "untested" in result


def test_remediation_and_rank() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
    )
    rem = [
        r for r in (heur.get("remediation") or [])
        if isinstance(r, dict) and not str(r.get("item") or "").startswith("Information")
    ]
    assert rem
    for r in rem[:2]:
        assert r.get("timing")
    ranked = [
        r for r in (heur.get("ranked_effects") or [])
        if isinstance(r, dict) and not str(r.get("risk") or "").startswith("Information")
    ]
    assert ranked
    effects = {str(r.get("effect") or "") for r in ranked}
    assert any(
        e in effects for e in ("Price", "Structure", "First hundred days")
    )


def test_risk_register_schema_and_qa() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["05_Financial_Due_Diligence.pdf", "10_HR_Organizational_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
        operational_spec={"insight_snapshot": "Ops risk opened"},
        regulatory_spec={"permit_register": [{"identifier": "Factory licence"}]},
        tech_spec={"insight_snapshot": "IP/tech opened"},
    )
    register = [
        r for r in (heur.get("risk_register") or [])
        if isinstance(r, dict) and not str(r.get("risk") or "").startswith("Information")
    ]
    assert register
    for r in register[:3]:
        assert r.get("root_cause")
        assert r.get("event")
        assert r.get("exposure")
        assert r.get("controls")
        assert r.get("residual")
        assert r.get("owner")
        assert r.get("action")
        assert r.get("evidence_class") in {"known_weakness", "uncertainty"}
    upstream = heur.get("upstream_registers") or {}
    assert upstream.get("present", {}).get("management_quality") is True
    assert upstream.get("present", {}).get("capital_structure") is True
    assert upstream.get("present", {}).get("cash_flow") is True
    qa = heur.get("ir_evidence_qa") or []
    checks = {r.get("check") for r in qa if isinstance(r, dict)}
    for need in (
        "upstream_registers",
        "risk_row_schema",
        "known_vs_uncertainty",
        "quantified_where_possible",
        "conflict_reconcile",
        "pre_vs_post_close",
        "no_manageable_blocker_silence",
    ):
        assert need in checks
    mgmt_qa = next(r for r in qa if r.get("check") == "upstream_registers")
    assert mgmt_qa.get("status") == "PASS"
    silence_qa = next(r for r in qa if r.get("check") == "no_manageable_blocker_silence")
    assert silence_qa.get("status") == "PASS"
    assert isinstance(heur.get("questions"), list)
    if any(isinstance(r, dict) and r.get("status") == "FAIL" for r in qa):
        assert heur.get("reliance_verdict") != "READY" or heur.get("questions")


def test_manageable_blocker_silence_fails_qa() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus() + " Covenant breach is a manageable risk that can be managed away.",
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    qa = heur.get("ir_evidence_qa") or []
    silence = next(r for r in qa if r.get("check") == "no_manageable_blocker_silence")
    # Covenant / liquidity typically ranks Structure — silence should FAIL
    assert silence.get("status") == "FAIL"
    assert heur.get("reliance_verdict") != "READY"


def test_legacy_dual_write() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus(),
        sources=["08_Technical_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
    )
    assert heur.get("tech_components")
    assert heur.get("technical_risks") is not None
    assert heur.get("scalability_notes") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_render_no_invest() -> None:
    heur = _heuristic_internal_risk_spec(
        company="Test3",
        corpus=_ir_corpus() + " We recommend invest.",
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    md = render_internal_risk_markdown("Internal Risk", heur)
    assert "## 1. Key-Person" in md
    assert "## 2. Financial Strain" in md
    assert "## 3. Control & Governance" in md
    assert "## 4. Remediation" in md
    assert "## 5. Ranked by Price" in md
    assert "## 6. Risk Register" in md
    assert "## 7. Internal Risk Evidence QA" in md
    assert "## 8. Questions and Inputs Required" in md
    assert "## 9. Quality & Reliance" in md
    assert "Untested is not failed" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Root cause" in md


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "internal_risk",
        "agentName": "Internal Risk",
        "target_company": "Test3",
        "summary": "Internal Risk for Test3",
        "sources": ["10_HR_Organizational_Due_Diligence.pdf"],
        "spec": _heuristic_internal_risk_spec(
            company="Test3",
            corpus=_ir_corpus(),
            sources=["10_HR_Organizational_Due_Diligence.pdf"],
            legacy_spec=_legacy(),
            management_spec=_management(),
            capital_spec=_capital(),
            cash_flow_spec=_cash_flow(),
        ),
    }
    md = render_agent_document("internal_risk", output)
    assert "## 9. Quality & Reliance" in md or "## 6. Risk Register" in md
    assert "Key-Person" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_internal_risk_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_ir_corpus(),
        sources=["10_HR_Organizational_Due_Diligence.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
        management_spec=_management(),
        capital_spec=_capital(),
        cash_flow_spec=_cash_flow(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "DD-21"
    assert isinstance(spec.get("deal_slots"), dict)
    assert spec.get("ir_evidence_qa")
    assert spec.get("risk_register")
