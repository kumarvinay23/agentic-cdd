"""Compose DiligenceIQ Revenue Quality — durability of revenue (prompt book).

Splits revenue into contracted recurring, behavioural recurring, one-off /
project, and pass-through. States contract share, weighted average remaining
term, and short-notice cancellation. Builds a period revenue bridge. Checks
recognition / cut-off. Sizes non-repeating items. Dual-writes legacy Revenue
Persistence Analysis fields (retention_metrics / revenue_mix / quality_flags /
quality_notes).

No invest/pass. No balance-sheet ratios. No company allowlists.
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

_DOCUMENT_TITLE = "Revenue Persistence Analysis"
_DD_CODE = "DD-09b"

_SPLIT_RULE = (
    "Revenue is split into recurring under contract, recurring by behaviour "
    "but not committed, project or one-off, and pass-through or rebilled — "
    "reconciled to total revenue."
)
_CONTRACT_RULE = (
    "Share under contract, weighted average remaining term, and the "
    "proportion cancellable at short notice are stated from the contracts."
)
_BRIDGE_RULE = (
    "A revenue bridge links periods: opening, new customers, expansion, "
    "price, contraction, churn, closing."
)
_RECOG_RULE = (
    "Recognition and cut-off are examined: timing vs delivery, deferred "
    "revenue, unbilled amounts, and any change in treatment across periods."
)
_NONREP_RULE = (
    "Revenue that will not repeat — one-off contracts, grants, rebates, "
    "non-recurring projects — is identified and sized."
)
_DURABILITY_RULE = (
    "This agent answers how much of the revenue is real and repeating. "
    "Balance-sheet ratios do not belong here."
)
_BILLING_RULE = (
    "Billed revenue is reconciled to recognised revenue — deferred, unbilled "
    "and cut-off differences are shown, not assumed away."
)
_TAXONOMY_RULE = (
    "Revenue is classified as contracted, cancellable, habitual (behavioural "
    "uncommitted), one-off / project, or pass-through — not a seller label alone."
)
_PVMA_RULE = (
    "The revenue bridge separates price, volume, mix and acquisition / new "
    "customers from expansion and churn."
)
_RENEWAL_RULE = (
    "Renewal and cancellation exposure are sized from contracts — remaining "
    "term and short-notice share alone are not enough."
)
_PIPELINE_RULE = (
    "Pipeline is kept separate from enforceable backlog; behavioural recurring "
    "is not treated as backlog."
)
_ARR_RULE = (
    "ARR / MRR is stated only when the definition and evidence are present — "
    "otherwise omitted or labelled as an information request."
)
_CROSS_CHECK_RULE = (
    "Revenue durability is cross-checked with Customer Stickiness and Cash Flow "
    "where those agents are available."
)
_RECURRING_NE_BACKLOG = (
    "Recurring by behaviour is not enforceable backlog."
)
_BILLING_CUE = re.compile(
    r"(?i)\b(billed|billing|invoiced|invoice\s+value|recognised|recognized|"
    r"deferred\s+revenue|unbilled|cut[- ]?off)\b"
)
_PIPELINE_CUE = re.compile(
    r"(?i)\b(pipeline|backlog|booked\s+not\s+billed|order\s+book|"
    r"committed\s+orders?|soft\s+pipeline)\b"
)
_ARR_CUE = re.compile(
    r"(?i)\b(ARR|MRR|annual\s+recurring\s+revenue|monthly\s+recurring\s+revenue)\b"
)
_ACQ_CUE = re.compile(
    r"(?i)\b(new\s+customers?|acquisition|acquired\s+revenue|logo\s+adds?|"
    r"new\s+logos?)\b"
)
_VOLUME_CUE = re.compile(
    r"(?i)\b(volume|units?\s+sold|quantity|same[- ]store|like[- ]for[- ]like)\b"
)
_MIX_CUE = re.compile(
    r"(?i)\b(mix|channel\s+mix|product\s+mix|segment\s+mix)\b"
)
_RENEWAL_CUE = re.compile(
    r"(?i)\b(renewal|renew(?:ed|ing)?|auto[- ]renew|cancellation\s+exposure|"
    r"at[- ]risk\s+renewal|upcoming\s+renewal)\b"
)

_GRR_RE = re.compile(r"(?i)Gross Revenue Retention\s*\(GRR\)\s+(\d+(?:\.\d+)?)%")
_NRR_RE = re.compile(r"(?i)Net Revenue Retention\s*\(NRR\)\s+(\d+(?:\.\d+)?)%")
_LOGO_CHURN_RE = re.compile(r"(?i)Logo Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")
_REV_CHURN_RE = re.compile(r"(?i)Revenue Churn\s*\(%\)\s+(\d+(?:\.\d+)?)%")
_FLEET_REV_RE = re.compile(r"(?i)Fleet segment\s*\((\d+(?:\.\d+)?)%\s+of revenue\)")
_FLEET_SHARE_RE = re.compile(r"(?i)Fleet Operator\s+(\d+(?:\.\d+)?)%")
_FLEET_TERM_RE = re.compile(
    r"(?i)Fleet.*?(\d+)\s*[–\-]\s*(\d+)\s*month(?:s)?\s+renewable\s+contracts?"
)
_REPEAT_RE = re.compile(
    r"(?i)Repeat\s*/\s*Referral\s+Purchase\s*\(%\)\s+"
    r"((?:N/A\s+)?(?:[\d.]+\s*%\s*){1,4})"
)
_REPEAT_ALT_RE = re.compile(
    r"(?i)(?:repeat|referral)\s+(?:purchase|rate)[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_ONLINE_RE = re.compile(r"(?i)Online Sales Share\s*\(%\)\s+(?:[\d.]+\s+%){0,2}\s*([\d.]+)\s*%")
_EMI_RE = re.compile(r"(?i)(~)?(\d+(?:\.\d+)?)%\s+of customers purchase via EMI")
_TERM_MONTHS_RE = re.compile(
    r"(?i)(\d+)\s*[–\-to]+\s*(\d+)\s*month(?:s)?\s+(?:renewable\s+)?(?:contract|agreement|term)"
)
_WART_RE = re.compile(
    r"(?i)(?:weighted\s+average\s+(?:remaining\s+)?term|WART|average\s+remaining\s+term)"
    r"[^.%]{0,40}?(\d+(?:\.\d+)?)\s*(months?|years?)"
)
_SHORT_NOTICE_RE = re.compile(
    r"(?i)(?:cancel(?:lable|lation)?|terminate|notice)\s+"
    r"(?:at\s+)?(?:short\s+notice|within\s+(\d+)\s*(?:days?|months?)|"
    r"(\d+)\s*(?:days?|months?)\s+notice)"
)
_DEFERRED_RE = re.compile(
    r"(?i)\b(deferred\s+revenue|contract\s+liabilit(?:y|ies)|unbilled\s+(?:revenue|receivable)|"
    r"accrued\s+revenue|revenue\s+recognition|cut[- ]?off|ASC\s*606|Ind\s*AS\s*115)\b"
)
_NONREP_CUE = re.compile(
    r"(?i)\b(one[- ]off|non[- ]recurring|grant|rebate|stimulus|project\s+revenue|"
    r"non[- ]repeat|spot\s+(?:sale|order)|launch\s+(?:cohort|promotion))\b"
)
_BALANCE_SHEET_CUE = re.compile(
    r"(?i)\b(current\s+ratio|debt\s*/\s*equity|quick\s+ratio|net\s+debt\s*/\s*ebitda|"
    r"interest\s+coverage|balance[- ]sheet\s+ratio)\b"
)
_INVEST_RE = re.compile(
    r"(?i)\b(invest|pass|buy|sell|recommendation|verdict|IC\s+decision)\b"
)
_BRIDGE_CUE = re.compile(
    r"(?i)\b(opening|new\s+customers?|expansion|contraction|churn|closing|"
    r"revenue\s+bridge|waterfall)\b"
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


def _pct(val: float | None) -> str:
    if val is None:
        return _NA
    return f"{val:g}%"


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def gather_revenue_quality_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "customer": 1,
        "deal_strategy": 2,
        "market_competition": 3,
        "operations": 4,
        "company_management": 5,
        "legal_esg": 6,
    }
    needles = (
        "retention", "churn", "revenue", "valuation", "nrr", "grr",
        "commercial", "recurring", "contract", "financial", "customer",
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


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _retention_from_corpus(text: str) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for regex, key in (
        (_GRR_RE, "grr_pct"),
        (_NRR_RE, "nrr_pct"),
        (_LOGO_CHURN_RE, "logo_churn_pct"),
        (_REV_CHURN_RE, "revenue_churn_pct"),
    ):
        m = regex.search(text or "")
        if m:
            metrics[key] = float(m.group(1))
    return metrics


def _extract_revenue_split(
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    fleet = None
    m = _FLEET_REV_RE.search(text) or _FLEET_SHARE_RE.search(text)
    if m:
        fleet = float(m.group(1))
    elif isinstance(legacy.get("revenue_mix"), dict):
        if legacy["revenue_mix"].get("fleet_revenue_pct") is not None:
            fleet = float(legacy["revenue_mix"]["fleet_revenue_pct"])

    repeat = None
    rm = _REPEAT_RE.search(text)
    if rm:
        # Prefer the latest in-series year (usually 3rd token before industry avg)
        nums = re.findall(r"(\d+(?:\.\d+)?)\s*%", rm.group(0))
        if len(nums) >= 2:
            # Drop trailing industry-avg when 4 values present (FY22/23/24 + avg)
            repeat = float(nums[-2] if len(nums) >= 3 else nums[-1])
        elif nums:
            repeat = float(nums[-1])
    if repeat is None:
        rm2 = _REPEAT_ALT_RE.search(text)
        if rm2:
            repeat = float(rm2.group(1))

    # Pass-through rarely present in EV packs — leave info request unless cued
    passthrough = None
    if re.search(r"(?i)pass[- ]through|rebill(?:ed|ing)?", text):
        pm = re.search(
            r"(?i)(?:pass[- ]through|rebill(?:ed|ing)?)\s*(?:revenue)?[^.%]{0,40}?"
            r"(\d+(?:\.\d+)?)\s*%",
            text,
        )
        if pm:
            passthrough = float(pm.group(1))

    contracted = fleet  # fleet agreements = recurring under contract
    behavioural = repeat  # repeat/referral without commitment
    known = (contracted or 0.0) + (behavioural or 0.0) + (passthrough or 0.0)
    one_off = max(0.0, 100.0 - known) if (contracted is not None or behavioural is not None) else None

    period = "FY2024E"
    rows: list[dict[str, Any]] = []
    buckets = [
        (
            "recurring_under_contract",
            contracted,
            "Fleet / B2B contracts renewable" if contracted is not None else None,
        ),
        (
            "recurring_behavioural",
            behavioural,
            "Repeat / referral purchase (uncommitted) — habitual, not backlog"
            if behavioural is not None else None,
        ),
        (
            "project_or_one_off",
            one_off,
            "Unit / product sales and other non-committed revenue" if one_off is not None else None,
        ),
        (
            "pass_through_or_rebilled",
            passthrough,
            "Pass-through / rebilled" if passthrough is not None else None,
        ),
    ]
    total = 0.0
    filled = 0
    for kind, pct, evidence in buckets:
        if pct is None:
            rows.append({
                "bucket": kind.replace("_", " "),
                "period": period,
                "share_pct": _info_request(f"{kind.replace('_', ' ')} share of revenue"),
                "amount": _NA,
                "evidence": _info_request(f"evidence for {kind.replace('_', ' ')}"),
                "source": _NA,
                "notes": _SPLIT_RULE,
            })
        else:
            filled += 1
            total += pct
            rows.append({
                "bucket": kind.replace("_", " "),
                "period": period,
                "share_pct": pct,
                "amount": _NA,
                "evidence": evidence or _DOC_CITE,
                "source": _DOC_CITE,
                "notes": _SPLIT_RULE,
            })

    reconcile = f"{total:g}% of labelled share"
    if filled >= 2 and abs(total - 100.0) < 0.6:
        reconcile = f"Reconciles to 100% ({total:g}%) {_COMPUTED}"
    elif filled >= 2:
        reconcile = (
            f"Labelled shares sum to {total:g}% — residual assigned to "
            f"project/one-off {_COMPUTED}"
        )
    else:
        reconcile = _info_request("full revenue split that reconciles to 100%")

    rows.append({
        "bucket": "reconcile_to_total",
        "period": period,
        "share_pct": reconcile if isinstance(reconcile, str) else total,
        "amount": _NA,
        "evidence": reconcile,
        "source": _COMPUTED if filled >= 2 else _NA,
        "notes": _SPLIT_RULE + " " + _DURABILITY_RULE,
    })
    return rows


def _extract_contract_terms(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []

    fleet_pct = None
    m = _FLEET_REV_RE.search(text) or _FLEET_SHARE_RE.search(text)
    if m:
        fleet_pct = float(m.group(1))

    term_lo = term_hi = None
    tm = _FLEET_TERM_RE.search(text) or _TERM_MONTHS_RE.search(text)
    if tm:
        term_lo, term_hi = int(tm.group(1)), int(tm.group(2))

    wart = None
    wm = _WART_RE.search(text)
    if wm:
        wart = f"{wm.group(1)} {wm.group(2)}"
    elif term_lo is not None and term_hi is not None:
        mid = (term_lo + term_hi) / 2
        wart = f"~{mid:g} months (midpoint of {term_lo}–{term_hi} month renewable fleet terms) {_COMPUTED}"

    short = _info_request("share cancellable at short notice")
    sm = _SHORT_NOTICE_RE.search(text)
    if sm:
        short = _clean(sm.group(0), 120)

    # Retail / consumer unit sales = largely cancellable pre-delivery / not under term
    short_share = None
    if fleet_pct is not None:
        short_share = max(0.0, 100.0 - fleet_pct)

    rows.append({
        "metric": "Share under contract",
        "value": _pct(fleet_pct) if fleet_pct is not None else _info_request(
            "share of revenue under enforceable contract"
        ),
        "detail": (
            f"Fleet / B2B contracted revenue ~{fleet_pct:g}% of total"
            if fleet_pct is not None else _NA
        ),
        "source": _DOC_CITE if fleet_pct is not None else _NA,
        "notes": _CONTRACT_RULE,
    })
    rows.append({
        "metric": "Weighted average remaining term",
        "value": wart or _info_request("weighted average remaining contract term"),
        "detail": (
            f"Fleet agreements {term_lo}–{term_hi} months renewable"
            if term_lo is not None else _NA
        ),
        "source": _DOC_CITE if (wart or term_lo) else _NA,
        "notes": _CONTRACT_RULE,
    })
    rows.append({
        "metric": "Cancellable at short notice",
        "value": (
            f"~{short_share:g}% not under multi-month fleet contract {_COMPUTED}"
            if short_share is not None
            else short
        ),
        "detail": short if _is_filled(short) and not short.startswith("Information") else (
            "Retail / one-off unit sales are not term-committed"
            if short_share is not None else _NA
        ),
        "source": _COMPUTED if short_share is not None else _NA,
        "notes": _CONTRACT_RULE,
    })
    return rows


def _extract_revenue_bridge(
    corpus: str,
    retention: dict[str, float],
) -> list[dict[str, str]]:
    text = _prose(corpus)
    grr = retention.get("grr_pct")
    nrr = retention.get("nrr_pct")
    rev_churn = retention.get("revenue_churn_pct")
    rows: list[dict[str, str]] = []

    # Bridge components as % of opening where retention metrics exist
    if grr is not None or nrr is not None or rev_churn is not None:
        churn_pct = rev_churn if rev_churn is not None else (
            max(0.0, 100.0 - grr) if grr is not None else None
        )
        expansion = None
        if nrr is not None and grr is not None:
            expansion = nrr - grr
        rows.extend([
            {
                "component": "Opening revenue",
                "value": "100% of prior-period retained base (index)",
                "period": "FY2023 → FY2024",
                "source": _COMPUTED,
                "notes": _BRIDGE_RULE,
            },
            {
                "component": "New customers / acquisition",
                "value": (
                    _clean(next((s for s in _sentences(text) if _ACQ_CUE.search(s)), ""), 120)
                    or _info_request("new-logo / acquisition revenue between periods")
                ),
                "period": "FY2023 → FY2024",
                "source": _DOC_CITE if _ACQ_CUE.search(text) else _NA,
                "notes": f"{_BRIDGE_RULE} {_PVMA_RULE}",
            },
            {
                "component": "Expansion",
                "value": (
                    f"~{expansion:g} pp (NRR − GRR) {_COMPUTED}"
                    if expansion is not None
                    else _info_request("expansion / upsell revenue")
                ),
                "period": "FY2023 → FY2024",
                "source": _COMPUTED if expansion is not None else _NA,
                "notes": _BRIDGE_RULE,
            },
            {
                "component": "Price",
                "value": _info_request("price contribution to the bridge"),
                "period": "FY2023 → FY2024",
                "source": _NA,
                "notes": f"{_BRIDGE_RULE} {_PVMA_RULE}",
            },
            {
                "component": "Volume",
                "value": (
                    _clean(next((s for s in _sentences(text) if _VOLUME_CUE.search(s)), ""), 120)
                    or _info_request("volume contribution to the bridge")
                ),
                "period": "FY2023 → FY2024",
                "source": _DOC_CITE if _VOLUME_CUE.search(text) else _NA,
                "notes": f"{_BRIDGE_RULE} {_PVMA_RULE}",
            },
            {
                "component": "Mix",
                "value": (
                    _clean(next((s for s in _sentences(text) if _MIX_CUE.search(s)), ""), 120)
                    or _info_request("mix contribution to the bridge")
                ),
                "period": "FY2023 → FY2024",
                "source": _DOC_CITE if _MIX_CUE.search(text) else _NA,
                "notes": f"{_BRIDGE_RULE} {_PVMA_RULE}",
            },
            {
                "component": "Contraction",
                "value": _info_request("contraction / downsell between periods"),
                "period": "FY2023 → FY2024",
                "source": _NA,
                "notes": _BRIDGE_RULE,
            },
            {
                "component": "Churn",
                "value": (
                    f"Revenue churn ~{churn_pct:g}% / GRR {grr:g}%"
                    if churn_pct is not None and grr is not None
                    else (
                        f"Revenue churn ~{churn_pct:g}%"
                        if churn_pct is not None
                        else _info_request("churn between periods")
                    )
                ),
                "period": "FY2023 → FY2024",
                "source": _DOC_CITE if churn_pct is not None else _NA,
                "notes": _BRIDGE_RULE,
            },
            {
                "component": "Closing revenue",
                "value": (
                    f"NRR {nrr:g}% of opening base (net of expansion/churn)"
                    if nrr is not None
                    else _info_request("closing revenue after bridge")
                ),
                "period": "FY2024",
                "source": _DOC_CITE if nrr is not None else _NA,
                "notes": _BRIDGE_RULE,
            },
        ])
    else:
        # Look for explicit bridge language
        for s in _sentences(text):
            if _BRIDGE_CUE.search(s) and re.search(r"\d", s):
                rows.append({
                    "component": "Bridge evidence",
                    "value": _clean(s, 180),
                    "period": _NA,
                    "source": _DOC_CITE,
                    "notes": _BRIDGE_RULE,
                })
                if len(rows) >= 4:
                    break
        if not rows:
            for comp in (
                "Opening revenue", "New customers / acquisition", "Expansion",
                "Price", "Volume", "Mix", "Contraction", "Churn", "Closing revenue",
            ):
                rows.append({
                    "component": comp,
                    "value": _info_request(f"{comp.lower()} for the period bridge"),
                    "period": _NA,
                    "source": _NA,
                    "notes": _BRIDGE_RULE,
                })
    return rows[:10]


def _extract_recognition(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    sents = _sentences(text)
    rows: list[dict[str, str]] = []
    for s in sents:
        if not _DEFERRED_RE.search(s):
            continue
        rows.append({
            "topic": "Recognition / cut-off",
            "finding": _clean(s, 180),
            "deferred_or_unbilled": (
                "Deferred / unbilled mentioned"
                if re.search(r"(?i)deferred|unbilled", s) else _NA
            ),
            "treatment_change": (
                "Possible change in treatment"
                if re.search(r"(?i)change|adopt|transition", s) else _NA
            ),
            "source": _DOC_CITE,
            "notes": _RECOG_RULE,
        })
        if len(rows) >= 4:
            break
    if not rows:
        rows.append({
            "topic": "Recognition timing vs delivery",
            "finding": _info_request(
                "when revenue is recognised relative to delivery / acceptance"
            ),
            "deferred_or_unbilled": _info_request("deferred revenue and unbilled balances"),
            "treatment_change": _info_request(
                "any change in recognition treatment across periods"
            ),
            "source": _NA,
            "notes": _RECOG_RULE,
        })
    return rows


def _extract_non_repeating(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    sents = _sentences(text)
    rows: list[dict[str, str]] = []
    for s in sents:
        if not _NONREP_CUE.search(s):
            continue
        # Skip balance-sheet noise
        if _BALANCE_SHEET_CUE.search(s):
            continue
        kind = "one_off"
        low = s.lower()
        if "grant" in low:
            kind = "grant"
        elif "rebate" in low:
            kind = "rebate"
        elif "project" in low:
            kind = "non_recurring_project"
        size = _NA
        sm = re.search(
            r"(?i)(INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr|crore)?|\d+(?:\.\d+)?\s*%|"
            r"\$[\d,]+)",
            s,
        )
        if sm:
            size = sm.group(1)
        rows.append({
            "item": _clean(s, 160),
            "kind": kind,
            "size": size,
            "will_repeat": "No — treat as non-repeating",
            "source": _DOC_CITE,
            "notes": _NONREP_RULE,
        })
        if len(rows) >= 5:
            break
    if not rows:
        rows.append({
            "item": _info_request(
                "one-off contracts, grants, rebates or non-recurring projects"
            ),
            "kind": "unknown",
            "size": _NA,
            "will_repeat": _NA,
            "source": _NA,
            "notes": _NONREP_RULE,
        })
    return rows


def _legacy_dual_write(
    *,
    retention: dict[str, float],
    split: list[dict],
    bridge: list[dict],
    corpus: str,
    legacy: dict[str, Any],
) -> tuple[dict[str, float], dict[str, float], list[str], list[str]]:
    metrics = dict(retention)
    for k, v in (legacy.get("retention_metrics") or {}).items():
        if k not in metrics and isinstance(v, (int, float)):
            metrics[k] = float(v)

    mix: dict[str, float] = {}
    text = _prose(corpus)
    online = _ONLINE_RE.search(text)
    if online:
        mix["online_sales_pct"] = float(online.group(1))
    emi = _EMI_RE.search(text)
    if emi:
        mix["emi_customer_pct"] = float(emi.group(2))
    for row in split:
        if not isinstance(row, dict):
            continue
        bucket = str(row.get("bucket") or "").lower()
        pct = row.get("share_pct")
        if not isinstance(pct, (int, float)):
            continue
        if "under contract" in bucket:
            mix["fleet_revenue_pct"] = float(pct)
        elif "behavioural" in bucket:
            mix["repeat_purchase_pct"] = float(pct)
        elif "one.off" in bucket or "one off" in bucket or "project" in bucket:
            mix["one_off_revenue_pct"] = float(pct)
    for k, v in (legacy.get("revenue_mix") or {}).items():
        if k not in mix and isinstance(v, (int, float)):
            mix[k] = float(v)

    flags: list[str] = []
    if metrics.get("nrr_pct") is not None and metrics["nrr_pct"] < 90:
        flags.append(f"NRR {metrics['nrr_pct']:g}% below 90% durability threshold.")
    if metrics.get("logo_churn_pct") is not None and metrics["logo_churn_pct"] > 30:
        flags.append(
            f"Logo churn {metrics['logo_churn_pct']:g}% elevated vs typical benchmarks."
        )
    if metrics.get("grr_pct") is not None and metrics.get("nrr_pct") is not None:
        flags.append(
            f"Expansion uplift (NRR−GRR) ~{metrics['nrr_pct'] - metrics['grr_pct']:g} pp."
        )
    for f in (legacy.get("quality_flags") or [])[:3]:
        if isinstance(f, str) and f.strip() and f not in flags:
            flags.append(_soften_invest(_clean(f, 200)))

    notes: list[str] = [_DURABILITY_RULE, _SPLIT_RULE]
    for b in bridge[:2]:
        if isinstance(b, dict) and _is_filled(b.get("value")):
            if not str(b.get("value")).startswith("Information"):
                notes.append(_clean(f"{b.get('component')}: {b.get('value')}", 200))
    for n in (legacy.get("quality_notes") or [])[:3]:
        if isinstance(n, str) and n.strip() and not _BALANCE_SHEET_CUE.search(n):
            notes.append(_soften_invest(_clean(n, 220)))
    return metrics, mix, flags[:6], notes[:8]


def _extract_billing_recognised(corpus: str, recognition: list[dict]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for s in _sentences(text):
        if not _BILLING_CUE.search(s):
            continue
        if not re.search(r"(?i)billed|invoic|recognised|recognized|deferred|unbilled", s):
            continue
        rows.append({
            "line": _clean(s, 80),
            "billed": (
                _clean(s, 100) if re.search(r"(?i)bill|invoic", s) else _info_request("billed amount")
            ),
            "recognised": (
                _clean(s, 100)
                if re.search(r"(?i)recognised|recognized|deferred|unbilled", s)
                else _info_request("recognised amount")
            ),
            "difference": _info_request("billed − recognised / deferred / unbilled variance"),
            "source": _DOC_CITE,
            "notes": _BILLING_RULE,
        })
        if len(rows) >= 4:
            break
    # Fold recognition findings
    for r in recognition:
        if not isinstance(r, dict):
            continue
        if not _is_filled(r.get("finding")) or str(r.get("finding")).startswith("Information"):
            continue
        rows.append({
            "line": _clean(r.get("topic") or "Recognition", 60),
            "billed": _info_request("billed amount for this line"),
            "recognised": _clean(r.get("finding"), 120),
            "difference": _clean(r.get("deferred_or_unbilled"), 80),
            "source": str(r.get("source") or _DOC_CITE),
            "notes": _BILLING_RULE,
        })
        if len(rows) >= 6:
            break
    if not rows:
        rows.append({
            "line": "Total revenue",
            "billed": _info_request("billed / invoiced revenue"),
            "recognised": _info_request("recognised revenue"),
            "difference": _info_request("deferred / unbilled / cut-off variance"),
            "source": _NA,
            "notes": _BILLING_RULE,
        })
    return rows[:6]


def _extract_revenue_taxonomy(
    split: list[dict],
    contracts: list[dict],
) -> list[dict[str, Any]]:
    """Map split + contracts into contracted / cancellable / habitual / one-off / pass-through."""
    rows: list[dict[str, Any]] = []
    mapping = {
        "under contract": "contracted",
        "behavioural": "habitual",
        "one_off": "one_off",
        "one-off": "one_off",
        "project": "one_off",
        "pass": "pass_through",
    }
    for r in split:
        if not isinstance(r, dict):
            continue
        bucket = str(r.get("bucket") or "").lower()
        if "reconcile" in bucket:
            continue
        tax = "other"
        for needle, label in mapping.items():
            if needle in bucket:
                tax = label
                break
        share = r.get("share_pct")
        rows.append({
            "taxonomy": tax,
            "bucket": _clean(r.get("bucket"), 40),
            "share_pct": share,
            "evidence": _clean(r.get("evidence"), 120),
            "source": str(r.get("source") or _NA),
            "notes": f"{_TAXONOMY_RULE} {_RECURRING_NE_BACKLOG}",
        })
    # Explicit cancellable from contract terms
    cancel = next(
        (
            c for c in contracts
            if isinstance(c, dict) and "cancellable" in str(c.get("metric") or "").lower()
        ),
        None,
    )
    if cancel:
        rows.append({
            "taxonomy": "cancellable",
            "bucket": "cancellable at short notice",
            "share_pct": cancel.get("value"),
            "evidence": _clean(cancel.get("detail"), 120),
            "source": str(cancel.get("source") or _NA),
            "notes": f"{_TAXONOMY_RULE} {_RENEWAL_RULE}",
        })
    if not rows:
        for tax in ("contracted", "cancellable", "habitual", "one_off", "pass_through"):
            rows.append({
                "taxonomy": tax,
                "bucket": tax,
                "share_pct": _info_request(f"{tax} share of revenue"),
                "evidence": _NA,
                "source": _NA,
                "notes": _TAXONOMY_RULE,
            })
    return rows[:8]


def _extract_renewal_cancellation(
    contracts: list[dict],
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        metric = str(c.get("metric") or "")
        rows.append({
            "exposure": metric,
            "value": _clean(c.get("value"), 100),
            "detail": _clean(c.get("detail"), 120),
            "source": str(c.get("source") or _NA),
            "notes": _RENEWAL_RULE,
        })
    for s in _sentences(text):
        if not _RENEWAL_CUE.search(s):
            continue
        rows.append({
            "exposure": "Renewal / cancellation evidence",
            "value": _clean(s, 120),
            "detail": _clean(s, 160),
            "source": _DOC_CITE,
            "notes": _RENEWAL_RULE,
        })
        if len(rows) >= 6:
            break
    if len(rows) < 2:
        rows.append({
            "exposure": "Upcoming renewal book",
            "value": _info_request("renewal schedule / at-risk renewal $"),
            "detail": _NA,
            "source": _NA,
            "notes": _RENEWAL_RULE,
        })
        rows.append({
            "exposure": "Cancellation exposure",
            "value": _info_request("cancellation $ / short-notice share"),
            "detail": _NA,
            "source": _NA,
            "notes": _RENEWAL_RULE,
        })
    return rows[:8]


def _extract_pipeline_vs_backlog(corpus: str) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in _sentences(text):
        if not _PIPELINE_CUE.search(s):
            continue
        has_pipe = bool(re.search(r"(?i)\bpipeline|soft\s+pipeline\b", s))
        has_back = bool(
            re.search(r"(?i)\bbacklog|booked\s+not\s+billed|committed\s+orders?\b", s)
        )
        kinds: list[str] = []
        if has_pipe:
            kinds.append("pipeline")
        if has_back:
            kinds.append("backlog")
        if not kinds:
            kinds.append("pipeline")
        for kind in kinds:
            if kind in seen:
                continue
            seen.add(kind)
            rows.append({
                "kind": kind,
                "finding": _clean(s, 160),
                "enforceable": (
                    "Yes — treat as backlog"
                    if kind == "backlog"
                    else "No — pipeline / soft; not enforceable backlog"
                ),
                "source": _DOC_CITE,
                "notes": f"{_PIPELINE_RULE} {_RECURRING_NE_BACKLOG}",
            })
        if len(rows) >= 4:
            break
    if "pipeline" not in seen:
        rows.append({
            "kind": "pipeline",
            "finding": _info_request("sales pipeline (non-enforceable)"),
            "enforceable": "No — pipeline is not backlog",
            "source": _NA,
            "notes": _PIPELINE_RULE,
        })
    if "backlog" not in seen:
        rows.append({
            "kind": "backlog",
            "finding": _info_request("enforceable backlog / booked orders"),
            "enforceable": "Yes if contracted and cancellable terms allow",
            "source": _NA,
            "notes": f"{_PIPELINE_RULE} {_RECURRING_NE_BACKLOG}",
        })
    return rows[:6]


def _arr_discipline(corpus: str, retention: dict[str, float]) -> dict[str, Any]:
    del retention
    text = _prose(corpus)
    hit = _ARR_CUE.search(text)
    if not hit:
        return {
            "stated": False,
            "metric": _NA,
            "definition": _info_request("ARR/MRR definition (if used)"),
            "value": _NA,
            "source": _NA,
            "notes": _ARR_RULE,
        }
    sent = next((s for s in _sentences(text) if _ARR_CUE.search(s)), hit.group(0))
    # Explicit denial / absence of a definition is not "defined"
    denied = bool(
        re.search(
            r"(?i)\b(no|not|without|absent|missing|undefined)\b.{0,40}\b"
            r"(ARR|MRR|defin(?:ed|ition))\b"
            r"|\b(ARR|MRR)\b.{0,40}\b(no|not|undefined|missing)\b.{0,20}\bdefin",
            sent,
        )
    )
    if denied:
        return {
            "stated": False,
            "metric": "ARR" if re.search(r"(?i)\bARR\b", sent) else "MRR",
            "definition": _info_request("ARR/MRR definition (if used)"),
            "value": _NA,
            "source": _DOC_CITE,
            "notes": _ARR_RULE,
            "definition_present": False,
        }
    val = _NA
    vm = re.search(r"(?i)(?:ARR|MRR)[^.%]{0,40}?([\d,]+(?:\.\d+)?\s*(?:Cr|cr|mn|m|bn)?)", sent)
    if vm:
        val = _clean(vm.group(0), 80)
    defined = bool(
        re.search(r"(?i)\b(defined\s+as|definition\s*[:=]|means|equals|calculated\s+as)\b", sent)
    )
    return {
        "stated": True,
        "metric": "ARR" if re.search(r"(?i)\bARR\b", sent) else "MRR",
        "definition": (
            _clean(sent, 160) if defined
            else _info_request("ARR/MRR definition — metric named but not defined")
        ),
        "value": val if defined else _info_request("ARR/MRR value only after definition evidenced"),
        "source": _DOC_CITE,
        "notes": _ARR_RULE,
        "definition_present": defined,
    }


def _cross_check_stickiness_cash_flow(
    *,
    stickiness_spec: dict[str, Any] | None,
    cash_flow_spec: dict[str, Any] | None,
    retention: dict[str, float],
) -> dict[str, Any]:
    stick_present = isinstance(stickiness_spec, dict) and bool(stickiness_spec)
    cf_present = isinstance(cash_flow_spec, dict) and bool(cash_flow_spec)
    aligned: list[str] = []
    conflicts: list[str] = []

    if stick_present:
        s_ret = stickiness_spec.get("retention_metrics") if isinstance(
            stickiness_spec.get("retention_metrics"), dict
        ) else {}
        # Also check common stickiness keys
        for key in ("nrr_pct", "grr_pct", "logo_churn_pct"):
            rq_v = retention.get(key)
            st_v = s_ret.get(key) if isinstance(s_ret, dict) else None
            if st_v is None and isinstance(stickiness_spec.get(key), (int, float)):
                st_v = stickiness_spec.get(key)
            if rq_v is not None and st_v is not None:
                try:
                    if abs(float(rq_v) - float(st_v)) > 5.0:
                        conflicts.append(
                            f"{key}: Revenue Quality {rq_v} vs Stickiness {st_v}"
                        )
                    else:
                        aligned.append(f"{key} aligned with Stickiness ({rq_v})")
                except (TypeError, ValueError):
                    pass
        if not aligned and not conflicts:
            aligned.append("Stickiness present — no overlapping retention keys to compare yet.")
    if cf_present:
        metrics = cash_flow_spec.get("cash_metrics") if isinstance(
            cash_flow_spec.get("cash_metrics"), dict
        ) else {}
        wc = cash_flow_spec.get("working_capital")
        if metrics or wc:
            aligned.append("Cash Flow present — durability cross-check available.")
        else:
            conflicts.append(
                "Cash Flow present but thin (no cash_metrics / working_capital) for reconcile."
            )

    return {
        "stickiness_present": stick_present,
        "cash_flow_present": cf_present,
        "aligned": aligned[:6],
        "conflicts": conflicts[:6],
        "notes": (
            f"{_CROSS_CHECK_RULE} "
            + (
                f"{len(conflicts)} conflict(s)."
                if conflicts
                else (
                    "No conflicts detected."
                    if stick_present or cf_present
                    else "Stickiness and Cash Flow not available in this run."
                )
            )
        ),
        "source": _DOC_CITE if (stick_present or cf_present) else _NA,
    }


def _rq_evidence_qa(
    *,
    billing: list[dict[str, Any]],
    taxonomy: list[dict[str, Any]],
    bridge: list[dict],
    renewals: list[dict[str, Any]],
    pipeline: list[dict[str, Any]],
    arr: dict[str, Any],
    cross: dict[str, Any],
    split: list[dict],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    bill_ok = any(
        isinstance(r, dict)
        and (
            (
                _is_filled(r.get("recognised"))
                and not str(r.get("recognised")).startswith("Information")
            )
            or (
                _is_filled(r.get("billed"))
                and not str(r.get("billed")).startswith("Information")
            )
        )
        for r in billing
    )
    rows.append({
        "check": "billing_recognised_reconcile",
        "status": "PASS" if bill_ok else "FAIL",
        "finding": (
            "Billing / recognition evidence present"
            if bill_ok
            else _info_request("billed ↔ recognised reconcile (deferred / unbilled)")
        ),
        "action": _BILLING_RULE,
    })

    tax_filled = {
        str(r.get("taxonomy") or "")
        for r in taxonomy
        if isinstance(r, dict)
        and (
            isinstance(r.get("share_pct"), (int, float))
            or (
                _is_filled(r.get("share_pct"))
                and not str(r.get("share_pct")).startswith("Information")
            )
        )
    }
    need = {"contracted", "habitual", "one_off", "cancellable"}
    tax_ok = len(tax_filled & need) >= 2
    rows.append({
        "check": "revenue_taxonomy",
        "status": "PASS" if tax_ok else "FAIL",
        "finding": (
            f"Taxonomy buckets filled: {', '.join(sorted(tax_filled)) or 'none'}"
            if tax_ok
            else _info_request("contracted / cancellable / habitual / one-off taxonomy")
        ),
        "action": _TAXONOMY_RULE,
    })

    pvma = {"Price", "Volume", "Mix", "New customers / acquisition", "New customers"}
    pvma_ok = sum(
        1 for b in bridge
        if isinstance(b, dict)
        and str(b.get("component") or "") in pvma
        and _is_filled(b.get("value"))
        and not str(b.get("value")).startswith("Information")
    )
    rows.append({
        "check": "price_volume_mix_acquisition",
        "status": "PASS" if pvma_ok >= 1 else "FAIL",
        "finding": (
            f"{pvma_ok} price/volume/mix/acquisition bridge component(s)"
            if pvma_ok >= 1
            else _info_request("price / volume / mix / acquisition bridge drivers")
        ),
        "action": _PVMA_RULE,
    })

    ren_ok = sum(
        1 for r in renewals
        if isinstance(r, dict)
        and _is_filled(r.get("value"))
        and not str(r.get("value")).startswith("Information")
    )
    rows.append({
        "check": "renewal_cancellation_exposure",
        "status": "PASS" if ren_ok >= 1 else "FAIL",
        "finding": (
            f"{ren_ok} renewal / cancellation exposure row(s)"
            if ren_ok >= 1
            else _info_request("renewal schedule and cancellation exposure")
        ),
        "action": _RENEWAL_RULE,
    })

    pipe_ok = any(
        isinstance(r, dict)
        and r.get("kind") in {"pipeline", "backlog"}
        and _is_filled(r.get("finding"))
        and not str(r.get("finding")).startswith("Information")
        for r in pipeline
    )
    # Also PASS if explicit separation rule is present with kinds
    kinds = {str(r.get("kind") or "") for r in pipeline if isinstance(r, dict)}
    rows.append({
        "check": "pipeline_vs_backlog",
        "status": "PASS" if pipe_ok or ({"pipeline", "backlog"} <= kinds) else "FAIL",
        "finding": (
            "Pipeline kept separate from backlog"
            if pipe_ok or ({"pipeline", "backlog"} <= kinds)
            else _info_request("pipeline vs enforceable backlog")
        ),
        "action": _PIPELINE_RULE,
    })

    if arr.get("stated") and not arr.get("definition_present"):
        arr_status = "FAIL"
        arr_finding = _info_request("ARR/MRR definition before stating the metric")
    else:
        arr_status = "PASS"
        arr_finding = (
            _ARR_RULE if not arr.get("stated")
            else f"{arr.get('metric')} stated with definition"
        )
    rows.append({
        "check": "arr_discipline",
        "status": arr_status,
        "finding": arr_finding,
        "action": _ARR_RULE,
    })

    cross_ok = (
        (cross.get("stickiness_present") or cross.get("cash_flow_present"))
        and not cross.get("conflicts")
    )
    rows.append({
        "check": "stickiness_cash_flow_cross_check",
        "status": "PASS" if cross_ok else "FAIL",
        "finding": (
            "; ".join(cross.get("aligned") or [])[:200]
            if cross_ok
            else (
                "; ".join(cross.get("conflicts") or [])[:200]
                if cross.get("conflicts")
                else _info_request("Stickiness + Cash Flow outputs for cross-check")
            )
        ),
        "action": _CROSS_CHECK_RULE,
    })

    # Recurring ≠ backlog: FAIL if habitual/behavioural labelled as backlog
    bad = any(
        isinstance(r, dict)
        and (
            "behavioural" in str(r.get("bucket") or "").lower()
            or str(r.get("taxonomy") or "") == "habitual"
        )
        and re.search(r"(?i)\bbacklog\b", str(r.get("evidence") or "") + str(r.get("notes") or ""))
        and "not backlog" not in str(r.get("evidence") or "").lower()
        and "not backlog" not in str(r.get("notes") or "").lower()
        for r in list(split) + list(taxonomy)
    )
    rows.append({
        "check": "recurring_ne_enforceable_backlog",
        "status": "FAIL" if bad else "PASS",
        "finding": (
            "Behavioural recurring incorrectly treated as backlog"
            if bad
            else _RECURRING_NE_BACKLOG
        ),
        "action": _RECURRING_NE_BACKLOG,
    })
    return rows


def _questions_from_rq_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("rq_evidence_qa")
        if isinstance(spec.get("rq_evidence_qa"), list)
        else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("billing_recognised_reconcile"):
        out.append(normalize_question({
            "question": "Provide billed ↔ recognised revenue reconcile with deferred/unbilled",
            "required_records": "Billing ledger + revenue recognition schedule",
            "decision_effect": "Durability cannot rest on unreconciled recognition",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "billing_recognised_reconcile QA PASS",
            "interim_treatment": "BLOCKED — do not invent recognition bridges",
        }))
    if _qa_fail("revenue_taxonomy"):
        out.append(normalize_question({
            "question": "Classify revenue as contracted / cancellable / habitual / one-off / pass-through",
            "required_records": "Contract register + revenue by durability bucket",
            "decision_effect": "Seller labels misstate the multiple",
            "priority": "signing_condition",
            "owner": "financial / commercial diligence",
            "timing": "per deal timetable",
            "closure_test": "revenue_taxonomy QA PASS",
            "interim_treatment": "LIMITED — withhold durability claims",
        }))
    if _qa_fail("price_volume_mix_acquisition"):
        out.append(normalize_question({
            "question": "Complete the revenue bridge with price, volume, mix and acquisition",
            "required_records": "Period bridge with driver pack",
            "decision_effect": "NRR alone does not explain growth quality",
            "priority": "signing_condition",
            "owner": "financial diligence lead",
            "timing": "per deal timetable",
            "closure_test": "price_volume_mix_acquisition QA PASS",
            "interim_treatment": "LIMITED — flag bridge as incomplete",
        }))
    if _qa_fail("renewal_cancellation_exposure"):
        out.append(normalize_question({
            "question": "Size renewal book and cancellation / short-notice exposure",
            "required_records": "Contract renewal schedule + termination terms",
            "decision_effect": "Near-term cancellation risk is untested",
            "priority": "signing_condition",
            "owner": "commercial diligence lead",
            "timing": "before IC",
            "closure_test": "renewal_cancellation_exposure QA PASS",
            "interim_treatment": "LIMITED — treat renewals as at risk",
        }))
    if _qa_fail("pipeline_vs_backlog"):
        out.append(normalize_question({
            "question": "Separate sales pipeline from enforceable backlog",
            "required_records": "Order book / backlog vs CRM pipeline",
            "decision_effect": "Soft pipeline must not be valued as backlog",
            "priority": "mandatory_pre_decision",
            "owner": "commercial diligence lead",
            "timing": "before IC",
            "closure_test": "pipeline_vs_backlog QA PASS",
            "interim_treatment": "Strip pipeline from backlog claims",
        }))
    if _qa_fail("arr_discipline"):
        out.append(normalize_question({
            "question": "Define ARR/MRR with calculation evidence or remove the metric",
            "required_records": "ARR definition memo + bridge to recognised revenue",
            "decision_effect": "Undefined ARR misstates recurring revenue",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "arr_discipline QA PASS",
            "interim_treatment": "Omit ARR until defined",
        }))
    if _qa_fail("stickiness_cash_flow_cross_check"):
        out.append(normalize_question({
            "question": "Supply Stickiness and Cash Flow outputs to cross-check durability",
            "required_records": "Customer Stickiness + Cash Flow agent specs",
            "decision_effect": "Retention / cash conflicts undermine revenue quality",
            "priority": "signing_condition",
            "owner": "financial diligence lead",
            "timing": "per deal timetable",
            "closure_test": "stickiness_cash_flow_cross_check QA PASS",
            "interim_treatment": "LIMITED until cross-check complete",
        }))
    if _qa_fail("recurring_ne_enforceable_backlog"):
        out.append(normalize_question({
            "question": "Remove behavioural recurring from backlog; keep as habitual only",
            "required_records": "Contract vs behavioural revenue split",
            "decision_effect": "Habitual revenue is not enforceable backlog",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "recurring_ne_enforceable_backlog QA PASS",
            "interim_treatment": "REWORK — strip backlog label from habitual",
        }))
    return out


def _quality_reliance(
    *,
    split: list[dict],
    contracts: list[dict],
    bridge: list[dict],
    recognition: list[dict],
    nonrep: list[dict],
) -> tuple[str, str, str]:
    split_filled = sum(
        1 for r in split
        if isinstance(r, dict)
        and isinstance(r.get("share_pct"), (int, float))
        and "reconcile" not in str(r.get("bucket") or "").lower()
    )
    contract_filled = any(
        isinstance(r, dict) and _is_filled(r.get("value"))
        and not str(r.get("value")).startswith("Information")
        for r in contracts
    )
    bridge_filled = any(
        isinstance(r, dict) and _is_filled(r.get("value"))
        and not str(r.get("value")).startswith("Information")
        and r.get("component") in {"Churn", "Expansion", "Closing revenue"}
        for r in bridge
    )
    recog_filled = any(
        isinstance(r, dict) and _is_filled(r.get("finding"))
        and not str(r.get("finding")).startswith("Information")
        for r in recognition
    )
    nonrep_filled = any(
        isinstance(r, dict) and _is_filled(r.get("item"))
        and not str(r.get("item")).startswith("Information")
        for r in nonrep
    )

    if split_filled >= 2 and (contract_filled or bridge_filled):
        quality = "PASS"
    elif split_filled >= 1 or bridge_filled:
        quality = "REWORK"
    else:
        quality = "REWORK"

    if split_filled >= 2 and bridge_filled:
        reliance = "READY"
    elif split_filled >= 1 or contract_filled:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: revenue split "
        f"{'present' if split_filled >= 2 else 'incomplete'}.",
        f"Reliance {reliance}: "
        f"{'durability picture usable' if reliance == 'READY' else 'gaps remain'}.",
    ]
    if not recog_filled:
        bits.append("Recognition / cut-off still an information request.")
    if not nonrep_filled:
        bits.append("Non-repeating items not yet evidenced.")
    bits.append("Balance-sheet ratios excluded from this agent.")
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_revenue_quality_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    stickiness_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    text = _prose(corpus)
    retention = _retention_from_corpus(text)
    for k, v in (legacy.get("retention_metrics") or {}).items():
        if k not in retention and isinstance(v, (int, float)):
            retention[k] = float(v)

    split = _extract_revenue_split(corpus, legacy)
    contracts = _extract_contract_terms(corpus)
    bridge = _extract_revenue_bridge(corpus, retention)
    recognition = _extract_recognition(corpus)
    nonrep = _extract_non_repeating(corpus)
    billing = _extract_billing_recognised(corpus, recognition)
    taxonomy = _extract_revenue_taxonomy(split, contracts)
    renewals = _extract_renewal_cancellation(contracts, corpus)
    pipeline = _extract_pipeline_vs_backlog(corpus)
    arr = _arr_discipline(corpus, retention)
    cross = _cross_check_stickiness_cash_flow(
        stickiness_spec=stickiness_spec,
        cash_flow_spec=cash_flow_spec,
        retention=retention,
    )

    metrics, mix, flags, notes = _legacy_dual_write(
        retention=retention,
        split=split,
        bridge=bridge,
        corpus=corpus,
        legacy=legacy,
    )
    for rule in (
        _BILLING_RULE, _TAXONOMY_RULE, _PVMA_RULE, _RENEWAL_RULE,
        _PIPELINE_RULE, _ARR_RULE, _CROSS_CHECK_RULE, _RECURRING_NE_BACKLOG,
    ):
        if not any(rule[:28].lower() in str(n).lower() for n in notes):
            notes.append(rule)

    rq_qa = _rq_evidence_qa(
        billing=billing,
        taxonomy=taxonomy,
        bridge=bridge,
        renewals=renewals,
        pipeline=pipeline,
        arr=arr,
        cross=cross,
        split=split,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in rq_qa)

    quality, reliance, rationale = _quality_reliance(
        split=split,
        contracts=contracts,
        bridge=bridge,
        recognition=recognition,
        nonrep=nonrep,
    )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale = "Revenue quality QA has open FAILs — reliance limited. " + rationale
    if cross.get("conflicts"):
        quality = "REWORK"
        rationale = "Stickiness/Cash Flow cross-check conflicts — rework. " + rationale

    contracted = next(
        (
            r.get("share_pct") for r in split
            if isinstance(r, dict) and "under contract" in str(r.get("bucket") or "").lower()
            and isinstance(r.get("share_pct"), (int, float))
        ),
        None,
    )
    bits = [f"Revenue Quality for {company}"]
    if contracted is not None:
        bits.append(f"~{float(contracted):g}% under contract")
    if retention.get("nrr_pct") is not None:
        bits.append(f"NRR {retention['nrr_pct']:g}%")
    if retention.get("grr_pct") is not None:
        bits.append(f"GRR {retention['grr_pct']:g}%")
    nonrep_n = sum(
        1 for r in nonrep
        if isinstance(r, dict) and _is_filled(r.get("item"))
        and not str(r.get("item")).startswith("Information")
    )
    bits.append(f"{nonrep_n} non-repeating item(s)")

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "revenue_split": split,
        "contract_terms": contracts,
        "revenue_bridge": bridge,
        "recognition_cutoff": recognition,
        "non_repeating": nonrep,
        "billing_recognised": billing,
        "revenue_taxonomy": taxonomy,
        "renewal_cancellation": renewals,
        "pipeline_vs_backlog": pipeline,
        "arr_discipline": arr,
        "stickiness_cash_flow_cross_check": cross,
        "rq_evidence_qa": rq_qa,
        # Legacy dual-write
        "retention_metrics": metrics,
        "revenue_mix": mix,
        "quality_flags": flags,
        "quality_notes": notes[:12],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not split and not metrics,
    }
    out["questions"] = _questions_from_rq_gaps(out)
    return out


def _llm_revenue_quality_spec(
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
            "revenue_quality",
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
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot: string,\n"
        "revenue_split: [{bucket, period, share_pct, amount, evidence, source, notes}],\n"
        "contract_terms: [{metric, value, detail, source, notes}],\n"
        "revenue_bridge: [{component, value, period, source, notes}] — include "
        "Opening, New customers/acquisition, Expansion, Price, Volume, Mix, "
        "Contraction, Churn, Closing,\n"
        "recognition_cutoff: [{topic, finding, deferred_or_unbilled, "
        "treatment_change, source, notes}],\n"
        "non_repeating: [{item, kind, size, will_repeat, source, notes}],\n"
        "billing_recognised: [{line, billed, recognised, difference, source, notes}],\n"
        "revenue_taxonomy: [{taxonomy (contracted|cancellable|habitual|one_off|"
        "pass_through), bucket, share_pct, evidence, source, notes}],\n"
        "renewal_cancellation: [{exposure, value, detail, source, notes}],\n"
        "pipeline_vs_backlog: [{kind (pipeline|backlog), finding, enforceable, "
        "source, notes}],\n"
        "arr_discipline: {stated, metric, definition, value, source, notes, "
        "definition_present},\n"
        "retention_metrics: {string: number},\n"
        "revenue_mix: {string: number},\n"
        "quality_flags: [string],\n"
        "quality_notes: [string],\n"
        "rq_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "billing_recognised_reconcile, revenue_taxonomy, price_volume_mix_acquisition, "
        "renewal_cancellation_exposure, pipeline_vs_backlog, arr_discipline, "
        "stickiness_cash_flow_cross_check, recurring_ne_enforceable_backlog,\n"
        "questions: [{question, required_records, decision_effect, priority, owner, "
        "timing, closure_test, interim_treatment}],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "Do NOT include balance-sheet ratios. No invest or pass. "
        "Recurring by behaviour is not enforceable backlog. ARR only if defined."
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
    stickiness_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heur = _heuristic_revenue_quality_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy_spec,
        stickiness_spec=stickiness_spec,
        cash_flow_spec=cash_flow_spec,
    )
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    def _rows(key: str, id_field: str) -> list[dict]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        out: list[dict] = []
        for row in raw:
            if not isinstance(row, dict):
                continue
            blob = " ".join(str(v) for v in row.values())
            if _BALANCE_SHEET_CUE.search(blob):
                continue
            cleaned = {
                k: (_clean(v, 400) if isinstance(v, str) else v)
                for k, v in row.items()
            }
            if not _is_filled(cleaned.get(id_field)) and cleaned.get("share_pct") is None:
                continue
            out.append(cleaned)
        return out or heur.get(key) or []

    llm["revenue_split"] = _rows("revenue_split", "bucket")
    llm["contract_terms"] = _rows("contract_terms", "metric")
    llm["revenue_bridge"] = _rows("revenue_bridge", "component")
    llm["recognition_cutoff"] = _rows("recognition_cutoff", "topic")
    llm["non_repeating"] = _rows("non_repeating", "item")
    llm["billing_recognised"] = _rows("billing_recognised", "line")
    llm["revenue_taxonomy"] = _rows("revenue_taxonomy", "taxonomy")
    llm["renewal_cancellation"] = _rows("renewal_cancellation", "exposure")
    llm["pipeline_vs_backlog"] = _rows("pipeline_vs_backlog", "kind")

    arr_raw = llm.get("arr_discipline") if isinstance(llm.get("arr_discipline"), dict) else {}
    llm["arr_discipline"] = arr_raw or heur.get("arr_discipline") or {}

    llm["stickiness_cash_flow_cross_check"] = (
        heur.get("stickiness_cash_flow_cross_check") or {}
    )

    ret = llm.get("retention_metrics") if isinstance(llm.get("retention_metrics"), dict) else {}
    llm["retention_metrics"] = {
        str(k): float(v)
        for k, v in (ret or heur.get("retention_metrics") or {}).items()
        if isinstance(v, (int, float))
    } or heur.get("retention_metrics") or {}

    mix = llm.get("revenue_mix") if isinstance(llm.get("revenue_mix"), dict) else {}
    llm["revenue_mix"] = {
        str(k): float(v)
        for k, v in (mix or heur.get("revenue_mix") or {}).items()
        if isinstance(v, (int, float))
    } or heur.get("revenue_mix") or {}

    flags = llm.get("quality_flags") if isinstance(llm.get("quality_flags"), list) else []
    llm["quality_flags"] = [
        _soften_invest(_clean(f, 200)) for f in flags if isinstance(f, str) and f.strip()
    ][:6] or heur.get("quality_flags") or []

    notes = llm.get("quality_notes") if isinstance(llm.get("quality_notes"), list) else []
    notes = [
        _soften_invest(_clean(n, 220))
        for n in notes
        if isinstance(n, str) and n.strip() and not _BALANCE_SHEET_CUE.search(n)
    ]
    for rule in (
        _DURABILITY_RULE, _BILLING_RULE, _TAXONOMY_RULE, _PVMA_RULE, _RENEWAL_RULE,
        _PIPELINE_RULE, _ARR_RULE, _CROSS_CHECK_RULE, _RECURRING_NE_BACKLOG,
    ):
        if not any(rule[:28].lower() in str(n).lower() for n in notes):
            notes.append(rule)
    llm["quality_notes"] = (notes or heur.get("quality_notes") or [])[:12]

    rq_qa = _rq_evidence_qa(
        billing=llm["billing_recognised"],
        taxonomy=llm["revenue_taxonomy"],
        bridge=llm["revenue_bridge"],
        renewals=llm["renewal_cancellation"],
        pipeline=llm["pipeline_vs_backlog"],
        arr=llm["arr_discipline"] if isinstance(llm["arr_discipline"], dict) else {},
        cross=llm["stickiness_cash_flow_cross_check"],
        split=llm["revenue_split"],
    )
    llm["rq_evidence_qa"] = rq_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in rq_qa)
    cross = llm["stickiness_cash_flow_cross_check"]

    quality, reliance, rationale = _quality_reliance(
        split=llm["revenue_split"],
        contracts=llm["contract_terms"],
        bridge=llm["revenue_bridge"],
        recognition=llm["recognition_cutoff"],
        nonrep=llm["non_repeating"],
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
    if qa_fail and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Revenue quality QA has open FAILs — reliance limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )
    if isinstance(cross, dict) and cross.get("conflicts"):
        llm["quality_verdict"] = "REWORK"
        llm["quality_reliance_rationale"] = (
            "Stickiness/Cash Flow cross-check conflicts — rework. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )

    if not llm.get("questions"):
        llm["questions"] = _questions_from_rq_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_rq_gaps(llm)

    for dead in (
        "recommendation", "confidence", "investment_verdict", "verdict",
        "invest_recommendation", "balance_sheet", "leverage_ratios",
    ):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not llm["revenue_split"] and not llm["retention_metrics"]
    return llm


def build_revenue_quality_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    stickiness_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
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
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    if corpus is None:
        gathered_corpus, gathered_sources = gather_revenue_quality_corpus(deal, idx)
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
        llm = _llm_revenue_quality_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
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
                sources=sources,
                legacy_spec=legacy,
                corpus=corpus,
                stickiness_spec=stickiness_spec,
                cash_flow_spec=cash_flow_spec,
            )
            out["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return out

    heur = _heuristic_revenue_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy,
        stickiness_spec=stickiness_spec,
        cash_flow_spec=cash_flow_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


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
        "revenue durability insight"
    )
    return f"> **Insight Snapshot:** {body}\n\n"


def _fmt_share(val: object) -> str:
    if isinstance(val, (int, float)):
        return f"{float(val):g}%"
    return _clean(val, 80)


def render_revenue_quality_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    split = spec.get("revenue_split") if isinstance(spec.get("revenue_split"), list) else []
    contracts = (
        spec.get("contract_terms") if isinstance(spec.get("contract_terms"), list) else []
    )
    bridge = (
        spec.get("revenue_bridge") if isinstance(spec.get("revenue_bridge"), list) else []
    )
    recog = (
        spec.get("recognition_cutoff")
        if isinstance(spec.get("recognition_cutoff"), list) else []
    )
    nonrep = (
        spec.get("non_repeating") if isinstance(spec.get("non_repeating"), list) else []
    )
    billing = (
        spec.get("billing_recognised")
        if isinstance(spec.get("billing_recognised"), list) else []
    )
    taxonomy = (
        spec.get("revenue_taxonomy")
        if isinstance(spec.get("revenue_taxonomy"), list) else []
    )
    renewals = (
        spec.get("renewal_cancellation")
        if isinstance(spec.get("renewal_cancellation"), list) else []
    )
    pipeline = (
        spec.get("pipeline_vs_backlog")
        if isinstance(spec.get("pipeline_vs_backlog"), list) else []
    )
    arr = (
        spec.get("arr_discipline")
        if isinstance(spec.get("arr_discipline"), dict) else {}
    )
    cross = (
        spec.get("stickiness_cash_flow_cross_check")
        if isinstance(spec.get("stickiness_cash_flow_cross_check"), dict) else {}
    )
    flags = spec.get("quality_flags") if isinstance(spec.get("quality_flags"), list) else []
    notes = spec.get("quality_notes") if isinstance(spec.get("quality_notes"), list) else []
    retention = (
        spec.get("retention_metrics")
        if isinstance(spec.get("retention_metrics"), dict) else {}
    )
    mix = spec.get("revenue_mix") if isinstance(spec.get("revenue_mix"), dict) else {}
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_DURABILITY_RULE}\n\n")

    # 1
    parts.append("## 1. Revenue Split\n\n")
    parts.append(f"{_SPLIT_RULE}\n\n")
    parts.append(f"{_TAXONOMY_RULE}\n\n")
    if split:
        parts.append(_table(
            ["Bucket", "Period", "Share", "Amount", "Evidence", "Source"],
            [
                [
                    _clean(r.get("bucket"), 40),
                    _clean(r.get("period"), 16),
                    _fmt_share(r.get("share_pct")),
                    _clean(r.get("amount"), 40),
                    _clean(r.get("evidence"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in split if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('revenue split by durability bucket')}**\n\n")
    if taxonomy:
        parts.append("### Taxonomy (contracted / cancellable / habitual / one-off)\n\n")
        parts.append(_table(
            ["Taxonomy", "Bucket", "Share", "Evidence", "Source"],
            [
                [
                    _clean(r.get("taxonomy"), 24),
                    _clean(r.get("bucket"), 40),
                    _fmt_share(r.get("share_pct")),
                    _clean(r.get("evidence"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in taxonomy if isinstance(r, dict)
            ],
        ))
    if billing:
        parts.append("### Billing ↔ recognised\n\n")
        parts.append(f"{_BILLING_RULE}\n\n")
        parts.append(_table(
            ["Line", "Billed", "Recognised", "Difference", "Source"],
            [
                [
                    _clean(r.get("line"), 60),
                    _clean(r.get("billed"), 80),
                    _clean(r.get("recognised"), 80),
                    _clean(r.get("difference"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in billing if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Contract Share, Term & Cancellation\n\n")
    parts.append(f"{_CONTRACT_RULE}\n\n")
    parts.append(f"{_RENEWAL_RULE}\n\n")
    if contracts:
        parts.append(_table(
            ["Metric", "Value", "Detail", "Source"],
            [
                [
                    _clean(r.get("metric"), 40),
                    _clean(r.get("value"), 80),
                    _clean(r.get("detail"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in contracts if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('contract share and remaining term')}**\n\n")
    if renewals:
        parts.append("### Renewal / cancellation exposure\n\n")
        parts.append(_table(
            ["Exposure", "Value", "Detail", "Source"],
            [
                [
                    _clean(r.get("exposure"), 40),
                    _clean(r.get("value"), 80),
                    _clean(r.get("detail"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in renewals if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Revenue Bridge\n\n")
    parts.append(f"{_BRIDGE_RULE}\n\n")
    parts.append(f"{_PVMA_RULE}\n\n")
    if bridge:
        parts.append(_table(
            ["Component", "Value", "Period", "Source"],
            [
                [
                    _clean(r.get("component"), 40),
                    _clean(r.get("value"), 100),
                    _clean(r.get("period"), 24),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in bridge if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('opening → closing revenue bridge')}**\n\n")
    if retention:
        parts.append("### Legacy retention metrics (dual-write)\n\n")
        for k, v in list(retention.items())[:8]:
            parts.append(f"- `{k}`: {v:g}\n" if isinstance(v, (int, float)) else f"- `{k}`: {v}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Recognition & Cut-off\n\n")
    parts.append(f"{_RECOG_RULE}\n\n")
    parts.append(f"{_PIPELINE_RULE}\n\n")
    if recog:
        parts.append(_table(
            ["Topic", "Finding", "Deferred / unbilled", "Treatment change", "Source"],
            [
                [
                    _clean(r.get("topic"), 40),
                    _clean(r.get("finding"), 140),
                    _clean(r.get("deferred_or_unbilled"), 60),
                    _clean(r.get("treatment_change"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in recog if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('revenue recognition and cut-off')}**\n\n")
    if pipeline:
        parts.append("### Pipeline vs enforceable backlog\n\n")
        parts.append(f"{_RECURRING_NE_BACKLOG}\n\n")
        parts.append(_table(
            ["Kind", "Finding", "Enforceable?", "Source"],
            [
                [
                    _clean(r.get("kind"), 20),
                    _clean(r.get("finding"), 140),
                    _clean(r.get("enforceable"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in pipeline if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Non-repeating Revenue\n\n")
    parts.append(f"{_NONREP_RULE}\n\n")
    parts.append(f"{_ARR_RULE}\n\n")
    if nonrep:
        parts.append(_table(
            ["Item", "Kind", "Size", "Will repeat?", "Source"],
            [
                [
                    _clean(r.get("item"), 140),
                    _clean(r.get("kind"), 24),
                    _clean(r.get("size"), 40),
                    _clean(r.get("will_repeat"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in nonrep if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('non-repeating revenue items')}**\n\n")
    if arr:
        parts.append("### ARR / MRR discipline\n\n")
        parts.append(_table(
            ["Field", "Value"],
            [
                ["Stated", "Yes" if arr.get("stated") else "No"],
                ["Metric", _clean(arr.get("metric"), 40)],
                ["Definition", _clean(arr.get("definition"), 160)],
                ["Value", _clean(arr.get("value"), 80)],
                ["Source", _clean(arr.get("source") or _NA, 40)],
            ],
        ))
    if cross:
        parts.append("### Stickiness + Cash Flow cross-check\n\n")
        parts.append(f"{_CROSS_CHECK_RULE}\n\n")
        parts.append(_table(
            ["Field", "Value"],
            [
                ["Stickiness present", "Yes" if cross.get("stickiness_present") else "No"],
                ["Cash Flow present", "Yes" if cross.get("cash_flow_present") else "No"],
                [
                    "Aligned",
                    _clean("; ".join(cross.get("aligned") or []) or _NA, 200),
                ],
                [
                    "Conflicts",
                    _clean("; ".join(cross.get("conflicts") or []) or "None", 200),
                ],
                ["Notes", _clean(cross.get("notes"), 200)],
            ],
        ))
    if flags or notes or mix:
        parts.append("### Legacy quality flags / mix\n\n")
        for f in flags[:4]:
            if isinstance(f, str):
                parts.append(f"- {_clean(f, 200)}\n")
        for k, v in list(mix.items())[:6]:
            parts.append(f"- mix `{k}`: {v:g}\n" if isinstance(v, (int, float)) else f"- mix `{k}`: {v}\n")
        for n in notes[:3]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 200)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 6
    rq_qa = (
        spec.get("rq_evidence_qa")
        if isinstance(spec.get("rq_evidence_qa"), list) else []
    )
    parts.append("## 6. Revenue Quality Evidence QA\n\n")
    parts.append(
        "QA enforces billing↔recognised, taxonomy, price/volume/mix/acquisition, "
        "renewal/cancellation, pipeline vs backlog, ARR discipline, Stickiness + "
        "Cash Flow cross-check, and recurring ≠ enforceable backlog.\n\n"
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
                for r in rq_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('revenue quality evidence QA rows')}\n\n"
    )
    parts.append("---\n\n")

    # 7
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 7. Questions and Inputs Required\n\n")
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
        parts.append(f"{_info_request('Questions for material revenue-quality gaps')}\n\n")
    parts.append("---\n\n")

    # 8
    parts.append("## 8. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(qv, 30)],
            ["Reliance Verdict", _clean(rv, 30)],
            ["Rationale", _soften_invest(_clean(rationale, 460))],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — can diligence rest on this durability picture?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open revenue-quality QA FAILs cap READY → LIMITED. "
        "This document measures how durable the revenue is. It does not "
        "recommend invest or pass. Balance-sheet ratios are out of scope. "
        f"{_RECURRING_NE_BACKLOG}*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, s in enumerate(srcs[:16], start=1):
            parts.append(f"{i}. {_clean(s, 120)}\n")
    else:
        parts.append(f"1. {_NA}\n")
    parts.append("\n")
    return "".join(parts)
