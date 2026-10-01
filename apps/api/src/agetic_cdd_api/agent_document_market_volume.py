"""Compose DiligenceIQ Market Volume & Growth — size + growth split (prompt book).

Bottom-up units × capture × price; top-down perimeter match; market vs company
growth; plan multiple. Compute company growth from accounts when present.
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

_FY_ROW = re.compile(
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+"
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?",
    re.IGNORECASE,
)
_REVENUE_ROW = re.compile(
    r"\bRevenue\s+"
    r"([\d,\.\-\(\)]+(?:\.\d+)?)\s+([\d,\.\-\(\)]+(?:\.\d+)?)\s+"
    r"([\d,\.\-\(\)]+(?:\.\d+)?)\s+([\d,\.\-\(\)]+(?:\.\d+)?)\s+"
    r"([\d,\.\-\(\)]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_UNITS = re.compile(
    r"(?:~|approx\.?\s*|approximately\s*)?"
    r"([\d]{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"\s*(million|m|bn|billion|mn)?"
    r"\s*(?:units?|vehicles?|scooters?|households?|premises|sites|tonnes?|tons?)\b",
    re.IGNORECASE,
)
_ASP = re.compile(
    r"(?:ASP|average\s+selling\s+price|realised\s+price|price\s+per\s+unit)"
    r"[^\d₹$]{0,40}?(?:INR\s*|USD\s*|€\s*|₹\s*|\$)?\s*"
    r"([\d]{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)",
    re.IGNORECASE,
)
_SHARE = re.compile(
    r"(?:market\s+share|share)\s*(?:of\s+)?(?:~)?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_CAGR_SPAN = re.compile(
    r"(?:~)?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:CAGR|compound)[^\n.]{0,40}?"
    r"(?:FY\s*(20\d{2})E?\s*[–\-to]+\s*FY\s*(20\d{2})E?|"
    r"(20\d{2})\s*[–\-to]+\s*(20\d{2}))",
    re.IGNORECASE,
)
_CAGR_SIMPLE = re.compile(
    r"(?:CAGR|growing\s+at)[^\d%]{0,30}?(?:~)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_TAM = re.compile(
    r"\bTAM\b[^\d$₹]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
    re.IGNORECASE,
)
_SAM = re.compile(
    r"\bSAM\b[^\d$₹]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
    re.IGNORECASE,
)
_SERIES_POINT = re.compile(
    r"(FY\s*20\d{2}E?)\s[^.\d]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
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


def gather_market_volume_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "financial": 2,
        "customer": 3,
        "company_management": 4,
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
        # Prefer structured workbook TOTAL Current sums (Residential+Commercial)
        tables = loaded.get("tables") if isinstance(loaded.get("tables"), list) else []
        if tables:
            from agetic_cdd_api.deep_dive_extractors import extract_sizing_from_workbook_tables

            sizing = extract_sizing_from_workbook_tables(tables)
            tam, sam, som = sizing.get("TAM"), sizing.get("SAM"), sizing.get("SOM")
            if tam and sam and som:
                # Single combined TOTAL line — avoids double-counting segment rows
                text = (
                    f"{text}\nTOTAL Current {tam.value} {sam.value} {som.value}\n"
                    f"{tam.raw or ''}"
                ).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _parse_num(raw: str) -> float | None:
    """Parse US or European-style decimals (1,234.56 / 1.234,56 / 1234,5)."""
    s = (raw or "").strip().replace("\u00a0", "").replace(" ", "")
    if not s:
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1]
    if s.startswith("-"):
        neg = True
        s = s[1:]
    # 1.234.567,89 or 1.234,56
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d+,\d{1,6}", s) and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _cagr(start: float, end: float, years: float) -> str | None:
    if start <= 0 or years <= 0:
        return None
    rate = (end / start) ** (1 / years) - 1
    return f"{rate * 100:.1f}%"


def _fy_series(corpus: str) -> tuple[list[str], list[float]]:
    years_m = _FY_ROW.search(corpus)
    rev_m = _REVENUE_ROW.search(corpus)
    if not years_m or not rev_m:
        return [], []
    years = [f"FY{years_m.group(i)}" for i in range(1, 6)]
    revs = [_parse_num(rev_m.group(i)) for i in range(1, 6)]
    out_y, out_r = [], []
    for y, r in zip(years, revs):
        if r is None:
            continue
        out_y.append(y)
        out_r.append(r)
    return out_y, out_r


def _money_match(m: re.Match[str] | None) -> str:
    if not m:
        return _NA
    return f"{_fmt_num(m.group(1), m.group(2))} {_DOC_CITE}"


def _bottom_up(corpus: str) -> dict[str, str]:
    units_m = _UNITS.search(corpus)
    share_m = _SHARE.search(corpus)
    asp_m = _ASP.search(corpus)

    units_raw = _parse_num(units_m.group(1)) if units_m else None
    scale = (units_m.group(2) or "").lower() if units_m else ""
    if units_raw is not None:
        if scale in {"million", "m"}:
            units_raw *= 1_000_000
        elif scale in {"bn", "billion"}:
            units_raw *= 1_000_000_000

    capture = _parse_num(share_m.group(1)) / 100 if share_m else None
    price = _parse_num(asp_m.group(1)) if asp_m else None

    arithmetic = _info_request("bottom-up arithmetic: units × capture × realised price")
    size = _NA
    if units_raw is not None and capture is not None and price is not None:
        product = units_raw * capture * price
        arithmetic = (
            f"{units_raw:,.0f} units × {capture * 100:.1f}% capture × "
            f"{price:g} price/unit = {product:,.0f} {_COMPUTED}"
        )
        size = f"{product:,.0f} {_COMPUTED}"
    elif units_raw is not None and capture is not None:
        product = units_raw * capture
        arithmetic = (
            f"{units_raw:,.0f} units × {capture * 100:.1f}% capture = "
            f"{product:,.0f} units capturable {_COMPUTED} "
            f"(price/unit {_info_request('realised annual price per unit')})"
        )
        size = f"{product:,.0f} units {_COMPUTED}"
    elif units_raw is not None:
        arithmetic = (
            f"Units evidenced: {units_raw:,.0f} {_DOC_CITE}. "
            f"Capture and price still required for full bottom-up size."
        )

    return {
        "units": (
            f"{_fmt_num(units_m.group(1), units_m.group(2))} {_DOC_CITE}"
            if units_m
            else _info_request("countable units in the served geography")
        ),
        "capture_share": (
            f"{share_m.group(1)}% {_DOC_CITE}"
            if share_m
            else _info_request("realistically capturable share")
        ),
        "realised_price": (
            f"{_fmt_num(asp_m.group(1))} {_DOC_CITE}"
            if asp_m
            else _info_request("realised annual price per unit")
        ),
        "arithmetic": arithmetic,
        "bottom_up_size": size if size != _NA else (
            arithmetic if "×" in arithmetic else _info_request("bottom-up market size")
        ),
    }


def _top_down(corpus: str, perimeter: dict[str, Any] | None) -> dict[str, str]:
    sam_m = _SAM.search(corpus)
    tam_m = _TAM.search(corpus)
    perim_note = ""
    if isinstance(perimeter, dict):
        bits = [
            _clean(perimeter.get(k), 80)
            for k in ("service", "customer_types", "geography", "value_chain_stage")
            if perimeter.get(k)
        ]
        if bits:
            perim_note = "Our perimeter: " + " · ".join(bits[:3])

    if sam_m:
        return {
            "published_figure": _money_match(sam_m),
            "published_perimeter": _info_request("published perimeter behind SAM"),
            "matches_ours": (
                "Candidate match — SAM usually tracks the served segment; confirm against "
                f"Market Definition axes. {perim_note}".strip()
            ),
            "use": f"Top-down cross-check {_DOC_CITE}",
            "fallback": "Use only if perimeter matches; otherwise rely on bottom-up",
        }
    if tam_m:
        return {
            "published_figure": _money_match(tam_m),
            "published_perimeter": "Broader industry TAM — typically wider than served market",
            "matches_ours": "No — TAM is context unless perimeter is proven identical",
            "use": "Context only — do not substitute for bottom-up addressable size",
            "fallback": "No matching top-down source — rely on the bottom-up figure",
        }
    return {
        "published_figure": _NA,
        "published_perimeter": _NA,
        "matches_ours": "No matching published source found",
        "use": "Rely on the bottom-up figure",
        "fallback": "No top-down source with a matching perimeter — bottom-up stands",
    }


def _market_series(corpus: str, legacy: dict[str, Any] | None) -> tuple[list[dict[str, str]], str]:
    rows: list[dict[str, str]] = []
    for m in _SERIES_POINT.finditer(corpus[:40_000]):
        rows.append({
            "period": _clean(m.group(1), 20),
            "value": f"{_fmt_num(m.group(2), m.group(3))} {_DOC_CITE}",
            "currency_units": (m.group(3) or "as stated").lower(),
            "source_date": _clean(m.group(1), 20),
            "kind": "observed_or_stated",
        })
        if len(rows) >= 6:
            break

    # Legacy TAM/SAM as series anchors
    if isinstance(legacy, dict):
        for key in ("tam", "sam", "som"):
            metric = legacy.get(key)
            if isinstance(metric, dict) and metric.get("value") is not None:
                rows.append({
                    "period": metric.get("as_of") or "as stated",
                    "value": (
                        f"{metric.get('unit', 'USD')} {metric['value']} "
                        f"{metric.get('scale') or ''} {_DOC_CITE}"
                    ).strip(),
                    "currency_units": f"{metric.get('unit', 'USD')} {metric.get('scale') or ''}".strip(),
                    "source_date": metric.get("as_of") or "pack",
                    "kind": key.upper(),
                })

    growth_note = _info_request("market growth from series endpoints and years elapsed")
    span = _CAGR_SPAN.search(corpus)
    if span:
        y1 = span.group(2) or span.group(4)
        y2 = span.group(3) or span.group(5)
        years = None
        if y1 and y2:
            try:
                years = abs(int(y2) - int(y1))
            except ValueError:
                years = None
        rate = span.group(1)
        if years and years > 1:
            growth_note = (
                f"{rate}% CAGR over {years} years (FY{y1}–FY{y2}) {_DOC_CITE} — "
                f"multi-year rate from endpoints, not a one-year label"
            )
        elif years == 1:
            growth_note = (
                f"{rate}% over 1 year (FY{y1}–FY{y2}) {_DOC_CITE} — "
                f"labelled as a one-year rate, not a multi-year CAGR"
            )
        elif years == 0:
            growth_note = (
                f"{rate}% stated for FY{y1} (zero-year span) {_DOC_CITE} — "
                f"not a multi-year CAGR; endpoints are the same year"
            )
        else:
            growth_note = f"{rate}% with stated span {_DOC_CITE}"
    else:
        simple = _CAGR_SIMPLE.search(corpus)
        if simple:
            growth_note = (
                f"{simple.group(1)}% growth rate stated {_DOC_CITE} — "
                f"confirm years elapsed before treating as multi-year CAGR"
            )

    if not rows:
        rows.append({
            "period": _info_request("market series period"),
            "value": _info_request("market series value"),
            "currency_units": _NA,
            "source_date": _NA,
            "kind": "missing",
        })
    return rows[:8], growth_note


def _company_growth(corpus: str) -> tuple[dict[str, str], list[dict[str, str]]]:
    years, revs = _fy_series(corpus)
    company: dict[str, str] = {
        "geography_period_align": (
            "Aligned to same geography / segment / period as the market series where evidenced"
        ),
        "historical_growth": _info_request("company historical growth from accounting records"),
        "basis": _NA,
    }
    decomp: list[dict[str, str]] = []

    if len(revs) >= 2:
        # Prefer first actual-like to last plan-like, or first to penultimate
        start_i, end_i = 0, len(revs) - 1
        # Prefer span ending before pure forecast if possible
        for i, y in enumerate(years):
            if "E" not in y.upper():
                start_i = 0
                end_i = i
        if end_i <= start_i:
            end_i = len(revs) - 1
        n = max(1, end_i - start_i)
        start_rev, end_rev = revs[start_i], revs[end_i]
        rate = _cagr(start_rev, end_rev, n)
        basis = (
            f"Revenue {_fmt_num(f'{start_rev:g}', 'cr')} → "
            f"{_fmt_num(f'{end_rev:g}', 'cr')} {_COMPUTED}"
        )
        align = f"Company revenue {years[start_i]}→{years[end_i]} from P&L {_DOC_CITE}"
        if rate:
            company = {
                "geography_period_align": align,
                "historical_growth": f"{rate} over {n} year(s) {_COMPUTED}",
                "basis": basis,
            }
        elif start_rev <= 0:
            # Turnaround / non-positive base — CAGR undefined; still report endpoints.
            company = {
                "geography_period_align": align,
                "historical_growth": (
                    f"CAGR undefined from non-positive base "
                    f"({start_rev:g} → {end_rev:g} over {n} year(s)) {_COMPUTED}"
                ),
                "basis": basis,
            }
        # One-year labelling when span is a single year
        if n == 1 and start_rev > 0:
            yoy = (end_rev / start_rev - 1) * 100
            company["historical_growth"] = (
                f"{yoy:.1f}% one-year change {years[start_i]}→{years[end_i]} {_COMPUTED} "
                f"(not labelled as multi-year CAGR)"
            )
        elif n == 1 and start_rev <= 0:
            company["historical_growth"] = (
                f"One-year change from non-positive base "
                f"{start_rev:g} → {end_rev:g} {_COMPUTED} (not labelled as CAGR)"
            )

    # Decomposition legs — evidence-gated
    lower = corpus.lower()
    for driver, needles in (
        ("share_gain", ("market share", "share gain", "share of")),
        ("price", ("asp", "price", "average selling")),
        ("mix", ("mix", "software", "attach", "margin")),
        ("acquisition", ("acquisition", "m&a", "inorganic")),
    ):
        if any(n in lower for n in needles):
            decomp.append({
                "driver": driver,
                "contribution": _info_request(f"quantified contribution of {driver}"),
                "evidence": f"Driver '{driver}' mentioned in pack {_DOC_CITE}",
            })
        else:
            decomp.append({
                "driver": driver,
                "contribution": _NA,
                "evidence": f"Omitted — '{driver}' not evidenced as a growth leg",
            })
    return company, decomp


def _plan_multiple(corpus: str, market_growth: str, company: dict[str, str]) -> dict[str, str]:
    plan_rate = None
    mkt_rate = None
    # Extract numeric rates
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", market_growth):
        try:
            mkt_rate = float(m.group(1))
            break
        except ValueError:
            pass
    hist = str(company.get("historical_growth") or "")
    for m in re.finditer(r"(\d{1,3}(?:\.\d+)?)\s*%", hist):
        try:
            plan_rate = float(m.group(1))
            break
        except ValueError:
            pass
    # Plan CAGR from pack (longer-horizon)
    plan_m = re.search(
        r"(?:plan|target|path|fy20\d{2}e)[^\d%]{0,40}?(\d{1,3}(?:\.\d+)?)\s*%\s*(?:cagr|growth)",
        corpus[:30_000],
        re.I,
    )
    if plan_m:
        try:
            plan_rate = float(plan_m.group(1))
        except ValueError:
            pass

    if plan_rate is not None and mkt_rate is not None and mkt_rate > 0:
        multiple = plan_rate / mkt_rate
        plain = (
            f"Plan implies ~{plan_rate:g}% vs market ~{mkt_rate:g}% "
            f"→ about {multiple:.1f}× the market rate {_COMPUTED}."
        )
        must = _NA
        if multiple >= 2:
            plain += (
                " Plan requires growing several times faster than the market — say so plainly."
            )
            must = (
                "What must be true: sustained share gains, pricing power, and capacity "
                "to outpace market volume on the same geography and segment."
            )
        return {
            "plan_rate": f"{plan_rate:g}%",
            "market_rate": f"{mkt_rate:g}%",
            "multiple": f"{multiple:.1f}× {_COMPUTED}",
            "plain_english": plain,
            "what_must_be_true": must,
        }
    return {
        "plan_rate": _info_request("plan implied growth rate"),
        "market_rate": market_growth if market_growth and not market_growth.startswith("Information") else _info_request("market growth rate"),
        "multiple": _info_request("plan / market growth multiple"),
        "plain_english": (
            "Cannot state the multiple until both plan and market endpoint rates are evidenced."
        ),
        "what_must_be_true": _NA,
    }


def _quality_reliance(*, has_bottom_up: bool, has_company: bool, accounts_present: bool) -> tuple[str, str, str]:
    quality = "PASS"
    if accounts_present and not has_company:
        return (
            "REWORK",
            "BLOCKED",
            "Accounts are in the data room but company growth was not computed — not acceptable.",
        )
    if has_bottom_up and has_company:
        return "PASS", "READY", "Bottom-up size and company growth from accounts both present."
    if has_bottom_up or has_company:
        return "PASS", "LIMITED", "Partial sizing / growth evidence — top-down or decomposition incomplete."
    return "PASS", "BLOCKED", "Insufficient units/price/accounts to size or split growth."


def _llm_market_volume_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    perimeter_note: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    system = compose_system(
        "market_volume_and_growth",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        + (f"Approved / draft market perimeter:\n{perimeter_note}\n\n" if perimeter_note else "")
        + f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "bottom_up: {units, capture_share, realised_price, arithmetic, bottom_up_size},\n"
        "top_down: {published_figure, published_perimeter, matches_ours, use, fallback},\n"
        "market_series: [{period, value, currency_units, source_date, kind}],\n"
        "market_growth_note (string — endpoints + years; never mislabel 1-year as multi-year),\n"
        "company_growth: {geography_period_align, historical_growth, basis},\n"
        "growth_decomposition: [{driver, contribution, evidence}] "
        "drivers share_gain|price|mix|acquisition,\n"
        "plan_vs_market: {plan_rate, market_rate, multiple, plain_english, what_must_be_true},\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "If revenue accounts are present, compute company growth — do not write Not available. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _sizing_from_corpus(corpus: str) -> dict[str, Any]:
    """Re-extract TAM/SAM/SOM from corpus; prefer TOTAL Current sums over segment rows."""
    from agetic_cdd_api.deep_dive_extractors import _extract_sizing

    sizing = _extract_sizing(corpus or "")
    out: dict[str, Any] = {}
    for label, key in (("TAM", "tam"), ("SAM", "sam"), ("SOM", "som")):
        metric = sizing.get(label)
        if metric is not None:
            out[key] = metric.model_dump()
    return out


def _prefer_sizing(
    *,
    corpus: str,
    legacy: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pick TAM/SAM/SOM: corpus TOTAL extract wins over stale segment legacy."""
    extracted = _sizing_from_corpus(corpus)
    cur = current if isinstance(current, dict) else {}
    out: dict[str, Any] = {}
    for key in ("tam", "sam", "som"):
        cand = extracted.get(key) or cur.get(key) or legacy.get(key)
        out[key] = cand
    # If corpus found a Combined/TOTAL figure and legacy is a smaller segment, keep corpus
    for key in ("tam", "sam", "som"):
        ext = extracted.get(key)
        leg = legacy.get(key) if isinstance(legacy.get(key), dict) else None
        if not isinstance(ext, dict) or ext.get("value") is None:
            continue
        raw = str(ext.get("raw") or "")
        if "TOTAL" in raw.upper() or "Combined" in raw:
            out[key] = ext
            continue
        if isinstance(leg, dict) and isinstance(leg.get("value"), (int, float)) and isinstance(
            ext.get("value"), (int, float)
        ):
            # Prefer the larger Current figure when both look like $M market size
            if float(ext["value"]) >= float(leg["value"]) * 1.05:
                out[key] = ext
    return out


def _heuristic_market_volume_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    perimeter: dict[str, Any] | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bottom = _bottom_up(corpus)
    top = _top_down(corpus, perimeter)
    series, mkt_growth = _market_series(corpus, legacy_spec)
    company_g, decomp = _company_growth(corpus)
    plan = _plan_multiple(corpus, mkt_growth, company_g)

    accounts_present = bool(_FY_ROW.search(corpus) and _REVENUE_ROW.search(corpus))
    has_bottom = "×" in str(bottom.get("arithmetic") or "") or (
        bottom.get("bottom_up_size") not in {_NA, None}
        and not str(bottom.get("bottom_up_size", "")).startswith("Information")
    )
    has_company = (
        company_g.get("historical_growth")
        and not str(company_g["historical_growth"]).startswith("Information")
        and "Not available" not in str(company_g["historical_growth"])
    )
    quality, reliance, qr = _quality_reliance(
        has_bottom_up=bool(has_bottom),
        has_company=bool(has_company),
        accounts_present=accounts_present,
    )

    insight = (
        f"Market Volume & Growth for {company}: bottom-up "
        f"{_clean(bottom.get('bottom_up_size'), 80)}; "
        f"market growth {_clean(mkt_growth, 100)}; "
        f"company {_clean(company_g.get('historical_growth'), 80)}. "
        f"Share gain = company growth − market growth on the same perimeter."
    )

    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    sizing = _prefer_sizing(corpus=corpus, legacy=legacy)
    return {
        "insight_snapshot": insight,
        "bottom_up": bottom,
        "top_down": top,
        "market_series": series,
        "market_growth_note": mkt_growth,
        "company_growth": company_g,
        "growth_decomposition": decomp,
        "plan_vs_market": plan,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": "Market Volume & Growth",
        "dd_code": legacy.get("dd_code") or "DD-01",
        "tam": sizing.get("tam"),
        "sam": sizing.get("sam"),
        "som": sizing.get("som"),
        "cagr_pct": legacy.get("cagr_pct") or [],
        "penetration_pct": legacy.get("penetration_pct") or [],
        "unit_volume_notes": legacy.get("unit_volume_notes") or [],
        "growth_notes": legacy.get("growth_notes") or [mkt_growth],
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str,
) -> dict[str, Any]:
    for key in ("bottom_up", "top_down", "company_growth", "plan_vs_market"):
        if not isinstance(llm.get(key), dict):
            llm[key] = {}
    for key in ("market_series", "growth_decomposition"):
        if not isinstance(llm.get(key), list):
            llm[key] = []

    # Refuse "Not available" when accounts are computable
    accounts_present = bool(_FY_ROW.search(corpus) and _REVENUE_ROW.search(corpus))
    cg = llm.get("company_growth") or {}
    hist = str(cg.get("historical_growth") or "")
    if accounts_present and (
        not hist
        or hist.lower().startswith("not available")
        or hist.startswith("Information")
        or hist == _NA
    ):
        _, revs = _fy_series(corpus)
        years, _ = _fy_series(corpus)
        if len(revs) >= 2:
            n = max(1, len(revs) - 1)
            rate = _cagr(revs[0], revs[-1], n)
            if rate:
                llm["company_growth"] = {
                    **cg,
                    "historical_growth": f"{rate} over {n} year(s) {_COMPUTED}",
                    "basis": (
                        f"Revenue series from accounts {_COMPUTED} "
                        f"({years[0]}→{years[-1]})" if years else f"Revenue series {_COMPUTED}"
                    ),
                    "geography_period_align": cg.get("geography_period_align")
                    or "From accounting records in the data room",
                }

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else "PASS"
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else "LIMITED"

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Market Volume & Growth"
    llm["dd_code"] = "DD-01"
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    sizing = _prefer_sizing(corpus=corpus, legacy=legacy, current=llm)
    for k in ("tam", "sam", "som"):
        llm[k] = sizing.get(k)
    for k in ("cagr_pct", "penetration_pct", "unit_volume_notes", "growth_notes"):
        llm.setdefault(k, legacy.get(k))
    return llm


def build_market_volume_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    perimeter: dict[str, Any] | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    # Always gather the VDR corpus so TOTAL Current workbook extract can win.
    # Callers may pass a thin legacy-derived corpus that only contains a segment
    # row (e.g. hauling TAM $498) — merge gathered text in front so sizing prefers TOTAL.
    gathered_corpus, gathered_sources = gather_market_volume_corpus(deal, idx)
    if corpus is None:
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    elif gathered_corpus:
        corpus = f"{gathered_corpus}\n{corpus}"
        sources = list(dict.fromkeys([*(gathered_sources or []), *(sources or [])]))
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
        vars_ = prompt_vars_from_deal(deal)
        perim_note = None
        if isinstance(perimeter, dict):
            perim_note = "; ".join(
                f"{k}={_clean(perimeter.get(k), 100)}"
                for k in ("service", "customer_types", "geography", "value_chain_stage")
                if perimeter.get(k)
            )
        llm = _llm_market_volume_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=vars_.get("geography"),
            materiality=vars_.get("materiality"),
            perimeter_note=perim_note,
        )
        if llm:
            return _normalise_llm_spec(
                llm, sources=sources, legacy_spec=legacy_spec, corpus=corpus
            )

    return _heuristic_market_volume_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        perimeter=perimeter,
        legacy_spec=legacy_spec,
    )


def render_market_volume_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    bottom = spec.get("bottom_up") if isinstance(spec.get("bottom_up"), dict) else {}
    top = spec.get("top_down") if isinstance(spec.get("top_down"), dict) else {}
    series = spec.get("market_series") if isinstance(spec.get("market_series"), list) else []
    company = spec.get("company_growth") if isinstance(spec.get("company_growth"), dict) else {}
    decomp = spec.get("growth_decomposition") if isinstance(spec.get("growth_decomposition"), list) else []
    plan = spec.get("plan_vs_market") if isinstance(spec.get("plan_vs_market"), dict) else {}
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Bottom-Up Market Size\n\n")
    parts.append(
        "Countable units in the served geography × capturable share × realised annual price. "
        "Show the arithmetic.\n\n"
    )
    parts.append(_table(
        ["Component", "Value"],
        [
            ["Units (served geography)", _clean(bottom.get("units"), 160)],
            ["Capturable share", _clean(bottom.get("capture_share"), 80)],
            ["Realised price / unit", _clean(bottom.get("realised_price"), 80)],
            ["Arithmetic", _clean(bottom.get("arithmetic"), 280)],
            ["Bottom-up size", _clean(bottom.get("bottom_up_size"), 120)],
        ],
    ))
    parts.append("---\n\n")

    parts.append("## 2. Top-Down Cross-Check\n\n")
    parts.append(
        "Published source only if its perimeter matches. Otherwise say so and rely on bottom-up.\n\n"
    )
    parts.append(_table(
        ["Field", "Content"],
        [
            ["Published figure", _clean(top.get("published_figure"), 120)],
            ["Published perimeter", _clean(top.get("published_perimeter"), 160)],
            ["Matches ours?", _clean(top.get("matches_ours"), 200)],
            ["Use", _clean(top.get("use"), 160)],
            ["Fallback", _clean(top.get("fallback"), 160)],
        ],
    ))
    parts.append("---\n\n")

    parts.append("## 3. Market Series & Growth\n\n")
    parts.append(
        "Historical and forecast periods with source dates, currency and consistent units. "
        "Growth from endpoints and years elapsed — never label a one-year rate as multi-year.\n\n"
    )
    if series:
        parts.append(_table(
            ["Period", "Value", "Currency / Units", "Source Date", "Kind"],
            [
                [
                    _clean(r.get("period"), 20),
                    _clean(r.get("value"), 80),
                    _clean(r.get("currency_units"), 40),
                    _clean(r.get("source_date"), 40),
                    _clean(r.get("kind"), 30),
                ]
                for r in series if isinstance(r, dict)
            ],
        ))
    parts.append(f"**Market growth:** {_clean(spec.get('market_growth_note'), 320)}\n\n")
    parts.append("---\n\n")

    parts.append("## 4. Company Growth vs Market\n\n")
    parts.append(
        "Same geography, segment and period — from accounting records. "
        "Decompose the difference into share gain, price, mix and acquisition.\n\n"
    )
    parts.append(_table(
        ["Field", "Content"],
        [
            ["Alignment", _clean(company.get("geography_period_align"), 200)],
            ["Company historical growth", _clean(company.get("historical_growth"), 160)],
            ["Basis", _clean(company.get("basis"), 160)],
        ],
    ))
    if decomp:
        parts.append("### Growth Decomposition\n\n")
        parts.append(_table(
            ["Driver", "Contribution", "Evidence"],
            [
                [
                    _clean(r.get("driver"), 30),
                    _clean(r.get("contribution"), 120),
                    _clean(r.get("evidence"), 160),
                ]
                for r in decomp if isinstance(r, dict)
            ],
        ))
    parts.append(
        "*If the accounts are in the data room, growth is computed — "
        '"Not available" is not acceptable.*\n\n'
    )
    parts.append("---\n\n")

    parts.append("## 5. Plan vs Market Multiple\n\n")
    parts.append(
        "Compare the plan's implied growth with the market rate and state the multiple. "
        "If several times faster, say so plainly.\n\n"
    )
    parts.append(_table(
        ["Field", "Content"],
        [
            ["Plan rate", _clean(plan.get("plan_rate"), 60)],
            ["Market rate", _clean(plan.get("market_rate"), 120)],
            ["Multiple", _clean(plan.get("multiple"), 80)],
            ["Plain English", _clean(plan.get("plain_english"), 280)],
            ["What must be true", _clean(plan.get("what_must_be_true"), 280)],
        ],
    ))
    parts.append(
        "*This section does not recommend invest or pass. "
        "Share gain = company growth − market growth on the matched perimeter.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
            ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
            [
                "Rationale",
                _clean(
                    spec.get("quality_reliance_rationale")
                    or "Limits stated in the sections above.",
                    300,
                ),
            ],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can sizing and share-gain conclusions rest on this work?\n\n"
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
