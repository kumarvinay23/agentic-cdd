#!/usr/bin/env python3
"""Turn the evidence index into the coverage picture the ontology's gates consume.

    python coverage.py --work <work>            -> <work>/coverage.json + coverage.md
    python ontology.py gates --work <work>      -> <work>/gates.json

coverage.json is deliberately small and explicit:

    {
      "modules":  {CODE: {present, populated_facts, facts, coverage_pct, confidence, verdict_stance}},
      "doc_types": [DocType ids evidenced anywhere in the corpus],
      "survey_n":  int | null,
      "missing_core": [CODE, ...],
      "substituted": {CODE: [CODE, ...]},
      "source_artifacts": {"resolved": n, "absent": n, "web": n}
    }

DocType inference runs over the citations the agents actually made, resolved against
config/vdr_taxonomy.yaml. A corpus with no survey or interview artefact leaves the
research_gated slides unrenderable - which is a finding about the engagement, not a bug.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


FILENAME_HINTS = [
    ("survey",             [r"survey", r"responses", r"\bnps\b", r"questionnaire"]),
    ("interviews",         [r"interview", r"stakeholder", r"expert", r"verbatim", r"transcript"]),
    ("financials",         [r"financial", r"p&l", r"pnl", r"balance", r"cashflow", r"cash flow",
                            r"depreciation", r"loanschedule", r"loan schedule", r"debtschedule",
                            r"monthlyfinancial", r"trialbalance"]),
    ("cap_table",          [r"cap", r"capitalization", r"capitalisation", r"securitiesledger", r"equityledger"]),
    ("projections",        [r"projection", r"forecast", r"budget", r"investorworkbook", r"workbook", r"assumption"]),
    ("market_model",       [r"tam", r"sam", r"som", r"marketsizing", r"expansionanalysis", r"marketmodel"]),
    ("cim",                [r"\bcim\b", r"teaser", r"processletter", r"informationmemorandum", r"lendermemorandum"]),
    ("contract",           [r"agreement", r"contract", r"lease", r"grant", r"\bmsa\b", r"\bsow\b", r"fpep"]),
    ("legal",              [r"litigation", r"legal", r"claim", r"licence", r"license", r"permit", r"proceeding"]),
    ("esg",                [r"\besg\b", r"impact", r"carbon", r"ghg", r"diversion", r"sustainab", r"baselinemetric"]),
    ("marketing",          [r"proposal", r"marketing", r"map", r"deck", r"collateral", r"salesproposal"]),
    ("kpi_pack",           [r"\bkpi\b", r"revenueby", r"metric", r"dashboard", r"cohort", r"retention"]),
    ("firmographic",       [r"firmographic", r"companylist", r"partnerlist"]),
    ("statistical_series", [r"census", r"bureau", r"statistic", r"\bfred\b", r"macro"]),
    ("analyst",            [r"gartner", r"forrester", r"idc", r"mckinsey", r"grandview", r"marketsandmarkets",
                            r"statista", r"mordor", r"ibisworld", r"researchandmarkets"]),
]


def infer_doc_type(name: str, vdr_path: str | None, vdr) -> str:
    """Filename hints first, then the VDR node's canonical_for, then 'web'/'unknown'."""
    n = norm(name)
    for dt, pats in FILENAME_HINTS:
        if any(re.search(p, n) for p in pats):
            return dt
    if vdr_path:
        code = re.match(r"(\d+(?:_\d+)*)", vdr_path.lstrip("_"))
        if code:
            parts = code.group(1).split("_")
            sec = vdr["sections"].get(parts[0])
            if sec:
                sub = sec.get("subsections", {}).get("_".join(parts[:2])) if len(parts) > 1 else None
                top = (sub or {}).get("topics", {}).get("_".join(parts[:3])) if len(parts) > 2 else None
                for node in (top, sub, sec):
                    if node and node.get("canonical_for"):
                        return node["canonical_for"][0]
    return "unknown"


VDR_RX = re.compile(r"VDR__(?P<path>.+)$", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    work = Path(a.work)

    ev = json.loads((work / "evidence.json").read_text())
    checks = json.loads((work / "auto_checks.json").read_text())
    reg = yaml.safe_load((SKILL / "config" / "module_registry.yaml").read_text())
    vdr = yaml.safe_load((SKILL / "config" / "vdr_taxonomy.yaml").read_text())
    modules_reg = reg["modules"]

    by_mod = checks["coverage"]["by_module"]
    verdicts = checks.get("verdicts", {})
    stance = {}
    for s, codes in (checks.get("verdict_divergence", {}).get("by_stance") or {}).items():
        for c in codes:
            stance[c] = s

    present_codes = {f["module"] for f in ev["facts"]}
    # data-room and analyst-research items count toward their module-of-record, so a module the
    # agents never produced (e.g. CBG/HPF on a thin agent run) is still "present" when the VDR fills it
    direct = defaultdict(int)
    for f in ev["facts"]:
        if f.get("source") in ("vdr_direct", "management_doc", "analyst_research"):
            direct[f["module"]] += 1
    modules = {}
    for code in modules_reg:
        cov = by_mod.get(code)
        modules[code] = {
            "present": code in present_codes,
            "facts": (cov or {}).get("facts", 0),
            "populated_facts": (cov or {}).get("populated", 0) + direct.get(code, 0),
            "direct_facts": direct.get(code, 0),
            "coverage_pct": (cov or {}).get("coverage_pct", 0),
            "confidence": (verdicts.get(code) or {}).get("confidence", "not_stated"),
            "verdict_stance": stance.get(code, "unknown"),
            "criticality": modules_reg[code]["criticality"],
        }

    # substitution: a module that supersedes an absent one stands in for it
    substituted = defaultdict(list)
    for code, m in modules_reg.items():
        for old in m.get("supersedes", []) or []:
            if modules.get(code, {}).get("present") and not modules.get(old, {}).get("present"):
                substituted[old].append(code)

    # ---- source artefacts and doc types, from the citations the agents actually made
    arts, absent, web = {}, 0, 0
    for f in ev["facts"]:
        c = f.get("citations") or {}
        for d in c.get("doc") or []:
            m = VDR_RX.search(d)
            path = m.group("path") if m else None
            fname = (path or d).split("__")[-1]
            key = norm(fname)
            rec = arts.setdefault(key, {"filename": fname, "vdr_path": path, "citations": 0})
            rec["citations"] += 1
            if path and not rec.get("vdr_path"):
                rec["vdr_path"] = path
        web += len(c.get("web") or [])

    doc_types = Counter()
    for rec in arts.values():
        dt = infer_doc_type(rec["filename"], rec.get("vdr_path"), vdr)
        rec["doc_type"] = dt
        doc_types[dt] += 1
        if not rec.get("vdr_path"):
            absent += 1
    if web:
        doc_types["web"] += 1

    survey_n = None
    for f in ev["facts"]:
        m = re.search(r"\bn\s*=\s*(\d{2,5})\b", f.get("text", ""))
        if m and re.search(r"survey|respond|sample", f.get("text", ""), re.I):
            survey_n = max(survey_n or 0, int(m.group(1)))

    missing_core = [c for c, m in modules.items()
                    if m["criticality"] == "core" and not m["present"] and not substituted.get(c)]

    out = {
        "modules": modules,
        "doc_types": sorted(k for k in doc_types if k != "unknown"),
        "doc_type_counts": dict(doc_types),
        "survey_n": survey_n,
        "missing_core": missing_core,
        "substituted": dict(substituted),
        "source_artifacts": {"resolved": len(arts) - absent, "unresolved_path": absent,
                             "web_citations": web, "distinct": len(arts)},
        "artifacts": sorted(arts.values(), key=lambda r: -r["citations"]),
    }
    (work / "coverage.json").write_text(json.dumps(out, indent=1))

    lines = ["# Coverage", "",
             f"Modules present: {sum(1 for m in modules.values() if m['present'])}/{len(modules)}",
             f"Distinct source artefacts cited: {out['source_artifacts']['distinct']} "
             f"({out['source_artifacts']['unresolved_path']} without a resolvable data-room path)",
             f"Web citations: {web}",
             f"Document types evidenced: {', '.join(out['doc_types']) or 'none'}",
             f"Primary research (survey / interviews): "
             f"{'yes' if set(out['doc_types']) & {'survey', 'interviews'} else 'NO'}",
             f"Survey n: {survey_n if survey_n else 'not stated'}", ""]
    if missing_core:
        lines += [f"**Missing core modules:** {', '.join(missing_core)}", ""]
    if substituted:
        lines += ["**Substituted:** " + "; ".join(f"{k} -> {', '.join(v)}" for k, v in substituted.items()), ""]
    lines += ["| Module | Present | Facts | Populated | Cov % | Confidence | Stance |",
              "|---|---|---|---|---|---|---|"]
    for c in sorted(modules):
        m = modules[c]
        lines.append(f"| {c} | {'y' if m['present'] else '-'} | {m['facts']} | {m['populated_facts']} | "
                     f"{m['coverage_pct']} | {m['confidence']} | {m['verdict_stance']} |")
    (work / "coverage.md").write_text("\n".join(lines) + "\n")

    print(f"[coverage] modules {sum(1 for m in modules.values() if m['present'])}/{len(modules)}; "
          f"doc types {out['doc_types']}; primary research "
          f"{'yes' if set(out['doc_types']) & {'survey','interviews'} else 'NO'}; "
          f"missing core {missing_core or 'none'}")


if __name__ == "__main__":
    main()
