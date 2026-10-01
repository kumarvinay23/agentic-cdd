"""Company Background — DiligenceIQ prompt-book operating picture."""

from __future__ import annotations

from agetic_cdd_api.agent_document_company_background import (
    _heuristic_company_background_spec,
    build_company_background_spec,
    render_company_background_markdown,
)
from agetic_cdd_api.agent_document_render import render_agent_document
from agetic_cdd_api.prompt_book import compose_system, listed_agents


class _FakeDeal:
    id = "deal-cb-1"
    name = "Test3"
    company = "Test3"
    sector = "Electric Two-Wheelers"
    geography = "India"


def _ola_index() -> dict:
    corporate = (
        "02 Corporate Overview. Legal Name Ola Electric Mobility Limited. "
        "Founded 2017. Headquarters Bengaluru, Karnataka, India. "
        "Sector Electric Vehicle Manufacturing / Clean Mobility Technology. "
        "Shareholding Structure Bhavish Aggarwal (Founder) 36.9% Promoter "
        "SoftBank Group 10.4% Strategic Institutional. "
        "Product Portfolio S1 Pro Gen 2 S1 Air S1 X Roadster. "
        "Revenue Model Vehicle Sales 88% Accessories & Merchandise 4% "
        "Extended Warranty & AMC 3% Software / Connected Services 2%. "
        "Futurefactory, Krishnagiri, Tamil Nadu manufacturing campus. "
        "Listed August 2024 on BSE & NSE IPO. "
        "annual capacity of 10 million units. capacity utilisation 75%."
    )
    financial = (
        "05 Financial Due Diligence Profit & Loss Summary (INR Crore). "
        "Line Item FY2021 FY2022 FY2023 FY2024E FY2025E "
        "Revenue 8 456 2,630 4,900 8,200 "
        "Sales & Marketing (40) (180) (420) (540) (680) "
        "R&D Expenses (85) (210) (380) (480) (520) "
        "G&A Expenses (35) (120) (320) (380) (430)."
    )
    hr = (
        "10 HR Organizational Due Diligence. Metric FY2022 FY2023 FY2024E "
        "Total Headcount (FTE) 3,200 8,500 9,800 "
        "Technology / R&D 650 1,800 2,200 Sales & Customer 400 1,100 1,400."
    )
    commercial = (
        "04 Commercial Due Diligence. Online Sales Share (%) 72% 70% 68%. "
        "direct-to-consumer digital-first model with experience centers. "
        "The online funnel captures ~68% of orders. "
        "South India 42% North India 28% of sales mix."
    )
    return {
        "document_count": 4,
        "category_counts": {
            "company_management": 2,
            "financial": 1,
            "customer": 1,
        },
        "documents": [
            {
                "filename": "02_Corporate_Overview.pdf",
                "cdl_category": "company_management",
                "excerpt": corporate,
            },
            {
                "filename": "05_Financial_Due_Diligence.pdf",
                "cdl_category": "financial",
                "excerpt": financial,
            },
            {
                "filename": "10_HR_Organizational_Due_Diligence.pdf",
                "cdl_category": "company_management",
                "excerpt": hr,
            },
            {
                "filename": "04_Commercial_Due_Diligence.pdf",
                "cdl_category": "customer",
                "excerpt": commercial,
            },
        ],
    }


def _corpus() -> tuple[str, list[str]]:
    docs = _ola_index()["documents"]
    return " ".join(d["excerpt"] for d in docs), [d["filename"] for d in docs]


def test_company_background_prompt_book_listed() -> None:
    system = compose_system(
        "company_background",
        sector="Electric Two-Wheelers",
        geography="India",
    )
    assert "company_background" in listed_agents()
    assert "Describe the business from its records" in system
    assert system.count("WHERE TO LOOK, IN THIS ORDER") == 1


def test_company_background_markdown_follows_prompt_book() -> None:
    corpus, sources = _corpus()
    heur = _heuristic_company_background_spec(
        company="Test3",
        corpus=corpus,
        sources=sources,
        entity={
            "legal_name": "Ola Electric Mobility Limited",
            "jurisdiction": "Bengaluru, Karnataka, India",
            "incorporation_date": "2017",
            "entity_type": "public",
            "governance_notes": ["Listing: BSE & NSE"],
        },
    )
    md = render_company_background_markdown("Company Background", heur)

    assert "## 1. What It Sells & How It Makes Money" in md
    assert "## 2. Physical Operation" in md
    assert "## 3. Ownership, Legal Entities & History" in md
    assert "## 4. Operating Model" in md
    assert "## 5. Quality & Reliance" in md
    assert "**Recommendation:**" not in md
    assert "**Confidence:**" not in md
    assert "Execution Verdict" not in md
    assert "does not recommend invest or pass" in md.lower()
    assert "Bengaluru" in md
    assert "Bhavish" in md or "SoftBank" in md
    assert "Vehicle Sales" in md or "88%" in md
    assert "S1 Pro" in md
    assert "Headcount by Function" in md
    assert "2,200" in md or "2200" in md or "9,800" in md
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert heur.get("operating_model")
    assert "Invest in" not in (heur.get("operating_model") or "")


def test_build_company_background_spec_renderable() -> None:
    corpus, sources = _corpus()
    spec = build_company_background_spec(
        _FakeDeal(),
        index=_ola_index(),
        company="Test3",
        corpus=corpus,
        sources=sources,
        entity_spec={"legal_name": "Ola Electric Mobility Limited"},
    )
    md = render_company_background_markdown("Company Background", spec)
    assert "## 1. What It Sells" in md
    assert "Preliminary Investment" not in md


def test_render_agent_document_company_background_uses_document() -> None:
    output = {
        "agentName": "Company Background",
        "target_company": "Test3",
        "document": (
            "# Company Background\n\n"
            "## 1. What It Sells & How It Makes Money\n\n"
            "Seeded body.\n\n"
            "## 5. Quality & Reliance\n\n"
            "**Quality:** PASS\n"
        ),
        "spec": {},
    }
    rendered = render_agent_document("company_background", output)
    assert "## 1. What It Sells" in rendered
    assert "Seeded body" in rendered
    assert "**Recommendation:**" not in rendered


def test_render_agent_document_company_background_from_spec() -> None:
    output = {
        "agentName": "Company Background",
        "target_company": "Test3",
        "sources": ["02_Corporate_Overview.pdf"],
        "spec": {
            "legal_name": "Ola Electric Mobility Limited",
            "offers": {
                "sells": "S1 Pro electric scooters",
                "how_charges": "Unit sale",
                "who_pays": "Consumers",
            },
            "revenue_by_service_line": [
                {"label": "Vehicle Sales", "share": "88%", "period": "FY2024E", "source": "(DOC: [1])"}
            ],
            "revenue_by_customer_type": [],
            "revenue_by_geography": [],
            "recurring_by_contract": "Omitted: not stated",
            "accounts_reconciliation": "Headline FY2024E ₹4,900 cr",
            "products_in_company_terms": ["S1 Pro"],
            "omitted_fields": [],
            "sites": [{"site": "Bengaluru", "type": "HQ", "role": "HQ", "source": "(DOC: [1])"}],
            "capacity": {"fleet_or_capacity": "10 million units", "utilisation": "Omitted: n/a", "source": "(DOC: [1])"},
            "headcount_by_function": [
                {"function": "Total", "headcount": "9,800", "period": "FY2024E", "source": "(DOC: [1])"}
            ],
            "ownership": {
                "legal_entities": "Ola Electric Mobility Limited",
                "ownership_or_cap_table": "Founder 36.9%",
                "history_events": [{"date": "2017", "event": "Founded", "evidence": "(DOC: [1])"}],
                "corporate_record_requests": [],
            },
            "operating_model": "One scooter sold D2C from Futurefactory.",
            "quality_verdict": "PASS",
            "reliance_verdict": "LIMITED",
            "quality_reliance_rationale": "Partial geography split.",
        },
    }
    rendered = render_agent_document("company_background", output)
    assert "## 1. What It Sells" in rendered
    assert "Ola Electric Mobility Limited" in rendered
    assert "4,900" in rendered
    assert "**Recommendation:**" not in rendered
    assert "## 5. Quality & Reliance" in rendered
