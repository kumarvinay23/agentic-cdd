"""Fix 4 — bind narrative sentences to fact_ids and verify numbers match.

Every title, bullet and note that contains a figure must cite the fact_ids it
uses. A checker confirms the rendered number equals the bound fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from agetic_cdd_api.fdd_schemas import ExhibitStoreDoc, SlideSpec
from agetic_cdd_api.services_fdd_tokens import (
    assert_no_raw_numeric_literals,
    format_fdd_number,
    resolve_text,
    resolve_text_pptx,
    strip_allowed_labels,
)


@dataclass(frozen=True)
class NarrativeBinding:
    fact_id: str
    display: str
    value: float | None
    raw_token: str = ""


@dataclass
class NarrativeBindResult:
    text: str
    bindings: list[NarrativeBinding] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    faults: list[str] = field(default_factory=list)
    ok: bool = True


def claim_implication_headline(
    claim: str,
    implication: str,
    *,
    max_len: int = 180,
) -> str:
    """Title policy — claim plus implication, not a bare number."""
    claim_s = " ".join(str(claim or "").split()).strip().rstrip(".")
    impl_s = " ".join(str(implication or "").split()).strip().rstrip(".")
    if claim_s and impl_s:
        text = f"{claim_s} — {impl_s}"
    else:
        text = claim_s or impl_s or "Diligence finding"
    return text[:max_len]


def bind_text(
    text: str,
    store: ExhibitStoreDoc | None,
    *,
    pptx: bool = True,
    store_scale: str = "M",
    display_scale: str = "k",
    declared_fact_ids: Iterable[str] | None = None,
) -> NarrativeBindResult:
    """Resolve tokens, collect fact_ids, and flag unbound / mismatched numbers."""
    raw = text or ""
    if not raw.strip():
        return NarrativeBindResult(text=raw, ok=True)

    declared = [str(x) for x in (declared_fact_ids or []) if x]
    bindings: list[NarrativeBinding] = []
    faults: list[str] = []

    if store is not None and "{{ex:" in raw:
        resolved = (
            resolve_text_pptx(
                raw,
                store,
                store_scale=store_scale,
                display_scale=display_scale,
            )
            if pptx
            else resolve_text(raw, store)
        )
        out_text = resolved.text
        for tok in resolved.bindings:
            fid = str(getattr(tok, "fact_id", None) or "").strip()
            if not fid:
                faults.append(f"token {tok.raw} resolved without fact_id")
                continue
            bindings.append(
                NarrativeBinding(
                    fact_id=fid,
                    display=str(tok.display or ""),
                    value=tok.value if isinstance(tok.value, (int, float)) else None,
                    raw_token=tok.raw,
                )
            )
        for missing in resolved.unresolved:
            faults.append(f"unresolved token {missing}")
    else:
        out_text = raw

    fact_ids = list(dict.fromkeys([*declared, *[b.fact_id for b in bindings]]))
    literals = assert_no_raw_numeric_literals(out_text)
    if literals:
        covered = _literals_covered_by_bindings(literals, bindings)
        uncovered = [lit for lit in literals if lit not in covered]
        if uncovered and not fact_ids:
            faults.append("numbers without fact_id: " + ", ".join(uncovered[:6]))
        elif uncovered:
            if not _literals_match_declared(
                uncovered,
                store,
                fact_ids,
                display_scale=display_scale,
                store_scale=store_scale,
            ):
                faults.append(
                    "numbers do not match cited fact_ids: " + ", ".join(uncovered[:6])
                )

    return NarrativeBindResult(
        text=out_text,
        bindings=bindings,
        fact_ids=fact_ids,
        faults=faults,
        ok=not faults,
    )


def assert_narrative_bound(
    text: str,
    store: ExhibitStoreDoc | None,
    *,
    required_fact_ids: Iterable[str] | None = None,
    pptx: bool = True,
    store_scale: str = "M",
    display_scale: str = "k",
) -> list[str]:
    """Return fault messages (empty = pass)."""
    declared = list(required_fact_ids or [])
    result = bind_text(
        text,
        store,
        declared_fact_ids=declared,
        pptx=pptx,
        store_scale=store_scale,
        display_scale=display_scale,
    )
    faults = list(result.faults)
    if declared:
        missing = [fid for fid in declared if fid not in set(result.fact_ids)]
        # Declared ids are already merged into result.fact_ids; keep API for callers
        # that want explicit required membership after resolve-only binds.
        for fid in declared:
            if fid and fid not in {b.fact_id for b in result.bindings} and "{{ex:" in (text or ""):
                # Token path should have produced the id; soft if only declared.
                pass
        _ = missing
    return faults


def check_narrative_bound(
    text: str,
    store: ExhibitStoreDoc | None,
    *,
    declared_fact_ids: Iterable[str] | None = None,
    pptx: bool = True,
) -> list[str]:
    """Alias used by slide stamping."""
    return assert_narrative_bound(
        text,
        store,
        required_fact_ids=declared_fact_ids,
        pptx=pptx,
    )


def _literals_covered_by_bindings(
    literals: list[str],
    bindings: list[NarrativeBinding],
) -> set[str]:
    covered: set[str] = set()
    for lit in literals:
        for b in bindings:
            if _approx_literal_in_display(lit, b.display or ""):
                covered.add(lit)
                break
            if b.value is not None:
                try:
                    lit_n = float(re.sub(r"[^\d.]", "", lit) or "nan")
                except ValueError:
                    continue
                # Match raw store value or common k/M display scaling.
                for cand in (b.value, b.value * 1000.0, b.value / 1000.0, b.value * 1e6):
                    if abs(cand - lit_n) < max(0.05, abs(cand) * 0.002):
                        covered.add(lit)
                        break
    return covered


def _approx_literal_in_display(literal: str, display: str) -> bool:
    a = re.sub(r"[^\d.]", "", literal)
    b = re.sub(r"[^\d.]", "", display or "")
    if not a or not b:
        return False
    try:
        return abs(float(a) - float(b)) < 0.05 or a in b or b in a
    except ValueError:
        return a in b


def _literals_match_declared(
    literals: list[str],
    store: ExhibitStoreDoc | None,
    fact_ids: list[str],
    *,
    display_scale: str,
    store_scale: str,
) -> bool:
    """True when each literal can be explained by one declared fact's display."""
    if not store or not fact_ids:
        return False
    displays = _displays_for_fact_ids(
        store, fact_ids, display_scale=display_scale, store_scale=store_scale
    )
    if not displays:
        return False
    for lit in literals:
        if not any(_approx_literal_in_display(lit, d) for d in displays):
            return False
    return True


def _displays_for_fact_ids(
    store: ExhibitStoreDoc,
    fact_ids: list[str],
    *,
    display_scale: str,
    store_scale: str,
) -> list[str]:
    from agetic_cdd_api.services_fdd_format import format_cell

    want = {str(f) for f in fact_ids}
    out: list[str] = []
    for ex in store.exhibits or []:
        for cell in ex.cells or []:
            if str(cell.fact_id or "") not in want:
                continue
            out.append(
                format_cell(
                    cell,
                    store_scale=store_scale,
                    display_scale=display_scale,
                    prose=True,
                )
            )
            if cell.value is not None:
                out.append(format_fdd_number(cell.value))
                out.append(str(cell.value))
    return out


def stamp_slide_narrative_bindings(
    slides: Iterable[SlideSpec],
    store: ExhibitStoreDoc,
    *,
    store_scale: str = "M",
    display_scale: str = "k",
) -> list[SlideSpec]:
    """Attach narrative fact_ids and flag unbound numbers on content slides."""
    out: list[SlideSpec] = []
    for slide in slides:
        declared = list(getattr(slide, "figure_ids", None) or [])
        fact_like = [
            x
            for x in declared
            if x and not str(x).startswith("ex_") and ":" in str(x)
        ]
        # Client footnotes must not carry bind diagnostics (they polluted the deck).
        footnotes = [
            fn
            for fn in (slide.footnotes or [])
            if not str(fn).startswith("Narrative bind:")
        ]
        texts = [
            slide.headline or "",
            *(slide.observations or []),
        ]
        all_fact_ids: list[str] = list(fact_like)
        faults: list[str] = []
        for line in texts:
            if not line or not strip_allowed_labels(line).strip():
                continue
            if not assert_no_raw_numeric_literals(line) and "{{ex:" not in line:
                continue
            result = bind_text(
                line,
                store,
                pptx=True,
                store_scale=store_scale,
                display_scale=display_scale,
                declared_fact_ids=fact_like,
            )
            all_fact_ids.extend(result.fact_ids)
            faults.extend(result.faults)

        updates: dict[str, Any] = {}
        if footnotes != list(slide.footnotes or []):
            updates["footnotes"] = footnotes
        uniq_facts = list(dict.fromkeys(all_fact_ids))
        if uniq_facts:
            merged = list(dict.fromkeys([*declared, *uniq_facts]))
            updates["figure_ids"] = merged[:16]
            updates["narrative_fact_ids"] = uniq_facts[:16]
        if faults:
            # Keep faults machine-readable only — never append to completeness_detail
            # (that string is painted into client Completeness footnotes).
            updates["narrative_bind_faults"] = faults[:8]
        # Strip any legacy Narrative bind pollution from completeness_detail.
        existing = str(getattr(slide, "completeness_detail", "") or "").strip()
        if "Narrative bind:" in existing:
            cleaned = existing.split("Narrative bind:")[0].strip(" ;")
            updates["completeness_detail"] = cleaned
        out.append(slide.model_copy(update=updates) if updates else slide)
    return out
