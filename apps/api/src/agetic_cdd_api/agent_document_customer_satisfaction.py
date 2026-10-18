"""Compose DiligenceIQ Customer Satisfaction — sentiment evidence quality (prompt book).

Assesses whether survey evidence is representative enough to rely on; uses operational
service records as harder evidence; links service failures to subsequent cancellations
as association (not causation) where data allow; treats public reviews as self-selected
signals; designs research when evidence is thin.

Never infer poor customer focus from an inaccessible survey file. Never quote a
satisfaction score another agent cannot trace. No invest/pass. No company allowlists.
Preserves legacy Onboarding Failure Analysis shape (nps / peer_nps /
service_satisfaction_pct / churn_drivers / satisfaction_notes).
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

_DOCUMENT_TITLE = "Onboarding Failure Analysis"
_DD_CODE = "DD-12"

_INACCESSIBLE_RULE = (
    "Absence of an accessible survey file does **not** imply poor customer focus — "
    "it is an information gap, not a finding about service quality."
)
_ASSOCIATION_RULE = (
    "Service failure vs subsequent cancellation is reported as an **association** "
    "unless the data support more."
)
_REVIEWS_RULE = (
    "Public reviews are a **self-selected signal**, not research."
)

_NPS_RE = re.compile(
    r"(?i)(?:Net Promoter Score\s*\(NPS\)|NPS Score|NPS)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"
)
_CSAT_RE = re.compile(
    r"(?i)(?:Service Satisfaction|CSAT|Customer Satisfaction)\s*(?:\([^)]*\))?\s*[:=]?\s*"
    r"(\d+(?:\.\d+)?)\s*%"
)
_PEER_NPS_RE = re.compile(
    r"(?i)([A-Z][A-Za-z0-9 &().-]{2,40}?)\s*(?:NPS|Net Promoter)\s*[:=]?\s*(-?\d+(?:\.\d+)?)"
)
_RESPONSE_RATE_RE = re.compile(
    r"(?i)response\s+rate\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%"
)
_SAMPLE_SIZE_RE = re.compile(
    r"(?i)(?:sample\s+size|n\s*=|surveyed)\s*[:=]?\s*([\d,]{2,})"
)
_SURVEY_DATE_RE = re.compile(
    r"(?i)(?:survey(?:ed)?|fieldwork|interview(?:ed)?)\s+(?:in\s+|dated?\s+|as\s+of\s+)?"
    r"((?:Q[1-4]\s+)?(?:FY|CY)?\s?20\d{2}(?:[–\-]\d{2})?|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20\d{2})"
)
_COMPLAINT_RE = re.compile(
    r"(?i)(complaints?|tickets?|service\s+requests?)\s*[:=]?\s*([\d,]+(?:\.\d+)?)\b"
)
_RESOLUTION_RE = re.compile(
    r"(?i)(?:resolution|response)\s+time[s]?\s*[:=]?\s*([\d.]+)\s*(days?|hours?|hrs?)"
)
_MISSED_RE = re.compile(
    r"(?i)(missed|late|delayed)\s+(?:service|collections?|deliver(?:y|ies)|sla)[^.%]{0,40}?"
    r"(\d+(?:\.\d+)?)\s*%?"
)
_DEFECT_RE = re.compile(
    r"(?i)(defect|quality\s+failure|contamination|warranty\s+claim)[^.%]{0,40}?"
    r"([\d,]+(?:\.\d+)?)\s*%?"
)
_CHURN_DRIVER_RE = re.compile(
    r"(?i)"
    r"(Service Delay(?:\s*&\s*Unresolved Complaints)?|"
    r"Software Bugs\s*/\s*Feature Gaps(?:\s*\([^)]*\))?|"
    r"Battery Performance Below Expectations|"
    r"Competitive Product Launch(?:\s*\([^)]*\))?|"
    r"Spare Parts Unavailability|"
    r"Price Increase\s*/\s*Subsidy Reduction|"
    r"Lifestyle\s*/\s*Need Change|"
    r"[A-Z][A-Za-z0-9 /&()-]{4,60}?)"
    r"\s+(\d+(?:\.\d+)?)%\s+(Critical|High|Medium|Low)\b"
)
_ASSOC_CUE = re.compile(
    r"(?i)\b(churn|cancell(?:ed|ation)|attrit(?:ion|ed)|lapsed|"
    r"subsequent(?:ly)?\s+(?:churn|cancel)|service\s+failure\s+(?:led|drove|preceded))\b"
)
_REVIEW_CUE = re.compile(
    r"(?i)\b(app\s+store|google\s+play|google\s+reviews?|trustpilot|"
    r"glassdoor|public\s+reviews?|online\s+reviews?|star\s+rating)\b"
)
_INACCESSIBLE_CUE = re.compile(
    r"(?i)\b(survey\s+(?:file\s+)?(?:missing|inaccessible|not\s+(?:opened|available|provided))|"
    r"could\s+not\s+(?:open|access)\s+(?:the\s+)?survey|"
    r"survey\s+(?:workbook|pack)\s+(?:absent|unavailable))\b"
)
_BIAS_CUE = re.compile(
    r"(?i)\b(selection\s+bias|self[- ]selected|non[- ]response|survivorship|"
    r"promoter[- ]only|voluntary\s+respondents?)\b"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)


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
    out = _INVEST_LANG.sub("sentiment evidence only — no deal verdict expressed", raw)
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


def _score_is_traceable(
    score: Any,
    *,
    corpus: str = "",
    definition: str = "",
    source: str = "",
) -> tuple[bool, str]:
    """A score is quoteable only when numeric and tied to a source or definition."""
    val = _num(score)
    if val is None:
        return False, "No numeric score evidenced."
    has_def = _is_filled(definition)
    has_src = bool(source and source not in {_NA, ""}) or bool(re.search(r"\(DOC:", str(source)))
    in_corpus = bool(corpus) and (
        re.search(rf"(?i)\b{re.escape(str(int(val)) if val == int(val) else val)}\b", corpus) is not None
    )
    if has_def or has_src or in_corpus:
        return True, "Score tied to pack evidence."
    return False, "Score not traceable to a defining source — do not quote without a source locator."


def _association_only(notes: str = "", *, causation_claimed: bool = False) -> bool:
    if causation_claimed and re.search(r"(?i)\b(caused|causal|drove|led\s+directly)\b", notes or ""):
        # Still force association unless explicit controlled study language exists
        if re.search(r"(?i)\b(controlled|regression|causal\s+model|instrumental)\b", notes or ""):
            return False
    return True


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_customer_satisfaction_corpus(
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
        "nps", "csat", "survey", "satisfaction", "commercial", "churn",
        "complaint", "competition", "retention", "service", "quality",
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


def _extract_nps(corpus: str) -> float | None:
    m = _NPS_RE.search(corpus or "")
    return _num(m.group(1)) if m else None


def _extract_csat(corpus: str) -> float | None:
    m = _CSAT_RE.search(corpus or "")
    return _num(m.group(1)) if m else None


def _extract_peer_nps(corpus: str, *, focal: float | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for m in _PEER_NPS_RE.finditer(corpus or ""):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" :|-")
        if len(name) < 3 or name.lower() in {"nps", "net promoter", "score"}:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        val = _num(m.group(2))
        if val is None:
            continue
        if focal is not None and abs(val - focal) < 0.01 and "target" in key:
            continue
        out.append(f"{name}: NPS {val:g}")
        if len(out) >= 6:
            break
    return out


def _extract_churn_drivers(corpus: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for m in _CHURN_DRIVER_RE.finditer(corpus or ""):
        driver = re.sub(r"\s+", " ", m.group(1)).strip()
        key = driver.lower()
        if key in seen or len(driver) < 4:
            continue
        seen.add(key)
        out.append({
            "driver": driver[:120],
            "contribution_pct": _num(m.group(2)),
            "severity": m.group(3).title(),
        })
        if len(out) >= 8:
            break
    return out


def _extract_survey_assessment(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    inaccessible = bool(_INACCESSIBLE_CUE.search(text))
    date_m = _SURVEY_DATE_RE.search(text)
    sample_m = _SAMPLE_SIZE_RE.search(text)
    rate_m = _RESPONSE_RATE_RE.search(text)
    bias = ""
    if _BIAS_CUE.search(text):
        hit = _BIAS_CUE.search(text)
        bias = hit.group(0) if hit else "selection bias noted"
    has_survey_lang = bool(re.search(r"(?i)\b(survey|CSAT|NPS\s+study|respondent)\b", text))
    present = has_survey_lang and not inaccessible
    score_def = _NA
    if re.search(r"(?i)promoters?\s*[-–]\s*detractors?|valid\s+responses?|0[-–]10\s+scale", text):
        score_def = (
            "Scores calculated from valid responses on the stated scale "
            f"(promoters − detractors / valid respondents) {_DOC_CITE}"
        )
    elif present:
        score_def = _info_request("score definition and valid-response rule for the survey")

    pop = _NA
    pop_m = re.search(
        r"(?i)(?:survey(?:ed)?|target(?:ed)?)\s+(?:population|customers?|users?|respondents?)"
        r"[^.?]{0,80}",
        text,
    )
    if pop_m:
        pop = _clean(pop_m.group(0), 160)

    wording = _NA
    if re.search(r"(?i)question\s+wording|asked\s+respondents|Likert|0[-–]10", text):
        wording = _clean(
            next(
                (s for s in _sentences(text) if re.search(r"(?i)question|asked|Likert|0[-–]10", s)),
                _NA,
            ),
            220,
        )

    segment_mix = _NA
    if re.search(r"(?i)segment\s+mix|by\s+segment|respondent\s+mix", text):
        segment_mix = _clean(
            next(
                (s for s in _sentences(text) if re.search(r"(?i)segment|mix|respondent", s)),
                _NA,
            ),
            220,
        )

    info = ""
    if inaccessible:
        info = _info_request("accessible survey file with date, population, sample and response rate")
    elif present and (not date_m or not sample_m or not rate_m):
        missing = []
        if not date_m:
            missing.append("date")
        if not sample_m:
            missing.append("sample size")
        if not rate_m:
            missing.append("response rate")
        info = _info_request("survey " + ", ".join(missing))

    return {
        "present": present,
        "date": _clean(date_m.group(1), 40) if date_m else _NA,
        "target_population": pop,
        "sample_size": sample_m.group(1).replace(",", "") if sample_m else _NA,
        "response_rate": f"{rate_m.group(1)}%" if rate_m else _NA,
        "segment_mix": segment_mix,
        "question_wording": wording,
        "selection_bias": bias or (
            _info_request("selection / non-response bias assessment") if present else _NA
        ),
        "score_definition": score_def,
        "scores_from_valid_only": (
            True
            if (
                "valid" in score_def.lower()
                and "request" not in score_def.lower()
                and score_def != _NA
            )
            else _info_request("confirm scores use valid responses only")
        ),
        "inaccessible_file_note": _INACCESSIBLE_RULE if inaccessible else "",
        "information_request": info,
        "source": _DOC_CITE if present or inaccessible else _NA,
    }


def _extract_operational_signals(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    out: list[dict[str, str]] = []

    def _add(signal_type: str, measure: str, value: str, trend: str = _NA) -> None:
        if not value or value == _NA:
            return
        out.append({
            "signal_type": signal_type,
            "measure": measure,
            "value": value,
            "trend": trend,
            "source": _DOC_CITE,
        })

    for m in _COMPLAINT_RE.finditer(text):
        _add("complaint", m.group(1), m.group(2))
        if len(out) >= 6:
            break
    for m in _RESOLUTION_RE.finditer(text):
        _add("resolution_time", "resolution/response time", f"{m.group(1)} {m.group(2)}")
        if len(out) >= 8:
            break
    for m in _MISSED_RE.finditer(text):
        _add("missed_service", m.group(1) + " service", m.group(2))
        if len(out) >= 10:
            break
    for m in _DEFECT_RE.finditer(text):
        _add("quality_failure", m.group(1), m.group(2))
        if len(out) >= 12:
            break

    # Trend sentences
    for s in _pick_sentences(
        _sentences(text),
        keywords=("trend", "improved", "worsened", "increased", "decreased",
                  "complaint", "resolution", "service", "defect", "quality"),
        limit=3,
    ):
        if any(k in s.lower() for k in ("complaint", "resolution", "service", "defect", "quality")):
            out.append({
                "signal_type": "other",
                "measure": "trend note",
                "value": _clean(s, 180),
                "trend": _clean(s, 120),
                "source": _DOC_CITE,
            })
            break
    return out[:8]


def _extract_churn_association(corpus: str) -> dict[str, Any]:
    text = _prose(corpus)
    has_service = bool(re.search(
        r"(?i)\b(service\s+(?:delay|failure|issue)|complaint|unresolved|defect|quality\s+failure)\b",
        text,
    ))
    has_churn = bool(_ASSOC_CUE.search(text))
    comparable = has_service and has_churn
    notes = _NA
    if comparable:
        notes = _clean(
            next(
                (
                    s for s in _sentences(text)
                    if re.search(r"(?i)churn|cancel", s)
                    and re.search(r"(?i)service|complaint|defect|quality", s)
                ),
                "Service issues and subsequent cancellations appear in the same packs.",
            ),
            320,
        )
        notes = f"{notes} {_ASSOCIATION_RULE}"
    return {
        "comparable": comparable,
        "association_only": True,
        "service_failure": (
            _clean(
                next(
                    (s for s in _sentences(text) if re.search(r"(?i)service|complaint|defect", s)),
                    _NA,
                ),
                200,
            )
            if has_service else _NA
        ),
        "subsequent_cancellation": (
            _clean(
                next(
                    (s for s in _sentences(text) if re.search(r"(?i)churn|cancel|attrit|lapse", s)),
                    _NA,
                ),
                200,
            )
            if has_churn else _NA
        ),
        "notes": notes if comparable else (
            _info_request("matched service-failure and subsequent-cancellation records")
        ),
        "source": _DOC_CITE if comparable else _NA,
        "information_request": (
            "" if comparable else _info_request(
                "customer-level link of service failures to subsequent cancellations"
            )
        ),
    }


def _extract_public_reviews(corpus: str) -> dict[str, str]:
    text = _prose(corpus)
    if _REVIEW_CUE.search(text):
        note = _clean(
            next(
                (s for s in _sentences(text) if _REVIEW_CUE.search(s)),
                "Public / app-store style reviews appear in the packs.",
            ),
            280,
        )
        return {
            "treated_as": "self_selected_signal",
            "notes": f"{note} {_REVIEWS_RULE}",
            "source": _DOC_CITE,
        }
    return {
        "treated_as": "self_selected_signal",
        "notes": (
            "No public-review corpus was opened. If used later, treat as a self-selected "
            "signal, not research."
        ),
        "source": _NA,
    }


def _extract_research_design(
    *,
    survey: dict[str, Any],
    ops: list[dict[str, str]],
    association: dict[str, Any],
) -> dict[str, Any]:
    thin = (
        not survey.get("present")
        and len(ops) < 2
        and not association.get("comparable")
    ) or bool(survey.get("inaccessible_file_note"))
    if not thin and survey.get("present") and (
        not _is_filled(survey.get("sample_size")) or not _is_filled(survey.get("response_rate"))
    ):
        thin = True
    if not thin:
        return {
            "needed": False,
            "population": _NA,
            "sample": _NA,
            "method": _NA,
            "questions": _NA,
            "timing": _NA,
            "rationale": "Sentiment / ops evidence is sufficient to assess without a new study.",
        }
    return {
        "needed": True,
        "population": "Active customers in the last 12 months, stratified by segment and tenure",
        "sample": "Powered for ±5 pp on CSAT / NPS at 95% confidence; report response rate",
        "method": "Blind outbound survey (email/SMS) plus operational ticket sample audit",
        "questions": (
            "0–10 recommend (NPS); overall satisfaction; service resolution; "
            "intent to renew/repurchase; open reason for dissatisfaction"
        ),
        "timing": "Field within 4–6 weeks of exclusivity; report before IC",
        "rationale": (
            "Current sentiment evidence is thin or survey design incomplete — "
            "commission designed research rather than relying on untraceable scores "
            "or inaccessible files."
        ),
    }


def _legacy_fields(
    *,
    nps: float | None,
    peer_nps: list[str],
    csat: float | None,
    drivers: list[dict[str, Any]],
    legacy: dict[str, Any],
    notes: list[str],
) -> dict[str, Any]:
    leg_nps = legacy.get("nps") if isinstance(legacy, dict) else None
    leg_csat = legacy.get("service_satisfaction_pct") if isinstance(legacy, dict) else None
    leg_peers = legacy.get("peer_nps") if isinstance(legacy, dict) else None
    leg_drivers = legacy.get("churn_drivers") if isinstance(legacy, dict) else None
    leg_notes = legacy.get("satisfaction_notes") if isinstance(legacy, dict) else None

    out_nps = nps if nps is not None else _num(leg_nps)
    out_csat = csat if csat is not None else _num(leg_csat)
    out_peers = peer_nps or ([p for p in (leg_peers or []) if isinstance(p, str)] if isinstance(leg_peers, list) else [])
    out_drivers = drivers or (
        [d for d in (leg_drivers or []) if isinstance(d, dict)] if isinstance(leg_drivers, list) else []
    )
    out_notes = notes[:]
    if isinstance(leg_notes, list):
        for n in leg_notes:
            if isinstance(n, str) and n.strip() and n not in out_notes:
                out_notes.append(n.strip()[:240])
    return {
        "nps": out_nps,
        "peer_nps": out_peers[:8],
        "service_satisfaction_pct": out_csat,
        "churn_drivers": out_drivers[:8],
        "satisfaction_notes": out_notes[:8],
    }


def _quality_reliance(
    *,
    survey: dict[str, Any],
    ops_count: int,
    association: dict[str, Any],
    nps_traceable: bool,
    csat_traceable: bool,
    research_needed: bool,
) -> tuple[str, str, str]:
    design_ok = (
        survey.get("present")
        and _is_filled(survey.get("date"))
        and _is_filled(survey.get("sample_size"))
        and _is_filled(survey.get("response_rate"))
    )
    has_score = nps_traceable or csat_traceable
    if design_ok and has_score and (ops_count >= 1 or association.get("comparable")):
        return (
            "PASS",
            "READY",
            "Survey design assessed and scores are traceable; operational and/or association "
            "evidence supports reliance.",
        )
    if has_score or ops_count or survey.get("present") or association.get("comparable"):
        gaps = []
        if not design_ok:
            gaps.append("survey design incomplete (date/sample/response rate)")
        if not has_score:
            gaps.append("no traceable NPS/CSAT")
        if not ops_count:
            gaps.append("few operational service measures")
        return (
            "PASS",
            "LIMITED",
            "Sentiment evidence is present but reliance is limited: "
            + "; ".join(gaps[:3])
            + ". "
            + (survey.get("inaccessible_file_note") or ""),
        )
    if research_needed:
        return (
            "PASS",
            "BLOCKED",
            "Sentiment evidence is thin — research is designed for the deal team to commission. "
            + _INACCESSIBLE_RULE,
        )
    return (
        "PASS",
        "BLOCKED",
        "No survey, operational service measures or association evidence was opened.",
    )


def _valid_responses_confirmed(survey: dict[str, Any]) -> bool:
    flag = survey.get("scores_from_valid_only")
    if flag is True:
        return True
    if isinstance(flag, str) and "valid" in flag.lower() and "request" not in flag.lower():
        return True
    score_def = str(survey.get("score_definition") or "").lower()
    return "valid" in score_def and "request" not in score_def


def _survey_evidence_qa(
    survey: dict[str, Any],
    *,
    association: dict[str, Any],
    reviews: dict[str, Any],
    insight: str = "",
    notes: list[str] | None = None,
) -> list[dict[str, str]]:
    """Explicit PASS/FAIL QA for survey evidence discipline."""
    rows: list[dict[str, str]] = []
    design_ok = (
        bool(survey.get("present"))
        and _is_filled(survey.get("date"))
        and _is_filled(survey.get("sample_size"))
        and _is_filled(survey.get("response_rate"))
    )
    rows.append({
        "check": "survey_metadata_complete",
        "status": "PASS" if design_ok else "FAIL",
        "finding": (
            "Survey date, sample size and response rate evidenced"
            if design_ok
            else _info_request("survey date, sample size and response rate")
        ),
        "action": (
            "Metadata supports representativeness assessment"
            if design_ok
            else "Do not treat headline NPS/CSAT as diligence-grade until metadata is complete"
        ),
    })

    valid_ok = _valid_responses_confirmed(survey)
    rows.append({
        "check": "scores_from_valid_responses_only",
        "status": "PASS" if valid_ok else "FAIL",
        "finding": (
            "Scores calculated from valid responses only"
            if valid_ok
            else _info_request("confirmation that NPS/CSAT use valid responses only")
        ),
        "action": (
            "Valid-response rule stated with score definition"
            if valid_ok
            else "Withhold or null NPS/CSAT until valid-response rule is confirmed"
        ),
    })

    inaccessible = bool(survey.get("inaccessible_file_note"))
    corpus_bits = " ".join(
        [
            str(insight or ""),
            " ".join(n for n in (notes or []) if isinstance(n, str)),
            str(survey.get("inaccessible_file_note") or ""),
        ]
    ).lower()
    poor_focus_inferred = (
        inaccessible
        and "poor" in corpus_bits
        and "focus" in corpus_bits
        and "information gap" not in corpus_bits
        and "does not imply" not in corpus_bits
        and "does **not** imply" not in corpus_bits
    )
    if inaccessible and not poor_focus_inferred:
        rows.append({
            "check": "no_poor_focus_from_missing_file",
            "status": "PASS",
            "finding": "Inaccessible survey treated as information gap, not poor customer focus",
            "action": _INACCESSIBLE_RULE,
        })
    elif poor_focus_inferred:
        rows.append({
            "check": "no_poor_focus_from_missing_file",
            "status": "FAIL",
            "finding": "Missing survey file was framed as poor customer focus",
            "action": "Rewrite as information gap — never infer poor focus from inaccessible file",
        })
    else:
        rows.append({
            "check": "no_poor_focus_from_missing_file",
            "status": "PASS",
            "finding": "No inaccessible-survey poor-focus inference detected",
            "action": "Keep inaccessible files as gaps only",
        })

    assoc_ok = bool(association.get("association_only", True))
    rows.append({
        "check": "association_not_causation",
        "status": "PASS" if assoc_ok else "FAIL",
        "finding": (
            "Service↔churn framed as association (not Stickiness causation)"
            if assoc_ok
            else "Causation claimed without support — soften to association"
        ),
        "action": _ASSOCIATION_RULE,
    })

    reviews_ok = str(reviews.get("treated_as") or "") == "self_selected_signal"
    rows.append({
        "check": "public_reviews_self_selected",
        "status": "PASS" if reviews_ok else "FAIL",
        "finding": (
            "Public reviews labelled self-selected signal"
            if reviews_ok
            else "Public reviews must not be treated as research"
        ),
        "action": _REVIEWS_RULE,
    })
    return rows


def _questions_from_sat_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    survey = (
        spec.get("survey_assessment")
        if isinstance(spec.get("survey_assessment"), dict)
        else {}
    )
    qa = (
        spec.get("survey_evidence_qa")
        if isinstance(spec.get("survey_evidence_qa"), list)
        else []
    )
    ops = (
        spec.get("operational_signals")
        if isinstance(spec.get("operational_signals"), list)
        else []
    )
    research = (
        spec.get("research_design")
        if isinstance(spec.get("research_design"), dict)
        else {}
    )
    assoc = (
        spec.get("churn_association")
        if isinstance(spec.get("churn_association"), dict)
        else {}
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if survey.get("inaccessible_file_note") or (
        not survey.get("present") and not ops and not assoc.get("comparable")
    ):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Provide an accessible customer survey pack "
                        "(or confirm none exists for the perimeter)"
                    ),
                    "required_records": (
                        "Survey file with date, population, sample, response rate and wording"
                    ),
                    "decision_effect": (
                        "Sentiment representativeness cannot be assessed; "
                        "missing file is a gap not poor focus"
                    ),
                    "priority": "mandatory_pre_decision",
                    "owner": "commercial diligence lead",
                    "timing": "before IC",
                    "closure_test": "Accessible survey OR written confirmation none exists",
                    "interim_treatment": _INACCESSIBLE_RULE,
                }
            )
        )

    if _qa_fail("survey_metadata_complete"):
        out.append(
            normalize_question(
                {
                    "question": "Complete survey metadata: date, sample size and response rate",
                    "required_records": "Survey methodology / fieldwork note",
                    "decision_effect": "Headline NPS/CSAT cannot be assessed for bias",
                    "priority": "mandatory_pre_decision",
                    "owner": "commercial diligence lead",
                    "timing": "before IC",
                    "closure_test": "survey_metadata_complete QA status PASS",
                    "interim_treatment": "LIMITED reliance on any quoted scores",
                }
            )
        )

    if _qa_fail("scores_from_valid_responses_only"):
        out.append(
            normalize_question(
                {
                    "question": "Confirm NPS/CSAT are calculated from valid responses only",
                    "required_records": "Score definition and valid-response rule",
                    "decision_effect": "Unvalidated scores must not be quoted across agents",
                    "priority": "mandatory_pre_decision",
                    "owner": "commercial diligence lead",
                    "timing": "before IC",
                    "closure_test": "scores_from_valid_responses_only QA status PASS",
                    "interim_treatment": "Null / withhold NPS and CSAT until confirmed",
                }
            )
        )

    if not ops:
        out.append(
            normalize_question(
                {
                    "question": (
                        "Provide operational service measures "
                        "(complaints, missed/late service, defects, resolution times)"
                    ),
                    "required_records": "Support / ops quality dashboard for the review period",
                    "decision_effect": "Harder evidence of service quality is missing",
                    "priority": "signing_condition",
                    "owner": "operations / commercial diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "≥1 operational signal with measure and value",
                    "interim_treatment": "Do not rest diligence on survey alone",
                }
            )
        )

    if not assoc.get("comparable"):
        out.append(
            normalize_question(
                {
                    "question": (
                        "Link service failures to subsequent cancellations "
                        "(association only — not Stickiness causation)"
                    ),
                    "required_records": "Churn cohort tagged with preceding service events",
                    "decision_effect": "Service↔churn link remains untested",
                    "priority": "signing_condition",
                    "owner": "commercial diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "churn_association.comparable = true; association_only = true",
                    "interim_treatment": "Association withheld; do not infer Stickiness causation",
                }
            )
        )

    if research.get("needed"):
        out.append(
            normalize_question(
                {
                    "question": "Commission the proposed research design (population, sample, method, timing)",
                    "required_records": "Approved research brief matching research_design fields",
                    "decision_effect": "Thin sentiment evidence stays unrepresentative until fielded",
                    "priority": "residual_uncertainty",
                    "owner": "commercial diligence lead",
                    "timing": "per deal timetable",
                    "closure_test": "Fieldwork complete or research_design.needed = false after new packs",
                    "interim_treatment": "BLOCKED / LIMITED reliance until study returns",
                }
            )
        )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for q in out:
        key = q.get("question", "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    if not unique:
        unique.append(
            normalize_question(
                {
                    "question": (
                        "No material customer-satisfaction inputs are missing "
                        "for the stated perimeter"
                    ),
                    "required_records": "N/A — survey, ops and association publishable",
                    "decision_effect": "None — satisfaction evidence publishable as shared basis",
                    "priority": "residual_uncertainty",
                    "owner": "commercial diligence lead",
                    "timing": "n/a",
                    "closure_test": "Re-run if survey file or ops period changes",
                    "interim_treatment": "None",
                }
            )
        )
    return unique[:12]


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_customer_satisfaction_spec(
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
    for note in (legacy.get("satisfaction_notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            extra += "\n" + note.strip()
    for peer in (legacy.get("peer_nps") or [])[:4]:
        if isinstance(peer, str) and peer.strip():
            extra += "\n" + peer.strip()
    corpus_full = (corpus or "") + extra

    survey = _extract_survey_assessment(corpus_full)
    nps = _extract_nps(corpus_full)
    csat = _extract_csat(corpus_full)
    if nps is None:
        nps = _num(legacy.get("nps"))
    if csat is None:
        csat = _num(legacy.get("service_satisfaction_pct"))
    peers = _extract_peer_nps(corpus_full, focal=nps)
    drivers = _extract_churn_drivers(corpus_full)
    ops = _extract_operational_signals(corpus_full)
    association = _extract_churn_association(corpus_full)
    association["related_agent"] = "customer_stickiness"
    association["association_only"] = True if association.get("association_only", True) else False
    if association.get("comparable"):
        association["association_only"] = True
        notes_a = str(association.get("notes") or "")
        if "stickiness" not in notes_a.lower():
            association["notes"] = (
                f"{_clean(notes_a, 280)} {_ASSOCIATION_RULE} "
                "Not Stickiness causation."
            ).strip()
    reviews = _extract_public_reviews(corpus_full)
    research = _extract_research_design(survey=survey, ops=ops, association=association)

    nps_ok, nps_note = _score_is_traceable(
        nps, corpus=corpus_full, definition=str(survey.get("score_definition") or ""), source=_DOC_CITE
    )
    csat_ok, csat_note = _score_is_traceable(
        csat, corpus=corpus_full, definition=str(survey.get("score_definition") or ""), source=_DOC_CITE
    )
    # Keep legacy numbers when present in packs/legacy, but flag traceability.
    if nps is not None and not nps_ok and legacy.get("nps") is not None:
        nps_ok, nps_note = True, "Score retained from prior extract with pack citation pending."
    if csat is not None and not csat_ok and legacy.get("service_satisfaction_pct") is not None:
        csat_ok, csat_note = True, "Score retained from prior extract with pack citation pending."

    valid_ok = _valid_responses_confirmed(survey)
    if not valid_ok:
        nps_ok = False
        csat_ok = False
        nps_note = "Withheld — valid-response rule not confirmed."
        csat_note = "Withheld — valid-response rule not confirmed."

    notes: list[str] = []
    if survey.get("inaccessible_file_note"):
        notes.append(survey["inaccessible_file_note"])
    if association.get("comparable"):
        notes.append(_ASSOCIATION_RULE)
    if reviews.get("treated_as") == "self_selected_signal" and _is_filled(reviews.get("notes")):
        notes.append(_REVIEWS_RULE)
    if research.get("needed"):
        notes.append("Research design proposed — sentiment evidence is thin.")

    legacy_out = _legacy_fields(
        nps=nps if nps_ok else nps,
        peer_nps=peers,
        csat=csat if csat_ok else csat,
        drivers=drivers,
        legacy=legacy,
        notes=notes,
    )
    # Untraceable / unvalidated scores are not quoted
    if nps is not None and not nps_ok:
        legacy_out["nps"] = None
    if csat is not None and not csat_ok:
        legacy_out["service_satisfaction_pct"] = None

    bits = [f"Customer Satisfaction for {company}:"]
    if legacy_out.get("nps") is not None:
        bits.append(f"NPS {legacy_out['nps']:g}" + (" (traceable)" if nps_ok else " (trace pending)"))
    if legacy_out.get("service_satisfaction_pct") is not None:
        bits.append(f"service satisfaction {legacy_out['service_satisfaction_pct']:g}%")
    bits.append(
        "survey design "
        + ("assessed" if survey.get("present") else "thin/missing")
    )
    bits.append(f"{len(ops)} operational signal(s)")
    if association.get("comparable"):
        bits.append("service↔churn association stated")
    if research.get("needed"):
        bits.append("research design proposed")
    insight = _soften_invest(" ".join(bits) + f" {_DOC_CITE}")

    survey_qa = _survey_evidence_qa(
        survey,
        association=association,
        reviews=reviews,
        insight=insight,
        notes=notes,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in survey_qa)

    quality, reliance, rationale = _quality_reliance(
        survey=survey,
        ops_count=len(ops),
        association=association,
        nps_traceable=nps_ok and legacy_out.get("nps") is not None,
        csat_traceable=csat_ok and legacy_out.get("service_satisfaction_pct") is not None,
        research_needed=bool(research.get("needed")),
    )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        rationale = (
            "Survey evidence QA has open FAILs — reliance limited. " + rationale
        )

    out = {
        "insight_snapshot": insight,
        "survey_assessment": survey,
        "nps": legacy_out["nps"],
        "peer_nps": legacy_out["peer_nps"],
        "service_satisfaction_pct": legacy_out["service_satisfaction_pct"],
        "churn_drivers": legacy_out["churn_drivers"],
        "satisfaction_notes": legacy_out["satisfaction_notes"],
        "operational_signals": ops,
        "churn_association": association,
        "public_reviews": reviews,
        "research_design": research,
        "survey_evidence_qa": survey_qa,
        "score_traceability": {
            "nps_traceable": bool(nps_ok and legacy_out.get("nps") is not None),
            "csat_traceable": bool(csat_ok and legacy_out.get("service_satisfaction_pct") is not None),
            "notes": f"NPS: {nps_note} CSAT: {csat_note}",
        },
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": (
            legacy_out.get("nps") is None
            and legacy_out.get("service_satisfaction_pct") is None
            and not legacy_out.get("churn_drivers")
            and not ops
        ),
    }
    out["questions"] = _questions_from_sat_gaps(out)
    return out


def _llm_customer_satisfaction_spec(
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
            "customer_satisfaction",
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
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "survey_assessment: {present, date, target_population, sample_size, response_rate, "
        "segment_mix, question_wording, selection_bias, score_definition, scores_from_valid_only, "
        "inaccessible_file_note, information_request, source},\n"
        "nps (number|null), peer_nps: [string], service_satisfaction_pct (number|null),\n"
        "churn_drivers: [{driver, contribution_pct, severity}],\n"
        "satisfaction_notes: [string],\n"
        "operational_signals: [{signal_type, measure, value, trend, source}],\n"
        "churn_association: {comparable, association_only, related_agent (customer_stickiness), "
        "service_failure, subsequent_cancellation, notes, source, information_request},\n"
        "public_reviews: {treated_as, notes, source} — treated_as must be self_selected_signal,\n"
        "research_design: {needed, population, sample, method, questions, timing, rationale},\n"
        "survey_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "survey_metadata_complete, scores_from_valid_responses_only, no_poor_focus_from_missing_file, "
        "association_not_causation, public_reviews_self_selected,\n"
        "questions: [{question, required_records, decision_effect, priority, "
        "owner, timing, closure_test, interim_treatment}],\n"
        "score_traceability: {nps_traceable, csat_traceable, notes},\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Never quote a satisfaction score another agent cannot trace. "
        "Never infer poor customer focus from an inaccessible survey file. "
        "Public reviews are self-selected signals, not research. "
        "Service failure vs churn is association unless causation is evidenced — "
        "not Stickiness causation. "
        "Include Questions for every material gap. "
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
    heur = _heuristic_customer_satisfaction_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
    )

    survey = llm.get("survey_assessment") if isinstance(llm.get("survey_assessment"), dict) else {}
    if not survey:
        survey = heur["survey_assessment"]
    else:
        base = dict(heur["survey_assessment"])
        for k, v in survey.items():
            if v is not None and str(v).strip():
                base[k] = v
        if base.get("inaccessible_file_note") or _INACCESSIBLE_CUE.search(corpus or ""):
            base["inaccessible_file_note"] = _INACCESSIBLE_RULE
        survey = base
    llm["survey_assessment"] = survey

    # Scores — prefer LLM then heuristic; enforce traceability + valid responses
    nps = _num(llm.get("nps"))
    if nps is None:
        nps = heur.get("nps")
    csat = _num(llm.get("service_satisfaction_pct"))
    if csat is None:
        csat = heur.get("service_satisfaction_pct")
    nps_ok, nps_note = _score_is_traceable(
        nps, corpus=corpus, definition=str(survey.get("score_definition") or ""), source=_DOC_CITE
    )
    csat_ok, csat_note = _score_is_traceable(
        csat, corpus=corpus, definition=str(survey.get("score_definition") or ""), source=_DOC_CITE
    )
    valid_ok = _valid_responses_confirmed(survey)
    if not valid_ok:
        nps_ok = False
        csat_ok = False
        nps_note = "Withheld — valid-response rule not confirmed."
        csat_note = "Withheld — valid-response rule not confirmed."
    if nps is not None and not nps_ok:
        nps = None
    if csat is not None and not csat_ok:
        csat = None
    llm["nps"] = nps
    llm["service_satisfaction_pct"] = csat

    peers = llm.get("peer_nps") if isinstance(llm.get("peer_nps"), list) else []
    peers = [p for p in peers if isinstance(p, str) and p.strip()] or heur.get("peer_nps") or []
    llm["peer_nps"] = peers[:8]

    drivers = llm.get("churn_drivers") if isinstance(llm.get("churn_drivers"), list) else []
    cleaned_drivers: list[dict[str, Any]] = []
    for row in drivers:
        if not isinstance(row, dict) or not row.get("driver"):
            continue
        cleaned_drivers.append({
            "driver": _clean(row.get("driver"), 120),
            "contribution_pct": _num(row.get("contribution_pct")),
            "severity": _clean(row.get("severity"), 20) or None,
        })
    if not cleaned_drivers:
        cleaned_drivers = heur.get("churn_drivers") or []
    llm["churn_drivers"] = cleaned_drivers[:8]

    notes = llm.get("satisfaction_notes") if isinstance(llm.get("satisfaction_notes"), list) else []
    notes = [_soften_invest(_clean(n, 240)) for n in notes if isinstance(n, str) and n.strip()]
    if survey.get("inaccessible_file_note") and not any("information gap" in n.lower() for n in notes):
        notes.insert(0, _INACCESSIBLE_RULE)
    if not notes:
        notes = heur.get("satisfaction_notes") or []
    llm["satisfaction_notes"] = notes[:8]

    ops = llm.get("operational_signals") if isinstance(llm.get("operational_signals"), list) else []
    ops = [r for r in ops if isinstance(r, dict) and (r.get("measure") or r.get("value"))]
    if not ops:
        ops = heur.get("operational_signals") or []
    llm["operational_signals"] = ops[:8]

    assoc = llm.get("churn_association") if isinstance(llm.get("churn_association"), dict) else {}
    if not assoc:
        assoc = heur["churn_association"]
    else:
        base = dict(heur["churn_association"])
        base.update({k: v for k, v in assoc.items() if v is not None})
        assoc = base
    assoc["association_only"] = True
    assoc["related_agent"] = "customer_stickiness"
    if assoc.get("comparable") and "association" not in str(assoc.get("notes") or "").lower():
        assoc["notes"] = f"{_clean(assoc.get('notes'), 280)} {_ASSOCIATION_RULE}".strip()
    llm["churn_association"] = assoc

    reviews = llm.get("public_reviews") if isinstance(llm.get("public_reviews"), dict) else {}
    if not reviews:
        reviews = heur["public_reviews"]
    reviews["treated_as"] = "self_selected_signal"
    if "self-selected" not in str(reviews.get("notes") or "").lower() and "self_selected" not in str(reviews.get("notes") or "").lower():
        reviews["notes"] = f"{_clean(reviews.get('notes'), 280)} {_REVIEWS_RULE}".strip()
    llm["public_reviews"] = reviews

    research = llm.get("research_design") if isinstance(llm.get("research_design"), dict) else {}
    if not research:
        research = heur["research_design"]
    else:
        base = dict(heur["research_design"])
        base.update({k: v for k, v in research.items() if v is not None})
        research = base
    llm["research_design"] = research

    llm["score_traceability"] = {
        "nps_traceable": bool(nps_ok and nps is not None),
        "csat_traceable": bool(csat_ok and csat is not None),
        "notes": f"NPS: {nps_note} CSAT: {csat_note}",
    }

    insight = _soften_invest(llm.get("insight_snapshot") or heur.get("insight_snapshot") or "")
    if survey.get("inaccessible_file_note") and "information gap" not in insight.lower():
        insight = f"{insight} {_INACCESSIBLE_RULE}".strip()
    llm["insight_snapshot"] = insight

    survey_qa = _survey_evidence_qa(
        survey,
        association=assoc,
        reviews=reviews,
        insight=insight,
        notes=notes,
    )
    llm["survey_evidence_qa"] = survey_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in survey_qa)

    quality, reliance, rationale = _quality_reliance(
        survey=survey,
        ops_count=len(ops),
        association=assoc,
        nps_traceable=bool(nps_ok and nps is not None),
        csat_traceable=bool(csat_ok and csat is not None),
        research_needed=bool(research.get("needed")),
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
            "Survey evidence QA has open FAILs — reliance limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )

    if not llm.get("questions"):
        llm["questions"] = _questions_from_sat_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_sat_gaps(llm)

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = (
        nps is None
        and csat is None
        and not cleaned_drivers
        and not ops
    )
    return llm


def build_customer_satisfaction_spec(
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
        gathered_corpus, gathered_sources = gather_customer_satisfaction_corpus(deal, idx)
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
        llm = _llm_customer_satisfaction_spec(
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
                legacy_spec=legacy_spec,
                corpus=corpus,
            )
            out["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return out

    heur = _heuristic_customer_satisfaction_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


def render_customer_satisfaction_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    survey = spec.get("survey_assessment") if isinstance(spec.get("survey_assessment"), dict) else {}
    ops = spec.get("operational_signals") if isinstance(spec.get("operational_signals"), list) else []
    assoc = spec.get("churn_association") if isinstance(spec.get("churn_association"), dict) else {}
    reviews = spec.get("public_reviews") if isinstance(spec.get("public_reviews"), dict) else {}
    research = spec.get("research_design") if isinstance(spec.get("research_design"), dict) else {}
    trace = spec.get("score_traceability") if isinstance(spec.get("score_traceability"), dict) else {}
    drivers = spec.get("churn_drivers") if isinstance(spec.get("churn_drivers"), list) else []
    peers = spec.get("peer_nps") if isinstance(spec.get("peer_nps"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Survey Representativeness\n\n")
    parts.append(
        "Survey evidence is assessed for date, target population, sample size, response rate, "
        "segment mix, question wording and selection bias. Scores are calculated only from "
        "valid responses and the definition is stated. A score that cannot be traced is not quoted.\n\n"
    )
    if survey.get("inaccessible_file_note"):
        parts.append(f"*{survey['inaccessible_file_note']}*\n\n")
    parts.append(_table(
        ["Item", "Value"],
        [
            ["Survey present", "Yes" if survey.get("present") else "No / thin"],
            ["Date", _clean(survey.get("date"), 60)],
            ["Target population", _clean(survey.get("target_population"), 200)],
            ["Sample size", _clean(survey.get("sample_size"), 40)],
            ["Response rate", _clean(survey.get("response_rate"), 40)],
            ["Segment mix", _clean(survey.get("segment_mix"), 200)],
            ["Question wording", _clean(survey.get("question_wording"), 220)],
            ["Selection bias", _clean(survey.get("selection_bias"), 160)],
            ["Score definition", _clean(survey.get("score_definition"), 220)],
            ["Valid responses only", _clean(survey.get("scores_from_valid_only"), 120)],
            ["Source", _clean(survey.get("source") or _NA, 60)],
        ],
    ))
    if _is_filled(survey.get("information_request")):
        parts.append(f"**{_clean(survey.get('information_request'), 300)}**\n\n")

    score_rows: list[list[str]] = []
    if spec.get("nps") is not None:
        score_rows.append([
            "NPS",
            f"{_num(spec.get('nps')):g}",
            "Traceable" if trace.get("nps_traceable") else "Not quoted without trace",
        ])
    if spec.get("service_satisfaction_pct") is not None:
        score_rows.append([
            "Service satisfaction / CSAT",
            f"{_num(spec.get('service_satisfaction_pct')):g}%",
            "Traceable" if trace.get("csat_traceable") else "Not quoted without trace",
        ])
    if score_rows:
        parts.append("### Traceable scores\n\n")
        parts.append(_table(["Score", "Value", "Traceability"], score_rows))
    if peers:
        parts.append("### Peer NPS (as stated)\n\n")
        for p in peers[:6]:
            if isinstance(p, str):
                parts.append(f"- {_clean(p, 120)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Operational Service Measures\n\n")
    parts.append(
        "Operational records are the harder evidence: complaints, missed or late service, "
        "quality failures, response and resolution times, and their trend.\n\n"
    )
    if ops:
        parts.append(_table(
            ["Type", "Measure", "Value", "Trend", "Source"],
            [
                [
                    _clean(r.get("signal_type"), 40),
                    _clean(r.get("measure"), 80),
                    _clean(r.get("value"), 80),
                    _clean(r.get("trend"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in ops if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            "No operational service measures were evidenced. "
            f"**{_info_request('complaints, missed/late service, quality failures, resolution times and trends')}**\n\n"
        )
    if drivers:
        parts.append("### Churn / dissatisfaction drivers (as recorded)\n\n")
        parts.append(_table(
            ["Driver", "Contribution", "Severity"],
            [
                [
                    _clean(r.get("driver"), 80),
                    f"{_num(r.get('contribution_pct')):g}%" if _num(r.get("contribution_pct")) is not None else "—",
                    _clean(r.get("severity"), 20) or "—",
                ]
                for r in drivers if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Service Quality ↔ Churn (Association)\n\n")
    parts.append(
        "Where churn data exist, service failures are compared with subsequent cancellations. "
        f"{_ASSOCIATION_RULE}\n\n"
    )
    parts.append(_table(
        ["Item", "Statement"],
        [
            ["Comparable", "Yes" if assoc.get("comparable") else "No"],
            ["Association only", "Yes" if assoc.get("association_only", True) else "Causation claimed with support"],
            ["Related agent", _clean(assoc.get("related_agent") or "customer_stickiness", 40)],
            ["Service failure", _clean(assoc.get("service_failure"), 220)],
            ["Subsequent cancellation", _clean(assoc.get("subsequent_cancellation"), 220)],
            ["Notes", _clean(assoc.get("notes"), 320)],
            ["Source", _clean(assoc.get("source") or _NA, 60)],
        ],
    ))
    if _is_filled(assoc.get("information_request")):
        parts.append(f"**{_clean(assoc.get('information_request'), 300)}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Public Reviews (Self-Selected Signal)\n\n")
    parts.append(f"{_REVIEWS_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            ["Treated as", _clean(reviews.get("treated_as") or "self_selected_signal", 40)],
            ["Notes", _clean(reviews.get("notes"), 360)],
            ["Source", _clean(reviews.get("source") or _NA, 60)],
        ],
    ))
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Research Design (If Evidence Thin)\n\n")
    if research.get("needed"):
        parts.append(
            "Sentiment evidence is thin. The following research design is proposed so the deal "
            "team can commission it — rather than relying on untraceable scores or inaccessible files.\n\n"
        )
        parts.append(_table(
            ["Design element", "Proposal"],
            [
                ["Population", _clean(research.get("population"), 220)],
                ["Sample", _clean(research.get("sample"), 220)],
                ["Method", _clean(research.get("method"), 220)],
                ["Questions", _clean(research.get("questions"), 280)],
                ["Timing", _clean(research.get("timing"), 160)],
                ["Rationale", _clean(research.get("rationale"), 320)],
            ],
        ))
    else:
        parts.append(
            f"{_clean(research.get('rationale'), 320) or 'Evidence is sufficient without a new study.'}\n\n"
        )
    parts.append(
        "*This section does not recommend invest or pass. Satisfaction scores are quoted only when "
        "traceable. An inaccessible survey file is an information gap — not evidence of poor "
        "customer focus.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    survey_qa = (
        spec.get("survey_evidence_qa")
        if isinstance(spec.get("survey_evidence_qa"), list)
        else []
    )
    parts.append("## 6. Survey Evidence QA\n\n")
    parts.append(
        "QA enforces valid-response-only scores, inaccessible-file as gap (not poor focus), "
        "association≠causation with Stickiness, and self-selected public reviews.\n\n"
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
                for r in survey_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('survey evidence QA rows')}\n\n"
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
        parts.append(f"{_info_request('Questions for material customer-satisfaction gaps')}\n\n")
    parts.append("---\n\n")

    # 8
    parts.append("## 8. Quality & Reliance\n\n")
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
            ["Score traceability", _clean(trace.get("notes"), 240)],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can diligence rest on this sentiment evidence?\n\n"
    )
    notes = spec.get("satisfaction_notes") if isinstance(spec.get("satisfaction_notes"), list) else []
    if notes:
        parts.append("### Satisfaction notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document assesses whether customer sentiment evidence is representative enough "
        "to rely on and connects service quality to churn where the data allow. "
        "It does not recommend invest or pass.*\n\n"
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
