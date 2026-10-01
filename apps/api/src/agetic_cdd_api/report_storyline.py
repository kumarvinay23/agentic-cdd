"""Storyline model and default configs for all 5 report types.

A *storyline* is an ordered list of sections that define the structure of
a generated report.  Each section has a title, kind, include flag, optional
user instructions, and a list of pipeline agent keys that feed it.

Default storylines match the live DiligenceIQ section shapes observed on
Test2 (see CONTEXT.md "Live … generation" blocks).  Builders can override
or extend at runtime.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class StorylineSection:
    idx: int
    title: str
    kind: str = ""
    included: bool = True
    instructions: str = ""
    agents: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StorylineSection:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Default storylines — matching live DiligenceIQ observed section structures.
# ---------------------------------------------------------------------------

_OPS_DASHBOARD_SECTIONS: list[dict] = [
    {"idx": 1, "title": "Executive Dashboard", "kind": "sheet",
     "agents": ["executive_summary", "recommendations", "historical_performance",
                "deal_context_and_objectives", "final_valuation_range", "management_quality"]},
    {"idx": 2, "title": "Customer Analysis", "kind": "sheet",
     "agents": ["customer_segmentation", "customer_stickiness", "customer_satisfaction"]},
    {"idx": 3, "title": "Operational & Risk", "kind": "sheet",
     "agents": ["operational_risk", "supplier_dependence", "supply_chain_resilience",
                "internal_risk", "capital_structure", "company_background"]},
    {"idx": 4, "title": "Financial Analysis", "kind": "sheet",
     "agents": ["historical_performance", "revenue_quality", "cost_structure", "internal_risk"]},
    {"idx": 5, "title": "Source Data", "kind": "sheet",
     "agents": ["scope_and_methodology", "appendices", "competitive_differentiation",
                "deal_context_and_objectives"]},
]

_IC_MEMO_SECTIONS: list[dict] = [
    {"idx": 1, "title": "1.1 Market Risk", "kind": "risk",
     "agents": ["market_risk", "market_volume_and_growth", "competitive_differentiation",
                "customer_segmentation", "buying_behavior", "capital_structure", "demand_drivers"]},
    {"idx": 2, "title": "1.2 Internal Risk", "kind": "risk",
     "agents": ["internal_risk", "operational_risk", "customer_stickiness", "appendices",
                "capital_structure", "competitor_identification", "cash_flow"]},
    {"idx": 3, "title": "1.3 Growth Opportunities", "kind": "opportunity",
     "agents": ["growth_opportunities", "cost_structure", "historical_performance",
                "market_share_strategy", "market_volume_and_growth", "operational_risk",
                "market_pricing", "final_valuation_range", "customer_segmentation"]},
    {"idx": 4, "title": "1.4 Synergies", "kind": "opportunity",
     "agents": ["synergies"]},
    {"idx": 5, "title": "2.1 Valuation Model", "kind": "valuation",
     "agents": ["valuation_model", "final_valuation_range", "historical_performance",
                "company_background", "market_pricing", "sensitivity_analysis"]},
    {"idx": 6, "title": "2.2 Sensitivity Analysis", "kind": "valuation",
     "agents": ["sensitivity_analysis", "supply_chain_resilience"]},
    {"idx": 7, "title": "2.3 Final Valuation Range", "kind": "valuation",
     "agents": ["final_valuation_range", "sensitivity_analysis", "valuation_model"]},
    {"idx": 8, "title": "3.1 Executive Summary", "kind": "synthesis",
     "agents": ["executive_summary", "recommendations", "historical_performance",
                "deal_context_and_objectives", "appendices", "company_background",
                "market_risk", "operational_risk", "regulatory_compliance", "supplier_dependence"]},
    {"idx": 9, "title": "3.2 Final Recommendation", "kind": "synthesis",
     "agents": ["recommendations", "final_valuation_range", "executive_summary", "appendices",
                "historical_performance", "market_volume_and_growth", "customer_satisfaction",
                "competitive_differentiation"]},
    {"idx": 10, "title": "3.3 Appendices & Sourcing", "kind": "appendix",
     "agents": ["appendices", "scope_and_methodology"]},
]

_STRATEGY_REPORT_SECTIONS: list[dict] = [
    {"idx": 1, "title": "1.0 Deal Framing & Scope", "kind": "framing",
     "agents": ["strategic_direction", "deal_context_and_objectives", "growth_opportunities",
                "appendices", "executive_summary", "market_definition", "customer_stickiness",
                "market_pricing", "demand_drivers", "synergies", "regulatory_compliance"]},
    {"idx": 2, "title": "2.0 Company & Management", "kind": "company",
     "agents": ["management_quality", "company_background", "operational_risk", "internal_risk",
                "cost_structure", "regulatory_compliance", "market_volume_and_growth",
                "customer_stickiness", "market_risk", "competitor_identification"]},
    {"idx": 3, "title": "3.0 Legal, IP & ESG", "kind": "legal",
     "agents": ["regulatory_compliance", "ip_and_technology", "esg_and_sustainability",
                "operational_risk", "supply_chain_resilience"]},
]

_MARKET_DECK_SECTIONS: list[dict] = [
    {"idx": 1, "title": "Key Findings", "kind": "summary",
     "agents": ["market_definition"]},
    {"idx": 2, "title": "Market perimeter & definition", "kind": "market",
     "agents": ["market_definition", "buying_behavior", "customer_segmentation",
                "growth_opportunities", "market_intel_deck", "market_pricing"]},
    {"idx": 3, "title": "TAM / SAM / SOM estimation", "kind": "market",
     "agents": ["market_volume_and_growth", "market_definition", "buying_behavior",
                "customer_segmentation", "growth_opportunities", "market_intel_deck"]},
    {"idx": 4, "title": "Market taxonomy, segmentation & boundaries", "kind": "market",
     "agents": ["market_definition", "customer_segmentation", "buying_behavior",
                "growth_opportunities", "market_intel_deck", "market_pricing"]},
    {"idx": 5, "title": "Historical trajectory & growth rate", "kind": "market",
     "agents": ["market_volume_and_growth", "strategic_direction", "growth_opportunities",
                "historical_performance", "market_share_strategy", "buying_behavior",
                "competitor_identification"]},
    {"idx": 6, "title": "CAGR benchmarking & market lifecycle", "kind": "market",
     "agents": ["market_volume_and_growth", "buying_behavior", "cost_structure",
                "customer_segmentation", "growth_opportunities", "historical_performance"]},
    {"idx": 7, "title": "Pricing power, competitive position & margin", "kind": "competitive",
     "agents": ["market_pricing", "competitive_differentiation", "competitor_identification",
                "cost_structure", "historical_performance", "market_risk"]},
    {"idx": 8, "title": "Macro & structural demand drivers", "kind": "market",
     "agents": ["demand_drivers", "market_risk", "buying_behavior",
                "deal_context_and_objectives", "market_share_strategy", "recommendations"]},
    {"idx": 9, "title": "Sustainability, cyclicality & demand verdict", "kind": "market",
     "agents": ["demand_drivers", "competitive_differentiation", "esg_and_sustainability",
                "revenue_quality", "appendices", "buying_behavior", "customer_satisfaction"]},
    {"idx": 10, "title": "Direct & adjacent competitor universe", "kind": "competitive",
     "agents": ["competitor_identification"]},
    {"idx": 11, "title": "Competitive positioning matrix", "kind": "competitive",
     "agents": ["competitor_identification", "market_pricing", "market_risk",
                "competitive_differentiation", "internal_risk", "sensitivity_analysis"]},
    {"idx": 12, "title": "Competitive capability matrix & barriers", "kind": "competitive",
     "agents": ["competitive_differentiation", "competitor_identification", "market_risk",
                "internal_risk", "market_pricing", "sensitivity_analysis"]},
    {"idx": 13, "title": "Core strategic differentiators & moat", "kind": "competitive",
     "agents": ["competitive_differentiation", "company_background", "ip_and_technology",
                "strategic_direction", "swot_analysis"]},
    {"idx": 14, "title": "Competitive battlecards", "kind": "competitive",
     "agents": ["competitive_differentiation", "competitor_identification", "market_pricing",
                "market_risk", "strategic_direction"]},
    {"idx": 15, "title": "Differentiation verdict & market share", "kind": "competitive",
     "agents": ["market_share_strategy", "growth_opportunities", "buying_behavior",
                "competitive_differentiation", "customer_segmentation", "market_definition"]},
    {"idx": 16, "title": "SWOT summary matrix", "kind": "synthesis",
     "agents": ["swot_analysis", "appendices", "company_background",
                "competitor_identification", "customer_satisfaction", "deal_context_and_objectives"]},
    {"idx": 17, "title": "Market Intel Deck - Summary", "kind": "summary",
     "agents": ["market_share_strategy", "market_intel_deck", "appendices",
                "buying_behavior", "company_background", "customer_satisfaction"]},
]

_CDD_DECK_SECTIONS: list[dict] = [
    {"idx": 1, "title": "Cover & Engagement Overview", "kind": "cover",
     "agents": ["deal_context_and_objectives", "strategic_direction", "company_background"]},
    {"idx": 2, "title": "Basis of Preparation & Disclaimer", "kind": "methodology",
     "agents": ["scope_and_methodology", "appendices"]},
    {"idx": 3, "title": "Scope & Research Approach", "kind": "methodology",
     "agents": ["scope_and_methodology", "company_background"]},
    {"idx": 4, "title": "Business Introduction & Market Primer", "kind": "content",
     "agents": ["company_background", "management_quality", "strategic_direction",
                "market_definition", "buying_behavior"]},
    {"idx": 5, "title": "Market Sizing & Growth", "kind": "content",
     "agents": ["market_volume_and_growth", "growth_opportunities", "demand_drivers",
                "market_pricing"]},
    {"idx": 6, "title": "Competitive Landscape", "kind": "content",
     "agents": ["competitor_identification", "competitive_differentiation",
                "market_share_strategy", "ip_and_technology", "swot_analysis"]},
    {"idx": 7, "title": "Customer & Commercial Analysis", "kind": "content",
     "agents": ["customer_segmentation", "buying_behavior", "customer_stickiness",
                "customer_satisfaction", "revenue_quality"]},
    {"idx": 8, "title": "Operations & Risk", "kind": "content",
     "agents": ["operational_risk", "supplier_dependence", "supply_chain_resilience",
                "internal_risk", "market_risk", "execution_risk", "regulatory_compliance"]},
    {"idx": 9, "title": "Financial Analysis", "kind": "content",
     "agents": ["historical_performance", "cost_structure", "cash_flow",
                "capital_structure", "valuation_modeling", "trading_comps"]},
    {"idx": 10, "title": "Executive Summary & Decision", "kind": "exec_bullets",
     "agents": ["ic_synthesis", "executive_summary", "recommendation", "recommendations",
                "valuation_modeling", "synergies", "growth_opportunities", "swot_analysis"]},
    {"idx": 11, "title": "Appendix & Sources", "kind": "appendix",
     "agents": ["scope_and_methodology", "appendices", "company_background"]},
]

DEFAULT_STORYLINES: dict[str, list[dict]] = {
    "ops_dashboard": _OPS_DASHBOARD_SECTIONS,
    "ic_memo": _IC_MEMO_SECTIONS,
    "strategy_report": _STRATEGY_REPORT_SECTIONS,
    "market_deck": _MARKET_DECK_SECTIONS,
    "cdd_deck": _CDD_DECK_SECTIONS,
}


def default_storyline(report_type: str) -> list[StorylineSection]:
    raw = deepcopy(DEFAULT_STORYLINES.get(report_type, []))
    return [StorylineSection.from_dict({**s, "included": True}) for s in raw]


def storyline_as_dicts(sections: list[StorylineSection]) -> list[dict]:
    return [s.to_dict() for s in sections]


def all_source_agents(sections: list[StorylineSection]) -> list[str]:
    """Unique agent keys across all included sections, preserving first-seen order."""
    seen: set[str] = set()
    result: list[str] = []
    for s in sections:
        if not s.included:
            continue
        for a in s.agents:
            if a not in seen:
                seen.add(a)
                result.append(a)
    return result
