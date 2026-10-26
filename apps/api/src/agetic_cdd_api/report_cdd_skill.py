"""Render the CDD deck with the DiligenceIQ v4.1 template.

The builder in ``tools/cdd-report-builder`` is the renderer that produced
Compost_Crew_CDD_v4: a fixed slide master, native charts, and pages removed
when the evidence does not support them. This module fills ``content.json``
from the deal's agent specs and calls that renderer. Deal-specific sentences
from the Compost Crew analyst script are not copied.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from contextvars import ContextVar
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agetic_cdd_api.report_builder_base import BuildContext
from agetic_cdd_api.report_cdd_audit import audit_exceptions, glossary_terms, slide_blob, verdict_rows
from agetic_cdd_api.report_cdd_calcs import DeckMath, derive
from agetic_cdd_api.report_cdd_evidence import EvidenceBook, build_agent_evidence, prepare_evidence
from agetic_cdd_api.report_cdd_deck_v4 import (
    _clean,
    _company,
    _filled,
    _findings,
    _fmt_number,
    _is_cap_table_text,
    _is_ledger_sizing_text,
    _is_ownership_perimeter,
    _is_qa_meta,
    _resolve,
    _revenue_millions,
    _sizing_metrics,
    _spec,
)

_REF = "RUN-1"
_slide_refs: ContextVar[list[str] | None] = ContextVar("cdd_slide_refs", default=None)


def _refs_now() -> list[str]:
    current = _slide_refs.get()
    return current if current else [_REF]


def _bind(book: EvidenceBook, *buckets: str) -> None:
    _slide_refs.set(book.refs(*buckets))


def _bind_ids(ids: list[str]) -> None:
    _slide_refs.set([fid for fid in ids if fid] or _refs_now())


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[4] / "tools" / "cdd-report-builder"


def _fit_line(text: str, limit: int = 160) -> str:
    line = " ".join(str(text or "").split())
    if len(line) <= limit:
        return line
    return line[:limit].rsplit(" ", 1)[0]


def _title(text: str) -> dict[str, Any]:
    return {"text": _clean(text, 165), "refs": _refs_now(), "kind": "interpretation"}


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": _clean(text, 320), "refs": _refs_now(), "kind": "fact"}


def _bullets(items: list[str]) -> dict[str, Any]:
    return {
        "type": "bullets",
        "items": [{"text": _clean(item, 170), "refs": _refs_now(), "kind": "fact"} for item in items if _filled(item)],
    }


def _table(
    columns: list[str],
    rows: list[list[str]],
    row_refs: list[list[str]] | None = None,
) -> dict[str, Any]:
    return {
        "type": "table",
        "columns": columns,
        "rows": [[_clean(cell, 90) for cell in row] for row in rows],
        "row_refs": row_refs if row_refs is not None else [_refs_now() for _ in rows],
    }


def _chart(
    categories: list[str],
    values: list[float],
    name: str,
    *,
    unit: str = "$M",
    chart_type: str = "column",
    kind: str = "fact",
    point_refs: list[str] | None = None,
    series: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if series:
        drawn = [{"name": item["name"], "values": item["values"]} for item in series]
        traced = [item.get("point_refs") or [] for item in series]
    else:
        drawn = [{"name": name, "values": values}]
        traced = [point_refs] if point_refs else []
    payload = {
        "type": "chart",
        "chart_type": chart_type,
        "categories": categories,
        "series": drawn,
        "unit_label": unit,
        "number_format": "0.0",
        "value_axis_title": unit,
        "refs": _refs_now(),
        "kind": kind,
    }
    if traced and any(traced):
        payload["point_refs"] = traced
    return payload


def _slide_ids(skill: Path) -> list[str]:
    data = yaml.safe_load((skill / "config" / "slide_map.yaml").read_text())
    return [slide["id"] for slide in data["slides"]]


def _paged(
    title: str,
    subtitle: str,
    columns: list[str],
    rows: list[list[str]],
    takeaway: str,
    *,
    size: int = 8,
    row_ids: list[str] | None = None,
) -> dict[str, Any] | list[dict[str, Any]]:
    pages = []
    for start in range(0, len(rows), size):
        chunk = rows[start:start + size]
        refs = None
        if row_ids is not None:
            refs = [[fid] for fid in row_ids[start:start + size]]
        pages.append({
            "title": _title(title),
            "subtitle": _title(subtitle),
            "elements": {
                "table": _table(columns, chunk, refs),
                "takeaway": _text(takeaway),
            },
        })
    return pages[0] if len(pages) == 1 else pages


def _withheld_page_gaps(skill: Path, filled: set[str]) -> list[dict[str, Any]]:
    data = yaml.safe_load((skill / "config" / "slide_map.yaml").read_text())
    survey: list[str] = []
    other: list[str] = []
    for slide in data["slides"]:
        sid = slide["id"]
        if sid in filled or sid in {"S004_contents", "S007_glossary", "S101_exceptions"}:
            continue
        if slide.get("archetype") in {"divider", "contents", "back_cover", "cover"}:
            continue
        if slide.get("gate") == "research_gated":
            survey.append(sid)
        else:
            other.append(sid)
    gaps = []
    if survey:
        gaps.append({
            "severity": "MEDIUM",
            "rule": "E11-NO-PRIMARY",
            "issue": f"{len(survey)} pages need a survey or interview file",
            "treatment": "No survey or interview file was loaded.",
            "slides": survey,
        })
    if other:
        gaps.append({
            "severity": "MEDIUM",
            "rule": "E1-NOT-PROVIDED",
            "issue": f"{len(other)} pages have nothing further in the loaded record",
            "treatment": "Not in the loaded record.",
            "slides": other,
        })
    return gaps


def _put_room_slides(slides: dict[str, Any], put, math: DeckMath, company: str) -> None:
    def open_slot(*ids: str) -> str:
        for sid in ids:
            if sid not in slides:
                return sid
        return ""

    if math.ties:
        sid = open_slot("S020_highlights_summary", "S040_growth_factors_overview")
        if sid:
            math.ties["slide"] = sid
            _bind_ids(math.ties["ids"])
            put(sid, {
                "title": _title("Management accounts and the company workbook do not tie on revenue"),
                "subtitle": _title(math.ties["issue"]),
                "elements": {"rows": _table(math.ties["columns"], math.ties["rows"])},
            })
    if math.unit_basis:
        sid = open_slot("S013_business_model_comparison", "S014_model_scorecard")
        if sid:
            math.unit_basis["slide"] = sid
            _bind_ids(math.unit_basis["ids"])
            put(sid, {
                "title": _title(
                    math.unit_basis["issue"]
                    or f"Locations, price and retention for {company}, on the bases the workbook states"
                ),
                "subtitle": _title(
                    (
                        f"Residential price on the existing book is {math.unit_basis['price']} a month. "
                        "No third-party local price was in the loaded files."
                    )
                    if math.unit_basis.get("price")
                    else "Model basis and actual cohort basis are both shown. They are not averaged."
                ),
                "elements": {
                    "table": _table(math.unit_basis["columns"], math.unit_basis["rows"]),
                    "takeaway": _text(
                        math.unit_basis["treatment"].rstrip(".") + ". " + math.unit_basis["reconcile"]
                        if math.unit_basis.get("reconcile")
                        else math.unit_basis["treatment"]
                    ),
                },
            })
    if math.cohorts:
        sid = open_slot("S016_pain_points")
        if sid:
            _bind_ids(math.cohorts["ids"])
            last_col = math.cohorts["columns"][-1]
            opening = math.cohorts["rows"][0]
            put(sid, {
                "title": _title(f"Logo retention by cohort for {company}"),
                "subtitle": _title("Each cell is the workbook's retention for that cohort in that year. Revenue cohorts are not mixed in."),
                "heads": {
                    "left_head": "Logo retention by cohort",
                    "right_head": "How to read the count",
                },
                "elements": {
                    "left": _table(math.cohorts["columns"], math.cohorts["rows"]),
                    "right": _bullets([
                        f"{opening[0]} is {opening[-1]} by {last_col}.",
                        "The accounts column is the cohort's opening count. It is not the new-logo count for that year.",
                        "A later cohort is not assumed to follow an earlier one.",
                    ]),
                },
            })
    if math.concentration:
        sid = open_slot("S069_target_strengths")
        if sid:
            _bind_ids(math.concentration["ids"])
            put(sid, {
                "title": _title(f"Largest accounts for {company}, as the workbook ranks them"),
                "subtitle": _title("Names are the labels in the concentration sheet. A rank without a share is left out."),
                "heads": {
                    "quotes_head": "Largest accounts in the workbook",
                    "right_head": "What the ranking shows",
                },
                "elements": {
                    "quotes": _table(math.concentration["columns"], math.concentration["rows"]),
                    "right": _bullets([math.concentration["note"]]),
                },
            })
    if math.subscriber_curve:
        sid = open_slot("S048_downturn_resilience")
        if sid:
            curve = math.subscriber_curve
            _bind_ids(curve["ids"])
            put(sid, {
                "title": _title(f"Subscriber retention and revenue retention for {company} diverge as the book ages"),
                "subtitle": _title("Both series are the retention curve in the workbook. One is not converted into the other."),
                "heads": {
                    "chart_head": "Subscriber retention and revenue retention",
                    "right_head": "How the two series differ",
                },
                "elements": {
                    "chart": _chart(
                        curve["categories"],
                        [],
                        "Retention",
                        unit="%",
                        series=[
                            {"name": "Subscriber retention", "values": curve["subscriber"], "point_refs": curve["ids"]},
                            {"name": "Revenue retention", "values": curve["revenue"], "point_refs": curve["ids"]},
                        ],
                    ),
                    "right": _bullets([
                        "The month label is the age of the book on that row.",
                        "A missing month is not interpolated.",
                    ]),
                },
            })
    if math.contracts:
        sid = open_slot("S074_l1_right_to_win")
        if sid:
            _bind_ids([*math.contracts["ids"], math.contracts.get("revenue_id") or ""])
            note = "A contract total is not treated as company revenue."
            if math.contracts.get("share"):
                note = (
                    f"The largest contract is {math.contracts['share']} of {math.contracts['year']} revenue. "
                    "The workbook's own name is kept."
                )
            if math.dc_cases and math.dc_cases.get("run_rate") is not None:
                note = (
                    note.rstrip(".")
                    + f". First-half billings annualize to {math.dc_cases['run_rate']:.2f} million."
                )
            put(sid, {
                "title": _title(
                    f"The largest contract is {math.contracts['share']} of {math.contracts['year']} revenue"
                    if math.contracts.get("share") else
                    f"Largest contracts on record for {company}"
                ),
                "subtitle": _title("Ranked by the latest actual year the contract sheet states."),
                "elements": {
                    "table": _table(math.contracts["columns"], math.contracts["rows"]),
                    "takeaway": _text(note),
                },
            })
    if math.web_competitors and "S060_competitor_archetypes" not in slides:
        rows = math.web_competitors[:6]
        _bind_ids([row["id"] for row in rows])
        priced = next((row for row in rows if re.search(r"\$\d", row["price"])), None)
        title = (
            f"{priced['name']} lists {priced['price']}, read outside the data room"
            if priced else
            "Local competitors read on web pages, outside the data room"
        )
        note = "These pages are outside the data room and are not CIM statements."
        if priced and re.search(r"\d", priced.get("commercial") or ""):
            note = (
                f"{priced['name']} lists a residential price of {priced['price']} "
                f"and a commercial entry {priced['commercial']}. {note}"
            )
        retrieved = next((row["retrieved"] for row in rows if row.get("retrieved")), "")
        if retrieved:
            note = f"{retrieved}. {note}"
        put("S060_competitor_archetypes", {
            "title": _title(title),
            "subtitle": _title("These pages are not in the CIM and not in the data room."),
            "elements": {
                "table": _table(
                    ["Competitor", "Footprint", "Residential price", "Record"],
                    [
                        [
                            _fit_line(row["name"], 40),
                            _fit_line(row["footprint"], 70),
                            _fit_line(row["price"], 40),
                            "Web, outside the data room",
                        ]
                        for row in rows
                    ],
                ),
                "takeaway": _text(note),
            },
        })
    if math.conclusion and "S018_industry_trends" not in slides:
        closing = math.conclusion
        _bind_ids([closing["id"]])
        put("S018_industry_trends", {
            "title": _title(closing["title"]),
            "subtitle": _title(closing["subtitle"]),
            "heads": {
                "left_head": "What the record supports",
                "right_head": "Reliance",
            },
            "elements": {
                "left": _table(["Read", "On the record"], closing["rows"]),
                "right": _bullets(closing["bullets"]),
            },
        })


def build_skill_content(
    ctx: BuildContext, book: EvidenceBook | None = None
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Return content.json and the withhold list (slides the specs cannot support)."""
    if book is None:
        book = build_agent_evidence(ctx)
    math = derive(ctx, book)
    company = _company(ctx)
    today = date.today().strftime("%B %Y")
    slides: dict[str, Any] = {}
    filled: set[str] = set()

    def put(sid: str, payload: dict[str, Any]) -> None:
        slides[sid] = payload
        filled.add(sid)

    _bind(book, "method")
    put("S001_cover", {
        "elements": {
            "report_title": _text(f"Commercial Due Diligence: {company}"),
            "report_subtitle": _text("Draft for discussion"),
            "prepared_for": _text("Prepared for DiligenceIQ"),
            "report_date": _text(today),
        },
    })
    modules = len([k for k, v in ctx.agent_outputs.items() if isinstance(v, dict) and v])
    put("S002_disclaimer", {
        "title": _title("Disclaimer & reliance limitations"),
        "subtitle": _title("This report is limited to the modules and data-room documents loaded for this deal."),
        "elements": {
            "disclaimer_body": _text(
                f"Prepared for discussion of {company}. It is not a recommendation to invest. "
                "Accounts and workbooks outrank the CIM, and the CIM outranks agent outputs."
            ),
            "data_notice": _text(
                "Evidence is limited to the diligence modules loaded for this deal. "
                "A module with no fact base is an open request, not a negative finding. "
                "Plan years carry a P suffix and are not results."
            ),
        },
    })
    put("S003_engagement", {
        "title": _title(
            f"The mandate: test whether {company}'s trading, customers and market support the management plan"
        ),
        "subtitle": _title("Each finding is graded by the evidence behind it: established, indicated or asserted."),
        "heads": {
            "col1_head": "Business & Financials",
            "col2_head": "Market & Geography",
            "col3_head": "Customers & Retention",
            "col4_head": "Competitive Landscape",
            "col5_head": "Growth Opportunities",
        },
        "elements": {
            "lead": _text(
                f"Commercial due diligence on {company} using the data room and the diligence modules loaded for this deal."
            ),
            "col1_body": _bullets(["What has the business delivered?", "How do margins trend?", "What is contracted?"]),
            "col2_body": _bullets(["How large is the serviceable market?", "Is the sizing method sound?", "Which geographies are next?"]),
            "col3_body": _bullets(["How are customers retained?", "How concentrated is revenue?", "What is untested without research?"]),
            "col4_body": _bullets(["Who competes for the same customers?", "Is price in line?", "Which differentiators hold?"]),
            "col5_body": _bullets(["Which levers are in the plan?", "What must be true for each?", "What would change the view?"]),
        },
    })
    _bind(book, "method")
    put("S005_research_approach", {
        "title": _title(
            "The findings rest on the data room first: accounts and workbooks outrank the CIM, and the CIM outranks the agent outputs"
        ),
        "subtitle": _title("Where they disagree, the data room is used and the agent finding is an exception."),
        "elements": {
            "left": _table(
                ["Rank", "Source", "Use"],
                [
                    ["1", "Accounts / QBO actuals", "Established results"],
                    ["2", "Company workbook", "Indicated, company's model"],
                    ["3", "CIM / management", "Asserted until tied to accounts"],
                    ["4", "Agent outputs", "A lead, rejected if uncited"],
                ],
            ),
            "right": _bullets([
                "No customer survey is assumed.",
                "Plan years are marked P and are not results.",
                "Pages without an exhibit are withheld.",
            ]),
        },
    })

    hist = _resolve(ctx, "historical_performance")
    actuals, partials = book.snapshot_points(hist)
    points = actuals or partials
    if points:
        latest = points[-1]
        prior = points[-2] if len(points) > 1 else None
        if prior and prior[1]:
            matched = next(
                (
                    row for row in math.yoy
                    if row["earlier"] == prior[0] and row["later"] == latest[0]
                ),
                None,
            )
            change = f" ({matched['pct']:+.1f}%)" if matched else ""
            if matched:
                for calc in math.calculations:
                    if calc.id == matched["pct_id"] and "S009_company_snapshot" not in calc.used_on:
                        calc.used_on.append("S009_company_snapshot")
            headline = (
                f"Revenue was {_fmt_number(prior[1], scale='million')} in {prior[0]} and "
                f"{_fmt_number(latest[1], scale='million')} in {latest[0]}{change}"
            )
        else:
            headline = f"{_fmt_number(latest[1], scale='million')} revenue in {latest[0]}"
        _bind(book, "revenue_actual", "revenue_partial", "narrative_hpf")
        kpis = [
            {
                "value": _fmt_number(value, scale="million"),
                "label": f"Revenue {label}",
                "refs": [fid] if fid and fid != _REF else _refs_now(),
                "kind": "fact",
            }
            for label, value, fid in points[-4:]
        ]
        if actuals and partials and len(kpis) < 5:
            label, value, fid = partials[-1]
            kpis.append({
                "value": _fmt_number(value, scale="million"),
                "label": f"Revenue {label}",
                "refs": [fid] if fid and fid != _REF else _refs_now(),
                "kind": "fact",
            })
        if len(kpis) < 5 and math.margins:
            shown = next(
                (item for item in math.margins if "ebitda" in str(item.get("metric") or "").lower()),
                math.margins[-1],
            )
            kpis.append({
                "value": f"{shown['value']:.1f}%",
                "label": f"{shown.get('metric') or 'Margin'} {shown['label']}",
                "refs": [shown["id"]],
                "kind": "fact",
            })
        facts = [
            line for line in _findings(hist, 6)
            if not _is_qa_meta(line) and not _is_cap_table_text(line) and not _is_ownership_perimeter(line)
        ] or [headline]
        put("S009_company_snapshot", {
            "title": _title(headline),
            "subtitle": _title("Actuals from the accounts extract. Plan years are not on this chart."),
            "elements": {
                "kpis": {"type": "kpis", "items": kpis},
                "left": _bullets(facts),
                "right": _chart(
                    [p[0] for p in points[-6:]],
                    [p[1] for p in points[-6:]],
                    "Revenue",
                    point_refs=[p[2] for p in points[-6:]],
                ),
            },
        })

    ownership = _spec(_resolve(ctx, "company_background")).get("ownership")
    events = _spec(_resolve(ctx, "company_background")).get("history_events")
    if not isinstance(events, list) and isinstance(ownership, dict):
        events = ownership.get("history_events")
    if math.milestones:
        _bind_ids([item["id"] for item in math.milestones])
        put("S010_platform_evolution", {
            "title": _title(f"How {company} was built, from the milestones the CIM states"),
            "subtitle": _title("The 2018 line is the leadership-page biography. These are not accounts."),
            "elements": {
                "flow": _table(["When", "Event"], [[item["when"], item["what"]] for item in math.milestones[:6]]),
                "right": _bullets([f"{item['when']}: {item['what']}" for item in math.milestones[:4]]),
            },
        })
    elif isinstance(events, list) and events:
        rows = []
        for event in events[:6]:
            if isinstance(event, dict):
                when = _clean(event.get("year") or event.get("date") or "—", 24)
                what = _clean(event.get("event") or event.get("description") or "", 80)
            else:
                when, what = "—", _clean(event, 80)
            if what and not _is_cap_table_text(f"{when} {what}"):
                rows.append([when, what])
        if rows:
            _bind(book, "history")
            put("S010_platform_evolution", {
                "title": _title(f"How {company} was assembled, from the events on record"),
                "subtitle": _title("Milestones are management's unless the accounts also show them."),
                "elements": {
                    "flow": _table(["When", "Event"], rows),
                    "right": _bullets([f"{a}: {b}" for a, b in rows]),
                },
            })
    if "S010_platform_evolution" not in slides and math.cim_history:
        _bind_ids([fid for item in math.cim_history for fid in item["ids"]])
        put("S010_platform_evolution", {
            "title": _title(f"How {company} scaled, on the years the CIM table states"),
            "subtitle": _title("These are the CIM's figures. They are not a substitute for the accounts."),
            "elements": {
                "flow": _table(["When", "As the CIM states"], [[item["when"], item["what"]] for item in math.cim_history]),
                "right": _bullets([f"{item['when']}: {item['what']}" for item in math.cim_history[:4]]),
            },
        })

    if math.costs:
        cost_ids = [fid for item in math.costs for fid in (item.get("ids") or [item["id"]])]
        _bind_ids(cost_ids)
        lead = next((item for item in math.costs if "labor" in item["name"].lower() and item.get("share")), None)
        title = (
            f"{lead['name']} are {lead['share']} of {lead['year']} revenue"
            if lead else f"Cost lines on record for {company}"
        )
        put("S011_value_chain", {
            "title": _title(title),
            "subtitle": _title(
                "Each share divides that line by accounts revenue for the same year. Segment shares use the workbook."
            ),
            "elements": {
                "table": _table(
                    ["Cost", "Amount", "Share"],
                    [[item["name"], item["amount"], item["share"]] for item in math.costs],
                ),
                "takeaway": _text(
                    "Fleet adds maintenance, fuel, risk management, and other fleet. A cost without an amount is omitted."
                ),
            },
        })

    segments = _spec(_resolve(ctx, "customer_segmentation")).get("segments")
    if isinstance(segments, list):
        rows = []
        cats, vals = [], []
        for seg in segments:
            if not isinstance(seg, dict) or not _filled(seg.get("name")):
                continue
            share = seg.get("share_pct")
            share_txt = f"{float(share):.0f}%" if isinstance(share, (int, float)) else "—"
            rows.append([_clean(seg["name"], 40), share_txt, _clean(seg.get("key_driver") or "", 60)])
            if isinstance(share, (int, float)):
                cats.append(_clean(seg["name"], 24))
                vals.append(float(share))
        econ_rows = []
        for seg in segments:
            if not isinstance(seg, dict) or not _filled(seg.get("name")):
                continue
            detail = seg.get("arr") or seg.get("price") or seg.get("arpu") or seg.get("locations")
            if _filled(detail):
                econ_rows.append([_clean(seg["name"], 40), _clean(detail, 40), _clean(seg.get("locations") or "", 24) or "—"])
        if len(econ_rows) >= 2:
            _bind(book, "economics")
            put("S012_business_model_flow", {
                "title": _title(f"How {company}'s segments are priced and sized, from the segmentation module"),
                "subtitle": _title("Locations, price and ARR are shown only when the module states them."),
                "elements": {
                    "flow": _table(["Segment", "Economics", "Locations"], econ_rows),
                    "right": _bullets([f"{a}: {b}" for a, b, _c in econ_rows]),
                },
            })
        elif len(rows) >= 2:
            _bind(book, "segments")
            put("S013_business_model_comparison", {
                "title": _title(f"{company} is reported in {len(rows)} segments"),
                "subtitle": _title("Shares are shown only when the segmentation module states them."),
                "elements": {
                    "table": _table(["Segment", "Share", "Driver"], rows),
                    "takeaway": _text("A share without a source stays indicated."),
                },
            })
    if len(math.mix) >= 2:
        _bind(book, "segments")
        mix_bits = ", ".join(f"{item['name']} {item['share']:.0f}%" for item in math.mix)
        mix_lead = (
            f"Segment mix for {company}, calculated from segment revenue"
            if math.mix_calculated
            else f"Segment mix for {company}"
        )
        mix_title = f"{mix_lead}: {mix_bits}"
        put("S042_gf2_mix_shift", {
            "title": _title(mix_title if len(mix_title) <= 160 else mix_lead),
            "subtitle": _title(
                "Shares calculated from segment revenue divided by the total."
                if math.mix_calculated
                else "Shares as the segmentation module stated them. This is not a multi-year shift."
            ),
            "elements": {
                "chart": _chart(
                    [item["name"] for item in math.mix],
                    [item["share"] for item in math.mix],
                    "Share %",
                    unit="%",
                    kind="calc" if math.mix_calculated else "fact",
                    point_refs=[
                        item.get("calc_id") or item["id"] for item in math.mix
                    ],
                ),
                "right": _bullets([
                    f"{item['name']}: {item['share']:.1f}% of the total" if math.mix_calculated else f"{item['name']}: {item['share']:.0f}% stated"
                    for item in math.mix[:5]
                ]),
            },
        })
    if math.yoy:
        latest = math.yoy[-1]
        _bind(book, "revenue_actual")
        put("S023_h1_growth_drivers", {
            "title": _title(
                f"Revenue moved {latest['delta']:+,.2f} million from {latest['earlier']} to {latest['later']} ({latest['pct']:+.1f}%)"
            ),
            "subtitle": _title("Each change is later actual revenue minus the prior actual. Plan years are excluded."),
            "elements": {
                "left": _table(
                    ["Step", "$M", "%"],
                    [[f"{row['earlier']} to {row['later']}", f"{row['delta']:+.2f}", f"{row['pct']:+.1f}"] for row in math.yoy],
                ),
                "right": _bullets([
                    f"{row['earlier']} to {row['later']}: {row['delta']:+.2f} million, {row['pct']:+.1f}%."
                    for row in math.yoy
                ]),
            },
        })

    def _real_finding(line: str) -> bool:
        if _is_qa_meta(line):
            return False
        return not re.search(r"(?i)\b0 claimed advantage\b|\b0 external risk\b|internal prior=", line)

    diff = [line for line in _findings(_resolve(ctx, "competitive_differentiation"), 6) if _real_finding(line)][:3]
    risks = [line for line in _findings(_resolve(ctx, "market_risk"), 4) if _real_finding(line)][:2]
    if diff or risks:
        _bind(book, "barriers")
        put("S015_barriers", {
            "title": _title(f"What the record says protects {company}, and what it does not establish"),
            "subtitle": _title("A moat is not adopted from an agent label."),
            "elements": {
                "left": _bullets(diff or ["No differentiation finding on file."]),
                "right": _bullets(risks or ["No risk finding on file."]),
            },
        })
    if math.leaders and "S015_barriers" not in slides:
        _bind_ids([math.leaders[0]["id"]])
        bios = [person for person in math.leaders[:4] if person.get("bio")]
        bio_ids = [person["bio_id"] for person in bios if person.get("bio_id")]
        if bio_ids:
            _bind_ids([math.leaders[0]["id"], *bio_ids])
        ben = next((person for person in math.leaders if person["name"] == "Ben Parry" and "2018" in person.get("bio", "")), None)
        put("S015_barriers", {
            "title": _title(
                "Ben Parry acquired the company in 2018, on the CIM leadership page"
                if ben else
                "The CIM names a leadership team and the biography under each name"
            ),
            "subtitle": _title("The biographies are the CIM's wording. These people were not interviewed."),
            "heads": {
                "left_head": "Name and the CIM biography",
                "right_head": "What this page does not prove",
            },
            "elements": {
                "left": _bullets([
                    _fit_line(
                        f"{person['name']}, {person['role']}. {person['bio'].split('. ')[0].rstrip('.')}."
                        if person.get("bio") else
                        f"{person['name']}, {person['role']}"
                    )
                    for person in math.leaders[:4]
                ]),
                "right": _bullets(
                    [
                        "The 2018 acquisition sentence is the biography under Ben Parry, CEO.",
                        "No interview file was loaded for these names.",
                    ]
                    if ben else
                    [
                        "No interview file was loaded for these names.",
                        "The management module did not return a separate biography.",
                    ]
                ),
            },
        })
    if math.risks:
        _bind(book, "risks")
        put("S049_risk_assessment", {
            "title": _title(f"Risks on record for {company}"),
            "subtitle": _title("Severity is shown only when the risk module states one."),
            "elements": {
                "left": _table(
                    ["Risk", "Severity", "Note"],
                    [[item["name"], item["severity"], item["note"]] for item in math.risks],
                ),
                "right": _bullets([item["name"] for item in math.risks]),
            },
        })

    thesis = _findings(_resolve(ctx, "executive_summary"), 3) or _findings(_resolve(ctx, "recommendations"), 3)
    if thesis:
        _bind(book, "thesis")
        put("S020_highlights_summary", {
            "title": _title(thesis[0]),
            "subtitle": _title("Lead finding. It is not a recommendation to invest."),
            "elements": {"rows": _table(["#", "Finding"], [[str(i + 1), line] for i, line in enumerate(thesis[:5])])},
        })

    metrics = _sizing_metrics(ctx)
    if metrics:
        cats = [label for label, _v in metrics]
        values = []
        for _label, text in metrics:
            match = re.search(r"([\d,.]+)", text)
            values.append(float(match.group(1).replace(",", "")) if match else 0.0)
        joined = ", ".join(f"{label} {value}" for label, value in metrics)
        _bind(book, "sizing")
        put("S021_h1_market_size", {
            "title": _title(f"On the evidenced model the market for {company} is {joined}"),
            "subtitle": _title("TAM, SAM and SOM from the market-volume module."),
            "elements": {
                "chart": _chart(
                    cats,
                    values,
                    "Market",
                    point_refs=book.buckets.get("sizing", [])[: len(cats)],
                ),
                "right": _bullets([f"{label} {value}" for label, value in metrics]),
            },
        })
        if len(math.lines) >= 2:
            _bind(book, "sam_lines")
            put("S037_tam_walkdown", {
                "title": _title(
                    "Serviceable market by line: " + ", ".join(f"{item['name']} {item['value']:.1f}" for item in math.lines)
                ),
                "subtitle": _title("Line figures from the market-volume module. This is not a repeat of the TAM total."),
                "elements": {
                    "chart": _chart(
                        [item["name"] for item in math.lines],
                        [item["value"] for item in math.lines],
                        "Line",
                        point_refs=[item["id"] for item in math.lines],
                    ),
                    "right": _bullets([f"{item['name']}: {item['value']:.1f}" for item in math.lines]),
                },
            })
    if len(math.margins) >= 2:
        _bind(book, "margins")
        last_margin = math.margins[-1]
        put("S045_gf4_pricing_stability", {
            "title": _title(f"Margin on record is {last_margin['value']:.1f}% in {last_margin['label']}"),
            "subtitle": _title("Actual and year-to-date margins only. A plan margin is not on this chart."),
            "elements": {
                "chart": _chart(
                    [f"{item.get('metric') or 'Margin'} {item['label']}" for item in math.margins],
                    [item["value"] for item in math.margins],
                    "Margin %",
                    unit="%",
                    point_refs=[item["id"] for item in math.margins],
                ),
                "right": _bullets([
                    f"{item.get('metric') or 'Margin'} {item['label']}: {item['value']:.1f}%"
                    for item in math.margins[:5]
                ]),
            },
        })
    if math.bridge:
        bridge = math.bridge
        _bind_ids([bridge["actual_id"], bridge["plan_id"]])
        put("S046_sam_growth_build", {
            "title": _title(
                f"The plan at {bridge['plan_label']} is {bridge['multiple']:.2f}x {bridge['actual_label']} revenue, a bridge of {bridge['delta']:+.2f} million"
            ),
            "subtitle": _title("The bridge is plan revenue minus the latest actual. It is not a result."),
            "elements": {
                "left": _table(
                    ["Step", "$M"],
                    [
                        [f"Actual {bridge['actual_label']}", f"{bridge['actual']:.2f}"],
                        [f"Plan {bridge['plan_label']}", f"{bridge['plan']:.2f}"],
                        ["Bridge", f"{bridge['delta']:+.2f}"],
                        ["Multiple", f"{bridge['multiple']:.2f}x"],
                    ],
                ),
                "right": _chart(
                    [bridge["actual_label"], bridge["plan_label"]],
                    [bridge["actual"], bridge["plan"]],
                    "Revenue",
                    point_refs=[bridge["actual_id"], bridge["plan_id"]],
                ),
                "takeaway": _text(f"Multiple {bridge['multiple']:.2f}x is plan divided by the latest actual."),
            },
        })
    if math.bridge and (math.momentum or math.trading):
        bridge = math.bridge
        momentum = math.momentum
        trading = math.trading
        refs = []
        if momentum:
            refs.append(momentum["rate_id"])
        if trading:
            plan = book.by_id.get(bridge["plan_id"]) or {}
            docs = list((plan.get("citations") or {}).get("doc") or [])
            trading_id = book.add(
                module="HPF",
                title="Historical Performance",
                text=(
                    f"Trading case {trading['value']:.2f} million by {bridge['plan_label']}, "
                    "carrying the latest actual growth forward."
                ),
                docs=docs,
                bucket="revenue_plan",
                grade="indicated",
            )
            refs.extend([fid for fid in (trading_id, bridge["plan_id"]) if fid])
            low = trading.get("low") or {}
            if low.get("id"):
                refs.append(low["id"])
        if math.dc_cases and math.dc_cases.get("id"):
            refs.append(math.dc_cases["id"])
        _bind_ids(refs or [bridge["actual_id"], bridge["plan_id"]])
        rows = [[f"Plan {bridge['plan_label']}", f"{bridge['plan']:.2f}"]]
        low = (trading or {}).get("low") or {}
        if trading:
            rows.append([
                f"Latest actual growth carried from {trading['later']} to {trading['plan_label']}",
                f"{trading['value']:.2f}",
            ])
        if low:
            rows.append([
                f"Year-to-date pace at {low['rate']:.1f}% from {trading['later']} to {trading['plan_label']}",
                f"{low['value']:.2f}",
            ])
        if momentum:
            rows.append([
                f"Momentum at {momentum['rate']:.1f}% from {bridge['actual_label']} to {bridge['plan_label']}",
                f"{momentum['value']:.2f}",
            ])
            rows.append(["Plan minus momentum", f"{momentum['gap']:+.2f}"])
        if math.dc_cases:
            rows.extend(math.dc_cases["rows"][: max(0, 9 - len(rows))])
        if trading and low:
            title = (
                f"Recent trading points to {low['value']:.2f} to {trading['value']:.2f} million "
                f"by {trading['plan_label']}"
            )
            subtitle = (
                "The low case carries year-to-date growth forward. "
                "The high case carries the latest full-year growth forward."
            )
        elif trading:
            title = (
                f"Carrying the latest actual growth forward reaches {trading['value']:.2f} million "
                f"by {trading['plan_label']}"
            )
            subtitle = "The plan is the other case. This row only restates the latest year of actual growth."
        else:
            title = (
                f"At the stated market rate of {momentum['rate']:.1f}%, {bridge['actual_label']} revenue "
                f"reaches {momentum['value']:.2f} million by {bridge['plan_label']}"
            )
            subtitle = "Momentum compounds the latest actual at the market rate the module stated. The plan is the other case."
        put("S047_scenario_analysis", {
            "title": _title(title),
            "subtitle": _title(subtitle),
            "elements": {
                "table": _table(["Case", "$M"], rows),
                "takeaway": _text(
                    "Each case is a calculation from figures already on the record. None of them is a result. "
                    "Upside and full contract, when shown, are spectrum cases and are not the plan."
                    if math.dc_cases else
                    "Each case is a calculation from figures already on the record. None of them is a result."
                ),
            },
        })

    forward = math.forward or {}
    dc = forward.get("dc") or {}
    trading_case = math.trading or {}
    low_case = trading_case.get("low") or {}
    if (
        "S049_risk_assessment" not in slides
        and trading_case
        and (low_case or dc)
        and math.bridge
    ):
        bridge = math.bridge
        bits = []
        risk_rows = []
        if low_case:
            risk_rows.append([
                "Plan pace",
                f"{low_case['value']:.2f} to {trading_case['value']:.2f} versus plan {bridge['plan']:.2f}",
                "Neither case is a result",
            ])
            bits.append(
                f"Year-to-date pace {low_case['value']:.2f} million and full-year pace {trading_case['value']:.2f} million, "
                f"against a plan of {bridge['plan']:.2f} million by {bridge['plan_label']}."
            )
        if dc:
            risk_rows.append([
                "Municipal - DC",
                f"{dc['actual']} in {dc['actual_year']}, {dc['mix']} of that workbook",
                f"{dc['plan']} in {dc['plan_year']}",
            ])
            bits.append(
                f"Municipal - DC is {dc['actual']} in {dc['actual_year']}, {dc['mix']} of that workbook, "
                f"and {dc['plan']} in {dc['plan_year']}."
            )
        plan = book.by_id.get(bridge["plan_id"]) or {}
        risk_id = book.add(
            module="HPF",
            title="Historical Performance",
            text=" ".join(bits),
            docs=list((plan.get("citations") or {}).get("doc") or []),
            bucket="risks",
            grade="indicated",
        )
        if risk_id and risk_rows:
            _bind_ids([risk_id])
            put("S049_risk_assessment", {
                "title": _title(
                    f"The plan at {bridge['plan']:.2f} million sits above both trading cases"
                    if low_case else
                    f"Municipal - DC is {dc.get('mix') or dc.get('actual')} of the stated workbook"
                ),
                "subtitle": _title(
                    f"Municipal - DC is {dc['mix']} of {dc['actual_year']} workbook revenue."
                    if dc.get("mix") else
                    "These cases are calculations. Neither one is a result."
                ),
                "heads": {
                    "left_head": "Two risks the files support",
                    "right_head": "What these rows do not prove",
                },
                "elements": {
                    "left": _table(["Risk", "On the record", "Open point"], risk_rows),
                    "right": _bullets([
                        item for item in [
                            "The low case uses the opening months of the latest year against the same months a year earlier."
                            if low_case else "",
                            "The full-year case carries the latest actual growth forward."
                            if low_case else "",
                            "The contract sheet's largest row keeps the workbook's own name."
                            if dc else "",
                        ]
                        if item
                    ]),
                },
            })

    perimeter = _spec(_resolve(ctx, "market_definition")).get("perimeter") or _spec(_resolve(ctx, "market_definition")).get("insight_snapshot")
    if _filled(perimeter) and not _is_ownership_perimeter(str(perimeter)):
        excluded = _spec(_resolve(ctx, "market_definition")).get("excluded") or []
        rows = [["In perimeter", _clean(perimeter, 80)]]
        if isinstance(excluded, list):
            for item in excluded[:3]:
                if _filled(item) and not _is_ownership_perimeter(str(item)) and not _is_cap_table_text(str(item)):
                    rows.append(["Excluded", _clean(item, 80)])
        _bind(book, "perimeter")
        put("S034_market_definitions", {
            "title": _title(f"The market used for {company} is the perimeter in the market-definition module"),
            "subtitle": _title(_clean(perimeter, 150)),
            "elements": {
                "table": _table(["Boundary", "As stated"], rows),
                "takeaway": _text("Agent perimeters that disagree with this page are exceptions."),
            },
        })

    claims = _spec(_resolve(ctx, "competitive_differentiation")).get("differentiators") or []
    if isinstance(claims, list) and claims:
        rows = []
        for item in claims[:6]:
            claim = item.get("claim") or item.get("name") if isinstance(item, dict) else ""
            evidence = item.get("evidence") if isinstance(item, dict) else ""
            if (
                isinstance(item, dict)
                and _filled(claim)
                and not _is_qa_meta(str(claim))
                and not _is_qa_meta(str(evidence or ""))
            ):
                rows.append([
                    _clean(claim, 40),
                    _clean(evidence or "Not in the data room", 60),
                ])
        if rows:
            _bind(book, "claims")
            put("S029_h4_differentiation", {
                "title": _title(f"Which of {company}'s claimed differentiators have a figure behind them"),
                "subtitle": _title("An empty evidence cell is not support."),
                "elements": {
                    "table": _table(["Claim", "Evidence on file"], rows),
                "takeaway": _text("A claim without evidence stays asserted."),
            },
        })
    if math.claims and "S029_h4_differentiation" not in slides:
        _bind_ids([item["id"] for item in math.claims])
        service = next((item for item in math.claims if item["name"] == "On-time service"), None)
        put("S029_h4_differentiation", {
            "title": _title(
                "The CIM states 99.5% on-time and a 70 NPS. No survey file tests either."
                if service else
                "The CIM states these claims. No survey file tests them."
            ),
            "subtitle": _title("Each row is a sentence in the CIM. None of them is a survey result."),
            "elements": {
                "table": _table(
                    ["Claim", "As stated", "Test"],
                    [[item["name"], item["stated"], item["test"]] for item in math.claims],
                ),
                "takeaway": _text("These are statements in the CIM. They are not results of a survey or an interview."),
            },
        })

    peers = _spec(_resolve(ctx, "competitor_identification")).get("competitors") or []
    if isinstance(peers, list):
        rows = []
        for row in peers[:6]:
            if not isinstance(row, dict):
                continue
            name = _clean(row.get("name") or "", 40)
            if not name or name.lower() == company.lower():
                continue
            scope = str(row.get("classification") or row.get("scope") or "").strip()
            outside = row.get("in_geography") is False or bool(re.search(r"(?i)national|out of geography|outside", scope))
            local = row.get("in_geography") is True or bool(re.search(r"(?i)\blocal\b", scope))
            kind = "Outside geography" if outside and not local else (scope or "—")
            geography = _clean(row.get("geography") or "—", 28)
            if outside and not local:
                geography = _clean(f"Outside geography · {geography}", 40)
            rows.append([
                name,
                _clean(kind, 28),
                geography,
                _clean(row.get("overlap") or row.get("note") or "—", 40),
            ])
        if rows:
            _bind(book, "competitors")
            put("S060_competitor_archetypes", {
                "title": _title(f"Named competitors for {company}, with local names kept distinct from the rest"),
                "subtitle": _title("A name the module marks as outside the stated geography is labelled, not treated as local."),
                "elements": {
                    "table": _table(["Competitor", "Type", "Geography", "Overlap"], rows),
                    "takeaway": _text("A name without overlap is still listed, and marked thin."),
                },
            })

    same = _spec(_resolve(ctx, "customer_stickiness")).get("retention_on_same_population")
    same = same if isinstance(same, dict) else {}
    from agetic_cdd_api.report_cdd_deck_v4 import _pct_from
    grr = _pct_from(same.get("grr") if same else _spec(_resolve(ctx, "customer_stickiness")).get("grr"))
    nrr = _pct_from(same.get("nrr") if same else _spec(_resolve(ctx, "customer_stickiness")).get("nrr"))
    if math.retention:
        held = math.retention
        population = _clean(held["population"], 60)
        _bind(book, "retention")
        put("S068_churn_triggers", {
            "title": _title(
                f"On {population}, NRR is {held['nrr']:.1f}% and GRR is {held['grr']:.1f}%, a spread of {held['spread']:+.1f} points"
            ),
            "subtitle": _title("The spread is NRR minus GRR for this one population. It is not a churn survey."),
            "elements": {
                "left": _table(
                    ["Population", "GRR", "NRR", "NRR minus GRR"],
                    [[population, f"{held['grr']:.1f}%", f"{held['nrr']:.1f}%", f"{held['spread']:+.1f}"]],
                ),
                "right": _bullets([
                    f"GRR {held['grr']:.1f}% and NRR {held['nrr']:.1f}% are the module's figures.",
                    f"Spread {held['spread']:+.1f} points is NRR minus GRR.",
                ]),
            },
        })
        if not math.retention_curve:
            put("S079_l3_expand_accounts", {
                "title": _title(f"NRR {held['nrr']:.1f}% against GRR {held['grr']:.1f}% on {population}"),
                "subtitle": _title("One population, two rates. A multi-year curve is withheld until the module stores one."),
                "elements": {
                    "chart": _chart(
                        ["GRR", "NRR"],
                        [held["grr"], held["nrr"]],
                        "Retention %",
                        unit="%",
                        point_refs=[held["grr_id"], held["nrr_id"]],
                    ),
                    "right": _bullets([f"NRR sits {held['spread']:+.1f} points relative to GRR."]),
                },
            })
    elif grr is not None or nrr is not None:
        cats, series_vals, notes = [], [], []
        if grr is not None:
            cats.append("GRR")
            series_vals.append(grr)
            notes.append(f"GRR {grr:.1f}%")
        if nrr is not None:
            cats.append("NRR")
            series_vals.append(nrr)
            notes.append(f"NRR {nrr:.1f}%")
        population = _clean(same.get("population") or "the stated population", 60)
        _bind(book, "retention")
        put("S044_gf3_channel_stickiness", {
            "title": _title(f"Retention for {company} on {population}"),
            "subtitle": _title("Gross and net retention for one population only."),
            "elements": {
                "chart": _chart(cats, series_vals, "Retention %", unit="%"),
                "right": _bullets(notes),
            },
        })
    if math.retention_curve:
        curve = math.retention_curve
        _bind_ids([fid for series in curve["series"] for fid in series["point_refs"]])
        nrr_series = next((series for series in curve["series"] if series.get("name") == "NRR"), None)
        nrr_values = list((nrr_series or {}).get("values") or [])
        if len(nrr_values) >= 2:
            curve_title = (
                f"NRR moved from {nrr_values[0]:.1f}% in {curve['categories'][0]} "
                f"to {nrr_values[-1]:.1f}% in {curve['categories'][-1]}"
            )
        else:
            curve_title = f"Retention by year on {curve['population']}"
        put("S079_l3_expand_accounts", {
            "title": _title(curve_title),
            "subtitle": _title("Each point is the rate stored for that year. A missing year is not interpolated."),
            "elements": {
                "chart": _chart(
                    curve["categories"],
                    [],
                    "Retention",
                    unit="%",
                    series=curve["series"],
                ),
                "right": _bullets([
                    "The chart uses the yearly rates on file.",
                    "Plan years are not added to this curve.",
                ]),
            },
        })

    if math.lever_dollars:
        dollars = math.lever_dollars
        _bind(book, "lever_amounts")
        amount_rows = [
            [
                item["name"],
                f"{item['actual']:.2f}",
                f"{item['plan']:.2f}",
                f"{item['delta']:+.2f}",
                f"{item['share']:.1f}%" if item["share"] is not None else "—",
            ]
            for item in dollars["rows"]
        ]
        amount_rows.append(["Total", "—", "—", f"{dollars['total']:+.2f}", "—"])
        put("S072_growth_levers_overview", {
            "title": _title(f"The plan increment across these levers is {dollars['total']:+.2f} million"),
            "subtitle": _title(
                f"Each increment is plan {dollars['plan_label']} minus actual {dollars['actual_label']}. "
                "A lever without both figures is left out of the total."
            ),
            "elements": {
                "rows": _table(["Lever", dollars["actual_label"], dollars["plan_label"], "Increment", "Share"], amount_rows),
            },
        })
    levers = _spec(_resolve(ctx, "growth_opportunities")).get("levers") or []
    if not math.lever_dollars and isinstance(levers, list) and levers:
        rows = []
        for lever in levers[:6]:
            if (
                isinstance(lever, dict)
                and _filled(lever.get("name") or lever.get("lever"))
                and not _is_qa_meta(str(lever.get("name") or lever.get("lever") or ""))
                and not _is_qa_meta(str(lever.get("effect") or lever.get("evidence") or ""))
            ):
                rows.append([
                    _clean(lever.get("name") or lever.get("lever"), 40),
                    _clean(lever.get("effect") or lever.get("evidence") or "Untested", 60),
                ])
        if rows:
            _bind(book, "levers")
            put("S072_growth_levers_overview", {
                "title": _title(f"Growth levers for {company}, with the effect the module states"),
                "subtitle": _title("A lever without a figure is untested."),
                "elements": {"rows": _table(["Lever", "Effect on file"], rows)},
            })
    if math.forward and "S072_growth_levers_overview" not in slides:
        dc_line = (math.forward or {}).get("dc") or {}
        utica_line = (math.forward or {}).get("utica") or {}
        step = next((item for item in math.claims if item["name"] == "Rate step-up"), None)
        lever_rows = []
        lever_ids = []
        if dc_line.get("id"):
            lever_rows.append([
                "Municipal - DC",
                f"{dc_line['actual']} in {dc_line['actual_year']}; {dc_line['plan']} in {dc_line['plan_year']}",
                dc_line.get("mix") or "—",
            ])
            lever_ids.append(dc_line["id"])
        if utica_line.get("id"):
            lever_rows.append([
                "Utica",
                f"{utica_line['early']} in {utica_line['early_year']}",
                f"{utica_line['plan']} in {utica_line['plan_year']}",
            ])
            lever_ids.append(utica_line["id"])
        if step:
            lever_rows.append(["Rate step-up", step["stated"], step["test"]])
            lever_ids.append(step["id"])
        if math.quotas and math.quotas.get("reps") is not None:
            lever_rows.append([
                "Sales capacity",
                f"Latest new logos equal {math.quotas['reps']:.1f} of one quota",
                "Not a bookings record",
            ])
            for calc in math.calculations:
                if calc.id == "CALC-LOGO-QUOTA" and "S072_growth_levers_overview" not in calc.used_on:
                    calc.used_on.append("S072_growth_levers_overview")
        if math.deals and math.deals.get("split_id"):
            lever_rows.append([
                "Agricity",
                "About $1.2M subcontract and $1.6M own book",
                "Not added to company revenue",
            ])
            lever_ids.append(math.deals["split_id"])
        if len(lever_rows) >= 2:
            _bind_ids(lever_ids)
            put("S072_growth_levers_overview", {
                "title": _title(
                    f"Municipal - DC is {dc_line['mix']} of {dc_line['actual_year']} workbook revenue"
                    if dc_line.get("mix") else
                    "The stated growth levers are plan figures, not a commitment"
                ),
                "subtitle": _title("Each line is stated in the workbook or the CIM. None of them is a result."),
                "elements": {
                    "rows": _table(["Lever", "On the record", "Not established"], lever_rows),
                },
            })

    if math.assessment:
        assessment_ids = list(math.assessment["ids"])
        if math.picture and math.picture.get("id"):
            assessment_ids.append(math.picture["id"])
        _bind_ids(assessment_ids)
        put("S062_criteria_vs_archetypes", {
            "title": _title(
                f"Pictures on the CIM competitive page are described as {math.picture['name']}"
                if math.picture else
                f"Management's comparison of {company} with the alternatives it named"
            ),
            "subtitle": _title("Shown once, as a self-assessment. Yes and no are the marks on the record."),
            "elements": {
                "table": _table(math.assessment["columns"], math.assessment["rows"]),
                "takeaway": _text(
                    (
                        "The CIM also scores " + ", ".join(math.assessment["omitted"]) + ". That column is not on this page."
                        if math.assessment.get("omitted")
                        else "This is management's self-assessment. It is not customer evidence."
                    )
                    + (
                        " Local operating companies read outside the data room are on the competitor page. This matrix does not name them."
                        if math.web_competitors else
                        " The table does not name local operating companies."
                    )
                    + (
                        f" Pictures on that page are described as {math.picture['name']}."
                        if math.picture else ""
                    )
                ),
            },
        })
    if math.prices:
        prices = math.prices
        _bind_ids([point["id"] for point in prices["points"]])
        gap = prices["gap"]
        put("S064_price_benchmarking", {
            "title": _title(
                f"On a {prices['unit']} basis the company price is {gap['value']:+.1f}% versus {gap['peer']}"
                if gap else
                f"Prices the market-pricing module stated, all on a {prices['unit']} basis"
            ),
            "subtitle": _title("Only prices that share one unit are plotted. A different basis is not converted."),
            "heads": {
                "chart_head": "Prices on one basis",
                "right_head": "What the comparison does not prove",
            },
            "elements": {
                "chart": _chart(
                    [point["name"] for point in prices["points"]],
                    [point["value"] for point in prices["points"]],
                    prices["unit"],
                    unit=prices["unit"],
                    point_refs=[point["id"] for point in prices["points"]],
                ),
                "right": _bullets([
                    f"{point['name']}: {point['value']:.2f}" for point in prices["points"][:4]
                ] + ["The gap, when shown, is the company price divided by the first peer price, minus one."]),
            },
        })
    elif math.unit_basis and math.unit_basis.get("price"):
        price_row = next((row for row in math.unit_basis["rows"] if row[0] == "Price per month"), None)
        if price_row and len(price_row) >= 4:
            points = []
            for label, raw in zip(("Commercial", "Municipal", "Residential"), price_row[1:4]):
                match = re.search(r"\d+(?:\.\d+)?", str(raw).replace(",", ""))
                if match:
                    points.append((label, raw, float(match.group(0))))
            source = book.by_id.get((math.unit_basis.get("ids") or [""])[0]) or {}
            docs = list((source.get("citations") or {}).get("doc") or [])
            if len(points) >= 2 and docs:
                fid = book.add(
                    module="CST",
                    title="Customer Stickiness",
                    text="Price per month. " + ". ".join(f"{label} {raw}" for label, raw, _amount in points) + ".",
                    docs=docs,
                    bucket="prices",
                    grade="established",
                )
                if fid:
                    book.by_id[fid]["cells"] = {label: raw for label, raw, _amount in points}
                    book.by_id[fid]["row_label"] = "Price per month"
                    _bind_ids([fid])
                    put("S064_price_benchmarking", {
                        "title": _title(
                            f"Residential price on the existing book is {math.unit_basis['price']} a month"
                        ),
                        "subtitle": _title(
                            "Workbook prices only. A web list price is outside the data room and is not in this chart."
                            if math.web_competitors else
                            "No third-party local price was in the loaded files."
                        ),
                        "heads": {
                            "chart_head": "Prices on the workbook row",
                            "right_head": "Workbook prices only" if math.web_competitors else "No outside price was loaded",
                        },
                        "elements": {
                            "chart": _chart(
                                [label for label, _raw, _amount in points],
                                [amount for _label, _raw, amount in points],
                                "Price",
                                unit="$",
                                point_refs=[fid for _ in points],
                            ),
                            "right": _bullets([f"{label}: {raw}" for label, raw, _amount in points]),
                        },
                    })
    if math.logos:
        logos = math.logos
        logo_ids = list(logos["new_ids"] + logos["churn_ids"])
        net_bits = ", ".join(f"{item['value']:.0f} in {item['label']}" for item in logos["nets"])
        logo_notes = [f"Net additions are new logos minus churned logos: {net_bits}."]
        if math.quotas and math.quotas.get("reps") is not None:
            logo_notes.append(f"The latest new-logo count equals {math.quotas['reps']:.1f} of the stated quota.")
        active = logos.get("active") or {}
        if active.get("id"):
            logo_ids.append(active["id"])
            logo_notes.append(
                f"Active accounts were {active['count']} in {active['year']} "
                f"and {active['later']} at {active['later_label']}."
            )
        _bind_ids(logo_ids)
        latest_year = logos["categories"][-1]
        latest_net = next((item["value"] for item in logos["nets"] if item["label"] == latest_year), None)
        scope = (
            "Commercial new logos"
            if re.search(r"commercial", str(logos.get("section") or ""), re.I)
            else "New logos"
        )
        if latest_net is not None:
            logo_title = (
                f"{scope} were {logos['new'][-1]:.0f} in {latest_year} and churned logos were "
                f"{logos['churned'][-1]:.0f}, a net of {latest_net:.0f}"
            )
        elif math.quotas and math.quotas.get("reps") is not None:
            logo_title = f"Latest new logos equal {math.quotas['reps']:.1f} of one stated quota"
        else:
            logo_title = f"New and churned logos for {company}, from the years on record"
        put("S073_l1_new_customers", {
            "title": _title(logo_title),
            "subtitle": _title("Net additions are new logos minus churned logos. A year with only one of the two is omitted."),
            "elements": {
                "chart": _chart(
                    logos["categories"],
                    [],
                    "Logos",
                    unit="logos",
                    series=[
                        {"name": "New logos", "values": logos["new"], "point_refs": logos["new_ids"]},
                        {"name": "Churned logos", "values": logos["churned"], "point_refs": logos["churn_ids"]},
                    ],
                ),
                "right": _bullets(logo_notes),
            },
        })
    if math.quotas:
        _bind_ids([row["id"] for row in math.quotas["rows"]])
        quota_notes = ["Quotas are the plan's figures. They are not a record of what the current team sells."]
        if math.quotas.get("reps") is not None:
            quota_notes.append(f"Latest new logos equal {math.quotas['reps']:.1f} of the stated quota.")
        rep_row = next((row for row in math.quotas["rows"] if re.search(r"(?i)sales rep", row["driver"])), None)
        rep_span = re.findall(r"\d+", rep_row["baseline"]) if rep_row and len(re.findall(r"\d+", rep_row["baseline"])) >= 2 else None
        if rep_row:
            growth_span = re.findall(r"\d+", rep_row["growth_case"])
            if len(growth_span) >= 2:
                quota_notes.append(f"The growth case takes those reps from {growth_span[0]} to {growth_span[1]}.")
        ramp = next((row for row in math.quotas["rows"] if re.search(r"(?i)ramp", row["driver"])), None)
        if ramp:
            quota_notes.append(f"Ramp on the record: {ramp['baseline']}. Growth case: {ramp['growth_case']}.")
        marketing = next((row for row in math.quotas["rows"] if re.search(r"(?i)marketing", row["driver"])), None)
        if marketing:
            quota_notes.append(
                f"Marketing on the record: {marketing['baseline']}. Growth case: {marketing['growth_case']}."
            )
        put("S075_l1_channel_expansion", {
            "title": _title(
                f"The plan takes quota-carrying reps from {rep_span[0]} to {rep_span[1]}. No bookings history was loaded."
                if rep_span else
                (
                    f"The latest new-logo count is {math.quotas['reps']:.1f} times one stated quota"
                    if math.quotas.get("reps") is not None else
                    f"Sales quotas stated for {company}"
                )
            ),
            "subtitle": _title("Each row is a quota the growth record stored. A missing productivity history is not filled in."),
            "heads": {
                "left_head": "Quotas on the record",
                "right_head": "What the quota does not prove",
            },
            "elements": {
                "left": _table(
                    ["Driver", "Baseline", "Growth case"],
                    [[row["driver"], row["baseline"], row["growth_case"]] for row in math.quotas["rows"]],
                ),
                "right": _bullets(quota_notes[:5]),
            },
        })
    if math.zips:
        _bind_ids(math.zips["ids"])
        best_zip = None
        best_score = None
        for zip_row in math.zips["rows"]:
            try:
                score = float(zip_row[4])
            except (TypeError, ValueError, IndexError):
                continue
            if best_score is None or score > best_score:
                best_score = score
                best_zip = zip_row
        put("S081_l5_adjacent_segments", {
            "title": _title(
                (
                    f"{str(best_zip[1]).title()} {best_zip[3]} scores {best_zip[4]}, "
                    + (
                        "ahead of the Montgomery zips on this page"
                        if any(str(row[2]).lower() == "montgomery" for row in math.zips["rows"])
                        and str(best_zip[2]).lower() != "montgomery"
                        else "the highest on this page"
                    )
                )
                if best_zip else
                f"ZIP scores on record for {company}"
            ),
            "subtitle": _title(
                "Maryland is the summary ranking. Northern Virginia is the ranking block on the same workbook."
                if math.zips.get("virginia")
                else "The company's scoring model, highest score first."
            ),
            "elements": {
                "table": _table(["Territory", "Area", "County", "ZIP", "Score"], math.zips["rows"]),
                "takeaway": _text("A score ranks where to go. It is not a revenue figure."),
            },
        })
    if math.initiatives:
        items = math.initiatives["rows"]
        share = math.initiatives["share"]
        _bind_ids([row["id"] for row in items] + ([share["id"]] if share else []))
        init_rows = []
        notes = []
        for row in items:
            init_rows.append([
                row["name"],
                row["status"],
                f"{row['actual']:.2f}" if row["actual"] is not None else "—",
                f"{row['plan']:.2f}" if row["plan"] is not None else "—",
                f"{row['delta']:+.2f}" if row.get("delta") is not None else "—",
            ])
            if row.get("cagr") is not None:
                notes.append(f"{row['name']} compounds at {row['cagr']:.1f}% a year between the stated years.")
        if not notes:
            notes = ["A change is plan minus actual. A missing figure stays blank."]
        put("S082_l6_product_expansion", {
            "title": _title(
                f"Named initiatives are {share['value']:.1f}% of the stated revenue total"
                if share else
                f"Initiatives on record for {company}"
            ),
            "subtitle": _title("Status, actual and plan are shown only where the module stored them."),
            "elements": {
                "left": _table(["Initiative", "Status", "Actual", "Plan", "Change"], init_rows),
                "right": _bullets(notes[:4]),
            },
        })
    products = (math.forward or {}).get("products") or {}
    if products.get("lines") and "S082_l6_product_expansion" not in slides:
        product_ids = [line["id"] for line in products["lines"] if line.get("id")]
        if products.get("revenue_id"):
            product_ids.append(products["revenue_id"])
        _bind_ids(product_ids)
        put("S082_l6_product_expansion", {
            "title": _title(
                f"Utica and Key Compostables are {products['now']:.1f}% of 2025 workbook revenue "
                f"and {products['later']:.1f}% of the 2030 plan"
                if products.get("now") is not None and products.get("later") is not None else
                f"Utica and the product lines on the segment sheet for {company}"
            ),
            "subtitle": _title("Each amount is the segment sheet. The shares use workbook revenue for the same year."),
            "heads": {
                "left_head": "Lines on the segment sheet",
                "right_head": "What is not established",
            },
            "elements": {
                "left": _table(
                    ["Line", "2025", "2030P"],
                    [[line["name"], line["actual"], line["plan"]] for line in products["lines"]],
                ),
                "right": _bullets([
                    "Utica is zero in 2025 on this sheet. Its plan amount is not a result.",
                    "A permit and a grant are not a facility profit and loss.",
                ]),
            },
        })
    if math.deals:
        _bind_ids([row["id"] for row in math.deals["rows"]])
        deal_rows = []
        residual_notes = []
        for row in math.deals["rows"]:
            terms = (
                f"{row['price']:.2f} at {row['multiple']:.2f}x"
                if row["price"] is not None and row["multiple"] else
                "—"
            )
            deal_rows.append([
                row["name"],
                row["status"],
                row["scale"],
                row.get("terms_text") or terms,
                f"{row['implied']:.2f}" if row["implied"] is not None else "—",
            ])
            if row["residual"] is not None:
                residual_notes.append(
                    f"{row['name']}: stated effect minus implied earnings is {row['residual']:+.2f} million."
                )
    if len(math.price_moves) >= 2:
        _bind_ids([row["id"] for row in math.price_moves])
        put("S080_l4_pricing", {
            "title": _title(
                f"Stated prices moved {math.price_moves[0]['change']:+.1f}% on {math.price_moves[0]['name']}"
            ),
            "subtitle": _title("Each change is the later stated price divided by the earlier one. It is not a commitment to raise price."),
            "elements": {
                "left": _table(
                    ["Lever", "Prior", "Current", "Change"],
                    [
                        [row["name"], f"{row['prior']:.2f}", f"{row['current']:.2f}", f"{row['change']:+.1f}%"]
                        for row in math.price_moves
                    ],
                ),
                "right": _bullets([
                    f"{row['name']}: {row['prior']:.2f} to {row['current']:.2f}, {row['change']:+.1f}%."
                    for row in math.price_moves[:4]
                ]),
            },
        })
    if math.deals:
        deal_ids = [row["id"] for row in math.deals["rows"]]
        if math.deals.get("note_id"):
            deal_ids.append(math.deals["note_id"])
        economics = math.deals.get("economics") or {}
        if economics.get("id"):
            deal_ids.append(economics["id"])
            term_bits = [f"${economics['price']:.1f}M at {economics['multiple']:.1f}x"]
            if economics.get("cash") is not None:
                term_bits.append(f"cash ${economics['cash']:.1f}M")
            if economics.get("note_k") is not None:
                term_bits.append(f"note ${economics['note_k']:.0f}k")
            if economics.get("equity") is not None:
                term_bits.append(f"{economics['equity']:.0f}% equity")
            if economics.get("warrant") is not None:
                term_bits.append(f"{economics['warrant']:.1f}% warrants")
            deal_rows = deal_rows[:7]
            deal_rows.append([
                "Bought earnings",
                "Proposed",
                "Price and multiple",
                "; ".join(term_bits),
                f"{economics['implied']:.2f}",
            ])
            if economics.get("insource") is not None:
                deal_rows.append([
                    "In-sourced margin",
                    "CIM",
                    "Stated separately",
                    f"${economics['insource']:.1f}M a year",
                    "—",
                ])
        _bind_ids(deal_ids)
        if economics.get("id"):
            deal_title = (
                f"The stated {economics['stated']:.1f} million EBITDA effect exceeds the "
                f"{economics['implied']:.2f} million implied by the price and multiple."
            )
            deal_note = (
                f"Implied earnings are {economics['implied']:.2f} million. "
                f"Stated EBITDA effect minus that figure is {economics['residual']:.2f} million."
            )
            if economics.get("insource") is not None:
                deal_note += (
                    f" The CIM also states {economics['insource']:.1f} million a year of in-sourced margin. "
                    "The two are not added together."
                )
        else:
            deal_title = (
                "The CIM states an acquisition. Stated revenue is not added to company revenue on this page."
                if math.deals.get("note") or math.deals.get("split") else
                f"Acquisitions on record for {company}"
            )
            deal_note = (
                math.deals["note"]
                if math.deals.get("note") else
                (
                    " ".join(residual_notes)
                    if residual_notes else
                    "A price without a multiple is not converted into earnings. Cost and capex are not deducted."
                )
            )
        put("S083_l7_ma", {
            "title": _title(deal_title),
            "subtitle": _title("Implied earnings are the stated price divided by the stated multiple."),
            "elements": {
                "table": _table(["Target", "Status", "Scale", "Terms", "Implied"], deal_rows),
            "takeaway": _text(deal_note),
            },
        })

    if math.method_core:
        _bind_ids([row["id"] for row in math.method_core])
        put("S089_sizing_method_core", {
            "title": _title(f"How the {company} sizing was built, from the current-territory workbook"),
            "subtitle": _title("Each line is the market model's stated count, price and participation."),
            "elements": {
                "flow": _table(["Line", "As stated"], [[row["name"], row["basis"]] for row in math.method_core]),
                "right": _bullets(["These steps are read from the market workbook. A securities ledger is not a customer count."]),
            },
        })
    bottom = None if math.method_core else _spec(_resolve(ctx, "market_volume_and_growth")).get("bottom_up")
    if isinstance(bottom, dict) and any(_filled(bottom.get(k)) for k in ("units", "arithmetic", "bottom_up_size")):
        rows = []
        for key, label in (
            ("units", "Units"),
            ("capture_share", "Capture"),
            ("realised_price", "Price"),
            ("arithmetic", "Arithmetic"),
            ("bottom_up_size", "Bottom-up size"),
        ):
            if _filled(bottom.get(key)) and not _is_ledger_sizing_text(str(bottom.get(key))):
                rows.append([label, _clean(bottom.get(key), 80)])
        for step in math.haircuts:
            rows.append([f"After haircut {step['step']}", f"{step['output']:.2f} million at {step['rate']:.1f}%"])
        if rows:
            _bind(book, "bottom_up")
            put("S089_sizing_method_core", {
                "title": _title(f"How the {company} sizing was built, from the bottom-up record"),
                "subtitle": _title("Every SOM figure moves with these assumptions."),
                "elements": {
                    "flow": _table(["Step", "On record"], rows),
                    "right": _bullets([
                        "A stated haircut is applied only when the record also gives a money base."
                        if math.haircuts
                        else "Steps are the module's bottom-up record.",
                        "A haircut rate without a money base is not applied.",
                    ]),
                },
            })

    if math.method_adjacent and not math.adjacent:
        _bind_ids([row["id"] for row in math.method_adjacent])
        put("S090_sizing_method_adjacent", {
            "title": _title(f"Adjacent lines for {company} are sized in the same workbook"),
            "subtitle": _title("Product lines sit beside the core collection build. Each keeps the basis the workbook stated."),
            "elements": {
                "flow": _table(["Line", "As stated"], [[row["name"], row["basis"]] for row in math.method_adjacent]),
                "right": _bullets(["A capture ratio is shown only when the workbook also states that line's sales."]),
            },
        })
    if len(math.adjacent) >= 2:
        _bind_ids([row["id"] for row in math.adjacent])
        notes = []
        flow = []
        for row in math.adjacent:
            actual = f"{row['actual']:.2f}" if row["actual"] is not None else "—"
            flow.append([row["name"], _clean(row["basis"], 70), f"{row['som']:.2f}", actual])
            if row["capture"] is not None:
                notes.append(f"{row['name']}: stated sales are {row['capture']:.1f}% of that line's SOM.")
        put("S090_sizing_method_adjacent", {
            "title": _title(f"Adjacent lines for {company} are sized apart from the core market"),
            "subtitle": _title("Each line keeps the basis and the SOM the market module stated."),
            "elements": {
                "flow": _table(["Line", "Basis", "SOM", "Actual"], flow),
                "right": _bullets(notes or ["No stated sales were given, so no capture ratio is calculated."]),
            },
        })

    adjusted = verdict_rows(ctx, book.facts)
    _put_room_slides(slides, put, math, company)
    bridge = math.segment_bridge
    if bridge and "S040_growth_factors_overview" not in slides:
        _bind_ids(bridge["ids"])
        put("S040_growth_factors_overview", {
            "title": _title(bridge["title"]),
            "subtitle": _title(bridge["subtitle"]),
            "elements": {"rows": _table(bridge["columns"], bridge["rows"])},
        })
    elif bridge:
        math.calculations = [
            calc for calc in math.calculations
            if not calc.id.startswith("CALC-SEG-") and not calc.id.startswith("CALC-MUNI-")
        ]
    panel_heads = {
        "S009_company_snapshot": {"left_head": "Figures on the accounts", "right_head": "Revenue for those years"},
        "S010_platform_evolution": {"flow_head": "Milestones the CIM states", "right_head": "What the page does not prove"},
        "S023_h1_growth_drivers": {"left_head": "Change in accounts revenue", "right_head": "How the change was calculated"},
        "S042_gf2_mix_shift": {"chart_head": "Share of workbook revenue", "right_head": "Each share uses that year's total"},
        "S045_gf4_pricing_stability": {"chart_head": "Margin on the accounts", "right_head": "Not a pricing study"},
        "S046_sam_growth_build": {"left_head": "Plan versus latest actual", "right_head": "The bridge is not a result"},
        "S073_l1_new_customers": {"chart_head": "New and churned logos", "right_head": "Net additions on record"},
        "S079_l3_expand_accounts": {"chart_head": "Retention by year", "right_head": "The rate stored for that year"},
        "S089_sizing_method_core": {"flow_head": "How the sizing was built", "right_head": "What the workbook states"},
        "S090_sizing_method_adjacent": {"flow_head": "Adjacent lines in the workbook", "right_head": "What is not a capture ratio"},
    }
    for sid, heads in panel_heads.items():
        page = slides.get(sid)
        if isinstance(page, dict) and not page.get("heads"):
            page["heads"] = heads

    if adjusted:
        blocked = [row for row in adjusted if row["adjusted"] == "Blocked"]
        visible = [row for row in adjusted if row["adjusted"] != "Blocked"]
        if blocked:
            visible.insert(0, {
                "module": f"{len(blocked)} modules",
                "stated": "BLOCKED",
                "adjusted": "Blocked",
                "basis": "Findings from a blocked module are not relied on.",
            })
        method_ids = book.buckets.get("method") or []
        audit_docs = list((book.by_id[method_ids[0]].get("citations") or {}).get("doc") or []) if method_ids else []
        verdict_ids = []
        for row in visible:
            fid = book.add(
                module="SCM",
                title="Scope & Methodology",
                text=f"Verdict {row['module']}. Stated {row['stated']}. Adjusted {row['adjusted']}. {row['basis']}",
                docs=audit_docs,
                bucket="verdicts",
                grade="indicated",
            )
            if fid:
                verdict_ids.append(fid)
        _bind_ids(verdict_ids)
        slides["S099_module_verdicts"] = _paged(
            "Module verdicts restated at the grade the facts support",
            "A stated pass is lowered when the facts are thinner than the module claimed.",
            ["Module", "Stated", "Adjusted", "Basis"],
            [[row["module"], row["stated"], row["adjusted"], row["basis"]] for row in visible],
            "The adjusted grade is the one this report uses. It is not raised above the facts.",
        )
        filled.add("S099_module_verdicts")

    source_rows = book.source_rows(limit=24)
    if source_rows:
        read_from_room = any(how.startswith("Read") for _doc, how, _fid in source_rows)
        cited_only = any(not how.startswith("Read") for _doc, how, _fid in source_rows)
        source_display: list[list[str]] = []
        source_ids: list[str] = []
        cited_names: list[str] = []
        for doc, how, _fid in source_rows:
            if not how.startswith("Read"):
                cited_names.append(doc)
                continue
            fid = book.add(
                module="SCM",
                title="Scope & Methodology",
                text=f"Source file {doc}. How used: Read.",
                docs=[doc],
                bucket="sources",
                grade="indicated",
            )
            if not fid:
                continue
            source_display.append([doc, "Read"])
            source_ids.append(fid)
        if cited_names:
            fid = book.add(
                module="SCM",
                title="Scope & Methodology",
                text="Other files were named by a module and were not read as a workbook.",
                docs=cited_names[:6],
                bucket="sources",
                grade="indicated",
            )
            if fid:
                source_display.append(["Other named files", "Cited only"])
                source_ids.append(fid)
        _bind_ids(source_ids)
        slides["S100_source_register"] = _paged(
            "Sources the report rests on, read from the room or only cited",
            "Read means the workbook was extracted. Cited only means a module named the file.",
            ["Source", "How used"],
            source_display,
            " ".join(
                part for part in (
                    "Read means the workbook was extracted into the evidence register." if read_from_room else "",
                    "Cited only means the file was named by a module and was not read as a workbook." if cited_only else "",
                )
                if part
            ),
            row_ids=source_ids,
        )
        filled.add("S100_source_register")

    _bind(book, "method")
    put("S097_back_cover", {
        "elements": {
            "back_contact": _text(
                f"DiligenceIQ · Commercial due diligence on {company}. Draft for discussion, {today}."
            ),
        },
    })

    gaps = audit_exceptions(ctx, book.facts, math, slides)
    gaps.extend(_withheld_page_gaps(skill_dir(), filled))
    method_ids = book.buckets.get("method") or []
    audit_docs = list((book.by_id[method_ids[0]].get("citations") or {}).get("doc") or []) if method_ids else []
    gap_ids = []
    for gap in gaps:
        slide_label = str((gap.get("slides") or ["—"])[0]).split("_", 1)[0]
        fid = book.add(
            module="SCM",
            title="Scope & Methodology",
            text=(
                f"Exception {gap['severity']}. Rule {gap.get('rule') or '—'}. "
                f"Slide {slide_label}. {gap['issue']} {gap['treatment']}"
            ),
            docs=audit_docs,
            bucket="exceptions",
            grade="indicated",
        )
        if fid:
            gap_ids.append(fid)
            gap["id"] = fid
    _bind_ids(gap_ids)
    slides["S101_exceptions"] = _paged(
        "What this report could not establish",
        "Each row is a gap in the record. A withheld template page is not, by itself, a finding.",
        ["Severity", "Rule", "Gap", "Slide", "Treatment"],
        [[
            gap["severity"],
            gap.get("rule") or "—",
            gap["issue"],
            str((gap.get("slides") or ["—"])[0]).split("_", 1)[0],
            gap["treatment"],
        ] for gap in gaps],
        "The adjusted verdicts and the source register are the other half of this audit.",
        size=8,
    )
    filled.add("S101_exceptions")
    glossary = _glossary_terms(ctx, slides)
    if glossary:
        pages = []
        for start in range(0, len(glossary), 10):
            chunk = glossary[start:start + 10]
            pages.append({
                "title": {"text": "Terms used in this report", "refs": ["RUN:glossary"], "kind": "fact"},
                "subtitle": {
                    "text": "A term is listed only when it appears in this report. Plan years carry a P suffix.",
                    "refs": ["RUN:glossary"],
                    "kind": "fact",
                },
                "elements": {
                    "table": {
                        "type": "table",
                        "columns": ["Term", "Meaning in this report"],
                        "rows": [[term, _clean(meaning, 140)] for term, meaning in chunk],
                        "row_refs": [["RUN:glossary"] for _ in chunk],
                    },
                    "takeaway": {
                        "type": "text",
                        "text": "A term that does not appear in the report is not defined here.",
                        "refs": ["RUN:glossary"],
                        "kind": "fact",
                    },
                },
            })
        slides["S007_glossary"] = pages[0] if len(pages) == 1 else pages
        filled.add("S007_glossary")

    skill = skill_dir()
    sm = yaml.safe_load((skill / "config" / "slide_map.yaml").read_text())
    divider_ids = {slide["id"] for slide in sm["slides"] if slide.get("archetype") == "divider"}
    keep = filled | {"S004_contents", "S101_exceptions"} | divider_ids
    withhold = [
        {"id": sid, "exception": "E1-NOT-PROVIDED", "reason": "No exhibit in the loaded modules for this page."}
        for sid in _slide_ids(skill)
        if sid not in keep
    ]

    content = {
        "project": {
            "name": company,
            "target": company,
            "client": "DiligenceIQ",
            "date": today,
            "status": "Draft for discussion",
            "footer": f"{company} · Commercial due diligence · Draft for discussion",
        },
        "slides": slides,
        "withhold": withhold,
        "calculations": math.payload(),
        "exceptions": [
            {
                "severity": gap["severity"],
                "issue": gap["issue"],
                "slides": gap["slides"],
                "source": gap.get("id") or book.refs("method")[0],
                "treatment": gap["treatment"],
            }
            for gap in gaps
        ],
    }
    return content, withhold


def _glossary_terms(ctx: BuildContext, slides: dict[str, Any]) -> list[tuple[str, str]]:
    raw = yaml.safe_load((skill_dir() / "config" / "glossary.yaml").read_text())
    terms = dict(raw.get("terms") or {})
    for agent in ctx.agent_outputs.values():
        extra = _spec(agent).get("glossary") if isinstance(agent, dict) else None
        if isinstance(extra, dict):
            terms.update({str(key): str(value) for key, value in extra.items()})
    return glossary_terms(slide_blob(slides), terms)


def render_cdd_with_skill(ctx: BuildContext, out_path: Path) -> None:
    skill = skill_dir()
    renderer = skill / "scripts" / "render_deck.py"
    template = skill / "assets" / "cdd_template.pptx"
    if not renderer.is_file() or not template.is_file():
        raise FileNotFoundError(f"CDD template renderer is not at {skill}")
    work = out_path.parent / "_cdd_skill_work"
    work.mkdir(parents=True, exist_ok=True)
    book = prepare_evidence(ctx, work)
    content, _withheld = build_skill_content(ctx, book)
    (work / "content.json").write_text(json.dumps(content), encoding="utf-8")
    (work / "evidence.json").write_text(json.dumps({"facts": book.facts}), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(renderer),
            "--content", str(work / "content.json"),
            "--work", str(work),
            "--out", str(out_path),
            "--template", str(template),
        ],
        check=True,
        cwd=str(skill),
    )
