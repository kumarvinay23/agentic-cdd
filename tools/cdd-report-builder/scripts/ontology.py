#!/usr/bin/env python3
"""The CDD ontology, loaded as one graph, with the queries the rest of the skill asks of it.

    from ontology import Ontology
    O = Ontology.load()                      # reads ontology/ + config/
    O.resolve("rebuild the TAM walkdown")    # -> {intent, targets, scope, operation}
    O.lineage("mkt.sam", evidence=EV)        # -> metric -> evidence -> artefact -> vdr node
    O.gate_status(coverage)                  # -> which of the 101 slides render, and why not
    O.crosswalk()                            # -> VdrNode <-> AgentModule <-> SlideSpec edges

Command line:
    python ontology.py validate                     axiom sweep over the static registries
    python ontology.py resolve "<prompt>"           show how a prompt is routed
    python ontology.py crosswalk [--out FILE.yaml]  regenerate config/crosswalk.yaml
    python ontology.py gates --work <dir>           gate decisions for a prepared run
    python ontology.py lineage <metric|evidence id> --work <dir>

Nothing here reads a deck or drafts content; this module only answers questions about
structure. Content rules live in references/03_transformation_rules.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SKILL = Path(__file__).resolve().parent.parent


def _load(p: Path):
    return yaml.safe_load(p.read_text())


# --------------------------------------------------------------------------- graph
@dataclass
class Ontology:
    tbox: dict
    modules: dict
    metrics: dict
    slides: list
    slides_by_id: dict = field(default_factory=dict)
    sections: list = field(default_factory=list)
    gates: dict = field(default_factory=dict)
    vdr: dict = field(default_factory=dict)
    lexicon: dict = field(default_factory=dict)

    # ---------------------------------------------------------------- loading
    @classmethod
    def load(cls, skill: Path = SKILL) -> "Ontology":
        tbox = _load(skill / "ontology" / "cdd_ontology.yaml")
        reg = _load(skill / "config" / "module_registry.yaml")
        met = _load(skill / "config" / "metric_registry.yaml")
        sm = _load(skill / "config" / "slide_map.yaml")
        vdr = _load(skill / "config" / "vdr_taxonomy.yaml")
        lex_path = skill / "config" / "lexicon.yaml"
        lex = _load(lex_path) if lex_path.exists() else {}
        o = cls(tbox=tbox, modules=reg["modules"], metrics=met["metrics"],
                slides=sm["slides"], sections=sm["sections"], gates=sm["gates"],
                vdr=vdr, lexicon=lex)
        o.slides_by_id = {s["id"]: s for s in o.slides}
        o._reg, o._met, o._sm = reg, met, sm
        return o

    # ---------------------------------------------------------------- axioms
    def validate(self) -> list[str]:
        """Static axiom sweep. Returns a list of violations (empty = sound)."""
        errs = []
        # A2: exactly one module-of-record per metric
        owner: dict[str, list[str]] = {}
        for code, m in self.modules.items():
            for mid in m.get("record_for_metrics", []):
                owner.setdefault(mid, []).append(code)
                if mid not in self.metrics:
                    errs.append(f"A2: module {code} claims unknown metric {mid}")
        for mid in self.metrics:
            n = len(owner.get(mid, []))
            if n == 0:
                errs.append(f"A2: metric {mid} has no module-of-record")
            elif n > 1:
                errs.append(f"A2: metric {mid} has {n} owners: {owner[mid]}")
        for mid, m in self.metrics.items():
            if owner.get(mid) and m["record_module"] not in owner[mid]:
                errs.append(f"A2: {mid} declares record_module={m['record_module']} "
                            f"but registry gives {owner[mid]}")
        # referential integrity of the slide map
        sec_ids = {s["id"] for s in self.sections}
        seen_no, seen_id = set(), set()
        for s in self.slides:
            if s["id"] in seen_id:
                errs.append(f"duplicate slide id {s['id']}")
            seen_id.add(s["id"])
            if s["no"] in seen_no:
                errs.append(f"duplicate slide number {s['no']}")
            seen_no.add(s["no"])
            if s["section"] not in sec_ids:
                errs.append(f"{s['id']}: unknown section {s['section']}")
            if s["gate"] not in self.gates:
                errs.append(f"{s['id']}: unknown gate {s['gate']}")
            for code in s["primary_modules"] + s["secondary_modules"] + s.get("fallback_modules", []):
                if code not in self.modules:
                    errs.append(f"{s['id']}: unknown module {code}")
            for mid in s["metrics"]:
                if mid not in self.metrics:
                    errs.append(f"{s['id']}: unknown metric {mid}")
            # A4: a slide may only state metrics its modules can own or evidence
            contributors = set(s["primary_modules"] + s["secondary_modules"] + s.get("fallback_modules", []))
            for mid in s["metrics"]:
                rec = self.metrics[mid]["record_module"]
                fb = self.metrics[mid].get("fallback_record_module")
                if rec not in contributors and (not fb or fb not in contributors):
                    errs.append(f"{s['id']}: states {mid} but neither its module-of-record "
                                f"({rec}) nor its fallback contributes")
            if s["gate"] == "core" and not s["primary_modules"] and s["archetype"] not in (
                    "cover", "back_cover", "divider", "contents"):
                errs.append(f"{s['id']}: core gate with no primary modules")
        # every module must land somewhere
        placed = set()
        for s in self.slides:
            placed |= set(s["primary_modules"] + s["secondary_modules"] + s.get("fallback_modules", []))
        for code, m in self.modules.items():
            if code not in placed and not m.get("supersedes_only"):
                errs.append(f"module {code} ({m['title']}) feeds no slide")
        # A4 hard exclusions coherent
        for row in self._met.get("hard_exclusions", []):
            scope = row.get("metrics")
            for mid, m in self.metrics.items():
                in_scope = mid in scope if scope else m["class"] == row.get("metric_class")
                if in_scope and row["doc_type"] in m["admissible_doc_types"]:
                    errs.append(f"A4: {mid} admits {row['doc_type']} but it is hard-excluded "
                                f"({scope and 'by metric' or 'for class ' + str(row.get('metric_class'))})")
        return errs

    # ---------------------------------------------------------------- crosswalk
    def crosswalk(self) -> dict:
        """VdrNode -> AgentModule -> SlideSpec, derived rather than hand-maintained."""
        # doc_type -> vdr topic nodes
        dt_nodes: dict[str, list[str]] = {}
        for sc, sec in self.vdr["sections"].items():
            for sub, subsec in sec.get("subsections", {}).items():
                for tc, top in subsec.get("topics", {}).items():
                    for dt in top.get("canonical_for", []) or subsec.get("canonical_for", []):
                        dt_nodes.setdefault(dt, []).append(f"{tc} {top['title']}")
        mod_slides: dict[str, dict] = {}
        for s in self.slides:
            for role, key in (("primary", "primary_modules"),
                              ("secondary", "secondary_modules"),
                              ("fallback", "fallback_modules")):
                for code in s.get(key, []):
                    mod_slides.setdefault(code, {"primary": [], "secondary": [], "fallback": []})
                    mod_slides[code][role].append(s["id"])
        rows = []
        for code, m in sorted(self.modules.items()):
            nodes = sorted({n for dt in m.get("expects", []) for n in dt_nodes.get(dt, [])})
            rows.append({
                "module": code,
                "title": m["title"],
                "criticality": m["criticality"],
                "expects_doc_types": m.get("expects", []),
                "vdr_nodes": nodes,
                "owns_metrics": m.get("record_for_metrics", []),
                "slides": mod_slides.get(code, {"primary": [], "secondary": [], "fallback": []}),
            })
        return {"version": 2,
                "generated_by": "scripts/ontology.py crosswalk",
                "doc": "Derived edges VdrNode <-> AgentModule <-> SlideSpec. Regenerate after "
                       "editing module_registry.yaml, slide_map.yaml or vdr_taxonomy.yaml.",
                "modules": rows}

    # ---------------------------------------------------------------- gates
    def gate_status(self, coverage: dict) -> list[dict]:
        """Decide, for each slide, whether it renders.

        coverage = {
          "modules": {CODE: {"present": bool, "populated_facts": int, "confidence": str}},
          "doc_types": [DocType ids present in the corpus],
          "survey_n": int | None,
        }
        """
        mods = coverage.get("modules", {})
        dts = set(coverage.get("doc_types", []))
        survey_n = coverage.get("survey_n")
        has_primary_research = bool(dts & {"survey", "interviews"})
        out = []
        for s in self.slides:
            g = s["gate"]
            cfg = self.gates[g]
            facts = lambda codes: sum(mods.get(c, {}).get("populated_facts", 0) for c in codes)
            present = lambda codes: [c for c in codes if mods.get(c, {}).get("present")]
            rec = {"id": s["id"], "no": s["no"], "gate": g, "render": True,
                   "reason": "", "exception": None, "substituted_with": []}
            if g in ("always", "derived"):
                pass
            elif g == "core":
                p = present(s["primary_modules"])
                if p and facts(p) >= cfg.get("min_facts", 1):
                    pass
                else:
                    fb = present(s.get("fallback_modules", []))
                    if fb and facts(fb) >= cfg.get("fallback_min_facts", 3):
                        rec["substituted_with"] = fb
                        rec["exception"] = cfg.get("fallback_exception", "E12-SUBSTITUTION")
                        rec["reason"] = (f"module-of-record {s['primary_modules']} absent; "
                                         f"built from {fb}")
                    else:
                        rec["render"] = False
                        rec["exception"] = "E9-BLOCKER"
                        rec["reason"] = (f"core slide: primary modules {s['primary_modules']} "
                                         f"absent and no usable fallback")
            elif g == "conditional":
                p = present(s["primary_modules"])
                if not p or facts(p) < cfg.get("min_facts", 3):
                    rec["render"] = False
                    rec["exception"] = cfg.get("exception", "E1-NOT-PROVIDED")
                    rec["reason"] = (f"insufficient evidence: {facts(p)} populated facts from "
                                     f"{p or s['primary_modules']}, need {cfg.get('min_facts', 3)}")
            elif g == "research_gated":
                if not has_primary_research:
                    rec["render"] = False
                    rec["exception"] = cfg.get("exception", "E11-NO-PRIMARY")
                    rec["reason"] = "no survey or interview source in the corpus"
                elif survey_n is not None and survey_n < cfg.get("min_n", 30):
                    rec["reason"] = f"survey n={survey_n} below {cfg.get('min_n', 30)}: report, do not chart"
                else:
                    p = present(s["primary_modules"])
                    if not p or facts(p) < cfg.get("min_facts", 3):
                        rec["render"] = False
                        rec["exception"] = "E1-NOT-PROVIDED"
                        rec["reason"] = f"primary research present but {s['primary_modules']} contribute too little"
            out.append(rec)
        # a divider whose whole section was withheld goes with it, otherwise the deck carries a
        # section heading followed by nothing
        by_id = {r["id"]: r for r in out}
        alive = {sd["section"] for sd in self.slides
                 if sd["archetype"] != "divider" and by_id[sd["id"]]["render"]}
        for sd in self.slides:
            if sd["archetype"] == "divider" and sd["section"] not in alive:
                r = by_id[sd["id"]]
                r["render"] = False
                r["exception"] = "E1-NOT-PROVIDED"
                r["reason"] = "every page in this section was withheld"
        return out

    # ---------------------------------------------------------------- lineage
    def lineage(self, ident: str, evidence: dict | None = None) -> dict:
        """Walk the provenance chain from a metric or an evidence id back to the data room."""
        res = {"query": ident, "kind": None, "chain": []}
        if ident in self.metrics:
            m = self.metrics[ident]
            res["kind"] = "metric"
            res["metric"] = {"id": ident, "label": m["label"], "class": m["class"],
                             "subject": m["subject"], "record_module": m["record_module"],
                             "admissible_doc_types": m["admissible_doc_types"]}
            res["stated_on"] = [s["id"] for s in self.slides if ident in s["metrics"]]
            if evidence:
                items = [e for e in evidence.get("items", []) if ident in (e.get("measures") or [])]
                res["chain"] = [{"evidence": e["evidence_id"], "module": e["module"],
                                 "kind": e.get("kind"), "basis": e.get("basis"),
                                 "cites": e.get("citations", []), "flags": e.get("flags", [])}
                                for e in items]
                if not items:
                    res["gap"] = (f"No evidence item measures {ident}. "
                                  f"Module-of-record {m['record_module']} "
                                  f"{'is present but silent' if m['record_module'] in (evidence.get('modules') or {}) else 'is absent'}.")
        elif evidence:
            item = next((e for e in evidence.get("items", []) if e["evidence_id"] == ident), None)
            if item:
                res["kind"] = "evidence"
                res["item"] = item
                res["chain"] = [{"artifact": c} for c in item.get("citations", [])]
        if res["kind"] is None:
            res["kind"] = "unresolved"
        return res

    # ---------------------------------------------------------------- prompt routing
    INTENT_CUES = [
        ("build_deck",      r"\b(build|produce|generate|create|make|assemble)\b.*\b(deck|report|pack|powerpoint|pptx|cdd)\b"),
        ("refresh_deck",    r"\b(refresh|re-?run|rerun|update|regenerate)\b.*\b(deck|report|pack)\b"),
        ("rebuild_slide",   r"\b(redo|rebuild|re-?draft|fix|change|rewrite|tighten|redraw)\b.*\b(slides?|pages?|exhibits?|charts?|tables?|walk\w*|map|scorecard|matrix|summary)\b"),
        ("explain_lineage", r"\b(where|which source|what source|trace|provenance|comes? from|backed by|evidence for)\b"),
        ("list_gaps",       r"\b(gap|missing|not provided|unanswered|follow[- ]?up|what do we still need|exception)\b"),
        ("assess_coverage", r"\b(coverage|can we|enough evidence|do we have enough|how complete)\b"),
        ("change_scope",    r"\b(perimeter|currency|horizon|scope|rebase|in\s?scope|out of scope)\b"),
        ("validate",        r"\b(validate|check|qa|quality|sound|sanity)\b"),
        ("review",          r"\b(review|red[- ]?flag|challenge|stress[- ]test|issue register|is (?:this|the) (?:deck|analysis) (?:ic[- ]ready|right|sound))\b"),
        ("explain_rule",    r"\b(why|rule|how is .* decided|methodology|how do you)\b"),
        ("query_evidence",  r"\b(what do we know|show me|list|tell me about|summari[sz]e)\b"),
    ]

    def resolve(self, prompt: str) -> dict:
        """Route a natural-language prompt onto ontology objects. Never guesses a perimeter,
        a currency or a metric owner - those come back as `ask`."""
        p = prompt.strip()
        low = p.lower()
        targets = {"slides": [], "modules": [], "metrics": [], "sections": [], "rules": []}

        # 1. explicit ids
        for m in re.finditer(r"\bS?(\d{1,3})\b(?=\s*(?:$|[^\w%]))", p):
            n = int(m.group(1))
            if re.search(r"\b(slide|page|s)\s*0*%d\b" % n, low) or re.match(r"^S\d{2,3}", m.group(0)):
                hit = next((s["id"] for s in self.slides if s["no"] == n), None)
                if hit:
                    targets["slides"].append(hit)
        for sid in self.slides_by_id:
            if sid.lower() in low:
                targets["slides"].append(sid)
        for code in self.modules:
            if re.search(rf"\b{code}\b", p):
                targets["modules"].append(code)
        for mid in self.metrics:
            if mid.lower() in low:
                targets["metrics"].append(mid)
        for rid in re.findall(r"\b([TRCE]\d{1,2})(?:-[A-Z-]+)?\b", p):
            targets["rules"].append(rid)

        # 2. lexicon aliases
        lex = self.lexicon or {}
        for kind, key in (("slides", "slide_aliases"), ("modules", "module_aliases"),
                          ("metrics", "metric_aliases"), ("sections", "section_aliases")):
            for alias, ident in (lex.get(key) or {}).items():
                if re.search(rf"\b{re.escape(alias.lower())}\b", low):
                    targets[kind].extend(ident if isinstance(ident, list) else [ident])
        for alias, ids in (lex.get("bundles") or {}).items():
            if re.search(rf"\b{re.escape(alias.lower())}\b", low):
                for i in ids:
                    if i in self.slides_by_id:
                        targets["slides"].append(i)
                    elif i in self.modules:
                        targets["modules"].append(i)
                    elif i in self.metrics:
                        targets["metrics"].append(i)

        # 3. registry titles and aliases
        for code, mod in self.modules.items():
            names = [mod["title"]] + list(mod.get("aliases") or [])
            if any(re.search(rf"\b{re.escape(n.lower())}\b", low) for n in names):
                targets["modules"].append(code)
        for mid, met in self.metrics.items():
            if any(re.search(rf"\b{re.escape(a.lower())}\b", low) for a in (met.get("aliases") or [])):
                targets["metrics"].append(mid)
        for s in self.slides:
            t = s["blueprint_title"].split("—")[-1].strip().lower()
            if len(t) > 8 and t in low:
                targets["slides"].append(s["id"])
        for sec in self.sections:
            if re.search(rf"\b{re.escape(sec['name'].lower())}\b", low) or \
               re.search(rf"\b{re.escape(sec['id'])}\b", low):
                targets["sections"].append(sec["id"])

        # 4. intent
        intent = None
        for name, rx in self.INTENT_CUES:
            if re.search(rx, low):
                intent = name
                break
        # a rebuild verb plus any resolved slide is a rebuild, whatever the noun was
        if re.search(r"\b(redo|rebuild|re-?draft|fix|rewrite|tighten|redraw)\b", low) and \
           (targets["slides"] or targets["metrics"]) and intent in (None, "query_evidence"):
            intent = "rebuild_slide"
        if intent is None:
            intent = "build_deck" if not any(targets.values()) else "query_evidence"

        # expand sections to slides, metrics to their slides
        for sec in targets["sections"]:
            targets["slides"].extend(s["id"] for s in self.slides if s["section"] == sec)
        if intent == "rebuild_slide" and not targets["slides"]:
            for mid in targets["metrics"]:
                targets["slides"].extend(s["id"] for s in self.slides if mid in s["metrics"])
            for code in targets["modules"]:
                targets["slides"].extend(s["id"] for s in self.slides if code in s["primary_modules"])
        for k in targets:
            seen, uniq = set(), []
            for v in targets[k]:
                if v not in seen:
                    seen.add(v)
                    uniq.append(v)
            targets[k] = uniq

        op = (self.tbox["prompt_resolution"]["intents"].get(intent) or {}).get("operation", "")
        out = {"prompt": p, "intent": intent, "targets": targets, "operation": op,
               "scope": "deal" if intent in ("build_deck", "refresh_deck", "assess_coverage") else "targets"}
        # refuse / ask
        ask = []
        if intent == "change_scope" and re.search(r"\bperimeter\b", low):
            ask.append("Which entity is the deal perimeter? Naming it changes every company-level figure.")
        if intent == "rebuild_slide" and not targets["slides"]:
            ask.append("Which slide? Give a number (e.g. 37), an id (S037_tam_walkdown) or the exhibit name.")
        if intent in ("build_deck", "refresh_deck") and not targets["slides"]:
            out["scope"] = "deal"
        if ask:
            out["ask"] = ask
        return out


# --------------------------------------------------------------------------- cli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("validate")
    r = sub.add_parser("resolve"); r.add_argument("prompt")
    c = sub.add_parser("crosswalk"); c.add_argument("--out")
    g = sub.add_parser("gates"); g.add_argument("--work", required=True)
    l = sub.add_parser("lineage"); l.add_argument("ident"); l.add_argument("--work")
    a = ap.parse_args(argv)
    O = Ontology.load()

    if a.cmd == "validate":
        errs = O.validate()
        print(f"modules {len(O.modules)}  metrics {len(O.metrics)}  slides {len(O.slides)}")
        if errs:
            for e in errs:
                print("  VIOLATION:", e)
            return 1
        print("ontology sound: all axioms hold")
        return 0

    if a.cmd == "resolve":
        print(json.dumps(O.resolve(a.prompt), indent=1))
        return 0

    if a.cmd == "crosswalk":
        cw = O.crosswalk()
        text = yaml.safe_dump(cw, sort_keys=False, width=100, allow_unicode=True)
        if a.out:
            Path(a.out).write_text(text)
            print("wrote", a.out)
        else:
            print(text)
        return 0

    if a.cmd == "gates":
        work = Path(a.work)
        cov = json.loads((work / "coverage.json").read_text())
        rows = O.gate_status(cov)
        drop = [r for r in rows if not r["render"]]
        sub_ = [r for r in rows if r["substituted_with"]]
        print(f"render {len(rows) - len(drop)}/{len(rows)}   dropped {len(drop)}   substituted {len(sub_)}")
        for r in drop:
            print(f"  DROP {r['id']:<34} {r['exception']:<18} {r['reason']}")
        for r in sub_:
            print(f"  SUB  {r['id']:<34} {r['exception']:<18} {r['reason']}")
        (work / "gates.json").write_text(json.dumps(rows, indent=1))
        return 0

    if a.cmd == "lineage":
        ev = None
        if a.work and (Path(a.work) / "evidence.json").exists():
            ev = json.loads((Path(a.work) / "evidence.json").read_text())
        print(json.dumps(O.lineage(a.ident, ev), indent=1)[:8000])
        return 0


if __name__ == "__main__":
    sys.exit(main())
