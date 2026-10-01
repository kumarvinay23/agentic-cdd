"""Compose DiligenceIQ Market Pricing — realised price & pricing power (prompt book).

List vs realised; named competitors; PVM bridge; observed response (not
elasticity unless measured); escalators. Distinguish % vs percentage-point.
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
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")

_ASP_LABEL = re.compile(
    r"(?:ASP|Avg\.?\s*Selling\s*Price|average\s+selling\s+price|realised\s+(?:net\s+)?price)",
    re.IGNORECASE,
)
_LIST_PRICE_LABEL = re.compile(
    r"(?:list\s+price|flagship\s+price|MRP|sticker\s+price)",
    re.IGNORECASE,
)
_DISCOUNT = re.compile(
    r"(?:discount|rebate|credit|surcharge)[^\d%]{0,30}?(?:~)?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
# Name + pricing cue only — numeric capture is deferred to _first_money (skips years).
_COMPETITOR_ANCHOR = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\b"
    r"[^.\n]{0,60}?(?:priced?\s+at|ASP|list\s+price|\blist\b|INR|USD|₹|\$)",
    re.IGNORECASE,
)
_INDUSTRY_ASP_LABEL = re.compile(
    r"(?:industry|peer|competitor)\s*(?:ASP|average)",
    re.IGNORECASE,
)
_CHURN = re.compile(
    r"(?:churn|downgrade|attrition)[^\d%]{0,40}?(?:~)?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_CHURN_FROM_TO = re.compile(
    r"(?:churn|downgrade|attrition)[^\d%]{0,40}?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%"
    r"[^\d%]{0,40}?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%",
    re.IGNORECASE,
)
_CUSTOMERS_AFFECTED = re.compile(
    r"(?:([\d,]+)\s+(?:customers?|accounts?|subscribers?)\s+"
    r"(?:affected|impacted|churned|downgraded))",
    re.IGNORECASE,
)
_ESCALATOR = re.compile(
    r"(?:escalat(?:or|ion)|indexation|CPI\s*link|price\s+adjustment\s+clause)",
    re.IGNORECASE,
)
_ESCALATOR_PCT = re.compile(
    r"(?:escalat\w+|indexation)[^\d%]{0,40}?(?:~)?"
    r"(\d{1,2}(?:[.,]\d+)?)\s*%\s*(?:of\s+)?(?:revenue|ARR|contracts?)?",
    re.IGNORECASE,
)
# Reject generic labels — competitor names must come from the data room, not an OEM list.
_UNNAMED_LABELS = frozenset({
    "industry", "peer", "peers", "competitor", "competitors", "alternative",
    "alternatives", "market", "avg", "average", "company", "target", "the",
})
_PROPER_NEAR_PRICE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,3})\b"
    r"[^.\n]{0,80}?(?:priced?\s+at|ASP|list\s+price|INR|USD|₹|\$)",
    re.IGNORECASE,
)
# Currency-anchored money; group1 after currency, group2 before trailing currency.
_MONEY_ANCHORED = re.compile(
    r"(?:INR\s*|USD\s*|₹\s*|\$\s*)(?:~)?"
    r"([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"|"
    r"(?:~)?([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)\s*(?:INR|USD)\b",
    re.IGNORECASE,
)
# Fallback numerals that look like prices (thousands separators or ≥3 digits), not bare years.
_MONEY_FALLBACK = re.compile(
    r"(?:~)?([\d]{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d{3,}(?:[.,]\d+)?)"
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


def _parse_num(raw: str) -> float | None:
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
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", s):
        # European thousands (1.234.567,89)
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
        # US thousands (1,234,567.89)
        s = s.replace(",", "")
    elif re.fullmatch(r"\d{1,2}(,\d{2})+,\d{3}(\.\d+)?", s):
        # Indian grouping (1,47,499)
        s = s.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", s) and "." not in s:
        # European decimal comma with 1–2 places only (12,5) — not 98,200
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _is_year_token(raw: str) -> bool:
    """True for 19xx/20xx calendar years — never treat as a price."""
    digits = re.sub(r"[^\d]", "", (raw or "").strip())
    return bool(re.fullmatch(r"(?:19|20)\d{2}", digits))


def _first_money(text: str, *, max_chars: int = 100) -> tuple[str, float] | None:
    """First price in window: prefer currency-anchored values; skip years.

    Fixes fragile scans that otherwise capture intermediate years
    (e.g. 'ASP increased in 2023 to $150' → 150, not 2023).
    """
    window = (text or "")[:max_chars]
    for m in _MONEY_ANCHORED.finditer(window):
        raw = m.group(1) or m.group(2)
        if not raw or _is_year_token(raw):
            continue
        val = _parse_num(raw)
        if val is not None:
            return raw, val
    for m in _MONEY_FALLBACK.finditer(window):
        raw = m.group(1)
        if not raw or _is_year_token(raw):
            continue
        val = _parse_num(raw)
        if val is not None:
            return raw, val
    return None


def _labelled_money(corpus: str, label_re: re.Pattern[str]) -> tuple[str, float] | None:
    m = label_re.search(corpus or "")
    if not m:
        return None
    return _first_money(corpus[m.end(): m.end() + 100])


def gather_market_pricing_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "customer": 1,
        "financial": 2,
        "deal_strategy": 3,
        "operations": 4,
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
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _realised_prices(corpus: str, legacy: dict[str, Any] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    asp = _labelled_money(corpus, _ASP_LABEL)
    list_p = _labelled_money(corpus, _LIST_PRICE_LABEL)
    disc_m = _DISCOUNT.search(corpus)

    asp_raw, asp_val = (asp[0], asp[1]) if asp else (None, None)
    list_raw, list_val = (list_p[0], list_p[1]) if list_p else (None, None)

    # Legacy price_points
    if isinstance(legacy, dict):
        for pp in (legacy.get("price_points") or [])[:4]:
            if not isinstance(pp, dict) or pp.get("value") is None:
                continue
            label = str(pp.get("label") or "price").lower()
            is_list = label in {"flagship", "list", "mrp", "opp"}
            rows.append({
                "service_or_segment": label,
                "period": pp.get("as_of") or "as stated",
                "list_price": (
                    f"{pp.get('unit', '')} {pp['value']:g} {_DOC_CITE}".strip()
                    if is_list
                    else _NA
                ),
                "realised_net_price": (
                    f"{pp.get('unit', '')} {pp['value']:g} {_DOC_CITE}".strip()
                    if not is_list
                    else _NA
                ),
                "notes": _clean(pp.get("raw"), 120) or _DOC_CITE,
            })

    if asp_val is not None and not any(
        "asp" in str(r.get("service_or_segment", "")).lower() for r in rows
    ):
        disc_note = ""
        if disc_m:
            # Discount off list is a relative % of list price — not percentage points.
            disc_note = (
                f"Discount/credit signal: {disc_m.group(1)}% of list "
                f"(percentage of list price, not percentage points) {_DOC_CITE}"
            )
        rows.insert(0, {
            "service_or_segment": "blended / ASP",
            "period": "as stated",
            "list_price": (
                f"{_fmt_num(list_raw)} {_DOC_CITE}" if list_raw else _NA
            ),
            "realised_net_price": f"{_fmt_num(asp_raw)} {_DOC_CITE}",
            "notes": disc_note or "Keep list and realised separate",
        })
    if list_val is not None and asp_val is not None and list_val > asp_val:
        gap_pct = (list_val - asp_val) / list_val * 100
        rows.append({
            "service_or_segment": "list vs realised gap",
            "period": "as stated",
            "list_price": f"{list_val:g} {_DOC_CITE}",
            "realised_net_price": f"{asp_val:g} {_DOC_CITE}",
            "notes": (
                f"List exceeds realised by ~{gap_pct:.1f}% "
                f"(relative percentage change on list base — not percentage points) {_COMPUTED}"
            ),
        })

    if not rows:
        rows.append({
            "service_or_segment": _info_request("service / segment"),
            "period": _info_request("period"),
            "list_price": _info_request("list price from invoices / ledger"),
            "realised_net_price": _info_request(
                "realised net price after discounts, credits, surcharges"
            ),
            "notes": "List and realised must stay separate",
        })
    return rows[:6]


def _is_named_competitor(name: str) -> bool:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return False
    if all(p.lower().rstrip(".,;:") in _UNNAMED_LABELS for p in parts):
        return False
    # Require at least one capitalised token (proper noun from the VDR)
    return any(p[:1].isupper() and p.lower() not in _UNNAMED_LABELS for p in parts)


def _competitor_comps(corpus: str, legacy: dict[str, Any] | None) -> list[dict[str, str]]:
    """Extract named competitors from VDR text only — no sector OEM allowlist.

    Price search starts *after* the name match inside a local window (not
    ``window[len(name):]``, which wrongly sliced from the pre-context).
    """
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(name: str, price: str | None) -> None:
        key = name.strip().lower()
        if not key or key in seen or not _is_named_competitor(name):
            return
        seen.add(key)
        rows.append({
            "competitor": name.strip(),
            "equivalent_service": _info_request(f"equivalent service spec vs {name.strip()}"),
            "their_price": (
                f"{_fmt_num(price)} {_DOC_CITE}"
                if price
                else _info_request(f"dated quote / published price for {name.strip()}")
            ),
            "date_or_source": _DOC_CITE,
            "notes": "Named comparator extracted from data room — unnamed peers are not acceptable",
        })

    span = corpus[:40_000]
    for m in _COMPETITOR_ANCHOR.finditer(span):
        name = m.group(1)
        # Window around match; price search begins after the name within that window.
        start_idx = max(0, m.start() - 40)
        end_idx = min(len(span), m.end() + 120)
        window = span[start_idx:end_idx]
        match_offset = m.start() - start_idx
        search_start = match_offset + len(name)
        money = _first_money(window[search_start:], max_chars=120)
        _add(name, money[0] if money else None)
        if len(rows) >= 5:
            break

    if len(rows) < 5:
        for m in _PROPER_NEAR_PRICE.finditer(span):
            name = m.group(1)
            if name.strip().lower() in seen:
                continue
            money = _first_money(span[m.end(): m.end() + 100], max_chars=100)
            _add(name, money[0] if money else None)
            if len(rows) >= 5:
                break

    # Reject unnamed industry ASP as a comparator row — flag as context only
    ind_label = _INDUSTRY_ASP_LABEL.search(corpus)
    ind_money = (
        _first_money(corpus[ind_label.end(): ind_label.end() + 80])
        if ind_label
        else None
    )
    if ind_money and not rows:
        rows.append({
            "competitor": _info_request("named competitor (unnamed industry ASP is not acceptable)"),
            "equivalent_service": _NA,
            "their_price": (
                f"Industry ASP ~{_fmt_num(ind_money[0])} — context only, "
                f"not a named comparator {_DOC_CITE}"
            ),
            "date_or_source": _DOC_CITE,
            "notes": "Unnamed comparator rejected for competitive comparison",
        })
    elif not rows:
        if isinstance(legacy, dict):
            for sig in (legacy.get("power_signals") or [])[:2]:
                if not isinstance(sig, str):
                    continue
                named = _PROPER_NEAR_PRICE.search(sig) or _COMPETITOR_ANCHOR.search(sig)
                if named and _is_named_competitor(named.group(1)):
                    rows.append({
                        "competitor": named.group(1),
                        "equivalent_service": _info_request("equivalent service specification"),
                        "their_price": _clean(sig, 120) + f" {_DOC_CITE}",
                        "date_or_source": _DOC_CITE,
                        "notes": "From pricing power extract — confirm dated quote",
                    })
        if not rows:
            rows.append({
                "competitor": _info_request("named competitor"),
                "equivalent_service": _info_request("equivalent service specification"),
                "their_price": _info_request("dated quote or published price"),
                "date_or_source": _NA,
                "notes": "Unnamed comparators are not acceptable",
            })
    return rows[:5]


def _pvm_bridge(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = _pick_sentences(
        sents,
        keywords=("price", "volume", "mix", "gross profit", "revenue bridge", "asp"),
        limit=4,
    )
    rows: list[dict[str, str]] = []
    for driver in ("price", "volume", "mix"):
        hit = next((h for h in hits if driver in h.lower()), None)
        rows.append({
            "leg": driver,
            "from_to": _info_request(f"{driver} contribution period-to-period"),
            "revenue_impact": (
                _clean(hit, 160) + f" {_DOC_CITE}" if hit else _info_request(f"{driver} revenue impact")
            ),
            "gross_profit_impact": _info_request(f"{driver} gross-profit impact"),
            "notes": "Reconcile legs to reported revenue and gross profit",
        })
    if not any("gross profit" in (h or "").lower() for h in hits):
        rows.append({
            "leg": "reconciliation",
            "from_to": _info_request("opening → closing gross profit"),
            "revenue_impact": _info_request("revenue bridge total"),
            "gross_profit_impact": _info_request("gross profit bridge total"),
            "notes": "Bridge must reconcile to reported P&L",
        })
    return rows[:5]


def _observed_response(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = _pick_sentences(
        sents,
        keywords=("price increase", "raised price", "hike", "churn", "downgrade", "volume"),
        limit=3,
    )
    from_to = _CHURN_FROM_TO.search(corpus)
    churn_m = _CHURN.search(corpus)
    cust_m = _CUSTOMERS_AFFECTED.search(corpus)
    rows: list[dict[str, str]] = []
    if hits or churn_m or cust_m or from_to:
        if from_to:
            a = _parse_num(from_to.group(1))
            b = _parse_num(from_to.group(2))
            if a is not None and b is not None:
                pp = b - a
                churn_note = (
                    f"Churn rate {a:g}% → {b:g}% "
                    f"(Δ {pp:+.1f} percentage points — absolute rate shift, "
                    f"not a relative % change) {_DOC_CITE}"
                )
            else:
                churn_note = (
                    f"{from_to.group(1)}% → {from_to.group(2)}% {_DOC_CITE} — "
                    f"label as percentage-point change between rates"
                )
        elif churn_m:
            # Single stated rate is a level (%), not a pp delta unless two rates exist.
            churn_note = (
                f"Churn/downgrade rate level: {churn_m.group(1)}% {_DOC_CITE} "
                f"(stated rate level — not a percentage-point change; "
                f"pp requires two rates)"
            )
        else:
            churn_note = _info_request("churn / downgrades in following periods")
        rows.append({
            "event": (
                _clean(hits[0], 160) + f" {_DOC_CITE}"
                if hits
                else _info_request("past price increase event")
            ),
            "customers_affected": (
                f"{cust_m.group(1)} customers {_DOC_CITE}"
                if cust_m
                else _info_request("number of customers affected")
            ),
            "churn_or_downgrade": churn_note,
            "volume_following": _info_request("volume in following periods"),
            "label": (
                "Observed response — not elasticity "
                "(no measured price-volume relationship evidenced)"
            ),
        })
    else:
        rows.append({
            "event": _info_request("past price increase with dated outcome"),
            "customers_affected": _info_request("number of customers affected"),
            "churn_or_downgrade": _info_request("churn / downgrades after the increase"),
            "volume_following": _info_request("volume in following periods"),
            "label": "Observed response — do not call this elasticity without a measured relationship",
        })
    return rows[:3]


def _escalators(corpus: str) -> dict[str, str]:
    has = bool(_ESCALATOR.search(corpus))
    pct_m = _ESCALATOR_PCT.search(corpus)
    if has:
        return {
            "present": f"Escalator / indexation language evidenced {_DOC_CITE}",
            "revenue_coverage": (
                f"{pct_m.group(1)}% of revenue/contracts {_DOC_CITE}"
                if pct_m
                else _info_request("proportion of revenue covered by escalators")
            ),
            "notes": (
                "State coverage as a percentage of revenue (not percentage points) "
                "unless comparing two rates."
            ),
        }
    return {
        "present": _info_request("whether contracts carry price escalators"),
        "revenue_coverage": _info_request("proportion of revenue covered by escalators"),
        "notes": "Distinguish % of revenue from percentage-point rate changes",
    }


def _pct_discipline_note() -> str:
    return (
        "Discipline: a **percentage change** is relative to a base "
        "(e.g. price up 5%); a **percentage-point** change is an absolute difference "
        "between two rates (e.g. churn 3% → 5% is +2 percentage points, not +2%). "
        "Label each figure accordingly."
    )


def _quality_reliance(
    *,
    realised_ok: bool,
    named_comps: int,
    has_response: bool,
) -> tuple[str, str, str]:
    if realised_ok and named_comps >= 1:
        return (
            "PASS",
            "READY" if has_response else "LIMITED",
            f"Realised pricing evidenced; {named_comps} named competitor row(s). "
            + ("Observed response present." if has_response else "Observed response incomplete."),
        )
    if realised_ok or named_comps >= 1:
        return "PASS", "LIMITED", "Partial pricing evidence — list/realised or named comps incomplete."
    return "PASS", "BLOCKED", "Insufficient realised pricing and named competitor evidence."


def _llm_market_pricing_spec(
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

    system = compose_system(
        "market_pricing",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "realised_prices: [{service_or_segment, period, list_price, realised_net_price, notes}],\n"
        "competitor_comparisons: [{competitor, equivalent_service, their_price, date_or_source, notes}] "
        "— competitor must be named; reject unnamed industry/peer rows,\n"
        "pvm_bridge: [{leg, from_to, revenue_impact, gross_profit_impact, notes}],\n"
        "observed_response: [{event, customers_affected, churn_or_downgrade, volume_following, label}] "
        "— label as observed response not elasticity unless measured,\n"
        "escalators: {present, revenue_coverage, notes},\n"
        "pct_vs_pp_note (string),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Distinguish percentage change from percentage-point change every time. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_market_pricing_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    realised = _realised_prices(corpus, legacy_spec)
    comps = _competitor_comps(corpus, legacy_spec)
    pvm = _pvm_bridge(corpus)
    response = _observed_response(corpus)
    escalators = _escalators(corpus)

    realised_ok = any(
        r.get("realised_net_price")
        and not str(r["realised_net_price"]).startswith("Information")
        and r["realised_net_price"] != _NA
        for r in realised
    )
    named = sum(
        1
        for r in comps
        if r.get("competitor")
        and not str(r["competitor"]).startswith("Information")
        and "unnamed" not in str(r.get("notes", "")).lower()
    )
    has_response = any(
        r.get("event") and not str(r["event"]).startswith("Information") for r in response
    )
    quality, reliance, qr = _quality_reliance(
        realised_ok=realised_ok,
        named_comps=named,
        has_response=has_response,
    )

    insight = (
        f"Market Pricing for {company}: realised vs list kept separate; "
        f"{named} named competitor comparison(s); "
        f"past increases labelled as observed response (not elasticity unless measured). "
        f"{_pct_discipline_note()}"
    )

    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    return {
        "insight_snapshot": insight,
        "realised_prices": realised,
        "competitor_comparisons": comps,
        "pvm_bridge": pvm,
        "observed_response": response,
        "escalators": escalators,
        "pct_vs_pp_note": _pct_discipline_note(),
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": "Market Pricing",
        "dd_code": legacy.get("dd_code") or "DD-17",
        "price_points": legacy.get("price_points") or [],
        "pricing_notes": legacy.get("pricing_notes") or [],
        "power_signals": legacy.get("power_signals") or [],
        "consumes_ceiling": legacy.get("consumes_ceiling"),
        "ceiling_sam": legacy.get("ceiling_sam"),
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    for key in ("realised_prices", "competitor_comparisons", "pvm_bridge", "observed_response"):
        if not isinstance(llm.get(key), list):
            llm[key] = []
    if not isinstance(llm.get("escalators"), dict):
        llm["escalators"] = {
            "present": _info_request("escalators"),
            "revenue_coverage": _info_request("revenue coverage"),
            "notes": _pct_discipline_note(),
        }

    # Drop unnamed competitor rows
    cleaned: list[dict[str, Any]] = []
    for row in llm.get("competitor_comparisons") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("competitor") or "").strip()
        if not name or not _is_named_competitor(name):
            continue
        cleaned.append(row)
    if not cleaned:
        cleaned = [{
            "competitor": _info_request("named competitor"),
            "equivalent_service": _info_request("equivalent service specification"),
            "their_price": _info_request("dated quote or published price"),
            "date_or_source": _NA,
            "notes": "Unnamed comparators are not acceptable",
        }]
    llm["competitor_comparisons"] = cleaned

    # Soften elasticity language to observed response
    for row in llm.get("observed_response") or []:
        if not isinstance(row, dict):
            continue
        label = str(row.get("label") or "")
        if re.search(r"\belasticity\b", label, re.I) and not re.search(
            r"measured|estimated\s+elasticity", label, re.I
        ):
            row["label"] = (
                "Observed response — not elasticity "
                "(no measured price-volume relationship evidenced)"
            )

    if not llm.get("pct_vs_pp_note"):
        llm["pct_vs_pp_note"] = _pct_discipline_note()

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else "PASS"
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else "LIMITED"

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Market Pricing"
    llm["dd_code"] = "DD-17"
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    for k in ("price_points", "pricing_notes", "power_signals", "consumes_ceiling", "ceiling_sam"):
        llm.setdefault(k, legacy.get(k))
    return llm


def build_market_pricing_spec(
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
    if corpus is None:
        gathered_corpus, gathered_sources = gather_market_pricing_corpus(deal, idx)
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
        vars_ = prompt_vars_from_deal(deal)
        llm = _llm_market_pricing_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=vars_.get("geography"),
            materiality=vars_.get("materiality"),
        )
        if llm:
            return _normalise_llm_spec(llm, sources=sources, legacy_spec=legacy_spec)

    return _heuristic_market_pricing_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy_spec,
    )


def render_market_pricing_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    realised = spec.get("realised_prices") if isinstance(spec.get("realised_prices"), list) else []
    comps = spec.get("competitor_comparisons") if isinstance(spec.get("competitor_comparisons"), list) else []
    pvm = spec.get("pvm_bridge") if isinstance(spec.get("pvm_bridge"), list) else []
    response = spec.get("observed_response") if isinstance(spec.get("observed_response"), list) else []
    escalators = spec.get("escalators") if isinstance(spec.get("escalators"), dict) else {}
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Realised Net Price\n\n")
    parts.append(
        "From invoices / billing ledger after discounts, credits and surcharges. "
        "**List price and realised price stay separate.**\n\n"
    )
    if realised:
        parts.append(_table(
            ["Service / Segment", "Period", "List Price", "Realised Net Price", "Notes"],
            [
                [
                    _clean(r.get("service_or_segment"), 60),
                    _clean(r.get("period"), 30),
                    _clean(r.get("list_price"), 80),
                    _clean(r.get("realised_net_price"), 80),
                    _clean(r.get("notes"), 160),
                ]
                for r in realised if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Named Competitor Comparisons\n\n")
    parts.append(
        "Equivalent service specification with dated quotes or published prices. "
        "**Unnamed comparators are not acceptable.**\n\n"
    )
    if comps:
        parts.append(_table(
            ["Competitor", "Equivalent Service", "Their Price", "Date / Source", "Notes"],
            [
                [
                    _clean(r.get("competitor"), 40),
                    _clean(r.get("equivalent_service"), 100),
                    _clean(r.get("their_price"), 80),
                    _clean(r.get("date_or_source"), 60),
                    _clean(r.get("notes"), 120),
                ]
                for r in comps if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Price–Volume–Mix Bridge\n\n")
    parts.append(
        "Period-to-period bridge reconciling to reported revenue and gross profit.\n\n"
    )
    if pvm:
        parts.append(_table(
            ["Leg", "From → To", "Revenue Impact", "Gross Profit Impact", "Notes"],
            [
                [
                    _clean(r.get("leg"), 30),
                    _clean(r.get("from_to"), 80),
                    _clean(r.get("revenue_impact"), 120),
                    _clean(r.get("gross_profit_impact"), 120),
                    _clean(r.get("notes"), 100),
                ]
                for r in pvm if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Observed Response to Past Price Increases\n\n")
    parts.append(
        "Churn, downgrades and volume in following periods, with customers affected. "
        "Describe as **observed response**, not elasticity, unless a measured relationship "
        "is evidenced. Distinguish % vs percentage-point changes.\n\n"
    )
    if response:
        parts.append(_table(
            ["Event", "Customers Affected", "Churn / Downgrade", "Volume Following", "Label"],
            [
                [
                    _clean(r.get("event"), 120),
                    _clean(r.get("customers_affected"), 60),
                    _clean(r.get("churn_or_downgrade"), 100),
                    _clean(r.get("volume_following"), 100),
                    _clean(r.get("label"), 120),
                ]
                for r in response if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Contract Escalators\n\n")
    parts.append(
        f"- **Present:** {_clean(escalators.get('present'), 200)}\n"
        f"- **Revenue coverage:** {_clean(escalators.get('revenue_coverage'), 160)}\n"
        f"- **Notes:** {_clean(escalators.get('notes'), 200)}\n\n"
    )
    if spec.get("pct_vs_pp_note"):
        parts.append(f"**% vs pp:** {_clean(spec.get('pct_vs_pp_note'), 400)}\n\n")
    parts.append(
        "*This section does not recommend invest or pass. "
        "A pricing-led growth plan is only credible if realised prices, named comps, "
        "and observed response support it.*\n\n"
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
        f"can a pricing-led plan rest on this evidence?\n\n"
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
