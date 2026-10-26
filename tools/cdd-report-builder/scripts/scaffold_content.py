#!/usr/bin/env python3
"""Step 4: turn the ontology + the evidence base into a per-slide drafting pack.

Usage: python scaffold_content.py --work <work>

Writes:
  <work>/drafting_pack.md      for every slide that will render: the blueprint contract
                               (purpose, what it must contain, the analysis it performs, the
                               quality bar), the DiligenceIQ mapping (modules, metrics, rules,
                               gate) and the candidate evidence - id, fact/interpretation,
                               flags and text - drawn from its primary and secondary modules.
  <work>/content_skeleton.json a content.json skeleton for the rendering slides only.
  <work>/withheld.md           the slides the gates removed, with the reason and what would
                               unlock each one. This is drafting input too: the exceptions
                               appendix is built from it.

Nothing here invents text. It selects evidence and restates the contract.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import read_json, slide_map, write_json  # noqa: E402

# Which module sections are worth surfacing for a given metric class, so a 9-row table
# is not offered 400 candidate rows.
SECTION_HINTS = {
    "market":      ("size", "tam", "sam", "growth", "cagr", "perimeter", "definition", "taxonomy",
                    "driver", "lifecycle", "volume"),
    "financial":   ("revenue", "mix", "cost", "margin", "cash", "debt", "capital", "quality"),
    "customer":    ("segment", "tier", "retention", "churn", "loyalty", "satisfaction", "persona",
                    "procurement", "purchase", "switch", "criteria"),
    "competitive": ("competitor", "capability", "differen", "moat", "barrier", "share", "win",
                    "position", "price"),
    "operational": ("supplier", "supply", "process", "scalab", "continuity", "technology", "infra"),
    "valuation":   ("valuation", "multiple", "football", "synerg", "scenario", "sensitiv", "bid"),
    "esg":         ("esg", "impact", "sustain"),
    "risk":        ("risk", "threat", "exposure", "compliance", "litigation", "mitigat"),
}


def candidates(sd, facts_by_mod, limit_per_module=14):
    """Evidence from this slide's modules, facts first, populated first, flagged last."""
    out, seen = [], set()
    metric_classes = {m.split(".")[0] for m in sd.get("metrics", [])}
    hints = set()
    for c in metric_classes:
        hints |= set(SECTION_HINTS.get({"mkt": "market", "fin": "financial", "cust": "customer",
                                        "comp": "competitive", "ops": "operational",
                                        "val": "valuation", "esg": "esg", "risk": "risk"}.get(c, c), ()))

    def score(f):
        s = 0
        if f["class"] == "fact":
            s -= 4
        if not f.get("flags"):
            s -= 2
        if any(x in (f.get("section_key", "") + f.get("section_title", "")).lower() for x in hints):
            s -= 3
        if any(x in (f.get("flags") or []) for x in ("NA", "PLACEHOLDER")):
            s += 6
        if f["kind"] in ("verdict", "snapshot"):
            s -= 1
        return s

    for role, weight in (("primary_modules", 0), ("fallback_modules", 1), ("secondary_modules", 2)):
        for code in sd.get(role, []) or []:
            rows = sorted(facts_by_mod.get(code, []), key=score)[:limit_per_module]
            for f in rows:
                if f["id"] in seen:
                    continue
                seen.add(f["id"])
                out.append((role.split("_")[0], f))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    work = Path(a.work)
    facts = read_json(work / "evidence.json")["facts"]
    sm = slide_map()
    gates = {}
    if (work / "gates.json").exists():
        gates = {g["id"]: g for g in read_json(work / "gates.json")}
    cov = read_json(work / "coverage.json") if (work / "coverage.json").exists() else {}

    facts_by_mod = defaultdict(list)
    for f in facts:
        facts_by_mod[f["module"]].append(f)

    md = ["# Drafting pack", "",
          "For every slide that will render: the blueprint contract, the ontology mapping and the",
          "candidate evidence. Rules: every text unit, bullet and table row carries `refs`;",
          "F = fact (source-reported), I = interpretation (an agent's view - attribute it).",
          "Items flagged NA / PLACEHOLDER are not evidence. OCR_* / TABLE_CLIPPED must be checked on",
          "the page image (python scripts/crop_evidence.py --work <work> --id <ID>) before a figure",
          "is used. Never state a metric this slide is not listed as able to state.", ""]
    if cov:
        md += [f"Corpus: {sum(1 for m in cov['modules'].values() if m['present'])}/{len(cov['modules'])} "
               f"modules; document types {', '.join(cov['doc_types'])}; "
               f"primary research {'present' if set(cov['doc_types']) & {'survey', 'interviews'} else 'ABSENT'}.", ""]

    skeleton = {"project": {"name": "", "target": "", "client": "", "date": "",
                            "status": "Draft for discussion", "footer": ""},
                "slides": {}, "calculations": [], "exceptions": [], "metrics": {},
                "force_render": []}
    withheld = ["# Slides withheld by a coverage gate", "",
                "Each row is an exception. The deck does not contain these pages; the exceptions",
                "appendix (S101) must state every one of them with the follow-up that would unlock it.", "",
                "| Slide | Blueprint | Gate | Exception | Reason | Unlocked by |",
                "|---|---|---|---|---|---|"]

    UNLOCK = {
        "E11-NO-PRIMARY": "a customer survey export or an interview programme in the data room",
        "E1-NOT-PROVIDED": "populated findings from the module(s) named, i.e. a data-room response "
                           "to the outstanding request",
        "E9-BLOCKER": "the missing core module - the report cannot be issued without it",
    }

    for sd in sm["slides"]:
        g = gates.get(sd["id"])
        if g and not g["render"]:
            withheld.append(f"| {sd['id']} | {sd['no']:02d} {sd['blueprint_title']} | {sd['gate']} | "
                            f"{g['exception']} | {g['reason']} | "
                            f"{UNLOCK.get(g['exception'], 'see reason')} |")
            continue

        md.append(f"## {sd['id']}  ({sd['no']:02d} · {sd['archetype']} · gate: {sd['gate']})")
        md.append(f"**{sd['blueprint_title']}** — {sd['purpose']}")
        if g and g.get("substituted_with"):
            md.append(f"> SUBSTITUTED: module-of-record absent; built from "
                      f"{', '.join(g['substituted_with'])}. Say so on the slide and log "
                      f"{g['exception']}.")
        md.append("")
        md.append("**Must contain**")
        for b in sd["must_contain"]:
            md.append(f"- {b}")
        md.append(f"\n**Analysis** — {sd['analysis']}")
        md.append(f"**Exhibit** — {sd['exhibit_spec']} (form: `{sd['exhibit']}`)")
        md.append(f"**Quality bar** — {sd['quality_bar']}")
        mapping = []
        if sd["primary_modules"]:
            mapping.append("primary " + ", ".join(sd["primary_modules"]))
        if sd["secondary_modules"]:
            mapping.append("secondary " + ", ".join(sd["secondary_modules"]))
        if sd["metrics"]:
            mapping.append("may state " + ", ".join(sd["metrics"]))
        for k, lbl in (("transform", "T"), ("calc", "C"), ("source_priority", "R"), ("exception", "E")):
            if sd.get(k):
                mapping.append(f"{lbl}: " + ", ".join(sd[k]))
        md.append("**Mapping** — " + "; ".join(mapping) if mapping else "")
        md.append("")

        if sd["archetype"] in ("divider", "contents"):
            md.append("_auto / fixed_\n")
            skeleton["slides"][sd["id"]] = {"elements": {}}
            continue

        sk = {"title": {"text": "", "refs": []}, "subtitle": {"text": "", "refs": []}, "elements": {}}
        if sd["archetype"] in ("cover", "back_cover", "disclaimer", "text_panel"):
            sk = {"elements": {}}

        cands = candidates(sd, facts_by_mod)
        if cands:
            md.append("**Candidate evidence**")
            for role, f in cands:
                tag = "F" if f["class"] == "fact" else "I"
                fl = ",".join(f.get("flags") or [])
                md.append(f"- `{f['id']}` [{tag}·{role}]{' {'+fl+'}' if fl else ''} "
                          f"{' '.join(f['text'].split())[:240]}")
            md.append("")
        else:
            md.append("_No candidate evidence from the mapped modules — this slide should not have "
                      "passed its gate; check coverage.json._\n")

        for el in sd.get("elements", []):
            md.append(f"### {el['name']} [{el['type']}]"
                      + (f" — {el['head']}" if el.get("head") else ""))
            md.append(f"- limits: {el.get('limits', {})}")
            md.append("")
            sk["elements"][el["name"]] = {"type": el["type"], "refs": [],
                                          "_candidates": [f["id"] for _, f in cands][:24]}
        skeleton["slides"][sd["id"]] = sk

    (work / "drafting_pack.md").write_text("\n".join(md), encoding="utf-8")
    (work / "withheld.md").write_text("\n".join(withheld) + "\n", encoding="utf-8")
    write_json(work / "content_skeleton.json", skeleton)
    n_render = len(skeleton["slides"])
    print(f"[scaffold] {n_render} slides to draft; {len(withheld) - 6} withheld; "
          f"drafting_pack.md, withheld.md, content_skeleton.json -> {work}")


if __name__ == "__main__":
    main()
