"""Compose DiligenceIQ Internal Risk — day-one inherited issues inside the business.

Pulls validated upstream registers (mgmt / fin / cash flow / ops / tech /
compliance). Key-person exposure, financial strain, observed vs untested
controls, remediation (pre-decision vs post-close). Unified register row
schema: root cause, event, exposure, controls, residual, owner, action.
Known weakness vs uncertainty. Conflict reconcile before rank. Ban
"manageable risk" silence of blockers.

Dual-writes legacy DD-21 fields (tech_components / technical_risks /
scalability_notes).

No invest/pass. No company hardcoding.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+)?(?:recommend|advise|suggest)\s+(?:to\s+)?(?:invest|pass)\b"
)

_DOCUMENT_TITLE = "Internal Risk"
_DD_CODE = "DD-21"
_AGENT_KEY = "internal_risk"

_KEY_PERSON_RULE = (
    "Dependence on individuals and the effect if each left — facts taken from "
    "the management agent, not restated differently."
)
_STRAIN_RULE = (
    "Financial strain from the records: cash trend, liquidity headroom, "
    "covenant position, creditor days versus terms, and distributions made "
    "while earnings were weak."
)
_CONTROL_RULE = (
    "Control and governance weaknesses actually observed "
    "(reconciliations not performed, approvals missing, records incomplete) "
    "are distinguished from procedures simply unable to be tested. "
    "Untested is not failed."
)
_REMEDIATE_RULE = (
    "Remediation is sized: cost, how long it would take, and whether it is a "
    "pre-completion condition or a post-close action."
)
_RANK_RULE = (
    "Internal risks are ranked by effect on price, structure, or the first "
    "hundred days — after conflicts are reconciled."
)
_ROW_RULE = (
    "Each material internal risk row states root cause, event, exposure, "
    "controls, residual, owner, and action."
)
_KNOWN_RULE = (
    "Known / observed weaknesses are labelled separately from uncertainty. "
    "Untested is not failed."
)
_UPSTREAM_RULE = (
    "Pull validated registers from management, Capital Structure, Cash Flow, "
    "operations, technology and compliance where available — do not invent."
)
_CONFLICT_RULE = (
    "Reconcile conflicting register rows (same risk, different effect or "
    "evidence class) before ranking."
)
_MANAGEABLE_RULE = (
    "Do not label a blocker as 'manageable risk' to silence it — Structure / "
    "pre-decision items stay visible."
)
_MANAGEABLE_RE = re.compile(
    r"(?i)\b(manageable\s+risk|readily\s+manageable|easily\s+manageable|"
    r"risk\s+is\s+manageable|can\s+be\s+managed\s+away)\b"
)

_AMOUNT_RE = re.compile(
    r"(?i)(?:USD|US\$|\$)\s*~?([\d.]+)\s*([MB])\b|"
    r"(?:INR|₹)\s*([\d,]+(?:\.\d+)?)\s*(Cr|cr|crore)?"
)
_OBS_WEAK_RE = re.compile(
    r"(?i)\b("
    r"reconcil(?:iation)?s?\s+(?:not\s+performed|missing|overdue)|"
    r"approvals?\s+(?:missing|absent|bypass(?:ed)?|not\s+obtained)|"
    r"records?\s+(?:incomplete|missing|not\s+maintained)|"
    r"audit\s+(?:finding|exception|qualification)|"
    r"control\s+(?:failure|deficiency|weakness)|"
    r"segregation\s+of\s+duties\s+(?:gap|breach|weak)|"
    r"journal\s+entries?\s+without\s+approval|"
    r"bank\s+reconcil"
    r")\b"
)
_UNTESTED_RE = re.compile(
    r"(?i)\b("
    r"not\s+(?:yet\s+)?(?:tested|audited|reviewed)|"
    r"untested|unable\s+to\s+test|access\s+(?:denied|not\s+provided)|"
    r"penetration\s+testing\s+not\s+(?:yet\s+)?complete|"
    r"testing\s+(?:incomplete|pending|outstanding)"
    r")\b"
)
_TESTED_RE = re.compile(
    r"(?i)\b(tested|audited|inspection\s+passed|walkthrough\s+completed|"
    r"sample\s+tested|control\s+tested)\b"
)
_DISTRIB_RE = re.compile(
    r"(?i)\b(dividend|distribution|share\s+buy[- ]?back|related[- ]party\s+"
    r"(?:payment|loan)|cash\s+sweep)\b"
)
_CREDITOR_RE = re.compile(
    r"(?i)\b(creditor\s+days|DPO|days\s+payable|overdue\s+(?:trade\s+)?"
    r"creditors?|stretched\s+payables?|payment\s+terms)\b"
)
_LIQUIDITY_RE = re.compile(
    r"(?i)\b(cash\s+(?:burn|runway|trend|floor|headroom)|liquidity|"
    r"freely\s+available\s+cash|restricted\s+cash|working\s+capital)\b"
)
_COVENANT_RE = re.compile(
    r"(?i)\b(covenant(?:s)?(?:\s+headroom|\s+breach|\s+waiver)?|"
    r"net\s+debt\s*/\s*EBITDA|interest\s+cover)\b"
)
_TIME_RE = re.compile(
    r"(?i)(within\s+\d+\s+(?:months?|weeks?|days?)|"
    r"\d+[-–]\d+\s+(?:months?|weeks?)|"
    r"pre[- ]?completion|post[- ]?close|day\s+1|"
    r"first\s+(?:30|60|90|100)\s+days?)"
)
_COST_RE = re.compile(
    r"(?i)(?:cost|spend|budget|remediat(?:e|ion)|fix)\s*(?:of|at|:)?\s*"
    r"(?:(?:USD|US\$|\$)\s*~?[\d.]+\s*[MB]|"
    r"(?:INR|₹)\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr|crore)?)"
)


def _soften_invest(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    out = _INVEST_LANG.sub("risk evidence only — no deal verdict expressed", raw)
    return re.sub(r"\s{2,}", " ", out).strip(" —-–:")


def _info_request(need: str) -> str:
    return f"Information request: {need}"


def _round(val: float, digits: int = 1) -> float:
    return round(float(val), digits)


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
        cells = [(_soften_invest(_clean(c, 220)) or "—") for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n\n"


def _prose(corpus: str) -> str:
    text = _ZWSP.sub("", corpus or "")
    text = _PDF_BULLETS.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _window(text: str, start: int, *, radius: int = 180) -> str:
    return text[max(0, start - radius) : min(len(text), start + radius)]


def _usd_m_from_match(m: re.Match[str]) -> float | None:
    if m.group(1):
        val = float(m.group(1))
        unit = (m.group(2) or "M").upper()
        return val * 1000.0 if unit.startswith("B") else val
    if m.group(3):
        inr = float(m.group(3).replace(",", ""))
        if m.group(4):
            return _round(inr * 10.0 / 83.0, 1)
        return _round(inr / 83.0, 1)
    return None


def _is_info(val: Any) -> bool:
    s = str(val or "")
    low = s.lower().strip()
    return (
        not s
        or s.startswith("Information")
        or s.startswith("N/A")
        or s == _NA
        or low.startswith("named in hr")
        or low.startswith("named in the corporate pack")
        or low in {"key person", "n/a", "na"}
    )


# ---------------------------------------------------------------------------
# corpus
# ---------------------------------------------------------------------------


def gather_internal_risk_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "company_management": 0,
        "financial": 1,
        "operations": 2,
        "legal_esg": 3,
        "deal_strategy": 4,
    }
    needles = (
        "hr", "org", "management", "governance", "audit", "internal",
        "control", "financial", "covenant", "cash", "tech", "cyber",
        "operational", "legal",
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
        text = _ZWSP.sub("", text)
        text = _PDF_BULLETS.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:12_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


# ---------------------------------------------------------------------------
# section builders
# ---------------------------------------------------------------------------


def _key_person_exposure(
    management: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Take key-person facts from the management agent — do not restate differently."""
    mq = management if isinstance(management, dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    from agetic_cdd_api.agent_document_management_quality import _plausible_person_name

    for kp in mq.get("key_persons") or []:
        if not isinstance(kp, dict) or not kp.get("person"):
            continue
        person = _clean(kp.get("person"), 80)
        key = person.lower()
        if (
            not person
            or key in seen
            or key.startswith("information request")
            or key.startswith("named in hr")
            or key in {"key person", "n/a", "na"}
        ):
            continue
        if not _plausible_person_name(person):
            # Garbled CEO sentence → fall through to executive roster.
            continue
        seen.add(key)
        rows.append(
            {
                "person": person,
                "what_depends": _clean(
                    kp.get("what_depends")
                    or _info_request(f"what depends on {person}"),
                    160,
                ),
                "effect_if_left": _clean(
                    kp.get("what_depends")
                    or _info_request(f"effect if {person} left"),
                    160,
                ),
                "notice_incentives": _clean(
                    kp.get("notice_incentives") or _NA, 100
                ),
                "source": kp.get("source") or "(DOC: management agent)",
                "notes": _KEY_PERSON_RULE,
            }
        )

    for s in mq.get("succession") or []:
        if not isinstance(s, dict):
            continue
        role = _clean(s.get("role"), 40)
        incumbent = _clean(s.get("incumbent"), 60)
        status = str(s.get("succession_status") or "")
        if not role and not incumbent:
            continue
        person = f"{incumbent} ({role})" if incumbent and role else (incumbent or role)
        key = person.lower()
        if key in seen:
            # Enrich existing row with succession status
            for r in rows:
                if r["person"].lower() == key or (
                    incumbent and incumbent.lower() in r["person"].lower()
                ):
                    if "Succession" not in str(r.get("effect_if_left") or ""):
                        r["effect_if_left"] = _clean(
                            f"{r.get('effect_if_left')}; succession: {status}",
                            180,
                        )
                    break
            continue
        if "gap" not in status.lower() and "high" not in status.lower():
            continue
        seen.add(key)
        rows.append(
            {
                "person": person,
                "what_depends": _clean(
                    f"{role} continuity — succession status: {status}", 140
                ),
                "effect_if_left": _clean(
                    f"No evidenced second line; {status}", 140
                ),
                "notice_incentives": _NA,
                "source": s.get("source") or "(DOC: management agent)",
                "notes": _KEY_PERSON_RULE,
            }
        )

    # Fall back to named CEO / founder / controlling shareholder on the MQ roster
    # when key_persons was empty (avoids the info-request retention stub).
    if not rows:
        for ex in mq.get("executives") or mq.get("c_suite") or []:
            if not isinstance(ex, dict):
                continue
            name = _clean(ex.get("name"), 60)
            role = _clean(ex.get("role"), 40)
            if not name or name.lower().startswith("information"):
                continue
            if not _plausible_person_name(name):
                continue
            try:
                crit = int(ex.get("criticality") or 0)
            except (TypeError, ValueError):
                crit = 0
            is_ceo = bool(re.search(r"(?i)\b(?:ceo|founder|chairman|controlling)\b", role))
            if not is_ceo and crit < 5:
                continue
            person = f"{name} ({role})" if role else name
            rows.append(
                {
                    "person": person,
                    "what_depends": (
                        f"Strategic direction and equity control concentrated with {name} — "
                        "continuity risk without retention / succession"
                    ),
                    "effect_if_left": (
                        f"Deal continuity and post-close integration depend on {name} remaining"
                    ),
                    "notice_incentives": _NA,
                    "source": "(DOC: management agent)",
                    "notes": _KEY_PERSON_RULE,
                }
            )
            break
    if not rows:
        rows.append(
            {
                "person": _info_request(
                    "key-person map from management agent (run Management Quality first)"
                ),
                "what_depends": _info_request("what depends on each individual"),
                "effect_if_left": _info_request("effect if each left"),
                "notice_incentives": _NA,
                "source": _NA,
                "notes": _KEY_PERSON_RULE,
            }
        )
    return rows[:10]


def _financial_strain(
    *,
    corpus: str,
    capital: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    cap = capital if isinstance(capital, dict) else {}
    rows: list[dict[str, Any]] = []

    # Cash / liquidity from capital structure + corpus
    cash_rows = [
        c for c in (cap.get("cash_split") or [])
        if isinstance(c, dict)
    ]
    free = next(
        (
            c for c in cash_rows
            if "freely" in str(c.get("bucket") or "").lower()
        ),
        None,
    )
    burn = cap.get("cash_burn_rate_monthly_inr_cr")
    cash_detail_bits: list[str] = []
    if free and not _is_info(free.get("amount")):
        cash_detail_bits.append(
            f"Freely available cash: {free.get('amount')} "
            f"(capital structure)"
        )
    elif free:
        cash_detail_bits.append(
            "Freely available cash not sized in capital structure"
        )
    if burn is not None:
        cash_detail_bits.append(f"Monthly cash burn ~{burn} Cr (capital structure)")
    lm = _LIQUIDITY_RE.search(text)
    if lm:
        cash_detail_bits.append(_clean(_window(text, lm.start(), radius=90), 120))
    rows.append(
        {
            "indicator": "Cash trend / liquidity headroom",
            "finding": (
                "; ".join(cash_detail_bits)
                if cash_detail_bits
                else _info_request("cash trend and liquidity headroom from records")
            ),
            "strain": (
                "Elevated"
                if burn is not None or (lm and "burn" in lm.group(0).lower())
                else ("Open" if cash_detail_bits else "Unknown")
            ),
            "source": "(DOC: capital structure)" if free or burn is not None else (
                _DOC_CITE if lm else _NA
            ),
            "notes": _STRAIN_RULE,
        }
    )

    # Covenant position
    facilities = [
        f for f in (cap.get("facilities") or [])
        if isinstance(f, dict)
    ]
    cov_bits: list[str] = []
    any_headroom = False
    for f in facilities[:6]:
        head = f.get("covenants_headroom")
        name = _clean(f.get("facility") or f.get("name"), 40)
        if head and not _is_info(head):
            cov_bits.append(f"{name}: {head}")
            any_headroom = True
        elif name:
            cov_bits.append(f"{name}: covenants / headroom not evidenced")
    cm = _COVENANT_RE.search(text)
    if cm and not any_headroom:
        cov_bits.append(_clean(_window(text, cm.start(), radius=80), 120))
    gaps = cap.get("schedule_gaps") or []
    if gaps and not any_headroom:
        cov_bits.append(
            f"Facility schedule incomplete ({len(gaps)} gap(s)) — "
            f"covenant headroom cannot be relied upon"
        )
    rows.append(
        {
            "indicator": "Covenant position",
            "finding": (
                "; ".join(cov_bits[:4])
                if cov_bits
                else _info_request("covenant tests and headroom from loan documents")
            ),
            "strain": "Elevated" if gaps and not any_headroom else (
                "Sized" if any_headroom else "Unknown"
            ),
            "source": "(DOC: capital structure)" if facilities else (
                _DOC_CITE if cm else _NA
            ),
            "notes": _STRAIN_RULE,
        }
    )

    # Creditor stretch
    debt_like = [
        d for d in (cap.get("debt_like_items") or [])
        if isinstance(d, dict)
    ]
    overdue = [
        d for d in debt_like
        if "overdue" in str(d.get("kind") or "").lower()
        or "creditor" in str(d.get("item") or "").lower()
        or "creditor" in str(d.get("kind") or "").lower()
    ]
    creditor_bits: list[str] = []
    for d in overdue[:3]:
        amt = d.get("amount")
        creditor_bits.append(
            f"{_clean(d.get('item') or d.get('kind'), 50)}"
            + (f" — {amt}" if amt is not None and not _is_info(amt) else "")
        )
    crm = _CREDITOR_RE.search(text)
    if crm:
        creditor_bits.append(_clean(_window(text, crm.start(), radius=80), 120))
    rows.append(
        {
            "indicator": "Creditor days vs terms",
            "finding": (
                "; ".join(creditor_bits)
                if creditor_bits
                else _info_request(
                    "creditor days versus contractual terms / overdue trade creditors"
                )
            ),
            "strain": "Elevated" if overdue or crm else "Unknown",
            "source": "(DOC: capital structure)" if overdue else (
                _DOC_CITE if crm else _NA
            ),
            "notes": _STRAIN_RULE,
        }
    )

    # Distributions while earnings weak
    dm = _DISTRIB_RE.search(text)
    weak = re.search(
        r"(?i)(weak\s+earnings|loss[- ]making|negative\s+EBITDA|earnings\s+decline)",
        text,
    )
    if dm:
        finding = _clean(_window(text, dm.start(), radius=100), 140)
        if weak:
            finding += "; earnings-weak language also present in packs"
        rows.append(
            {
                "indicator": "Distributions while earnings weak",
                "finding": finding,
                "strain": "Elevated" if weak else "Observed",
                "source": _DOC_CITE,
                "notes": _STRAIN_RULE,
            }
        )
    else:
        rows.append(
            {
                "indicator": "Distributions while earnings weak",
                "finding": _info_request(
                    "dividends / distributions / related-party cash while earnings weak"
                ),
                "strain": "Unknown",
                "source": _NA,
                "notes": _STRAIN_RULE,
            }
        )

    return rows


def _governance_controls(
    *,
    corpus: str,
    legacy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (observed_weaknesses, control_test_register). Untested ≠ failed."""
    text = _prose(corpus)
    observed: list[dict[str, Any]] = []
    tested_register: list[dict[str, Any]] = []
    seen: set[str] = set()

    for m in _OBS_WEAK_RE.finditer(text):
        win = _window(text, m.start(), radius=120)
        key = _clean(m.group(0), 60).lower()
        if key in seen:
            continue
        seen.add(key)
        observed.append(
            {
                "weakness": _clean(m.group(0), 80),
                "evidence": _clean(win, 160),
                "status": "Observed",
                "source": _DOC_CITE,
                "notes": _CONTROL_RULE,
            }
        )

    # Legacy technical risks that are control/governance flavoured
    for note in list(legacy.get("technical_risks") or []) + list(
        legacy.get("scalability_notes") or []
    ):
        if not isinstance(note, str) or not note.strip():
            continue
        low = note.lower()
        if _OBS_WEAK_RE.search(note) or any(
            k in low for k in ("control", "governance", "approval", "reconcil", "audit")
        ):
            key = _clean(note, 60).lower()
            if key in seen:
                continue
            seen.add(key)
            observed.append(
                {
                    "weakness": _clean(note.split(":")[0], 80),
                    "evidence": _clean(note, 160),
                    "status": "Observed",
                    "source": _DOC_CITE,
                    "notes": _CONTROL_RULE,
                }
            )

    # Build tested vs untested register from corpus + tech risks
    for m in _UNTESTED_RE.finditer(text):
        # Prefer forward context so prior bullets do not pollute the control name
        win = text[m.start() : min(len(text), m.start() + 160)]
        if not re.search(
            r"(?i)\b(control|test|audit|reconcil|approval|penetration|"
            r"cyber|security|review|walkthrough)\b",
            win,
        ):
            continue
        control_name = _clean(win, 100)
        key = control_name.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        tested_register.append(
            {
                "control": control_name,
                "tested": "Not tested",
                "result": "Untested — not a failure; evidence of test not in packs",
                "source": _DOC_CITE,
                "notes": _CONTROL_RULE,
            }
        )
        if len(tested_register) >= 6:
            break

    for m in _TESTED_RE.finditer(text):
        win = _window(text, m.start(), radius=100)
        if _UNTESTED_RE.search(win):
            continue
        if not re.search(
            r"(?i)\b(control|test|audit|reconcil|approval|sample|"
            r"inspection|walkthrough)\b",
            win,
        ):
            continue
        control_name = _clean(win, 100)
        key = control_name.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        tested_register.append(
            {
                "control": control_name,
                "tested": "Tested",
                "result": "Test evidenced in packs",
                "source": _DOC_CITE,
                "notes": _CONTROL_RULE,
            }
        )
        if len(tested_register) >= 8:
            break

    # Tech components with low maturity → systems risk (observed / untested)
    for tc in legacy.get("tech_components") or []:
        if not isinstance(tc, dict):
            continue
        name = _clean(tc.get("component"), 60)
        maturity = tc.get("maturity_score")
        risk = _clean(tc.get("key_risk"), 100)
        if not name:
            continue
        if isinstance(maturity, (int, float)) and maturity < 3.5:
            observed.append(
                {
                    "weakness": f"Systems maturity — {name}",
                    "evidence": (
                        f"Maturity {maturity}/5"
                        + (f"; key risk: {risk}" if risk else "")
                    ),
                    "status": "Observed",
                    "source": _DOC_CITE,
                    "notes": _CONTROL_RULE,
                }
            )
        if risk and _UNTESTED_RE.search(risk):
            key = f"{name}-{risk}".lower()[:60]
            if key not in seen:
                seen.add(key)
                tested_register.append(
                    {
                        "control": f"{name} — {risk}",
                        "tested": "Not tested",
                        "result": "Untested — not a failure",
                        "source": _DOC_CITE,
                        "notes": _CONTROL_RULE,
                    }
                )

    # Explicit untested notes from legacy technical risks
    for note in list(legacy.get("technical_risks") or []) + list(
        legacy.get("scalability_notes") or []
    ):
        if not isinstance(note, str) or not _UNTESTED_RE.search(note):
            continue
        key = _clean(note, 60).lower()
        if key in seen:
            continue
        seen.add(key)
        tested_register.append(
            {
                "control": _clean(note, 120),
                "tested": "Not tested",
                "result": "Untested — not a failure",
                "source": _DOC_CITE,
                "notes": _CONTROL_RULE,
            }
        )

    if not observed:
        observed.append(
            {
                "weakness": _info_request(
                    "observed control / governance weakness "
                    "(reconciliations, approvals, incomplete records)"
                ),
                "evidence": _NA,
                "status": "Not evidenced",
                "source": _NA,
                "notes": _CONTROL_RULE,
            }
        )
    if not tested_register:
        tested_register.append(
            {
                "control": _info_request("named controls in scope for testing"),
                "tested": "Not tested",
                "result": "No control-test evidence opened — untested is not failed",
                "source": _NA,
                "notes": _CONTROL_RULE,
            }
        )

    return observed[:10], tested_register[:10]


def _remediation_rows(
    *,
    key_persons: list[dict[str, Any]],
    strain: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    corpus: str,
) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []

    def _cost_time(window: str) -> tuple[str, str]:
        cm = _COST_RE.search(window) or _AMOUNT_RE.search(window)
        cost = _clean(cm.group(0), 60) if cm else _info_request("remediation cost")
        tm = _TIME_RE.search(window)
        timing = _clean(tm.group(1), 40) if tm else _info_request("remediation duration")
        return cost, timing

    # Key-person remediation → often post-close retention / succession
    for kp in key_persons[:4]:
        if not isinstance(kp, dict) or _is_info(kp.get("person")):
            continue
        person = kp.get("person")
        rows.append(
            {
                "item": f"Key-person continuity — {person}",
                "cost": _info_request(
                    f"retention / succession cost for {person}"
                ),
                "duration": _info_request("time to put second line / retention in place"),
                "timing": "Post-close action (first hundred days)",
                "source": kp.get("source") or "(DOC: management agent)",
                "notes": _REMEDIATE_RULE,
            }
        )

    # Elevated strain → often pre-completion (covenant waiver / cash)
    for s in strain:
        if not isinstance(s, dict):
            continue
        if str(s.get("strain") or "") not in {"Elevated", "Observed"}:
            continue
        indicator = s.get("indicator")
        cost, duration = _cost_time(str(s.get("finding") or ""))
        pre = (
            "Pre-completion condition"
            if "covenant" in str(indicator or "").lower()
            or "liquidity" in str(indicator or "").lower()
            or "cash" in str(indicator or "").lower()
            else "Post-close action"
        )
        rows.append(
            {
                "item": f"Remediate — {indicator}",
                "cost": cost,
                "duration": duration,
                "timing": pre,
                "source": s.get("source") or _DOC_CITE,
                "notes": _REMEDIATE_RULE,
            }
        )

    # Observed control weaknesses
    for w in observed[:4]:
        if not isinstance(w, dict) or _is_info(w.get("weakness")):
            continue
        if str(w.get("status") or "") != "Observed":
            continue
        evidence = str(w.get("evidence") or "")
        cost, duration = _cost_time(evidence + " " + text[:400])
        rows.append(
            {
                "item": f"Fix control — {w.get('weakness')}",
                "cost": cost,
                "duration": duration,
                "timing": (
                    "Pre-completion condition"
                    if "audit" in str(w.get("weakness") or "").lower()
                    else "Post-close action"
                ),
                "source": w.get("source") or _DOC_CITE,
                "notes": _REMEDIATE_RULE,
            }
        )

    if not rows:
        rows.append(
            {
                "item": _info_request("remediation items to size"),
                "cost": _info_request("remediation cost"),
                "duration": _info_request("remediation duration"),
                "timing": _info_request("pre-completion vs post-close"),
                "source": _NA,
                "notes": _REMEDIATE_RULE,
            }
        )
    return rows[:12]


def _rank_rows(
    *,
    key_persons: list[dict[str, Any]],
    strain: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    for kp in key_persons[:3]:
        if not isinstance(kp, dict) or _is_info(kp.get("person")):
            continue
        rows.append(
            {
                "risk": f"Key-person — {kp.get('person')}",
                "effect": "First hundred days",
                "rationale": (
                    "Day-one continuity / approvals dependency; "
                    "retention and succession sit in the first hundred days"
                ),
                "source": kp.get("source") or "(DOC: management agent)",
                "notes": _RANK_RULE,
            }
        )

    for s in strain:
        if not isinstance(s, dict):
            continue
        if str(s.get("strain") or "") not in {"Elevated", "Observed"}:
            continue
        indicator = str(s.get("indicator") or "")
        if "covenant" in indicator.lower() or "liquidity" in indicator.lower() or "cash" in indicator.lower():
            effect = "Structure"
            rationale = (
                "May require waiver, escrow, CP, or cash injection before / at completion"
            )
        elif "creditor" in indicator.lower() or "distribution" in indicator.lower():
            effect = "Price"
            rationale = (
                "Working-capital / net-debt / leakage adjustment typically prices in"
            )
        else:
            effect = "First hundred days"
            rationale = "Monitor and remediate in the first hundred days"
        rows.append(
            {
                "risk": indicator,
                "effect": effect,
                "rationale": rationale,
                "source": s.get("source") or _DOC_CITE,
                "notes": _RANK_RULE,
            }
        )

    for w in observed[:3]:
        if not isinstance(w, dict) or str(w.get("status") or "") != "Observed":
            continue
        if _is_info(w.get("weakness")):
            continue
        rows.append(
            {
                "risk": w.get("weakness"),
                "effect": (
                    "Structure"
                    if "audit" in str(w.get("weakness") or "").lower()
                    else "First hundred days"
                ),
                "rationale": (
                    "Observed control failure — indemnity / CP if material; "
                    "else fix in first hundred days"
                ),
                "source": w.get("source") or _DOC_CITE,
                "notes": _RANK_RULE,
            }
        )

    # Ensure remediation timing feeds rank when nothing else ranked
    if not rows:
        for r in remediation[:3]:
            if not isinstance(r, dict) or _is_info(r.get("item")):
                continue
            timing = str(r.get("timing") or "").lower()
            if "pre-completion" in timing or "structure" in timing:
                effect = "Structure"
            elif "price" in timing:
                effect = "Price"
            else:
                effect = "First hundred days"
            rows.append(
                {
                    "risk": r.get("item"),
                    "effect": effect,
                    "rationale": _clean(r.get("timing"), 120),
                    "source": r.get("source") or _NA,
                    "notes": _RANK_RULE,
                }
            )

    if not rows:
        rows.append(
            {
                "risk": _info_request("internal risks to rank"),
                "effect": _info_request("price / structure / first hundred days"),
                "rationale": _RANK_RULE,
                "source": _NA,
                "notes": _RANK_RULE,
            }
        )
    return rows[:12]


def _legacy_dual_write(
    *,
    legacy: dict[str, Any],
    observed: list[dict[str, Any]],
    key_persons: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    tech = [
        t for t in (legacy.get("tech_components") or [])
        if isinstance(t, dict)
    ]
    risks = [
        r for r in (legacy.get("technical_risks") or [])
        if isinstance(r, str) and r.strip()
    ]
    notes = [
        n for n in (legacy.get("scalability_notes") or [])
        if isinstance(n, str) and n.strip()
    ]
    # Append internal-risk flavoured notes without inventing tech content
    for kp in key_persons[:3]:
        if isinstance(kp, dict) and not _is_info(kp.get("person")):
            note = f"Key-person exposure: {kp.get('person')} — {kp.get('effect_if_left')}"
            if note not in notes:
                notes.append(_clean(note, 200))
    for w in observed[:3]:
        if isinstance(w, dict) and str(w.get("status")) == "Observed" and not _is_info(
            w.get("weakness")
        ):
            note = f"Governance/control: {w.get('weakness')}"
            if note not in risks:
                risks.append(_clean(note, 200))
    return tech[:12], risks[:12], notes[:12]


def _upstream_registers(
    *,
    management: dict[str, Any] | None,
    capital: dict[str, Any] | None,
    cash_flow: dict[str, Any] | None,
    operational: dict[str, Any] | None,
    regulatory: dict[str, Any] | None,
    tech: dict[str, Any] | None,
) -> dict[str, Any]:
    present = {
        "management_quality": isinstance(management, dict) and bool(
            management.get("key_persons") or management.get("succession")
        ),
        "capital_structure": isinstance(capital, dict) and bool(
            capital.get("facilities") or capital.get("cash_split")
        ),
        "cash_flow": isinstance(cash_flow, dict) and bool(
            cash_flow.get("bridge")
            or cash_flow.get("cash_bridge")
            or cash_flow.get("working_capital")
            or cash_flow.get("insight_snapshot")
        ),
        "operational_risk": isinstance(operational, dict) and bool(operational),
        "regulatory_compliance": isinstance(regulatory, dict) and bool(regulatory),
        "ip_and_technology": isinstance(tech, dict) and bool(tech),
    }
    opened = [k for k, v in present.items() if v]
    missing = [k for k, v in present.items() if not v]
    return {
        "present": present,
        "opened": opened,
        "missing": missing,
        "notes": _UPSTREAM_RULE,
    }


def _build_risk_register(
    *,
    key_persons: list[dict[str, Any]],
    strain: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    tested_register: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    rem_by_key = {
        str(r.get("item") or "").lower(): r
        for r in remediation
        if isinstance(r, dict)
    }
    rank_by_key = {
        str(r.get("risk") or "").lower(): r
        for r in ranked
        if isinstance(r, dict)
    }

    for kp in key_persons:
        if not isinstance(kp, dict) or _is_info(kp.get("person")):
            continue
        person = str(kp.get("person") or "")
        rem = next(
            (r for k, r in rem_by_key.items() if person.lower()[:20] in k),
            None,
        )
        rk = next(
            (r for k, r in rank_by_key.items() if person.lower()[:20] in k),
            None,
        )
        rows.append({
            "risk": f"Key-person — {person}",
            "root_cause": _clean(kp.get("what_depends") or "Concentration of authority", 120),
            "event": f"Departure / incapacity of {person}",
            "exposure": _clean(kp.get("effect_if_left"), 120),
            "controls": _clean(
                kp.get("notice_incentives") or _info_request("notice / incentives / second line"),
                100,
            ),
            "residual": "Elevated until succession evidenced",
            "owner": "Management / HR diligence lead",
            "action": _clean(
                (rem or {}).get("timing") or "Retention + succession in first hundred days",
                100,
            ),
            "evidence_class": "known_weakness",
            "quantified": False,
            "source": kp.get("source") or "(DOC: management agent)",
            "rank_effect": (rk or {}).get("effect"),
            "notes": _ROW_RULE,
        })

    for s in strain:
        if not isinstance(s, dict) or _is_info(s.get("indicator")):
            continue
        strain_lvl = str(s.get("strain") or "")
        if strain_lvl in {"Unknown", ""}:
            evid = "uncertainty"
        elif strain_lvl in {"Elevated", "Observed"}:
            evid = "known_weakness"
        else:
            evid = "known_weakness"
        indicator = str(s.get("indicator") or "")
        rem = next(
            (r for k, r in rem_by_key.items() if indicator.lower()[:16] in k),
            None,
        )
        rk = next(
            (r for k, r in rank_by_key.items() if indicator.lower()[:16] in k),
            None,
        )
        finding = str(s.get("finding") or "")
        quantified = bool(re.search(r"(?i)(\d|USD|INR|₹|%|x\b)", finding))
        rows.append({
            "risk": indicator,
            "root_cause": f"Financial strain — {indicator}",
            "event": _clean(finding, 120),
            "exposure": _clean(finding, 120),
            "controls": _info_request(f"current control / monitoring for {indicator}"),
            "residual": strain_lvl or _info_request("residual strain"),
            "owner": "Financial diligence lead",
            "action": _clean(
                (rem or {}).get("timing") or _info_request("pre-decision vs post-close action"),
                100,
            ),
            "evidence_class": evid,
            "quantified": quantified,
            "source": s.get("source") or _DOC_CITE,
            "rank_effect": (rk or {}).get("effect"),
            "notes": _ROW_RULE,
        })

    for w in observed:
        if not isinstance(w, dict) or _is_info(w.get("weakness")):
            continue
        status = str(w.get("status") or "")
        evid = "known_weakness" if status == "Observed" else "uncertainty"
        weakness = str(w.get("weakness") or "")
        rem = next(
            (r for k, r in rem_by_key.items() if weakness.lower()[:20] in k),
            None,
        )
        rk = next(
            (r for k, r in rank_by_key.items() if weakness.lower()[:20] in k),
            None,
        )
        rows.append({
            "risk": weakness,
            "root_cause": "Control / governance failure observed in records",
            "event": _clean(w.get("evidence"), 120),
            "exposure": _info_request(f"exposure if '{weakness}' persists"),
            "controls": "Control failed as observed" if evid == "known_weakness" else "Untested",
            "residual": status or "Open",
            "owner": "Controls / audit diligence lead",
            "action": _clean(
                (rem or {}).get("timing") or _info_request("remediation timing"),
                100,
            ),
            "evidence_class": evid,
            "quantified": False,
            "source": w.get("source") or _DOC_CITE,
            "rank_effect": (rk or {}).get("effect"),
            "notes": _ROW_RULE,
        })

    for t in tested_register:
        if not isinstance(t, dict) or _is_info(t.get("control")):
            continue
        if "not tested" not in str(t.get("tested") or "").lower():
            continue
        ctrl = str(t.get("control") or "")
        # Avoid duplicating an observed weakness already listed
        if any(ctrl.lower()[:24] in str(r.get("risk") or "").lower() for r in rows):
            continue
        rows.append({
            "risk": f"Untested control — {ctrl}",
            "root_cause": "Testing incomplete / access not provided",
            "event": _clean(t.get("result"), 120),
            "exposure": _info_request(f"exposure if '{ctrl}' fails when tested"),
            "controls": "Not tested",
            "residual": "Uncertainty — untested is not failed",
            "owner": "Controls diligence lead",
            "action": "Complete testing pre-decision where material",
            "evidence_class": "uncertainty",
            "quantified": False,
            "source": t.get("source") or _DOC_CITE,
            "rank_effect": "First hundred days",
            "notes": _KNOWN_RULE,
        })

    if not rows:
        rows.append({
            "risk": _info_request("internal risk register row"),
            "root_cause": _info_request("root cause"),
            "event": _info_request("event"),
            "exposure": _info_request("exposure"),
            "controls": _info_request("controls"),
            "residual": _info_request("residual"),
            "owner": _info_request("owner"),
            "action": _info_request("action"),
            "evidence_class": "uncertainty",
            "quantified": False,
            "source": _NA,
            "notes": _ROW_RULE,
        })
    return rows[:16]


def _reconcile_conflicts(
    *,
    register: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    corpus: str,
) -> dict[str, Any]:
    conflicts: list[str] = []
    resolved: list[str] = []
    # Same risk stem appearing with different evidence classes
    by_stem: dict[str, list[dict[str, Any]]] = {}
    for r in register:
        if not isinstance(r, dict) or _is_info(r.get("risk")):
            continue
        stem = re.sub(r"(?i)^(key-person\s*[—\-]\s*|untested control\s*[—\-]\s*)", "", str(r.get("risk")))
        stem = stem.lower()[:28]
        by_stem.setdefault(stem, []).append(r)
    for stem, group in by_stem.items():
        classes = {str(g.get("evidence_class") or "") for g in group}
        if "known_weakness" in classes and "uncertainty" in classes:
            conflicts.append(
                f"'{_clean(stem, 40)}' tagged both known_weakness and uncertainty"
            )
            # Prefer known_weakness
            for g in group:
                if g.get("evidence_class") == "uncertainty":
                    g["evidence_class"] = "known_weakness"
                    g["conflict_note"] = "Reconciled to known_weakness"
            resolved.append(f"Reconciled '{_clean(stem, 40)}' → known_weakness")

    # Ranked Structure/Price vs "manageable" language in corpus or rationale
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:do\s+not\s+label|must\s+not\s+call)[^.!?\n]*manageable[^.!?\n]*[.!?]?",
        " ",
        corpus or "",
    )
    manageable_hit = bool(_MANAGEABLE_RE.search(scrubbed))
    blockers = [
        r for r in ranked
        if isinstance(r, dict)
        and str(r.get("effect") or "") in {"Structure", "Price"}
        and not _is_info(r.get("risk"))
    ]
    if manageable_hit and blockers:
        conflicts.append(
            "Pack uses 'manageable risk' language while Structure/Price blockers are open"
        )
    for r in ranked:
        if not isinstance(r, dict):
            continue
        blob = f"{r.get('risk')} {r.get('rationale')}"
        if _MANAGEABLE_RE.search(blob) and str(r.get("effect") or "") in {"Structure", "Price"}:
            conflicts.append(
                f"Ranked blocker '{_clean(r.get('risk'), 50)}' labelled manageable — strip"
            )
            r["rationale"] = (
                str(r.get("rationale") or "")
                + " [reconciled: blocker not silenced as manageable]"
            )
            resolved.append(f"Cleared manageable label on '{_clean(r.get('risk'), 40)}'")

    return {
        "conflicts": conflicts[:8],
        "resolved": resolved[:8],
        "open_conflict_count": max(0, len(conflicts) - len(resolved)),
        "notes": _CONFLICT_RULE,
    }


def _ir_evidence_qa(
    *,
    register: list[dict[str, Any]],
    ranked: list[dict[str, Any]],
    remediation: list[dict[str, Any]],
    upstream: dict[str, Any],
    conflict: dict[str, Any],
    corpus: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    real = [
        r for r in register
        if isinstance(r, dict) and not _is_info(r.get("risk"))
    ]
    opened = list(upstream.get("opened") or [])
    core_ok = (
        "management_quality" in opened
        and ("capital_structure" in opened or "cash_flow" in opened)
    )
    rows.append({
        "check": "upstream_registers",
        "status": "PASS" if core_ok else "FAIL",
        "finding": (
            f"Opened: {', '.join(opened) or 'none'}"
            if core_ok
            else _info_request(
                "Management Quality + Capital Structure and/or Cash Flow priors"
            )
        ),
        "action": _UPSTREAM_RULE,
    })

    schema_ok = all(
        not _is_info(r.get("root_cause"))
        and not _is_info(r.get("event"))
        and not _is_info(r.get("exposure"))
        and not _is_info(r.get("controls"))
        and not _is_info(r.get("residual"))
        and not _is_info(r.get("owner"))
        and not _is_info(r.get("action"))
        for r in real
    ) if real else False
    # Soft: allow info-request on exposure/controls for some rows if majority complete
    if real and not schema_ok:
        partial = sum(
            1 for r in real
            if not _is_info(r.get("root_cause"))
            and not _is_info(r.get("event"))
            and not _is_info(r.get("owner"))
            and not _is_info(r.get("action"))
        )
        schema_ok = partial >= max(1, len(real) // 2)
    rows.append({
        "check": "risk_row_schema",
        "status": "PASS" if real and schema_ok else "FAIL",
        "finding": (
            f"{len(real)} register row(s) with root cause/event/exposure/controls/"
            f"residual/owner/action"
            if real and schema_ok
            else _info_request("internal risk rows with full schema")
        ),
        "action": _ROW_RULE,
    })

    classes = {str(r.get("evidence_class") or "") for r in real}
    known_n = sum(1 for r in real if r.get("evidence_class") == "known_weakness")
    unc_n = sum(1 for r in real if r.get("evidence_class") == "uncertainty")
    known_ok = real and ("known_weakness" in classes or "uncertainty" in classes)
    rows.append({
        "check": "known_vs_uncertainty",
        "status": "PASS" if known_ok else "FAIL",
        "finding": (
            f"{known_n} known weakness(es) · {unc_n} uncertainty row(s)"
            if known_ok
            else _info_request("label known weakness vs uncertainty on each row")
        ),
        "action": _KNOWN_RULE,
    })

    quant_n = sum(1 for r in real if r.get("quantified"))
    rem_sized = sum(
        1 for r in remediation
        if isinstance(r, dict)
        and not _is_info(r.get("item"))
        and not _is_info(r.get("cost"))
    )
    quant_ok = quant_n >= 1 or rem_sized >= 1 or (
        real and all(not _is_info(r.get("exposure")) for r in real[:3])
    )
    rows.append({
        "check": "quantified_where_possible",
        "status": "PASS" if quant_ok else "FAIL",
        "finding": (
            f"{quant_n} quantified exposure(s); {rem_sized} remediation cost(s) sized"
            if quant_ok
            else _info_request("quantify exposure or remediation cost where bounded")
        ),
        "action": _REMEDIATE_RULE,
    })

    open_c = int(conflict.get("open_conflict_count") or 0)
    hard = [
        c for c in (conflict.get("conflicts") or [])
        if "manageable" in str(c).lower() or "both known" in str(c).lower()
    ]
    # PASS when no hard open conflicts remain
    recon_ok = open_c == 0 or (
        not hard and bool(conflict.get("resolved"))
    )
    # If manageable+blocker conflict listed and not resolved → FAIL
    if any("manageable" in str(c).lower() for c in (conflict.get("conflicts") or [])):
        if not any("manageable" in str(r).lower() for r in (conflict.get("resolved") or [])):
            # Only fail if ranked still has manageable language
            still = any(
                isinstance(r, dict)
                and _MANAGEABLE_RE.search(f"{r.get('risk')} {r.get('rationale')}")
                and str(r.get("effect") or "") in {"Structure", "Price"}
                for r in ranked
            )
            recon_ok = not still
    rows.append({
        "check": "conflict_reconcile",
        "status": "PASS" if recon_ok else "FAIL",
        "finding": (
            (
                f"Resolved {len(conflict.get('resolved') or [])} conflict(s)"
                if conflict.get("resolved")
                else "No open register conflicts"
            )
            if recon_ok
            else "; ".join(conflict.get("conflicts") or [])
            or _info_request("reconcile conflicting internal risk rows before rank")
        ),
        "action": _CONFLICT_RULE,
    })

    rem_real = [
        r for r in remediation
        if isinstance(r, dict) and not _is_info(r.get("item"))
    ]
    timing_ok = all(
        (
            "pre-completion" in str(r.get("timing") or "").lower()
            or "pre-decision" in str(r.get("timing") or "").lower()
            or "post-close" in str(r.get("timing") or "").lower()
            or "hundred" in str(r.get("timing") or "").lower()
        )
        for r in rem_real
    ) if rem_real else False
    rows.append({
        "check": "pre_vs_post_close",
        "status": "PASS" if timing_ok else "FAIL",
        "finding": (
            f"{len(rem_real)} remediation row(s) with pre-decision vs post-close timing"
            if timing_ok
            else _info_request("pre-decision / pre-completion vs post-close timing")
        ),
        "action": _REMEDIATE_RULE,
    })

    # Affirmative manageable silence only — strip advisory sentences
    scrubbed = re.sub(
        r"(?i)[^.!?\n]*(?:"
        r"do\s+not\s+label|"
        r"must\s+not\s+call|"
        r"ban\s+[^.]*manageable|"
        r"silenc(?:e|ing)"
        r")[^.!?\n]*[.!?]?",
        " ",
        corpus or "",
    )
    for r in list(ranked) + list(register):
        if isinstance(r, dict):
            scrubbed += " " + f"{r.get('risk')} {r.get('rationale')} {r.get('action')}"
    blockers = [
        r for r in ranked
        if isinstance(r, dict)
        and str(r.get("effect") or "") in {"Structure", "Price"}
        and not _is_info(r.get("risk"))
    ]
    silence = bool(_MANAGEABLE_RE.search(scrubbed)) and bool(blockers)
    # Also fail if a Structure/Price row itself still says manageable
    for r in blockers:
        if _MANAGEABLE_RE.search(f"{r.get('risk')} {r.get('rationale')}"):
            silence = True
    rows.append({
        "check": "no_manageable_blocker_silence",
        "status": "PASS" if not silence else "FAIL",
        "finding": (
            "No 'manageable risk' silence over Structure/Price blockers"
            if not silence
            else "Blocker labelled manageable — keep Structure/Price items visible"
        ),
        "action": _MANAGEABLE_RULE,
    })
    return rows


def _questions_from_ir_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("ir_evidence_qa")
        if isinstance(spec.get("ir_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("upstream_registers"):
        out.append(normalize_question({
            "question": (
                "Open Management Quality plus Capital Structure and/or Cash Flow "
                "registers for Internal Risk"
            ),
            "required_records": "Management key-person map + capital/cash priors",
            "decision_effect": "Without priors, day-one inherited risks cannot be validated",
            "priority": "mandatory_pre_decision",
            "owner": "Ops / financial diligence lead",
            "timing": "before IC",
            "closure_test": "upstream_registers QA PASS",
            "interim_treatment": "LIMITED — do not invent internal risk from thin packs",
        }))
    if _qa_fail("risk_row_schema"):
        out.append(normalize_question({
            "question": (
                "Complete internal risk rows with root cause, event, exposure, "
                "controls, residual, owner and action"
            ),
            "required_records": "Ops / mgmt / fin / tech / compliance registers",
            "decision_effect": "Incomplete rows leave residual and ownership unusable",
            "priority": "mandatory_pre_decision",
            "owner": "Internal risk lead",
            "timing": "before IC",
            "closure_test": "risk_row_schema QA PASS",
            "interim_treatment": "LIMITED — withhold incomplete rows from rank",
        }))
    if _qa_fail("known_vs_uncertainty"):
        out.append(normalize_question({
            "question": "Label each row known weakness vs uncertainty (untested ≠ failed)",
            "required_records": "Control-test log + observed failure evidence",
            "decision_effect": "Blurring untested with failed overstates day-one risk",
            "priority": "signing_condition",
            "owner": "Controls diligence lead",
            "timing": "per deal timetable",
            "closure_test": "known_vs_uncertainty QA PASS",
            "interim_treatment": "LIMITED — keep untested separate from observed",
        }))
    if _qa_fail("quantified_where_possible"):
        out.append(normalize_question({
            "question": "Quantify exposure or remediation cost where the bound is known",
            "required_records": "Cash/covenant schedules + remediation budgets",
            "decision_effect": "Unsized internal risks cannot set price or structure",
            "priority": "signing_condition",
            "owner": "Financial diligence lead",
            "timing": "per deal timetable",
            "closure_test": "quantified_where_possible QA PASS",
            "interim_treatment": "LIMITED — keep unsized items on the open register",
        }))
    if _qa_fail("conflict_reconcile"):
        out.append(normalize_question({
            "question": "Reconcile conflicting internal risk rows before ranking",
            "required_records": "Aligned mgmt / fin / controls findings",
            "decision_effect": "Conflicting ranks mis-set price vs structure protections",
            "priority": "mandatory_pre_decision",
            "owner": "Internal risk lead",
            "timing": "before IC",
            "closure_test": "conflict_reconcile QA PASS",
            "interim_treatment": "LIMITED until conflicts closed",
        }))
    if _qa_fail("pre_vs_post_close"):
        out.append(normalize_question({
            "question": "Classify each remediation as pre-decision/pre-completion vs post-close",
            "required_records": "Remediation plan with cost, duration, timing",
            "decision_effect": "Wrong timing leaves CPs or day-one actions missing",
            "priority": "signing_condition",
            "owner": "Deal counsel + ops lead",
            "timing": "before SPA",
            "closure_test": "pre_vs_post_close QA PASS",
            "interim_treatment": "LIMITED — do not assume post-close fixes pre-decision unknowns",
        }))
    if _qa_fail("no_manageable_blocker_silence"):
        out.append(normalize_question({
            "question": "Remove 'manageable risk' labels that silence Structure/Price blockers",
            "required_records": "Ranked register with effect column intact",
            "decision_effect": "Silenced blockers reappear as day-one surprises",
            "priority": "mandatory_pre_decision",
            "owner": "Internal risk lead",
            "timing": "before IC",
            "closure_test": "no_manageable_blocker_silence QA PASS",
            "interim_treatment": "LIMITED — keep blockers visible regardless of narrative",
        }))
    return out


def _quality_reliance(
    *,
    key_persons: list[dict[str, Any]],
    strain: list[dict[str, Any]],
    observed: list[dict[str, Any]],
    tested_register: list[dict[str, Any]],
    management: dict[str, Any] | None,
    capital: dict[str, Any] | None,
    qa_fail: bool = False,
) -> tuple[str, str, str]:
    real_kp = [
        k for k in key_persons
        if isinstance(k, dict) and not _is_info(k.get("person"))
    ]
    real_obs = [
        o for o in observed
        if isinstance(o, dict) and str(o.get("status")) == "Observed" and not _is_info(
            o.get("weakness")
        )
    ]
    strain_known = [
        s for s in strain
        if isinstance(s, dict) and str(s.get("strain") or "") not in {"Unknown", ""}
    ]
    tested_n = sum(
        1 for t in tested_register
        if isinstance(t, dict) and str(t.get("tested") or "") == "Tested"
    )
    untested_n = sum(
        1 for t in tested_register
        if isinstance(t, dict) and "not tested" in str(t.get("tested") or "").lower()
    )

    mq_ok = isinstance(management, dict) and bool(management.get("key_persons"))
    cap_ok = isinstance(capital, dict) and (
        bool(capital.get("facilities")) or bool(capital.get("cash_split"))
    )

    if real_kp and (strain_known or real_obs) and mq_ok:
        quality = "PASS"
    else:
        quality = "REWORK"

    if mq_ok and cap_ok and (tested_n + untested_n) > 0:
        reliance = "READY" if real_kp else "LIMITED"
    elif mq_ok or cap_ok:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    if qa_fail and reliance == "READY":
        reliance = "LIMITED"

    bits = [
        f"{len(real_kp)} key-person exposure(s) from management agent",
        f"{len(strain_known)} financial-strain indicator(s)",
        f"{len(real_obs)} observed control/governance weakness(es)",
        f"{tested_n} control(s) tested, {untested_n} not tested (untested ≠ failed)",
        _ROW_RULE,
        _MANAGEABLE_RULE,
    ]
    if qa_fail:
        bits.append("Open Internal Risk QA FAILs cap READY → LIMITED")
    if not mq_ok:
        bits.append("Management agent key-person map not available — run Management Quality")
    if not cap_ok:
        bits.append("Capital structure schedule thin — liquidity/covenant reliance limited")
    return quality, reliance, _soften_invest(". ".join(bits) + ".")


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_internal_risk_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    legacy_spec: dict[str, Any] | None = None,
    management_spec: dict[str, Any] | None = None,
    capital_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
    operational_spec: dict[str, Any] | None = None,
    regulatory_spec: dict[str, Any] | None = None,
    tech_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    # Soft-fill cash cues from Cash Flow prior into corpus for strain detection
    cf_bits: list[str] = []
    if isinstance(cash_flow_spec, dict):
        snap = cash_flow_spec.get("insight_snapshot")
        if isinstance(snap, str) and snap.strip():
            cf_bits.append(snap.strip())
        for key in ("bridge", "cash_bridge", "working_capital", "liquidity_notes"):
            for row in cash_flow_spec.get(key) or []:
                if isinstance(row, dict):
                    cf_bits.append(
                        " ".join(
                            str(row.get(k) or "")
                            for k in ("line", "item", "finding", "note", "amount")
                            if row.get(k)
                        )
                    )
                elif isinstance(row, str) and row.strip():
                    cf_bits.append(row.strip())
    enriched = "\n".join(x for x in (corpus or "", "\n".join(cf_bits)) if x.strip())

    key_persons = _key_person_exposure(management_spec)
    strain = _financial_strain(corpus=enriched, capital=capital_spec)
    observed, tested_register = _governance_controls(corpus=enriched, legacy=legacy)
    remediation = _remediation_rows(
        key_persons=key_persons,
        strain=strain,
        observed=observed,
        corpus=enriched,
    )
    ranked = _rank_rows(
        key_persons=key_persons,
        strain=strain,
        observed=observed,
        remediation=remediation,
    )
    register = _build_risk_register(
        key_persons=key_persons,
        strain=strain,
        observed=observed,
        tested_register=tested_register,
        remediation=remediation,
        ranked=ranked,
    )
    conflict = _reconcile_conflicts(
        register=register, ranked=ranked, corpus=enriched
    )
    upstream = _upstream_registers(
        management=management_spec,
        capital=capital_spec,
        cash_flow=cash_flow_spec,
        operational=operational_spec,
        regulatory=regulatory_spec,
        tech=tech_spec,
    )
    tech, tech_risks, scale_notes = _legacy_dual_write(
        legacy=legacy,
        observed=observed,
        key_persons=key_persons,
    )
    ir_qa = _ir_evidence_qa(
        register=register,
        ranked=ranked,
        remediation=remediation,
        upstream=upstream,
        conflict=conflict,
        corpus=enriched,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in ir_qa)
    quality, reliance, rationale = _quality_reliance(
        key_persons=key_persons,
        strain=strain,
        observed=observed,
        tested_register=tested_register,
        management=management_spec,
        capital=capital_spec,
        qa_fail=qa_fail,
    )

    real_kp = sum(1 for k in key_persons if isinstance(k, dict) and not _is_info(k.get("person")))
    real_obs = sum(
        1 for o in observed
        if isinstance(o, dict) and str(o.get("status")) == "Observed" and not _is_info(
            o.get("weakness")
        )
    )
    bits = [
        f"Internal Risk for {company}",
        f"{real_kp} key-person exposure(s)",
        f"{real_obs} observed control weakness(es)",
        f"{len(upstream.get('opened') or [])} upstream register(s)",
    ]
    struct_n = sum(
        1 for r in ranked
        if isinstance(r, dict) and str(r.get("effect") or "") == "Structure"
    )
    if struct_n:
        bits.append(f"{struct_n} structure-relevant")

    out = {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "key_person_exposure": key_persons,
        "financial_strain": strain,
        "observed_weaknesses": observed,
        "control_testing": tested_register,
        "remediation": remediation,
        "ranked_effects": ranked,
        "risk_register": register,
        "conflict_reconcile": conflict,
        "upstream_registers": upstream,
        "ir_evidence_qa": ir_qa,
        # Legacy dual-write
        "tech_components": tech,
        "technical_risks": tech_risks,
        "scalability_notes": scale_notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "slug": _AGENT_KEY,
        "track": legacy.get("track") or "E",
        "empty": not real_kp and not real_obs,
    }
    out["questions"] = _questions_from_ir_gaps(out)
    return out


def _llm_internal_risk_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    management_summary: str | None = None,
    capital_summary: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "internal_risk",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
        src_lines = "\n".join(f"[{i}] {s}" for i, s in enumerate(sources[:16], start=1)) or "[1] VDR"
        user = (
            f"Company: {company}\n\nSources:\n{src_lines}\n\n"
            f"Management agent facts (use; do not restate differently):\n"
            f"{(management_summary or 'N/A')[:4000]}\n\n"
            f"Capital structure facts:\n{(capital_summary or 'N/A')[:4000]}\n\n"
            f"Corpus:\n{corpus[:28000]}\n\n"
            "Return JSON with keys:\n"
            "insight_snapshot,\n"
            "key_person_exposure: [{person, what_depends, effect_if_left, "
            "notice_incentives, source}],\n"
            "financial_strain: [{indicator, finding, strain, source}],\n"
            "observed_weaknesses: [{weakness, evidence, status, source}],\n"
            "control_testing: [{control, tested, result, source}],\n"
            "remediation: [{item, cost, duration, timing, source}],\n"
            "ranked_effects: [{risk, effect, rationale, source}],\n"
            "risk_register: [{risk, root_cause, event, exposure, controls, "
            "residual, owner, action, evidence_class, source}],\n"
            "quality_verdict, reliance_verdict, quality_reliance_rationale.\n"
            "Untested is not failed. Do not label blockers as manageable risk. "
            "No invent. No invest or pass."
        )
        return generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    heur: dict[str, Any],
    corpus: str = "",
    management_spec: dict[str, Any] | None = None,
    capital_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
    operational_spec: dict[str, Any] | None = None,
    regulatory_spec: dict[str, Any] | None = None,
    tech_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out = dict(heur)
    for key in (
        "insight_snapshot",
        "key_person_exposure",
        "financial_strain",
        "observed_weaknesses",
        "control_testing",
        "remediation",
        "ranked_effects",
        "risk_register",
        "quality_verdict",
        "reliance_verdict",
        "quality_reliance_rationale",
    ):
        if key in llm and llm[key]:
            out[key] = llm[key]

    key_persons = out.get("key_person_exposure") or []
    strain = out.get("financial_strain") or []
    observed = out.get("observed_weaknesses") or []
    tested_register = out.get("control_testing") or []
    remediation = out.get("remediation") or []
    ranked = out.get("ranked_effects") or []
    register = out.get("risk_register") if isinstance(out.get("risk_register"), list) else []
    if not register:
        register = _build_risk_register(
            key_persons=key_persons if isinstance(key_persons, list) else [],
            strain=strain if isinstance(strain, list) else [],
            observed=observed if isinstance(observed, list) else [],
            tested_register=tested_register if isinstance(tested_register, list) else [],
            remediation=remediation if isinstance(remediation, list) else [],
            ranked=ranked if isinstance(ranked, list) else [],
        )
    conflict = _reconcile_conflicts(
        register=register,
        ranked=ranked if isinstance(ranked, list) else [],
        corpus=corpus,
    )
    upstream = _upstream_registers(
        management=management_spec,
        capital=capital_spec,
        cash_flow=cash_flow_spec,
        operational=operational_spec,
        regulatory=regulatory_spec,
        tech=tech_spec,
    )
    out["risk_register"] = register
    out["conflict_reconcile"] = conflict
    out["upstream_registers"] = upstream
    ir_qa = _ir_evidence_qa(
        register=register,
        ranked=ranked if isinstance(ranked, list) else [],
        remediation=remediation if isinstance(remediation, list) else [],
        upstream=upstream,
        conflict=conflict,
        corpus=corpus,
    )
    out["ir_evidence_qa"] = ir_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in ir_qa)
    qv = out.get("quality_verdict")
    rv = out.get("reliance_verdict")
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            key_persons=key_persons if isinstance(key_persons, list) else [],
            strain=strain if isinstance(strain, list) else [],
            observed=observed if isinstance(observed, list) else [],
            tested_register=tested_register if isinstance(tested_register, list) else [],
            management=management_spec,
            capital=capital_spec,
            qa_fail=qa_fail,
        )
        out["quality_verdict"] = qv
        out["reliance_verdict"] = rv
        out["quality_reliance_rationale"] = rationale
    elif qa_fail and rv == "READY":
        out["reliance_verdict"] = "LIMITED"
        out["quality_reliance_rationale"] = (
            str(out.get("quality_reliance_rationale") or "")
            + " Open Internal Risk QA FAILs cap READY → LIMITED."
        ).strip()

    llm_questions = llm.get("questions") if isinstance(llm.get("questions"), list) else None
    if llm_questions:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q = []
        for raw_q in llm_questions:
            q = normalize_question(raw_q)
            if q:
                filled_q.append(q)
        out["questions"] = filled_q or _questions_from_ir_gaps(out)
    else:
        out["questions"] = _questions_from_ir_gaps(out)
    out["composer"] = "llm_v1"
    return out


def build_internal_risk_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    management_spec: dict[str, Any] | None = None,
    capital_spec: dict[str, Any] | None = None,
    cash_flow_spec: dict[str, Any] | None = None,
    operational_spec: dict[str, Any] | None = None,
    regulatory_spec: dict[str, Any] | None = None,
    tech_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index
    from agetic_cdd_api.services_pipeline import read_agent_output_file

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    def _load(agent_key: str) -> dict[str, Any] | None:
        try:
            disk = read_agent_output_file(deal, agent_key=agent_key) or {}
            spec = disk.get("spec")
            return spec if isinstance(spec, dict) else None
        except Exception:
            return None

    management = management_spec if isinstance(management_spec, dict) else _load("management_quality")
    capital = capital_spec if isinstance(capital_spec, dict) else _load("capital_structure")
    cash_flow = cash_flow_spec if isinstance(cash_flow_spec, dict) else _load("cash_flow")
    operational = (
        operational_spec if isinstance(operational_spec, dict) else _load("operational_risk")
    )
    regulatory = (
        regulatory_spec
        if isinstance(regulatory_spec, dict)
        else _load("regulatory_compliance")
    )
    tech = tech_spec if isinstance(tech_spec, dict) else _load("ip_and_technology")

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_internal_risk_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources

    # Seed corpus with legacy tech risk strings so heuristics have anchors
    seed_bits: list[str] = []
    for tc in legacy.get("tech_components") or []:
        if isinstance(tc, dict) and tc.get("component"):
            seed_bits.append(
                f"{tc['component']} maturity {tc.get('maturity_score')} — "
                f"{tc.get('key_risk') or ''}"
            )
    for note in list(legacy.get("technical_risks") or []) + list(
        legacy.get("scalability_notes") or []
    ):
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    full_corpus = "\n\n".join(x for x in (corpus or "", "\n".join(seed_bits)) if x.strip())

    heur = _heuristic_internal_risk_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        legacy_spec=legacy,
        management_spec=management,
        capital_spec=capital,
        cash_flow_spec=cash_flow,
        operational_spec=operational,
        regulatory_spec=regulatory,
        tech_spec=tech,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    mq_summary = ""
    if management:
        mq_summary = str(management.get("insight_snapshot") or "")
        for kp in (management.get("key_persons") or [])[:6]:
            if isinstance(kp, dict):
                mq_summary += (
                    f"\n- {kp.get('person')}: {kp.get('what_depends')} "
                    f"| {kp.get('notice_incentives')}"
                )
    cap_summary = ""
    if capital:
        cap_summary = str(capital.get("insight_snapshot") or "")
        for c in (capital.get("cash_split") or [])[:4]:
            if isinstance(c, dict):
                cap_summary += f"\n- cash {c.get('bucket')}: {c.get('amount')}"
        for f in (capital.get("facilities") or [])[:4]:
            if isinstance(f, dict):
                cap_summary += (
                    f"\n- facility {f.get('facility')}: "
                    f"covenants {f.get('covenants_headroom')}"
                )
    if cash_flow:
        cap_summary += f"\nCash Flow: {cash_flow.get('insight_snapshot') or ''}"

    llm_raw = _llm_internal_risk_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
        management_summary=mq_summary,
        capital_summary=cap_summary,
    )
    if not llm_raw:
        return heur
    out = _normalise_llm_spec(
        llm_raw,
        heur=heur,
        corpus=full_corpus,
        management_spec=management,
        capital_spec=capital,
        cash_flow_spec=cash_flow,
        operational_spec=operational,
        regulatory_spec=regulatory,
        tech_spec=tech,
    )
    out["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return out


def render_internal_risk_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    key_persons = (
        spec.get("key_person_exposure")
        if isinstance(spec.get("key_person_exposure"), list)
        else []
    )
    strain = (
        spec.get("financial_strain")
        if isinstance(spec.get("financial_strain"), list)
        else []
    )
    observed = (
        spec.get("observed_weaknesses")
        if isinstance(spec.get("observed_weaknesses"), list)
        else []
    )
    tested = (
        spec.get("control_testing")
        if isinstance(spec.get("control_testing"), list)
        else []
    )
    remediation = (
        spec.get("remediation") if isinstance(spec.get("remediation"), list) else []
    )
    ranked = (
        spec.get("ranked_effects")
        if isinstance(spec.get("ranked_effects"), list)
        else []
    )
    tech = (
        spec.get("tech_components")
        if isinstance(spec.get("tech_components"), list)
        else []
    )
    tech_risks = (
        spec.get("technical_risks")
        if isinstance(spec.get("technical_risks"), list)
        else []
    )
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_UPSTREAM_RULE}\n\n")
    parts.append(f"{_KEY_PERSON_RULE}\n\n")
    parts.append(f"{_ROW_RULE}\n\n")
    parts.append(f"{_MANAGEABLE_RULE}\n\n")

    # 1
    parts.append("## 1. Key-Person & Organisational Exposure\n\n")
    parts.append(f"{_KEY_PERSON_RULE}\n\n")
    if key_persons:
        parts.append(_table(
            ["Person", "What depends", "Effect if left", "Notice / incentives", "Source"],
            [
                [
                    _clean(r.get("person"), 40),
                    _clean(r.get("what_depends"), 80),
                    _clean(r.get("effect_if_left"), 80),
                    _clean(r.get("notice_incentives") or _NA, 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in key_persons if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"**{_info_request('key-person map from management agent')}**\n\n"
        )
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Financial Strain\n\n")
    parts.append(f"{_STRAIN_RULE}\n\n")
    if strain:
        parts.append(_table(
            ["Indicator", "Finding from records", "Strain", "Source"],
            [
                [
                    _clean(r.get("indicator"), 40),
                    _clean(r.get("finding"), 140),
                    _clean(r.get("strain"), 20),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in strain if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('financial strain indicators')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Control & Governance Weaknesses\n\n")
    parts.append(f"{_CONTROL_RULE}\n\n")
    parts.append("### Observed weaknesses\n\n")
    if observed:
        parts.append(_table(
            ["Weakness", "Evidence", "Status", "Source"],
            [
                [
                    _clean(r.get("weakness"), 60),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("status"), 20),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in observed if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('observed control / governance weaknesses')}**\n\n")
    parts.append("### Controls tested vs not tested\n\n")
    parts.append("Untested is not failed.\n\n")
    if tested:
        parts.append(_table(
            ["Control", "Tested?", "Result", "Source"],
            [
                [
                    _clean(r.get("control"), 80),
                    _clean(r.get("tested"), 24),
                    _clean(r.get("result"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in tested if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Remediation (cost · time · pre/post)\n\n")
    parts.append(f"{_REMEDIATE_RULE}\n\n")
    if remediation:
        parts.append(_table(
            ["Item", "Cost", "Duration", "Pre-completion vs post-close", "Source"],
            [
                [
                    _clean(r.get("item"), 60),
                    _clean(r.get("cost"), 40),
                    _clean(r.get("duration"), 40),
                    _clean(r.get("timing"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in remediation if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('remediation cost and timing')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Ranked by Price / Structure / First 100 Days\n\n")
    parts.append(f"{_RANK_RULE}\n\n")
    if ranked:
        parts.append(_table(
            ["Risk", "Effect", "Rationale", "Source"],
            [
                [
                    _clean(r.get("risk"), 60),
                    _clean(r.get("effect"), 24),
                    _clean(r.get("rationale"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in ranked if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('ranked internal risks')}**\n\n")
    parts.append("---\n\n")

    # 6 — Unified register + conflict reconcile
    register = (
        spec.get("risk_register") if isinstance(spec.get("risk_register"), list) else []
    )
    conflict = (
        spec.get("conflict_reconcile")
        if isinstance(spec.get("conflict_reconcile"), dict) else {}
    )
    upstream = (
        spec.get("upstream_registers")
        if isinstance(spec.get("upstream_registers"), dict) else {}
    )
    parts.append("## 6. Risk Register & Conflict Reconcile\n\n")
    parts.append(f"{_ROW_RULE}\n\n")
    parts.append(f"{_KNOWN_RULE}\n\n")
    parts.append(f"{_CONFLICT_RULE}\n\n")
    parts.append(
        f"**Upstream opened:** "
        f"{_clean(', '.join(upstream.get('opened') or []) or _NA, 200)}  \n"
        f"**Upstream missing:** "
        f"{_clean(', '.join(upstream.get('missing') or []) or 'None', 200)}\n\n"
    )
    if register:
        parts.append(_table(
            [
                "Risk", "Root cause", "Event", "Exposure", "Controls",
                "Residual", "Owner", "Action", "Class",
            ],
            [
                [
                    _clean(r.get("risk"), 36),
                    _clean(r.get("root_cause"), 50),
                    _clean(r.get("event"), 50),
                    _clean(r.get("exposure"), 50),
                    _clean(r.get("controls"), 40),
                    _clean(r.get("residual"), 36),
                    _clean(r.get("owner"), 36),
                    _clean(r.get("action"), 50),
                    _clean(r.get("evidence_class"), 20),
                ]
                for r in register if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('internal risk register rows')}**\n\n")
    parts.append(_table(
        ["Field", "Value"],
        [
            [
                "Conflicts",
                _clean("; ".join(conflict.get("conflicts") or []) or "None", 220),
            ],
            [
                "Resolved",
                _clean("; ".join(conflict.get("resolved") or []) or "None", 220),
            ],
        ],
    ))
    parts.append("---\n\n")

    # Supporting legacy tech register
    if tech or tech_risks:
        parts.append("## Supporting — Systems / Tech Debt Register\n\n")
        if tech:
            parts.append(_table(
                ["Component", "Maturity", "Key risk"],
                [
                    [
                        _clean(t.get("component"), 40),
                        str(t.get("maturity_score") if t.get("maturity_score") is not None else "—"),
                        _clean(t.get("key_risk"), 80),
                    ]
                    for t in tech if isinstance(t, dict)
                ],
            ))
        for note in tech_risks[:6]:
            if isinstance(note, str) and note.strip():
                parts.append(f"- {_soften_invest(_clean(note, 160))}\n")
        parts.append("\n---\n\n")

    # 7 QA
    ir_qa = (
        spec.get("ir_evidence_qa")
        if isinstance(spec.get("ir_evidence_qa"), list) else []
    )
    parts.append("## 7. Internal Risk Evidence QA\n\n")
    parts.append(
        "QA enforces upstream registers, row schema, known-vs-uncertainty, "
        "quantification, conflict reconcile, pre- vs post-close timing, and no "
        "'manageable risk' silence of blockers.\n\n"
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
                for r in ir_qa
                if isinstance(r, dict)
            ],
        )
        or f"**{_info_request('Internal Risk evidence QA rows')}**\n\n"
    )
    parts.append("---\n\n")

    # 8 Questions
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    parts.append("## 8. Questions and Inputs Required\n\n")
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
        parts.append(
            "None are missing — material Internal Risk gaps are closed, "
            "or no Questions were generated from open QA FAILs.\n\n"
        )
    parts.append("---\n\n")

    # 9 Quality
    parts.append("## 9. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(qv, 30)],
            ["Reliance Verdict", _clean(rv, 30)],
            ["Rationale", _clean(rationale, 460)],
        ],
    ))
    parts.append(f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n")
    parts.append(f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this Internal Risk assessment?\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open Internal Risk QA FAILs cap READY → LIMITED. "
        "Untested controls are not treated as failed. "
        f"{_MANAGEABLE_RULE} "
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
