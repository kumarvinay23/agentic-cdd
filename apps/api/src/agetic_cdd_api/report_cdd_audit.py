"""Appendix audit for the CDD deck.

Verdicts are restated at the grade the facts support. Exceptions name a gap
in the record. The glossary lists a term only when the deck uses it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agetic_cdd_api.report_builder_base import BuildContext
from agetic_cdd_api.report_cdd_calcs import DeckMath
from agetic_cdd_api.report_cdd_deck_v4 import _resolve, _spec
from agetic_cdd_api.report_cdd_evidence import _module

_ORDER = ["blocked", "asserted", "limited", "indicated", "established"]
_LABEL = {
    "blocked": "Blocked",
    "asserted": "Asserted",
    "limited": "Limited",
    "indicated": "Indicated",
    "established": "Established",
}
_HAIRCUT = re.compile(r"(?i)haircut")


def verdict_rows(ctx: BuildContext, facts: list[dict[str, Any]]) -> list[dict[str, str]]:
    """One row per module that stated a verdict or loaded facts. Weakest first."""
    by_code: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        code = str(fact.get("module") or "")
        if code and code != "SCM":
            by_code.setdefault(code, []).append(fact)
    rows = []
    seen: set[str] = set()
    for key, agent in ctx.agent_outputs.items():
        if not isinstance(agent, dict):
            continue
        code, title = _module(key)
        if code in seen:
            continue
        seen.add(code)
        spec = _spec(agent)
        quality = str(spec.get("quality_verdict") or "").strip()
        reliance = str(spec.get("reliance_verdict") or "").strip()
        module_facts = by_code.get(code, [])
        if not quality and not reliance and not module_facts:
            continue
        stated_rank = _lower(_verdict_rank(quality), _verdict_rank(reliance))
        evidence_rank = _evidence_rank(module_facts)
        adjusted, basis = _adjusted(stated_rank, evidence_rank, quality, reliance)
        stated = " / ".join(part for part in (quality, reliance) if part) or "—"
        rows.append({
            "module": title,
            "stated": stated,
            "adjusted": adjusted,
            "basis": basis,
            "rank": adjusted,
        })
    rows.sort(key=lambda row: (_adjust_sort(row["rank"]), row["module"]))
    stated = [row for row in rows if row["stated"] != "—"]
    silent = [row for row in rows if row["stated"] == "—"]
    return stated + silent


def glossary_terms(slide_blob: str, terms: dict[str, str]) -> list[tuple[str, str]]:
    """Terms whose name appears in the deck, in alphabetical order."""
    found = []
    for key, meaning in terms.items():
        label = key.split(" (", 1)[0]
        if re.search(rf"(?<![A-Za-z]){re.escape(label)}(?![A-Za-z])", slide_blob, re.I):
            found.append((key, str(meaning)))
    found.sort(key=lambda item: item[0].lower())
    return found


def audit_exceptions(
    ctx: BuildContext,
    facts: list[dict[str, Any]],
    math: DeckMath,
    slides: dict[str, Any],
) -> list[dict[str, Any]]:
    """Material gaps. A template page with no exhibit is not, by itself, an exception."""
    items: list[dict[str, Any]] = []

    def add(severity: str, issue: str, treatment: str, slide: str, rule: str) -> None:
        items.append({
            "severity": severity,
            "rule": rule,
            "issue": issue,
            "treatment": treatment,
            "slides": [slide],
        })

    blocked_titles: list[str] = []
    for key, agent in ctx.agent_outputs.items():
        if not isinstance(agent, dict):
            continue
        spec = _spec(agent)
        stated = " ".join(
            str(spec.get(field) or "")
            for field in ("quality_verdict", "reliance_verdict")
        )
        if _verdict_rank(stated) == "blocked":
            _code, title = _module(key)
            blocked_titles.append(title)
    if blocked_titles:
        add(
            "HIGH",
            f"{len(blocked_titles)} modules are marked blocked.",
            "Findings from a blocked module are not relied on.",
            "S099_module_verdicts",
            "E1-NOT-PROVIDED",
        )

    bottom = _spec(_resolve(ctx, "market_volume_and_growth")).get("bottom_up")
    if isinstance(bottom, dict):
        blob = " ".join(str(bottom.get(key) or "") for key in ("capture_share", "arithmetic", "units", "bottom_up_size"))
        if _HAIRCUT.search(blob) and not math.haircuts:
            add(
                "HIGH",
                "A haircut rate has no money base.",
                "The rate was not applied.",
                "S089_sizing_method_core",
                "E1-NOT-PROVIDED",
            )

    if any(fact.get("module") == "HPF" and "plan" in (fact.get("period_status") or {}) for fact in facts):
        add(
            "MEDIUM",
            "Plan years are in the file and are not results.",
            "They carry a P suffix and stay off the actuals chart.",
            "S046_sam_growth_build" if "S046_sam_growth_build" in slides else "S009_company_snapshot",
            "E1-NOT-PROVIDED",
        )

    satisfaction = _spec(_resolve(ctx, "customer_satisfaction"))
    if not any(satisfaction.get(key) for key in ("nps", "interviews", "survey", "quotes")):
        add(
            "MEDIUM",
            "No customer survey or interviews were loaded.",
            "NPS and quote pages stay withheld.",
            "S065_incumbent_nps",
            "E11-NO-PRIMARY",
        )

    if math.assessment:
        add(
            "MEDIUM",
            "The competitor comparison is a self-assessment.",
            "Shown once, and not as customer evidence.",
            "S062_criteria_vs_archetypes",
            "E1-NOT-PROVIDED",
        )
    if math.prices and math.prices.get("gap"):
        add(
            "MEDIUM",
            "The price gap uses one peer price on one unit.",
            "It is not treated as a full benchmark.",
            "S064_price_benchmarking",
            "E1-NOT-PROVIDED",
        )
    if math.quotas:
        add(
            "MEDIUM",
            "Quotas have no rep-level bookings behind them.",
            "They are shown as the plan stated them.",
            "S075_l1_channel_expansion",
            "E1-NOT-PROVIDED",
        )
    if math.zips:
        add(
            "MEDIUM",
            "ZIP scores have no revenue attached.",
            "They are not converted into a market figure.",
            "S081_l5_adjacent_segments",
            "E1-NOT-PROVIDED",
        )
    if math.ties and math.ties.get("slide") in slides:
        add("HIGH", math.ties["issue"], math.ties["treatment"], math.ties["slide"], "E3-CONFLICT")
    if math.unit_basis and math.unit_basis.get("issue") and math.unit_basis.get("slide") in slides:
        add("HIGH", math.unit_basis["issue"], math.unit_basis["treatment"], math.unit_basis["slide"], "E3-CONFLICT")
    if math.deals and any(row.get("residual") is not None for row in math.deals["rows"]):
        add(
            "MEDIUM",
            "A stated earnings effect is not net of cost.",
            "The remainder is shown as gross.",
            "S083_l7_ma",
            "E3-CONFLICT",
        )

    read = any(fact.get("source") == "vdr_direct" for fact in facts)
    cited = any((fact.get("citations") or {}).get("doc") and fact.get("source") != "vdr_direct" for fact in facts)
    if cited and not read:
        add(
            "MEDIUM",
            "Files named by the modules were not read as workbooks.",
            "The source register marks them cited only.",
            "S100_source_register",
            "E1-NOT-PROVIDED",
        )

    if not items:
        add(
            "MEDIUM",
            "No material gap was detected in the loaded modules.",
            "Template pages without an exhibit stay withheld.",
            "S005_research_approach",
            "E1-NOT-PROVIDED",
        )
    severity = {"HIGH": 0, "MEDIUM": 1}
    items.sort(key=lambda item: severity.get(item["severity"], 9))
    return items


def _verdict_rank(text: str) -> str:
    token = str(text or "").upper()
    if any(word in token for word in ("BLOCK", "FAIL", "REJECT")):
        return "blocked"
    if "ASSERT" in token:
        return "asserted"
    if any(word in token for word in ("LIMIT", "LOW", "WEAK")):
        return "limited"
    if any(word in token for word in ("INDICAT", "MEDIUM", "PARTIAL")):
        return "indicated"
    if any(word in token for word in ("PASS", "HIGH", "READY", "ESTABLISH")):
        return "established"
    return ""


def _lower(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    return left if _ORDER.index(left) <= _ORDER.index(right) else right


def _evidence_rank(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return "none"
    if all("UNCITED" in (fact.get("flags") or []) for fact in facts):
        return "asserted"
    if any(fact.get("source") == "vdr_direct" or fact.get("grade") == "established" for fact in facts):
        return "established"
    if any(fact.get("grade") == "indicated" for fact in facts):
        return "indicated"
    return "asserted"


def _adjusted(stated: str, evidence: str, quality: str, reliance: str) -> tuple[str, str]:
    if evidence == "none":
        return "Not produced", "No facts were loaded for this module."
    if stated == "blocked":
        return "Blocked", "The module marked itself blocked."
    if not stated:
        return _LABEL[evidence], "No verdict was stated, so the facts set the grade."
    if _ORDER.index(evidence) < _ORDER.index(stated):
        return _LABEL[evidence], "Lowered to the facts on file."
    if quality and reliance and _verdict_rank(quality) != _verdict_rank(reliance):
        return _LABEL[stated], "The lower stated grade is used."
    return _LABEL[stated], "The stated grade matches the facts."


def _adjust_sort(label: str) -> int:
    order = ["Not produced", "Blocked", "Asserted", "Limited", "Indicated", "Established"]
    return order.index(label) if label in order else len(order)


def slide_blob(slides: dict[str, Any]) -> str:
    return json.dumps(slides, ensure_ascii=False)
