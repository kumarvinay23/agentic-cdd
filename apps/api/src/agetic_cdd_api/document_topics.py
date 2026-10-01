"""Document topic keys — dedupe next steps and section headings."""

from __future__ import annotations

import re

# Maps next-step catalog keys to phrases that indicate the topic is already covered.
TOPIC_NEEDLES: dict[str, tuple[str, ...]] = {
    "market_overview": ("market overview", "industry overview", "market landscape"),
    "business_model": ("business model", "revenue model", "go to market", "how does"),
    "growth_strategy": ("growth strategy", "expansion strategy", "scaling plan"),
    "key_risks": ("key risk", "investment risk", "key investment risks", "mitigant"),
    "market_share": ("market share", "'s market share", "share of the market", "share trend"),
    "growth_rate": ("growth rate", "revenue growth", "cagr", "yoy", "year over year"),
    "competitor": ("competitor", "competition", "competitive landscape", "main competitors", "who are the main"),
    "penetration": ("penetration", "addressable market", "tam", "sam", "som"),
    "sales_ratio": ("sales ratio", "channel mix", "sales mix", "mix ratio"),
    # Scope & Methodology agent docs (coverage record)
    "coverage_table": ("coverage table", "coverage record", "questions evidenced", "work done"),
    "exclusions": ("exclusions & ownership", "out of scope", "cannot with current evidence", "not yet done"),
    "fieldwork": ("fieldwork log", "interview", "site visit", "participants"),
    "unfinished": ("unfinished work", "must_close", "must close", "residual", "could change"),
    "coverage_conclusion": ("coverage conclusion", "diligence coverage", "completeness of the diligence"),
    "quality_reliance": ("quality & reliance", "quality:", "reliance:", "rework", "blocked"),
    # Valuation Model (FV-05)
    "earnings_basis": (
        "declared earnings",
        "earnings basis",
        "earnings figure",
        "one earnings",
    ),
    "comps": (
        "comparable compan",
        "trading comps",
        "peer median",
        "range & median",
    ),
    "precedents": (
        "precedent transaction",
        "precedents",
        "acquirer",
        "consideration",
    ),
    "dcf": (
        "discounted cash flow",
        "discount rate",
        "wacc",
        "terminal assumption",
        "implied exit multiple",
    ),
    "reconcile": (
        "method reconciliation",
        "reconcile the methods",
        "football field",
        "disagree materially",
    ),
    # Sensitivity Analysis (nested under valuation_modeling)
    "ranked_drivers": (
        "ranked driver",
        "one at a time",
        "value movement",
        "tornado",
    ),
    "sens_grid": (
        "two-driver grid",
        "two driver grid",
        "wacc vs",
        "direction check",
        "sensitivity matrix",
    ),
    "sens_cases": (
        "downside, base",
        "downside / base",
        "upside case",
        "by their assumptions",
        "growth, margin and capital",
    ),
    "breakevens": (
        "break-even",
        "breakeven",
        "falls below the hurdle",
        "operating terms",
    ),
    # Final Valuation Range
    "final_range": (
        "final valuation range",
        "low, base and high",
        "low / base / high",
        "publishing gate",
        "range withheld",
    ),
    "walk_away": (
        "walk-away",
        "walk away",
        "above the recommended",
        "above, not below",
    ),
    "ev_equity_bridge": (
        "ev → equity",
        "ev to equity",
        "equity bridge",
        "net debt position",
        "debt-like",
    ),
    # legacy scope needles (older docs)
    "ic_questions": ("ic question", "investment committee", "key investment committee"),
    "engagement_boundaries": ("engagement boundar", "in-scope", "out-of-scope", "scope definition"),
    "methodology": ("analytical methodology", "frameworks applied", "data sources"),
    "time_horizon": ("time horizon", "historical analysis", "forward projection"),
    "deliverables": ("deliverable structure", "deliverable"),
    "synthesis": ("analytical synthesis", "hidden insights", "second-order"),
    "target_profile": ("target profile", "sector", "business model"),
    "provenance": ("source provenance", "## sources"),
    # Deal Context agent docs
    "exec_summary": ("executive summary", "deal overview"),
    "hypotheses": ("investment hypothes", "must-be-true", "must be true", "fail threshold"),
    "risks": ("critical risk", "red flag"),
    "open_questions": ("open question", "critical open question", "unlocking document"),
    "metrics": ("high-signal metric", "key metric"),
    "fact_ledger": ("fact ledger", "headline fact", "source locator"),
    "verdict": ("preliminary verdict", "recommendation", "confidence"),
    # Company Background agent docs (prompt-book operating picture)
    "revenue_splits": (
        "what it sells",
        "revenue by service",
        "revenue by customer",
        "revenue by geography",
        "accounts reconciliation",
        "recurring by contract",
    ),
    "physical_ops": (
        "physical operation",
        "sites & facilities",
        "fleet / capacity",
        "headcount by function",
    ),
    "ownership_history": (
        "ownership, legal",
        "cap table",
        "corporate record",
        "history (evidenced)",
    ),
    "operating_model": ("operating model", "unit of revenue", "in-house"),
    # legacy company-background needles
    "company_snapshot": ("company snapshot", "target name", "headquarters", "major shareholders"),
    "timeline": ("key timeline", "historical evolution", "m&a", "capital history"),
    "revenue_model": ("revenue breakdown", "business & revenue", "value proposition"),
    "products": ("products & solution", "product/service", "offering mix"),
    "footprint": ("organizational & operational", "global presence", "functional org"),
    "close_gaps": ("close gap", "n/a", "data room did not provide"),
    # Management Quality
    "exec_roster": (
        "executive & senior",
        "operating roster",
        "prior delivery",
        "vs target",
        "tenure",
    ),
    "key_persons": (
        "key-person",
        "key person",
        "what depends",
        "notice / incentives",
        "retention",
    ),
    "succession_board": (
        "succession by critical",
        "second-line",
        "second line",
        "board composition",
    ),
    "gap_states": (
        "confirmed vacancies",
        "capability gaps",
        "information gaps",
        "proposed hires",
    ),
}

_BACKFILL_ORDER: tuple[str, ...] = (
    "market_overview",
    "business_model",
    "growth_strategy",
    "key_risks",
    "growth_rate",
    "competitor",
    "penetration",
    "sales_ratio",
    "market_share",
)


def normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", (heading or "").strip().lower())


def topic_key_for_text(text: str) -> str | None:
    """Return the best-matching topic key for a heading or prompt."""
    lower = (text or "").lower()
    best_key: str | None = None
    best_len = 0
    for key, needles in TOPIC_NEEDLES.items():
        for needle in needles:
            if needle in lower and len(needle) > best_len:
                best_key = key
                best_len = len(needle)
    return best_key


def topic_keys_in_text(text: str) -> set[str]:
    lower = (text or "").lower()
    return {key for key, needles in TOPIC_NEEDLES.items() if any(n in lower for n in needles)}


def parse_section_headings(markdown: str) -> list[str]:
    headings: list[str] = []
    for line in (markdown or "").splitlines():
        if line.startswith("## ") and not line.strip().lower().startswith("## sources"):
            headings.append(line[3:].strip())
    return headings


def covered_topic_keys(
    *,
    document_markdown: str = "",
    user_prompts: list[str] | None = None,
) -> set[str]:
    """Topics already written or explicitly requested in this workspace."""
    covered: set[str] = set()
    for prompt in user_prompts or []:
        covered |= topic_keys_in_text(prompt)
    for heading in parse_section_headings(document_markdown):
        covered |= topic_keys_in_text(heading)
        key = topic_key_for_text(heading)
        if key:
            covered.add(key)
    return covered


def split_document_sections(markdown: str) -> tuple[str, list[tuple[str, str]]]:
    """Return preamble and body sections (heading, body) before Sources."""
    sources_header = "## Sources"
    marker = "<!-- cdd:sources"
    if sources_header in markdown:
        head, _, _ = markdown.partition(sources_header)
    elif marker in markdown:
        head, _, _ = markdown.partition(marker)
    else:
        head = markdown

    head = head.rstrip()
    if not head:
        return "", []

    parts = re.split(r"(?=^## )", head, flags=re.MULTILINE)
    preamble = ""
    sections: list[tuple[str, str]] = []
    for part in parts:
        stripped = part.strip()
        if not stripped:
            continue
        if not stripped.startswith("## "):
            preamble = stripped
            continue
        first_nl = stripped.find("\n")
        if first_nl < 0:
            heading = stripped[3:].strip()
            body = ""
        else:
            heading = stripped[3:first_nl].strip()
            body = stripped[first_nl + 1 :].strip()
        if heading.lower() == "sources":
            continue
        sections.append((heading, body))
    return preamble, sections


def backfill_topic_keys(
    *,
    picked: tuple[str, ...],
    covered: set[str],
    limit: int = 4,
    catalog_keys: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Fill next-step slots with uncovered topics when contextual picks repeat covered work."""
    out: list[str] = []
    seen: set[str] = set()
    fill_order = catalog_keys or _BACKFILL_ORDER
    for key in picked:
        if key in covered or key in seen:
            continue
        out.append(key)
        seen.add(key)
        if len(out) >= limit:
            return tuple(out)
    for key in fill_order:
        if key in covered or key in seen:
            continue
        out.append(key)
        seen.add(key)
        if len(out) >= limit:
            break
    return tuple(out)
