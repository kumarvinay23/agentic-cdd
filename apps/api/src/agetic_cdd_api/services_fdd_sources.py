"""Classify databook sources as investor workbook vs ledger (QBO, etc.)."""

from __future__ import annotations

from typing import Any, Iterable

# Keep hints specific — bare ".xlsx" / "p&l" mis-classify QBO exports as workbook.
_WORKBOOK_HINTS = (
    "workbook",
    "investor",
    "financial_model",
    "financial model",
    "model",
    "cim",
    "mgmt pack",
    "management pack",
    "management accounts",
    "datapack",
    "data pack",
    "model inputs",
    "financial summary",
)
_LEDGER_HINTS = (
    "qbo",
    "quickbooks",
    "quick books",
    "intuit",
    "ledger",
    "general ledger",
    "trial balance",
    "xero",
    "sage",
    "bank",
    ".qbo",
    "gl_",
    "gl ",
)
# Monthly / management packs are neither investor workbook nor QBO ledger.
_MANAGEMENT_HINTS = (
    "monthly financial",
    "monthly financials",
    "monthly pack",
    "management accounts",
    "mgmt accounts",
    "ytd26",
    "ytd 26",
)


def source_blob(*parts: Any) -> str:
    bits: list[str] = []
    for p in parts:
        if p is None:
            continue
        if isinstance(p, (list, tuple, set)):
            bits.extend(str(x) for x in p if x)
        else:
            bits.append(str(p))
    return " ".join(bits).lower()


def classify_source(*parts: Any) -> str:
    """Return ``workbook``, ``ledger``, ``management``, or ``unknown``."""
    blob = source_blob(*parts)
    if not blob:
        return "unknown"
    mgmt = any(h in blob for h in _MANAGEMENT_HINTS)
    wb = any(h in blob for h in _WORKBOOK_HINTS)
    ld = any(h in blob for h in _LEDGER_HINTS)
    # Monthly pack filenames often contain "financials" — prefer management.
    if mgmt and not (wb and "investor" in blob):
        return "management"
    if wb and not ld:
        return "workbook"
    if ld and not wb:
        return "ledger"
    if wb and ld:
        # Filename noise — prefer the more specific ledger token when both hit.
        if any(h in blob for h in ("qbo", "quickbooks", "intuit", ".qbo")):
            return "ledger"
        return "workbook"
    return "unknown"


def display_source_name(kind: str, raw: Iterable[str] | None = None) -> str:
    if kind == "workbook":
        return "investor workbook"
    if kind == "ledger":
        return "QBO ledger"
    if kind == "management":
        return "monthly pack"
    names = [str(s).strip() for s in (raw or []) if str(s).strip()]
    return names[0] if names else "alternate source"


def prefer_workbook_among(
    primary_value: float | None,
    primary_sources: list[str] | None,
    alternatives: list[dict[str, Any]] | None,
) -> tuple[float | None, list[str], list[dict[str, Any]], str | None]:
    """Pick investor-workbook value when ledger and workbook both present.

    Returns ``(value, sources, alternatives, note)``.
    """
    value = primary_value
    sources = list(primary_sources or [])
    alts = [dict(a) for a in (alternatives or []) if isinstance(a, dict)]
    note: str | None = None

    candidates: list[tuple[float, list[str], str]] = []
    if value is not None:
        candidates.append(
            (float(value), sources, classify_source(sources))
        )
    for alt in alts:
        try:
            av = float(alt["value"]) if alt.get("value") is not None else None
        except (TypeError, ValueError):
            av = None
        if av is None:
            continue
        asrc = [str(s) for s in (alt.get("sources") or [])]
        candidates.append((av, asrc, classify_source(asrc, alt.get("captions"))))

    workbook = [c for c in candidates if c[2] == "workbook"]
    ledger = [c for c in candidates if c[2] == "ledger"]

    if workbook:
        # Prefer the strongest investor/workbook hint when several classify as workbook.
        def _wb_strength(src: list[str]) -> int:
            blob = source_blob(src)
            score = 0
            for token in ("investor", "workbook", "cim", "financial_model", "mgmt"):
                if token in blob:
                    score += 2
            return score

        workbook.sort(key=lambda c: -_wb_strength(c[1]))
        wb_val, wb_src, _ = workbook[0]
        # Retain every materially different peer as an alternative for gap notes.
        peers: list[dict[str, Any]] = []
        for val, src, kind in candidates:
            if abs(val - wb_val) < 1e-9:
                continue
            peers.append(
                {
                    "value": val,
                    "sources": src
                    or (
                        ["QBO ledger"]
                        if kind == "ledger"
                        else (["investor workbook"] if kind == "workbook" else [])
                    ),
                    "chosen": False,
                    "source_kind": kind,
                }
            )
        if value is None or abs(float(value) - wb_val) > 1e-9:
            note = "fdd_basis:investor_workbook"
        return wb_val, (wb_src or sources or ["investor workbook"]), peers or alts, note

    if ledger and value is not None:
        # No workbook peer — keep ledger primary; still expose other alts.
        return value, sources, alts, None

    return value, sources, alts, note
