"""Compose DiligenceIQ Market Share Strategy — matched share + plan arithmetic (prompt book).

Share is calculated only where the numerator (from the accounts) and the denominator
(from the approved market perimeter) match on service, geography, unit and date. Where
they cannot be matched, share is not calculable and a named information request is
raised — missing share is unassessed and establishes neither leadership nor weakness.
Share movement is measured over time and separated from market growth and from
acquisitions. The growth plan is translated into physical requirements (customers per
month, volume, capacity, sales headcount), funnel economics are read where CRM data
exist, and a bottom-up attainable case is set beside management ambition.

No invest/pass. No company or OEM allowlists. Preserves the legacy Win/Loss Matrix
shape (share_trends / wins / losses / strategy_notes) for decks.
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

_UNASSESSED = (
    "Share is unassessed on a matched basis (neither strength nor weakness claimed)."
)

_DOCUMENT_TITLE = "Win/Loss Matrix"
_DD_CODE = "DD-05"

# --- scope / matching cues -------------------------------------------------

_NUMERATOR_CUE = re.compile(
    r"\b(revenue|turnover|billings|invoiced\s+sales|net\s+sales|"
    r"units\s+sold|volumes?\s+sold|deliveries|registrations|shipments|"
    r"customer\s+accounts?|active\s+customers?|management\s+accounts|"
    r"audited\s+accounts|from\s+the\s+accounts|trial\s+balance|"
    r"order\s+intake)\b",
    re.IGNORECASE,
)
_DENOMINATOR_CUE = re.compile(
    r"\b(TAM|SAM|SOM|total\s+addressable\s+market|addressable\s+market|"
    r"serviceable\s+(?:addressable\s+)?market|market\s+size|market\s+value|"
    r"market\s+volume|industry\s+(?:size|volume|revenue)|"
    r"approved\s+(?:market\s+)?perimeter|market\s+perimeter|"
    r"total\s+market)\b",
    re.IGNORECASE,
)
_UNIT_REVENUE = re.compile(
    r"\b(revenue|turnover|billings|sales\s+value|GMV|value\s+terms|"
    r"INR|USD|EUR|GBP|crore|cr\b|lakh|mn\b|million|bn\b|billion)\b|[₹$€£]",
    re.IGNORECASE,
)
_UNIT_VOLUME = re.compile(
    r"\b(units?|volume|vehicles?|registrations?|tonnes?|tons?|litres?|liters?|"
    r"shipments?|deliveries|kWh|MWh|seats?|trips?|orders?)\b",
    re.IGNORECASE,
)
_UNIT_CUSTOMERS = re.compile(
    r"\b(customers?|accounts?|subscribers?|clients?|members?|policies|"
    r"connections?|households?|premises)\b",
    re.IGNORECASE,
)
_SERVICE_CUE = re.compile(
    r"(?:market\s+for|segment\s+of|category\s+of|within\s+the|in\s+the|the)\s+"
    r"([A-Za-z0-9][A-Za-z0-9 \-/&]{3,44}?)\s+"
    r"(?:market|segment|category|vertical|services?|business)\b",
    re.IGNORECASE,
)
_GEO_CUE = re.compile(
    r"\b(?:in|across|throughout|within|for)\s+"
    r"((?:the\s+)?[A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,2})\b"
)
_GEO_WORD = re.compile(
    r"\b(domestic|national|nationwide|pan[- ]?[A-Z][a-z]+|regional|"
    r"state[- ]level|city[- ]level|metro|urban|rural|export\s+markets?)\b",
)
_GEO_STOP = {
    "the", "company", "management", "target", "group", "board", "revenue",
    "share", "market", "fy", "cy", "q1", "q2", "q3", "q4", "crm", "tam", "sam",
    "information", "memorandum", "data", "room", "the company", "the group",
    "the target", "the market", "the business",
}
_DATE = re.compile(
    r"\b((?:FY|CY)\s?(?:19|20)?\d{2}(?:[-–/](?:\d{2}|\d{4}))?|"
    r"(?:19|20)\d{2}(?:[-–/](?:\d{2}|\d{4}))?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2}|"
    r"Q[1-4]\s*(?:FY|CY)?\s?(?:19|20)?\d{2})\b",
    re.IGNORECASE,
)

# --- share value cues -----------------------------------------------------

_SHARE_PCT = re.compile(
    r"(?:market\s+share|share\s+of\s+(?:the\s+)?market|share\s+position|share)"
    r"[^.\d%]{0,40}?(?:of\s+|at\s+|was\s+|is\s+|~|≈)?"
    r"(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_PCT_SHARE = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:of\s+(?:the\s+)?market|"
    r"(?:market\s+)?share)\b",
    re.IGNORECASE,
)
_SHARE_FROM_TO = re.compile(
    r"share[^.]{0,60}?\bfrom\s+(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%"
    r"(?:\s+in\s+((?:FY|CY)?\s?(?:19|20)?\d{2}(?:[-–/]\d{2,4})?))?"
    r"[^.]{0,30}?\bto\s+(?:~|≈)?(\d{1,3}(?:\.\d+)?)\s*%"
    r"(?:\s+in\s+((?:FY|CY)?\s?(?:19|20)?\d{2}(?:[-–/]\d{2,4})?))?",
    re.IGNORECASE,
)
_TREND_ROW = re.compile(
    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
    r"(\d{1,3}(?:\.\d+)?)\s*%[^\n]{0,40}?"
    r"\b(Strong\s+Gain|Gaining\s+Share|Gaining|Losing\s+Share|Losing|"
    r"Declining|Steady\s+Growth|Steady|Flat|Fragmented)\b",
)
_SUBJECT_SHARE = re.compile(
    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})"
    r"(?:'s|’s)?\s+(?:market\s+)?share\b",
)
_GAIN_CUE = re.compile(
    r"\b(strong\s+gain|gaining(?:\s+share)?|gained\s+share|share\s+gain|"
    r"rising\s+share|share\s+expansion|outgrew\s+the\s+market)\b",
    re.IGNORECASE,
)
_LOSS_CUE = re.compile(
    r"\b(losing\s+share|loses\s+share|lost\s+share|share\s+loss|"
    r"declining\s+share|share\s+erosion|ceding\s+share|"
    r"declining|underperform(?:ed|ing)?\s+the\s+market)\b",
    re.IGNORECASE,
)
_MARKET_GROWTH_CUE = re.compile(
    r"\b(market\s+(?:grew|growth|expanded|expansion|CAGR)|"
    r"industry\s+(?:grew|growth|CAGR)|category\s+growth|"
    r"underlying\s+market\s+growth|TAM\s+growth|market\s+grew\s+by)\b",
    re.IGNORECASE,
)
_ACQUISITION_CUE = re.compile(
    r"\b(acquisition|acquisitions|acquired|inorganic|bolt[- ]?on|"
    r"merger|merged|takeover|M&A|purchase\s+of\s+(?:a\s+)?business)\b",
    re.IGNORECASE,
)
_ORGANIC_CUE = re.compile(
    r"\b(organic(?:ally)?|like[- ]for[- ]like|same[- ]store|underlying\s+growth|"
    r"excluding\s+acquisitions?|ex[- ]M&A)\b",
    re.IGNORECASE,
)

# --- plan requirement cues -------------------------------------------------

_CUSTOMERS_PER_PERIOD = re.compile(
    r"(\d[\d,.]*)\s*(?:k|m|mn|million|lakh|crore)?\s*"
    r"(?:new\s+|additional\s+)?"
    r"(?:customers?|accounts?|subscribers?|clients?|policies|connections?)\s*"
    r"(?:per|/|a|each)\s*(month|week|quarter|year|annum)",
    re.IGNORECASE,
)
_CUSTOMERS_PER_PERIOD_ALT = re.compile(
    r"(?:per\s+month|monthly|each\s+month)[^.\d]{0,30}(\d[\d,.]*)\s*"
    r"(?:new\s+)?(?:customers?|accounts?|subscribers?|clients?)",
    re.IGNORECASE,
)
_HEADCOUNT = re.compile(
    r"(?:(\d[\d,.]*)\s*(?:additional\s+)?"
    r"(?:sales|field|BD|business\s+development|commercial)\s+"
    r"(?:headcount|reps?|representatives?|executives?|staff|people|FTEs?|"
    r"team\s+members?|managers?)"
    r"|(?:sales|commercial)\s+(?:headcount|team|force)\s+"
    r"(?:of|to|from)?\s*(?:~)?(\d[\d,.]*))",
    re.IGNORECASE,
)
_CAPACITY = re.compile(
    r"(?:(\d[\d,.]*)\s*(?:k|m|mn|million)?\s*(?:additional\s+)?"
    r"(?:vehicles?|trucks?|vans?|buses|fleet|depots?|stores?|outlets?|"
    r"branches|plants?|lines?|warehouses?|beds?|seats?|MW|GW|"
    r"sq\.?\s?ft|square\s+feet)"
    r"|(?:capacity|installed\s+capacity|fleet\s+size)\s*"
    r"(?:of|to|at)?\s*(?:~)?(\d[\d,.]*))",
    re.IGNORECASE,
)
_VOLUME = re.compile(
    r"(?:(?:volume|throughput|output|units)\s*(?:of|to|at)?\s*(?:~)?"
    r"(\d[\d,.]*)\s*(k|m|mn|million|bn|billion|lakh|crore)?"
    r"|(\d[\d,.]*)\s*(k|m|mn|million|bn|billion|lakh|crore)?\s*"
    r"(?:units?|vehicles?|tonnes?|litres?|liters?|orders?|trips?)\b)",
    re.IGNORECASE,
)
_PLAN_CUE = re.compile(
    r"\b(growth\s+plan|business\s+plan|management\s+plan|five[- ]year\s+plan|"
    r"expansion\s+plan|roll[- ]?out|scale[- ]?up|ramp[- ]?up|"
    r"plan\s+to\s+(?:add|grow|reach|win)|target(?:s|ing)?)\b",
    re.IGNORECASE,
)

# --- funnel cues ----------------------------------------------------------

_LEADS = re.compile(
    r"(?:(\d[\d,.]*)\s*(?:k|m|mn)?\s*(?:qualified\s+)?"
    r"(?:leads?|enquir(?:y|ies)|inquir(?:y|ies)|MQLs?|SQLs?|prospects?)"
    r"|(?:leads?|enquir(?:y|ies)|inquir(?:y|ies)|pipeline)\s*"
    r"(?:of|at|per\s+month\s+of)?\s*(?:~)?(\d[\d,.]*))",
    re.IGNORECASE,
)
_CONVERSION = re.compile(
    r"(?:(?:conversion(?:\s+rate)?|close\s+rate|win\s+rate|"
    r"lead[- ]to[- ](?:order|sale|customer)|hit\s+rate)"
    r"[^.\d%]{0,25}(\d{1,3}(?:\.\d+)?)\s*%"
    r"|(\d{1,3}(?:\.\d+)?)\s*%\s*(?:conversion|close\s+rate|win\s+rate))",
    re.IGNORECASE,
)
_SALES_CYCLE = re.compile(
    r"(?:sales\s+cycle|cycle\s+(?:time|length)|time\s+to\s+(?:close|convert)|"
    r"lead\s+time\s+to\s+order)"
    r"[^.\d]{0,25}(\d{1,3}(?:[-–]\d{1,3})?)\s*"
    r"(days?|weeks?|months?)",
    re.IGNORECASE,
)
_CAC = re.compile(
    r"(?:CAC|cost\s+per\s+acquisition|customer\s+acquisition\s+cost|"
    r"acquisition\s+cost|cost\s+to\s+acquire)"
    r"[^.\d₹$€£]{0,25}(?:INR\s*|USD\s*|Rs\.?\s*|[₹$€£])?\s*"
    r"(\d[\d,.]*)\s*(cr|crore|lakh|lakhs|k|m|mn|million)?",
    re.IGNORECASE,
)
_RETENTION = re.compile(
    r"(?:retention(?:\s+rate)?|repeat\s+(?:rate|purchase)|renewal\s+rate|"
    r"churn(?:\s+rate)?|logo\s+retention)"
    r"[^.\d%]{0,25}(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_CHANNEL_CUE = re.compile(
    r"\b(direct\s+sales|direct|inside\s+sales|field\s+sales|telesales|"
    r"dealers?(?:hip)?s?|distributors?|resellers?|channel\s+partners?|"
    r"partners?|online|digital|e-?commerce|marketplace|retail|"
    r"franchise|referrals?|brokers?|agency|agents?|wholesale|"
    r"institutional|enterprise|SME)\b",
    re.IGNORECASE,
)
_CRM_CUE = re.compile(
    r"\b(CRM|pipeline\s+(?:report|data|review)|funnel\s+(?:data|report|metrics)|"
    r"lead\s+management|sales\s+dashboard|opportunity\s+report)\b",
    re.IGNORECASE,
)

# --- ambition cues --------------------------------------------------------

_TARGET_SHARE = re.compile(
    r"(?:target(?:s|ing|ed)?|aim(?:s|ing)?(?:\s+for)?|ambition(?:\s+of)?|"
    r"aspir(?:e|es|ation)|plans?\s+to\s+(?:reach|achieve|hold)|goal\s+of|"
    r"guidance\s+of)"
    r"[^.\d%]{0,45}(\d{1,3}(?:\.\d+)?)\s*%\s*(?:market\s+)?share",
    re.IGNORECASE,
)
_TARGET_SHARE_ALT = re.compile(
    r"(\d{1,3}(?:\.\d+)?)\s*%\s*(?:market\s+)?share\s+"
    r"(?:by|in|before)\s+((?:FY|CY)?\s?(?:19|20)?\d{2}(?:[-–/]\d{2,4})?)",
    re.IGNORECASE,
)
_AMBITION_CUE = re.compile(
    r"\b(target|ambition|aspiration|aim|management\s+case|business\s+plan|"
    r"guidance|plan\s+to\s+(?:reach|double|triple|grow)|"
    r"five[- ]year\s+plan|forecast)\b",
    re.IGNORECASE,
)
_ATTAINABLE_CUE = re.compile(
    r"\b(bottom[- ]up|attainable|achievable|base\s+case|run[- ]rate|"
    r"current\s+trajectory|extrapolat(?:e|ed|ion)|steady\s+state|"
    r"at\s+current\s+rates?)\b",
    re.IGNORECASE,
)
_LEADERSHIP = re.compile(
    r"\b(clear\s+market\s+leader|market\s+leadership|market[- ]leading|"
    r"market\s+leader|leadership\s+position|leading\s+player|"
    r"number\s+one|no\.?\s*1\b|#1\b|dominant(?:\s+position)?|dominance|"
    r"top\s+player)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_NAME = re.compile(
    r"(?i)^(?:tbd|n/?a|unnamed|placeholder|various|others?|peer\s*\d*|"
    r"competitor\s*\d*|company\s*\d*)$"
)


# ---------------------------------------------------------------------------
# small render helpers
# ---------------------------------------------------------------------------


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


def _is_filled(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text == _NA or text.startswith("N/A"):
        return False
    return not text.startswith("Information request")


def _num(raw: Any) -> float | None:
    text = str(raw or "").strip().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", text)
    if not m:
        return None
    try:
        return float(m.group(0))
    except ValueError:
        return None


def _pct_text(value: Any) -> str:
    val = _num(value)
    if val is None:
        return ""
    return f"{val:g}%"


def _soften_leadership(text: Any, *, calculable: bool = False) -> str:
    """Strip leadership/dominance claims when share is not calculable on a matched basis."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if calculable:
        return raw
    out = _LEADERSHIP.sub("share position (not calculable on a matched basis)", raw)
    if out != raw and "unassessed" not in out.lower():
        out = out.rstrip(" .") + ". " + _UNASSESSED
    return out


def _unit_family(text: Any) -> str:
    """Return revenue | units | customers | unknown for a share input description."""
    blob = str(text or "")
    if not blob.strip():
        return "unknown"
    scores = {
        "revenue": len(_UNIT_REVENUE.findall(blob)),
        "units": len(_UNIT_VOLUME.findall(blob)),
        "customers": len(_UNIT_CUSTOMERS.findall(blob)),
    }
    best = max(scores, key=lambda k: scores[k])
    return best if scores[best] > 0 else "unknown"


def _period_of(text: Any) -> str:
    m = _DATE.search(str(text or ""))
    if not m:
        return ""
    return _clean(m.group(1), 20)


def _scope_service(corpus: str, *, sector: str | None = None) -> str:
    m = _SERVICE_CUE.search(corpus or "")
    if m:
        candidate = _clean(m.group(1), 60)
        if len(candidate) >= 4 and candidate.lower() not in _GEO_STOP:
            return f"{candidate} {_DOC_CITE}"
    if sector and str(sector).strip():
        return f"{_clean(sector, 60)} {_DOC_CITE}"
    return _info_request("service / segment the share applies to")


def _scope_geography(corpus: str, *, geography: str | None = None) -> str:
    if geography and str(geography).strip():
        return f"{_clean(geography, 60)} {_DOC_CITE}"
    for m in _GEO_CUE.finditer(corpus or ""):
        candidate = _clean(m.group(1), 50)
        if candidate.lower().strip() in _GEO_STOP:
            continue
        if len(candidate) >= 3:
            return f"{candidate} {_DOC_CITE}"
    m2 = _GEO_WORD.search(corpus or "")
    if m2:
        return f"{_clean(m2.group(1), 40)} scope {_DOC_CITE}"
    return _info_request("geography the numerator and denominator both cover")


def _share_calculable(
    numerator: Any,
    denominator: Any,
    *,
    unit_numerator: str | None = None,
    unit_denominator: str | None = None,
    service: Any = None,
    geography: Any = None,
    date_or_period: Any = None,
) -> tuple[bool, str]:
    """Return (calculable, match_notes).

    Share is calculable only when the numerator (accounts) and the denominator
    (approved market perimeter) match on service, geography, unit and date.
    """
    num = str(numerator or "").strip()
    den = str(denominator or "").strip()
    fails: list[str] = []

    if not _is_filled(num):
        fails.append("numerator from the accounts is not evidenced")
    if not _is_filled(den):
        fails.append("denominator from the approved market perimeter is not evidenced")

    un = (unit_numerator or "").strip().lower() or _unit_family(num)
    ud = (unit_denominator or "").strip().lower() or _unit_family(den)
    if un == "unknown":
        fails.append("unit basis of the numerator is not stated")
    if ud == "unknown":
        fails.append("unit basis of the denominator is not stated")
    if un != "unknown" and ud != "unknown" and un != ud:
        fails.append(
            f"unit mismatch — numerator on {un}, denominator on {ud}; "
            "a share cannot be formed across different units"
        )

    svc = str(service or "").strip()
    if not _is_filled(svc):
        fails.append("service / segment scope is not matched")

    geo = str(geography or "").strip()
    if not _is_filled(geo):
        geo_blob = f"{num} {den}"
        if _GEO_CUE.search(geo_blob) or _GEO_WORD.search(geo_blob):
            geo = _clean(geo_blob, 60)
        else:
            fails.append("geography is not matched across numerator and denominator")

    period = str(date_or_period or "").strip()
    if not _is_filled(period):
        period = _period_of(f"{num} {den}")
        if not period:
            fails.append("date / period is not matched across numerator and denominator")

    if fails:
        return False, (
            "Share not calculable: " + "; ".join(fails[:4]) + ". " + _UNASSESSED
        )
    return True, (
        f"Numerator and denominator match on service, geography, unit ({un}) "
        f"and period ({period or 'as stated'}) {_COMPUTED}"
    )


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_market_share_strategy_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "customer": 2,
        "financial": 3,
        "operations": 4,
        "company_management": 5,
    }
    needles = (
        "share", "competition", "competitor", "win", "loss", "funnel", "crm",
        "commercial", "thesis", "volume", "capacity", "pipeline", "sales",
        "growth", "plan",
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
# heuristic extraction
# ---------------------------------------------------------------------------


def _stated_share(corpus: str) -> tuple[str, str] | None:
    """Return (pct, surrounding sentence) for any share percentage stated in prose."""
    text = corpus or ""
    for pattern in (_SHARE_PCT, _PCT_SHARE):
        m = pattern.search(text)
        if m:
            start = max(0, m.start() - 160)
            return m.group(1), _clean(text[start : m.end() + 160], 240)
    return None


def _subject_of(sent: str, *, focal: str = "") -> str:
    m = _SUBJECT_SHARE.search(sent or "")
    if m:
        name = _clean(m.group(1), 60).rstrip(".,;")
        if (
            len(name) >= 2
            and not _PLACEHOLDER_NAME.match(name)
            and name.lower() not in _GEO_STOP
            and name.lower() not in {"its", "our", "their", "the"}
        ):
            return name
    if re.search(r"(?i)\b(the\s+company|the\s+group|the\s+target|the\s+business)\b", sent or ""):
        return focal or "Focal company"
    return focal or _info_request("whose share moved (named company)")


def _movement_context(corpus: str) -> tuple[str, str, str]:
    """Return (vs_market_growth, acquisition_contribution, organic_notes) from corpus."""
    sents = _sentences(corpus)
    growth_hit = next((s for s in sents if _MARKET_GROWTH_CUE.search(s)), "")
    acq_hit = next((s for s in sents if _ACQUISITION_CUE.search(s)), "")
    org_hit = next((s for s in sents if _ORGANIC_CUE.search(s)), "")

    vs_growth = (
        f"{_clean(growth_hit, 170)} {_DOC_CITE}"
        if growth_hit
        else _info_request("market growth for the same period, to separate share gain from market growth")
    )
    acq = (
        f"{_clean(acq_hit, 170)} {_DOC_CITE}"
        if acq_hit
        else _info_request("acquisition contribution to the share change (M&A vs organic split)")
    )
    if org_hit:
        organic = f"{_clean(org_hit, 170)} {_DOC_CITE}"
    elif growth_hit and acq_hit:
        organic = (
            "Organic component must be derived by removing market growth and "
            f"acquisition contribution from the reported change {_COMPUTED}"
        )
    else:
        organic = _info_request("organic share change excluding market growth and acquisitions")
    return vs_growth, acq, organic


def _delta_pp(share_from: Any, share_to: Any) -> str:
    a, b = _num(share_from), _num(share_to)
    if a is None or b is None:
        return _info_request("share delta in percentage points (pp) — both endpoints required")
    return f"{b - a:+.1f} pp {_COMPUTED}"


def _trend_label(text: str) -> str:
    blob = text or ""
    if _GAIN_CUE.search(blob):
        return "Gaining share"
    if _LOSS_CUE.search(blob):
        return "Losing share"
    return ""


def _extract_matched_share(
    corpus: str,
    *,
    sector: str | None = None,
    geography: str | None = None,
    legacy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del legacy  # legacy share numbers are stated, not matched — never promote them here
    sents = _sentences(corpus)
    num_sent = next((s for s in sents if _NUMERATOR_CUE.search(s)), "")
    den_sent = next((s for s in sents if _DENOMINATOR_CUE.search(s)), "")

    numerator = (
        f"{_clean(num_sent, 200)} {_DOC_CITE}"
        if num_sent
        else _info_request(
            "share numerator from the accounts (service revenue or units for the stated period)"
        )
    )
    denominator = (
        f"{_clean(den_sent, 200)} {_DOC_CITE}"
        if den_sent
        else _info_request(
            "share denominator from the approved market perimeter (same service, geography, unit and date)"
        )
    )
    service = _scope_service(corpus, sector=sector)
    geo = _scope_geography(corpus, geography=geography)
    un = _unit_family(num_sent)
    ud = _unit_family(den_sent)
    period = _period_of(f"{num_sent} {den_sent}") or _period_of(corpus)
    unit_label = (
        f"{un} (numerator) / {ud} (denominator)"
        if un != ud
        else (un if un != "unknown" else _info_request("unit both sides are measured in"))
    )

    scope_ok, notes = _share_calculable(
        numerator,
        denominator,
        unit_numerator=un,
        unit_denominator=ud,
        service=service,
        geography=geo,
        date_or_period=period,
    )
    stated = _stated_share(corpus)
    share_pct: str | None = None
    calculable = False
    if scope_ok and stated:
        calculable = True
        share_pct = _pct_text(stated[0])
        notes = (
            f"{notes} Share {share_pct} reconciles to the matched numerator and "
            f"denominator above {_DOC_CITE}"
        )
    elif scope_ok and not stated:
        notes = (
            "Share not calculable: numerator and denominator scope matches, but no "
            f"share value or arithmetic is stated for the period. {_UNASSESSED}"
        )
    elif stated:
        notes = (
            f"{notes} A share of {_pct_text(stated[0])} is stated in prose "
            f"({_clean(stated[1], 140)}) but it is not tied to a matched numerator "
            f"and denominator, so it is not adopted as a calculated share {_DOC_CITE}"
        )

    info_req = ""
    if not calculable:
        info_req = _info_request(
            "matched share inputs — service revenue or units from the accounts as numerator, "
            "and the approved market perimeter on the same service, geography, unit and date "
            "as denominator"
        )

    return {
        "calculable": calculable,
        "numerator": numerator,
        "denominator": denominator,
        "share_pct": share_pct,
        "service": service,
        "geography": geo,
        "unit": unit_label,
        "date_or_period": period or _info_request("date / period both sides cover"),
        "match_notes": notes,
        "information_request": info_req,
        "source": _DOC_CITE if (num_sent or den_sent) else _NA,
    }


def _legacy_trend_rows(legacy: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in (legacy or {}).get("share_trends") or []:
        if isinstance(raw, dict):
            rows.append(raw)
        elif hasattr(raw, "model_dump"):
            try:
                dumped = raw.model_dump()
                if isinstance(dumped, dict):
                    rows.append(dumped)
            except Exception:
                continue
    return rows


def _extract_share_movement(
    corpus: str,
    *,
    focal: str = "",
    legacy: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    vs_growth, acq, organic = _movement_context(corpus)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(row: dict[str, str]) -> None:
        key = str(row.get("peer_or_focal") or "").lower()[:40]
        if key and key in seen:
            return
        if key:
            seen.add(key)
        rows.append(row)

    # 1. Explicit "share from X% (period) to Y% (period)" statements.
    for sent in sents:
        m = _SHARE_FROM_TO.search(sent)
        if not m:
            continue
        s_from, p_from, s_to, p_to = m.group(1), m.group(2), m.group(3), m.group(4)
        periods = _DATE.findall(sent)
        period_from = _clean(p_from or (periods[0] if periods else ""), 20)
        period_to = _clean(p_to or (periods[1] if len(periods) > 1 else ""), 20)
        local_growth = (
            f"{_clean(sent, 160)} {_DOC_CITE}"
            if _MARKET_GROWTH_CUE.search(sent)
            else vs_growth
        )
        local_acq = (
            f"{_clean(sent, 160)} {_DOC_CITE}"
            if _ACQUISITION_CUE.search(sent)
            else acq
        )
        _add({
            "peer_or_focal": _subject_of(sent, focal=focal),
            "period_from": period_from or _info_request("opening period"),
            "period_to": period_to or _info_request("closing period"),
            "share_from_pct": _pct_text(s_from),
            "share_to_pct": _pct_text(s_to),
            "delta_pp": _delta_pp(s_from, s_to),
            "vs_market_growth": local_growth,
            "acquisition_contribution": local_acq,
            "organic_notes": organic,
            "source": _DOC_CITE,
        })
        if len(rows) >= 6:
            break

    # 2. Trend table rows: "<Name> 12.4% Strong Gain".
    if len(rows) < 6:
        for m in _TREND_ROW.finditer(corpus or ""):
            name = _clean(m.group(1), 60).rstrip(".,;")
            if _PLACEHOLDER_NAME.match(name) or name.lower() in _GEO_STOP:
                continue
            label = _clean(m.group(3), 30)
            _add({
                "peer_or_focal": name,
                "period_from": _info_request("opening period for the trend label"),
                "period_to": _period_of(corpus) or _info_request("closing period"),
                "share_from_pct": _info_request("opening share"),
                "share_to_pct": _pct_text(m.group(2)),
                "delta_pp": _info_request(
                    f"share delta in percentage points — trend stated as '{label}' only"
                ),
                "vs_market_growth": vs_growth,
                "acquisition_contribution": acq,
                "organic_notes": organic,
                "source": _DOC_CITE,
            })
            if len(rows) >= 6:
                break

    # 3. Directional prose without both endpoints.
    if len(rows) < 6:
        for sent in _pick_sentences(
            sents,
            keywords=("share", "gain", "losing", "declining", "erosion", "outgrew"),
            limit=8,
        ):
            label = _trend_label(sent)
            if not label:
                continue
            _add({
                "peer_or_focal": _subject_of(sent, focal=focal),
                "period_from": _info_request("opening period"),
                "period_to": _period_of(sent) or _info_request("closing period"),
                "share_from_pct": _info_request("opening share"),
                "share_to_pct": _info_request("closing share"),
                "delta_pp": _info_request(
                    f"share delta in percentage points — prose states '{label}' without endpoints"
                ),
                "vs_market_growth": (
                    f"{_clean(sent, 160)} {_DOC_CITE}"
                    if _MARKET_GROWTH_CUE.search(sent)
                    else vs_growth
                ),
                "acquisition_contribution": (
                    f"{_clean(sent, 160)} {_DOC_CITE}"
                    if _ACQUISITION_CUE.search(sent)
                    else acq
                ),
                "organic_notes": organic,
                "source": _DOC_CITE,
            })
            if len(rows) >= 6:
                break

    # 4. Legacy trend rows as a movement seed (stated share, not a matched calculation).
    if len(rows) < 6:
        for raw in _legacy_trend_rows(legacy):
            name = _clean(raw.get("name"), 60)
            if not name or _PLACEHOLDER_NAME.match(name):
                continue
            pct = raw.get("market_share_pct")
            trend = _clean(raw.get("trend"), 40)
            _add({
                "peer_or_focal": name,
                "period_from": _info_request("opening period for the stated share"),
                "period_to": _info_request("closing period for the stated share"),
                "share_from_pct": _info_request("opening share"),
                "share_to_pct": _pct_text(pct) if pct is not None else _info_request("stated share"),
                "delta_pp": _info_request(
                    "share delta in percentage points — legacy extract carries a stated "
                    f"share{f' with trend {trend}' if trend else ''}, not two endpoints"
                ),
                "vs_market_growth": vs_growth,
                "acquisition_contribution": acq,
                "organic_notes": organic,
                "source": _DOC_CITE,
            })
            if len(rows) >= 6:
                break

    if not rows:
        rows.append({
            "peer_or_focal": _info_request("company whose share movement is measured"),
            "period_from": _info_request("opening period"),
            "period_to": _info_request("closing period"),
            "share_from_pct": _info_request("opening share"),
            "share_to_pct": _info_request("closing share"),
            "delta_pp": _info_request("share delta in percentage points (pp)"),
            "vs_market_growth": vs_growth,
            "acquisition_contribution": acq,
            "organic_notes": organic,
            "source": _NA,
        })
    return rows[:6]


def _first_group(m: re.Match[str] | None) -> str:
    if not m:
        return ""
    for g in m.groups():
        if g:
            return str(g)
    return str(m.group(0))


def _extract_plan_requirements(corpus: str) -> dict[str, str]:
    text = corpus or ""
    sents = _sentences(text)
    plan_sents = [s for s in sents if _PLAN_CUE.search(s)]
    plan_blob = " ".join(plan_sents) if plan_sents else text

    def _hit(pattern: re.Pattern[str], unit_hint: str = "") -> str:
        m = pattern.search(plan_blob) or pattern.search(text)
        if not m:
            return ""
        raw = _first_group(m)
        val = _fmt_num(raw, unit_hint) if raw else ""
        context = _clean(m.group(0), 90)
        if val and val not in context:
            return f"{context} (~{val}) {_DOC_CITE}"
        return f"{context} {_DOC_CITE}"

    cust = _hit(_CUSTOMERS_PER_PERIOD) or _hit(_CUSTOMERS_PER_PERIOD_ALT)
    volume = _hit(_VOLUME)
    capacity = _hit(_CAPACITY)
    headcount = _hit(_HEADCOUNT)

    other = ""
    for sent in plan_sents:
        if re.search(
            r"(?i)\b(service\s+centres?|service\s+centers?|workshops?|charging|"
            r"hubs?|depots?|technicians?|installers?|engineers?|"
            r"working\s+capital|inventory|spares?)\b",
            sent,
        ):
            other = f"{_clean(sent, 180)} {_DOC_CITE}"
            break

    missing = [
        label
        for label, value in (
            ("customers to win per month", cust),
            ("volume required", volume),
            ("vehicles / capacity required", capacity),
            ("sales headcount required", headcount),
        )
        if not value
    ]
    filled_any = any([cust, volume, capacity, headcount, other])

    return {
        "customers_per_month": cust or _info_request("customers to win per month under the plan"),
        "volume": volume or _info_request("volume required by the plan"),
        "capacity": capacity or _info_request("vehicles / capacity required to serve the plan"),
        "sales_headcount": headcount or _info_request("sales headcount required to win the plan"),
        "other_physical": other or _info_request(
            "other physical requirements of the plan (service capacity, working capital, people)"
        ),
        "source": _DOC_CITE if filled_any else _NA,
        "gaps": (
            _info_request(", ".join(missing))
            if missing
            else f"All four physical requirements are evidenced in the plan {_COMPUTED}"
        ),
    }


def _channel_name(sent: str) -> str:
    m = _CHANNEL_CUE.search(sent or "")
    if not m:
        return ""
    name = _clean(m.group(1), 40)
    return name[:1].upper() + name[1:] if name else ""


def _funnel_row(channel: str, blob: str, *, source: str) -> dict[str, str]:
    leads_m = _LEADS.search(blob)
    conv_m = _CONVERSION.search(blob)
    cycle_m = _SALES_CYCLE.search(blob)
    cac_m = _CAC.search(blob)
    ret_m = _RETENTION.search(blob)
    return {
        "channel": channel,
        "leads": (
            f"{_clean(leads_m.group(0), 70)} {_DOC_CITE}"
            if leads_m
            else _info_request("lead volume for this channel")
        ),
        "conversion_rate": (
            f"{_pct_text(_first_group(conv_m))} {_DOC_CITE}"
            if conv_m
            else _info_request("lead-to-order conversion rate")
        ),
        "sales_cycle": (
            f"{_clean(cycle_m.group(1), 20)} {_clean(cycle_m.group(2), 12)} {_DOC_CITE}"
            if cycle_m
            else _info_request("sales cycle length")
        ),
        "cac": (
            f"{_clean(cac_m.group(0), 70)} {_DOC_CITE}"
            if cac_m
            else _info_request("cost per acquisition (CAC)")
        ),
        "retention": (
            f"{_pct_text(ret_m.group(1))} {_DOC_CITE}"
            if ret_m
            else _info_request("retention / repeat rate for this channel")
        ),
        "source": source,
    }


def _extract_funnel_economics(corpus: str) -> list[dict[str, str]]:
    text = corpus or ""
    sents = _sentences(text)
    metric_patterns = (_LEADS, _CONVERSION, _SALES_CYCLE, _CAC, _RETENTION)
    metric_sents = [
        s for s in sents if any(p.search(s) for p in metric_patterns)
    ]
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    for sent in metric_sents:
        channel = _channel_name(sent)
        if not channel:
            continue
        key = channel.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(_funnel_row(channel, sent, source=_DOC_CITE))
        if len(rows) >= 6:
            break

    if not rows and metric_sents:
        blob = " ".join(metric_sents)
        rows.append(
            _funnel_row(
                "All channels (channel split not stated)",
                blob,
                source=_DOC_CITE,
            )
        )

    if not rows:
        crm_note = (
            "CRM / pipeline data referenced but no funnel rates extracted"
            if _CRM_CUE.search(text)
            else "no CRM / pipeline data in the opened packs"
        )
        rows.append({
            "channel": _info_request(f"channel-level funnel ({crm_note})"),
            "leads": _info_request("leads by channel"),
            "conversion_rate": _info_request("conversion rate by channel"),
            "sales_cycle": _info_request("sales cycle length by channel"),
            "cac": _info_request("cost per acquisition by channel"),
            "retention": _info_request("retention by channel"),
            "source": _NA,
        })
    return rows[:6]


def _bottom_up_from_funnel(funnel: list[dict[str, str]]) -> tuple[str, float | None]:
    """Derive an attainable customers-per-period figure from funnel rates."""
    for row in funnel:
        if not isinstance(row, dict):
            continue
        leads = _num(row.get("leads")) if _is_filled(row.get("leads")) else None
        conv = _num(row.get("conversion_rate")) if _is_filled(row.get("conversion_rate")) else None
        if leads is None or conv is None:
            continue
        won = leads * conv / 100.0
        channel = _clean(row.get("channel"), 40)
        return (
            f"{channel}: ~{_fmt_num(f'{leads:g}')} leads × {conv:g}% conversion "
            f"≈ {won:.0f} new customers per stated period {_COMPUTED}"
        ), won
    return "", None


def _attainable_vs_ambition(
    corpus: str,
    *,
    funnel: list[dict[str, str]],
    plan: dict[str, str],
    calculable: bool,
) -> dict[str, str]:
    text = corpus or ""
    sents = _sentences(text)

    ambition = ""
    target_pct: float | None = None
    m = _TARGET_SHARE.search(text)
    if m:
        target_pct = _num(m.group(1))
        ambition = f"{_clean(m.group(0), 160)} {_DOC_CITE}"
    else:
        m2 = _TARGET_SHARE_ALT.search(text)
        if m2:
            target_pct = _num(m2.group(1))
            ambition = (
                f"Management ambition {_pct_text(m2.group(1))} share by "
                f"{_clean(m2.group(2), 20)} {_DOC_CITE}"
            )
    if not ambition:
        hit = next(
            (
                s for s in _pick_sentences(
                    sents,
                    keywords=("target", "ambition", "plan", "guidance", "aim", "forecast"),
                    limit=6,
                )
                if _AMBITION_CUE.search(s) and re.search(r"\d", s)
            ),
            "",
        )
        ambition = (
            f"{_clean(hit, 200)} {_DOC_CITE}"
            if hit
            else _info_request("management ambition for share, volume or customers with a date")
        )

    bottom_up, attainable_customers = _bottom_up_from_funnel(funnel)
    if not bottom_up:
        hit = next((s for s in sents if _ATTAINABLE_CUE.search(s)), "")
        bottom_up = (
            f"{_clean(hit, 200)} {_DOC_CITE}"
            if hit
            else _info_request(
                "bottom-up attainable case built from funnel rates (leads × conversion × "
                "capacity) for the same period as the ambition"
            )
        )

    plan_customers = _num(plan.get("customers_per_month")) if _is_filled(
        plan.get("customers_per_month")
    ) else None

    gap = ""
    if attainable_customers is not None and plan_customers is not None:
        shortfall = plan_customers - attainable_customers
        gap = (
            f"Plan needs ~{plan_customers:g} customers per month; funnel rates support "
            f"~{attainable_customers:.0f} — "
            + (
                f"shortfall of ~{shortfall:.0f} per month {_COMPUTED}"
                if shortfall > 0
                else f"headroom of ~{abs(shortfall):.0f} per month {_COMPUTED}"
            )
        )
    elif target_pct is not None and calculable:
        gap = (
            f"Ambition of {target_pct:g}% share must be bridged from the matched share "
            f"above; the gap is expressed in percentage points (pp), not % {_COMPUTED}"
        )
    else:
        gap = _info_request(
            "gap between the bottom-up attainable case and management ambition, in "
            "percentage points of share and in customers/volume per period"
        )

    levers: list[str] = []
    for label, pattern in (
        ("conversion rate", _CONVERSION),
        ("lead volume", _LEADS),
        ("sales headcount", _HEADCOUNT),
        ("capacity", _CAPACITY),
        ("sales cycle", _SALES_CYCLE),
        ("CAC", _CAC),
        ("retention", _RETENTION),
    ):
        if pattern.search(text):
            levers.append(label)
    what_must_change = (
        (
            "To close the gap the plan depends on: "
            + ", ".join(levers[:5])
            + f". Each must be evidenced as achievable against the current run-rate {_COMPUTED}"
        )
        if levers
        else _info_request(
            "what would have to change to close the gap (conversion, lead volume, "
            "headcount, capacity) with evidence it is achievable"
        )
    )

    return {
        "bottom_up_attainable": bottom_up,
        "management_ambition": ambition,
        "gap": gap,
        "what_must_change": what_must_change,
        "source": _DOC_CITE if (_is_filled(ambition) or _is_filled(bottom_up)) else _NA,
    }


def _coerce_trend_row(raw: Any) -> dict[str, Any] | None:
    """Coerce legacy/derived rows to the CompetitorRow shape decks expect."""
    if hasattr(raw, "model_dump"):
        try:
            raw = raw.model_dump()
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    name = _clean(raw.get("name"), 60)
    if not name or _PLACEHOLDER_NAME.match(name):
        return None

    def _f(key: str) -> float | None:
        return _num(raw.get(key)) if raw.get(key) is not None else None

    trend = raw.get("trend")
    software = raw.get("software")
    return {
        "name": name,
        "market_share_pct": _f("market_share_pct"),
        "units_000s": _f("units_000s"),
        "flagship_price_inr": _f("flagship_price_inr"),
        "trend": _clean(trend, 40) if trend else None,
        "nps": _f("nps"),
        "software": _clean(software, 60) if software else None,
    }


def _legacy_fields(
    movement: list[dict[str, str]],
    corpus: str,
    legacy: dict[str, Any] | None,
    *,
    focal: str = "",
    attainable: dict[str, str] | None = None,
    matched_share: dict[str, Any] | None = None,
) -> dict[str, list[Any]]:
    legacy = legacy if isinstance(legacy, dict) else {}
    calculable = bool((matched_share or {}).get("calculable"))

    share_trends: list[dict[str, Any]] = []
    for raw in _legacy_trend_rows(legacy):
        row = _coerce_trend_row(raw)
        if row:
            share_trends.append(row)
    if not share_trends:
        for row in movement:
            if not isinstance(row, dict):
                continue
            name = str(row.get("peer_or_focal") or "")
            if not name or name.startswith("Information"):
                continue
            pct = _num(row.get("share_to_pct")) if _is_filled(row.get("share_to_pct")) else None
            trend = _trend_label(
                " ".join(
                    str(row.get(k) or "")
                    for k in ("delta_pp", "organic_notes", "vs_market_growth")
                )
            )
            delta = _num(row.get("delta_pp"))
            if not trend and delta is not None:
                trend = "Gaining share" if delta > 0 else ("Losing share" if delta < 0 else "Flat")
            coerced = _coerce_trend_row({
                "name": name,
                "market_share_pct": pct,
                "trend": trend or None,
            })
            if coerced:
                share_trends.append(coerced)

    wins: list[str] = []
    losses: list[str] = []
    focal_key = (focal or "").strip().lower()
    for row in movement:
        if not isinstance(row, dict):
            continue
        name = str(row.get("peer_or_focal") or "")
        if not name or name.startswith("Information"):
            continue
        share_to = row.get("share_to_pct")
        share_txt = _pct_text(share_to) or "share n/a"
        delta = _num(row.get("delta_pp"))
        blob = " ".join(
            str(row.get(k) or "")
            for k in ("delta_pp", "organic_notes", "vs_market_growth", "acquisition_contribution")
        )
        label = _trend_label(blob)
        gaining = (delta > 0) if delta is not None else (label == "Gaining share")
        losing = (delta < 0) if delta is not None else (label == "Losing share")
        if not label and delta is not None:
            label = "Gaining share" if delta > 0 else ("Losing share" if delta < 0 else "Flat")
        is_focal = bool(focal_key) and focal_key in name.lower()
        line = f"{name}: {label or 'movement stated'} (share {share_txt})"
        if is_focal and gaining:
            wins.append(line)
        elif is_focal and losing:
            losses.append(line)
        elif not is_focal and losing:
            wins.append(f"Share opportunity · {line}")
        elif not is_focal and gaining:
            losses.append(f"Share pressure · {line}")

    notes: list[str] = []
    att = attainable or {}
    for key in ("gap", "what_must_change", "bottom_up_attainable"):
        value = att.get(key)
        if _is_filled(value):
            notes.append(_soften_leadership(_clean(value, 200), calculable=calculable))
    if matched_share and not calculable:
        notes.append(
            "Share is not calculable on a matched numerator/denominator basis — "
            "unassessed, not a leadership or weakness finding."
        )
    for sent in _pick_sentences(
        _sentences(corpus),
        keywords=("share", "plan", "capacity", "conversion", "headcount", "channel"),
        limit=4,
    ):
        notes.append(_soften_leadership(_clean(sent, 180), calculable=calculable))
        if len(notes) >= 5:
            break

    def _merge(primary: list[str], fallback_key: str) -> list[str]:
        out = list(dict.fromkeys([x for x in primary if isinstance(x, str) and x.strip()]))
        if out:
            return out[:5]
        fb = legacy.get(fallback_key) or []
        return [
            _soften_leadership(x, calculable=calculable)
            for x in fb
            if isinstance(x, str) and x.strip()
        ][:5]

    return {
        "share_trends": share_trends[:8],
        "wins": _merge(wins, "wins"),
        "losses": _merge(losses, "losses"),
        "strategy_notes": _merge(notes, "strategy_notes"),
    }


def _movement_split_complete(movement: list[dict[str, str]]) -> bool:
    for row in movement:
        if not isinstance(row, dict):
            continue
        if _is_filled(row.get("vs_market_growth")) and _is_filled(
            row.get("acquisition_contribution")
        ):
            return True
    return False


def _quality_reliance(
    *,
    calculable: bool,
    share_stated: bool,
    movement_count: int,
    funnel_count: int,
    plan_filled: bool,
    attainable_filled: bool,
    split_complete: bool,
) -> tuple[str, str, str]:
    evidence_bits = (
        f"{movement_count} movement row(s); {funnel_count} funnel row(s); "
        f"plan requirements {'evidenced' if plan_filled else 'incomplete'}; "
        f"attainable-vs-ambition {'built' if attainable_filled else 'incomplete'}; "
        f"organic vs M&A split {'separated' if split_complete else 'not separated'}."
    )
    if calculable and (movement_count or funnel_count or attainable_filled):
        if split_complete:
            return (
                "PASS",
                "READY",
                f"Share calculated on matched numerator and denominator. {evidence_bits}",
            )
        return (
            "PASS",
            "LIMITED",
            (
                "Share calculated on matched inputs, but share movement is not separated "
                f"from market growth and acquisitions. {evidence_bits}"
            ),
        )
    if share_stated or movement_count or funnel_count or plan_filled or attainable_filled:
        return (
            "PASS",
            "LIMITED",
            (
                "Share is not calculable on a matched numerator/denominator basis — "
                "unassessed, establishing neither leadership nor weakness. "
                f"{evidence_bits}"
            ),
        )
    return (
        "PASS",
        "BLOCKED",
        (
            "Share is unassessed (numerator and denominator cannot be matched) and no "
            "share movement, plan requirement or funnel evidence was found in the "
            "opened packs."
        ),
    )


def _heuristic_market_share_strategy_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra_bits: list[str] = []
    for key in ("wins", "losses", "strategy_notes"):
        for item in (legacy.get(key) or [])[:6]:
            if isinstance(item, str) and item.strip():
                extra_bits.append(item.strip())
    for raw in _legacy_trend_rows(legacy)[:8]:
        name = _clean(raw.get("name"), 60)
        pct = raw.get("market_share_pct")
        trend = _clean(raw.get("trend"), 40)
        if name:
            bits = [name]
            if pct is not None:
                bits.append(f"{_pct_text(pct)} market share")
            if trend:
                bits.append(trend)
            extra_bits.append(" ".join(bits))
    corpus_full = (corpus or "") + ("\n" + "\n".join(extra_bits) if extra_bits else "")

    matched = _extract_matched_share(
        corpus_full, sector=sector, geography=geography, legacy=legacy
    )
    movement = _extract_share_movement(corpus_full, focal=company, legacy=legacy)
    plan = _extract_plan_requirements(corpus_full)
    funnel = _extract_funnel_economics(corpus_full)
    attainable = _attainable_vs_ambition(
        corpus_full,
        funnel=funnel,
        plan=plan,
        calculable=bool(matched.get("calculable")),
    )
    legacy_fields = _legacy_fields(
        movement,
        corpus_full,
        legacy,
        focal=company,
        attainable=attainable,
        matched_share=matched,
    )

    calculable = bool(matched.get("calculable"))
    movement_count = sum(
        1 for r in movement
        if isinstance(r, dict) and not str(r.get("peer_or_focal") or "").startswith("Information")
    )
    funnel_count = sum(
        1 for r in funnel
        if isinstance(r, dict) and not str(r.get("channel") or "").startswith("Information")
    )
    plan_filled = any(
        _is_filled(plan.get(k))
        for k in ("customers_per_month", "volume", "capacity", "sales_headcount")
    )
    attainable_filled = _is_filled(attainable.get("bottom_up_attainable")) and _is_filled(
        attainable.get("management_ambition")
    )
    split_complete = _movement_split_complete(movement)
    quality, reliance, rationale = _quality_reliance(
        calculable=calculable,
        share_stated=bool(_stated_share(corpus_full)),
        movement_count=movement_count,
        funnel_count=funnel_count,
        plan_filled=plan_filled,
        attainable_filled=attainable_filled,
        split_complete=split_complete,
    )

    share_txt = (
        f"matched share {matched.get('share_pct')}"
        if calculable and matched.get("share_pct")
        else "share not calculable on a matched numerator/denominator basis (unassessed)"
    )
    insight = _soften_leadership(
        (
            f"Market Share Strategy for {company}: {share_txt}; "
            f"{movement_count} share-movement row(s) with market growth and acquisition "
            f"contribution held separately; plan translated into physical requirements "
            f"({'evidenced' if plan_filled else 'gaps named'}); "
            f"{funnel_count} funnel row(s); bottom-up attainable case set beside "
            f"management ambition. Share deltas are stated in percentage points (pp)."
        ),
        calculable=calculable,
    )

    return {
        "insight_snapshot": insight,
        "matched_share": matched,
        "share_movement": movement,
        "plan_requirements": plan,
        "funnel_economics": funnel,
        "attainable_vs_ambition": attainable,
        "share_trends": legacy_fields["share_trends"],
        "wins": legacy_fields["wins"],
        "losses": legacy_fields["losses"],
        "strategy_notes": legacy_fields["strategy_notes"],
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": list(sources or [])[:16],
        "composer": "heuristic_v1",
        "empty": (
            not calculable
            and movement_count == 0
            and funnel_count == 0
            and not plan_filled
            and not legacy_fields["share_trends"]
        ),
    }


# ---------------------------------------------------------------------------
# LLM composer
# ---------------------------------------------------------------------------


def _llm_market_share_strategy_spec(
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

    if not gemini_configured() or not (corpus or "").strip():
        return None

    try:
        system = compose_system(
            "market_share_strategy",
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
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "matched_share: {calculable (bool), numerator, denominator, share_pct (string or null), "
        "service, geography, unit, date_or_period, match_notes, information_request, source},\n"
        "share_movement: [{peer_or_focal, period_from, period_to, share_from_pct, "
        "share_to_pct, delta_pp, vs_market_growth, acquisition_contribution, "
        "organic_notes, source}],\n"
        "plan_requirements: {customers_per_month, volume, capacity, sales_headcount, "
        "other_physical, source, gaps},\n"
        "funnel_economics: [{channel, leads, conversion_rate, sales_cycle, cac, "
        "retention, source}],\n"
        "attainable_vs_ambition: {bottom_up_attainable, management_ambition, gap, "
        "what_must_change, source},\n"
        "share_trends: [{name, market_share_pct, units_000s, flagship_price_inr, trend, "
        "nps, software}] — names only from the evidence,\n"
        "wins: [string],\n"
        "losses: [string],\n"
        "strategy_notes: [string],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n\n"
        "Rules:\n"
        "Do NOT calculate share unless numerator and denominator match on service, "
        "geography, unit and date. The numerator comes from the accounts and the "
        "denominator from the approved market perimeter. If they cannot be matched, set "
        "calculable false, share_pct null, and name the information request.\n"
        "Missing share is unassessed — it establishes neither leadership nor weakness. "
        "Never describe the target as a market leader from missing or unmatched share.\n"
        "Use percentage points (pp) for share deltas — not % for deltas.\n"
        "Separate share movement from market growth and from acquisitions in every row.\n"
        "Translate the growth plan into physical requirements: customers per month, "
        "volume, vehicles/capacity, sales headcount.\n"
        "Read the funnel only where CRM/pipeline data exist: leads, conversion, sales "
        "cycle, CAC, retention by channel.\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
        "Do NOT invent peer, OEM or channel lists — extract names from evidence only.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    # --- matched share -----------------------------------------------------
    matched = llm.get("matched_share")
    if not isinstance(matched, dict):
        matched = _extract_matched_share(corpus, legacy=legacy)
    else:
        for key, label in (
            ("numerator", "share numerator from the accounts"),
            ("denominator", "share denominator from the approved market perimeter"),
            ("service", "service / segment the share applies to"),
            ("geography", "geography both sides cover"),
            ("unit", "unit both sides are measured in"),
            ("date_or_period", "date / period both sides cover"),
        ):
            if not str(matched.get(key) or "").strip():
                matched[key] = _info_request(label)
        scope_ok, notes = _share_calculable(
            matched.get("numerator"),
            matched.get("denominator"),
            service=matched.get("service"),
            geography=matched.get("geography"),
            date_or_period=matched.get("date_or_period"),
        )
        claimed = bool(matched.get("calculable")) and bool(
            str(matched.get("share_pct") or "").strip()
        )
        calculable = bool(scope_ok and claimed)
        matched["calculable"] = calculable
        if not calculable:
            matched["share_pct"] = None
            if not str(matched.get("match_notes") or "").strip():
                matched["match_notes"] = notes
            elif "not calculable" not in str(matched["match_notes"]).lower():
                matched["match_notes"] = (
                    f"{_clean(matched['match_notes'], 300)} {notes}"
                )
            if not _is_filled(matched.get("information_request")):
                matched["information_request"] = _info_request(
                    "matched share inputs — numerator from the accounts and denominator "
                    "from the approved market perimeter on the same service, geography, "
                    "unit and date"
                )
        else:
            matched["share_pct"] = _pct_text(matched.get("share_pct")) or str(
                matched.get("share_pct")
            )
            matched["information_request"] = str(matched.get("information_request") or "")
            if not str(matched.get("match_notes") or "").strip():
                matched["match_notes"] = notes
        matched.setdefault("source", _DOC_CITE)
    llm["matched_share"] = matched
    calculable = bool(matched.get("calculable"))

    # --- share movement ----------------------------------------------------
    vs_growth, acq, organic = _movement_context(corpus)
    cleaned_movement: list[dict[str, Any]] = []
    for row in llm.get("share_movement") or []:
        if not isinstance(row, dict):
            continue
        name = _clean(row.get("peer_or_focal"), 60)
        if not name or _PLACEHOLDER_NAME.match(name):
            continue
        row["peer_or_focal"] = _soften_leadership(name, calculable=calculable)
        for key, label in (
            ("period_from", "opening period"),
            ("period_to", "closing period"),
            ("share_from_pct", "opening share"),
            ("share_to_pct", "closing share"),
        ):
            if not str(row.get(key) or "").strip():
                row[key] = _info_request(label)
        delta = str(row.get("delta_pp") or "").strip()
        if not delta:
            row["delta_pp"] = _delta_pp(row.get("share_from_pct"), row.get("share_to_pct"))
        elif "pp" not in delta.lower():
            val = _num(delta)
            row["delta_pp"] = (
                f"{val:+.1f} pp {_COMPUTED}"
                if val is not None
                else _info_request("share delta in percentage points (pp)")
            )
        if not str(row.get("vs_market_growth") or "").strip():
            row["vs_market_growth"] = vs_growth
        if not str(row.get("acquisition_contribution") or "").strip():
            row["acquisition_contribution"] = acq
        if not str(row.get("organic_notes") or "").strip():
            row["organic_notes"] = organic
        row.setdefault("source", _DOC_CITE)
        cleaned_movement.append(row)
    if not cleaned_movement:
        cleaned_movement = _extract_share_movement(corpus, legacy=legacy)
    llm["share_movement"] = cleaned_movement[:6]

    # --- plan requirements -------------------------------------------------
    plan = llm.get("plan_requirements")
    if not isinstance(plan, dict):
        plan = _extract_plan_requirements(corpus)
    else:
        for key, label in (
            ("customers_per_month", "customers to win per month under the plan"),
            ("volume", "volume required by the plan"),
            ("capacity", "vehicles / capacity required to serve the plan"),
            ("sales_headcount", "sales headcount required to win the plan"),
            ("other_physical", "other physical requirements of the plan"),
        ):
            if not str(plan.get(key) or "").strip():
                plan[key] = _info_request(label)
        missing = [
            label
            for key, label in (
                ("customers_per_month", "customers to win per month"),
                ("volume", "volume required"),
                ("capacity", "vehicles / capacity required"),
                ("sales_headcount", "sales headcount required"),
            )
            if not _is_filled(plan.get(key))
        ]
        if not str(plan.get("gaps") or "").strip():
            plan["gaps"] = (
                _info_request(", ".join(missing))
                if missing
                else f"All four physical requirements are evidenced in the plan {_COMPUTED}"
            )
        plan.setdefault("source", _DOC_CITE)
    llm["plan_requirements"] = plan

    # --- funnel ------------------------------------------------------------
    cleaned_funnel: list[dict[str, Any]] = []
    for row in llm.get("funnel_economics") or []:
        if not isinstance(row, dict):
            continue
        channel = _clean(row.get("channel"), 60)
        if not channel:
            continue
        row["channel"] = channel
        for key, label in (
            ("leads", "lead volume for this channel"),
            ("conversion_rate", "lead-to-order conversion rate"),
            ("sales_cycle", "sales cycle length"),
            ("cac", "cost per acquisition (CAC)"),
            ("retention", "retention / repeat rate for this channel"),
        ):
            if not str(row.get(key) or "").strip():
                row[key] = _info_request(label)
        row.setdefault("source", _DOC_CITE)
        cleaned_funnel.append(row)
    if not cleaned_funnel:
        cleaned_funnel = _extract_funnel_economics(corpus)
    llm["funnel_economics"] = cleaned_funnel[:6]

    # --- attainable vs ambition -------------------------------------------
    attainable = llm.get("attainable_vs_ambition")
    if not isinstance(attainable, dict):
        attainable = _attainable_vs_ambition(
            corpus,
            funnel=cleaned_funnel,
            plan=plan,
            calculable=calculable,
        )
    else:
        for key, label in (
            ("bottom_up_attainable", "bottom-up attainable case built from funnel rates"),
            ("management_ambition", "management ambition with a date"),
            ("gap", "gap between attainable case and ambition (in pp and in customers/volume)"),
            ("what_must_change", "what would have to change to close the gap"),
        ):
            if not str(attainable.get(key) or "").strip():
                attainable[key] = _info_request(label)
        for key in ("bottom_up_attainable", "management_ambition", "gap", "what_must_change"):
            attainable[key] = _soften_leadership(attainable[key], calculable=calculable)
        attainable.setdefault("source", _DOC_CITE)
    llm["attainable_vs_ambition"] = attainable

    # --- legacy dual-write -------------------------------------------------
    heur_legacy = _legacy_fields(
        cleaned_movement,
        corpus,
        legacy,
        attainable=attainable,
        matched_share=matched,
    )
    trends: list[dict[str, Any]] = []
    for raw in llm.get("share_trends") or []:
        row = _coerce_trend_row(raw)
        if row:
            trends.append(row)
    llm["share_trends"] = trends[:8] or heur_legacy["share_trends"]
    for key in ("wins", "losses", "strategy_notes"):
        raw = llm.get(key)
        if isinstance(raw, list) and raw:
            llm[key] = [
                _soften_leadership(_clean(x, 220), calculable=calculable)
                for x in raw
                if isinstance(x, str) and x.strip()
            ][:5]
        else:
            llm[key] = heur_legacy[key]

    # --- verdicts / housekeeping ------------------------------------------
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        quality, reliance, rationale = _quality_reliance(
            calculable=calculable,
            share_stated=bool(_stated_share(corpus)),
            movement_count=sum(
                1 for r in cleaned_movement
                if isinstance(r, dict)
                and not str(r.get("peer_or_focal") or "").startswith("Information")
            ),
            funnel_count=sum(
                1 for r in cleaned_funnel
                if isinstance(r, dict)
                and not str(r.get("channel") or "").startswith("Information")
            ),
            plan_filled=any(
                _is_filled(plan.get(k))
                for k in ("customers_per_month", "volume", "capacity", "sales_headcount")
            ),
            attainable_filled=_is_filled(attainable.get("bottom_up_attainable"))
            and _is_filled(attainable.get("management_ambition")),
            split_complete=_movement_split_complete(cleaned_movement),
        )
        llm["quality_verdict"] = qv if qv in {"PASS", "REWORK"} else quality
        llm["reliance_verdict"] = (
            rv if rv in {"READY", "LIMITED", "BLOCKED"} else reliance
        )
        if not str(llm.get("quality_reliance_rationale") or "").strip():
            llm["quality_reliance_rationale"] = rationale
    else:
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
    if not calculable and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Share is not calculable on a matched numerator/denominator basis — "
            "unassessed, so reliance is limited. "
            + _clean(llm.get("quality_reliance_rationale"), 260)
        )

    for dead in ("recommendation", "confidence", "key_conditions", "investment_verdict"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_leadership(
        llm.get("insight_snapshot") or "", calculable=calculable
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = (
        not calculable
        and not llm["share_trends"]
        and not any(
            isinstance(r, dict)
            and not str(r.get("peer_or_focal") or "").startswith("Information")
            for r in cleaned_movement
        )
    )
    return llm


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


def build_market_share_strategy_spec(
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
    sector = vars_.get("sector")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_market_share_strategy_corpus(deal, idx)
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
        llm = _llm_market_share_strategy_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=sector,
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

    return _heuristic_market_share_strategy_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        sector=sector,
        geography=geography,
        legacy_spec=legacy_spec,
    )


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


def render_market_share_strategy_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    matched = spec.get("matched_share") if isinstance(spec.get("matched_share"), dict) else {}
    movement = (
        spec.get("share_movement") if isinstance(spec.get("share_movement"), list) else []
    )
    plan = (
        spec.get("plan_requirements")
        if isinstance(spec.get("plan_requirements"), dict)
        else {}
    )
    funnel = (
        spec.get("funnel_economics")
        if isinstance(spec.get("funnel_economics"), list)
        else []
    )
    attainable = (
        spec.get("attainable_vs_ambition")
        if isinstance(spec.get("attainable_vs_ambition"), dict)
        else {}
    )
    srcs = sources or spec.get("primary_sources") or spec.get("sources") or []
    calculable = bool(matched.get("calculable"))

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Matched Share (Numerator / Denominator)\n\n")
    parts.append(
        "Share is calculated **only** where the numerator (from the accounts) and the "
        "denominator (from the approved market perimeter) match on service, geography, "
        "unit and date. Where they cannot be matched, share is not calculable and the "
        "missing input is named.\n\n"
    )
    parts.append(_table(
        ["Item", "Value"],
        [
            ["Calculable", "Yes" if calculable else "No — share not calculable"],
            [
                "Share",
                _clean(matched.get("share_pct"), 40)
                if calculable and matched.get("share_pct")
                else "Not calculable — unassessed",
            ],
            ["Numerator (accounts)", _clean(matched.get("numerator"), 220)],
            [
                "Denominator (approved market perimeter)",
                _clean(matched.get("denominator"), 220),
            ],
            ["Service / segment", _clean(matched.get("service"), 80)],
            ["Geography", _clean(matched.get("geography"), 80)],
            ["Unit", _clean(matched.get("unit"), 80)],
            ["Date / period", _clean(matched.get("date_or_period"), 60)],
            ["Match notes", _clean(matched.get("match_notes"), 320)],
            ["Source", _clean(matched.get("source") or _NA, 60)],
        ],
    ))
    if not calculable:
        req = _clean(
            matched.get("information_request")
            or _info_request("matched numerator and denominator for the share calculation"),
            300,
        )
        parts.append(f"**{req}**\n\n")
        parts.append(
            "*Missing share is unassessed — it establishes neither leadership nor "
            "weakness.*\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 2. Share Movement Over Time\n\n")
    parts.append(
        "Movement is measured between two dated endpoints and held **separate** from "
        "market growth and from acquisitions. Deltas are stated in percentage points "
        "(pp), never in %.\n\n"
    )
    if movement:
        parts.append(_table(
            [
                "Company / Peer", "From", "To", "Share From", "Share To", "Δ (pp)",
                "vs Market Growth", "Acquisition Contribution", "Organic Notes", "Source",
            ],
            [
                [
                    _clean(r.get("peer_or_focal"), 50),
                    _clean(r.get("period_from"), 40),
                    _clean(r.get("period_to"), 40),
                    _clean(r.get("share_from_pct"), 40),
                    _clean(r.get("share_to_pct"), 40),
                    _clean(r.get("delta_pp"), 60),
                    _clean(r.get("vs_market_growth"), 90),
                    _clean(r.get("acquisition_contribution"), 90),
                    _clean(r.get("organic_notes"), 90),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in movement if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 3. Physical Requirements of the Plan\n\n")
    parts.append(
        "The growth plan translated into what must physically happen: customers to win "
        "per month, volume, vehicles / capacity to serve them, and sales headcount to "
        "win them.\n\n"
    )
    parts.append(_table(
        ["Requirement", "Value from the plan"],
        [
            ["Customers to win per month", _clean(plan.get("customers_per_month"), 200)],
            ["Volume", _clean(plan.get("volume"), 200)],
            ["Vehicles / capacity", _clean(plan.get("capacity"), 200)],
            ["Sales headcount", _clean(plan.get("sales_headcount"), 200)],
            ["Other physical requirements", _clean(plan.get("other_physical"), 200)],
            ["Gaps", _clean(plan.get("gaps"), 240)],
            ["Source", _clean(plan.get("source") or _NA, 60)],
        ],
    ))
    parts.append("---\n\n")

    parts.append("## 4. Funnel Economics\n\n")
    parts.append(
        "Read only where CRM / pipeline data exist: leads, conversion, sales cycle, "
        "cost per acquisition and retention by channel. Absent CRM data, the rates are "
        "requested rather than assumed.\n\n"
    )
    if funnel:
        parts.append(_table(
            ["Channel", "Leads", "Conversion", "Sales Cycle", "CAC", "Retention", "Source"],
            [
                [
                    _clean(r.get("channel"), 60),
                    _clean(r.get("leads"), 70),
                    _clean(r.get("conversion_rate"), 50),
                    _clean(r.get("sales_cycle"), 50),
                    _clean(r.get("cac"), 60),
                    _clean(r.get("retention"), 50),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in funnel if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Bottom-Up Attainable vs Management Ambition\n\n")
    parts.append(
        "The attainable case is built bottom-up from funnel rates and serving capacity, "
        "then set beside management ambition. The gap and what would have to change to "
        "close it are stated explicitly.\n\n"
    )
    parts.append(_table(
        ["Basis", "Statement"],
        [
            ["Bottom-up attainable", _clean(attainable.get("bottom_up_attainable"), 300)],
            ["Management ambition", _clean(attainable.get("management_ambition"), 300)],
            ["Gap", _clean(attainable.get("gap"), 300)],
            ["What must change", _clean(attainable.get("what_must_change"), 300)],
            ["Source", _clean(attainable.get("source") or _NA, 60)],
        ],
    ))
    parts.append(
        "*This section does not recommend invest or pass. Where the numerator and "
        "denominator cannot be matched on service, geography, unit and date, share is "
        "not calculable and is therefore unassessed — it establishes neither leadership "
        "nor weakness. Share movement must be separated from market growth and from "
        "acquisitions before any conclusion is drawn.*\n\n"
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
                    320,
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
        f"can diligence rest on this share and plan arithmetic?\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(list(srcs)[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
