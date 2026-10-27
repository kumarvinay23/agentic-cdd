"""Block statements the fact store contradicts, before they are written onto a page.

Called from ``derive`` before a deck is filled. The evidence book itself stays in
``report_cdd_evidence``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agetic_cdd_api.report_cdd_evidence import EvidenceBook

logger = logging.getLogger(__name__)

Fact = dict[str, Any]

_DEBUG_LINE = re.compile(
    r"period\(s\) from accounts|CIM gap\(s\)|databook promoted",
    re.I,
)
_PROFIT_RETURN = re.compile(r"(?i)returned to profit")
_YEAR = re.compile(r"\b(20\d{2})\b")
_REVENUE_ACTUAL = re.compile(r"Revenue (\d{4}) \(actual\): \$([0-9,]+\.\d{2})M")
_SCENARIO = re.compile(r"(?i)modeled|upside|full contract|spectrum")
_TOTAL_REVENUE = re.compile(r"(?i)^(total\s+)?(net\s+)?(revenues?|sales|turnover)$")
_PLAN_MILESTONE = re.compile(r"(?i)\bclose series\b")
_CELL_AMOUNT = re.compile(
    r"(?i)(?P<sign>-)?\s*[$€£]?\s*(?P<number>\d[\d,]*(?:\.\d+)?)\s*"
    r"(?P<unit>billions?|millions?|thousands?|bn|mn|mm|k|m|b)?"
)


def _cell_amount(raw: object) -> float | None:
    """Signed amount in millions. A thousands suffix and a leading minus both count."""
    match = _CELL_AMOUNT.search(str(raw or ""))
    if not match:
        return None
    number = float(match.group("number").replace(",", ""))
    if match.group("sign"):
        number = -number
    unit = (match.group("unit") or "").lower()
    if unit in {"b", "bn", "billion", "billions"}:
        return number * 1_000
    if unit in {"k", "thousand", "thousands"}:
        return number / 1_000
    if unit in {"m", "mm", "mn", "million", "millions"}:
        return number
    if abs(number) >= 100_000:
        return number / 1_000_000
    return number


def is_debug_line(text: str) -> bool:
    return bool(_DEBUG_LINE.search(str(text or "")))


def is_plan_milestone(text: str) -> bool:
    """An uncompleted plan item is not a milestone that has happened."""
    return bool(_PLAN_MILESTONE.search(str(text or "")))


def contradicts_profit_return(text: str, book: EvidenceBook) -> bool:
    """'Returned to profit' in a year is false when an earlier actual year is already positive."""
    if not _PROFIT_RETURN.search(str(text or "")):
        return False
    stated = _YEAR.search(str(text))
    stated_year = int(stated.group(1)) if stated else None
    positive: list[int] = []
    for fact in book.facts:
        if not re.fullmatch(r"(?i)ebitda", str(fact.get("row_label") or "").strip()):
            continue
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        for key, raw in cells.items():
            if not re.fullmatch(r"20\d{2}", str(key)):
                continue
            amount = _cell_amount(raw)
            if amount is not None and amount >= 0:
                positive.append(int(key))
    if not positive:
        return False
    if stated_year is None:
        return len(set(positive)) >= 2
    return any(year < stated_year for year in positive)


def drop_mislabeled_contract_revenue(book: EvidenceBook) -> None:
    """A modelled contract amount is not company revenue for a year the accounts do not state."""
    scenario_amounts: set[float] = set()
    account_years: set[str] = set()
    for fact in book.facts:
        label = str(fact.get("row_label") or "").strip()
        section = str(fact.get("section_title") or "")
        cells = fact.get("cells") if isinstance(fact.get("cells"), dict) else {}
        if _SCENARIO.search(f"{section} {label}"):
            for raw in cells.values():
                amount = _cell_amount(raw)
                if amount is not None:
                    scenario_amounts.add(round(amount, 2))
        if _TOTAL_REVENUE.match(label) and re.search(r"(?i)statement of operations|management accounts", section):
            for key in cells:
                if re.fullmatch(r"20\d{2}", str(key)):
                    account_years.add(str(key))
    if not scenario_amounts:
        return
    kept: list[Fact] = []
    removed: set[str] = set()
    for fact in book.facts:
        match = _REVENUE_ACTUAL.search(str(fact.get("text") or ""))
        if match and match.group(1) not in account_years:
            amount = round(float(match.group(2).replace(",", "")), 2)
            if any(abs(amount - scenario) <= 0.01 for scenario in scenario_amounts):
                fact_id = str(fact.get("id") or "")
                removed.add(fact_id)
                logger.info(
                    "Dropped mislabeled contract revenue %s: %s amount %.2f matches a scenario and is not an accounts year",
                    fact_id or "(no id)",
                    match.group(1),
                    amount,
                )
                continue
        kept.append(fact)
    if not removed:
        return
    book.facts = kept
    book.by_id = {str(fact.get("id") or ""): fact for fact in kept if fact.get("id")}
    for bucket, ids in list(book.buckets.items()):
        book.buckets[bucket] = [fid for fid in ids if fid not in removed]
