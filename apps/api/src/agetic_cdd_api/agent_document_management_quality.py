"""Compose DiligenceIQ Management Quality — team vs underwritten plan (prompt book).

Named executives, key-person risk, succession, vacancy vs capability vs info gaps.
No investment verdict. Never infer a vacancy from a missing biography.
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

_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_BOARD_ROW = re.compile(
    r"([A-Z][A-Za-z .'-]{2,50}?)\s+"
    r"((?:Chairman|Managing Director|Independent Director|Non[- ]Executive|"
    r"Executive|Audit Committee|Director)[^|]{0,60}?)"
    r"\s+(Independent|Executive|Non[- ]Executive)",
    re.IGNORECASE,
)
_ESOP = re.compile(
    r"\b(ESOP|equity incentive|stock option|retention bonus|notice period)\b"
    r"[^.|]{0,120}",
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
    inaccessible: list[str] = []
    for doc in ranked[:14]:
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
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources, inaccessible


def _executives_from_f06(f06: dict[str, Any] | None, corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if isinstance(f06, dict):
        for item in f06.get("c_suite") or []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            rows.append({
                "name": str(item.get("name") or "").strip(),
                "role": str(item.get("role") or "Executive").strip(),
                "tenure": _NA,
                "remit": str(item.get("role") or "Senior operating role").strip(),
                "prior_delivery": _NA,
                "vs_target": _NA,
                "source": _DOC_CITE,
                "criticality": str(item.get("criticality") or ""),
            })
    if rows:
        # Enrich tenure from corpus near each name when present.
        for row in rows:
            name = row["name"]
            if not name or name == _NA:
                continue
            idx = corpus.lower().find(name.lower())
            if idx < 0:
                continue
            window = corpus[idx : idx + 220]
            tm = _TENURE.search(window)
            if tm:
                row["tenure"] = f"{tm.group(1)} years {_DOC_CITE}"
            # Prior experience snippet after name/role if present
            exp = re.search(
                r"(?:Prior Experience|previously|formerly)\s*[:\-]?\s*"
                r"([A-Za-z0-9][^.\n|]{8,120})",
                window,
                re.I,
            )
            if exp:
                row["prior_delivery"] = _clean(exp.group(1), 120) + f" {_DOC_CITE}"
        return rows[:10]

    # Fallback: CEO/CFO/CTO/CHRO labels in corporate pack
    for m in re.finditer(
        r"\b(CEO|CFO|CTO|COO|CHRO|Founder)\b\s*(?:&|and)?\s*"
        r"(?:Founder)?\s*([A-Z][A-Za-z .'-]{2,40})",
        corpus[:25_000],
    ):
        role, name = m.group(1), _clean(m.group(2), 40)
        if len(name.split()) < 2:
            continue
        rows.append({
            "name": name,
            "role": role,
            "tenure": _NA,
            "remit": role,
            "prior_delivery": _NA,
            "vs_target": _NA,
            "source": _DOC_CITE,
            "criticality": "5" if role in {"CEO", "Founder"} else "4",
        })
        if len(rows) >= 8:
            break
    return rows


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
                name = str(item.get("name") or "").strip()
                role = str(item.get("role") or "").strip()
                if not name:
                    continue
                break_if = (
                    f"Approvals, external relationships and strategic direction "
                    f"tied to {role} — continuity risk if {name} exits"
                )
                rows.append({
                    "person": f"{name} ({role})",
                    "what_depends": break_if,
                    "notice_incentives": _NA,
                    "source": _DOC_CITE,
                })
    for sent in key_sents:
        if any(sent[:60].lower() in r["what_depends"].lower() for r in rows):
            continue
        person = "Named in HR / corporate pack"
        for ex in executives:
            if ex["name"] and ex["name"].split()[0].lower() in sent.lower():
                person = f"{ex['name']} ({ex['role']})"
                break
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
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    system = compose_system(
        "management_quality",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
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
        "executives: [{name, role, tenure, remit, prior_delivery, vs_target, source}],\n"
        "key_persons: [{person, what_depends, notice_incentives, source}],\n"
        "succession: [{role, incumbent, second_line, succession_status, source}],\n"
        "board: [{name, role, independence, source}],\n"
        "confirmed_vacancies: [{item, evidence, hiring_cost_eligible, source}],\n"
        "capability_gaps: [{item, evidence, hiring_cost_eligible, source}],\n"
        "information_gaps: [{item, evidence, hiring_cost_eligible, source}],\n"
        "proposed_hires: [{role, demonstrated_need, cost, date, source}] "
        "(only if confirmed vacancy or capability gap supports it; else []),\n"
        "assessment_read (string — team vs plan only; no invest/pass),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Never infer a vacancy from a missing biography. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_management_quality_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    inaccessible: list[str],
    f06_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    executives = _executives_from_f06(f06_spec, corpus)
    key_persons = _key_person_rows(executives, corpus, f06_spec)
    succession = _succession_rows(executives, f06_spec, corpus)
    board = _board_rows(corpus)
    gaps = _gap_states(executives, f06_spec, corpus)

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

    quality, reliance, qr = _quality_reliance(
        exec_count=len(executives),
        key_person=len(key_persons),
        confirmed=len(gaps["confirmed_vacancies"]),
        capability=len(gaps["capability_gaps"]),
        info_gaps=len(gaps["information_gaps"]),
    )

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

    # Proposed hires only from confirmed / capability with need — no invented costs/dates
    proposed: list[dict[str, str]] = []
    for row in gaps["confirmed_vacancies"][:2]:
        proposed.append({
            "role": row["item"],
            "demonstrated_need": row["evidence"],
            "cost": _info_request("budgeted hiring cost"),
            "date": _info_request("target start date"),
            "source": row.get("source") or _DOC_CITE,
        })

    return {
        "insight_snapshot": insight,
        "sources_resolved": sources_resolved,
        "executives": executives,
        "key_persons": key_persons,
        "succession": succession,
        "board": board,
        "confirmed_vacancies": gaps["confirmed_vacancies"],
        "capability_gaps": gaps["capability_gaps"],
        "information_gaps": gaps["information_gaps"],
        "proposed_hires": proposed,
        "assessment_read": assessment,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        # Preserve F-06 keys for downstream
        "c_suite": (f06_spec or {}).get("c_suite") if isinstance(f06_spec, dict) else [],
        "succession_gaps": (f06_spec or {}).get("succession_gaps") if isinstance(f06_spec, dict) else [],
        "org_risk_score": (f06_spec or {}).get("org_risk_score") if isinstance(f06_spec, dict) else None,
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    inaccessible: list[str],
    f06_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    for key in (
        "executives", "key_persons", "succession", "board",
        "confirmed_vacancies", "capability_gaps", "information_gaps",
        "proposed_hires", "sources_resolved",
    ):
        if not isinstance(llm.get(key), list):
            llm[key] = []

    # Guard: strip proposed hires that lack demonstrated need
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

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    if isinstance(f06_spec, dict):
        llm.setdefault("c_suite", f06_spec.get("c_suite") or [])
        llm.setdefault("succession_gaps", f06_spec.get("succession_gaps") or [])
        llm.setdefault("org_risk_score", f06_spec.get("org_risk_score"))
    return llm


def build_management_quality_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    f06_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    inaccessible: list[str] | None = None,
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

    vars_ = prompt_vars_from_deal(deal)
    llm = _llm_management_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        inaccessible=inaccessible,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if llm:
        return _normalise_llm_spec(
            llm,
            sources=sources,
            inaccessible=inaccessible,
            f06_spec=f06_spec,
        )

    return _heuristic_management_quality_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        inaccessible=inaccessible,
        f06_spec=f06_spec,
    )


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
    if executives:
        parts.append(_table(
            ["Name", "Role", "Tenure", "Remit", "Prior Delivery", "Vs Target", "Source"],
            [
                [
                    _clean(r.get("name"), 40),
                    _clean(r.get("role"), 40),
                    _clean(r.get("tenure"), 40),
                    _clean(r.get("remit"), 60),
                    _clean(r.get("prior_delivery"), 80),
                    _clean(r.get("vs_target"), 60),
                    _clean(r.get("source"), 40),
                ]
                for r in executives if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(
            f"{_info_request('named executives with tenure, remit and prior delivery')}\n\n"
        )
    parts.append("---\n\n")

    parts.append("## 3. Key-Person Dependencies\n\n")
    parts.append(
        "What breaks if the person leaves; notice, incentives and retention where evidenced.\n\n"
    )
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
    parts.append("---\n\n")

    parts.append("## 4. Second-Line Depth, Succession & Board\n\n")
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

    if spec.get("assessment_read"):
        parts.append(f"**Read:** {_clean(spec.get('assessment_read'), 520)}\n\n")
    parts.append(
        "*This section assesses the team against the plan being underwritten. "
        "It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can a decision rest on this management assessment?\n\n"
    )
    if spec.get("quality_reliance_rationale"):
        parts.append(f"**Rationale:** {_clean(spec.get('quality_reliance_rationale'), 520)}\n\n")

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
