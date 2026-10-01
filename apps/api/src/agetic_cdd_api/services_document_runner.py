"""Document Workspace DW-2 — internal capability runner over CDL / VDR."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from agetic_cdd_api.document_capabilities import capability_by_id
from agetic_cdd_api.document_topics import (
    normalize_heading,
    split_document_sections,
    topic_key_for_text,
)
from agetic_cdd_api.models import Deal
from agetic_cdd_api.services_document_synthesis import synthesize_section
from agetic_cdd_api.services_library import (
    ingest_vdr_to_library,
    load_library_document,
    load_library_index,
)
from agetic_cdd_api.services_library_search import (
    citation_meta_for_source,
    format_citation_hint,
    group_chunks_as_sources,
    search_library_chunks,
)
from agetic_cdd_api.services_vdr import list_vdr_docs
from agetic_cdd_api.services_web_research import research_web

_EventCb = Callable[[dict[str, Any]], None] | None

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WHITESPACE = re.compile(r"\s+")
# Protect common corporate / diligence abbreviations before sentence splits.
_ABBREV_DOT = re.compile(
    r"\b(?:"
    r"Inc|Ltd|LLC|Corp|Co|PLC|GmbH|"
    r"Mr|Mrs|Ms|Dr|Prof|vs|etc|"
    r"e\.g|i\.e|Fig|No|Vol|approx|"
    r"FY\d{2,4}|Q[1-4]|U\.S|U\.K|E\.U"
    r")\.",
    re.IGNORECASE,
)
_PREFIX_RE = re.compile(
    r"^\s*(?:research this and add a section to the document:\s*)?",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(
    r"^\s*(?:what is|what's|who are|who is|how is|how are)\s+",
    re.IGNORECASE,
)

# Prefer data-room runnable caps (algo / illustrative). Web caps selected separately.
_INTERNAL_SRCS = frozenset({"algo", "illustrative", "meta", "report"})
_WEB_SRCS = frozenset({"web"})

# Prompt keyword → capability ids (ordered preference).
_PROMPT_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("market share", "share trend", "marimekko", "segment mix"),
        ("mkt_marimekko_segments", "mkt_size_vs_penetration_combo"),
    ),
    (
        ("penetration", "tam", "sam", "som", "addressable market", "market opportunity", "market size"),
        ("mkt_tam_sam_ovals", "mkt_size_vs_penetration_combo", "mkt_marimekko_segments"),
    ),
    (
        ("growth rate", "revenue growth", "cagr", "yoy", "year over year"),
        ("growth_trend", "gx_yoy_scorecard", "gx_cagr_momentum"),
    ),
    (
        ("competitor", "competition", "competitive", "peers", "landscape"),
        ("investment_thesis", "kpi_scorecard"),
    ),
    (
        ("risk", "mitigant", "challenge"),
        ("risk_assessment", "narr_risks_mitigants"),
    ),
    (
        ("margin", "profitability", "ebitda", "gross margin"),
        ("margin_bridge", "gx_yoy_scorecard"),
    ),
    (
        ("valuation", "enterprise value", "multiple"),
        ("implied_valuation", "investment_thesis"),
    ),
    (
        ("thesis", "investment case", "investment highlight"),
        ("investment_thesis", "narr_investment_summary"),
    ),
    (
        ("kpi", "key performance", "metric"),
        ("kpi_scorecard", "gx_x_kpi_grid"),
    ),
    (
        ("geographic", "geography", "region"),
        ("gen_geographic_mix",),
    ),
    (
        ("penetration", "ev penetration", "adopt"),
        ("mkt_tam_sam_ovals", "mkt_size_vs_penetration_combo"),
    ),
    (
        ("sales ratio", "channel mix", "sales mix", "mix ratio"),
        ("mkt_marimekko_segments", "gen_geographic_mix"),
    ),
    (
        ("market overview", "industry overview", "market landscape"),
        ("mkt_tam_sam_ovals", "mkt_marimekko_segments"),
    ),
    (
        ("business model", "how does", "revenue model", "go to market"),
        ("investment_thesis", "kpi_scorecard"),
    ),
    (
        ("growth strategy", "expansion", "scaling"),
        ("growth_trend", "investment_thesis"),
    ),
]

_WEB_RULES: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
    (
        ("competitor", "competition", "competitive", "peers", "landscape", "who are the main"),
        ("gx_x_competitor_table", "gx_x_market_evidence"),
    ),
    (
        ("market share", "tam", "sam", "som", "market size", "penetration", "funnel", "addressable"),
        ("gx_x_market_funnel", "gx_x_market_evidence"),
    ),
    (
        ("web", "external", "industry report"),
        ("gx_x_market_evidence", "gx_x_competitor_table"),
    ),
]

# Which CDL categories to prefer when retrieving for a capability.
_CAP_CATEGORIES: dict[str, tuple[str, ...]] = {
    "mkt_marimekko_segments": ("market_competition", "deal_strategy", "customer"),
    "mkt_size_vs_penetration_combo": ("market_competition", "deal_strategy", "financial"),
    "mkt_tam_sam_ovals": ("market_competition", "deal_strategy"),
    "growth_trend": ("financial", "deal_strategy"),
    "gx_yoy_scorecard": ("financial", "deal_strategy"),
    "gx_cagr_momentum": ("financial", "market_competition"),
    "kpi_scorecard": ("financial", "deal_strategy", "company_management"),
    "gx_x_kpi_grid": ("financial", "deal_strategy"),
    "investment_thesis": ("deal_strategy", "market_competition", "company_management"),
    "narr_investment_summary": ("deal_strategy", "financial"),
    "risk_assessment": ("deal_strategy", "legal_esg", "operations", "market_competition"),
    "narr_risks_mitigants": ("deal_strategy", "legal_esg", "operations"),
    "margin_bridge": ("financial",),
    "implied_valuation": ("financial", "deal_strategy"),
    "cmp_positioning_scatter": ("market_competition", "deal_strategy"),
    "gen_geographic_mix": ("customer", "market_competition", "financial"),
    "section_dashboard": ("deal_strategy", "financial", "market_competition"),
}

_DEFAULT_CAPS = ("kpi_scorecard", "investment_thesis")
_MAX_INTERNAL_CAPS = 2
_MAX_WEB_CAPS = 2
_MAX_SOURCES_PER_TASK = 6
_SNIPPET_LEN = 480
# Skip disk loads for docs with only the "ready" bonus and no token/category signal.
_MIN_DOC_SCORE = 1.0
_PASSAGES_PER_DOC = 5


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9%]{3,}", (text or "").lower()) if t}


_SHARE_PCT = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]{1,24}(?:\s+[A-Z][A-Za-z0-9&.\-]{1,24}){0,3})\b"
    r"[^.\n]{0,60}?(?:share(?:\s+of)?|held|holds?|at|of)?\s*"
    r"(~?\d{1,2}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_GROWTH_PCT = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]{1,24}(?:\s+[A-Z][A-Za-z0-9&.\-]{1,24}){0,3}|YoY|CAGR|revenue)\b"
    r"[^.\n]{0,40}?(?:grew|growth|CAGR|YoY|increased)?\s*"
    r"(~?\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)

# Caps / prompts that always get a DiligenceIQ-style [[CHART]] exhibit.
_CHART_CAP_IDS = frozenset(
    {
        "mkt_marimekko_segments",
        "mkt_size_vs_penetration_combo",
        "mkt_tam_sam_ovals",
        "growth_trend",
        "gx_yoy_scorecard",
        "gx_cagr_momentum",
        "gx_x_market_funnel",
        "gx_x_market_evidence",
    }
)
_CHART_PROMPT_NEEDLES = (
    "market share",
    "share trend",
    "growth rate",
    "revenue growth",
    "cagr",
    "yoy",
    "penetration",
    "marimekko",
    "sales ratio",
    "ev penetration",
)


def _emit(on_event: _EventCb, payload: dict[str, Any]) -> None:
    if on_event:
        on_event(payload)


def _pick_cap_ids(
    prompt: str,
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]],
    *,
    allowed_srcs: frozenset[str],
    limit: int,
) -> list[str]:
    lower = (prompt or "").lower()
    picked: list[str] = []
    for needles, cap_ids in rules:
        if any(n in lower for n in needles):
            for cid in cap_ids:
                if cid in picked:
                    continue
                cap = capability_by_id(cid)
                if cap and cap.get("src") in allowed_srcs:
                    picked.append(cid)
                if len(picked) >= limit:
                    return picked
    return picked


def select_capabilities(prompt: str, *, limit: int = _MAX_INTERNAL_CAPS) -> list[dict[str, Any]]:
    """Keyword map from user prompt → curated internal capabilities."""
    picked = _pick_cap_ids(prompt, _PROMPT_RULES, allowed_srcs=_INTERNAL_SRCS, limit=limit)
    if not picked:
        for cid in _DEFAULT_CAPS:
            if capability_by_id(cid) and cid not in picked:
                picked.append(cid)
            if len(picked) >= limit:
                break
    return [capability_by_id(cid) for cid in picked if capability_by_id(cid)]  # type: ignore[misc]


def select_web_capabilities(prompt: str, *, limit: int = _MAX_WEB_CAPS) -> list[dict[str, Any]]:
    """Keyword map → web capabilities (DW-4)."""
    picked = _pick_cap_ids(prompt, _WEB_RULES, allowed_srcs=_WEB_SRCS, limit=limit)
    return [capability_by_id(cid) for cid in picked if capability_by_id(cid)]  # type: ignore[misc]


def resolve_capabilities(
    prompt: str,
    *,
    capability_ids: list[str] | None = None,
    limit_internal: int = _MAX_INTERNAL_CAPS,
    limit_web: int = _MAX_WEB_CAPS,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve internal + web capabilities from an explicit catalog pick or prompt keywords."""
    if capability_ids:
        internal: list[dict[str, Any]] = []
        web: list[dict[str, Any]] = []
        for cid in capability_ids:
            cap = capability_by_id(cid)
            if not cap:
                continue
            src = str(cap.get("src") or "")
            if src in _WEB_SRCS:
                web.append(cap)
            elif src in _INTERNAL_SRCS:
                internal.append(cap)
        return internal[:limit_internal], web[:limit_web]
    return (
        select_capabilities(prompt, limit=limit_internal),
        select_web_capabilities(prompt, limit=limit_web),
    )


def ensure_library_index(deal: Deal, db: Session | None) -> dict | None:
    index = load_library_index(deal)
    if index is not None:
        return index
    if db is None:
        return None
    if not list_vdr_docs(deal):
        return None
    return ingest_vdr_to_library(db, deal=deal)


def _score_doc(entry: dict, *, query_tokens: set[str], preferred: set[str]) -> float:
    filename = str(entry.get("filename") or "").lower()
    excerpt = str(entry.get("excerpt") or "").lower()
    category = str(entry.get("cdl_category") or "")
    score = 0.0
    if category in preferred:
        score += 4.0
    hay = f"{filename} {excerpt}"
    score += sum(1.0 for t in query_tokens if t in hay)
    if entry.get("status") == "ready":
        score += 0.5
    return score


def _split_sentences(text: str) -> list[str]:
    """Split on sentence boundaries while keeping common abbreviations intact."""
    protected = _ABBREV_DOT.sub(lambda m: m.group(0)[:-1] + "\0", text or "")
    parts = _SENTENCE_SPLIT.split(protected)
    return [p.replace("\0", ".").strip() for p in parts if p.strip()]


def _passage_snippets(text: str, query_tokens: set[str], *, limit: int = 3) -> list[str]:
    cleaned = _WHITESPACE.sub(" ", text or "").strip()
    if not cleaned:
        return []
    sentences = [s for s in _split_sentences(cleaned) if len(s) > 40]
    ranked: list[tuple[float, str]] = []
    for sent in sentences:
        lower = sent.lower()
        hits = sum(1 for t in query_tokens if t in lower)
        if not hits:
            continue
        score = float(hits)
        # Prefer narrative claims over table rows with many % cells.
        pct_count = len(re.findall(r"~?\d+(?:\.\d+)?%", sent))
        if pct_count >= 3:
            score -= 3.0
        if re.search(
            r"\b(?:holds?|held|leading|recorded|represents?|stood|showing)\b",
            lower,
        ):
            score += 2.5
        if 70 <= len(sent) <= 420:
            score += 0.5
        ranked.append((score, sent))
    ranked.sort(key=lambda item: (-item[0], -len(item[1])))
    out: list[str] = []
    for _score, sent in ranked[:limit]:
        out.append(sent[:_SNIPPET_LEN])
    if not out and cleaned:
        out.append(cleaned[:_SNIPPET_LEN])
    return out


def retrieve_passages(
    deal: Deal,
    *,
    prompt: str,
    capability: dict[str, Any],
    index: dict | None,
    limit: int = _MAX_SOURCES_PER_TASK,
) -> list[dict[str, Any]]:
    """Rank CDL documents and return DiligenceIQ-shaped source rows."""
    if not index:
        return []

    preferred = set(_CAP_CATEGORIES.get(str(capability.get("id") or ""), ()))
    cap_title = str(capability.get("title") or "")
    query = f"{prompt} {cap_title}".strip()

    chunk_hits = search_library_chunks(
        deal,
        query=query,
        categories=preferred or None,
        limit=limit * _PASSAGES_PER_DOC * 2,
        index=index,
    )
    if chunk_hits:
        return group_chunks_as_sources(
            chunk_hits,
            limit=limit,
            passages_per_doc=_PASSAGES_PER_DOC,
            snippet_len=_SNIPPET_LEN,
        )

    return _retrieve_passages_legacy(
        deal,
        prompt=prompt,
        capability=capability,
        index=index,
        limit=limit,
    )


def _retrieve_passages_legacy(
    deal: Deal,
    *,
    prompt: str,
    capability: dict[str, Any],
    index: dict | None,
    limit: int,
) -> list[dict[str, Any]]:
    """Keyword fallback when FTS index is empty or returns no hits."""
    if not index:
        return []

    query_tokens = _tokenize(prompt) | _tokenize(str(capability.get("title") or ""))
    preferred = set(_CAP_CATEGORIES.get(str(capability.get("id") or ""), ()))
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]
    scored = [
        (_score_doc(d, query_tokens=query_tokens, preferred=preferred), d) for d in docs
    ]
    scored.sort(key=lambda item: item[0], reverse=True)

    sources: list[dict[str, Any]] = []
    for score, entry in scored:
        if len(sources) >= limit:
            break
        if score < _MIN_DOC_SCORE:
            break
        filename = str(entry.get("filename") or "")
        if not filename:
            continue
        payload = load_library_document(deal, filename) or {}
        text = str(payload.get("text") or entry.get("excerpt") or "")
        if not text.strip():
            continue
        snippets = _passage_snippets(text, query_tokens, limit=_PASSAGES_PER_DOC)
        if not snippets:
            continue
        sources.append(
            {
                "origin": "internal",
                "title": filename,
                "snippet": snippets[0],
                "passages": snippets,
                "cdl_category": entry.get("cdl_category"),
            }
        )
    return sources


def _section_heading(prompt: str, deal: Deal) -> str:
    text = _PREFIX_RE.sub("", (prompt or "").strip())
    text = _QUESTION_RE.sub("", text).strip().rstrip("?.!")
    if not text:
        subject = (deal.company or deal.name or "Company").strip()
        return f"Research notes — {subject}"
    # Title-case lightly without destroying acronyms already uppercase.
    if len(text) > 90:
        text = text[:87].rstrip() + "…"
    if text[0].islower():
        text = text[0].upper() + text[1:]
    return text


def _evidence_blob(sources: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for i, src in enumerate(sources):
        for passage in src.get("passages") or [src.get("snippet") or ""]:
            parts.append(f"{{src:{i}}} {passage}")
    return "\n\n".join(parts)


def _build_task(
    *,
    task_id: str,
    capability: dict[str, Any],
    sources: list[dict[str, Any]],
    ms: int,
    tool: str = "internal",
    queries: list[str] | None = None,
    status: str = "done",
    chart: dict[str, Any] | None = None,
) -> dict[str, Any]:
    n = len(sources)
    is_web = tool == "web"
    if is_web:
        if n:
            summary = (
                f"Reviewed {n} web source{'s' if n != 1 else ''} "
                "filtered to the deal subject."
            )
        else:
            summary = "No on-subject web sources were found for this analysis."
        label = "Web research"
        title = f"Web research: {capability.get('title') or capability.get('id')}"
    else:
        if n:
            summary = (
                f"Read {n} data-room document{'s' if n != 1 else ''} "
                "and selected the passages most relevant to the question."
            )
        else:
            summary = "No matching data-room passages were found for this analysis."
        label = "Data room"
        title = f"Run analysis: {capability.get('title') or capability.get('id')}"

    detail_sources = []
    for s in sources:
        cite_meta = citation_meta_for_source(s)
        row = {
            "origin": s.get("origin") or ("web" if is_web else "internal"),
            "title": s["title"],
            "snippet": s.get("snippet"),
            **cite_meta,
        }
        if s.get("url"):
            row["url"] = s["url"]
        if s.get("domain"):
            row["domain"] = s["domain"]
        detail_sources.append(row)

    detail: dict[str, Any] = {
        "sources": detail_sources,
        "evidence": _evidence_blob(sources),
        "capability_id": capability.get("id"),
    }
    if queries:
        detail["queries"] = queries
    if chart:
        detail["chart"] = chart
    exhibit = capability.get("exhibit")
    if exhibit:
        detail["exhibit"] = exhibit

    return {
        "id": task_id,
        "tool": tool,
        "title": title,
        "label": label,
        "status": status,
        "summary": summary,
        "detail": detail,
        "ms": ms,
    }


def _register_source(
    registry: dict[str, dict[str, Any]],
    src: dict[str, Any],
) -> str:
    """Register a source under a unique citation title (avoids origin/title collisions)."""
    raw = str(src.get("title") or "").strip() or "Untitled source"
    origin = str(src.get("origin") or "internal")
    title = raw
    if title in registry:
        tag = "web" if origin == "web" else "data room"
        alt = f"{raw} ({tag})"
        if alt not in registry:
            title = alt
        else:
            n = 2
            while f"{raw} ({n})" in registry:
                n += 1
            title = f"{raw} ({n})"
    row = dict(src)
    row["title"] = title
    registry[title] = row
    return title


def _source_meta_map(sources: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Citation title → origin/url/domain for Sources footer + flatten."""
    out: dict[str, dict[str, Any]] = {}
    for src in sources:
        title = str(src.get("title") or "")
        if not title:
            continue
        # Titles are disambiguated by _register_source before this runs.
        cite_meta = citation_meta_for_source(src)
        out[title] = {
            "origin": src.get("origin") or "internal",
            "url": src.get("url"),
            "domain": src.get("domain") or (
                urlparse(str(src["url"])).netloc if src.get("url") else None
            ),
            "snippet": src.get("snippet"),
            **cite_meta,
        }
    return out


def _format_source_footer_line(n: int, title: str, meta: dict[str, Any] | None) -> str:
    origin = (meta or {}).get("origin") or "internal"
    if origin == "web":
        domain = (meta or {}).get("domain")
        url = (meta or {}).get("url")
        if url and domain:
            return f"**[{n}]** (web) [{title}]({url}) - {domain}\n"
        if url:
            return f"**[{n}]** (web) [{title}]({url})\n"
        return f"**[{n}]** (web) {title}\n"
    hint = format_citation_hint(meta)
    if hint:
        return f"**[{n}]** (data room) {title} — {hint}\n"
    return f"**[{n}]** (data room) {title}\n"


def _extract_share_chart(
    sources: list[dict[str, Any]],
    *,
    title: str = "Market Share Trend",
) -> dict[str, Any] | None:
    """Build a simple bar chart from name/% patterns in evidence."""
    series: list[dict[str, Any]] = []
    seen: set[str] = set()
    blob = "\n".join(
        str(p)
        for s in sources
        for p in (s.get("passages") or [s.get("snippet") or ""])
    )
    for m in _SHARE_PCT.finditer(blob):
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        try:
            value = float(m.group(2).lstrip("~"))
        except ValueError:
            continue
        if value <= 0 or value > 100:
            continue
        key = label.lower()
        if key in seen or len(label) < 3:
            continue
        # Skip sentence-leading filler words mistaken as labels.
        if key.split()[0] in {"the", "and", "with", "from", "this", "that"}:
            continue
        seen.add(key)
        series.append({"label": label, "value": value})
        if len(series) >= 6:
            break
    if len(series) < 2:
        return None
    return {"type": "bar", "title": title, "series": series, "unit": "%"}


def _extract_growth_chart(
    sources: list[dict[str, Any]],
    *,
    title: str = "Growth Trend",
) -> dict[str, Any] | None:
    """Build a bar chart from growth/CAGR/YoY % patterns."""
    series: list[dict[str, Any]] = []
    seen: set[str] = set()
    blob = "\n".join(
        str(p)
        for s in sources
        for p in (s.get("passages") or [s.get("snippet") or ""])
    )
    for m in _GROWTH_PCT.finditer(blob):
        label = re.sub(r"\s+", " ", m.group(1)).strip()
        try:
            value = float(m.group(2).lstrip("~"))
        except ValueError:
            continue
        if value <= 0 or value > 500:
            continue
        key = label.lower()
        if key in seen or len(label) < 2:
            continue
        seen.add(key)
        series.append({"label": label, "value": value})
        if len(series) >= 6:
            break
    if len(series) < 1:
        return None
    return {"type": "line", "title": title, "series": series, "unit": "%"}


def _chart_kind_for_title(title: str) -> str:
    lower = (title or "").lower()
    if "growth" in lower:
        return "line"
    return "bar"


def _chart_title_for(*, prompt: str, capability: dict[str, Any] | None = None) -> str:
    hay = f"{prompt} {capability.get('id') if capability else ''} {capability.get('title') if capability else ''}".lower()
    if any(k in hay for k in ("growth", "cagr", "yoy", "revenue growth")):
        return "Growth Trend"
    if "penetration" in hay:
        return "Market Penetration"
    if "sales ratio" in hay or "channel mix" in hay:
        return "Sales Mix"
    return "Market Share Trend"


def _wants_chart(*, prompt: str, capability: dict[str, Any] | None = None) -> bool:
    cid = str((capability or {}).get("id") or "")
    if cid in _CHART_CAP_IDS:
        return True
    lower = (prompt or "").lower()
    return any(n in lower for n in _CHART_PROMPT_NEEDLES)


def _build_chart_for_sources(
    sources: list[dict[str, Any]],
    *,
    prompt: str,
    capability: dict[str, Any],
) -> dict[str, Any] | None:
    """Always return a chart for share/growth caps; fill series when evidence allows."""
    if not _wants_chart(prompt=prompt, capability=capability):
        return None
    title = _chart_title_for(prompt=prompt, capability=capability)
    if "Growth" in title:
        chart = _extract_growth_chart(sources, title=title) or _extract_share_chart(
            sources, title=title
        )
    else:
        chart = _extract_share_chart(sources, title=title) or _extract_growth_chart(
            sources, title=title
        )
    if chart:
        return chart
    # DiligenceIQ always emits the marker even when series are empty.
    kind = _chart_kind_for_title(title)
    return {
        "type": kind,
        "title": title,
        "series": [],
        "placeholder": True,
        "unit": "%",
    }


def _primary_capability(caps: list[dict[str, Any]]) -> dict[str, Any] | None:
    return caps[0] if caps else None


def _normalize_chart(chart: dict[str, Any] | None, *, title: str) -> dict[str, Any]:
    """Ensure chart payloads always have a valid DIQ-shaped schema."""
    base = dict(chart or {})
    base["title"] = str(base.get("title") or title)
    base["type"] = _chart_kind_for_title(base["title"])
    base.setdefault("unit", "%")
    series = base.get("series")
    base["series"] = series if isinstance(series, list) else []
    if not base["series"]:
        base["placeholder"] = True
    return base


def _finalize_charts(
    charts: list[dict[str, Any]],
    *,
    prompt: str,
    caps: list[dict[str, Any]],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collapse to one primary exhibit; always emit for share/growth prompts."""
    primary = _primary_capability(caps)
    wants = _wants_chart(prompt=prompt, capability=primary) or any(
        _wants_chart(prompt=prompt, capability=c) for c in caps
    )
    if not wants:
        return []
    title = _chart_title_for(prompt=prompt, capability=primary)
    with_series = [c for c in charts if c.get("series")]
    if with_series:
        best = max(with_series, key=lambda c: len(c.get("series") or []))
        normalized = _normalize_chart(dict(best), title=title)
        normalized["title"] = title
        return [normalized]
    if charts:
        return [_normalize_chart(dict(charts[0]), title=title)]
    filled = _extract_share_chart(sources, title=title) or _extract_growth_chart(
        sources, title=title
    )
    if filled and filled.get("series"):
        return [_normalize_chart(filled, title=title)]
    return [_normalize_chart(None, title=title)]


def _append_chart_markers(body: str, charts: list[dict[str, Any]]) -> str:
    if not charts:
        return body
    parts = [body.rstrip()]
    for chart in charts:
        label = str(chart.get("title") or "Exhibit")
        payload = json.dumps(chart, ensure_ascii=False)
        parts.append(f"\n\n[[CHART: {label}]]\n<!-- cdd:chart {payload} -->")
    return "\n".join(parts).strip() + "\n"


def _parse_existing_source_titles(markdown: str) -> list[str]:
    titles: list[str] = []
    for line in markdown.splitlines():
        m = re.match(r"\*\*\[(\d+)\]\*\*\s*(?:\([^)]*\)\s*)?(.+)$", line.strip())
        if not m:
            m = re.match(r"\[(\d+)\]\s+(.+)$", line.strip())
        if not m:
            continue
        title = m.group(2).strip()
        # Strip trailing " - domain" for web lines if present.
        title = re.sub(r"\s+-\s+\S+$", "", title)
        title = re.sub(r"^\[([^\]]+)\]\([^)]+\)\s*", r"\1", title)
        if title:
            titles.append(title)
    return titles


def _parse_existing_source_meta(markdown: str) -> dict[str, dict[str, Any]]:
    """Recover origin/url/domain from an existing Sources footer."""
    out: dict[str, dict[str, Any]] = {}
    for line in markdown.splitlines():
        raw = line.strip()
        m = re.match(r"\*\*\[(\d+)\]\*\*\s*(?:\(([^)]*)\)\s*)?(.+)$", raw)
        if not m:
            continue
        kind = (m.group(2) or "data room").strip().lower()
        rest = m.group(3).strip()
        domain = None
        url = None
        title = rest
        link = re.match(r"^\[([^\]]+)\]\(([^)]+)\)(?:\s+-\s+(\S+))?$", rest)
        if link:
            title = link.group(1).strip()
            url = link.group(2).strip()
            domain = link.group(3)
        else:
            title = re.sub(r"\s+-\s+\S+$", "", title).strip()
        if not title:
            continue
        out[title] = {
            "origin": "web" if kind == "web" else "internal",
            "url": url,
            "domain": domain,
            "snippet": None,
        }
    return out


def build_cite_map(document_markdown: str, source_titles: list[str]) -> dict[str, int]:
    """Stable citation ids: existing Sources first, then newly referenced titles."""
    existing = _parse_existing_source_titles(document_markdown)
    cite_map: dict[str, int] = {t: i + 1 for i, t in enumerate(existing)}
    for title in source_titles:
        if title not in cite_map:
            cite_map[title] = len(cite_map) + 1
    return cite_map


def merge_document_section(
    markdown: str,
    *,
    heading: str,
    body: str,
    source_titles: list[str],
    source_meta: dict[str, dict[str, Any]] | None = None,
) -> tuple[str, dict[str, int]]:
    """Insert a ## section before Sources and extend the numbered Sources list."""
    meta = dict(_parse_existing_source_meta(markdown))
    meta.update(source_meta or {})
    cite_map = build_cite_map(markdown, source_titles)
    # Ordered title list for the footer (existing order, then new titles).
    existing = _parse_existing_source_titles(markdown)
    ordered = list(existing)
    for title in source_titles:
        if title not in ordered:
            ordered.append(title)

    sources_header = "## Sources"
    marker = "<!-- cdd:sources"
    if sources_header in markdown:
        _head, _sep, _tail = markdown.partition(sources_header)
    elif marker in markdown:
        _head, _sep, _tail = markdown.partition(marker)
    else:
        _head = markdown

    preamble, sections = split_document_sections(_head)
    norm_new = normalize_heading(heading)
    new_topic = topic_key_for_text(heading)
    kept: list[tuple[str, str]] = []
    for existing_heading, existing_body in sections:
        if normalize_heading(existing_heading) == norm_new:
            continue
        if new_topic and topic_key_for_text(existing_heading) == new_topic:
            continue
        kept.append((existing_heading, existing_body))
    kept.append((heading, body.rstrip()))

    body_parts: list[str] = []
    if preamble.strip():
        body_parts.append(preamble.rstrip())
    for sec_heading, sec_body in kept:
        block = f"## {sec_heading}\n"
        if sec_body.strip():
            block += sec_body.rstrip() + "\n"
        body_parts.append(block.rstrip())
    head = "\n\n".join(body_parts).rstrip() + "\n\n"

    sources_block = (
        f"{sources_header}\n\n"
        f"<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->\n\n"
    )
    for title in ordered:
        n = cite_map[title]
        sources_block += _format_source_footer_line(n, title, meta.get(title))

    return head + sources_block, cite_map


def flatten_message_sources(
    sources: list[dict[str, Any]],
    *,
    cite_map: dict[str, int],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for src in sources:
        title = str(src["title"])
        if title in seen:
            continue
        cite_id = cite_map.get(title)
        if cite_id is None:
            # Never invent colliding ids — body and footer must stay aligned.
            continue
        seen.add(title)
        origin = src.get("origin") or "internal"
        cite_meta = citation_meta_for_source(src)
        out.append(
            {
                "id": cite_id,
                "type": "web" if origin == "web" else "vdr",
                "title": title,
                "url": src.get("url"),
                "domain": src.get("domain"),
                "snippet": src.get("snippet"),
                "date": None,
                "used": True,
                **cite_meta,
            }
        )
    out.sort(key=lambda row: int(row["id"]))
    return out


def iter_document_research(
    deal: Deal,
    *,
    prompt: str,
    document_markdown: str,
    db: Session | None = None,
    capability_ids: list[str] | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Yield progress events (`type=task`) then a final `type=result` payload.
    """
    subject = (deal.company or deal.name or "the company").strip() or "the company"
    internal_caps, web_caps = resolve_capabilities(prompt, capability_ids=capability_ids)
    # Prefer web for competitor prompts: still keep one internal when available.
    if web_caps and "competitor" in (prompt or "").lower():
        internal_caps = internal_caps[:1]

    index = ensure_library_index(deal, db)
    tasks: list[dict[str, Any]] = []
    by_title: dict[str, dict[str, Any]] = {}
    charts: list[dict[str, Any]] = []
    task_n = 0

    for cap in internal_caps:
        task_n += 1
        task_id = f"t{task_n}"
        yield {
            "type": "task",
            "task": {
                "id": task_id,
                "tool": "internal",
                "title": f"Run analysis: {cap.get('title') or cap.get('id')}",
                "label": "Data room",
                "status": "running",
                "summary": "Searching the data room…",
            },
        }
        started = time.perf_counter()
        found = retrieve_passages(deal, prompt=prompt, capability=cap, index=index)
        ms = int((time.perf_counter() - started) * 1000)
        chart = _build_chart_for_sources(found, prompt=prompt, capability=cap)
        if chart:
            charts.append(chart)
        task = _build_task(
            task_id=task_id,
            capability=cap,
            sources=found,
            ms=ms,
            tool="internal",
            chart=chart,
        )
        tasks.append(task)
        yield {"type": "task", "task": task}
        for src in found:
            _register_source(by_title, src)

    for cap in web_caps:
        task_n += 1
        task_id = f"t{task_n}"
        yield {
            "type": "task",
            "task": {
                "id": task_id,
                "tool": "web",
                "title": f"Web research: {cap.get('title') or cap.get('id')}",
                "label": "Web research",
                "status": "running",
                "summary": "Searching the open web…",
            },
        }
        started = time.perf_counter()
        found, queries = research_web(prompt=prompt, subject=subject, capability=cap)
        ms = int((time.perf_counter() - started) * 1000)
        chart = _build_chart_for_sources(found, prompt=prompt, capability=cap)
        if chart:
            charts.append(chart)
        task = _build_task(
            task_id=task_id,
            capability=cap,
            sources=found,
            ms=ms,
            tool="web",
            queries=queries,
            chart=chart,
        )
        tasks.append(task)
        yield {"type": "task", "task": task}
        for src in found:
            _register_source(by_title, src)

    deduped = list(by_title.values())
    heading = _section_heading(prompt, deal)
    source_titles = list(by_title.keys())
    source_meta = _source_meta_map(deduped)
    all_caps = internal_caps + web_caps
    charts = _finalize_charts(
        charts, prompt=prompt, caps=all_caps, sources=deduped
    )

    cite_map = build_cite_map(document_markdown, source_titles)
    synthesized = synthesize_section(
        prompt=prompt,
        heading=heading,
        sources=deduped,
        cite_map=cite_map,
        deal=deal,
        tasks=tasks,
    )
    body = _append_chart_markers(synthesized["body"], charts)
    markdown, cite_map = merge_document_section(
        document_markdown,
        heading=heading,
        body=body,
        source_titles=source_titles,
        source_meta=source_meta,
    )

    flat_sources = flatten_message_sources(deduped, cite_map=cite_map)
    yield {
        "type": "result",
        "result": {
            "content": synthesized["assistant"],
            "tasks": tasks,
            "sources": flat_sources,
            "document": markdown,
            "heading": heading,
            "section_body": body,
            "source_titles": source_titles,
            "source_meta": source_meta,
            "evidence_sources": deduped,
            "cite_map": cite_map,
            "baseline_document": document_markdown,
            "capabilities": [c.get("id") for c in (internal_caps + web_caps)],
            "charts": charts,
        },
    }


def remap_citation_ids(
    text: str,
    *,
    old_map: dict[str, int],
    new_map: dict[str, int],
) -> str:
    """Rewrite [n] markers when citation numbers shift after a remount."""
    if not text or old_map == new_map:
        return text
    id_remap: dict[int, int] = {}
    for title, old_id in old_map.items():
        new_id = new_map.get(title)
        if new_id is not None and new_id != old_id:
            id_remap[int(old_id)] = int(new_id)
    if not id_remap:
        return text

    def _repl(match: re.Match[str]) -> str:
        old = int(match.group(1))
        return f"[{id_remap.get(old, old)}]"

    return re.sub(r"\[(\d+)\]", _repl, text)


def remount_research_onto_document(
    latest_markdown: str,
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Re-apply a research section onto the latest document.md.

    Used when another writer changed the document while research ran outside
    the persistence lock. Recomputes cite ids and remaps [n] in body + chat.
    """
    baseline = str(result.get("baseline_document") or "")
    if latest_markdown == baseline and result.get("document"):
        return result

    heading = str(result.get("heading") or "Research notes")
    body = str(result.get("section_body") or "")
    source_titles = list(result.get("source_titles") or [])
    source_meta = dict(result.get("source_meta") or {})
    old_map = {str(k): int(v) for k, v in (result.get("cite_map") or {}).items()}
    evidence = list(result.get("evidence_sources") or [])

    new_map = build_cite_map(latest_markdown, source_titles)
    remapped_body = remap_citation_ids(body, old_map=old_map, new_map=new_map)
    markdown, final_map = merge_document_section(
        latest_markdown,
        heading=heading,
        body=remapped_body,
        source_titles=source_titles,
        source_meta=source_meta,
    )
    flat_sources = flatten_message_sources(evidence, cite_map=final_map)
    remapped_content = remap_citation_ids(
        str(result.get("content") or ""),
        old_map=old_map,
        new_map=final_map,
    )
    updated = dict(result)
    updated.update(
        {
            "document": markdown,
            "sources": flat_sources,
            "section_body": remapped_body,
            "cite_map": final_map,
            "content": remapped_content,
            "baseline_document": latest_markdown,
        }
    )
    return updated


def run_document_research(
    deal: Deal,
    *,
    prompt: str,
    document_markdown: str,
    db: Session | None = None,
    on_event: _EventCb = None,
) -> dict[str, Any]:
    """Sync wrapper around iter_document_research."""
    result: dict[str, Any] | None = None
    for event in iter_document_research(
        deal, prompt=prompt, document_markdown=document_markdown, db=db
    ):
        if event.get("type") == "result":
            result = event["result"]
        else:
            _emit(on_event, event)
    if result is None:
        raise RuntimeError("document research produced no result")
    return result
