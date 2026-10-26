"""Deck-level content rules (evidence integrity, claim strength, structure, IC readiness).

    chart_audit        every plotted value equals the parsed value of the evidence cell it cites,
                       on one unit/scale basis; ranges and missing values are never plotted as
                       points; forecast categories stay labelled as forecast.
    claim_strength     strong claims ("Invest", "high moat", "competitive pricing", "leader")
                       only where the slide's evidence grade supports them (config/claim_rules.yaml).
    truncation         no "…", no word cut mid-way ("afte."), no dangling heading fragment.
    repetition         the same table, bullet or title may not appear on two slides; the
                       duplicate must be consolidated.
    completeness       a slide that is mostly "insufficient" panels is unfinished: withhold it or
                       complete it; disclaimer and glossary must carry real text.

Each rule returns a list of (where, message, severity) with severity "e" or "w".
"""
from __future__ import annotations

import json
import re
from collections import defaultdict

from .values import parse_value, parse_label, same_axis

FACT_BASES = {"data_room_computed", "data_room_doc"}
MGMT_DOC = re.compile(r"cim|teaser|process.?letter|information memorandum|management presentation", re.I)


def iter_elements(content):
    for sid, sc in (content.get("slides") or {}).items():
        pages = sc if isinstance(sc, list) else [sc]
        for pi, page in enumerate(pages, 1):
            if not isinstance(page, dict):
                continue
            where = sid if len(pages) == 1 else f"{sid} p{pi}"
            yield sid, where, page


def refs_of(obj, acc=None):
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "refs" and isinstance(v, list):
                acc += [x for x in v if isinstance(x, str)]
            elif k == "row_refs" and isinstance(v, list):
                for rr in v:
                    acc += rr if isinstance(rr, list) else [rr]
            else:
                refs_of(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            refs_of(v, acc)
    return acc


# ----------------------------------------------------------------------------- chart audit
def _cells_values(f):
    """All parsed numeric cells of an evidence item, keyed by header."""
    out = {}
    hdr = f.get("table_header") or []
    rl = str(f.get("row_label") or "")
    for k, v in (f.get("cells") or {}).items():
        out[k] = parse_value(v, f"{k} {rl}" if k != "Line" else k)
    if not out and f.get("value") is not None:
        out[f.get("label", "value")] = parse_value(f.get("value"), f.get("label", ""))
    return out


def chart_audit(content, facts):
    issues = []
    for sid, where, page in iter_elements(content):
        for name, el in (page.get("elements") or {}).items():
            if not isinstance(el, dict) or el.get("type") != "chart":
                continue
            loc = f"{where}.{name}"
            cats = el.get("categories") or []
            series = el.get("series") or []
            point_refs = el.get("point_refs")          # [[ref per category] per series]
            refs = el.get("refs") or []
            if not series or not cats:
                issues.append((loc, "chart has no categories or series", "e"))
                continue
            # forecast labelling
            for c in cats:
                lab, is_f = parse_label(c)
                if re.fullmatch(r"20\d\d", str(c).strip()) and el.get("plan_from") and int(c) >= int(el["plan_from"]):
                    issues.append((loc, f"category {c} is a plan year but not labelled (use {c}P)", "e"))
            unit = el.get("unit_label") or el.get("number_format")
            if not unit:
                issues.append((loc, "chart states no unit", "e"))
            for si, s in enumerate(series):
                vals = s.get("values") or []
                if len(vals) != len(cats):
                    issues.append((loc, f"series '{s.get('name')}' has {len(vals)} values for {len(cats)} categories", "e"))
                    continue
                # each value must be traceable to an evidence cell with the same unit basis
                pr = (point_refs[si] if point_refs and si < len(point_refs) else None) or \
                     ([refs[i] if i < len(refs) else (refs[0] if refs else None) for i in range(len(vals))]
                      if len(refs) in (1, len(vals)) else [None] * len(vals))
                parsed = []
                for i, (v, r) in enumerate(zip(vals, pr)):
                    if v is None:
                        continue                        # an explicit gap is allowed
                    f = facts.get(r) if r else None
                    if r and r.startswith(("CALC", "CHECK:", "RUN:")):
                        continue
                    if not f:
                        issues.append((loc, f"point {cats[i]} has no evidence ref", "e"))
                        continue
                    cv = _cells_values(f)
                    hit = None
                    for hk, pv in cv.items():
                        if pv.is_range and pv.low is not None and (abs(pv.low - v) < 1e-9 or abs(pv.high - v) < 1e-9):
                            issues.append((loc, f"point {cats[i]}={v} is one end of a range "
                                                f"'{pv.raw}' in {r} - ranges are not plottable as points", "e"))
                            hit = "range"
                            break
                        if pv.chartable and _close(pv.value, v):
                            hit = pv
                            break
                    if hit is None:
                        issues.append((loc, f"point {cats[i]}={v} does not match any cell of {r} "
                                            f"({'; '.join(f'{k}={p.raw}' for k, p in list(cv.items())[:4])})", "e"))
                    elif hit != "range":
                        parsed.append(hit)
                ok, why = same_axis(parsed) if len(parsed) >= 2 else (True, "")
                if not ok:
                    issues.append((loc, f"series '{s.get('name')}': {why}", "e"))
    return issues


def _close(a, b):
    if a is None or b is None:
        return False
    return abs(a - b) <= max(1e-6, abs(a) * 0.005)


# ----------------------------------------------------------------------------- evidence grade
def evidence_grade(page, facts):
    """Page grade = best claim-level grade of the evidence on the page (C5: by source class, not
    by citation count; a management workbook alone is 'indicated', an agent restatement 'asserted')."""
    from .controls import claim_grade
    refs = [r for r in refs_of(page) if isinstance(r, str)]
    return claim_grade(refs, facts)[0]


ORDER = ["unsupported", "asserted", "indicated", "established"]


def claim_strength(content, facts, rules):
    issues = []
    pats = [(p["id"], re.compile(p["rx"], re.I), p["requires"], p["why"]) for p in rules.get("patterns", [])]
    for sid, where, page in iter_elements(content):
        grade = evidence_grade(page, facts)
        texts = []
        for k in ("title", "subtitle"):
            v = page.get(k)
            if v:
                texts.append((k, v["text"] if isinstance(v, dict) else str(v)))
        for name, el in (page.get("elements") or {}).items():
            if isinstance(el, dict) and el.get("type") in ("text",) and name in ("takeaway", "lead"):
                texts.append((name, el.get("text", "")))
            if isinstance(el, dict) and el.get("type") == "bullets":
                for i, it in enumerate(el.get("items") or [], 1):
                    if isinstance(it, dict) and it.get("kind") != "interpretation_attributed":
                        texts.append((f"{name}.item{i}", it.get("text", "")))
        for loc, t in texts:
            for pid, rx, req, why in pats:
                m = rx.search(t or "")
                if not m:
                    continue
                before, after = (t or "")[max(0, m.start() - 40):m.start()], (t or "")[m.end():m.end() + 40]
                if re.search(r"\b(not|no|unproven|cannot|without|lacks?|absence of|rather than)\b", before, re.I) or \
                        re.search(r"^\s*(is|are)\s+(not|unproven|indicated|asserted|untested)", after, re.I):
                    continue                      # negated or explicitly graded down
                if re.search(r"\b(management|the cim|per the company|the company states|claims?|asserts?|"
                             r"self-assess\w*|the agents? (?:rate|rated|describe))\b", t, re.I) and req != "never":
                    continue                      # attributed, not asserted
                if req == "never" or ORDER.index(grade) < ORDER.index(req):
                    issues.append((f"{where}.{loc}",
                                   f"unsupported claim '{m.group(0)}' ({pid}); slide evidence is "
                                   f"'{grade}' but needs '{req}'. {why} Allowed phrasing at this grade: "
                                   f"{rules['ladder'][grade]}.", "e"))
    return issues


# ----------------------------------------------------------------------------- truncation
TRUNC_RX = re.compile(r"…|\.\.\.(?!\w)")


def truncation(content, facts):
    issues = []
    for sid, where, page in iter_elements(content):
        units = []
        for k in ("title", "subtitle"):
            v = page.get(k)
            if v:
                units.append((k, v["text"] if isinstance(v, dict) else str(v),
                              v.get("refs", []) if isinstance(v, dict) else []))
        for name, el in (page.get("elements") or {}).items():
            if not isinstance(el, dict):
                continue
            if el.get("type") in ("text", "insufficient"):
                units.append((name, el.get("text", ""), el.get("refs", [])))
            elif el.get("type") == "bullets":
                for i, it in enumerate(el.get("items") or [], 1):
                    if isinstance(it, dict):
                        units.append((f"{name}.item{i}", it.get("text", ""), it.get("refs", [])))
            elif el.get("type") == "table":
                for ri, row in enumerate(el.get("rows") or [], 1):
                    for ci, c in enumerate(row):
                        units.append((f"{name}.row{ri}.c{ci}", str(c),
                                      (el.get("row_refs") or [[]] * ri)[ri - 1] if el.get("row_refs") else []))
        for loc, t, refs in units:
            if not t:
                continue
            if TRUNC_RX.search(t):
                issues.append((f"{where}.{loc}", f"truncated text ('…'): {t[-60:]!r}", "e"))
                continue
            # a final word that is only a prefix of a longer word in the cited source
            m = re.search(r"([a-z][A-Za-z]{3,})\.?\s*$", t)
            if m and refs and len(t) >= 25:
                w = m.group(1).lower()
                src = " ".join(facts[r]["text"] for r in refs if r in facts).lower()
                words = set(re.findall(r"[a-z]+", src))
                if w not in words and any(x.startswith(w) and len(x) > len(w) + 1 for x in words):
                    issues.append((f"{where}.{loc}", f"text ends mid-word ('{m.group(1)}'): {t[-60:]!r}", "e"))
    return issues


# ----------------------------------------------------------------------------- repetition
def _norm(t):
    return re.sub(r"[^a-z0-9]+", " ", (t or "").lower()).strip()


def repetition(content):
    issues = []
    tables, bullets, titles = defaultdict(list), defaultdict(list), defaultdict(list)
    for sid, where, page in iter_elements(content):
        t = page.get("title")
        if t:
            titles[_norm(t["text"] if isinstance(t, dict) else t)[:90]].append(sid)
        for name, el in (page.get("elements") or {}).items():
            if not isinstance(el, dict):
                continue
            if el.get("type") == "table" and el.get("row_refs"):
                key = frozenset(r for rr in el["row_refs"] for r in (rr if isinstance(rr, list) else [rr])
                                if isinstance(r, str) and not r.startswith(("CHECK:", "RUN:", "CALC")))
                if len(key) >= 2:
                    tables[key].append(f"{where}.{name}")
            if el.get("type") == "bullets":
                for it in el.get("items") or []:
                    if isinstance(it, dict) and len(it.get("text", "")) > 40:
                        bullets[_norm(it["text"])[:120]].append(f"{where}.{name}")
    for key, locs in tables.items():
        if len({l.split('.')[0].split(' ')[0] for l in locs}) > 1:
            issues.append((", ".join(locs), "same table (identical evidence rows) on more than one slide - "
                                            "consolidate onto one slide and cross-reference", "e"))
    # near-duplicate tables: >= 70 % shared rows
    keys = [k for k in tables if len(k) >= 3]
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            if a == b:
                continue
            ov = len(a & b) / min(len(a), len(b))
            sa = {l.split('.')[0] for l in tables[a]}
            sb = {l.split('.')[0] for l in tables[b]}
            if ov >= 0.7 and not (sa & sb):
                issues.append((f"{tables[a][0]}, {tables[b][0]}",
                               f"tables share {ov:.0%} of their evidence rows - consolidate", "e"))
    for key, locs in bullets.items():
        if len({l.split('.')[0].split(' ')[0] for l in locs}) > 1:
            issues.append((", ".join(sorted(set(locs))), f"bullet repeated across slides: '{key[:70]}'", "e"))
    for key, locs in titles.items():
        if len(set(locs)) > 1 and key:          # continuation pages of one slide share a title
            issues.append((", ".join(locs), "same action title on more than one slide", "e"))
    return issues


# ----------------------------------------------------------------------------- completeness
def completeness(content, slide_map):
    issues = []
    sm = {s["id"]: s for s in slide_map["slides"]}
    for sid, where, page in iter_elements(content):
        sd = sm.get(sid)
        if not sd:
            continue
        els = [e for e in (page.get("elements") or {}).values() if isinstance(e, dict)]
        if sd["archetype"] in ("cover", "back_cover", "contents", "divider"):
            continue
        if els:
            ins = sum(1 for e in els if e.get("type") == "insufficient")
            if ins and ins * 2 >= len(els):
                issues.append((where, f"{ins} of {len(els)} panels are 'insufficient' - the page is unfinished. "
                                      f"Complete it, or add it to content.withhold with a reason", "e"))
        if sd["archetype"] in ("disclaimer", "text_panel"):
            for e in els:
                if e.get("type") == "insufficient" or len(e.get("text", "") or "") < 60:
                    issues.append((where, "disclaimer / glossary panel is empty or placeholder", "e"))
    return issues


# ----------------------------------------------------------------------------- IC readiness
PRECISE_MONEY = re.compile(r"[$₹€£]\d[\d,]*\.\d{2}\s?(?:M|B|bn|mn|cr)\b")
PRECISE_PCT = re.compile(r"\b\d{2,3}\.\d%")


def ic_readiness(content, facts):
    """Partner-review checks. Warnings, not errors:
    they mark a deck that is accurate but not yet investment-committee ready."""
    issues = []
    slides = content.get("slides", {})
    # 1. answer first: an executive summary with at least three graded rows
    hl = slides.get("S020_highlights_summary")
    rows = ((hl or {}).get("elements", {}).get("rows", {}) or {}).get("rows", []) if isinstance(hl, dict) else []
    if len(rows) < 3:
        issues.append(("S020_highlights_summary", "no executive summary with >= 3 findings - the deck must "
                                                  "answer first (T21)", "w"))
    # 2. a plan is tested -> a diligence case must be stated
    uses_plan = any(isinstance(f, dict) and "plan" in (f.get("period_status") or {}).values()
                    for r in _all_refs(content) for f in [facts.get(r)])
    blob = json.dumps(slides, ensure_ascii=False).lower()
    if uses_plan and "diligence case" not in blob:
        issues.append(("deck", "the deck tests a management plan but states no diligence case "
                               "(management vs diligence vs downside) - T20", "w"))
    # 3. precision and length of titles
    long_titles = []
    for sid, where, page in iter_elements(content):
        t = page.get("title")
        txt = (t.get("text") if isinstance(t, dict) else t) or ""
        m = PRECISE_MONEY.search(txt) or PRECISE_PCT.search(txt)
        if m:
            issues.append((f"{where}.title", f"'{m.group(0)}' is more precise than a title needs - round it "
                                             f"(tables keep the precision) - T22", "w"))
        if len(txt) > 130:
            long_titles.append(where)
    if long_titles:
        issues.append(("deck", f"{len(long_titles)} titles run to two lines (> 130 chars), e.g. "
                               f"{', '.join(long_titles[:3])}; tighten the so-what to one line where it can be", "w"))
    return issues


def _all_refs(content):
    out = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in ("refs", "point_refs", "row_refs"):
                    for x in (v if isinstance(v, list) else [v]):
                        for y in (x if isinstance(x, list) else [x]):
                            if isinstance(y, str):
                                out.add(y)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(content.get("slides", {}))
    return out
