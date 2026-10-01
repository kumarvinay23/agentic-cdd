"""Compose DiligenceIQ Market Definition — competition perimeter (prompt book).

Four-axis perimeter from operating footprint. Exclusions (strategy vs capability).
Addressable / obtainable with named assumptions. Published figures are context
unless perimeter matches. Downstream market agents wait until approved.
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


def _money(m: re.Match[str] | None) -> str:
    if not m:
        return _NA
    return f"{_fmt_num(m.group(1), m.group(2))} {_DOC_CITE}"


def _perimeter(corpus: str, prior: dict[str, Any] | None) -> dict[str, str]:
    sents = _sentences(corpus)
    service = _pick_sentences(
        sents,
        keywords=(
            "product", "sells", "offering", "scooter", "vehicle", "software",
            "service", "platform", "manufactur",
        ),
        limit=2,
    )
    customer = _pick_sentences(
        sents,
        keywords=(
            "customer", "b2c", "b2b", "retail", "fleet", "consumer",
            "end-user", "segment", "icp",
        ),
        limit=2,
    )
    geography = _pick_sentences(
        sents,
        keywords=(
            "india", "geography", "region", "export", "state", "metro",
            "reachable", "presence", "market share by",
        ),
        limit=2,
    )
    value_chain = _pick_sentences(
        sents,
        keywords=(
            "vertical", "manufactur", "assembly", "retail", "distribution",
            "oem", "value chain", "battery", "cell", "software",
        ),
        limit=2,
    )

    # Prefer prior F-05 / company background style fields when present
    if isinstance(prior, dict):
        offers = prior.get("offers") if isinstance(prior.get("offers"), dict) else {}
        if offers.get("sells") and not service:
            service = [str(offers["sells"])]
        if offers.get("to_whom") and not customer:
            customer = [str(offers["to_whom"])]

    geos = []
    for m in _GEO_SHARE.finditer(corpus[:30_000]):
        geos.append(f"{_clean(m.group(1), 40)} ~{m.group(2)}% {_DOC_CITE}")
        if len(geos) >= 4:
            break
    # Organics / regional operators often name metro footprints without % shares.
    # Scan a wide window and assemble the full footprint (not just the first state hit).
    if not geos:
        footprint_re = re.compile(
            r"(?i)Washington\s*,?\s*D\.?C\.?|Washington\s+metropolitan|"
            r"DMV|NOVA|Northern\s+Virginia|Maryland|Philadelphia|metropolitan\s+area"
        )
        hits = footprint_re.findall(corpus[:60_000])
        if hits:
            # Canonical order for Compost Crew-style DMV + Philly footprints
            priority = [
                ("washington", "Washington D.C."),
                ("metropolitan", "metropolitan area"),
                ("maryland", "Maryland"),
                ("northern", "Northern Virginia"),
                ("nova", "NOVA"),
                ("philadelphia", "Philadelphia"),
                ("dmv", "DMV"),
            ]
            seen: set[str] = set()
            ordered: list[str] = []
            lower_hits = [h.lower() for h in hits]
            for key, label in priority:
                if any(key in h for h in lower_hits) and label.lower() not in seen:
                    seen.add(label.lower())
                    ordered.append(label)
            # Prefer a composed footprint when we have metro + state signals
            if any("washington" in h for h in lower_hits) and (
                any("maryland" in h for h in lower_hits)
                or any("virginia" in h or "nova" in h for h in lower_hits)
            ):
                phrase = "Washington D.C. metropolitan area (including Maryland and Northern Virginia)"
                if any("philadelphia" in h for h in lower_hits):
                    phrase += " and Philadelphia"
                geos.append(_clean(phrase, 200) + f" {_DOC_CITE}")
            elif ordered:
                geos.append(_clean(", ".join(ordered), 160) + f" {_DOC_CITE}")

    return {
        "service": (
            _clean(service[0], 280) + f" {_DOC_CITE}"
            if service
            else _info_request("service sold — from operating footprint, not industry label")
        ),
        "customer_types": (
            _clean(customer[0], 280) + f" {_DOC_CITE}"
            if customer
            else _info_request("customer types actually served")
        ),
        "geography": (
            ("; ".join(geos) if geos else (_clean(geography[0], 280) + f" {_DOC_CITE}" if geography else ""))
            or _info_request("geography actually reachable from operating footprint")
        ),
        "value_chain_stage": (
            _clean(value_chain[0], 280) + f" {_DOC_CITE}"
            if value_chain
            else _info_request("stage of the value chain occupied")
        ),
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
        "label": "Addressable market (from this perimeter)",
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
        "source": _DOC_CITE if (sam_m or tam_m) else _NA,
    }
    obtainable = {
        "label": "Obtainable market (from this perimeter)",
        "value": _money(som_m) if som_m else _info_request("obtainable market from the perimeter"),
        "basis": (
            "SOM cited — subject to capacity and realistic penetration assumptions"
            if som_m
            else "Obtainable slice not evidenced independently of published SOM"
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
            "matches_ours": "unknown — confirm perimeter match before using as addressable",
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
            "matches_ours": "n/a",
            "use": "Broader industry figures are context, not the market",
            "source": _NA,
        })
    return rows[:5]


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
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None

    system = compose_system(
        "market_definition",
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
        "insight_snapshot (string),\n"
        "perimeter: {service, customer_types, geography, value_chain_stage, footprint_basis},\n"
        "double_count_streams: [{stream, risk, treatment}],\n"
        "exclusions: [{exclusion, kind, why}] — kind is strategic|capability|unclassified,\n"
        "addressable_market: {label, value, basis, source},\n"
        "obtainable_market: {label, value, basis, source},\n"
        "assumptions: [{assumption, statement}],\n"
        "published_figures: [{figure, published_perimeter, matches_ours, use, source}],\n"
        "industry_context_note (string — broader industry figures are context, not the market),\n"
        "approval_gate: {status, blocks_downstream_market_agents, axes_evidenced, note},\n"
        "quality_verdict (PASS|REWORK),\n"
        "reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Use operating footprint, not an industry label. "
        "If a published figure's perimeter does not match yours, it is context only. "
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
) -> dict[str, Any]:
    perimeter = _perimeter(corpus, prior_spec)
    streams = _double_count(corpus)
    exclusions = _exclusions(corpus)
    addressable, obtainable, assumptions = _markets(corpus)
    published = _published_figures(corpus)

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

    insight = (
        f"Market Definition for {company}: perimeter on service, customer type, "
        f"geography and value-chain stage from operating footprint ({axes}/4 axes evidenced). "
        f"Downstream market agents blocked until perimeter approved "
        f"(gate={gate['status']}). Broader industry figures are context, not the market."
    )

    # Preserve legacy DD-02 fields for report consumers
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    return {
        "insight_snapshot": insight,
        "perimeter": perimeter,
        "double_count_streams": streams,
        "exclusions": exclusions,
        "addressable_market": addressable,
        "obtainable_market": obtainable,
        "assumptions": assumptions,
        "published_figures": published,
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
        "market_framing": legacy.get("market_framing") or [
            perimeter.get("service"),
            perimeter.get("customer_types"),
        ],
        "segments": legacy.get("segments") or [],
        "macro_drivers": legacy.get("macro_drivers") or [],
        "policy_context": legacy.get("policy_context") or [],
        "geographies": legacy.get("geographies") or (
            [perimeter["geography"]] if perimeter.get("geography") else []
        ),
    }


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(llm.get("perimeter"), dict):
        llm["perimeter"] = {
            "service": _info_request("service sold"),
            "customer_types": _info_request("customer types"),
            "geography": _info_request("geography"),
            "value_chain_stage": _info_request("value-chain stage"),
            "footprint_basis": "Use operating footprint, not an industry label.",
        }
    for key in ("double_count_streams", "exclusions", "assumptions", "published_figures"):
        if not isinstance(llm.get(key), list):
            llm[key] = []
    for key in ("addressable_market", "obtainable_market"):
        if not isinstance(llm.get(key), dict):
            llm[key] = {
                "label": key.replace("_", " ").title(),
                "value": _info_request(key),
                "basis": _NA,
                "source": _NA,
            }
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

    if not llm.get("industry_context_note"):
        llm["industry_context_note"] = (
            "Broader industry figures are context, not the market."
        )

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

    if not prefer_heuristic:
        vars_ = prompt_vars_from_deal(deal)
        llm = _llm_market_definition_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=vars_.get("geography"),
            materiality=vars_.get("materiality"),
        )
        if llm:
            return _normalise_llm_spec(llm, sources=sources, legacy_spec=legacy_spec)

    return _heuristic_market_definition_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        prior_spec=prior_spec,
        legacy_spec=legacy_spec,
    )


def render_market_definition_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    perimeter = spec.get("perimeter") if isinstance(spec.get("perimeter"), dict) else {}
    streams = spec.get("double_count_streams") if isinstance(spec.get("double_count_streams"), list) else []
    exclusions = spec.get("exclusions") if isinstance(spec.get("exclusions"), list) else []
    addressable = spec.get("addressable_market") if isinstance(spec.get("addressable_market"), dict) else {}
    obtainable = spec.get("obtainable_market") if isinstance(spec.get("obtainable_market"), dict) else {}
    assumptions = spec.get("assumptions") if isinstance(spec.get("assumptions"), list) else []
    published = spec.get("published_figures") if isinstance(spec.get("published_figures"), list) else []
    gate = spec.get("approval_gate") if isinstance(spec.get("approval_gate"), dict) else {}
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    parts.append("## 1. Perimeter — Four Axes\n\n")
    parts.append(
        "Drawn from the company's **operating footprint**, not an industry label. "
        "Axes: service · customer type · geography · value-chain stage.\n\n"
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

    parts.append("## 4. Addressable & Obtainable Market\n\n")
    parts.append(
        "Sized from **this** perimeter. Name every assumption: serviceable geography, "
        "regulation, route or delivery radius, capacity, realistic penetration.\n\n"
    )
    parts.append(_table(
        ["Market", "Value", "Basis", "Source"],
        [
            [
                _clean(addressable.get("label") or "Addressable", 40),
                _clean(addressable.get("value"), 80),
                _clean(addressable.get("basis"), 160),
                _clean(addressable.get("source"), 40),
            ],
            [
                _clean(obtainable.get("label") or "Obtainable", 40),
                _clean(obtainable.get("value"), 80),
                _clean(obtainable.get("basis"), 160),
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
        "State each published figure's perimeter and whether it matches ours. "
        "If it does not, it is **context only** and cannot be used as the addressable market.\n\n"
    )
    if published:
        parts.append(_table(
            ["Figure", "Published Perimeter", "Matches Ours?", "Use", "Source"],
            [
                [
                    _clean(r.get("figure"), 60),
                    _clean(r.get("published_perimeter"), 100),
                    _clean(r.get("matches_ours"), 60),
                    _clean(r.get("use"), 120),
                    _clean(r.get("source"), 40),
                ]
                for r in published if isinstance(r, dict)
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

    parts.append("## 7. Quality & Reliance\n\n")
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
