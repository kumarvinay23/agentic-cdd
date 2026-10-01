"""DiligenceIQ-style prompt book — house rules + per-agent prompts.

House rules are stored once and prepended to each agent prompt via
``compose_system``. Placeholders use ``[SQUARE_BRACKETS]`` filled at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent

_AGENT_FILES: dict[str, str] = {
    "deal_context_and_objectives": "deal_context_and_objectives.md",
    "scope_and_methodology": "scope_and_methodology.md",
    "company_background": "company_background.md",
    "management_quality": "management_quality.md",
    "strategic_direction": "strategic_direction.md",
    "ip_and_technology": "ip_and_technology.md",
    "regulatory_compliance": "regulatory_compliance.md",
    "esg_and_sustainability": "esg_and_sustainability.md",
    "market_definition": "market_definition.md",
    "market_volume_and_growth": "market_volume_and_growth.md",
    "market_pricing": "market_pricing.md",
    "demand_drivers": "demand_drivers.md",
    "competitor_identification": "competitor_identification.md",
    "competitive_differentiation": "competitive_differentiation.md",
    "market_share_strategy": "market_share_strategy.md",
    "customer_segmentation": "customer_segmentation.md",
    "customer_stickiness": "customer_stickiness.md",
    "customer_satisfaction": "customer_satisfaction.md",
    "buying_behavior": "buying_behavior.md",
    "supplier_dependence": "supplier_dependence.md",
    "supply_chain_resilience": "supply_chain_resilience.md",
    "operational_risk": "operational_risk.md",
    "cost_structure": "cost_structure.md",
    "historical_performance": "historical_performance.md",
    "revenue_quality": "revenue_quality.md",
    "capital_structure": "capital_structure.md",
    "valuation_modeling": "valuation_modeling.md",
    "sensitivity_analysis": "sensitivity_analysis.md",
    "final_valuation_range": "final_valuation_range.md",
    "market_risk": "market_risk.md",
    "internal_risk": "internal_risk.md",
    "growth_opportunities": "growth_opportunities.md",
    "synergies": "synergies.md",
    "swot_analysis": "swot_analysis.md",
    "recommendation": "recommendation.md",
    "ic_synthesis": "ic_synthesis.md",
    "executive_summary": "ic_synthesis.md",
}

_DEFAULT_MATERIALITY = "deal-material"
_DEFAULT_SECTOR = "the target sector"
_DEFAULT_GEOGRAPHY = "the target geography"


def _read_prompt_file(filename: str) -> str:
    path = _DIR / filename
    return path.read_text(encoding="utf-8").strip()


def _fill(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace(f"[{key}]", value)
    return out


def house_rules(
    *,
    materiality: str | None = None,
    sector: str | None = None,
    geography: str | None = None,
) -> str:
    """Shared preamble prepended to every agent system prompt."""
    text = _read_prompt_file("house_rules.md")
    return _fill(
        text,
        {
            "MATERIALITY": (materiality or _DEFAULT_MATERIALITY).strip() or _DEFAULT_MATERIALITY,
            "SECTOR": (sector or _DEFAULT_SECTOR).strip() or _DEFAULT_SECTOR,
            "GEOGRAPHY": (geography or _DEFAULT_GEOGRAPHY).strip() or _DEFAULT_GEOGRAPHY,
        },
    )


def agent_prompt(
    agent_key: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> str:
    """Agent-specific prompt body (without house rules)."""
    filename = _AGENT_FILES.get(agent_key)
    if not filename:
        raise KeyError(f"No prompt-book entry for agent_key={agent_key!r}")
    text = _read_prompt_file(filename)
    return _fill(
        text,
        {
            "MATERIALITY": (materiality or _DEFAULT_MATERIALITY).strip() or _DEFAULT_MATERIALITY,
            "SECTOR": (sector or _DEFAULT_SECTOR).strip() or _DEFAULT_SECTOR,
            "GEOGRAPHY": (geography or _DEFAULT_GEOGRAPHY).strip() or _DEFAULT_GEOGRAPHY,
        },
    )


def compose_system(
    agent_key: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> str:
    """House rules once, then the agent prompt — ready as an LLM system message."""
    rules = house_rules(
        materiality=materiality,
        sector=sector,
        geography=geography,
    )
    body = agent_prompt(
        agent_key,
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    return f"{rules}\n\n---\n\n{body}"


def listed_agents() -> list[str]:
    return sorted(_AGENT_FILES.keys())


def prompt_vars_from_deal(deal: Any) -> dict[str, str | None]:
    """Best-effort sector / geography / materiality from a Deal-like object."""
    sector = getattr(deal, "sector", None) or getattr(deal, "industry", None)
    geography = getattr(deal, "geography", None) or getattr(deal, "region", None)
    materiality = getattr(deal, "materiality", None)
    if isinstance(sector, str) and not sector.strip():
        sector = None
    if isinstance(geography, str) and not geography.strip():
        geography = None
    return {
        "sector": sector if isinstance(sector, str) else None,
        "geography": geography if isinstance(geography, str) else None,
        "materiality": materiality if isinstance(materiality, str) else None,
    }
