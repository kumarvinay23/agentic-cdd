"""S0/S1 Foundation contract: F-01…F-06 roles bound to live slugs and VDR kinds.

Live Workflow agent_keys stay unchanged. F-02/F-03 have no extra nav rows; they
are context-store roles until product adds UI. IP and ESG stay sibling slugs.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FoundationRole:
    code: str
    name: str
    slug: str | None
    substage: str
    primary_kinds: tuple[str, ...]
    secondary_kinds: tuple[str, ...]
    ui_visible: bool
    spec_output: str


# First-match filename kinds (category, kind) prepended in services_library.
BIND_FILENAME_TYPES: tuple[tuple[str, str, str], ...] = (
    (r"process\s*letter|process\s*memo|bid(?:ding)?\s*process", "deal_strategy", "process"),
    (r"\bnda\b|non[\s-]*disclosure", "legal_esg", "nda"),
    (r"articles\s*of\s*(inc|incorporation)|certificate\s*of\s*incorporation", "company_management", "articles"),
    (r"org(?:anisation|anization)?\s*chart|orgchart", "company_management", "org_chart"),
    (r"\bteaser\b", "deal_strategy", "teaser"),
    (r"\bcim\b|confidential\s*information\s*memorand", "deal_strategy", "cim"),
)

FOUNDATION_ROLES: tuple[FoundationRole, ...] = (
    FoundationRole(
        code="F-01",
        name="Deal Hypothesis",
        slug="strategic_direction",
        substage="A",
        primary_kinds=("cim", "strategy"),
        secondary_kinds=("teaser",),
        ui_visible=True,
        spec_output="Strategic Thesis Document",
    ),
    FoundationRole(
        code="F-02",
        name="Orchestrator",
        slug=None,
        substage="A",
        primary_kinds=("teaser",),
        secondary_kinds=("cim", "strategy"),
        ui_visible=False,
        spec_output="CDD Roadmap & Hook Analysis",
    ),
    FoundationRole(
        code="F-03",
        name="Process Lead",
        slug=None,
        substage="A",
        primary_kinds=("process",),
        secondary_kinds=(),
        ui_visible=False,
        spec_output="Bidding Timeline & Requirements Table",
    ),
    FoundationRole(
        code="F-04",
        name="Compliance",
        slug="regulatory_compliance",
        substage="A",
        primary_kinds=("nda",),
        secondary_kinds=("legal",),
        ui_visible=True,
        spec_output="Jurisdiction-real permits, tested obligations, litigation and transaction triggers",
    ),
    FoundationRole(
        code="F-05",
        name="Company Intel",
        slug="company_background",
        substage="B",
        primary_kinds=("articles",),
        secondary_kinds=("company",),
        ui_visible=True,
        spec_output="Legal Entity Status Statement",
    ),
    FoundationRole(
        code="F-06",
        name="Management Assessment",
        slug="management_quality",
        substage="B",
        primary_kinds=("org_chart",),
        secondary_kinds=("company",),
        ui_visible=True,
        spec_output="Operational Risk Map",
    ),
)

SIBLING_ROLES: tuple[FoundationRole, ...] = (
    FoundationRole(
        code="F-IP",
        name="IP & Technology",
        slug="ip_and_technology",
        substage="A",
        primary_kinds=("technical",),
        secondary_kinds=(),
        ui_visible=True,
        spec_output="Technology / IP baseline",
    ),
    FoundationRole(
        code="F-ESG",
        name="ESG & Sustainability",
        slug="esg_and_sustainability",
        substage="A",
        primary_kinds=("legal",),
        secondary_kinds=("nda",),
        ui_visible=True,
        spec_output="ESG factors with financial or regulatory consequence",
    ),
)

ALL_FOUNDATION_ROLES: tuple[FoundationRole, ...] = FOUNDATION_ROLES + SIBLING_ROLES

# S2: A (F-01 → F-02 → F-03/F-04/IP/ESG) then B (F-05 → F-06).
ROLE_WAVES: tuple[tuple[str, ...], ...] = (
    ("F-01",),
    ("F-02",),
    ("F-03", "F-04", "F-IP", "F-ESG"),
    ("F-05",),
    ("F-06",),
)

ROLE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "F-02": ("F-01",),
    "F-06": ("F-05",),
}


def role_by_code(code: str) -> FoundationRole | None:
    return next((role for role in ALL_FOUNDATION_ROLES if role.code == code), None)


def role_by_slug(slug: str) -> FoundationRole | None:
    return next((role for role in ALL_FOUNDATION_ROLES if role.slug == slug), None)


def _kind_of(doc: dict) -> str:
    return str(doc.get("doc_kind") or "")


def _filename_of(doc: dict) -> str:
    return str(doc.get("filename") or doc.get("name") or "")


def bind_for_role(index: dict, role: FoundationRole) -> dict:
    docs = [doc for doc in (index.get("documents") or []) if isinstance(doc, dict)]
    primary = [doc for doc in docs if _kind_of(doc) in role.primary_kinds]
    primary_names = {_filename_of(doc) for doc in primary}
    secondary = [
        doc
        for doc in docs
        if _kind_of(doc) in role.secondary_kinds and _filename_of(doc) not in primary_names
    ]
    if primary:
        coverage = "full"
    elif secondary:
        coverage = "partial"
    else:
        coverage = "missing"
    return {
        "code": role.code,
        "name": role.name,
        "slug": role.slug,
        "substage": role.substage,
        "ui_visible": role.ui_visible,
        "spec_output": role.spec_output,
        "coverage": coverage,
        "primary": [_filename_of(doc) for doc in primary if _filename_of(doc)],
        "secondary": [_filename_of(doc) for doc in secondary if _filename_of(doc)],
        "documents": primary + secondary,
    }


def bind_for_slug(index: dict, slug: str) -> dict | None:
    role = role_by_slug(slug)
    if role is None:
        return None
    return bind_for_role(index, role)


def foundation_binds(index: dict) -> dict[str, dict]:
    binds: dict[str, dict] = {}
    for role in ALL_FOUNDATION_ROLES:
        payload = bind_for_role(index, role)
        binds[role.code] = {key: value for key, value in payload.items() if key != "documents"}
    return binds


def primary_role_codes_for_kind(kind: str) -> list[str]:
    return [role.code for role in ALL_FOUNDATION_ROLES if kind in role.primary_kinds]


def needed_role_codes(slugs: list[str] | None, *, full_phase: bool) -> list[str]:
    """Ordered role codes for a Foundations run (full A→B chain or the requested slugs)."""
    if full_phase or not slugs:
        wanted = {role.code for role in ALL_FOUNDATION_ROLES}
    else:
        wanted = set()
        for slug in slugs:
            role = role_by_slug(slug)
            if role is None:
                continue
            wanted.add(role.code)
            wanted.update(ROLE_DEPENDENCIES.get(role.code, ()))
    ordered: list[str] = []
    for wave in ROLE_WAVES:
        for code in wave:
            if code in wanted:
                ordered.append(code)
    return ordered
