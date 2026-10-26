#!/usr/bin/env python3
"""Rebuild the derived pages after the analyst has edited content.json.

    python finalize_content.py --work <work> [--content <content.json>]

The analyst pass rewrites findings pages, adds exceptions and withholds pages. The pages that are
*about* the deck must then be regenerated from what the deck now says, or they go stale:

  * S099 / S100       - module verdicts and source register, from the final evidence base
  * S101 exceptions   - from content.exceptions (uses each exception's `short` / `treatment_short`
                        when given, else whole sentences; never a mid-word cut)
  * S007 glossary     - only the terms the finished deck actually uses (+ content.glossary_extra)
  * withhold          - every id in content.withhold is removed from slides and listed in one
                        E13-WITHHELD exception, with its reason
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib.common import read_json, write_json, load_yaml  # noqa: E402
import draft_baseline as db  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--content")
    a = ap.parse_args()
    work = Path(a.work)
    cp = Path(a.content) if a.content else work / "content.json"
    content = read_json(cp)
    db.STRONG = re.compile("|".join(f"(?:{p['rx']})" for p in load_yaml("claim_rules.yaml")["patterns"]), re.I)
    d = db.Drafter(work, content["project"])
    w = content.get("withhold") or []
    for x in w:
        content["slides"].pop(x["id"], None)
    content["exceptions"] = [e for e in content["exceptions"] if e.get("rule") != "E13-WITHHELD"]
    if w:
        content["exceptions"].append({
            "severity": "MEDIUM", "rule": "E13-WITHHELD",
            "issue": f"{len(w)} standard pages withheld: the evidence does not support them or they would repeat another page.",
            "short": f"{len(w)} standard pages withheld (no basis in evidence, or duplicate of another page)",
            "slides": [x["id"] for x in w], "source": "content.withhold",
            "treatment": "Each is listed in withheld.md with its reason and the request that would unlock it.",
            "treatment_short": "Listed with reasons; unlock via the data requests on this page"})
    # C5: 'Grade' columns are recomputed from each row's refs so a table never claims more
    # support than its sources give (management workbooks grade 'indicated', CIM 'asserted')
    from lib.controls import claim_grade
    facts = {f["id"]: f for f in read_json(work / "evidence.json")["facts"]}
    regraded = 0
    for sid, sc in content["slides"].items():
        for page in (sc if isinstance(sc, list) else [sc]):
            for el in ((page or {}).get("elements") or {}).values():
                if not isinstance(el, dict) or el.get("type") != "table" or "Grade" not in el.get("columns", []):
                    continue
                gi = el["columns"].index("Grade")
                for ri, row in enumerate(el["rows"]):
                    if str(row[gi]).strip().lower() not in ("established", "indicated", "asserted", "unsupported"):
                        continue
                    refs = (el.get("row_refs") or [[]] * len(el["rows"]))[ri]
                    # forward-looking if the row label or the table's headers are (plan year, scenario...)
                    lab = [str(c) for c in row if not re.fullmatch(r"\s*\d+\s*", str(c))][:2]
                    g = claim_grade(refs, facts, text=" ".join(el["columns"] + lab))[0]
                    if g != row[gi]:
                        row[gi] = g
                        regraded += 1
    if regraded:
        print(f"[finalize] {regraded} table grades restated from source classes (C5)")
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    content["exceptions"].sort(key=lambda e: order.get(e["severity"], 9))
    if "S099_module_verdicts" in content["slides"]:
        content["slides"]["S099_module_verdicts"] = d.module_verdicts(content)
    if "S100_source_register" in content["slides"]:
        content["slides"]["S100_source_register"] = d.source_register()
    if "S101_exceptions" in content["slides"]:
        content["slides"]["S101_exceptions"] = d.exceptions_slide(content["exceptions"])
    if "S007_glossary" in content["slides"]:
        content["slides"].pop("S007_glossary")
        content["slides"]["S007_glossary"] = d.glossary(content, content.get("glossary_extra"))
    write_json(cp, content)
    lines = ["# Withheld pages", ""] + [f"- **{x['id']}** ({x.get('exception', 'E13-WITHHELD')}): {x['reason']}" for x in w]
    (work / "withheld.md").write_text("\n".join(lines) + "\n")
    print(f"[finalize] {len(content['slides'])} slides; {len(content['exceptions'])} exceptions; {len(w)} withheld")


if __name__ == "__main__":
    main()
