"""Static 44-agent pipeline catalog (live DiligenceIQ slug keys)."""

from __future__ import annotations

PIPELINE_PHASES: list[dict] = [
    {
        "phaseName": "Data Ingestion",
        "phaseUuid": "data_ingestion",
        "phase_id": "data_ingestion",
        "icon": "database",
        "order": 1,
        "stages": [
            {
                "stageTitle": "Deal Framing & Scope",
                "stageKey": "deal_framing_and_scope",
                "stageNumber": 0,
                "description": "Extracting deal context, hypotheses, and defining the analytical roadmap.",
                "agents": [
                    {
                        "agentName": "Deal Context & Objectives",
                        "agent_key": "deal_context_and_objectives",
                        "category": "deal_overview",
                        "description": "Defines transaction rationale, goals, sponsor/financing structure, and key hypotheses.",
                    },
                    {
                        "agentName": "Scope & Methodology",
                        "agent_key": "scope_and_methodology",
                        "category": "strategy",
                        "description": "Delineates scope, limitations, data sources, and line of inquiry.",
                    },
                ],
            }
        ],
    },
    {
        "phaseName": "Foundations",
        "phaseUuid": "foundations",
        "phase_id": "foundations",
        "icon": "building",
        "order": 2,
        "stages": [
            {
                "stageTitle": "Company & Management",
                "stageKey": "company_and_management",
                "stageNumber": 1,
                "description": "Analyzing company background, strategic direction, and management quality.",
                "agents": [
                    {"agentName": "Company Background", "agent_key": "company_background", "category": "management", "description": "Entity profile and corporate history."},
                    {"agentName": "Strategic Direction", "agent_key": "strategic_direction", "category": "strategy", "description": "Strategic thesis and direction."},
                    {"agentName": "Management Quality", "agent_key": "management_quality", "category": "management", "description": "Management team assessment."},
                ],
            },
            {
                "stageTitle": "Legal, IP & ESG",
                "stageKey": "legal_ip_and_esg",
                "stageNumber": 6,
                "description": "Regulatory, IP/tech, and ESG baseline.",
                "agents": [
                    {"agentName": "Regulatory Compliance", "agent_key": "regulatory_compliance", "category": "legal_compliance", "description": "Jurisdiction-real permits, tested obligations, litigation and transaction triggers."},
                    {"agentName": "IP & Technology", "agent_key": "ip_and_technology", "category": "legal_compliance", "description": "IP and technology architecture."},
                    {"agentName": "ESG & Sustainability", "agent_key": "esg_and_sustainability", "category": "legal_compliance", "description": "Material ESG with financial or regulatory consequence; product vs footprint."},
                ],
            },
        ],
    },
    {
        "phaseName": "Deep Dive",
        "phaseUuid": "deep_dive",
        "phase_id": "deep_dive",
        "icon": "search",
        "order": 3,
        "stages": [
            {
                "stageTitle": "Market Analysis",
                "stageKey": "market_analysis",
                "stageNumber": 2,
                "description": "Market definition, sizing, pricing, and demand.",
                "agents": [
                    {"agentName": "Market Definition", "agent_key": "market_definition", "category": "market_research", "description": "Market definition and segmentation."},
                    {"agentName": "Market Volume & Growth", "agent_key": "market_volume_and_growth", "category": "market_research", "description": "TAM/SAM/SOM and growth."},
                    {"agentName": "Market Pricing", "agent_key": "market_pricing", "category": "market_research", "description": "Pricing benchmarks."},
                    {"agentName": "Demand Drivers", "agent_key": "demand_drivers", "category": "market_research", "description": "Demand and macro drivers."},
                ],
            },
            {
                "stageTitle": "Competitive Landscape",
                "stageKey": "competitive_landscape",
                "stageNumber": 3,
                "description": "Competitors, differentiation, share, SWOT.",
                "agents": [
                    {"agentName": "Competitor Identification", "agent_key": "competitor_identification", "category": "market_research", "description": "Peer set and positioning."},
                    {"agentName": "Competitive Differentiation", "agent_key": "competitive_differentiation", "category": "market_research", "description": "Moat and differentiation."},
                    {"agentName": "Market Share Strategy", "agent_key": "market_share_strategy", "category": "strategy", "description": "Share and win strategy."},
                    {"agentName": "SWOT Analysis", "agent_key": "swot_analysis", "category": "strategy", "description": "SWOT synthesis."},
                ],
            },
            {
                "stageTitle": "Customer Analysis",
                "stageKey": "customer_analysis",
                "stageNumber": 4,
                "description": "Segmentation, stickiness, satisfaction, buying behavior.",
                "agents": [
                    {"agentName": "Customer Segmentation", "agent_key": "customer_segmentation", "category": "customer_data", "description": "ICP and segments."},
                    {"agentName": "Customer Stickiness", "agent_key": "customer_stickiness", "category": "customer_data", "description": "Retention and stickiness."},
                    {"agentName": "Customer Satisfaction", "agent_key": "customer_satisfaction", "category": "customer_data", "description": "Satisfaction and VoC."},
                    {"agentName": "Buying Behavior", "agent_key": "buying_behavior", "category": "customer_data", "description": "Buying process and decisioning."},
                ],
            },
            {
                "stageTitle": "Supplier & Operational Analysis",
                "stageKey": "supplier_and_operational_analysis",
                "stageNumber": 5,
                "description": "Suppliers, cost, ops risk, supply chain.",
                "agents": [
                    {"agentName": "Supplier Dependence", "agent_key": "supplier_dependence", "category": "operations", "description": "Supplier concentration."},
                    {"agentName": "Cost Structure", "agent_key": "cost_structure", "category": "operations", "description": "Cost structure analysis."},
                    {"agentName": "Operational Risk", "agent_key": "operational_risk", "category": "operations", "description": "Operational risks."},
                    {"agentName": "Supply Chain Resilience", "agent_key": "supply_chain_resilience", "category": "operations", "description": "Supply chain resilience."},
                ],
            },
            {
                "stageTitle": "Financial Analysis",
                "stageKey": "financial_analysis",
                "stageNumber": 7,
                "description": "Historical performance, revenue quality, cash flow, capital structure.",
                "agents": [
                    {"agentName": "Historical Performance", "agent_key": "historical_performance", "category": "financial_data", "description": "Historical P&L performance."},
                    {"agentName": "Revenue Quality", "agent_key": "revenue_quality", "category": "financial_data", "description": "Revenue quality and durability."},
                    {"agentName": "Cash Flow", "agent_key": "cash_flow", "category": "financial_data", "description": "Cash flow profile."},
                    {"agentName": "Capital Structure", "agent_key": "capital_structure", "category": "financial_data", "description": "Capital structure."},
                ],
            },
            {
                "stageTitle": "Risk & Opportunity Assessment",
                "stageKey": "risk_and_opportunity_assessment",
                "stageNumber": 8,
                "description": "Market/internal risk, growth, synergies.",
                "agents": [
                    {"agentName": "Market Risk", "agent_key": "market_risk", "category": "strategy", "description": "External market risks sized to company numbers."},
                    {"agentName": "Internal Risk", "agent_key": "internal_risk", "category": "strategy", "description": "Internal risks a buyer inherits on day one."},
                    {"agentName": "Growth Opportunities", "agent_key": "growth_opportunities", "category": "strategy", "description": "Costed growth options: sized revenue/margin, requirements, evidence, base vs upside."},
                    {"agentName": "Synergies", "agent_key": "synergies", "category": "strategy", "description": "Buyer-specific synergies net of cost to achieve; hypotheses only if no named buyer."},
                ],
            },
        ],
    },
    {
        "phaseName": "Final Verdict",
        "phaseUuid": "final_verdict",
        "phase_id": "final_verdict",
        "icon": "gavel",
        "order": 4,
        "stages": [
            {
                "stageTitle": "Risks & Growth",
                "stageKey": "risks_and_growth",
                "stageNumber": 9,
                "description": "Human-capital vulnerability and compensation alignment before valuation.",
                "agents": [
                    {"agentName": "Execution Risk", "agent_key": "execution_risk", "category": "management", "description": "Human capital vulnerability assessment (FV-01)."},
                    {"agentName": "Compensation Alignment", "agent_key": "compensation_alignment", "category": "management", "description": "Compensation adjustment table (FV-02)."},
                ],
            },
            {
                "stageTitle": "Valuation",
                "stageKey": "valuation",
                "stageNumber": 10,
                "description": "Trading comps, precedent transactions, and football-field synthesis.",
                "agents": [
                    {"agentName": "Trading Comps", "agent_key": "trading_comps", "category": "financial_data", "description": "Valuation benchmark analysis (FV-03)."},
                    {"agentName": "Precedent Transactions", "agent_key": "precedent_transactions", "category": "financial_data", "description": "Precedent transaction analysis (FV-04)."},
                    {"agentName": "Valuation Model", "agent_key": "valuation_modeling", "category": "financial_data", "description": "Earnings basis, methods, sensitivity, final range (FV-05)."},
                ],
            },
            {
                "stageTitle": "Summary & Recommendation",
                "stageKey": "executive_synthesis",
                "stageNumber": 11,
                "description": "IC synthesis and Go/No-Go recommendation.",
                "agents": [
                    {"agentName": "IC Synthesis", "agent_key": "ic_synthesis", "category": "deal_overview", "description": "Executive summary for the committee (FV-06)."},
                    {"agentName": "Recommendation", "agent_key": "recommendation", "category": "strategy", "description": "Transaction structure and returns (FV-07)."},
                ],
            },
        ],
    },
    {
        "phaseName": "Reports",
        "phaseUuid": "reports",
        "phase_id": "reports",
        "icon": "file",
        "order": 5,
        "stages": [
            {
                "stageTitle": "Report Generators",
                "stageKey": "report_generators",
                "stageNumber": 12,
                "description": "Terminal deliverable builders.",
                "agents": [
                    {"agentName": "Strategy Report", "agent_key": "strategy_report", "category": "report", "description": "Strategy narrative (.docx)."},
                    {"agentName": "Market Intel Deck", "agent_key": "market_intel_deck", "category": "report", "description": "Market deck (.pptx)."},
                    {"agentName": "Operations Dashboard", "agent_key": "operations_dashboard", "category": "report", "description": "Ops dashboard (.xlsx)."},
                    {"agentName": "IC Memo", "agent_key": "ic_memo", "category": "report", "description": "IC memo (.pdf)."},
                    {"agentName": "CDD Deck", "agent_key": "cdd_deck", "category": "report", "description": "Full CDD deck."},
                ],
            }
        ],
    },
]


PHASE1_AGENT_KEYS = ["deal_context_and_objectives", "scope_and_methodology"]
# Visible Foundations slugs. F-01…F-06 roles: see foundation_roles.py (S0).
PHASE2_AGENT_KEYS = [
    "company_background",
    "strategic_direction",
    "management_quality",
    "regulatory_compliance",
    "ip_and_technology",
    "esg_and_sustainability",
]
# Deep Dive live slugs (catalog order). Spec/deps: deep_dive_roles.py.
PHASE3_AGENT_KEYS = [
    "market_definition",
    "market_volume_and_growth",
    "market_pricing",
    "demand_drivers",
    "competitor_identification",
    "competitive_differentiation",
    "market_share_strategy",
    "swot_analysis",
    "customer_segmentation",
    "customer_stickiness",
    "customer_satisfaction",
    "buying_behavior",
    "supplier_dependence",
    "cost_structure",
    "operational_risk",
    "supply_chain_resilience",
    "historical_performance",
    "revenue_quality",
    "cash_flow",
    "capital_structure",
    "market_risk",
    "internal_risk",
    "growth_opportunities",
    "synergies",
]
# Final Verdict live slugs (catalog order). Spec/deps: verdict_roles.py.
PHASE4_AGENT_KEYS = [
    "execution_risk",
    "compensation_alignment",
    "trading_comps",
    "precedent_transactions",
    "valuation_modeling",
    "ic_synthesis",
    "recommendation",
]
REPORT_PHASE_ID = "reports"


def agent_src(phase_id: str, agent_key: str) -> str:
    """DiligenceIQ src tag: algo | algo+web | report."""
    if phase_id == REPORT_PHASE_ID:
        return "report"
    if phase_id == "deep_dive":
        from agetic_cdd_api.deep_dive_roles import role_by_slug

        role = role_by_slug(agent_key)
        return role.src if role else "algo"
    if phase_id == "final_verdict":
        return "algo"
    return "algo"


def iter_catalog_agents():
    for phase in PIPELINE_PHASES:
        for stage in phase["stages"]:
            for agent in stage["agents"]:
                yield phase, stage, agent


def all_agent_keys() -> list[str]:
    return [agent["agent_key"] for _, _, agent in iter_catalog_agents()]


def get_agent_meta(agent_key: str) -> dict | None:
    for phase, stage, agent in iter_catalog_agents():
        if agent["agent_key"] == agent_key:
            return {"phase": phase, "stage": stage, "agent": agent}
    return None


def phase_by_id(phase_id: str) -> dict | None:
    for phase in PIPELINE_PHASES:
        if phase["phase_id"] == phase_id or phase["phaseUuid"] == phase_id:
            return phase
    return None


def agent_keys_for_phase(phase: dict) -> list[str]:
    keys: list[str] = []
    for stage in phase["stages"]:
        keys.extend(agent["agent_key"] for agent in stage["agents"])
    return keys


def previous_phase(phase: dict) -> dict | None:
    prior = phase["order"] - 1
    for candidate in PIPELINE_PHASES:
        if candidate["order"] == prior:
            return candidate
    return None


def report_agent_keys() -> list[str]:
    phase = phase_by_id(REPORT_PHASE_ID)
    return agent_keys_for_phase(phase) if phase else []


def total_agent_count() -> int:
    n = 0
    for phase in PIPELINE_PHASES:
        for stage in phase["stages"]:
            n += len(stage["agents"])
    return n


def build_stub_roadmap(*, agent_status: str = "idle") -> list[dict]:
    """W3/W4: roadmap with stub agent statuses (real runs in later waves)."""
    roadmap = []
    for phase in PIPELINE_PHASES:
        agents_flat = []
        stages_out = []
        phase_id = phase["phase_id"]
        for stage in phase["stages"]:
            stage_agents = []
            for agent in stage["agents"]:
                item = {
                    **agent,
                    "uuid": agent["agent_key"],
                    "status": agent_status,
                    "stageTitle": stage["stageTitle"],
                    "src": agent.get("src") or agent_src(phase_id, agent["agent_key"]),
                }
                stage_agents.append(item)
                agents_flat.append(item)
            stages_out.append({**stage, "agents": stage_agents})
        total = len(agents_flat)
        completed = sum(1 for a in agents_flat if a["status"] == "completed")
        roadmap.append(
            {
                "phaseName": phase["phaseName"],
                "phaseUuid": phase["phaseUuid"],
                "phase_id": phase_id,
                "id": phase_id,
                "name": phase["phaseName"],
                "icon": phase["icon"],
                "order": phase["order"],
                "totalAgents": total,
                "completedAgents": completed,
                "status": "completed" if completed == total and total else ("in_progress" if completed else "pending"),
                "stages": stages_out,
                "agents": agents_flat,
                "agentList": agents_flat,
            }
        )
    return roadmap
