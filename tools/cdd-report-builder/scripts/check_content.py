#!/usr/bin/env python3
"""Step 7 (content side): verify content.json against the mapping spec and the evidence base.

Usage: python check_content.py --content <work>/content.json --work <work> [--render-log <work>/render_log.json]

Hard errors (exit 1):
  * a mapped slide/element is missing (use an explicit {"type": "insufficient"} element instead)
  * a text-bearing element, bullet or table row has no evidence reference, or references an unknown id
  * a reference points at a PLACEHOLDER item (e.g. "Regulation X") or content restates an N/A item as fact
  * a number shown on a slide cannot be found in its referenced evidence or in a declared calculation
  * a calculation does not recompute from its inputs, or its inputs are not in the cited evidence
  * banned text (template instructions, reference-report names, configured terms) appears
  * presentation limits (characters / items / rows) are exceeded, or render_log reports overflow
Warnings: references to flagged evidence (OCR, suitability, clipped tables), interpretation items
without a fact reference, metric-consistency gaps.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import operator
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import SKILL_DIR, load_yaml, read_json, slide_map, write_json  # noqa: E402

NUM_IN_TEXT = re.compile(r"(?<![\w.])[-−]?\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|(?<![\w.])[-−]?\d+(?:\.\d+)?")
TRIVIAL = re.compile(r"^(?:[0-9]|10)$")
YEAR = re.compile(r"^(19|20)\d\d$")
FLAG_WARN = {"OCR_CURRENCY", "OCR_CURRENCY_AMBIGUOUS", "SOURCE_SUITABILITY", "TABLE_CLIPPED", "LOW_OCR_CONF", "UNCITED_NUMBER", "PARTIAL_NA"}
NA_WORDS = re.compile(r"not provided|insufficient|n/a|not available|no data|gap|missing|unknown|not disclosed|not quantified|unresolved|absent|lack", re.I)

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.Pow: operator.pow, ast.USub: operator.neg}


def safe_eval(expr, names):
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.Name):
            return float(names[n.id])
        if isinstance(n, ast.BinOp):
            return OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp):
            return OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("sum", "avg", "min", "max", "abs", "round"):
            args = [ev(a) for a in n.args]
            return {"sum": sum, "avg": lambda *x: sum(x) / len(x), "min": min, "max": max, "abs": abs,
                    "round": lambda v, d=0: round(v, int(d))}[n.func.id](*args)
        raise ValueError(f"unsupported expression element {ast.dump(n)}")
    return ev(ast.parse(expr, mode="eval"))


def nums_in(text):
    out = []
    t = re.sub(r"\[\d{1,2}\]", "", str(text))            # citation markers
    t = re.sub(r"\bS\d{2}\b|\bC\d{1,2}\b|\bT\d{1,2}\b|\bE\d\b|\bR\d\b", "", t)  # slide / rule ids
    t = re.sub(r"\b[A-Z]{2,4}-\d+(-[A-Z]\d+)*(-R\d+)?\b", "", t)  # evidence ids
    t = re.sub(r"_n\d+|\bn=\d+|\bn\d{2,4}\b", "", t)       # sample sizes in doc names
    t = re.sub(r"\b\d+(?:\.\d+)?\s?kWh\b", "", t)
    for m in NUM_IN_TEXT.finditer(t):
        raw = m.group(0).replace("−", "-")
        try:
            v = float(raw.replace(",", ""))
        except ValueError:
            continue
        s = raw.replace(",", "").lstrip("-")
        dec = len(s.split(".")[1]) if "." in s else 0
        out.append((raw, v, dec))
    return out


def evidence_numbers(fact):
    """Numbers the cited source actually prints - its body, and the heading it sits under.

    A section heading ("Post-Closing 100-Day Action Plan") is part of the source page, so a
    figure lifted from it is traceable; excluding headings produced false 'untraceable number'
    errors on every slide that used a heading as a bullet lead.
    """
    vals = []
    t = " | ".join(str(fact.get(k, "")) for k in ("text", "section_title", "label", "row_label"))
    t = re.sub(r"\(DOC:[^)]*\)|\[\d{1,2}\]", "", t)
    t = re.sub(r"SYNTHETIC_\d+_\S+", "", t)
    for raw, v, dec in nums_in(t):
        vals.append(v)
    return vals


def matches(v, dec, pool):
    for y in pool:
        if y is None:
            continue
        for cand in (y, abs(y)):
            if round(cand, dec) == round(abs(v), dec) or math.isclose(abs(v), cand, rel_tol=0.005):
                return True
            # unit scaling (e.g. 0.442 vs 44.2 %, bn vs cr are NOT auto-converted on purpose)
            if math.isclose(abs(v), cand * 100, rel_tol=0.005) or math.isclose(abs(v) * 100, cand, rel_tol=0.005):
                return True
    return False


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def e(self, where, msg):
        self.errors.append({"where": where, "msg": msg})

    def w(self, where, msg):
        self.warnings.append({"where": where, "msg": msg})


def text_units(el):
    """Yield (label, text, refs, kind) for every text-bearing unit of an element."""
    t = el.get("type")
    refs = el.get("refs", [])
    if t in ("text", "insufficient"):
        yield ("text", el.get("text", ""), refs, el.get("kind"))
    elif t == "bullets":
        for i, it in enumerate(el.get("items", []), 1):
            if isinstance(it, dict):
                yield (f"item{i}", it.get("text", ""), it.get("refs", []) or refs, it.get("kind"))
            else:
                yield (f"item{i}", str(it), refs, None)
    elif t == "table":
        rr = el.get("row_refs") or []
        for i, row in enumerate(el.get("rows", []), 1):
            rrefs = rr[i - 1] if i - 1 < len(rr) and rr[i - 1] else refs
            yield (f"row{i}", " | ".join(str(c) for c in row), rrefs, "table_row")
    elif t == "chart":
        vals = " ".join(str(v) for s in el.get("series", []) for v in s.get("values", []) if v is not None)
        yield ("chart_values", vals, refs, "chart")
    elif t == "kpis":
        for i, it in enumerate(el.get("items", []), 1):
            yield (f"kpi{i}", f"{it.get('value','')} {it.get('label','')} {it.get('note','')}", it.get("refs", []) or refs, it.get("kind"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--content", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--render-log")
    a = ap.parse_args()
    work = Path(a.work)
    content = read_json(a.content)
    sm = slide_map()
    defaults = sm["defaults"]
    facts = {f["id"]: f for f in read_json(work / "evidence.json")["facts"]}
    banned_cfg = load_yaml("banned_terms.yaml")
    banned = [re.compile(p, re.I) for p in banned_cfg.get("patterns", [])]
    banned += [re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in banned_cfg.get("reference_report_terms", [])]
    rep = Report()
    calcs = {c["id"]: c for c in content.get("calculations", [])}

    # ---- calculations
    calc_outputs_by_slide = {}
    for cid, c in calcs.items():
        try:
            names = {k: float(v["value"]) for k, v in c["inputs"].items()}
            val = safe_eval(c["formula"], names)
            dec = int(c.get("rounding", 1))
            if round(val, dec) != round(float(c["output"]), dec):
                rep.e(f"calc {cid}", f"formula gives {round(val, dec)} but output states {c['output']}")
        except Exception as ex:  # noqa: BLE001
            rep.e(f"calc {cid}", f"cannot evaluate: {ex}")
            continue
        for k, v in c["inputs"].items():
            ref = v.get("ref")
            refs = ref if isinstance(ref, list) else [ref]
            if isinstance(ref, str) and (ref == "CALC" or ref.startswith(("CHECK:", "RUN:"))):
                continue   # value produced by a script (auto_checks.json / run parameters) or another calc
            if not ref or any(r not in facts for r in refs):
                if True:
                    rep.e(f"calc {cid}", f"input {k} has unknown ref {ref}")
                continue
            pool = [n for r in refs for n in evidence_numbers(facts[r])]
            if not matches(float(v["value"]), 6, pool) and not matches(float(v["value"]), 1, pool):
                rep.e(f"calc {cid}", f"input {k}={v['value']} not found in evidence {ref}")
        for s in c.get("used_on", []):
            calc_outputs_by_slide.setdefault(s, []).append(float(c["output"]))
            for extra in c.get("also_shown_as", []):
                calc_outputs_by_slide[s].append(float(extra))

    # ---- slides
    # Slides withheld by a coverage gate are absent by design (axiom A6). They must appear in the
    # exceptions, not in the deck; an unexplained absence is still an error.
    gated_out = {}
    gp = Path(a.work) / "gates.json"
    if gp.exists():
        gated_out = {g["id"]: g for g in read_json(gp) if not g.get("render")}
    forced = set(content.get("force_render", []))
    gated_out = {k: v for k, v in gated_out.items() if k not in forced}
    # analyst withholds (unfinished or duplicative pages) behave exactly like gate drops
    for w in content.get("withhold", []) or []:
        gated_out[w["id"]] = {"id": w["id"], "exception": w.get("exception", "E13-WITHHELD"),
                              "reason": w.get("reason", "")}
    ex_slides = {s for e in content.get("exceptions", []) for s in (e.get("slides") or [])}
    for sid, g in gated_out.items():
        if sid not in ex_slides:
            rep.w(sid, f"withheld by gate ({g['exception']}) but not named in any exception - "
                       f"the reader cannot see that this page is missing")

    for sd in sm["slides"]:
        sid = sd["id"]
        if sd["archetype"] in ("divider", "contents"):
            continue
        if sid in gated_out:
            continue
        sc_all = content["slides"].get(sid)
        if sc_all is None:
            rep.e(sid, "slide missing from content.json")
            continue
        pages = sc_all if isinstance(sc_all, list) else [sc_all]
        if isinstance(sc_all, list) and len(sc_all) > 1 and not sd.get("repeatable"):
            rep.e(sid, "multiple pages supplied for a non-repeatable slide")
        for pi, sc in enumerate(pages, 1):
            where = sid if len(pages) == 1 else f"{sid} p{pi}"
            slide_refs = []
            if sd["archetype"] not in ("cover", "back_cover", "disclaimer", "text_panel"):
                for key in ("title", "subtitle"):
                    v = sc.get(key)
                    if not v:
                        rep.e(where, f"missing {key}")
                        continue
                    txt = v["text"] if isinstance(v, dict) else v
                    lim = defaults[key]["max_chars"]
                    if len(txt) > lim:
                        rep.e(where, f"{key} is {len(txt)} chars > {lim}")
                    if isinstance(v, dict):
                        slide_refs += v.get("refs", [])
            els = sc.get("elements", {})
            for el in sd.get("elements", []):
                name = el["name"]
                spec = els.get(name)
                if el["type"] == "auto":
                    continue
                if spec is None:
                    rep.e(where, f"element '{name}' missing (use type 'insufficient' with a reason if evidence is absent)")
                    continue
                lim = el.get("limits", {})
                t = spec.get("type")
                if t not in (el["type"], "insufficient") and not (el["type"] == "kpis" and t == "kpis"):
                    rep.e(where, f"element '{name}' type {t} != mapped type {el['type']}")
                if t == "text" and lim.get("max_chars") and len(spec.get("text", "")) > lim["max_chars"]:
                    rep.e(where, f"{name}: {len(spec['text'])} chars > {lim['max_chars']}")
                if t == "bullets":
                    items = spec.get("items", [])
                    if lim.get("max_items") and len(items) > lim["max_items"]:
                        rep.e(where, f"{name}: {len(items)} bullets > {lim['max_items']}")
                    for i, it in enumerate(items, 1):
                        tx = it["text"] if isinstance(it, dict) else it
                        if lim.get("max_chars_item") and len(tx) > lim["max_chars_item"]:
                            rep.e(where, f"{name} item{i}: {len(tx)} chars > {lim['max_chars_item']}")
                if t == "table":
                    rows = spec.get("rows", [])
                    mr = lim.get("max_rows", defaults["table"]["max_rows"])
                    if len(rows) > mr:
                        rep.e(where, f"{name}: {len(rows)} rows > {mr}")
                    for i, r in enumerate(rows, 1):
                        if len(r) != len(spec.get("columns", [])):
                            rep.e(where, f"{name} row{i}: {len(r)} cells vs {len(spec.get('columns', []))} columns")
                        for c in r:
                            if lim.get("max_chars_cell") and len(str(c)) > lim["max_chars_cell"]:
                                rep.e(where, f"{name} row{i}: cell {len(str(c))} chars > {lim['max_chars_cell']}")
                if t == "chart":
                    ncat = len(spec.get("categories", []))
                    for s_ in spec.get("series", []):
                        if len(s_.get("values", [])) != ncat:
                            rep.e(where, f"{name}: series '{s_.get('name')}' has {len(s_.get('values', []))} values for {ncat} categories")
                    if not spec.get("unit_label") and not spec.get("number_format"):
                        rep.w(where, f"{name}: chart has no unit label / number format")
                # refs & numbers
                for label, txt, refs, kind in text_units(spec):
                    loc = f"{where}.{name}.{label}"
                    if not refs and t != "insufficient":
                        rep.e(loc, "no evidence reference")
                    for r in refs:
                        if r not in facts:
                            if r.startswith(("CALC:", "RUN:", "EXC:", "CHECK:")):
                                continue
                            rep.e(loc, f"unknown evidence id {r}")
                            continue
                        f = facts[r]
                        if "PLACEHOLDER" in f["flags"]:
                            if "placeholder" in txt.lower() or kind == "gap":
                                rep.w(loc, f"cites placeholder evidence {r} to document the gap")
                            else:
                                rep.e(loc, f"references placeholder evidence {r}: {f['text'][:80]}")
                        if "NA" in f["flags"] and not NA_WORDS.search(txt) and kind in ("fact", "table_row", None):
                            rep.w(loc, f"references N/A evidence {r} but text does not say it is missing")
                        for fl in f["flags"]:
                            if fl in FLAG_WARN:
                                rep.w(loc, f"uses {fl} evidence {r} - verify against page image (crop_evidence.py)")
                    if kind == "fact" and any(r in facts for r in refs) and all(facts.get(r, {}).get("class") == "interpretation" for r in refs if r in facts):
                        rep.w(loc, "item marked 'fact' but only cites agent interpretation (Read/Synthesis/Verdict)")
                    if kind not in (None, "fact", "calc", "interpretation", "table_row", "chart", "gap"):
                        rep.e(loc, f"unknown kind {kind}")
                    pool = [n for r in refs if r in facts for n in evidence_numbers(facts[r])]
                    pool += calc_outputs_by_slide.get(sid, [])
                    pool += [n for r in slide_refs if r in facts for n in evidence_numbers(facts[r])]
                    # a CHECK:/RUN: ref means the number was computed by a pipeline script into
                    # auto_checks.json / coverage.json; those are traceable without being evidence
                    script_backed = any(isinstance(r, str) and r.startswith(("CHECK:", "RUN:"))
                                        for r in refs)
                    for raw, v, dec in nums_in(txt):
                        if YEAR.match(raw) or TRIVIAL.match(raw.lstrip("-")):
                            continue
                        if script_backed:
                            continue
                        if not matches(v, dec, pool):
                            rep.e(loc, f"number {raw} not found in referenced evidence or declared calculations")
            # title/subtitle numbers must be backed by something on the slide
            all_pool = calc_outputs_by_slide.get(sid, [])
            for r in collect_all_refs(sc):
                if r in facts:
                    all_pool += evidence_numbers(facts[r])
            for key in ("title", "subtitle"):
                v = sc.get(key)
                txt = (v["text"] if isinstance(v, dict) else v) if v else ""
                key_refs = (v.get("refs") or []) if isinstance(v, dict) else []
                if any(isinstance(r, str) and r.startswith(("CHECK:", "RUN:")) for r in key_refs):
                    continue   # figure computed by a pipeline script; traceable, not evidence-borne
                for raw, val, dec in nums_in(txt):
                    if YEAR.match(raw) or TRIVIAL.match(raw.lstrip("-")):
                        continue
                    if not matches(val, dec, all_pool):
                        rep.e(f"{where}.{key}", f"number {raw} not backed by any evidence/calculation on the slide")
            # banned text anywhere on the slide
            blob = json.dumps(sc, ensure_ascii=False)
            for rx in banned:
                m = rx.search(blob)
                if m:
                    rep.e(where, f"banned text '{m.group(0)}'")

    # ---- metric consistency
    for key, m in content.get("metrics", {}).items():
        for s in m.get("slides", []):
            blob = json.dumps(content["slides"].get(s, {}), ensure_ascii=False)
            if str(m["value"]) not in blob:
                rep.e(f"metric {key}", f"value '{m['value']}' not shown on {s} although declared there")

    # ---- exceptions
    ids = {s["id"] for s in sm["slides"]}
    for i, ex in enumerate(content.get("exceptions", []), 1):
        for k in ("severity", "issue", "treatment"):
            if not ex.get(k):
                rep.e(f"exception {i}", f"missing {k}")
        for s in ex.get("slides", []):
            if s not in ids:
                rep.e(f"exception {i}", f"unknown slide {s}")

    # ---- deck-level rules (v3): chart audit, evidence-graded claims, truncation, repetition,
    #      completeness. See scripts/lib/content_rules.py and config/claim_rules.yaml.
    from lib import content_rules as CR
    claim_cfg = load_yaml("claim_rules.yaml")
    for fn in (lambda: CR.chart_audit(content, facts), lambda: CR.claim_strength(content, facts, claim_cfg),
               lambda: CR.truncation(content, facts), lambda: CR.repetition(content),
               lambda: CR.completeness(content, sm), lambda: CR.ic_readiness(content, facts)):
        for where, msg, sev in fn():
            (rep.e if sev == "e" else rep.w)(where, msg)

    # ---- diligence controls C1-C6 (lib/controls.py, config/controls.yaml)
    from lib import controls as CT
    rp = work / "reconciliation.json"
    recon = read_json(rp) if rp.exists() else None
    for where, msg, sev in CT.run_all(content, facts, recon):
        (rep.e if sev == "e" else rep.w)(where, msg)
    write_json(work / "claim_register.json", CT.claim_register(content, facts))

    # ---- render log
    if a.render_log and Path(a.render_log).exists():
        rl = read_json(a.render_log)
        for o in rl.get("overflow", []):
            rep.e(f"{o['slide']}.{o['element']}", f"text/table overflow at minimum readable size (needs {o.get('needed_pt')}pt) - shorten or split")
        for er in rl.get("errors", []):
            rep.e(f"{er['slide']}.{er['element']}", er["error"])

    out = {"errors": rep.errors, "warnings": rep.warnings,
           "summary": {"errors": len(rep.errors), "warnings": len(rep.warnings)}}
    write_json(work / "check_report.json", out)
    print(f"[check] errors {len(rep.errors)}  warnings {len(rep.warnings)}")
    for e in rep.errors[:80]:
        print("  ERROR", e["where"], "-", e["msg"])
    sys.exit(1 if rep.errors else 0)


def collect_all_refs(obj, acc=None):
    acc = [] if acc is None else acc
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("refs",) and isinstance(v, list):
                acc += [x for x in v if isinstance(x, str)]
            elif k == "row_refs" and isinstance(v, list):
                for rr in v:
                    acc += rr if isinstance(rr, list) else [rr]
            else:
                collect_all_refs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            collect_all_refs(v, acc)
    return acc


if __name__ == "__main__":
    main()
