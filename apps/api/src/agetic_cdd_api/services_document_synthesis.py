"""Deterministic + optional Gemini Document Workspace synthesis.

Turns ranked VDR passages into DiligenceIQ-style section body + fact-bearing
assistant chat. Gemini is preferred when AGETIC_CDD_GEMINI_API_KEY is set;
otherwise (or on failure) heuristics run.
"""

from __future__ import annotations

import re
from typing import Any

_WHITESPACE = re.compile(r"\s+")
_JUNK_GLYPH = re.compile(r"[■▪●◆□◦]+")
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
_METRIC = re.compile(
    r"(?:"
    r"~?\d+(?:\.\d+)?\s*%|"
    r"\d+(?:\.\d+)?\s*percent|"
    r"FY\d{2,4}E?|"
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|"
    r"\bCAGR\b|"
    r"\b\d+\s*x\b"
    r")",
    re.IGNORECASE,
)
_PROSE_HINT = re.compile(
    r"\b(?:"
    r"holds?|held|is|are|was|were|has|have|had|"
    r"recorded|represents?|showing|stood|reached|"
    r"grew|growth|increased|declined|leading|competes?|"
    r"market share|penetration|revenue|units sold"
    r")\b",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(
    r"^\s*(?:research this and add a section to the document:\s*)?",
    re.IGNORECASE,
)


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9%]{3,}", (text or "").lower()) if t}


def _split_sentences(text: str) -> list[str]:
    protected = _ABBREV_DOT.sub(lambda m: m.group(0)[:-1] + "\0", text or "")
    parts = _SENTENCE_SPLIT.split(protected)
    return [p.replace("\0", ".").strip() for p in parts if p.strip()]


def _clean(text: str) -> str:
    text = _JUNK_GLYPH.sub(" ", text or "")
    return _WHITESPACE.sub(" ", text).strip()


def _company_tokens(deal: Any) -> set[str]:
    bits = []
    for attr in ("company", "name"):
        val = getattr(deal, attr, None)
        if val:
            bits.append(str(val))
    return _tokenize(" ".join(bits))


def _score_sentence(
    sent: str,
    *,
    prompt_tokens: set[str],
    company_tokens: set[str],
) -> float:
    lower = sent.lower()
    tokens = _tokenize(sent)
    if len(sent) < 48:
        return -1.0

    score = 0.0
    score += 2.0 * len(prompt_tokens & tokens)
    score += 1.5 * len(company_tokens & tokens)
    if _METRIC.search(sent):
        score += 3.0
    if _PROSE_HINT.search(sent):
        score += 2.5
    # Penalize table-like scrapes (many short numeric cells, few letters).
    letter_ratio = sum(1 for c in sent if c.isalpha()) / max(len(sent), 1)
    if letter_ratio < 0.45:
        score -= 4.0
    pct_count = len(re.findall(r"~?\d+(?:\.\d+)?%", sent))
    if pct_count >= 3:
        score -= 5.0
    if re.search(r"(?:Market Share\s*\([^)]*\)|Dimension\s+Ola|Units Sold\s*\()", sent, re.I):
        score -= 3.0
    if re.search(
        r"(?:Date Target Name Acquirer|Transaction Value \(USD\)|Implied Multiple)",
        sent,
        re.I,
    ):
        score -= 6.0
    if re.match(r"^\d+\s+\d+\s+[A-Z]", sent) or re.search(
        r"This document consolidates|absent from the primary due diligence",
        sent,
        re.I,
    ):
        score -= 5.0
    # Prefer answer-length sentences.
    if 80 <= len(sent) <= 420:
        score += 1.0
    elif len(sent) > 520:
        score -= 1.5
    # Mild boost when the sentence mentions the question topic explicitly.
    if "share" in prompt_tokens and "share" in lower:
        score += 1.5
    if "share" in prompt_tokens and re.search(
        r"\b(?:holds?|leading|market share of|share position)\b", lower
    ):
        score += 3.0
    if "growth" in prompt_tokens and ("growth" in lower or "cagr" in lower):
        score += 1.5
    if "competitor" in prompt_tokens or "competitors" in prompt_tokens:
        if any(w in lower for w in ("competitor", "competitive", "rival", "peer")):
            score += 1.5
    return score


_SHARE_TREND_ROW = re.compile(
    r"(Ola Electric|Ather Energy|TVS\s*iQube|Bajaj Chetak|Hero Vida|Ampere(?:\s*\([^)]*\))?)"
    r"\s+(~?\d+%)\s+(~?\d+%)\s+(~?\d+%)"
    r"(?:\s+(Strong Gain|Steady Growth|Losing Share|Declining|Gaining))?",
    re.IGNORECASE,
)
_MARKET_SIZE_CLAIM = re.compile(
    r"(?:electric two-wheeler|E2W)\s+market[^.]*?(?:~?\d[\d,]*)\s*units[^.]*?(?:~?\d+%)\s*EV penetration[^.]*\.",
    re.IGNORECASE,
)


def _structured_claims(text: str) -> list[str]:
    """Lift facts out of table-ish PDF scrapes into short prose claims."""
    claims: list[str] = []
    for m in _SHARE_TREND_ROW.finditer(text or ""):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        y3 = m.group(4)
        trend = (m.group(5) or "").strip()
        claim = (
            f"{name} holds a market share of {y3} as of FY2024E"
            + (f", showing a {trend.lower()} trend" if trend else "")
            + "."
        )
        claims.append(claim)
    for m in _MARKET_SIZE_CLAIM.finditer(text or ""):
        claims.append(_clean(m.group(0)))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for c in claims:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _structured_claim_bonus(sent: str, *, prompt_tokens: set[str], company_tokens: set[str]) -> float:
    """Prefer the diligence subject (highest share / strong gain / name match)."""
    lower = sent.lower()
    bonus = 0.0
    m = re.search(r"market share of\s*~?(\d+(?:\.\d+)?)\s*%", lower)
    if m:
        # 32% → +6.4; 6% → +1.2 — surfaces the leader first.
        bonus += float(m.group(1)) / 5.0
    if "strong gain" in lower or "leading" in lower:
        bonus += 5.0
    name_tokens = _tokenize(sent) - {
        "holds", "market", "share", "as", "of", "fy2024e", "showing", "a", "trend",
        "losing", "steady", "growth", "declining", "gaining",
    }
    if name_tokens & (prompt_tokens | company_tokens):
        bonus += 8.0
    return bonus


def _collect_candidates(
    sources: list[dict[str, Any]],
    *,
    cite_map: dict[str, int],
    prompt_tokens: set[str],
    company_tokens: set[str],
) -> list[tuple[float, int, str]]:
    """Return (score, cite_id, sentence) ranked descending."""
    rows: list[tuple[float, int, str]] = []
    seen: set[str] = set()
    for src in sources:
        title = str(src.get("title") or "")
        cite = cite_map.get(title)
        if cite is None:
            continue
        chunks = list(src.get("passages") or [])
        if src.get("snippet"):
            chunks.append(str(src["snippet"]))
        # Also mine structured claims from the joined evidence blob.
        joined = "\n".join(str(c) for c in chunks)
        structured = _structured_claims(joined)
        chunks.extend(structured)
        structured_set = set(structured)
        for chunk in chunks:
            cleaned = _clean(str(chunk))
            if not cleaned:
                continue
            sentences = _split_sentences(cleaned)
            if len(sentences) == 1 and len(cleaned) > 40:
                # Table dumps often lack periods — treat whole chunk as one unit.
                sentences = [cleaned]
            for sent in sentences:
                sent = _clean(sent)
                key = sent.lower()[:160]
                if key in seen:
                    continue
                score = _score_sentence(
                    sent, prompt_tokens=prompt_tokens, company_tokens=company_tokens
                )
                if sent in structured_set:
                    score += 4.0 + _structured_claim_bonus(
                        sent, prompt_tokens=prompt_tokens, company_tokens=company_tokens
                    )
                if score < 1.5:
                    continue
                seen.add(key)
                # Trim long sentences for readability.
                if len(sent) > 380:
                    sent = sent[:377].rstrip() + "…"
                rows.append((score, cite, sent))
    rows.sort(key=lambda r: (-r[0], r[1], -len(r[2])))
    return rows


def _attach_cite(sentence: str, cite: int) -> str:
    s = sentence.rstrip()
    if re.search(rf"\[{cite}\]\s*$", s):
        return s
    # Avoid double punctuation before cite.
    if s.endswith((".", "!", "?")):
        return f"{s} [{cite}]"
    return f"{s}. [{cite}]"


def _compose_paragraphs(picked: list[tuple[int, str]]) -> str:
    """Build 1–2 prose paragraphs from (cite, sentence) pairs."""
    if not picked:
        return ""
    lead = _attach_cite(picked[0][1], picked[0][0])
    if len(picked) == 1:
        return lead + "\n"

    rest = [_attach_cite(sent, cite) for cite, sent in picked[1:]]
    # First paragraph: lead + up to one supporting sentence.
    para1 = lead
    if rest:
        para1 = f"{lead} {rest[0]}"
        rest = rest[1:]
    if not rest:
        return para1 + "\n"
    para2 = " ".join(rest[:2])
    return f"{para1}\n\n{para2}\n"


def _topic_phrase(prompt: str) -> str:
    text = _PREFIX_RE.sub("", (prompt or "").strip())
    text = re.sub(
        r"^\s*(?:what is|what's|who are|who is|how is|how are)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    ).strip().rstrip("?.!")
    return text or "the topic"


def _lead_fact_line(
    picked: list[tuple[int, str]],
    *,
    prompt_tokens: set[str],
    company_tokens: set[str],
) -> str:
    if not picked:
        return ""
    # Prefer the sentence that best answers the prompt (not merely first paragraph order).
    cite, sent = max(
        picked,
        key=lambda item: _score_sentence(
            item[1], prompt_tokens=prompt_tokens, company_tokens=company_tokens
        )
        + _structured_claim_bonus(
            item[1], prompt_tokens=prompt_tokens, company_tokens=company_tokens
        ),
    )
    # Prefer a compact clause that still carries a metric when present.
    metric = _METRIC.search(sent)
    if metric and len(sent) > 160:
        # Keep surrounding context around the first metric.
        start = max(0, metric.start() - 60)
        end = min(len(sent), metric.end() + 80)
        snippet = sent[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(sent):
            snippet = snippet + "…"
        return _attach_cite(snippet, cite)
    return _attach_cite(sent, cite)


_CITE_RE = re.compile(r"\[(\d+)\]")

_LLM_SYSTEM = """You are a commercial due diligence (CDD) analyst writing for an IC memo.
Use ONLY the numbered evidence passages provided. Do not invent figures, dates, or competitors.
Every factual claim must include an inline citation like [n] using only evidence ids listed.
Ignore off-topic or table-header noise. Prefer clear prose over copying raw PDF scrapes.
Return a single JSON object with keys:
- "body": 1-3 short markdown paragraphs answering the question (no heading, no bullet list unless essential).
- "assistant": 1-2 sentences for chat: confirm the section was added, state the key finding with citations.
Do not include a Sources footer."""


def _evidence_pack(
    sources: list[dict[str, Any]],
    *,
    cite_map: dict[str, int],
    limit_passages: int = 10,
) -> tuple[str, set[int]]:
    """Build a prompt evidence block and the set of allowed citation ids."""
    allowed: set[int] = set()
    blocks: list[str] = []
    count = 0
    for src in sources:
        title = str(src.get("title") or "")
        cite = cite_map.get(title)
        if cite is None:
            continue
        allowed.add(cite)
        passages = list(src.get("passages") or [])
        if src.get("snippet"):
            passages = [str(src["snippet"])] + passages
        # Prefer structured claims mined from table scrapes.
        structured = _structured_claims("\n".join(str(p) for p in passages))
        ordered = structured + passages
        seen_local: set[str] = set()
        for p in ordered:
            cleaned = _clean(str(p))
            if not cleaned or len(cleaned) < 40:
                continue
            key = cleaned.lower()[:120]
            if key in seen_local:
                continue
            seen_local.add(key)
            if len(cleaned) > 500:
                cleaned = cleaned[:497].rstrip() + "…"
            blocks.append(f"[{cite}] ({title})\n{cleaned}")
            count += 1
            if count >= limit_passages:
                break
        if count >= limit_passages:
            break
    return "\n\n".join(blocks), allowed


def _sanitize_cites(text: str, allowed: set[int]) -> str:
    """Drop citation markers that are not in the allowed set."""

    def repl(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return m.group(0) if n in allowed else ""

    cleaned = _CITE_RE.sub(repl, text or "")
    return _WHITESPACE.sub(" ", cleaned).strip()


def _llm_synthesize(
    *,
    prompt: str,
    heading: str,
    sources: list[dict[str, Any]],
    cite_map: dict[str, int],
    deal: Any,
    tasks: list[dict[str, Any]],
) -> dict[str, str] | None:
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured():
        return None

    evidence, allowed = _evidence_pack(sources, cite_map=cite_map)
    if not evidence or not allowed:
        return None

    company = (getattr(deal, "company", None) or getattr(deal, "name", None) or "the company")
    task_names = ", ".join(
        (t.get("title") or "").replace("Run analysis: ", "") for t in tasks[:3]
    )
    user = (
        f"Deal company / name: {company}\n"
        f"Section heading: {heading}\n"
        f"User question: {prompt}\n"
        f"Analyses run: {task_names or 'data-room retrieval'}\n\n"
        f"Evidence passages (cite only these ids: {sorted(allowed)}):\n\n"
        f"{evidence}\n"
    )
    parsed = generate_json(system=_LLM_SYSTEM, user=user)
    if not parsed:
        return None

    body = _sanitize_cites(str(parsed.get("body") or ""), allowed)
    assistant = _sanitize_cites(str(parsed.get("assistant") or ""), allowed)
    if not body or not assistant:
        return None
    # Require at least one valid citation in the body when evidence exists.
    if not _CITE_RE.search(body):
        return None
    if not body.endswith("\n"):
        body += "\n"
    return {"body": body, "assistant": assistant}


def _heuristic_synthesize(
    *,
    prompt: str,
    heading: str,
    sources: list[dict[str, Any]],
    cite_map: dict[str, int],
    deal: Any,
    tasks: list[dict[str, Any]],
) -> dict[str, str]:
    prompt_tokens = _tokenize(prompt)
    company_tokens = _company_tokens(deal)
    candidates = _collect_candidates(
        sources,
        cite_map=cite_map,
        prompt_tokens=prompt_tokens,
        company_tokens=company_tokens,
    )

    # Cap diversity: at most two sentences per citation id.
    picked: list[tuple[int, str]] = []
    per_cite: dict[int, int] = {}
    share_claim_used = False
    for _score, cite, sent in candidates:
        if per_cite.get(cite, 0) >= 2:
            continue
        # One share-trend claim is enough; prefer the highest-scored (already sorted).
        if re.search(r"holds a market share of\s*~?\d+", sent, re.I):
            if share_claim_used:
                continue
            share_claim_used = True
        # Skip near-duplicates of already picked text.
        overlap_too_high = False
        for _, prev in picked:
            shared = _tokenize(sent) & _tokenize(prev)
            if len(shared) >= 8:
                overlap_too_high = True
                break
        if overlap_too_high:
            continue
        picked.append((cite, sent))
        per_cite[cite] = per_cite.get(cite, 0) + 1
        if len(picked) >= 3:
            break

    if not picked:
        # Last resort: top snippets as short prose (still not raw bullets).
        for src in sources[:3]:
            title = str(src.get("title") or "")
            cite = cite_map.get(title)
            if cite is None:
                continue
            snippet = _clean(str(src.get("snippet") or ""))
            if not snippet:
                continue
            if len(snippet) > 280:
                snippet = snippet[:277].rstrip() + "…"
            picked.append((cite, snippet))
            if len(picked) >= 3:
                break

    body = _compose_paragraphs(picked)
    cites_used = sorted({c for c, _ in picked})
    cite_txt = ", ".join(f"[{n}]" for n in cites_used[:6])
    task_names = ", ".join(
        (t.get("title") or "").replace("Run analysis: ", "") for t in tasks[:3]
    )
    topic = _topic_phrase(prompt)
    lead = _lead_fact_line(
        picked, prompt_tokens=prompt_tokens, company_tokens=company_tokens
    )

    assistant = (
        f"I added a new section to the document titled “{heading}” with information "
        f"on {topic}, citing sources {cite_txt}."
    )
    if lead:
        assistant += f" {lead}"
    if task_names:
        assistant += f" Analyses run: {task_names}."

    return {"body": body, "assistant": assistant}


def synthesize_section(
    *,
    prompt: str,
    heading: str,
    sources: list[dict[str, Any]],
    cite_map: dict[str, int],
    deal: Any,
    tasks: list[dict[str, Any]],
) -> dict[str, str]:
    """
    Return ``body`` (markdown section body) and ``assistant`` (chat content).

    Prefers Gemini when configured; falls back to deterministic heuristics.
    """
    if not sources:
        body = (
            "No supporting passages were found in the data room for this question. "
            "Upload VDR documents and run Analyze / library ingest, then try again.\n"
        )
        assistant = (
            f"I looked through the data room for “{heading}” but found no supporting passages. "
            "Upload VDR files and ingest the library, then ask again."
        )
        return {"body": body, "assistant": assistant}

    llm = _llm_synthesize(
        prompt=prompt,
        heading=heading,
        sources=sources,
        cite_map=cite_map,
        deal=deal,
        tasks=tasks,
    )
    if llm:
        return llm

    return _heuristic_synthesize(
        prompt=prompt,
        heading=heading,
        sources=sources,
        cite_map=cite_map,
        deal=deal,
        tasks=tasks,
    )
