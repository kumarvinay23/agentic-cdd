"""Independent checks and verified citations.

A verifier recomputes each published figure from the fact store, applies
the ontology rules, and compares a claim with its source passage. Three
gates decide the outcome: the run is complete, the analysis is valid, and
the output is publishable. PASS, CLOSED, and READY stay unpublished
without a specific source.

Text blocks and claims keep permanent ids. Citation numbers are assigned
only after assembly, and each one must name the page, slide, sheet, or
cell it quotes. A pointer is not a citation. Reordering the source list
does not change which passage a citation names.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

_POINTER = re.compile(r"(?i)\b(ibid\.?|see above|op\. cit\.?|as above)\b|^(?:\[?\d+\]?|source\s+\d+)$")
_LOCATOR_FIELDS = ("page", "slide", "cell", "sheet")


def permanent_id(kind: str, *parts: object) -> str:
    """An id that stays put when the surrounding list is reordered."""
    material = "|".join(str(part) for part in parts)
    digest = hashlib.sha256(material.encode()).hexdigest()[:12]
    return f"{kind}-{digest}"


def number_citations(blocks: list[dict[str, Any]], sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Number citations after the blocks are assembled. Identity is the locator."""
    catalog = _catalog(sources)
    numbered: list[dict[str, Any]] = []
    number = 1
    for block in blocks:
        for cite in block.get("citations") or []:
            gap = _citation_fault(cite, catalog)
            if gap:
                raise ValueError(gap)
            locator = _locator(cite)
            source_id = str(cite.get("source_id") or "")
            source = catalog[(source_id, locator)]
            numbered.append(
                {
                    "citation_id": permanent_id("cite", source_id, locator),
                    "number": number,
                    "source_id": source_id,
                    "locator": locator,
                    "block_id": block.get("block_id"),
                    "passage": str(source.get("text") or ""),
                }
            )
            number += 1
    return numbered


def verify(output: dict[str, Any]) -> dict[str, Any]:
    """Run the three gates. A failing gate is named in errors."""
    errors: list[str] = []
    run_gap = _run_gap(output)
    analysis_gap = _analysis_gap(output)
    publish_gap = _publish_gap(output)
    if run_gap:
        errors.append(run_gap)
    if analysis_gap:
        errors.append(analysis_gap)
    if publish_gap:
        errors.append(publish_gap)
    return {
        "run_complete": run_gap is None,
        "analysis_valid": analysis_gap is None,
        "output_publishable": publish_gap is None,
        "errors": errors,
    }


def ensure_verification(agent_key: str, output: dict[str, Any]) -> str | None:
    """Stamp permanent ids, number citations, and hold a failed gate."""
    _stamp_ids(agent_key, output)
    assembled = _assemble(output)
    report = verify(output)
    if assembled and assembled not in report["errors"]:
        report["errors"].insert(0, assembled)
        report["output_publishable"] = False
    output["verification"] = {
        "run_complete": report["run_complete"],
        "analysis_valid": report["analysis_valid"],
        "output_publishable": report["output_publishable"],
    }
    if report["errors"]:
        return report["errors"][0]
    return None


def _stamp_ids(agent_key: str, output: dict[str, Any]) -> None:
    blocks = output.get("blocks")
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("text") and not block.get("block_id"):
                block["block_id"] = permanent_id("blk", agent_key, str(block.get("text")))
    ledger = output.get("claims_ledger")
    claims = ledger.get("claims") if isinstance(ledger, dict) else None
    for claim in claims or []:
        if isinstance(claim, dict) and not claim.get("claim_id"):
            claim["claim_id"] = permanent_id("claim", agent_key, str(claim.get("claim_as_stated") or ""))


def _assemble(output: dict[str, Any]) -> str | None:
    blocks = output.get("blocks")
    if not isinstance(blocks, list):
        return None
    if not any(isinstance(block, dict) and block.get("citations") for block in blocks):
        return None
    try:
        output["citations"] = number_citations(blocks, list(output.get("sources_index") or []))
    except ValueError as exc:
        return str(exc)
    return None


def _run_gap(output: dict[str, Any]) -> str | None:
    result = output.get("result")
    if not isinstance(result, dict):
        return None
    store = result.get("fact_store") or {}
    for bucket in ("numbers", "counts"):
        values = result.get(bucket) or {}
        if not isinstance(values, dict):
            continue
        for fact_id in values.values():
            if isinstance(fact_id, str) and fact_id not in store:
                return f"fact {fact_id} is not in the fact store"
    return None


def _analysis_gap(output: dict[str, Any]) -> str | None:
    for calc in _calculations(output):
        gap = _recompute_gap(calc)
        if gap:
            return gap
    return _claim_gap(output)


def _publish_gap(output: dict[str, Any]) -> str | None:
    unproven = _unproven_verdict(output)
    if unproven:
        return unproven
    blocks = output.get("blocks")
    if not isinstance(blocks, list):
        return None
    if not any(isinstance(block, dict) and block.get("citations") for block in blocks):
        return None
    try:
        number_citations(blocks, list(output.get("sources_index") or []))
    except ValueError as exc:
        return str(exc)
    return None


def _calculations(output: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [item for item in (output.get("calculations") or []) if isinstance(item, dict)]
    result = output.get("result")
    store = result.get("fact_store") if isinstance(result, dict) else None
    if isinstance(store, dict):
        for fact in store.values():
            if isinstance(fact, dict) and fact.get("calc_id") and fact.get("inputs") and "rounding" in fact:
                rows.append(fact)
    return rows


def _recompute_gap(calc: dict[str, Any]) -> str | None:
    if "rounding" not in calc or not calc.get("calc_id"):
        return None
    from agetic_cdd_api.services_fact_repository import get_fact

    if calc.get("fact_id"):
        stored = get_fact(str(calc["fact_id"]))
        if stored and stored.get("value") is not None and stored.get("value") != calc.get("value"):
            return f"{calc['calc_id']} does not match the fact store"
    from agetic_cdd_api.services_calculation_library import ask_calculation, recompute

    again = recompute(calc)
    if not again["match"]:
        return f"{calc['calc_id']} does not match the fact store"
    fresh = ask_calculation(
        str(calc["calc_id"]),
        inputs=dict(calc.get("inputs") or {}),
        sources=list(calc.get("sources") or []),
        scale="percent" if calc.get("scale") == "percent" else "ratio",
        rounding=int(calc["rounding"]),
    )
    failed = [str(check["id"]) for check in fresh.get("checks") or [] if not check.get("passed")]
    if failed:
        return f"{failed[0]} failed"
    return None


def _claim_gap(output: dict[str, Any]) -> str | None:
    ledger = output.get("claims_ledger")
    rows = ledger.get("claims") if isinstance(ledger, dict) else None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status in {"unknown", "management_claim"}:
            continue
        if status in {"known", "tested"} and row.get("source_wording") and not row.get("wording_match"):
            return "claim does not match its source passage"
    return None


def _unproven_verdict(output: dict[str, Any]) -> str | None:
    from agetic_cdd_api.agent_module_registry import withhold_unsourced_verdicts

    fresh = {key: value for key, value in output.items() if key != "verdicts_withheld"}
    held = withhold_unsourced_verdicts(fresh)
    notes = held.get("verdicts_withheld") or []
    if notes:
        return "unproven verdict: " + str(notes[0])
    return None


def _catalog(sources: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    catalog: dict[tuple[str, str], dict[str, Any]] = {}
    for source in sources:
        locator = _locator(source)
        if locator:
            catalog[(str(source.get("source_id") or ""), locator)] = source
    return catalog


def _citation_fault(cite: dict[str, Any], catalog: dict[tuple[str, str], dict[str, Any]]) -> str | None:
    if _is_pointer(cite):
        return "a citation must name a page, slide, or cell"
    locator = _locator(cite)
    source = catalog.get((str(cite.get("source_id") or ""), locator))
    if source is None:
        return "citation does not match a page, slide, or cell"
    passage = str(cite.get("passage") or "")
    if passage and passage not in str(source.get("text") or ""):
        return "citation does not match its source passage"
    return None


def _is_pointer(cite: dict[str, Any]) -> bool:
    if _locator(cite):
        return False
    if cite.get("pointer") is True or cite.get("source_index") is not None or cite.get("index") is not None:
        return True
    text = str(cite.get("text") or cite.get("ref") or "").strip()
    return bool(_POINTER.search(text)) or not _locator(cite)


def _locator(item: dict[str, Any]) -> str:
    for field in _LOCATOR_FIELDS:
        value = item.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return ""
