#!/usr/bin/env python3
"""C2 - reconcile financial measures across sources and versions.

    python reconcile.py --work <work>

Collects every value of the headline measures (revenue, gross profit / margin, EBITDA / margin,
net income, ARR) for each period from every data-room source and the CIM tie-out, compares them
on the same period and status (actual vs plan), and writes:

    <work>/reconciliation.json   {"rows": [...], "conflicts": [...]}
    <work>/reconciliation.md     one table per measure, differences quantified

A difference inside the rounding of the less precise source is 'consistent (rounding)'; anything
larger than `reconcile.tolerance_pct` (config/controls.yaml) is a conflict. Conflicts are never
resolved by picking one figure: the deck states which basis it uses and why, and the difference
goes into an exception (check_content raises C2 otherwise).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib.common import read_json, write_json, load_yaml  # noqa: E402
from lib.values import parse_value  # noqa: E402
from lib.controls import artefact_of, classify  # noqa: E402

PERIOD = re.compile(r"^(?:fy)?(20\d\d)\s*([pfe])?$|^(20\d\d) ytd|^ttm", re.I)


def norm_label(t):
    t = re.sub(r"\[[^\]]*\]", "", str(t or "")).strip().lower()
    return re.sub(r"\s+", " ", t)


def metric_of(label, rxs):
    for m, rx in rxs.items():
        if re.search(rx, label, re.I):
            return m
    return None


def to_base(v):
    """Value in a comparable unit: currency -> $M, percent -> %. A currency figure printed with no
    scale ("$13.3" in a CIM table headed $M) is kept as `unscaled` and resolved against the other
    sources in its group (see resolve_unscaled)."""
    if v.value is None or v.is_missing or v.is_range:
        return None
    if len(re.findall(r"\d[\d,.]*", v.raw or "")) > 1 and not v.notes:
        return None                                    # a list of figures, not one value
    if v.kind == "currency":
        if not v.scale and abs(v.value) < 1000:
            return ("unscaled", v.value)
        scale = {"": 1e-6, "k": 1e-3, "M": 1.0, "B": 1e3}.get(v.scale, None)
        return None if scale is None else v.value * scale
    if v.kind == "percent":
        return v.value
    return None


def decimals(raw):
    m = re.search(r"\d[\d,]*\.(\d+)", raw or "")
    return len(m.group(1)) if m else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    work = Path(a.work)
    cfgc = load_yaml("controls.yaml")["reconcile"]
    rxs = cfgc["metrics"]
    facts = read_json(work / "evidence.json")["facts"]
    rows = []
    for f in facts:
        if f.get("source") != "vdr_direct":
            continue
        label = norm_label(f.get("row_label") or f.get("label") or "")
        cells = f.get("cells") or {}
        # CIM tie-out rows: "Revenue 2025" | Value in the CIM | Support
        m_ = re.match(r"^([^,]*?)\s+(20\d\d)(p)?$", label)
        if "Value in the CIM" in cells and m_:
            met = metric_of(m_.group(1), rxs)
            if met:
                per, st = m_.group(2) + ("P" if m_.group(3) else ""), ("plan" if m_.group(3) else "actual")
                for col, src in (("Value in the CIM", "CIM"), ("Support", "CIM support schedule")):
                    v = parse_value(cells.get(col, ""))
                    b = to_base(v)
                    if b is not None:
                        rows.append({"metric": met, "period": per, "status": st, "value": b, "raw": v.raw,
                                     "dec": decimals(v.raw), "unit": v.kind, "ref": f["id"], "source": src})
            continue
        met = metric_of(label, rxs)
        if not met:
            continue
        ps = f.get("period_status") or {}
        for col, raw in cells.items():
            pm = PERIOD.match(str(col).strip())
            if not pm or col == "Line":
                continue
            per = str(col).strip()
            if re.search(r"ytd|ttm|at \d", per, re.I):
                continue                                    # part periods are compared separately
            v = parse_value(raw, f"{col} {label}")
            b = to_base(v)
            if b is None:
                continue
            st = "plan" if (ps.get(col) == "plan" or per.upper().endswith("P")) else "actual"
            per = re.sub(r"\s*p$", "P", per, flags=re.I) if st == "plan" else re.sub(r"\D", "", per)
            rows.append({"metric": met, "period": per, "status": st, "value": b, "raw": str(raw),
                         "dec": decimals(str(raw)), "unit": v.kind, "ref": f["id"],
                         "source": artefact_of(f) or f.get("section_title", ""), "class": classify(f["id"], {f["id"]: f})})
    groups = defaultdict(list)
    for r in rows:
        groups[(r["metric"], r["period"], r["status"], r["unit"])].append(r)
    # resolve unscaled currency against scaled peers: accept $M when within 20% of their median
    for key, vals in groups.items():
        scaled = sorted(v["value"] for v in vals if not isinstance(v["value"], tuple))
        med = scaled[len(scaled) // 2] if scaled else None
        keep = []
        for v in vals:
            if isinstance(v["value"], tuple):
                x = v["value"][1]
                if med and abs(x - med) <= 0.2 * abs(med):
                    v["value"] = x
                    v["raw"] += " (read as $M from its table)"
                    keep.append(v)
            else:
                keep.append(v)
        groups[key] = keep
    conflicts, table = [], []
    tol = float(cfgc.get("tolerance_pct", 0.5))
    for (met, per, st, unit), vals in sorted(groups.items()):
        uniq = {}
        for v in vals:
            uniq.setdefault((v["source"], round(v["value"], 6)), v)
        vals = list(uniq.values())
        if len({v["source"] for v in vals}) < 2:
            continue
        lo, hi = min(v["value"] for v in vals), max(v["value"] for v in vals)
        spread = (hi - lo) / abs(lo) * 100 if lo else 0.0
        # allowance for the least precise source (e.g. "$13.3mn" is +/- 0.05)
        allow = max(0.5 * 10 ** -v["dec"] for v in vals)
        status = "consistent" if hi - lo <= 1e-9 else ("consistent (rounding)" if hi - lo <= allow + 1e-9 or spread <= tol
                                                       else "CONFLICT")
        rec = {"metric": met, "period": per, "status": st, "unit": unit, "spread_abs": round(hi - lo, 4),
               "spread_pct": round(spread, 2), "result": status,
               "values": [{"source": v["source"], "raw": v["raw"], "value": round(v["value"], 4), "ref": v["ref"]}
                          for v in sorted(vals, key=lambda x: x["value"])]}
        table.append(rec)
        if status == "CONFLICT":
            conflicts.append(rec)
    write_json(work / "reconciliation.json", {"rows": table, "conflicts": conflicts})
    lines = ["# Reconciliation of headline measures (C2)", "",
             f"{len(table)} measure-periods seen in two or more sources; {len(conflicts)} conflicts "
             f"(> {tol}% after rounding).", "",
             "| Measure | Period | Status | Values by source | Spread | Result |", "|---|---|---|---|---|---|"]
    for r in table:
        vs = "; ".join(f"{v['source']}: {v['raw']}" for v in r["values"])
        lines.append(f"| {r['metric']} | {r['period']} | {r['status']} | {vs} | {r['spread_abs']} "
                     f"({r['spread_pct']}%) | {r['result']} |")
    (work / "reconciliation.md").write_text("\n".join(lines) + "\n")
    print(f"[reconcile] {len(table)} comparable measure-periods; {len(conflicts)} conflicts -> reconciliation.md")


if __name__ == "__main__":
    main()
