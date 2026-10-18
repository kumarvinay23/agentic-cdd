"""Compose DiligenceIQ Capital Structure — funding position at completion.

Facility-by-facility schedule, debt-like items, cash split (freely available /
restricted / operating minimum), change-of-control triggers, sourced net-debt
bridge, fully diluted cap table, approved-EBITDA leverage discipline, and
existing vs acquisition financing. Dual-writes legacy Intrinsic Value
Statement fields (debt_instruments / debt_total_usd_m / leverage_ratios /
dcf_metrics / capital_notes).

No invest/pass. No company allowlists. Do not calculate leverage from an
incomplete facility schedule.
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

_DOCUMENT_TITLE = "Intrinsic Value Statement (NPV)"
_DD_CODE = "DD-24"

_FACILITY_RULE = (
    "Every facility is scheduled from the loan documents and the ledger — "
    "lender, drawn balance, rate, repayment, maturity, security, guarantees, "
    "covenants and headroom — and reconciled to the balance sheet."
)
_DEBT_LIKE_RULE = (
    "Items that behave like debt even though they sit elsewhere are listed "
    "and sized: overdue creditors, unpaid dividends, deferred consideration, "
    "capex creditors, leases, unfunded employee obligations, tax arrears."
)
_CASH_RULE = (
    "Cash is split into freely available, restricted, and the operating "
    "minimum. Only freely available cash counts against debt in full."
)
_COC_RULE = (
    "Change-of-control clauses, prepayment penalties and consents the "
    "transaction would trigger are identified from the facility documents."
)
_NET_DEBT_RULE = (
    "Net debt is presented as gross debt, less available cash, plus debt-like "
    "items, with every line sourced."
)
_LEVERAGE_RULE = (
    "Leverage is not calculated from an incomplete facility schedule — a "
    "partial schedule gives a wrong ratio, not an approximate one."
)
_CAP_TABLE_RULE = (
    "The equity capitalisation table is stated on a fully diluted basis — "
    "options, warrants, convertibles and prefs are included, not omitted."
)
_APPROVED_EBITDA_RULE = (
    "Leverage uses approved EBITDA only. If EBITDA is negative or unapproved, "
    "state alternative metrics (e.g. debt / revenue) and withhold net debt / EBITDA."
)
_FINANCING_LINK_RULE = (
    "Existing / refinancing facilities are separated from acquisition / "
    "transaction financing — the buyer must see what is new money vs take-out."
)
_CAP_TABLE_CUE = re.compile(
    r"(?i)\b(cap\s*table|capitalisation\s+table|capitalization\s+table|"
    r"fully\s+diluted|ordinary\s+shares?|preference\s+shares?|"
    r"warrants?|options?\s+pool|convertible\s+(?:notes?|prefs?))\b"
)
_EBITDA_CUE = re.compile(
    r"(?i)\b((?:approved|adjusted|reported|LTM|NTM)\s+)?EBITDA\b"
)
_ACQ_FINANCE_CUE = re.compile(
    r"(?i)\b(acquisition\s+(?:facility|financing|debt|loan)|"
    r"transaction\s+financing|new\s+money|take[- ]out|"
    r"refinanc(?:e|ing)|existing\s+(?:facility|debt|loan))\b"
)
_SHAREHOLDER_LINE_RE = re.compile(
    r"(?i)([A-Za-z][A-Za-z0-9 &.\-]{1,40}?)\s*[—\-–:]\s*"
    r"([\d,]+(?:\.\d+)?)\s*%(?:\s*(?:fully\s+diluted|FD))?"
)

_DEBT_LINE_RE = re.compile(
    r"(?i)([A-Za-z][A-Za-z0-9 &/\-()]{2,60}?)\s*[—\-–:]\s*"
    r"(?:USD|US\$|\$)\s*([\d,]+(?:\.\d+)?)\s*M\b"
)
_TOTAL_DEBT_RE = re.compile(
    r"(?i)(?:total\s+(?:gross\s+)?debt|gross\s+debt|debt\s+total)"
    r"[^.%]{0,40}?(?:USD|US\$|\$)?\s*([\d,]+(?:\.\d+)?)\s*M\b"
)
_RATE_RE = re.compile(
    r"(?i)(?:interest\s+rate|coupon|pricing|SOFR|LIBOR|SBI\s*MCLR|repo)"
    r"[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_MATURITY_RE = re.compile(
    r"(?i)(?:maturit(?:y|ies)|due\s+(?:date|in)|tenor)"
    r"[^.%]{0,40}?(20\d{2}|FY\d{2,4}|\d+\s*years?)"
)
_COVENANT_RE = re.compile(
    r"(?i)\b(covenant|headroom|leverage\s+test|interest\s+cover|"
    r"debt\s*/\s*EBITDA|net\s+debt\s*/\s*EBITDA|springing)\b"
)
_COC_RE = re.compile(
    r"(?i)\b(change[- ]of[- ]control|CoC|mandatory\s+prepay|"
    r"prepayment\s+penalty|make[- ]whole|consent\s+required|"
    r"lender\s+consent|event\s+of\s+default)\b"
)
_CASH_FREE_RE = re.compile(
    r"(?i)(?:freely\s+available\s+cash|unrestricted\s+cash|available\s+cash)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn)?"
)
_CASH_RESTRICTED_RE = re.compile(
    r"(?i)(?:restricted\s+cash|escrow|margin\s+money|lien(?:ed)?\s+cash)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn)?"
)
_CASH_MINIMUM_RE = re.compile(
    r"(?i)(?:operating\s+minimum|minimum\s+cash|cash\s+floor|"
    r"working\s+capital\s+minimum)"
    r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹)?\s*([\d,]+(?:\.\d+)?)\s*(M|Cr|mn)?"
)
_LEASE_RE = re.compile(
    r"(?i)\b(finance\s+lease|capital\s+lease|lease\s+obligation|"
    r"IFRS\s*16|Ind\s*AS\s*116|right[- ]of[- ]use)\b"
)
_DEBT_LIKE_CUE = re.compile(
    r"(?i)\b(overdue|past[- ]due|declared\s+dividend|unpaid\s+dividend|"
    r"deferred\s+consideration|contingent\s+consideration|earn[- ]?out|"
    r"capex\s+creditor|unfunded|gratuity|pension|tax\s+arrear|"
    r"deferred\s+tax\s+liabilit)\b"
)
_RATIO_CUE = re.compile(
    r"(?i)\b(net\s+debt\s*/\s*(?:EBITDA|revenue)|debt\s*/\s*equity|"
    r"interest\s+coverage|current\s+ratio|leverage)\b"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)

_DEBT_LIKE_KINDS = (
    ("Overdue trade creditors", ("overdue", "past-due", "past due", "beyond normal terms")),
    ("Declared unpaid dividends", ("declared dividend", "unpaid dividend")),
    ("Deferred / contingent consideration", ("deferred consideration", "contingent consideration", "earn-out", "earnout")),
    ("Capex creditors", ("capex creditor", "capital expenditure creditor")),
    ("Lease obligations", ("finance lease", "capital lease", "lease obligation", "ifrs 16", "ind as 116")),
    ("Unfunded employee obligations", ("unfunded", "gratuity", "pension deficit")),
    ("Tax arrears", ("tax arrear", "tax arrears", "overdue tax")),
)


def _info_request(what: str) -> str:
    return f"Information request: {what}"


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or text == _NA:
        return False
    return not text.startswith("Information request")


def _num(raw: Any) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).replace(",", "").strip()
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("funding-position evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _insight(text: Any, *, max_chars: int = 520) -> str:
    snap = _soften_invest(_clean(text, max_chars))
    return f"**Insight Snapshot:** {snap}\n\n" if snap else ""


def _table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [(_clean(c, 220) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    text = _HEADER_LINE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _fmt_amt(value: Any, *, unit: str = "USD M") -> str:
    n = _num(value)
    if n is None:
        return _clean(value, 40) or "—"
    return f"{n:g} {unit}" if unit else f"{n:g}"


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_capital_structure_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "legal_esg": 1,
        "deal_strategy": 2,
        "operations": 3,
        "company_management": 4,
        "customer": 5,
        "market_competition": 6,
    }
    needles = (
        "debt", "loan", "facility", "credit", "bond", "debenture", "ncd",
        "lease", "cash", "liquidity", "covenant", "refinance", "capital",
        "financial", "valuation", "bank", "security", "guarantee",
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
    for doc in ranked[:14]:
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


def _facilities_from_legacy_and_corpus(
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in legacy.get("debt_instruments") or []:
        if not isinstance(item, dict):
            continue
        name = _clean(item.get("name") or item.get("facility") or item.get("instrument"), 80)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        amount = _num(
            item.get("amount_usd_m")
            if item.get("amount_usd_m") is not None
            else item.get("drawn_balance") or item.get("balance")
        )
        rows.append(
            {
                "facility": name,
                "lender": item.get("lender") or _info_request(f"lender for {name}"),
                "drawn_balance": amount if amount is not None else _info_request(f"drawn balance for {name}"),
                "rate": item.get("rate") or _info_request(f"rate for {name}"),
                "repayment_profile": item.get("repayment_profile") or _info_request(f"repayment profile for {name}"),
                "maturity": item.get("maturity") or _info_request(f"maturity for {name}"),
                "security": item.get("security") or _info_request(f"security for {name}"),
                "guarantees": item.get("guarantees") or _info_request(f"guarantees for {name}"),
                "covenants_headroom": item.get("covenants_headroom") or item.get("covenants")
                or _info_request(f"covenants / headroom for {name}"),
                "source": "legacy extract",
                "notes": _FACILITY_RULE,
            }
        )

    for m in _DEBT_LINE_RE.finditer(corpus or ""):
        name = _clean(m.group(1), 80)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        if len(name.split()) > 8:
            continue
        # Skip ratio / prose false positives
        if re.search(r"(?i)^(total|net|gross|leverage|ratio|coverage)", name):
            continue
        seen.add(key)
        amount = float(m.group(2).replace(",", ""))
        rows.append(
            {
                "facility": name,
                "lender": _info_request(f"lender for {name}"),
                "drawn_balance": amount,
                "rate": _info_request(f"rate for {name}"),
                "repayment_profile": _info_request(f"repayment profile for {name}"),
                "maturity": _info_request(f"maturity for {name}"),
                "security": _info_request(f"security for {name}"),
                "guarantees": _info_request(f"guarantees for {name}"),
                "covenants_headroom": _info_request(f"covenants / headroom for {name}"),
                "source": _DOC_CITE,
                "notes": _FACILITY_RULE,
            }
        )

    # Enrich first facility with any rate/maturity cues found globally
    text = _prose(corpus)
    rate_m = _RATE_RE.search(text)
    mat_m = _MATURITY_RE.search(text)
    cov_hit = bool(_COVENANT_RE.search(text))
    if rows and rate_m:
        for row in rows:
            if str(row.get("rate") or "").startswith("Information"):
                row["rate"] = f"{rate_m.group(1)}% (pack-level cue — confirm per facility)"
                break
    if rows and mat_m:
        for row in rows:
            if str(row.get("maturity") or "").startswith("Information"):
                row["maturity"] = f"{mat_m.group(1)} (pack-level cue — confirm per facility)"
                break
    if rows and cov_hit:
        for row in rows:
            if str(row.get("covenants_headroom") or "").startswith("Information"):
                row["covenants_headroom"] = _info_request(
                    "per-facility covenant tests and headroom from loan docs"
                )
                break

    if not rows:
        rows.append(
            {
                "facility": _info_request("facility name from loan docs / ledger"),
                "lender": _info_request("lender"),
                "drawn_balance": _NA,
                "rate": _NA,
                "repayment_profile": _NA,
                "maturity": _NA,
                "security": _NA,
                "guarantees": _NA,
                "covenants_headroom": _NA,
                "source": _NA,
                "notes": _FACILITY_RULE,
            }
        )
    return rows[:12]


def _schedule_complete(facilities: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    """A schedule is complete only when real facilities have lender + balance + key terms."""
    real = [
        f for f in facilities
        if isinstance(f, dict)
        and _is_filled(f.get("facility"))
        and not str(f.get("facility")).startswith("Information")
    ]
    gaps: list[str] = []
    if not real:
        return False, ["No facilities scheduled from loan documents / ledger"]

    required = (
        "lender",
        "drawn_balance",
        "rate",
        "maturity",
        "security",
        "covenants_headroom",
    )
    filled_facilities = 0
    for f in real:
        missing_fields = [
            field for field in required
            if not _is_filled(f.get(field))
            or str(f.get(field)).startswith("Information")
            or f.get(field) == _NA
        ]
        if not missing_fields and isinstance(f.get("drawn_balance"), (int, float)):
            filled_facilities += 1
        else:
            gaps.append(
                f"{f.get('facility')}: missing {', '.join(missing_fields) or 'drawn balance'}"
            )
    # Complete only if every real facility has core fields — not "most"
    complete = filled_facilities == len(real) and filled_facilities >= 1
    if not complete and not gaps:
        gaps.append("Facility schedule incomplete — lender / rate / maturity / security / covenants still open")
    return complete, gaps


def _bs_reconciliation(
    facilities: list[dict[str, Any]],
    legacy: dict[str, Any],
    corpus: str,
) -> list[dict[str, Any]]:
    drawn = [
        float(f["drawn_balance"])
        for f in facilities
        if isinstance(f, dict) and isinstance(f.get("drawn_balance"), (int, float))
    ]
    scheduled = sum(drawn) if drawn else None
    total = _num(legacy.get("debt_total_usd_m"))
    if total is None:
        m = _TOTAL_DEBT_RE.search(corpus or "")
        if m:
            total = float(m.group(1).replace(",", ""))

    rows: list[dict[str, Any]] = []
    if scheduled is not None:
        rows.append(
            {
                "line": "Sum of scheduled drawn balances",
                "amount": scheduled,
                "source": _COMPUTED,
                "notes": _FACILITY_RULE,
            }
        )
    if total is not None:
        rows.append(
            {
                "line": "Reported total / gross debt",
                "amount": total,
                "source": _DOC_CITE,
                "notes": _FACILITY_RULE,
            }
        )
    if scheduled is not None and total is not None:
        diff = round(total - scheduled, 2)
        rows.append(
            {
                "line": "Unexplained difference (BS / reported − scheduled)",
                "amount": diff,
                "source": _COMPUTED,
                "notes": (
                    "Reconciled"
                    if abs(diff) < 0.6
                    else _info_request("accounts explaining the debt reconciliation gap")
                ),
            }
        )
    if not rows:
        rows.append(
            {
                "line": _info_request("balance-sheet gross debt to reconcile"),
                "amount": _NA,
                "source": _NA,
                "notes": _FACILITY_RULE,
            }
        )
    return rows


def _debt_like_items(corpus: str, facilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    lower = text.lower()

    # Leases already in facility schedule still belong in debt-like if classified as lease
    for f in facilities:
        if not isinstance(f, dict):
            continue
        name = str(f.get("facility") or "")
        if _LEASE_RE.search(name) or "lease" in name.lower():
            rows.append(
                {
                    "item": name,
                    "kind": "Lease obligations",
                    "amount": f.get("drawn_balance")
                    if isinstance(f.get("drawn_balance"), (int, float))
                    else _info_request(f"lease obligation size for {name}"),
                    "where_sits": "Debt / lease liability (also on facility schedule)",
                    "source": f.get("source") or _DOC_CITE,
                    "notes": _DEBT_LIKE_RULE,
                }
            )

    for kind, needles in _DEBT_LIKE_KINDS:
        if kind == "Lease obligations" and rows:
            continue
        if any(n in lower for n in needles):
            # Pull a short evidence sentence
            evidence = next(
                (s for s in _sentences(corpus) if any(n in s.lower() for n in needles)),
                None,
            )
            rows.append(
                {
                    "item": _clean(evidence, 120) if evidence else kind,
                    "kind": kind,
                    "amount": _info_request(f"sized amount for {kind.lower()}"),
                    "where_sits": _info_request(f"balance-sheet / note location for {kind.lower()}"),
                    "source": _DOC_CITE if evidence else _NA,
                    "notes": _DEBT_LIKE_RULE,
                }
            )

    if not rows and not _DEBT_LIKE_CUE.search(corpus or ""):
        for kind, _needles in _DEBT_LIKE_KINDS[:4]:
            rows.append(
                {
                    "item": _info_request(kind),
                    "kind": kind,
                    "amount": _NA,
                    "where_sits": _NA,
                    "source": _NA,
                    "notes": _DEBT_LIKE_RULE,
                }
            )
    return rows[:10]


def _cash_split(corpus: str, legacy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    def _add(bucket: str, amount: Any, counts: str, *, source: str, detail: str) -> None:
        rows.append(
            {
                "bucket": bucket,
                "amount": amount,
                "counts_against_debt": counts,
                "detail": detail,
                "source": source,
                "notes": _CASH_RULE,
            }
        )

    free_m = _CASH_FREE_RE.search(text)
    rest_m = _CASH_RESTRICTED_RE.search(text)
    min_m = _CASH_MINIMUM_RE.search(text)

    # Soft cue from leverage pack cash burn / liquidity notes — still request split
    cash_burn = None
    ratios = legacy.get("leverage_ratios") if isinstance(legacy.get("leverage_ratios"), dict) else {}
    if isinstance(ratios.get("cash_burn_rate_monthly_inr_cr"), (int, float)):
        cash_burn = float(ratios["cash_burn_rate_monthly_inr_cr"])

    if free_m:
        unit = (free_m.group(2) or "M").upper()
        _add(
            "Freely available",
            f"{free_m.group(1)} {unit}",
            "Yes — counts in full",
            source=_DOC_CITE,
            detail="Unrestricted cash available at completion",
        )
    else:
        _add(
            "Freely available",
            _info_request("freely available / unrestricted cash"),
            "Yes — counts in full (once evidenced)",
            source=_NA,
            detail=_CASH_RULE,
        )

    if rest_m:
        unit = (rest_m.group(2) or "M").upper()
        _add(
            "Restricted",
            f"{rest_m.group(1)} {unit}",
            "No — not counted against debt",
            source=_DOC_CITE,
            detail="Escrow / lien / margin / restricted balances",
        )
    else:
        _add(
            "Restricted",
            _info_request("restricted / escrow / lien cash"),
            "No — not counted against debt",
            source=_NA,
            detail=_CASH_RULE,
        )

    if min_m:
        unit = (min_m.group(2) or "M").upper()
        _add(
            "Operating minimum",
            f"{min_m.group(1)} {unit}",
            "No — retained to operate",
            source=_DOC_CITE,
            detail="Cash the business needs to keep running",
        )
    else:
        detail = _CASH_RULE
        if cash_burn is not None:
            detail = (
                f"Pack cites monthly cash burn ~{cash_burn:g} Cr — operating minimum "
                f"still needs an explicit cash-floor figure."
            )
        _add(
            "Operating minimum",
            _info_request("operating cash minimum / cash floor"),
            "No — retained to operate",
            source=_NA,
            detail=detail,
        )
    return rows


def _change_of_control(corpus: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sent in _sentences(corpus or "")[:60]:
        if not _COC_RE.search(sent):
            continue
        kind = "Change of control"
        lower = sent.lower()
        if "prepay" in lower or "make-whole" in lower or "make whole" in lower:
            kind = "Prepayment / make-whole"
        elif "consent" in lower:
            kind = "Consent required"
        rows.append(
            {
                "trigger": _clean(sent, 160),
                "kind": kind,
                "consequence": _info_request("what the clause requires at completion"),
                "source": _DOC_CITE,
                "notes": _COC_RULE,
            }
        )
        if len(rows) >= 6:
            break
    if not rows:
        rows = [
            {
                "trigger": _info_request("change-of-control clause from facility docs"),
                "kind": "Change of control",
                "consequence": _NA,
                "source": _NA,
                "notes": _COC_RULE,
            },
            {
                "trigger": _info_request("prepayment penalties / make-whole"),
                "kind": "Prepayment / make-whole",
                "consequence": _NA,
                "source": _NA,
                "notes": _COC_RULE,
            },
            {
                "trigger": _info_request("lender / noteholder consents required"),
                "kind": "Consent required",
                "consequence": _NA,
                "source": _NA,
                "notes": _COC_RULE,
            },
        ]
    return rows


def _net_debt_bridge(
    facilities: list[dict[str, Any]],
    debt_like: list[dict[str, Any]],
    cash: list[dict[str, Any]],
    legacy: dict[str, Any],
    *,
    schedule_complete: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    gross = sum(
        float(f["drawn_balance"])
        for f in facilities
        if isinstance(f, dict) and isinstance(f.get("drawn_balance"), (int, float))
    )
    if not gross and _num(legacy.get("debt_total_usd_m")) is not None:
        gross = float(legacy["debt_total_usd_m"])

    rows.append(
        {
            "component": "Gross debt (scheduled facilities)",
            "amount": gross if gross else _info_request("gross debt from complete facility schedule"),
            "sign": "+",
            "source": _COMPUTED if gross else _NA,
            "notes": _NET_DEBT_RULE,
        }
    )

    free = next(
        (c for c in cash if isinstance(c, dict) and "freely" in str(c.get("bucket") or "").lower()),
        None,
    )
    free_amt = _num(free.get("amount")) if free else None
    rows.append(
        {
            "component": "Less: freely available cash",
            "amount": free_amt if free_amt is not None else (
                free.get("amount") if free else _info_request("freely available cash")
            ),
            "sign": "−",
            "source": (free or {}).get("source") or _NA,
            "notes": _CASH_RULE,
        }
    )

    debt_like_sized = [
        d for d in debt_like
        if isinstance(d, dict) and isinstance(d.get("amount"), (int, float))
    ]
    debt_like_sum = sum(float(d["amount"]) for d in debt_like_sized)
    rows.append(
        {
            "component": "Plus: debt-like items",
            "amount": debt_like_sum if debt_like_sized else _info_request("sized debt-like items"),
            "sign": "+",
            "source": _COMPUTED if debt_like_sized else _NA,
            "notes": _DEBT_LIKE_RULE,
        }
    )

    if (
        schedule_complete
        and gross
        and free_amt is not None
        and debt_like_sized is not None
    ):
        # Only compute a closing net-debt figure when schedule is complete and cash is numeric
        net = gross - float(free_amt) + float(debt_like_sum)
        rows.append(
            {
                "component": "Net debt (completion funding position)",
                "amount": round(net, 2),
                "sign": "=",
                "source": _COMPUTED,
                "notes": _NET_DEBT_RULE,
            }
        )
    else:
        rows.append(
            {
                "component": "Net debt (completion funding position)",
                "amount": _info_request(
                    "net debt after complete facility schedule + available cash + debt-like sizes"
                ),
                "sign": "=",
                "source": _NA,
                "notes": _LEVERAGE_RULE,
            }
        )
    return rows


def _extract_cap_table(corpus: str, legacy: dict[str, Any]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in legacy.get("cap_table") or legacy.get("shareholders") or []:
        if not isinstance(item, dict):
            continue
        holder = _clean(
            item.get("holder") or item.get("shareholder") or item.get("name"), 60
        )
        if not holder or holder.lower() in seen:
            continue
        seen.add(holder.lower())
        pct = _num(item.get("fully_diluted_pct") or item.get("pct") or item.get("share_pct"))
        rows.append({
            "holder": holder,
            "instrument": _clean(item.get("instrument") or item.get("class") or "Equity", 40),
            "shares": item.get("shares") if item.get("shares") is not None else _NA,
            "fully_diluted_pct": pct if pct is not None else _info_request(
                f"fully diluted % for {holder}"
            ),
            "source": "legacy extract",
            "notes": _CAP_TABLE_RULE,
        })

    for m in _SHAREHOLDER_LINE_RE.finditer(text):
        holder = _clean(m.group(1), 60)
        if not holder or holder.lower() in seen:
            continue
        if re.search(r"(?i)^(total|fully|ordinary|preference|debt|cash)", holder):
            continue
        seen.add(holder.lower())
        rows.append({
            "holder": holder,
            "instrument": "Equity / as stated",
            "shares": _NA,
            "fully_diluted_pct": float(m.group(2).replace(",", "")),
            "source": _DOC_CITE,
            "notes": _CAP_TABLE_RULE,
        })
        if len(rows) >= 8:
            break

    diluted_hit = bool(re.search(r"(?i)\bfully\s+diluted\b", text))
    if _CAP_TABLE_CUE.search(text) and not rows:
        sent = next((s for s in _sentences(text) if _CAP_TABLE_CUE.search(s)), None)
        rows.append({
            "holder": _clean(sent, 80) if sent else _info_request("shareholder / holder"),
            "instrument": _info_request("instrument class (ordinary / pref / option / warrant)"),
            "shares": _NA,
            "fully_diluted_pct": _info_request("fully diluted ownership %"),
            "source": _DOC_CITE if sent else _NA,
            "notes": _CAP_TABLE_RULE,
            "fully_diluted_basis": diluted_hit,
        })

    if not rows:
        for label in ("Founders / management", "Financial sponsor / PE", "Other / options pool"):
            rows.append({
                "holder": _info_request(label),
                "instrument": _info_request("instrument class"),
                "shares": _NA,
                "fully_diluted_pct": _info_request("fully diluted %"),
                "source": _NA,
                "notes": _CAP_TABLE_RULE,
                "fully_diluted_basis": False,
            })
    else:
        for row in rows:
            row.setdefault("fully_diluted_basis", diluted_hit or any(
                isinstance(r.get("fully_diluted_pct"), (int, float)) for r in rows
            ))
    return rows[:10]


def _financing_vs_acquisition(
    facilities: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    for f in facilities:
        if not isinstance(f, dict):
            continue
        name = str(f.get("facility") or "")
        if not _is_filled(name) or name.startswith("Information"):
            continue
        blob = f"{name} {f.get('notes') or ''} {f.get('lender') or ''}"
        kind = "existing / refinancing"
        if re.search(
            r"(?i)\b(acquisition|transaction\s+financ|new\s+money|bridge\s+to\s+sale)\b",
            blob,
        ):
            kind = "acquisition / transaction financing"
        elif re.search(r"(?i)\brefinanc", blob):
            kind = "refinancing / take-out"
        rows.append({
            "facility": _clean(name, 60),
            "classification": kind,
            "drawn_balance": f.get("drawn_balance"),
            "evidence": _clean(name, 80),
            "source": f.get("source") or _DOC_CITE,
            "notes": _FINANCING_LINK_RULE,
        })

    for s in _sentences(text):
        if not _ACQ_FINANCE_CUE.search(s):
            continue
        kind = "acquisition / transaction financing"
        if re.search(r"(?i)\brefinanc|existing\s+(?:facility|debt)|take[- ]out\b", s):
            kind = "existing / refinancing"
        if any(
            isinstance(r, dict) and _clean(s, 40) in str(r.get("evidence") or "")
            for r in rows
        ):
            continue
        rows.append({
            "facility": _clean(s, 60),
            "classification": kind,
            "drawn_balance": _NA,
            "evidence": _clean(s, 140),
            "source": _DOC_CITE,
            "notes": _FINANCING_LINK_RULE,
        })
        if len(rows) >= 8:
            break

    if not rows:
        rows.append({
            "facility": _info_request("existing / refinancing facilities"),
            "classification": "existing / refinancing",
            "drawn_balance": _NA,
            "evidence": _NA,
            "source": _NA,
            "notes": _FINANCING_LINK_RULE,
        })
        rows.append({
            "facility": _info_request("acquisition / transaction financing"),
            "classification": "acquisition / transaction financing",
            "drawn_balance": _NA,
            "evidence": _NA,
            "source": _NA,
            "notes": _FINANCING_LINK_RULE,
        })
    return rows[:10]


def _leverage_discipline(
    *,
    schedule_complete: bool,
    schedule_gaps: list[str],
    legacy: dict[str, Any],
    corpus: str,
    net_debt: list[dict[str, Any]],
    hp_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approved-EBITDA leverage; alt metrics if EBITDA negative / missing."""
    text = _prose(corpus)
    ebitda: float | None = None
    ebitda_label = _info_request("approved EBITDA")
    ebitda_source = _NA
    approved = False

    # Prefer explicit approved / adjusted EBITDA in corpus
    m = re.search(
        r"(?i)\b(approved|adjusted|quality\s+of\s+earnings)\s+EBITDA\b"
        r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹)?\s*([-]?[\d,]+(?:\.\d+)?)\s*(M|Cr|mn)?",
        text,
    )
    if m:
        ebitda = float(m.group(2).replace(",", ""))
        unit = (m.group(3) or "M").upper()
        ebitda_label = f"Approved/adjusted EBITDA {ebitda:g} {unit}"
        ebitda_source = _DOC_CITE
        approved = True
    else:
        m2 = re.search(
            r"(?i)\b(LTM|NTM|reported)?\s*EBITDA\b"
            r"[^.%]{0,40}?(?:USD|US\$|\$|INR|₹)?\s*([-]?[\d,]+(?:\.\d+)?)\s*(M|Cr|mn)?",
            text,
        )
        if m2:
            ebitda = float(m2.group(2).replace(",", ""))
            unit = (m2.group(3) or "M").upper()
            ebitda_label = f"EBITDA {ebitda:g} {unit} (not labelled approved)"
            ebitda_source = _DOC_CITE
            approved = False

    if ebitda is None and isinstance(hp_spec, dict):
        perf = hp_spec.get("performance_metrics") if isinstance(
            hp_spec.get("performance_metrics"), dict
        ) else {}
        for key in ("ebitda_fy2024", "ebitda_fy2025", "ebitda_fy2023", "ebitda"):
            if isinstance(perf.get(key), (int, float)):
                ebitda = float(perf[key])
                ebitda_label = f"Historical Performance {key}"
                ebitda_source = "(PRIOR: historical_performance)"
                approved = False
                break
        if ebitda is None:
            for row in hp_spec.get("pl_lines") or []:
                if not isinstance(row, dict):
                    continue
                if "ebitda" in str(row.get("line") or row.get("metric") or "").lower():
                    n = _num(row.get("amount") or row.get("value"))
                    if n is not None:
                        ebitda = n
                        ebitda_label = "Historical Performance P&L EBITDA"
                        ebitda_source = "(PRIOR: historical_performance)"
                        approved = False
                        break

    net = next(
        (
            r.get("amount") for r in net_debt
            if isinstance(r, dict)
            and "net debt" in str(r.get("component") or "").lower()
            and isinstance(r.get("amount"), (int, float))
        ),
        None,
    )

    ratios: dict[str, Any] = {}
    alt_metrics: list[str] = []
    status = "withheld"

    if not schedule_complete:
        status = "withheld_incomplete_schedule"
        ratios["leverage_withheld"] = (
            "Not calculated — facility schedule incomplete. "
            + ("; ".join(schedule_gaps[:3]) if schedule_gaps else _LEVERAGE_RULE)
        )
    elif ebitda is None:
        status = "withheld_no_approved_ebitda"
        ratios["leverage_withheld"] = (
            "Net debt / EBITDA withheld — approved EBITDA not evidenced. "
            + _APPROVED_EBITDA_RULE
        )
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            key = str(k).lower()
            if "ebitda" in key:
                continue
            ratios[str(k)] = v
            if "revenue" in key or "equity" in key or "interest" in key:
                alt_metrics.append(f"{k}={v}")
        if not alt_metrics:
            alt_metrics.append(_info_request("debt / revenue or interest cover as alt metric"))
    elif ebitda <= 0:
        status = "alt_metrics_negative_ebitda"
        ratios["leverage_withheld"] = (
            f"Net debt / EBITDA withheld — EBITDA {ebitda:g} is negative/zero. "
            + _APPROVED_EBITDA_RULE
        )
        # Preserve non-EBITDA legacy ratios as alternatives
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            key = str(k).lower()
            if "ebitda" in key:
                continue
            if "revenue" in key or "equity" in key or "interest" in key or "burn" in key:
                ratios[str(k)] = v
                alt_metrics.append(f"{k}={v}")
        if not alt_metrics:
            alt_metrics.append(_info_request("debt / revenue (EBITDA negative)"))
            alt_metrics.append(_info_request("interest cover N/A — negative EBITDA"))
    elif not approved:
        status = "withheld_unapproved_ebitda"
        ratios["leverage_withheld"] = (
            f"EBITDA {ebitda:g} present but not labelled approved — "
            "withhold net debt / EBITDA until QoE / approved figure. "
            + _APPROVED_EBITDA_RULE
        )
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            key = str(k).lower()
            if "ebitda" in key:
                continue
            if "revenue" in key or "burn" in key or "liquidity" in key:
                ratios[str(k)] = v
    else:
        status = "computed_on_approved_ebitda"
        if net is not None and ebitda:
            ratios["net_debt_ebitda"] = round(float(net) / float(ebitda), 2)
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            key = str(k).lower()
            if "ebitda" in key and k not in ratios:
                ratios[str(k)] = v
            elif "revenue" in key or "burn" in key:
                ratios[str(k)] = v

    # Always keep liquidity cues
    for k, v in (legacy.get("leverage_ratios") or {}).items():
        key = str(k).lower()
        if ("burn" in key or "liquidity" in key or "runway" in key) and k not in ratios:
            ratios[str(k)] = v

    return {
        "status": status,
        "ebitda": ebitda if ebitda is not None else _NA,
        "ebitda_label": ebitda_label,
        "ebitda_approved": approved,
        "ebitda_source": ebitda_source,
        "ratios": ratios,
        "alt_metrics": alt_metrics[:6],
        "notes": f"{_LEVERAGE_RULE} {_APPROVED_EBITDA_RULE}",
        "source": ebitda_source,
    }


def _legacy_dual_write(
    *,
    facilities: list[dict[str, Any]],
    schedule_complete: bool,
    schedule_gaps: list[str],
    legacy: dict[str, Any],
    corpus: str,
    leverage_discipline: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], float | None, dict[str, Any], dict[str, float], list[str]]:
    instruments: list[dict[str, Any]] = []
    for f in facilities:
        if not isinstance(f, dict):
            continue
        name = f.get("facility")
        if not _is_filled(name) or str(name).startswith("Information"):
            continue
        amount = f.get("drawn_balance") if isinstance(f.get("drawn_balance"), (int, float)) else None
        instruments.append({"name": _clean(name, 80), "amount_usd_m": amount})

    scheduled = sum(
        float(i["amount_usd_m"])
        for i in instruments
        if isinstance(i.get("amount_usd_m"), (int, float))
    )
    legacy_total = _num(legacy.get("debt_total_usd_m"))
    total = legacy_total if legacy_total is not None else (scheduled or None)

    leverage: dict[str, Any] = {}
    disc = leverage_discipline if isinstance(leverage_discipline, dict) else {}
    if disc.get("ratios"):
        leverage = dict(disc["ratios"])
    elif schedule_complete:
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            leverage[str(k)] = v
    else:
        leverage["leverage_withheld"] = (
            "Not calculated — facility schedule incomplete. "
            + ("; ".join(schedule_gaps[:3]) if schedule_gaps else _LEVERAGE_RULE)
        )
        for k, v in (legacy.get("leverage_ratios") or {}).items():
            key = str(k).lower()
            if "burn" in key or "liquidity" in key or "runway" in key:
                leverage[str(k)] = v

    dcf: dict[str, float] = {}
    for k, v in (legacy.get("dcf_metrics") or {}).items():
        n = _num(v)
        if n is not None:
            dcf[str(k)] = n

    notes: list[str] = []
    for note in legacy.get("capital_notes") or []:
        if isinstance(note, str) and note.strip():
            notes.append(_soften_invest(_clean(note, 200)))
    for rule in (
        _FACILITY_RULE, _DEBT_LIKE_RULE, _CASH_RULE, _COC_RULE, _NET_DEBT_RULE,
        _LEVERAGE_RULE, _CAP_TABLE_RULE, _APPROVED_EBITDA_RULE, _FINANCING_LINK_RULE,
    ):
        if not any(rule[:28].lower() in n.lower() for n in notes):
            notes.append(rule)
    if not schedule_complete:
        notes.append("Facility schedule incomplete — leverage not calculated.")
    if _RATIO_CUE.search(corpus or "") and not schedule_complete:
        notes.append(
            "Pack cites leverage figures; they are not used until the facility schedule is complete."
        )
    if disc.get("status") == "alt_metrics_negative_ebitda":
        notes.append("EBITDA negative — alternative leverage metrics only.")
    deduped: list[str] = []
    seen: set[str] = set()
    for n in notes:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(n)
    return instruments[:12], total, leverage, dcf, deduped[:10]


def _cap_evidence_qa(
    *,
    facilities: list[dict[str, Any]],
    debt_like: list[dict[str, Any]],
    cash: list[dict[str, Any]],
    coc: list[dict[str, Any]],
    net_debt: list[dict[str, Any]],
    cap_table: list[dict[str, Any]],
    financing_link: list[dict[str, Any]],
    leverage_disc: dict[str, Any],
    schedule_complete: bool,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    rows.append({
        "check": "facility_schedule_complete",
        "status": "PASS" if schedule_complete else "FAIL",
        "finding": (
            "Facility schedule complete"
            if schedule_complete
            else _info_request("complete facility schedule (lender/rate/maturity/security/covenants)")
        ),
        "action": _FACILITY_RULE,
    })

    dl_ok = any(
        isinstance(d, dict)
        and _is_filled(d.get("item"))
        and not str(d.get("item")).startswith("Information")
        for d in debt_like
    )
    rows.append({
        "check": "debt_like_catalogue",
        "status": "PASS" if dl_ok else "FAIL",
        "finding": (
            f"{sum(1 for d in debt_like if isinstance(d, dict))} debt-like row(s)"
            if dl_ok
            else _info_request("debt-like catalogue sized")
        ),
        "action": _DEBT_LIKE_RULE,
    })

    cash_buckets = {
        str(c.get("bucket") or "")
        for c in cash if isinstance(c, dict)
    }
    cash_ok = (
        any("Freely" in b for b in cash_buckets)
        and any("Restricted" in b for b in cash_buckets)
        and any("Operating" in b or "minimum" in b.lower() for b in cash_buckets)
        and any(
            isinstance(c, dict)
            and "freely" in str(c.get("bucket") or "").lower()
            and _is_filled(c.get("amount"))
            and not str(c.get("amount")).startswith("Information")
            for c in cash
        )
    )
    rows.append({
        "check": "cash_split_free_restricted_minimum",
        "status": "PASS" if cash_ok else "FAIL",
        "finding": (
            "Cash split evidenced (free / restricted / operating minimum)"
            if cash_ok
            else _info_request("cash split: freely available / restricted / operating minimum")
        ),
        "action": _CASH_RULE,
    })

    coc_ok = any(
        isinstance(r, dict)
        and _is_filled(r.get("trigger"))
        and not str(r.get("trigger")).startswith("Information")
        for r in coc
    )
    rows.append({
        "check": "change_of_control_consents",
        "status": "PASS" if coc_ok else "FAIL",
        "finding": (
            "CoC / prepayment / consent evidence present"
            if coc_ok
            else _info_request("change-of-control / prepayment / consent clauses")
        ),
        "action": _COC_RULE,
    })

    net_ok = any(
        isinstance(r, dict)
        and "net debt" in str(r.get("component") or "").lower()
        and isinstance(r.get("amount"), (int, float))
        for r in net_debt
    )
    sourced = all(
        isinstance(r, dict) and _is_filled(r.get("source")) and r.get("source") != _NA
        for r in net_debt
        if isinstance(r, dict) and "net debt" not in str(r.get("component") or "").lower()
    ) if net_debt else False
    rows.append({
        "check": "net_debt_bridge_sourced",
        "status": "PASS" if net_ok and (sourced or schedule_complete) else "FAIL",
        "finding": (
            "Net debt bridge closed with sourced lines"
            if net_ok
            else _info_request("sourced net debt bridge (gross − free cash + debt-like)")
        ),
        "action": _NET_DEBT_RULE,
    })

    cap_filled = any(
        isinstance(r, dict)
        and _is_filled(r.get("holder"))
        and not str(r.get("holder")).startswith("Information")
        and (
            isinstance(r.get("fully_diluted_pct"), (int, float))
            or r.get("fully_diluted_basis")
        )
        for r in cap_table
    )
    rows.append({
        "check": "cap_table_fully_diluted",
        "status": "PASS" if cap_filled else "FAIL",
        "finding": (
            "Fully diluted cap table present"
            if cap_filled
            else _info_request("fully diluted capitalisation table")
        ),
        "action": _CAP_TABLE_RULE,
    })

    lev_status = str(leverage_disc.get("status") or "")
    lev_ok = lev_status in {
        "computed_on_approved_ebitda",
        "alt_metrics_negative_ebitda",
    }
    rows.append({
        "check": "approved_ebitda_leverage",
        "status": "PASS" if lev_ok else "FAIL",
        "finding": (
            f"Leverage discipline: {lev_status}"
            if lev_ok
            else _info_request("approved EBITDA (or alt metrics if negative)")
        ),
        "action": _APPROVED_EBITDA_RULE,
    })

    classes = {
        str(r.get("classification") or "")
        for r in financing_link if isinstance(r, dict)
    }
    fin_ok = any(
        isinstance(r, dict)
        and _is_filled(r.get("facility"))
        and not str(r.get("facility")).startswith("Information")
        for r in financing_link
    ) and (
        any("acquisition" in c for c in classes)
        or any("existing" in c or "refinanc" in c for c in classes)
    )
    rows.append({
        "check": "financing_vs_acquisition",
        "status": "PASS" if fin_ok else "FAIL",
        "finding": (
            f"Financing classes: {', '.join(sorted(classes)) or 'none'}"
            if fin_ok
            else _info_request("existing/refi vs acquisition financing classification")
        ),
        "action": _FINANCING_LINK_RULE,
    })

    # Silence unused facilities warning for QA context
    _ = facilities
    return rows


def _questions_from_cap_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("cap_evidence_qa")
        if isinstance(spec.get("cap_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("facility_schedule_complete"):
        out.append(normalize_question({
            "question": "Complete the facility schedule (lender, drawn, rate, maturity, security, covenants)",
            "required_records": "Loan agreements + debt ledger reconcile",
            "decision_effect": "Incomplete schedule makes leverage wrong, not approximate",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "facility_schedule_complete QA PASS",
            "interim_treatment": "BLOCKED — withhold leverage",
        }))
    if _qa_fail("debt_like_catalogue"):
        out.append(normalize_question({
            "question": "Catalogue and size debt-like items (overdue creditors, dividends, leases, etc.)",
            "required_records": "AP ageing + notes to accounts + lease schedule",
            "decision_effect": "Off-schedule obligations understate funding need",
            "priority": "signing_condition",
            "owner": "financial diligence lead",
            "timing": "per deal timetable",
            "closure_test": "debt_like_catalogue QA PASS",
            "interim_treatment": "LIMITED — treat catalogue as open",
        }))
    if _qa_fail("cash_split_free_restricted_minimum"):
        out.append(normalize_question({
            "question": "Split cash into freely available, restricted and operating minimum",
            "required_records": "Bank confirmations + escrow / lien schedule",
            "decision_effect": "Only free cash counts against debt in full",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "cash_split_free_restricted_minimum QA PASS",
            "interim_treatment": "Do not net restricted cash against debt",
        }))
    if _qa_fail("change_of_control_consents"):
        out.append(normalize_question({
            "question": "Extract CoC, prepayment and consent triggers from facility documents",
            "required_records": "Facility agreements + intercreditor",
            "decision_effect": "Unexpected prepay / consent can break the funding plan",
            "priority": "signing_condition",
            "owner": "legal / financial diligence",
            "timing": "before signing",
            "closure_test": "change_of_control_consents QA PASS",
            "interim_treatment": "LIMITED — assume CoC risk open",
        }))
    if _qa_fail("net_debt_bridge_sourced"):
        out.append(normalize_question({
            "question": "Produce a sourced net debt bridge (gross − free cash + debt-like)",
            "required_records": "Facility schedule + cash split + debt-like sizes",
            "decision_effect": "Completion funding position is unproven",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "net_debt_bridge_sourced QA PASS",
            "interim_treatment": "BLOCKED — no invented net debt",
        }))
    if _qa_fail("cap_table_fully_diluted"):
        out.append(normalize_question({
            "question": "Provide a fully diluted capitalisation table (options, warrants, convertibles)",
            "required_records": "Cap table + option / warrant / convertible registers",
            "decision_effect": "Undiluted equity misstates ownership and proceeds",
            "priority": "signing_condition",
            "owner": "legal / financial diligence",
            "timing": "per deal timetable",
            "closure_test": "cap_table_fully_diluted QA PASS",
            "interim_treatment": "LIMITED — treat dilution as open",
        }))
    if _qa_fail("approved_ebitda_leverage"):
        out.append(normalize_question({
            "question": "Supply approved EBITDA for leverage, or alt metrics if EBITDA is negative",
            "required_records": "QoE / approved EBITDA bridge (or debt/revenue if negative)",
            "decision_effect": "Unapproved or negative EBITDA makes ND/EBITDA misleading",
            "priority": "mandatory_pre_decision",
            "owner": "financial diligence lead",
            "timing": "before IC",
            "closure_test": "approved_ebitda_leverage QA PASS",
            "interim_treatment": "Withhold ND/EBITDA until approved figure",
        }))
    if _qa_fail("financing_vs_acquisition"):
        out.append(normalize_question({
            "question": "Classify facilities as existing/refinancing vs acquisition/transaction financing",
            "required_records": "Sources & uses + facility purpose schedules",
            "decision_effect": "Buyer must see new money vs take-out clearly",
            "priority": "signing_condition",
            "owner": "financial diligence lead",
            "timing": "per deal timetable",
            "closure_test": "financing_vs_acquisition QA PASS",
            "interim_treatment": "LIMITED — do not blend facility purposes",
        }))
    return out


def _quality_reliance(
    *,
    facilities: list[dict[str, Any]],
    debt_like: list[dict[str, Any]],
    cash: list[dict[str, Any]],
    coc: list[dict[str, Any]],
    net_debt: list[dict[str, Any]],
    schedule_complete: bool,
    schedule_gaps: list[str],
) -> tuple[str, str, str]:
    real_facilities = sum(
        1 for f in facilities
        if isinstance(f, dict)
        and _is_filled(f.get("facility"))
        and not str(f.get("facility")).startswith("Information")
        and isinstance(f.get("drawn_balance"), (int, float))
    )
    cash_free_filled = any(
        isinstance(c, dict)
        and "freely" in str(c.get("bucket") or "").lower()
        and _is_filled(c.get("amount"))
        and not str(c.get("amount")).startswith("Information")
        for c in cash
    )
    debt_like_filled = any(
        isinstance(d, dict)
        and _is_filled(d.get("item"))
        and not str(d.get("item")).startswith("Information")
        and isinstance(d.get("amount"), (int, float))
        for d in debt_like
    )
    coc_filled = any(
        isinstance(r, dict)
        and _is_filled(r.get("trigger"))
        and not str(r.get("trigger")).startswith("Information")
        for r in coc
    )
    net_closed = any(
        isinstance(r, dict)
        and "net debt" in str(r.get("component") or "").lower()
        and isinstance(r.get("amount"), (int, float))
        for r in net_debt
    )

    if schedule_complete and real_facilities >= 1 and cash_free_filled:
        quality = "PASS"
    elif real_facilities >= 1:
        quality = "REWORK"
    else:
        quality = "REWORK"

    if schedule_complete and cash_free_filled and net_closed:
        reliance = "READY"
    elif real_facilities >= 1:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: facility schedule "
        f"{'complete' if schedule_complete else 'incomplete'} "
        f"({real_facilities} facility(ies) with balances).",
        f"Reliance {reliance}: "
        f"{'funding position usable' if reliance == 'READY' else 'gaps remain'}.",
    ]
    if schedule_gaps:
        bits.append("Gaps: " + "; ".join(schedule_gaps[:2]) + ".")
    if not cash_free_filled:
        bits.append("Freely available cash not yet evidenced.")
    if not debt_like_filled:
        bits.append("Debt-like items not yet sized.")
    if not coc_filled:
        bits.append("Change-of-control / prepayment / consents still an information request.")
    bits.append(_LEVERAGE_RULE)
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_capital_structure_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    hp_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    facilities = _facilities_from_legacy_and_corpus(corpus, legacy)
    complete, gaps = _schedule_complete(facilities)
    reconciliation = _bs_reconciliation(facilities, legacy, corpus)
    debt_like = _debt_like_items(corpus, facilities)
    cash = _cash_split(corpus, legacy)
    coc = _change_of_control(corpus)
    net_debt = _net_debt_bridge(
        facilities, debt_like, cash, legacy, schedule_complete=complete
    )
    cap_table = _extract_cap_table(corpus, legacy)
    financing_link = _financing_vs_acquisition(facilities, corpus)
    leverage_disc = _leverage_discipline(
        schedule_complete=complete,
        schedule_gaps=gaps,
        legacy=legacy,
        corpus=corpus,
        net_debt=net_debt,
        hp_spec=hp_spec,
    )
    instruments, total, leverage, dcf, notes = _legacy_dual_write(
        facilities=facilities,
        schedule_complete=complete,
        schedule_gaps=gaps,
        legacy=legacy,
        corpus=corpus,
        leverage_discipline=leverage_disc,
    )
    cap_qa = _cap_evidence_qa(
        facilities=facilities,
        debt_like=debt_like,
        cash=cash,
        coc=coc,
        net_debt=net_debt,
        cap_table=cap_table,
        financing_link=financing_link,
        leverage_disc=leverage_disc,
        schedule_complete=complete,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in cap_qa)

    quality, reliance, rationale = _quality_reliance(
        facilities=facilities,
        debt_like=debt_like,
        cash=cash,
        coc=coc,
        net_debt=net_debt,
        schedule_complete=complete,
        schedule_gaps=gaps,
    )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale = "Capital structure QA has open FAILs — reliance limited. " + rationale

    bits = [f"Capital Structure for {company}"]
    if total is not None:
        bits.append(f"gross debt ~{total:g} USD M")
    bits.append(f"{len([f for f in facilities if isinstance(f.get('drawn_balance'), (int, float))])} facility(ies)")
    bits.append("schedule complete" if complete else "schedule incomplete — leverage withheld")
    if gaps:
        bits.append(f"{len(gaps)} gap(s)")

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "facilities": facilities,
        "balance_sheet_reconciliation": reconciliation,
        "debt_like_items": debt_like,
        "cash_split": cash,
        "change_of_control": coc,
        "net_debt_bridge": net_debt,
        "cap_table": cap_table,
        "financing_vs_acquisition": financing_link,
        "leverage_discipline": leverage_disc,
        "cap_evidence_qa": cap_qa,
        "schedule_complete": complete,
        "schedule_gaps": gaps,
        # Legacy dual-write
        "debt_instruments": instruments,
        "debt_total_usd_m": total,
        "leverage_ratios": leverage,
        "dcf_metrics": dcf,
        "capital_notes": notes[:10],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not instruments and total is None,
    }
    out["questions"] = _questions_from_cap_gaps(out)
    return out


def _llm_capital_structure_spec(
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
            "capital_structure",
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
        "facilities: [{facility, lender, drawn_balance, rate, repayment_profile, "
        "maturity, security, guarantees, covenants_headroom, source, notes}],\n"
        "balance_sheet_reconciliation: [{line, amount, source, notes}],\n"
        "debt_like_items: [{item, kind, amount, where_sits, source, notes}],\n"
        "cash_split: [{bucket, amount, counts_against_debt, detail, source, notes}],\n"
        "change_of_control: [{trigger, kind, consequence, source, notes}],\n"
        "net_debt_bridge: [{component, amount, sign, source, notes}],\n"
        "cap_table: [{holder, instrument, shares, fully_diluted_pct, source, notes}],\n"
        "financing_vs_acquisition: [{facility, classification, drawn_balance, "
        "evidence, source, notes}],\n"
        "leverage_discipline: {status, ebitda, ebitda_label, ebitda_approved, "
        "ratios, alt_metrics, notes, source},\n"
        "schedule_complete: boolean,\n"
        "schedule_gaps: [string],\n"
        "debt_instruments: [{name, amount_usd_m}],\n"
        "debt_total_usd_m: number|null,\n"
        "leverage_ratios: {string: number|string},\n"
        "dcf_metrics: {string: number},\n"
        "capital_notes: [string],\n"
        "cap_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "facility_schedule_complete, debt_like_catalogue, "
        "cash_split_free_restricted_minimum, change_of_control_consents, "
        "net_debt_bridge_sourced, cap_table_fully_diluted, approved_ebitda_leverage, "
        "financing_vs_acquisition,\n"
        "questions: [{question, required_records, decision_effect, priority, owner, "
        "timing, closure_test, interim_treatment}],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "Do NOT calculate leverage if the facility schedule is incomplete. "
        "Leverage only on approved EBITDA; alt metrics if negative. "
        "No invest or pass."
    )
    try:
        return generate_json(system=system, user=user, temperature=0.1)
    except Exception:
        return None


def _normalise_llm_spec(
    raw: dict[str, Any],
    *,
    heur: dict[str, Any],
    sources: list[str],
    legacy: dict[str, Any],
    corpus: str = "",
    hp_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm = dict(raw) if isinstance(raw, dict) else {}

    def _rows(key: str, need: str) -> list[dict[str, Any]]:
        rows = llm.get(key) if isinstance(llm.get(key), list) else []
        rows = [r for r in rows if isinstance(r, dict) and r.get(need)]
        return rows or list(heur.get(key) or [])

    facilities = _rows("facilities", "facility")
    for row in facilities:
        row["notes"] = _FACILITY_RULE
    llm["facilities"] = facilities

    recon = _rows("balance_sheet_reconciliation", "line")
    for row in recon:
        row["notes"] = _FACILITY_RULE
    llm["balance_sheet_reconciliation"] = recon or heur.get("balance_sheet_reconciliation") or []

    debt_like = _rows("debt_like_items", "item")
    for row in debt_like:
        row["notes"] = _DEBT_LIKE_RULE
    llm["debt_like_items"] = debt_like

    cash = _rows("cash_split", "bucket")
    for row in cash:
        row["notes"] = _CASH_RULE
    llm["cash_split"] = cash

    coc = _rows("change_of_control", "trigger")
    for row in coc:
        row["notes"] = _COC_RULE
    llm["change_of_control"] = coc

    net_debt = _rows("net_debt_bridge", "component")
    for row in net_debt:
        row["notes"] = _NET_DEBT_RULE
    llm["net_debt_bridge"] = net_debt

    cap_table = _rows("cap_table", "holder")
    for row in cap_table:
        row["notes"] = _CAP_TABLE_RULE
    llm["cap_table"] = cap_table or heur.get("cap_table") or []

    financing_link = _rows("financing_vs_acquisition", "facility")
    for row in financing_link:
        row["notes"] = _FINANCING_LINK_RULE
    llm["financing_vs_acquisition"] = financing_link or heur.get("financing_vs_acquisition") or []

    complete_heur, gaps_heur = _schedule_complete(facilities)
    if "schedule_complete" in llm:
        complete = bool(llm.get("schedule_complete")) and complete_heur
    else:
        complete = complete_heur
    gaps = llm.get("schedule_gaps") if isinstance(llm.get("schedule_gaps"), list) else []
    gaps = [str(g).strip() for g in gaps if str(g).strip()] or gaps_heur
    llm["schedule_complete"] = complete
    llm["schedule_gaps"] = gaps[:8]

    leverage_disc = _leverage_discipline(
        schedule_complete=complete,
        schedule_gaps=gaps,
        legacy={
            **legacy,
            "leverage_ratios": llm.get("leverage_ratios")
            if isinstance(llm.get("leverage_ratios"), dict)
            else legacy.get("leverage_ratios"),
        },
        corpus=corpus,
        net_debt=net_debt,
        hp_spec=hp_spec,
    )
    llm["leverage_discipline"] = leverage_disc

    instruments, total, leverage, dcf, notes = _legacy_dual_write(
        facilities=facilities,
        schedule_complete=complete,
        schedule_gaps=gaps,
        legacy={
            **legacy,
            "leverage_ratios": llm.get("leverage_ratios")
            if isinstance(llm.get("leverage_ratios"), dict)
            else legacy.get("leverage_ratios"),
            "dcf_metrics": llm.get("dcf_metrics")
            if isinstance(llm.get("dcf_metrics"), dict)
            else legacy.get("dcf_metrics"),
            "capital_notes": llm.get("capital_notes")
            if isinstance(llm.get("capital_notes"), list)
            else legacy.get("capital_notes"),
            "debt_total_usd_m": llm.get("debt_total_usd_m", legacy.get("debt_total_usd_m")),
        },
        corpus=corpus,
        leverage_discipline=leverage_disc,
    )
    llm["debt_instruments"] = instruments or heur.get("debt_instruments") or []
    llm["debt_total_usd_m"] = total if total is not None else heur.get("debt_total_usd_m")
    llm["leverage_ratios"] = leverage
    llm["dcf_metrics"] = dcf or heur.get("dcf_metrics") or {}
    llm["capital_notes"] = notes

    cap_qa = _cap_evidence_qa(
        facilities=facilities,
        debt_like=debt_like,
        cash=cash,
        coc=coc,
        net_debt=net_debt,
        cap_table=llm["cap_table"],
        financing_link=llm["financing_vs_acquisition"],
        leverage_disc=leverage_disc,
        schedule_complete=complete,
    )
    llm["cap_evidence_qa"] = cap_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in cap_qa)

    quality, reliance, rationale = _quality_reliance(
        facilities=facilities,
        debt_like=debt_like,
        cash=cash,
        coc=coc,
        net_debt=net_debt,
        schedule_complete=complete,
        schedule_gaps=gaps,
    )
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
    llm["reliance_verdict"] = rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
    llm["quality_reliance_rationale"] = (
        _soften_invest(_clean(llm.get("quality_reliance_rationale"), 460))
        if str(llm.get("quality_reliance_rationale") or "").strip()
        else rationale
    )
    if qa_fail and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Capital structure QA has open FAILs — reliance limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )

    if not llm.get("questions"):
        llm["questions"] = _questions_from_cap_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_cap_gaps(llm)

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not llm.get("debt_instruments") and llm.get("debt_total_usd_m") is None
    return llm


def build_capital_structure_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    hp_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_capital_structure_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources
    if not srcs:
        srcs = [
            str(d.get("filename"))
            for d in ((idx or {}).get("documents") or [])
            if isinstance(d, dict) and d.get("filename")
        ][:8]

    seed_bits: list[str] = []
    for b in legacy.get("debt_instruments") or []:
        if isinstance(b, dict) and b.get("name") is not None:
            amt = b.get("amount_usd_m")
            seed_bits.append(
                f"{b['name']} — USD {amt}M" if amt is not None else str(b["name"])
            )
    if legacy.get("debt_total_usd_m") is not None:
        seed_bits.append(f"Total debt USD {legacy['debt_total_usd_m']}M")
    for note in legacy.get("capital_notes") or []:
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    seed = "\n".join(seed_bits)
    full_corpus = "\n\n".join(x for x in (corpus or "", seed) if x.strip())

    heur = _heuristic_capital_structure_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        geography=vars_.get("geography"),
        legacy_spec=legacy,
        hp_spec=hp_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm_raw = _llm_capital_structure_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
        deal_perimeter=vars_.get("deal_perimeter"),
        transaction_type=vars_.get("transaction_type"),
        as_of_date=vars_.get("as_of_date"),
        review_periods=vars_.get("review_periods"),
        decision_stage=vars_.get("decision_stage"),
    )
    if not llm_raw:
        return heur
    out = _normalise_llm_spec(
        llm_raw,
        heur=heur,
        sources=srcs,
        legacy=legacy,
        corpus=full_corpus,
        hp_spec=hp_spec,
    )
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_capital_structure_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    facilities = spec.get("facilities") if isinstance(spec.get("facilities"), list) else []
    recon = (
        spec.get("balance_sheet_reconciliation")
        if isinstance(spec.get("balance_sheet_reconciliation"), list) else []
    )
    debt_like = (
        spec.get("debt_like_items") if isinstance(spec.get("debt_like_items"), list) else []
    )
    cash = spec.get("cash_split") if isinstance(spec.get("cash_split"), list) else []
    coc = (
        spec.get("change_of_control")
        if isinstance(spec.get("change_of_control"), list) else []
    )
    net_debt = (
        spec.get("net_debt_bridge") if isinstance(spec.get("net_debt_bridge"), list) else []
    )
    instruments = (
        spec.get("debt_instruments") if isinstance(spec.get("debt_instruments"), list) else []
    )
    leverage = (
        spec.get("leverage_ratios") if isinstance(spec.get("leverage_ratios"), dict) else {}
    )
    dcf = spec.get("dcf_metrics") if isinstance(spec.get("dcf_metrics"), dict) else {}
    notes = spec.get("capital_notes") if isinstance(spec.get("capital_notes"), list) else []
    gaps = spec.get("schedule_gaps") if isinstance(spec.get("schedule_gaps"), list) else []
    complete = bool(spec.get("schedule_complete"))
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_LEVERAGE_RULE}\n\n")

    # 1
    parts.append("## 1. Facility Schedule\n\n")
    parts.append(f"{_FACILITY_RULE}\n\n")
    if facilities:
        parts.append(_table(
            [
                "Facility", "Lender", "Drawn", "Rate", "Repayment",
                "Maturity", "Security", "Covenants / headroom", "Source",
            ],
            [
                [
                    _clean(r.get("facility"), 40),
                    _clean(r.get("lender"), 40),
                    (
                        _fmt_amt(r.get("drawn_balance"))
                        if isinstance(r.get("drawn_balance"), (int, float))
                        else _clean(r.get("drawn_balance"), 40)
                    ),
                    _clean(r.get("rate"), 40),
                    _clean(r.get("repayment_profile"), 40),
                    _clean(r.get("maturity"), 40),
                    _clean(r.get("security"), 40),
                    _clean(r.get("covenants_headroom"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in facilities if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('facility-by-facility schedule from loan docs')}**\n\n")
    parts.append(
        f"**Schedule status:** {'Complete' if complete else 'Incomplete'}"
        f"{' — leverage withheld' if not complete else ''}\n\n"
    )
    if gaps:
        parts.append("### Schedule gaps\n\n")
        for g in gaps[:8]:
            parts.append(f"- {_clean(g, 200)}\n")
        parts.append("\n")
    if recon:
        parts.append("### Reconciliation to balance sheet / reported debt\n\n")
        parts.append(_table(
            ["Line", "Amount", "Source"],
            [
                [
                    _clean(r.get("line"), 80),
                    (
                        _fmt_amt(r.get("amount"))
                        if isinstance(r.get("amount"), (int, float))
                        else _clean(r.get("amount"), 60)
                    ),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in recon if isinstance(r, dict)
            ],
        ))
    if instruments:
        parts.append("### Legacy instruments (dual-write)\n\n")
        parts.append(_table(
            ["Instrument", "Amount (USD M)"],
            [
                [
                    _clean(i.get("name"), 60),
                    _fmt_amt(i.get("amount_usd_m"), unit="")
                    if i.get("amount_usd_m") is not None else "—",
                ]
                for i in instruments if isinstance(i, dict)
            ],
        ))
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Debt-like Items\n\n")
    parts.append(f"{_DEBT_LIKE_RULE}\n\n")
    if debt_like:
        parts.append(_table(
            ["Item", "Kind", "Amount", "Where it sits", "Source"],
            [
                [
                    _clean(r.get("item"), 80),
                    _clean(r.get("kind"), 40),
                    (
                        _fmt_amt(r.get("amount"))
                        if isinstance(r.get("amount"), (int, float))
                        else _clean(r.get("amount"), 40)
                    ),
                    _clean(r.get("where_sits"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in debt_like if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('debt-like items sized')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Cash Split\n\n")
    parts.append(f"{_CASH_RULE}\n\n")
    if cash:
        parts.append(_table(
            ["Bucket", "Amount", "Counts against debt?", "Detail", "Source"],
            [
                [
                    _clean(r.get("bucket"), 40),
                    _clean(r.get("amount"), 40),
                    _clean(r.get("counts_against_debt"), 40),
                    _clean(r.get("detail"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in cash if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('cash split: freely available / restricted / operating minimum')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Change of Control, Prepayment & Consents\n\n")
    parts.append(f"{_COC_RULE}\n\n")
    if coc:
        parts.append(_table(
            ["Trigger / clause", "Kind", "Consequence at completion", "Source"],
            [
                [
                    _clean(r.get("trigger"), 100),
                    _clean(r.get("kind"), 40),
                    _clean(r.get("consequence"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in coc if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('change-of-control / prepayment / consent provisions')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Net Debt Bridge (Sourced)\n\n")
    parts.append(f"{_NET_DEBT_RULE}\n\n")
    if net_debt:
        parts.append(_table(
            ["Component", "Sign", "Amount", "Source"],
            [
                [
                    _clean(r.get("component"), 80),
                    _clean(r.get("sign"), 8),
                    (
                        _fmt_amt(r.get("amount"))
                        if isinstance(r.get("amount"), (int, float))
                        else _clean(r.get("amount"), 60)
                    ),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in net_debt if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('sourced net debt bridge')}**\n\n")
    cap_table = spec.get("cap_table") if isinstance(spec.get("cap_table"), list) else []
    financing_link = (
        spec.get("financing_vs_acquisition")
        if isinstance(spec.get("financing_vs_acquisition"), list) else []
    )
    leverage_disc = (
        spec.get("leverage_discipline")
        if isinstance(spec.get("leverage_discipline"), dict) else {}
    )

    if cap_table:
        parts.append("### Fully diluted cap table\n\n")
        parts.append(f"{_CAP_TABLE_RULE}\n\n")
        parts.append(_table(
            ["Holder", "Instrument", "Shares", "Fully diluted %", "Source"],
            [
                [
                    _clean(r.get("holder"), 60),
                    _clean(r.get("instrument"), 40),
                    _clean(r.get("shares"), 40),
                    (
                        f"{float(r['fully_diluted_pct']):g}%"
                        if isinstance(r.get("fully_diluted_pct"), (int, float))
                        else _clean(r.get("fully_diluted_pct"), 40)
                    ),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in cap_table if isinstance(r, dict)
            ],
        ))

    if financing_link:
        parts.append("### Financing vs acquisition debt\n\n")
        parts.append(f"{_FINANCING_LINK_RULE}\n\n")
        parts.append(_table(
            ["Facility", "Classification", "Drawn", "Evidence", "Source"],
            [
                [
                    _clean(r.get("facility"), 60),
                    _clean(r.get("classification"), 40),
                    (
                        _fmt_amt(r.get("drawn_balance"))
                        if isinstance(r.get("drawn_balance"), (int, float))
                        else _clean(r.get("drawn_balance"), 40)
                    ),
                    _clean(r.get("evidence"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in financing_link if isinstance(r, dict)
            ],
        ))

    if leverage:
        parts.append("### Leverage / related metrics\n\n")
        parts.append(f"{_APPROVED_EBITDA_RULE}\n\n")
        if not complete or "leverage_withheld" in leverage:
            parts.append(f"*{_LEVERAGE_RULE}*\n\n")
        if leverage_disc:
            parts.append(
                f"- Discipline status: `{_clean(leverage_disc.get('status'), 60)}`\n"
                f"- EBITDA: {_clean(leverage_disc.get('ebitda_label'), 120)} "
                f"(approved: {'yes' if leverage_disc.get('ebitda_approved') else 'no'})\n"
            )
            for alt in (leverage_disc.get("alt_metrics") or [])[:4]:
                parts.append(f"- Alt: {_clean(alt, 160)}\n")
            parts.append("\n")
        for k, v in list(leverage.items())[:10]:
            if isinstance(v, (int, float)):
                parts.append(f"- `{k}`: {v:g}\n")
            else:
                parts.append(f"- `{k}`: {_clean(v, 200)}\n")
        parts.append("\n")
    if dcf:
        parts.append("### Legacy DCF metrics (dual-write — not a funding substitute)\n\n")
        for k, v in list(dcf.items())[:8]:
            parts.append(f"- `{k}`: {v:g}\n" if isinstance(v, (int, float)) else f"- `{k}`: {v}\n")
        parts.append("\n")
    if notes:
        parts.append("### Notes\n\n")
        for n in notes[:6]:
            parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This section does not recommend invest or pass. Leverage is not calculated "
        "from an incomplete facility schedule. Only freely available cash counts "
        "against debt in full. Cap table is fully diluted. Existing / refi facilities "
        "are separated from acquisition financing.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    cap_qa = (
        spec.get("cap_evidence_qa")
        if isinstance(spec.get("cap_evidence_qa"), list) else []
    )
    parts.append("## 6. Capital Structure Evidence QA\n\n")
    parts.append(
        "QA enforces facility-schedule completeness, debt-like catalogue, cash split, "
        "CoC/consents, sourced net-debt bridge, fully diluted cap table, approved-EBITDA "
        "leverage discipline, and financing vs acquisition classification.\n\n"
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
                for r in cap_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('capital structure evidence QA rows')}\n\n"
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
        parts.append(f"{_info_request('Questions for material capital-structure gaps')}\n\n")
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
    parts.append(f"**Quality:** {_clean(qv, 20)} — is the funding map accurate and honest about limits?\n\n")
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — can diligence rest on this completion "
        "funding position?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open capital-structure QA FAILs cap READY → LIMITED. "
        "This agent does not issue an invest or pass recommendation.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"{i}. {_clean(name, 120)}\n")
    else:
        parts.append(f"1. {_NA}\n")
    parts.append("\n")
    return "".join(parts)
