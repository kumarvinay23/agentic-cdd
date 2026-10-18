"""Company Background — DiligenceIQ prompt-book operating picture."""

from __future__ import annotations

from agetic_cdd_api.agent_document_company_background import (
    _heuristic_company_background_spec,
    _parse_headcount_by_function,
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
    assert "## 6. Quality & Reliance" in md
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
    assert isinstance(heur.get("questions"), list)
    # Thin-evidence path must emit Questions with closure tests
    thin = _heuristic_company_background_spec(
        company="SparseCo",
        corpus="SparseCo Limited provides services. No mix disclosed.",
        sources=["note.pdf"],
        entity={"legal_name": "SparseCo Limited"},
    )
    assert thin.get("questions")
    from agetic_cdd_api.prompt_book import questions_complete

    assert questions_complete(thin["questions"])
    thin_md = render_company_background_markdown("Company Background", thin)
    assert "Questions and Inputs Required" in thin_md
    assert "Closure Test" in thin_md


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
    assert "## 6. Quality & Reliance" in rendered


def test_canonicalize_cap_table_includes_small_option_grants() -> None:
    from agetic_cdd_api.agent_document_company_background import (
        _canonicalize_cap_table_text,
        _ledger_named_holdings,
        _ledger_share_quantities,
    )

    # Regression: earlier parser dropped Tiffany 2,070 (looked like year 2070)
    # and failed to re-sum when only Ben+Dan appeared in the parenthetical.
    wrong = (
        "Total evidenced common equity/option shares: 10,200,010 "
        "(10,000,010 + 200,000). Ben Parry 10,000,010; Dan Israel 200,000; "
        "Tiffany Williams 2,070; Timothy Jenkins 481."
    )
    qtys = _ledger_share_quantities(wrong)
    assert qtys == [10_000_010, 200_000, 2_070, 481]
    assert sum(qtys) == 10_202_561
    fixed = _canonicalize_cap_table_text(wrong)
    assert fixed is not None
    assert "10,202,561" in fixed.split(".", 1)[0]
    assert "10,200,010" not in fixed.split(".", 1)[0]

    ledger = (
        "Securities ledger: 10,000,010 (Ben Parry), 200,000 (Dan Israel), "
        "2,070 (Tiffany Williams), 481 (Timothy Jenkins)."
    )
    assert "10,202,561" in (_canonicalize_cap_table_text(ledger) or "")

    # Full certificate ledger — Dan Israel holds CS-03 + CS-06 + CS-07 = 292,300.
    # Totals / % must come from summing this scrape, not a hardcoded canon.
    full = (
        "Cap Table Summary — Common Stock outstanding 10,294,861. "
        "Ben Parry 61.27% of all outstanding; 55.26% fully diluted. "
        "Securities ledger: "
        "CS-01 Ben Parry 10,000,010; "
        "CS-03 Dan Israel 200,000; "
        "CS-06 Dan Israel 687; "
        "CS-07 Dan Israel 91,613; "
        "Tiffany Williams 2,070; Timothy Jenkins 481."
    )
    holdings = _ledger_named_holdings(full)
    assert holdings.get("Dan Israel") == 292_300
    assert holdings.get("Ben Parry") == 10_000_010
    canon = _canonicalize_cap_table_text(full)
    assert canon is not None
    assert "10,294,861" in canon
    assert "292,300" in canon
    assert "97.14%" in canon
    assert "61.27%" in canon
    assert "55.26%" in canon
    assert "<0.01%" in canon or "Timothy Jenkins 481 (<0.01%" in (canon or "")
    assert "0.00% of common" not in (canon or "")

    # Multi-line ledger: certificates after the header must still be summed.
    multiline = (
        "Cap Table Summary — Common Stock outstanding 10,294,861.\n"
        "Securities ledger:\n"
        "CS-01 Ben Parry 10,000,010\n"
        "CS-03 Dan Israel 200,000\n"
        "CS-06 Dan Israel 687\n"
        "CS-07 Dan Israel 91,613\n"
        "Tiffany Williams 2,070\n"
        "Timothy Jenkins 481\n"
    )
    assert _ledger_named_holdings(multiline).get("Dan Israel") == 292_300
    assert "10,294,861" in (_canonicalize_cap_table_text(multiline) or "")

    # Employee Yes/No column must not drop CS-06/CS-07 or invent "Dan Israel No".
    with_employee_col = (
        "Cap Table Summary — Common Stock outstanding 10,294,861. "
        "Ben Parry 61.27% of all outstanding; 55.26% fully diluted. "
        "CS-01 Ben Parry CEO Yes 10,000,010; "
        "CS-03 Dan Israel Senior Vice President No 200,000; "
        "CS-06 Dan Israel No 687; "
        "CS-07 Dan Israel No 91,613; "
        "Tiffany Williams Commercial Driver Yes 2,070; "
        "Timothy Jenkins Composting Lead Operator Yes 481."
    )
    emp_h = _ledger_named_holdings(with_employee_col)
    assert emp_h.get("Dan Israel") == 292_300
    assert emp_h.get("Ben Parry") == 10_000_010
    assert not any(" no" in k.lower() or k.lower().endswith(" yes") for k in emp_h)
    emp_c = _canonicalize_cap_table_text(with_employee_col)
    assert emp_c is not None
    assert "10,294,861" in emp_c
    assert "292,300" in emp_c
    assert "97.14%" in emp_c
    assert "Dan Israel No" not in emp_c

    # Blank holder + Employee=No on later certs → carry forward prior holder.
    carry = (
        "Cap Table Summary — Common Stock outstanding 10,294,861\n"
        "CS-01\tBen Parry\tCEO\tYes\t10,000,010\n"
        "CS-03\tDan Israel\tSVP\tNo\t200,000\n"
        "CS-06\t687\tNo\n"
        "CS-07\t91,613\tNo\n"
        "Tiffany Williams\t2,070\n"
        "Timothy Jenkins\t481\n"
    )
    assert _ledger_named_holdings(carry).get("Dan Israel") == 292_300

    # PDF/table extract: Certificate / Shares / Holder on separate lines.
    stacked = (
        "Cap Table Summary — Common Stock outstanding 10,294,861.\n"
        "CS-01\n10,000,010\nBen Parry\n"
        "CS-03\n200,000\nDan Israel\n"
        "CS-06\n687\nDan Israel\n"
        "CS-07\n91,613\nDan Israel\n"
        "CS-08\n2,070\nTiffany Williams\n"
        "CS-09\n481\nTimothy Jenkins\n"
    )
    stacked_h = _ledger_named_holdings(stacked)
    assert stacked_h.get("Dan Israel") == 292_300
    assert stacked_h.get("Ben Parry") == 10_000_010
    stacked_c = _canonicalize_cap_table_text(stacked)
    assert stacked_c is not None
    assert "10,294,861" in stacked_c
    assert "97.14%" in stacked_c

    # Job Title beside a holder must not drop the block; titles re-attach from text.
    with_title = (
        "Cap Table Summary — Common Stock outstanding 10,294,861. "
        "CS-01 Ben Parry CEO 10,000,010; "
        "CS-03 Dan Israel Senior Vice President 200,000; "
        "CS-06 Dan Israel 687; CS-07 Dan Israel 91,613; "
        "Tiffany Williams Commercial Driver 2,070; Timothy Jenkins 481."
    )
    titled = _ledger_named_holdings(with_title)
    assert titled.get("Ben Parry") == 10_000_010
    assert titled.get("Dan Israel") == 292_300
    assert all("CEO" not in n and "SVP" not in n.upper() for n in titled)
    canon_t = _canonicalize_cap_table_text(with_title)
    assert canon_t is not None
    assert "10,294,861" in canon_t
    assert "Ben Parry (CEO)" in canon_t
    assert "Commercial Driver" in canon_t

    # Controlling holder omitted from scrape — do NOT invent them; note stated gap.
    no_ctrl = (
        "Cap Table Summary — Common Stock outstanding 10,294,861. "
        "Dan Israel 200,000; Tiffany Williams 2,070; Timothy Jenkins 481."
    )
    partial = _canonicalize_cap_table_text(no_ctrl)
    assert partial is not None
    assert "Ben Parry" not in partial
    assert "10,000,010" not in partial
    assert "Dan Israel" in partial
    assert "10,294,861" in partial
    assert "Attributed certificates" in partial or "202,551" in partial


def test_stated_outstanding_after_sentence_period() -> None:
    """'…. Common Stock outstanding N' must still set the total when CS rows are thin."""
    from agetic_cdd_api.agent_document_company_background import (
        _canonicalize_cap_table_text,
    )

    thin = (
        "Cap table: Ben Parry 10,000,010, Dan Israel 200,000, "
        "Tiffany Williams 2,070, Timothy Jenkins 481. "
        "Common Stock outstanding 10,294,861. "
        "Ben Parry 61.27% of all outstanding."
    )
    canon = _canonicalize_cap_table_text(thin)
    assert canon is not None
    assert "10,294,861" in canon
    # Only Ben gets the pack's "of all outstanding" % — not every holder.
    assert canon.count("61.27% of all outstanding") == 1


def test_headcount_and_heuristic_tolerate_empty_sources() -> None:
    """Empty sources must not IndexError; heuristic return must be complete."""
    rows = _parse_headcount_by_function(
        "Total Headcount (FTE) 3,200 Technology / R&D 650 1,800 2,200",
        [],
    )
    assert isinstance(rows, list)
    heur = _heuristic_company_background_spec(
        company="SparseCo",
        corpus="SparseCo Limited provides organics services in the UK.",
        sources=[],
        entity={"legal_name": "SparseCo Limited"},
    )
    assert heur.get("offers")
    assert heur.get("quality_verdict") in {"PASS", "REWORK"}
    assert heur.get("reliance_verdict") in {"READY", "LIMITED", "BLOCKED"}
    assert isinstance(heur.get("questions"), list)
    assert "composer" in heur
