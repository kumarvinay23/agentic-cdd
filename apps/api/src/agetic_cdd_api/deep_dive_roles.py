"""Phase 3 Deep Dive roles — live slug keys bound to Genovation DD-01…24 specs.

Runtime identity stays DiligenceIQ agent_key (`slug`). Genovation `code` values
may share a numeric stem with a letter suffix (DD-09 vs DD-09b, DD-01 vs DD-01b);
orchestration, DB keys, and cascade must key on **slug** (or the full `code`
string), never the bare numeric stem.

DAG edge direction (critical path): Customers/Ops → Financials.
DD-14 (`supply_chain_resilience`) is an Ops *producer*; DD-09b / DD-24a / DD-24
consume it. It does **not** depend on financial agents — no cycle there.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeepDiveRole:
    code: str  # Genovation id; letter suffixes are distinct codes (DD-09 ≠ DD-09b)
    name: str
    slug: str  # DiligenceIQ agent_key — unique runtime primary key
    track: str  # A…F Genovation track letter
    stage_key: str
    src: str  # algo | algo+web
    category: str
    spec_output: str
    depends_on: tuple[str, ...] = ()  # upstream live slugs
    foundation_deps: tuple[str, ...] = ()  # F-01…F-06 role codes
    primary_kinds: tuple[str, ...] = ()
    filename_needles: tuple[str, ...] = ()


# Cross-track DAG (Genovation) mapped onto live slugs.
DEEP_DIVE_ROLES: tuple[DeepDiveRole, ...] = (
    # Track A / Market Analysis
    DeepDiveRole(
        code="DD-02",
        name="Market Definition",
        slug="market_definition",
        track="A",
        stage_key="market_analysis",
        src="algo+web",
        category="market_research",
        spec_output="Macro Environment Analysis",
        foundation_deps=("F-01", "F-05"),
        primary_kinds=("market", "market_competition", "deal_strategy", "customer"),
        filename_needles=(
            "market", "competition", "industry", "thesis", "executive",
            "commercial", "gartner", "magic quadrant", "overview",
        ),
    ),
    DeepDiveRole(
        code="DD-01",
        name="Market Volume & Growth",
        slug="market_volume_and_growth",
        track="A",
        stage_key="market_analysis",
        src="algo+web",
        category="market_research",
        spec_output="Market Ceiling Analysis",
        depends_on=("market_definition",),
        foundation_deps=("F-01",),
        primary_kinds=("market", "market_competition", "deal_strategy"),
        filename_needles=(
            "thesis", "tam", "sam", "som", "market size", "market stats",
            "investment", "executive", "competition", "commercial",
        ),
    ),
    DeepDiveRole(
        code="DD-17",
        name="Market Pricing",
        slug="market_pricing",
        track="A",
        stage_key="market_analysis",
        src="algo+web",
        category="market_research",
        spec_output="Optimal Price Point Analysis",
        depends_on=("market_definition", "market_volume_and_growth"),
        primary_kinds=("market", "market_competition", "customer", "deal_strategy"),
        filename_needles=(
            "commercial", "pricing", "price", "asp", "selling", "flagship",
            "van westendorp", "thesis", "competition",
        ),
    ),
    DeepDiveRole(
        code="DD-03",
        name="Demand Drivers",
        slug="demand_drivers",
        track="A",
        stage_key="market_analysis",
        src="algo+web",
        category="market_research",
        spec_output="Regional Economic Cycle Risk",
        depends_on=("market_definition", "market_volume_and_growth"),
        primary_kinds=("market", "customer", "deal_strategy"),
        filename_needles=(
            "commercial", "thesis", "geographic", "region", "demand",
            "sales by region", "market",
        ),
    ),
    # Track B / Competitive Landscape
    DeepDiveRole(
        code="DD-04",
        name="Competitor Identification",
        slug="competitor_identification",
        track="B",
        stage_key="competitive_landscape",
        src="algo+web",
        category="market_research",
        spec_output="Competitive Positioning Matrix",
        depends_on=("market_definition",),
        primary_kinds=("market", "market_competition"),
        filename_needles=(
            "competition", "competitor", "market", "positioning", "landscape", "g2",
        ),
    ),
    DeepDiveRole(
        code="DD-06",
        name="Competitive Differentiation",
        slug="competitive_differentiation",
        track="B",
        stage_key="competitive_landscape",
        src="algo+web",
        category="market_research",
        spec_output="Imitability Ladder Report",
        depends_on=("market_definition",),
        foundation_deps=("F-01",),
        primary_kinds=("market", "market_competition"),
        filename_needles=(
            "competition", "differenti", "moat", "feature", "software", "market",
        ),
    ),
    DeepDiveRole(
        code="DD-05",
        name="Market Share Strategy",
        slug="market_share_strategy",
        track="B",
        stage_key="competitive_landscape",
        src="algo",
        category="strategy",
        spec_output="Win/Loss Matrix",
        depends_on=("market_definition",),
        primary_kinds=("market", "market_competition", "customer"),
        filename_needles=(
            "competition", "market share", "share", "win", "loss", "trend", "crm",
        ),
    ),
    DeepDiveRole(
        code="DD-07",
        name="SWOT Analysis",
        slug="swot_analysis",
        track="B",
        stage_key="competitive_landscape",
        src="algo",
        category="strategy",
        spec_output="Buyer's Perspective Analysis",
        # Synthesis runs after validated upstream findings are available.
        depends_on=(
            "competitive_differentiation",
            "market_share_strategy",
            "customer_stickiness",
            "revenue_quality",
            "cost_structure",
            "historical_performance",
            "market_risk",
            "internal_risk",
            "growth_opportunities",
        ),
        primary_kinds=("market", "market_competition", "customer"),
        filename_needles=(
            "competition", "porter", "swot", "threat", "nps", "review", "market",
        ),
    ),
    # Track C / Customer Analysis
    DeepDiveRole(
        code="DD-08",
        name="Customer Segmentation",
        slug="customer_segmentation",
        track="C",
        stage_key="customer_analysis",
        src="algo+web",
        category="customer_data",
        spec_output="Ideal Customer Profile (ICP)",
        foundation_deps=("F-05",),
        primary_kinds=("customer",),
        filename_needles=(
            "commercial",
            "customer",
            "segment",
            "icp",
            "thesis",
            "executive",
        ),
    ),
    DeepDiveRole(
        code="DD-11",
        name="Customer Stickiness",
        slug="customer_stickiness",
        track="C",
        stage_key="customer_analysis",
        src="algo+web",
        category="customer_data",
        spec_output="Revenue Retention Table",
        primary_kinds=("customer", "financial"),
        filename_needles=(
            "retention",
            "cohort",
            "valuation",
            "churn",
            "commercial",
            "comparable",
        ),
    ),
    DeepDiveRole(
        code="DD-12",
        name="Customer Satisfaction",
        slug="customer_satisfaction",
        track="C",
        stage_key="customer_analysis",
        src="algo+web",
        category="customer_data",
        spec_output="Onboarding Failure Analysis",
        depends_on=("competitor_identification",),
        primary_kinds=("customer", "market_competition"),
        filename_needles=(
            "commercial",
            "churn",
            "nps",
            "csat",
            "survey",
            "retention",
            "competition",
        ),
    ),
    DeepDiveRole(
        code="DD-09",
        name="Buying Behavior",
        slug="buying_behavior",
        track="C",
        stage_key="customer_analysis",
        src="algo+web",
        category="customer_data",
        spec_output="Concentration Risk Analysis",
        depends_on=("market_share_strategy",),
        primary_kinds=("customer", "financial"),
        filename_needles=(
            "commercial",
            "concentration",
            "channel",
            "retention",
            "valuation",
            "customer",
        ),
    ),
    # Track D / Supplier & Operational
    DeepDiveRole(
        code="DD-22",
        name="Supplier Dependence",
        slug="supplier_dependence",
        track="D",
        stage_key="supplier_and_operational_analysis",
        src="algo",
        category="operations",
        spec_output="Vendor Concentration Risk Analysis",
        primary_kinds=("operations",),
        filename_needles=(
            "supplier",
            "vendor",
            "manufacturing",
            "supply chain",
            "cell",
            "lithium",
        ),
    ),
    DeepDiveRole(
        code="DD-13",
        name="Cost Structure",
        slug="cost_structure",
        track="D",
        stage_key="supplier_and_operational_analysis",
        src="algo",
        category="operations",
        spec_output="Economic Engine Efficiency",
        foundation_deps=("F-06",),
        primary_kinds=("operations", "financial"),
        filename_needles=(
            "financial",
            "bom",
            "gross margin",
            "thesis",
            "sales marketing spend",
            "cac",
            "ltv",
            "spend",
            "manufacturing",
        ),
    ),
    DeepDiveRole(
        code="DD-19",
        name="Operational Risk",
        slug="operational_risk",
        track="D",
        stage_key="supplier_and_operational_analysis",
        src="algo",
        category="operations",
        spec_output="Billing Integrity Audit",
        primary_kinds=("operations", "financial"),
        filename_needles=(
            "operational",
            "manufacturing",
            "defect",
            "service",
            "crm vs",
            "accounting",
            "audit",
            "integrity",
            "tier",
        ),
    ),
    # Ops producer for finance (MRR/PVM). Downstream only — no finance deps.
    DeepDiveRole(
        code="DD-14",
        name="Supply Chain Resilience",
        slug="supply_chain_resilience",
        track="D",
        stage_key="supplier_and_operational_analysis",
        src="algo",
        category="operations",
        spec_output="MRR Waterfall Narrative",
        primary_kinds=("operations", "financial"),
        filename_needles=(
            "manufacturing",
            "localization",
            "logistics",
            "mrr",
            "waterfall",
            "pvm",
            "supply chain",
        ),
    ),
    # Track F / Financial Analysis (critical path) — consumes C + D, never feeds them
    DeepDiveRole(
        code="DD-23",
        name="Historical Performance",
        slug="historical_performance",
        track="F",
        stage_key="financial_analysis",
        src="algo",
        category="financial_data",
        spec_output="Adjusted EBITDA Bridge",
        depends_on=("buying_behavior", "operational_risk"),
        primary_kinds=("financial",),
        filename_needles=(
            "financial",
            "p&l",
            "pnl",
            "historical",
            "income",
            "ebitda",
            "profit",
            "revenue",
        ),
    ),
    # Distinct Genovation code DD-09b (not DD-09). Runtime key = revenue_quality.
    DeepDiveRole(
        code="DD-09b",
        name="Revenue Quality",
        slug="revenue_quality",
        track="F",
        stage_key="financial_analysis",
        src="algo",
        category="financial_data",
        spec_output="Revenue Persistence Analysis",
        depends_on=("buying_behavior", "supply_chain_resilience"),
        primary_kinds=("financial", "customer"),
        filename_needles=(
            "revenue",
            "recurring",
            "mrr",
            "retention",
            "churn",
            "valuation",
            "nrr",
            "grr",
        ),
    ),
    DeepDiveRole(
        code="DD-24a",
        name="Cash Flow",
        slug="cash_flow",
        track="F",
        stage_key="financial_analysis",
        src="algo",
        category="financial_data",
        spec_output="Cash Flow Profile",
        depends_on=("supply_chain_resilience", "historical_performance"),
        primary_kinds=("financial",),
        filename_needles=(
            "cash",
            "working capital",
            "liquidity",
            "burn",
            "capex",
            "financial",
        ),
    ),
    DeepDiveRole(
        code="DD-24",
        name="Capital Structure",
        slug="capital_structure",
        track="F",
        stage_key="financial_analysis",
        src="algo",
        category="financial_data",
        spec_output="Intrinsic Value Statement (NPV)",
        depends_on=("historical_performance", "supply_chain_resilience"),
        primary_kinds=("financial",),
        filename_needles=(
            "projection",
            "5year",
            "dcf",
            "valuation",
            "model",
            "capital",
            "debt",
            "financial",
        ),
    ),
    # Track E / Risk & Opportunity (live stage)
    DeepDiveRole(
        code="DD-20",
        name="Market Risk",
        slug="market_risk",
        track="E",
        stage_key="risk_and_opportunity_assessment",
        src="algo",
        category="strategy",
        spec_output="External market risks sized to company numbers",
        depends_on=("demand_drivers",),
        foundation_deps=("F-04",),
        primary_kinds=("market", "legal", "deal_strategy"),
        filename_needles=(
            "esg",
            "risk",
            "regulatory",
            "legal",
            "fame",
            "subsidy",
            "litigation",
            "investment",
            "thesis",
        ),
    ),
    DeepDiveRole(
        code="DD-21",
        name="Internal Risk",
        slug="internal_risk",
        track="E",
        stage_key="risk_and_opportunity_assessment",
        src="algo",
        category="strategy",
        spec_output="Internal risks a buyer inherits on day one",
        depends_on=("management_quality", "capital_structure"),
        primary_kinds=("operations", "company_management", "financial"),
        filename_needles=(
            "architecture",
            "tech debt",
            "it ",
            "technology",
            "technical",
            "software",
            "cyber",
            "hr",
            "org",
            "governance",
            "audit",
            "internal control",
            "financial",
        ),
    ),
    DeepDiveRole(
        code="DD-01b",
        name="Growth Opportunities",
        slug="growth_opportunities",
        track="E",
        stage_key="risk_and_opportunity_assessment",
        src="algo",
        category="strategy",
        spec_output="Growth Levers",
        depends_on=("market_volume_and_growth", "market_pricing"),
        primary_kinds=("market", "deal_strategy"),
        filename_needles=(
            "growth",
            "expansion",
            "opportunity",
            "thesis",
            "investment",
            "tam",
            "penetration",
        ),
    ),
    DeepDiveRole(
        code="DD-06b",
        name="Synergies",
        slug="synergies",
        track="E",
        stage_key="risk_and_opportunity_assessment",
        src="algo",
        category="strategy",
        spec_output="Synergy Thesis",
        depends_on=("competitive_differentiation",),
        foundation_deps=("F-01",),
        primary_kinds=("deal_strategy", "market"),
        filename_needles=(
            "synergy",
            "thesis",
            "cim",
            "investment",
            "value creation",
            "integration",
        ),
    ),
)

TRACK_LABELS: dict[str, str] = {
    "A": "Market",
    "B": "Competition",
    "C": "Customers",
    "D": "Operations",
    "E": "Legal/ESG & Risk",
    "F": "Financials",
}

FINDINGS_DOC_BY_TRACK: dict[str, tuple[str, ...]] = {
    "A": (
        "Market Ceiling Analysis",
        "Macro Environment Analysis",
        "Regional Economic Cycle Risk",
    ),
    "B": (
        "Competitive Positioning Matrix",
        "Win/Loss Matrix",
        "Imitability Ladder Report",
        "Buyer's Perspective Analysis",
    ),
    "C": (
        "ICP Definition",
        "Concentration Risk Analysis",
        "Revenue Persistence Analysis",
        "Retention Table",
        "Churn Analysis",
    ),
    "D": (
        "Engine Efficiency",
        "MRR Waterfall",
        "Revenue Bridge",
        "PVM Variance",
        "Pricing Analysis",
        "Tier Assessment",
        "Integrity Audit",
    ),
    "E": (
        "ESG Eligibility",
        "Tech Debt Assessment",
        "Vendor Risk Analysis",
    ),
    "F": (
        "Adjusted EBITDA Bridge",
        "Intrinsic Value (NPV)",
    ),
}


def role_by_slug(slug: str) -> DeepDiveRole | None:
    return next((role for role in DEEP_DIVE_ROLES if role.slug == slug), None)


def role_by_code(code: str) -> DeepDiveRole | None:
    return next((role for role in DEEP_DIVE_ROLES if role.code == code), None)


def all_deep_dive_slugs() -> list[str]:
    return [role.slug for role in DEEP_DIVE_ROLES]


def depends_on_map() -> dict[str, tuple[str, ...]]:
    return {role.slug: role.depends_on for role in DEEP_DIVE_ROLES}


def topo_order(slugs: list[str] | None = None) -> list[str]:
    """Strict topological order over Deep Dive roles (catalog order as tie-break).

    On a cycle, returns acyclic prefix then remaining cyclic nodes (catalog order).
    Callers that need a hard fail should use ``validate_dag()`` — do not treat
    ``len(topo_order()) == n`` as proof the DAG is acyclic.
    """
    wanted = set(slugs or all_deep_dive_slugs())
    # Include upstream deps of requested slugs.
    expanded = set(wanted)
    changed = True
    while changed:
        changed = False
        for role in DEEP_DIVE_ROLES:
            if role.slug not in expanded:
                continue
            for dep in role.depends_on:
                if dep not in expanded:
                    expanded.add(dep)
                    changed = True

    remaining = {role.slug for role in DEEP_DIVE_ROLES if role.slug in expanded}
    ordered: list[str] = []
    deps = depends_on_map()
    catalog = all_deep_dive_slugs()

    while remaining:
        ready = [
            slug
            for slug in catalog
            if slug in remaining and all(dep not in remaining for dep in deps.get(slug, ()))
        ]
        if not ready:
            # Cycle detected — do not swallow; append stuck nodes after the break.
            break
        for slug in ready:
            ordered.append(slug)
            remaining.remove(slug)

    if remaining:
        ordered.extend(slug for slug in catalog if slug in remaining)
    return ordered


def validate_dag() -> list[str]:
    """Return human-readable DAG errors (empty = valid)."""
    errors: list[str] = []
    known = set(all_deep_dive_slugs())
    deps = depends_on_map()

    slugs = [role.slug for role in DEEP_DIVE_ROLES]
    codes = [role.code for role in DEEP_DIVE_ROLES]
    if len(slugs) != len(set(slugs)):
        errors.append("Duplicate Deep Dive slug(s) — slug must be unique")
    if len(codes) != len(set(codes)):
        errors.append("Duplicate Deep Dive code(s) — full code (incl. suffix) must be unique")

    for role in DEEP_DIVE_ROLES:
        for dep in role.depends_on:
            if dep not in known:
                errors.append(f"Role '{role.slug}' depends on unknown slug '{dep}'")
            if dep == role.slug:
                errors.append(f"Role '{role.slug}' has a self-referential depends_on")

    # Strict cycle check (independent of topo_order cycle fallback).
    remaining = set(known)
    catalog = all_deep_dive_slugs()
    while remaining:
        ready = [
            slug
            for slug in catalog
            if slug in remaining and all(dep not in remaining for dep in deps.get(slug, ()))
        ]
        if not ready:
            errors.append(f"Cyclic dependency detected among: {sorted(remaining)}")
            break
        for slug in ready:
            remaining.remove(slug)

    return errors


def cascade_blast_radius(slug: str) -> list[str]:
    """Downstream consumers (direct + transitive) for Slice 7 cascade design."""
    children: dict[str, list[str]] = {s: [] for s in all_deep_dive_slugs()}
    for role in DEEP_DIVE_ROLES:
        for dep in role.depends_on:
            children.setdefault(dep, []).append(role.slug)
    out: list[str] = []
    stack = list(children.get(slug, []))
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(children.get(cur, []))
    return out
