"""A status on every claim, and the claims ledger that records it.

Statuses are known, unknown, management claim, tested and failed. Unknown
can hold a conclusion back. It never proves a problem. The ledger is the
ontology claims schedule: the claim, its status, the facts that test it
and the result. History uses actuals. A plan or a forecast stays labelled.
A trend uses the latest period, the prior period and the peak. Disagreeing
sources keep the fact selected by source authority, and the conflict is
logged. A premium, advantage or gap requires the same population and the
same period. The deal stays separate from acquisitions the target plans.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

STATUSES = ("known", "unknown", "management_claim", "tested", "failed")
SCHEDULE_ID = "GOV-04"

# Same order as the ontology authority lists. Earlier documents win.
_AUTHORITY = {
    "FINANCIAL_ACTUAL": (
        "FIN_AUDITED_FS",
        "FIN_REVIEWED_FS",
        "FIN_TAX_RETURN",
        "FIN_MGMT_ACCOUNTS",
        "FIN_TRIAL_BALANCE",
        "FIN_INVESTOR_WORKBOOK",
        "FIN_QOE_REPORT",
        "CIM",
        "TEASER",
        "AGENT_OUTPUT",
    ),
    "FINANCIAL_PLAN": (
        "FIN_MGMT_MODEL",
        "FIN_BUDGET",
        "FIN_INVESTOR_WORKBOOK",
        "DEAL_MODEL",
        "CIM",
        "TEASER",
        "AGENT_OUTPUT",
    ),
    "KPI": (
        "KPI_SYSTEM_EXTRACT",
        "KPI_CUSTOMER_LIST",
        "KPI_MGMT_REPORT",
        "FIN_INVESTOR_WORKBOOK",
        "CIM",
        "TEASER",
        "AGENT_OUTPUT",
    ),
}
_PLAN = re.compile(r"\b(forecast|projected|projection|budget|plan)\b", re.I)
_WORD = re.compile(r"[a-z]{5,}")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def move(status: str, event: str) -> str:
    """Next status. A failed test of an unknown claim leaves it unknown."""
    if status not in STATUSES:
        raise ValueError(f"unknown claim status {status}")
    if status == "unknown" and event == "test_fail":
        return "unknown"
    steps = {
        ("unknown", "management"): "management_claim",
        ("unknown", "test_pass"): "tested",
        ("unknown", "adopt_actual"): "known",
        ("management_claim", "test_pass"): "tested",
        ("management_claim", "test_fail"): "failed",
        ("tested", "adopt"): "known",
        ("tested", "test_fail"): "failed",
        ("known", "test_fail"): "failed",
        ("failed", "test_pass"): "tested",
    }
    return steps.get((status, event), status)


def conclude(status: str, *, problem: bool) -> dict[str, Any]:
    """What the claim may support. Unknown and management claims prove nothing."""
    if status == "unknown":
        return {"conclusion": "held", "proves_problem": False}
    if status == "management_claim":
        return {"conclusion": "not_adopted", "proves_problem": False}
    if status == "failed":
        return {"conclusion": "rejected", "proves_problem": True}
    if status == "tested":
        return {"conclusion": "supported", "proves_problem": problem}
    if status == "known":
        return {"conclusion": "fact", "proves_problem": problem}
    raise ValueError(f"unknown claim status {status}")


def basis_of(text: str) -> str:
    """Label a figure. History may use only an actual."""
    if _PLAN.search(text or ""):
        if re.search(r"forecast|projected|projection", text or "", re.I):
            return "forecast"
        return "plan"
    return "actual"


def history_figure(figure: dict[str, Any]) -> dict[str, Any]:
    basis = str(figure.get("basis") or basis_of(str(figure.get("text") or "")))
    if basis in {"plan", "forecast"}:
        raise ValueError("history uses actual figures only")
    labelled = dict(figure)
    labelled["basis"] = "actual"
    return labelled


def trend(latest: float, prior: float, peak: float) -> dict[str, str]:
    """Compare the latest period with the prior period and the peak."""
    return {
        "versus_prior": _direction(latest, prior),
        "versus_peak": "at_peak" if latest == peak else "below_peak" if latest < peak else "above_peak",
    }


def like_with_like(left: dict[str, Any], right: dict[str, Any]) -> str | None:
    """A premium, advantage or gap needs the same population and the same period."""
    if left.get("population") != right.get("population") or left.get("period") != right.get("period"):
        return "compare like with like"
    return None


def deal_separation(item: dict[str, Any]) -> str | None:
    """An acquisition the target plans is not the deal being diligenced."""
    if item.get("subject") == "target_acquisition" and item.get("as_deal") is True:
        return "the deal is separate from the target's planned acquisitions"
    return None


def select_by_authority(family: str, sources: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Pick the fact the authority order selects, and log every disagreement."""
    order = _AUTHORITY.get(family) or _AUTHORITY["KPI"]
    ranked = sorted(sources, key=lambda source: _rank(order, str(source.get("doc_type") or "")))
    if not ranked:
        raise ValueError("no source to select")
    chosen = ranked[0]
    conflicts = [source for source in ranked[1:] if source.get("value") != chosen.get("value")]
    from agetic_cdd_api.services_fact_repository import record_selection

    chosen["fact_id"] = record_selection(chosen, conflicts)
    return chosen, conflicts


def matches_source(claim: str, source: str) -> bool:
    """True when the claim uses the source's numbers and wording."""
    claim_n = " ".join((claim or "").lower().split())
    source_n = " ".join((source or "").lower().split())
    if not claim_n or not source_n:
        return False
    if claim_n in source_n or source_n in claim_n:
        return True
    numbers = _NUMBER.findall(claim_n)
    if any(number not in source_n for number in numbers):
        return False
    words = _WORD.findall(claim_n)
    return any(word in source_n for word in words)


def wording_rate(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 1.0
    hits = sum(1 for claim, source in pairs if matches_source(claim, source))
    return hits / len(pairs)


def record_claim(agent_key: str, item: dict[str, Any]) -> dict[str, Any]:
    """One ledger row: status, the facts that test it, and the result."""
    status = str(item.get("status") or "unknown")
    if status not in STATUSES:
        raise ValueError(f"unknown claim status {status}")
    stated = str(item.get("claim_as_stated") or item.get("text") or "")
    source_wording = str(item.get("source_wording") or "")
    outcome = conclude(status, problem=bool(item.get("problem")))
    chosen, conflicts = _selection(item)
    return {
        "claim_id": item.get("claim_id") or _claim_id(agent_key, stated),
        "agent_module": agent_key,
        "claim_as_stated": stated,
        "tested_against": list(item.get("facts") or []),
        "result": _ledger_result(status),
        "use": outcome["conclusion"],
        "status": status,
        "proves_problem": outcome["proves_problem"],
        "wording_match": matches_source(stated, source_wording) if source_wording else False,
        "source_wording": source_wording,
        "basis": item.get("basis") or basis_of(stated),
        "selected": chosen,
        "conflicts": conflicts,
        "schedule": SCHEDULE_ID,
    }


def ensure_claims(agent_key: str, output: dict[str, Any]) -> str | None:
    """Attach the ledger. A claim that breaks a basis rule blocks publication."""
    raw = output.get("claims")
    rows = [item for item in raw if isinstance(item, dict)] if isinstance(raw, list) else []
    ledger: list[dict[str, Any]] = []
    for item in rows:
        gap = _claim_gap(item)
        if gap:
            return gap
        ledger.append(record_claim(agent_key, item))
    output["claims_ledger"] = {"schedule": SCHEDULE_ID, "claims": ledger}
    return None


def _claim_gap(item: dict[str, Any]) -> str | None:
    status = str(item.get("status") or "unknown")
    if status == "unknown" and item.get("proves_problem") is True:
        return "unknown cannot prove a problem"
    if item.get("use") == "history" and str(item.get("basis") or "") in {"plan", "forecast"}:
        return "history uses actual figures only"
    if item.get("comparison") == "trend" and None in (item.get("latest"), item.get("prior"), item.get("peak")):
        return "a trend compares the latest period with the prior period and the peak"
    if item.get("comparison") in {"premium", "advantage", "gap"}:
        sides = item.get("sides") or []
        if len(sides) == 2:
            return like_with_like(sides[0], sides[1])
    return deal_separation(item)


def _selection(item: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    sources = item.get("sources")
    if not isinstance(sources, list) or not sources:
        return None, []
    return select_by_authority(str(item.get("family") or "KPI"), sources)


def _ledger_result(status: str) -> str:
    if status in {"known", "tested"}:
        return "confirmed"
    if status == "failed":
        return "rejected"
    return "unverifiable"


def _direction(latest: float, other: float) -> str:
    if latest > other:
        return "up"
    if latest < other:
        return "down"
    return "flat"


def _rank(order: tuple[str, ...], doc_type: str) -> int:
    try:
        return order.index(doc_type)
    except ValueError:
        return len(order)


def _claim_id(agent_key: str, stated: str) -> str:
    digest = hashlib.sha256(f"{agent_key}|{stated}".encode()).hexdigest()[:8]
    return f"claim-{digest}"
