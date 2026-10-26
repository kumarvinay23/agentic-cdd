#!/usr/bin/env python3
"""Prioritised issue register and revised conclusion for the deal team (controls C1-C6).

    python review_register.py --work <work> [--content <content.json>] [--out <register.xlsx>]

Inputs
  content.json -> issues[]      analyst-reviewed issues (the register's backbone)
               -> conclusion    revised conclusion at the confidence the evidence supports
  check_report.json             automated C1-C6 flags (filed as P3 'review' rows when no analyst
                                issue already covers that control on that slide)
  reconciliation.json           C2 conflicts, quantified
  claim_register.json           every claim with its source classes and grade

Issue fields (content.json -> issues[]):
  id, priority (1 = must resolve before a decision, 2 = before signing, 3 = residual),
  control (C1..C6 or other), claim, slides, problem, impact, correction, evidence_required,
  could_change (subset of price / structure / decision), pre_decision (mandatory | residual),
  status (corrected | qualified | withheld | open)

Outputs  <work>/issue_register.xlsx (register, conclusion, reconciliation, claim grades,
         automated flags) and <work>/issue_register.md
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib.common import read_json  # noqa: E402

CONTROL_NAMES = {
    "C1": "Contracted vs recurring", "C2": "Reconciliation", "C3": "Figure integrity",
    "C4": "Population comparability", "C5": "Claim-level evidence", "C6": "Net incremental value",
}
COLS = ["ID", "Priority", "Control", "Claim", "Slide / section", "Problem", "Quantified impact",
        "Proposed correction", "Evidence required", "Could change", "Pre-decision", "Status"]


def slide_ref(s):
    return ", ".join(sorted({re.sub(r"_.*", "", x) for x in (s if isinstance(s, list) else [s]) if x}))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--content")
    ap.add_argument("--out")
    a = ap.parse_args()
    work = Path(a.work)
    content = read_json(Path(a.content) if a.content else work / "content.json")
    chk = read_json(work / "check_report.json") if (work / "check_report.json").exists() else {}
    recon = read_json(work / "reconciliation.json") if (work / "reconciliation.json").exists() else {}
    claims = read_json(work / "claim_register.json") if (work / "claim_register.json").exists() else []

    issues = sorted(content.get("issues", []), key=lambda i: (i.get("priority", 3), i.get("id", "")))
    covered = {(i.get("control"), re.sub(r"_.*", "", s)) for i in issues for s in (i.get("slides") or [])}
    auto = defaultdict(list)
    for sev, lst in (("error", chk.get("errors", [])), ("warning", chk.get("warnings", []))):
        for e in lst:
            m = re.match(r"(C[1-6]):\s*(.*)", e["msg"])
            if not m:
                continue
            sl = re.sub(r"[ .].*", "", e["where"]).split("_")[0]
            if (m.group(1), sl) in covered:
                continue
            auto[(m.group(1), sl)].append((sev, e["where"], m.group(2)))
    n = len(issues)
    auto_rows = []
    for (ctl, sl), items in sorted(auto.items()):
        n += 1
        auto_rows.append({
            "id": f"A{n:02d}", "priority": 2 if any(s == "error" for s, _, _ in items) else 3, "control": ctl,
            "claim": f"{len(items)} automated flag(s) on {sl}", "slides": [sl],
            "problem": items[0][2][:240], "impact": "not quantified (automated flag)",
            "correction": "Review each flagged element; correct, attribute or withhold", "evidence_required": "see flag",
            "could_change": [], "pre_decision": "residual", "status": "open"})
    rows = issues + auto_rows

    # ---------------------------------------------------------------- markdown
    concl = content.get("conclusion") or {}
    md = ["# Diligence issue register", "",
          f"{len(issues)} reviewed issues; {len(auto_rows)} groups of automated control flags; "
          f"{len(recon.get('conflicts', []))} unreconciled measure-periods.", "",
          "| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS)]
    for i in rows:
        md.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in [
            i["id"], f"P{i.get('priority', 3)}", f"{i.get('control', '')} {CONTROL_NAMES.get(i.get('control'), '')}",
            i.get("claim", ""), slide_ref(i.get("slides", [])), i.get("problem", ""), i.get("impact", ""),
            i.get("correction", ""), i.get("evidence_required", ""), ", ".join(i.get("could_change") or []) or "no",
            i.get("pre_decision", ""), i.get("status", "")]) + " |")
    if concl:
        md += ["", "## Revised conclusion", "", f"**Confidence: {concl.get('confidence', '')}**", "",
               concl.get("statement", ""), "", "### Usable now", ""]
        md += [f"- {u}" for u in concl.get("usable", [])]
        md += ["", "### Depends on unresolved work", ""]
        md += [f"- {d['finding']} (depends on {', '.join(d.get('depends_on', []))})" for d in concl.get("dependent", [])]
    (work / "issue_register.md").write_text("\n".join(md) + "\n")

    # ---------------------------------------------------------------- workbook
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    hdr_fill, hdr_font = PatternFill("solid", fgColor="14213D"), Font(bold=True, color="FFFFFF")
    pfill = {1: "F6E0DD", 2: "FBEFD9", 3: "EEF1F5"}
    wrap = Alignment(wrap_text=True, vertical="top")

    def sheet(ws, cols, data, widths):
        ws.append(cols)
        for c in ws[1]:
            c.fill, c.font, c.alignment = hdr_fill, hdr_font, wrap
        for r in data:
            ws.append(r)
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = wrap
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Issue register"
    sheet(ws, COLS, [[i["id"], f"P{i.get('priority', 3)}",
                      f"{i.get('control', '')} {CONTROL_NAMES.get(i.get('control'), '')}".strip(),
                      i.get("claim", ""), slide_ref(i.get("slides", [])), i.get("problem", ""), i.get("impact", ""),
                      i.get("correction", ""), i.get("evidence_required", ""),
                      ", ".join(i.get("could_change") or []) or "no", i.get("pre_decision", ""), i.get("status", "")]
                     for i in rows], [6, 8, 20, 34, 12, 46, 30, 40, 40, 16, 13, 12])
    for r in range(2, ws.max_row + 1):
        p = int(str(ws.cell(r, 2).value)[1:])
        ws.cell(r, 2).fill = PatternFill("solid", fgColor=pfill.get(p, "FFFFFF"))
        ws.cell(r, 2).font = Font(bold=True)

    wc = wb.create_sheet("Revised conclusion")
    wc.column_dimensions["A"].width = 26
    wc.column_dimensions["B"].width = 110
    wc.append(["Confidence", concl.get("confidence", "")])
    wc.append(["Conclusion", concl.get("statement", "")])
    for u in concl.get("usable", []):
        wc.append(["Usable now", u])
    for d_ in concl.get("dependent", []):
        wc.append(["Depends on open work", f"{d_['finding']}  [{', '.join(d_.get('depends_on', []))}]"])
    for row in wc.iter_rows():
        for c in row:
            c.alignment = wrap
        row[0].font = Font(bold=True)

    wr = wb.create_sheet("Reconciliation")
    sheet(wr, ["Measure", "Period", "Status", "Values by source", "Spread", "Spread %", "Result"],
          [[r["metric"], r["period"], r["status"], "\n".join(f"{v['source']}: {v['raw']}" for v in r["values"]),
            r["spread_abs"], r["spread_pct"], r["result"]] for r in recon.get("rows", [])],
          [16, 9, 9, 70, 10, 10, 20])

    wg = wb.create_sheet("Claim grades")
    sheet(wg, ["Slide", "Element", "Claim", "Grade", "Source classes", "Refs"],
          [[c["slide"], c["element"], c["claim"][:500], c["grade"], ", ".join(c["source_classes"]),
            ", ".join(map(str, c["refs"]))[:300]] for c in claims], [22, 16, 80, 12, 34, 40])

    wf = wb.create_sheet("Automated flags")
    sheet(wf, ["Severity", "Where", "Flag"],
          [["error", e["where"], e["msg"]] for e in chk.get("errors", [])] +
          [["warning", e["where"], e["msg"]] for e in chk.get("warnings", [])], [10, 40, 120])

    out = Path(a.out) if a.out else work / "issue_register.xlsx"
    wb.save(out)
    print(f"[register] {len(issues)} reviewed issues + {len(auto_rows)} automated groups -> {out}")


if __name__ == "__main__":
    main()
