#!/usr/bin/env python3
"""Step 3 (cont.): flatten module IRs into an addressable evidence base and run automatic checks.

Usage:  python evidence_index.py --work <workdir>

Writes:
  <work>/evidence.json          every atomic piece of evidence with a stable id, class, basis and flags
  <work>/evidence_digest.md     compact human/LLM-readable view grouped by module & section (for drafting)
  <work>/auto_checks.json       cross-module findings: conflicts, divergence, coverage, citation index
Evidence ids:  <MOD>-<sec>-<kind><n>[-R<row>]   e.g. MVG-1-T1-R4 (module MVG, section 1, table 1, row 4)
               kinds: S snapshot, R read, F field, N note, T table, Y synthesis, V verdict
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import (registry, read_json, write_json, citations, basis_of, doc_type,  # noqa: E402
                        is_na, is_placeholder, parse_numbers, similarity, doc_key)

FIN_KEYWORDS = re.compile(
    r"ebitda|revenue|margin|wacc|beta|\bev\b|ev/|debt|capex|cash|valuation|multiple|market size|"
    r"income|profit|loss|diversity|headcount|market share|terminal|cost of|price|₹|\$", re.I)
SOURCE_COL = re.compile(r"^(source|sources|source / confidence|data source|evidence|evidence source|reference)", re.I)
CURRENCY_HDR = re.compile(r"₹|®|\bcr\b|INR|Rs|crore", re.I)
INTERP_LABELS = re.compile(r"^(verdict|recommendation|confidence|key condition|primary .*risk|.*rating|.*score|summary of)", re.I)
STANCE = [
    ("negative", re.compile(r"\b(reject|do not invest|walk away|no-go)\b", re.I)),
    ("insufficient", re.compile(r"\b(conduct further|seek additional|inconclusive|challenging to provide|gather more|due to the lack of data)\b", re.I)),
    ("cautious", re.compile(r"\b(caution|cautious)\b", re.I)),
    ("positive", re.compile(r"\b(invest|proceed|go\b|accretive|maintain)\b", re.I)),
]
KPI_PATTERNS = {
    "nps": re.compile(r"\bNPS\b|net promoter", re.I),
    "csat": re.compile(r"\bCSAT\b", re.I),
    "retention_rate": re.compile(r"retention rate|employee retention|\bGRR\b|\bNRR\b", re.I),
    "churn": re.compile(r"churn", re.I),
    "cac": re.compile(r"acquisition cost|\bCAC\b", re.I),
    "market_share": re.compile(r"market share", re.I),
    "revenue": re.compile(r"revenue from operations|^revenue\b|total income", re.I),
    "gross_profit": re.compile(r"gross profit", re.I),
    "loss_before_tax": re.compile(r"(loss|profit) before tax", re.I),
    "wacc": re.compile(r"\bWACC\b", re.I),
}
MS_RE = re.compile(
    r"(?P<cur>USD|\$|₹|INR)?\s?(?P<num>\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s?(?P<unit>bn|billion|B\b|cr\b|crore|mn|million)",
    re.I)
YEAR_RE = re.compile(r"\b(20[1-4]\d)\b")
CAGR_RE = re.compile(r"CAGR[^.%]{0,60}?(\d{1,2}(?:\.\d+)?)\s?%|(\d{1,2}(?:\.\d+)?)\s?%[^.]{0,40}CAGR", re.I)


def stance_of(text):
    for name, rx in STANCE:
        if rx.search(text or ""):
            return name
    return "unclear"


def mk(fid, mod, sec, kind, text, page=None, **kw):
    cit = citations(text)
    f = {"id": fid, "module": mod["module_id"], "module_title": mod["title"],
         "section_n": sec["n"], "section_key": sec["key"], "section_title": sec["matched_title"],
         "kind": kind, "text": text, "citations": cit, "basis": basis_of(cit),
         "numbers": [n["raw"] for n in parse_numbers(re.sub(r"\(DOC:[^)]*\)|\[\d+\]", "", text))],
         "page": page, "flags": []}
    f.update(kw)
    interp = kind in ("snapshot", "read", "synthesis", "verdict") or sec["key"] == "verdict" or \
        (kind == "field" and INTERP_LABELS.match(kw.get("label", "")))
    f["class"] = "interpretation" if interp else "fact"
    if is_placeholder(text):
        f["flags"].append("PLACEHOLDER")
    return f


def build(work: Path):
    reg = registry()
    mods = {p.stem: read_json(p) for p in sorted((work / "modules").glob("*.json"))}
    facts = []
    for mid, mod in mods.items():
        secs = ([mod["overview"]] if any(mod["overview"][k] for k in ("snapshot", "fields", "tables", "notes", "read")) else []) + mod["sections"]
        for sec in secs:
            base = f"{mid}-{sec['n']}"
            if sec.get("snapshot"):
                facts.append(mk(f"{base}-S", mod, sec, "snapshot", sec["snapshot"]))
            for i, fd in enumerate(sec["fields"], 1):
                txt = f"{fd['label']}: {fd['value']}"
                f = mk(f"{base}-F{i}", mod, sec, "field", txt, fd.get("page"), label=fd["label"], value=fd["value"])
                if is_na(fd["value"]):
                    f["flags"].append("NA")
                f["flags"] += [x for x in fd.get("flags", []) if x not in f["flags"]]
                facts.append(f)
            for i, nt in enumerate(sec["notes"], 1):
                f = mk(f"{base}-N{i}", mod, sec, "note", nt["text"], nt.get("page"))
                if is_na(nt["text"]):
                    f["flags"].append("NA")
                facts.append(f)
            for ti, tb in enumerate(sec["tables"], 1):
                hdr = tb["header"] or [f"col{j+1}" for j in range(max((len(r) for r in tb["rows"]), default=0))]
                src_cols = {j for j, h in enumerate(hdr) if SOURCE_COL.match(h or "")}
                cur_cols = {j for j, h in enumerate(hdr) if CURRENCY_HDR.search(h or "")}
                for ri, row in enumerate(tb["rows"], 1):
                    cells = {(hdr[j] if j < len(hdr) and hdr[j] else f"col{j+1}"): c for j, c in enumerate(row)}
                    text = " | ".join(f"{k}: {v}" for k, v in cells.items() if v)
                    bx = tb.get("cell_bboxes", [])
                    f = mk(f"{base}-T{ti}-R{ri}", mod, sec, "table_row", text, tb.get("page"),
                           table_header=hdr, cells=cells, row_label=row[0] if row else "",
                           bbox=_row_bbox(bx[ri - 1]) if ri - 1 < len(bx) and bx[ri - 1] and bx[ri - 1][0] else None)
                    data_cells = [c for j, c in enumerate(row) if j not in src_cols and j > 0]
                    if data_cells and all(is_na(c) for c in data_cells):
                        f["flags"].append("NA")
                    elif any(is_na(c) for c in data_cells):
                        f["flags"].append("PARTIAL_NA")
                    for j in cur_cols:
                        if j < len(row) and re.match(r"^[~72]\d", row[j] or ""):
                            f["flags"].append("OCR_CURRENCY_AMBIGUOUS")
                    f["flags"] += [x for x in tb.get("flags", []) if x not in f["flags"]]
                    if tb.get("conf") and tb["conf"] < 80:
                        f["flags"].append("LOW_OCR_CONF")
                    facts.append(f)
            if sec.get("read"):
                facts.append(mk(f"{base}-R", mod, sec, "read", sec["read"]))
        for i, y in enumerate(mod["synthesis"], 1):
            facts.append(mk(f"{mid}-Y{i}", mod, {"n": 99, "key": "synthesis", "matched_title": "Analytical Synthesis"}, "synthesis", y["text"], y.get("page")))
        if mod["verdict"]:
            v = mod["verdict"]
            txt = f"Recommendation: {v.get('recommendation','')} | Confidence: {v.get('confidence','')} | Key conditions: {v.get('key_conditions','')}"
            facts.append(mk(f"{mid}-V", mod, {"n": 100, "key": "module_verdict", "matched_title": "Verdict"}, "verdict", txt, v.get("page"),
                            recommendation=v.get("recommendation"), confidence=v.get("confidence"), key_conditions=v.get("key_conditions")))

    # --- analyst verification overrides (work/verified.json), recorded after visual checks with
    #     crop_evidence.py: {"ID": {"status": "confirmed"|"corrected", "text": "<corrected row text>",
    #     "cells": {...}, "note": "..."}}. Originals are kept in `ocr_text`.
    vpath = work / "verified.json"
    if vpath.exists():
        ver = read_json(vpath)
        for f in facts:
            v = ver.get(f["id"])
            if not v:
                continue
            f["verification"] = v
            if v.get("status") == "corrected":
                f["ocr_text"] = f["text"]
                if v.get("cells"):
                    f["cells"].update(v["cells"])
                    f["text"] = " | ".join(f"{k}: {x}" for k, x in f["cells"].items() if x)
                if v.get("text"):
                    f["text"] = v["text"]
                f["numbers"] = [n["raw"] for n in parse_numbers(re.sub(r"\(DOC:[^)]*\)|\[\d+\]", "", f["text"]))]
                f["flags"] = [x for x in f["flags"] if not x.startswith("OCR_") and x != "LOW_OCR_CONF"] + ["VERIFIED_CORRECTED"]
            else:
                f["flags"] = [x for x in f["flags"] if not x.startswith("OCR_") and x != "LOW_OCR_CONF"] + ["VERIFIED"]

    # --- evidence suitability (rule R4): financial / market numbers backed only by survey or interview docs
    for f in facts:
        if f["class"] != "fact" or not f["numbers"] or "NA" in f["flags"]:
            continue
        cit = f["citations"]
        if cit["doc"] and not cit["computed"] and not cit["web"]:
            types = {doc_type(d, reg) for d in cit["doc"]}
            if types <= {"survey", "interviews"} and FIN_KEYWORDS.search(f["text"]):
                f["flags"].append("SOURCE_SUITABILITY")
        if f["basis"] == "uncited":
            f["flags"].append("UNCITED_NUMBER")
    return mods, facts


def _row_bbox(cells):
    xs = [c[0] for c in cells if c]; ys = [c[1] for c in cells if c]
    x1 = [c[0] + c[2] for c in cells if c]; y1 = [c[1] + c[3] for c in cells if c]
    return [min(xs), min(ys), max(x1) - min(xs), max(y1) - min(ys)] if xs else None


def cross_checks(mods, facts, reg):
    out = {}
    # coverage (C2): share of fact-class items that are not NA / placeholder
    cov = {}
    for mid in mods:
        fs = [f for f in facts if f["module"] == mid and f["class"] == "fact"]
        ok = [f for f in fs if "NA" not in f["flags"] and "PLACEHOLDER" not in f["flags"]]
        cov[mid] = {"facts": len(fs), "populated": len(ok), "coverage_pct": round(100 * len(ok) / len(fs)) if fs else 0}
    tot = sum(c["facts"] for c in cov.values()); pop = sum(c["populated"] for c in cov.values())
    out["coverage"] = {"by_module": cov, "overall_pct": round(100 * pop / tot) if tot else 0,
                       "formula": "populated fact items / all fact items (table rows, fields, notes); NA and placeholder items excluded"}
    # verdicts & divergence (C3)
    verdicts = {}
    for mid, mod in mods.items():
        v = mod.get("verdict") or {}
        verdicts[mid] = {"title": mod["title"], "recommendation": v.get("recommendation", ""),
                         "confidence": (v.get("confidence") or "").split(",")[0].strip(), "stance": stance_of(v.get("recommendation", "")),
                         "evidence_id": f"{mid}-V" if v else None}
    stances = defaultdict(list)
    for mid, v in verdicts.items():
        stances[v["stance"]].append(mid)
    out["verdicts"] = verdicts
    out["verdict_divergence"] = {"by_stance": dict(stances),
                                 "divergent": bool(stances.get("negative")) and bool(stances.get("positive")),
                                 "low_confidence_modules": [m for m, v in verdicts.items() if v["confidence"].lower().startswith("low")]}
    # market size mentions by year (C8 / E3)
    ms = []
    for f in facts:
        if not re.search(r"market", f["text"], re.I):
            continue
        for sent in re.split(r"(?<=[.;])\s+", f["text"]):
            if not re.search(r"market|TAM|SAM|SOM", sent, re.I):
                continue
            yrs = YEAR_RE.findall(sent)
            for m in MS_RE.finditer(sent):
                ms.append({"value": m.group("num"), "unit": m.group("unit"), "currency": m.group("cur") or "",
                           "years": yrs, "evidence_id": f["id"], "class": f["class"], "snippet": sent[:220]})
    by_year = defaultdict(set)
    for m in ms:
        for y in m["years"] or ["(no year)"]:
            by_year[y].add(f"{m['currency']}{m['value']} {m['unit']}".strip())
    out["market_size_mentions"] = {"mentions": ms, "distinct_values_by_year": {y: sorted(v) for y, v in by_year.items()},
                                   "conflict_years": [y for y, v in by_year.items() if len(v) > 1 and y != "(no year)"]}
    cagr = defaultdict(set)
    for f in facts:
        for m in CAGR_RE.finditer(f["text"]):
            cagr[(m.group(1) or m.group(2))].add(f["id"])
    out["cagr_mentions"] = {k: sorted(v) for k, v in cagr.items()}
    # KPI values across modules (E3)
    kpis = defaultdict(list)
    for f in facts:
        if f["kind"] not in ("table_row", "field"):
            continue
        label = f.get("row_label") or f.get("label") or ""
        for k, rx in KPI_PATTERNS.items():
            if rx.search(label):
                kpis[k].append({"evidence_id": f["id"], "module": f["module"], "text": f["text"][:200],
                                "na": "NA" in f["flags"]})
    out["kpi_observations"] = {k: v for k, v in kpis.items()}
    out["kpi_conflicts"] = [k for k, v in kpis.items() if any(x["na"] for x in v) and any(not x["na"] for x in v)
                            and len({x["module"] for x in v}) > 1]
    # entity naming variants
    tn = None
    for f in facts:
        if f["kind"] == "table_row" and re.match(r"target (name|company)", f.get("row_label", ""), re.I):
            vals = [v for k, v in f["cells"].items() if v and not re.match(r"target", v, re.I)]
            if vals:
                tn = vals[0].split("(")[0].strip()
                break
        if f["kind"] == "field" and re.match(r"target (name|company)", f.get("label", ""), re.I):
            tn = f["value"].split("(")[0].strip()
            break
    variants = defaultdict(int)
    if tn:
        tok = re.escape(tn.split()[0])
        for f in facts:
            for m in re.finditer(rf"\b{tok}(?:\s+[A-Z][\w]+)?", f["text"]):
                variants[m.group(0)] += 1
    out["entity"] = {"target_name": tn, "name_variants": dict(sorted(variants.items(), key=lambda kv: -kv[1]))}
    # citation index
    docs = defaultdict(lambda: {"modules": set(), "count": 0, "type": None})
    webs = defaultdict(lambda: {"modules": set(), "count": 0})
    for f in facts:
        for d in f["citations"]["doc"]:
            docs[d]["modules"].add(f["module"]); docs[d]["count"] += 1; docs[d]["type"] = doc_type(d, reg)
        for w in f["citations"]["web"]:
            webs[w]["modules"].add(f["module"]); webs[w]["count"] += 1
    # resolve web refs: module-local Sources list first, else project-level list from SCM methodology
    scm_map = {}
    for f in facts:
        if f["module"] == "SCM":
            for m in re.finditer(r"([\w.-]+\.(?:com|org|net|io|in))\s*\[(\d{1,2})\]", f["text"]):
                scm_map[int(m.group(2))] = m.group(1)
    local = {mid: {s["n"]: s["text"] for s in mod.get("sources", [])} for mid, mod in mods.items()}
    inline = defaultdict(dict)   # e.g. "[4] Ride-hailing, Worldwide | Statista Market Forecast" inside prose
    for f in facts:
        for m in re.finditer(r"\[(\d{1,2})\]\s+([A-Z][^\[\]()]{12,90}?(?:Forecast|Outlook|Report|Research|\d{4}))", f["text"]):
            inline[f["module"]].setdefault(int(m.group(1)), m.group(2).strip())
    web_index = {}
    for w, d in sorted(webs.items()):
        res = sorted({local[m][w] for m in d["modules"] if w in local.get(m, {})} |
                     {f"{inline[m][w]} (inline in {m})" for m in d["modules"] if w in inline.get(m, {})})
        scm_res = [scm_map[w] + " (via SCM data-source list)"] if w in scm_map else []
        web_index[str(w)] = {"modules": sorted(d["modules"]), "count": d["count"],
                             "resolved_as": res + scm_res,
                             "numbering_inconsistent": bool(res and scm_res),
                             "unresolved": not res and not scm_res}
    # group OCR spelling variants (same alphanumeric key) and truncated names (prefix of a full name);
    # display the most frequent spelling
    groups = {}
    for d, v in docs.items():
        groups.setdefault(doc_key(d), []).append((d, v))
    keys = sorted(groups, key=len, reverse=True)
    parent = {}
    for k in keys:
        full = [K for K in keys if len(K) > len(k) and K.startswith(k) and len(k) >= 12]
        parent[k] = full[0] if full else k
    merged = {}
    for k, members in groups.items():
        root = parent[k]
        while parent.get(root, root) != root:
            root = parent[root]
        mv = merged.setdefault(root, {"names": defaultdict(int), "modules": set(), "count": 0})
        for d, v in members:
            mv["names"][d] += v["count"]; mv["modules"] |= v["modules"]; mv["count"] += v["count"]
    merged = {max(v["names"], key=v["names"].get): v for v in merged.values()}
    out["citation_index"] = {
        "documents": {d: {"type": doc_type(d, reg), "count": v["count"], "modules": sorted(v["modules"]),
                          "spellings": sorted(v["names"])} for d, v in sorted(merged.items())},
        "web": web_index,
    }
    # synthetic markers
    markers = reg.get("synthetic_markers", [])
    syn = [f["id"] for f in facts if any(mk_.lower() in f["text"].lower() for mk_ in markers)]
    out["synthetic"] = {"detected": bool(syn), "evidence_ids": syn[:50], "count": len(syn)}
    # flag counts
    fc = defaultdict(int)
    for f in facts:
        for fl in f["flags"]:
            fc[fl] += 1
    out["flag_counts"] = dict(fc)
    return out


def digest(mods, facts):
    lines = ["# Evidence digest", "Legend: [F]=fact (source-reported)  [I]=interpretation (agent view)  flags in {}", ""]
    by_mod = defaultdict(list)
    for f in facts:
        by_mod[f["module"]].append(f)
    for mid, fs in by_mod.items():
        lines.append(f"## {mid} — {mods[mid]['title']}")
        cur = None
        for f in fs:
            if f["section_title"] != cur:
                cur = f["section_title"]
                lines.append(f"### {f['section_n']}. {cur}")
            tag = "F" if f["class"] == "fact" else "I"
            fl = ("{" + ",".join(f["flags"]) + "}") if f["flags"] else ""
            txt = f["text"] if len(f["text"]) < 600 else f["text"][:600] + " …"
            lines.append(f"- `{f['id']}` [{tag}] {txt} {fl}")
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    a = ap.parse_args()
    work = Path(a.work)
    reg = registry()
    mods, facts = build(work)
    checks = cross_checks(mods, facts, reg)
    write_json(work / "evidence.json", {"facts": facts})
    write_json(work / "auto_checks.json", checks)
    (work / "evidence_digest.md").write_text(digest(mods, facts), encoding="utf-8")
    print(f"[evidence] {len(facts)} evidence items; coverage {checks['coverage']['overall_pct']}%; "
          f"flags {checks['flag_counts']}; market-size conflict years {checks['market_size_mentions']['conflict_years']}; "
          f"KPI conflicts {checks['kpi_conflicts']}; verdict divergence {checks['verdict_divergence']['divergent']}")


if __name__ == "__main__":
    main()
