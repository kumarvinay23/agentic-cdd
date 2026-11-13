"""Route data-room passages by what each agent needs.

Needs are stable ids for schedules, metrics, record types, and document types.
A chunk is tagged by topic, so one passage can serve several agents. Search
uses those topics and their synonyms, with the company name removed. Keyword
and semantic scores are combined, and a passage that every agent would receive
is ranked lower.

Numbers may be satisfied from the fact store. A text need is met or logged as
not found, with the searches that were run. Only that coverage check may say
an item is not in the data room. A web source is lower-tier and never replaces
a data-room figure.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

_TOKEN = re.compile(r"[a-z0-9]{4,}")
_NOT_IN_ROOM = "not in the data room"

# id, kind, phrases an analyst would search. The first phrase is the query.
_NEEDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "net_debt_schedule": ("schedule", ("net debt", "net debt schedule")),
    "facility_record": ("record_type", ("credit facility", "term loan", "facility agreement")),
    "cap_table": ("schedule", ("cap table", "capitalization table", "ownership table")),
    "financing_terms": ("document_type", ("financing terms", "interest rate", "loan covenant")),
    "revenue_schedule": ("schedule", ("revenue schedule", "total revenue", "net revenue")),
    "retention_metric": ("metric", ("net revenue retention", "gross revenue retention", "logo retention")),
    "customer_record": ("record_type", ("customer record", "customer concentration", "top customer")),
    "segment_schedule": ("schedule", ("customer segment", "revenue by segment", "segment mix")),
    "market_size": ("metric", ("market size", "total addressable market", "tam")),
    "market_growth": ("metric", ("market growth", "industry cagr", "market cagr")),
    "competitor_set": ("record_type", ("competitor", "competitive landscape", "market share")),
    "price_level": ("metric", ("market price", "price level", "average selling price")),
    "cost_schedule": ("schedule", ("cost structure", "cost of goods", "operating expense")),
    "supplier_record": ("record_type", ("supplier", "vendor concentration", "supply agreement")),
    "cash_flow_schedule": ("schedule", ("cash flow", "operating cash flow", "free cash flow")),
    "forecast_schedule": ("schedule", ("forecast", "budget", "management plan")),
    "trading_multiple": ("metric", ("trading multiple", "ev ebitda", "comparable company")),
    "precedent_deal": ("record_type", ("precedent transaction", "transaction multiple", "deal comps")),
    "working_capital": ("metric", ("working capital", "net working capital")),
    "headcount_record": ("record_type", ("headcount", "employee count", "organisation chart")),
    "permit_record": ("record_type", ("permit", "licence", "regulatory approval")),
    "litigation_record": ("record_type", ("litigation", "lawsuit", "legal claim")),
    "technology_record": ("record_type", ("technology", "intellectual property", "software architecture")),
    "esg_record": ("record_type", ("esg", "sustainability", "emission")),
    "thesis_document": ("document_type", ("investment thesis", "strategic rationale", "deal thesis")),
    "company_profile": ("document_type", ("company overview", "corporate history", "founded")),
    "management_record": ("record_type", ("management team", "chief executive", "board of directors")),
    "risk_register": ("schedule", ("risk register", "key risk", "mitigant")),
    "synergy_schedule": ("schedule", ("synergy", "cost saving", "revenue synergy")),
    "compensation_record": ("record_type", ("compensation", "bonus plan", "management incentive")),
    "satisfaction_metric": ("metric", ("customer satisfaction", "net promoter", "nps")),
    "demand_driver": ("record_type", ("demand driver", "volume driver", "usage growth")),
}

# Each analysis agent declares the needs it must be able to retrieve.
AGENT_NEEDS: dict[str, tuple[str, ...]] = {
    "deal_context_and_objectives": ("thesis_document", "financing_terms"),
    "scope_and_methodology": ("thesis_document", "company_profile"),
    "company_background": ("company_profile", "headcount_record"),
    "strategic_direction": ("thesis_document", "forecast_schedule"),
    "management_quality": ("management_record", "compensation_record"),
    "regulatory_compliance": ("permit_record", "litigation_record"),
    "ip_and_technology": ("technology_record",),
    "esg_and_sustainability": ("esg_record", "permit_record"),
    "market_definition": ("market_size", "competitor_set"),
    "market_volume_and_growth": ("market_size", "market_growth"),
    "market_pricing": ("price_level", "market_size"),
    "demand_drivers": ("demand_driver", "market_growth"),
    "competitor_identification": ("competitor_set", "market_size"),
    "competitive_differentiation": ("competitor_set", "price_level"),
    "market_share_strategy": ("competitor_set", "market_growth"),
    "swot_analysis": ("risk_register", "competitor_set"),
    "customer_segmentation": ("segment_schedule", "customer_record"),
    "customer_stickiness": ("retention_metric", "customer_record"),
    "customer_satisfaction": ("satisfaction_metric", "customer_record"),
    "buying_behavior": ("customer_record", "segment_schedule"),
    "supplier_dependence": ("supplier_record", "cost_schedule"),
    "cost_structure": ("cost_schedule", "revenue_schedule"),
    "operational_risk": ("risk_register", "supplier_record"),
    "supply_chain_resilience": ("supplier_record", "risk_register"),
    "historical_performance": ("revenue_schedule", "cost_schedule"),
    "revenue_quality": ("revenue_schedule", "retention_metric", "customer_record"),
    "cash_flow": ("cash_flow_schedule", "working_capital"),
    "capital_structure": ("net_debt_schedule", "facility_record", "cap_table", "financing_terms"),
    "market_risk": ("market_growth", "risk_register"),
    "internal_risk": ("risk_register", "management_record"),
    "growth_opportunities": ("forecast_schedule", "market_growth"),
    "synergies": ("synergy_schedule", "cost_schedule"),
    "execution_risk": ("risk_register", "management_record"),
    "compensation_alignment": ("compensation_record", "management_record"),
    "trading_comps": ("trading_multiple", "revenue_schedule"),
    "precedent_transactions": ("precedent_deal", "trading_multiple"),
    "valuation_modeling": ("trading_multiple", "forecast_schedule", "net_debt_schedule"),
    "ic_synthesis": ("thesis_document", "risk_register"),
    "recommendation": ("thesis_document", "financing_terms"),
    "appendices": ("company_profile", "revenue_schedule"),
}

# competitor_identification line above has a silly conditional. I'll fix that in the dict... I already wrote it badly. Let me fix when I notice - I'll rewrite that one key cleanly via search_replace after if needed. I'll fix it now before the file is considered done by editing the write... I already included the bad line. I'll fix with StrReplace.

_AGENTS_FOR_NEED: dict[str, int] = {}
for _needs in AGENT_NEEDS.values():
    for _need_id in _needs:
        _AGENTS_FOR_NEED[_need_id] = _AGENTS_FOR_NEED.get(_need_id, 0) + 1


def agent_needs(agent_key: str) -> tuple[str, ...]:
    return AGENT_NEEDS.get(agent_key, ())


def tag_text(text: str) -> list[str]:
    """Topic ids found in one passage. A passage may carry several."""
    lowered = (text or "").lower()
    found: list[str] = []
    for need_id, (_kind, phrases) in _NEEDS.items():
        if any(_contains_phrase(phrase, lowered) for phrase in phrases):
            found.append(need_id)
    return found


def tag_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for chunk in chunks:
        if isinstance(chunk, dict):
            chunk["topics"] = tag_text(str(chunk.get("text") or ""))
    return chunks


def search_queries(agent_key: str, *, company: str = "") -> list[str]:
    """Queries from the agent's needs. The company name is not part of the query."""
    banned = {token.lower() for token in _TOKEN.findall(company.lower())}
    queries: list[str] = []
    for need_id in agent_needs(agent_key):
        phrase = _NEEDS[need_id][1][0]
        words = [word for word in phrase.split() if word.lower() not in banned]
        if words:
            queries.append(" ".join(words))
    return queries


def route_evidence(agent_key: str, chunks: list[dict[str, Any]], *, company: str = "") -> list[dict[str, Any]]:
    """Rank passages for one agent. Generic passages sink below a specific hit."""
    wanted = set(agent_needs(agent_key))
    if not wanted:
        return []
    queries = search_queries(agent_key, company=company)
    ranked: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        text = str(chunk.get("text") or "")
        topics = list(chunk.get("topics") or tag_text(text))
        if not wanted.intersection(topics) and _keyword_score(text, wanted) <= 0:
            continue
        score = _keyword_score(text, wanted) * 3.0 + _semantic_score(text, wanted)
        if _is_generic(topics):
            score *= 0.25
        row = dict(chunk)
        row["topics"] = topics
        row["score"] = round(score, 4)
        row["queries"] = queries
        ranked.append((score, row))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [row for _score, row in ranked]


def coverage_check(
    agent_key: str,
    chunks: list[dict[str, Any]],
    *,
    facts: dict[str, Any] | None = None,
    company: str = "",
) -> dict[str, Any]:
    """Mark each text need met or not found. Numbers may come from the fact store."""
    routed = route_evidence(agent_key, chunks, company=company)
    fact_ids = {key for key, value in (facts or {}).items() if value is not None and value != ""}
    needs: list[dict[str, Any]] = []
    for need_id in agent_needs(agent_key):
        queries = _queries_for_need(need_id, company)
        matched = [row["chunk_id"] for row in routed if need_id in (row.get("topics") or []) and row.get("chunk_id")]
        if need_id in fact_ids or matched:
            needs.append(
                {
                    "need_id": need_id,
                    "kind": _NEEDS[need_id][0],
                    "status": "met",
                    "source": "fact_store" if need_id in fact_ids else "data_room",
                    "chunk_ids": matched,
                    "searches": queries,
                    "statement": None,
                }
            )
            continue
        needs.append(
            {
                "need_id": need_id,
                "kind": _NEEDS[need_id][0],
                "status": "not_found",
                "source": None,
                "chunk_ids": [],
                "searches": queries,
                "statement": not_in_data_room(need_id, queries),
            }
        )
    return {"agent_key": agent_key, "chunks": routed, "needs": needs}


def not_in_data_room(need_id: str, searches: list[str]) -> str:
    """The only wording that may say an item is not in the data room."""
    label = _NEEDS.get(need_id, ("", (need_id,)))[1][0]
    search_text = "; ".join(searches) if searches else label
    return f"{label} is {_NOT_IN_ROOM}. Searches: {search_text}"


def evidence_pack(agent_key: str, texts: list[str], *, facts: dict[str, Any] | None = None, company: str = "") -> dict[str, Any]:
    """Build chunks from source text and return the coverage check."""
    chunks: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        for piece_index, piece in enumerate(_passages(text)):
            chunks.append(
                {
                    "chunk_id": f"src-{index}-{piece_index}",
                    "text": piece,
                    "topics": tag_text(piece),
                }
            )
    report = coverage_check(agent_key, chunks, facts=facts, company=company)
    report["received_chunk_ids"] = [row.get("chunk_id") for row in report["chunks"]]
    return report


def recall(relevant_ids: list[str], received_ids: list[str]) -> float:
    if not relevant_ids:
        return 1.0
    received = set(received_ids)
    found = sum(1 for item in relevant_ids if item in received)
    return found / len(relevant_ids)


def false_gap_rate(statements: list[tuple[bool, str | None]]) -> float:
    """Share of 'not in the data room' lines that are wrong.

    Each item is (need_is_actually_missing, statement or None).
    """
    spoken = [(missing, text) for missing, text in statements if text and _NOT_IN_ROOM in text.lower()]
    if not spoken:
        return 0.0
    wrong = sum(1 for missing, _text in spoken if not missing)
    return wrong / len(spoken)


def prefer_data_room_figure(data_room_value: Any, web_source: dict[str, Any] | None) -> dict[str, Any]:
    """A web figure never replaces a data-room figure."""
    if data_room_value is not None and data_room_value != "":
        return {"value": data_room_value, "tier": "data_room", "url": None, "retrieved_on": None}
    source = web_source or {}
    return {
        "value": source.get("value"),
        "tier": "web",
        "url": source.get("url"),
        "retrieved_on": source.get("retrieved_on"),
    }


def stamp_web_source(source: dict[str, Any], *, retrieved_on: str | None = None) -> dict[str, Any]:
    source["tier"] = "web"
    source["retrieved_on"] = retrieved_on or date.today().isoformat()
    return source


def _queries_for_need(need_id: str, company: str) -> list[str]:
    banned = {token.lower() for token in _TOKEN.findall(company.lower())}
    queries: list[str] = []
    for phrase in _NEEDS[need_id][1]:
        words = [word for word in phrase.split() if word.lower() not in banned]
        if words:
            queries.append(" ".join(words))
    return queries


def _passages(text: str) -> list[str]:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) < 40:
        return []
    if len(cleaned) <= 900:
        return [cleaned]
    pieces: list[str] = []
    start = 0
    while start < len(cleaned):
        pieces.append(cleaned[start : start + 900])
        start += 780
    return pieces


def _contains_phrase(phrase: str, lowered: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, lowered) is not None


def _keyword_score(text: str, wanted: set[str]) -> float:
    lowered = text.lower()
    score = 0.0
    for need_id in wanted:
        if any(_contains_phrase(phrase, lowered) for phrase in _NEEDS[need_id][1]):
            score += 1.0
    return score


def _semantic_score(text: str, wanted: set[str]) -> float:
    tokens = set(_TOKEN.findall(text.lower()))
    if not tokens:
        return 0.0
    best = 0.0
    for need_id in wanted:
        phrases = " ".join(_NEEDS[need_id][1])
        needed = set(_TOKEN.findall(phrases))
        if not needed:
            continue
        overlap = len(tokens & needed) / len(needed)
        best = max(best, overlap)
    return best


def _is_generic(topics: list[str]) -> bool:
    if len(topics) < 4:
        return False
    broad = sum(1 for topic in topics if _AGENTS_FOR_NEED.get(topic, 0) >= 4)
    return broad >= 4
