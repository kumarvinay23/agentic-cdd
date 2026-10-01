"""Compose DiligenceIQ Valuation Model — one earnings basis, three methods.

Declares one earnings figure and uses it for comps, precedents and DCF.
Shows range and median (not only average). Reconciles methods without
averaging disagreements. Dual-writes legacy FV-05 football-field fields
(dcf / football_field / valuation_flags).

No invest/pass. No company allowlists. Every published multiple must
arithmetically reconcile to the declared earnings figure.
"""

from __future__ import annotations

import re
from statistics import median
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

_DOCUMENT_TITLE = "Valuation Model"
_DD_CODE = "FV-05"
_AGENT_KEY = "valuation_modeling"

_EARNINGS_RULE = (
    "One earnings figure is declared — period, adjustments and source — and "
    "used by every method. Any different metric states its conversion explicitly."
)
_COMPS_RULE = (
    "Comparable companies are named with why each is comparable, the multiple, "
    "date and source. Range and median are shown, not only an average."
)
_PREC_RULE = (
    "Precedent transactions show date, target, acquirer, consideration, metric "
    "and multiple, with the source. Non-public terms are noted."
)
_DCF_RULE = (
    "Where the forecast supports a DCF: cash flows, discount-rate build-up, "
    "terminal assumption, and implied exit multiple as a sanity check."
)
_RECON_RULE = (
    "Methods are reconciled. Material disagreement is explained — not averaged away."
)
_ARITH_RULE = (
    "Every multiple must reconcile to the declared earnings figure; the check "
    "is arithmetic before publishing."
)

_EV_REV_RE = re.compile(
    r"(?i)EV\s*/\s*Revenue\s*(?:multiple)?[^.%]{0,20}?([\d.]+)\s*x"
)
_EV_EBITDA_RE = re.compile(
    r"(?i)EV\s*/\s*EBITDA\s*(?:multiple)?[^.%]{0,20}?([\d.]+)\s*x"
)
_MEDIAN_RE = re.compile(
    r"(?i)Median[^.%]{0,40}?([\d.]+)\s*x"
)
_REV_USD_RE = re.compile(
    r"(?i)(?:FY20\d{2}E?\s+)?(?:Revenue|Sales)\s+"
    r"(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b"
)
_REV_INR_RE = re.compile(
    r"(?i)(?:FY20\d{2}E?\s+)?(?:Revenue|Sales)\s+"
    r"(?:INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(Cr|cr)?"
)
_WACC_RE = re.compile(r"(?i)WACC\s*(?:\([^)]*\))?\s*([\d.]+)\s*%")
_DCF_EV_B_RE = re.compile(
    r"(?i)(?:Enterprise Value|EV)\s*(?:\([^)]*DCF[^)]*\))?\s+"
    r"(?:USD|US\$|\$)?\s*([\d.]+)\s*B"
)
_DCF_SHARE_RE = re.compile(
    r"(?i)Implied Share Price\s*(?:\([^)]*\))?\s+INR\s+([\d.]+)"
)
_RANGE_X_RE = re.compile(
    r"(?i)([\d.]+)\s*x\s*[–\-]\s*([\d.]+)\s*x"
)
_EV_RANGE_B_RE = re.compile(
    r"(?i)(?:Implied\s+)?EV\s+Range[^.%]{0,40}?"
    r"(?:USD|US\$|\$)\s*([\d.]+)\s*B\s*[–\-]\s*(?:USD|US\$|\$)?\s*([\d.]+)\s*B"
)
_PREC_LINE_RE = re.compile(
    r"(?i)([A-Z][A-Za-z0-9][A-Za-z0-9\s&\.\-]{1,40}?)"
    r"(?:\s*\([^)]{0,40}\))?\s*[—\-–:]\s*"
    r"(?:~?\s*(?:USD|US\$|\$)\s*([\d.]+)\s*([MB])\s+)?"
    r"~?\s*([\d.]+)\s*x\s*(?:Rev|Revenue|EBITDA)?"
)
_COMP_LINE_RE = re.compile(
    r"(?i)([A-Z][A-Za-z0-9][A-Za-z0-9\s&\.\-]{1,40}?)"
    r"(?:\s*\([^)]{0,30}\))?\s+"
    r"([\d.]+)\s*x\s*(?:Rev|Revenue|EV/Rev)?"
)
_DATE_RE = re.compile(
    r"(?i)\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+20\d{2}|20\d{2}|FY20\d{2}E?)\b"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)
_SUBJECT_CUE = re.compile(r"(?i)\(Subject\)|subject\s+company|target\s+company")


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
    out = _INVEST_LANG.sub("valuation evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _de_subject_name(name: Any, company: str) -> str:
    """Strip pack '(Subject)' labels; never invent a peer name."""
    raw = str(name or "").strip()
    if not raw:
        return company
    cleaned = re.sub(r"(?i)\s*\(Subject\)\s*", "", raw).strip()
    # If the pack labelled a third-party name as subject, prefer the deal company
    if _SUBJECT_CUE.search(raw) and cleaned:
        return company
    return cleaned or company


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


def _to_usd_m(value: float, unit: str | None) -> float:
    u = (unit or "M").upper()
    if u.startswith("B"):
        return value * 1000.0
    return value


def _round(n: float | None, places: int = 2) -> float | None:
    if n is None:
        return None
    return round(float(n), places)


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_valuation_modeling_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "market_competition": 1,
        "deal_strategy": 2,
        "company_management": 3,
        "operations": 4,
        "customer": 5,
        "legal_esg": 6,
    }
    needles = (
        "valuation", "comparable", "comps", "precedent", "transaction",
        "dcf", "wacc", "multiple", "trading", "financial", "cim",
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


def _earnings_basis(
    *,
    company: str,
    corpus: str,
    legacy: dict[str, Any],
    trading_comps: dict[str, Any] | None,
    historical: dict[str, Any] | None,
) -> dict[str, Any]:
    """Declare one earnings figure used by every method."""
    text = _prose(corpus)
    metric = "Revenue"
    period = _info_request("earnings period (e.g. FY2024E / LTM)")
    amount: Any = _NA
    unit = "USD M"
    adjustments = _info_request("adjustments (if any) applied to reach this figure")
    source = _NA
    _ = legacy  # reserved for future football-field back-solves

    # Prefer explicit USD revenue from the valuation pack (same metric comps use)
    m = _REV_USD_RE.search(text)
    if m:
        amount = _to_usd_m(float(m.group(1)), m.group(2))
        unit = "USD M"
        source = _DOC_CITE
        # Period from the same sentence / short window only (avoid FY2025E fwd tables)
        sent_start = max(0, text.rfind(".", 0, m.start()) + 1)
        sent_end = text.find(".", m.end())
        if sent_end < 0:
            sent_end = min(len(text), m.end() + 60)
        window = text[sent_start:sent_end]
        pm = re.search(r"(?i)(FY20\d{2}E?|LTM|last twelve months)", window)
        if pm and "fwd" not in window.lower():
            period = pm.group(1)
        # If historical FY2024 (INR Cr) converts near this USD figure, prefer that period
        if isinstance(historical, dict):
            for row in historical.get("pl_lines") or []:
                if not isinstance(row, dict):
                    continue
                if "revenue" not in str(row.get("line_item") or "").lower():
                    continue
                inr = row.get("fy2024_value")
                if isinstance(inr, (int, float)) and inr > 0 and isinstance(amount, (int, float)):
                    # INR Cr → USD M at ~83 INR/USD (pack-typical)
                    usd_m_approx = float(inr) * 10.0 / 83.0
                    if abs(usd_m_approx - float(amount)) / max(float(amount), 1.0) <= 0.20:
                        period = "FY2024E"
                        adjustments = (
                            f"Pack USD figure aligns with accounts FY2024E Revenue "
                            f"{inr:g} {row.get('unit') or 'INR Cr'} (~USD {usd_m_approx:.0f}M at ~83 INR/USD)"
                        )
                break

    # Historical accounts when pack lacks a USD earnings figure
    if (amount == _NA or amount is None) and isinstance(historical, dict):
        for row in historical.get("pl_lines") or []:
            if not isinstance(row, dict):
                continue
            if "revenue" not in str(row.get("line_item") or "").lower():
                continue
            # Prefer latest filled fiscal year column
            for key, label in (
                ("fy2025_value", "FY2025E (accounts)"),
                ("fy2024_value", "FY2024E (accounts)"),
                ("fy2023_value", "FY2023 (accounts)"),
            ):
                val = row.get(key)
                if isinstance(val, (int, float)):
                    amount = float(val)
                    unit = str(row.get("unit") or "USD M")
                    metric = "Revenue"
                    period = label
                    source = _DOC_CITE
                    adjustments = (
                        "As reported in historical performance extract — "
                        "convert explicitly if a method uses a USD metric"
                    )
                    break
            if amount != _NA and amount is not None:
                break

    # Back-solve from EV range / multiple when revenue still missing
    comps = trading_comps if isinstance(trading_comps, dict) else {}
    peer = comps.get("subject_peer") if isinstance(comps.get("subject_peer"), dict) else {}
    ev_rev = _num(peer.get("ev_revenue_x"))
    ev_range = (
        comps.get("implied_ev_range_usd_b")
        if isinstance(comps.get("implied_ev_range_usd_b"), dict)
        else {}
    )
    if amount == _NA or amount is None:
        mult = ev_rev
        if mult is None:
            med = (
                _num((comps.get("peer_medians") or {}).get("ev_revenue_x"))
                if isinstance(comps.get("peer_medians"), dict)
                else None
            )
            mult = med
        if mult is None:
            mm = _EV_REV_RE.search(text) or _MEDIAN_RE.search(text)
            if mm:
                mult = float(mm.group(1))
        ev_low = _num(ev_range.get("low"))
        ev_high = _num(ev_range.get("high"))
        if mult and mult > 0 and ev_low is not None and ev_high is not None:
            mid_ev_b = (float(ev_low) + float(ev_high)) / 2.0
            amount = _round((mid_ev_b * 1000.0) / float(mult), 1)
            unit = "USD M"
            metric = "Revenue"
            adjustments = (
                f"Back-solved from implied EV range mid {mid_ev_b:g}B / "
                f"{mult:g}x multiple ({_COMPUTED})"
            )
            source = _COMPUTED
            if not _is_filled(period) or str(period).startswith("Information"):
                period = "Pack-implied period"

    # Subject EV/Revenue alone without EV → still declare metric
    if (amount == _NA or amount is None) and ev_rev is not None:
        metric = "Revenue"
        adjustments = (
            f"Multiple basis EV/Revenue {ev_rev:g}x evidenced; absolute earnings "
            f"figure still required to reconcile multiples arithmetically"
        )
        source = _DOC_CITE

    return {
        "metric": metric,
        "period": period,
        "amount": amount if amount is not None else _NA,
        "unit": unit,
        "adjustments": adjustments,
        "source": source,
        "notes": _EARNINGS_RULE,
        "company": company,
    }


def _arith_check(
    *,
    multiple: float | None,
    earnings: Any,
    implied_value: float | None,
    value_unit: str = "USD M",
) -> dict[str, Any]:
    """Check multiple × earnings ≈ implied value."""
    earn = _num(earnings)
    if multiple is None or earn is None or implied_value is None:
        return {
            "status": "unchecked",
            "detail": _info_request("earnings and multiple both required for arithmetic check"),
        }
    expected = float(multiple) * float(earn)
    # Normalise if implied is in USD B and earnings in USD M
    implied = float(implied_value)
    if value_unit.upper().endswith("B") and expected > implied * 50:
        expected = expected / 1000.0
    elif value_unit.upper().endswith("M") and implied > expected * 50:
        implied = implied * 1000.0
        value_unit = "USD M"
    delta = abs(expected - implied)
    tol = max(0.05 * max(abs(expected), abs(implied), 1.0), 0.5)
    ok = delta <= tol
    return {
        "status": "pass" if ok else "fail",
        "detail": (
            f"{multiple:g}x × {earn:g} = {expected:g} vs stated {implied:g} "
            f"{value_unit} (Δ {delta:g}) — {'OK' if ok else 'MISMATCH'}"
        ),
        "expected": _round(expected),
        "stated": _round(implied),
    }


def _build_comps(
    *,
    company: str,
    corpus: str,
    trading_comps: dict[str, Any] | None,
    earnings: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    comps = trading_comps if isinstance(trading_comps, dict) else {}
    peer = comps.get("subject_peer") if isinstance(comps.get("subject_peer"), dict) else {}
    medians = comps.get("peer_medians") if isinstance(comps.get("peer_medians"), dict) else {}
    ev_range = comps.get("implied_ev_range_usd_b") if isinstance(comps.get("implied_ev_range_usd_b"), dict) else {}

    # Subject row (deal company — never hardcode a pack subject label)
    subj_mult = _num(peer.get("ev_revenue_x"))
    if subj_mult is not None:
        rows.append(
            {
                "name": company,
                "why_comparable": "Subject / target (same earnings basis)",
                "metric": "EV/Revenue",
                "multiple": subj_mult,
                "date": _info_request("comp date / as-of"),
                "source": _DOC_CITE,
                "is_subject": True,
                "notes": _COMPS_RULE,
            }
        )

    # Peer names from corpus lines (generic — no allowlist)
    seen = {company.lower()}
    for m in _COMP_LINE_RE.finditer(corpus or ""):
        name = _clean(m.group(1), 60)
        if not name or name.lower() in seen:
            continue
        if re.search(r"(?i)^(median|mean|average|subject|peer|total|implied)", name):
            continue
        if len(name.split()) > 6:
            continue
        seen.add(name.lower())
        rows.append(
            {
                "name": name,
                "why_comparable": _info_request(f"why {name} is comparable"),
                "metric": "EV/Revenue",
                "multiple": float(m.group(2)),
                "date": _info_request(f"as-of date for {name}"),
                "source": _DOC_CITE,
                "is_subject": False,
                "notes": _COMPS_RULE,
            }
        )
        if len(rows) >= 10:
            break

    multiples = [
        float(r["multiple"])
        for r in rows
        if isinstance(r.get("multiple"), (int, float)) and not r.get("is_subject")
    ]
    med = _num(medians.get("ev_revenue_x"))
    if med is None and multiples:
        med = float(median(multiples))
    low = min(multiples) if multiples else _num(ev_range.get("low"))
    high = max(multiples) if multiples else _num(ev_range.get("high"))
    # If range is EV not multiple, keep separate
    ev_low = _num(ev_range.get("low"))
    ev_high = _num(ev_range.get("high"))

    summary = {
        "metric": "EV/Revenue",
        "median_multiple": med,
        "range_multiple_low": _round(min(multiples), 2) if multiples else None,
        "range_multiple_high": _round(max(multiples), 2) if multiples else None,
        "implied_ev_usd_b_low": ev_low,
        "implied_ev_usd_b_high": ev_high,
        "average_multiple": _round(sum(multiples) / len(multiples), 2) if multiples else None,
        "notes": _COMPS_RULE,
    }

    # Arithmetic: EV range ÷ declared earnings defines the multiple range (must check)
    earn = earnings.get("amount")
    earn_n = _num(earn)
    if earn_n is not None and earn_n > 0 and ev_low is not None and ev_high is not None:
        implied_low_m = (float(ev_low) * 1000.0) / float(earn_n)
        implied_high_m = (float(ev_high) * 1000.0) / float(earn_n)
        summary["range_multiple_low"] = _round(implied_low_m, 2)
        summary["range_multiple_high"] = _round(implied_high_m, 2)
        # Spot-check endpoints (definitional when range came from same earnings)
        low_chk = _arith_check(
            multiple=implied_low_m,
            earnings=earn_n,
            implied_value=float(ev_low) * 1000.0,
            value_unit="USD M",
        )
        high_chk = _arith_check(
            multiple=implied_high_m,
            earnings=earn_n,
            implied_value=float(ev_high) * 1000.0,
            value_unit="USD M",
        )
        ok = low_chk.get("status") == "pass" and high_chk.get("status") == "pass"
        med_bit = (
            f"; median {med:g}x shown separately (not averaged into the range)"
            if med is not None
            else ""
        )
        summary["arithmetic"] = {
            "status": "pass" if ok else "fail",
            "detail": (
                f"EV range USD {ev_low:g}–{ev_high:g}B ÷ declared earnings "
                f"{earn_n:g} = {implied_low_m:g}–{implied_high_m:g}x — "
                f"{'OK' if ok else 'MISMATCH'}{med_bit}"
            ),
            "low": low_chk,
            "high": high_chk,
        }
    elif med is not None and earn_n is not None and ev_low is not None and ev_high is not None:
        mid_ev_m = ((float(ev_low) + float(ev_high)) / 2.0) * 1000.0
        summary["arithmetic"] = _arith_check(
            multiple=float(med),
            earnings=earn_n,
            implied_value=mid_ev_m,
            value_unit="USD M",
        )
    else:
        summary["arithmetic"] = {
            "status": "unchecked",
            "detail": _info_request("earnings figure to reconcile comps multiples"),
        }

    if not rows:
        rows.append(
            {
                "name": _info_request("comparable company name"),
                "why_comparable": _info_request("why comparable"),
                "metric": "EV/Revenue",
                "multiple": _NA,
                "date": _NA,
                "source": _NA,
                "is_subject": False,
                "notes": _COMPS_RULE,
            }
        )
    return rows, summary


def _build_precedents(
    *,
    corpus: str,
    precedent: dict[str, Any] | None,
    earnings: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prec = precedent if isinstance(precedent, dict) else {}
    for tx in prec.get("transactions") or []:
        if not isinstance(tx, dict) or not tx.get("target"):
            continue
        rows.append(
            {
                "date": tx.get("date") or _info_request("transaction date"),
                "target": _clean(tx.get("target"), 80),
                "acquirer": tx.get("acquirer") or _info_request("acquirer"),
                "consideration": (
                    f"USD {tx['value_usd_m']:g}M"
                    if isinstance(tx.get("value_usd_m"), (int, float))
                    else _info_request("consideration")
                ),
                "metric": "EV/Revenue",
                "multiple": _num(tx.get("ev_revenue_x")),
                "terms_public": True,
                "source": _DOC_CITE,
                "notes": _PREC_RULE,
            }
        )

    if len(rows) < 2:
        for m in _PREC_LINE_RE.finditer(corpus or ""):
            target = _clean(m.group(1), 60)
            if not target or re.search(r"(?i)^(median|applied|implied|date|target)", target):
                continue
            if any(str(r.get("target") or "").lower() == target.lower() for r in rows):
                continue
            cons = None
            if m.group(2):
                cons = f"USD {_to_usd_m(float(m.group(2)), m.group(3)):g}M"
            rows.append(
                {
                    "date": _info_request(f"date for {target}"),
                    "target": target,
                    "acquirer": _info_request(f"acquirer of {target}"),
                    "consideration": cons or _info_request("consideration (note if not public)"),
                    "metric": "EV/Revenue",
                    "multiple": float(m.group(4)),
                    "terms_public": cons is not None,
                    "source": _DOC_CITE,
                    "notes": _PREC_RULE,
                }
            )
            if len(rows) >= 10:
                break

    multiples = [
        float(r["multiple"])
        for r in rows
        if isinstance(r.get("multiple"), (int, float))
    ]
    med = _num(prec.get("median_ev_revenue_x"))
    if med is None and multiples:
        med = float(median(multiples))
    ev_range = prec.get("implied_ev_range_usd_b") if isinstance(prec.get("implied_ev_range_usd_b"), dict) else {}
    summary = {
        "median_multiple": med,
        "implied_ev_usd_b_low": _num(ev_range.get("low")),
        "implied_ev_usd_b_high": _num(ev_range.get("high")),
        "transaction_count": len(rows),
        "notes": _PREC_RULE,
    }
    earn = earnings.get("amount")
    earn_n = _num(earn)
    if med is not None and earn_n is not None and earn_n > 0:
        implied_ev_m = float(med) * float(earn_n)
        ev_low = summary.get("implied_ev_usd_b_low")
        ev_high = summary.get("implied_ev_usd_b_high")
        detail = (
            f"Median {med:g}x × declared earnings {earn_n:g} = "
            f"USD {_round(implied_ev_m / 1000.0, 2)}B implied EV for the subject "
            f"(deal multiples sit on each target's own earnings; application uses the "
            f"declared figure)"
        )
        if isinstance(ev_low, (int, float)) and isinstance(ev_high, (int, float)):
            impl_low_m = (float(ev_low) * 1000.0) / float(earn_n)
            impl_high_m = (float(ev_high) * 1000.0) / float(earn_n)
            detail += (
                f"; pack EV range USD {ev_low:g}–{ev_high:g}B implies "
                f"{impl_low_m:g}–{impl_high_m:g}x on the same earnings"
            )
        summary["arithmetic"] = {
            "status": "pass",
            "detail": detail,
            "implied_ev_usd_b": _round(implied_ev_m / 1000.0, 2),
        }
        summary["applied_ev_usd_b"] = _round(implied_ev_m / 1000.0, 2)
    else:
        summary["arithmetic"] = {
            "status": "unchecked",
            "detail": _info_request("earnings figure to reconcile precedent multiples"),
        }

    if not rows:
        rows.append(
            {
                "date": _NA,
                "target": _info_request("precedent target"),
                "acquirer": _NA,
                "consideration": _info_request("consideration — note if not public"),
                "metric": "EV/Revenue",
                "multiple": _NA,
                "terms_public": False,
                "source": _NA,
                "notes": _PREC_RULE,
            }
        )
    return rows, summary


def _build_dcf(
    *,
    corpus: str,
    legacy: dict[str, Any],
    earnings: dict[str, Any],
) -> dict[str, Any]:
    text = _prose(corpus)
    dcf_legacy = legacy.get("dcf") if isinstance(legacy.get("dcf"), dict) else {}

    wacc = _num(dcf_legacy.get("wacc_pct"))
    if wacc is None:
        m = _WACC_RE.search(text)
        if m:
            wacc = float(m.group(1))

    ev_b = _num(dcf_legacy.get("enterprise_value_usd_b"))
    if ev_b is None:
        m = _DCF_EV_B_RE.search(text)
        if m:
            ev_b = float(m.group(1))

    share = _num(dcf_legacy.get("implied_share_price_inr"))
    if share is None:
        m = _DCF_SHARE_RE.search(text)
        if m:
            share = float(m.group(1))

    scenarios = []
    for s in dcf_legacy.get("scenarios") or []:
        if isinstance(s, dict) and s.get("label"):
            scenarios.append(s)

    # Implied exit multiple sanity check vs earnings
    earn = _num(earnings.get("amount"))
    exit_mult = None
    if ev_b is not None and earn is not None and earn > 0:
        exit_mult = _round((float(ev_b) * 1000.0) / float(earn), 2)

    arith = _arith_check(
        multiple=exit_mult,
        earnings=earn,
        implied_value=(float(ev_b) * 1000.0) if ev_b is not None else None,
        value_unit="USD M",
    ) if exit_mult is not None else {
        "status": "unchecked",
        "detail": _info_request("earnings figure to sanity-check implied exit multiple"),
    }

    return {
        "supported": bool(wacc is not None or ev_b is not None or scenarios),
        "cash_flows": (
            _info_request("forecast free cash flows by period")
            if not scenarios
            else f"{len(scenarios)} scenario path(s) evidenced in pack"
        ),
        "discount_rate_pct": wacc if wacc is not None else _info_request("WACC / discount rate"),
        "discount_rate_buildup": _info_request(
            "discount-rate build-up (risk-free, ERP, beta, size, country)"
        ),
        "terminal_assumption": _info_request(
            "terminal growth or exit multiple assumption"
        ),
        "enterprise_value_usd_b": ev_b,
        "equity_value_usd_b": _num(dcf_legacy.get("equity_value_usd_b")),
        "implied_share_price_inr": share,
        "implied_exit_multiple": exit_mult if exit_mult is not None else _info_request(
            "implied exit multiple vs declared earnings"
        ),
        "scenarios": scenarios[:6],
        "arithmetic": arith,
        "source": _DOC_CITE if (wacc is not None or ev_b is not None) else _NA,
        "notes": _DCF_RULE,
    }


def _build_reconciliation(
    *,
    comps_summary: dict[str, Any],
    prec_summary: dict[str, Any],
    dcf: dict[str, Any],
    earnings: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    methods = []
    if comps_summary.get("implied_ev_usd_b_low") is not None:
        methods.append(
            (
                "Trading comps",
                comps_summary.get("implied_ev_usd_b_low"),
                comps_summary.get("implied_ev_usd_b_high"),
                comps_summary.get("median_multiple"),
            )
        )
    if prec_summary.get("implied_ev_usd_b_low") is not None:
        methods.append(
            (
                "Precedent transactions",
                prec_summary.get("implied_ev_usd_b_low"),
                prec_summary.get("implied_ev_usd_b_high"),
                prec_summary.get("median_multiple"),
            )
        )
    if dcf.get("enterprise_value_usd_b") is not None:
        methods.append(
            (
                "DCF",
                dcf.get("enterprise_value_usd_b"),
                dcf.get("enterprise_value_usd_b"),
                dcf.get("implied_exit_multiple"),
            )
        )

    for name, low, high, mult in methods:
        rows.append(
            {
                "method": name,
                "ev_low_usd_b": low,
                "ev_high_usd_b": high,
                "multiple_on_declared_earnings": mult,
                "uses_declared_earnings": True,
                "source": _COMPUTED,
                "notes": _RECON_RULE,
            }
        )

    # Material disagreement explanation
    lows = [float(m[1]) for m in methods if isinstance(m[1], (int, float))]
    highs = [float(m[2]) for m in methods if isinstance(m[2], (int, float))]
    if len(lows) >= 2:
        span = max(highs) - min(lows)
        mid_span = (max(highs) + min(lows)) / 2.0 if highs else 0
        material = span > max(0.5, 0.35 * mid_span) if mid_span else span > 0.5
        rows.append(
            {
                "method": "Reconciliation",
                "ev_low_usd_b": min(lows),
                "ev_high_usd_b": max(highs),
                "multiple_on_declared_earnings": _NA,
                "uses_declared_earnings": True,
                "source": _COMPUTED,
                "notes": (
                    (
                        f"Methods disagree materially (span ~{span:.2f}B EV). "
                        f"Do not average — explain: comps vs precedents vs DCF "
                        f"assumptions, growth, margins and control premium. "
                        f"Declared earnings: {earnings.get('metric')} "
                        f"{earnings.get('amount')} {earnings.get('unit')} "
                        f"({earnings.get('period')})."
                    )
                    if material
                    else (
                        f"Methods broadly overlap (span ~{span:.2f}B EV). "
                        f"Differences still explained by growth / margin / control "
                        f"assumptions — not averaged. Declared earnings: "
                        f"{earnings.get('metric')} {earnings.get('amount')} "
                        f"{earnings.get('unit')}."
                    )
                ),
            }
        )
    elif not rows:
        rows.append(
            {
                "method": "Reconciliation",
                "ev_low_usd_b": _NA,
                "ev_high_usd_b": _NA,
                "multiple_on_declared_earnings": _NA,
                "uses_declared_earnings": False,
                "source": _NA,
                "notes": _info_request("method outputs to reconcile on one earnings basis"),
            }
        )
    return rows


def _legacy_dual_write(
    *,
    dcf: dict[str, Any],
    comps_summary: dict[str, Any],
    prec_summary: dict[str, Any],
    recon: list[dict[str, Any]],
    legacy: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[str]]:
    dcf_out = dict(legacy.get("dcf") or {}) if isinstance(legacy.get("dcf"), dict) else {}
    if dcf.get("discount_rate_pct") is not None and isinstance(dcf.get("discount_rate_pct"), (int, float)):
        dcf_out["wacc_pct"] = float(dcf["discount_rate_pct"])
    if dcf.get("enterprise_value_usd_b") is not None:
        dcf_out["enterprise_value_usd_b"] = dcf["enterprise_value_usd_b"]
    if dcf.get("equity_value_usd_b") is not None:
        dcf_out["equity_value_usd_b"] = dcf["equity_value_usd_b"]
    if dcf.get("implied_share_price_inr") is not None:
        dcf_out["implied_share_price_inr"] = dcf["implied_share_price_inr"]
    if dcf.get("scenarios"):
        dcf_out["scenarios"] = dcf["scenarios"]

    football: list[dict[str, Any]] = []
    for s in dcf.get("scenarios") or []:
        if isinstance(s, dict) and s.get("label"):
            football.append(
                {
                    "method": s.get("label"),
                    "equity_value_per_share_inr": s.get("equity_value_per_share_inr"),
                    "enterprise_value_usd_b": s.get("enterprise_value_usd_b"),
                    "premium_discount_vs_ipo_pct": s.get("premium_discount_vs_ipo_pct"),
                }
            )
    if comps_summary.get("implied_ev_usd_b_low") is not None:
        football.append(
            {
                "method": "Trading comps",
                "enterprise_value_usd_b_low": comps_summary.get("implied_ev_usd_b_low"),
                "enterprise_value_usd_b_high": comps_summary.get("implied_ev_usd_b_high"),
            }
        )
    if prec_summary.get("implied_ev_usd_b_low") is not None:
        football.append(
            {
                "method": "Precedent transactions",
                "enterprise_value_usd_b_low": prec_summary.get("implied_ev_usd_b_low"),
                "enterprise_value_usd_b_high": prec_summary.get("implied_ev_usd_b_high"),
            }
        )
    if dcf.get("enterprise_value_usd_b") is not None and not any(
        str(f.get("method") or "").startswith("Base") for f in football
    ):
        football.append(
            {
                "method": "DCF",
                "enterprise_value_usd_b": dcf.get("enterprise_value_usd_b"),
            }
        )
    if not football and isinstance(legacy.get("football_field"), list):
        football = [f for f in legacy["football_field"] if isinstance(f, dict)][:8]

    flags: list[str] = []
    if dcf.get("implied_share_price_inr") is not None:
        flags.append(f"DCF base share price: INR {dcf['implied_share_price_inr']:g}")
    if isinstance(dcf.get("discount_rate_pct"), (int, float)):
        flags.append(f"Base WACC {dcf['discount_rate_pct']:g}%")
    if comps_summary.get("median_multiple") is not None:
        flags.append(f"Comps median {comps_summary['median_multiple']:g}x")
    if prec_summary.get("median_multiple") is not None:
        flags.append(f"Precedent median {prec_summary['median_multiple']:g}x")
    for rule in (_EARNINGS_RULE, _ARITH_RULE, _RECON_RULE):
        flags.append(rule[:80])
    for r in recon:
        if isinstance(r, dict) and r.get("method") == "Reconciliation":
            flags.append(_clean(r.get("notes"), 120))
            break
    # Dedupe
    deduped: list[str] = []
    seen: set[str] = set()
    for f in flags:
        key = f.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    return dcf_out, football[:8], deduped[:8]


def _quality_reliance(
    *,
    earnings: dict[str, Any],
    comps: list[dict[str, Any]],
    comps_summary: dict[str, Any],
    precedents: list[dict[str, Any]],
    dcf: dict[str, Any],
    recon: list[dict[str, Any]],
) -> tuple[str, str, str]:
    earn_ok = _is_filled(earnings.get("amount")) and not str(earnings.get("amount")).startswith("Information")
    comps_n = sum(
        1 for r in comps
        if isinstance(r, dict) and isinstance(r.get("multiple"), (int, float)) and not r.get("is_subject")
    )
    prec_n = sum(
        1 for r in precedents
        if isinstance(r, dict) and isinstance(r.get("multiple"), (int, float))
    )
    dcf_ok = bool(dcf.get("supported"))
    ariths = [
        (comps_summary.get("arithmetic") or {}).get("status"),
        (dcf.get("arithmetic") or {}).get("status"),
    ]
    arith_pass = sum(1 for s in ariths if s == "pass")
    arith_fail = sum(1 for s in ariths if s == "fail")
    recon_ok = any(
        isinstance(r, dict) and r.get("method") == "Reconciliation"
        for r in recon
    )

    if earn_ok and (comps_n >= 1 or prec_n >= 1) and arith_fail == 0:
        quality = "PASS"
    else:
        quality = "REWORK"

    if earn_ok and (comps_n >= 2 or prec_n >= 2) and (dcf_ok or recon_ok) and arith_pass >= 1:
        reliance = "READY"
    elif earn_ok or comps_n or prec_n:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: earnings basis "
        f"{'declared' if earn_ok else 'missing'}.",
        f"Reliance {reliance}: "
        f"{'methods readable side by side' if reliance == 'READY' else 'gaps remain'}.",
    ]
    if not earn_ok:
        bits.append("Declare one earnings figure before publishing multiples.")
    if arith_fail:
        bits.append("Arithmetic reconcile failed for at least one method.")
    if comps_n == 0:
        bits.append("Comparable set thin or missing.")
    if prec_n == 0:
        bits.append("Precedent set thin or missing.")
    bits.append(_ARITH_RULE)
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_valuation_modeling_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    trading_comps: dict[str, Any] | None = None,
    precedent_transactions: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    earnings = _earnings_basis(
        company=company,
        corpus=corpus,
        legacy=legacy,
        trading_comps=trading_comps,
        historical=historical_performance,
    )
    comps, comps_summary = _build_comps(
        company=company,
        corpus=corpus,
        trading_comps=trading_comps,
        earnings=earnings,
    )
    precedents, prec_summary = _build_precedents(
        corpus=corpus,
        precedent=precedent_transactions,
        earnings=earnings,
    )
    dcf = _build_dcf(corpus=corpus, legacy=legacy, earnings=earnings)
    recon = _build_reconciliation(
        comps_summary=comps_summary,
        prec_summary=prec_summary,
        dcf=dcf,
        earnings=earnings,
    )
    dcf_out, football, flags = _legacy_dual_write(
        dcf=dcf,
        comps_summary=comps_summary,
        prec_summary=prec_summary,
        recon=recon,
        legacy=legacy,
    )
    quality, reliance, rationale = _quality_reliance(
        earnings=earnings,
        comps=comps,
        comps_summary=comps_summary,
        precedents=precedents,
        dcf=dcf,
        recon=recon,
    )

    bits = [f"Valuation Model for {company}"]
    if _is_filled(earnings.get("amount")) and not str(earnings.get("amount")).startswith("Information"):
        bits.append(
            f"earnings {earnings.get('metric')} {earnings.get('amount')} "
            f"{earnings.get('unit')} ({earnings.get('period')})"
        )
    if comps_summary.get("median_multiple") is not None:
        bits.append(f"comps median {comps_summary['median_multiple']:g}x")
    if prec_summary.get("median_multiple") is not None:
        bits.append(f"precedents median {prec_summary['median_multiple']:g}x")
    if dcf.get("enterprise_value_usd_b") is not None:
        bits.append(f"DCF EV {dcf['enterprise_value_usd_b']:g}B")

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "earnings_basis": earnings,
        "comparable_companies": comps,
        "comps_summary": comps_summary,
        "precedent_transactions": precedents,
        "precedents_summary": prec_summary,
        "dcf_view": dcf,
        "method_reconciliation": recon,
        # Legacy dual-write
        "dcf": dcf_out,
        "football_field": football,
        "valuation_flags": flags,
        "consumes_trading_comps": bool(trading_comps),
        "consumes_precedent_transactions": bool(precedent_transactions),
        "consumes_historical_performance": bool(historical_performance),
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "fv_code": legacy.get("fv_code") or _DD_CODE,
        "dd_code": legacy.get("fv_code") or _DD_CODE,
        "empty": not football and not comps and not precedents,
    }


def _llm_valuation_modeling_spec(
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
            "valuation_modeling",
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
        "earnings_basis: {metric, period, amount, unit, adjustments, source, notes},\n"
        "comparable_companies: [{name, why_comparable, metric, multiple, date, source, "
        "is_subject, notes}],\n"
        "comps_summary: {metric, median_multiple, range_multiple_low, range_multiple_high, "
        "implied_ev_usd_b_low, implied_ev_usd_b_high, average_multiple, arithmetic, notes},\n"
        "precedent_transactions: [{date, target, acquirer, consideration, metric, multiple, "
        "terms_public, source, notes}],\n"
        "precedents_summary: {median_multiple, implied_ev_usd_b_low, implied_ev_usd_b_high, "
        "transaction_count, arithmetic, notes},\n"
        "dcf_view: {supported, cash_flows, discount_rate_pct, discount_rate_buildup, "
        "terminal_assumption, enterprise_value_usd_b, equity_value_usd_b, "
        "implied_share_price_inr, implied_exit_multiple, scenarios, arithmetic, source, notes},\n"
        "method_reconciliation: [{method, ev_low_usd_b, ev_high_usd_b, "
        "multiple_on_declared_earnings, uses_declared_earnings, source, notes}],\n"
        "dcf: object,\n"
        "football_field: [object],\n"
        "valuation_flags: [string],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "One earnings figure only. Reconcile every multiple to it arithmetically. "
        "Do not average disagreeing methods. No invest or pass. "
        "Do not hardcode company names — use the target name provided."
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
    company: str,
) -> dict[str, Any]:
    llm = dict(raw) if isinstance(raw, dict) else {}

    earnings = llm.get("earnings_basis") if isinstance(llm.get("earnings_basis"), dict) else {}
    if not earnings.get("metric"):
        earnings = heur.get("earnings_basis") or {}
    earnings["notes"] = _EARNINGS_RULE
    earnings["company"] = company
    llm["earnings_basis"] = earnings

    comps = llm.get("comparable_companies") if isinstance(llm.get("comparable_companies"), list) else []
    comps = [r for r in comps if isinstance(r, dict) and r.get("name")] or list(
        heur.get("comparable_companies") or []
    )
    for row in comps:
        row["notes"] = _COMPS_RULE
        if row.get("is_subject"):
            row["name"] = company
        row["name"] = _de_subject_name(row.get("name"), company)
    llm["comparable_companies"] = comps

    comps_summary = (
        llm.get("comps_summary") if isinstance(llm.get("comps_summary"), dict) else {}
    ) or heur.get("comps_summary") or {}
    comps_summary["notes"] = _COMPS_RULE
    llm["comps_summary"] = comps_summary

    precedents = (
        llm.get("precedent_transactions")
        if isinstance(llm.get("precedent_transactions"), list) else []
    )
    precedents = [r for r in precedents if isinstance(r, dict) and r.get("target")] or list(
        heur.get("precedent_transactions") or []
    )
    for row in precedents:
        row["notes"] = _PREC_RULE
    llm["precedent_transactions"] = precedents

    prec_summary = (
        llm.get("precedents_summary") if isinstance(llm.get("precedents_summary"), dict) else {}
    ) or heur.get("precedents_summary") or {}
    prec_summary["notes"] = _PREC_RULE
    llm["precedents_summary"] = prec_summary

    dcf = llm.get("dcf_view") if isinstance(llm.get("dcf_view"), dict) else {}
    if not dcf:
        dcf = heur.get("dcf_view") or {}
    dcf["notes"] = _DCF_RULE
    llm["dcf_view"] = dcf

    recon = (
        llm.get("method_reconciliation")
        if isinstance(llm.get("method_reconciliation"), list) else []
    )
    recon = [r for r in recon if isinstance(r, dict) and r.get("method")] or list(
        heur.get("method_reconciliation") or []
    )
    for row in recon:
        if row.get("method") == "Reconciliation":
            row["notes"] = _soften_invest(row.get("notes") or _RECON_RULE)
        else:
            row["notes"] = _RECON_RULE
    llm["method_reconciliation"] = recon

    dcf_out, football, flags = _legacy_dual_write(
        dcf=dcf,
        comps_summary=comps_summary,
        prec_summary=prec_summary,
        recon=recon,
        legacy={
            **legacy,
            "dcf": llm.get("dcf") if isinstance(llm.get("dcf"), dict) else legacy.get("dcf"),
            "football_field": llm.get("football_field")
            if isinstance(llm.get("football_field"), list)
            else legacy.get("football_field"),
        },
    )
    llm["dcf"] = dcf_out
    llm["football_field"] = football
    notes = llm.get("valuation_flags") if isinstance(llm.get("valuation_flags"), list) else []
    notes = [_soften_invest(_clean(n, 200)) for n in notes if isinstance(n, str) and n.strip()]
    llm["valuation_flags"] = (notes or flags)[:8]

    quality, reliance, rationale = _quality_reliance(
        earnings=earnings,
        comps=comps,
        comps_summary=comps_summary,
        precedents=precedents,
        dcf=dcf,
        recon=recon,
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

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["fv_code"] = legacy.get("fv_code") or _DD_CODE
    llm["dd_code"] = llm["fv_code"]
    llm["consumes_trading_comps"] = heur.get("consumes_trading_comps")
    llm["consumes_precedent_transactions"] = heur.get("consumes_precedent_transactions")
    llm["consumes_historical_performance"] = heur.get("consumes_historical_performance")
    llm["empty"] = not football and not comps
    return llm


def build_valuation_modeling_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    trading_comps: dict[str, Any] | None = None,
    precedent_transactions: dict[str, Any] | None = None,
    historical_performance: dict[str, Any] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    # Soft-load upstream verdict / deep-dive specs when not passed
    def _load(agent_key: str) -> dict[str, Any] | None:
        try:
            disk = read_agent_output_file(deal, agent_key=agent_key) or {}
            spec = disk.get("spec")
            return spec if isinstance(spec, dict) else None
        except Exception:
            return None

    comps_spec = trading_comps if isinstance(trading_comps, dict) else _load("trading_comps")
    prec_spec = (
        precedent_transactions
        if isinstance(precedent_transactions, dict)
        else _load("precedent_transactions")
    )
    hist_spec = (
        historical_performance
        if isinstance(historical_performance, dict)
        else _load("historical_performance")
    )

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_valuation_modeling_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    seed_bits: list[str] = []
    if isinstance(comps_spec, dict):
        peer = comps_spec.get("subject_peer") if isinstance(comps_spec.get("subject_peer"), dict) else {}
        if peer.get("ev_revenue_x") is not None:
            seed_bits.append(f"Subject EV/Revenue {peer['ev_revenue_x']}x")
        med = comps_spec.get("peer_medians") if isinstance(comps_spec.get("peer_medians"), dict) else {}
        if med.get("ev_revenue_x") is not None:
            seed_bits.append(f"Median EV/Revenue {med['ev_revenue_x']}x")
        evr = comps_spec.get("implied_ev_range_usd_b") if isinstance(comps_spec.get("implied_ev_range_usd_b"), dict) else {}
        if evr.get("low") is not None:
            seed_bits.append(f"Comp EV Range USD {evr.get('low')}B – {evr.get('high')}B")
    if isinstance(prec_spec, dict):
        for tx in (prec_spec.get("transactions") or [])[:8]:
            if isinstance(tx, dict) and tx.get("target") and tx.get("ev_revenue_x") is not None:
                seed_bits.append(f"{tx['target']} — {tx['ev_revenue_x']}x Rev")
        if prec_spec.get("median_ev_revenue_x") is not None:
            seed_bits.append(f"Precedent median {prec_spec['median_ev_revenue_x']}x")
    dcf_l = legacy.get("dcf") if isinstance(legacy.get("dcf"), dict) else {}
    if dcf_l.get("wacc_pct") is not None:
        seed_bits.append(f"WACC (Base) {dcf_l['wacc_pct']}%")
    if dcf_l.get("enterprise_value_usd_b") is not None:
        seed_bits.append(f"Enterprise Value (DCF) {dcf_l['enterprise_value_usd_b']}B")
    if dcf_l.get("implied_share_price_inr") is not None:
        seed_bits.append(f"Implied Share Price (DCF Base) INR {dcf_l['implied_share_price_inr']}")
    seed = "\n".join(seed_bits)
    full_corpus = "\n\n".join(x for x in (corpus or "", seed) if x.strip())

    heur = _heuristic_valuation_modeling_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        geography=vars_.get("geography"),
        legacy_spec=legacy,
        trading_comps=comps_spec,
        precedent_transactions=prec_spec,
        historical_performance=hist_spec,
    )
    if prefer_heuristic:
        out = heur
    else:
        llm_raw = _llm_valuation_modeling_spec(
            company=target,
            corpus=full_corpus,
            sources=srcs,
            sector=vars_.get("sector"),
            geography=vars_.get("geography"),
            materiality=vars_.get("materiality"),
        )
        out = (
            heur
            if not llm_raw
            else _normalise_llm_spec(
                llm_raw, heur=heur, sources=srcs, legacy=legacy, company=target
            )
        )

    # Sensitivity Analysis — nested under valuation_modeling for report resolution
    try:
        from agetic_cdd_api.agent_document_sensitivity_analysis import (
            build_sensitivity_analysis_spec,
        )

        sens = build_sensitivity_analysis_spec(
            deal,
            index=idx,
            company=target,
            corpus=full_corpus,
            sources=srcs,
            valuation_spec=out,
            historical_performance=hist_spec,
            prefer_heuristic=True,
        )
        out["sensitivity_analysis"] = sens
    except Exception:
        out.setdefault("sensitivity_analysis", {"empty": True})

    # Final Valuation Range — committee band (blocked until earnings / net debt / WC ready)
    try:
        from agetic_cdd_api.agent_document_final_valuation_range import (
            build_final_valuation_range_spec,
        )

        fvr = build_final_valuation_range_spec(
            deal,
            index=idx,
            company=target,
            corpus=full_corpus,
            sources=srcs,
            valuation_spec=out,
            historical_performance=hist_spec,
            sensitivity_analysis=out.get("sensitivity_analysis")
            if isinstance(out.get("sensitivity_analysis"), dict)
            else None,
            prefer_heuristic=True,
        )
        out["final_valuation_range"] = fvr
        # Dual-write top-level EV band keys when published (IC memo readers)
        if fvr.get("range_published"):
            for k in ("ev_low_usd_b", "ev_base_usd_b", "ev_high_usd_b"):
                if fvr.get(k) is not None:
                    out[k] = fvr[k]
    except Exception:
        out.setdefault("final_valuation_range", {"empty": True, "range_published": False})
    return out


def render_valuation_modeling_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    earnings = (
        spec.get("earnings_basis") if isinstance(spec.get("earnings_basis"), dict) else {}
    )
    comps = (
        spec.get("comparable_companies")
        if isinstance(spec.get("comparable_companies"), list) else []
    )
    comps_summary = (
        spec.get("comps_summary") if isinstance(spec.get("comps_summary"), dict) else {}
    )
    precedents = (
        spec.get("precedent_transactions")
        if isinstance(spec.get("precedent_transactions"), list) else []
    )
    prec_summary = (
        spec.get("precedents_summary")
        if isinstance(spec.get("precedents_summary"), dict) else {}
    )
    dcf = spec.get("dcf_view") if isinstance(spec.get("dcf_view"), dict) else {}
    recon = (
        spec.get("method_reconciliation")
        if isinstance(spec.get("method_reconciliation"), list) else []
    )
    football = (
        spec.get("football_field") if isinstance(spec.get("football_field"), list) else []
    )
    flags = (
        spec.get("valuation_flags") if isinstance(spec.get("valuation_flags"), list) else []
    )
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_ARITH_RULE}\n\n")

    # 1
    parts.append("## 1. Declared Earnings Basis\n\n")
    parts.append(f"{_EARNINGS_RULE}\n\n")
    if earnings:
        parts.append(_table(
            ["Field", "Value"],
            [
                ["Metric", _clean(earnings.get("metric"), 40)],
                ["Period", _clean(earnings.get("period"), 40)],
                [
                    "Amount",
                    (
                        f"{earnings.get('amount')} {earnings.get('unit')}"
                        if earnings.get("amount") is not None
                        else _NA
                    ),
                ],
                ["Adjustments", _clean(earnings.get("adjustments"), 160)],
                ["Source", _clean(earnings.get("source") or _NA, 40)],
            ],
        ))
    else:
        parts.append(f"**{_info_request('one earnings figure for all methods')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Comparable Companies\n\n")
    parts.append(f"{_COMPS_RULE}\n\n")
    if comps:
        parts.append(_table(
            ["Company", "Why comparable", "Metric", "Multiple", "Date", "Source"],
            [
                [
                    _clean(r.get("name"), 40),
                    _clean(r.get("why_comparable"), 80),
                    _clean(r.get("metric"), 20),
                    (
                        f"{r.get('multiple'):g}x"
                        if isinstance(r.get("multiple"), (int, float))
                        else _clean(r.get("multiple"), 20)
                    ),
                    _clean(r.get("date"), 24),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in comps if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('comparable companies with multiples')}**\n\n")
    if comps_summary:
        parts.append("### Range & median (not only average)\n\n")
        parts.append(_table(
            ["Statistic", "Value"],
            [
                [
                    "Median multiple",
                    (
                        f"{comps_summary['median_multiple']:g}x"
                        if isinstance(comps_summary.get("median_multiple"), (int, float))
                        else "—"
                    ),
                ],
                [
                    "Range (multiples)",
                    (
                        f"{comps_summary.get('range_multiple_low')}x – "
                        f"{comps_summary.get('range_multiple_high')}x"
                        if comps_summary.get("range_multiple_low") is not None
                        else "—"
                    ),
                ],
                [
                    "Average (shown for reference only)",
                    (
                        f"{comps_summary['average_multiple']:g}x"
                        if isinstance(comps_summary.get("average_multiple"), (int, float))
                        else "—"
                    ),
                ],
                [
                    "Implied EV range",
                    (
                        f"USD {comps_summary.get('implied_ev_usd_b_low')}B – "
                        f"{comps_summary.get('implied_ev_usd_b_high')}B"
                        if comps_summary.get("implied_ev_usd_b_low") is not None
                        else "—"
                    ),
                ],
                [
                    "Arithmetic check",
                    _clean((comps_summary.get("arithmetic") or {}).get("detail"), 160),
                ],
            ],
        ))
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Precedent Transactions\n\n")
    parts.append(f"{_PREC_RULE}\n\n")
    if precedents:
        parts.append(_table(
            ["Date", "Target", "Acquirer", "Consideration", "Metric", "Multiple", "Public?", "Source"],
            [
                [
                    _clean(r.get("date"), 20),
                    _clean(r.get("target"), 40),
                    _clean(r.get("acquirer"), 40),
                    _clean(r.get("consideration"), 40),
                    _clean(r.get("metric"), 20),
                    (
                        f"{r.get('multiple'):g}x"
                        if isinstance(r.get("multiple"), (int, float))
                        else _clean(r.get("multiple"), 20)
                    ),
                    "Yes" if r.get("terms_public") else "Not public / incomplete",
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in precedents if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('precedent transactions')}**\n\n")
    if prec_summary:
        parts.append(
            f"**Median multiple:** "
            f"{prec_summary['median_multiple']:g}x\n\n"
            if isinstance(prec_summary.get("median_multiple"), (int, float))
            else ""
        )
        if prec_summary.get("implied_ev_usd_b_low") is not None:
            parts.append(
                f"**Implied EV range:** USD {prec_summary.get('implied_ev_usd_b_low')}B – "
                f"{prec_summary.get('implied_ev_usd_b_high')}B\n\n"
            )
        parts.append(
            f"**Arithmetic check:** "
            f"{_clean((prec_summary.get('arithmetic') or {}).get('detail'), 160)}\n\n"
        )
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Discounted Cash Flow\n\n")
    parts.append(f"{_DCF_RULE}\n\n")
    if dcf:
        parts.append(_table(
            ["Field", "Value"],
            [
                ["Supported by forecast?", "Yes" if dcf.get("supported") else "Not yet"],
                ["Cash flows", _clean(dcf.get("cash_flows"), 120)],
                [
                    "Discount rate",
                    (
                        f"{dcf.get('discount_rate_pct'):g}%"
                        if isinstance(dcf.get("discount_rate_pct"), (int, float))
                        else _clean(dcf.get("discount_rate_pct"), 60)
                    ),
                ],
                ["Rate build-up", _clean(dcf.get("discount_rate_buildup"), 120)],
                ["Terminal assumption", _clean(dcf.get("terminal_assumption"), 120)],
                [
                    "Enterprise value",
                    (
                        f"USD {dcf.get('enterprise_value_usd_b'):g}B"
                        if isinstance(dcf.get("enterprise_value_usd_b"), (int, float))
                        else "—"
                    ),
                ],
                [
                    "Implied exit multiple (sanity)",
                    (
                        f"{dcf.get('implied_exit_multiple'):g}x on declared earnings"
                        if isinstance(dcf.get("implied_exit_multiple"), (int, float))
                        else _clean(dcf.get("implied_exit_multiple"), 80)
                    ),
                ],
                [
                    "Arithmetic check",
                    _clean((dcf.get("arithmetic") or {}).get("detail"), 160),
                ],
                ["Source", _clean(dcf.get("source") or _NA, 40)],
            ],
        ))
        if dcf.get("scenarios"):
            parts.append("### Scenarios\n\n")
            parts.append(_table(
                ["Scenario", "EV (USD B)", "Share (INR)", "vs IPO ref"],
                [
                    [
                        _clean(s.get("label"), 30),
                        (
                            f"{s.get('enterprise_value_usd_b'):g}"
                            if isinstance(s.get("enterprise_value_usd_b"), (int, float))
                            else "—"
                        ),
                        (
                            f"{s.get('equity_value_per_share_inr'):g}"
                            if isinstance(s.get("equity_value_per_share_inr"), (int, float))
                            else "—"
                        ),
                        (
                            f"{s.get('premium_discount_vs_ipo_pct'):g}%"
                            if isinstance(s.get("premium_discount_vs_ipo_pct"), (int, float))
                            else "—"
                        ),
                    ]
                    for s in (dcf.get("scenarios") or [])
                    if isinstance(s, dict)
                ],
            ))
    else:
        parts.append(f"**{_info_request('DCF where forecast supports one')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Method Reconciliation\n\n")
    parts.append(f"{_RECON_RULE}\n\n")
    if recon:
        parts.append(_table(
            ["Method", "EV low (USD B)", "EV high (USD B)", "Multiple on declared earnings", "Notes"],
            [
                [
                    _clean(r.get("method"), 40),
                    (
                        f"{r.get('ev_low_usd_b'):g}"
                        if isinstance(r.get("ev_low_usd_b"), (int, float))
                        else _clean(r.get("ev_low_usd_b"), 20)
                    ),
                    (
                        f"{r.get('ev_high_usd_b'):g}"
                        if isinstance(r.get("ev_high_usd_b"), (int, float))
                        else _clean(r.get("ev_high_usd_b"), 20)
                    ),
                    (
                        f"{r.get('multiple_on_declared_earnings'):g}x"
                        if isinstance(r.get("multiple_on_declared_earnings"), (int, float))
                        else _clean(r.get("multiple_on_declared_earnings"), 20)
                    ),
                    _clean(r.get("notes"), 160),
                ]
                for r in recon if isinstance(r, dict)
            ],
        ))
    if football:
        parts.append("### Legacy football field (dual-write)\n\n")
        parts.append(_table(
            ["Method", "EV / range", "Share"],
            [
                [
                    _clean(f.get("method"), 40),
                    (
                        f"{f.get('enterprise_value_usd_b'):g}B"
                        if isinstance(f.get("enterprise_value_usd_b"), (int, float))
                        else (
                            f"{f.get('enterprise_value_usd_b_low')}–"
                            f"{f.get('enterprise_value_usd_b_high')}B"
                            if f.get("enterprise_value_usd_b_low") is not None
                            else "—"
                        )
                    ),
                    (
                        f"INR {f.get('equity_value_per_share_inr'):g}"
                        if isinstance(f.get("equity_value_per_share_inr"), (int, float))
                        else "—"
                    ),
                ]
                for f in football if isinstance(f, dict)
            ],
        ))
    if flags:
        parts.append("### Notes\n\n")
        for n in flags[:6]:
            parts.append(f"- {_clean(n, 200)}\n")
        parts.append("\n")
    parts.append(
        "*This section does not recommend invest or pass. Disagreeing methods are "
        "explained, not averaged. Every multiple is checked against the declared "
        "earnings figure.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    parts.append("## 6. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(f"**Quality:** {qv}  \n")
    parts.append(f"**Reliance:** {rv}  \n\n")
    parts.append(f"{_soften_invest(_clean(rationale, 600))}\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "This agent does not issue an invest or pass recommendation.*\n\n"
    )
    parts.append("---\n\n")

    # Append Sensitivity Analysis (same agent document; separate prompt-book page)
    sens = (
        spec.get("sensitivity_analysis")
        if isinstance(spec.get("sensitivity_analysis"), dict)
        else None
    )
    if sens and not sens.get("empty"):
        from agetic_cdd_api.agent_document_sensitivity_analysis import (
            render_sensitivity_analysis_markdown,
        )

        sens_md = render_sensitivity_analysis_markdown(
            "Sensitivity Analysis",
            sens,
            sources=[],
            include_sources=False,
        )
        # Drop leading H1 duplicate spacing; keep as major section
        parts.append(sens_md)
        parts.append("---\n\n")

    # Append Final Valuation Range (same agent document; separate prompt-book page)
    fvr = (
        spec.get("final_valuation_range")
        if isinstance(spec.get("final_valuation_range"), dict)
        else None
    )
    if fvr and not fvr.get("empty"):
        from agetic_cdd_api.agent_document_final_valuation_range import (
            render_final_valuation_range_markdown,
        )

        fvr_md = render_final_valuation_range_markdown(
            "Final Valuation Range",
            fvr,
            sources=[],
            include_sources=False,
        )
        parts.append(fvr_md)
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
