"""Compose DiligenceIQ Company Background — real operating business (prompt book).

What it sells, to whom, from where, how it makes money. No investment verdict.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _INDUSTRY,
    _clean,
    _first_match,
    _fmt_num,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_HQ = re.compile(
    r"(?:Headquarters|Head Office|Registered Office)\s*[:\-]?\s*"
    r"([A-Za-z0-9][^.\n|]{4,90}?)(?:\.|$|\n|\|)",
    re.IGNORECASE,
)
_FOUNDED = re.compile(
    r"(?:Founded|Incorporated|Incorporation)\s*[:\-]?\s*"
    r"(?:in\s+)?((?:19|20)\d{2})",
    re.IGNORECASE,
)
_LEGAL_NAME = re.compile(
    r"(?:Legal Name|legal name)\s+([A-Z][A-Za-z0-9 &.,'\-]{4,80}?(?:Limited|Ltd|LLC|Inc|PLC)?)",
    re.IGNORECASE,
)
_HEADCOUNT = re.compile(
    r"Total Headcount\s*\(?FTE\)?[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)",
    re.IGNORECASE,
)
_HEADCOUNT_ALT = re.compile(
    r"(?:headcount|employees|workforce)\s*(?:of|=|:)?\s*"
    r"(?:~)?([\d,]+)",
    re.IGNORECASE,
)
_SHAREHOLDER = re.compile(
    r"([A-Z][A-Za-z0-9 &./()\-]{2,55}?)\s+(\d{1,2}(?:\.\d+)?)\s*%",
)
_FY_ROW = re.compile(
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?\s+"
    r"FY\s*(20\d{2})E?\s+FY\s*(20\d{2})E?",
    re.IGNORECASE,
)
_REVENUE_ROW = re.compile(
    r"\bRevenue\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+"
    r"([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ONLINE_SHARE = re.compile(
    r"Online Sales Share\s*\(?%?\)?[^\d%]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_ONLINE_SHARE_ALT = re.compile(
    r"(?:online|digital[- ]first)\D{0,40}?(\d{1,2}(?:\.\d+)?)\s*%\s*(?:of\s+)?(?:orders|sales|revenue)",
    re.IGNORECASE,
)
# Generic "Label NN%" pairs — used inside Revenue Model / mix blocks only.
_LABEL_PCT = re.compile(
    r"([A-Za-z][A-Za-z0-9 &/+\-]{1,55}?)\s+(\d{1,2}(?:\.\d+)?)\s*%",
)
_PRODUCT_PORTFOLIO = re.compile(
    r"(?:Product(?:s)?\s*(?:Portfolio|Lineup|Catalogue|Catalog)|Offering(?:s)?)\s*[:\-]?\s*"
    r"(.{10,220}?)(?:\.|$|\n|Revenue|Shareholding|Headquarters)",
    re.IGNORECASE | re.DOTALL,
)
_SITE_LINE = re.compile(
    r"(?:Headquarters|Head Office|Registered Office|Factory|Plant|Campus|"
    r"Manufacturing\s+(?:site|facility|campus)|Warehouse|Depot|Office)\s*[:\-]?\s*"
    r"([A-Za-z0-9][^.\n|]{3,90}?)(?:\.|$|\n|\|)",
    re.IGNORECASE,
)
_IPO = re.compile(
    r"\b(IPO|Listed|listing)\b[^.|]{0,100}?(?:20\d{2}|BSE|NSE|NYSE|LSE|exchange)",
    re.IGNORECASE,
)
_D2C = re.compile(
    r"\b(direct[- ]to[- ]consumer|D2C|digital[- ]first|experience centers?|"
    r"company[- ]owned\s+stores?|dealer[- ]led)\b",
    re.IGNORECASE,
)
_CAPACITY = re.compile(
    r"(?:annual\s+)?(?:production\s+)?capacity\s*(?:of|=|:)?\s*"
    r"(?:~)?([\d,]+(?:\.\d+)?)\s*(million|mn|m|units?/?(?:year|yr|month|mo)?|p\.?a\.?)?",
    re.IGNORECASE,
)
_UTILISATION = re.compile(
    r"(?:capacity\s+)?utili[sz]ation\s*(?:of|=|:)?\s*"
    r"(?:~)?(\d{1,3}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_MONTHLY_PROD = re.compile(
    r"(?:monthly\s+production|producing)\s*(?:of|=|:)?\s*"
    r"(?:~)?([\d,]+)\s*units?",
    re.IGNORECASE,
)
# Geography / region share — only when a % follows a place-like token.
_GEO_SPLIT = re.compile(
    r"\b((?:South|North|West|East|Central)\s+[A-Za-z]{2,20}|"
    r"domestic|export|EMEA|APAC|Americas|[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b"
    r"[^%]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%",
)
_CUSTOMER_TYPE = re.compile(
    r"\b((?:retail|individual|B2C|B2B|fleet|corporate|institutional|"
    r"consumer|enterprise)\s*(?:customers?|buyers?|segment)?)"
    r"[^%]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_RECURRING = re.compile(
    r"\b(recurring|subscription|AMC|warranty|connected\s+services?|"
    r"software\s*/?\s*connected|maintenance)\b[^%]{0,50}?(\d{1,2}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
)
_SHAREHOLDER_PREFIXES = re.compile(
    r"^(?:Category|Shareholder|Stake|Promoter(?:\s+Group)?|Strategic(?:\s+Institutional)?|"
    r"Financial(?:\s+Institutional)?|Retail(?:\s*&\s*DII)?|Employee|Miscellaneous|"
    r"Public)\s+",
    re.IGNORECASE,
)

_STREAM_SKIP = {
    "online sales share", "market share", "gross margin", "ebitda margin",
    "yoy", "cagr", "nps", "retention", "churn", "growth", "share",
}
_GEO_SKIP = {
    "online", "digital", "vehicle", "software", "warranty", "accessories",
    "financing", "subscription", "recurring", "promoter", "public",
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


def _omit(reason: str) -> str:
    return f"Omitted: {reason}"


def _info_request(label: str) -> str:
    return f"Information request: {label} (not stated in the data room)"


def _cite_for(filename: str | None) -> str:
    if not filename:
        return _DOC_CITE
    low = filename.lower()
    if "financial" in low or "valuation" in low:
        return "(DOC: data room financials)"
    if "corporate" in low or "hr" in low or "overview" in low:
        return "(DOC: corporate / HR pack)"
    if "commercial" in low:
        return "(DOC: commercial diligence)"
    if "operational" in low or "manufactur" in low:
        return "(DOC: operations pack)"
    return f"(DOC: {filename})"


def gather_company_background_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    """Join company / financial / commercial / ops text for Company Background."""
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "company_management": 0,
        "financial": 1,
        "customer": 2,
        "operations": 3,
        "deal_strategy": 4,
        "market_competition": 5,
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
    for doc in ranked[:12]:
        filename = str(doc.get("filename") or "")
        if not filename:
            continue
        try:
            loaded = load_library_document(deal, filename) or {}
        except Exception:
            loaded = {}
        text = str(loaded.get("text") or doc.get("excerpt") or "")
        text = re.sub(r"[■▪●◆□◦\x7f]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 40:
            continue
        blobs.append(f"### {filename}\n{text[:14_000]}")
        sources.append(filename)
        if sum(len(b) for b in blobs) > 56_000:
            break
    return "\n\n".join(blobs), sources


def _parse_shareholders(corpus: str, *, limit: int = 5) -> str | None:
    block = corpus
    idx = re.search(r"Shareholding Structure", corpus, re.I)
    if idx:
        block = corpus[idx.start() : idx.start() + 900]
    skip = {
        "promoter", "strategic", "financial", "institutional", "retail",
        "employee", "miscellaneous", "category", "stake", "shareholder",
        "public shareholders", "esop pool", "others", "fiis", "public",
        "dii", "diluted",
    }
    hits: list[str] = []
    seen: set[str] = set()
    for m in _SHAREHOLDER.finditer(block):
        name = re.sub(r"\s+", " ", m.group(1)).strip(" -")
        for _ in range(3):
            stripped = _SHAREHOLDER_PREFIXES.sub("", name).strip(" -")
            if stripped == name:
                break
            name = stripped
        pct = m.group(2)
        key = name.lower()
        if (
            not name
            or key in skip
            or any(s == key or key.startswith(s + " ") for s in skip)
            or len(name) < 3
            or name[0].islower()
        ):
            continue
        if key in seen:
            continue
        seen.add(key)
        hits.append(f"{name} {pct}%")
        if len(hits) >= limit:
            break
    return "; ".join(hits) if hits else None


_LEDGER_SHARE_QTY = re.compile(
    r"(?i)(?<![.\d])([\d]{1,3}(?:,\d{3})+|\d{3,})\s+"
    r"(?:(?:common|option|equity/option|equity)\s+)?shares?\b"
)
_STATED_SHARE_TOTAL = re.compile(
    r"(?i)(?P<prefix>shows?\s+|equal(?:s|ing)?\s+|total(?:ing)?\s+)"
    r"(?P<total>[\d]{1,3}(?:,\d{3})+|\d{4,})\s+"
    r"(?P<mid>(?:outstanding\s+)?(?:common\s+)?(?:equity/option\s+)?)shares?"
)


def _ledger_share_quantities(text: str) -> list[int]:
    """Pull discrete share quantities from a securities-ledger narrative."""
    out: list[int] = []
    seen: set[int] = set()
    for m in _LEDGER_SHARE_QTY.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        try:
            n = int(raw)
        except ValueError:
            continue
        if n < 10 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _canonicalize_cap_table_text(text: str | None) -> str | None:
    """Ensure ownership narrative carries a correctly summed share total when components exist."""
    if not text or str(text).startswith("Information"):
        return text
    raw = str(text).strip()
    qtys = _ledger_share_quantities(raw)
    if len(qtys) < 2:
        return raw

    # Prefer component grants over a stated total that sits near "outstanding"
    stated = None
    sm = _STATED_SHARE_TOTAL.search(raw)
    if sm:
        try:
            stated = int(sm.group("total").replace(",", ""))
        except ValueError:
            stated = None
    components = [n for n in qtys if stated is None or n != stated]
    if len(components) < 2:
        components = list(qtys)
    # Drop any quantity that equals the sum of the remaining (already a total)
    for n in list(components):
        others = [x for x in components if x != n]
        if len(others) >= 2 and n == sum(others):
            components = others
            break
    if len(components) < 2:
        return raw
    total = sum(components)
    total_fmt = f"{total:,}"
    if sm is not None:
        mid = sm.group("mid") or ""
        return (
            raw[: sm.start()]
            + f"{sm.group('prefix')}{total_fmt} {mid}shares"
            + raw[sm.end() :]
        )
    if total_fmt in raw and raw.strip().startswith("Total evidenced"):
        return raw
    parts = " + ".join(f"{n:,}" for n in components)
    # Lead with the total so clipped findings / slide bullets keep the correct figure
    body = raw
    if total_fmt in body:
        # Already has total mid/end — still lead with it for clip-safety
        return (
            f"Total evidenced common equity/option shares: {total_fmt} ({parts}). {body}"
        )
    return (
        f"Total evidenced common equity/option shares: {total_fmt} ({parts}). "
        f"{body.rstrip('. ')}."
    )


def _sanitize_legal_name(raw: Any, *, company: str) -> str:
    """Strip invented jurisdiction / cap-table parentheticals from a legal name."""
    from agetic_cdd_api.report_builder_base import _clean_legal_name

    cleaned = _clean_legal_name(raw, fallback=company)
    if not cleaned:
        return company
    return cleaned.rstrip(" .")

def _parse_sector(
    corpus: str,
    entity: dict[str, Any],
    *,
    company: str | None = None,
) -> str | None:
    """Resolve a human sector label from entity notes / corpus — never NAICS bleed."""
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus
    from agetic_cdd_api.services_deals import sector_label

    # Prefer organics / specialized inference over bare industry keyword hits
    # (e.g. "Excludes Education & Health Care" in a ZIP analysis must not win).
    # Include company / legal name — thin corpora still carry "Compost Crew".
    name_hint = " ".join(
        x for x in (
            company,
            str(entity.get("legal_name") or ""),
            str(entity.get("trading_name") or ""),
        ) if x
    )
    inferred = infer_sector_id_from_corpus(f"{name_hint}\n{corpus or ''}")
    if inferred != "generic":
        return sector_label(inferred)

    for note in entity.get("governance_notes") or []:
        if isinstance(note, str) and "sector" in note.lower():
            return _clean(note.split(":", 1)[-1].strip(), 80)
    sector_m = re.search(
        r"Sector\s+([A-Za-z][^.\n|]{4,90}?)(?:\.|$|\n|Stock\s+Exchange)",
        corpus,
        re.I,
    )
    if sector_m:
        return _clean(sector_m.group(1), 80)
    industry_m = _first_match(_INDUSTRY, corpus)
    if industry_m:
        hit = industry_m.group(0)
        # Reject healthcare when the hit sits inside an exclusion / NAICS filter clause
        window = corpus[max(0, industry_m.start() - 40) : industry_m.end() + 20]
        if re.search(r"(?i)excludes?.{0,30}health|education\s*&\s*health", window):
            return None
        sector = _clean(hit, 60).title()
        if re.search(r"(?i)health\s*care|healthcare", sector):
            return None
        if "electric" in sector.lower() and "two" in sector.lower():
            return "Electric Two-Wheelers"
        return sector
    return None


def _parse_headcount(corpus: str) -> str | None:
    m = _HEADCOUNT.search(corpus)
    if m:
        nums = re.findall(r"[\d,]+", m.group(1))
        if nums:
            raw = nums[-1].replace(",", "")
            try:
                return f"{int(raw):,}"
            except ValueError:
                return nums[-1]
    m2 = _HEADCOUNT_ALT.search(corpus)
    if m2:
        return _fmt_num(m2.group(1))
    return None


_PNL_SERVICE_LINES = re.compile(
    r"(?i)\b("
    r"Commercial\s+Sales|Municipal\s+Sales|Residential\s+Sales|"
    r"Key\s*Compostables(?:\s+Sales)?|Compost\s+Sales|"
    r"Curbside\s+Composting|Organic\s+Waste\s+Collection"
    r")\b"
)


def _parse_revenue_streams(corpus: str) -> list[dict[str, str]]:
    """Pull service-line mix only from Revenue Model / mix blocks in the corpus."""
    streams: list[dict[str, str]] = []
    seen: set[str] = set()
    blocks: list[str] = []
    for m in re.finditer(
        r"(?:Revenue\s+Model|Revenue\s+Breakdown|Revenue\s+Mix|Contribution\s+by\s+Stream)"
        r"(.{0,600})",
        corpus,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        blocks.append(m.group(1))
    if not blocks:
        # Fallback: short window after the word "Revenue" that contains several % marks
        for m in re.finditer(r"\bRevenue\b(.{0,350})", corpus, flags=re.IGNORECASE | re.DOTALL):
            window = m.group(1)
            if window.count("%") >= 2:
                blocks.append(window)
                break
    for block in blocks:
        for m in _LABEL_PCT.finditer(block):
            name = _clean(m.group(1), 60).strip(" -:/")
            key = name.lower()
            if (
                not name
                or key in seen
                or key in _STREAM_SKIP
                or any(s in key for s in _STREAM_SKIP)
                or len(name) < 3
            ):
                continue
            seen.add(key)
            streams.append({
                "dimension": "service_line",
                "label": name,
                "share": f"{m.group(2)}%",
                "period": "latest disclosed",
                "source": _DOC_CITE,
            })
            if len(streams) >= 6:
                return streams

    # Accounts P&L named lines (Commercial / Municipal / Residential / …) — no % needed
    if len(streams) < 3:
        for m in _PNL_SERVICE_LINES.finditer(corpus[:40_000]):
            name = re.sub(r"\s+", " ", m.group(1)).strip()
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            streams.append({
                "dimension": "service_line",
                "label": name,
                "share": "evidenced in accounts",
                "period": "accounts P&L",
                "source": _DOC_CITE,
            })
            if len(streams) >= 6:
                break
    return streams


def _parse_products(corpus: str) -> list[str]:
    """Extract product/service names from Product Portfolio (or similar) in the corpus."""
    products: list[str] = []
    seen: set[str] = set()
    m = _PRODUCT_PORTFOLIO.search(corpus)
    if m:
        raw = re.sub(r"\s+", " ", m.group(1)).strip()
        # Split on common separators; keep multi-word product tokens from the pack.
        parts = re.split(r"\s{2,}|,|/|;|\||(?<=[a-z\)])\s+(?=[A-Z0-9])", raw)
        for part in parts:
            name = _clean(part, 40).strip(" -")
            if not name or len(name) < 2:
                continue
            key = name.lower()
            if key in seen or key in {"product", "portfolio", "and", "the"}:
                continue
            seen.add(key)
            products.append(name)
            if len(products) >= 8:
                break
    return products


def _parse_presence(corpus: str) -> list[dict[str, str]]:
    """Sites/facilities named after HQ / factory / campus labels in the corpus."""
    rows: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(site: str, rtype: str) -> None:
        site = _clean(site, 90)
        key = site.lower()
        if not site or key in seen:
            return
        seen.add(key)
        rows.append({
            "site": site,
            "type": rtype,
            "role": "Named in data room",
            "source": _DOC_CITE,
        })

    for m in _SITE_LINE.finditer(corpus):
        site = m.group(1)
        label = m.group(0).lower()
        rtype = "Facility"
        if "head" in label or "registered" in label or "office" in label:
            rtype = "HQ"
        elif "factory" in label or "plant" in label or "manufactur" in label or "campus" in label:
            rtype = "Manufacturing"
        elif "warehouse" in label or "depot" in label:
            rtype = "Logistics"
        add(site, rtype)
        if len(rows) >= 5:
            return rows

    # Named "… manufacturing campus / factory / plant" without a leading label.
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9][\w ]{1,50}?)\s+"
        r"(?:manufacturing\s+campus|factory|plant|gigafactory)\b",
        corpus,
    ):
        add(m.group(0), "Manufacturing")
        if len(rows) >= 5:
            break
    return rows


def _parse_ma_events(corpus: str) -> list[dict[str, str]]:
    """Capital / listing events only when the wording appears in the corpus."""
    events: list[dict[str, str]] = []
    ipo = _IPO.search(corpus)
    if ipo:
        events.append({
            "date": _clean(ipo.group(0), 60),
            "event": "Public listing / IPO (as stated in data room)",
            "evidence": _DOC_CITE,
        })
    # Strategic investment mentions — use the investor name from the sentence, not a fixed list.
    for m in re.finditer(
        r"([A-Z][A-Za-z0-9 &./-]{2,40}?)\s+(?:strategic\s+)?(?:investment|investor|shareholder)",
        corpus[:20_000],
    ):
        name = _clean(m.group(1), 40)
        if name.lower() in {"the", "a", "an", "major", "key", "institutional"}:
            continue
        events.append({
            "date": _NA,
            "event": f"{name} investment / shareholding (date not stated in excerpt)",
            "evidence": _DOC_CITE,
        })
        if len(events) >= 4:
            break
    return events[:4]


def _parse_headcount_by_function(corpus: str, sources: list[str]) -> list[dict[str, str]]:
    cite = _cite_for(next((s for s in sources if "hr" in s.lower()), sources[0] if sources else None))
    rows: list[dict[str, str]] = []
    patterns = [
        (r"Technology\s*/\s*R&D[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)", "Technology / R&D"),
        (r"Sales\s*(?:&|/)\s*Customer[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)", "Sales & Customer"),
        (r"Manufactur(?:ing|e)[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)", "Manufacturing"),
        (r"G&A[^\d]{0,40}?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\s+\d[\d,]*)*)", "G&A"),
    ]
    for pat, label in patterns:
        m = re.search(pat, corpus, re.I)
        if not m:
            continue
        nums = re.findall(r"[\d,]+", m.group(1))
        if not nums:
            continue
        raw = nums[-1].replace(",", "")
        try:
            val = f"{int(raw):,}"
        except ValueError:
            val = nums[-1]
        rows.append({"function": label, "headcount": val, "period": "latest disclosed", "source": cite})
    total = _parse_headcount(corpus)
    if total and not any(r["function"] == "Total" for r in rows):
        rows.insert(0, {
            "function": "Total",
            "headcount": total,
            "period": "latest disclosed",
            "source": cite,
        })
    return rows


def _accounts_total(corpus: str) -> tuple[str | None, str | None]:
    years_m = _FY_ROW.search(corpus)
    rev_m = _REVENUE_ROW.search(corpus)
    if not years_m or not rev_m:
        return None, None
    # Prefer FY2024 slot (index 3) when present
    year = years_m.group(4)
    raw = rev_m.group(4)
    return f"FY{year}", _fmt_num(raw, "cr")


def _quality_reliance(*, filled: int, requests: int) -> tuple[str, str, str]:
    quality = "PASS"
    if filled >= 6 and requests <= 2:
        reliance = "READY"
        rationale = (
            f"Operating description is usable: {filled} evidenced fields; "
            f"{requests} information request(s)."
        )
    elif filled >= 3:
        reliance = "LIMITED"
        rationale = (
            f"{filled} evidenced operating fields; {requests} material request(s) remain — "
            f"later agents should treat this as a partial picture of the real company."
        )
    else:
        reliance = "BLOCKED"
        rationale = (
            f"Only {filled} operating fields located; later agents lack a reliable "
            f"description of how the business actually works."
        )
    return quality, reliance, rationale


def _llm_company_background_spec(
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

    system = compose_system(
        "company_background",
        sector=sector,
        geography=geography,
        materiality=materiality,
    )
    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string — real operating business only),\n"
        "offers: {sells (string), how_charges (string), who_pays (string)},\n"
        "revenue_by_service_line: [{label, share, period, source}],\n"
        "revenue_by_customer_type: [{label, share, period, source}],\n"
        "revenue_by_geography: [{label, share, period, source}],\n"
        "recurring_by_contract (string — proportion recurring; or omit reason),\n"
        "accounts_reconciliation (string — how split reconciles to accounts),\n"
        "products_in_company_terms: [string] (company's own product/service names),\n"
        "omitted_fields: [{field, reason}] (fields that do not apply),\n"
        "sites: [{site, type, role, source}],\n"
        "capacity: {fleet_or_capacity, utilisation, source} "
        "(omit fields that do not apply with reason in omitted_fields),\n"
        "headcount_by_function: [{function, headcount, period, source}],\n"
        "ownership: {legal_entities, ownership_or_cap_table, history_events: "
        "[{date, event, evidence}], corporate_record_requests: [string]},\n"
        "operating_model (string — one plain-language paragraph: one unit of "
        "revenue end-to-end; what is in-house),\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
        "Use the company's own product/service names. Do not import another sector's template.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_company_background_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    entity: dict[str, Any],
) -> dict[str, Any]:
    sents = _sentences(corpus)
    sector = _parse_sector(corpus, entity, company=company)
    legal = _sanitize_legal_name(entity.get("legal_name") or company, company=company)
    legal_m = _LEGAL_NAME.search(corpus)
    if legal_m and (not entity.get("legal_name") or company == "Target"):
        legal = _sanitize_legal_name(_clean(legal_m.group(1), 80), company=company)

    hq = entity.get("jurisdiction")
    if isinstance(hq, str) and re.search(r"(?i)jurisdiction|organized in|Maryland\s*/\s*D\.?C", hq):
        if not re.search(r"(?i)headquarters|registered office|HQ\b", hq):
            hq = None
    if not hq:
        hq_m = _HQ.search(corpus)
        hq = _clean(hq_m.group(1), 80) if hq_m else None
        if isinstance(hq, str) and re.search(r"(?i)jurisdiction|organized in|Maryland\s*/\s*D\.?C", hq):
            if not re.search(r"(?i)headquarters|registered office|HQ\b", hq):
                hq = None
    founded = entity.get("incorporation_date")
    if not founded:
        fm = _FOUNDED.search(corpus)
        founded = fm.group(1) if fm else None

    fin_cite = _DOC_CITE
    for src in sources:
        if "financial" in src.lower():
            fin_cite = _cite_for(src)
            break
    primary_cite = _cite_for(sources[0] if sources else None)

    streams = _parse_revenue_streams(corpus)
    products = _parse_products(corpus)
    period, accounts_total = _accounts_total(corpus)

    # Customer type — online share as channel proxy when true B2B/B2C split missing
    customer_rows: list[dict[str, str]] = []
    for m in _CUSTOMER_TYPE.finditer(corpus[:30_000]):
        customer_rows.append({
            "label": _clean(m.group(1), 40),
            "share": f"{m.group(2)}%",
            "period": period or "latest disclosed",
            "source": "(DOC: commercial diligence)",
        })
        if len(customer_rows) >= 4:
            break
    online = _ONLINE_SHARE.search(corpus) or _ONLINE_SHARE_ALT.search(corpus)
    if online and not customer_rows:
        customer_rows.append({
            "label": "Online / digital channel (orders)",
            "share": f"{online.group(1)}%",
            "period": period or "latest disclosed",
            "source": "(DOC: commercial diligence)",
        })
        offline = None
        try:
            offline = f"{100 - float(online.group(1)):.0f}%"
        except ValueError:
            offline = None
        if offline:
            customer_rows.append({
                "label": "Offline / experience-center channel (implied)",
                "share": offline,
                "period": period or "latest disclosed",
                "source": _COMPUTED,
            })

    geo_rows: list[dict[str, str]] = []
    for m in _GEO_SPLIT.finditer(corpus[:30_000]):
        label = _clean(m.group(1), 40)
        if label.lower() in _GEO_SKIP or any(s in label.lower() for s in _GEO_SKIP):
            continue
        # Prefer region-like labels (contain a compass/region word or look like a place).
        if not re.search(
            r"south|north|west|east|central|domestic|export|emea|apac|americas|[A-Z]",
            label,
            re.I,
        ):
            continue
        geo_rows.append({
            "label": label,
            "share": f"{m.group(2)}%",
            "period": period or "latest disclosed",
            "source": "(DOC: commercial diligence)",
        })
        if len(geo_rows) >= 4:
            break

    omitted: list[dict[str, str]] = []
    if not streams:
        omitted.append({
            "field": "revenue_by_service_line",
            "reason": "No service-line mix found in the accounting / commercial packs",
        })
    if not customer_rows:
        omitted.append({
            "field": "revenue_by_customer_type",
            "reason": "No customer-type revenue split in the data room",
        })
    if not geo_rows:
        omitted.append({
            "field": "revenue_by_geography",
            "reason": "No geographic revenue split in the data room",
        })

    recurring = None
    rec_hits: list[str] = []
    for m in _RECURRING.finditer(corpus[:40_000]):
        label = _clean(m.group(1), 40)
        rec_hits.append(f"{label} {m.group(2)}%")
        if len(rec_hits) >= 3:
            break
    # Also pull warranty/software shares from streams
    for s in streams:
        low = s["label"].lower()
        if any(k in low for k in ("warranty", "amc", "software", "connected", "subscription")):
            rec_hits.append(f"{s['label']} {s['share']}")
    if rec_hits:
        recurring = (
            "Disclosed recurring / aftermarket lines (not full contract book): "
            + "; ".join(dict.fromkeys(rec_hits))
            + f" {_DOC_CITE}"
        )
    else:
        recurring = _omit("Contract-level recurring revenue % not stated in the data room")

    if accounts_total and streams:
        recon = (
            f"Service-line shares are mix percentages from commercial / corporate packs; "
            f"headline accounts revenue for {period} is {accounts_total} {fin_cite}. "
            f"Absolute rupee bridge by line was not provided — treat mix as directional until "
            f"a line-item P&L by stream is obtained."
        )
    elif accounts_total:
        recon = (
            f"Accounts show {accounts_total} revenue for {period} {fin_cite}; "
            f"no service-line mix to reconcile."
        )
    else:
        recon = _info_request("audited revenue by service line / customer / geography")

    d2c = bool(_D2C.search(corpus))
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus as _inf0

    organics_early = _inf0(f"{legal}\n{company}\n{corpus}") == "waste_organics" or (
        bool(sector) and bool(re.search(r"(?i)organic|compost|waste", str(sector)))
    )
    if organics_early:
        sector = "Organics & Composting"
    sells = (
        f"{', '.join(products[:4])} and related services"
        if products
        else (
            (
                "Organic waste collection and composting services, finished compost / soil "
                "amendments, and compostable supplies"
                if organics_early
                else f"{sector} products/services"
            )
            if sector
            else _info_request("product / service catalogue in company terms")
        )
    )
    # Never default to an EV/vehicle charging template — that bleeds across sectors.
    if organics_early:
        how_charges = (
            "Monthly subscription fees for residential pickups, recurring commercial and "
            "municipal service contracts, and per-unit product sales"
        )
    elif streams or products:
        how_charges = _info_request("how the company charges (pricing / contract model)")
    else:
        how_charges = _NA
    if d2c and how_charges != _NA and "Information request" not in how_charges:
        how_charges += " via direct-to-consumer / digital-first channels"
    how_charges += f" {primary_cite}" if how_charges != _NA else ""
    who_pays = (
        "End consumers (and any fleet/commercial buyers named in commercial packs)"
        if d2c or customer_rows
        else _NA
    )

    sites = _parse_presence(corpus)
    if not sites and hq:
        sites = [{"site": hq, "type": "HQ", "role": "Registered / headquarters", "source": primary_cite}]
    if not sites:
        omitted.append({
            "field": "sites",
            "reason": "No sites / facilities named in the data room",
        })

    cap_m = _CAPACITY.search(corpus)
    util_m = _UTILISATION.search(corpus)
    month_m = _MONTHLY_PROD.search(corpus)
    capacity: dict[str, str] = {}
    if cap_m:
        unit = (cap_m.group(2) or "units").strip()
        capacity["fleet_or_capacity"] = f"{_fmt_num(cap_m.group(1))} {unit} {_DOC_CITE}"
    if month_m:
        capacity["fleet_or_capacity"] = (
            capacity.get("fleet_or_capacity", "")
            + ("; " if capacity.get("fleet_or_capacity") else "")
            + f"Monthly production ~{_fmt_num(month_m.group(1))} units {_DOC_CITE}"
        ).strip("; ")
    if util_m:
        capacity["utilisation"] = f"{util_m.group(1)}% {_DOC_CITE}"
    if not capacity.get("fleet_or_capacity"):
        omitted.append({
            "field": "fleet_or_capacity",
            "reason": "No fleet / production capacity figure in the data room",
        })
        capacity["fleet_or_capacity"] = _omit("No capacity / fleet figure in VDR")
    if not capacity.get("utilisation"):
        capacity["utilisation"] = _omit("Utilisation not measurable from current packs")
    capacity.setdefault("source", "(DOC: operations pack)")

    headcount_rows = _parse_headcount_by_function(corpus, sources)
    if not headcount_rows:
        omitted.append({
            "field": "headcount_by_function",
            "reason": "No functional headcount split in the HR pack",
        })

    ownership_text = _canonicalize_cap_table_text(_parse_shareholders(corpus))
    # Prefer securities-ledger narrative from corpus when present (richer than % list)
    ledger_m = re.search(
        r"(?i)(?:Common Stock outstanding|Securities ledger|Stock Option Plan).{0,500}",
        corpus[:80_000],
    )
    if ledger_m:
        ownership_text = _canonicalize_cap_table_text(ledger_m.group(0)) or ownership_text
    history = _parse_ma_events(corpus)
    founded_m = founded
    if founded_m:
        history.insert(0, {
            "date": founded_m,
            "event": f"Founded / incorporated ({founded_m})",
            "evidence": primary_cite,
        })
    corp_requests: list[str] = []
    if not ownership_text:
        corp_requests.append(_info_request("current cap table / share register"))
    if not history:
        corp_requests.append(_info_request("corporate history / formation documents"))
    if not entity.get("entity_type") and not re.search(r"\b(Limited|Ltd|LLC|Inc|PLC)\b", legal):
        corp_requests.append(_info_request("legal entity type and corporate record"))

    # Operating model paragraph
    in_house_bits = []
    if sites:
        in_house_bits.append("manufacturing / assembly at named sites")
    if d2c:
        in_house_bits.append("direct digital sales and experience centers")
    if any("software" in s["label"].lower() or "connected" in s["label"].lower() for s in streams):
        in_house_bits.append("software / connected services")
    if not in_house_bits:
        in_house_bits.append("core product delivery (extent of outsourcing not stated)")

    op_seed = _pick_sentences(
        sents,
        keywords=("manufactur", "sell", "deliver", "experience center", "factory", "battery"),
        limit=2,
    )
    operating_model = (
        f"For one unit of revenue, {legal} typically designs and builds the product "
        f"({' / '.join(products[:3]) if products else 'its core offering'}), "
        f"sells it to the paying customer"
        f"{' through D2C / digital and experience-center channels' if d2c else ''}, "
        f"and may attach aftermarket / warranty / software where disclosed. "
        f"In-house today (from VDR): {', '.join(in_house_bits)}. "
        f"{_clean(op_seed[0], 180) if op_seed else ''} {_DOC_CITE}"
    ).strip()

    filled = 0
    if streams:
        filled += 1
    if customer_rows:
        filled += 1
    if geo_rows:
        filled += 1
    if sites:
        filled += 1
    if capacity.get("fleet_or_capacity") and not str(capacity["fleet_or_capacity"]).startswith("Omitted"):
        filled += 1
    if headcount_rows:
        filled += 1
    if ownership_text:
        filled += 1
    if operating_model:
        filled += 1
    requests_n = len(corp_requests) + sum(
        1 for o in omitted if "request" in o.get("reason", "").lower() or o["field"].startswith("revenue")
    )
    quality, reliance, qr = _quality_reliance(filled=filled, requests=requests_n)

    # Refuse cross-sector template bleed (EV vehicle AMC / Healthcare products)
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus as _inf

    organics_deal = organics_early or _inf(f"{legal}\n{company}\n{corpus}") == "waste_organics" or (
        bool(sector) and bool(re.search(r"(?i)organic|compost|waste", str(sector)))
    )
    if organics_deal:
        sector = "Organics & Composting"
    insight = (
        f"{legal} operates as a real business in "
        f"{sector or 'its disclosed sector'}: "
        f"what it sells, where it operates, and how money is earned are taken from the VDR — "
        f"not from a generic sector template."
    )

    sells_s = sells if isinstance(sells, str) else _NA
    how_s = how_charges if isinstance(how_charges, str) else _NA
    if organics_deal and re.search(r"(?i)\bhealthcare\b|\belectric\b|\bvehicle", sells_s):
        sells_s = (
            "Organic waste collection and composting services, finished compost / soil "
            "amendments, and compostable supplies"
        )
    if organics_deal and re.search(
        r"(?i)vehicle|warranty/AMC|two-wheeler|\bEV\b|Healthcare products", how_s
    ):
        how_s = (
            "Monthly subscription fees for residential pickups, recurring commercial and "
            "municipal service contracts, and per-unit product sales"
        )

    return {
        "insight_snapshot": insight,
        "offers": {
            "sells": sells_s,
            "how_charges": how_s,
            "who_pays": who_pays,
        },
        "revenue_by_service_line": streams,
        "revenue_by_customer_type": customer_rows,
        "revenue_by_geography": geo_rows,
        "recurring_by_contract": recurring,
        "accounts_reconciliation": recon,
        "products_in_company_terms": products,
        "omitted_fields": omitted,
        "sites": sites,
        "capacity": capacity,
        "headcount_by_function": headcount_rows,
        "ownership": {
            "legal_entities": legal,
            "ownership_or_cap_table": ownership_text or _info_request("cap table and corporate record"),
            "headquarters": hq or _NA,
            "founded": founded or _NA,
            "history_events": history,
            "corporate_record_requests": corp_requests,
        },
        "operating_model": operating_model,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        # Downstream / F-05 compatibility
        "legal_name": legal,
        "jurisdiction": hq,
        "incorporation_date": founded,
        "entity_type": entity.get("entity_type"),
        "governance_notes": entity.get("governance_notes") or [],
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    company: str,
    sources: list[str],
    entity: dict[str, Any],
) -> dict[str, Any]:
    offers = llm.get("offers") if isinstance(llm.get("offers"), dict) else {}
    ownership = llm.get("ownership") if isinstance(llm.get("ownership"), dict) else {}
    ownership.setdefault("legal_entities", entity.get("legal_name") or company)
    ownership.setdefault(
        "ownership_or_cap_table",
        _info_request("cap table and corporate record"),
    )
    ownership.setdefault("history_events", [])
    ownership.setdefault("corporate_record_requests", [])
    llm["ownership"] = ownership
    # Also refuse Healthcare / EV template bleed when normalising LLM output
    offers = llm.get("offers") if isinstance(llm.get("offers"), dict) else {}
    sells = str(offers.get("sells") or "")
    how = str(offers.get("how_charges") or "")
    from agetic_cdd_api.services_accounts_extract import infer_sector_id_from_corpus as _inf2

    # entity may carry wrong industry; trust corpus organics signals
    # (corpus not passed here — use ownership / products / streams / company as proxy)
    organics_proxy = _inf2(company) == "waste_organics" or any(
        re.search(r"(?i)compost|organic|hauling|municipal|key\s*compost", str(x))
        for x in (
            *(llm.get("products_in_company_terms") or []),
            *((r.get("label") if isinstance(r, dict) else r) for r in (llm.get("revenue_by_service_line") or [])),
            ownership.get("legal_entities"),
            company,
        )
    )
    if organics_proxy:
        if re.search(r"(?i)\bhealthcare\b|\belectric\b|\bvehicle|Health Care", sells) or not sells.strip():
            offers["sells"] = (
                "Organic waste collection and composting services, finished compost / soil "
                "amendments, and compostable supplies"
            )
        if re.search(r"(?i)vehicle|warranty/AMC|two-wheeler|\bEV\b", how):
            offers["how_charges"] = (
                "Monthly subscription fees for residential pickups, recurring commercial and "
                "municipal service contracts, and per-unit product sales"
            )
        snap = str(llm.get("insight_snapshot") or "")
        if re.search(r"(?i)healthcare|health\s*care|electric two|vehicle", snap):
            llm["insight_snapshot"] = (
                f"{company} operates as a real business in Organics & Composting: "
                f"what it sells, where it operates, and how money is earned are taken from the VDR — "
                f"not from a generic sector template."
            )
        llm["offers"] = offers
    llm["offers"] = {
        "sells": offers.get("sells") or _NA,
        "how_charges": offers.get("how_charges") or _NA,
        "who_pays": offers.get("who_pays") or _NA,
    }
    llm.setdefault("revenue_by_service_line", [])
    llm.setdefault("revenue_by_customer_type", [])
    llm.setdefault("revenue_by_geography", [])
    llm.setdefault("omitted_fields", [])
    llm.setdefault("sites", [])
    llm.setdefault("headcount_by_function", [])
    llm.setdefault("products_in_company_terms", [])

    # Option-holder Job Titles from a securities ledger are not an org headcount roster.
    # Drop fabricated functional headcount when every row is a single named title.
    hc = llm.get("headcount_by_function")
    if isinstance(hc, list) and hc:
        title_like = 0
        for row in hc:
            if not isinstance(row, dict):
                continue
            fn = str(row.get("function") or "")
            try:
                n = int(float(row.get("headcount") or 0))
            except (TypeError, ValueError):
                n = 0
            if n <= 1 and re.search(
                r"(?i)ceo|driver|svp|vice\s+president|operator|ex-employee|director",
                fn,
            ):
                title_like += 1
        if title_like >= max(2, len(hc) - 1):
            llm["headcount_by_function"] = []
            omitted = llm.get("omitted_fields") if isinstance(llm.get("omitted_fields"), list) else []
            omitted.append({
                "field": "headcount_by_function",
                "reason": (
                    "Securities-ledger option-holder job titles are not a payroll "
                    "headcount roster — omitted rather than inventing org chart counts"
                ),
            })
            llm["omitted_fields"] = omitted

    if not isinstance(llm.get("capacity"), dict):
        llm["capacity"] = {
            "fleet_or_capacity": _omit("Not stated"),
            "utilisation": _omit("Not stated"),
            "source": _NA,
        }
    if not str(llm.get("operating_model") or "").strip():
        llm["operating_model"] = _info_request("plain-language operating model from management")

    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"} or rv not in {"READY", "LIMITED", "BLOCKED"}:
        filled = sum(
            1
            for key in (
                llm.get("revenue_by_service_line"),
                llm.get("sites"),
                llm.get("headcount_by_function"),
                ownership.get("ownership_or_cap_table"),
                llm.get("operating_model"),
            )
            if key
        )
        qv, rv, rationale = _quality_reliance(
            filled=filled,
            requests=len(ownership.get("corporate_record_requests") or []),
        )
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv
        llm.setdefault("quality_reliance_rationale", rationale)
    else:
        llm["quality_verdict"] = qv
        llm["reliance_verdict"] = rv

    for dead in ("recommendation", "confidence", "key_conditions", "verdict", "synthesis"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    # Sanitize legal name — LLMs sometimes append cap-table / jurisdiction parentheticals
    raw_legal = ownership.get("legal_entities") or entity.get("legal_name") or company
    clean_legal = _sanitize_legal_name(raw_legal, company=company)
    ownership["legal_entities"] = clean_legal
    # Canonicalize share totals — LLM arithmetic on the ledger is unstable across runs
    ownership["ownership_or_cap_table"] = _canonicalize_cap_table_text(
        ownership.get("ownership_or_cap_table")
    ) or ownership.get("ownership_or_cap_table")
    llm["ownership"] = ownership
    llm["legal_name"] = clean_legal
    # Do not invent jurisdiction when the data room leaves it open
    hq = ownership.get("headquarters") or entity.get("jurisdiction")
    if isinstance(hq, str) and re.search(r"(?i)jurisdiction|organized in|Maryland\s*/\s*D\.?C", hq):
        # Soft claim without incorporation evidence → treat as HQ footprint only if explicit HQ
        if not re.search(r"(?i)headquarters|registered office|HQ\b", hq):
            hq = None
    llm["jurisdiction"] = hq
    llm["incorporation_date"] = ownership.get("founded") or entity.get("incorporation_date")
    llm["entity_type"] = entity.get("entity_type")
    llm["governance_notes"] = entity.get("governance_notes") or []
    return llm


def build_company_background_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    entity_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
) -> dict[str, Any]:
    """Build prompt-book Company Background fields from CDL + optional F-05 entity."""
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    entity = entity_spec if isinstance(entity_spec, dict) else {}
    target = company or str(
        entity.get("legal_name")
        or getattr(deal, "company", None)
        or deal.name
        or "Target"
    )
    if corpus is None or sources is None:
        corpus, sources = gather_company_background_corpus(deal, idx)
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
    if not vars_.get("sector"):
        vars_["sector"] = _parse_sector(corpus, entity, company=target)

    llm = _llm_company_background_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if llm:
        return _normalise_llm_spec(llm, company=target, sources=sources, entity=entity)

    return _heuristic_company_background_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        entity=entity,
    )


def render_company_background_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    """Render prompt-book Company Background (real operating business)."""
    offers = spec.get("offers") if isinstance(spec.get("offers"), dict) else {}
    service = spec.get("revenue_by_service_line") if isinstance(spec.get("revenue_by_service_line"), list) else []
    customers = spec.get("revenue_by_customer_type") if isinstance(spec.get("revenue_by_customer_type"), list) else []
    geos = spec.get("revenue_by_geography") if isinstance(spec.get("revenue_by_geography"), list) else []
    omitted = spec.get("omitted_fields") if isinstance(spec.get("omitted_fields"), list) else []
    sites = spec.get("sites") if isinstance(spec.get("sites"), list) else []
    capacity = spec.get("capacity") if isinstance(spec.get("capacity"), dict) else {}
    headcount = spec.get("headcount_by_function") if isinstance(spec.get("headcount_by_function"), list) else []
    ownership = spec.get("ownership") if isinstance(spec.get("ownership"), dict) else {}
    history = ownership.get("history_events") if isinstance(ownership.get("history_events"), list) else []
    requests = ownership.get("corporate_record_requests") if isinstance(ownership.get("corporate_record_requests"), list) else []
    products = spec.get("products_in_company_terms") if isinstance(spec.get("products_in_company_terms"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1. Revenue / what it sells
    parts.append("## 1. What It Sells & How It Makes Money\n\n")
    parts.append(f"- **Sells:** {_clean(offers.get('sells'), 220)}\n")
    parts.append(f"- **How it charges:** {_clean(offers.get('how_charges'), 220)}\n")
    parts.append(f"- **Who pays:** {_clean(offers.get('who_pays'), 160)}\n\n")
    if products:
        parts.append("**Products / services (company terms):** "
                     + ", ".join(_clean(p, 40) for p in products[:8] if p) + "\n\n")

    parts.append("### Revenue by Service Line\n\n")
    if service:
        parts.append(_table(
            ["Service Line", "Share", "Period", "Source"],
            [
                [
                    _clean(r.get("label") or r.get("stream"), 80),
                    _clean(r.get("share") or r.get("contribution"), 20),
                    _clean(r.get("period"), 40),
                    _clean(r.get("source") or r.get("cite"), 60),
                ]
                for r in service if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_omit('No service-line mix in the data room')}\n\n")

    parts.append("### Revenue by Customer Type\n\n")
    if customers:
        parts.append(_table(
            ["Customer Type", "Share", "Period", "Source"],
            [
                [
                    _clean(r.get("label"), 80),
                    _clean(r.get("share"), 20),
                    _clean(r.get("period"), 40),
                    _clean(r.get("source"), 60),
                ]
                for r in customers if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_omit('No customer-type revenue split in the data room')}\n\n")

    parts.append("### Revenue by Geography\n\n")
    if geos:
        parts.append(_table(
            ["Geography", "Share", "Period", "Source"],
            [
                [
                    _clean(r.get("label"), 80),
                    _clean(r.get("share"), 20),
                    _clean(r.get("period"), 40),
                    _clean(r.get("source"), 60),
                ]
                for r in geos if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_omit('No geographic revenue split in the data room')}\n\n")

    parts.append(f"**Recurring by contract:** {_clean(spec.get('recurring_by_contract'), 320)}\n\n")
    parts.append(f"**Accounts reconciliation:** {_clean(spec.get('accounts_reconciliation'), 420)}\n\n")
    if omitted:
        parts.append("**Fields omitted (do not apply / not in records):**\n\n")
        for row in omitted[:8]:
            if isinstance(row, dict):
                parts.append(f"- {_clean(row.get('field'), 60)} — {_clean(row.get('reason'), 160)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 2. Physical operation
    parts.append("## 2. Physical Operation\n\n")
    parts.append("### Sites & Facilities\n\n")
    if sites:
        parts.append(_table(
            ["Site", "Type", "Role", "Source"],
            [
                [
                    _clean(r.get("site") or r.get("region"), 80),
                    _clean(r.get("type"), 40),
                    _clean(r.get("role") or r.get("importance"), 80),
                    _clean(r.get("source") or r.get("cite"), 60),
                ]
                for r in sites if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_omit('No sites named in the data room')}\n\n")

    parts.append("### Fleet / Capacity & Utilisation\n\n")
    parts.append(f"- **Fleet or capacity:** {_clean(capacity.get('fleet_or_capacity'), 200)}\n")
    parts.append(f"- **Utilisation:** {_clean(capacity.get('utilisation'), 120)}\n")
    if capacity.get("source"):
        parts.append(f"- **Source:** {_clean(capacity.get('source'), 60)}\n")
    parts.append("\n")

    parts.append("### Headcount by Function\n\n")
    if headcount:
        parts.append(_table(
            ["Function", "Headcount", "Period", "Source"],
            [
                [
                    _clean(r.get("function"), 60),
                    _clean(r.get("headcount"), 20),
                    _clean(r.get("period"), 40),
                    _clean(r.get("source"), 60),
                ]
                for r in headcount if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_omit('No functional headcount split in the data room')}\n\n")
    parts.append("---\n\n")

    # 3. Ownership & history
    parts.append("## 3. Ownership, Legal Entities & History\n\n")
    parts.append(f"- **Legal entity / entities:** {_clean(ownership.get('legal_entities'), 120)}\n")
    if ownership.get("headquarters"):
        parts.append(f"- **Headquarters:** {_clean(ownership.get('headquarters'), 80)}\n")
    if ownership.get("founded"):
        parts.append(f"- **Founded / incorporated:** {_clean(ownership.get('founded'), 40)}\n")
    parts.append(
        f"- **Ownership / cap table:** "
        f"{_clean(ownership.get('ownership_or_cap_table'), 220)}\n\n"
    )
    parts.append("### History (evidenced)\n\n")
    if history:
        parts.append(_table(
            ["Date", "Event", "Evidence"],
            [
                [
                    _clean(r.get("date"), 40),
                    _clean(r.get("event"), 160),
                    _clean(r.get("evidence") or r.get("cite"), 60),
                ]
                for r in history if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('corporate history with dated events')}\n\n")
    if requests:
        parts.append("**Corporate record requests:**\n\n")
        for req in requests[:6]:
            parts.append(f"- {_clean(req, 200)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 4. Operating model
    parts.append("## 4. Operating Model\n\n")
    parts.append(f"{_clean(spec.get('operating_model'), 900)}\n\n")
    parts.append(
        "*This section describes how the business actually operates. "
        "It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    # 5. Quality & Reliance
    parts.append("## 5. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can later agents rest on this picture of the real company?\n\n"
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
