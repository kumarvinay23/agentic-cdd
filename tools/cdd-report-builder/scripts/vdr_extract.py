#!/usr/bin/env python3
"""Read data-room workbooks directly and merge them into the evidence base.

    python vdr_extract.py --vdr <data-room dir> --work <work>

Why: agent modules summarise the data room, and they can drop the numbers that matter most. In
a first run no Historical Performance module was produced, so the deck had no revenue or
profit history while the data room held 43 months of accounts and a reconciled investor
workbook. This step closes that gap without guessing:

  * only sheets matched by a recipe in config/vdr_extractors.yaml are read;
  * every row becomes an evidence item attributed to the module-of-record (HPF, RVQ, CST, MVG ...)
    with basis `data_room_computed`, so R1 ranks it above anything an agent restated;
  * every value keeps its unit and scale, and every year column is flagged actual or plan, so
    "2030P" can never be mistaken for a result;
  * computed items (TTM, year-to-date vs prior year) are declared as computed, with the months
    they sum.

Writes <work>/vdr_evidence.json and merges it into <work>/evidence.json (idempotent: previous
VDR-direct items are replaced, agent items untouched). Re-run coverage.py and ontology.py gates
afterwards - run_pipeline.py prepare does this in order.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
from lib.common import read_json, write_json  # noqa: E402

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
YEAR_RX = re.compile(r"^(?:fy)?((?:19|20)\d{2})\s*([pfe]|h1|h2|ytd|a)?\b", re.I)
PCT_LABEL = re.compile(r"%|margin|retention|churn %|churn rate|share|\bgrr\b|\bnrr\b|\brate\b|mix|participation", re.I)
COUNT_LABEL = re.compile(r"\b(accounts|locations|subscriptions|subscribers|logos|homes|households|"
                         r"count|payers|contracted hh|active hh|tons|businesses|score)\b", re.I)


def load_grid(ws, max_rows, max_cols):
    grid = []
    for r in ws.iter_rows(min_row=1, max_row=max_rows, max_col=max_cols, values_only=True):
        grid.append(list(r))
    return grid


def header_info(h, plan_after):
    """-> (label, status) where status is actual | plan | ytd | None."""
    if isinstance(h, dt.datetime):
        return h.strftime("%b-%Y"), "actual" if h.year <= (plan_after or 9999) else "plan"
    if isinstance(h, (int, float)) and 1990 <= h <= 2100:
        y = int(h)
        if plan_after and y > plan_after:
            return f"{y}P", "plan"
        return str(y), "actual"
    s = " ".join(str(h or "").split())
    if re.search(r"\bat \d{1,2}-\w{3}|at \d{1,2}-\w{3}-\d{4}", s, re.I):
        return s, "ytd"
    m = YEAR_RX.match(s)
    if m:
        y, suf = int(m.group(1)), (m.group(2) or "").lower()
        if suf in ("p", "f", "e") or (plan_after and y > plan_after and suf not in ("h1", "h2", "ytd")):
            return (s if suf in ("p", "f", "e") else f"{s}P"), "plan"
        if suf in ("h1", "h2", "ytd") or re.search(r"at \d{1,2}-", s):
            return s, "ytd"
        return s, "actual"
    if re.search(r"at \d{1,2}-\w{3}-\d{4}|at 30-jun", s, re.I):
        return s, "actual"
    return s, None


COL_UNITS = [
    (re.compile(r"^(zip|zip code|code|id|rank|year)$", re.I), "id"),
    (re.compile(r"\b(accounts|hh|households|homes|locations|count|stops|subscriptions|subscribers|subs|logos)\b", re.I), "count"),
    (re.compile(r"participation|%|\bmix\b|\bshare\b|retention|cagr", re.I), "pct_frac"),
    (re.compile(r"\(\$ ?mn\)|\(\$ ?m\)|\$ ?million|\(\$ million\)", re.I), "money_M"),
    (re.compile(r"score", re.I), "score"),
    (re.compile(r"revenue|\(\$|\$/|arr\b|mrr\b|arpu|arpa|price|value", re.I), "money"),
]


def col_unit(col_header):
    for rx, u in COL_UNITS:
        if rx.search(str(col_header or "")):
            return u
    return None


def fmt_value(v, units, label, header, scale_M=False, col_header=None):
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return " ".join(v.split())
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (dt.datetime, dt.date)):
        return v.strftime("%d-%b-%Y")
    if not isinstance(v, (int, float)):
        return " ".join(str(v).split())
    u = units
    cu = col_unit(col_header)
    if cu == "id":
        return str(int(v)) if float(v).is_integer() else str(v)
    if cu == "score":
        return f"{v:.2f}"
    if cu == "money" and u in ("money_M", "money_M_if_header"):
        cu = None
    col_forced = False
    if cu and not re.fullmatch(r"(?:fy)?\d{4}\s*(?:[pfea]|h1|h2|ytd)?", str(col_header or "").strip(), re.I):
        u = cu
        col_forced = True
    if u == "auto":
        if re.search(r"\$|arpa|arpu|ltv|revenue \(\$\)", label, re.I) and not re.search(r"%", label):
            u = "money_M" if re.search(r"\$ ?mn|\(\$m\)|\$m\b", label, re.I) else "money"
        elif PCT_LABEL.search(label) and abs(v) <= 3:
            u = "pct_frac"
        elif abs(v) <= 1.5 and re.search(r"\bcohort\b", label, re.I) and not re.search(r"\$|revenue", label, re.I):
            u = "pct_frac"
        elif COUNT_LABEL.search(label):
            u = "count"
        elif re.search(r"\(\$m\)|\$m|\$mn|\(\$ ?mn\)|\$ ?million", header + " " + label, re.I):
            u = "money_M"
        elif re.search(r"\(\$\)|revenue \(\$\)|\$/|ltv|arpa|arpu|\$ ", header + " " + label, re.I):
            u = "money"
        elif abs(v) < 1000 and isinstance(v, float) and not float(v).is_integer():
            u = "money_M"
        else:
            u = "count"
    if u == "money_M_if_header":
        u = "money_M" if re.search(r"million|\$m", header, re.I) else "money"
    if u == "pct_frac":
        return f"{v * 100:.1f}%"
    if u == "money_M":
        return f"-${abs(v):,.2f}M" if v < 0 else f"${v:,.2f}M"
    if u == "money":
        if not col_forced and PCT_LABEL.search(label) and abs(v) <= 1.5 and "$" not in label:
            return f"{v * 100:.1f}%"
        if scale_M and abs(v) >= 1e5:
            m = v / 1e6
            return f"-${abs(m):,.2f}M" if m < 0 else f"${m:,.2f}M"
        if not col_forced and abs(v) < 1 and v != 0 and PCT_LABEL.search(label):
            return f"{v * 100:.1f}%"
        return f"-${abs(v):,.0f}" if v < 0 else (f"${v:,.2f}" if abs(v) < 100 and not float(v).is_integer()
                                                  else f"${v:,.0f}")
    if u == "count":
        if isinstance(v, float) and not v.is_integer():
            return f"{v:,.2f}"
        return f"{int(v):,}"
    return str(v)


def find_header_row(grid):
    best, best_i = 0, None
    for i, row in enumerate(grid[:12]):
        years = sum(1 for c in row if (isinstance(c, (int, float)) and 1990 <= c <= 2100)
                    or (isinstance(c, str) and YEAR_RX.match(c.strip()))
                    or isinstance(c, dt.datetime))
        texts = sum(1 for c in row if isinstance(c, str) and c.strip())
        score = years * 3 + texts
        if score > best and (years >= 2 or texts >= 3):
            best, best_i = score, i
    return best_i


def label_col(grid, start):
    counts = {}
    for row in grid[start + 1:start + 30]:
        for j, c in enumerate(row[:4]):
            if isinstance(c, str) and c.strip():
                counts[j] = counts.get(j, 0) + 1
                break
    return max(counts, key=counts.get) if counts else 0


ACRONYMS = {"TAM", "SAM", "SOM", "CIM", "ARR", "MRR", "DC", "ICP", "NOVA", "MD", "VA", "EBITDA", "GRR",
            "NRR", "LTV", "ARPU", "ARPA", "HH", "YTD", "TTM", "QBO", "SG&A", "US", "USDA", "KPI"}
SMALL_WORDS = {"at", "of", "and", "the", "to", "by", "in", "on", "for", "per", "vs"}


def block_case(lab: str) -> str:
    """'RETENTION, MODEL BASIS (2026)' -> 'Retention, model basis (2026)'; keeps TAM/SAM/CIM/ARR/DC upper."""
    words = " ".join(lab.split()).split(" ")
    out = []
    for k, w in enumerate(words):
        core = re.sub(r"[^A-Za-z]", "", w)
        if core.upper() in ACRONYMS:
            out.append(w)                      # acronym
        elif k == 0:
            out.append(w.capitalize())
        else:
            out.append(w.lower())
    return " ".join(out)


def extract_notes(grid, hi, recipe, sec, vdr_rel, min_len=60):
    """Long explanatory sentences under a table ('These are government-programme households ...')."""
    out = []
    for row in grid[hi + 1:]:
        for c in row:
            if isinstance(c, str) and len(c) >= min_len and not re.match(r"^\s*(source|note)s?:?\s*$", c, re.I):
                k = len(out) + 1
                out.append({
                    "id": f"{recipe['module']}-V{sec['n']}-N{k}", "module": recipe["module"],
                    "module_title": sec["title"], "section_n": sec["n"], "section_key": sec["key"],
                    "section_title": sec["title"], "kind": "note", "text": " ".join(c.split()),
                    "citations": {"doc": [vdr_rel], "web": [], "computed": True},
                    "basis": "data_room_doc", "numbers": re.findall(r"[$]?\d[\d,.]*%?", c), "page": None,
                    "flags": [], "class": "fact", "measures": [], "subject": recipe.get("subject", "target"),
                    "source": "vdr_direct", "recipe": recipe["id"]})
                break
    return out


def extract_sheet(ws, recipe, art_path, plan_after, vdr_rel):
    grid = load_grid(ws, recipe.get("max_rows", 40) + 4, recipe.get("max_cols", 60))
    hi = None
    if recipe.get("header_match"):
        hm = re.compile(recipe["header_match"], re.I)
        hi = next((i for i, row in enumerate(grid)
                   if any(isinstance(c, str) and hm.search(c) for c in row)), None)
    kv = recipe.get("kv")          # label / value sheets with no header row (control panels)
    if kv and hi is None:
        hi = 0
        grid = [list(r) for r in grid]
        while len(grid[0]) <= kv["value_col"]:
            grid[0].append(None)
        grid[0][kv["value_col"]] = kv.get("header", "Value")
    if hi is None:
        hi = find_header_row(grid)
    if hi is None:
        return [], []
    if recipe.get("col_range"):
        a_, b_ = recipe["col_range"]
        grid = [[None] * a_ + r[a_:b_ + 1] for r in grid]
    lc = recipe.get("label_col", label_col(grid, hi))
    hdr_row = grid[hi]
    cols = []
    for j, h in enumerate(hdr_row):
        if j <= lc or h in (None, ""):
            continue
        lab, status = header_info(h, plan_after)
        if recipe.get("columns") == "annual" and not (isinstance(h, (int, float)) and 1990 <= h <= 2100):
            continue
        cols.append((j, lab, status))
    if not cols:
        return [], []
    # monthly accounts: relabel a partial final year as YTD
    months = [h for h in hdr_row if isinstance(h, dt.datetime)]
    if recipe.get("columns") == "annual" and months:
        last = max(months)
        cols = [(j, (f"{lab.rstrip('P')} YTD ({MONTHS[last.month - 1]})" if lab.rstrip("P") == str(last.year)
                     and last.month < 12 else lab.rstrip("P")),
                 ("ytd" if lab.rstrip("P") == str(last.year) and last.month < 12 else "actual"))
                for j, lab, st in cols]
    rows_map = {re.compile(k, re.I): v for k, v in (recipe.get("rows") or {}).items()}
    stop = re.compile(recipe["stop_at"], re.I) if recipe.get("stop_at") else None
    keep = re.compile(recipe["keep_rows"], re.I) if recipe.get("keep_rows") else None
    out, derived = [], []
    sec = recipe["section"]
    carry = None
    block = None      # an all-caps sub-header row ("RETENTION, MODEL BASIS (2026)") qualifies the rows below
    rn = 0
    for i, row in enumerate(grid[hi + 1:], start=hi + 1):
        lab = row[lc] if lc < len(row) else None
        if isinstance(lab, str) and lab.strip() and not any(
                row[j] not in (None, "") for j, _, _ in cols if j < len(row)):
            letters = [ch for ch in lab if ch.isalpha()]
            if len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8:
                if stop and stop.search(lab):
                    break
                block = block_case(lab)
                continue
        if recipe.get("label_is_number") and isinstance(lab, (int, float)):
            lab = f"{int(lab)} months"
        elif isinstance(lab, (int, float)) and not isinstance(lab, bool):
            lab = str(int(lab)) if float(lab).is_integer() else str(lab)
        # multi-column label (e.g. segment + territory)
        extra = ""
        if lc + 1 < len(row) and isinstance(row[lc + 1], str) and row[lc + 1].strip() and \
                all(j != lc + 1 for j, _, _ in cols):
            extra = row[lc + 1].strip()
        if isinstance(lab, str) and lab.strip():
            carry = lab.strip()
        elif recipe.get("carry_label") and carry and any(
                row[j] not in (None, "") for j, _, _ in cols if j < len(row)):
            lab = carry
        else:
            if not extra:
                continue
            lab = extra
            extra = ""
        lab = " ".join(str(lab).split())
        if stop and stop.search(lab):
            break
        if keep and not keep.search(lab) and not (extra and keep.search(extra)):
            continue
        full = f"{lab} — {extra}" if extra else lab
        if block:
            full = f"{full} [{block}]"
        model_basis = bool(block and re.search(r"model|plan|assum|forecast|projec|budget|target", block, re.I))
        cells, nums, statuses = {}, [], {}
        for j, hl, st in cols:
            raw = row[j] if j < len(row) else None
            fv = fmt_value(raw, recipe.get("units", "auto"), full, " ".join(str(x) for x in hdr_row if x),
                           recipe.get("scale_M", False), col_header=hdr_row[j])
            if fv is None:
                continue
            cells[hl] = fv
            statuses[hl] = "plan" if model_basis else st
            if re.search(r"\d", fv):
                nums.append(fv)
        if not cells or not nums:
            continue
        rn += 1
        measures = [m for rx, m in rows_map.items() if rx.search(full)][:1]
        eid = f"{recipe['module']}-V{sec['n']}-R{rn}"
        text = f"{full} | " + " | ".join(f"{k}: {v}" for k, v in cells.items())
        out.append({
            "id": eid, "module": recipe["module"], "module_title": sec["title"],
            "section_n": sec["n"], "section_key": sec["key"], "section_title": sec["title"],
            "kind": "table_row", "text": text,
            "citations": {"doc": [vdr_rel], "web": [], "computed": True},
            "basis": "data_room_computed", "numbers": nums, "page": None,
            "flags": ["MODEL_BASIS"] if model_basis else [],
            "table_header": ["Line"] + list(cells.keys()), "cells": {"Line": full, **cells},
            "row_label": full, "class": "fact", "measures": measures,
            "subject": recipe.get("subject", "target"), "source": "vdr_direct",
            "period_status": statuses, "recipe": recipe["id"],
        })
    if recipe.get("notes"):
        derived += extract_notes(grid, hi, recipe, sec, vdr_rel)
    dq = recipe.get("dq_duplicate_column")
    if dq and out:
        dqrx = re.compile(f"^(?:{dq})$", re.I)
        dq = next((k for k in out[0]["cells"] if dqrx.match(str(k))), None)
    if dq and out:
        seen = {}
        for it in out:
            key = str(it["cells"].get(dq, "")).strip().lower()
            if not key:
                continue
            if key in seen:
                it["flags"].append("DUPLICATE_ENTITY")
                derived.append({
                    "id": f"{recipe['module']}-V{sec['n']}-DQ{len(derived) + 1}", "module": recipe["module"],
                    "module_title": sec["title"], "section_n": sec["n"], "section_key": sec["key"],
                    "section_title": sec["title"], "kind": "field", "label": "Data-quality finding",
                    "value": f"'{it['cells'].get(dq)}' appears twice (ranks {seen[key]} and {it['row_label']})",
                    "text": f"Data-quality finding: '{it['cells'].get(dq)}' appears twice in {ws.title} "
                            f"(ranks {seen[key]} and {it['row_label']}); cumulative shares below the second "
                            f"occurrence are overstated.",
                    "citations": {"doc": [vdr_rel], "web": [], "computed": True},
                    "basis": "data_room_computed", "numbers": [], "page": None,
                    "flags": ["DATA_QUALITY"], "class": "fact", "measures": ["cust.concentration"],
                    "subject": "target", "source": "vdr_direct", "recipe": recipe["id"]})
            else:
                seen[key] = it["row_label"]
    # derived TTM / YTD comparisons from the monthly columns
    if "ttm" in (recipe.get("derive") or []) and months:
        mcols = [(j, h) for j, h in enumerate(hdr_row) if isinstance(h, dt.datetime)]
        last = max(h for _, h in mcols)
        q_end = [h for _, h in mcols if h.month in (3, 6, 9, 12)]
        anchors = sorted({last, max(q_end)} if q_end else {last})
        targets = {"total revenues": "revenue", "gross profit": "gross profit", "ebitda": "EBITDA",
                   "total cost of operations": "cost of operations",
                   "total selling, general, & adminsitrative": "SG&A",
                   "total selling, general, & administrative": "SG&A"}
        for i, row in enumerate(grid):
            lab = str(row[lc] or "").strip().lower() if lc < len(row) else ""
            if lab not in targets:
                continue
            name = targets[lab]
            for a in anchors:
                ai = a.year * 12 + a.month
                vals = [(h, row[j]) for j, h in mcols
                        if ai - 12 < h.year * 12 + h.month <= ai and isinstance(row[j], (int, float))]
                if len(vals) != 12:
                    continue
                tot = sum(v for _, v in vals)
                eid = f"HPF-V{sec['n']}-TTM-{name.replace(' ', '').replace('&', '')}-{a.strftime('%b%y')}"
                derived.append({
                    "id": eid, "module": "HPF", "module_title": sec["title"], "section_n": sec["n"],
                    "section_key": sec["key"], "section_title": sec["title"], "kind": "field",
                    "label": f"TTM {name} to {a.strftime('%b-%Y')}", "value": f"${tot / 1e6:,.2f}M",
                    "text": f"TTM {name} to {a.strftime('%b-%Y')}: ${tot / 1e6:,.2f}M "
                            f"(sum of 12 months {vals[0][0].strftime('%b-%Y')} to {a.strftime('%b-%Y')})",
                    "citations": {"doc": [vdr_rel], "web": [], "computed": True},
                    "basis": "data_room_computed", "numbers": [f"${tot / 1e6:,.2f}M"], "page": None,
                    "flags": ["COMPUTED"], "class": "fact",
                    "measures": ["fin.revenue" if name == "revenue" else
                                 "fin.ebitda" if name == "EBITDA" else "fin.cost_base"],
                    "subject": "target", "source": "vdr_direct", "recipe": recipe["id"]})
            # YTD vs prior-year same months
            ytd = [(h, row[j]) for j, h in mcols if h.year == last.year and isinstance(row[j], (int, float))]
            py = [(h, row[j]) for j, h in mcols if h.year == last.year - 1 and h.month <= last.month
                  and isinstance(row[j], (int, float))]
            if ytd and len(ytd) == len(py):
                a_, b_ = sum(v for _, v in ytd), sum(v for _, v in py)
                g = (a_ / b_ - 1) * 100 if b_ else None
                per = f"Jan-{MONTHS[last.month - 1]}"
                eid = f"HPF-V{sec['n']}-YTD-{name.replace(' ', '').replace('&', '')}"
                derived.append({
                    "id": eid, "module": "HPF", "module_title": sec["title"], "section_n": sec["n"],
                    "section_key": sec["key"], "section_title": sec["title"], "kind": "field",
                    "label": f"{name} {per} {last.year} vs {last.year - 1}",
                    "value": f"${a_ / 1e6:,.2f}M vs ${b_ / 1e6:,.2f}M"
                             + (f" ({g:+.1f}%)" if g is not None else ""),
                    "text": f"{name} {per} {last.year}: ${a_ / 1e6:,.2f}M vs {per} {last.year - 1}: "
                            f"${b_ / 1e6:,.2f}M" + (f", change {g:+.1f}%" if g is not None else ""),
                    "citations": {"doc": [vdr_rel], "web": [], "computed": True},
                    "basis": "data_room_computed",
                    "numbers": [f"${a_ / 1e6:,.2f}M", f"${b_ / 1e6:,.2f}M"] + ([f"{g:+.1f}%"] if g is not None else []),
                    "page": None, "flags": ["COMPUTED"], "class": "fact",
                    "measures": ["fin.revenue_growth" if name == "revenue" else "fin.ebitda"],
                    "subject": "target", "source": "vdr_direct", "recipe": recipe["id"]})
    return out, derived


def detect_plan_after(files):
    import openpyxl
    for f in files:
        if not re.search(r"monthly financials|management accounts", f.name, re.I):
            continue
        try:
            wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
            for ws in wb.worksheets:
                for row in ws.iter_rows(min_row=1, max_row=4, values_only=True):
                    ds = [c for c in row if isinstance(c, dt.datetime)]
                    if ds:
                        last = max(ds)
                        return last.year if last.month == 12 else last.year - 1
        except Exception:  # noqa: BLE001
            continue
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vdr", required=True, nargs="+")
    ap.add_argument("--work", required=True)
    ap.add_argument("--plan-after", type=int)
    ap.add_argument("--recipes", nargs="*", default=[],
                    help="deal-profile recipe files tried before the generic ones")
    a = ap.parse_args()
    import openpyxl
    cfg = yaml.safe_load((SKILL / "config" / "vdr_extractors.yaml").read_text())
    prof = []
    for rp in a.recipes:
        prof += (yaml.safe_load(Path(rp).read_text()) or {}).get("recipes", [])
    pid = {r["id"] for r in prof}
    cfg["recipes"] = prof + [r for r in cfg["recipes"] if r["id"] not in pid]
    skip_rx = re.compile(cfg.get("skip_sheets", "$^"), re.I)
    fb_mods = [(re.compile(k, re.I), v) for k, v in (cfg.get("fallback_modules") or {}).items()]
    fb_n = 150
    files = []
    for d in a.vdr:
        files += sorted(Path(d).rglob("*.xlsx"))
    files = [f for f in files if not f.name.startswith(("~$", ".~"))]
    plan_after = a.plan_after or (detect_plan_after(files) if cfg.get("plan_after") == "auto" else cfg.get("plan_after"))
    items, derived, log = [], [], []
    for f in files:
        rel = None
        for d in a.vdr:
            try:
                rel = str(f.relative_to(Path(d).parent)).replace("/", "__").replace(" VDR__", " VDR__")
                break
            except ValueError:
                continue
        rel = rel or f.name
        try:
            wb = openpyxl.load_workbook(f, data_only=True, read_only=True)
        except Exception as ex:  # noqa: BLE001
            log.append(f"skip {f.name}: {ex}")
            continue
        for ws in wb.worksheets:
            matched = False
            if skip_rx.search(ws.title.strip()) and not any(
                    rc.get("allow_data") and re.search(rc["sheet"], ws.title.strip(), re.I) for rc in cfg["recipes"]):
                continue                    # raw data / lookup tabs are not evidence
            for rc in cfg["recipes"]:
                if re.search(rc["file"], f.name, re.I) and re.search(rc["sheet"], ws.title.strip(), re.I):
                    got, der = extract_sheet(ws, rc, f, plan_after, rel)
                    if not got and not der:
                        continue            # recipe matched the name but not the layout
                    matched = True
                    items += got
                    derived += der
                    log.append(f"{f.name} :: {ws.title} -> {rc['id']} ({len(got)} rows, {len(der)} derived)")
                    if not rc.get("continue"):
                        break
            if matched or not cfg.get("generic_fallback") or skip_rx.search(ws.title.strip()):
                continue
            # fallback: any other sheet with a period header is read, flagged for verification
            mod = next((m for rx, m in fb_mods if rx.search(ws.title) or rx.search(f.name)), "APX")
            fb_n += 1
            rc = {"id": "generic", "module": mod, "units": "auto", "subject": "target",
                  "max_rows": cfg.get("fallback_max_rows", 40),
                  "section": {"n": fb_n, "key": f"vdr_generic_{fb_n}",
                              "title": f"{ws.title.strip()} ({f.name}) - generic extract, verify"}}
            got, der = extract_sheet(ws, rc, f, plan_after, rel)
            periods = sum(1 for it in got[:1] for st in (it.get("period_status") or {}).values() if st)
            if got and periods >= 2:
                if mod == "APX":            # guess the owner from what the rows measure
                    labels = " ".join(it["row_label"] for it in got)
                    score = Counter()
                    for rx, m in fb_mods:
                        score[m] += len(rx.findall(labels))
                    mod2 = score.most_common(1)[0][0] if score and score.most_common(1)[0][1] else "APX"
                    if mod2 != "APX":
                        for it in got:
                            it["module"] = mod2
                            it["id"] = it["id"].replace("APX-", f"{mod2}-", 1)
                        mod = mod2
                for it in got:
                    it["flags"].append("GENERIC_EXTRACT")
                items += got
                log.append(f"{f.name} :: {ws.title} -> generic/{mod} ({len(got)} rows, verify)")
    # de-duplicate ids (same recipe matched twice)
    seen, uniq = set(), []
    for it in items + derived:
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        uniq.append(it)
    work = Path(a.work)
    inventory = []
    for d in a.vdr:
        for f in sorted(Path(d).rglob("*")):
            if f.is_file() and not f.name.startswith((".", "~$")):
                parts = f.relative_to(Path(d)).parts
                inventory.append({"name": f.name, "section": parts[0] if len(parts) > 1 else ""})
    write_json(work / "vdr_evidence.json", {"plan_after": plan_after, "items": uniq, "log": log,
                                            "files": inventory})
    ev = read_json(work / "evidence.json")
    ev["facts"] = [f for f in ev["facts"] if f.get("source") != "vdr_direct"] + uniq
    write_json(work / "evidence.json", ev)
    nm = merge_management(a.vdr, work)
    print(f"[vdr] management documents: {nm} evidence items (flagged MGMT_REPRESENTATION)")
    print(f"[vdr] actuals through {plan_after}; {len(uniq)} evidence items from "
          f"{sum(1 for l in log if '->' in l)} sheets merged into evidence.json")
    for l in log:
        print("   ", l)



# ============================================================================ management documents
def extract_management_pptx(path: Path, vdr_rel: str, module: str = "CBG"):
    """CIM / management presentation -> evidence. Every item is flagged MGMT_REPRESENTATION:
    admissible, attributed ("the CIM states"), and graded 'asserted' unless corroborated by
    data-room workbooks (claim_rules.yaml). Tables become table_row items; text becomes notes."""
    from pptx import Presentation
    out = []
    prs = Presentation(str(path))
    for pno, slide in enumerate(prs.slides, 1):
        texts, tables = [], []

        def walk(shapes):
            for sh in shapes:
                if sh.shape_type == 6:
                    walk(sh.shapes)
                elif getattr(sh, "has_table", False) and sh.has_table:
                    tables.append([[c.text.strip() for c in r.cells] for r in sh.table.rows])
                elif getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                    t = " ".join(p.text.strip() for p in sh.text_frame.paragraphs if p.text.strip())
                    if t:
                        texts.append(t)
        walk(slide.shapes)
        title = next((t for t in texts if 12 <= len(t) <= 90 and t.upper() == t and not t.isdigit()),
                     next((t for t in texts if 12 <= len(t) <= 90), f"CIM page {pno}"))
        sec = {"n": 200 + pno, "key": f"cim_p{pno}", "title": f"CIM p{pno}: {title.title() if title.isupper() else title}"}
        base = {"module": module, "module_title": "Company background (CIM, management material)",
                "section_n": sec["n"], "section_key": sec["key"], "section_title": sec["title"],
                "citations": {"doc": [vdr_rel], "web": [], "computed": False}, "basis": "data_room_doc",
                "page": pno, "class": "fact", "subject": "target", "source": "vdr_direct",
                "recipe": "cim_pptx"}
        for ti, tb in enumerate(tables, 1):
            if len(tb) < 2:
                continue
            hdr = [h or f"col{j}" for j, h in enumerate(tb[0])]
            for ri, row in enumerate(tb[1:], 1):
                if not any(row[1:]):
                    continue
                cells = {hdr[j]: row[j] for j in range(min(len(hdr), len(row))) if row[j]}
                text = " | ".join(f"{k}: {v}" for k, v in cells.items())
                out.append({**base, "id": f"{module}-C{pno}-T{ti}-R{ri}", "kind": "table_row", "text": text,
                            "table_header": hdr, "cells": cells, "row_label": row[0],
                            "numbers": re.findall(r"[$₹€£]?\d[\d,.]*\s?(?:%|[kKmMbB]n?|x)?", text),
                            "flags": ["MGMT_REPRESENTATION"]})
        for ni, t in enumerate([t for t in texts if len(t) >= 30 and t != title], 1):
            out.append({**base, "id": f"{module}-C{pno}-N{ni}", "kind": "note", "text": t,
                        "numbers": re.findall(r"[$₹€£]?\d[\d,.]*\s?(?:%|[kKmMbB]n?|x)?", t),
                        "flags": ["MGMT_REPRESENTATION"]})
    return out


def merge_management(vdr_dirs, work: Path):
    items = []
    for d in vdr_dirs:
        for f in sorted(Path(d).rglob("*.pptx")):
            if re.search(r"(?<![a-z])cim(?![a-z])|information memorandum|management presentation", f.name, re.I):
                rel = str(f.relative_to(Path(d).parent)).replace("/", "__")
                items += extract_management_pptx(f, rel)
    if not items:
        return 0
    ev = read_json(work / "evidence.json")
    ids = {i["id"] for i in items}
    ev["facts"] = [f for f in ev["facts"] if f["id"] not in ids] + items
    write_json(work / "evidence.json", ev)
    return len(items)


if __name__ == "__main__":
    main()
