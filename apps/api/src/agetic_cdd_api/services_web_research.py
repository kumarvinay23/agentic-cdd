"""DW-4 web research — Gemini Google Search grounding + subject filter.

Falls back to DuckDuckGo Instant Answer when Gemini grounding is unavailable.
Off-topic results (wrong industry/geography) are dropped before they become
document citations.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any
from urllib.parse import urlparse

from agetic_cdd_api.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT_S = 35
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "what",
        "who",
        "are",
        "main",
        "research",
        "section",
        "document",
        "add",
        "market",
        "share",
        "analysis",
    }
)


def _tokenize(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9%]{3,}", (text or "").lower())
        if t not in _STOP
    }


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host or None
    except Exception:
        return None


def _subject_tokens(subject: str, prompt: str) -> set[str]:
    return _tokenize(subject) | _tokenize(prompt)


def filter_by_subject(
    results: list[dict[str, Any]],
    *,
    subject: str,
    prompt: str,
) -> list[dict[str, Any]]:
    """Keep pages that share subject/prompt tokens; drop clear off-topic noise."""
    needed = _subject_tokens(subject, prompt)
    if not needed:
        return results[:8]

    scored: list[tuple[int, dict[str, Any]]] = []
    for row in results:
        hay = f"{row.get('title') or ''} {row.get('snippet') or ''} {row.get('url') or ''}".lower()
        hits = sum(1 for t in needed if t in hay)
        scored.append((hits, row))

    kept = [row for hits, row in scored if hits >= 1]
    if kept:
        return kept[:8]
    # No subject hits — keep a tiny slice rather than inventing empty research.
    return [row for _hits, row in scored[:2]]


def _gemini_google_search(query: str, *, subject: str) -> list[dict[str, Any]]:
    api_key = settings.gemini_api_key.strip()
    if not api_key or not settings.document_synthesis_llm:
        return []

    model = (settings.gemini_model or "gemini-3.6-flash").strip()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Research the following for commercial due diligence on {subject}. "
                            f"Focus ONLY on this subject and its industry/geography. "
                            f"Query: {query}\n"
                            "Summarize key findings in 3 short bullets and cite sources."
                        )
                    }
                ],
            }
        ],
        "tools": [{"google_search": {}}],
        "generationConfig": {"temperature": 0.2},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as resp:
            envelope = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini google_search failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        cand = (envelope.get("candidates") or [{}])[0]
        meta = cand.get("groundingMetadata") or {}
        chunks = meta.get("groundingChunks") or []
        supports = meta.get("groundingSupports") or []
        # Map chunk index → short support text when available.
        support_txt: dict[int, str] = {}
        for support in supports:
            segs = support.get("groundingChunkIndices") or []
            text = (support.get("segment") or {}).get("text") or ""
            for idx in segs:
                if isinstance(idx, int) and text:
                    support_txt[idx] = text[:320]
        for i, chunk in enumerate(chunks):
            web = chunk.get("web") or {}
            href = web.get("uri") or web.get("url")
            title = web.get("title") or href or f"Web source {i + 1}"
            if not href or href in seen:
                continue
            seen.add(href)
            out.append(
                {
                    "origin": "web",
                    "title": title,
                    "url": href,
                    "domain": _domain(href),
                    "snippet": support_txt.get(i) or title,
                }
            )
        # Also fold model answer text as evidence context on first source.
        parts = ((cand.get("content") or {}).get("parts") or [])
        answer = " ".join(str(p.get("text") or "") for p in parts).strip()
        if answer and out:
            out[0]["snippet"] = (answer[:400] + ("…" if len(answer) > 400 else ""))
            out[0]["passages"] = [answer[:1200]]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gemini grounding parse failed: %s", exc)
        return []
    return out


def _duckduckgo_search(query: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    )
    url = f"https://api.duckduckgo.com/?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "AgenticCDD/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(title: str, href: str | None, snippet: str) -> None:
        if not href or href in seen:
            return
        seen.add(href)
        out.append(
            {
                "origin": "web",
                "title": title or href,
                "url": href,
                "domain": _domain(href),
                "snippet": (snippet or title or "")[:320],
                "passages": [(snippet or title or "")[:800]],
            }
        )

    abs_text = data.get("AbstractText") or ""
    abs_url = data.get("AbstractURL") or data.get("AbstractSource")
    if abs_text and abs_url:
        add(data.get("Heading") or "Abstract", str(abs_url), abs_text)

    for topic in data.get("RelatedTopics") or []:
        if not isinstance(topic, dict):
            continue
        if "Topics" in topic:
            for sub in topic.get("Topics") or []:
                if isinstance(sub, dict) and sub.get("FirstURL"):
                    add(
                        (sub.get("Text") or "")[:80],
                        sub.get("FirstURL"),
                        sub.get("Text") or "",
                    )
        elif topic.get("FirstURL"):
            add((topic.get("Text") or "")[:80], topic.get("FirstURL"), topic.get("Text") or "")
        if len(out) >= 8:
            break
    return out


def build_web_queries(*, prompt: str, subject: str, capability: dict[str, Any]) -> list[str]:
    cap_title = str(capability.get("title") or capability.get("id") or "market")
    base = f"{subject} {cap_title}"
    lower = (prompt or "").lower()
    queries = [f"{subject} competitors market share", f"{subject} industry overview"]
    if "competitor" in lower or "peer" in lower:
        queries = [
            f"{subject} main competitors",
            f"{subject} competitive landscape market share",
        ]
    elif "share" in lower or "tam" in lower or "penetration" in lower:
        queries = [
            f"{subject} market share",
            f"{subject} market size TAM SAM",
        ]
    elif "growth" in lower:
        queries = [f"{subject} revenue growth rate", f"{subject} CAGR"]
    return [q if subject.lower() in q.lower() else f"{base} {q}" for q in queries[:2]]


def research_web(
    *,
    prompt: str,
    subject: str,
    capability: dict[str, Any],
    limit: int = 6,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Run web research for one capability.

    Returns (sources, queries_used). Sources are DiligenceIQ-shaped with origin=web.
    """
    queries = build_web_queries(prompt=prompt, subject=subject, capability=capability)
    collected: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for query in queries:
        rows = _gemini_google_search(query, subject=subject)
        if not rows:
            rows = _duckduckgo_search(query)
        for row in rows:
            href = str(row.get("url") or "")
            if href and href in seen_urls:
                continue
            if href:
                seen_urls.add(href)
            if "passages" not in row:
                row["passages"] = [str(row.get("snippet") or "")]
            collected.append(row)

    filtered = filter_by_subject(collected, subject=subject, prompt=prompt)
    return filtered[:limit], queries
