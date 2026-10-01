"""Compose DiligenceIQ Cost Structure — GL map, cost behaviour, unit economics.

Maps the ledger into operating categories for this business. Classifies fixed /
variable / step by driver (not account name). Computes unit economics where
data allow. Flags inflation exposure vs plan assumptions. Sizes efficiency
opportunities net of cost-to-achieve. Dual-writes legacy Economic Engine
Efficiency fields (bom_components / cost_metrics / efficiency_notes).

No invest/pass. No cross-sector cost-ratio benchmarks. No company allowlists.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
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

_DOCUMENT_TITLE = "Economic Engine Efficiency"
_DD_CODE = "DD-13"

_MAP_RULE = (
    "The general ledger is mapped into operating categories relevant to this "
    "business and reconciled to reported cost of sales and operating costs; "
    "any unexplained difference is shown."
)
_CLASS_RULE = (
    "Each category is classified as fixed, variable or step using the "
    "operational driver that moves it — not the account name."
)
_UNIT_RULE = (
    "Unit economics are shown where the data allow (per route, site, tonne, "
    "customer or service), with utilisation and how unit cost moves with volume."
)
_INFLATION_RULE = (
    "Inflation exposure is identified by category (wage, fuel, disposal, "
    "insurance) and compared with what the plan assumes."
)
_EFFICIENCY_RULE = (
    "Efficiency opportunities are quantified net of the cost to achieve them, "
    "with whether each is already counted in the plan."
)
_NO_BENCHMARK_RULE = (
    "Cost ratios are not imported from another sector as a benchmark. "
    "If the ledger cannot be mapped, missing accounts are named and requested."
)

_BOM_LINE_RE = re.compile(
    r"(?i)([A-Za-z][A-Za-z0-9 &/\-]{2,40}?)\s*[—\-–:]\s*(\d+(?:\.\d+)?)\s*%"
)
_BOM_FALSE_RE = re.compile(
    r"(?i)^(fy\d{2,4}|20\d{2}|n/?m|n/?a|yoy|qoq|ltm|cagr|ebitda|gm|cogs|"
    r"total|other|misc|various|share|pct|%|growth|margin)$"
)
_BOM_REJECT_TOKEN = re.compile(
    r"(?i)\b(gordon|wacc|dcf|valuation|bonus|estimated|performance|"
    r"today|annual|yoy|qoq|cagr|probability|milestone|target)\b"
)
_GROSS_MARGIN_RE = re.compile(
    r"(?i)(?:gross\s+margin|GM)\s*(?:(?:pct|%|of\s+revenue)?\s*[:=]?\s*)"
    r"(\d+(?:\.\d+)?)\s*%"
)
_COGS_UNIT_RE = re.compile(
    r"(?i)(?:COGS|cost\s+of\s+(?:goods|sales)|unit\s+cost)"
    r"[^.%]{0,40}?(?:INR|₹|Rs\.?|USD|\$)?\s*([\d,]+(?:\.\d+)?)"
)
_CAC_RE = re.compile(
    r"(?i)\bCAC\b[^.%]{0,30}?(?:INR|₹|Rs\.?|USD|\$)?\s*([\d,]+(?:\.\d+)?)"
)
_LTV_RE = re.compile(
    r"(?i)\b(?:LTV|lifetime\s+value)\b[^.%]{0,40}?(?:INR|₹|Rs\.?|USD|\$)?\s*([\d,]+(?:\.\d+)?)"
)
_UTIL_RE = re.compile(
    r"(?i)(?:utilisation|utilization|capacity\s+utilisation|capacity\s+utilization)"
    r"[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_WAGE_INFL_RE = re.compile(
    r"(?i)(?:wage|salary|labour|labor)\s+(?:inflation|increase|growth)"
    r"[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_FUEL_INFL_RE = re.compile(
    r"(?i)(?:fuel|energy|power)\s+(?:inflation|increase|price)"
    r"[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_PLAN_MARGIN_RE = re.compile(
    r"(?i)(?:margin\s+expansion|gross\s+margin\s+(?:to|target)|GM\s+target)"
    r"[^.%]{0,50}?(\d+(?:\.\d+)?)\s*%"
)
_EFFICIENCY_CUE = re.compile(
    r"(?i)\b(scale\s+advantage|localisation|localization|vertical\s+integration|"
    r"cost\s+(?:reduction|saving|out)|efficiency|automation|lean|"
    r"procurement\s+saving|bom\s+(?:reduction|optim))\b"
)
_INFLATION_CUE = re.compile(
    r"(?i)\b(inflation|wage\s+pressure|fuel\s+price|disposal\s+fee|"
    r"insurance\s+premium|indexation|pass[- ]through)\b"
)
_FIXED_CUE = re.compile(
    r"(?i)\b(rent|lease|facility|facilities|depreciation|amortisation|"
    r"amortization|head\s*office|admin(?:istration)?|insurance|"
    r"salaried\s+(?:staff|headcount)|fixed\s+overhead)\b"
)
_VARIABLE_CUE = re.compile(
    r"(?i)\b(material|bom|battery|component|cogs|direct\s+labour|direct\s+labor|"
    r"fuel|freight|commission|piece[- ]rate|per[- ]unit|variable)\b"
)
_STEP_CUE = re.compile(
    r"(?i)\b(shift|plant|site|depot|warehouse|route|fleet\s+addition|"
    r"step[- ]?(?:cost|fixed)|lump(?:y)?\s+capacity)\b"
)
_UNIT_CUE = re.compile(
    r"(?i)\b(per\s+(?:unit|vehicle|route|site|tonne|ton|customer|service|kwh)|"
    r"unit\s+cost|cost\s+per)\b"
)
_SECTOR_BENCH_CUE = re.compile(
    r"(?i)\b(industry\s+average|sector\s+benchmark|peer\s+cost\s+ratio|"
    r"typical\s+for\s+the\s+industry|cross[- ]sector)\b"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)

# Heuristic category buckets for manufacturing / ops packs when GL is absent.
_CATEGORY_HINTS: list[tuple[str, tuple[str, ...], str, str]] = [
    (
        "Materials / BOM",
        ("battery", "motor", "electronics", "chassis", "panel", "tyre", "tire",
         "wiring", "braking", "material", "component", "bom", "cogs"),
        "Variable",
        "Moves with units produced / sold (BOM and direct materials).",
    ),
    (
        "Direct labour",
        ("labour", "labor", "assembly", "operator", "wage", "payroll"),
        "Variable / step",
        "Variable with volume; may step when a shift or line is added.",
    ),
    (
        "Fuel / energy",
        ("fuel", "energy", "power", "electricity", "diesel"),
        "Variable",
        "Moves with utilisation of assets / throughput.",
    ),
    (
        "Fleet / maintenance",
        ("fleet", "maintenance", "spares", "repair", "logistics", "freight"),
        "Mixed",
        "Base maintenance often step/fixed per asset; usage-driven spend variable.",
    ),
    (
        "Facilities",
        ("facility", "facilities", "rent", "lease", "plant", "warehouse", "depot"),
        "Fixed / step",
        "Site rent and plant overhead fixed until a site or line is added.",
    ),
    (
        "Sales",
        ("sales", "marketing", "cac", "commission", "advertising"),
        "Mixed",
        "Commissions variable with sales; brand / fixed CAC programme often step.",
    ),
    (
        "Administration",
        ("admin", "administration", "overhead", "g&a", "sg&a", "corporate"),
        "Fixed",
        "Head-office and G&A typically do not move unit-for-unit with volume.",
    ),
]


def _info_request(what: str) -> str:
    return f"Information request: {what}"


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
    out = _INVEST_LANG.sub("cost-structure evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
    out = _SECTOR_BENCH_CUE.sub("this-business evidence only", out)
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


def _fmt_pct(value: Any) -> str:
    n = _num(value)
    if n is None:
        return _clean(value, 40) or "—"
    return f"{n:g}%"


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_cost_structure_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "financial": 0,
        "operations": 1,
        "deal_strategy": 2,
        "company_management": 3,
        "customer": 4,
        "market_competition": 5,
        "legal_esg": 6,
    }
    needles = (
        "financial", "cost", "cogs", "margin", "bom", "manufacturing",
        "operations", "payroll", "labour", "labor", "fuel", "fleet",
        "budget", "forecast", "thesis", "spend", "cac", "ltv",
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
    for doc in ranked[:14]:
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


def _hint_category(name: str) -> tuple[str, str, str]:
    lowered = name.lower()
    for label, needles, behaviour, driver in _CATEGORY_HINTS:
        if any(n in lowered for n in needles):
            return label, behaviour, driver
    if _FIXED_CUE.search(name):
        return name, "Fixed", "Does not move unit-for-unit with volume (account cue + driver check needed)."
    if _STEP_CUE.search(name):
        return name, "Step", "Moves when capacity (site / shift / route) is added."
    if _VARIABLE_CUE.search(name):
        return name, "Variable", "Moves with volume / throughput."
    return name, "Unclassified", _info_request(f"operational driver for '{name}'")


def _looks_like_bom_category(name: str, share: float | None) -> bool:
    cat = (name or "").strip()
    if not cat or len(cat) < 3:
        return False
    if _BOM_FALSE_RE.match(cat):
        return False
    if _BOM_REJECT_TOKEN.search(cat):
        return False
    if share is not None and (share <= 0 or share > 100):
        return False
    words = cat.split()
    if len(words) > 5:
        return False
    # Prefer component-like labels (space or known cost cue), skip bare codes
    if len(words) == 1 and len(cat) <= 4 and not _VARIABLE_CUE.search(cat):
        return False
    return True


def _bom_from_legacy_and_corpus(
    corpus: str,
    legacy: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in legacy.get("bom_components") or []:
        if not isinstance(item, dict):
            continue
        cat = _clean(item.get("category") or item.get("name"), 60)
        if not cat:
            continue
        share = _num(item.get("share_pct") if item.get("share_pct") is not None else item.get("pct"))
        if not _looks_like_bom_category(cat, share):
            continue
        key = cat.lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "category": cat,
                "share_pct": share,
                "source": "legacy extract",
            }
        )

    # Only scan free text for BOM lines when legacy is thin
    if len(rows) < 3:
        for m in _BOM_LINE_RE.finditer(corpus or ""):
            cat = _clean(m.group(1), 60)
            if not cat:
                continue
            share = float(m.group(2))
            if not _looks_like_bom_category(cat, share):
                continue
            if len(cat.split()) > 6:
                continue
            key = cat.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "category": cat,
                    "share_pct": share,
                    "source": _DOC_CITE,
                }
            )
    return rows[:16]


def _metrics_from_corpus(corpus: str, legacy: dict[str, Any]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    legacy_metrics = legacy.get("cost_metrics") if isinstance(legacy.get("cost_metrics"), dict) else {}
    for k, v in legacy_metrics.items():
        n = _num(v)
        if n is not None:
            metrics[str(k)] = n

    text = _prose(corpus)
    gm = _GROSS_MARGIN_RE.search(text)
    if gm and "gross_margin_pct" not in metrics:
        metrics["gross_margin_pct"] = float(gm.group(1))
    cogs = _COGS_UNIT_RE.search(text)
    if cogs and "cogs_per_unit" not in metrics and "cogs_per_unit_inr" not in metrics:
        metrics["cogs_per_unit"] = float(cogs.group(1).replace(",", ""))
    cac = _CAC_RE.search(text)
    if cac and "cac" not in metrics and "cac_inr" not in metrics:
        metrics["cac"] = float(cac.group(1).replace(",", ""))
    ltv = _LTV_RE.search(text)
    if ltv and "ltv" not in metrics and "ltv_inr" not in metrics:
        metrics["ltv"] = float(ltv.group(1).replace(",", ""))
    cac_v = metrics.get("cac") or metrics.get("cac_inr")
    ltv_v = metrics.get("ltv") or metrics.get("ltv_inr")
    if cac_v and ltv_v and "ltv_cac_ratio" not in metrics:
        metrics["ltv_cac_ratio"] = round(float(ltv_v) / float(cac_v), 1)
    util = _UTIL_RE.search(text)
    if util:
        metrics["utilisation_pct"] = float(util.group(1))
    return metrics


def _build_gl_map(
    bom: list[dict[str, Any]],
    metrics: dict[str, float],
    corpus: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return (operating_categories, reconciliation, missing_accounts)."""
    aggregated: dict[str, dict[str, Any]] = {}
    for row in bom:
        cat = str(row.get("category") or "")
        label, _behaviour, _driver = _hint_category(cat)
        slot = aggregated.setdefault(
            label,
            {
                "category": label,
                "gl_accounts": [],
                "amount": _NA,
                "share_pct": 0.0,
                "mapped_to": "Cost of sales" if label.startswith("Materials") or label.startswith("Direct") else "Operating costs",
                "source": row.get("source") or _DOC_CITE,
                "notes": _MAP_RULE,
            },
        )
        slot["gl_accounts"].append(cat)
        share = _num(row.get("share_pct"))
        if share is not None:
            slot["share_pct"] = float(slot["share_pct"] or 0) + share

    # Promote sales CAC into Sales category when present
    if metrics.get("cac") is not None or metrics.get("cac_inr") is not None:
        sales = aggregated.setdefault(
            "Sales",
            {
                "category": "Sales",
                "gl_accounts": [],
                "amount": _NA,
                "share_pct": None,
                "mapped_to": "Operating costs",
                "source": _DOC_CITE,
                "notes": _MAP_RULE,
            },
        )
        sales["gl_accounts"] = list(dict.fromkeys([*(sales.get("gl_accounts") or []), "CAC / customer acquisition"]))
        cac_v = metrics.get("cac") or metrics.get("cac_inr")
        sales["amount"] = f"{cac_v:g} (CAC)"

    categories: list[dict[str, Any]] = []
    for label, slot in aggregated.items():
        accounts = slot.get("gl_accounts") or []
        share = slot.get("share_pct")
        categories.append(
            {
                "category": label,
                "gl_accounts": ", ".join(str(a) for a in accounts[:8]) if accounts else _NA,
                "amount": slot.get("amount") or _NA,
                "share_pct": share if isinstance(share, (int, float)) and share else None,
                "mapped_to": slot.get("mapped_to") or "Operating costs",
                "source": slot.get("source") or _DOC_CITE,
                "notes": _MAP_RULE,
            }
        )

    if not categories:
        categories = [
            {
                "category": label,
                "gl_accounts": _info_request(f"GL accounts for {label.lower()}"),
                "amount": _NA,
                "share_pct": None,
                "mapped_to": "Unmapped",
                "source": _NA,
                "notes": _MAP_RULE,
            }
            for label, *_ in _CATEGORY_HINTS[:5]
        ]

    mapped_share = sum(
        float(c["share_pct"])
        for c in categories
        if isinstance(c.get("share_pct"), (int, float))
    )
    reconciliation: list[dict[str, Any]] = []
    if mapped_share > 0:
        reconciliation.append(
            {
                "line": "Mapped operating categories (share sum)",
                "reported": f"{mapped_share:g}%",
                "mapped": f"{mapped_share:g}%",
                "difference": "0%" if abs(mapped_share - 100) < 0.6 else f"{mapped_share - 100:+.1f} pp vs 100%",
                "source": _COMPUTED,
                "notes": _MAP_RULE,
            }
        )
        if abs(mapped_share - 100) >= 0.6:
            reconciliation.append(
                {
                    "line": "Unexplained / unmapped share",
                    "reported": "100%",
                    "mapped": f"{mapped_share:g}%",
                    "difference": f"{100 - mapped_share:+.1f} pp",
                    "source": _COMPUTED,
                    "notes": _info_request("remaining GL accounts to close the map to 100% of COS / opex"),
                }
            )
    gm = metrics.get("gross_margin_pct")
    if gm is not None:
        reconciliation.append(
            {
                "line": "Implied COGS (100 − gross margin)",
                "reported": f"{100 - float(gm):g}% of revenue",
                "mapped": f"Gross margin {gm:g}%",
                "difference": "Reconcile BOM / materials map to this COGS share",
                "source": _COMPUTED,
                "notes": _MAP_RULE,
            }
        )

    missing: list[str] = []
    text = _prose(corpus).lower()
    has_gl = bool(re.search(r"(?i)\b(general\s+ledger|trial\s+balance|chart\s+of\s+accounts|gl\s+detail)\b", corpus or ""))
    if not has_gl:
        missing.append("General ledger / trial balance detail")
    if not bom:
        missing.append("Cost of sales / BOM bridge by operating category")
    if "payroll" not in text and "wage" not in text and "labour" not in text and "labor" not in text:
        missing.append("Payroll / labour cost by function")
    if not _INFLATION_CUE.search(corpus or ""):
        missing.append("Category-level inflation assumptions in the plan")
    if not categories or all(
        str(c.get("gl_accounts") or "").startswith("Information request") for c in categories
    ):
        missing.append("Mapped GL account listing by operating category")

    return categories, reconciliation, missing


def _build_classification(categories: list[dict[str, Any]], corpus: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cat in categories:
        label = str(cat.get("category") or "")
        _, behaviour, driver = _hint_category(label)
        # Refine with corpus cues when category string is generic
        if behaviour == "Unclassified":
            sample = f"{label} {cat.get('gl_accounts') or ''} {corpus[:2000]}"
            if _VARIABLE_CUE.search(sample):
                behaviour, driver = "Variable", "Moves with volume / throughput (evidence cue)."
            elif _STEP_CUE.search(sample):
                behaviour, driver = "Step", "Moves when capacity (site / shift / route) is added."
            elif _FIXED_CUE.search(sample):
                behaviour, driver = "Fixed", "Does not move unit-for-unit with volume."
        rows.append(
            {
                "category": label,
                "classification": behaviour,
                "driver": driver,
                "justification": (
                    f"Classified by operational driver ({driver}) — not by account name. "
                    f"{_CLASS_RULE}"
                ),
                "source": cat.get("source") or _DOC_CITE,
                "notes": _CLASS_RULE,
            }
        )
    if not rows:
        rows.append(
            {
                "category": _info_request("operating cost categories"),
                "classification": _NA,
                "driver": _info_request("driver that moves each category"),
                "justification": _CLASS_RULE,
                "source": _NA,
                "notes": _CLASS_RULE,
            }
        )
    return rows


def _build_unit_economics(
    metrics: dict[str, float],
    corpus: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cogs = metrics.get("cogs_per_unit") or metrics.get("cogs_per_unit_inr")
    if cogs is not None:
        rows.append(
            {
                "unit": "Per unit produced / sold",
                "cost": f"{cogs:g}",
                "utilisation": (
                    f"{metrics['utilisation_pct']:g}%"
                    if metrics.get("utilisation_pct") is not None
                    else _info_request("capacity utilisation")
                ),
                "volume_sensitivity": (
                    "Unit materials cost stays roughly flat with volume; "
                    "fixed/step overhead dilutes as utilisation rises."
                ),
                "source": _DOC_CITE,
                "notes": _UNIT_RULE,
            }
        )
    cac = metrics.get("cac") or metrics.get("cac_inr")
    if cac is not None:
        rows.append(
            {
                "unit": "Per customer acquired (CAC)",
                "cost": f"{cac:g}",
                "utilisation": _NA,
                "volume_sensitivity": (
                    "Acquisition cost is not a production unit cost; scale depends on channel mix."
                ),
                "source": _DOC_CITE,
                "notes": _UNIT_RULE,
            }
        )
    # Narrative unit-cost hits
    for sent in _sentences(corpus or "")[:40]:
        if not _UNIT_CUE.search(sent):
            continue
        if any(str(r.get("cost")) in sent for r in rows if r.get("cost")):
            continue
        rows.append(
            {
                "unit": _clean(sent, 80),
                "cost": _clean(sent, 120),
                "utilisation": (
                    f"{metrics['utilisation_pct']:g}%"
                    if metrics.get("utilisation_pct") is not None
                    else _info_request("utilisation for this unit")
                ),
                "volume_sensitivity": _info_request("unit-cost response to volume change"),
                "source": _DOC_CITE,
                "notes": _UNIT_RULE,
            }
        )
        if len(rows) >= 6:
            break
    if not rows:
        rows.append(
            {
                "unit": _info_request("unit of measure (route / site / tonne / customer / service)"),
                "cost": _NA,
                "utilisation": _info_request("utilisation"),
                "volume_sensitivity": _info_request("how unit cost moves with volume"),
                "source": _NA,
                "notes": _UNIT_RULE,
            }
        )
    return rows[:8]


def _build_inflation(corpus: str, metrics: dict[str, float]) -> list[dict[str, Any]]:
    text = _prose(corpus)
    rows: list[dict[str, Any]] = []
    wage = _WAGE_INFL_RE.search(text)
    fuel = _FUEL_INFL_RE.search(text)
    plan_gm = _PLAN_MARGIN_RE.search(text)

    def _add(category: str, exposure: str, plan: str, *, source: str = _DOC_CITE) -> None:
        rows.append(
            {
                "category": category,
                "exposure": exposure,
                "plan_assumption": plan,
                "gap": (
                    "Plan assumption stated"
                    if _is_filled(plan) and not str(plan).startswith("Information")
                    else "Plan assumption not evidenced — may be assuming inflation away"
                ),
                "source": source,
                "notes": _INFLATION_RULE,
            }
        )

    if wage:
        _add("Wage / labour", f"{wage.group(1)}% wage inflation evidenced", _info_request("plan wage inflation assumption"))
    else:
        _add(
            "Wage / labour",
            _info_request("historical / contracted wage inflation"),
            _info_request("plan wage inflation assumption"),
            source=_NA,
        )
    if fuel:
        _add("Fuel / energy", f"{fuel.group(1)}% fuel/energy move evidenced", _info_request("plan fuel / energy assumption"))
    else:
        _add(
            "Fuel / energy",
            _info_request("fuel / energy inflation exposure"),
            _info_request("plan fuel / energy assumption"),
            source=_NA,
        )
    _add(
        "Disposal / processing",
        _info_request("disposal / processing fee inflation"),
        _info_request("plan disposal assumption"),
        source=_NA,
    )
    _add(
        "Insurance",
        _info_request("insurance premium inflation"),
        _info_request("plan insurance assumption"),
        source=_NA,
    )
    if plan_gm:
        rows.append(
            {
                "category": "Plan margin expansion",
                "exposure": (
                    f"Latest gross margin {metrics['gross_margin_pct']:g}%"
                    if metrics.get("gross_margin_pct") is not None
                    else _NA
                ),
                "plan_assumption": f"Plan references margin / GM around {plan_gm.group(1)}%",
                "gap": "Test whether inflation is netted inside the margin expansion path",
                "source": _DOC_CITE,
                "notes": _INFLATION_RULE,
            }
        )
    elif metrics.get("gross_margin_pct") is not None:
        rows.append(
            {
                "category": "Plan margin expansion",
                "exposure": f"Latest gross margin {metrics['gross_margin_pct']:g}%",
                "plan_assumption": _info_request("plan gross-margin path and inflation net-off"),
                "gap": "Plan inflation vs margin path not evidenced",
                "source": _COMPUTED,
                "notes": _INFLATION_RULE,
            }
        )
    return rows


def _build_efficiency(
    corpus: str,
    legacy: dict[str, Any],
    metrics: dict[str, float],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for note in legacy.get("efficiency_notes") or []:
        if not isinstance(note, str) or not note.strip():
            continue
        key = note.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "opportunity": _clean(note, 160),
                "gross_benefit": _info_request("gross benefit of this efficiency"),
                "cost_to_achieve": _info_request("cost to achieve"),
                "net_benefit": _info_request("net benefit"),
                "in_plan": _info_request("whether already counted in the plan"),
                "source": _DOC_CITE,
                "notes": _EFFICIENCY_RULE,
            }
        )
    for sent in _sentences(corpus or "")[:50]:
        if not _EFFICIENCY_CUE.search(sent):
            continue
        key = sent.strip().lower()[:80]
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "opportunity": _clean(sent, 160),
                "gross_benefit": _info_request("gross benefit"),
                "cost_to_achieve": _info_request("cost to achieve"),
                "net_benefit": _info_request("net benefit"),
                "in_plan": _info_request("already in plan?"),
                "source": _DOC_CITE,
                "notes": _EFFICIENCY_RULE,
            }
        )
        if len(rows) >= 6:
            break
    if metrics.get("gross_margin_pct") is not None and not rows:
        rows.append(
            {
                "opportunity": (
                    f"Margin improvement path from current gross margin "
                    f"{metrics['gross_margin_pct']:g}% — size only with this-business evidence"
                ),
                "gross_benefit": _info_request("gross benefit"),
                "cost_to_achieve": _info_request("cost to achieve"),
                "net_benefit": _info_request("net benefit"),
                "in_plan": _info_request("already in plan?"),
                "source": _COMPUTED,
                "notes": _EFFICIENCY_RULE,
            }
        )
    if not rows:
        rows.append(
            {
                "opportunity": _info_request("efficiency opportunities evidenced in the packs"),
                "gross_benefit": _NA,
                "cost_to_achieve": _NA,
                "net_benefit": _NA,
                "in_plan": _NA,
                "source": _NA,
                "notes": _EFFICIENCY_RULE,
            }
        )
    return rows[:8]


def _legacy_dual_write(
    *,
    bom: list[dict[str, Any]],
    metrics: dict[str, float],
    efficiency: list[dict[str, Any]],
    missing: list[str],
    legacy: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, float], list[str]]:
    bom_out: list[dict[str, Any]] = []
    for row in bom:
        share = _num(row.get("share_pct"))
        bom_out.append(
            {
                "category": _clean(row.get("category"), 60),
                "share_pct": share if share is not None else None,
            }
        )
    if not bom_out:
        for item in legacy.get("bom_components") or []:
            if isinstance(item, dict) and item.get("category"):
                bom_out.append(
                    {
                        "category": _clean(item.get("category"), 60),
                        "share_pct": _num(item.get("share_pct")),
                    }
                )

    metrics_out = dict(metrics)
    for k, v in (legacy.get("cost_metrics") or {}).items():
        if k not in metrics_out:
            n = _num(v)
            if n is not None:
                metrics_out[str(k)] = n

    notes: list[str] = []
    for row in efficiency:
        if isinstance(row, dict) and _is_filled(row.get("opportunity")):
            if not str(row.get("opportunity")).startswith("Information"):
                notes.append(_clean(row.get("opportunity"), 200))
    for note in legacy.get("efficiency_notes") or []:
        if isinstance(note, str) and note.strip():
            notes.append(_clean(note, 200))
    for rule in (_MAP_RULE, _CLASS_RULE, _UNIT_RULE, _INFLATION_RULE, _EFFICIENCY_RULE, _NO_BENCHMARK_RULE):
        if not any(rule[:28].lower() in n.lower() for n in notes):
            notes.append(rule)
    if missing:
        notes.append("Missing accounts / packs: " + "; ".join(missing[:4]))
    # Dedupe preserve order
    deduped: list[str] = []
    seen: set[str] = set()
    for n in notes:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(n)
    return bom_out[:16], metrics_out, deduped[:8]


def _quality_reliance(
    *,
    categories: list[dict[str, Any]],
    classification: list[dict[str, Any]],
    unit_econ: list[dict[str, Any]],
    inflation: list[dict[str, Any]],
    efficiency: list[dict[str, Any]],
    missing: list[str],
    reconciliation: list[dict[str, Any]],
) -> tuple[str, str, str]:
    mapped = sum(
        1 for c in categories
        if isinstance(c, dict)
        and _is_filled(c.get("gl_accounts"))
        and not str(c.get("gl_accounts")).startswith("Information")
    )
    classified = sum(
        1 for c in classification
        if isinstance(c, dict)
        and str(c.get("classification") or "") not in {"", "Unclassified", _NA}
        and not str(c.get("driver") or "").startswith("Information")
    )
    units = sum(
        1 for u in unit_econ
        if isinstance(u, dict)
        and _is_filled(u.get("cost"))
        and not str(u.get("cost")).startswith("Information")
        and u.get("cost") != _NA
    )
    infl_filled = sum(
        1 for r in inflation
        if isinstance(r, dict)
        and _is_filled(r.get("exposure"))
        and not str(r.get("exposure")).startswith("Information")
    )
    eff_filled = sum(
        1 for r in efficiency
        if isinstance(r, dict)
        and _is_filled(r.get("opportunity"))
        and not str(r.get("opportunity")).startswith("Information")
    )
    recon_ok = any(
        isinstance(r, dict)
        and "0%" in str(r.get("difference") or "")
        for r in reconciliation
    )

    if mapped >= 2 and classified >= 2 and (units >= 1 or recon_ok):
        quality = "PASS"
    else:
        quality = "REWORK"

    # Missing GL detail is common; READY when map + behaviour + unit cost exist.
    if mapped >= 2 and classified >= 2 and units >= 1:
        reliance = "READY" if len(missing) <= 2 else "LIMITED"
    elif mapped >= 1 or classified >= 1:
        reliance = "LIMITED"
    else:
        reliance = "BLOCKED"

    bits = [
        f"Quality {quality}: GL/operating map "
        f"{'present' if mapped >= 2 else 'incomplete'} ({mapped} categories).",
        f"Reliance {reliance}: "
        f"{'cost base usable for margin-plan testing' if reliance == 'READY' else 'gaps remain'}.",
    ]
    if missing:
        bits.append("Missing: " + "; ".join(missing[:3]) + ".")
    if infl_filled < 1:
        bits.append("Inflation exposure vs plan still largely an information request.")
    if eff_filled < 1:
        bits.append("Efficiency net of cost-to-achieve not yet quantified.")
    bits.append("No cross-sector cost-ratio benchmarks used.")
    return quality, reliance, " ".join(bits)


# ---------------------------------------------------------------------------
# heuristic / LLM / build / render
# ---------------------------------------------------------------------------


def _heuristic_cost_structure_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    bom = _bom_from_legacy_and_corpus(corpus, legacy)
    metrics = _metrics_from_corpus(corpus, legacy)
    categories, reconciliation, missing = _build_gl_map(bom, metrics, corpus)
    classification = _build_classification(categories, corpus)
    unit_econ = _build_unit_economics(metrics, corpus)
    inflation = _build_inflation(corpus, metrics)
    efficiency = _build_efficiency(corpus, legacy, metrics)
    bom_out, metrics_out, notes = _legacy_dual_write(
        bom=bom,
        metrics=metrics,
        efficiency=efficiency,
        missing=missing,
        legacy=legacy,
    )
    quality, reliance, rationale = _quality_reliance(
        categories=categories,
        classification=classification,
        unit_econ=unit_econ,
        inflation=inflation,
        efficiency=efficiency,
        missing=missing,
        reconciliation=reconciliation,
    )

    bits = [f"Cost Structure for {company}"]
    if bom_out:
        top = max(
            (b for b in bom_out if isinstance(b.get("share_pct"), (int, float))),
            key=lambda b: float(b["share_pct"]),
            default=None,
        )
        if top:
            bits.append(f"largest bucket {top['category']} {float(top['share_pct']):g}%")
    if metrics_out.get("gross_margin_pct") is not None:
        bits.append(f"GM {metrics_out['gross_margin_pct']:g}%")
    bits.append(f"{len(categories)} operating categor{'y' if len(categories) == 1 else 'ies'}")
    if missing:
        bits.append(f"{len(missing)} information gap(s)")

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "operating_categories": categories,
        "reconciliation": reconciliation,
        "cost_classification": classification,
        "unit_economics": unit_econ,
        "inflation_exposure": inflation,
        "efficiency_opportunities": efficiency,
        "missing_accounts": missing,
        # Legacy dual-write
        "bom_components": bom_out,
        "cost_metrics": metrics_out,
        "efficiency_notes": notes,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": not bom_out and not metrics_out and not categories,
    }


def _llm_cost_structure_spec(
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
    try:
        system = compose_system(
            "cost_structure",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot: string,\n"
        "operating_categories: [{category, gl_accounts, amount, share_pct, "
        "mapped_to, source, notes}],\n"
        "reconciliation: [{line, reported, mapped, difference, source, notes}],\n"
        "cost_classification: [{category, classification, driver, justification, "
        "source, notes}],\n"
        "unit_economics: [{unit, cost, utilisation, volume_sensitivity, source, notes}],\n"
        "inflation_exposure: [{category, exposure, plan_assumption, gap, source, notes}],\n"
        "efficiency_opportunities: [{opportunity, gross_benefit, cost_to_achieve, "
        "net_benefit, in_plan, source, notes}],\n"
        "missing_accounts: [string],\n"
        "bom_components: [{category, share_pct}],\n"
        "cost_metrics: {string: number},\n"
        "efficiency_notes: [string],\n"
        "quality_verdict: PASS|REWORK,\n"
        "reliance_verdict: READY|LIMITED|BLOCKED,\n"
        "quality_reliance_rationale: string.\n"
        "Do NOT import cost ratios from another sector. No invest or pass. "
        "Classify by driver, not account name."
    )
    try:
        return generate_json(system=system, user=user, temperature=0.1)
    except Exception:
        return None


def _normalise_llm_spec(
    raw: dict[str, Any],
    *,
    heur: dict[str, Any],
    sources: list[str],
    legacy: dict[str, Any],
) -> dict[str, Any]:
    llm = dict(raw) if isinstance(raw, dict) else {}

    def _rows(key: str, need: str) -> list[dict[str, Any]]:
        rows = llm.get(key) if isinstance(llm.get(key), list) else []
        rows = [r for r in rows if isinstance(r, dict) and r.get(need)]
        return rows or list(heur.get(key) or [])

    categories = _rows("operating_categories", "category")
    for row in categories:
        row["notes"] = _MAP_RULE
        if row.get("gl_accounts"):
            row["gl_accounts"] = _soften_invest(_clean(row.get("gl_accounts"), 200))
    llm["operating_categories"] = categories

    recon = _rows("reconciliation", "line")
    for row in recon:
        row["notes"] = _MAP_RULE
    llm["reconciliation"] = recon or heur.get("reconciliation") or []

    classification = _rows("cost_classification", "category")
    for row in classification:
        row["notes"] = _CLASS_RULE
        row["justification"] = _soften_invest(
            row.get("justification") or _CLASS_RULE
        )
        # Reject account-name-only justifications that cite sector benchmarks
        if _SECTOR_BENCH_CUE.search(str(row.get("justification") or "")):
            row["justification"] = _CLASS_RULE
    llm["cost_classification"] = classification

    unit_econ = _rows("unit_economics", "unit")
    for row in unit_econ:
        row["notes"] = _UNIT_RULE
        for field in ("cost", "utilisation", "volume_sensitivity"):
            if row.get(field):
                row[field] = _soften_invest(_clean(row.get(field), 200))
    llm["unit_economics"] = unit_econ

    inflation = _rows("inflation_exposure", "category")
    for row in inflation:
        row["notes"] = _INFLATION_RULE
    llm["inflation_exposure"] = inflation

    efficiency = _rows("efficiency_opportunities", "opportunity")
    for row in efficiency:
        row["notes"] = _EFFICIENCY_RULE
        row["opportunity"] = _soften_invest(_clean(row.get("opportunity"), 200))
    llm["efficiency_opportunities"] = efficiency

    missing = llm.get("missing_accounts") if isinstance(llm.get("missing_accounts"), list) else []
    missing = [str(m).strip() for m in missing if str(m).strip()] or list(
        heur.get("missing_accounts") or []
    )
    llm["missing_accounts"] = missing[:8]

    bom = llm.get("bom_components") if isinstance(llm.get("bom_components"), list) else []
    bom = [
        {"category": _clean(b.get("category"), 60), "share_pct": _num(b.get("share_pct"))}
        for b in bom
        if isinstance(b, dict) and b.get("category")
    ] or heur.get("bom_components") or []
    llm["bom_components"] = bom[:16]

    metrics = llm.get("cost_metrics") if isinstance(llm.get("cost_metrics"), dict) else {}
    cleaned_metrics: dict[str, float] = {}
    for k, v in metrics.items():
        n = _num(v)
        if n is not None:
            cleaned_metrics[str(k)] = n
    if not cleaned_metrics:
        cleaned_metrics = dict(heur.get("cost_metrics") or {})
    llm["cost_metrics"] = cleaned_metrics

    notes = llm.get("efficiency_notes") if isinstance(llm.get("efficiency_notes"), list) else []
    notes = [_soften_invest(_clean(n, 240)) for n in notes if isinstance(n, str) and n.strip()]
    for rule in (
        _MAP_RULE, _CLASS_RULE, _UNIT_RULE, _INFLATION_RULE, _EFFICIENCY_RULE, _NO_BENCHMARK_RULE,
    ):
        if not any(rule[:28].lower() in x.lower() for x in notes):
            notes.append(rule)
    if not notes:
        notes = list(heur.get("efficiency_notes") or [])
    llm["efficiency_notes"] = notes[:8]

    quality, reliance, rationale = _quality_reliance(
        categories=categories,
        classification=classification,
        unit_econ=unit_econ,
        inflation=inflation,
        efficiency=efficiency,
        missing=missing,
        reconciliation=llm.get("reconciliation") or [],
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

    for dead in ("recommendation", "confidence", "investment_verdict", "verdict", "invest_recommendation"):
        llm.pop(dead, None)

    llm["insight_snapshot"] = _soften_invest(
        llm.get("insight_snapshot") or heur.get("insight_snapshot") or ""
    )
    llm["primary_sources"] = list(sources or [])[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = legacy.get("document") or _DOCUMENT_TITLE
    llm["dd_code"] = legacy.get("dd_code") or _DD_CODE
    llm["empty"] = not categories and not bom
    return llm


def build_cost_structure_spec(
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
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}

    gathered_sources: list[str] = []
    if corpus is None:
        corpus, gathered_sources = gather_cost_structure_corpus(deal, idx or {})
    srcs = list(sources or []) or gathered_sources
    if not srcs:
        srcs = [
            str(d.get("filename"))
            for d in ((idx or {}).get("documents") or [])
            if isinstance(d, dict) and d.get("filename")
        ][:8]

    # Fold legacy BOM / metrics into a seed corpus when VDR text is thin
    seed_bits: list[str] = []
    for b in legacy.get("bom_components") or []:
        if isinstance(b, dict) and b.get("category") is not None:
            share = b.get("share_pct")
            seed_bits.append(
                f"{b['category']} — {share}%" if share is not None else str(b["category"])
            )
    for k, v in (legacy.get("cost_metrics") or {}).items():
        seed_bits.append(f"{k} {v}")
    for note in legacy.get("efficiency_notes") or []:
        if isinstance(note, str) and note.strip():
            seed_bits.append(note.strip())
    seed = "\n".join(seed_bits)
    full_corpus = "\n\n".join(x for x in (corpus or "", seed) if x.strip())

    heur = _heuristic_cost_structure_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        geography=vars_.get("geography"),
        legacy_spec=legacy,
    )
    if prefer_heuristic:
        return heur

    llm_raw = _llm_cost_structure_spec(
        company=target,
        corpus=full_corpus,
        sources=srcs,
        sector=vars_.get("sector"),
        geography=vars_.get("geography"),
        materiality=vars_.get("materiality"),
    )
    if not llm_raw:
        return heur
    return _normalise_llm_spec(llm_raw, heur=heur, sources=srcs, legacy=legacy)


def render_cost_structure_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    categories = (
        spec.get("operating_categories")
        if isinstance(spec.get("operating_categories"), list) else []
    )
    reconciliation = (
        spec.get("reconciliation") if isinstance(spec.get("reconciliation"), list) else []
    )
    classification = (
        spec.get("cost_classification")
        if isinstance(spec.get("cost_classification"), list) else []
    )
    unit_econ = (
        spec.get("unit_economics") if isinstance(spec.get("unit_economics"), list) else []
    )
    inflation = (
        spec.get("inflation_exposure")
        if isinstance(spec.get("inflation_exposure"), list) else []
    )
    efficiency = (
        spec.get("efficiency_opportunities")
        if isinstance(spec.get("efficiency_opportunities"), list) else []
    )
    missing = (
        spec.get("missing_accounts") if isinstance(spec.get("missing_accounts"), list) else []
    )
    bom = spec.get("bom_components") if isinstance(spec.get("bom_components"), list) else []
    metrics = spec.get("cost_metrics") if isinstance(spec.get("cost_metrics"), dict) else {}
    notes = spec.get("efficiency_notes") if isinstance(spec.get("efficiency_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]
    parts.append(f"{_NO_BENCHMARK_RULE}\n\n")

    # 1
    parts.append("## 1. Operating Category Map (GL → Cost Base)\n\n")
    parts.append(f"{_MAP_RULE}\n\n")
    if categories:
        parts.append(_table(
            ["Category", "GL accounts / packs", "Amount", "Share", "Maps to", "Source"],
            [
                [
                    _clean(r.get("category"), 40),
                    _clean(r.get("gl_accounts"), 120),
                    _clean(r.get("amount"), 40),
                    _fmt_pct(r.get("share_pct")) if r.get("share_pct") is not None else "—",
                    _clean(r.get("mapped_to"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in categories if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('GL map into operating categories')}**\n\n")
    if reconciliation:
        parts.append("### Reconciliation to reported COS / operating costs\n\n")
        parts.append(_table(
            ["Line", "Reported", "Mapped", "Difference", "Source"],
            [
                [
                    _clean(r.get("line"), 60),
                    _clean(r.get("reported"), 60),
                    _clean(r.get("mapped"), 60),
                    _clean(r.get("difference"), 80),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in reconciliation if isinstance(r, dict)
            ],
        ))
    if missing:
        parts.append("### Missing accounts / packs\n\n")
        for m in missing:
            parts.append(f"- {_clean(m, 160)}\n")
        parts.append("\n")
    if bom:
        parts.append("### Legacy BOM bridge (dual-write)\n\n")
        parts.append(_table(
            ["Component", "Share"],
            [
                [
                    _clean(b.get("category"), 60),
                    _fmt_pct(b.get("share_pct")) if b.get("share_pct") is not None else "—",
                ]
                for b in bom if isinstance(b, dict)
            ],
        ))
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Fixed / Variable / Step by Driver\n\n")
    parts.append(f"{_CLASS_RULE}\n\n")
    if classification:
        parts.append(_table(
            ["Category", "Classification", "Driver", "Justification", "Source"],
            [
                [
                    _clean(r.get("category"), 40),
                    _clean(r.get("classification"), 30),
                    _clean(r.get("driver"), 100),
                    _clean(r.get("justification"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in classification if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('fixed / variable / step classification by driver')}**\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Unit Economics & Utilisation\n\n")
    parts.append(f"{_UNIT_RULE}\n\n")
    if unit_econ:
        parts.append(_table(
            ["Unit", "Cost", "Utilisation", "As volume changes", "Source"],
            [
                [
                    _clean(r.get("unit"), 60),
                    _clean(r.get("cost"), 80),
                    _clean(r.get("utilisation"), 60),
                    _clean(r.get("volume_sensitivity"), 140),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in unit_econ if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('unit economics (route / site / tonne / customer / service)')}**\n\n")
    if metrics:
        parts.append("### Legacy cost metrics (dual-write)\n\n")
        for k, v in list(metrics.items())[:10]:
            parts.append(
                f"- `{k}`: {v:g}\n" if isinstance(v, (int, float)) else f"- `{k}`: {v}\n"
            )
        parts.append("\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Inflation Exposure vs Plan\n\n")
    parts.append(f"{_INFLATION_RULE}\n\n")
    if inflation:
        parts.append(_table(
            ["Category", "Exposure", "Plan assumption", "Gap", "Source"],
            [
                [
                    _clean(r.get("category"), 40),
                    _clean(r.get("exposure"), 100),
                    _clean(r.get("plan_assumption"), 100),
                    _clean(r.get("gap"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in inflation if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('inflation exposure by category vs plan')}**\n\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Efficiency Opportunities (Net of Cost to Achieve)\n\n")
    parts.append(f"{_EFFICIENCY_RULE}\n\n")
    if efficiency:
        parts.append(_table(
            ["Opportunity", "Gross benefit", "Cost to achieve", "Net", "In plan?", "Source"],
            [
                [
                    _clean(r.get("opportunity"), 100),
                    _clean(r.get("gross_benefit"), 60),
                    _clean(r.get("cost_to_achieve"), 60),
                    _clean(r.get("net_benefit"), 60),
                    _clean(r.get("in_plan"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in efficiency if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('efficiency opportunities net of cost to achieve')}**\n\n")
    if notes:
        parts.append("### Notes\n\n")
        for n in notes[:6]:
            parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This section does not recommend invest or pass. Cost ratios are not imported "
        "from another sector. Classifications use operational drivers, not account names.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    parts.append("## 6. Quality & Reliance\n\n")
    qv = spec.get("quality_verdict") or "REWORK"
    rv = spec.get("reliance_verdict") or "BLOCKED"
    rationale = spec.get("quality_reliance_rationale") or _NA
    parts.append(f"**Quality:** {qv}  \n")
    parts.append(f"**Reliance:** {rv}  \n\n")
    parts.append(f"{_soften_invest(_clean(rationale, 600))}\n\n")
    parts.append(
        "*Quality is PASS or REWORK. Reliance is READY, LIMITED, or BLOCKED. "
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
