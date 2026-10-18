"""Compose DiligenceIQ Strategic Direction — growth plan vs evidence (prompt book).

Separate ambition / approved budget / tested case. Bridge, plan-vs-actual,
initiatives (stand-alone vs synergy), funding vs Cash Flow / Capital Structure.
No high-confidence while funding/capacity untested.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _fmt_num,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_THREE_CASE_RULE = (
    "Management ambition, the board-approved budget, and the independently "
    "tested case stay on separate lines — never merge them."
)
_BRIDGE_RULE = (
    "The plan bridge runs from latest actual revenue/EBITDA to plan final year "
    "by price, volume, mix, new geography, acquisition and cost."
)
_PVA_RULE = (
    "Delivery history uses original target vs actual for prior years — a future "
    "target is not evidence of past delivery."
)
_INITIATIVE_RULE = (
    "Each initiative states investment, capacity/hiring, dependencies, owner, "
    "timing and an on-track milestone — and is flagged stand-alone or synergy."
)
_FUNDING_RULE = (
    "Funding reconciles to available cash and debt capacity and is cross-checked "
    "with Cash Flow / Capital Structure where those agents are available."
)
_SYNERGY_RULE = (
    "Stand-alone growth is kept separate from synergy / buyer-contributed upside."
)
_NO_HIGH_CONF_RULE = (
    "Do not assign high confidence while material funding or capacity "
    "assumptions remain untested."
)
_SYNERGY_CUE = re.compile(
    r"(?i)\b(synerg(?:y|ies)|buyer\s+contribut|sponsor\s+value[- ]?add|"
    r"acquisition\s+upside|post[- ]deal\s+integration)\b"
)
_STANDALONE_CUE = re.compile(
    r"(?i)\b(stand[- ]alone|organic\s+growth|self[- ]funded|"
    r"funded\s+from\s+operating\s+cash|ex[- ]buyer)\b"
)

_FY_ROW = re.compile(
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+"
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?",
    re.IGNORECASE,
)
_REVENUE_ROW = re.compile(
    r"\bRevenue\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_EBITDA_ROW = re.compile(
    r"\bEBITDA\s+"
    r"([\d,\-\(\)]+(?:\.\d+)?)\s+([\d,\-\(\)]+(?:\.\d+)?)\s+"
    r"([\d,\-\(\)]+(?:\.\d+)?)\s+([\d,\-\(\)]+(?:\.\d+)?)\s+"
    r"([\d,\-\(\)]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_CAGR = re.compile(
    r"(?:CAGR|compound\s+annual\s+growth)[^\d%]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_MILESTONE = re.compile(
    r"(Gross Margin|EBITDA|PAT|NRR|Market Share|Capacity|Localization)"
    r"[^|]{0,40}?(?:>\s*)?(\d{1,3}(?:\.\d+)?)\s*%?\s*"
    r"(FY\s*20\d{2}E?)",
    re.IGNORECASE,
)
_CASH = re.compile(
    r"(?:cash(?:\s+balance)?|liquidity|runway)[^\d]{0,40}?"
    r"(?:INR\s*)?(?:₹)?\s*([\d,]+(?:\.\d+)?)\s*(cr|crore|Cr|million|bn|billion)?",
    re.IGNORECASE,
)
_DEBT = re.compile(
    r"(?:total\s+debt|senior\s+debt|net\s+debt)[^\d]{0,40}?"
    r"(?:USD\s*|INR\s*|₹\s*)?([\d,]+(?:\.\d+)?)\s*(cr|crore|m|million|bn|billion)?",
    re.IGNORECASE,
)


def _insight(text: Any, *, max_chars: int = 520) -> str:
    body = _clean(text, max_chars)
    return f"**Insight Snapshot:** {body}\n\n" if body else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not headers or not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else "—"
            cells.append(str(val or "—").replace("|", "\\|").replace("\n", " ").strip())
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def gather_strategic_direction_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "deal_strategy": 0,
        "financial": 1,
        "market_competition": 2,
        "operations": 3,
        "company_management": 4,
        "customer": 5,
    }
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]
    ranked = sorted(
        docs,
        key=lambda d: (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            str(d.get("filename") or ""),
        ),
    )
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        try:
            loaded = load_library_document(deal, filename) or {}
        except Exception:
            loaded = {}
        text = str(loaded.get("text") or doc.get("excerpt") or "")
        text = re.sub(r"[■▪●◆□◦\x7f]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _parse_num(raw: str) -> float | None:
    s = (raw or "").strip().replace(",", "")
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _fy_series(corpus: str) -> tuple[list[str], list[float], list[float]]:
    years_m = _FY_ROW.search(corpus)
    rev_m = _REVENUE_ROW.search(corpus)
    if not years_m or not rev_m:
        return [], [], []
    years = [f"FY{years_m.group(i)}" for i in range(1, 6)]
    revs = [_parse_num(rev_m.group(i)) for i in range(1, 6)]
    ebitdas: list[float | None] = [None] * 5
    ebitda_m = _EBITDA_ROW.search(corpus)
    if ebitda_m:
        ebitdas = [_parse_num(ebitda_m.group(i)) for i in range(1, 6)]
    # Drop None revs
    out_y, out_r, out_e = [], [], []
    for y, r, e in zip(years, revs, ebitdas):
        if r is None:
            continue
        out_y.append(y)
        out_r.append(r)
        out_e.append(e if e is not None else float("nan"))
    return out_y, out_r, out_e


def _cagr(start: float, end: float, years: int) -> str:
    if start <= 0 or years <= 0:
        return _NA
    rate = (end / start) ** (1 / years) - 1
    return f"{rate * 100:.1f}% {_COMPUTED}"


def _year_span_from_labels(*labels: str) -> int | None:
    """Years elapsed between two FY/calendar labels (2026→2030 = 4, not 5)."""
    years: list[int] = []
    for lab in labels:
        m = re.search(r"(20\d{2})", str(lab or ""))
        if m:
            years.append(int(m.group(1)))
    if len(years) < 2:
        return None
    span = abs(years[-1] - years[0])
    return span if span > 0 else None


def _fix_cagr_year_span_text(text: str, *, span: int | None = None) -> str:
    """Rewrite 'over N years' when N disagrees with year labels in the same string."""
    s = str(text or "")
    if not s:
        return s
    inferred = span
    if inferred is None:
        ys = [int(y) for y in re.findall(r"(20\d{2})", s)]
        if len(ys) >= 2:
            inferred = abs(ys[-1] - ys[0])
    if not inferred or inferred <= 0:
        return s
    # Recompute stated CAGR if "$A to $B over N years" pattern with wrong N
    m = re.search(
        r"(?i)\$?\s*([\d.]+)\s*M?\s+to\s+\$?\s*([\d.]+)\s*M?\s+over\s+(\d+)\s+years?",
        s,
    )
    if m:
        wrong_n = int(m.group(3))
        if wrong_n != inferred:
            try:
                start_v, end_v = float(m.group(1)), float(m.group(2))
                rate = (end_v / start_v) ** (1 / inferred) - 1
                cagr_txt = f"{rate * 100:.1f}%"
            except (ValueError, ZeroDivisionError):
                cagr_txt = None
            s = re.sub(
                rf"(?i)over\s+{wrong_n}\s+years?",
                f"over {inferred} years",
                s,
            )
            if cagr_txt:
                s = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*CAGR", f"{cagr_txt} CAGR", s, count=1)
                s = re.sub(r"CAGR\s*\([^)]*?(\d+(?:\.\d+)?)\s*%", f"CAGR ({cagr_txt}", s, count=1)
            return s
    s = re.sub(r"(?i)over\s+\d+\s+years?", f"over {inferred} years", s)
    return s


def _three_cases(corpus: str, f01: dict[str, Any] | None) -> dict[str, str]:
    sents = _sentences(corpus)
    ambition = _pick_sentences(
        sents,
        keywords=("ambition", "target", "aim", "roadmap", "path to", "fy2028", "fy2027"),
        limit=2,
    )
    budget = _pick_sentences(
        sents,
        keywords=("budget", "board", "approved", "plan", "guidance"),
        limit=2,
    )
    drivers = []
    if isinstance(f01, dict):
        drivers = [d for d in (f01.get("investment_drivers") or []) if isinstance(d, str)][:2]

    return {
        "management_ambition": (
            _clean(ambition[0], 280) + f" {_DOC_CITE}"
            if ambition
            else (
                _clean(drivers[0], 280) + f" {_DOC_CITE}"
                if drivers
                else _info_request("management ambition / long-range plan narrative")
            )
        ),
        "board_approved_budget": (
            _clean(budget[0], 280) + f" {_DOC_CITE}"
            if budget
            else _info_request("board-approved budget vs management ambition")
        ),
        "independently_tested_case": (
            "Only items below marked Supported in Assumptions are in the tested case; "
            "untested funding / capacity legs stay out of this case."
        ),
    }


def _bridge_rows(corpus: str) -> tuple[list[dict[str, str]], str, str]:
    years, revs, ebitdas = _fy_series(corpus)
    if len(revs) < 2:
        return [], _NA, _NA

    # Latest "actual-like" = last non-E year if labeled, else index 2 (third column often FY2023)
    # Heuristic: prefer the column before first E if years contain E; else years[-2]
    actual_idx = max(0, len(years) - 2)
    for i, y in enumerate(years):
        if "E" not in y.upper() or i == 0:
            actual_idx = i
    # Prefer penultimate as plan end often last
    plan_idx = len(years) - 1
    if plan_idx == actual_idx and len(years) >= 2:
        actual_idx = len(years) - 2

    actual_y, plan_y = years[actual_idx], years[plan_idx]
    actual_rev, plan_rev = revs[actual_idx], revs[plan_idx]
    n_years = max(1, plan_idx - actual_idx)
    overall = _cagr(actual_rev, plan_rev, n_years)

    # Driver legs — only if corpus mentions them; otherwise info request / omit
    lower = corpus.lower()
    legs: list[dict[str, str]] = []
    leg_defs = [
        ("volume", ("volume", "units", "unit sales")),
        ("price", ("price", "asp", "average selling")),
        ("mix", ("mix", "software", "services mix", "margin expansion")),
        ("new_geography", ("geography", "export", "new market", "international")),
        ("acquisition", ("acquisition", "m&a", "inorganic")),
        ("cost", ("cost", "localization", "bom", "opex", "margin")),
    ]
    for driver, needles in leg_defs:
        if any(n in lower for n in needles):
            # Equal-split of overall CAGR is not invented as fact — mark as not evidenced split
            legs.append({
                "driver": driver,
                "from_metric": f"Revenue {actual_y} {_fmt_num(f'{actual_rev:g}', 'cr')}",
                "to_metric": f"Revenue {plan_y} {_fmt_num(f'{plan_rev:g}', 'cr')}",
                "implied_annual_growth": _info_request(
                    f"driver-level CAGR for {driver} (pack states overall path; leg not split)"
                ),
                "evidence": f"Driver '{driver}' mentioned in pack {_DOC_CITE}",
                "status": "untested_split",
            })
        else:
            legs.append({
                "driver": driver,
                "from_metric": "—",
                "to_metric": "—",
                "implied_annual_growth": _NA,
                "evidence": f"Omitted: '{driver}' not evidenced as a bridge leg in the data room",
                "status": "omitted",
            })

    # Add overall bridge row as computed
    legs.insert(0, {
        "driver": "overall (all legs)",
        "from_metric": f"Revenue {actual_y} {_fmt_num(f'{actual_rev:g}', 'cr')}",
        "to_metric": f"Revenue {plan_y} {_fmt_num(f'{plan_rev:g}', 'cr')}",
        "implied_annual_growth": overall,
        "evidence": f"P&L series {_DOC_CITE}",
        "status": "computed_from_accounts",
    })

    ebitda_from = (
        f"EBITDA {actual_y} {_fmt_num(f'{ebitdas[actual_idx]:g}', 'cr')}"
        if actual_idx < len(ebitdas) and ebitdas[actual_idx] == ebitdas[actual_idx]
        else _NA
    )
    ebitda_to = (
        f"EBITDA {plan_y} {_fmt_num(f'{ebitdas[plan_idx]:g}', 'cr')}"
        if plan_idx < len(ebitdas) and ebitdas[plan_idx] == ebitdas[plan_idx]
        else _NA
    )
    return legs, ebitda_from, ebitda_to


def _plan_vs_actual(corpus: str) -> list[dict[str, str]]:
    """Prior-year targets vs actuals — future targets alone do not count as delivery."""
    years, revs, _ = _fy_series(corpus)
    rows: list[dict[str, str]] = []
    # Look for explicit target/budget language
    for m in re.finditer(
        r"(FY\s*20\d{2}E?)\s[^.]{0,80}?(?:target|budget|guidance|plan)\s*"
        r"[^.\d]{0,20}?([\d,]+(?:\.\d+)?)\s*(cr|crore|%)?",
        corpus[:40_000],
        re.I,
    ):
        fy = re.sub(r"\s+", "", m.group(1).upper().replace("E", ""))
        target = _fmt_num(m.group(2), m.group(3) or "cr")
        actual = _NA
        for y, r in zip(years, revs):
            if fy in y.upper().replace("E", ""):
                actual = _fmt_num(f"{r:g}", "cr")
                break
        rows.append({
            "year": m.group(1),
            "original_target": f"{target} {_DOC_CITE}",
            "actual_outcome": f"{actual} {_DOC_CITE}" if actual != _NA else _info_request(f"actual for {m.group(1)}"),
            "variance": _COMPUTED if actual != _NA else _NA,
            "note": "Past target vs actual only — future targets are not delivery evidence",
        })
        if len(rows) >= 3:
            break

    if not rows:
        # Cannot invent PVA — register information gap for last three years
        for label in ("Year T-2", "Year T-1", "Year T"):
            rows.append({
                "year": label,
                "original_target": _info_request("original budget / guidance for the year"),
                "actual_outcome": _info_request("actual outcome for the year"),
                "variance": _NA,
                "note": "A future target is not evidence of past delivery",
            })
    return rows[:3]


def _classify_synergy_flag(text: str, *, default: str = "stand_alone") -> str:
    if _SYNERGY_CUE.search(text or ""):
        return "synergy / buyer-dependent"
    if _STANDALONE_CUE.search(text or ""):
        return "stand_alone"
    return default


def _initiatives(corpus: str, f01: dict[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pack_default = _classify_synergy_flag(corpus, default="stand_alone")
    for m in _MILESTONE.finditer(corpus[:50_000]):
        name = _clean(m.group(1), 40)
        target = f"{m.group(2)}% {m.group(3)}" if m.group(2) else m.group(3)
        window = m.group(0)
        rows.append({
            "initiative": name,
            "investment": _info_request(f"capex / opex for {name}"),
            "capacity_or_hiring": _info_request(f"capacity / hiring for {name}"),
            "dependencies": _NA,
            "owner": _info_request(f"owner for {name}"),
            "timing": _clean(m.group(3), 20),
            "milestone": f"{name} → {target} {_DOC_CITE}",
            "synergy_flag": _classify_synergy_flag(window, default=pack_default),
            "source": _DOC_CITE,
            "notes": f"{_INITIATIVE_RULE} {_SYNERGY_RULE}",
        })
        if len(rows) >= 5:
            break

    if isinstance(f01, dict):
        for driver in (f01.get("investment_drivers") or [])[:3]:
            if not isinstance(driver, str):
                continue
            label = _clean(driver.split("—")[0].split("-")[0], 60)
            if any(label.lower() in r["initiative"].lower() for r in rows):
                continue
            rows.append({
                "initiative": label,
                "investment": _info_request(f"investment for {label}"),
                "capacity_or_hiring": _info_request(f"capacity / hiring for {label}"),
                "dependencies": _NA,
                "owner": _info_request(f"owner for {label}"),
                "timing": _NA,
                "milestone": _clean(driver, 160) + f" {_DOC_CITE}",
                "synergy_flag": _classify_synergy_flag(driver, default=pack_default),
                "source": _DOC_CITE,
                "notes": f"{_INITIATIVE_RULE} {_SYNERGY_RULE}",
            })
            if len(rows) >= 6:
                break

    if not rows:
        rows.append({
            "initiative": _info_request("named strategic initiatives"),
            "investment": _NA,
            "capacity_or_hiring": _NA,
            "dependencies": _NA,
            "owner": _NA,
            "timing": _NA,
            "milestone": _NA,
            "synergy_flag": "stand_alone",
            "source": _NA,
            "notes": _INITIATIVE_RULE,
        })
    return rows[:6]


def _funding(
    corpus: str,
    *,
    cash_flow_spec: dict[str, Any] | None = None,
    capital_structure_spec: dict[str, Any] | None = None,
) -> dict[str, str]:
    cash_m = _CASH.search(corpus)
    debt_m = _DEBT.search(corpus)
    cash = (
        f"{_fmt_num(cash_m.group(1), cash_m.group(2) or 'cr')} {_DOC_CITE}"
        if cash_m
        else _info_request("available cash / liquidity")
    )
    debt = (
        f"{_fmt_num(debt_m.group(1), debt_m.group(2) or '')} {_DOC_CITE}"
        if debt_m
        else _info_request("debt capacity / facilities")
    )

    # Soft-fill from Capital Structure / Cash Flow priors when pack thin
    if str(cash).startswith("Information") and isinstance(cash_flow_spec, dict):
        metrics = cash_flow_spec.get("cash_metrics") if isinstance(
            cash_flow_spec.get("cash_metrics"), dict
        ) else {}
        for key in ("closing_cash", "available_cash", "cash", "liquidity"):
            if metrics.get(key) is not None:
                cash = f"{metrics[key]} (PRIOR: cash_flow)"
                break
    if str(debt).startswith("Information") and isinstance(capital_structure_spec, dict):
        if capital_structure_spec.get("debt_total_usd_m") is not None:
            debt = (
                f"{capital_structure_spec['debt_total_usd_m']} USD M gross debt "
                "(PRIOR: capital_structure)"
            )
        elif isinstance(capital_structure_spec.get("leverage_ratios"), dict):
            debt = "Debt capacity cues from Capital Structure prior"

    if _STANDALONE_CUE.search(corpus):
        stand = next(
            (s for s in _sentences(corpus) if _STANDALONE_CUE.search(s)),
            "Stand-alone growth funding evidenced in pack",
        )
        stand_alone = f"{_clean(stand, 160)} {_DOC_CITE}"
    else:
        stand_alone = _info_request("stand-alone funding for the plan (ex-buyer)")

    return {
        "available_cash": cash,
        "debt_capacity": debt,
        "stand_alone_growth_funding": stand_alone,
        "buyer_contributed": (
            "Keep buyer / sponsor contributions separate — not evidenced as stand-alone "
            f"funding {_DOC_CITE}"
            if re.search(r"(?i)\b(sponsor|buyer|acquisition financing|synerg)\b", corpus)
            else "No buyer-contributed funding identified in the pack; treat plan as stand-alone unless evidenced."
        ),
        "reconciliation": (
            f"Cash {cash}; debt capacity {debt}. "
            "Do not treat plan delivery as funded until investment by initiative is reconciled. "
            f"{_FUNDING_RULE}"
        ),
        "notes": f"{_FUNDING_RULE} {_SYNERGY_RULE}",
    }


def _assumptions(
    *,
    bridge: list[dict[str, str]],
    funding: dict[str, str],
    initiatives: list[dict[str, str]],
    pva: list[dict[str, str]],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    supported: list[dict[str, str]] = []
    untested: list[dict[str, str]] = []

    for leg in bridge:
        if leg.get("status") == "computed_from_accounts":
            supported.append({
                "assumption": f"Overall revenue path {leg.get('from_metric')} → {leg.get('to_metric')}",
                "basis": leg.get("evidence") or _DOC_CITE,
            })
        elif leg.get("status") == "untested_split":
            untested.append({
                "assumption": f"Driver split for {leg.get('driver')}",
                "basis": "Mentioned but not quantified as a bridge leg",
            })

    pva_ok = sum(
        1 for r in pva
        if r.get("actual_outcome") and not str(r["actual_outcome"]).startswith("Information")
        and r.get("original_target") and not str(r["original_target"]).startswith("Information")
    )
    if pva_ok >= 1:
        supported.append({
            "assumption": "At least one prior-year plan-vs-actual pair evidenced",
            "basis": _DOC_CITE,
        })
    else:
        untested.append({
            "assumption": "Three-year plan-vs-actual delivery record",
            "basis": "Original targets vs actuals not found — future targets are not delivery evidence",
        })

    for init in initiatives:
        if str(init.get("investment", "")).startswith("Information"):
            untested.append({
                "assumption": f"Funding / investment for {init.get('initiative')}",
                "basis": "Investment not stated",
            })
        if str(init.get("capacity_or_hiring", "")).startswith("Information"):
            untested.append({
                "assumption": f"Capacity / hiring for {init.get('initiative')}",
                "basis": "Capacity not stated",
            })
        if init.get("milestone") and init["milestone"] != _NA and not str(init["milestone"]).startswith("Information"):
            supported.append({
                "assumption": f"Milestone stated for {init.get('initiative')}",
                "basis": init["milestone"],
            })

    if str(funding.get("available_cash", "")).startswith("Information"):
        untested.append({
            "assumption": "Plan funded from available cash",
            "basis": "Cash not evidenced",
        })
    else:
        supported.append({
            "assumption": "Cash / liquidity figure present in pack",
            "basis": funding.get("available_cash") or _DOC_CITE,
        })

    return supported[:8], untested[:8]


def _is_filled(val: Any) -> bool:
    s = str(val or "").strip()
    return bool(s) and s != _NA and not s.startswith("Information") and not s.upper().startswith("N/A")


def _funding_untested(
    funding: dict[str, Any],
    untested: list[dict[str, str]],
) -> bool:
    if any(
        str(funding.get(k, "")).startswith("Information")
        for k in ("available_cash", "stand_alone_growth_funding")
    ):
        return True
    return any(
        "fund" in str(a.get("assumption", "")).lower()
        or "capacity" in str(a.get("assumption", "")).lower()
        for a in untested
        if isinstance(a, dict)
    )


def _sd_evidence_qa(
    *,
    three: dict[str, Any],
    bridge: list[dict[str, Any]],
    pva: list[dict[str, Any]],
    initiatives: list[dict[str, Any]],
    funding: dict[str, Any],
    untested: list[dict[str, Any]],
    cash_flow_spec: dict[str, Any] | None,
    capital_structure_spec: dict[str, Any] | None,
    strategy_read: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    cases_ok = all(
        _is_filled(three.get(k))
        for k in (
            "management_ambition",
            "board_approved_budget",
            "independently_tested_case",
        )
    )
    # Independently tested case may be a deliberate "only supported…" placeholder
    tested = str(three.get("independently_tested_case") or "")
    if "only supported" in tested.lower():
        cases_ok = (
            _is_filled(three.get("management_ambition"))
            and _is_filled(three.get("board_approved_budget"))
        )
    rows.append({
        "check": "three_case_separation",
        "status": "PASS" if cases_ok else "FAIL",
        "finding": (
            "Ambition, board budget and tested case present as separate lines"
            if cases_ok
            else _info_request("management ambition vs board budget vs tested case")
        ),
        "action": _THREE_CASE_RULE,
    })

    driver_set = {
        str(r.get("driver") or "").lower()
        for r in bridge if isinstance(r, dict)
    }
    required_drivers = {"price", "volume", "mix", "new geography", "acquisition", "cost"}
    # Accept short aliases
    aliases = {
        "geo": "new geography",
        "geography": "new geography",
        "m&a": "acquisition",
        "overall (all legs)": "overall",
    }
    normalised = {aliases.get(d, d) for d in driver_set}
    bridge_ok = bool(bridge) and (
        "overall" in normalised
        or len(required_drivers & normalised) >= 3
        or any(
            isinstance(r, dict) and r.get("status") == "computed_from_accounts"
            for r in bridge
        )
    )
    rows.append({
        "check": "bridge_drivers",
        "status": "PASS" if bridge_ok else "FAIL",
        "finding": (
            f"Bridge legs present ({len(bridge)})"
            if bridge_ok
            else _info_request("revenue/EBITDA bridge by price/volume/mix/geo/M&A/cost")
        ),
        "action": _BRIDGE_RULE,
    })

    pva_ok = sum(
        1 for r in pva
        if isinstance(r, dict)
        and _is_filled(r.get("original_target"))
        and _is_filled(r.get("actual_outcome"))
    ) >= 1
    rows.append({
        "check": "plan_vs_actual",
        "status": "PASS" if pva_ok else "FAIL",
        "finding": (
            "At least one prior-year target vs actual pair evidenced"
            if pva_ok
            else _info_request("three-year plan-vs-actual (original target vs dated actual)")
        ),
        "action": _PVA_RULE,
    })

    init_ok = any(
        isinstance(r, dict)
        and _is_filled(r.get("initiative"))
        and (
            _is_filled(r.get("milestone"))
            or _is_filled(r.get("investment"))
            or _is_filled(r.get("owner"))
        )
        for r in initiatives
    )
    synergy_flagged = all(
        isinstance(r, dict) and r.get("synergy_flag")
        for r in initiatives
        if isinstance(r, dict) and _is_filled(r.get("initiative"))
    ) if initiatives else False
    rows.append({
        "check": "initiatives_complete",
        "status": "PASS" if init_ok and synergy_flagged else "FAIL",
        "finding": (
            f"{len(initiatives)} initiative row(s); synergy/stand-alone flags present"
            if init_ok and synergy_flagged
            else _info_request(
                "initiatives with investment, capacity, owner, milestone, synergy flag"
            )
        ),
        "action": _INITIATIVE_RULE,
    })

    cash_ok = _is_filled(funding.get("available_cash"))
    debt_ok = _is_filled(funding.get("debt_capacity"))
    priors_present = bool(cash_flow_spec) or bool(capital_structure_spec)
    funding_ok = cash_ok or debt_ok or priors_present
    rows.append({
        "check": "funding_vs_cf_cs",
        "status": "PASS" if funding_ok else "FAIL",
        "finding": (
            (
                f"Cash/debt evidenced"
                + (" · CF/CS prior present" if priors_present else "")
            )
            if funding_ok
            else _info_request(
                "available cash / debt capacity (cross-check Cash Flow / Capital Structure)"
            )
        ),
        "action": _FUNDING_RULE,
    })

    stand_ok = _is_filled(funding.get("stand_alone_growth_funding")) or _is_filled(
        funding.get("buyer_contributed")
    )
    rows.append({
        "check": "synergy_vs_standalone",
        "status": "PASS" if (stand_ok and synergy_flagged) or (stand_ok and not initiatives) else "FAIL",
        "finding": (
            "Stand-alone vs synergy / buyer contribution kept separate"
            if stand_ok and (synergy_flagged or not initiatives)
            else _info_request("stand-alone vs synergy / buyer-contributed funding split")
        ),
        "action": _SYNERGY_RULE,
    })

    fund_gap = _funding_untested(funding, untested)  # type: ignore[arg-type]
    # Affirmative high-confidence claims only — strip advisory "do not assign…" sentences
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:"
        r"do\s+not\s+(?:assign|give)\s+[^.!?\n]*high[- ]confidence|"
        r"high[- ]confidence\s+withheld|"
        r"while\s+(?:material\s+)?(?:funding|capacity)[^.!?\n]*untested|"
        r"remain(?:s|ing)?\s+untested"
        r")[^.!?\n]*[.!?]?",
        " ",
        strategy_read or "",
    )
    high_conf = bool(
        re.search(
            r"(?i)\b(?:high[- ]confidence|comprehensive\s+(?:view|assessment|coverage))\b",
            scrubbed,
        )
    )
    # PASS when we correctly withhold high confidence while gaps remain,
    # or when there is no funding/capacity gap.
    no_hc_ok = (not fund_gap) or (not high_conf)
    rows.append({
        "check": "no_high_confidence_while_untested",
        "status": "PASS" if no_hc_ok else "FAIL",
        "finding": (
            "High confidence withheld while funding/capacity untested"
            if fund_gap and not high_conf
            else (
                "No material funding/capacity gap — high-confidence gate not triggered"
                if not fund_gap
                else "High-confidence language present while funding/capacity remain untested"
            )
        ),
        "action": _NO_HIGH_CONF_RULE,
    })
    return rows


def _questions_from_sd_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("sd_evidence_qa")
        if isinstance(spec.get("sd_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("three_case_separation"):
        out.append(normalize_question({
            "question": "Separate management ambition, board-approved budget and tested case",
            "required_records": "Board pack + management plan + IC bridge notes",
            "decision_effect": "Merged cases inflate underwritable growth",
            "priority": "mandatory_pre_decision",
            "owner": "strategy diligence lead",
            "timing": "before IC",
            "closure_test": "three_case_separation QA PASS",
            "interim_treatment": "LIMITED — do not merge cases",
        }))
    if _qa_fail("bridge_drivers"):
        out.append(normalize_question({
            "question": "Build revenue/EBITDA bridge by price, volume, mix, geo, M&A and cost",
            "required_records": "Plan model + latest actuals + driver schedules",
            "decision_effect": "Growth path untested without driver bridge",
            "priority": "mandatory_pre_decision",
            "owner": "financial / strategy diligence",
            "timing": "before IC",
            "closure_test": "bridge_drivers QA PASS",
            "interim_treatment": "LIMITED — withhold CAGR claims",
        }))
    if _qa_fail("plan_vs_actual"):
        out.append(normalize_question({
            "question": "Provide three-year original target vs dated actual outcomes",
            "required_records": "Prior budgets + audited / management actuals",
            "decision_effect": "Future targets are not delivery evidence",
            "priority": "signing_condition",
            "owner": "strategy diligence lead",
            "timing": "per deal timetable",
            "closure_test": "plan_vs_actual QA PASS",
            "interim_treatment": "LIMITED — treat delivery history as open",
        }))
    if _qa_fail("initiatives_complete"):
        out.append(normalize_question({
            "question": "Complete initiative rows (investment, capacity, owner, milestone, synergy flag)",
            "required_records": "Initiative tracker + capex / hiring plan",
            "decision_effect": "Uncosted initiatives corrupt funding and capacity tests",
            "priority": "mandatory_pre_decision",
            "owner": "strategy diligence lead",
            "timing": "before IC",
            "closure_test": "initiatives_complete QA PASS",
            "interim_treatment": "LIMITED — withhold initiative delivery claims",
        }))
    if _qa_fail("funding_vs_cf_cs"):
        out.append(normalize_question({
            "question": "Reconcile plan funding to Cash Flow and Capital Structure outputs",
            "required_records": "Cash Flow + Capital Structure agent specs / bank facilities",
            "decision_effect": "Unfunded plan cannot be underwritten",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "funding_vs_cf_cs QA PASS",
            "interim_treatment": "BLOCKED — do not treat plan as funded",
        }))
    if _qa_fail("synergy_vs_standalone"):
        out.append(normalize_question({
            "question": "Split stand-alone growth from synergy / buyer-contributed upside",
            "required_records": "Stand-alone model + synergy schedule",
            "decision_effect": "Buyer upside must not pad stand-alone underwriting",
            "priority": "signing_condition",
            "owner": "strategy diligence lead",
            "timing": "per deal timetable",
            "closure_test": "synergy_vs_standalone QA PASS",
            "interim_treatment": "LIMITED — strip synergy from stand-alone case",
        }))
    if _qa_fail("no_high_confidence_while_untested"):
        out.append(normalize_question({
            "question": "Remove high-confidence language until funding/capacity are tested",
            "required_records": "Closed funding + capacity diligence",
            "decision_effect": "High confidence with open funding/capacity misleads IC",
            "priority": "mandatory_pre_decision",
            "owner": "strategy diligence lead",
            "timing": "before IC",
            "closure_test": "no_high_confidence_while_untested QA PASS",
            "interim_treatment": "REWORK — strip high-confidence claims",
        }))
    return out


def _quality_reliance(
    *,
    supported: int,
    untested: int,
    funding_untested: bool,
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    quality = "PASS"
    if funding_untested or untested >= 3:
        reliance = "BLOCKED" if funding_untested and untested >= 2 else "LIMITED"
        rationale = (
            f"{supported} supported assumption(s); {untested} untested. "
            "Do not give high confidence while material funding or capacity assumptions remain untested."
        )
    elif supported >= 3:
        reliance = "READY"
        rationale = f"{supported} supported; {untested} residual untested items."
    else:
        reliance = "LIMITED"
        rationale = f"Thin evidence: {supported} supported; {untested} untested."
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale = (
            "Open strategic-direction QA FAILs cap READY → LIMITED. " + rationale
        )
    return quality, reliance, rationale


def _llm_strategic_direction_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    deal_perimeter: str | None = None,
    transaction_type: str | None = None,
    as_of_date: str | None = None,
    review_periods: str | None = None,
    decision_stage: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    try:
        system = compose_system(
            "strategic_direction",
            sector=sector,
            geography=geography,
            materiality=materiality,
            target_company=company,
            deal_perimeter=deal_perimeter,
            transaction_type=transaction_type,
            as_of_date=as_of_date,
            review_periods=review_periods,
            decision_stage=decision_stage,
        )
    except KeyError:
        return None
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "three_cases: {management_ambition, board_approved_budget, independently_tested_case},\n"
        "bridge: [{driver, from_metric, to_metric, implied_annual_growth, evidence, status}],\n"
        "ebitda_bridge_note (string),\n"
        "plan_vs_actual: [{year, original_target, actual_outcome, variance, note}],\n"
        "initiatives: [{initiative, investment, capacity_or_hiring, dependencies, owner, "
        "timing, milestone, synergy_flag (stand_alone|synergy / buyer-dependent), source}],\n"
        "funding: {available_cash, debt_capacity, stand_alone_growth_funding, "
        "buyer_contributed, reconciliation},\n"
        "supported_assumptions: [{assumption, basis}],\n"
        "untested_assumptions: [{assumption, basis}],\n"
        "sd_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "three_case_separation, bridge_drivers, plan_vs_actual, initiatives_complete, "
        "funding_vs_cf_cs, synergy_vs_standalone, no_high_confidence_while_untested,\n"
        "questions: [{question, required_records, decision_effect, priority, owner, "
        "timing, closure_test, interim_treatment}],\n"
        "strategy_read (string — which assumptions supported vs untested; "
        "no high-confidence if funding/capacity untested; no invest/pass),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Never merge ambition, approved budget, and tested case. "
        "A future target is not evidence of past delivery. "
        "Keep stand-alone growth separate from synergies. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_strategic_direction_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    f01_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
    capital_structure_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    three = _three_cases(corpus, f01_spec)
    bridge, ebitda_from, ebitda_to = _bridge_rows(corpus)
    pva = _plan_vs_actual(corpus)
    initiatives = _initiatives(corpus, f01_spec)
    funding = _funding(
        corpus,
        cash_flow_spec=cash_flow_spec,
        capital_structure_spec=capital_structure_spec,
    )
    supported, untested = _assumptions(
        bridge=bridge,
        funding=funding,
        initiatives=initiatives,
        pva=pva,
    )
    fund_gap = _funding_untested(funding, untested)

    strategy_read = (
        f"Supported assumptions: {len(supported)}. Untested: {len(untested)}. "
        "Do not assign high confidence while material funding or capacity assumptions remain untested. "
        f"EBITDA bridge note: {ebitda_from} → {ebitda_to}."
    )

    sd_qa = _sd_evidence_qa(
        three=three,
        bridge=bridge,
        pva=pva,
        initiatives=initiatives,
        funding=funding,
        untested=untested,
        cash_flow_spec=cash_flow_spec,
        capital_structure_spec=capital_structure_spec,
        strategy_read=strategy_read,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in sd_qa)

    quality, reliance, qr = _quality_reliance(
        supported=len(supported),
        untested=len(untested),
        funding_untested=fund_gap,
        qa_fail=qa_fail,
    )

    cagr_m = _CAGR.search(corpus)
    insight = (
        f"Strategic Direction for {company}: ambition, board budget and tested case are kept "
        f"separate. Bridge has {len([b for b in bridge if b.get('status') != 'omitted'])} legs; "
        f"{len(supported)} assumptions supported, {len(untested)} untested"
        + (f"; pack cites CAGR ~{cagr_m.group(1)}% {_DOC_CITE}" if cagr_m else "")
        + "."
    )

    out = {
        "insight_snapshot": insight,
        "three_cases": three,
        "bridge": bridge,
        "ebitda_bridge_note": f"{ebitda_from} → {ebitda_to}",
        "plan_vs_actual": pva,
        "initiatives": initiatives,
        "funding": funding,
        "supported_assumptions": supported,
        "untested_assumptions": untested,
        "sd_evidence_qa": sd_qa,
        "cash_flow_prior_present": bool(cash_flow_spec),
        "capital_structure_prior_present": bool(capital_structure_spec),
        "strategy_read": strategy_read,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        # Preserve F-01 keys
        "investment_drivers": (f01_spec or {}).get("investment_drivers") if isinstance(f01_spec, dict) else [],
        "must_be_true": (f01_spec or {}).get("must_be_true") if isinstance(f01_spec, dict) else [],
        "deal_breaker_risks": (f01_spec or {}).get("deal_breaker_risks") if isinstance(f01_spec, dict) else [],
        "attractiveness_score": (f01_spec or {}).get("attractiveness_score") if isinstance(f01_spec, dict) else None,
        "thesis_framework": (f01_spec or {}).get("thesis_framework") if isinstance(f01_spec, dict) else None,
    }
    out["questions"] = _questions_from_sd_gaps(out)
    return out


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    f01_spec: dict[str, Any] | None,
    cash_flow_spec: dict[str, Any] | None = None,
    capital_structure_spec: dict[str, Any] | None = None,
    corpus: str = "",
) -> dict[str, Any]:
    heur = _heuristic_strategic_direction_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        f01_spec=f01_spec,
        cash_flow_spec=cash_flow_spec,
        capital_structure_spec=capital_structure_spec,
    )
    for key in (
        "bridge", "plan_vs_actual", "initiatives",
        "supported_assumptions", "untested_assumptions",
    ):
        if not isinstance(llm.get(key), list) or not llm.get(key):
            llm[key] = list(heur.get(key) or [])
    if not isinstance(llm.get("three_cases"), dict) or not llm.get("three_cases"):
        llm["three_cases"] = heur.get("three_cases") or {
            "management_ambition": _NA,
            "board_approved_budget": _NA,
            "independently_tested_case": _NA,
        }
    if not isinstance(llm.get("funding"), dict) or not llm.get("funding"):
        llm["funding"] = heur.get("funding") or {
            "available_cash": _info_request("available cash"),
            "debt_capacity": _info_request("debt capacity"),
            "stand_alone_growth_funding": _info_request("stand-alone funding"),
            "buyer_contributed": "Keep buyer contributions separate.",
            "reconciliation": _NA,
        }

    # Ensure synergy_flag on initiatives
    for row in llm.get("initiatives") or []:
        if isinstance(row, dict) and not row.get("synergy_flag"):
            row["synergy_flag"] = _classify_synergy_flag(
                " ".join(str(row.get(k) or "") for k in (
                    "initiative", "milestone", "dependencies", "notes",
                )),
                default="stand_alone",
            )

    untested = [
        a for a in (llm.get("untested_assumptions") or [])
        if isinstance(a, dict)
    ]
    fund_gap = _funding_untested(llm.get("funding") or {}, untested)
    read = str(llm.get("strategy_read") or "")
    if fund_gap and re.search(r"high[- ]confidence|comprehensive", read, re.I):
        llm["strategy_read"] = (
            f"{_clean(read, 400)} — high confidence withheld while funding/capacity remain untested."
        )
    if not llm.get("strategy_read"):
        llm["strategy_read"] = heur.get("strategy_read")

    sd_qa = _sd_evidence_qa(
        three=llm.get("three_cases") or {},
        bridge=llm.get("bridge") or [],
        pva=llm.get("plan_vs_actual") or [],
        initiatives=llm.get("initiatives") or [],
        funding=llm.get("funding") or {},
        untested=untested,
        cash_flow_spec=cash_flow_spec,
        capital_structure_spec=capital_structure_spec,
        strategy_read=str(llm.get("strategy_read") or ""),
    )
    llm["sd_evidence_qa"] = sd_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in sd_qa)
    llm["cash_flow_prior_present"] = bool(cash_flow_spec)
    llm["capital_structure_prior_present"] = bool(capital_structure_spec)

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            supported=len(llm.get("supported_assumptions") or []),
            untested=len(untested),
            funding_untested=fund_gap,
            qa_fail=qa_fail,
        )
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        llm.setdefault("quality_reliance_rationale", rationale)
    else:
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        if (fund_gap or qa_fail) and rv == "READY":
            llm["reliance_verdict"] = "LIMITED"
            llm["quality_reliance_rationale"] = (
                (llm.get("quality_reliance_rationale") or "")
                + " Reliance capped at LIMITED while funding/capacity assumptions "
                "or strategic-direction QA FAILs remain open."
            ).strip()

    if not isinstance(llm.get("questions"), list) or not llm.get("questions"):
        llm["questions"] = _questions_from_sd_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_sd_gaps(llm)

    for dead in ("recommendation", "confidence", "key_conditions", "investment_verdict"):
        llm.pop(dead, None)

    # Fix off-by-one CAGR year spans (2026→2030 is 4 years, not 5)
    for row in llm.get("bridge") or []:
        if not isinstance(row, dict):
            continue
        span = _year_span_from_labels(
            str(row.get("from_metric") or ""),
            str(row.get("to_metric") or ""),
        )
        for key in ("implied_annual_growth", "from_metric", "to_metric", "evidence"):
            if isinstance(row.get(key), str):
                row[key] = _fix_cagr_year_span_text(row[key], span=span)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    if isinstance(f01_spec, dict):
        llm.setdefault("investment_drivers", f01_spec.get("investment_drivers") or [])
        llm.setdefault("must_be_true", f01_spec.get("must_be_true") or [])
        llm.setdefault("deal_breaker_risks", f01_spec.get("deal_breaker_risks") or [])
        llm.setdefault("attractiveness_score", f01_spec.get("attractiveness_score"))
        llm.setdefault("thesis_framework", f01_spec.get("thesis_framework"))
    return llm


def build_strategic_direction_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    f01_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
    capital_structure_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    if corpus is None or sources is None:
        corpus, sources = gather_strategic_direction_corpus(deal, idx)
    if not corpus:
        bits: list[str] = []
        sources = list(sources or [])
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                sources.append(str(doc.get("filename") or "source"))
        corpus = "\n".join(bits)

    vars_ = prompt_vars_from_deal(deal)
    heur = _heuristic_strategic_direction_spec(
        company=target,
        corpus=corpus or "",
        sources=sources or [],
        f01_spec=f01_spec,
        cash_flow_spec=cash_flow_spec,
        capital_structure_spec=capital_structure_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm = _llm_strategic_direction_spec(
        company=target,
        corpus=corpus or "",
        sources=sources or [],
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
        deal_perimeter=vars_.get("deal_perimeter"),
        transaction_type=vars_.get("transaction_type"),
        as_of_date=vars_.get("as_of_date"),
        review_periods=vars_.get("review_periods"),
        decision_stage=vars_.get("decision_stage"),
    )
    if llm:
        out = _normalise_llm_spec(
            llm,
            sources=sources or [],
            f01_spec=f01_spec,
            cash_flow_spec=cash_flow_spec,
            capital_structure_spec=capital_structure_spec,
            corpus=corpus or "",
        )
        out["deal_slots"] = {k: v for k, v in vars_.items() if v}
        return out

    return heur


def render_strategic_direction_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    three = spec.get("three_cases") if isinstance(spec.get("three_cases"), dict) else {}
    bridge = spec.get("bridge") if isinstance(spec.get("bridge"), list) else []
    pva = spec.get("plan_vs_actual") if isinstance(spec.get("plan_vs_actual"), list) else []
    initiatives = spec.get("initiatives") if isinstance(spec.get("initiatives"), list) else []
    funding = spec.get("funding") if isinstance(spec.get("funding"), dict) else {}
    supported = spec.get("supported_assumptions") if isinstance(spec.get("supported_assumptions"), list) else []
    untested = spec.get("untested_assumptions") if isinstance(spec.get("untested_assumptions"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Three Cases — Do Not Merge\n\n")
    parts.append(
        "Keep **management ambition**, the **board-approved budget**, and the "
        "**independently tested case** on separate lines.\n\n"
    )
    parts.append(_table(
        ["Case", "Content"],
        [
            ["Management ambition", _clean(three.get("management_ambition"), 320)],
            ["Board-approved budget", _clean(three.get("board_approved_budget"), 320)],
            ["Independently tested case", _clean(three.get("independently_tested_case"), 320)],
        ],
    ))
    parts.append("---\n\n")

    parts.append("## 2. Bridge — Latest Actual to Plan Final Year\n\n")
    parts.append(
        "Drivers: price, volume, mix, new geography, acquisition, cost. "
        "State the annual growth rate each leg implies.\n\n"
    )
    if bridge:
        parts.append(_table(
            ["Driver", "From", "To", "Implied Annual Growth", "Evidence", "Status"],
            [
                [
                    _clean(r.get("driver"), 40),
                    _clean(r.get("from_metric"), 60),
                    _clean(r.get("to_metric"), 60),
                    _clean(r.get("implied_annual_growth"), 80),
                    _clean(r.get("evidence"), 100),
                    _clean(r.get("status"), 30),
                ]
                for r in bridge if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('revenue / EBITDA bridge by driver')}\n\n")
    if spec.get("ebitda_bridge_note"):
        parts.append(f"**EBITDA:** {_clean(spec.get('ebitda_bridge_note'), 200)}\n\n")
    parts.append("---\n\n")

    parts.append("## 3. Plan vs Actual — Delivery History\n\n")
    parts.append(
        "Last three years: original target against actual outcome. "
        "A future target is **not** evidence of past delivery.\n\n"
    )
    if pva:
        parts.append(_table(
            ["Year", "Original Target", "Actual Outcome", "Variance", "Note"],
            [
                [
                    _clean(r.get("year"), 20),
                    _clean(r.get("original_target"), 80),
                    _clean(r.get("actual_outcome"), 80),
                    _clean(r.get("variance"), 40),
                    _clean(r.get("note"), 100),
                ]
                for r in pva if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('three-year plan-vs-actual record')}\n\n")
    parts.append("---\n\n")

    parts.append("## 4. Initiatives\n\n")
    parts.append(f"{_INITIATIVE_RULE} {_SYNERGY_RULE}\n\n")
    if initiatives:
        parts.append(_table(
            [
                "Initiative", "Investment", "Capacity / Hiring", "Dependencies",
                "Owner", "Timing", "Milestone", "Stand-alone / Synergy",
            ],
            [
                [
                    _clean(r.get("initiative"), 60),
                    _clean(r.get("investment"), 60),
                    _clean(r.get("capacity_or_hiring"), 60),
                    _clean(r.get("dependencies"), 60),
                    _clean(r.get("owner"), 40),
                    _clean(r.get("timing"), 30),
                    _clean(r.get("milestone"), 100),
                    _clean(r.get("synergy_flag") or "stand_alone", 40),
                ]
                for r in initiatives if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"{_info_request('initiatives with investment, capacity, owner, timing, milestone, synergy flag')}\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 5. Funding Reconciliation\n\n")
    parts.append(f"{_FUNDING_RULE}\n\n")
    parts.append(
        "Stand-alone growth funding stays separate from anything a buyer would contribute.\n\n"
    )
    parts.append(f"- **Available cash:** {_clean(funding.get('available_cash'), 120)}\n")
    parts.append(f"- **Debt capacity:** {_clean(funding.get('debt_capacity'), 120)}\n")
    parts.append(
        f"- **Stand-alone growth funding:** "
        f"{_clean(funding.get('stand_alone_growth_funding'), 160)}\n"
    )
    parts.append(f"- **Buyer-contributed:** {_clean(funding.get('buyer_contributed'), 160)}\n")
    parts.append(f"- **Reconciliation:** {_clean(funding.get('reconciliation'), 280)}\n")
    if spec.get("cash_flow_prior_present") or spec.get("capital_structure_prior_present"):
        parts.append(
            f"- **Priors:** Cash Flow="
            f"{'yes' if spec.get('cash_flow_prior_present') else 'no'}; "
            f"Capital Structure="
            f"{'yes' if spec.get('capital_structure_prior_present') else 'no'}\n"
        )
    parts.append("\n---\n\n")

    parts.append("## 6. Assumptions — Supported vs Untested\n\n")
    parts.append("### Supported\n\n")
    if supported:
        parts.append(_table(
            ["Assumption", "Basis"],
            [
                [_clean(r.get("assumption"), 160), _clean(r.get("basis"), 160)]
                for r in supported if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None registered from the opened packs.\n\n")
    parts.append("### Untested\n\n")
    if untested:
        parts.append(_table(
            ["Assumption", "Basis"],
            [
                [_clean(r.get("assumption"), 160), _clean(r.get("basis"), 160)]
                for r in untested if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None registered.\n\n")
    if spec.get("strategy_read"):
        parts.append(f"**Read:** {_clean(spec.get('strategy_read'), 520)}\n\n")
    parts.append(
        "*Do not give a high-confidence verdict while material funding or capacity "
        "assumptions remain untested. This section does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    # 7
    sd_qa = (
        spec.get("sd_evidence_qa")
        if isinstance(spec.get("sd_evidence_qa"), list) else []
    )
    parts.append("## 7. Strategic Direction Evidence QA\n\n")
    parts.append(
        "QA enforces three-case separation, bridge drivers, plan-vs-actual, "
        "initiatives (incl. synergy flag), funding vs Cash Flow / Capital Structure, "
        "and no high-confidence while funding/capacity remain untested.\n\n"
    )
    parts.append(
        _table(
            ["Check", "Status", "Finding", "Action"],
            [
                [
                    _clean(r.get("check"), 60),
                    _clean(r.get("status"), 20),
                    _clean(r.get("finding"), 220),
                    _clean(r.get("action"), 180),
                ]
                for r in sd_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('strategic direction evidence QA rows')}\n\n"
    )
    parts.append("---\n\n")

    # 8
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 8. Questions and Inputs Required\n\n")
    if questions:
        for row in questions[:12]:
            if not isinstance(row, dict):
                continue
            parts.append(
                f"- **{_clean(row.get('question'), 200)}** — "
                f"records: {_clean(row.get('required_records'), 120)}; "
                f"effect: {_clean(row.get('decision_effect'), 120)}; "
                f"priority: {_clean(row.get('priority'), 40)}; "
                f"owner: {_clean(row.get('owner'), 40)}; "
                f"timing: {_clean(row.get('timing'), 40)}; "
                f"closure: {_clean(row.get('closure_test'), 120)}; "
                f"interim: {_clean(row.get('interim_treatment'), 120)}\n"
            )
        parts.append("\n")
    else:
        parts.append(
            "None are missing — material strategic-direction gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    # 9
    parts.append("## 9. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "PASS"
    rv = spec.get("reliance_verdict") or "LIMITED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(qv, 30)],
            ["Reliance Verdict", _clean(rv, 30)],
            ["Rationale", _clean(rationale, 460)],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(qv, 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — "
        f"can a decision rest on this strategy test?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open strategic-direction QA FAILs cap READY → LIMITED. "
        "This agent does not issue an invest or pass recommendation. "
        f"{_NO_HIGH_CONF_RULE}*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    for i, src in enumerate(srcs[:40], start=1):
        if isinstance(src, str) and src.strip():
            parts.append(f"**[{i}]** {src.strip()}\n")
        elif isinstance(src, dict):
            title_s = src.get("title") or src.get("name") or src.get("file") or "Source"
            parts.append(f"**[{i}]** {_clean(title_s, 120)}\n")
    parts.append("\n")
    return "".join(parts)
