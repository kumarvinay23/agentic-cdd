"""Compose DiligenceIQ Buying Behavior — purchase maps & sales assumptions (prompt book).

Maps how each customer type decides, how long it takes and what makes them
switch — inputs that decide whether a growth plan's sales assumptions are
realistic. Per-segment purchase maps; CRM sales-cycle median/range by segment;
switching triggers from wins/losses (say vs did); seasonality measured not
asserted; interview claims require sample/dates/method or labelled anecdotal.

No invest/pass. No company allowlists. Preserves legacy Concentration Risk
Analysis shape (concentration_flags / channel_mix / buying_metrics /
behavior_notes / segment_hhi).
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _pick_sentences,
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

_DOCUMENT_TITLE = "Concentration Risk Analysis"
_DD_CODE = "DD-09"

_ANECDOTAL_RULE = (
    "Interview-based claims carry sample size, dates and method, "
    "or they are labelled **anecdotal**."
)
_SEASONALITY_RULE = (
    "Seasonality is measured from monthly records; if the pattern is not in "
    "the data, it is **not asserted**."
)
_CYCLE_RULE = (
    "Sales-cycle length is measured by segment from CRM timestamps — "
    "one cycle length is **not** assigned to all customers."
)
_SAY_VS_DID = (
    "What customers **say** is distinguished from what they **did** "
    "(bid outcomes / win-loss)."
)

_SEGMENT_RE = re.compile(
    r"(?i)\b("
    r"Fleet(?:\s+Operator)?|Retail(?:\s+(?:Customer|Buyer))?|"
    r"B2B|B2C|Enterprise|SME|Commercial|Institutional|"
    r"Individual(?:\s+Buyer)?|Consumer|Corporate|"
    r"[A-Z][A-Za-z0-9 &/-]{2,40}?\s+segment"
    r")\b"
)
_CYCLE_RE = re.compile(
    r"(?i)(?:sales\s+cycle|time[- ]to[- ]purchase|purchase\s+cycle|"
    r"days?\s+to\s+(?:close|purchase|convert)|cycle\s+length)"
    r"[^.%]{0,40}?"
    r"(?:median\s*)?(\d+(?:\.\d+)?)\s*(?:[-–to]+\s*(\d+(?:\.\d+)?))?\s*(days?|weeks?|months?)?"
)
_MEDIAN_CYCLE_RE = re.compile(
    r"(?i)(?:median|p50)\s+(?:sales\s+)?cycle[^.\d]{0,30}?(\d+(?:\.\d+)?)\s*(days?|weeks?|months?)?"
)
_RANGE_CYCLE_RE = re.compile(
    r"(?i)(?:range|from|between)\s+(\d+(?:\.\d+)?)\s*[-–to]+\s*(\d+(?:\.\d+)?)\s*(days?|weeks?|months?)"
)
_TTP_RE = re.compile(
    r"(?i)(?:time\s+to\s+purchase|TTP)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(days?|weeks?)?"
)
_ONLINE_RE = re.compile(
    r"(?i)online\s+(?:sales|mix|share|channel)[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_EMI_RE = re.compile(
    r"(?i)(?:EMI|financed)\s+(?:purchase|share|mix)?[^.%]{0,30}?(\d+(?:\.\d+)?)\s*%"
)
_CAC_RE = re.compile(
    r"(?i)(?:CAC|customer\s+acquisition\s+cost)\s*[:=]?\s*"
    r"(?:INR|Rs\.?|₹)?\s*([\d,]+(?:\.\d+)?)"
)
_FLEET_REV_RE = re.compile(
    r"(?i)Fleet\s+(?:segment\s+)?(?:\()?(\d+(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:revenue|mix)?"
)
_HHI_RE = re.compile(r"(?i)\b(?:segment\s+)?HHI\s*[:=]?\s*(\d+(?:\.\d+)?)")
_WIN_LOSS_RE = re.compile(
    r"(?i)\b(win(?:ning)?|loss|lost\s+(?:to|deal)|bid\s+outcome|win[- ]loss)\b"
)
_PROCUREMENT_RE = re.compile(
    r"(?i)\b(tender|RFP|RFQ|framework\s+agreement|direct\s+(?:buy|purchase)|"
    r"purchase\s+order|procurement|negotiated\s+contract)\b"
)
_SEASON_CUE = re.compile(
    r"(?i)\b(seasonal(?:ity)?|monthly\s+(?:signup|sign-up|cancellation|volume)|"
    r"peak\s+(?:month|quarter)|festive|monsoon|Q[1-4]\s+spike)\b"
)
_MONTHLY_SERIES_RE = re.compile(
    r"(?i)(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*"
    r"(?:20\d{2})?\s*[:=]?\s*([\d,]+)"
)
_INTERVIEW_CUE = re.compile(
    r"(?i)\b(interview(?:ed|s)?|focus\s+group|customer\s+call|"
    r"management\s+said|told\s+us|anecdotal)\b"
)
_SAMPLE_RE = re.compile(
    r"(?i)(?:n\s*=|sample\s+size|interviewed)\s*[:=]?\s*([\d,]{1,})"
)
_DATE_RE = re.compile(
    r"(?i)(?:Q[1-4]\s+)?(?:FY|CY)?\s?20\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2}"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)

_DEFAULT_SEGMENTS = ("Retail / B2C", "Fleet / B2B")


def _info_request(label: str) -> str:
    return f"Information request: {label}"


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
    out = _INVEST_LANG.sub("buying evidence only — no deal verdict expressed", raw)
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


def _label_anecdotal(claim: str, *, corpus: str = "") -> tuple[str, bool]:
    """Return (labelled claim, is_anecdotal)."""
    text = str(claim or "").strip()
    if not text:
        return "", False
    if not _INTERVIEW_CUE.search(text) and not _INTERVIEW_CUE.search(corpus[:2000]):
        return text, False
    has_sample = bool(_SAMPLE_RE.search(text) or _SAMPLE_RE.search(corpus[:4000]))
    has_date = bool(_DATE_RE.search(text) or _DATE_RE.search(corpus[:4000]))
    has_method = bool(re.search(
        r"(?i)\b(structured\s+interview|semi[- ]structured|survey|CRM|win[- ]loss\s+note)\b",
        text + " " + corpus[:2000],
    ))
    if has_sample and has_date and has_method:
        return text, False
    if re.search(r"(?i)\banecdotal\b", text):
        return text, True
    return f"{text} [anecdotal — sample/dates/method not evidenced]", True


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_buying_behavior_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "customer": 0,
        "market_competition": 1,
        "deal_strategy": 2,
        "operations": 3,
        "financial": 4,
    }
    needles = (
        "commercial", "customer", "sales", "crm", "win", "loss", "fleet",
        "retail", "channel", "competition", "pricing", "procurement",
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


def _detect_segments(corpus: str) -> list[str]:
    text = _prose(corpus)
    found: list[str] = []
    seen: set[str] = set()
    for m in _SEGMENT_RE.finditer(text):
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        raw = re.sub(r"(?i)\s+segment$", "", raw).strip()
        key = raw.lower()
        if key in seen or len(raw) < 3:
            continue
        # Normalise common aliases
        if "fleet" in key or key == "b2b":
            label = "Fleet / B2B"
        elif "retail" in key or key in {"b2c", "consumer", "individual", "individual buyer"}:
            label = "Retail / B2C"
        else:
            label = raw[:60]
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        found.append(label)
        if len(found) >= 6:
            break
    if not found:
        # Soft defaults only as information-request scaffolds when corpus mentions buying
        if re.search(r"(?i)\b(purchase|sales\s+cycle|channel|buyer|procurement)\b", text):
            return list(_DEFAULT_SEGMENTS)
    return found


def _extract_purchase_maps(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    segments = _detect_segments(corpus)
    maps: list[dict[str, str]] = []

    decision_m = re.search(
        r"(?i)(?:decision[- ]maker|decides?|buyer\s+persona)[^.?]{0,100}",
        text,
    )
    budget_m = re.search(
        r"(?i)(?:budget\s+holder|pays?\s+for|funding\s+source|CFO|procurement\s+budget)[^.?]{0,80}",
        text,
    )
    approval_m = re.search(
        r"(?i)(?:approval|sign[- ]off|committee|levels?\s+of\s+approval)[^.?]{0,100}",
        text,
    )
    trigger_m = re.search(
        r"(?i)(?:purchase\s+trigger|trigger(?:s|ed)?\s+(?:a\s+)?purchase|"
        r"starts?\s+(?:a\s+)?(?:buy|purchase)|replacement\s+cycle)[^.?]{0,100}",
        text,
    )
    proc_hit = _PROCUREMENT_RE.search(text)
    procurement = _clean(proc_hit.group(0), 40) if proc_hit else _NA

    for seg in segments or list(_DEFAULT_SEGMENTS):
        # Prefer segment-local sentences
        seg_sents = [
            s for s in _sentences(text)
            if any(tok in s.lower() for tok in seg.lower().replace("/", " ").split())
        ]
        local = " ".join(seg_sents[:8]) if seg_sents else text

        dm = decision_m.group(0) if decision_m else None
        if not dm:
            dm_local = re.search(
                r"(?i)(?:decision[- ]maker|fleet\s+manager|owner|buyer)[^.?]{0,80}",
                local,
            )
            dm = dm_local.group(0) if dm_local else None

        maps.append({
            "segment": seg,
            "decision_maker": _clean(dm, 160) if dm else _info_request(f"decision-maker for {seg}"),
            "budget_holder": (
                _clean(budget_m.group(0), 120) if budget_m
                else _info_request(f"budget holder for {seg}")
            ),
            "approval_steps": (
                _clean(approval_m.group(0), 160) if approval_m
                else _info_request(f"approval steps for {seg}")
            ),
            "procurement_route": (
                procurement if procurement != _NA
                else _info_request(f"procurement route (tender/framework/direct) for {seg}")
            ),
            "purchase_trigger": (
                _clean(trigger_m.group(0), 160) if trigger_m
                else _info_request(f"purchase trigger for {seg}")
            ),
            "source": _DOC_CITE if (dm or budget_m or approval_m or proc_hit or trigger_m) else _NA,
        })
    return maps


def _extract_sales_cycles(corpus: str) -> list[dict[str, Any]]:
    text = _prose(corpus)
    segments = _detect_segments(corpus) or list(_DEFAULT_SEGMENTS)
    cycles: list[dict[str, Any]] = []

    median_m = _MEDIAN_CYCLE_RE.search(text) or _TTP_RE.search(text) or _CYCLE_RE.search(text)
    range_m = _RANGE_CYCLE_RE.search(text)
    global_median = None
    global_unit = "days"
    global_lo = None
    global_hi = None
    if median_m:
        global_median = _num(median_m.group(1))
        if median_m.lastindex and median_m.lastindex >= 2:
            unit = median_m.group(median_m.lastindex)
            if unit and re.search(r"(?i)day|week|month", unit):
                global_unit = unit.lower().rstrip("s") + "s"
    if range_m:
        global_lo = _num(range_m.group(1))
        global_hi = _num(range_m.group(2))
        if range_m.group(3):
            global_unit = range_m.group(3).lower().rstrip("s") + "s"

    # Per-segment mentions
    for seg in segments:
        seg_pat = re.escape(seg.split("/")[0].strip())
        local_m = re.search(
            rf"(?i){seg_pat}[^.%]{{0,80}}(?:sales\s+cycle|time[- ]to[- ]purchase|"
            rf"days?\s+to\s+(?:close|purchase))[^.%]{{0,40}}?"
            rf"(\d+(?:\.\d+)?)\s*(days?|weeks?|months?)?",
            text,
        )
        median = _num(local_m.group(1)) if local_m else None
        unit = (local_m.group(2) if local_m and local_m.lastindex >= 2 and local_m.group(2) else global_unit)
        if unit:
            unit = str(unit).lower().rstrip("s") + "s"
        assigned_global = False
        if median is None and global_median is not None and len(segments) == 1:
            median = global_median
            assigned_global = True
        # Never assign one global cycle to multiple segments without per-segment evidence
        if median is None and global_median is not None and len(segments) > 1:
            cycles.append({
                "segment": seg,
                "median": _info_request(f"CRM median sales cycle for {seg}"),
                "range_low": _NA,
                "range_high": _NA,
                "unit": unit or "days",
                "source": _NA,
                "notes": (
                    f"A single pack figure ({global_median:g} {unit}) must not be "
                    f"assigned to all segments. {_CYCLE_RULE}"
                ),
                "crm_evidenced": False,
            })
            continue

        lo = global_lo if assigned_global or local_m else (global_lo if len(segments) == 1 else None)
        hi = global_hi if assigned_global or local_m else (global_hi if len(segments) == 1 else None)
        if median is not None:
            cycles.append({
                "segment": seg,
                "median": f"{median:g} {unit}",
                "range_low": f"{lo:g}" if lo is not None else _info_request(f"cycle range low for {seg}"),
                "range_high": f"{hi:g}" if hi is not None else _info_request(f"cycle range high for {seg}"),
                "unit": unit,
                "source": _DOC_CITE,
                "notes": _CYCLE_RULE,
                "crm_evidenced": True,
            })
        else:
            cycles.append({
                "segment": seg,
                "median": _info_request(f"CRM median sales cycle for {seg}"),
                "range_low": _NA,
                "range_high": _NA,
                "unit": "days",
                "source": _NA,
                "notes": _CYCLE_RULE,
                "crm_evidenced": False,
            })
    return cycles


def _extract_switching(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    has_wl = bool(_WIN_LOSS_RE.search(text))
    say_sents = _pick_sentences(
        _sentences(text),
        keywords=("said", "stated", "claimed", "cited", "told", "interview", "prefer"),
        limit=4,
    )
    did_sents = _pick_sentences(
        _sentences(text),
        keywords=("won", "lost", "switched", "chose", "selected", "awarded", "bid"),
        limit=4,
    )
    criteria = _pick_sentences(
        _sentences(text),
        keywords=("criteria", "price", "range", "service", "feature", "switching", "trigger"),
        limit=5,
    )
    said_raw = [_clean(s, 200) for s in say_sents if s]
    did_raw = [_clean(s, 200) for s in did_sents if s]
    said: list[str] = []
    did: list[str] = []
    anecdotal_count = 0
    for s in said_raw:
        labelled, is_anec = _label_anecdotal(s, corpus=text)
        if labelled:
            said.append(labelled)
            if is_anec:
                anecdotal_count += 1
    for s in did_raw:
        labelled, is_anec = _label_anecdotal(s, corpus=text)
        if labelled:
            did.append(labelled)
            if is_anec:
                anecdotal_count += 1

    triggers = [_clean(s, 180) for s in criteria if re.search(r"(?i)switch|trigger|win|loss|chose", s)][:4]
    if not triggers and has_wl:
        triggers = [_clean(s, 180) for s in did_raw[:2]]

    return {
        "evidenced": bool(triggers or said or did or has_wl),
        "purchase_criteria": triggers or [_info_request("purchase criteria from bid outcomes / win-loss")],
        "switching_triggers": triggers or [_info_request("switching triggers from wins and losses")],
        "customers_say": said or [_info_request("stated preferences (with sample/dates/method)")],
        "customers_did": did or [_info_request("observed win/loss outcomes")],
        "say_vs_did_note": _SAY_VS_DID,
        "anecdotal_count": anecdotal_count,
        "source": _DOC_CITE if (triggers or said or did or has_wl) else _NA,
        "information_request": (
            "" if (triggers or did)
            else _info_request("win/loss notes and bid outcomes with switching triggers")
        ),
    }


def _extract_seasonality(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    has_cue = bool(_SEASON_CUE.search(text))
    monthly = list(_MONTHLY_SERIES_RE.finditer(text))
    measured = len(monthly) >= 3 or (
        has_cue and bool(re.search(r"(?i)monthly|signup|sign-up|cancellation|volume", text))
        and bool(re.search(r"\d", text))
    )
    # Require numeric monthly pattern — cues alone are not enough to assert
    if len(monthly) < 3 and not (
        has_cue and re.search(r"(?i)(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec).{0,20}\d", text)
    ):
        measured = False

    pattern = _NA
    if measured:
        pattern = _clean(
            next(
                (s for s in _sentences(text) if _SEASON_CUE.search(s) or _MONTHLY_SERIES_RE.search(s)),
                "Monthly series evidenced in packs.",
            ),
            280,
        )
        # Control note
        if not re.search(r"(?i)control(?:ling)?\s+for|exclud(?:e|ing)\s+acquisit|organic", text):
            pattern = (
                f"{pattern} Information request: confirm seasonality controls for "
                f"growth and acquisitions."
            )

    return {
        "measured": measured,
        "pattern": pattern if measured else (
            f"{_SEASONALITY_RULE} {_info_request('monthly signups, cancellations and volume series')}"
        ),
        "controls_for_growth_acq": (
            bool(re.search(r"(?i)control(?:ling)?\s+for|exclud(?:e|ing)\s+acquisit|organic", text))
            if measured else False
        ),
        "asserted_without_data": False,  # composer never asserts
        "source": _DOC_CITE if measured else _NA,
        "notes": _SEASONALITY_RULE,
    }


def _extract_implications(
    *,
    maps: list[dict],
    cycles: list[dict],
    switching: dict,
    seasonality: dict,
    metrics: dict[str, float],
) -> dict[str, str]:
    capacity = _info_request("sales capacity implications from cycle length and segment mix")
    conversion = _info_request("conversion assumptions by segment from CRM funnel")
    pricing = _info_request("pricing strategy implications from purchase criteria / switching")

    evidenced_cycles = [c for c in cycles if c.get("crm_evidenced")]
    if evidenced_cycles:
        bits = [f"{c['segment']}: median {c.get('median')}" for c in evidenced_cycles[:3]]
        capacity = (
            f"Sales capacity must reflect segment-specific cycles ({'; '.join(bits)}). "
            f"{_CYCLE_RULE} {_DOC_CITE}"
        )
    if switching.get("evidenced"):
        conversion = (
            f"Conversion and win-rate assumptions should reflect evidenced switching triggers "
            f"and the say-vs-did split. {_SAY_VS_DID} {_DOC_CITE}"
        )
    if metrics.get("cac_inr") is not None or metrics.get("online_sales_pct") is not None:
        parts = []
        if metrics.get("cac_inr") is not None:
            parts.append(f"CAC {_num(metrics['cac_inr']):g}")
        if metrics.get("online_sales_pct") is not None:
            parts.append(f"online mix {metrics['online_sales_pct']:g}%")
        pricing = (
            f"Pricing / channel strategy should reconcile with {' · '.join(parts)}. {_DOC_CITE}"
        )
    if not seasonality.get("measured"):
        capacity = f"{capacity} Seasonality not measured — do not bake an asserted seasonal ramp into the plan."

    return {
        "sales_capacity": _clean(capacity, 360),
        "conversion_assumptions": _clean(conversion, 360),
        "pricing_strategy": _clean(pricing, 360),
    }


def _extract_buying_metrics(corpus: str, legacy: dict[str, Any]) -> dict[str, float]:
    text = _prose(corpus)
    out: dict[str, float] = {}
    prior = legacy.get("buying_metrics") if isinstance(legacy.get("buying_metrics"), dict) else {}

    m = _ONLINE_RE.search(text)
    if m:
        out["online_sales_pct"] = float(m.group(1))
    m = _EMI_RE.search(text)
    if m:
        out["emi_purchase_pct"] = float(m.group(1))
    m = _CAC_RE.search(text)
    if m:
        val = _num(m.group(1))
        if val is not None:
            out["cac_inr"] = val
    m = _TTP_RE.search(text) or _CYCLE_RE.search(text)
    if m:
        val = _num(m.group(1))
        if val is not None:
            out["time_to_purchase_days"] = val
    m = _FLEET_REV_RE.search(text)
    if m:
        out["fleet_revenue_pct"] = float(m.group(1))

    for k, v in prior.items():
        if k not in out and _num(v) is not None:
            out[k] = float(_num(v))  # type: ignore[arg-type]
    return out


def _extract_segment_hhi(corpus: str, legacy: dict[str, Any]) -> float | None:
    m = _HHI_RE.search(corpus or "")
    if m:
        return _num(m.group(1))
    return _num(legacy.get("segment_hhi"))


def _extract_channel_mix(corpus: str, legacy: dict[str, Any]) -> list[str]:
    text = _prose(corpus)
    hits = _pick_sentences(
        _sentences(text),
        keywords=("online", "dealer", "experience center", "channel", "digital", "direct"),
        limit=5,
    )
    out = [_clean(s, 180) for s in hits if s][:4]
    if not out:
        for c in (legacy.get("channel_mix") or [])[:4]:
            if isinstance(c, str) and c.strip():
                out.append(_clean(c, 180))
    return out


def _extract_concentration_flags(
    corpus: str,
    legacy: dict[str, Any],
    *,
    metrics: dict[str, float],
    hhi: float | None,
) -> list[str]:
    flags: list[str] = []
    if metrics.get("fleet_revenue_pct") is not None and metrics["fleet_revenue_pct"] >= 30:
        flags.append(
            f"Fleet / B2B is {metrics['fleet_revenue_pct']:g}% of revenue — concentration flag."
        )
    if metrics.get("online_sales_pct") is not None:
        flags.append(f"Online sales mix {metrics['online_sales_pct']:g}%.")
    if hhi is not None and hhi >= 2500:
        flags.append(f"Segment HHI {hhi:g} — elevated concentration.")
    elif hhi is not None:
        flags.append(f"Segment HHI {hhi:g}.")
    for f in (legacy.get("concentration_flags") or [])[:4]:
        if isinstance(f, str) and f.strip() and f not in flags:
            flags.append(_clean(f, 200))
    # Corpus cues
    for s in _pick_sentences(
        _sentences(_prose(corpus)),
        keywords=("concentration", "dependen", "single segment", "top segment"),
        limit=3,
    ):
        line = _clean(s, 180)
        if line and line not in flags:
            flags.append(line)
    return flags[:6]


def _quality_reliance(
    *,
    maps: list[dict],
    cycles: list[dict],
    switching: dict,
    seasonality: dict,
    anecdotal_count: int,
) -> tuple[str, str, str]:
    map_filled = sum(
        1 for m in maps
        if any(_is_filled(m.get(k)) for k in (
            "decision_maker", "budget_holder", "approval_steps",
            "procurement_route", "purchase_trigger",
        ))
    )
    cycle_ok = sum(1 for c in cycles if c.get("crm_evidenced"))
    switch_ok = bool(switching.get("evidenced"))
    season_ok = bool(seasonality.get("measured"))

    if map_filled and cycle_ok and switch_ok:
        reliance = "READY" if season_ok and anecdotal_count == 0 else "LIMITED"
        rationale = (
            "Purchase maps and segment-level cycles evidenced; "
            + ("seasonality measured. " if season_ok else "seasonality not measured — not asserted. ")
            + (f"{anecdotal_count} anecdotal claim(s) labelled. " if anecdotal_count else "")
            + _ANECDOTAL_RULE
        )
        return "PASS", reliance, rationale
    if map_filled or cycle_ok or switch_ok:
        return (
            "PASS",
            "LIMITED",
            "Partial buying evidence — maps/cycles/switching incomplete; "
            f"{_SEASONALITY_RULE} {_ANECDOTAL_RULE}",
        )
    return (
        "PASS",
        "BLOCKED",
        "No per-segment purchase maps, CRM cycles or win/loss switching evidence was opened.",
    )


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_buying_behavior_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for note in (legacy.get("behavior_notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            extra += "\n" + note.strip()
    for flag in (legacy.get("concentration_flags") or [])[:4]:
        if isinstance(flag, str) and flag.strip():
            extra += "\n" + flag.strip()
    corpus_full = (corpus or "") + extra

    maps = _extract_purchase_maps(corpus_full)
    cycles = _extract_sales_cycles(corpus_full)
    switching = _extract_switching(corpus_full)
    seasonality = _extract_seasonality(corpus_full)
    metrics = _extract_buying_metrics(corpus_full, legacy)
    hhi = _extract_segment_hhi(corpus_full, legacy)
    channel = _extract_channel_mix(corpus_full, legacy)
    flags = _extract_concentration_flags(
        corpus_full, legacy, metrics=metrics, hhi=hhi,
    )
    implications = _extract_implications(
        maps=maps, cycles=cycles, switching=switching,
        seasonality=seasonality, metrics=metrics,
    )

    notes: list[str] = []
    notes.append(_CYCLE_RULE)
    notes.append(_SEASONALITY_RULE)
    notes.append(_ANECDOTAL_RULE)
    if switching.get("evidenced"):
        notes.append(_SAY_VS_DID)
    for n in (legacy.get("behavior_notes") or [])[:4]:
        if isinstance(n, str) and n.strip():
            labelled, _ = _label_anecdotal(n, corpus=corpus_full)
            if labelled and labelled not in notes:
                notes.append(labelled)

    quality, reliance, rationale = _quality_reliance(
        maps=maps,
        cycles=cycles,
        switching=switching,
        seasonality=seasonality,
        anecdotal_count=int(switching.get("anecdotal_count") or 0),
    )

    bits = [f"Buying Behavior for {company}:"]
    segs = [m.get("segment") for m in maps if m.get("segment")]
    if segs:
        bits.append(f"{len(segs)} segment map(s)")
    cycle_ok = sum(1 for c in cycles if c.get("crm_evidenced"))
    bits.append(f"{cycle_ok}/{len(cycles) or 0} segment cycle(s) CRM-evidenced")
    bits.append("switching " + ("evidenced" if switching.get("evidenced") else "thin"))
    bits.append("seasonality " + ("measured" if seasonality.get("measured") else "not asserted"))
    if metrics.get("time_to_purchase_days") is not None:
        bits.append(f"TTP {metrics['time_to_purchase_days']:g}d (not applied to all segments)")

    return {
        "insight_snapshot": _soften_invest("; ".join(bits)),
        "purchase_maps": maps,
        "sales_cycles": cycles,
        "switching": switching,
        "seasonality": seasonality,
        "implications": implications,
        # Legacy dual-write
        "concentration_flags": flags,
        "channel_mix": channel,
        "buying_metrics": metrics,
        "behavior_notes": notes[:8],
        "segment_hhi": hhi,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": (
            not any(_is_filled(m.get("decision_maker")) for m in maps)
            and not any(c.get("crm_evidenced") for c in cycles)
            and not switching.get("evidenced")
            and not metrics
        ),
    }


def _llm_buying_behavior_spec(
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
            "buying_behavior",
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
        "purchase_maps: [{segment, decision_maker, budget_holder, approval_steps, "
        "procurement_route, purchase_trigger, source}],\n"
        "sales_cycles: [{segment, median, range_low, range_high, unit, source, notes, crm_evidenced}],\n"
        "switching: {evidenced, purchase_criteria: [string], switching_triggers: [string], "
        "customers_say: [string], customers_did: [string], say_vs_did_note, anecdotal_count, "
        "source, information_request},\n"
        "seasonality: {measured, pattern, controls_for_growth_acq, asserted_without_data, source, notes},\n"
        "implications: {sales_capacity, conversion_assumptions, pricing_strategy},\n"
        "concentration_flags: [string], channel_mix: [string],\n"
        "buying_metrics: {online_sales_pct?, emi_purchase_pct?, cac_inr?, time_to_purchase_days?, "
        "fleet_revenue_pct?},\n"
        "behavior_notes: [string], segment_hhi (number|null),\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT assign one sales-cycle length to all segments. "
        "Do NOT assert seasonality without monthly data. "
        "Interview claims need sample/dates/method or label anecdotal. "
        "Distinguish what customers say from what they did. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
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
    heur = _heuristic_buying_behavior_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
    )

    maps = llm.get("purchase_maps") if isinstance(llm.get("purchase_maps"), list) else []
    cleaned_maps: list[dict[str, str]] = []
    for row in maps:
        if not isinstance(row, dict) or not row.get("segment"):
            continue
        cleaned_maps.append({
            "segment": _clean(row.get("segment"), 60),
            "decision_maker": _clean(row.get("decision_maker"), 160) or _NA,
            "budget_holder": _clean(row.get("budget_holder"), 120) or _NA,
            "approval_steps": _clean(row.get("approval_steps"), 160) or _NA,
            "procurement_route": _clean(row.get("procurement_route"), 80) or _NA,
            "purchase_trigger": _clean(row.get("purchase_trigger"), 160) or _NA,
            "source": _clean(row.get("source"), 60) or _DOC_CITE,
        })
    if not cleaned_maps:
        cleaned_maps = heur["purchase_maps"]
    llm["purchase_maps"] = cleaned_maps

    cycles = llm.get("sales_cycles") if isinstance(llm.get("sales_cycles"), list) else []
    cleaned_cycles: list[dict[str, Any]] = []
    for row in cycles:
        if not isinstance(row, dict) or not row.get("segment"):
            continue
        cleaned_cycles.append({
            "segment": _clean(row.get("segment"), 60),
            "median": _clean(row.get("median"), 80) or _NA,
            "range_low": _clean(row.get("range_low"), 40) or _NA,
            "range_high": _clean(row.get("range_high"), 40) or _NA,
            "unit": _clean(row.get("unit"), 20) or "days",
            "source": _clean(row.get("source"), 60) or _NA,
            "notes": _clean(row.get("notes"), 240) or _CYCLE_RULE,
            "crm_evidenced": bool(row.get("crm_evidenced")),
        })
    # Guard: identical median across >1 segment without per-segment CRM → force info request
    if len(cleaned_cycles) > 1:
        medians = {str(c.get("median")) for c in cleaned_cycles if _is_filled(c.get("median"))}
        if len(medians) == 1 and all(c.get("crm_evidenced") for c in cleaned_cycles):
            # Ambiguous — prefer heuristic which already blocks global assign
            cleaned_cycles = heur["sales_cycles"]
    if not cleaned_cycles:
        cleaned_cycles = heur["sales_cycles"]
    llm["sales_cycles"] = cleaned_cycles

    switching = llm.get("switching") if isinstance(llm.get("switching"), dict) else {}
    if not switching:
        switching = heur["switching"]
    else:
        base = dict(heur["switching"])
        base.update({k: v for k, v in switching.items() if v is not None})
        # Relabel anecdotal
        for key in ("customers_say", "customers_did", "purchase_criteria", "switching_triggers"):
            items = base.get(key) if isinstance(base.get(key), list) else []
            relabelled: list[str] = []
            anec = 0
            for item in items:
                if not isinstance(item, str):
                    continue
                labelled, is_anec = _label_anecdotal(item, corpus=corpus)
                if labelled:
                    relabelled.append(labelled)
                    if is_anec:
                        anec += 1
            if relabelled:
                base[key] = relabelled
            if key == "customers_say":
                base["anecdotal_count"] = anec
        base["say_vs_did_note"] = _SAY_VS_DID
        switching = base
    llm["switching"] = switching

    seasonality = llm.get("seasonality") if isinstance(llm.get("seasonality"), dict) else {}
    if not seasonality:
        seasonality = heur["seasonality"]
    else:
        base = dict(heur["seasonality"])
        # Never allow LLM to assert without measured flag from heuristic or clear monthly data
        claimed = bool(seasonality.get("measured"))
        if claimed and not heur["seasonality"].get("measured"):
            seasonality = {
                **base,
                "measured": False,
                "asserted_without_data": False,
                "pattern": (
                    f"{_SEASONALITY_RULE} {_info_request('monthly signups, cancellations and volume')}"
                ),
                "notes": _SEASONALITY_RULE,
            }
        else:
            base.update({k: v for k, v in seasonality.items() if v is not None})
            base["asserted_without_data"] = False
            base["notes"] = _SEASONALITY_RULE
            seasonality = base
    llm["seasonality"] = seasonality

    implications = llm.get("implications") if isinstance(llm.get("implications"), dict) else {}
    if not implications:
        implications = heur["implications"]
    else:
        base = dict(heur["implications"])
        for k in ("sales_capacity", "conversion_assumptions", "pricing_strategy"):
            if implications.get(k):
                base[k] = _soften_invest(_clean(implications[k], 360))
        implications = base
    llm["implications"] = implications

    # Legacy dual-write — prefer LLM lists grounded, else heuristic; numbers from heuristic/LLM merge
    flags = llm.get("concentration_flags") if isinstance(llm.get("concentration_flags"), list) else []
    flags = [_soften_invest(_clean(f, 200)) for f in flags if isinstance(f, str) and f.strip()]
    if not flags:
        flags = heur["concentration_flags"]
    llm["concentration_flags"] = flags[:6]

    channel = llm.get("channel_mix") if isinstance(llm.get("channel_mix"), list) else []
    channel = [_clean(c, 180) for c in channel if isinstance(c, str) and c.strip()]
    if not channel:
        channel = heur["channel_mix"]
    llm["channel_mix"] = channel[:4]

    metrics_llm = llm.get("buying_metrics") if isinstance(llm.get("buying_metrics"), dict) else {}
    metrics = dict(heur.get("buying_metrics") or {})
    for k, v in metrics_llm.items():
        n = _num(v)
        if n is not None:
            metrics[k] = n
    llm["buying_metrics"] = metrics

    hhi = _num(llm.get("segment_hhi"))
    if hhi is None:
        hhi = heur.get("segment_hhi")
    llm["segment_hhi"] = hhi

    notes = llm.get("behavior_notes") if isinstance(llm.get("behavior_notes"), list) else []
    cleaned_notes: list[str] = []
    for n in notes:
        if not isinstance(n, str) or not n.strip():
            continue
        labelled, _ = _label_anecdotal(_soften_invest(_clean(n, 240)), corpus=corpus)
        if labelled:
            cleaned_notes.append(labelled)
    if not cleaned_notes:
        cleaned_notes = heur["behavior_notes"]
    # Ensure rules present
    for rule in (_CYCLE_RULE, _SEASONALITY_RULE, _ANECDOTAL_RULE):
        if not any(rule[:40].lower() in x.lower() for x in cleaned_notes):
            cleaned_notes.append(rule)
    llm["behavior_notes"] = cleaned_notes[:8]

    quality, reliance, rationale = _quality_reliance(
        maps=cleaned_maps,
        cycles=cleaned_cycles,
        switching=switching,
        seasonality=seasonality,
        anecdotal_count=int(switching.get("anecdotal_count") or 0),
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
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = (
        not any(_is_filled(m.get("decision_maker")) for m in cleaned_maps)
        and not any(c.get("crm_evidenced") for c in cleaned_cycles)
        and not switching.get("evidenced")
        and not metrics
    )
    return llm


def build_buying_behavior_spec(
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
        gathered_corpus, gathered_sources = gather_buying_behavior_corpus(deal, idx)
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
        llm = _llm_buying_behavior_spec(
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

    return _heuristic_buying_behavior_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )


def render_buying_behavior_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    maps = spec.get("purchase_maps") if isinstance(spec.get("purchase_maps"), list) else []
    cycles = spec.get("sales_cycles") if isinstance(spec.get("sales_cycles"), list) else []
    switching = spec.get("switching") if isinstance(spec.get("switching"), dict) else {}
    seasonality = spec.get("seasonality") if isinstance(spec.get("seasonality"), dict) else {}
    implications = spec.get("implications") if isinstance(spec.get("implications"), dict) else {}
    metrics = spec.get("buying_metrics") if isinstance(spec.get("buying_metrics"), dict) else {}
    flags = spec.get("concentration_flags") if isinstance(spec.get("concentration_flags"), list) else []
    channel = spec.get("channel_mix") if isinstance(spec.get("channel_mix"), list) else []
    notes = spec.get("behavior_notes") if isinstance(spec.get("behavior_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Purchase Maps (by Segment)\n\n")
    parts.append(
        "For each customer type in scope: decision-maker, budget holder, approval steps, "
        "procurement route (tender, framework, direct) and the trigger that starts a purchase. "
        "Maps are separate per segment.\n\n"
    )
    if maps:
        parts.append(_table(
            ["Segment", "Decision-maker", "Budget holder", "Approval steps",
             "Procurement", "Purchase trigger", "Source"],
            [
                [
                    _clean(r.get("segment"), 40),
                    _clean(r.get("decision_maker"), 100),
                    _clean(r.get("budget_holder"), 80),
                    _clean(r.get("approval_steps"), 100),
                    _clean(r.get("procurement_route"), 60),
                    _clean(r.get("purchase_trigger"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in maps if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"**{_info_request('per-segment purchase maps (decision-maker, budget, approvals, route, trigger)')}**\n\n"
        )
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Sales Cycle (by Segment)\n\n")
    parts.append(f"{_CYCLE_RULE} Median and range from CRM timestamps.\n\n")
    if cycles:
        parts.append(_table(
            ["Segment", "Median", "Range low", "Range high", "Unit", "CRM evidenced", "Source"],
            [
                [
                    _clean(r.get("segment"), 40),
                    _clean(r.get("median"), 60),
                    _clean(r.get("range_low"), 40),
                    _clean(r.get("range_high"), 40),
                    _clean(r.get("unit"), 20),
                    "Yes" if r.get("crm_evidenced") else "No",
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in cycles if isinstance(r, dict)
            ],
        ))
        for r in cycles:
            if isinstance(r, dict) and _is_filled(r.get("notes")) and not r.get("crm_evidenced"):
                parts.append(f"*{_clean(r.get('notes'), 280)}*\n\n")
                break
    else:
        parts.append(f"**{_info_request('CRM median and range sales cycle by segment')}**\n\n")
    if metrics.get("time_to_purchase_days") is not None:
        parts.append(
            f"Pack figure TTP/cycle {metrics['time_to_purchase_days']:g} days is retained in "
            f"buying_metrics but is **not** assigned to every segment without per-segment CRM. "
            f"{_COMPUTED}\n\n"
        )
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Purchase Criteria & Switching Triggers\n\n")
    parts.append(
        f"From bid outcomes, win/loss notes and interviews. {_SAY_VS_DID} {_ANECDOTAL_RULE}\n\n"
    )
    parts.append(_table(
        ["Item", "Evidence"],
        [
            ["Evidenced", "Yes" if switching.get("evidenced") else "No / thin"],
            [
                "Purchase criteria",
                "; ".join(_clean(x, 120) for x in (switching.get("purchase_criteria") or [])[:4] if isinstance(x, str))
                or _NA,
            ],
            [
                "Switching triggers",
                "; ".join(_clean(x, 120) for x in (switching.get("switching_triggers") or [])[:4] if isinstance(x, str))
                or _NA,
            ],
            [
                "Customers say",
                "; ".join(_clean(x, 120) for x in (switching.get("customers_say") or [])[:3] if isinstance(x, str))
                or _NA,
            ],
            [
                "Customers did",
                "; ".join(_clean(x, 120) for x in (switching.get("customers_did") or [])[:3] if isinstance(x, str))
                or _NA,
            ],
            ["Source", _clean(switching.get("source") or _NA, 60)],
        ],
    ))
    if _is_filled(switching.get("information_request")):
        parts.append(f"**{_clean(switching.get('information_request'), 300)}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Seasonality (Measured, Not Asserted)\n\n")
    parts.append(f"{_SEASONALITY_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            ["Measured from monthly records", "Yes" if seasonality.get("measured") else "No"],
            ["Pattern", _clean(seasonality.get("pattern"), 320)],
            [
                "Controls for growth / acquisitions",
                "Yes" if seasonality.get("controls_for_growth_acq") else "No / not evidenced",
            ],
            ["Asserted without data", "No — composer does not assert"],
            ["Source", _clean(seasonality.get("source") or _NA, 60)],
        ],
    ))
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Implications (Capacity · Conversion · Pricing)\n\n")
    parts.append(
        "What the maps, cycles and switching evidence imply for sales capacity, "
        "conversion assumptions and pricing strategy.\n\n"
    )
    parts.append(_table(
        ["Dimension", "Implication"],
        [
            ["Sales capacity", _clean(implications.get("sales_capacity"), 360)],
            ["Conversion assumptions", _clean(implications.get("conversion_assumptions"), 360)],
            ["Pricing strategy", _clean(implications.get("pricing_strategy"), 360)],
        ],
    ))
    if flags or channel or metrics or spec.get("segment_hhi") is not None:
        parts.append("### Legacy concentration / channel signals\n\n")
        if flags:
            for f in flags[:5]:
                if isinstance(f, str):
                    parts.append(f"- {_clean(f, 200)}\n")
            parts.append("\n")
        if channel:
            parts.append("**Channel mix:** " + "; ".join(_clean(c, 100) for c in channel[:4] if isinstance(c, str)) + "\n\n")
        if metrics:
            metric_bits = [f"{k}: {v:g}" for k, v in list(metrics.items())[:6] if v is not None]
            if metric_bits:
                parts.append("**Buying metrics:** " + " · ".join(metric_bits) + "\n\n")
        if spec.get("segment_hhi") is not None:
            parts.append(f"**Segment HHI:** {spec['segment_hhi']:g}\n\n")
    parts.append(
        "*This section does not recommend invest or pass. Seasonality is not asserted "
        "without monthly data. Interview claims without sample/dates/method are labelled anecdotal.*\n\n"
    )
    parts.append("---\n\n")

    # 6
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
                    360,
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
        f"can diligence rest on these buying maps and cycle measures?\n\n"
    )
    if notes:
        parts.append("### Behavior notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document maps how customers buy by segment and tests whether growth-plan "
        "sales assumptions are realistic. It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
