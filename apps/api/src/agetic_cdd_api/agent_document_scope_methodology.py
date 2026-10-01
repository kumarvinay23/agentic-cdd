"""Compose DiligenceIQ Scope & Methodology — coverage record (prompt book).

Honest map of work performed vs evidence vs undone. No investment verdict.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _INDUSTRY,
    _clean,
    _first_match,
    _pick_sentences,
    _sentences,
    gather_deal_context_corpus,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_INTERNAL = "(DOC: INTERNAL DATA ROOM EXCERPTS)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_FY_SPAN = re.compile(
    r"FY\s*(20\d{2})\s*[-–—/]\s*FY?\s*(20\d{2})E?",
    re.IGNORECASE,
)
_FY_SINGLE = re.compile(r"\bFY\s*(20(?:2[0-9]|1[5-9]))E?\b", re.IGNORECASE)
_INTERVIEW = re.compile(
    r"(?P<label>(?:management\s+)?interview|site\s+visit|plant\s+tour|"
    r"expert\s+(?:call|interview)|management\s+meeting)"
    r".{0,120}?",
    re.IGNORECASE | re.DOTALL,
)
_DATE_NEAR = re.compile(
    r"\b(?:(?P<dmy>\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"
    r"|(?P<iso>\d{4}-\d{2}-\d{2})"
    r"|(?P<mdy>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})"
    r"|(?P<dmon>\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+\d{4})"
    r"|(?P<fy>FY\s*20\d{2}(?:E)?))\b",
    re.IGNORECASE,
)
_PARTICIPANTS = re.compile(
    r"(?:attended by|participants?|with|present)\s*:?\s*"
    r"([A-Z][A-Za-z .,&/\-]{3,120})",
)

# Canonical in-scope investment questions → owning workstream + CDL category key.
_QUESTION_CATALOG: list[dict[str, str]] = [
    {
        "question": "What is the growth potential of the target market in the focus geography?",
        "workstream": "Market / Competition",
        "cdl": "market_competition",
        "method": "Market sizing / growth bridge from VDR market packs",
    },
    {
        "question": "How durable is competitive position and share?",
        "workstream": "Market / Competition",
        "cdl": "market_competition",
        "method": "Competitive landscape and share evidence review",
    },
    {
        "question": "What do historical and LTM financials say about performance quality?",
        "workstream": "Financial",
        "cdl": "financial",
        "method": "P&L / KPI extraction and trend review",
    },
    {
        "question": "Can operations support the plan (capacity, supply chain, quality)?",
        "workstream": "Operations",
        "cdl": "operations",
        "method": "Ops / manufacturing / supply-chain pack review",
    },
    {
        "question": "How sticky and high-quality is the customer / revenue base?",
        "workstream": "Customer",
        "cdl": "customer",
        "method": "Retention, concentration, and commercial quality review",
    },
    {
        "question": "What legal, regulatory, or ESG exposures could change structure or price?",
        "workstream": "Legal / ESG",
        "cdl": "legal_esg",
        "method": "Legal / regulatory pack review",
    },
    {
        "question": "Is management and organisation capable of executing the plan?",
        "workstream": "Company / Management",
        "cdl": "company_management",
        "method": "Corporate overview / org / management pack review",
    },
    {
        "question": "What is the deal perimeter, thesis, and capital context?",
        "workstream": "Deal / Strategy",
        "cdl": "deal_strategy",
        "method": "Deal context / investment thesis pack review",
    },
]

_CDL_TO_LABEL = {
    "deal_strategy": "Deal / Strategy",
    "company_management": "Company / Management",
    "market_competition": "Market / Competition",
    "customer": "Customer",
    "operations": "Operations",
    "legal_esg": "Legal / ESG",
    "financial": "Financial",
}


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


def _detect_periods(corpus: str) -> str:
    years = sorted({int(y) for y in _FY_SINGLE.findall(corpus) if 2015 <= int(y) <= 2035})
    span = _FY_SPAN.search(corpus)
    if span:
        a, b = int(span.group(1)), int(span.group(2))
        if 2015 <= a <= b <= 2035 and (b - a) <= 15:
            return f"FY{a}–FY{b}"
    if years:
        return f"FY{min(years)}–FY{max(years)}"
    return "N/A (data room did not provide it)"


def _docs_for_cdl(index: dict[str, Any], cdl: str) -> list[str]:
    out: list[str] = []
    for doc in index.get("documents") or []:
        if not isinstance(doc, dict):
            continue
        if str(doc.get("cdl_category") or "") == cdl:
            name = str(doc.get("filename") or "").strip()
            if name:
                out.append(name)
    return out


def _status_for_docs(filenames: list[str], *, corpus_hit: bool) -> str:
    if not filenames:
        return "not_started"
    if corpus_hit and len(filenames) >= 1:
        return "complete" if len(filenames) >= 2 else "partial"
    return "partial"


def _corpus_hit_for_workstream(corpus: str, workstream: str) -> bool:
    needles = {
        "Market / Competition": ("market", "tam", "sam", "competitor", "share", "cagr"),
        "Financial": ("revenue", "ebitda", "p&l", "margin", "cash"),
        "Operations": ("manufactur", "capacity", "supply chain", "defect", "factory"),
        "Customer": ("customer", "churn", "nps", "retention", "cohort"),
        "Legal / ESG": ("legal", "litigation", "regulatory", "fame", "compliance", "esg"),
        "Company / Management": ("management", "headcount", "board", "founder", "org"),
        "Deal / Strategy": ("investment thesis", "deal", "acquisition", "sponsor"),
    }.get(workstream, ())
    lower = (corpus or "").lower()
    return any(n in lower for n in needles)


def _impact_for_status(status: str, workstream: str) -> tuple[str, str]:
    """Return (could_change, gate) for unfinished items."""
    critical = {"Financial", "Legal / ESG", "Customer", "Deal / Strategy"}
    if status == "complete":
        return "—", "—"
    if workstream in critical:
        if status == "not_started":
            return "decision", "must_close"
        return "price", "must_close"
    if status == "not_started":
        return "structure", "must_close"
    return "price", "residual"


def _find_fieldwork(corpus: str) -> list[dict[str, str]]:
    """Extract interview / site-visit claims; undated rows are marked not counting."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in _INTERVIEW.finditer(corpus[:80_000]):
        window = corpus[max(0, m.start() - 40) : m.end() + 160]
        label = _clean(m.group("label"), 40).title()
        date_m = _DATE_NEAR.search(window)
        date = "undated — does not count as work performed"
        status = "claimed_undated"
        if date_m:
            date = next(g for g in date_m.groups() if g)
            status = "recorded"
        part_m = _PARTICIPANTS.search(window)
        participants = _clean(part_m.group(1), 120) if part_m else "N/A (data room did not provide it)"
        key = f"{label}|{date}|{participants}".lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "date": date,
            "participants": participants,
            "type": label,
            "status": status,
            "source": _INTERNAL,
        })
        if len(rows) >= 8:
            break
    return rows


def _quality_reliance(
    *,
    evidenced: int,
    in_scope: int,
    must_close: int,
    docs_read: int,
    docs_available: int,
) -> tuple[str, str, str]:
    quality = "PASS"
    if in_scope <= 0:
        return "REWORK", "BLOCKED", "No in-scope questions were registered."
    ratio = evidenced / max(in_scope, 1)
    if must_close > 0 and ratio < 0.5:
        reliance = "BLOCKED"
        rationale = (
            f"{evidenced}/{in_scope} questions evidenced; {must_close} items must close "
            f"before a decision. Documents read {docs_read}/{docs_available}."
        )
    elif must_close > 0 or ratio < 0.85:
        reliance = "LIMITED"
        rationale = (
            f"{evidenced}/{in_scope} questions evidenced; {must_close} must-close item(s) remain. "
            f"Documents read {docs_read}/{docs_available}. Coverage is not comprehensive."
        )
    else:
        reliance = "READY"
        rationale = (
            f"{evidenced}/{in_scope} questions evidenced; documents read "
            f"{docs_read}/{docs_available}. Residual items only."
        )
    return quality, reliance, rationale


def _llm_scope_methodology_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    covered: list[str],
    gaps: list[str],
    document_count: int,
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    system = compose_system(
        "scope_and_methodology",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:16], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"VDR documents available: {document_count}\n"
        f"CDL categories with files: {', '.join(covered) or 'none'}\n"
        f"CDL categories without files: {', '.join(gaps) or 'none'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string — coverage honesty only),\n"
        "coverage_counts: {questions_evidenced (int), questions_in_scope (int), "
        "documents_read (int), documents_available (int)},\n"
        "coverage_table: [{question, work_done, source, period, method, status}] "
        "status is complete|partial|not_started (8–12 rows),\n"
        "completed_work: [string],\n"
        "planned_work: [string],\n"
        "blocked_work: [string],\n"
        "exclusions: [{item, reason, state, workstream}] "
        "state is not_yet_done|cannot_with_evidence|out_of_scope,\n"
        "fieldwork: [{date, participants, type, status}] — undated interviews "
        "must set status claimed_undated and must not count as work performed,\n"
        "unfinished: [{item, could_change, gate, workstream}] "
        "could_change is price|structure|decision; gate is must_close|residual,\n"
        "coverage_conclusion (string — completeness of diligence only; "
        "never investment attractiveness; never say comprehensive if must_close remains),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_scope_methodology_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    index: dict[str, Any],
    covered: list[str],
    gaps: list[str],
) -> dict[str, Any]:
    counts = index.get("category_counts") if isinstance(index.get("category_counts"), dict) else {}
    docs_available = int(index.get("document_count") or len(index.get("documents") or []) or 0)
    docs_read = len([s for s in sources if s]) or docs_available
    periods = _detect_periods(corpus)
    industry_m = _first_match(_INDUSTRY, corpus)
    industry = _clean(industry_m.group(0), 60) if industry_m else "N/A (data room did not provide it)"
    if industry_m and "electric" in industry.lower() and "two" in industry.lower():
        industry = "Electric Two-Wheelers"

    coverage_table: list[dict[str, str]] = []
    completed: list[str] = []
    planned: list[str] = []
    blocked: list[str] = []
    unfinished: list[dict[str, str]] = []
    exclusions: list[dict[str, str]] = []

    for entry in _QUESTION_CATALOG:
        cdl = entry["cdl"]
        workstream = entry["workstream"]
        filenames = _docs_for_cdl(index, cdl)
        hit = _corpus_hit_for_workstream(corpus, workstream)
        status = _status_for_docs(filenames, corpus_hit=hit)
        src = ", ".join(filenames[:3]) if filenames else "N/A (data room did not provide it)"
        if filenames and len(filenames) > 3:
            src += f" (+{len(filenames) - 3} more)"
        work_done = (
            f"Opened {len(filenames)} VDR file(s); extracted evidence for {workstream.lower()}"
            if filenames and hit
            else (
                f"Files present ({len(filenames)}) but limited extract for this question"
                if filenames
                else "Not started — no VDR files in this category"
            )
        )
        row = {
            "question": entry["question"].replace("the target market", f"the {industry} market")
            if "market" in entry["question"].lower() and industry != "N/A (data room did not provide it)"
            else entry["question"].replace("the deal perimeter", f"{company}'s deal perimeter")
            if "perimeter" in entry["question"].lower()
            else entry["question"],
            "work_done": work_done,
            "source": src if not filenames else f"{src} {_DOC_CITE}",
            "period": periods if filenames else "—",
            "method": entry["method"],
            "status": status,
        }
        coverage_table.append(row)

        label = f"{workstream}: {row['question'][:80]}"
        if status == "complete":
            completed.append(label)
        elif status == "partial":
            planned.append(f"Deepen {workstream} evidence ({len(filenames)} file(s) opened)")
            could, gate = _impact_for_status(status, workstream)
            unfinished.append({
                "item": f"Complete {workstream} question to full evidence standard",
                "could_change": could,
                "gate": gate,
                "workstream": workstream,
            })
        else:
            planned.append(f"Start {workstream} workstream — category empty in VDR")
            blocked.append(
                f"{workstream}: cannot finish without VDR files "
                f"(Information request: {workstream} pack)"
            )
            exclusions.append({
                "item": entry["question"],
                "reason": f"No files under CDL category {workstream}",
                "state": "cannot_with_evidence",
                "workstream": workstream,
            })
            could, gate = _impact_for_status(status, workstream)
            unfinished.append({
                "item": f"Obtain and review {workstream} pack",
                "could_change": could,
                "gate": gate,
                "workstream": workstream,
            })

    # Agreement-style out-of-scope defaults (always disclose).
    exclusions.append({
        "item": "Macro-economic / socio-political overlay beyond sector packs",
        "reason": "Outside agreed commercial CDD perimeter unless sponsor expands scope",
        "state": "out_of_scope",
        "workstream": "Deal / Strategy",
    })
    exclusions.append({
        "item": "Full quality-of-earnings recreations not present in VDR",
        "reason": "Not yet commissioned / no QoE binder in data room",
        "state": "not_yet_done",
        "workstream": "Financial",
    })
    for gap in gaps:
        if any(e.get("workstream") == gap and e.get("state") == "cannot_with_evidence" for e in exclusions):
            continue
        exclusions.append({
            "item": f"Primary diligence under {gap}",
            "reason": f"CDL category '{gap}' has zero indexed files",
            "state": "cannot_with_evidence",
            "workstream": gap,
        })

    fieldwork = _find_fieldwork(corpus)
    if not fieldwork:
        fieldwork = [{
            "date": "undated — does not count as work performed",
            "participants": "N/A (data room did not provide it)",
            "type": "Interview / site visit",
            "status": "none_claimed",
            "source": _INTERNAL,
        }]

    evidenced = sum(1 for r in coverage_table if r["status"] in {"complete", "partial"})
    # Stricter: only complete counts as "evidenced" for the headline ratio.
    evidenced_strict = sum(1 for r in coverage_table if r["status"] == "complete")
    # Prompt book: "questions evidenced" — count partial as evidenced-with-limits.
    questions_evidenced = evidenced
    questions_in_scope = len(coverage_table)
    must_close = sum(1 for u in unfinished if u.get("gate") == "must_close")

    quality, reliance, qr_rationale = _quality_reliance(
        evidenced=evidenced_strict,
        in_scope=questions_in_scope,
        must_close=must_close,
        docs_read=docs_read,
        docs_available=docs_available,
    )

    insight = (
        f"Coverage record for {company}: {questions_evidenced}/{questions_in_scope} "
        f"in-scope questions have at least partial evidence; "
        f"{evidenced_strict}/{questions_in_scope} complete. "
        f"Documents read {docs_read}/{docs_available}. "
        f"{must_close} unfinished item(s) must close before a decision."
    )

    if must_close:
        conclusion = (
            f"Diligence coverage for {company} is incomplete. "
            f"{questions_evidenced}/{questions_in_scope} questions evidenced "
            f"({evidenced_strict} complete); documents read {docs_read}/{docs_available}. "
            f"{must_close} must-close item(s) remain — do not treat the pack as comprehensive."
        )
    else:
        conclusion = (
            f"Diligence coverage for {company} meets the current workplan: "
            f"{questions_evidenced}/{questions_in_scope} questions evidenced; "
            f"documents read {docs_read}/{docs_available}. "
            f"Residual items only; coverage conclusion is about completeness, not the business."
        )

    # Seed planned list with second-order picks when thin.
    if len(planned) < 2:
        seeds = _pick_sentences(
            _sentences(corpus),
            keywords=("gap", "open", "missing", "further", "confirm"),
            limit=2,
        )
        for s in seeds:
            planned.append(_clean(s, 160))

    return {
        "insight_snapshot": insight,
        "coverage_counts": {
            "questions_evidenced": questions_evidenced,
            "questions_in_scope": questions_in_scope,
            "questions_complete": evidenced_strict,
            "documents_read": docs_read,
            "documents_available": docs_available,
        },
        "coverage_table": coverage_table,
        "completed_work": completed[:12],
        "planned_work": planned[:12],
        "blocked_work": blocked[:12],
        "exclusions": exclusions[:16],
        "fieldwork": fieldwork[:8],
        "unfinished": unfinished[:12],
        "coverage_conclusion": conclusion,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr_rationale,
        "covered": covered,
        "gaps": gaps,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    company: str,
    sources: list[str],
    document_count: int,
    covered: list[str],
    gaps: list[str],
) -> dict[str, Any]:
    counts = llm.get("coverage_counts") if isinstance(llm.get("coverage_counts"), dict) else {}
    table = llm.get("coverage_table") if isinstance(llm.get("coverage_table"), list) else []
    unfinished = llm.get("unfinished") if isinstance(llm.get("unfinished"), list) else []
    must_close = sum(
        1
        for u in unfinished
        if isinstance(u, dict) and str(u.get("gate") or "").lower() in {"must_close", "must-close"}
    )
    q_evid = int(counts.get("questions_evidenced") or 0)
    q_scope = int(counts.get("questions_in_scope") or len(table) or 0)
    d_read = int(counts.get("documents_read") or len(sources) or 0)
    d_avail = int(counts.get("documents_available") or document_count or 0)
    counts = {
        "questions_evidenced": q_evid,
        "questions_in_scope": q_scope or len(table),
        "questions_complete": int(counts.get("questions_complete") or q_evid),
        "documents_read": d_read,
        "documents_available": d_avail,
    }
    llm["coverage_counts"] = counts

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        qv, rv, rationale = _quality_reliance(
            evidenced=int(counts.get("questions_complete") or 0),
            in_scope=counts["questions_in_scope"],
            must_close=must_close,
            docs_read=d_read,
            docs_available=d_avail,
        )
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        llm.setdefault("quality_reliance_rationale", rationale)
    else:
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv

    conclusion = str(llm.get("coverage_conclusion") or "").strip()
    banned = ("invest", "attractive", "compelling", "buy", "pass on the deal")
    if not conclusion or any(b in conclusion.lower() for b in banned):
        if must_close:
            conclusion = (
                f"Diligence coverage for {company} is incomplete: "
                f"{counts['questions_evidenced']}/{counts['questions_in_scope']} questions evidenced; "
                f"documents read {d_read}/{d_avail}. "
                f"{must_close} must-close item(s) remain — not comprehensive."
            )
        else:
            conclusion = (
                f"Diligence coverage for {company}: "
                f"{counts['questions_evidenced']}/{counts['questions_in_scope']} questions evidenced; "
                f"documents read {d_read}/{d_avail}."
            )
    if must_close and "comprehensive" in conclusion.lower() and "not" not in conclusion.lower():
        conclusion = (
            f"Diligence coverage for {company} is incomplete. "
            f"{counts['questions_evidenced']}/{counts['questions_in_scope']} evidenced; "
            f"{must_close} must-close item(s) remain."
        )
    llm["coverage_conclusion"] = conclusion
    llm.setdefault("covered", covered)
    llm.setdefault("gaps", gaps)
    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    # Strip legacy invest fields if model emits them.
    for dead in ("recommendation", "confidence", "key_conditions", "deliverables"):
        llm.pop(dead, None)
    return llm


def build_scope_methodology_spec(
    deal: Deal,
    *,
    index: dict[str, Any],
    company: str | None = None,
    covered: list[str] | None = None,
    gaps: list[str] | None = None,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal

    target = (company or deal.company or deal.name or "Target").strip()
    corpus, sources = gather_deal_context_corpus(deal, index)
    if not corpus:
        bits: list[str] = []
        for doc in index.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                sources.append(str(doc.get("filename") or "source"))
        corpus = "\n".join(bits)

    covered_labels = list(covered or [])
    gap_labels = list(gaps or [])
    if not covered_labels:
        from agetic_cdd_api.services_library import CDL_CATEGORIES, CDL_LABELS

        counts = index.get("category_counts") if isinstance(index.get("category_counts"), dict) else {}
        covered_labels = [CDL_LABELS[k] for k in CDL_CATEGORIES if counts.get(k)]
        gap_labels = [CDL_LABELS[k] for k in CDL_CATEGORIES if not counts.get(k)]

    vars_ = prompt_vars_from_deal(deal)
    if not vars_.get("sector"):
        industry_m = _first_match(_INDUSTRY, corpus)
        if industry_m:
            inferred = _clean(industry_m.group(0), 60)
            if "electric" in inferred.lower() and "two" in inferred.lower():
                inferred = "Electric Two-Wheelers"
            vars_["sector"] = inferred

    doc_count = int(index.get("document_count") or len(index.get("documents") or []) or 0)
    llm = _llm_scope_methodology_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        covered=covered_labels,
        gaps=gap_labels,
        document_count=doc_count,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if llm:
        return _normalise_llm_spec(
            llm,
            company=target,
            sources=sources,
            document_count=doc_count,
            covered=covered_labels,
            gaps=gap_labels,
        )

    return _heuristic_scope_methodology_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        index=index,
        covered=covered_labels,
        gaps=gap_labels,
    )


def render_scope_methodology_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    """Render prompt-book Scope & Methodology coverage record."""
    counts = spec.get("coverage_counts") if isinstance(spec.get("coverage_counts"), dict) else {}
    table = spec.get("coverage_table") if isinstance(spec.get("coverage_table"), list) else []
    exclusions = spec.get("exclusions") if isinstance(spec.get("exclusions"), list) else []
    fieldwork = spec.get("fieldwork") if isinstance(spec.get("fieldwork"), list) else []
    unfinished = spec.get("unfinished") if isinstance(spec.get("unfinished"), list) else []
    completed = spec.get("completed_work") if isinstance(spec.get("completed_work"), list) else []
    planned = spec.get("planned_work") if isinstance(spec.get("planned_work"), list) else []
    blocked = spec.get("blocked_work") if isinstance(spec.get("blocked_work"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    q_evid = counts.get("questions_evidenced", "—")
    q_scope = counts.get("questions_in_scope", "—")
    d_read = counts.get("documents_read", "—")
    d_avail = counts.get("documents_available", "—")

    parts: list[str] = [f"# {title}\n\n"]
    parts.append("## 1. Coverage Record\n\n")
    parts.append(_insight(spec.get("insight_snapshot")))
    parts.append(
        f"**Coverage counts:** {q_evid} / {q_scope} questions evidenced · "
        f"{d_read} / {d_avail} documents read.\n\n"
    )
    if counts.get("questions_complete") is not None:
        parts.append(
            f"*Of those, {counts.get('questions_complete')} marked complete "
            f"(partial still counts as evidenced, not as finished).*\n\n"
        )

    cov_rows: list[list[str]] = []
    for row in table[:12]:
        if not isinstance(row, dict):
            continue
        cov_rows.append([
            _clean(row.get("question"), 160),
            _clean(row.get("work_done"), 160),
            _clean(row.get("source"), 120),
            _clean(row.get("period"), 40),
            _clean(row.get("method"), 80),
            _clean(row.get("status"), 20),
        ])
    parts.append("### Coverage Table\n\n")
    parts.append(_table(
        ["Question", "Work Done", "Source", "Period", "Method", "Status"],
        cov_rows,
    ))

    parts.append("### Work Status Split\n\n")
    parts.append(
        f"| State | Count |\n| --- | --- |\n"
        f"| Completed | {len(completed)} |\n"
        f"| Planned (not yet done) | {len(planned)} |\n"
        f"| Blocked (cannot with current evidence) | {len(blocked)} |\n\n"
    )
    if completed:
        parts.append("**Completed**\n\n")
        for item in completed[:10]:
            parts.append(f"- {_clean(item, 220)}\n")
        parts.append("\n")
    if planned:
        parts.append("**Planned / not yet done**\n\n")
        for item in planned[:10]:
            parts.append(f"- {_clean(item, 220)}\n")
        parts.append("\n")
    if blocked:
        parts.append("**Blocked — cannot be done with current evidence**\n\n")
        for item in blocked[:10]:
            parts.append(f"- {_clean(item, 220)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    parts.append("## 2. Exclusions & Ownership\n\n")
    parts.append(
        "Three states: **not yet done**, **cannot with current evidence**, "
        "**out of scope by agreement**.\n\n"
    )
    ex_rows: list[list[str]] = []
    for row in exclusions[:16]:
        if not isinstance(row, dict):
            continue
        ex_rows.append([
            _clean(row.get("item"), 140),
            _clean(row.get("reason"), 160),
            _clean(row.get("state"), 40),
            _clean(row.get("workstream"), 40),
        ])
    parts.append(_table(["Exclusion", "Reason", "State", "Workstream"], ex_rows))
    parts.append("---\n\n")

    parts.append("## 3. Fieldwork Log (Interviews & Site Visits)\n\n")
    parts.append(
        "An undated interview does **not** count as work performed.\n\n"
    )
    fw_rows: list[list[str]] = []
    for row in fieldwork[:8]:
        if not isinstance(row, dict):
            continue
        fw_rows.append([
            _clean(row.get("date"), 60),
            _clean(row.get("participants"), 100),
            _clean(row.get("type"), 40),
            _clean(row.get("status"), 40),
        ])
    if not fw_rows:
        fw_rows = [[
            "undated — does not count as work performed",
            "N/A (data room did not provide it)",
            "—",
            "none_claimed",
        ]]
    parts.append(_table(["Date", "Participants", "Type", "Status"], fw_rows))
    parts.append("---\n\n")

    parts.append("## 4. Unfinished Work — Decision Impact\n\n")
    parts.append(
        "Ranked by whether unfinished work could change **price**, **structure**, "
        "or the **decision**. Gate: must close before a decision vs residual.\n\n"
    )
    un_rows: list[list[str]] = []
    # must_close first
    ordered = sorted(
        [u for u in unfinished if isinstance(u, dict)],
        key=lambda u: (0 if str(u.get("gate") or "").startswith("must") else 1,
                       str(u.get("could_change") or "")),
    )
    for row in ordered[:12]:
        un_rows.append([
            _clean(row.get("item"), 160),
            _clean(row.get("could_change"), 20),
            _clean(row.get("gate"), 20),
            _clean(row.get("workstream"), 40),
        ])
    parts.append(_table(["Item", "Could Change", "Gate", "Workstream"], un_rows))
    parts.append("---\n\n")

    parts.append("## 5. Coverage Conclusion\n\n")
    parts.append(f"{_clean(spec.get('coverage_conclusion'), 900)}\n\n")
    parts.append(
        "*This section concludes on diligence completeness only. "
        "It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
                 f"is the work accurate and honest about limits?\n\n")
    parts.append(f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
                 f"can a decision rest on this coverage record?\n\n")
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
