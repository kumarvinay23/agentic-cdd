#!/usr/bin/env python3
"""Maintainer script: regenerate references/02_slide_mapping.md from config/slide_map.yaml.

    python scripts/export_mapping.py [--out references/02_slide_mapping.md] [--xlsx FILE.xlsx]

One section per slide, carrying both halves of the contract:
  * the blueprint's own requirement - purpose, what the page must contain, admissible sources,
    the analysis it performs, the exhibit form and the quality bar;
  * the DiligenceIQ mapping - gate, modules, metrics and the T/C/R/E rules that govern drafting.
Run after any edit to slide_map.yaml, and rebuild the template in the same pass.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
SM = yaml.safe_load((SKILL / "config" / "slide_map.yaml").read_text())
SEC = {s["id"]: s["name"] for s in SM["sections"]}
GATE_NOTE = {
    "always": "rendered unconditionally",
    "derived": "built from run data",
    "core": "must render; built from fallback modules if the module-of-record is absent (E12), "
            "blocker if neither is available (E9)",
    "conditional": "rendered only if the primary modules supply >= 3 populated facts; otherwise "
                   "withheld and logged E1",
    "research_gated": "rendered only if the corpus contains a survey or interview source; "
                      "otherwise withheld and logged E11",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(SKILL / "references" / "02_slide_mapping.md"))
    ap.add_argument("--xlsx")
    a = ap.parse_args()

    L = ["# Slide-by-slide mapping specification", "",
         "_Generated from `config/slide_map.yaml` by `scripts/export_mapping.py` — edit the YAML, "
         "not this file._", "",
         f"{len(SM['slides'])} slides: the {sum(1 for s in SM['slides'] if s['provenance'] == 'blueprint')}"
         "-page CDD reporting blueprint plus a DiligenceIQ evidence-and-audit appendix.",
         "",
         "Each slide carries two contracts. The **blueprint contract** (purpose, must contain, "
         "sources, analysis, exhibit, quality bar) is what the page owes the reader. The "
         "**mapping** is how this skill satisfies it from agent outputs: which modules feed it, "
         "which metrics it may state, which rules govern the transformation, and the coverage "
         "**gate** that decides whether the page can be produced at all.", "",
         "Evidence rule for every element: every text unit, bullet and table row carries `refs` to "
         "evidence ids (`MOD-sec-kind-row`); the renderer builds the source line and a speaker-note "
         "evidence trail; calculated values carry † and a calculation id.", ""]

    # index
    L += ["## Index", "", "| # | Slide | Section | Gate | Exhibit | Primary modules |",
          "|---|---|---|---|---|---|"]
    for s in SM["slides"]:
        L.append(f"| {s['no']:02d} | `{s['id']}` | {SEC[s['section']]} | {s['gate']} | "
                 f"{s['exhibit']} | {', '.join(s['primary_modules']) or '—'} |")
    L.append("")

    for s in SM["slides"]:
        L.append(f"## {s['no']:02d} · {s['id']} — {s['blueprint_title']}")
        L.append(f"_{SEC[s['section']]} · archetype `{s['archetype']}` · exhibit `{s['exhibit']}` · "
                 f"gate **{s['gate']}**_"
                 + ("  · _DiligenceIQ extension, not in the blueprint_"
                    if s["provenance"] != "blueprint" else ""))
        L.append("")
        L.append(f"**Purpose** — {s['purpose']}")
        L.append("")
        L.append("**Must contain**")
        for b in s["must_contain"]:
            L.append(f"- {b}")
        L.append("")
        L.append(f"**Admissible sources** — {s['source_spec']}")
        L.append(f"**Analysis** — {s['analysis']}")
        L.append(f"**Exhibit** — {s['exhibit_spec']}")
        L.append(f"**Quality bar** — {s['quality_bar']}")
        L.append(f"**Gate** — {s['gate']}: {GATE_NOTE.get(s['gate'], '')}")
        L.append("")
        rows = []
        if s["primary_modules"]:
            rows.append(("Primary modules", ", ".join(s["primary_modules"])))
        if s.get("fallback_modules"):
            rows.append(("Fallback modules", ", ".join(s["fallback_modules"]) +
                         " — use raises E12-SUBSTITUTION and must be stated on the slide"))
        if s["secondary_modules"]:
            rows.append(("Secondary modules", ", ".join(s["secondary_modules"])))
        if s["metrics"]:
            rows.append(("Metrics this slide may state", ", ".join(f"`{m}`" for m in s["metrics"])))
        for k, lbl in (("transform", "Transformation rules"), ("calc", "Calculations"),
                       ("source_priority", "Source priority"), ("exception", "Exception handling")):
            if s.get(k):
                rows.append((lbl, ", ".join(s[k])))
        if rows:
            L += ["| Mapping | Value |", "|---|---|"]
            L += [f"| {k} | {v} |" for k, v in rows]
            L.append("")
        els = s.get("elements") or []
        if els:
            L += ["| Element | Type | Panel heading | Limits |", "|---|---|---|---|"]
            for e in els:
                L.append(f"| `{e['name']}` | {e['type']} | {e.get('head', '—')} | "
                         f"{e.get('limits', {}) or '—'} |")
            L.append("")
        if s.get("repeatable"):
            L.append("_Repeatable: supply a list of pages in content.json when the content exceeds "
                     "one page._\n")

    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"wrote {a.out} ({len(SM['slides'])} slides)")

    if a.xlsx:
        from openpyxl import Workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "slide_map"
        ws.append(["No", "Slide id", "Section", "Archetype", "Exhibit", "Gate", "Blueprint title",
                   "Purpose", "Must contain", "Sources", "Analysis", "Exhibit spec", "Quality bar",
                   "Primary", "Fallback", "Secondary", "Metrics", "Transform", "Calc",
                   "Source priority", "Exception"])
        for s in SM["slides"]:
            ws.append([s["no"], s["id"], SEC[s["section"]], s["archetype"], s["exhibit"], s["gate"],
                       s["blueprint_title"], s["purpose"], "\n".join(s["must_contain"]),
                       s["source_spec"], s["analysis"], s["exhibit_spec"], s["quality_bar"],
                       ", ".join(s["primary_modules"]), ", ".join(s.get("fallback_modules", [])),
                       ", ".join(s["secondary_modules"]), ", ".join(s["metrics"]),
                       ", ".join(s["transform"]), ", ".join(s["calc"]),
                       ", ".join(s["source_priority"]), ", ".join(s["exception"])])
        ws2 = wb.create_sheet("elements")
        ws2.append(["Slide id", "Element", "Type", "Panel heading", "Limits"])
        for s in SM["slides"]:
            for e in s.get("elements") or []:
                ws2.append([s["id"], e["name"], e["type"], e.get("head", ""), str(e.get("limits", ""))])
        wb.save(a.xlsx)
        print(f"wrote {a.xlsx}")


if __name__ == "__main__":
    sys.exit(main())
