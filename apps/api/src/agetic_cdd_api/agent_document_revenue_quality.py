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
            "Repeat / referral purchase (uncommitted)" if behavioural is not None else None,
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
                "component": "New customers",
                "value": _info_request("new-logo revenue addition between periods"),
                "period": "FY2023 → FY2024",
                "source": _NA,
                "notes": _BRIDGE_RULE,
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
                "value": _info_request("price/mix contribution to the bridge"),
                "period": "FY2023 → FY2024",
                "source": _NA,
                "notes": _BRIDGE_RULE,
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
                "Opening revenue", "New customers", "Expansion", "Price",
                "Contraction", "Churn", "Closing revenue",
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

    metrics, mix, flags, notes = _legacy_dual_write(
        retention=retention,
        split=split,
        bridge=bridge,
        corpus=corpus,
        legacy=legacy,
    )
    quality, reliance, rationale = _quality_reliance(
        split=split,
        contracts=contracts,
        bridge=bridge,
        recognition=recognition,
        nonrep=nonrep,
    )

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

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "revenue_split": split,
        "contract_terms": contracts,
        "revenue_bridge": bridge,
        "recognition_cutoff": recognition,
        "non_repeating": nonrep,
        # Legacy dual-write
        "retention_metrics": metrics,
        "revenue_mix": mix,
        "quality_flags": flags,
        "quality_notes": notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not split and not metrics,
    }


def _llm_revenue_quality_spec(
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
            "revenue_quality",
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
        "insight_snapshot: string,\n"
        "revenue_split: [{bucket, period, share_pct, amount, evidence, source, notes}],\n"
        "contract_terms: [{metric, value, detail, source, notes}],\n"
        "revenue_bridge: [{component, value, period, source, notes}],\n"
        "recognition_cutoff: [{topic, finding, deferred_or_unbilled, "
        "treatment_change, source, notes}],\n"
        "non_repeating: [{item, kind, size, will_repeat, source, notes}],\n"
        "retention_metrics: {string: number},\n"
        "revenue_mix: {string: number},\n"
        "quality_flags: [string],\n"
        "quality_notes: [string],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "Do NOT include balance-sheet ratios. No invest or pass."
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
    heur = _heuristic_revenue_quality_spec(
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
            # Drop balance-sheet contamination
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
    if _DURABILITY_RULE not in notes:
        notes.insert(0, _DURABILITY_RULE)
    llm["quality_notes"] = (notes or heur.get("quality_notes") or [])[:8]

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
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
            )

    return _heuristic_revenue_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


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
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Contract Share, Term & Cancellation\n\n")
    parts.append(f"{_CONTRACT_RULE}\n\n")
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
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Revenue Bridge\n\n")
    parts.append(f"{_BRIDGE_RULE}\n\n")
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
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Non-repeating Revenue\n\n")
    parts.append(f"{_NONREP_RULE}\n\n")
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
    parts.append("## 6. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    parts.append(f"**Quality:** {qv} — is the work accurate and honest about limits?\n\n")
    parts.append(
        f"**Reliance:** {rv} — can diligence rest on this durability picture?\n\n"
    )
    rationale = spec.get("quality_reliance_rationale")
    if _is_filled(rationale):
        parts.append(f"{_soften_invest(str(rationale))}\n\n")
    parts.append(
        "*This document measures how durable the revenue is. It does not "
        "recommend invest or pass. Balance-sheet ratios are out of scope.*\n\n"
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
