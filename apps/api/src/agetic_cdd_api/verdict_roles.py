"""Phase 4 Final Verdict roles — FV-01…FV-07 bound to live slug keys.

Runtime identity is DiligenceIQ `agent_key` (`slug`). Genovation `code` (FV-01…)
is the stable spec id. Orchestration and the Verdict Store key on **slug**.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerdictRole:
    code: str  # FV-01…FV-07
    name: str
    slug: str  # DiligenceIQ agent_key
    stage: str  # A | B | C
    stage_key: str
    spec_output: str
    depends_on: tuple[str, ...] = ()  # upstream verdict slugs
    foundation_deps: tuple[str, ...] = ()  # F-01…F-06 role codes
    deep_dive_deps: tuple[str, ...] = ()  # upstream DD live slugs
    vdr_ref: str = ""  # reference CyberGuard filename (bind by kind at runtime)
    filename_needles: tuple[str, ...] = ()


STAGE_LABELS: dict[str, str] = {
    "A": "Risks & Growth",
    "B": "Valuation",
    "C": "Summary & Recommendation",
}

STAGE_ORDER: tuple[str, ...] = ("A", "B", "C")

# Sequential stages A → B → C; in-phase depends_on for FV-02→FV-04→FV-07 chain.
VERDICT_ROLES: tuple[VerdictRole, ...] = (
    VerdictRole(
        code="FV-01",
        name="Execution Risk",
        slug="execution_risk",
        stage="A",
        stage_key="risks_and_growth",
        spec_output="Human Capital Vulnerability Assessment",
        foundation_deps=("F-06",),
        vdr_ref="Exec_Tenure_and_Equity_Schedule.xlsx",
        filename_needles=("hr", "organizational", "tenure", "equity", "succession", "key-man"),
    ),
    VerdictRole(
        code="FV-02",
        name="Compensation Alignment",
        slug="compensation_alignment",
        stage="A",
        stage_key="risks_and_growth",
        spec_output="Compensation Adjustment Table",
        foundation_deps=("F-06",),
        deep_dive_deps=("cost_structure",),  # Genovation DD-13
        vdr_ref="Exec_Comp_vs_Market_Benchmark.csv",
        filename_needles=("hr", "compensation", "esop", "benchmark", "organizational"),
    ),
    VerdictRole(
        code="FV-03",
        name="Trading Comps",
        slug="trading_comps",
        stage="B",
        stage_key="valuation",
        spec_output="Valuation Benchmark Analysis",
        deep_dive_deps=("market_definition", "historical_performance"),  # DD-01, DD-23
        vdr_ref="Public_SaaS_Trading_Multiples.csv",
        filename_needles=("valuation", "comparable", "comps", "trading", "multiple"),
    ),
    VerdictRole(
        code="FV-04",
        name="Precedent Transactions",
        slug="precedent_transactions",
        stage="B",
        stage_key="valuation",
        spec_output="Precedent Transaction Analysis",
        depends_on=("compensation_alignment",),
        foundation_deps=("F-05",),
        vdr_ref="Recent_M_and_A_Deals_Cyber.csv",
        filename_needles=("valuation", "precedent", "transaction", "m&a", "deal"),
    ),
    VerdictRole(
        code="FV-05",
        name="Valuation Model",
        slug="valuation_modeling",
        stage="B",
        stage_key="valuation",
        spec_output="One earnings basis; comps / precedents / DCF reconciled",
        depends_on=("trading_comps", "precedent_transactions"),
        deep_dive_deps=("historical_performance", "capital_structure"),  # DD-23, DD-24
        vdr_ref="Valuation_Summary_Bridge.xlsx",
        filename_needles=("valuation", "dcf", "sensitivity", "bridge", "wacc"),
    ),
    VerdictRole(
        code="FV-06",
        name="IC Synthesis",
        slug="ic_synthesis",
        stage="C",
        stage_key="executive_synthesis",
        spec_output="Executive Summary (committee page)",
        depends_on=(
            "execution_risk",
            "compensation_alignment",
            "trading_comps",
            "precedent_transactions",
            "valuation_modeling",
        ),
        vdr_ref="Final_Diligence_Findings_All_Agents.txt",
        filename_needles=("findings", "investment thesis", "executive summary"),
    ),
    VerdictRole(
        code="FV-07",
        name="Recommendation",
        slug="recommendation",
        stage="C",
        stage_key="executive_synthesis",
        spec_output="Transaction Structure & Returns Summary",
        depends_on=("ic_synthesis",),
        vdr_ref="Term_Sheet_Draft_v1.pdf",
        filename_needles=("investment thesis", "term sheet", "deal structure", "valuation", "executive summary"),
    ),
)


_SLUG_MAP: dict[str, VerdictRole] = {role.slug: role for role in VERDICT_ROLES}
_CODE_MAP: dict[str, VerdictRole] = {role.code: role for role in VERDICT_ROLES}
_ALL_VERDICT_SLUGS: tuple[str, ...] = tuple(role.slug for role in VERDICT_ROLES)
_children_lists: dict[str, list[str]] = {slug: [] for slug in _ALL_VERDICT_SLUGS}
for role in VERDICT_ROLES:
    for dep in role.depends_on:
        _children_lists[dep].append(role.slug)
_CASCADE_CHILDREN: dict[str, tuple[str, ...]] = {
    slug: tuple(children) for slug, children in _children_lists.items()
}


def all_verdict_slugs() -> list[str]:
    return [role.slug for role in VERDICT_ROLES]


def role_by_slug(slug: str) -> VerdictRole | None:
    return _SLUG_MAP.get(slug)


def role_by_code(code: str) -> VerdictRole | None:
    return _CODE_MAP.get(code)


def depends_on_map() -> dict[str, tuple[str, ...]]:
    return {role.slug: role.depends_on for role in VERDICT_ROLES}


def topo_order(requested: list[str] | None = None) -> list[str]:
    """Topological run order from depends_on (stage A→B→C is implicit in the DAG)."""
    catalog = tuple(role.slug for role in VERDICT_ROLES)
    wanted = set(requested) if requested else set(catalog)
    deps = depends_on_map()

    ordered: list[str] = []
    remaining = {slug for slug in catalog if slug in wanted}

    while remaining:
        ready = [
            slug
            for slug in catalog
            if slug in remaining
            and all(dep not in remaining for dep in deps.get(slug, ()))
        ]
        if not ready:
            ordered.extend(slug for slug in catalog if slug in remaining)
            break
        for slug in ready:
            ordered.append(slug)
            remaining.remove(slug)

    return ordered


def validate_dag() -> list[str]:
    """Return human-readable DAG errors (empty = valid)."""
    errors: list[str] = []
    slugs = [role.slug for role in VERDICT_ROLES]
    codes = [role.code for role in VERDICT_ROLES]
    known = set(slugs)
    deps = depends_on_map()

    if len(slugs) != len(set(slugs)):
        errors.append("Duplicate Final Verdict slug(s)")
    if len(codes) != len(set(codes)):
        errors.append("Duplicate Final Verdict code(s)")

    for role in VERDICT_ROLES:
        for dep in role.depends_on:
            if dep not in known:
                errors.append(f"Role '{role.slug}' depends on unknown slug '{dep}'")
            if dep == role.slug:
                errors.append(f"Role '{role.slug}' has a self-referential depends_on")

    remaining = set(known)
    catalog = slugs
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
    """Downstream verdict consumers (direct + transitive)."""
    out: list[str] = []
    stack = list(_CASCADE_CHILDREN.get(slug, ()))
    seen: set[str] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        out.append(cur)
        stack.extend(_CASCADE_CHILDREN.get(cur, ()))
    return out
