"""DiligenceIQ-style prompt book — house rules + per-agent prompts.

House rules are stored once and prepended to each agent prompt via
``compose_system``. Post-draft QA uses ``compose_qa``. Placeholders use
``[SQUARE_BRACKETS]`` filled at runtime.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agetic_cdd_api.prompt_book.shared_controls import (
    CLAIM_REQUIRED_KEYS,
    QA_ISSUE_REQUIRED_KEYS,
    QUESTION_REQUIRED_KEYS,
    SOURCE_CATEGORIES,
    cite_reopen,
    normalize_claim,
    normalize_qa_issue,
    normalize_question,
    normalize_questions,
    normalize_verdicts,
    questions_complete,
    recalculate_bridge,
    validate_claim,
    validate_question,
)

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
    "cash_flow": "cash_flow.md",
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
    "appendices": "appendices.md",
}

_AGENT_DISPLAY_NAMES: dict[str, str] = {
    "deal_context_and_objectives": "Deal Context and Objectives",
    "scope_and_methodology": "Scope and Methodology",
    "company_background": "Company Background",
    "management_quality": "Management Quality",
    "strategic_direction": "Strategic Direction",
    "ip_and_technology": "IP and Technology",
    "regulatory_compliance": "Regulatory Compliance",
    "esg_and_sustainability": "ESG and Sustainability",
    "market_definition": "Market Definition",
    "market_volume_and_growth": "Market Volume and Growth",
    "market_pricing": "Market Pricing",
    "demand_drivers": "Demand Drivers",
    "competitor_identification": "Competitor Identification",
    "competitive_differentiation": "Competitive Differentiation",
    "market_share_strategy": "Market Share Strategy",
    "customer_segmentation": "Customer Segmentation",
    "customer_stickiness": "Customer Stickiness",
    "customer_satisfaction": "Customer Satisfaction",
    "buying_behavior": "Buying Behavior",
    "supplier_dependence": "Supplier Dependence",
    "supply_chain_resilience": "Supply Chain Resilience",
    "operational_risk": "Operational Risk",
    "cost_structure": "Cost Structure",
    "historical_performance": "Historical Performance",
    "cash_flow": "Cash Flow",
    "revenue_quality": "Revenue Quality",
    "capital_structure": "Capital Structure",
    "valuation_modeling": "Valuation Modeling",
    "sensitivity_analysis": "Sensitivity Analysis",
    "final_valuation_range": "Final Valuation Range",
    "market_risk": "Market Risk",
    "internal_risk": "Internal Risk",
    "growth_opportunities": "Growth Opportunities",
    "synergies": "Synergies",
    "swot_analysis": "SWOT Analysis",
    "recommendation": "Recommendations",
    "ic_synthesis": "Executive Summary",
    "executive_summary": "Executive Summary",
    "appendices": "Appendices",
}

_DEFAULT_MATERIALITY = "deal-material"
_DEFAULT_SECTOR = "the target sector"
_DEFAULT_GEOGRAPHY = "the target geography"
_DEFAULT_TARGET = "the target company"
_DEFAULT_PRODUCTS = "as stated in the data room"
_DEFAULT_CUSTOMERS = "as stated in the data room"
_DEFAULT_PERIMETER = "as stated in the engagement scope"
_DEFAULT_TRANSACTION = "as stated in the engagement scope"
_DEFAULT_AS_OF = "as stated in the data room"
_DEFAULT_REVIEW_PERIODS = "as stated in the data room"
_DEFAULT_DECISION_STAGE = "diligence"


def _read_prompt_file(filename: str) -> str:
    path = _DIR / filename
    return path.read_text(encoding="utf-8").strip()


def _fill(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace(f"[{key}]", value)
    return out


def _slot(
    value: str | None,
    default: str,
) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _deal_fill_map(
    *,
    materiality: str | None = None,
    sector: str | None = None,
    geography: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
    agent_name: str | None = None,
) -> dict[str, str]:
    return {
        "MATERIALITY": _slot(materiality, _DEFAULT_MATERIALITY),
        "SECTOR": _slot(sector, _DEFAULT_SECTOR),
        "GEOGRAPHY": _slot(geography, _DEFAULT_GEOGRAPHY),
        "TARGET_COMPANY": _slot(target_company, _DEFAULT_TARGET),
        "PRODUCTS_AND_SERVICES": _slot(products_and_services, _DEFAULT_PRODUCTS),
        "CUSTOMER_TYPES": _slot(customer_types, _DEFAULT_CUSTOMERS),
        "DEAL_PERIMETER": _slot(deal_perimeter, _DEFAULT_PERIMETER),
        "TRANSACTION_TYPE": _slot(transaction_type, _DEFAULT_TRANSACTION),
        "AS_OF_DATE": _slot(as_of_date, _DEFAULT_AS_OF),
        "REVIEW_PERIODS": _slot(review_periods, _DEFAULT_REVIEW_PERIODS),
        "DECISION_STAGE": _slot(decision_stage, _DEFAULT_DECISION_STAGE),
        "AGENT_NAME": _slot(agent_name, "the agent workstream"),
    }


def house_rules(
    *,
    materiality: str | None = None,
    sector: str | None = None,
    geography: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> str:
    """Shared preamble prepended to every agent system prompt."""
    text = _read_prompt_file("house_rules.md")
    return _fill(
        text,
        _deal_fill_map(
            materiality=materiality,
            sector=sector,
            geography=geography,
            target_company=target_company,
            products_and_services=products_and_services,
            customer_types=customer_types,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
        ),
    )


def shared_qa_prompt(
    agent_key: str,
    *,
    materiality: str | None = None,
    sector: str | None = None,
    geography: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> str:
    """Shared post-draft QA prompt (cite-reopen, recalc, issue register)."""
    text = _read_prompt_file("shared_qa.md")
    display = _AGENT_DISPLAY_NAMES.get(agent_key) or agent_key.replace("_", " ").title()
    return _fill(
        text,
        _deal_fill_map(
            materiality=materiality,
            sector=sector,
            geography=geography,
            target_company=target_company,
            products_and_services=products_and_services,
            customer_types=customer_types,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
            agent_name=display,
        ),
    )


def agent_prompt(
    agent_key: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> str:
    """Agent-specific prompt body (without house rules)."""
    filename = _AGENT_FILES.get(agent_key)
    if not filename:
        raise KeyError(f"No prompt-book entry for agent_key={agent_key!r}")
    text = _read_prompt_file(filename)
    return _fill(
        text,
        _deal_fill_map(
            materiality=materiality,
            sector=sector,
            geography=geography,
            target_company=target_company,
            products_and_services=products_and_services,
            customer_types=customer_types,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
        ),
    )


def compose_system(
    agent_key: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> str:
    """House rules once, then the agent prompt — ready as an LLM system message."""
    slots = dict(
        materiality=materiality,
        sector=sector,
        geography=geography,
        target_company=target_company,
        products_and_services=products_and_services,
        customer_types=customer_types,
        deal_perimeter=deal_perimeter,
        transaction_type=transaction_type,
        as_of_date=as_of_date,
        review_periods=review_periods,
        decision_stage=decision_stage,
    )
    rules = house_rules(**slots)
    body = agent_prompt(agent_key, **slots)
    return f"{rules}\n\n---\n\n{body}"


def compose_qa(
    agent_key: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    target_company: str | None = None,
    products_and_services: str | None = None,
    customer_types: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
    agent_specific_qa: str | None = None,
) -> str:
    """Post-draft QA system message: shared QA (+ optional agent-specific checks)."""
    slots = dict(
        materiality=materiality,
        sector=sector,
        geography=geography,
        target_company=target_company,
        products_and_services=products_and_services,
        customer_types=customer_types,
        deal_perimeter=deal_perimeter,
        transaction_type=transaction_type,
        as_of_date=as_of_date,
        review_periods=review_periods,
        decision_stage=decision_stage,
    )
    shared = shared_qa_prompt(agent_key, **slots)
    extra = (agent_specific_qa or "").strip()
    if extra:
        return f"{shared}\n\n---\n\n## Agent-specific QA\n\n{extra}"
    return shared


def listed_agents() -> list[str]:
    return sorted(_AGENT_FILES.keys())


def agent_display_name(agent_key: str) -> str:
    return _AGENT_DISPLAY_NAMES.get(agent_key) or agent_key.replace("_", " ").title()


def _meta_get(meta: Any, *keys: str) -> str | None:
    if not isinstance(meta, dict):
        return None
    for key in keys:
        val = meta.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def prompt_vars_from_deal(deal: Any) -> dict[str, str | None]:
    """Best-effort deal slots from a Deal-like object / metadata."""
    sector = getattr(deal, "sector", None) or getattr(deal, "industry", None)
    geography = getattr(deal, "geography", None) or getattr(deal, "region", None)
    materiality = getattr(deal, "materiality", None)
    target = getattr(deal, "company", None) or getattr(deal, "name", None)

    meta = getattr(deal, "cdd_metadata", None)
    if meta is None:
        meta = getattr(deal, "metadata", None)
    if isinstance(meta, str):
        meta = None

    if isinstance(sector, str) and not sector.strip():
        sector = None
    if isinstance(geography, str) and not geography.strip():
        geography = None

    geography = geography or _meta_get(meta, "geography", "region", "cdd_geography")
    materiality = materiality or _meta_get(meta, "materiality", "approved_materiality")
    perimeter = _meta_get(meta, "deal_perimeter", "perimeter", "acquisition_perimeter")
    transaction = _meta_get(meta, "transaction_type", "deal_type")
    as_of = _meta_get(meta, "as_of_date", "as_of", "reporting_date")
    review = _meta_get(meta, "review_periods", "periods")
    stage = _meta_get(meta, "decision_stage", "stage")
    products = _meta_get(meta, "products_and_services", "products", "services")
    customers = _meta_get(meta, "customer_types", "customers")

    return {
        "sector": sector if isinstance(sector, str) else None,
        "geography": geography if isinstance(geography, str) else None,
        "materiality": materiality if isinstance(materiality, str) else None,
        "target_company": target if isinstance(target, str) else None,
        "products_and_services": products,
        "customer_types": customers,
        "deal_perimeter": perimeter,
        "transaction_type": transaction,
        "as_of_date": as_of,
        "review_periods": review,
        "decision_stage": stage,
    }


__all__ = [
    "CLAIM_REQUIRED_KEYS",
    "QA_ISSUE_REQUIRED_KEYS",
    "QUESTION_REQUIRED_KEYS",
    "SOURCE_CATEGORIES",
    "agent_display_name",
    "agent_prompt",
    "cite_reopen",
    "compose_qa",
    "compose_system",
    "house_rules",
    "listed_agents",
    "normalize_claim",
    "normalize_qa_issue",
    "normalize_question",
    "normalize_questions",
    "normalize_verdicts",
    "prompt_vars_from_deal",
    "questions_complete",
    "recalculate_bridge",
    "shared_qa_prompt",
    "validate_claim",
    "validate_question",
]
