"""Compose DiligenceIQ Supply Chain Resilience — break tests & continuity (prompt book).

Tests what happens when something breaks (site, fleet, key input) and whether
capacity, contracts or plans can absorb it. Maps critical path with SPOFs;
capacity headroom vs plan; disruption history; continuity arrangements
(tested/untested); plausible downside or unbounded with why.

Reconciles every supplier fact with the supplier agent — two agents must not
report different terms for the same contract.

No invest/pass. No company allowlists. Preserves legacy MRR Waterfall Narrative
shape (logistics_metrics / localization_milestones / resilience_notes).
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

_COMPUTED = "(COMPUTED FACTS)"
_NA = "N/A (data room did not provide it)"
_SOURCES_MARKER = (
    "<!-- cdd:sources - maintained by the document copilot; [n] in the text resolves here -->"
)
_ZWSP = re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]+")
_PDF_BULLETS = re.compile(r"[■▪●◆□◦•‣\x7f]+")
_HEADER_LINE = re.compile(r"(?m)^\s*#{1,6}\s*\S+\s*$")

_DOCUMENT_TITLE = "MRR Waterfall Narrative"
_DD_CODE = "DD-14"

_SPOF_RULE = (
    "Every point with a single supplier, single site or single asset class "
    "is marked as a single point of failure."
)
_CAPACITY_RULE = (
    "Capacity and headroom are stated against current and planned volume; "
    "where the plan requires more capacity, say when it binds."
)
_HISTORY_RULE = (
    "Disruption history uses the company's own incidents — duration, "
    "revenue/cost impact, and how they were resolved."
)
_CONTINUITY_RULE = (
    "Continuity arrangements are recorded with whether each has actually "
    "been **used** or **tested** (or remains untested)."
)
_DOWNSIDE_RULE = (
    "Plausible downside is bounded with cost and duration, or stated as "
    "unbounded with why."
)
_RECONCILE_RULE = (
    "Every supplier fact is reconciled with the supplier agent — two agents "
    "must not report different terms for the same contract."
)

_STAGE_CUES = (
    "input", "raw material", "component", "cell", "battery", "assembly",
    "manufacturing", "plant", "factory", "warehouse", "logistics",
    "distribution", "service center", "delivery", "last mile",
)
_SPOF_CUE = re.compile(
    r"(?i)\b(single[- ]source|single[- ]site|sole[- ]source|single\s+plant|"
    r"one\s+facility|single\s+asset|SPOF|single\s+point\s+of\s+failure|"
    r"no\s+alternate|only\s+one|import(?:ed|s)?\s+(?:cells?|components?|core)|"
    r"concentration\s+risk|sole\s+supplier)\b"
)
_CAPACITY_CUE = re.compile(
    r"(?i)\b(capacity|utilization|headroom|throughput|units?\s+per\s+(?:day|month|year)|"
    r"gigafactory|binds?|bottleneck)\b"
)
_DISRUPT_CUE = re.compile(
    r"(?i)\b(disruption|outage|incident|halt|stockout|shortage|recall|"
    r"force\s+majeure|shutdown|downtime)\b"
)
_CONTINUITY_CUE = re.compile(
    r"(?i)\b(backup|spare\s+capacity|continuity|BCP|business\s+continuity|"
    r"dual[- ]source|contractual\s+priority|contingency|tested|untested|"
    r"never\s+tested|drill)\b"
)
_DIO_RE = re.compile(r"(?i)Days Inventory Outstanding\s*\(DIO\)\s+(\d+)\s+days")
_DPO_RE = re.compile(r"(?i)Days Payable Outstanding\s*\(DPO\)\s+(\d+)\s+days")
_LEAD_RE = re.compile(
    r"(?i)(?:order[- ]to[- ]delivery|lead\s+time)[^.%]{0,40}?(\d+(?:\.\d+)?)\s*days?"
)
_STOCKOUT_RE = re.compile(
    r"(?i)(?:parts?\s+)?stockout[^.%]{0,40}?(\d+(?:\.\d+)?)\s*%"
)
_UTIL_RE = re.compile(
    r"(?i)(?:capacity\s+)?utilization[^.%]{0,30}?(\d+(?:\.\d+)?)\s*%"
)
_CAPACITY_NUM_RE = re.compile(
    r"(?i)(?:monthly\s+)?(?:production\s+)?capacity[^.%]{0,40}?"
    r"([\d,]+(?:\.\d+)?)\s*(units?|vehicles?|packs?)?"
)
_LOCALIZATION_RE = re.compile(
    r"(?i)(localization|localis(?:e|ation)|import\s+(?:content|share)|"
    r"gigafactory\s+phase\s*[12]|FY20\d{2}.{0,40}(?:%|target))"
    r"[^.?]{0,120}"
)
_INVEST_LANG = re.compile(
    r"(?i)\b(?:we\s+recommend|recommend(?:s|ed|ation)?\s+(?:to\s+)?(?:invest|pass)|"
    r"invest(?:ment)?\s+recommendation|(?:strong(?:ly)?\s+)?(?:buy|sell|hold)\s+recommendation|"
    r"should\s+(?:invest|proceed|pass)|do\s+not\s+invest)\b"
)


def _info_request(label: str) -> str:
    return f"Information request: {label}"


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
    out = _INVEST_LANG.sub("resilience evidence only — no deal verdict expressed", raw)
    out = re.sub(
        r"(?i)(?:^|[\s—\-–:])(?:invest|pass)(?:\s+recommendation)?(?=[\s.,;:!?]|$)",
        " (no deal verdict) ",
        out,
    )
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


# ---------------------------------------------------------------------------
# corpus gather
# ---------------------------------------------------------------------------


def gather_supply_chain_resilience_corpus(
    deal: Deal,
    index: dict[str, Any],
) -> tuple[str, list[str]]:
    from agetic_cdd_api.services_library import load_library_document

    prefer = {
        "operations": 0,
        "financial": 1,
        "legal_esg": 2,
        "deal_strategy": 3,
        "customer": 4,
        "market_competition": 5,
    }
    needles = (
        "manufacturing", "supply", "operational", "logistics", "localization",
        "warehouse", "capacity", "disruption", "continuity", "gigafactory",
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
    for doc in ranked[:12]:
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
# supplier reconcile
# ---------------------------------------------------------------------------


def _supplier_vendor_index(supplier_spec: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index supplier-agent vendors by lowercased name for reconcile."""
    out: dict[str, dict[str, Any]] = {}
    if not isinstance(supplier_spec, dict):
        return out
    for row in supplier_spec.get("vendors") or []:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        out[str(row["name"]).lower()] = row
    # Also index contract terms
    for row in supplier_spec.get("contract_terms") or []:
        if not isinstance(row, dict) or not row.get("supplier"):
            continue
        key = str(row["supplier"]).lower()
        base = out.get(key) or {"name": row["supplier"]}
        base["supplier_contract"] = row
        out[key] = base
    return out


def _reconcile_supplier_facts(
    *,
    chain_nodes: list[dict[str, Any]],
    supplier_spec: dict[str, Any] | None,
    corpus: str,
) -> dict[str, Any]:
    """Ensure resilience does not contradict supplier agent on same contract/vendor."""
    idx = _supplier_vendor_index(supplier_spec)
    conflicts: list[str] = []
    aligned: list[str] = []
    if not idx:
        return {
            "supplier_agent_present": False,
            "aligned": [],
            "conflicts": [],
            "notes": (
                f"{_RECONCILE_RULE} Supplier agent output not available in this run — "
                f"supplier facts marked for reconcile on next cascade."
            ),
            "source": _NA,
        }

    text = _prose(corpus)
    for node in chain_nodes:
        name = str(node.get("supplier_or_asset") or "").strip()
        desc = str(node.get("description") or "")
        blob = f"{name} {desc} {node.get('stage') or ''}".strip()
        if not blob or blob.startswith("Information") or blob == _NA:
            continue
        # fuzzy match against supplier-agent vendors (name or description mention)
        hit = None
        for key, row in idx.items():
            vendor = str(row.get("name") or "").lower()
            if not vendor:
                continue
            needle = vendor[: max(3, min(6, len(vendor)))]
            if (
                needle in blob.lower()
                or name.lower()[:6] in key
                or key[:6] in name.lower()
            ):
                hit = row
                break
        if not hit:
            continue
        # Compare risk / alternate if resilience asserts SPOF
        if node.get("spof_type") == "single_supplier":
            alt = str(hit.get("alternate_available") or "").strip().lower()
            if alt in {"yes"}:
                conflicts.append(
                    f"{hit.get('name')}: resilience marks single-supplier SPOF but "
                    f"supplier agent has alternate_available={hit.get('alternate_available')}."
                )
            else:
                aligned.append(
                    f"{hit.get('name')}: SPOF/alternate status consistent with supplier agent."
                )
        elif str(node.get("spof") or "").lower() == "yes":
            aligned.append(
                f"{hit.get('name')}: named on critical path; supplier agent present."
            )
        # Contract terms — never invent conflicting terms
        sc = hit.get("supplier_contract") if isinstance(hit.get("supplier_contract"), dict) else {}
        if sc:
            for field in ("duration", "termination_rights", "change_of_control", "exclusivity"):
                res_claim = None
                # Look for conflicting numeric/term claims in node notes
                note = str(node.get("notes") or "")
                if field.replace("_", " ") in note.lower() and _is_filled(sc.get(field)):
                    # If supplier said unread / info request, resilience must not assert term
                    if str(sc.get("contract_read") or "").startswith("No") or str(sc.get(field) or "").startswith("Information"):
                        if re.search(r"(?i)\d+\s*-?\s*year|termination\s+for|exclusiv", note):
                            conflicts.append(
                                f"{hit.get('name')}: resilience asserted {field.replace('_', ' ')} "
                                f"but supplier agent has not read / evidenced that term."
                            )
                    else:
                        aligned.append(
                            f"{hit.get('name')}: {field.replace('_', ' ')} deferred to supplier agent."
                        )

    # Generic corpus check for vendor names with different risk
    for key, row in list(idx.items())[:8]:
        name = str(row.get("name") or "")
        if not name:
            continue
        risk = str(row.get("risk_level") or "")
        if risk and re.search(rf"(?i){re.escape(name)}.{{0,40}}(High|Medium|Low)", text):
            m = re.search(rf"(?i){re.escape(name)}.{{0,40}}(High|Medium|Low)", text)
            if m and m.group(1).lower() != risk.lower():
                conflicts.append(
                    f"{name}: resilience text risk {m.group(1)} ≠ supplier agent {risk}."
                )
            elif m:
                aligned.append(f"{name}: risk level aligned ({risk}).")

    return {
        "supplier_agent_present": True,
        "aligned": aligned[:8] or ["No overlapping supplier facts to compare yet."],
        "conflicts": conflicts[:8],
        "notes": (
            f"{_RECONCILE_RULE} "
            + (
                f"{len(conflicts)} conflict(s) flagged — prefer supplier agent contract terms."
                if conflicts else "No term conflicts detected against supplier agent."
            )
        ),
        "source": _DOC_CITE,
    }


# ---------------------------------------------------------------------------
# extractors
# ---------------------------------------------------------------------------


def _extract_named_asset(hit: str, *, spof_type: str) -> str:
    """Pull supplier / site / asset name from a SPOF sentence (skip cue words)."""
    skip = {
        "single", "sole", "only", "source", "site", "plant", "point", "failure",
        "asset", "class", "backup", "alternate", "qualified", "facility", "one",
        "supplier", "suppliers", "component", "components", "cell", "cells",
        "final", "assembly", "for", "the", "and", "with", "from", "no",
        "core", "imported", "import", "imports", "china", "korea", "taiwan",
        "india", "japan", "germany", "usa", "europe", "asia", "phase",
        "battery", "pack", "packs", "semiconductor", "semiconductors",
        "power", "electronics", "localization", "localisation", "lithium",
        "ion", "primarily", "currently", "concentration", "risk",
        "supply", "chain", "review", "management", "operational",
    }

    def _ok(cand: str) -> bool:
        token = re.sub(r"[^\w&'-]+", "", (cand or "").split()[0] if cand else "").lower()
        return bool(token) and token not in skip

    # Prefer "supplier X" / "from X" / "at X"
    for pat in (
        r"(?i)(?:supplier|vendor)\s+([A-Z][A-Za-z0-9&'.-]{1,}(?:\s+[A-Z][A-Za-z0-9&'.-]{1,}){0,3})",
        r"(?i)(?:plant|site|facility|factory)\s+(?:at\s+)?([A-Z][A-Za-z0-9&'.-]{2,}(?:\s+[A-Z][A-Za-z0-9&'.-]{1,}){0,2})",
    ):
        m = re.search(pat, hit or "")
        if m:
            cand = _clean(m.group(1), 60)
            if _ok(cand):
                return cand
    # Prefer ALL-CAPS acronyms (CATL, SDI)
    for m in re.finditer(r"\b([A-Z]{2,8})\b", hit or ""):
        tok = m.group(1)
        if tok.lower() not in skip and tok not in {"SPOF", "DIO", "DPO", "SLA", "BCP", "FY"}:
            return tok
    # Title-case tokens, skipping cue words / geographies
    for m in re.finditer(
        r"\b([A-Z][A-Za-z0-9&'.-]{2,}(?:\s+[A-Z][A-Za-z0-9&'.-]{1,}){0,3})\b",
        hit or "",
    ):
        cand = _clean(m.group(1), 60)
        if _ok(cand):
            return cand
    # Import / concentration without a named vendor → asset class, not geography
    if re.search(r"(?i)import|concentration|cell", hit or ""):
        return "imported cells / key inputs"
    if spof_type == "single_site":
        return _info_request("single site / plant name")
    if spof_type == "single_supplier":
        return _info_request("single supplier name")
    return _info_request("single asset name")


def _extract_critical_path(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    stages: list[dict[str, str]] = []
    # Prefer explicit chain language
    chain_sents = [
        s for s in _sentences(text)
        if any(c in s.lower() for c in _STAGE_CUES) or _SPOF_CUE.search(s)
    ]
    seen: set[str] = set()
    order_hints = [
        ("input / components", ("cell", "component", "raw", "import", "supplier")),
        ("manufacturing / assembly", ("plant", "factory", "assembly", "manufactur", "gigafactory")),
        ("inventory / logistics", ("warehouse", "inventory", "logistics", "DIO", "lead time")),
        ("distribution / delivery", ("distribution", "delivery", "service center", "last mile")),
    ]
    # Global SPOF sentences (may not share stage keywords)
    spof_sents = [s for s in _sentences(text) if _SPOF_CUE.search(s)]

    for label, keys in order_hints:
        local = next(
            (s for s in chain_sents if any(k in s.lower() for k in keys)),
            None,
        )
        # Prefer SPOF sentence that also mentions this stage's keys
        spof_local = next(
            (s for s in spof_sents if any(k in s.lower() for k in keys)),
            None,
        )
        if not spof_local and label.startswith("input") and spof_sents:
            # Default: supplier/source SPOFs attach to input stage
            if any(re.search(r"(?i)supplier|source|cell|component|import", s) for s in spof_sents):
                spof_local = next(
                    (s for s in spof_sents if re.search(r"(?i)supplier|source|cell|component|import", s)),
                    spof_sents[0],
                )
        spof = "No"
        spof_type = "none"
        spof_note = _NA
        supplier_or_asset = _NA
        hit = spof_local or (local if local and _SPOF_CUE.search(local) else None)
        if hit and _SPOF_CUE.search(hit):
            spof = "Yes"
            low = hit.lower()
            if "supplier" in low or ("source" in low and "single" in low) or "sole" in low:
                spof_type = "single_supplier"
            elif "import" in low or "concentration" in low:
                spof_type = "single_asset_class"
            elif "site" in low or "plant" in low or "facilit" in low:
                spof_type = "single_site"
            else:
                spof_type = "single_asset_class"
            spof_note = _clean(hit, 200)
            supplier_or_asset = _extract_named_asset(hit, spof_type=spof_type)
        elif local:
            spof_note = _clean(local, 160)
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        stages.append({
            "stage": label,
            "description": spof_note if spof_note != _NA else (
                _info_request(f"map stage '{label}' from input to delivered service")
            ),
            "spof": spof,
            "spof_type": spof_type,
            "supplier_or_asset": supplier_or_asset if supplier_or_asset != _NA else (
                _info_request(f"single supplier/site/asset at '{label}'") if spof == "Yes"
                else _NA
            ),
            "source": _DOC_CITE if local else _NA,
            "notes": _SPOF_RULE,
        })

    if not any(_is_filled(s.get("description")) for s in stages):
        stages = [{
            "stage": "end-to-end",
            "description": _info_request(
                "critical path from input to delivered service with SPOFs marked"
            ),
            "spof": "Unknown",
            "spof_type": "none",
            "supplier_or_asset": _NA,
            "source": _NA,
            "notes": _SPOF_RULE,
        }]
    return stages


def _apply_supplier_spofs(
    chain: list[dict[str, Any]],
    supplier_spec: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Mark input-stage SPOFs from supplier-agent vendors with no/partial alternate."""
    if not isinstance(supplier_spec, dict):
        return chain
    vendors = [
        v for v in (supplier_spec.get("vendors") or [])
        if isinstance(v, dict) and v.get("name")
    ]
    soleish = []
    for v in vendors:
        alt = str(v.get("alternate_available") or "").strip().lower()
        # Only true no-alternate vendors become supplier-agent SPOFs (partial ≠ sole).
        if alt in {"no", "none", "n"} or alt.startswith("no "):
            soleish.append(v)
    if not soleish:
        return chain

    out = [dict(n) for n in chain]
    # Prefer input stage; else prepend
    target_idx = next(
        (i for i, n in enumerate(out) if "input" in str(n.get("stage") or "").lower()),
        None,
    )
    primary = soleish[0]
    name = str(primary.get("name") or "Supplier")
    component = str(primary.get("component") or "key input")
    alt = primary.get("alternate_available") or "No"
    note = (
        f"{name} ({component}) — supplier agent alternate_available={alt}; "
        f"marked as single-supplier SPOF on the critical path."
    )
    if target_idx is None:
        out.insert(0, {
            "stage": "input / components",
            "description": note,
            "spof": "Yes",
            "spof_type": "single_supplier",
            "supplier_or_asset": name,
            "source": _DOC_CITE,
            "notes": _SPOF_RULE,
        })
    else:
        node = out[target_idx]
        if str(node.get("spof") or "").lower() != "yes":
            node["spof"] = "Yes"
            node["spof_type"] = "single_supplier"
            node["supplier_or_asset"] = name
            node["description"] = note
            node["source"] = _DOC_CITE
            node["notes"] = _SPOF_RULE
        elif not _is_filled(node.get("supplier_or_asset")) or str(node.get("supplier_or_asset")).startswith("Information"):
            node["supplier_or_asset"] = name
            if not _is_filled(node.get("description")) or str(node.get("description")).startswith("Information"):
                node["description"] = note
    # Additional high-risk sole vendors as notes on same stage
    if len(soleish) > 1 and out:
        extras = ", ".join(str(v.get("name")) for v in soleish[1:4])
        idx = target_idx if target_idx is not None else 0
        prev = str(out[idx].get("description") or "")
        if extras and extras not in prev:
            out[idx]["description"] = _clean(f"{prev} Also: {extras}.", 220)
    return out


def _extract_capacity_headroom(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    util_m = _UTIL_RE.search(text)
    cap_m = _CAPACITY_NUM_RE.search(text)
    sents = [
        s for s in _sentences(text)
        if _CAPACITY_CUE.search(s)
    ][:6]

    if util_m or cap_m or sents:
        util = f"{util_m.group(1)}%" if util_m else _NA
        capacity = (
            f"{cap_m.group(1)} {cap_m.group(2) or 'units'}" if cap_m else _NA
        )
        headroom = _NA
        if util_m:
            try:
                u = float(util_m.group(1))
                headroom = f"~{max(0.0, 100.0 - u):g}% implied unused" if u <= 100 else _NA
            except ValueError:
                headroom = _NA
        binds = _NA
        bind_sent = next(
            (s for s in sents if re.search(r"(?i)bind|plan|FY20|ramp|require", s)),
            None,
        )
        if bind_sent:
            binds = _clean(bind_sent, 200)
        else:
            binds = _info_request("when planned volume binds capacity")

        rows.append({
            "stage": "manufacturing / production",
            "current_capacity": capacity if capacity != _NA else (
                _clean(sents[0], 120) if sents else _info_request("current capacity")
            ),
            "utilization": util if util != _NA else _info_request("utilization"),
            "headroom": headroom if headroom != _NA else _info_request("headroom vs current volume"),
            "planned_volume": _info_request("planned volume at this stage"),
            "when_binds": binds,
            "source": _DOC_CITE,
            "notes": _CAPACITY_RULE,
        })
        # Logistics stage from DIO/lead
        dio = _DIO_RE.search(text)
        lead = _LEAD_RE.search(text)
        if dio or lead:
            rows.append({
                "stage": "inventory / logistics",
                "current_capacity": (
                    f"DIO {dio.group(1)} days" if dio else _NA
                ),
                "utilization": _NA,
                "headroom": (
                    f"Lead time {lead.group(1)} days" if lead else _info_request("logistics headroom")
                ),
                "planned_volume": _info_request("planned throughput vs logistics capacity"),
                "when_binds": _info_request("when logistics capacity binds under plan"),
                "source": _DOC_CITE,
                "notes": _CAPACITY_RULE,
            })
    if not rows:
        rows.append({
            "stage": "end-to-end",
            "current_capacity": _info_request("capacity at each stage"),
            "utilization": _NA,
            "headroom": _info_request("headroom vs current and planned volume"),
            "planned_volume": _info_request("planned volume"),
            "when_binds": _info_request("when the plan binds capacity"),
            "source": _NA,
            "notes": _CAPACITY_RULE,
        })
    return rows


def _extract_disruption_history(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    for s in _sentences(text):
        if not _DISRUPT_CUE.search(s):
            continue
        if len(s) < 30:
            continue
        duration = _NA
        dm = re.search(r"(?i)(\d+)\s*(days?|weeks?|months?)", s)
        if dm:
            duration = f"{dm.group(1)} {dm.group(2)}"
        impact = _NA
        im = re.search(
            r"(?i)(INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr)?|\d+(?:\.\d+)?\s*%\s+(?:revenue|cost|sales))",
            s,
        )
        if im:
            impact = _clean(im.group(0), 80)
        rows.append({
            "incident": _clean(s, 200),
            "duration": duration if duration != _NA else _info_request("incident duration"),
            "impact": impact if impact != _NA else _info_request("revenue or cost impact"),
            "resolution": (
                _clean(s, 160) if re.search(r"(?i)resolv|restor|recover|mitigat", s)
                else _info_request("how the incident was resolved")
            ),
            "source": _DOC_CITE,
            "notes": _HISTORY_RULE,
        })
        if len(rows) >= 5:
            break
    if not rows:
        rows.append({
            "incident": _info_request("company disruption incidents"),
            "duration": _NA,
            "impact": _NA,
            "resolution": _NA,
            "source": _NA,
            "notes": _HISTORY_RULE,
        })
    return rows


def _extract_continuity(corpus: str) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    for s in _sentences(text):
        if not _CONTINUITY_CUE.search(s):
            continue
        tested = "Untested / not evidenced"
        if re.search(r"(?i)\b(tested|drill|used\s+in|invoked|activated)\b", s):
            if re.search(r"(?i)\b(never|untested|not\s+tested)\b", s):
                tested = "Untested"
            else:
                tested = "Used or tested"
        elif re.search(r"(?i)\b(never|untested|not\s+tested)\b", s):
            tested = "Untested"
        kind = "other"
        low = s.lower()
        if "backup" in low or "dual" in low:
            kind = "backup_processor"
        elif "spare" in low:
            kind = "spare_capacity"
        elif "priority" in low or "contract" in low:
            kind = "contractual_priority"
        elif "bcp" in low or "continuity" in low:
            kind = "business_continuity_plan"
        rows.append({
            "arrangement": _clean(s, 200),
            "type": kind,
            "tested_or_used": tested,
            "source": _DOC_CITE,
            "notes": _CONTINUITY_RULE,
        })
        if len(rows) >= 6:
            break
    if not rows:
        rows.append({
            "arrangement": _info_request(
                "continuity arrangements (backup processors, spare capacity, contractual priority)"
            ),
            "type": "other",
            "tested_or_used": "Untested / not evidenced",
            "source": _NA,
            "notes": _CONTINUITY_RULE,
        })
    return rows


def _extract_downsides(
    *,
    chain: list[dict],
    capacity: list[dict],
    history: list[dict],
    corpus: str,
) -> list[dict[str, str]]:
    text = _prose(corpus)
    rows: list[dict[str, str]] = []
    # Material SPOFs
    for node in chain:
        if str(node.get("spof") or "").lower() != "yes":
            continue
        exposure = node.get("supplier_or_asset") or node.get("stage") or "exposure"
        # Look for bounded downside near this exposure
        local = next(
            (
                s for s in _sentences(text)
                if str(exposure).lower()[:5] in s.lower()
                and re.search(r"(?i)(\d+\s*days?|INR|halt|stop|cost|revenue)", s)
            ),
            None,
        )
        if local:
            cost = _NA
            cm = re.search(r"(?i)INR\s*[\d,]+(?:\.\d+)?\s*(?:Cr|cr)?|\d+(?:\.\d+)?%", local)
            if cm:
                cost = _clean(cm.group(0), 60)
            dur = _NA
            dm = re.search(r"(?i)(\d+)\s*(days?|weeks?|months?)", local)
            if dm:
                dur = f"{dm.group(1)} {dm.group(2)}"
            rows.append({
                "exposure": _clean(str(exposure), 80),
                "plausible_cost": cost if cost != _NA else _info_request(f"cost if {exposure} fails"),
                "duration": dur if dur != _NA else _info_request(f"duration if {exposure} fails"),
                "bounded": "Yes" if cost != _NA or dur != _NA else "No",
                "unbounded_reason": (
                    "" if (cost != _NA or dur != _NA)
                    else _info_request(f"why downside for {exposure} cannot yet be bounded")
                ),
                "source": _DOC_CITE,
                "notes": _DOWNSIDE_RULE,
            })
        else:
            rows.append({
                "exposure": _clean(str(exposure), 80),
                "plausible_cost": _info_request(f"cost if {exposure} fails"),
                "duration": _info_request(f"duration if {exposure} fails"),
                "bounded": "No",
                "unbounded_reason": (
                    "Material SPOF marked but packs do not bound cost/duration. "
                    f"{_DOWNSIDE_RULE}"
                ),
                "source": _NA,
                "notes": _DOWNSIDE_RULE,
            })
    # From disruption history impacts
    for h in history:
        if not isinstance(h, dict):
            continue
        if _is_filled(h.get("impact")) and not str(h.get("impact")).startswith("Information"):
            rows.append({
                "exposure": _clean(h.get("incident"), 80)[:80],
                "plausible_cost": _clean(h.get("impact"), 80),
                "duration": _clean(h.get("duration"), 40),
                "bounded": "Yes",
                "unbounded_reason": "",
                "source": _DOC_CITE,
                "notes": "From own disruption history.",
            })
        if len(rows) >= 6:
            break
    if not rows:
        rows.append({
            "exposure": _info_request("material operational exposures"),
            "plausible_cost": _NA,
            "duration": _NA,
            "bounded": "No",
            "unbounded_reason": _info_request("why downside cannot yet be bounded"),
            "source": _NA,
            "notes": _DOWNSIDE_RULE,
        })
    return rows[:6]


def _extract_logistics_metrics(corpus: str, legacy: dict[str, Any]) -> dict[str, float]:
    text = corpus or ""
    out: dict[str, float] = {}
    prior = legacy.get("logistics_metrics") if isinstance(legacy.get("logistics_metrics"), dict) else {}
    for key, rx in (
        ("dio_days", _DIO_RE),
        ("dpo_days", _DPO_RE),
        ("lead_time_days", _LEAD_RE),
    ):
        m = rx.search(text)
        if m:
            out[key] = float(m.group(1))
    sm = _STOCKOUT_RE.search(text)
    if sm:
        out["stockout_actual_pct"] = float(sm.group(1))
    um = _UTIL_RE.search(text)
    if um:
        out["utilization_pct"] = float(um.group(1))
    for k, v in prior.items():
        if k not in out and _num(v) is not None:
            out[k] = float(_num(v))  # type: ignore[arg-type]
    return out


def _extract_localization(corpus: str, legacy: dict[str, Any]) -> list[str]:
    text = _prose(corpus)
    out: list[str] = []
    for m in _LOCALIZATION_RE.finditer(text):
        out.append(_clean(m.group(0), 180))
        if len(out) >= 5:
            break
    for s in _pick_sentences(
        _sentences(text),
        keywords=("localization", "localise", "import content", "gigafactory", "domestic"),
        limit=4,
    ):
        line = _clean(s, 180)
        if line and line not in out:
            out.append(line)
    if not out:
        for m in (legacy.get("localization_milestones") or [])[:4]:
            if isinstance(m, str) and m.strip():
                out.append(_clean(m, 180))
    return out[:6]


def _quality_reliance(
    *,
    chain: list[dict],
    capacity: list[dict],
    history: list[dict],
    continuity: list[dict],
    downsides: list[dict],
    reconcile: dict,
) -> tuple[str, str, str]:
    spof_n = sum(1 for n in chain if str(n.get("spof") or "").lower() == "yes")
    cap_ok = sum(
        1 for r in capacity
        if _is_filled(r.get("current_capacity")) and not str(r.get("current_capacity")).startswith("Information")
    )
    hist_ok = sum(
        1 for r in history
        if _is_filled(r.get("incident")) and not str(r.get("incident")).startswith("Information")
    )
    cont_tested = sum(
        1 for r in continuity
        if "tested" in str(r.get("tested_or_used") or "").lower()
        and "untested" not in str(r.get("tested_or_used") or "").lower()
    )
    bound_n = sum(1 for r in downsides if str(r.get("bounded") or "").lower() == "yes")
    conflicts = len(reconcile.get("conflicts") or [])

    if (spof_n or cap_ok) and (hist_ok or cont_tested or bound_n):
        reliance = "READY" if bound_n and conflicts == 0 and cont_tested else "LIMITED"
        return (
            "PASS" if conflicts == 0 else "REWORK",
            reliance,
            f"Critical path with {spof_n} SPOF(s); capacity rows {cap_ok}; "
            f"history {hist_ok}; continuity tested {cont_tested}; bounded downsides {bound_n}. "
            f"Supplier reconcile conflicts: {conflicts}. {_RECONCILE_RULE}",
        )
    if spof_n or cap_ok or hist_ok:
        return (
            "PASS",
            "LIMITED",
            "Partial resilience evidence — continuity tests and/or downside bounds thin. "
            f"{_CONTINUITY_RULE} {_DOWNSIDE_RULE}",
        )
    return (
        "PASS",
        "BLOCKED",
        "No critical-path map, capacity headroom or disruption history was opened.",
    )


# ---------------------------------------------------------------------------
# heuristic / LLM / normalise / build / render
# ---------------------------------------------------------------------------


def _heuristic_supply_chain_resilience_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    geography: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    supplier_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del geography
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    extra = ""
    for note in (legacy.get("resilience_notes") or [])[:6]:
        if isinstance(note, str) and note.strip():
            extra += "\n" + note.strip()
    for m in (legacy.get("localization_milestones") or [])[:4]:
        if isinstance(m, str) and m.strip():
            extra += "\n" + m.strip()
    corpus_full = (corpus or "") + extra

    chain = _apply_supplier_spofs(
        _extract_critical_path(corpus_full),
        supplier_spec,
    )
    capacity = _extract_capacity_headroom(corpus_full)
    history = _extract_disruption_history(corpus_full)
    continuity = _extract_continuity(corpus_full)
    downsides = _extract_downsides(
        chain=chain, capacity=capacity, history=history, corpus=corpus_full,
    )
    reconcile = _reconcile_supplier_facts(
        chain_nodes=chain, supplier_spec=supplier_spec, corpus=corpus_full,
    )
    metrics = _extract_logistics_metrics(corpus_full, legacy)
    milestones = _extract_localization(corpus_full, legacy)

    notes: list[str] = [
        _SPOF_RULE,
        _CAPACITY_RULE,
        _HISTORY_RULE,
        _CONTINUITY_RULE,
        _DOWNSIDE_RULE,
        _RECONCILE_RULE,
    ]
    if reconcile.get("conflicts"):
        notes.append(
            f"Supplier reconcile: {len(reconcile['conflicts'])} conflict(s) — "
            f"prefer supplier agent contract terms."
        )
    for n in (legacy.get("resilience_notes") or [])[:3]:
        if isinstance(n, str) and n.strip():
            notes.append(_soften_invest(_clean(n, 240)))

    quality, reliance, rationale = _quality_reliance(
        chain=chain,
        capacity=capacity,
        history=history,
        continuity=continuity,
        downsides=downsides,
        reconcile=reconcile,
    )

    spof_n = sum(1 for n in chain if str(n.get("spof") or "").lower() == "yes")
    bits = [f"Supply Chain Resilience for {company}"]
    bits.append(f"{len(chain)} stage(s), {spof_n} SPOF(s)")
    bits.append(f"{len([h for h in history if _is_filled(h.get('incident')) and not str(h.get('incident')).startswith('Information')])} disruption record(s)")
    tested = sum(
        1 for c in continuity
        if "tested" in str(c.get("tested_or_used") or "").lower()
        and "untested" not in str(c.get("tested_or_used") or "").lower()
    )
    bits.append(f"{tested} continuity arrangement(s) used/tested")
    if metrics.get("dio_days") is not None:
        bits.append(f"DIO {metrics['dio_days']:g}d")

    return {
        "insight_snapshot": _soften_invest(". ".join(bits)),
        "critical_path": chain,
        "capacity_headroom": capacity,
        "disruption_history": history,
        "continuity_arrangements": continuity,
        "plausible_downsides": downsides,
        "supplier_reconcile": reconcile,
        # Legacy dual-write
        "logistics_metrics": metrics,
        "localization_milestones": milestones,
        "resilience_notes": notes[:8],
        "quality_verdict": quality,
        "reliance_verdict": reliance,
        "quality_reliance_rationale": rationale,
        "primary_sources": sources[:16],
        "composer": "heuristic_v1",
        "document": legacy.get("document") or _DOCUMENT_TITLE,
        "dd_code": legacy.get("dd_code") or _DD_CODE,
        "empty": (
            not any(str(n.get("spof") or "").lower() == "yes" for n in chain)
            and not metrics
            and not milestones
        ),
    }


def _llm_supply_chain_resilience_spec(
    *,
    company: str,
    corpus: str,
    sources: list[str],
    sector: str | None = None,
    geography: str | None = None,
    materiality: str | None = None,
    supplier_spec: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    from agetic_cdd_api.prompt_book import compose_system
    from agetic_cdd_api.services_gemini import gemini_configured, generate_json

    if not gemini_configured() or not corpus.strip():
        return None
    try:
        system = compose_system(
            "supply_chain_resilience",
            sector=sector,
            geography=geography,
            materiality=materiality,
        )
    except KeyError:
        return None

    src_list = "\n".join(f"[{i}] {name}" for i, name in enumerate(sources[:12], start=1))
    supplier_blob = ""
    if isinstance(supplier_spec, dict) and supplier_spec.get("vendors"):
        supplier_blob = (
            "\nSUPPLIER_AGENT_SPEC (reconcile — do not contradict contract terms):\n"
            + str({
                "vendors": (supplier_spec.get("vendors") or [])[:8],
                "contract_terms": (supplier_spec.get("contract_terms") or [])[:4],
            })[:4_000]
            + "\n"
        )
    user = (
        f"Target company / deal name: {company}\n"
        f"Geography focus: {geography or 'as evidenced in the data room'}\n\n"
        f"Sources:\n{src_list}\n"
        f"{supplier_blob}\n"
        f"Evidence:\n{corpus[:38_000]}\n\n"
        "Return JSON with keys:\n"
        "insight_snapshot (string),\n"
        "critical_path: [{stage, description, spof, spof_type, supplier_or_asset, source, notes}],\n"
        "capacity_headroom: [{stage, current_capacity, utilization, headroom, planned_volume, "
        "when_binds, source, notes}],\n"
        "disruption_history: [{incident, duration, impact, resolution, source, notes}],\n"
        "continuity_arrangements: [{arrangement, type, tested_or_used, source, notes}],\n"
        "plausible_downsides: [{exposure, plausible_cost, duration, bounded, unbounded_reason, "
        "source, notes}],\n"
        "supplier_reconcile: {supplier_agent_present, aligned: [string], conflicts: [string], "
        "notes, source},\n"
        "logistics_metrics: {dio_days?, dpo_days?, lead_time_days?, stockout_actual_pct?, "
        "utilization_pct?},\n"
        "localization_milestones: [string], resilience_notes: [string],\n"
        "quality_verdict (PASS|REWORK), reliance_verdict (READY|LIMITED|BLOCKED),\n"
        "quality_reliance_rationale (string)\n"
        "Do NOT contradict supplier-agent contract terms for the same supplier. "
        "Mark SPOFs. Say tested vs untested for continuity. "
        "Bound downside or say why unbounded. "
        "Do NOT include recommendation, confidence, or investment verdict fields.\n"
    )
    parsed = generate_json(system=system, user=user, temperature=0.15)
    return parsed if isinstance(parsed, dict) else None


def _normalise_llm_spec(
    llm: dict[str, Any],
    *,
    sources: list[str],
    legacy_spec: dict[str, Any] | None,
    corpus: str = "",
    supplier_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = legacy_spec if isinstance(legacy_spec, dict) else {}
    heur = _heuristic_supply_chain_resilience_spec(
        company="Target",
        corpus=corpus,
        sources=sources,
        legacy_spec=legacy,
        supplier_spec=supplier_spec,
    )

    def _rows(key: str, required: str) -> list[dict[str, Any]]:
        raw = llm.get(key) if isinstance(llm.get(key), list) else []
        cleaned = [r for r in raw if isinstance(r, dict) and r.get(required)]
        return cleaned or heur.get(key) or []

    llm["critical_path"] = _apply_supplier_spofs(
        _rows("critical_path", "stage"),
        supplier_spec,
    )
    llm["capacity_headroom"] = _rows("capacity_headroom", "stage")
    llm["disruption_history"] = _rows("disruption_history", "incident")
    continuity = _rows("continuity_arrangements", "arrangement")
    for row in continuity:
        status = str(row.get("tested_or_used") or "")
        if not status:
            row["tested_or_used"] = "Untested / not evidenced"
        row["notes"] = _CONTINUITY_RULE
    llm["continuity_arrangements"] = continuity

    downsides = _rows("plausible_downsides", "exposure")
    for row in downsides:
        bounded = str(row.get("bounded") or "").lower()
        if bounded not in {"yes", "no"}:
            has_cost = _is_filled(row.get("plausible_cost")) and not str(row.get("plausible_cost")).startswith("Information")
            has_dur = _is_filled(row.get("duration")) and not str(row.get("duration")).startswith("Information")
            row["bounded"] = "Yes" if (has_cost or has_dur) else "No"
        if str(row.get("bounded")).lower() == "no" and not _is_filled(row.get("unbounded_reason")):
            row["unbounded_reason"] = _info_request("why downside cannot yet be bounded")
        row["notes"] = _DOWNSIDE_RULE
    llm["plausible_downsides"] = downsides

    # Force supplier reconcile from authoritative heuristic merge
    reconcile = _reconcile_supplier_facts(
        chain_nodes=llm["critical_path"],
        supplier_spec=supplier_spec,
        corpus=corpus,
    )
    llm_rec = llm.get("supplier_reconcile") if isinstance(llm.get("supplier_reconcile"), dict) else {}
    if llm_rec.get("conflicts"):
        for c in llm_rec["conflicts"]:
            if isinstance(c, str) and c not in reconcile["conflicts"]:
                reconcile["conflicts"].append(c)
    llm["supplier_reconcile"] = reconcile

    metrics_llm = llm.get("logistics_metrics") if isinstance(llm.get("logistics_metrics"), dict) else {}
    metrics = dict(heur.get("logistics_metrics") or {})
    for k, v in metrics_llm.items():
        n = _num(v)
        if n is not None:
            metrics[k] = n
    llm["logistics_metrics"] = metrics

    milestones = llm.get("localization_milestones") if isinstance(llm.get("localization_milestones"), list) else []
    milestones = [_clean(m, 180) for m in milestones if isinstance(m, str) and m.strip()]
    if not milestones:
        milestones = heur["localization_milestones"]
    llm["localization_milestones"] = milestones[:6]

    notes = llm.get("resilience_notes") if isinstance(llm.get("resilience_notes"), list) else []
    notes = [_soften_invest(_clean(n, 240)) for n in notes if isinstance(n, str) and n.strip()]
    for rule in (
        _SPOF_RULE, _CAPACITY_RULE, _HISTORY_RULE, _CONTINUITY_RULE,
        _DOWNSIDE_RULE, _RECONCILE_RULE,
    ):
        if not any(rule[:28].lower() in x.lower() for x in notes):
            notes.append(rule)
    if not notes:
        notes = heur["resilience_notes"]
    llm["resilience_notes"] = notes[:8]

    quality, reliance, rationale = _quality_reliance(
        chain=llm["critical_path"],
        capacity=llm["capacity_headroom"],
        history=llm["disruption_history"],
        continuity=continuity,
        downsides=downsides,
        reconcile=reconcile,
    )
    qv = str(llm.get("quality_verdict") or "").upper()
    rv = str(llm.get("reliance_verdict") or "").upper()
    # Conflicts force REWORK
    if reconcile.get("conflicts"):
        llm["quality_verdict"] = "REWORK"
    else:
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
    llm["empty"] = not llm["critical_path"] and not metrics
    return llm


def build_supply_chain_resilience_spec(
    deal: Deal,
    *,
    index: dict[str, Any] | None = None,
    company: str | None = None,
    legacy_spec: dict[str, Any] | None = None,
    supplier_spec: dict[str, Any] | None = None,
    corpus: str | None = None,
    sources: list[str] | None = None,
    prefer_heuristic: bool = False,
) -> dict[str, Any]:
    from agetic_cdd_api.prompt_book import prompt_vars_from_deal
    from agetic_cdd_api.services_library import load_library_index

    idx = index if isinstance(index, dict) else load_library_index(deal)
    target = (company or deal.company or deal.name or "Target").strip()
    vars_ = prompt_vars_from_deal(deal)
    geography = vars_.get("geography")

    if corpus is None:
        gathered_corpus, gathered_sources = gather_supply_chain_resilience_corpus(deal, idx)
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
        llm = _llm_supply_chain_resilience_spec(
            company=target,
            corpus=corpus,
            sources=sources,
            sector=vars_.get("sector"),
            geography=geography,
            materiality=vars_.get("materiality"),
            supplier_spec=supplier_spec,
        )
        if llm:
            return _normalise_llm_spec(
                llm,
                sources=sources,
                legacy_spec=legacy_spec,
                corpus=corpus,
                supplier_spec=supplier_spec,
            )

    return _heuristic_supply_chain_resilience_spec(
        company=target,
        corpus=corpus,
        sources=sources,
        geography=geography,
        legacy_spec=legacy_spec,
        supplier_spec=supplier_spec,
    )


def render_supply_chain_resilience_markdown(
    title: str,
    spec: dict[str, Any],
    *,
    sources: list[str] | None = None,
) -> str:
    chain = spec.get("critical_path") if isinstance(spec.get("critical_path"), list) else []
    capacity = spec.get("capacity_headroom") if isinstance(spec.get("capacity_headroom"), list) else []
    history = spec.get("disruption_history") if isinstance(spec.get("disruption_history"), list) else []
    continuity = (
        spec.get("continuity_arrangements")
        if isinstance(spec.get("continuity_arrangements"), list) else []
    )
    downsides = (
        spec.get("plausible_downsides")
        if isinstance(spec.get("plausible_downsides"), list) else []
    )
    reconcile = (
        spec.get("supplier_reconcile")
        if isinstance(spec.get("supplier_reconcile"), dict) else {}
    )
    metrics = (
        spec.get("logistics_metrics")
        if isinstance(spec.get("logistics_metrics"), dict) else {}
    )
    milestones = (
        spec.get("localization_milestones")
        if isinstance(spec.get("localization_milestones"), list) else []
    )
    notes = spec.get("resilience_notes") if isinstance(spec.get("resilience_notes"), list) else []
    srcs = sources or spec.get("primary_sources") or []

    parts: list[str] = [f"# {title}\n\n", _insight(spec.get("insight_snapshot"))]

    # 1
    parts.append("## 1. Critical Path & Single Points of Failure\n\n")
    parts.append(
        f"Chain from input to delivered service. {_SPOF_RULE}\n\n"
    )
    if chain:
        parts.append(_table(
            ["Stage", "Description", "SPOF?", "SPOF type", "Supplier / site / asset", "Source"],
            [
                [
                    _clean(r.get("stage"), 40),
                    _clean(r.get("description"), 140),
                    _clean(r.get("spof"), 20),
                    _clean(r.get("spof_type"), 30),
                    _clean(r.get("supplier_or_asset"), 60),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in chain if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('critical path map with SPOFs')}**\n\n")
    parts.append("---\n\n")

    # 2
    parts.append("## 2. Capacity & Headroom\n\n")
    parts.append(f"{_CAPACITY_RULE}\n\n")
    if capacity:
        parts.append(_table(
            ["Stage", "Current capacity", "Utilization", "Headroom", "Planned volume",
             "When binds", "Source"],
            [
                [
                    _clean(r.get("stage"), 40),
                    _clean(r.get("current_capacity"), 80),
                    _clean(r.get("utilization"), 40),
                    _clean(r.get("headroom"), 80),
                    _clean(r.get("planned_volume"), 80),
                    _clean(r.get("when_binds"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in capacity if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('capacity and headroom by stage')}**\n\n")
    if metrics:
        bits = [f"{k}: {v:g}" for k, v in list(metrics.items())[:6] if v is not None]
        if bits:
            parts.append("**Logistics metrics:** " + " · ".join(bits) + f" {_COMPUTED}\n\n")
    parts.append("---\n\n")

    # 3
    parts.append("## 3. Disruption History\n\n")
    parts.append(f"{_HISTORY_RULE}\n\n")
    if history:
        parts.append(_table(
            ["Incident", "Duration", "Impact", "Resolution", "Source"],
            [
                [
                    _clean(r.get("incident"), 140),
                    _clean(r.get("duration"), 40),
                    _clean(r.get("impact"), 60),
                    _clean(r.get("resolution"), 100),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in history if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('company disruption history')}**\n\n")
    parts.append("---\n\n")

    # 4
    parts.append("## 4. Continuity Arrangements (Used / Tested)\n\n")
    parts.append(f"{_CONTINUITY_RULE}\n\n")
    if continuity:
        parts.append(_table(
            ["Arrangement", "Type", "Used or tested?", "Source"],
            [
                [
                    _clean(r.get("arrangement"), 160),
                    _clean(r.get("type"), 40),
                    _clean(r.get("tested_or_used"), 40),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in continuity if isinstance(r, dict)
            ],
        ))
    else:
        parts.append(f"**{_info_request('continuity arrangements and test status')}**\n\n")
    if milestones:
        parts.append("### Localization / resilience milestones\n\n")
        for m in milestones[:5]:
            if isinstance(m, str):
                parts.append(f"- {_clean(m, 200)}\n")
        parts.append("\n")
    parts.append("---\n\n")

    # 5
    parts.append("## 5. Plausible Downside & Supplier Reconcile\n\n")
    parts.append(f"{_DOWNSIDE_RULE}\n\n")
    if downsides:
        parts.append(_table(
            ["Exposure", "Plausible cost", "Duration", "Bounded?", "If unbounded — why", "Source"],
            [
                [
                    _clean(r.get("exposure"), 80),
                    _clean(r.get("plausible_cost"), 60),
                    _clean(r.get("duration"), 40),
                    _clean(r.get("bounded"), 20),
                    _clean(r.get("unbounded_reason"), 120),
                    _clean(r.get("source") or _NA, 40),
                ]
                for r in downsides if isinstance(r, dict)
            ],
        ))
    parts.append(f"### Supplier-agent reconcile\n\n{_RECONCILE_RULE}\n\n")
    parts.append(_table(
        ["Item", "Statement"],
        [
            [
                "Supplier agent present",
                "Yes" if reconcile.get("supplier_agent_present") else "No",
            ],
            [
                "Aligned",
                "; ".join(
                    _clean(a, 120) for a in (reconcile.get("aligned") or [])[:4]
                    if isinstance(a, str)
                ) or "—",
            ],
            [
                "Conflicts",
                "; ".join(
                    _clean(c, 120) for c in (reconcile.get("conflicts") or [])[:4]
                    if isinstance(c, str)
                ) or "None",
            ],
            ["Notes", _clean(reconcile.get("notes"), 280)],
        ],
    ))
    parts.append(
        "*This section does not recommend invest or pass. Continuity arrangements state "
        "used/tested status. Supplier contract terms defer to the supplier agent on conflict.*\n\n"
    )
    parts.append("---\n\n")

    # 6
    parts.append("## 6. Quality & Reliance\n\n")
    parts.append(_table(
        ["Metric", "Verdict / Explanation"],
        [
            ["Quality Verdict", _clean(spec.get("quality_verdict") or "PASS", 30)],
            ["Reliance Verdict", _clean(spec.get("reliance_verdict") or "LIMITED", 30)],
            [
                "Rationale",
                _clean(
                    spec.get("quality_reliance_rationale")
                    or "Limits stated in the sections above.",
                    360,
                ),
            ],
        ],
    ))
    parts.append(
        f"**Quality:** {_clean(spec.get('quality_verdict') or 'PASS', 20)} — "
        f"is the work accurate and honest about limits?\n\n"
    )
    parts.append(
        f"**Reliance:** {_clean(spec.get('reliance_verdict') or 'LIMITED', 20)} — "
        f"can diligence rest on these resilience tests?\n\n"
    )
    if notes:
        parts.append("### Resilience notes\n\n")
        for n in notes[:6]:
            if isinstance(n, str) and n.strip():
                parts.append(f"- {_clean(n, 240)}\n")
        parts.append("\n")
    parts.append(
        "*This document tests what happens when something breaks and whether capacity, "
        "contracts or plans can absorb it. It does not recommend invest or pass.*\n\n"
    )
    parts.append("---\n\n")

    parts.append("## Sources\n\n")
    parts.append(f"{_SOURCES_MARKER}\n\n")
    if srcs:
        for i, name in enumerate(srcs[:16], start=1):
            parts.append(f"[{i}] {_clean(name, 120)}\n")
        parts.append("\n")
    else:
        parts.append(f"{_NA}\n\n")

    return "".join(parts)
