"""Regulatory Compliance — DiligenceIQ prompt-book jurisdiction-real compliance."""

from __future__ import annotations

from pathlib import Path

from agetic_cdd_api.agent_document_regulatory_compliance import (
    _heuristic_regulatory_compliance_spec,
    build_regulatory_compliance_spec,
    render_regulatory_compliance_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-rc-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _rc_corpus() -> str:
    return (
        "Regulatory Compliance Status. "
        "Companies Act Compliance MCA / ROC Compliant Low. "
        "SEBI LODR (Post-IPO) SEBI Compliant Low. "
        "GST Filing GSTN Compliant Low. "
        "FAME-II Subsidy Claims MHI / DHI Under Review Medium. "
        "CCPA Consumer Complaints CCPA Active Proceedings High. "
        "AIS 156 Battery Safety Standard BIS / AIS Compliant (Gen 2+) Low. "
        "Environmental Clearance (Factory) MoEFCC Obtained Low. "
        "Labor Law Compliance (Factories Act) State Labour Dept. Generally Compliant Low. "
        "Data Protection (DPDPA 2023) MeitY Implementation Ongoing Medium. "
        "Customs / IGCR (Import duties) CBIC Under Assessment Medium. "
        "Key Legal Risks & Litigation. "
        "CCPA Class Complaint (Service Deficiency) Consumer Protection INR 120 Crore Active. "
        "IP Dispute (Battery Design Patent) IP Litigation INR 35 Crore Pre-litigation. "
        "FAME-II Subsidy Recovery Notice Regulatory INR 300 Crore Disputed — Under Appeal. "
        "Tax Assessment (Transfer Pricing) Income Tax Act INR 85 Crore Commissioner Appeal. "
        "Change of control consent required for environmental clearance transfer. "
        "ISO 9001 certification award received — not a compliance test. "
        "Sample GST filings tested — inspection passed for FY2024."
    )


def _legacy() -> dict:
    return {
        "role_code": "F-04",
        "risks": [
            {
                "clause": "CCPA Consumer Complaints — Active Proceedings (High risk)",
                "severity": 5,
                "mitigant": "Counsel review and carve-outs",
            },
            {
                "clause": "FAME-II Subsidy Claims — Under Review (Medium risk)",
                "severity": 4,
                "mitigant": "Counsel review and carve-outs",
            },
            {
                "clause": "Companies Act Compliance — Compliant (Low risk)",
                "severity": 2,
                "mitigant": "Monitor in legal DD",
            },
            {
                "clause": "Environmental Clearance (Factory) — Obtained (Low risk)",
                "severity": 2,
                "mitigant": "Monitor in legal DD",
            },
            {
                "clause": "Data Protection (DPDPA 2023) — Implementation Ongoing (Medium risk)",
                "severity": 4,
                "mitigant": "Counsel review and carve-outs",
            },
        ],
        "restricted_activities": [
            "Supply Agreements: Long-term agreements with key battery cell suppliers.",
            "Financing Facilities: Consortium facilities — key covenants reviewed.",
        ],
        "data_handling": [
            "Data Protection (DPDPA 2023) — Implementation Ongoing (Medium risk)",
        ],
        "penalty_notes": [
            "CCPA Class Complaint (Service Deficiency) Consumer Protection INR 120 Crore",
            "IP Dispute (Battery Design Patent) IP Litigation INR 35 Crore",
            "FAME-II Subsidy Recovery Notice Regulatory INR 300 Crore",
        ],
    }


def test_regulatory_compliance_prompt_book_listed() -> None:
    system = compose_system("regulatory_compliance", sector="EV", geography="India")
    assert "regulatory_compliance" in listed_agents()
    assert "permit" in system.lower() or "licence" in system.lower() or "license" in system.lower()
    body = agent_prompt("regulatory_compliance")
    assert "Ola" not in body and "SoftBank" not in body
    assert "untested" in body.lower()
    assert "award" in body.lower() or "certification" in body.lower()
    assert "never invent" in body.lower()


def test_regulatory_compliance_not_company_hardcoded() -> None:
    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_regulatory_compliance.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|", "Bhavish"):
        assert banned not in text, f"hardcoded: {banned}"


def test_permit_register_has_expiry_and_transfer() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    permits = [
        p for p in (heur.get("permit_register") or [])
        if isinstance(p, dict) and not str(p.get("identifier") or "").startswith("Information")
    ]
    assert permits
    for p in permits[:3]:
        assert p.get("holder")
        assert p.get("expiry")
        assert p.get("renewal_status")
        assert p.get("transfer_on_coc")


def test_untested_not_recorded_as_compliant() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    obligations = [
        o for o in (heur.get("obligations") or [])
        if isinstance(o, dict) and not str(o.get("obligation") or "").startswith("Information")
    ]
    assert obligations
    # Pack "Compliant" without a test cue must stay Untested
    companies_act = next(
        (
            o for o in obligations
            if "companies act" in str(o.get("obligation") or "").lower()
        ),
        None,
    )
    if companies_act:
        assert companies_act.get("tested") == "Untested"
        assert "not recorded as compliant" in str(companies_act.get("evidence") or "").lower() or (
            "not treated as tested" in str(companies_act.get("evidence") or "").lower()
        )
    # At least one Tested from GST sample
    assert any(str(o.get("tested") or "") == "Tested" for o in obligations)


def test_award_is_not_compliance_evidence() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_regulatory_compliance_markdown("Regulatory Compliance", heur)
    assert "award" in md.lower() or "certification" in md.lower()
    assert "not evidence of compliance" in md.lower()
    # No obligation should be Tested solely on ISO award language
    for o in heur.get("obligations") or []:
        if not isinstance(o, dict):
            continue
        ev = str(o.get("evidence") or "").lower()
        if "iso" in ev or "award" in ev:
            assert o.get("tested") == "Untested"


def test_litigation_never_invents_probability() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    lit = [
        r for r in (heur.get("litigation_register") or [])
        if isinstance(r, dict) and not str(r.get("matter") or "").startswith("Information")
    ]
    assert lit
    for r in lit:
        assert r.get("numeric_probability") is None
        assert r.get("matter")
        assert r.get("claimed_amount") or r.get("status")


def test_transaction_implications_present() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    txn = [
        t for t in (heur.get("transaction_implications") or [])
        if isinstance(t, dict) and not str(t.get("implication") or "").startswith("Information")
    ]
    assert txn
    kinds = " ".join(str(t.get("implication") or "") for t in txn).lower()
    assert any(k in kinds for k in ("consent", "indemnity", "condition", "notification", "escrow"))


def test_legacy_dual_write() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    assert heur.get("risks")
    assert heur.get("penalty_notes") is not None
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert heur.get("dd_code") == "F-04" or heur.get("role_code") == "F-04"


def test_render_no_invest() -> None:
    heur = _heuristic_regulatory_compliance_spec(
        company="Test3",
        corpus=_rc_corpus() + " We recommend invest.",
        sources=["06_Legal_Due_Diligence.pdf"],
        geography="India",
        legacy_spec=_legacy(),
    )
    md = render_regulatory_compliance_markdown("Regulatory Compliance", heur)
    assert "## 1. Applicable Laws" in md
    assert "## 2. Permit & Licence Register" in md
    assert "## 3. Obligations" in md
    assert "## 4. Litigation" in md
    assert "## 5. Transaction Implications" in md
    assert "## 6. Quality & Reliance" in md
    assert "Untested" in md
    assert "**Recommendation:**" not in md
    assert "we recommend invest" not in md.lower()
    assert "Not assigned" in md or "no evidenced basis" in md.lower()


def test_render_agent_document_dispatch() -> None:
    output = {
        "agent_key": "regulatory_compliance",
        "agentName": "Regulatory Compliance",
        "target_company": "Test3",
        "summary": "Regulatory Compliance for Test3",
        "sources": ["06_Legal_Due_Diligence.pdf"],
        "spec": _heuristic_regulatory_compliance_spec(
            company="Test3",
            corpus=_rc_corpus(),
            sources=["06_Legal_Due_Diligence.pdf"],
            geography="India",
            legacy_spec=_legacy(),
        ),
    }
    md = render_agent_document("regulatory_compliance", output)
    assert "## 6. Quality & Reliance" in md
    assert "Permit" in md or "Licence" in md or "License" in md


def test_build_prefers_heuristic_when_flagged() -> None:
    deal = _FakeDeal()
    spec = build_regulatory_compliance_spec(
        deal,  # type: ignore[arg-type]
        index={"documents": []},
        company="Test3",
        corpus=_rc_corpus(),
        sources=["06_Legal_Due_Diligence.pdf"],
        prefer_heuristic=True,
        legacy_spec=_legacy(),
    )
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("role_code") == "F-04" or spec.get("dd_code") == "F-04"
