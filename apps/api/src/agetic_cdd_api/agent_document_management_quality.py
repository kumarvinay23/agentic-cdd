"""Compose DiligenceIQ Management Quality — team vs underwritten plan (prompt book).

Named executives (tenure / scale / plan-vs-actual), incentive & retention
clauses, key-person risk, succession & board, vacancy vs capability vs info
gaps, score evidence, evidence checklist, and Strategic Direction / IC / ESG
cross-check. No investment verdict. Never infer a vacancy from a missing
biography.
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
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_ROSTER_RULE = (
    "Each executive role states name, tenure, remit, relevant prior scale, "
    "and results against target where budgets and actuals exist."
)
_INCENTIVE_RULE = (
    "Notice periods, incentive / equity and retention clauses are extracted "
    "from contracts or HR packs — not assumed."
)
_VACANCY_ENUM_RULE = (
    "Three states only: confirmed vacancy, demonstrated capability gap, "
    "information gap. Never infer a vacancy from a missing biography."
)
_BOARD_SUCCESSION_RULE = (
    "Second-line depth / succession for critical roles and board composition "
    "/ oversight are stated where records exist."
)
_SCORE_EVIDENCE_RULE = (
    "Every management score carries an evidence citation — scores without "
    "evidence are information gaps, not judgments."
)
_CHECKLIST_RULE = (
    "Evidence checklist closes on CVs/bios, employment contracts, incentive / "
    "retention documents and references — or registers each open item."
)
_CROSS_CHECK_RULE = (
    "Management findings are cross-checked with Strategic Direction, IC "
    "Synthesis and ESG where those agents are available."
)

_BOARD_ROW = re.compile(
    r"([A-Z][A-Za-z .'-]{2,50}?)\s+"
    r"((?:Chairman|Managing Director|Independent Director|Non[- ]Executive|"
    r"Executive|Audit Committee|Director)[^|]{0,60}?)"
    r"\s+(Independent|Executive|Non[- ]Executive)",
    re.IGNORECASE,
)
_ESOP = re.compile(
    r"\b(ESOP|equity incentive|stock option|retention bonus|notice period|"
    r"vesting|clawback|non[- ]compete|garden\s+leave)\b"
    r"[^.|]{0,140}",
    re.IGNORECASE,
)
_TENURE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
    re.IGNORECASE,
)
_KEYMAN = re.compile(
    r"(?i)(key[- ](?:man|person)|succession|single[- ]threaded|"
    r"founder[- ]dependent|dependency on)",
)
_PLAN_ACTUAL_CUE = re.compile(
    r"(?i)\b(vs\.?\s*target|against\s+(?:budget|plan|target)|plan\s+vs\.?\s*actual|"
    r"missed\s+target|beat\s+target|delivered\s+(?:below|above)|budget\s+variance)\b"
)
_SCALE_CUE = re.compile(
    r"(?i)\b(scale|revenue|EBITDA|headcount|ARR|GMV|fleet|units?\s+sold|"
    r"listed[- ]corp|prior\s+experience)\b"
)
_CV_CUE = re.compile(r"(?i)\b(CV|curriculum\s+vitae|biography|bio\s+pack|resume)\b")
_CONTRACT_CUE = re.compile(
    r"(?i)\b(employment\s+contract|service\s+agreement|executive\s+contract|"
    r"appointment\s+letter)\b"
)
_REFERENCE_CUE = re.compile(
    r"(?i)\b(reference\s+check|references?\s+(?:taken|obtained)|background\s+check)\b"
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


def _inaccessible(label: str) -> str:
    return f"Document inaccessible: {label}"


def gather_management_quality_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str], list[str]]:
    """Return (corpus, opened_sources, inaccessible_pointers)."""
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "company_management": 0,
        "deal_strategy": 1,
        "operations": 2,
        "financial": 3,
        "legal_esg": 4,
    }

    def _filename_boost(name: str) -> int:
        """Prefer cap-table / securities / org / HR packs that name CEO roles."""
        low = (name or "").lower()
        if re.search(
            r"(?i)cap\s*table|securities?\s*ledger|stockholder|shareholder|"
            r"\borg\b|org(?:anisation|anization)|roster|hr\b|management|"
            r"job\s*title|executive",
            low,
        ):
            return 0
        return 5

    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]
    ranked = sorted(
        docs,
        key=lambda d: (
            _filename_boost(str(d.get("filename") or "")),
            prefer.get(str(d.get("cdl_category") or ""), 9),
            str(d.get("filename") or ""),
        ),
    )
    blobs: list[str] = []
    sources: list[str] = []
    inaccessible: list[str] = []
    for doc in ranked[:18]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        # Prefer HR / corporate / org-chart-like files first for bios.
        try:
            loaded = load_library_document(deal, filename) or {}
        except Exception:
            loaded = {}
            inaccessible.append(_inaccessible(filename))
            continue
        text = str(loaded.get("text") or doc.get("excerpt") or "")
        text = re.sub(r"[■▪●◆□◦\x7f]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            # Pointer exists in index but body could not be opened with usable text.
            if not doc.get("excerpt"):
                inaccessible.append(_inaccessible(f"{filename} (empty extract)"))
            continue
        # Cap-table / ledger packs need a wider window for Job Title columns.
        cap = 24_000 if _filename_boost(filename) == 0 else 14_000
        blobs.append(f"### {filename}\n{text[:cap]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 72_000:
            break
    return "\n\n".join(blobs), sources, inaccessible


def _enrich_executive_row(row: dict[str, str], corpus: str) -> dict[str, str]:
    """Fill tenure / prior scale / plan-vs-actual from corpus near the name."""
    name = str(row.get("name") or "")
    if not name or name == _NA:
        return row
    idx = corpus.lower().find(name.lower())
    window = corpus[idx : idx + 280] if idx >= 0 else ""
    if window:
        tm = _TENURE.search(window)
        if tm and (row.get("tenure") in (None, "", _NA) or str(row.get("tenure")).startswith("N/A")):
            row["tenure"] = f"{tm.group(1)} years {_DOC_CITE}"
        exp = re.search(
            r"(?:Prior Experience|previously|formerly)\s*[:\-]?\s*"
            r"([A-Za-z0-9][^.\n|]{8,120})",
            window,
            re.I,
        )
        if exp and (
            row.get("prior_delivery") in (None, "", _NA)
            or str(row.get("prior_delivery")).startswith("N/A")
        ):
            row["prior_delivery"] = _clean(exp.group(1), 120) + f" {_DOC_CITE}"
        if _SCALE_CUE.search(window) and (
            row.get("relevant_scale") in (None, "", _NA)
            or str(row.get("relevant_scale")).startswith("N/A")
            or str(row.get("relevant_scale") or "").startswith("Information")
        ):
            scale_sent = next(
                (s for s in _sentences(window) if _SCALE_CUE.search(s)),
                window[:120],
            )
            row["relevant_scale"] = _clean(scale_sent, 120) + f" {_DOC_CITE}"
        if _PLAN_ACTUAL_CUE.search(window):
            pa = next(
                (s for s in _sentences(window) if _PLAN_ACTUAL_CUE.search(s)),
                None,
            )
            if pa:
                row["vs_target"] = _clean(pa, 120) + f" {_DOC_CITE}"

    # Corpus-level plan vs actual if still empty
    if row.get("vs_target") in (None, "", _NA) or str(row.get("vs_target")).startswith("N/A"):
        for s in _sentences(corpus):
            if _PLAN_ACTUAL_CUE.search(s) and (
                name.split()[0].lower() in s.lower()
                or str(row.get("role") or "").lower() in s.lower()
            ):
                row["vs_target"] = _clean(s, 120) + f" {_DOC_CITE}"
                break
    if row.get("vs_target") in (None, "", _NA) or str(row.get("vs_target")).startswith("N/A"):
        row["vs_target"] = _info_request(
            f"plan vs actual / budget delivery for {row.get('role') or name}"
        )
    if row.get("relevant_scale") in (None, "", _NA) or str(
        row.get("relevant_scale") or ""
    ).startswith(("N/A", "Information")):
        if row.get("prior_delivery") not in (None, "", _NA) and not str(
            row.get("prior_delivery")
        ).startswith("N/A"):
            row["relevant_scale"] = row["prior_delivery"]
        else:
            row["relevant_scale"] = _info_request(
                f"relevant prior scale for {row.get('role') or name}"
            )
    row.setdefault("notes", _ROSTER_RULE)
    return row


def _executives_from_f06(f06: dict[str, Any] | None, corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(f06, dict):
        for item in f06.get("c_suite") or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = _strip_unsourced_title(str(item.get("name") or "")).strip()
            role = _strip_unsourced_title(str(item.get("role") or "Executive")).strip() or "Executive"
            if not name or not _plausible_person_name(name):
                continue
            # Securities-ledger Job Titles (Ex-SVP G&A) are not an HR roster role.
            if re.search(r"(?i)\b(?:ex-?svp|ex-employee|option.?holder)\b", role):
                role = "Executive"
            rows.append({
                "name": name,
                "role": role,
                "tenure": _NA,
                "remit": role if role != "Executive" else "Senior operating role",
                "prior_delivery": _NA,
                "relevant_scale": _NA,
                "vs_target": _NA,
                "source": _DOC_CITE,
                "criticality": str(item.get("criticality") or ""),
                "replaceability": str(item.get("replaceability") or ""),
                "notes": _ROSTER_RULE,
            })
    if rows:
        return [_enrich_executive_row(r, corpus) for r in rows[:10]]

    # Fallback: CEO/CFO/CTO/CHRO labels in corporate pack / securities ledger.
    # Scan a wide window — cap-table Job Title columns often sit past page 1.
    seen: set[str] = set()
    pack = corpus[:160_000]

    def _norm_person(raw: str) -> str:
        name = _strip_unsourced_title(_clean(raw, 40))
        name = re.sub(
            r"(?i)\b(?:yes|no)\b(?:\s+employee)?\b|\bemployee\b(?:\s+(?:yes|no))?\b",
            " ",
            name,
        )
        return re.sub(r"\s{2,}", " ", name).strip(" ,.;")

    # Prefer "Name … CEO … Yes/No … shares" (name before title) — never
    # "CEO No Employee …" where Employee is a Yes/No column.
    for m in re.finditer(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+){1,3})\s*[,:]?\s*"
        r"(CEO|CFO|CTO|COO|CHRO|Founder|Chief\s+Executive(?:\s+Officer)?)\b"
        r"(?:\s+(?:Yes|No)\b)?",
        pack,
    ):
        name, role = _norm_person(m.group(1)), m.group(2)
        if not _plausible_person_name(name) or name.lower() in seen:
            continue
        seen.add(name.lower())
        role_norm = "CEO" if re.search(r"(?i)chief\s+executive|^CEO$", role) else role
        rows.append({
            "name": name,
            "role": role_norm,
            "tenure": _NA,
            "remit": role_norm,
            "prior_delivery": _NA,
            "relevant_scale": _NA,
            "vs_target": _NA,
            "source": _DOC_CITE,
            "criticality": "5" if role_norm in {"CEO", "Founder"} else "4",
            "replaceability": "1" if role_norm in {"CEO", "Founder"} else "",
            "notes": _ROSTER_RULE,
        })
        if len(rows) >= 8:
            break
    # Title-then-name only when the next tokens are not Yes/No Employee.
    if not rows:
        for m in re.finditer(
            r"\b(CEO|CFO|CTO|COO|CHRO|Founder)\b\s*(?:&|and)?\s*"
            r"(?:Founder)?\s*"
            r"(?!Yes\b|No\b|Employee\b)"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+){1,3})",
            pack,
        ):
            role, name = m.group(1), _norm_person(m.group(2))
            if not _plausible_person_name(name) or name.lower() in seen:
                continue
            seen.add(name.lower())
            rows.append({
                "name": name,
                "role": role,
                "tenure": _NA,
                "remit": role,
                "prior_delivery": _NA,
                "relevant_scale": _NA,
                "vs_target": _NA,
                "source": _DOC_CITE,
                "criticality": "5" if role in {"CEO", "Founder"} else "4",
                "replaceability": "",
                "notes": _ROSTER_RULE,
            })
            if len(rows) >= 8:
                break
    # Ownership narrative already composed: "Ben Parry (CEO) 10,000,010…"
    if not rows:
        for m in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+){1,3})\s*\(\s*"
            r"(CEO|CFO|CTO|COO|Founder|Chief\s+Executive(?:\s+Officer)?)\s*\)",
            pack,
        ):
            name, role = _norm_person(m.group(1)), m.group(2)
            if not _plausible_person_name(name) or name.lower() in seen:
                continue
            role_norm = "CEO" if re.search(r"(?i)chief\s+executive|^CEO$", role) else role
            seen.add(name.lower())
            rows.append({
                "name": name,
                "role": role_norm,
                "tenure": _NA,
                "remit": role_norm,
                "prior_delivery": _NA,
                "relevant_scale": _NA,
                "vs_target": _NA,
                "source": _DOC_CITE,
                "criticality": "5" if role_norm in {"CEO", "Founder"} else "4",
                "replaceability": "1" if role_norm in {"CEO", "Founder"} else "",
                "notes": _ROSTER_RULE,
            })
            if len(rows) >= 8:
                break
    # Controlling shareholder from securities ledger / cap table when no HR roster.
    if not rows:
        for m in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+)+)\b[^%]{0,120}"
            r"(\d{1,2}\.\d{1,2})\s*%\s+of\s+(?:common|all\s+outstanding)",
            pack,
        ):
            name = _strip_unsourced_title(m.group(1))
            try:
                pct = float(m.group(2))
            except ValueError:
                continue
            if pct < 50 or not _plausible_person_name(name) or name.lower() in seen:
                continue
            # Prefer CEO Job Title beside the holder when the ledger states it.
            title_m = re.search(
                rf"(?i)\b{re.escape(name)}\b[^\n]{{0,40}}\b(CEO|Founder)\b",
                pack,
            )
            role = title_m.group(1).upper() if title_m else "CEO"
            seen.add(name.lower())
            rows.append({
                "name": name,
                "role": role,
                "tenure": _NA,
                "remit": "Controlling shareholder / chief executive",
                "prior_delivery": _NA,
                "relevant_scale": _NA,
                "vs_target": _NA,
                "source": _DOC_CITE,
                "criticality": "5",
                "replaceability": "1",
                "notes": _ROSTER_RULE,
            })
            break
    return [_enrich_executive_row(r, corpus) for r in rows]


_UNSOURCED_TITLE_RE = re.compile(
    r"(?i)\s*[\(\[]?\s*(?:ex-?)?(?:svp|senior\s+vice\s+president|vice\s+president|"
    r"commercial\s+driver|driver|option.?holder|ex-employee)"
    r"(?:\s*(?:[,/&]|of|g&a|ga|finance|ops|operations)[^)\]]*)?[\)\]]?"
)
_PLACEHOLDER_PERSON_RE = re.compile(
    r"(?i)^(?:named in hr\b|named in (?:the\s+)?corporate pack\b|key person|n/?a|"
    r"information\s+request|no\s+employee|yes\s+employee|employee\s+status|"
    r"job\s+title|shares?\s+outstanding|title\s+employee)\b"
)
# Person names only — reject sentence fragments like
# "Compost Crew is led by a proven (CEO)".
_PERSON_NAME_RE = re.compile(
    r"^[A-Z][a-z]+(?:\s+[A-Z][a-z'-]+){1,3}$"
)
_PERSON_BAD_TOKEN_RE = re.compile(
    r"(?i)\b(?:is|are|was|were|led|by|the|a|an|and|or|for|with|from|of|"
    r"proven|company|crew|inc|llc|ltd|limited|owner|buyer|yes|no|employee|"
    r"status|shares?|outstanding|title|certificate)\b"
)
# Cap-table Employee column values that must never become the CEO name.
_EMPLOYMENT_STATUS_NAME_RE = re.compile(
    r"(?i)^(?:yes|no)(?:\s+employee)?$|^employee(?:\s+(?:yes|no))?$"
)


def _strip_unsourced_title(text: str) -> str:
    """Drop ledger Job Titles (Ex-SVP G&A, Commercial Driver) that are not HR roles."""
    t = _UNSOURCED_TITLE_RE.sub("", str(text or ""))
    t = re.sub(r"(?i)\bCommercial\s+Driver\b", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip(" ,;|-")
    t = re.sub(r"\(\s*\)", "", t).strip()
    return t


def _plausible_person_name(text: str) -> bool:
    """True when ``text`` looks like 'First Last' (optional role paren), not a sentence."""
    raw = str(text or "").strip()
    if not raw or _PLACEHOLDER_PERSON_RE.match(raw):
        return False
    base = re.sub(r"\s*\([^)]*\)\s*$", "", raw).strip()
    base = _strip_unsourced_title(base)
    # Strip Yes/No Employee flags that sit beside Job Title in the ledger.
    base = re.sub(
        r"(?i)\b(?:yes|no)\b(?:\s+employee)?\b|\bemployee\b(?:\s+(?:yes|no))?\b",
        " ",
        base,
    )
    base = re.sub(r"\s{2,}", " ", base).strip(" ,.;")
    if not base or _EMPLOYMENT_STATUS_NAME_RE.match(base):
        return False
    if not _PERSON_NAME_RE.match(base):
        return False
    if _PERSON_BAD_TOKEN_RE.search(base):
        return False
    return True


def _key_person_rows(
    executives: list[dict[str, str]],
    corpus: str,
    f06: dict[str, Any] | None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    sents = _sentences(corpus)
    key_sents = _pick_sentences(
        sents,
        keywords=("key-man", "key person", "succession", "founder", "dependency", "attrition"),
        limit=6,
    )
    # Prefer a named CEO / founder from the roster over the HR placeholder.
    fallback_person = ""
    for ex in executives:
        name = _strip_unsourced_title(str(ex.get("name") or "")).strip()
        role = _strip_unsourced_title(str(ex.get("role") or "")).strip()
        if not _plausible_person_name(name):
            continue
        if re.search(r"(?i)\b(?:ceo|founder|chairman|managing\s+director)\b", role):
            fallback_person = f"{name}" + (f" ({role})" if role else "")
            break
    if not fallback_person and executives:
        for ex in executives:
            name = _strip_unsourced_title(str(ex.get("name") or "")).strip()
            role = _strip_unsourced_title(str(ex.get("role") or "")).strip()
            if _plausible_person_name(name):
                fallback_person = f"{name}" + (f" ({role})" if role else "")
                break
    # Last resort: controlling shareholder named beside a majority % in this corpus.
    if not fallback_person:
        for m in re.finditer(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z'-]+)+)\b[^%]{0,80}"
            r"(\d{1,2}\.\d{1,2})\s*%\s+of\s+(?:common|all\s+outstanding)",
            corpus[:80_000],
        ):
            name = _strip_unsourced_title(m.group(1)).strip()
            try:
                pct = float(m.group(2))
            except ValueError:
                continue
            if pct >= 50 and _plausible_person_name(name):
                fallback_person = f"{name} (CEO)"
                break

    # High criticality / low replaceability from F-06
    if isinstance(f06, dict):
        for item in f06.get("c_suite") or []:
            if not isinstance(item, dict):
                continue
            try:
                crit = int(item.get("criticality") or 0)
                rep = int(item.get("replaceability") or 99)
            except (TypeError, ValueError):
                crit, rep = 0, 99
            if crit >= 5 or (crit >= 4 and rep <= 2):
                name = _strip_unsourced_title(str(item.get("name") or "")).strip()
                role = _strip_unsourced_title(str(item.get("role") or "")).strip()
                if not _plausible_person_name(name):
                    continue
                break_if = (
                    f"Approvals, external relationships and strategic direction "
                    f"tied to {role or 'this role'} — continuity risk if {name} exits"
                )
                person = f"{name} ({role})" if role else name
                rows.append({
                    "person": person,
                    "what_depends": break_if,
                    "notice_incentives": _NA,
                    "source": _DOC_CITE,
                })
    for sent in key_sents:
        if any(sent[:60].lower() in r["what_depends"].lower() for r in rows):
            continue
        person = ""
        for ex in executives:
            name = _strip_unsourced_title(str(ex.get("name") or "")).strip()
            role = _strip_unsourced_title(str(ex.get("role") or "")).strip()
            if _plausible_person_name(name) and name.split()[0].lower() in sent.lower():
                person = f"{name} ({role})" if role else name
                break
        if not person:
            person = fallback_person
        if not person or _PLACEHOLDER_PERSON_RE.match(person):
            continue  # never emit the HR placeholder into retention CPs
        if not _plausible_person_name(person):
            continue
        rows.append({
            "person": person,
            "what_depends": _clean(sent, 200),
            "notice_incentives": _NA,
            "source": _DOC_CITE,
        })
        if len(rows) >= 6:
            break

    # Incentives / notice from corpus when present
    incentives: list[str] = []
    for m in _ESOP.finditer(corpus[:40_000]):
        incentives.append(_clean(m.group(0), 140))
        if len(incentives) >= 3:
            break
    if incentives and rows:
        rows[0]["notice_incentives"] = "; ".join(incentives) + f" {_DOC_CITE}"
    elif rows:
        for r in rows:
            if r["notice_incentives"] == _NA:
                r["notice_incentives"] = _info_request(
                    "notice periods, equity / ESOP and retention arrangements"
                )
                break

    # Always flag the CEO / controlling shareholder when the roster names one —
    # even if the pack never uses the words "key-person" / "succession".
    if not rows and fallback_person and not _PLACEHOLDER_PERSON_RE.match(fallback_person):
        short = fallback_person.split("(", 1)[0].strip() or fallback_person
        rows.append({
            "person": fallback_person,
            "what_depends": (
                f"Strategic direction, customer relationships and equity control "
                f"concentrated with {short} — continuity risk without retention / succession"
            ),
            "notice_incentives": _info_request(
                "notice periods, equity / ESOP and retention arrangements"
            ),
            "source": _DOC_CITE,
        })
    return rows[:6]


def _board_rows(corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    block = corpus
    idx = re.search(r"Board of Directors", corpus, re.I)
    if idx:
        block = corpus[idx.start() : idx.start() + 1200]
    for m in _BOARD_ROW.finditer(block):
        name = _clean(m.group(1), 40)
        role = _clean(m.group(2), 60)
        indep = _clean(m.group(3), 20)
        key = name.lower()
        if key in seen or len(name.split()) < 2:
            continue
        seen.add(key)
        rows.append({
            "name": name,
            "role": role,
            "independence": indep,
            "source": _DOC_CITE,
        })
        if len(rows) >= 8:
            break
    return rows


def _succession_rows(
    executives: list[dict[str, str]],
    f06: dict[str, Any] | None,
    corpus: str,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    gaps = (f06 or {}).get("succession_gaps") if isinstance(f06, dict) else []
    gap_text = " ".join(str(g) for g in (gaps or []) if g)
    for ex in executives[:6]:
        status = "Not evidenced in data room"
        if _KEYMAN.search(gap_text) and ex.get("criticality") in {"5", "4"}:
            status = "Succession gap flagged in HR pack"
        elif "succession" in corpus.lower() and ex.get("role", "").upper() in {"CEO", "CTO", "CFO"}:
            # Look near the name
            if re.search(
                rf"{re.escape(ex['name'])}.{{0,80}}(?:succession|no clear successor|high risk)",
                corpus,
                re.I | re.DOTALL,
            ):
                status = "High succession risk noted near role"
            else:
                status = "Role present; successor not named in pack"
        rows.append({
            "role": ex.get("role") or "Role",
            "incumbent": ex.get("name") or _NA,
            "second_line": _NA,
            "succession_status": status,
            "source": _DOC_CITE,
        })
    if not rows:
        rows.append({
            "role": _NA,
            "incumbent": _NA,
            "second_line": _NA,
            "succession_status": _info_request("succession map / org chart with deputies"),
            "source": _NA,
        })
    return rows


def _gap_states(
    executives: list[dict[str, str]],
    f06: dict[str, Any] | None,
    corpus: str,
) -> dict[str, list[dict[str, str]]]:
    """confirmed_vacancy | capability_gap | information_gap — never invent vacancy from missing bio."""
    confirmed: list[dict[str, str]] = []
    capability: list[dict[str, str]] = []
    information: list[dict[str, str]] = []

    # Confirmed vacancy only if pack says vacant / open / hiring for role
    for m in re.finditer(
        r"\b((?:CEO|CFO|CTO|COO|CHRO|VP[\w\s/-]{0,30}|Head of [\w\s]{2,30}))\b"
        r".{0,40}?\b(vacant|open role|to be hired|hiring|unfilled)\b",
        corpus[:40_000],
        re.I | re.DOTALL,
    ):
        confirmed.append({
            "item": _clean(m.group(1), 60),
            "evidence": _clean(m.group(0), 160),
            "hiring_cost_eligible": "yes — confirmed vacancy",
            "source": _DOC_CITE,
        })

    for gap in (f06 or {}).get("succession_gaps") or []:
        if not isinstance(gap, str) or not gap.strip():
            continue
        low = gap.lower()
        if any(k in low for k in ("vacant", "open role", "unfilled", "to be hired")):
            confirmed.append({
                "item": _clean(gap, 120),
                "evidence": gap,
                "hiring_cost_eligible": "yes — confirmed vacancy",
                "source": _DOC_CITE,
            })
        elif any(k in low for k in ("attrition", "gap", "weak", "below", "risk", "morale", "continuity")):
            capability.append({
                "item": _clean(gap, 120),
                "evidence": gap,
                "hiring_cost_eligible": "yes — demonstrated capability gap",
                "source": _DOC_CITE,
            })

    # Information gaps: missing tenure / prior delivery / incentives — NOT vacancies
    missing_bio = [e for e in executives if e.get("prior_delivery") == _NA or e.get("tenure") == _NA]
    if missing_bio:
        names = ", ".join(e["name"] for e in missing_bio[:4] if e.get("name"))
        information.append({
            "item": f"Full biographies / tenure / delivery vs target for: {names or 'named executives'}",
            "evidence": "Fields not present in opened packs — not evidence of a vacancy",
            "hiring_cost_eligible": "no — information gap only",
            "source": _DOC_CITE,
        })
    information.append({
        "item": "Notice periods, ESOP vesting and retention arrangements by executive",
        "evidence": "Not fully stated for each critical role",
        "hiring_cost_eligible": "no — information gap only",
        "source": _NA,
    })
    if not confirmed and not capability and not information:
        information.append({
            "item": "Management assessment inputs",
            "evidence": "Limited leadership extract in current VDR bind",
            "hiring_cost_eligible": "no — information gap only",
            "source": _NA,
        })
    return {
        "confirmed_vacancies": confirmed[:6],
        "capability_gaps": capability[:6],
        "information_gaps": information[:6],
    }


def _incentive_retention_clauses(
    corpus: str,
    executives: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in _ESOP.finditer(corpus[:50_000]):
        snippet = _clean(m.group(0), 160)
        kind = "Incentive / retention"
        low = snippet.lower()
        if "notice" in low:
            kind = "Notice period"
        elif "esop" in low or "option" in low or "equity" in low or "vest" in low:
            kind = "Equity / ESOP"
        elif "retention" in low or "bonus" in low:
            kind = "Retention / bonus"
        elif "non-compete" in low or "non compete" in low or "clawback" in low:
            kind = "Restrictive covenant / clawback"
        person = "Pack-level (not named to a role)"
        for ex in executives:
            if ex.get("name") and ex["name"].split()[0].lower() in low:
                person = f"{ex['name']} ({ex.get('role') or 'Exec'})"
                break
        rows.append({
            "person_or_scope": person,
            "clause_kind": kind,
            "extract": snippet,
            "source": _DOC_CITE,
            "notes": _INCENTIVE_RULE,
        })
        if len(rows) >= 8:
            break
    if not rows:
        rows.append({
            "person_or_scope": _info_request("named executive or pack-level"),
            "clause_kind": "Notice / equity / retention",
            "extract": _info_request(
                "notice periods, ESOP vesting and retention clauses from contracts"
            ),
            "source": _NA,
            "notes": _INCENTIVE_RULE,
        })
    return rows[:8]


def _evidence_checklist(
    *,
    corpus: str,
    sources: list[str],
    executives: list[dict[str, str]],
    incentives: list[dict[str, str]],
) -> list[dict[str, str]]:
    src_blob = " ".join(sources).lower() + " " + (corpus[:8_000].lower())
    items = [
        (
            "CVs / biographies",
            bool(_CV_CUE.search(corpus) or any("hr" in s.lower() or "bio" in s.lower() for s in sources))
            and any(
                e.get("prior_delivery") not in (None, "", _NA)
                and not str(e.get("prior_delivery")).startswith("N/A")
                for e in executives
            ),
            "Opened biography / HR pack with prior delivery",
        ),
        (
            "Employment / service contracts",
            bool(_CONTRACT_CUE.search(corpus) or "contract" in src_blob),
            "Employment or service agreements for CXOs",
        ),
        (
            "Incentive / retention documents",
            any(
                isinstance(r, dict)
                and not str(r.get("extract") or "").startswith("Information")
                for r in incentives
            ),
            "ESOP / retention / notice extracts",
        ),
        (
            "References / background checks",
            bool(_REFERENCE_CUE.search(corpus)),
            "Reference or background-check evidence",
        ),
    ]
    rows: list[dict[str, str]] = []
    for label, closed, detail in items:
        rows.append({
            "item": label,
            "status": "CLOSED" if closed else "OPEN",
            "detail": detail if closed else _info_request(detail),
            "source": _DOC_CITE if closed else _NA,
            "notes": _CHECKLIST_RULE,
        })
    return rows


def _score_evidence(
    *,
    executives: list[dict[str, str]],
    f06: dict[str, Any] | None,
    key_persons: list[dict[str, str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    org = None
    if isinstance(f06, dict) and f06.get("org_risk_score") is not None:
        org = f06.get("org_risk_score")
        rows.append({
            "score": "org_risk_score",
            "value": str(org),
            "evidence": (
                f"F-06 org risk score {org}; "
                + (
                    f"{len(key_persons)} key-person row(s)"
                    if key_persons else "no key-person rows yet"
                )
            ),
            "source": _DOC_CITE,
            "notes": _SCORE_EVIDENCE_RULE,
        })
    for ex in executives[:8]:
        if not isinstance(ex, dict) or not ex.get("name"):
            continue
        crit = ex.get("criticality")
        rep = ex.get("replaceability")
        if not crit and not rep:
            continue
        bits = []
        if crit:
            bits.append(f"criticality={crit}")
        if rep:
            bits.append(f"replaceability={rep}")
        evidence_bits = [
            b for b in (
                ex.get("tenure"),
                ex.get("relevant_scale") or ex.get("prior_delivery"),
                ex.get("vs_target"),
            )
            if b and b != _NA and not str(b).startswith(("N/A", "Information"))
        ]
        rows.append({
            "score": f"{ex.get('role') or 'Exec'} criticality/replaceability",
            "value": "; ".join(bits),
            "evidence": (
                "; ".join(evidence_bits)
                if evidence_bits
                else _info_request(f"evidence supporting scores for {ex.get('name')}")
            ),
            "source": ex.get("source") or _DOC_CITE,
            "notes": _SCORE_EVIDENCE_RULE,
        })
    if not rows:
        rows.append({
            "score": _info_request("management score"),
            "value": _NA,
            "evidence": _info_request("evidence citation for each score"),
            "source": _NA,
            "notes": _SCORE_EVIDENCE_RULE,
        })
    return rows[:10]


def _cross_check_strategy_ic_esg(
    *,
    strategy_spec: dict[str, Any] | None,
    ic_spec: dict[str, Any] | None,
    esg_spec: dict[str, Any] | None,
    executives: list[dict[str, str]],
) -> dict[str, Any]:
    present = {
        "strategic_direction": isinstance(strategy_spec, dict) and bool(strategy_spec),
        "ic_synthesis": isinstance(ic_spec, dict) and bool(ic_spec),
        "esg": isinstance(esg_spec, dict) and bool(esg_spec),
    }
    aligned: list[str] = []
    conflicts: list[str] = []
    names = {
        str(e.get("name") or "").lower()
        for e in executives if isinstance(e, dict) and e.get("name")
    }

    def _scan(label: str, spec: dict[str, Any] | None) -> None:
        if not isinstance(spec, dict) or not spec:
            return
        blob_parts: list[str] = []
        for key in (
            "insight_snapshot", "assessment_read", "summary",
            "management_notes", "key_risks", "findings",
        ):
            val = spec.get(key)
            if isinstance(val, str):
                blob_parts.append(val)
            elif isinstance(val, list):
                blob_parts.extend(str(x) for x in val[:8])
        blob = " ".join(blob_parts).lower()
        if not blob.strip():
            aligned.append(f"{label} present — no overlapping management text to compare yet.")
            return
        hit = any(n and n.split()[0] in blob for n in names if n)
        if hit:
            aligned.append(f"{label} references overlapping management names.")
        else:
            aligned.append(f"{label} present — no named-executive overlap yet.")
        if re.search(r"(?i)\b(vacant|vacancy|weak management|unfilled)\b", blob):
            # Only conflict if MQ does not have confirmed vacancy
            conflicts.append(
                f"{label} cites vacancy/weak-management language — verify against MQ vacancy enum"
            )

    _scan("Strategic Direction", strategy_spec)
    _scan("IC Synthesis", ic_spec)
    _scan("ESG", esg_spec)

    return {
        "strategic_direction_present": present["strategic_direction"],
        "ic_synthesis_present": present["ic_synthesis"],
        "esg_present": present["esg"],
        "aligned": aligned[:6],
        "conflicts": conflicts[:6],
        "notes": (
            f"{_CROSS_CHECK_RULE} "
            + (
                f"{len(conflicts)} conflict(s)."
                if conflicts
                else (
                    "No conflicts detected."
                    if any(present.values())
                    else "Strategic Direction / IC Synthesis / ESG not available in this run."
                )
            )
        ),
        "source": _DOC_CITE if any(present.values()) else _NA,
    }


def _mq_evidence_qa(
    *,
    executives: list[dict[str, str]],
    incentives: list[dict[str, str]],
    confirmed: list[dict[str, str]],
    capability: list[dict[str, str]],
    info_gaps: list[dict[str, str]],
    succession: list[dict[str, str]],
    board: list[dict[str, str]],
    scores: list[dict[str, str]],
    checklist: list[dict[str, str]],
    cross: dict[str, Any],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    roster_ok = sum(
        1 for e in executives
        if isinstance(e, dict)
        and e.get("name")
        and e.get("tenure") not in (None, "", _NA)
        and not str(e.get("tenure")).startswith("N/A")
    ) >= 1 and len(executives) >= 2
    # Also require scale or vs_target attempt on at least one
    scale_ok = any(
        isinstance(e, dict)
        and (
            (
                e.get("relevant_scale")
                and not str(e.get("relevant_scale")).startswith(("N/A", "Information"))
            )
            or (
                e.get("vs_target")
                and not str(e.get("vs_target")).startswith(("N/A", "Information"))
            )
        )
        for e in executives
    )
    rows.append({
        "check": "role_roster_tenure_scale_plan_actual",
        "status": "PASS" if roster_ok and scale_ok else "FAIL",
        "finding": (
            f"{len(executives)} executives with tenure/scale/plan-vs-actual coverage"
            if roster_ok and scale_ok
            else _info_request("roster with tenure, prior scale and plan-vs-actual")
        ),
        "action": _ROSTER_RULE,
    })

    inc_ok = any(
        isinstance(r, dict)
        and not str(r.get("extract") or "").startswith("Information")
        for r in incentives
    )
    rows.append({
        "check": "incentive_retention_clauses",
        "status": "PASS" if inc_ok else "FAIL",
        "finding": (
            f"{sum(1 for r in incentives if isinstance(r, dict))} incentive/retention extract(s)"
            if inc_ok
            else _info_request("notice / ESOP / retention clause extracts")
        ),
        "action": _INCENTIVE_RULE,
    })

    # Vacancy enum discipline: FAIL if any confirmed vacancy lacks evidence, or
    # if information_gaps claim hiring_cost_eligible yes
    bad_enum = any(
        isinstance(g, dict)
        and "information gap" in str(g.get("hiring_cost_eligible") or "").lower()
        and str(g.get("hiring_cost_eligible") or "").lower().startswith("yes")
        for g in info_gaps
    ) or any(
        isinstance(g, dict)
        and "vacancy" in str(g.get("item") or "").lower()
        and "missing" in str(g.get("evidence") or "").lower()
        and "bio" in str(g.get("evidence") or "").lower()
        for g in confirmed
    )
    rows.append({
        "check": "vacancy_capability_info_enum",
        "status": "FAIL" if bad_enum else "PASS",
        "finding": (
            "Vacancy enum corrupted — missing bio treated as vacancy"
            if bad_enum
            else (
                f"{len(confirmed)} vacancy / {len(capability)} capability / "
                f"{len(info_gaps)} info-gap (bios ≠ vacancies)"
            )
        ),
        "action": _VACANCY_ENUM_RULE,
    })

    board_ok = bool(board) and any(
        isinstance(r, dict) and r.get("name")
        and not str(r.get("name")).startswith("Information")
        for r in board
    )
    succ_ok = any(
        isinstance(r, dict)
        and r.get("incumbent")
        and not str(r.get("incumbent")).startswith("N/A")
        for r in succession
    )
    rows.append({
        "check": "board_succession_tables",
        "status": "PASS" if board_ok or succ_ok else "FAIL",
        "finding": (
            f"Board {len(board)} / succession {len(succession)} row(s)"
            if board_ok or succ_ok
            else _info_request("board composition and succession / deputy map")
        ),
        "action": _BOARD_SUCCESSION_RULE,
    })

    score_ok = any(
        isinstance(r, dict)
        and r.get("evidence")
        and not str(r.get("evidence")).startswith("Information")
        for r in scores
    )
    rows.append({
        "check": "score_evidence",
        "status": "PASS" if score_ok else "FAIL",
        "finding": (
            f"{sum(1 for r in scores if isinstance(r, dict))} score(s) with evidence"
            if score_ok
            else _info_request("evidence citation for each management score")
        ),
        "action": _SCORE_EVIDENCE_RULE,
    })

    closed_n = sum(
        1 for r in checklist
        if isinstance(r, dict) and r.get("status") == "CLOSED"
    )
    rows.append({
        "check": "evidence_checklist_closure",
        "status": "PASS" if closed_n >= 2 else "FAIL",
        "finding": (
            f"Checklist {closed_n}/{len(checklist)} CLOSED"
            if closed_n >= 2
            else _info_request("close CVs / contracts / incentives / references checklist")
        ),
        "action": _CHECKLIST_RULE,
    })

    cross_ok = (
        (
            cross.get("strategic_direction_present")
            or cross.get("ic_synthesis_present")
            or cross.get("esg_present")
        )
        and not cross.get("conflicts")
    )
    rows.append({
        "check": "strategy_ic_esg_cross_check",
        "status": "PASS" if cross_ok else "FAIL",
        "finding": (
            "; ".join(cross.get("aligned") or [])[:200]
            if cross_ok
            else (
                "; ".join(cross.get("conflicts") or [])[:200]
                if cross.get("conflicts")
                else _info_request("Strategic Direction / IC Synthesis / ESG for cross-check")
            )
        ),
        "action": _CROSS_CHECK_RULE,
    })
    return rows


def _questions_from_mq_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    qa = (
        spec.get("mq_evidence_qa")
        if isinstance(spec.get("mq_evidence_qa"), list) else []
    )

    def _qa_fail(check: str) -> bool:
        return any(
            isinstance(r, dict) and r.get("check") == check and r.get("status") == "FAIL"
            for r in qa
        )

    if _qa_fail("role_roster_tenure_scale_plan_actual"):
        out.append(normalize_question({
            "question": "Complete executive roster with tenure, prior scale and plan-vs-actual",
            "required_records": "Bios + org chart + budget vs actual packs",
            "decision_effect": "Cannot underwrite delivery without named scale and track record",
            "priority": "mandatory_pre_decision",
            "owner": "HR / management diligence lead",
            "timing": "before IC",
            "closure_test": "role_roster_tenure_scale_plan_actual QA PASS",
            "interim_treatment": "LIMITED — withhold delivery claims",
        }))
    if _qa_fail("incentive_retention_clauses"):
        out.append(normalize_question({
            "question": "Extract notice, ESOP/equity and retention clauses for critical roles",
            "required_records": "Employment contracts + ESOP / retention schedules",
            "decision_effect": "Retention risk unpriced without clause extract",
            "priority": "signing_condition",
            "owner": "legal / HR diligence",
            "timing": "per deal timetable",
            "closure_test": "incentive_retention_clauses QA PASS",
            "interim_treatment": "LIMITED — treat retention as open",
        }))
    if _qa_fail("vacancy_capability_info_enum"):
        out.append(normalize_question({
            "question": "Reclassify gaps: vacancy vs capability vs information (bios ≠ vacancies)",
            "required_records": "Org chart + hiring plan + opened bios",
            "decision_effect": "Invented vacancies corrupt hiring cost in the model",
            "priority": "mandatory_pre_decision",
            "owner": "management diligence lead",
            "timing": "before IC",
            "closure_test": "vacancy_capability_info_enum QA PASS",
            "interim_treatment": "REWORK — strip vacancy labels from info gaps",
        }))
    if _qa_fail("board_succession_tables"):
        out.append(normalize_question({
            "question": "Provide board composition and succession / deputy map for critical roles",
            "required_records": "Board pack + succession / org chart",
            "decision_effect": "Key-person continuity untested",
            "priority": "signing_condition",
            "owner": "HR / board diligence",
            "timing": "per deal timetable",
            "closure_test": "board_succession_tables QA PASS",
            "interim_treatment": "LIMITED — flag succession as open",
        }))
    if _qa_fail("score_evidence"):
        out.append(normalize_question({
            "question": "Cite evidence for each management score (criticality / org risk)",
            "required_records": "HR pack + F-06 extract with source lines",
            "decision_effect": "Scores without evidence are not diligence judgments",
            "priority": "signing_condition",
            "owner": "management diligence lead",
            "timing": "per deal timetable",
            "closure_test": "score_evidence QA PASS",
            "interim_treatment": "Withhold scores until evidenced",
        }))
    if _qa_fail("evidence_checklist_closure"):
        out.append(normalize_question({
            "question": "Close evidence checklist: CVs, contracts, incentives, references",
            "required_records": "CV pack + contracts + ESOP docs + reference logs",
            "decision_effect": "Open checklist items block reliance on the team assessment",
            "priority": "mandatory_pre_decision",
            "owner": "HR diligence lead",
            "timing": "before IC",
            "closure_test": "evidence_checklist_closure QA PASS",
            "interim_treatment": "LIMITED until checklist ≥2 CLOSED",
        }))
    if _qa_fail("strategy_ic_esg_cross_check"):
        out.append(normalize_question({
            "question": "Supply Strategic Direction / IC Synthesis / ESG outputs for cross-check",
            "required_records": "Strategy + IC + ESG agent specs",
            "decision_effect": "Management claims may conflict with strategy / ESG narrative",
            "priority": "signing_condition",
            "owner": "IC coordinator",
            "timing": "per deal timetable",
            "closure_test": "strategy_ic_esg_cross_check QA PASS",
            "interim_treatment": "LIMITED until cross-check complete",
        }))
    return out


def _quality_reliance(
    *,
    exec_count: int,
    key_person: int,
    confirmed: int,
    capability: int,
    info_gaps: int,
) -> tuple[str, str, str]:
    quality = "PASS"
    if exec_count >= 3 and key_person >= 1 and info_gaps <= 2:
        reliance = "READY"
        rationale = (
            f"{exec_count} executives named; {key_person} key-person row(s); "
            f"{confirmed} confirmed vacancy(ies), {capability} capability gap(s)."
        )
    elif exec_count >= 1:
        reliance = "LIMITED"
        rationale = (
            f"{exec_count} executives evidenced; {info_gaps} information gap(s). "
            f"Missing biographies are information gaps — not vacancies."
        )
    else:
        reliance = "BLOCKED"
        rationale = (
            "No executives resolved from opened biographies / org charts / CIM pages."
        )
    return quality, reliance, rationale


def _llm_management_quality_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    inaccessible: list[str],
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
            "management_quality",
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
    inac = "\n".join(f"- {x}" for x in inaccessible[:8]) or "- (none)"
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources opened:\n{src_list}\n\n"
        f"Inaccessible pointers (say inaccessible, not unavailable):\n{inac}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "sources_resolved: [{pointer, status, note}] "
        "status is opened|inaccessible,\n"
        "executives: [{name, role, tenure, remit, prior_delivery, relevant_scale, "
        "vs_target, source, criticality, replaceability}],\n"
        "key_persons: [{person, what_depends, notice_incentives, source}],\n"
        "incentive_clauses: [{person_or_scope, clause_kind, extract, source, notes}],\n"
        "succession: [{role, incumbent, second_line, succession_status, source}],\n"
        "board: [{name, role, independence, source}],\n"
        "confirmed_vacancies: [{item, evidence, hiring_cost_eligible, source}],\n"
        "capability_gaps: [{item, evidence, hiring_cost_eligible, source}],\n"
        "information_gaps: [{item, evidence, hiring_cost_eligible, source}],\n"
        "proposed_hires: [{role, demonstrated_need, cost, date, source}] "
        "(only if confirmed vacancy or capability gap supports it; else []),\n"
        "score_evidence: [{score, value, evidence, source, notes}],\n"
        "evidence_checklist: [{item, status (CLOSED|OPEN), detail, source, notes}],\n"
        "mq_evidence_qa: [{check, status (PASS|FAIL), finding, action}] — include "
        "role_roster_tenure_scale_plan_actual, incentive_retention_clauses, "
        "vacancy_capability_info_enum, board_succession_tables, score_evidence, "
        "evidence_checklist_closure, strategy_ic_esg_cross_check,\n"
        "questions: [{question, required_records, decision_effect, priority, owner, "
        "timing, closure_test, interim_treatment}],\n"
        "assessment_read (string — team vs plan only; no invest/pass),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Never infer a vacancy from a missing biography. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    try:
        parsed = generate_json(system=system, user=user, temperature=0.15)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _heuristic_management_quality_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    inaccessible: list[str],
    f06_spec: dict[str, Any] | None = None,
    strategy_spec: dict[str, Any] | None = None,
    ic_spec: dict[str, Any] | None = None,
    esg_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    executives = _executives_from_f06(f06_spec, corpus)
    key_persons = _key_person_rows(executives, corpus, f06_spec)
    succession = _succession_rows(executives, f06_spec, corpus)
    board = _board_rows(corpus)
    gaps = _gap_states(executives, f06_spec, corpus)
    incentives = _incentive_retention_clauses(corpus, executives)
    checklist = _evidence_checklist(
        corpus=corpus,
        sources=sources,
        executives=executives,
        incentives=incentives,
    )
    scores = _score_evidence(
        executives=executives,
        f06=f06_spec,
        key_persons=key_persons,
    )
    cross = _cross_check_strategy_ic_esg(
        strategy_spec=strategy_spec,
        ic_spec=ic_spec,
        esg_spec=esg_spec,
        executives=executives,
    )

    sources_resolved = [
        {"pointer": s, "status": "opened", "note": "Loaded from Central Data Library"}
        for s in sources[:12]
    ]
    for note in inaccessible[:6]:
        sources_resolved.append({
            "pointer": note.replace("Document inaccessible: ", "", 1),
            "status": "inaccessible",
            "note": note,
        })

    mq_qa = _mq_evidence_qa(
        executives=executives,
        incentives=incentives,
        confirmed=gaps["confirmed_vacancies"],
        capability=gaps["capability_gaps"],
        info_gaps=gaps["information_gaps"],
        succession=succession,
        board=board,
        scores=scores,
        checklist=checklist,
        cross=cross,
    )
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in mq_qa)

    quality, reliance, qr = _quality_reliance(
        exec_count=len(executives),
        key_person=len(key_persons),
        confirmed=len(gaps["confirmed_vacancies"]),
        capability=len(gaps["capability_gaps"]),
        info_gaps=len(gaps["information_gaps"]),
    )
    if qa_fail and reliance == "READY":
        reliance = "LIMITED"
        qr = "Management quality QA has open FAILs — reliance limited. " + qr
    if cross.get("conflicts"):
        quality = "REWORK"
        qr = "Strategy/IC/ESG cross-check conflicts — rework. " + qr

    insight = (
        f"Management assessment for {company}: {len(executives)} named executives from "
        f"opened packs; {len(key_persons)} key-person dependencies flagged; "
        f"{len(gaps['confirmed_vacancies'])} confirmed vacancies, "
        f"{len(gaps['capability_gaps'])} capability gaps, "
        f"{len(gaps['information_gaps'])} information gaps "
        f"(missing bios are information gaps, not vacancies)."
    )

    assessment = (
        f"Against the plan being underwritten, the pack names {len(executives)} senior roles. "
        f"Key-person exposure is "
        + ("material" if key_persons else "not evidenced")
        + f". Hiring cost in the model may only attach to confirmed vacancies "
        f"({len(gaps['confirmed_vacancies'])}) or demonstrated capability gaps "
        f"({len(gaps['capability_gaps'])}) — not to information gaps."
    )

    proposed: list[dict[str, str]] = []
    for row in gaps["confirmed_vacancies"][:2]:
        proposed.append({
            "role": row["item"],
            "demonstrated_need": row["evidence"],
            "cost": _info_request("budgeted hiring cost"),
            "date": _info_request("target start date"),
            "source": row.get("source") or _DOC_CITE,
        })

    out = {
        "insight_snapshot": insight,
        "sources_resolved": sources_resolved,
        "executives": executives,
        "key_persons": key_persons,
        "incentive_clauses": incentives,
        "succession": succession,
        "board": board,
        "confirmed_vacancies": gaps["confirmed_vacancies"],
        "capability_gaps": gaps["capability_gaps"],
        "information_gaps": gaps["information_gaps"],
        "proposed_hires": proposed,
        "score_evidence": scores,
        "evidence_checklist": checklist,
        "strategy_ic_esg_cross_check": cross,
        "mq_evidence_qa": mq_qa,
        "assessment_read": assessment,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "c_suite": (f06_spec or {}).get("c_suite") if isinstance(f06_spec, dict) else [],
        "succession_gaps": (f06_spec or {}).get("succession_gaps") if isinstance(f06_spec, dict) else [],
        "org_risk_score": (f06_spec or {}).get("org_risk_score") if isinstance(f06_spec, dict) else None,
    }
    out["questions"] = _questions_from_mq_gaps(out)
    return out


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    inaccessible: list[str],
    f06_spec: dict[str, Any] | None,
    corpus: str = "",
    strategy_spec: dict[str, Any] | None = None,
    ic_spec: dict[str, Any] | None = None,
    esg_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    heur = _heuristic_management_quality_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        inaccessible=inaccessible,
        f06_spec=f06_spec,
        strategy_spec=strategy_spec,
        ic_spec=ic_spec,
        esg_spec=esg_spec,
    )
    for key in (
        "executives", "key_persons", "succession", "board",
        "confirmed_vacancies", "capability_gaps", "information_gaps",
        "proposed_hires", "sources_resolved", "incentive_clauses",
        "score_evidence", "evidence_checklist",
    ):
        if not isinstance(llm.get(key), list) or not llm.get(key):
            llm[key] = list(heur.get(key) or [])

    cleaned_hires = []
    for row in llm.get("proposed_hires") or []:
        if not isinstance(row, dict):
            continue
        need = str(row.get("demonstrated_need") or "")
        if not need or need.upper().startswith("N/A"):
            continue
        cleaned_hires.append(row)
    llm["proposed_hires"] = cleaned_hires

    if not llm.get("sources_resolved"):
        llm["sources_resolved"] = [
            {"pointer": s, "status": "opened", "note": "Loaded from Central Data Library"}
            for s in sources[:12]
        ]
        for note in inaccessible[:6]:
            llm["sources_resolved"].append({
                "pointer": note,
                "status": "inaccessible",
                "note": note,
            })

    llm["strategy_ic_esg_cross_check"] = (
        heur.get("strategy_ic_esg_cross_check") or {}
    )
    mq_qa = _mq_evidence_qa(
        executives=llm.get("executives") or [],
        incentives=llm.get("incentive_clauses") or [],
        confirmed=llm.get("confirmed_vacancies") or [],
        capability=llm.get("capability_gaps") or [],
        info_gaps=llm.get("information_gaps") or [],
        succession=llm.get("succession") or [],
        board=llm.get("board") or [],
        scores=llm.get("score_evidence") or [],
        checklist=llm.get("evidence_checklist") or [],
        cross=llm["strategy_ic_esg_cross_check"],
    )
    llm["mq_evidence_qa"] = mq_qa
    qa_fail = any(isinstance(r, dict) and r.get("status") == "FAIL" for r in mq_qa)

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            exec_count=len(llm.get("executives") or []),
            key_person=len(llm.get("key_persons") or []),
            confirmed=len(llm.get("confirmed_vacancies") or []),
            capability=len(llm.get("capability_gaps") or []),
            info_gaps=len(llm.get("information_gaps") or []),
        )
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        llm.setdefault("quality_reliance_rationale", rationale)
    else:
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv

    if qa_fail and llm["reliance_verdict"] == "READY":
        llm["reliance_verdict"] = "LIMITED"
        llm["quality_reliance_rationale"] = (
            "Management quality QA has open FAILs — reliance limited. "
            + _clean(llm.get("quality_reliance_rationale"), 300)
        )
    if (llm.get("strategy_ic_esg_cross_check") or {}).get("conflicts"):
        llm["quality_verdict"] = "REWORK"

    if not llm.get("questions"):
        llm["questions"] = _questions_from_mq_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw_q in llm.get("questions") or []:
            q = normalize_question(raw_q)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_mq_gaps(llm)

    for dead in ("recommendation", "confidence", "key_conditions", "investment_verdict"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    if isinstance(f06_spec, dict):
        llm.setdefault("c_suite", f06_spec.get("c_suite") or [])
        llm.setdefault("succession_gaps", f06_spec.get("succession_gaps") or [])
        llm.setdefault("org_risk_score", f06_spec.get("org_risk_score"))
    llm.setdefault("insight_snapshot", heur.get("insight_snapshot"))
    llm.setdefault("assessment_read", heur.get("assessment_read"))
    return llm


def build_management_quality_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    f06_spec: dict[str, Any] | None = None,
    strategy_spec: dict[str, Any] | None = None,
    ic_spec: dict[str, Any] | None = None,
    esg_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    inaccessible: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    if corpus is None or sources is None:
        corpus, sources, inac = gather_management_quality_corpus(deal, idx)
        inaccessible = list(inaccessible or []) + inac
    else:
        inaccessible = list(inaccessible or [])

    if not corpus:
        bits: list[str] = []
        sources = list(sources or [])
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                sources.append(str(doc.get("filename") or "source"))
        corpus = "\n".join(bits)
    # When the first gather misses Job Title / CEO beside the controlling holder,
    # pull additional cap-table / securities pages (same helper as Company Background).
    if not re.search(r"(?i)\b(?:CEO|Founder|Chief\s+Executive)\b", corpus or ""):
        try:
            from agetic_cdd_api.agent_document_company_background import (
                _load_cap_table_extras,
            )

            extra = _load_cap_table_extras(deal, idx, already=set(sources or []))
            if extra:
                corpus = f"{corpus or ''}\n\n{extra}"
                for line in extra.splitlines():
                    if line.startswith("### "):
                        fn = line[4:].strip()
                        if fn and fn not in (sources or []):
                            sources = list(sources or []) + [fn]
        except Exception:
            pass

    vars_ = prompt_vars_from_deal(deal)
    heur = _heuristic_management_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        inaccessible=inaccessible,
        f06_spec=f06_spec,
        strategy_spec=strategy_spec,
        ic_spec=ic_spec,
        esg_spec=esg_spec,
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    if prefer_heuristic:
        return heur

    llm = _llm_management_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        inaccessible=inaccessible,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
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
            inaccessible=inaccessible,
            f06_spec=f06_spec,
            corpus=corpus,
            strategy_spec=strategy_spec,
            ic_spec=ic_spec,
            esg_spec=esg_spec,
        )
        out["deal_slots"] = {k: v for k, v in vars_.items() if v}
        return out

    return heur


def render_management_quality_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    """Render prompt-book Management Quality assessment."""
    resolved = spec.get("sources_resolved") if isinstance(spec.get("sources_resolved"), list) else []
    executives = spec.get("executives") if isinstance(spec.get("executives"), list) else []
    key_persons = spec.get("key_persons") if isinstance(spec.get("key_persons"), list) else []
    succession = spec.get("succession") if isinstance(spec.get("succession"), list) else []
    board = spec.get("board") if isinstance(spec.get("board"), list) else []
    confirmed = spec.get("confirmed_vacancies") if isinstance(spec.get("confirmed_vacancies"), list) else []
    capability = spec.get("capability_gaps") if isinstance(spec.get("capability_gaps"), list) else []
    info_gaps = spec.get("information_gaps") if isinstance(spec.get("information_gaps"), list) else []
    hires = spec.get("proposed_hires") if isinstance(spec.get("proposed_hires"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Source Resolution\n\n")
    parts.append(
        "Pointers to biographies, organisation charts and CIM pages are resolved below. "
        "If a file could not be opened, it is marked **inaccessible** — not unavailable.\n\n"
    )
    if resolved:
        parts.append(_table(
            ["Pointer", "Status", "Note"],
            [
                [
                    _clean(r.get("pointer"), 80),
                    _clean(r.get("status"), 20),
                    _clean(r.get("note"), 120),
                ]
                for r in resolved if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('biography / org chart / CIM pointers')}\n\n")
    parts.append("---\n\n")

    parts.append("## 2. Executive & Senior Operating Roster\n\n")
    parts.append(f"{_ROSTER_RULE}\n\n")
    if executives:
        parts.append(_table(
            [
                "Name", "Role", "Tenure", "Remit", "Prior Delivery / Scale",
                "Vs Target", "Source",
            ],
            [
                [
                    _clean(r.get("name"), 40),
                    _clean(r.get("role"), 40),
                    _clean(r.get("tenure"), 40),
                    _clean(r.get("remit"), 60),
                    _clean(
                        r.get("relevant_scale") or r.get("prior_delivery"), 80
                    ),
                    _clean(r.get("vs_target"), 60),
                    _clean(r.get("source"), 40),
                ]
                for r in executives if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"{_info_request('named executives with tenure, remit, scale and plan-vs-actual')}\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 3. Key-Person Dependencies\n\n")
    parts.append(
        "What breaks if the person leaves; notice, incentives and retention where evidenced.\n\n"
    )
    parts.append(f"{_INCENTIVE_RULE}\n\n")
    if key_persons:
        parts.append(_table(
            ["Person", "What Depends / Breaks", "Notice / Incentives / Retention", "Source"],
            [
                [
                    _clean(r.get("person"), 60),
                    _clean(r.get("what_depends"), 160),
                    _clean(r.get("notice_incentives"), 100),
                    _clean(r.get("source"), 40),
                ]
                for r in key_persons if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('key-person map from HR / org packs')}\n\n")
    incentives = (
        spec.get("incentive_clauses")
        if isinstance(spec.get("incentive_clauses"), list) else []
    )
    if incentives:
        parts.append("### Incentive / retention clause extract\n\n")
        parts.append(_table(
            ["Person / scope", "Kind", "Extract", "Source"],
            [
                [
                    _clean(r.get("person_or_scope"), 60),
                    _clean(r.get("clause_kind"), 40),
                    _clean(r.get("extract"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in incentives if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 4. Second-Line Depth, Succession & Board\n\n")
    parts.append(f"{_BOARD_SUCCESSION_RULE}\n\n")
    parts.append("### Succession by Critical Role\n\n")
    if succession:
        parts.append(_table(
            ["Role", "Incumbent", "Second Line", "Succession Status", "Source"],
            [
                [
                    _clean(r.get("role"), 40),
                    _clean(r.get("incumbent"), 40),
                    _clean(r.get("second_line"), 60),
                    _clean(r.get("succession_status"), 100),
                    _clean(r.get("source"), 40),
                ]
                for r in succession if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('succession / deputy map')}\n\n")

    parts.append("### Board Composition & Oversight\n\n")
    if board:
        parts.append(_table(
            ["Name", "Role", "Independence", "Source"],
            [
                [
                    _clean(r.get("name"), 40),
                    _clean(r.get("role"), 60),
                    _clean(r.get("independence"), 30),
                    _clean(r.get("source"), 40),
                ]
                for r in board if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('board composition and oversight records')}\n\n")
    parts.append("---\n\n")

    parts.append("## 5. Vacancies, Capability Gaps & Information Gaps\n\n")
    parts.append(f"{_VACANCY_ENUM_RULE}\n\n")
    parts.append(
        "Three states only. **Confirmed vacancy** and **demonstrated capability gap** "
        "may support a hiring cost in the model. An **information gap** (including a "
        "missing biography) must not be treated as a vacancy or as weak management.\n\n"
    )
    parts.append("### Confirmed Vacancies\n\n")
    if confirmed:
        parts.append(_table(
            ["Item", "Evidence", "Hiring Cost Eligible", "Source"],
            [
                [
                    _clean(r.get("item"), 80),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("hiring_cost_eligible"), 40),
                    _clean(r.get("source"), 40),
                ]
                for r in confirmed if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None evidenced in the opened packs.\n\n")

    parts.append("### Demonstrated Capability Gaps\n\n")
    if capability:
        parts.append(_table(
            ["Item", "Evidence", "Hiring Cost Eligible", "Source"],
            [
                [
                    _clean(r.get("item"), 80),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("hiring_cost_eligible"), 40),
                    _clean(r.get("source"), 40),
                ]
                for r in capability if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None evidenced in the opened packs.\n\n")

    parts.append("### Information Gaps\n\n")
    if info_gaps:
        parts.append(_table(
            ["Item", "Evidence", "Hiring Cost Eligible", "Source"],
            [
                [
                    _clean(r.get("item"), 80),
                    _clean(r.get("evidence"), 120),
                    _clean(r.get("hiring_cost_eligible"), 40),
                    _clean(r.get("source"), 40),
                ]
                for r in info_gaps if isinstance(r, dict)
            ],
        ))
    else:
        parts.append("None registered.\n\n")

    if hires:
        parts.append("### Proposed Hires (need · cost · date)\n\n")
        parts.append(_table(
            ["Role", "Demonstrated Need", "Cost", "Date", "Source"],
            [
                [
                    _clean(r.get("role"), 60),
                    _clean(r.get("demonstrated_need"), 100),
                    _clean(r.get("cost"), 60),
                    _clean(r.get("date"), 40),
                    _clean(r.get("source"), 40),
                ]
                for r in hires if isinstance(r, dict)
            ],
        ))

    scores = (
        spec.get("score_evidence")
        if isinstance(spec.get("score_evidence"), list) else []
    )
    if scores:
        parts.append("### Score evidence\n\n")
        parts.append(f"{_SCORE_EVIDENCE_RULE}\n\n")
        parts.append(_table(
            ["Score", "Value", "Evidence", "Source"],
            [
                [
                    _clean(r.get("score"), 60),
                    _clean(r.get("value"), 40),
                    _clean(r.get("evidence"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in scores if isinstance(r, dict)
            ],
        ))

    checklist = (
        spec.get("evidence_checklist")
        if isinstance(spec.get("evidence_checklist"), list) else []
    )
    if checklist:
        parts.append("### Evidence checklist\n\n")
        parts.append(f"{_CHECKLIST_RULE}\n\n")
        parts.append(_table(
            ["Item", "Status", "Detail", "Source"],
            [
                [
                    _clean(r.get("item"), 60),
                    _clean(r.get("status"), 20),
                    _clean(r.get("detail"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in checklist if isinstance(r, dict)
            ],
        ))

    cross = (
        spec.get("strategy_ic_esg_cross_check")
        if isinstance(spec.get("strategy_ic_esg_cross_check"), dict) else {}
    )
    if cross:
        parts.append("### Strategic Direction / IC / ESG cross-check\n\n")
        parts.append(f"{_CROSS_CHECK_RULE}\n\n")
        parts.append(_table(
            ["Field", "Value"],
            [
                [
                    "Strategic Direction present",
                    "Yes" if cross.get("strategic_direction_present") else "No",
                ],
                [
                    "IC Synthesis present",
                    "Yes" if cross.get("ic_synthesis_present") else "No",
                ],
                ["ESG present", "Yes" if cross.get("esg_present") else "No"],
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

    if spec.get("assessment_read"):
        parts.append(f"**Read:** {_clean(spec.get('assessment_read'), 520)}\n\n")
    parts.append(
        "*This section assesses the team against the plan being underwritten. "
        "It does not recommend invest or pass. Missing biographies are information "
        "gaps — not vacancies.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    mq_qa = (
        spec.get("mq_evidence_qa")
        if isinstance(spec.get("mq_evidence_qa"), list) else []
    )
    parts.append("## 6. Management Quality Evidence QA\n\n")
    parts.append(
        "QA enforces roster (tenure/scale/plan-vs-actual), incentive extracts, "
        "vacancy enum discipline, board/succession, score evidence, checklist "
        "closure, and Strategy/IC/ESG cross-check.\n\n"
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
                for r in mq_qa
                if isinstance(r, dict)
            ],
        )
        or f"{_info_request('management quality evidence QA rows')}\n\n"
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
        parts.append(f"{_info_request('Questions for material management-quality gaps')}\n\n")
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
            ["Rationale", _clean(rationale, 460)],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(qv, 20)} — is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(rv, 20)} — can a decision rest on this management assessment?\n\n"
    )
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
        "Open management-quality QA FAILs cap READY → LIMITED. "
        "This agent does not issue an invest or pass recommendation. "
        f"{_VACANCY_ENUM_RULE}*\n\n"
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
