"""Findings and the executive summary.

Each report page answers one question. It carries the schedules, metrics
and comparison that question needs. The comparison recipe chooses the
chart. A finding is graded by impact and confidence, and the page title
states that finding and its number.

The executive summary is written last. Its words come from the graded
findings and the claims ledger. A figure that is in neither is not used.
"""

from __future__ import annotations

import re
from typing import Any

IMPACTS = ("high", "medium", "low")
CONFIDENCE = ("high", "medium", "low")
SUMMARY_ID = "executive_summary"
_DOWN = re.compile(r"\b(fell|declined|down|lower|below)\b", re.I)
_UP = re.compile(r"\b(grew|risen|rose|higher|above)\b", re.I)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def grade_finding(
    statement: str,
    *,
    number: int,
    impact: str,
    confidence: str,
    claim_status: str | None = None,
) -> dict[str, Any]:
    """Grade one finding. An unknown or a management claim cannot be high confidence."""
    if impact not in IMPACTS or confidence not in CONFIDENCE:
        raise ValueError("a finding needs an impact and a confidence")
    held = claim_status in {"unknown", "management_claim"}
    if held and confidence == "high":
        confidence = "medium"
    return {
        "number": number,
        "statement": statement.strip(),
        "impact": impact,
        "confidence": confidence,
        "held": held,
    }


def compare(recipe: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Run one comparison recipe. The chart comes from the recipe."""
    fn = _RECIPES.get(recipe)
    if fn is None:
        raise ValueError(f"unknown comparison {recipe}")
    return fn(inputs)


def build_page(
    page_id: str,
    question: str,
    *,
    schedules: list[str],
    metrics: list[str],
    comparison: dict[str, Any],
    finding: dict[str, Any],
) -> dict[str, Any]:
    """One page: the question, its evidence, the chart, and a title that states the finding."""
    compared = compare(str(comparison["recipe"]), comparison)
    if compared.get("error"):
        raise ValueError(str(compared["error"]))
    clash = _clash(compared, str(finding.get("statement") or ""))
    if clash:
        raise ValueError(clash)
    number = finding["number"]
    statement = str(finding["statement"]).strip()
    return {
        "page_id": page_id,
        "question": question,
        "schedules": list(schedules),
        "metrics": list(metrics),
        "comparison": compared,
        "chart": compared["chart"],
        "finding": finding,
        "title": f"{number}. {statement}",
    }


def assemble(
    plan: list[dict[str, Any]],
    pages: list[dict[str, Any]],
    claims_ledger: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Require every planned page, then write the executive summary from those findings."""
    ledger = claims_ledger or {"claims": []}
    by_id = {str(page.get("page_id")): page for page in pages}
    missing = [str(item["page_id"]) for item in plan if str(item["page_id"]) not in by_id]
    if missing:
        return {"ok": False, "error": "page plan missing " + ", ".join(missing)}
    ordered, gap = _ordered(plan, by_id)
    if gap:
        return {"ok": False, "error": gap}
    findings = [page["finding"] for page in ordered]
    body = _summary_body(findings, ledger)
    foreign = summary_is_grounded(body, findings, ledger)
    if foreign:
        return {"ok": False, "error": foreign}
    return {
        "ok": True,
        "pages": ordered,
        "executive_summary": {
            "page_id": SUMMARY_ID,
            "title": _summary_title(findings),
            "body": body,
            "composed_after": [page["page_id"] for page in ordered],
        },
    }


def summary_is_grounded(
    text: str,
    findings: list[dict[str, Any]],
    claims_ledger: dict[str, Any] | None,
) -> str | None:
    """A summary figure must already be in a graded finding or the claims ledger."""
    allowed = _allowed_numbers(findings, claims_ledger or {})
    foreign = [number for number in _NUMBER.findall(text or "") if number not in allowed]
    if foreign:
        return "executive summary uses a figure that is not in the findings or the claims ledger"
    return None


def ensure_findings(output: dict[str, Any]) -> str | None:
    """Hold a report whose page plan is incomplete or whose titles omit the finding."""
    plan = output.get("page_plan")
    if not isinstance(plan, list):
        return None
    pages = output.get("pages")
    if not isinstance(pages, list):
        return "page plan missing pages"
    result = assemble(plan, pages, output.get("claims_ledger") if isinstance(output.get("claims_ledger"), dict) else {"claims": []})
    if not result["ok"]:
        return str(result["error"])
    output["findings_report"] = result
    return None


def _ordered(plan: list[dict[str, Any]], by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    ordered: list[dict[str, Any]] = []
    for item in plan:
        page = by_id[str(item["page_id"])]
        if str(page.get("question") or "") != str(item.get("question") or ""):
            return [], f"{item['page_id']} does not answer its question"
        if not _states_finding(page):
            return [], f"{item['page_id']} title does not state its finding"
        ordered.append(page)
    return ordered, None


def _states_finding(page: dict[str, Any]) -> bool:
    finding = page.get("finding") or {}
    statement = str(finding.get("statement") or "").strip()
    number = str(finding.get("number") or "")
    title = str(page.get("title") or "")
    if not statement or not number or statement not in title:
        return False
    return re.search(rf"(^|\s){re.escape(number)}[.)]", title) is not None


def _summary_title(findings: list[dict[str, Any]]) -> str:
    lead = next((finding for finding in findings if not finding.get("held")), None)
    if lead is None:
        return "Held: no graded finding is established."
    return f"{lead['number']}. {lead['statement']}"


def _summary_body(findings: list[dict[str, Any]], ledger: dict[str, Any]) -> str:
    lines = [
        (
            f"{finding['number']}. {finding['statement']} "
            f"Impact {finding['impact']}, confidence {finding['confidence']}."
        )
        for finding in sorted(findings, key=lambda item: int(item["number"]))
    ]
    for claim in ledger.get("claims") or []:
        lines.append(_claim_line(claim))
    return "\n".join(line for line in lines if line)


def _claim_line(claim: dict[str, Any]) -> str:
    text = str(claim.get("claim_as_stated") or "").strip()
    status = str(claim.get("status") or "")
    if status == "unknown":
        return f"Held, not a proven problem: {text}"
    if status == "management_claim":
        return f"Management claim, not adopted: {text}"
    if status == "failed":
        return f"Rejected: {text}"
    if status in {"known", "tested"}:
        return text
    return ""


def _allowed_numbers(findings: list[dict[str, Any]], ledger: dict[str, Any]) -> set[str]:
    texts = [str(finding.get("statement") or "") for finding in findings]
    texts.extend(str(finding.get("number") or "") for finding in findings)
    for claim in ledger.get("claims") or []:
        texts.append(str(claim.get("claim_as_stated") or ""))
    return set(_NUMBER.findall(" ".join(texts)))


def _clash(compared: dict[str, Any], statement: str) -> str | None:
    direction = compared.get("direction")
    if direction not in {"up", "down"}:
        return None
    said_down = _DOWN.search(statement) is not None
    said_up = _UP.search(statement) is not None
    if said_down == said_up:
        return None
    said = "down" if said_down else "up"
    if said != direction:
        return "the finding does not match the comparison"
    return None


def _period_change(inputs: dict[str, Any]) -> dict[str, Any]:
    from agetic_cdd_api.services_claims import trend

    movement = trend(float(inputs["latest"]), float(inputs["prior"]), float(inputs["peak"]))
    return {"recipe": "period_change", "chart": "line", "result": movement, "direction": movement["versus_prior"]}


def _share(inputs: dict[str, Any]) -> dict[str, Any]:
    whole = float(inputs["whole"])
    if whole == 0:
        return {"error": "share needs a total", "chart": "bar"}
    share = float(inputs["part"]) / whole
    return {"recipe": "share", "chart": "bar", "result": {"share": round(share, 4)}, "direction": None}


def _gap(inputs: dict[str, Any]) -> dict[str, Any]:
    from agetic_cdd_api.services_claims import like_with_like

    fault = like_with_like(inputs["left"], inputs["right"])
    if fault:
        return {"error": fault, "chart": "bar"}
    gap = float(inputs["left"]["value"]) - float(inputs["right"]["value"])
    direction = "up" if gap > 0 else "down" if gap < 0 else "flat"
    return {"recipe": "gap", "chart": "bar", "result": {"gap": gap}, "direction": direction}


def _mix(inputs: dict[str, Any]) -> dict[str, Any]:
    parts = list(inputs.get("parts") or [])
    total = sum(float(part["value"]) for part in parts)
    if total == 0:
        return {"error": "mix needs a total", "chart": "stacked_bar"}
    shares = [{"label": part["label"], "share": round(float(part["value"]) / total, 4)} for part in parts]
    return {"recipe": "mix", "chart": "stacked_bar", "result": {"parts": shares}, "direction": None}


def _rank(inputs: dict[str, Any]) -> dict[str, Any]:
    rows = sorted(inputs.get("rows") or [], key=lambda row: float(row["value"]), reverse=True)
    return {
        "recipe": "rank",
        "chart": "bar",
        "result": {"order": [row["label"] for row in rows]},
        "direction": None,
    }


def _bridge(inputs: dict[str, Any]) -> dict[str, Any]:
    start = float(inputs["start"])
    end = float(inputs["end"])
    direction = "up" if end > start else "down" if end < start else "flat"
    return {"recipe": "bridge", "chart": "waterfall", "result": {"start": start, "end": end}, "direction": direction}


def _plan_vs_trading(inputs: dict[str, Any]) -> dict[str, Any]:
    from agetic_cdd_api.services_calculation_library import ask_calculation

    kept = {
        key: inputs[key]
        for key in ("plan", "ytd", "months", "trading", "earlier", "later", "plan_year", "later_year")
        if key in inputs
    }
    calc = ask_calculation("CALC-PLAN-VS-TRADING", inputs=kept)
    gap = float(calc["value"])
    direction = "up" if gap > 0 else "down" if gap < 0 else "flat"
    return {"recipe": "plan_vs_trading", "chart": "bar", "result": {"gap": gap, "basis": "plan"}, "direction": direction}


_RECIPES = {
    "period_change": _period_change,
    "share": _share,
    "gap": _gap,
    "mix": _mix,
    "rank": _rank,
    "bridge": _bridge,
    "plan_vs_trading": _plan_vs_trading,
}
