"""Compose DiligenceIQ-shaped Deal Context & Objectives documents from CDL evidence.

Remote DiligenceIQ writes a full IC-style memo (exec summary → verdict) with
``(DOC: …)`` / ``(COMPUTED FACTS)`` cites — not a file-count dump. This module
builds the same section skeleton from library text (+ optional Gemini).
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.models import Deal
from agetic_cdd_api.report_builder_base import sanitize_report_prose

_WHITESPACE = re.compile(r"\s+")
_JUNK = re.compile(r"[■▪●◆□◦\x7f]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ABBREV_DOT = re.compile(
    r"\b(?:"
    r"Inc|Ltd|LLC|Corp|Co|PLC|GmbH|"
    r"Mr|Mrs|Ms|Dr|Prof|vs|etc|"
    r"e\.g|i\.e|Fig|No|Vol|approx|"
    r"FY\d{2,4}|Q[1-4]|U\.S|U\.K|E\.U"
    r")\.",
    re.IGNORECASE,
)

_INDUSTRY = re.compile(
    r"\b(electric two[- ]wheelers?|EV two[- ]wheelers?|electric vehicles?|"
    r"two[- ]wheeler(?:s)?|battery technology|SaaS|fintech|healthcare)\b",
    re.IGNORECASE,
)
_TRANSACTION = re.compile(
    r"\b(acquisition|buyout|growth equity|growth[- ]capital|PIPE|IPO|"
    r"strategic investment|majority stake|minority stake)\b",
    re.IGNORECASE,
)
_SHARE = re.compile(
    r"(?:market share(?: of)?|share of)\s*(?:~)?(\d+(?:\.\d+)?)\s*%|"
    r"(?:~)?(\d+(?:\.\d+)?)\s*%\s*(?:market share|share)",
    re.IGNORECASE,
)
_CAGR = re.compile(
    r"(?:revenue\s+)?CAGR(?:\s+of)?\s*(?:~)?(\d+(?:\.\d+)?)\s*%|"
    r"(?:~)?(\d+(?:\.\d+)?)\s*%\s*CAGR",
    re.IGNORECASE,
)
_REVENUE = re.compile(
    r"(?:Revenue|revenue)\s*(?:\([^)]*\))?\s*(?:of|=|:)?\s*"
    r"(?:INR\s*)?(?:₹)?\s*([\d,]+(?:\.\d+)?)\s*(cr|crore|Cr|billion|B|bn|million|M)?",
    re.IGNORECASE,
)
_EBITDA = re.compile(
    r"(?:EBITDA)\s*(?:\([^)]*\))?\s*(?:of|=|:)?\s*"
    r"(?:INR\s*)?(?:₹)?\s*\(?([\d,]+(?:\.\d+)?)\)?\s*(cr|crore|Cr)?",
    re.IGNORECASE,
)
_NET_LOSS = re.compile(
    r"(?:net loss|Net Loss)\s*(?:of|=|:)?\s*"
    r"(?:INR\s*)?(?:₹)?\s*\(?([\d,]+(?:\.\d+)?)\)?\s*(cr|crore|Cr)?",
    re.IGNORECASE,
)
_MARKET_SIZE = re.compile(
    r"(?:market(?: size)?|TAM)\s*(?:of|=|:|—|-)?\s*"
    r"(?:USD|US\$|\$|₹)?\s*([\d,]+(?:\.\d+)?)\s*(B|bn|billion|cr|Cr)?",
    re.IGNORECASE,
)
_RISK_LINE = re.compile(
    r"(?:^|\n)\s*[•\-\u007f]?\s*((?:Key )?(?:Risk|Concern)s?[^\n]{10,220})",
    re.IGNORECASE,
)
_DOC_CITE = "(DOC: data room financials)"
_COMPUTED = "(COMPUTED FACTS)"

# Prefer contract / homes expansion sentences that already carry figures.
_CONTRACT_EXPANSION = re.compile(
    r"(?i)(?:municipal\s+contract|D\.?C\.?\s+municipal|anchor\s+contract|"
    r"homes?\s+(?:today|currently|from)|from\s+~?[\d,]+\s+homes?)",
)
_CIM_MARKETING = re.compile(
    r"(?i)closed-loop\s+\w+\s+leader|path to a \$\d+\s*million|"
    r"\$\d+\s*million business by \d{4}",
)


def _homes_dollar_pairs_from_corpus(corpus: str) -> dict[int, float]:
    """Map home/location counts → case dollars evidenced near each other in the pack.

    Used to keep 30k↔$10.4M and 60k↔$22.2M (etc.) from crossing when a sentence
    lists multiple targets. Never invents dollars absent from the corpus.
    """
    out: dict[int, float] = {}
    blob = corpus[:120_000] if corpus else ""
    patterns = (
        r"(?i)([\d,]+)\s*(?:homes?|locations?|units?)"
        r".{0,100}?\$\s*([\d,.]+)\s*[Mm]\b",
        r"(?i)\$\s*([\d,.]+)\s*[Mm]\b.{0,100}?"
        r"([\d,]+)\s*(?:homes?|locations?|units?)",
    )
    for idx, pat in enumerate(patterns):
        for m in re.finditer(pat, blob):
            try:
                if idx == 0:
                    homes = int(m.group(1).replace(",", ""))
                    dollars = float(m.group(2).replace(",", ""))
                else:
                    dollars = float(m.group(1).replace(",", ""))
                    homes = int(m.group(2).replace(",", ""))
            except ValueError:
                continue
            if homes < 100 or dollars <= 0:
                continue
            # Keep the first evidenced pairing for each home count.
            out.setdefault(homes, dollars)
    return out


def _align_homes_dollars(text: str, corpus: str) -> str:
    """Rewrite crossed home↔$ pairings using corpus-evidenced associations."""
    pairs = _homes_dollar_pairs_from_corpus(corpus)
    if len(pairs) < 2:
        return text
    t = text
    # Already carries both case dollars in ascending order — leave alone.
    case_vals = sorted({round(v, 2) for v in pairs.values()})
    if len(case_vals) >= 2:
        low, high = case_vals[0], case_vals[-1]
        low_s = f"{low:.2f}".rstrip("0").rstrip(".")
        high_s = f"{high:.2f}".rstrip("0").rstrip(".")
        if re.search(
            rf"(?i)\$\s*{re.escape(low_s)}\s*[Mm].{{0,60}}\$\s*{re.escape(high_s)}\s*[Mm]",
            t,
        ):
            return t
    # After each evidenced home count, if a nearby $ matches a *different*
    # case's dollars (e.g. 60k next to $10.4M), rewrite to this case's $.
    for homes, dollars in sorted(pairs.items(), key=lambda kv: -kv[0]):
        # Skip counts that only appear inside a range (30,000–60,000 homes).
        if re.search(
            rf"(?i)[\d,]+\s*[-–—]\s*({homes:,}|{homes})\b"
            rf"|({homes:,}|{homes})\s*[-–—]\s*[\d,]+",
            t,
        ) and not re.search(
            rf"(?i)(?<![-–—\d])({homes:,}|{homes})\s+(?:targeted\s+)?"
            rf"(?:homes?|locations?|units?)\b",
            t,
        ):
            continue
        hm = re.search(
            rf"(?i)(?<![-–—\d])({homes:,}|{homes})\s+(?:targeted\s+)?"
            rf"(?:homes?|locations?|units?)\b",
            t,
        )
        if not hm:
            continue
        window = t[hm.end() : hm.end() + 180]
        replaced = False
        for dm in re.finditer(r"(\$\s*)([\d,.]+)(\s*[Mm]\b)", window):
            try:
                cur = float(dm.group(2).replace(",", ""))
            except ValueError:
                continue
            if abs(cur - dollars) / max(dollars, 1e-9) < 0.03:
                break  # already correct
            # Only sibling expansion cases (e.g. 30k↔60k), not a smaller baseline
            # like 12k→$3M sitting earlier in the same sentence.
            other_vals = [
                v
                for h, v in pairs.items()
                if h != homes and max(h, homes) / max(min(h, homes), 1) <= 3.0
            ]
            if not any(abs(cur - v) / max(v, 1e-9) < 0.03 for v in other_vals):
                continue  # baseline / other non-case dollar — leave
            fmt = f"{dollars:.2f}".rstrip("0").rstrip(".")
            abs_start = hm.end() + dm.start()
            abs_end = hm.end() + dm.end()
            t = t[:abs_start] + f"{dm.group(1)}{fmt}{dm.group(3)}" + t[abs_end:]
            replaced = True
            break
        if replaced:
            continue
    return t


def _evidenced_contract_driver(
    corpus: str,
    sents: list[str],
) -> dict[str, str] | None:
    """Pick a contract/homes expansion sentence that already has $ and home counts.

    Returns None when the data room does not evidence the expansion — never
    invents baseline / case dollars from another deal.
    """
    scored: list[tuple[float, str]] = []
    for sent in sents:
        if _CIM_MARKETING.search(sent):
            continue
        if not _CONTRACT_EXPANSION.search(sent) and not re.search(
            r"(?i)[\d,]+\s+homes?.{0,80}\$|municipal",
            sent,
        ):
            continue
        homes = len(re.findall(r"(?i)[\d,]+\s*(?:[-–—]\s*[\d,]+)?\s*homes?", sent))
        dollars = re.findall(r"\$\s*[\d,.]+(?:\s*[MmBb])?", sent)
        if homes < 1 or len(dollars) < 1:
            continue
        score = float(homes) + float(len(dollars))
        if re.search(r"(?i)municipal|D\.?C\.?", sent):
            score += 2.0
        # Prefer actual / FY{n}A baselines over unlabeled plan dollars.
        if re.search(r"(?i)FY\d{4}A|FY\d{4}\s+actual|baseline", sent):
            score += 2.0
        elif re.search(r"(?i)FY\d{4}", sent):
            score += 0.5
        # Prefer sentences that already carry two case dollars (30k/60k bridge).
        if len(dollars) >= 2 and homes >= 2:
            score += 1.5
        # Penalize plan / projected dollars used as if they were the current baseline.
        if re.search(r"(?i)FY\d{4}P|FY\d{4}\s*\(plan\)|projected|plan\s+bridge", sent):
            score -= 0.5
        scored.append((score, sent))
    if not scored:
        # Fall back to a corpus window that already carries homes + $ (keep long
        # enough to finish the 2030 case — do not ellipsize mid-sentence).
        for m in re.finditer(
            r"(?i)[^.!?\n]{0,40}(?:municipal\s+contract|[\d,]+\s+homes?)"
            r"[^.!?\n]{10,360}",
            corpus[:80_000],
        ):
            chunk = _clean(m.group(0), 720)
            if _CIM_MARKETING.search(chunk):
                continue
            if not re.search(r"\$\s*[\d,.]+", chunk):
                continue
            if not re.search(r"(?i)homes?", chunk):
                continue
            scored.append((2.0, chunk))
    if not scored:
        return None
    scored.sort(key=lambda r: (-r[0], -len(r[1])))
    text = scored[0][1]
    text = _align_homes_dollars(text, corpus)
    # If the chosen sentence uses an unlabeled "$XM revenue" beside homes, but
    # the corpus already states an FY…A actual for the same contract, prefer that
    # labeled actual (still from this deal's pack — not a fixed dollar).
    if not re.search(r"(?i)FY\d{4}A", text):
        actual = re.search(
            r"(?i)(\$[\d.]+M)\s*(?:\(?\s*)?(FY\d{4}A)(?:\s+municipal\s+revenue)?",
            corpus[:100_000],
        )
        if actual and re.search(r"(?i)~?\$[\d.]+M\s+revenue|\$[\d.]+M\s*\([^)]*revenue", text):
            labeled = actual.group(0).strip()
            if "municipal" not in labeled.lower():
                labeled = f"{labeled} municipal revenue"
            text = re.sub(
                r"(?i)\(~?\$[\d.]+M\s+revenue\)",
                f"({labeled})",
                text,
                count=1,
            )
            text = re.sub(
                r"(?i)~?\$[\d.]+M\s+revenue\b",
                labeled,
                text,
                count=1,
            )
    figs = re.findall(r"\$\s*[\d,.]+(?:\s*[MmBb])?", text)
    # De-dupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for f in figs:
        key = re.sub(r"\s+", "", f.lower())
        if key in seen:
            continue
        seen.add(key)
        uniq.append(re.sub(r"\s+", "", f))
    figure = " → ".join(uniq[:3]) if uniq else None
    if not figure:
        return None
    return {"text": text, "figure": figure}


def _clean(text: Any, max_chars: int = 420) -> str:
    t = _JUNK.sub(" ", str(text or ""))
    t = _WHITESPACE.sub(" ", t).strip()
    t = sanitize_report_prose(t)
    if len(t) > max_chars:
        t = t[: max_chars - 1].rsplit(" ", 1)[0] + "…"
    return t


def _sentences(text: str) -> list[str]:
    protected = _ABBREV_DOT.sub(lambda m: m.group(0)[:-1] + "\0", text or "")
    parts = _SENTENCE_SPLIT.split(protected)
    out: list[str] = []
    for part in parts:
        s = _clean(part.replace("\0", "."), 480)
        if len(s) >= 40:
            out.append(s)
    return out


def _fmt_num(raw: str, unit: str | None = None) -> str:
    n = raw.replace(",", "")
    try:
        val = float(n)
        if val >= 100 and val == int(val):
            n = f"{int(val):,}"
        else:
            n = f"{val:g}"
    except ValueError:
        pass
    u = (unit or "").strip()
    if u.lower() in {"cr", "crore"}:
        return f"₹{n} cr"
    if u.lower() in {"b", "bn", "billion"}:
        return f"${n}B" if not n.startswith("$") else f"{n}B"
    if u.lower() in {"m", "million"}:
        return f"{n}M"
    return n


def _first_match(pattern: re.Pattern[str], text: str) -> re.Match[str] | None:
    return pattern.search(text or "")


def _first_captured_group(match: re.Match[str] | None) -> str | None:
    """Return the first non-empty capturing group, or None (never StopIteration)."""
    if match is None:
        return None
    for group in match.groups():
        if group:
            return str(group)
    return None


def _pick_sentences(
    sentences: list[str],
    *,
    keywords: tuple[str, ...],
    limit: int = 3,
    exclude: set[str] | None = None,
) -> list[str]:
    exclude = exclude or set()
    scored: list[tuple[float, str]] = []
    for sent in sentences:
        key = sent.lower()[:120]
        if key in exclude:
            continue
        lower = sent.lower()
        hits = sum(1 for kw in keywords if kw in lower)
        if not hits:
            continue
        score = float(hits)
        if re.search(r"\d", sent):
            score += 1.5
        scored.append((score, sent))
    scored.sort(key=lambda r: (-r[0], -len(r[1])))
    picked: list[str] = []
    seen: set[str] = set()
    for _, sent in scored:
        key = sent.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        picked.append(sent)
        if len(picked) >= limit:
            break
    return picked


def gather_deal_context_corpus(deal: Deal, index: dict[str, Any]) -> tuple[str, list[str]]:
    """Return (joined text, source filenames) from strategy / financial / market docs."""
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "deal_strategy",
        "company_management",
        "financial",
        "market_competition",
    }
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]
    ranked = sorted(
        docs,
        key=lambda d: (0 if d.get("cdl_category") in prefer else 1, str(d.get("filename") or "")),
    )
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:10]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        try:
            loaded = load_library_document(deal, filename) or {}
        except Exception:
            loaded = {}
        text = str(loaded.get("text") or doc.get("excerpt") or "")
        text = _JUNK.sub(" ", text)
        text = _WHITESPACE.sub(" ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:12_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 48_000:
            break
    return "\n\n".join(blobs), sources


def _llm_deal_context_spec(
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
    products_and_services: str | None = None,
    customer_types: str | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    system = compose_system(
        "deal_context_and_objectives",
        sector=sector,
        geography=geography,
        materiality=materiality,
        target_company=company,
        products_and_services=products_and_services,
        customer_types=customer_types,
        deal_perimeter=deal_perimeter,
        transaction_type=transaction_type,
        as_of_date=as_of_date,
        review_periods=review_periods,
        decision_stage=decision_stage,
    )
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "overview: {target_company, legal_entity, perimeter, buyer_context, "
        "acquirer_context, industry, transaction_type, deal_rationale, "
        "as_of_date, decision_stage},\n"
        "drivers: [{label, text, figure, source, is_hypothesis}] (exactly 3; "
        "is_hypothesis true when figure is missing),\n"
        "thesis_read (string),\n"
        "hypotheses_insight (string),\n"
        "hypotheses: [{hypothesis, threshold, fail_test, tested_by_agent, "
        "evidence, risk_level}] (3 to 6; tested_by_agent is a prompt-book "
        "agent slug),\n"
        "hypotheses_read (string),\n"
        "risks_insight (string),\n"
        "risk_bullets: [{level, text, size}] (High/Medium/Low),\n"
        "risk_table: [{risk, impact, evidence, mitigation}] (up to 4),\n"
        "risks_read (string),\n"
        "questions_insight (string),\n"
        "questions: [{question, required_records, unlocking_document, "
        "decision_effect, why, priority, owner, timing, closure_test, "
        "interim_treatment}] (3 to 6; priority is "
        "mandatory_pre_decision|signing_condition|closing_condition|"
        "residual_uncertainty),\n"
        "questions_read (string),\n"
        "fact_ledger: [{fact, value, unit, period, basis, source_locator}] "
        "(15 to 25 rows; basis is actual|LTM|forecast|budget; "
        "source_locator is file + sheet/cell, page, or slide),\n"
        "metrics_insight (string),\n"
        "metrics: [{metric, value, source, commentary}] (optional high-signal subset),\n"
        "metrics_read (string),\n"
        "synthesis (string — frame only; no invest/pass language),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _normalize_deal_context_questions(rows: Any) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    if not isinstance(rows, list):
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Preserve legacy why / unlocking_document aliases into shared schema.
        loose = dict(row)
        if loose.get("why") and not loose.get("decision_effect"):
            loose["decision_effect"] = loose["why"]
        if loose.get("unlocking_document") and not loose.get("required_records"):
            loose["required_records"] = loose["unlocking_document"]
        normalized = normalize_question(loose)
        # Keep legacy keys for older renderers / consumers.
        normalized["why"] = normalized["decision_effect"]
        normalized["unlocking_document"] = normalized["required_records"]
        if not normalized.get("closure_test"):
            doc = normalized["required_records"] or "named source record"
            normalized["closure_test"] = (
                f"Receive {doc} covering the stated period/population and "
                "reconcile to the fact ledger"
            )
        if not normalized.get("timing"):
            normalized["timing"] = (
                "before IC"
                if normalized["priority"] == "mandatory_pre_decision"
                else "per deal timetable"
            )
        out.append(normalized)
    return out


def _ensure_perimeter_questions(
    questions: list[dict[str, str]],
    *,
    overview: dict[str, Any],
) -> list[dict[str, str]]:
    """Add Questions rows for unevidenced perimeter slots."""
    existing_q = " ".join(q.get("question", "").lower() for q in questions)
    gaps = []
    perimeter = str(overview.get("perimeter") or "")
    if perimeter.startswith("N/A") or "information request" in perimeter.lower():
        if "perimeter" not in existing_q:
            gaps.append(
                {
                    "question": "What legal entities and operations are inside the acquisition perimeter?",
                    "required_records": "SPA draft / perimeter schedule / carve-out map",
                    "decision_effect": "Defines what is valued and diligence-covered",
                    "priority": "mandatory_pre_decision",
                    "owner": "deal lead",
                    "timing": "before IC",
                    "closure_test": "Named entities + % ownership reconcile to SPA schedule",
                    "interim_treatment": "Frame LIMITED; do not treat group totals as perimeter",
                }
            )
    txn = str(overview.get("transaction_type") or "")
    if txn.startswith("N/A") or "information request" in txn.lower() or not txn.strip():
        if "transaction" not in existing_q:
            gaps.append(
                {
                    "question": "What is the transaction type (share / asset / merger)?",
                    "required_records": "Teaser / SPA / engagement letter",
                    "decision_effect": "Changes diligence scope and structure conditions",
                    "priority": "mandatory_pre_decision",
                    "owner": "deal lead",
                    "timing": "before IC",
                    "closure_test": "Transaction type stated in executed or draft SPA",
                    "interim_treatment": "Assume unknown; avoid structure-specific conclusions",
                }
            )
    if not gaps:
        return questions
    return _normalize_deal_context_questions(list(questions) + gaps)[:8]


_FY_REVENUE_SERIES = re.compile(
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+"
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?.{0,80}?"
    r"Revenue\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)
_LEGAL_NAME = re.compile(
    r"(?:Legal Name|legal name)\s+([A-Z][A-Za-z0-9 &.,'\-]{4,80}?(?:Limited|Ltd|LLC|Inc|PLC)?)",
    re.IGNORECASE,
)
_HEADCOUNT_FACT = re.compile(
    r"Total Headcount\s*\(?FTE\)?[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)",
    re.IGNORECASE,
)


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _driver_row(
    *,
    label: str,
    text: str,
    figure: str | None = None,
    source: str = _DOC_CITE,
) -> dict[str, Any]:
    has_figure = bool(figure and str(figure).strip())
    return {
        "label": label,
        "text": text if has_figure else f"[Hypothesis] {text}",
        "figure": figure or "N/A (data room did not provide it)",
        "source": source if has_figure else "N/A",
        "is_hypothesis": not has_figure,
    }


def _fact(
    *,
    fact: str,
    value: str,
    unit: str,
    period: str,
    basis: str,
    source_locator: str,
) -> dict[str, str]:
    return {
        "fact": fact,
        "value": value,
        "unit": unit,
        "period": period,
        "basis": basis,
        "source_locator": source_locator,
    }


def _quality_reliance_from_coverage(*, fact_count: int, gaps: int) -> tuple[str, str, str]:
    """Honest Quality/Reliance from how much of the frame is evidenced."""
    quality = "PASS"  # honest about limits is still PASS
    if fact_count >= 15 and gaps <= 2:
        reliance = "READY"
        rationale = (
            f"Frame is usable: {fact_count} headline facts with locators; "
            f"limited open information requests."
        )
    elif fact_count >= 8:
        reliance = "LIMITED"
        rationale = (
            f"{fact_count} facts evidenced; {gaps} material gaps remain — "
            f"decision can lean on the frame only with those limits disclosed."
        )
    else:
        reliance = "BLOCKED"
        rationale = (
            f"Only {fact_count} headline facts located; IC cannot rely on this "
            f"frame until accounting / perimeter gaps are closed."
        )
    return quality, reliance, rationale


def _heuristic_deal_context_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    document_count: int,
) -> dict[str, Any]:
    sents = _sentences(corpus)
    industry_m = _first_match(_INDUSTRY, corpus)
    industry = _clean(industry_m.group(0), 60).title() if industry_m else "N/A (data room did not provide it)"
    if industry_m and "electric" in industry.lower() and "two" in industry.lower():
        industry = "Electric Two-Wheelers"

    txn_m = _first_match(_TRANSACTION, corpus)
    transaction = _clean(txn_m.group(0), 40).title() if txn_m else "Acquisition"

    share = _first_captured_group(_first_match(_SHARE, corpus))
    cagr = _first_captured_group(_first_match(_CAGR, corpus))

    rev_m = _first_match(_REVENUE, corpus)
    revenue = _fmt_num(rev_m.group(1), rev_m.group(2)) if rev_m else None

    ebitda_m = _first_match(_EBITDA, corpus)
    ebitda = _fmt_num(ebitda_m.group(1), ebitda_m.group(2)) if ebitda_m else None

    loss_m = _first_match(_NET_LOSS, corpus)
    net_loss = _fmt_num(loss_m.group(1), loss_m.group(2)) if loss_m else None

    mkt_m = _first_match(_MARKET_SIZE, corpus)
    market_size = _fmt_num(mkt_m.group(1), mkt_m.group(2)) if mkt_m else None

    growth_sents = _pick_sentences(
        sents,
        keywords=("growth", "demand", "incentive", "sustainability", "tailwind", "cagr"),
        limit=4,
    )
    # Prefer evidenced contract expansion over figure-less CIM marketing.
    growth_sents = [g for g in growth_sents if not _CIM_MARKETING.search(g)]
    contract_driver = _evidenced_contract_driver(corpus, sents)

    share_sents = _pick_sentences(
        sents,
        keywords=("market share", "share", "leading", "position"),
        limit=2,
        exclude={g.lower()[:120] for g in growth_sents},
    )
    revenue_sents = _pick_sentences(
        sents,
        keywords=("revenue", "units sold", "ebitda", "profitability"),
        limit=2,
        exclude={g.lower()[:120] for g in growth_sents + share_sents},
    )

    drivers: list[dict[str, Any]] = []
    if contract_driver:
        drivers.append(_driver_row(
            label="Driver 1",
            text=contract_driver["text"],
            figure=contract_driver.get("figure"),
            source=_DOC_CITE,
        ))
    elif cagr or growth_sents or industry != "N/A (data room did not provide it)":
        drivers.append(_driver_row(
            label="Driver 1",
            text=(
                growth_sents[0]
                if growth_sents
                else f"Growing demand in {industry}, supported by policy and consumer adoption."
            ),
            figure=f"{cagr}% CAGR" if cagr else None,
            source=_COMPUTED if cagr else _DOC_CITE,
        ))
    if share or share_sents:
        drivers.append(_driver_row(
            label="Driver 2",
            text=(
                f"Competitive share position for {company}"
                if share
                else (share_sents[0] if share_sents else f"Share trajectory for {company}.")
            ),
            figure=f"{share}% market share" if share else None,
            source=_DOC_CITE,
        ))
    if revenue or revenue_sents:
        drivers.append(_driver_row(
            label="Driver 3",
            text=(
                revenue_sents[0]
                if revenue_sents
                else f"Revenue scale-up evidenced in the financial pack."
            ),
            figure=revenue,
            source=_DOC_CITE if revenue else _COMPUTED,
        ))
    while len(drivers) < 3:
        drivers.append(_driver_row(
            label=f"Driver {len(drivers) + 1}",
            text="Thesis driver not yet evidenced in the data room.",
            figure=None,
        ))

    rationale_bits = []
    if industry != "N/A (data room did not provide it)":
        rationale_bits.append(f"Growing demand for {industry.lower()}")
    if share:
        rationale_bits.append("market share position")
    if cagr or revenue:
        rationale_bits.append("revenue scale")
    deal_rationale = (
        ", ".join(rationale_bits)
        if rationale_bits
        else f"Commercial diligence engagement on {company} across {document_count} VDR files"
    )

    legal_m = _LEGAL_NAME.search(corpus)
    legal_entity = _clean(legal_m.group(1), 80) if legal_m else company
    perimeter = _info_request("acquisition perimeter / carve-out boundaries")
    buyer_context = _info_request("buyer / sponsor context")

    insight = (
        f"This engagement frames {company}"
        + (f" ({legal_entity})" if legal_entity != company else "")
        + (f" in {industry}" if "N/A" not in industry else "")
        + f" for diligence — establishing drivers, fail-able hypotheses, and a fact ledger {_DOC_CITE}."
    )

    hypotheses = [
        {
            "hypothesis": (
                f"The {industry.lower()} market sustains growth"
                + (f" at or above {cagr}% CAGR" if cagr else "")
            ),
            "threshold": f"Market CAGR stays at or above {cagr}%" if cagr else "Market growth stays positive YoY",
            "fail_test": "Observed market CAGR falls below the stated threshold on the next market update",
            "tested_by_agent": "market_volume_and_growth",
            "evidence": growth_sents[0] if growth_sents else f"Policy and demand signals {_DOC_CITE}.",
            "risk_level": "Medium",
        },
        {
            "hypothesis": (
                f"{company} holds share"
                + (f" at or above {share}%" if share else " versus named peers")
            ),
            "threshold": f"Share ≥ {share}%" if share else "Share does not decline vs peer set",
            "fail_test": "Reported share falls below threshold in the next competitive pack",
            "tested_by_agent": "competitor_identification",
            "evidence": share_sents[0] if share_sents else f"Brand / distribution evidence {_DOC_CITE}.",
            "risk_level": "Medium",
        },
        {
            "hypothesis": f"{company} reaches an earnings inflection toward positive EBITDA",
            "threshold": "EBITDA margin crosses 0% within the forecast horizon" if not ebitda else f"EBITDA holds near {ebitda}",
            "fail_test": "Forward case shows sustained negative EBITDA with no credible path",
            "tested_by_agent": "historical_performance",
            "evidence": revenue_sents[0] if revenue_sents else f"P&L path {_DOC_CITE}.",
            "risk_level": "High",
        },
    ]

    risk_sents = _pick_sentences(
        sents,
        keywords=("risk", "loss", "dependency", "competition", "subsidy", "regulatory", "concern"),
        limit=4,
    )
    for m in _RISK_LINE.finditer(corpus):
        risk_sents.insert(0, _clean(m.group(1), 220))
    risk_sents = list(dict.fromkeys(risk_sents))[:4]

    risk_bullets = [
        {
            "level": "High",
            "size": net_loss or "N/A",
            "text": (
                f"Earnings / cash trajectory"
                + (f" (net loss {net_loss})" if net_loss else "")
                + f" {_DOC_CITE}."
            ),
        },
        {
            "level": "Medium",
            "size": f"{share}% share" if share else "N/A",
            "text": (
                risk_sents[0]
                if risk_sents
                else f"Competitive intensity in {industry.lower()} {_DOC_CITE}."
            ),
        },
        {
            "level": "Low",
            "size": "policy-linked",
            "text": f"Regulatory / incentive exposure {_DOC_CITE}.",
        },
    ]
    risk_table = [
        {
            "risk": "Competitive intensity",
            "impact": "Share / pricing pressure",
            "evidence": _DOC_CITE,
            "mitigation": "Test via competitor and share agents",
        },
        {
            "risk": "Regulatory / incentive change",
            "impact": "Demand / mix shift",
            "evidence": _DOC_CITE,
            "mitigation": "Map policy sensitivity in demand-drivers workstream",
        },
        {
            "risk": "Path to positive earnings",
            "impact": "Returns / funding need",
            "evidence": _DOC_CITE,
            "mitigation": "Stress cost and volume cases in financials",
        },
    ]

    questions = _normalize_deal_context_questions(
        [
            {
                "priority": "mandatory_pre_decision",
                "question": f"Will {company} hold share amid rising competition?",
                "why": "Share underpins the growth driver; could change price/structure",
                "unlocking_document": "Market / competition pack with share by segment and period",
                "owner": "market lead",
                "timing": "before IC",
                "closure_test": "Share by segment×period on matched Market Definition perimeter",
                "interim_treatment": "Growth driver labelled hypothesis; Reliance LIMITED",
            },
            {
                "priority": "signing_condition",
                "question": f"What policy changes would move demand for {industry.lower()}?",
                "why": "Incentive exposure can reprice the thesis",
                "unlocking_document": "Regulatory / FAME (or local equivalent) policy note",
                "owner": "regulatory lead",
                "timing": "per deal timetable",
                "closure_test": "Dated policy note with jurisdiction and effective dates",
                "interim_treatment": "Demand-driver sensitivity held as untested",
            },
            {
                "priority": "mandatory_pre_decision",
                "question": f"What is the accounting path to positive EBITDA for {company}?",
                "why": "Earnings inflection is a must-be-true hypothesis",
                "unlocking_document": "Audited P&L + management forecast workbook (sheet + cells)",
                "owner": "financials lead",
                "timing": "before IC",
                "closure_test": "Bridge from latest actual EBITDA to plan with formula+inputs",
                "interim_treatment": "Exclude earnings inflection from READY reliance",
            },
        ]
    )

    fact_ledger: list[dict[str, str]] = []
    src0 = sources[0] if sources else "data room"
    series = _FY_REVENUE_SERIES.search(corpus)
    if series:
        years = [series.group(i) for i in range(1, 6)]
        vals = [series.group(i) for i in range(6, 11)]
        for year, raw in zip(years, vals):
            basis = "forecast" if year >= "2024" else "actual"
            fact_ledger.append(_fact(
                fact=f"Revenue FY{year}",
                value=_fmt_num(raw, "cr"),
                unit="INR crore",
                period=f"FY{year}",
                basis=basis,
                source_locator=f"{next((s for s in sources if 'financial' in s.lower()), src0)} · P&L Revenue row",
            ))
    elif revenue:
        fact_ledger.append(_fact(
            fact="Revenue (extracted)",
            value=revenue,
            unit="money",
            period="see source",
            basis="actual",
            source_locator=f"{src0} · revenue mention",
        ))
    if cagr:
        fact_ledger.append(_fact(
            fact="Revenue CAGR",
            value=f"{cagr}%",
            unit="percent",
            period="multi-year",
            basis="computed",
            source_locator=_COMPUTED,
        ))
    if ebitda:
        fact_ledger.append(_fact(
            fact="EBITDA",
            value=ebitda,
            unit="money",
            period="see source",
            basis="actual",
            source_locator=f"{next((s for s in sources if 'financial' in s.lower()), src0)} · EBITDA line",
        ))
    if net_loss:
        fact_ledger.append(_fact(
            fact="Net loss",
            value=net_loss,
            unit="money",
            period="see source",
            basis="actual",
            source_locator=f"{src0} · PAT / net loss",
        ))
    if share:
        fact_ledger.append(_fact(
            fact="Market share",
            value=f"{share}%",
            unit="percent",
            period="see source",
            basis="actual",
            source_locator=f"{next((s for s in sources if 'market' in s.lower()), src0)} · share figure",
        ))
    if market_size:
        fact_ledger.append(_fact(
            fact="Market size / TAM",
            value=market_size,
            unit="money",
            period="see source",
            basis="actual",
            source_locator=_DOC_CITE,
        ))
    hc = _HEADCOUNT_FACT.search(corpus)
    if hc:
        nums = re.findall(r"[\d,]+", hc.group(1))
        if nums:
            raw = nums[-1].replace(",", "")
            try:
                hc_val = f"{int(raw):,}"
            except ValueError:
                hc_val = nums[-1]
            fact_ledger.append(_fact(
                fact="Total headcount (FTE)",
                value=hc_val,
                unit="count",
                period="latest reported",
                basis="actual",
                source_locator=f"{next((s for s in sources if 'hr' in s.lower()), src0)} · headcount table",
            ))
    fact_ledger.append(_fact(
        fact="Legal entity",
        value=legal_entity,
        unit="name",
        period="current",
        basis="actual",
        source_locator=f"{next((s for s in sources if 'corporate' in s.lower() or 'overview' in s.lower()), src0)}",
    ))
    fact_ledger.append(_fact(
        fact="Industry / sector",
        value=industry,
        unit="label",
        period="current",
        basis="actual",
        source_locator=_DOC_CITE,
    ))
    fact_ledger.append(_fact(
        fact="Transaction type",
        value=transaction,
        unit="label",
        period="current",
        basis="actual",
        source_locator=_DOC_CITE,
    ))
    # Pad to at least 15 with explicit information requests (unknown ≠ negative).
    gap_labels = [
        "Largest customer revenue share",
        "LTM revenue",
        "Gross margin (latest actual)",
        "Acquisition perimeter",
        "Buyer / sponsor identity",
        "Current-year budget revenue",
        "Final forecast-year revenue",
        "Working capital / cash burn (monthly)",
        "Net debt",
        "Customer retention / churn",
    ]
    gaps_needed = 0
    for label in gap_labels:
        if len(fact_ledger) >= 15:
            break
        fact_ledger.append(_fact(
            fact=label,
            value="N/A (data room did not provide it)",
            unit="—",
            period="—",
            basis="—",
            source_locator=_info_request(label),
        ))
        gaps_needed += 1

    metrics: list[dict[str, str]] = []
    for row in fact_ledger[:6]:
        if row["value"].startswith("N/A"):
            continue
        metrics.append({
            "metric": row["fact"],
            "value": row["value"],
            "source": row["source_locator"],
            "commentary": f"{row['basis']} · {row['period']}",
        })
    if not metrics:
        metrics.append({
            "metric": "VDR coverage",
            "value": str(document_count),
            "source": _DOC_CITE,
            "commentary": "Files indexed into the Central Data Library",
        })

    evidenced = sum(1 for r in fact_ledger if not str(r.get("value", "")).startswith("N/A"))
    quality, reliance, qr_rationale = _quality_reliance_from_coverage(
        fact_count=evidenced,
        gaps=gaps_needed,
    )

    synthesis = (
        f"The engagement frames {company}"
        + (f" in {industry}" if "N/A" not in industry else "")
        + f" with three thesis drivers, fail-able hypotheses, and a {len(fact_ledger)}-row fact ledger {_DOC_CITE}.\n\n"
        "This document does not approve or reject the deal. Synthesis agents own the decision.\n\n"
        "Non-obvious frame points:\n"
        f"* Drivers without figures are labelled hypotheses, not facts {_DOC_CITE}.\n"
        f"* Accounting records are preferred over CIM language for headline numbers {_DOC_CITE}.\n"
        f"* Open questions name the unlocking document rather than vague 'further diligence' {_DOC_CITE}."
    )

    return {
        "insight_snapshot": _clean(insight, 700),
        "overview": {
            "target_company": company,
            "legal_entity": legal_entity,
            "perimeter": perimeter,
            "buyer_context": buyer_context,
            "acquirer_context": buyer_context,
            "industry": industry,
            "transaction_type": transaction,
            "deal_rationale": deal_rationale,
        },
        "drivers": drivers[:3],
        "thesis_read": (
            f"The frame is driven by demand, share, and revenue evidence for {company}; "
            f"drivers without numbers are flagged as hypotheses."
        ),
        "hypotheses_insight": (
            f"Must-be-true tests for {company}: market growth, share durability, and earnings inflection — "
            f"each with a fail threshold and owning agent."
        ),
        "hypotheses": hypotheses,
        "hypotheses_read": (
            "Hypotheses are written so they can fail; named agents will test them downstream."
        ),
        "risks_insight": (
            "Risks already visible in the records, sized where the data room allows."
        ),
        "risk_bullets": risk_bullets,
        "risk_table": risk_table,
        "risks_read": (
            "Risks inform workstream priority; they are not an investment recommendation."
        ),
        "questions_insight": (
            "Open questions that block the thesis, each with an unlocking document."
        ),
        "questions": questions,
        "questions_read": (
            "Priority order tracks what would change the frame before synthesis."
        ),
        "fact_ledger": fact_ledger[:25],
        "metrics_insight": (
            "High-signal subset of the fact ledger for quick IC scanning."
        ),
        "metrics": metrics,
        "metrics_read": (
            f"Full ledger has {len(fact_ledger)} rows; unknowns are information requests, not negatives."
        ),
        "synthesis": synthesis,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr_rationale,
        "primary_sources": sources[:12],
        "composer": "heuristic_v1",
    }


def build_deal_context_spec(
    deal: Deal,
    *,
    index: dict[str, Any],
    company: str | None = None,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal

    target = (company or deal.company or deal.name or "Target").strip()
    corpus, sources = gather_deal_context_corpus(deal, index)
    if not corpus:
        # Fall back to excerpts only.
        bits = []
        for doc in index.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                sources.append(str(doc.get("filename") or "source"))
        corpus = "\n".join(bits)

    vars_ = prompt_vars_from_deal(deal)
    # Infer sector from corpus industry match when deal has none.
    if not vars_.get("sector"):
        industry_m = _first_match(_INDUSTRY, corpus)
        if industry_m:
            inferred = _clean(industry_m.group(0), 60)
            if "electric" in inferred.lower() and "two" in inferred.lower():
                inferred = "Electric Two-Wheelers"
            vars_["sector"] = inferred

    llm = _llm_deal_context_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
        deal_perimeter=vars_.get("deal_perimeter"),
        transaction_type=vars_.get("transaction_type"),
        as_of_date=vars_.get("as_of_date"),
        review_periods=vars_.get("review_periods"),
        decision_stage=vars_.get("decision_stage"),
        products_and_services=vars_.get("products_and_services"),
        customer_types=vars_.get("customer_types"),
    )
    if llm:
        llm.setdefault("overview", {})
        if isinstance(llm["overview"], dict):
            ov = llm["overview"]
            ov.setdefault("target_company", target)
            ov.setdefault(
                "legal_entity",
                ov.get("target_company") or target,
            )
            if vars_.get("deal_perimeter"):
                ov.setdefault("perimeter", vars_["deal_perimeter"])
            else:
                ov.setdefault(
                    "perimeter",
                    _info_request("acquisition perimeter / carve-out boundaries"),
                )
            if vars_.get("transaction_type"):
                ov.setdefault("transaction_type", vars_["transaction_type"])
            if vars_.get("as_of_date"):
                ov.setdefault("as_of_date", vars_["as_of_date"])
            if vars_.get("decision_stage"):
                ov.setdefault("decision_stage", vars_["decision_stage"])
            ov.setdefault(
                "buyer_context",
                ov.get("acquirer_context")
                or _info_request("buyer / sponsor context"),
            )
        # Normalise drivers: flag missing figures as hypotheses.
        # Prefer an evidenced contract/homes sentence from this deal's corpus
        # over figure-less CIM marketing — never paste another deal's numbers.
        contract_driver = _evidenced_contract_driver(corpus, _sentences(corpus))
        drivers = llm.get("drivers") if isinstance(llm.get("drivers"), list) else []
        normalised: list[dict[str, Any]] = []
        for i, d in enumerate(drivers[:3], start=1):
            if not isinstance(d, dict):
                continue
            fig = d.get("figure")
            has_fig = bool(fig) and "N/A" not in str(fig)
            row = dict(d)
            row.setdefault("label", f"Driver {i}")
            text = str(row.get("text") or "")
            if contract_driver and (
                _CIM_MARKETING.search(text)
                or (i == 1 and not re.search(r"(?i)homes?|\$\s*[\d,.]+", text))
            ):
                if i == 1 or _CIM_MARKETING.search(text):
                    row["text"] = contract_driver["text"]
                    row["figure"] = contract_driver.get("figure")
                    row["source"] = _DOC_CITE
                    row["is_hypothesis"] = False
                    normalised.append(row)
                    continue
            row["is_hypothesis"] = bool(d.get("is_hypothesis")) or not has_fig
            if row["is_hypothesis"] and not str(row.get("text", "")).startswith("[Hypothesis]"):
                row["text"] = f"[Hypothesis] {_clean(row.get('text'), 400)}"
            normalised.append(row)
        if contract_driver and normalised:
            d0 = normalised[0]
            if _CIM_MARKETING.search(str(d0.get("text") or "")) or not re.search(
                r"(?i)homes?|\$\s*[\d,.]+", str(d0.get("text") or "")
            ):
                normalised[0] = _driver_row(
                    label="Driver 1",
                    text=contract_driver["text"],
                    figure=contract_driver.get("figure"),
                    source=_DOC_CITE,
                )
        if normalised:
            llm["drivers"] = normalised
        # Hypotheses must name a testing agent.
        hyps = llm.get("hypotheses") if isinstance(llm.get("hypotheses"), list) else []
        for h in hyps:
            if isinstance(h, dict) and not h.get("tested_by_agent"):
                h["tested_by_agent"] = "historical_performance"
        llm["questions"] = _ensure_perimeter_questions(
            _normalize_deal_context_questions(llm.get("questions")),
            overview=llm["overview"] if isinstance(llm.get("overview"), dict) else {},
        )
        ledger = llm.get("fact_ledger") if isinstance(llm.get("fact_ledger"), list) else []
        from agetic_cdd_api.prompt_book import normalize_verdicts

        if not llm.get("quality_verdict") or not llm.get("reliance_verdict"):
            evidenced = sum(
                1
                for r in ledger
                if isinstance(r, dict) and not str(r.get("value", "")).startswith("N/A")
            )
            gaps = sum(
                1
                for r in ledger
                if isinstance(r, dict) and str(r.get("value", "")).startswith("N/A")
            )
            q, rel, rationale = _quality_reliance_from_coverage(
                fact_count=evidenced,
                gaps=gaps,
            )
            llm.setdefault("quality_verdict", q)
            llm.setdefault("reliance_verdict", rel)
            llm.setdefault("quality_reliance_rationale", rationale)
        qv, rv = normalize_verdicts(
            quality=llm.get("quality_verdict"),
            reliance=llm.get("reliance_verdict"),
            default_quality="PASS",
            default_reliance="LIMITED",
        )
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        # Strip investment-verdict fields if a model still emits them.
        for key in ("recommendation", "confidence", "verdict_insight", "key_conditions"):
            llm.pop(key, None)
        llm["primary_sources"] = sources[:12]
        llm["deal_slots"] = {k: v for k, v in vars_.items() if v}
        llm["composer"] = "gemini_v1"
        return llm

    heur = _heuristic_deal_context_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        document_count=int(index.get("document_count") or 0),
    )
    if isinstance(heur.get("overview"), dict):
        ov = heur["overview"]
        if vars_.get("deal_perimeter"):
            ov["perimeter"] = vars_["deal_perimeter"]
        if vars_.get("transaction_type"):
            ov["transaction_type"] = vars_["transaction_type"]
        if vars_.get("as_of_date"):
            ov["as_of_date"] = vars_["as_of_date"]
        if vars_.get("decision_stage"):
            ov["decision_stage"] = vars_["decision_stage"]
    heur["questions"] = _ensure_perimeter_questions(
        _normalize_deal_context_questions(heur.get("questions")),
        overview=heur["overview"] if isinstance(heur.get("overview"), dict) else {},
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


def render_deal_context_markdown(title: str, spec: dict[str, Any], *, sources: list[str] | None = None) -> str:
    """Render prompt-book Deal Context section skeleton from a structured spec."""
    overview = spec.get("overview") if isinstance(spec.get("overview"), dict) else {}
    drivers = spec.get("drivers") if isinstance(spec.get("drivers"), list) else []
    hypotheses = spec.get("hypotheses") if isinstance(spec.get("hypotheses"), list) else []
    risk_bullets = spec.get("risk_bullets") if isinstance(spec.get("risk_bullets"), list) else []
    risk_table = spec.get("risk_table") if isinstance(spec.get("risk_table"), list) else []
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    fact_ledger = spec.get("fact_ledger") if isinstance(spec.get("fact_ledger"), list) else []
    metrics = spec.get("metrics") if isinstance(spec.get("metrics"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    def insight(text: Any) -> str:
        body = _clean(text, 700)
        return f"**Insight Snapshot:** {body}\n\n" if body else ""

    def table(headers: list[str], rows: list[list[str]]) -> str:
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

    parts: list[str] = [f"# {title}\n\n", "## 1. Executive Summary\n\n"]
    parts.append(insight(spec.get("insight_snapshot")))
    parts.append("### Deal Overview\n")
    parts.append(table(
        ["Parameter", "Details"],
        [
            ["Target Company", str(overview.get("target_company") or "—")],
            ["Legal Entity", str(overview.get("legal_entity") or overview.get("target_company") or "—")],
            ["Perimeter", str(overview.get("perimeter") or _info_request("acquisition perimeter"))],
            [
                "Buyer / Investor Context",
                str(
                    overview.get("buyer_context")
                    or overview.get("acquirer_context")
                    or _info_request("buyer / sponsor context")
                ),
            ],
            ["Industry", str(overview.get("industry") or "—")],
            ["Transaction Type", str(overview.get("transaction_type") or "—")],
            ["As-of Date", str(overview.get("as_of_date") or "—")],
            ["Decision Stage", str(overview.get("decision_stage") or "—")],
            ["Deal Rationale", str(overview.get("deal_rationale") or "—")],
        ],
    ))
    parts.append("### Investment Thesis (Top 3 Drivers)\n")
    for i, driver in enumerate(drivers[:3], start=1):
        if isinstance(driver, dict):
            label = str(driver.get("label") or f"Driver {i}")
            text = _clean(driver.get("text"), 420)
            figure = _clean(driver.get("figure"), 80)
            source = _clean(driver.get("source"), 80)
            hyp = driver.get("is_hypothesis")
            fig_bit = f" — **Figure:** {figure} {source}" if figure and figure != "—" else ""
            tag = " *(hypothesis — no figure)*" if hyp else ""
            parts.append(f"- **{label}:** {text}{fig_bit}{tag}\n")
        else:
            parts.append(f"- **Driver {i}:** {_clean(driver, 420)}\n")
    parts.append("\n")
    if spec.get("thesis_read"):
        parts.append(f"**Read:** {_clean(spec.get('thesis_read'), 520)}\n\n")
    parts.append("---\n\n")

    parts.append("## 2. Key Investment Hypotheses (Must-Be-True)\n\n")
    parts.append(insight(spec.get("hypotheses_insight")))
    hyp_rows = []
    for i, row in enumerate(hypotheses[:6], start=1):
        if not isinstance(row, dict):
            continue
        hyp_rows.append([
            str(i),
            _clean(row.get("hypothesis"), 200),
            _clean(row.get("threshold") or row.get("fail_test"), 160),
            _clean(row.get("tested_by_agent") or "—", 60),
            _clean(row.get("evidence"), 160),
            str(row.get("risk_level") or "Medium"),
        ])
    parts.append(table(
        ["#", "Hypothesis", "Fail Threshold", "Tested By", "Evidence", "Risk"],
        hyp_rows,
    ))
    if spec.get("hypotheses_read"):
        parts.append(f"**Read:** {_clean(spec.get('hypotheses_read'), 420)}\n\n")
    parts.append("---\n\n")

    parts.append("## 3. Critical Risks & Red Flags\n\n")
    parts.append(insight(spec.get("risks_insight")))
    for bullet in risk_bullets[:5]:
        if isinstance(bullet, dict):
            level = str(bullet.get("level") or "Medium")
            size = bullet.get("size")
            text = _clean(bullet.get("text"), 320)
            size_bit = f" (size: {_clean(size, 40)})" if size else ""
            parts.append(f"- **{level} Risk{size_bit}:** {text}\n")
        elif bullet:
            parts.append(f"- {_clean(bullet, 320)}\n")
    parts.append("\n")
    risk_rows = []
    for row in risk_table[:5]:
        if not isinstance(row, dict):
            continue
        risk_rows.append([
            _clean(row.get("risk"), 80),
            _clean(row.get("impact"), 80),
            _clean(row.get("evidence"), 80),
            _clean(row.get("mitigation"), 120),
        ])
    parts.append(table(["Risk", "Impact", "Evidence", "Mitigation"], risk_rows))
    if spec.get("risks_read"):
        parts.append(f"**Read:** {_clean(spec.get('risks_read'), 420)}\n\n")
    parts.append("---\n\n")

    parts.append("## 4. Questions and Inputs Required\n\n")
    parts.append(insight(spec.get("questions_insight")))
    q_rows = []
    for row in questions[:8]:
        if not isinstance(row, dict):
            continue
        q_rows.append([
            str(row.get("priority") or "residual_uncertainty"),
            _clean(row.get("question"), 160),
            _clean(row.get("decision_effect") or row.get("why"), 100),
            _clean(
                row.get("required_records") or row.get("unlocking_document") or "—",
                120,
            ),
            _clean(row.get("owner") or "unassigned", 40),
            _clean(row.get("timing") or "—", 40),
            _clean(row.get("closure_test") or "—", 100),
            _clean(row.get("interim_treatment") or "—", 80),
        ])
    parts.append(
        table(
            [
                "Priority",
                "Question",
                "Decision Effect",
                "Required Records",
                "Owner",
                "Timing",
                "Closure Test",
                "Interim",
            ],
            q_rows,
        )
    )
    if spec.get("questions_read"):
        parts.append(f"**Read:** {_clean(spec.get('questions_read'), 320)}\n\n")
    parts.append("---\n\n")

    parts.append("## 5. Headline Fact Ledger\n\n")
    parts.append(insight(
        spec.get("metrics_insight")
        or "15–25 headline facts an IC expects on page one, each with a locator."
    ))
    ledger_rows = []
    for row in fact_ledger[:25]:
        if not isinstance(row, dict):
            continue
        ledger_rows.append([
            _clean(row.get("fact"), 80),
            _clean(row.get("value"), 60),
            _clean(row.get("unit"), 40),
            _clean(row.get("period"), 40),
            _clean(row.get("basis"), 40),
            _clean(row.get("source_locator"), 120),
        ])
    if not ledger_rows and metrics:
        for row in metrics[:15]:
            if not isinstance(row, dict):
                continue
            ledger_rows.append([
                _clean(row.get("metric"), 80),
                _clean(row.get("value"), 60),
                "—",
                "—",
                "—",
                _clean(row.get("source"), 120),
            ])
    parts.append(table(
        ["Fact", "Value", "Unit", "Period", "Basis", "Source Locator"],
        ledger_rows,
    ))
    if spec.get("metrics_read"):
        parts.append(f"**Read:** {_clean(spec.get('metrics_read'), 320)}\n\n")
    parts.append("---\n\n")

    parts.append("## Analytical Synthesis & Hidden Insights\n\n")
    synthesis = str(spec.get("synthesis") or "").strip()
    if synthesis:
        parts.append(synthesis if synthesis.endswith("\n") else synthesis + "\n")
    parts.append("\n")
    parts.append(
        "*This section frames the deal only. It does not recommend invest or pass.*\n\n"
    )

    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can a decision rest on this frame?\n\n"
    )
    if spec.get("quality_reliance_rationale"):
        parts.append(f"**Rationale:** {_clean(spec.get('quality_reliance_rationale'), 420)}\n\n")

    parts.append("## Sources\n\n")
    parts.append(
        "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->\n\n"
    )
    for i, src in enumerate(list(srcs)[:40], start=1):
        parts.append(f"**[{i}]** {src}\n")
    parts.append("\n")
    return "".join(parts)
