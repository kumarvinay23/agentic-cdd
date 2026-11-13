"""Agents receive the passages an analyst marked, and gap lines stay rare."""

from agetic_cdd_api.pipeline_catalog import all_agent_keys, report_agent_keys
from agetic_cdd_api.services_evidence_router import (
    AGENT_NEEDS,
    coverage_check,
    evidence_pack,
    false_gap_rate,
    prefer_data_room_figure,
    recall,
    route_evidence,
    search_queries,
    tag_text,
)


def _capital_chunks() -> list[dict]:
    marked = [
        ("c-debt", "Net debt schedule: borrowings 10 and cash 4."),
        ("c-facility", "Facility record: the credit facility is a term loan from First American Bank."),
        ("c-cap", "Cap table lists common units held by the seller."),
        ("c-terms", "Financing terms set an interest rate of 7.45 percent and a loan covenant."),
    ]
    chunks = [{"chunk_id": cid, "text": text, "topics": tag_text(text)} for cid, text in marked]
    generic = (
        "Company overview founded by the management team. Forecast budget and market growth. "
        "Competitor total revenue and a key risk. Customer satisfaction and net promoter score. "
        "Demand driver remains usage growth. Net debt is mentioned only in this overview."
    )
    chunks.append({"chunk_id": "c-generic", "text": generic, "topics": tag_text(generic)})
    chunks.append(
        {
            "chunk_id": "c-other",
            "text": "Customer concentration is low and the top customer is a municipality.",
            "topics": tag_text("Customer concentration is low and the top customer is a municipality."),
        }
    )
    return chunks


def test_capital_structure_declares_the_four_financing_needs() -> None:
    assert AGENT_NEEDS["capital_structure"] == (
        "net_debt_schedule",
        "facility_record",
        "cap_table",
        "financing_terms",
    )


def test_every_analysis_agent_declares_needs() -> None:
    reports = set(report_agent_keys())
    missing = [key for key in all_agent_keys() if key not in reports and key not in AGENT_NEEDS]
    assert missing == []
    for key in AGENT_NEEDS:
        report = coverage_check(key, [])
        assert report["needs"]
        assert all(need["statement"] for need in report["needs"])


def test_one_chunk_can_serve_two_agents() -> None:
    text = "Net debt schedule is 10. Customer segment mix is commercial and residential."
    topics = tag_text(text)
    assert "net_debt_schedule" in topics
    assert "segment_schedule" in topics
    chunk = [{"chunk_id": "shared", "text": text, "topics": topics}]
    assert route_evidence("capital_structure", chunk)
    assert route_evidence("customer_segmentation", chunk)


def test_queries_omit_the_company_name() -> None:
    queries = search_queries("capital_structure", company="Baytown Travel Centre")
    joined = " ".join(queries).lower()
    assert "baytown" not in joined
    assert "travel" not in joined
    assert "net debt" in joined


def test_agents_receive_marked_evidence_and_gaps_are_rare() -> None:
    relevant = []
    chunks = []
    for index in range(20):
        phrase = (
            "Net debt schedule",
            "Credit facility term loan",
            "Cap table ownership table",
            "Financing terms interest rate",
        )[index % 4]
        chunk_id = f"rel-{index}"
        text = f"{phrase} for period {index} with supporting detail in the workbook."
        relevant.append(chunk_id)
        chunks.append({"chunk_id": chunk_id, "text": text, "topics": tag_text(text)})
    chunks.extend(_capital_chunks())
    routed = route_evidence("capital_structure", chunks, company="Baytown")
    received = [row["chunk_id"] for row in routed]
    assert recall(relevant, received) >= 0.95
    generic = next(row for row in routed if row["chunk_id"] == "c-generic")
    assert routed[0]["score"] > generic["score"]

    report = coverage_check("capital_structure", chunks, company="Baytown")
    statements = []
    for need in report["needs"]:
        actually_missing = need["status"] == "not_found"
        statements.append((actually_missing, need["statement"]))
    assert false_gap_rate(statements) < 0.02
    assert all(need["status"] == "met" for need in report["needs"])
    assert all(need["statement"] is None for need in report["needs"])


def test_a_missing_need_names_the_searches() -> None:
    report = coverage_check("capital_structure", [], company="Northwind")
    gaps = [need for need in report["needs"] if need["status"] == "not_found"]
    assert len(gaps) == 4
    assert all("not in the data room" in need["statement"] for need in gaps)
    assert all(need["searches"] for need in gaps)
    planted = [(True, need["statement"]) for need in gaps]
    planted.append((False, None))
    assert false_gap_rate(planted) == 0.0
    assert false_gap_rate([(False, "net debt is not in the data room. Searches: net debt")]) == 1.0


def test_fact_store_number_meets_a_need_without_text() -> None:
    report = coverage_check(
        "capital_structure",
        [],
        facts={"net_debt_schedule": 10},
    )
    debt = next(need for need in report["needs"] if need["need_id"] == "net_debt_schedule")
    assert debt["status"] == "met"
    assert debt["source"] == "fact_store"
    assert debt["statement"] is None


def test_web_figure_never_overrides_a_data_room_figure() -> None:
    web = {
        "value": 99,
        "url": "https://example.com/market",
        "retrieved_on": "2026-10-31",
        "tier": "web",
    }
    kept = prefer_data_room_figure(10, web)
    assert kept["value"] == 10
    assert kept["tier"] == "data_room"
    fallback = prefer_data_room_figure(None, web)
    assert fallback["value"] == 99
    assert fallback["tier"] == "web"
    assert fallback["url"] == "https://example.com/market"
    assert fallback["retrieved_on"] == "2026-10-31"


def test_chart_keeps_the_data_room_share() -> None:
    from agetic_cdd_api.services_document_runner import _extract_share_chart

    chart = _extract_share_chart(
        [
            {
                "origin": "web",
                "tier": "web",
                "url": "https://example.com/share",
                "retrieved_on": "2026-10-31",
                "passages": ["Ola Electric holds 99% share while Ather Energy at 40%."],
            },
            {
                "origin": "internal",
                "tier": "data_room",
                "passages": ["Ola Electric holds 32% share while Ather Energy at 18%."],
            },
        ]
    )
    assert chart is not None
    values = [row["value"] for row in chart["series"]]
    assert 32.0 in values
    assert 18.0 in values
    assert 99.0 not in values
    assert 40.0 not in values


def test_deep_dive_pack_routes_the_agent() -> None:
    from agetic_cdd_api.services_deep_dive import _evidence_for_role

    pack = evidence_pack(
        "capital_structure",
        ["Net debt schedule shows borrowings of 10 and cash of 4 for the year."],
        company="Baytown",
    )
    wired = _evidence_for_role(
        "capital_structure",
        ["Net debt schedule shows borrowings of 10 and cash of 4 for the year."],
        "Baytown",
    )
    assert pack["needs"][0]["need_id"] == "net_debt_schedule"
    assert pack["needs"][0]["status"] == "met"
    assert wired["needs"][0]["status"] == "met"
