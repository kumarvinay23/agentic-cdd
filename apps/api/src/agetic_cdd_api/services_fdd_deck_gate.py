"""Fix 8 — release gate on the FDD deck.

Block-severity ontology flags already stop databook tabs from publishing.
This module stops the deck as well: no PPTX while an open block flag sits on
a schedule the chapter pack reads, and each slide carries a completeness
state instead of a silent empty table.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from agetic_cdd_api.fdd_schemas import SlideSpec, SlideTable
from agetic_cdd_api.services_fdd_bridge import GateBlockedError

# Core FDD schedules the chapter pack depends on (ontology schedule ids).
CORE_FDD_SCHEDULES: frozenset[str] = frozenset(
    {
        "FDD-02",  # P&L
        "FDD-03",  # QoE / EBITDA bridge
        "FDD-06",  # Revenue
        "FDD-07",  # Gross profit / COS
        "FDD-08",  # Costs / SG&A
        "FDD-11",  # Cash flow
        "FDD-12",  # Balance sheet
        "FDD-13",  # Net debt
        "FDD-14",  # Leases
        "FDD-15",  # NWC
        "FDD-18",  # Deal / structure
    }
)

CHAPTER_SCHEDULES: dict[str, frozenset[str]] = {
    "es": frozenset({"FDD-02", "FDD-03", "FDD-06", "FDD-07", "FDD-12", "FDD-13"}),
    "transaction": frozenset({"FDD-06", "FDD-07", "FDD-18"}),
    "qoe": frozenset({"FDD-02", "FDD-03"}),
    "trading": frozenset({"FDD-02", "FDD-06", "FDD-07", "FDD-08"}),
    "cash": frozenset({"FDD-11", "FDD-12"}),
    "bs": frozenset({"FDD-12", "FDD-13", "FDD-14", "FDD-15"}),
    "deal": frozenset({"FDD-18"}),
    "intro": frozenset(),
    "appendix": frozenset(),
    "cover": frozenset(),
    "contents": frozenset(),
}

CompletenessState = Literal["complete", "held", "blocked", "empty"]


@dataclass(frozen=True)
class NamedBlockFlag:
    code: str
    schedule_id: str
    message: str
    flag_id: str = ""

    def display(self) -> str:
        msg = (self.message or "").strip()
        if msg and msg != self.code:
            return f"{self.code} ({self.schedule_id}): {msg}"
        return f"{self.code} ({self.schedule_id})"


@dataclass(frozen=True)
class DeckReleaseGate:
    allowed: bool
    deal_id: str
    open_blocks: list[NamedBlockFlag] = field(default_factory=list)
    schedule_ids: frozenset[str] = field(default_factory=frozenset)
    detail: str = ""

    def named_flags(self) -> list[str]:
        return [f.display() for f in self.open_blocks]

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "deal_id": self.deal_id,
            "blocked": not self.allowed,
            "open_block_flags": [
                {
                    "code": f.code,
                    "schedule_id": f.schedule_id,
                    "message": f.message,
                    "flag_id": f.flag_id,
                    "display": f.display(),
                }
                for f in self.open_blocks
            ],
            "named_flags": self.named_flags(),
            "schedule_ids": sorted(self.schedule_ids),
            "detail": self.detail,
        }


def name_block_flag(flag: dict[str, Any]) -> NamedBlockFlag:
    code = str(flag.get("code") or "UNKNOWN").strip() or "UNKNOWN"
    schedule = str(flag.get("schedule_id") or "UNSCHEDULED").strip() or "UNSCHEDULED"
    message = str(flag.get("message") or "").strip() or code
    return NamedBlockFlag(
        code=code,
        schedule_id=schedule,
        message=message,
        flag_id=str(flag.get("flag_id") or ""),
    )


def load_open_flags_for_deal(deal_key: str) -> list[dict[str, Any]]:
    """Open flags from in-memory checker, falling back to ``v_open_flags``."""
    from agetic_cdd_api.services_published_pages import _deal_id
    from agetic_cdd_api.services_rule_checker import open_flags

    deal_id = _deal_id(deal_key) or str(deal_key or "").strip()
    if not deal_id:
        return []
    memory = list(open_flags(deal_id) or [])
    # Also try slug key if deal_id differs (tests often key by slug).
    slug = str(deal_key or "").strip()
    if slug and slug != deal_id:
        memory = memory or list(open_flags(slug) or [])
    if memory:
        return memory
    try:
        from agetic_cdd_api.services_databook_view import _load_open_flags
        from agetic_cdd_api.settings import settings

        url = settings.databook_database_url.strip()
        if not url:
            return []
        return list(_load_open_flags(url, deal_id) or [])
    except Exception:
        return []


def evaluate_deck_release_gate(
    deal_slug: str,
    *,
    schedule_ids: Iterable[str] | None = None,
) -> DeckReleaseGate:
    """Return whether the FDD deck may be produced for this deal."""
    from agetic_cdd_api.services_published_pages import _deal_id

    slug = str(deal_slug or "").strip()
    deal_id = _deal_id(slug) if slug else ""
    want = frozenset(
        str(s).strip()
        for s in (schedule_ids if schedule_ids is not None else CORE_FDD_SCHEDULES)
        if str(s).strip()
    )
    flags = load_open_flags_for_deal(slug or deal_id)
    blocks: list[NamedBlockFlag] = []
    for flag in flags:
        if str(flag.get("severity") or "").lower() != "block":
            continue
        if str(flag.get("status") or "OPEN").upper() not in {"OPEN", ""}:
            continue
        named = name_block_flag(flag)
        if want and named.schedule_id not in want and named.schedule_id != "UNSCHEDULED":
            continue
        # Unscheduled blocks still gate the deck — they name the rule.
        if want and named.schedule_id == "UNSCHEDULED":
            blocks.append(named)
            continue
        if not want or named.schedule_id in want:
            blocks.append(named)
    # Deduplicate by code+schedule.
    seen: set[tuple[str, str]] = set()
    unique: list[NamedBlockFlag] = []
    for b in blocks:
        key = (b.code, b.schedule_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(b)
    allowed = not unique
    detail = (
        "Deck release allowed — no open block flags on FDD schedules."
        if allowed
        else "Deck blocked by open block flags: " + "; ".join(b.display() for b in unique)
    )
    return DeckReleaseGate(
        allowed=allowed,
        deal_id=deal_id or slug,
        open_blocks=unique,
        schedule_ids=want,
        detail=detail,
    )


def assert_deck_release_allowed(
    deal_slug: str,
    *,
    schedule_ids: Iterable[str] | None = None,
) -> DeckReleaseGate:
    """Raise ``GateBlockedError`` naming every open block flag when deck is refused."""
    gate = evaluate_deck_release_gate(deal_slug, schedule_ids=schedule_ids)
    if gate.allowed:
        return gate
    names = gate.named_flags()
    raise GateBlockedError(
        "Deck blocked — open block flags on schedules the FDD reads: "
        + "; ".join(names)
    )


def schedules_for_chapter(chapter: str) -> frozenset[str]:
    return CHAPTER_SCHEDULES.get(str(chapter or "").strip().lower(), frozenset())


def blocked_flags_for_chapter(
    gate: DeckReleaseGate,
    chapter: str,
) -> list[NamedBlockFlag]:
    schedules = schedules_for_chapter(chapter)
    if not schedules:
        return []
    return [f for f in gate.open_blocks if f.schedule_id in schedules]


def held_completeness_table(
    *,
    title: str,
    state: CompletenessState,
    detail: str,
) -> SlideTable:
    label = {
        "blocked": "Blocked — open block flag on a schedule this slide reads",
        "held": "Held — evidence incomplete",
        "empty": "Empty — no published figures for this exhibit",
        "complete": "Complete",
    }.get(state, state)
    return SlideTable(
        title=title or "Exhibit completeness",
        headers=["Item", "Status"],
        rows=[
            ["Completeness", label],
            ["Detail", (detail or "—")[:180]],
        ],
        source="Deck release gate",
        evidence_tier="C",
    )


def _table_is_silent_hole(table: SlideTable | None) -> bool:
    if table is None:
        return True
    rows = list(table.rows or [])
    if not rows:
        return True
    # Single placeholder rows that say Pending / — without figures.
    if len(rows) == 1:
        blob = " ".join(str(c) for c in rows[0]).lower()
        if "pending" in blob or blob.strip() in {"—", "-", ""}:
            return True
    return False


def stamp_slide_completeness(
    slides: Iterable[SlideSpec],
    gate: DeckReleaseGate | None = None,
    *,
    deal_slug: str | None = None,
) -> list[SlideSpec]:
    """Stamp completeness_state; replace silent empty tables with held stubs."""
    if gate is None and deal_slug:
        gate = evaluate_deck_release_gate(deal_slug)
    out: list[SlideSpec] = []
    for slide in slides:
        chapter = str(slide.chapter or "")
        chapter_blocks = blocked_flags_for_chapter(gate, chapter) if gate else []
        updates: dict[str, Any] = {}
        sched = list(getattr(slide, "schedule_ids", None) or [])
        if not sched:
            sched = sorted(schedules_for_chapter(chapter))
            updates["schedule_ids"] = sched

        current = getattr(slide, "completeness_state", None) or "complete"
        detail = getattr(slide, "completeness_detail", None) or ""

        if chapter_blocks:
            named = "; ".join(f.display() for f in chapter_blocks)
            updates["completeness_state"] = "blocked"
            updates["completeness_detail"] = named
            # Do not leave a numeric matrix that depends on a blocked schedule.
            title = slide.table.title if slide.table is not None else "Exhibit held"
            updates["table"] = held_completeness_table(
                title=title,
                state="blocked",
                detail=named,
            )
            updates["kpis"] = []
            obs = [
                f"Blocked by open block flag(s): {named}",
                *(slide.observations or [])[:3],
            ]
            updates["observations"] = obs[:6]
            if "held —" not in (slide.headline or "").lower() and "blocked" not in (
                slide.headline or ""
            ).lower():
                updates["headline"] = "Exhibit blocked — open block flag on a read schedule"
            footnotes = list(slide.footnotes or [])
            note = f"Completeness: blocked — {named}"
            if note not in footnotes:
                footnotes = [note, *footnotes][:4]
            updates["footnotes"] = footnotes
        elif current == "complete" and _table_is_silent_hole(slide.table):
            # Content layouts with empty/pending tables → explicit empty state.
            layout = str(slide.layout or "")
            if layout in {
                "section_table_obs",
                "section_chart_obs",
                "kpi_strip",
                "request_table",
                "ledger_table",
            } and chapter not in {"cover", "contents"}:
                title = (
                    slide.table.title
                    if slide.table is not None and slide.table.title
                    else "Exhibit"
                )
                detail_txt = detail or "No published figures available for this exhibit"
                updates["completeness_state"] = "empty"
                updates["completeness_detail"] = detail_txt
                updates["table"] = held_completeness_table(
                    title=title,
                    state="empty",
                    detail=detail_txt,
                )
                footnotes = list(slide.footnotes or [])
                note = "Completeness: empty — no published figures"
                if note not in footnotes:
                    footnotes = [note, *footnotes][:4]
                updates["footnotes"] = footnotes
        elif current in {"held", "blocked", "empty"}:
            # Preserve planner-set state; ensure footnote chrome exists.
            # Strip narrative-bind diagnostics — they are QA-only, not client chrome.
            detail_clean = str(detail or "")
            if "Narrative bind:" in detail_clean:
                detail_clean = detail_clean.split("Narrative bind:")[0].strip(" ;")
                if detail_clean != detail:
                    updates["completeness_detail"] = detail_clean
            footnotes = list(slide.footnotes or [])
            # Drop legacy Completeness footnotes that still carry bind noise.
            footnotes = [
                fn
                for fn in footnotes
                if "Narrative bind:" not in str(fn)
            ]
            note = f"Completeness: {current}" + (
                f" — {detail_clean}" if detail_clean else ""
            )
            if note and note not in footnotes:
                footnotes = [note, *footnotes][:4]
            updates["footnotes"] = footnotes
        else:
            updates.setdefault("completeness_state", "complete")

        out.append(slide.model_copy(update=updates) if updates else slide)
    return out
