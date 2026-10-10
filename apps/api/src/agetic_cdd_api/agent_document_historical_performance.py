"""Compose DiligenceIQ Historical Performance — shared financial facts (prompt book).

Establishes revenue, margin and earnings by period from accounting records
rather than the seller's summary. Labels periods actual / LTM / forecast.
Computes growth and margin; names the trend in the first line. Compares
accounts vs CIM. Shows seasonal shape where evidenced. Flags comparability
distortions. Dual-writes legacy Adjusted EBITDA Bridge fields
(pl_lines / performance_metrics / bridge_notes).

No invest/pass. No company allowlists. These figures are the shared basis
for every other agent — publish once with locations.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_HEADER_LINE = re.compile(r"(?m)^\s*#{1,6}\s*\S+\s*$")

_DOCUMENT_TITLE = "Adjusted EBITDA Bridge"
_DD_CODE = "DD-23"

_RECORD_RULE = (
    "Revenue, cost of sales, gross margin, operating costs and EBITDA are taken "
    "from the accounting records for each period and the last twelve months. "
    "Each period is labelled actual, last twelve months or forecast."
)
_TREND_RULE = (
    "Growth and margin are calculated for each period. Direction is stated "
    "plainly in the first line (e.g. if earnings peaked two years ago)."
)
_CIM_RULE = (
    "Accounts are compared with the CIM or management summary. Where they "
    "differ, both are shown with the reason (period, perimeter, add-back, "
    "definition) and the chosen basis."
)
_SEASON_RULE = (
    "Monthly or quarterly shape is shown where the business is seasonal, "
    "with current year-to-date against the same period last year."
)
_DISTORT_RULE = (
    "Comparability distortions are identified: acquisitions, disposals, "
    "accounting changes, one-off contracts, or a change in the customer mix."
)
_SHARED_RULE = (
    "These figures are the shared basis for every other agent. Publish them "
    "as facts with their locations; do not restate them differently elsewhere."
)

_PNL_ITEMS = (
    "Revenue|Cost of Goods Sold|Gross Profit|Gross Margin\\s*\\(%\\)|"
    "R&D Expenses|Sales & Marketing|G&A Expenses|EBITDA|EBITDA Margin\\s*\\(%\\)|"
    "Depreciation & Amortisation|EBIT|Finance Costs|Net Loss\\s*\\(PAT\\)|"
    "Operating Expenses|Operating Costs|Cost of Sales"
)
_PNL_LINE_RE = re.compile(
    rf"(?i)({_PNL_ITEMS})\s+(.+?)(?=\s+(?:{_PNL_ITEMS})\s|\Z)"
)
_CIM_REV_RE = re.compile(
    r"(?i)Revenue\s*\(INR\s*Cr\)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)"
)
_ACCOUNTS_HEADER_RE = re.compile(
    r"(?i)Profit\s*&\s*Loss\s*Summary|accounting\s+records|audited\s+(?:financials|accounts)|"
    r"Financial\s+Due\s+Diligence"
)
_CIM_CUE_RE = re.compile(
    r"(?i)\b(CIM|Confidential\s+Information\s+Memorandum|management\s+summary|"
    r"Commercial\s+Due\s+Diligence|seller(?:'s)?\s+summary|teaser)\b"
)
_SEASON_CUE = re.compile(
    r"(?i)\b(seasonal|seasonality|monthly\s+run\s+rate|Q[1-4]\s*FY|quarter(?:ly)?|"
    r"YTD|year[- ]to[- ]date|same\s+period\s+last\s+year|SPLY|H[12]\s*FY)\b"
)
_DISTORT_CUE = re.compile(
    r"(?i)\b(acquisition|acquired|disposal|divest|accounting\s+change|"
    r"change\s+in\s+accounting|one[- ]off|non[- ]recurring|add[- ]back|"
    r"customer\s+mix|perimeter|pro\s*forma|restatement|reclassif)\b"
)
_INVEST_RE = re.compile(
    r"(?i)\b(invest|pass|buy|sell|recommendation|verdict|IC\s+decision)\b"
)


def _info_request(what: str) -> str:
    return f"Information request: {what}"


def _soften_invest(text: str) -> str:
    raw = str(text or "")
    raw = re.sub(
        r"(?i)\b(recommend(?:ation)?\s+(?:to\s+)?(?:invest|pass)|invest\s*/\s*pass|"
        r"investment\s+verdict|buy\s+recommendation)\b",
        "diligence finding",
        raw,
    )
    # Strip trailing IC-style "— invest/pass" without touching Quality PASS / Reliance.
    raw = re.sub(r"(?i)\s*[—\-]\s*\b(invest|pass)\b\.?\s*$", "", raw)
    raw = re.sub(r"(?i)(?<!quality\s)\b(invest)\b", "diligence finding", raw)
    return _clean(raw, 600)


def _is_filled(val: object) -> bool:
    text = str(val or "").strip()
    return bool(text) and text != _NA and not text.startswith("Information request")


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    text = _HEADER_LINE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_num_token(token: str) -> float | None:
    t = (token or "").strip()
    if not t or t.upper() in {"N/M", "N/A", "—", "-", "–"}:
        return None
    neg = t.startswith("(") and t.endswith(")")
    num = re.sub(r"[^\d.]", "", t.replace("%", ""))
    if not num:
        return None
    try:
        val = float(num)
    except ValueError:
        return None
    return -val if neg else val


def _parse_pnl_values(raw: str) -> list[float | None]:
    tokens = re.findall(r"N/M|\(?[-\d,.]+%?\)?", raw or "", flags=re.I)
    out: list[float | None] = []
    for token in tokens:
        if token.upper() == "N/M":
            out.append(None)
            continue
        val = _parse_num_token(token)
        if val is not None:
            out.append(val)
    return out


def _period_label(period: str) -> str:
    p = re.sub(r"\s+", "", (period or "").upper())
    if p in {"LTM", "TTM"}:
        return "last twelve months"
    if p.endswith("P") or "PLAN" in p:
        return "forecast"
    if p.endswith("E") or "FORECAST" in p:
        return "forecast"
    # Bare calendar years 2026+ are plan unless explicitly historical
    m = re.search(r"(20\d{2})", p)
    if m and int(m.group(1)) >= 2026:
        return "forecast"
    if p.startswith("YTD"):
        return "year to date"
    return "actual"


def _detect_period_headers(text: str) -> list[str]:
    m = re.search(
        r"(?i)(?:Line\s+Item|Profit\s*&\s*Loss)[^\n]{0,80}?"
        r"((?:FY\s*20\d{2}[EA]?\s*){3,6})",
        text or "",
    )
    if m:
        found = re.findall(r"(?i)FY\s*20\d{2}[EA]?", m.group(1))
        return [re.sub(r"\s+", "", f.upper().replace("FY ", "FY")) for f in found]
    return ["FY2021", "FY2022", "FY2023", "FY2024E", "FY2025E"]


def gather_historical_performance_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "deal_strategy": 1,
        "customer": 2,
        "operations": 3,
        "market_competition": 4,
        "company_management": 5,
        "legal_esg": 6,
    }
    needles = (
        "financial", "p&l", "pnl", "historical", "income", "ebitda",
        "profit", "revenue", "valuation", "cim", "commercial", "teaser",
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple[int, int, str]:
        name = str(d.get("filename") or "").lower()
        needle_hit = 0 if any(n in name for n in needles) else 1
        return (
            prefer.get(str(d.get("cdl_category") or ""), 9),
            needle_hit,
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        loaded: dict[str, Any] = {}
        try:
            raw_loaded = load_library_document(deal, filename)
            if isinstance(raw_loaded, dict):
                loaded = raw_loaded
        except Exception:
            loaded = {}
        text = ""
        body = loaded.get("text")
        if isinstance(body, str) and body.strip():
            text = body
        elif body is not None:
            text = str(body)
        if not text.strip():
            excerpt = doc.get("excerpt")
            if isinstance(excerpt, str) and excerpt.strip():
                text = excerpt
            elif excerpt is not None:
                text = str(excerpt)
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _extract_period_facts(corpus: str) -> list[dict[str, Any]]:
    from agetic_cdd_api.services_accounts_extract import (
        detect_unit_from_corpus,
        is_cim_crosswalk_context,
        looks_like_cim_page_list,
    )

    text = _prose(corpus)
    headers = _detect_period_headers(text)
    # Only trust default FY headers when a real Line-Item FY block was found
    headers_from_block = headers != ["FY2021", "FY2022", "FY2023", "FY2024E", "FY2025E"] or bool(
        re.search(
            r"(?i)(?:Line\s+Item|Profit\s*&\s*Loss)[^\n]{0,80}?(?:FY\s*20\d{2})",
            text or "",
        )
    )
    unit_default, _ = detect_unit_from_corpus(text)
    rows: list[dict[str, Any]] = []
    wanted = {
        "revenue", "cost of goods sold", "cost of sales", "gross profit",
        "gross margin (%)", "r&d expenses", "sales & marketing", "g&a expenses",
        "ebitda", "ebitda margin (%)", "operating expenses", "operating costs",
    }
    seen: set[str] = set()
    for match in _PNL_LINE_RE.finditer(text):
        item = re.sub(r"\s+", " ", match.group(1)).strip()
        key = item.lower()
        if key not in wanted or key in seen:
            continue
        if is_cim_crosswalk_context(text, match.start()):
            continue
        values = _parse_pnl_values(match.group(2))
        if looks_like_cim_page_list(values):
            continue
        if not headers_from_block and looks_like_cim_page_list(values):
            continue
        seen.add(key)
        unit = "%" if "margin" in key else unit_default
        for i, hdr in enumerate(headers):
            val = values[i] if i < len(values) else None
            if val is None and i >= len(values):
                continue
            # Drop year-as-value artefacts (e.g. Revenue FY2021 = 2023.0)
            if (
                isinstance(val, (int, float))
                and float(val).is_integer()
                and 2000 <= val <= 2100
                and "margin" not in key
            ):
                continue
            rows.append({
                "line_item": item,
                "period": hdr,
                "period_type": _period_label(hdr),
                "value": val,
                "unit": unit,
                "basis": "accounting_records",
                "source": _DOC_CITE,
                "location": f"P&L Summary · {hdr}",
                "notes": _RECORD_RULE,
            })
        if len(seen) >= 10:
            break
    return rows


def _pivot_pl_lines(period_facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_item: dict[str, dict[str, Any]] = {}
    for f in period_facts:
        if not isinstance(f, dict):
            continue
        item = str(f.get("line_item") or "")
        if not item:
            continue
        row = by_item.setdefault(
            item,
            {"line_item": item, "unit": f.get("unit") or "USD M"},
        )
        period = str(f.get("period") or "").upper().replace(" ", "")
        val = f.get("value")
        if val is None:
            continue
        if "2024" in period:
            row["fy2024_value"] = val
        elif "2023" in period:
            row["fy2023_value"] = val
        elif "2022" in period:
            row["fy2022_value"] = val
        elif "2021" in period:
            row["fy2021_value"] = val
        elif "2025" in period:
            row["fy2025_value"] = val
    return list(by_item.values())[:12]


def _series_for(period_facts: list[dict], line: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for f in period_facts:
        if not isinstance(f, dict):
            continue
        if str(f.get("line_item") or "").lower() != line.lower():
            continue
        if f.get("value") is None:
            continue
        if str(f.get("unit") or "") == "%":
            continue
        out.append((str(f.get("period") or ""), float(f["value"])))
    return out


def _extract_growth_margins(
    period_facts: list[dict[str, Any]],
) -> tuple[str, list[dict[str, str]]]:
    rev = _series_for(period_facts, "Revenue")
    ebitda = _series_for(period_facts, "EBITDA")
    gm_rows = [
        f for f in period_facts
        if isinstance(f, dict)
        and "gross margin" in str(f.get("line_item") or "").lower()
        and f.get("value") is not None
    ]
    em_rows = [
        f for f in period_facts
        if isinstance(f, dict)
        and "ebitda margin" in str(f.get("line_item") or "").lower()
        and f.get("value") is not None
    ]

    growth_rows: list[dict[str, str]] = []
    for i in range(1, len(rev)):
        prev_p, prev_v = rev[i - 1]
        cur_p, cur_v = rev[i]
        if prev_v == 0:
            continue
        rate = ((cur_v - prev_v) / abs(prev_v)) * 100
        growth_rows.append({
            "metric": "Revenue YoY growth",
            "period": cur_p,
            "value": f"{rate:+.0f}%",
            "prior_period": prev_p,
            "source": _COMPUTED,
            "notes": _TREND_RULE,
        })

    for f in gm_rows:
        growth_rows.append({
            "metric": "Gross margin",
            "period": str(f.get("period") or ""),
            "value": f"{float(f['value']):g}%",
            "prior_period": "",
            "source": _DOC_CITE,
            "notes": _TREND_RULE,
        })
    for f in em_rows:
        growth_rows.append({
            "metric": "EBITDA margin",
            "period": str(f.get("period") or ""),
            "value": f"{float(f['value']):g}%",
            "prior_period": "",
            "source": _DOC_CITE,
            "notes": _TREND_RULE,
        })

    headline = _info_request("earnings trend from accounting records")
    unit_label = "USD M"
    for f in period_facts:
        if isinstance(f, dict) and f.get("unit") and str(f.get("unit")) != "%":
            unit_label = str(f["unit"])
            break

    def _fmt_amt(v: float) -> str:
        return f"{unit_label} {v:g}"

    if ebitda:
        # Exclude pure outer-year forecasts (e.g. FY2025E / FY2030P) from the direction call;
        # keep recent actuals and near-term deal years.
        def _is_outer_forecast(period: str) -> bool:
            p = str(period).upper().replace(" ", "")
            if p.endswith("P"):
                return True
            return p.endswith("E") and not any(
                y in p for y in ("2025", "2024", "2023", "2022", "2021")
            )

        use = [(p, v) for p, v in ebitda if not _is_outer_forecast(p)] or ebitda
        peak_p, peak_v = max(use, key=lambda x: x[1])
        trough_p, trough_v = min(use, key=lambda x: x[1])
        last_p, last_v = use[-1]
        if trough_v < 0 and last_v > trough_v and last_v >= 0:
            headline = (
                f"EBITDA trough was {trough_p} ({_fmt_amt(trough_v)}); "
                f"returned to profit by {last_p} at {_fmt_amt(last_v)}."
            )
        elif trough_p != last_p and last_v > trough_v and trough_v < 0:
            headline = (
                f"EBITDA trough was {trough_p} ({_fmt_amt(trough_v)}); "
                f"losses narrowed by {last_p} to {_fmt_amt(last_v)}."
            )
        elif peak_p != last_p and peak_v > last_v:
            headline = (
                f"Earnings peaked in {peak_p} (EBITDA {_fmt_amt(peak_v)}) "
                f"and have not recovered; latest {last_p} EBITDA {_fmt_amt(last_v)}."
            )
        else:
            headline = (
                f"Latest EBITDA {last_p}: {_fmt_amt(last_v)} "
                f"(series range {trough_v:g} to {peak_v:g})."
            )
        # Pair revenue growth with the same last period when possible
        rev_use = [(p, v) for p, v in rev if not _is_outer_forecast(p)] or rev
        if rev_use and len(rev_use) >= 2:
            _, prev_v = rev_use[-2]
            cur_p, cur_v = rev_use[-1]
            if prev_v:
                g = ((cur_v - prev_v) / abs(prev_v)) * 100
                headline += f" Revenue {cur_p} {g:+.0f}% YoY."
        headline = _clean(headline, 320) + f" {_COMPUTED}"

    return headline, growth_rows[:16]


def _extract_cim_vs_accounts(
    corpus: str,
    period_facts: list[dict[str, Any]],
) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    accounts_rev = {
        str(f.get("period") or "").upper().replace(" ", ""): f.get("value")
        for f in period_facts
        if isinstance(f, dict)
        and str(f.get("line_item") or "").lower() == "revenue"
        and f.get("value") is not None
    }

    # Collect every Revenue (INR Cr) a/b/c triad; prefer ones that *differ* from accounts
    # (seller/commercial summaries) over restatements of the same P&L.
    cim_map: dict[str, float] = {}
    for m in _CIM_REV_RE.finditer(text):
        vals = [float(m.group(i).replace(",", "")) for i in (1, 2, 3)]
        candidate = {"FY2022": vals[0], "FY2023": vals[1], "FY2024E": vals[2]}
        differs = False
        for period, cim_val in candidate.items():
            acct = accounts_rev.get(period)
            if acct is None:
                acct = accounts_rev.get(period.replace("E", ""))
            if acct is not None and abs(float(acct) - cim_val) >= 0.5:
                differs = True
                break
        # Prefer commercial/CIM neighbourhood when present
        window = text[max(0, m.start() - 120): m.end() + 80]
        commercialish = bool(
            re.search(
                r"(?i)commercial|sales\s+metric|CIM|management\s+summary|teaser|"
                r"units\s+sold|market\s+share",
                window,
            )
        )
        if differs and (commercialish or not cim_map):
            cim_map = candidate
            if commercialish and differs:
                break
        elif not cim_map and not differs:
            cim_map = candidate  # fallback align-only if nothing else

    for period, cim_val in cim_map.items():
        acct = accounts_rev.get(period)
        if acct is None:
            acct = accounts_rev.get(period.replace("E", ""))
        if acct is None:
            continue
        if abs(float(acct) - cim_val) < 0.5:
            rows.append({
                "metric": "Revenue",
                "period": period,
                "accounts_value": f"INR {float(acct):g} Cr",
                "cim_value": f"INR {cim_val:g} Cr",
                "difference": "Aligned",
                "reason": "Same figure on both bases",
                "chosen_basis": "accounting_records",
                "why": "Accounts and CIM agree.",
                "source": _DOC_CITE,
                "notes": _CIM_RULE,
            })
        else:
            reason = (
                "Likely perimeter or definition difference "
                "(accounts vs commercial/CIM pack)"
            )
            rows.append({
                "metric": "Revenue",
                "period": period,
                "accounts_value": f"INR {float(acct):g} Cr",
                "cim_value": f"INR {cim_val:g} Cr",
                "difference": f"INR {float(acct) - cim_val:+.0f} Cr",
                "reason": reason,
                "chosen_basis": "accounting_records",
                "why": (
                    "Shared financial basis must come from accounting records, "
                    "not the seller summary."
                ),
                "source": _DOC_CITE,
                "notes": _CIM_RULE + " " + _SHARED_RULE,
            })

    if not rows:
        has_cim = bool(_CIM_CUE_RE.search(text))
        has_accounts = bool(_ACCOUNTS_HEADER_RE.search(text)) or bool(accounts_rev)
        if has_accounts and not cim_map:
            sample = next(iter(accounts_rev.values())) if accounts_rev else None
            rows.append({
                "metric": "Revenue",
                "period": _NA,
                "accounts_value": (
                    f"INR {float(sample):g} Cr (sample)" if sample is not None else _NA
                ),
                "cim_value": _NA,
                "difference": _info_request("CIM / management summary P&L for comparison"),
                "reason": "CIM figures not located in opened packs",
                "chosen_basis": "accounting_records",
                "why": "Only accounting-record figures are available.",
                "source": _DOC_CITE if accounts_rev else _NA,
                "notes": _CIM_RULE,
            })
        elif not has_accounts:
            rows.append({
                "metric": "Revenue",
                "period": _NA,
                "accounts_value": _info_request("audited / management accounts P&L"),
                "cim_value": _NA,
                "difference": _NA,
                "reason": "Accounting records not opened",
                "chosen_basis": "pending",
                "why": _info_request("which basis to use once both packs are opened"),
                "source": _NA,
                "notes": _CIM_RULE,
            })
    return rows[:8]


def _extract_seasonality(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    sents = _sentences(text)
    rows: list[dict[str, str]] = []
    for s in sents:
        if not _SEASON_CUE.search(s):
            continue
        if not re.search(r"\d", s):
            continue
        ytd = bool(re.search(r"(?i)YTD|year[- ]to[- ]date|same\s+period", s))
        rows.append({
            "shape": _clean(s, 180),
            "period_grain": (
                "monthly" if re.search(r"(?i)monthly", s)
                else "quarterly" if re.search(r"(?i)Q[1-4]|quarter", s)
                else "intra-year"
            ),
            "ytd_vs_prior": _clean(s, 140) if ytd else _info_request(
                "current YTD vs same period last year"
            ),
            "source": _DOC_CITE,
            "notes": _SEASON_RULE,
        })
        if len(rows) >= 5:
            break
    if not rows:
        rows.append({
            "shape": _info_request("monthly or quarterly P&L where seasonality matters"),
            "period_grain": _NA,
            "ytd_vs_prior": _info_request("current YTD vs same period last year"),
            "source": _NA,
            "notes": _SEASON_RULE,
        })
    return rows


def _extract_distortions(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    sents = _sentences(text)
    rows: list[dict[str, str]] = []
    for s in sents:
        if not _DISTORT_CUE.search(s):
            continue
        kind = "other"
        low = s.lower()
        if "acquisition" in low or "acquired" in low:
            kind = "acquisition"
        elif "disposal" in low or "divest" in low:
            kind = "disposal"
        elif "accounting" in low or "restatement" in low or "reclassif" in low:
            kind = "accounting_change"
        elif "one-off" in low or "one off" in low or "non-recurring" in low or "add-back" in low:
            kind = "one_off"
        elif "mix" in low:
            kind = "customer_mix"
        elif "perimeter" in low or "pro forma" in low or "proforma" in low:
            kind = "perimeter"
        rows.append({
            "distortion": _clean(s, 180),
            "kind": kind,
            "impact_on_comparability": _clean(s, 120),
            "source": _DOC_CITE,
            "notes": _DISTORT_RULE,
        })
        if len(rows) >= 6:
            break
    if not rows:
        rows.append({
            "distortion": _info_request(
                "acquisitions, disposals, accounting changes, one-offs or mix shifts"
            ),
            "kind": "unknown",
            "impact_on_comparability": _NA,
            "source": _NA,
            "notes": _DISTORT_RULE,
        })
    return rows


def _metric_unit_suffix(unit: str) -> str:
    u = (unit or "").strip().lower()
    if u == "%":
        return "pct"
    if "inr" in u and "cr" in u:
        return "inr_cr"
    if "usd" in u and ("m" in u or "mn" in u):
        return "usd_m"
    if "usd" in u:
        return "usd"
    if "gbp" in u:
        return "gbp"
    # Keep a stable non-INR key when unit is known but not INR
    if u and "inr" not in u:
        return re.sub(r"[^a-z0-9]+", "_", u).strip("_") or "units"
    return "inr_cr"


def _performance_metrics(pl_lines: list[dict]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for row in pl_lines:
        if not isinstance(row, dict):
            continue
        key = re.sub(r"[^a-z0-9]+", "_", str(row.get("line_item") or "").lower()).strip("_")
        if not key:
            continue
        unit = str(row.get("unit") or "")
        suffix = _metric_unit_suffix(unit)
        # Prefer calendar FY2024, else latest actual-looking year key on the row
        val_2024 = row.get("fy2024_value")
        if val_2024 is not None:
            metrics[f"{key}_fy2024_{suffix}"] = float(val_2024)
            # Dual-write legacy INR-shaped key only when unit is actually INR Cr
            if suffix == "inr_cr":
                metrics[f"{key}_fy2024_inr_cr"] = float(val_2024)
        for ykey, yval in row.items():
            m = re.fullmatch(r"fy(20\d{2})_value", str(ykey))
            if not m or yval is None:
                continue
            year = m.group(1)
            metrics[f"{key}_fy{year}_{suffix}"] = float(yval)
        if row.get("fy2021_value") is not None and key == "ebitda":
            metrics["ebitda_fy2021"] = float(row["fy2021_value"])
    return metrics


def _bridge_notes(
    trend_headline: str,
    cim_rows: list[dict],
    distortions: list[dict],
    legacy: dict[str, Any],
) -> list[str]:
    notes: list[str] = [_SHARED_RULE]
    if _is_filled(trend_headline) and not trend_headline.startswith("Information"):
        notes.append(_clean(trend_headline, 280))
    for r in cim_rows[:2]:
        if isinstance(r, dict) and str(r.get("difference") or "") not in {"", "Aligned"}:
            if not str(r.get("difference") or "").startswith("Information"):
                notes.append(
                    _clean(
                        f"Accounts vs CIM {r.get('period')}: accounts "
                        f"{r.get('accounts_value')} vs CIM {r.get('cim_value')} "
                        f"({r.get('difference')}). Basis: {r.get('chosen_basis')}.",
                        280,
                    )
                )
    for d in distortions[:2]:
        if isinstance(d, dict) and _is_filled(d.get("distortion")):
            if not str(d.get("distortion")).startswith("Information"):
                notes.append(_clean(str(d["distortion"]), 220))
    for n in (legacy.get("bridge_notes") or [])[:3]:
        if isinstance(n, str) and n.strip() and n not in notes:
            notes.append(_soften_invest(_clean(n, 220)))
    return notes[:8]


def _quality_reliance(
    *,
    period_facts: list[dict],
    growth_rows: list[dict],
    cim_rows: list[dict],
    seasonality: list[dict],
    distortions: list[dict],
) -> tuple[str, str, str]:
    has_rev = any(
        str(f.get("line_item") or "").lower() == "revenue" and f.get("value") is not None
        for f in period_facts if isinstance(f, dict)
    )
    has_ebitda = any(
        str(f.get("line_item") or "").lower() == "ebitda" and f.get("value") is not None
        for f in period_facts if isinstance(f, dict)
    )
    has_cim_diff = any(
        isinstance(r, dict)
        and str(r.get("difference") or "") not in {"", "Aligned"}
        and not str(r.get("difference") or "").startswith("Information")
        for r in cim_rows
    )
    season_filled = any(
        isinstance(s, dict) and _is_filled(s.get("shape"))
        and not str(s.get("shape")).startswith("Information")
        for s in seasonality
    )
    distort_filled = any(
        isinstance(d, dict) and _is_filled(d.get("distortion"))
        and not str(d.get("distortion")).startswith("Information")
        for d in distortions
    )

    quality = "PASS" if has_rev and has_ebitda else "REWORK"
    if has_rev and has_ebitda and (has_cim_diff or len(growth_rows) >= 2):
        reliance = "READY"
    elif has_rev or has_ebitda:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: accounting-record P&L "
        f"{'present' if has_rev and has_ebitda else 'incomplete'}.",
        f"Reliance {reliance}: "
        f"{'shared basis publishable' if reliance == 'READY' else 'gaps remain'}.",
    ]
    if has_cim_diff:
        bits.append("Accounts vs CIM differences shown with chosen basis.")
    if not season_filled:
        bits.append("Seasonal / YTD shape still an information request.")
    if not distort_filled:
        bits.append("Comparability distortions not yet evidenced.")
    return quality, reliance, " ".join(bits)


def _heuristic_historical_performance_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    deal: Deal | None = None,
) -> dict[str, Any]:
    del geography
    from agetic_cdd_api.services_accounts_extract import (
        accounts_to_period_facts,
        accounts_to_pl_lines,
        detect_unit_from_corpus,
        extract_accounts_pack,
    )

    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for item in (legacy.get("bridge_notes") or [])[:4]:
        if isinstance(item, str) and item.strip():
            extra += "\n" + item.strip()
    corpus_full = (corpus or "") + extra
    unit_default, _ = detect_unit_from_corpus(corpus_full)

    # 1) QBO + workbook accounts pack (preferred)
    accounts = extract_accounts_pack(deal) if deal is not None else None
    period_facts: list[dict[str, Any]] = []
    accounts_pl: list[dict[str, Any]] = []
    if accounts:
        period_facts = accounts_to_period_facts(accounts)
        accounts_pl = accounts_to_pl_lines(accounts)
        for src in accounts.get("sources") or []:
            if isinstance(src, str) and src and src not in sources:
                sources.append(src)

    # 2) Databook-promoted legacy lines when accounts thin
    if not period_facts and legacy.get("pl_lines"):
        for row in (legacy.get("pl_lines") or [])[:12]:
            if not isinstance(row, dict):
                continue
            item = str(row.get("line_item") or "")
            unit = str(row.get("unit") or unit_default)
            year_keys = [
                (k, m.group(1))
                for k, m in (
                    (key, re.fullmatch(r"fy(20\d{2})_value", str(key)))
                    for key in row.keys()
                )
                if m
            ]
            if not year_keys:
                for key, period in (
                    ("fy2021_value", "FY2021"),
                    ("fy2022_value", "FY2022"),
                    ("fy2023_value", "FY2023"),
                    ("fy2024_value", "FY2024"),
                    ("fy2025_value", "FY2025"),
                ):
                    if row.get(key) is None:
                        continue
                    year_keys.append((key, period.replace("FY", "")))
            for key, year_s in year_keys:
                if row.get(key) is None:
                    continue
                year = int(year_s)
                period = f"FY{year}P" if year >= 2026 else f"FY{year}"
                period_facts.append({
                    "line_item": item,
                    "period": period,
                    "period_type": _period_label(period),
                    "value": row[key],
                    "unit": unit,
                    "basis": "accounting_records",
                    "source": _DOC_CITE,
                    "location": f"Legacy P&L · {period}",
                    "notes": _RECORD_RULE,
                    "fiscal_year": year,
                })

    # 3) Regex prose extract — never CIM page lists
    if not period_facts:
        period_facts = _extract_period_facts(corpus_full)

    trend_headline, growth_rows = _extract_growth_margins(period_facts)
    cim_rows = _extract_cim_vs_accounts(corpus_full, period_facts)
    seasonality = _extract_seasonality(corpus_full)
    distortions = _extract_distortions(corpus_full)

    pl_lines = accounts_pl or _pivot_pl_lines(period_facts)
    if legacy.get("pl_lines") and not pl_lines:
        pl_lines = [r for r in legacy["pl_lines"] if isinstance(r, dict)][:12]

    metrics = _performance_metrics(pl_lines)
    if not metrics and isinstance(legacy.get("performance_metrics"), dict):
        metrics = {
            k: v for k, v in legacy["performance_metrics"].items()
            if isinstance(v, (int, float))
        }

    bridge = _bridge_notes(trend_headline, cim_rows, distortions, legacy)
    quality, reliance, rationale = _quality_reliance(
        period_facts=period_facts,
        growth_rows=growth_rows,
        cim_rows=cim_rows,
        seasonality=seasonality,
        distortions=distortions,
    )

    n_periods = len({
        str(f.get("period")) for f in period_facts if f.get("value") is not None
    })
    cim_gaps = len([
        r for r in cim_rows
        if str(r.get("difference")) not in {"", "Aligned"}
        and not str(r.get("difference", "")).startswith("Information")
    ])
    lead = (
        trend_headline.split("(")[0].strip()
        if _is_filled(trend_headline) and not trend_headline.startswith("Information")
        else f"Historical Performance for {company}"
    )
    bits = [lead, f"{n_periods} period(s) from accounts", f"{cim_gaps} CIM gap(s)"]
    if accounts:
        bits.insert(1, "QBO/workbook accounts extract")

    return {
        "insight_snapshot": _soften_invest(". ".join(b for b in bits if b)),
        "trend_headline": trend_headline,
        "period_facts": period_facts,
        "growth_and_margins": growth_rows,
        "accounts_vs_cim": cim_rows,
        "seasonality": seasonality,
        "comparability_distortions": distortions,
        "pl_lines": pl_lines,
        "performance_metrics": metrics,
        "bridge_notes": bridge,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not period_facts and not metrics,
        "accounts_extract": bool(accounts),
        "reporting_unit": (
            (accounts or {}).get("unit")
            or (pl_lines[0].get("unit") if pl_lines else None)
            or unit_default
        ),
    }


def _llm_historical_performance_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "historical_performance",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot: string (first line MUST name earnings direction plainly),\n"
        "trend_headline: string,\n"
        "period_facts: [{line_item, period, period_type, value, unit, basis, "
        "source, location, notes}],\n"
        "growth_and_margins: [{metric, period, value, prior_period, source, notes}],\n"
        "accounts_vs_cim: [{metric, period, accounts_value, cim_value, difference, "
        "reason, chosen_basis, why, source, notes}],\n"
        "seasonality: [{shape, period_grain, ytd_vs_prior, source, notes}],\n"
        "comparability_distortions: [{distortion, kind, impact_on_comparability, "
        "source, notes}],\n"
        "pl_lines: [{line_item, fy2024_value, fy2023_value, unit}],\n"
        "performance_metrics: {string: number},\n"
        "bridge_notes: [string],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "period_type must be actual | last twelve months | forecast | year to date.\n"
        "Prefer accounting_records over CIM. No invest or pass."
    )
    try:
        return generate_json(system=system, user=user, temperature=0.1)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str,
) -> dict[str, Any]:
    heur = _heuristic_historical_performance_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy_spec,
    )
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    def _rows(key: str, id_field: str) -> list[dict]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        out: list[dict] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            cleaned = {
                k: (_clean(v, 400) if isinstance(v, str) else v)
                for k, v in row.items()
            }
            if not _is_filled(cleaned.get(id_field)) and cleaned.get("value") is None:
                continue
            out.append(cleaned)
        return out or heur.get(key) or []

    llm["period_facts"] = _rows("period_facts", "line_item")
    llm["growth_and_margins"] = _rows("growth_and_margins", "metric")
    llm["accounts_vs_cim"] = _rows("accounts_vs_cim", "metric")
    llm["seasonality"] = _rows("seasonality", "shape")
    llm["comparability_distortions"] = _rows("comparability_distortions", "distortion")

    trend = _soften_invest(llm.get("trend_headline") or heur.get("trend_headline") or "")
    if not _is_filled(trend):
        trend = heur.get("trend_headline") or _info_request("earnings trend")
    llm["trend_headline"] = trend

    pl = llm.get("pl_lines") if isinstance(llm.get("pl_lines"), list) else []
    pl = [r for r in pl if isinstance(r, dict) and r.get("line_item")]
    llm["pl_lines"] = pl or heur.get("pl_lines") or []

    perf = llm.get("performance_metrics") if isinstance(llm.get("performance_metrics"), dict) else {}
    llm["performance_metrics"] = {
        str(k): float(v)
        for k, v in (perf or heur.get("performance_metrics") or {}).items()
        if isinstance(v, (int, float))
    } or heur.get("performance_metrics") or {}

    notes = llm.get("bridge_notes") if isinstance(llm.get("bridge_notes"), list) else []
    notes = [_soften_invest(_clean(n, 220)) for n in notes if isinstance(n, str) and n.strip()]
    if _SHARED_RULE not in notes:
        notes.insert(0, _SHARED_RULE)
    llm["bridge_notes"] = (notes or heur.get("bridge_notes") or [])[:8]

    quality, reliance, rationale = _quality_reliance(
        period_facts=llm["period_facts"],
        growth_rows=llm["growth_and_margins"],
        cim_rows=llm["accounts_vs_cim"],
        seasonality=llm["seasonality"],
        distortions=llm["comparability_distortions"],
    )
    qv = str(llm.get("quality_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    llm["quality_reliance_rationale"] = (
        _soften_invest(_clean(llm.get("quality_reliance_rationale"), 460))
        if str(llm.get("quality_reliance_rationale") or "").strip()
        else rationale
    )

    for dead in (
        "recommendation", "confidence", "investment_verdict", "verdict",
        "invest_recommendation",
    ):
        llm.pop(dead, None)

    snap = _soften_invest(llm.get("insight_snapshot") or "")
    if not _is_filled(snap) or snap.startswith("Information"):
        snap = heur.get("insight_snapshot") or trend
    if trend and not trend.startswith("Information") and trend.split(".")[0] not in snap:
        snap = _clean(f"{trend.split('(')[0].strip()}. {snap}", 480)
    llm["insight_snapshot"] = snap
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not llm["period_facts"] and not llm["performance_metrics"]
    return llm


def build_historical_performance_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_historical_performance_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    if not prefer_heuristic:
        llm = _llm_historical_performance_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
        )
        if llm:
            spec = _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )
            return _apply_databook_release(deal, spec)

    spec = _heuristic_historical_performance_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
        deal=deal,
    )
    return _apply_databook_release(deal, spec)


def _apply_databook_release(deal: Deal, spec: dict[str, Any]) -> dict[str, Any]:
    """G1 — overlay released databook; never leave agent material figures as silent finals."""
    try:
        from agetic_cdd_api.services_databook_consume import merge_promoted_into_historical_spec

        return merge_promoted_into_historical_spec(deal, spec)
    except Exception:
        return spec


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [str(c).replace("|", "/").replace("\n", " ") for c in row]
        while len(cells) < len(headers):
            cells.append("")
        lines.append("| " + " | ".join(cells[: len(headers)]) + " |")
    return "\n".join(lines) + "\n\n"


def _insight(text: object) -> str:
    body = _soften_invest(str(text or "").strip()) or _info_request(
        "historical performance insight from accounting records"
    )
    return f"> **Insight Snapshot:** {body}\n\n"


def render_historical_performance_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    period_facts = (
        spec.get("period_facts") if isinstance(spec.get("period_facts"), list) else []
    )
    growth = (
        spec.get("growth_and_margins")
        if isinstance(spec.get("growth_and_margins"), list) else []
    )
    cim = (
        spec.get("accounts_vs_cim")
        if isinstance(spec.get("accounts_vs_cim"), list) else []
    )
    season = spec.get("seasonality") if isinstance(spec.get("seasonality"), list) else []
    distort = (
        spec.get("comparability_distortions")
        if isinstance(spec.get("comparability_distortions"), list) else []
    )
    pl_lines = spec.get("pl_lines") if isinstance(spec.get("pl_lines"), list) else []
    bridge = spec.get("bridge_notes") if isinstance(spec.get("bridge_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []
    trend = str(spec.get("trend_headline") or "").strip()

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Financial Record (Accounting Basis)\n\n")
    parts.append(f"{_RECORD_RULE} {_SHARED_RULE}\n\n")
    if trend and not trend.startswith("Information"):
        parts.append(f"**Trend:** {_soften_invest(trend)}\n\n")
    if period_facts:
        parts.append(_table(
            ["Line item", "Period", "Type", "Value", "Unit", "Basis", "Location", "Source"],
            [
                [
                    _clean(r.get("line_item"), 40),
                    _clean(r.get("period"), 16),
                    _clean(r.get("period_type"), 20),
                    (
                        f"{float(r['value']):g}"
                        if isinstance(r.get("value"), (int, float))
                        else _clean(r.get("value"), 20)
                    ),
                    _clean(r.get("unit"), 12),
                    _clean(r.get("basis"), 24),
                    _clean(r.get("location"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in period_facts if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('P&L from accounting records by period')}**\n\n")
    if pl_lines:
        parts.append("### Legacy Adjusted EBITDA Bridge (dual-write)\n\n")
        parts.append(_table(
            ["Line item", "FY2023", "FY2024", "Unit"],
            [
                [
                    _clean(r.get("line_item"), 40),
                    (
                        f"{float(r['fy2023_value']):g}"
                        if isinstance(r.get("fy2023_value"), (int, float))
                        else "—"
                    ),
                    (
                        f"{float(r['fy2024_value']):g}"
                        if isinstance(r.get("fy2024_value"), (int, float))
                        else "—"
                    ),
                    _clean(r.get("unit"), 12),
                ]
                for r in pl_lines if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Growth & Margin Trends\n\n")
    parts.append(f"{_TREND_RULE}\n\n")
    if growth:
        parts.append(_table(
            ["Metric", "Period", "Value", "Prior period", "Source"],
            [
                [
                    _clean(r.get("metric"), 40),
                    _clean(r.get("period"), 16),
                    _clean(r.get("value"), 24),
                    _clean(r.get("prior_period"), 16),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in growth if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('period growth and margin rates')}**\n\n")
    parts.append("---\n\n")

    parts.append("## 3. Accounts vs CIM / Management Summary\n\n")
    parts.append(f"{_CIM_RULE}\n\n")
    if cim:
        parts.append(_table(
            ["Metric", "Period", "Accounts", "CIM / mgmt", "Difference",
             "Reason", "Chosen basis", "Why", "Source"],
            [
                [
                    _clean(r.get("metric"), 24),
                    _clean(r.get("period"), 16),
                    _clean(r.get("accounts_value"), 40),
                    _clean(r.get("cim_value"), 40),
                    _clean(r.get("difference"), 40),
                    _clean(r.get("reason"), 80),
                    _clean(r.get("chosen_basis"), 24),
                    _clean(r.get("why"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in cim if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('CIM comparison for revenue / EBITDA')}**\n\n")
    parts.append("---\n\n")

    parts.append("## 4. Seasonal / Intra-year Shape\n\n")
    parts.append(f"{_SEASON_RULE}\n\n")
    if season:
        parts.append(_table(
            ["Shape", "Grain", "YTD vs prior", "Source"],
            [
                [
                    _clean(r.get("shape"), 160),
                    _clean(r.get("period_grain"), 20),
                    _clean(r.get("ytd_vs_prior"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in season if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('monthly or quarterly seasonality')}**\n\n")
    parts.append("---\n\n")

    parts.append("## 5. Comparability Distortions\n\n")
    parts.append(f"{_DISTORT_RULE}\n\n")
    if distort:
        parts.append(_table(
            ["Distortion", "Kind", "Impact on comparability", "Source"],
            [
                [
                    _clean(r.get("distortion"), 160),
                    _clean(r.get("kind"), 24),
                    _clean(r.get("impact_on_comparability"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in distort if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('comparability distortions')}**\n\n")
    if bridge:
        parts.append("### Bridge notes\n\n")
        for n in bridge[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    parts.append(f"**Quality:** {qv} — is the work accurate and honest about limits?\n\n")
    parts.append(
        f"**Reliance:** {rv} — can diligence rest on this financial record "
        f"as the shared basis?\n\n"
    )
    rationale = spec.get("quality_reliance_rationale")
    if _is_filled(rationale):
        parts.append(f"{_soften_invest(str(rationale))}\n\n")
    parts.append(
        "*This document publishes the shared financial facts. It does not "
        "recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    if srcs:
        for i, s in enumerate(srcs[:16], start=1):
            parts.append(f"[{i}] {_clean(s, 120)} ")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n")
    parts.append(f"\n{_SOURCES_MARKER}\n")
    return "".join(parts)
