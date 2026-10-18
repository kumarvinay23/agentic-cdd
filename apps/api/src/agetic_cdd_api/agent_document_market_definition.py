"""Compose DiligenceIQ Market Definition — competition perimeter (prompt book).

Four-axis perimeter from operating footprint. Exclusions (strategy vs capability).
TAM/SAM/SOM (addressable / obtainable) with named assumptions + formulas.
Published figures are context unless perimeter matches. Right-to-win deferred.
Exports perimeter for Volume / Pricing / Share. Downstream market agents wait
until approved. No invest/pass.
"""

from __future__ import annotations

import re
from typing import Any

from agetic_cdd_api.agent_document_deal_context import (
    _DOC_CITE,
    _clean,
    _fmt_num,
    _pick_sentences,
    _sentences,
)
from agetic_cdd_api.models import Deal

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"

_TAM = re.compile(
    r"\bTAM\b[^\d$₹]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
    re.IGNORECASE,
)
_SAM = re.compile(
    r"\bSAM\b[^\d$₹]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
    re.IGNORECASE,
)
_SOM = re.compile(
    r"\bSOM\b[^\d$₹]{0,40}?(?:USD\s*|INR\s*|₹\s*|\$)?\s*"
    r"([\d,]+(?:\.\d+)?)\s*(B|Bn|billion|cr|crore|M|million)?",
    re.IGNORECASE,
)
_GEO_SHARE = re.compile(
    r"([A-Za-z][A-Za-z /,&\-]{2,40}?)\s*[:\(]?\s*(?:~)?(\d{1,2}(?:\.\d+)?)\s*%"
    r"[^\n.]{0,40}?(?:revenue|units|share)",
    re.IGNORECASE,
)
_PENETRATION = re.compile(
    r"(?:penetration|market\s+share)[^\d%]{0,40}?(\d{1,2}(?:\.\d+)?)\s*%",
    re.IGNORECASE,
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


def gather_market_definition_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "market_competition": 0,
        "deal_strategy": 1,
        "customer": 2,
        "company_management": 3,
        "operations": 4,
        "financial": 5,
    }
    geo_boost = re.compile(
        r"(?i)Philadelphia|Washington\s*,?\s*D\.?C|DMV|Northern\s+Virginia|Maryland|"
        r"geography|metropolitan|service\s+area|operating\s+footprint"
    )
    docs = [d for d in (index.get("documents") or []) if isinstance(d, dict)]

    def _rank(d: dict[str, Any]) -> tuple:
        excerpt = str(d.get("excerpt") or d.get("filename") or "")
        boost = 0 if geo_boost.search(excerpt) else 1
        return (
            boost,
            prefer.get(str(d.get("cdl_category") or ""), 9),
            str(d.get("filename") or ""),
        )

    ranked = sorted(docs, key=_rank)
    blobs: list[str] = []
    sources: list[str] = []
    for doc in ranked[:16]:
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
        if sum(len(b) for b in blobs) > 64_000:
            break
    return "\n\n".join(blobs), sources


def _money(m: re.Match[str] | None) -> str:
    if not m:
        return _NA
    return f"{_fmt_num(m.group(1), m.group(2))} {_DOC_CITE}"


def _is_polluted_service(text: str) -> bool:
    """Reject growth-thesis / foundation soft-fill splices as 'service sold'."""
    t = text or ""
    if re.search(r"(?i)Foundation\s*·|Uses\s+\w+|Insight Snapshot", t):
        return True
    if re.search(r"(?i)plan relies on|investment thesis|series\s*b|must be true", t):
        return True
    if "…" in t or "\u2026" in t:
        if re.search(r"(?i)Foundation|municipal contract|F-\d{2}", t):
            return True
    # KPI / retention consistency blurbs are not a market perimeter axis
    if re.search(r"(?i)\b(LTV|ARPU|YTD|Consistency\s*--|98\.\d%\s*→)", t):
        return True
    # CIM / teaser marketing blurbs are not a service / customer / chain definition
    if re.search(
        r"(?i)vertically-integrated|closed-?\s*loop|active locations|"
        r"tons diverted|Metro Region|composting leader",
        t,
    ):
        return True
    # Product SKU / price-list lines are not a value-chain stage
    if re.search(r"(?i)\b(cubic\s+yard|1cft|\d+\s*lb\s+bag|Farm Feast)", t):
        return True
    return False


def _clean_framing_list(raw: Any, *, perimeter: dict[str, str]) -> list[str]:
    """Prefer perimeter service; drop polluted legacy / foundation / KPI clips."""
    out: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            s = str(item or "").strip()
            if not s or s.startswith("Information") or _is_polluted_service(s):
                continue
            out.append(_clean(s, 280))
            if len(out) >= 2:
                break
    elif isinstance(raw, str) and raw.strip() and not _is_polluted_service(raw):
        out.append(_clean(raw, 280))
    if not out:
        for key in ("service",):
            val = str(perimeter.get(key) or "").strip()
            if val and not val.startswith("Information") and not _is_polluted_service(val):
                out.append(_clean(val, 280))
        cust = str(perimeter.get("customer_types") or "").strip()
        if (
            cust
            and not cust.startswith("Information")
            and not _is_polluted_service(cust)
            and len(out) < 2
        ):
            out.append(_clean(cust, 280))
    return out


def _perimeter(corpus: str, prior: dict[str, Any] | None) -> dict[str, str]:
    sents = _sentences(corpus)

    service = _pick_sentences(
        sents,
        keywords=(
            "product", "sells", "offering", "compost", "organic waste", "hauling",
            "collection", "soil amendment", "service", "platform",
        ),
        limit=4,
    )
    service = [s for s in service if not _is_polluted_service(s)]
    customer = _pick_sentences(
        sents,
        keywords=(
            "customer", "b2c", "b2b", "retail", "fleet", "consumer",
            "residential", "commercial", "municipal", "end-user", "segment", "icp",
        ),
        limit=2,
    )
    customer = [c for c in customer if not _is_polluted_service(c)]
    geography = _pick_sentences(
        sents,
        keywords=(
            "geography", "region", "export", "state", "metro",
            "reachable", "presence", "market share by", "washington", "philadelphia",
        ),
        limit=2,
    )
    value_chain = _pick_sentences(
        sents,
        keywords=(
            "vertical", "collection", "processing", "composting", "hauling",
            "manufactur", "assembly", "retail", "distribution",
            "oem", "value chain",
        ),
        limit=2,
    )
    value_chain = [v for v in value_chain if not _is_polluted_service(v)]

    # Prefer prior F-05 / company background offers over keyword hits from thesis packs
    if isinstance(prior, dict):
        offers = prior.get("offers") if isinstance(prior.get("offers"), dict) else {}
        sells = str(offers.get("sells") or "").strip()
        if sells and not _is_polluted_service(sells):
            service = [sells] + [s for s in service if s != sells]
        who = str(offers.get("who_pays") or offers.get("to_whom") or "").strip()
        if who and not _is_polluted_service(who):
            customer = [who] + [c for c in customer if c != who]

    geos = []
    for m in _GEO_SHARE.finditer(corpus[:30_000]):
        geos.append(f"{_clean(m.group(1), 40)} ~{m.group(2)}% {_DOC_CITE}")
        if len(geos) >= 4:
            break
    # Organics / regional operators often name metro footprints without % shares.
    # Scan a wide window and assemble the full footprint (not just the first state hit).
    if not geos:
        # Collect place names from this deal's corpus and compose a clean footprint.
        footprint_re = re.compile(
            r"(?i)\b(?:Washington\s*,?\s*D\.?C\.?|Washington\s+metropolitan\s+area|"
            r"District of Columbia|DMV|NOVA|Northern\s+Virginia|Maryland|"
            r"Philadelphia|New\s+York(?:\s+City)?|London|Singapore|"
            r"Montgomery\s+County|Fairfax\s+County|"
            r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\s+County)\b"
        )
        hits = footprint_re.findall(corpus[:80_000])
        if hits:
            noise = {
                "metropolitan area", "metro", "region", "across", "during", "in", "the",
            }
            # Normalize labels from corpus hits (preserve evidence, drop keyword debris).
            norm_map = [
                (r"(?i)washington\s*,?\s*d\.?c\.?|district of columbia", "Washington D.C."),
                (r"(?i)washington\s+metropolitan", "Washington metropolitan area"),
                (r"(?i)northern\s+virginia|nova", "Northern Virginia"),
                (r"(?i)\bmaryland\b", "Maryland"),
                (r"(?i)\bphiladelphia\b", "Philadelphia"),
                (r"(?i)\bdmv\b", "DMV"),
                (r"(?i)montgomery\s+county", "Montgomery County"),
                (r"(?i)fairfax\s+county", "Fairfax County"),
                (r"(?i)new\s+york(?:\s+city)?", "New York"),
                (r"(?i)\blondon\b", "London"),
                (r"(?i)\bsingapore\b", "Singapore"),
            ]
            seen: set[str] = set()
            ordered: list[str] = []
            lower_hits = [re.sub(r"\s+", " ", str(h)).strip().lower() for h in hits]
            for pat, label in norm_map:
                if any(re.search(pat, h) for h in lower_hits) and label.lower() not in seen:
                    if label.lower() in noise:
                        continue
                    seen.add(label.lower())
                    ordered.append(label)
            # Compose a readable metro footprint when the pack names the core + satellites.
            if "washington d.c." in seen and (
                "maryland" in seen or "northern virginia" in seen or "dmv" in seen
            ):
                phrase = "Washington D.C. metropolitan area"
                bits = [b for b in ("Maryland", "Northern Virginia") if b.lower() in seen]
                if bits:
                    phrase += f" (including {' and '.join(bits)})"
                if "philadelphia" in seen:
                    phrase += " and Philadelphia"
                geos.append(_clean(phrase, 220) + f" {_DOC_CITE}")
            elif ordered:
                geos.append(_clean(", ".join(ordered[:5]), 200) + f" {_DOC_CITE}")

    service_txt = (
        _clean(service[0], 280) + (f" {_DOC_CITE}" if "DOC:" not in service[0] else "")
        if service
        else _info_request("service sold — from operating footprint, not industry label")
    )
    if _is_polluted_service(service_txt):
        service_txt = _info_request("service sold — from operating footprint, not industry label")

    customer_txt = (
        _clean(customer[0], 280) + (f" {_DOC_CITE}" if customer and "DOC:" not in customer[0] else "")
        if customer
        else _info_request("customer types actually served")
    )
    if customer and _is_polluted_service(customer_txt):
        customer_txt = _info_request("customer types actually served")

    chain_txt = (
        _clean(value_chain[0], 280) + f" {_DOC_CITE}"
        if value_chain
        else _info_request("stage of the value chain occupied")
    )
    if value_chain and _is_polluted_service(chain_txt):
        chain_txt = _info_request("stage of the value chain occupied")

    return {
        "service": service_txt,
        "customer_types": customer_txt,
        "geography": (
            ("; ".join(geos) if geos else (_clean(geography[0], 280) + f" {_DOC_CITE}" if geography else ""))
            or _info_request("geography actually reachable from operating footprint")
        ),
        "value_chain_stage": chain_txt,
        "footprint_basis": (
            "Perimeter drawn from operating footprint in opened packs — not a sector label alone."
        ),
    }


def _double_count(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    hits = _pick_sentences(
        sents,
        keywords=(
            "collection", "processing", "sale of", "double count", "value chain",
            "aftermarket", "spare", "software attach", "battery", "services revenue",
        ),
        limit=3,
    )
    rows: list[dict[str, str]] = []
    for h in hits:
        rows.append({
            "stream": _clean(h, 120),
            "risk": "Could be counted twice if stacked with related stage revenue",
            "treatment": f"Keep as a distinct stream; do not sum into the same unit of demand {_DOC_CITE}",
        })
    if not rows:
        rows.append({
            "stream": _info_request("revenue streams that could double-count across the value chain"),
            "risk": _NA,
            "treatment": "Separate collection / processing / end-product sale when evidenced",
        })
    return rows[:4]


def _exclusions(corpus: str) -> list[dict[str, str]]:
    sents = _sentences(corpus)
    strategic = _pick_sentences(
        sents,
        keywords=("not compete", "out of scope", "exclude", "adjacent", "does not sell", "focus on"),
        limit=2,
    )
    capability = _pick_sentences(
        sents,
        keywords=(
            "cannot", "not yet", "unable", "capacity constrain", "no presence",
            "not licensed", "export restriction", "cannot currently",
        ),
        limit=2,
    )
    rows: list[dict[str, str]] = []
    for s in strategic:
        rows.append({
            "exclusion": _clean(s, 200),
            "kind": "strategic",
            "why": f"Deliberate strategic boundary {_DOC_CITE}",
        })
    for s in capability:
        rows.append({
            "exclusion": _clean(s, 200),
            "kind": "capability",
            "why": f"Cannot currently serve — capability / reach limit {_DOC_CITE}",
        })
    if not rows:
        rows.append({
            "exclusion": _info_request("explicit market exclusions"),
            "kind": "unclassified",
            "why": "Distinguish strategic exclusion from capability gap when evidence appears",
        })
    return rows[:5]


def _markets(corpus: str) -> tuple[dict[str, str], dict[str, str], list[dict[str, str]]]:
    tam_m = _TAM.search(corpus)
    sam_m = _SAM.search(corpus)
    som_m = _SOM.search(corpus)
    pen_m = _PENETRATION.search(corpus)

    sents = _sentences(corpus)
    reg = _pick_sentences(sents, keywords=("fame", "subsidy", "regulation", "policy", "licence"), limit=1)
    cap = _pick_sentences(sents, keywords=("capacity", "units p.a", "production", "factory"), limit=1)
    geo_ok = bool(_GEO_SHARE.search(corpus))

    assumptions = [
        {
            "assumption": "serviceable_geography",
            "statement": (
                f"Geography shares evidenced in pack {_DOC_CITE}"
                if geo_ok
                else _info_request("serviceable geography for addressable market")
            ),
        },
        {
            "assumption": "regulation",
            "statement": (
                _clean(reg[0], 160) + f" {_DOC_CITE}"
                if reg
                else _info_request("regulatory / licence constraints on the perimeter")
            ),
        },
        {
            "assumption": "route_or_delivery_radius",
            "statement": _info_request("route / delivery / distribution radius"),
        },
        {
            "assumption": "capacity",
            "statement": (
                _clean(cap[0], 160) + f" {_DOC_CITE}"
                if cap
                else _info_request("capacity constraint")
            ),
        },
        {
            "assumption": "realistic_penetration",
            "statement": (
                f"~{pen_m.group(1)}% {_DOC_CITE}"
                if pen_m
                else _info_request("realistic penetration rate")
            ),
        },
    ]

    addressable = {
        "label": "Addressable market / SAM (from this perimeter)",
        "value": _money(sam_m) if sam_m else (_money(tam_m) if tam_m else _info_request("addressable market sized from the perimeter")),
        "basis": (
            "SAM cited in pack — only valid if published perimeter matches ours; else treat as context"
            if sam_m
            else (
                "TAM cited — broader industry context until perimeter match is confirmed"
                if tam_m
                else "No perimeter-matched addressable figure in opened packs"
            )
        ),
        "formula": (
            "SAM = TAM × serviceable share × regulated eligible share "
            "(only when each input is evidenced on this perimeter)"
            if (sam_m or tam_m)
            else _info_request("formula + inputs for addressable market")
        ),
        "source": _DOC_CITE if (sam_m or tam_m) else _NA,
    }
    obtainable = {
        "label": "Obtainable market / SOM (from this perimeter)",
        "value": _money(som_m) if som_m else _info_request("obtainable market from the perimeter"),
        "basis": (
            "SOM cited — subject to capacity and realistic penetration assumptions"
            if som_m
            else "Obtainable slice not evidenced independently of published SOM"
        ),
        "formula": (
            "SOM = SAM × realistic penetration (capacity / reach constrained); "
            "right-to-win deferred — not scored in Market Definition"
            if som_m
            else _info_request("formula + inputs for obtainable market")
        ),
        "source": _DOC_CITE if som_m else _NA,
    }
    return addressable, obtainable, assumptions


def _published_figures(corpus: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for label, pattern in (("TAM", _TAM), ("SAM", _SAM), ("SOM", _SOM)):
        m = pattern.search(corpus)
        if not m:
            continue
        rows.append({
            "figure": f"{label} {_fmt_num(m.group(1), m.group(2))}",
            "published_perimeter": _info_request(f"published perimeter behind {label}"),
            "as_of_date": _info_request(f"as-of date for {label}"),
            "unit": "currency (as stated in source)",
            "matches_ours": "unknown — confirm perimeter/date/unit match before using as addressable",
            "use": (
                "Context only until perimeter match is confirmed — cannot be used as the addressable market"
                if label == "TAM"
                else "Candidate addressable/obtainable only if perimeter matches ours; otherwise context"
            ),
            "source": _DOC_CITE,
        })
    if not rows:
        rows.append({
            "figure": _info_request("published market figure"),
            "published_perimeter": _NA,
            "as_of_date": _NA,
            "unit": _NA,
            "matches_ours": "n/a",
            "use": "Broader industry figures are context, not the market",
            "source": _NA,
        })
    return rows[:5]


def _perimeter_export(
    perimeter: dict[str, str],
    *,
    as_of_date: str | None = None,
    unit: str | None = None,
) -> dict[str, Any]:
    """Shared fact register consumed by Volume / Pricing / Share agents."""
    axes = {
        k: perimeter.get(k)
        for k in ("service", "customer_types", "geography", "value_chain_stage")
    }
    complete = all(
        v
        and not str(v).startswith("Information")
        and v != _NA
        for v in axes.values()
    )
    return {
        "service": axes["service"],
        "customer_types": axes["customer_types"],
        "geography": axes["geography"],
        "value_chain_stage": axes["value_chain_stage"],
        "footprint_basis": perimeter.get("footprint_basis")
        or "Operating footprint — not an industry label alone.",
        "as_of_date": (as_of_date or "").strip() or _info_request("as-of date for perimeter"),
        "unit": (unit or "").strip() or "value (currency) unless volume stated",
        "complete": complete,
        "right_to_win": "deferred",
        "export_for": ["market_volume_and_growth", "market_pricing", "market_share_strategy"],
    }


def _perimeter_consistency_qa(
    *,
    perimeter_export: dict[str, Any],
    published: list[dict[str, str]],
) -> list[dict[str, str]]:
    """QA: same perimeter / date / unit across published comparisons."""
    checks: list[dict[str, str]] = []
    export_date = str(perimeter_export.get("as_of_date") or "")
    export_unit = str(perimeter_export.get("unit") or "")
    for row in published:
        if not isinstance(row, dict):
            continue
        fig = str(row.get("figure") or "published figure")
        match = str(row.get("matches_ours") or "").lower()
        pub_date = str(row.get("as_of_date") or "")
        pub_unit = str(row.get("unit") or "")
        ok_perimeter = "match" in match and "unknown" not in match and "no" not in match
        date_aligned = (
            pub_date
            and not pub_date.startswith("Information")
            and pub_date != _NA
            and export_date
            and not export_date.startswith("Information")
            and pub_date[:4] == export_date[:4]
            if len(export_date) >= 4 and len(pub_date) >= 4
            else False
        )
        unit_aligned = bool(pub_unit and export_unit and pub_unit != _NA)
        if ok_perimeter and date_aligned and unit_aligned:
            status = "PASS"
            note = f"{fig}: perimeter, date and unit aligned with export."
        elif "n/a" in match:
            status = "N/A"
            note = f"{fig}: no published figure to compare."
        else:
            status = "REWORK"
            note = (
                f"{fig}: hold as context until perimeter, as-of date and unit "
                f"match the exported four-axis object "
                f"(export date={_clean(export_date, 40)}; unit={_clean(export_unit, 40)})."
            )
        checks.append({
            "check": "same_perimeter_date_unit",
            "figure": fig,
            "status": status,
            "note": note,
        })
    if not checks:
        checks.append({
            "check": "same_perimeter_date_unit",
            "figure": "n/a",
            "status": "N/A",
            "note": "No published figures to reconcile to the exported perimeter.",
        })
    return checks


def _questions_from_md_gaps(spec: dict[str, Any]) -> list[dict[str, str]]:
    from agetic_cdd_api.prompt_book import normalize_question

    out: list[dict[str, str]] = []
    perimeter = spec.get("perimeter") if isinstance(spec.get("perimeter"), dict) else {}
    for axis, label in (
        ("service", "service sold"),
        ("customer_types", "customer types served"),
        ("geography", "geography actually reachable"),
        ("value_chain_stage", "value-chain stage occupied"),
    ):
        val = str(perimeter.get(axis) or "")
        if not val or val.startswith("Information") or val == _NA:
            out.append(
                normalize_question(
                    {
                        "question": f"Evidence the {label} axis from operating footprint",
                        "required_records": f"Operating / commercial pack describing {label}",
                        "decision_effect": "Wrong perimeter biases every later market number",
                        "priority": "mandatory_pre_decision",
                        "owner": "market diligence lead",
                        "timing": "before other market agents",
                        "closure_test": f"{label} stated with locator on operating footprint",
                        "interim_treatment": "Keep downstream market agents blocked",
                    }
                )
            )

    published = spec.get("published_figures") if isinstance(spec.get("published_figures"), list) else []
    for row in published:
        if not isinstance(row, dict):
            continue
        match = str(row.get("matches_ours") or "").lower()
        fig = str(row.get("figure") or "published figure")
        if "unknown" in match or match.startswith("information"):
            out.append(
                normalize_question(
                    {
                        "question": f"Confirm whether {fig} perimeter/date/unit matches ours",
                        "required_records": "Publisher scope note / methodology appendix",
                        "decision_effect": "Prevents using context figures as addressable",
                        "priority": "mandatory_pre_decision",
                        "owner": "market diligence lead",
                        "timing": "before IC sizing",
                        "closure_test": "Explicit match or context-only label with same unit/date",
                        "interim_treatment": "Treat figure as context only",
                    }
                )
            )

    assumptions = spec.get("assumptions") if isinstance(spec.get("assumptions"), list) else []
    for row in assumptions:
        if not isinstance(row, dict):
            continue
        stmt = str(row.get("statement") or "")
        name = str(row.get("assumption") or "assumption")
        if stmt.startswith("Information") or stmt == _NA:
            out.append(
                normalize_question(
                    {
                        "question": f"Provide evidence for assumption: {name}",
                        "required_records": f"Support for {name} on this perimeter",
                        "decision_effect": "Addressable / obtainable sizing not READY",
                        "priority": "signing_condition",
                        "owner": "market diligence lead",
                        "timing": "per deal timetable",
                        "closure_test": f"{name} stated with formula inputs and locator",
                        "interim_treatment": "Do not invent penetration or capacity",
                    }
                )
            )

    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for q in out:
        key = q.get("question", "").lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(q)
    if not unique:
        unique.append(
            normalize_question(
                {
                    "question": "No material market-definition inputs are missing for the stated perimeter",
                    "required_records": "N/A — current pack sufficient for four-axis export",
                    "decision_effect": "None — perimeter publishable for Volume / Pricing / Share",
                    "priority": "residual_uncertainty",
                    "owner": "market diligence lead",
                    "timing": "n/a",
                    "closure_test": "Re-run if operating footprint or geography changes",
                    "interim_treatment": "None",
                }
            )
        )
    return unique[:12]


def _approval_gate(*, perimeter: dict[str, str], untested: int) -> dict[str, Any]:
    axes_ok = sum(
        1
        for k in ("service", "customer_types", "geography", "value_chain_stage")
        if perimeter.get(k)
        and not str(perimeter[k]).startswith("Information")
        and perimeter[k] != _NA
    )
    if axes_ok >= 3 and untested <= 2:
        status = "ready_for_approval"
        blocks = True
        note = (
            f"{axes_ok}/4 perimeter axes evidenced. Downstream market agents remain "
            "blocked until this perimeter is approved."
        )
    elif axes_ok >= 1:
        status = "pending_approval"
        blocks = True
        note = (
            f"Only {axes_ok}/4 perimeter axes evidenced. Do not run other market agents "
            "until the perimeter is approved."
        )
    else:
        status = "blocked"
        blocks = True
        note = "Perimeter incomplete — all other market agents stay blocked."
    return {
        "status": status,
        "blocks_downstream_market_agents": blocks,
        "axes_evidenced": axes_ok,
        "note": note,
    }


def _quality_reliance(*, axes: int, published_as_context: bool, untested: int) -> tuple[str, str, str]:
    quality = "PASS"
    if axes < 2:
        return quality, "BLOCKED", f"Perimeter thin ({axes}/4 axes). Downstream market work must wait."
    if axes >= 3 and untested <= 2:
        reliance = "READY" if published_as_context else "LIMITED"
        rationale = (
            f"{axes}/4 axes set; {untested} untested assumption(s). "
            "Published industry figures held as context unless perimeter matches."
        )
        return quality, reliance, rationale
    return (
        quality,
        "LIMITED",
        f"{axes}/4 axes; {untested} untested. Approve perimeter before sizing downstream markets.",
    )


def _llm_market_definition_spec(
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
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    try:
        system = compose_system(
            "market_definition",
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
    user = (
        f"Target company / deal name: {company}\n\n"
        f"Sources:\n{src_list}\n\n"
        f"Evidence:\n{corpus[:40_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "perimeter: {service, customer_types, geography, value_chain_stage, footprint_basis},\n"
        "double_count_streams: [{stream, risk, treatment}],\n"
        "exclusions: [{exclusion, kind, why}] — kind is strategic|capability|unclassified,\n"
        "addressable_market: {label, value, basis, formula, source},\n"
        "obtainable_market: {label, value, basis, formula, source},\n"
        "assumptions: [{assumption, statement}],\n"
        "published_figures: [{figure, published_perimeter, as_of_date, unit, "
        "matches_ours, use, source}],\n"
        "right_to_win_deferred: true,\n"
        "industry_context_note (string — broader industry figures are context, not the market),\n"
        "approval_gate: {status, blocks_downstream_market_agents, axes_evidenced, note},\n"
        "questions: [{question, required_records, decision_effect, priority, "
        "owner, timing, closure_test, interim_treatment}],\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Use operating footprint, not an industry label. "
        "If a published figure's perimeter does not match yours, it is context only. "
        "Right-to-win is deferred — do not score competitive advantage here. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _heuristic_market_definition_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    prior_spec: dict[str, Any] | None = None,
    legacy_spec: dict[str, Any] | None = None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    perimeter = _perimeter(corpus, prior_spec)
    streams = _double_count(corpus)
    exclusions = _exclusions(corpus)
    addressable, obtainable, assumptions = _markets(corpus)
    published = _published_figures(corpus)
    export = _perimeter_export(perimeter, as_of_date=as_of_date)
    consistency = _perimeter_consistency_qa(
        perimeter_export=export,
        published=published,
    )

    untested = sum(
        1
        for a in assumptions
        if str(a.get("statement", "")).startswith("Information") or a.get("statement") == _NA
    )
    axes = sum(
        1
        for k in ("service", "customer_types", "geography", "value_chain_stage")
        if perimeter.get(k)
        and not str(perimeter[k]).startswith("Information")
        and perimeter[k] != _NA
    )
    gate = _approval_gate(perimeter=perimeter, untested=untested)
    quality, reliance, qr = _quality_reliance(
        axes=axes,
        published_as_context=True,
        untested=untested,
    )
    if any(c.get("status") == "REWORK" for c in consistency):
        if reliance == "READY":
            reliance = "LIMITED"
        qr = (
            f"{qr} Published figure(s) lack confirmed perimeter/date/unit match — "
            "held as context only."
        )

    insight = (
        f"Market Definition for {company}: perimeter on service, customer type, "
        f"geography and value-chain stage from operating footprint ({axes}/4 axes evidenced). "
        f"Downstream market agents blocked until perimeter approved "
        f"(gate={gate['status']}). Right-to-win deferred. "
        f"Broader industry figures are context, not the market."
    )

    # Preserve legacy DD-02 fields for report consumers — but never keep polluted
    # growth-thesis / Foundation soft-fill clips that leaked into prior runs.
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    framing = _clean_framing_list(legacy.get("market_framing"), perimeter=perimeter)
    geo_perim = str(perimeter.get("geography") or "").strip()
    legacy_geos = legacy.get("geographies") if isinstance(legacy.get("geographies"), list) else []

    def _geo_tokens(text: str) -> set[str]:
        keys = (
            "philadelphia", "washington", "maryland", "virginia", "nova", "dmv",
            "metropolitan",
        )
        low = text.lower()
        return {k for k in keys if k in low}

    geos: list[str] = []
    perim_tokens = _geo_tokens(geo_perim) if geo_perim and not geo_perim.startswith("Information") else set()
    for g in legacy_geos:
        s = str(g or "").strip()
        if not s or s.startswith("Information") or _is_polluted_service(s):
            continue
        # Prefer the fuller perimeter footprint when legacy dropped metros (e.g. Philly)
        if perim_tokens and perim_tokens - _geo_tokens(s):
            continue
        if geo_perim and len(geo_perim) > len(s) + 10 and not _is_polluted_service(geo_perim):
            continue
        geos.append(_clean(s, 220))
    if not geos and geo_perim and not geo_perim.startswith("Information"):
        geos = [_clean(geo_perim, 220)]
    out: dict[str, Any] = {
        "insight_snapshot": insight,
        "perimeter": perimeter,
        "perimeter_export": export,
        "double_count_streams": streams,
        "exclusions": exclusions,
        "addressable_market": addressable,
        "obtainable_market": obtainable,
        "assumptions": assumptions,
        "published_figures": published,
        "perimeter_consistency_qa": consistency,
        "right_to_win_deferred": True,
        "industry_context_note": (
            "Broader industry figures are context, not the market. "
            "A published figure whose perimeter does not match ours cannot be used as the addressable market."
        ),
        "approval_gate": gate,
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": qr,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        # Legacy Macro Environment fields
        "document": "Market Definition",
        "dd_code": legacy.get("dd_code") or "DD-02",
        "market_framing": framing,
        "segments": legacy.get("segments") or [],
        "macro_drivers": legacy.get("macro_drivers") or [],
        "policy_context": legacy.get("policy_context") or [],
        "geographies": geos,
    }
    out["questions"] = _questions_from_md_gaps(out)
    return out


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    as_of_date: str | None = None,
) -> dict[str, Any]:
    if not isinstance(llm.get("perimeter"), dict):
        llm["perimeter"] = {
            "service": _info_request("service sold"),
            "customer_types": _info_request("customer types"),
            "geography": _info_request("geography"),
            "value_chain_stage": _info_request("value-chain stage"),
            "footprint_basis": "Use operating footprint, not an industry label.",
        }
    perim = llm["perimeter"]
    for axis in ("service", "customer_types", "geography", "value_chain_stage"):
        val = str(perim.get(axis) or "").strip()
        if val and _is_polluted_service(val):
            perim[axis] = _info_request(axis.replace("_", " "))
    llm["perimeter"] = perim
    # Prefer clean perimeter over polluted legacy / LLM market_framing clips
    framing_raw = llm.get("market_framing")
    if framing_raw is None and isinstance(legacy_spec, dict):
        framing_raw = legacy_spec.get("market_framing")
    llm["market_framing"] = _clean_framing_list(framing_raw, perimeter=perim)
    legacy_geos = []
    if isinstance(legacy_spec, dict) and isinstance(legacy_spec.get("geographies"), list):
        legacy_geos = legacy_spec["geographies"]
    geos_in = llm.get("geographies") if isinstance(llm.get("geographies"), list) else legacy_geos
    geos: list[str] = []
    geo_perim = str(perim.get("geography") or "").strip()
    for g in geos_in or []:
        s = str(g or "").strip()
        if not s or s.startswith("Information") or _is_polluted_service(s):
            continue
        if geo_perim and len(geo_perim) > len(s) + 20 and not _is_polluted_service(geo_perim):
            continue
        geos.append(_clean(s, 220))
    if not geos and geo_perim and not geo_perim.startswith("Information"):
        geos = [_clean(geo_perim, 220)]
    llm["geographies"] = geos
    for key in ("double_count_streams", "exclusions", "assumptions", "published_figures"):
        if not isinstance(llm.get(key), list):
            llm[key] = []
    for row in llm.get("published_figures") or []:
        if isinstance(row, dict):
            row.setdefault("as_of_date", _info_request("as-of date"))
            row.setdefault("unit", "currency (as stated in source)")
    for key in ("addressable_market", "obtainable_market"):
        if not isinstance(llm.get(key), dict):
            llm[key] = {
                "label": key.replace("_", " ").title(),
                "value": _info_request(key),
                "basis": _NA,
                "formula": _info_request(f"formula for {key}"),
                "source": _NA,
            }
        else:
            llm[key].setdefault("formula", _info_request(f"formula for {key}"))
    llm["perimeter_export"] = _perimeter_export(
        llm["perimeter"],
        as_of_date=as_of_date,
    )
    llm["perimeter_consistency_qa"] = _perimeter_consistency_qa(
        perimeter_export=llm["perimeter_export"],
        published=llm.get("published_figures") or [],
    )
    llm["right_to_win_deferred"] = True
    if not isinstance(llm.get("approval_gate"), dict):
        llm["approval_gate"] = _approval_gate(
            perimeter=llm["perimeter"],
            untested=len(llm.get("assumptions") or []),
        )
    else:
        gate = llm["approval_gate"]
        status = str(gate.get("status") or "").strip().lower().replace(" ", "_")
        # Model must never self-approve — only ready_for_approval / pending / blocked.
        if status in {"approved", "approve", "ok", "pass"}:
            status = "ready_for_approval"
        if status not in {"ready_for_approval", "pending_approval", "blocked", "approved"}:
            status = "pending_approval"
        gate["status"] = status
        gate["blocks_downstream_market_agents"] = True
        llm["approval_gate"] = gate
    # Explicit human/system flag only.
    if llm.get("perimeter_approved") is True:
        llm["approval_gate"]["status"] = "approved"
    else:
        llm["perimeter_approved"] = False
        if llm["approval_gate"].get("status") == "approved":
            llm["approval_gate"]["status"] = "ready_for_approval"
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    if qv not in {"PASS", "REWORK"}:
        llm["quality_verdict"] = "PASS"
    else:
        llm["quality_verdict"] = qv
    if rv not in {"READY", "LIMITED", "BLOCKED"}:
        llm["reliance_verdict"] = "LIMITED"
    else:
        llm["reliance_verdict"] = rv
    if any(
        isinstance(c, dict) and c.get("status") == "REWORK"
        for c in (llm.get("perimeter_consistency_qa") or [])
    ):
        if llm["reliance_verdict"] == "READY":
            llm["reliance_verdict"] = "LIMITED"

    if not llm.get("industry_context_note"):
        llm["industry_context_note"] = (
            "Broader industry figures are context, not the market."
        )

    if not llm.get("questions"):
        llm["questions"] = _questions_from_md_gaps(llm)
    else:
        from agetic_cdd_api.prompt_book import normalize_question

        filled_q: list[dict[str, str]] = []
        for raw in llm.get("questions") or []:
            q = normalize_question(raw)
            if q.get("question"):
                filled_q.append(q)
        llm["questions"] = filled_q or _questions_from_md_gaps(llm)

    for dead in ("recommendation", "confidence", "key_conditions"):
        llm.pop(dead, None)

    llm["primary_sources"] = sources[:16]
    llm["composer"] = "llm_v1"
    llm["document"] = "Market Definition"
    llm["dd_code"] = "DD-02"
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    llm.setdefault("market_framing", legacy.get("market_framing") or [])
    llm.setdefault("segments", legacy.get("segments") or [])
    llm.setdefault("macro_drivers", legacy.get("macro_drivers") or [])
    llm.setdefault("policy_context", legacy.get("policy_context") or [])
    llm.setdefault("geographies", legacy.get("geographies") or [])
    return llm


def build_market_definition_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    prior_spec: dict[str, Any] | None = None,
    legacy_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    if corpus is None:
        gathered_corpus, gathered_sources = gather_market_definition_corpus(deal, idx)
        corpus = gathered_corpus
        if not sources:
            sources = gathered_sources
    sources = list(sources or [])
    if not corpus:
        bits: list[str] = []
        for doc in idx.get("documents") or []:
            if not isinstance(doc, dict):
                continue
            ex = str(doc.get("excerpt") or "").strip()
            if ex:
                bits.append(ex)
                name = str(doc.get("filename") or "source")
                if name not in sources:
                    sources.append(name)
        corpus = "\n".join(bits)

    vars_ = prompt_vars_from_deal(deal)
    if not prefer_heuristic:
        llm = _llm_market_definition_spec(
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
        )
        if llm:
            out = _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                as_of_date=vars_.get("as_of_date"),
            )
            out["deal_slots"] = {k: v for k, v in vars_.items() if v}
            return out

    heur = _heuristic_market_definition_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        prior_spec=prior_spec,
        legacy_spec=legacy_spec,
        as_of_date=vars_.get("as_of_date"),
    )
    heur["deal_slots"] = {k: v for k, v in vars_.items() if v}
    return heur


def render_market_definition_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    perimeter = spec.get("perimeter") if isinstance(spec.get("perimeter"), dict) else {}
    export = (
        spec.get("perimeter_export")
        if isinstance(spec.get("perimeter_export"), dict)
        else {}
    )
    streams = spec.get("double_count_streams") if isinstance(spec.get("double_count_streams"), list) else []
    exclusions = spec.get("exclusions") if isinstance(spec.get("exclusions"), list) else []
    addressable = spec.get("addressable_market") if isinstance(spec.get("addressable_market"), dict) else {}
    obtainable = spec.get("obtainable_market") if isinstance(spec.get("obtainable_market"), dict) else {}
    assumptions = spec.get("assumptions") if isinstance(spec.get("assumptions"), list) else []
    published = spec.get("published_figures") if isinstance(spec.get("published_figures"), list) else []
    consistency = (
        spec.get("perimeter_consistency_qa")
        if isinstance(spec.get("perimeter_consistency_qa"), list)
        else []
    )
    questions = spec.get("questions") if isinstance(spec.get("questions"), list) else []
    gate = spec.get("approval_gate") if isinstance(spec.get("approval_gate"), dict) else {}
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Perimeter — Four Axes\n\n")
    parts.append(
        "Drawn from the company's **operating footprint**, not an industry label. "
        "Axes: service · customer type · geography · value-chain stage. "
        "Exported as the shared fact for Volume / Pricing / Share.\n\n"
    )
    parts.append(_table(
        ["Axis", "Definition"],
        [
            ["Service sold", _clean(perimeter.get("service"), 320)],
            ["Customer types served", _clean(perimeter.get("customer_types"), 320)],
            ["Geography actually reachable", _clean(perimeter.get("geography"), 320)],
            ["Value-chain stage occupied", _clean(perimeter.get("value_chain_stage"), 320)],
        ],
    ))
    if perimeter.get("footprint_basis"):
        parts.append(f"*{_clean(perimeter.get('footprint_basis'), 280)}*\n\n")
    if export:
        parts.append("### Perimeter export (downstream shared fact)\n\n")
        parts.append(_table(
            ["Field", "Value"],
            [
                ["As-of date", _clean(export.get("as_of_date"), 80)],
                ["Unit", _clean(export.get("unit"), 80)],
                ["Complete", str(bool(export.get("complete")))],
                ["Right-to-win", _clean(export.get("right_to_win") or "deferred", 40)],
                [
                    "Consumers",
                    ", ".join(str(x) for x in (export.get("export_for") or [])[:6]) or "—",
                ],
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 2. Revenue Streams — Avoid Double Count\n\n")
    parts.append(
        "Separate streams that would otherwise be counted twice "
        "(e.g. collection, processing, sale of the end product).\n\n"
    )
    if streams:
        parts.append(_table(
            ["Stream", "Double-count Risk", "Treatment"],
            [
                [
                    _clean(r.get("stream"), 120),
                    _clean(r.get("risk"), 120),
                    _clean(r.get("treatment"), 160),
                ]
                for r in streams if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('value-chain revenue streams')}\n\n")
    parts.append("---\n\n")

    parts.append("## 3. Exclusions — Strategy vs Capability\n\n")
    if exclusions:
        parts.append(_table(
            ["Exclusion", "Kind", "Why"],
            [
                [
                    _clean(r.get("exclusion"), 200),
                    _clean(r.get("kind"), 20),
                    _clean(r.get("why"), 160),
                ]
                for r in exclusions if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"{_info_request('strategic and capability exclusions')}\n\n")
    parts.append("---\n\n")

    parts.append("## 4. Addressable & Obtainable Market (TAM / SAM / SOM)\n\n")
    parts.append(
        "Sized from **this** perimeter. Name every assumption and formula: serviceable "
        "geography, regulation, route or delivery radius, capacity, realistic penetration. "
        "Right-to-win is **deferred** — not scored here.\n\n"
    )
    if spec.get("right_to_win_deferred", True):
        parts.append(
            "**Right-to-win:** deferred to Competitive Differentiation / Market Share Strategy.\n\n"
        )
    parts.append(_table(
        ["Market", "Value", "Basis", "Formula", "Source"],
        [
            [
                _clean(addressable.get("label") or "Addressable / SAM", 48),
                _clean(addressable.get("value"), 80),
                _clean(addressable.get("basis"), 120),
                _clean(addressable.get("formula"), 120),
                _clean(addressable.get("source"), 40),
            ],
            [
                _clean(obtainable.get("label") or "Obtainable / SOM", 48),
                _clean(obtainable.get("value"), 80),
                _clean(obtainable.get("basis"), 120),
                _clean(obtainable.get("formula"), 120),
                _clean(obtainable.get("source"), 40),
            ],
        ],
    ))
    if assumptions:
        parts.append("### Named Assumptions\n\n")
        parts.append(_table(
            ["Assumption", "Statement"],
            [
                [_clean(r.get("assumption"), 40), _clean(r.get("statement"), 200)]
                for r in assumptions if isinstance(r, dict)
            ],
        ))
    parts.append("---\n\n")

    parts.append("## 5. Published Figures — Match or Context Only\n\n")
    parts.append(
        "State each published figure's perimeter, as-of date and unit, and whether it "
        "matches ours. If it does not, it is **context only** and cannot be used as the "
        "addressable market. Downstream comparisons must use the same perimeter, date and unit.\n\n"
    )
    if published:
        parts.append(_table(
            ["Figure", "Published Perimeter", "As-of", "Unit", "Matches Ours?", "Use", "Source"],
            [
                [
                    _clean(r.get("figure"), 48),
                    _clean(r.get("published_perimeter"), 80),
                    _clean(r.get("as_of_date"), 40),
                    _clean(r.get("unit"), 40),
                    _clean(r.get("matches_ours"), 48),
                    _clean(r.get("use"), 100),
                    _clean(r.get("source"), 40),
                ]
                for r in published if isinstance(r, dict)
            ],
        ))
    if consistency:
        parts.append("### Perimeter / date / unit QA\n\n")
        parts.append(_table(
            ["Check", "Figure", "Status", "Note"],
            [
                [
                    _clean(r.get("check"), 40),
                    _clean(r.get("figure"), 48),
                    _clean(r.get("status"), 16),
                    _clean(r.get("note"), 160),
                ]
                for r in consistency if isinstance(r, dict)
            ],
        ))
    if spec.get("industry_context_note"):
        parts.append(f"**Note:** {_clean(spec.get('industry_context_note'), 320)}\n\n")
    parts.append("---\n\n")

    parts.append("## 6. Approval Gate\n\n")
    parts.append(
        f"**Status:** {_clean(gate.get('status') or 'pending_approval', 40)}\n\n"
        f"**Blocks downstream market agents:** "
        f"{'yes' if gate.get('blocks_downstream_market_agents', True) else 'no'}\n\n"
        f"**Axes evidenced:** {_clean(gate.get('axes_evidenced'), 10)}\n\n"
    )
    if gate.get("note"):
        parts.append(f"{_clean(gate.get('note'), 400)}\n\n")
    parts.append(
        "*Every other market agent stays blocked until this perimeter is approved. "
        "This section does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

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
        parts.append(f"{_info_request('Questions for material perimeter gaps')}\n\n")
    parts.append("---\n\n")

    parts.append("## 8. Quality & Reliance\n\n")
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can sizing and later market agents rest on this perimeter?\n\n"
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


def market_definition_approved(spec: dict[str, Any] | None) -> bool:
    """True when the perimeter gate allows downstream market agents to run."""
    if not isinstance(spec, dict):
        return False
    gate = spec.get("approval_gate") if isinstance(spec.get("approval_gate"), dict) else {}
    if gate.get("status") == "approved":
        return True
    # Explicit user/system approval flag
    if spec.get("perimeter_approved") is True:
        return True
    return False
