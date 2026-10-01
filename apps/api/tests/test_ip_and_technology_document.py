"""IP & Technology — DiligenceIQ prompt-book owned vs rented systems."""

from __future__ import annotations

from agetic_cdd_api.agent_document_ip_and_technology import (
    _heuristic_ip_and_technology_spec,
    build_ip_and_technology_spec,
    render_ip_and_technology_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import agent_prompt, compose_system, listed_agents


class _FakeDeal:
    id = "deal-ip-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ip_corpus() -> str:
    return (
        "Technology Stack Assessment. MoveOS Software Ecosystem is proprietary "
        "in-house firmware owned by the company — Linux-based OTA capable. "
        "CRM Salesforce licensed SaaS for customer records. "
        "Billing and collections run on SAP subscription licence from SAP India. "
        "Plant processing equipment uses ordinary industry CNC tooling. "
        "Telematics fleet tracking via vendor AWS IoT Core — third-party hosted. "
        "Patent IN2023112345 granted India — registered owner company per IPO certificate. "
        "Trademark OLA MOVE pending USPTO. "
        "Salesforce MSA: change-of-control consent required; licence is non-transferable "
        "without written consent. "
        "SAP licence transfers on novation with 60 days notice. "
        "MoveOS capacity supports 2x plan volume; backup restore tested quarterly in FY2024 drill. "
        "Access control via SSO/RBAC. Integration with billing via REST API. "
        "Legacy billing module EOL by FY2026 — obsolescence risk. "
        "Incident: cloud outage Q1 2024 for 6 hours. "
        "Plan requires CRM upgrade migration by FY2026 at INR 12 Cr capex. "
        "Scheduling and routing not used — no logistics fleet dispatch in this business. "
        "Competitive claim of IP moat from patents must be verified on register."
    )


def test_ip_and_technology_prompt_book_listed() -> None:
    system = compose_system("ip_and_technology", sector="EV", geography="India")
    assert "ip_and_technology" in listed_agents()
    assert "intellectual" in system.lower() or "technology" in system.lower()
    body = agent_prompt("ip_and_technology")
    assert "Ola" not in body and "SoftBank" not in body
    assert "register" in body.lower()
    assert "change of control" in body.lower() or "change-of-control" in body.lower()


def test_ip_and_technology_not_company_hardcoded() -> None:
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "src/agetic_cdd_api/agent_document_ip_and_technology.py"
    )
    text = src.read_text(encoding="utf-8")
    for banned in ("Ola Electric", "SoftBank", "Ather Energy|", "TVS Motor|"):
        assert banned not in text, f"hardcoded: {banned}"
    prompt = agent_prompt("ip_and_technology")
    for banned in ("Ola", "SoftBank"):
        assert banned not in prompt


def test_tech_map_omits_non_applicable_with_reason() -> None:
    heur = _heuristic_ip_and_technology_spec(
        company="Test3",
        corpus=_ip_corpus(),
        sources=["08_Technical_Due_Diligence.pdf"],
    )
    tech_map = heur.get("technology_map") or []
    omitted = [
        t for t in tech_map
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "no"
    ]
    assert omitted
    assert all(_is_reason(t.get("omit_reason")) for t in omitted)
    applies = [
        t for t in tech_map
        if isinstance(t, dict) and str(t.get("applies") or "").lower() == "yes"
    ]
    assert applies


def test_tech_map_ignores_debt_schedule_and_loyalty() -> None:
    """Debt 'Maturity Schedule' and customer 'loyalty' are not run-tech."""
    heur = _heuristic_ip_and_technology_spec(
        company="Test3",
        corpus=(
            "Debt Profile & Maturity Schedule Senior Term Loan A USD 85M March 2027. "
            "Repeat purchase rate signals loyalty deficit versus industry. "
            "No CRM or customer record system described. "
            "MoveOS is proprietary in-house firmware."
        ),
        sources=["05_Financial_Due_Diligence.pdf"],
        legacy_spec={
            "core_tech": [
                "scheduling and routing: Debt Profile & Maturity Schedule …",
                "customer records: Contractual Structure loyalty …",
            ],
        },
    )
    tech_map = {t["category"]: t for t in (heur.get("technology_map") or []) if isinstance(t, dict)}
    sched = tech_map.get("scheduling and routing") or {}
    assert str(sched.get("applies") or "").lower() == "no"
    assert "Maturity Schedule" not in str(sched.get("system_or_method") or "")
    cust = tech_map.get("customer records") or {}
    assert str(cust.get("applies") or "").lower() == "no"
    core = heur.get("core_tech") or []
    assert not any("Maturity Schedule" in str(c) for c in core)
    assert not any("loyalty" in str(c).lower() for c in core)
    assert any("proprietary" in str(c).lower() or "MoveOS" in str(c) for c in core)


def _is_reason(val: object) -> bool:
    text = str(val or "").strip()
    return bool(text) and not text.startswith("Information request")


def test_using_tech_is_not_owning_ip() -> None:
    heur = _heuristic_ip_and_technology_spec(
        company="Test3",
        corpus=_ip_corpus(),
        sources=["a.pdf"],
        competitive_spec={
            "claimed_advantages": [
                {"claim": "IP moat from proprietary technology stack"},
            ],
            "moat_signals": ["patent advantage over peers"],
        },
    )
    md = render_ip_and_technology_markdown("IP & Technology", heur)
    assert "not owning" in md.lower() or "not own" in md.lower()
    ownership = heur.get("ownership_separation") or []
    assert any(
        isinstance(o, dict)
        and o.get("classification") in {
            "owned_ip", "licensed_technology", "vendor_dependency", "ordinary_tooling",
        }
        for o in ownership
    )
    reconcile = heur.get("ip_advantage_reconcile") or {}
    assert reconcile.get("other_agent_claims")


def test_register_verification_flags_assertion() -> None:
    heur = _heuristic_ip_and_technology_spec(
        company="Test3",
        corpus="Company asserts proprietary AI advantage. No register opened.",
        sources=["a.pdf"],
    )
    ownership = heur.get("ownership_separation") or []
    # Assertions without register language must not be Yes-verified
    for o in ownership:
        if not isinstance(o, dict):
            continue
        verified = str(o.get("register_verified") or "")
        if "assertion" in verified.lower() or verified.startswith("No"):
            assert not verified.startswith("Yes — register")


def test_ip_and_technology_markdown_follows_prompt_book() -> None:
    heur = _heuristic_ip_and_technology_spec(
        company="Test3",
        corpus=_ip_corpus(),
        sources=["08_Technical_Due_Diligence.pdf"],
        legacy_spec={
            "patents": ["Patents filed (cumulative): 42"],
            "core_tech": ["MoveOS maturity High"],
            "architecture_notes": ["OTA architecture note"],
        },
        competitive_spec={
            "claimed_advantages": [{"claim": "Patent-backed IP advantage"}],
        },
    )
    md = render_ip_and_technology_markdown("IP & Technology", heur)

    assert "## 1. Technology Map" in md
    assert "## 2. Owned IP" in md
    assert "## 3. Change-of-Control" in md
    assert "## 4. System Fitness" in md
    assert "## 5. Replacement / Upgrade" in md
    assert "## 6. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    coc = heur.get("change_of_control") or []
    assert any(
        isinstance(c, dict)
        and (
            "consent" in str(c.get("transfers_on_coc") or "").lower()
            or "transfer" in str(c.get("transfers_on_coc") or "").lower()
            or "Yes" in str(c.get("transfers_on_coc") or "")
            or "No" in str(c.get("transfers_on_coc") or "")
        )
        for c in coc
    )
    upgrades = heur.get("upgrade_costs") or []
    assert any(
        isinstance(u, dict)
        and (
            "INR" in str(u.get("cost") or "").upper()
            or "FY2026" in str(u.get("when_required") or "")
            or "upgrade" in str(u.get("item") or "").lower()
        )
        for u in upgrades
    )
    assert heur.get("patents")
    assert heur.get("core_tech")
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}


def test_normalise_strips_recommendation() -> None:
    from agetic_cdd_api.agent_document_ip_and_technology import _normalise_llm_spec

    llm = _normalise_llm_spec(
        {
            "insight_snapshot": "Tech is fine — invest",
            "technology_map": [
                {"category": "billing", "applies": "Yes", "system_or_method": "SAP"}
            ],
            "ownership_separation": [
                {
                    "asset": "Patent X",
                    "classification": "owned_ip",
                    "register_verified": "Yes — invented",
                    "evidence": "company says so",
                }
            ],
            "change_of_control": [{"asset": "SAP", "transfers_on_coc": "Unknown"}],
            "system_fitness": [{"system": "SAP", "dimension": "capacity", "assessment": "ok"}],
            "upgrade_costs": [{"item": "CRM upgrade", "cost": "INR 12 Cr"}],
            "recommendation": "Invest",
            "confidence": 0.9,
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
        },
        sources=["a.pdf"],
        legacy_spec=None,
        corpus=_ip_corpus(),
        competitive_spec={
            "claimed_advantages": [{"claim": "IP moat from patents"}],
        },
    )
    assert "recommendation" not in llm
    assert "confidence" not in llm
    assert "invest" not in str(llm.get("insight_snapshot") or "").lower()
    ownership = llm.get("ownership_separation") or []
    assert ownership
    # Invented Yes without register evidence softened
    assert not str(ownership[0].get("register_verified") or "").startswith(
        "Yes — invented"
    )


def test_render_agent_document_ip_and_technology() -> None:
    output = {
        "agentName": "IP & Technology",
        "target_company": "Test3",
        "sources": ["08_Technical_Due_Diligence.pdf"],
        "document": (
            "# IP & Technology\n\n"
            "## 1. Technology Map (How the Business Runs)\n\n"
            "Seeded.\n\n"
            "## 6. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("ip_and_technology", output)
    assert "## 1. Technology Map" in rendered
    assert "**Recommendation:**" not in rendered


def test_build_ip_and_technology_from_corpus() -> None:
    spec = build_ip_and_technology_spec(
        _FakeDeal(),
        index={
            "document_count": 1,
            "documents": [
                {
                    "filename": "08_Technical_Due_Diligence.pdf",
                    "cdl_category": "operations",
                    "doc_kind": "technical",
                    "excerpt": _ip_corpus(),
                }
            ],
            "category_counts": {"operations": 1},
        },
        company="Test3",
        prefer_heuristic=True,
    )
    md = render_ip_and_technology_markdown("IP & Technology", spec)
    assert "## 2. Owned IP" in md
    assert "## Sources" in md
    assert spec.get("composer") == "heuristic_v1"
    assert spec.get("dd_code") == "F-IP"
