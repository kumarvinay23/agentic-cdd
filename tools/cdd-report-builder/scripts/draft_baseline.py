#!/usr/bin/env python3
"""Baseline drafter: a mechanically evidence-backed content.json, as a floor - not a ceiling.

    python draft_baseline.py --work <work> --project "Project X" --target "X Ltd" \
        --client "Y Capital" --currency USD [--out <work>/content.json]

What it is for
  * a first pass whose every claim already carries refs, so the analyst edits prose rather than
    hunting evidence ids;
  * a regression harness - it exercises every element type, every archetype and the gating path,
    so a change to the template or the renderer fails here rather than in front of a client;
  * the mechanical slides (module verdicts, source register, exceptions) in full, which no human
    should hand-write.

What it is NOT
  * the analysis. Action titles here restate the module's own verdict; they do not synthesise
    across modules, they do not weigh evidence quality and they do not say what the IC should do.
  * Replace them. SKILL.md step 5 is the real drafting step; run this first, then rewrite the
    titles, the takeaways and the ordering.
Every slide it drafts is marked `"baseline": true` so check_content.py can report how much of the
deck is still machine prose.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.common import read_json, slide_map, write_json, load_yaml  # noqa: E402
from lib.values import parse_value, same_axis  # noqa: E402

NA_FLAGS = {"NA", "PLACEHOLDER"}
MAXT, MAXS, MAXB = 165, 150, 170
STRONG = None  # compiled from config/claim_rules.yaml at start-up


def clean(t: str) -> str:
    """Strip citations and whitespace. Never shortens: text that is too long is not used."""
    t = " ".join((t or "").split())
    t = re.sub(r"\s*\(DOC:[^)]*\)", "", t)
    t = re.sub(r"\s*\[\d{1,3}\]\S*", "", t)
    return t.strip(" ;,|")


def first_sentences(t: str, n: int) -> str | None:
    """The longest run of whole sentences that fits in n characters, or None.
    Replaces v2's cut-at-n-characters, which produced 'afte.' and '…' on the page."""
    t = clean(t)
    if len(t) <= n:
        return t
    parts = re.split(r"(?<=[.;!?])\s+", t)
    out = ""
    for p in parts:
        cand = (out + " " + p).strip()
        if len(cand) > n:
            break
        out = cand
    return out if len(out) >= 40 else None


def wcut(t: str, n: int) -> str:
    """Mechanical text only (file names, register rows): cut at a word boundary, no ellipsis."""
    t = clean(t)
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(" ,;:-—(")


def populated(f) -> bool:
    return not (set(f.get("flags") or []) & NA_FLAGS)


def attribute(t: str, f) -> str:
    """Agent views are attributed, never asserted (T8). Strong claims keep the attribution so
    check_content's claim-strength rule sees them as reported, not concluded."""
    if f.get("class") == "interpretation" or f.get("kind") in ("verdict", "read", "snapshot", "synthesis"):
        t = re.sub(r"^\s*(recommendation|verdict|read|insight snapshot)\s*:\s*", "", t, flags=re.I)
        if STRONG and STRONG.search(t):
            return f"The {f.get('module_title', 'agent').split('(')[0].strip()} agent claims: {t}"
    return t


def balanced(items, per_page):
    """Split into the fewest pages of at most per_page, as evenly as possible (no 10/10/1 tails)."""
    if not items:
        return []
    n = -(-len(items) // per_page)
    size = -(-len(items) // n)
    return [items[i:i + size] for i in range(0, len(items), size)]


def shorten(t: str, n: int = 88) -> str:
    """Whole clause or sentence that fits n characters; never a mid-sentence cut."""
    t = clean(t)
    if len(t) <= n:
        return t.rstrip(";,:")
    fs = first_sentences(t, n)
    if fs:
        return fs.rstrip(";,:")
    for sep in (" — ", " - ", "; ", ": ", " (", ", "):
        head = t.split(sep)[0].strip()
        if 25 <= len(head) <= n:
            return head
    return wcut(t, n)


class Drafter:
    def __init__(self, work: Path, meta: dict):
        self.work = work
        self.meta = meta
        self.facts = read_json(work / "evidence.json")["facts"]
        self.checks = read_json(work / "auto_checks.json")
        self.cov = read_json(work / "coverage.json")
        self.gates = {g["id"]: g for g in read_json(work / "gates.json")}
        self.sm = slide_map()
        self.by_id = {f["id"]: f for f in self.facts}
        self.by_mod = defaultdict(list)
        for f in self.facts:
            self.by_mod[f["module"]].append(f)
        self.exceptions = []
        self.used_metrics = {}
        self.used_titles = set()
        self.used_refs = set()      # each evidence row appears on one slide only (no repetition)
        self.used_texts = set()     # ... and each sentence, even when two modules restate it
        self.withhold = []

    # ---------------------------------------------------------------- selection
    def pool(self, sd, kinds=None, only_populated=True,
             roles=("primary_modules", "fallback_modules", "secondary_modules"), fresh=True):
        out = []
        for role in roles:
            for code in sd.get(role) or []:
                for f in self.by_mod.get(code, []):
                    if kinds and f["kind"] not in kinds:
                        continue
                    if only_populated and not populated(f):
                        continue
                    if fresh and f["id"] in self.used_refs:
                        continue
                    out.append(f)
        # data-room evidence first (R1), agent restatements after
        out.sort(key=lambda f: 0 if f.get("basis") == "data_room_computed" else 1)
        return out

    def claim(self, ids):
        self.used_refs.update(i for i in ids if isinstance(i, str))

    def table_groups(self, sd, max_rows, max_cols, max_cell=90):
        groups = defaultdict(list)
        for f in self.pool(sd, kinds={"table_row"}):
            hdr = tuple(f.get("table_header") or [])
            if 2 <= len(hdr) <= max_cols:
                groups[(f["module"], f["section_n"], hdr)].append(f)
        out = []
        for key in sorted(groups, key=lambda k: (0 if groups[k][0].get("basis") == "data_room_computed" else 1,
                                                 -len(groups[k]), k[1])):
            rows, seen = [], set()
            for f in groups[key]:
                cells = f.get("cells") or {}
                sig = " | ".join(str(v) for v in cells.values()).lower()
                if sig in seen:
                    continue
                if any(len(clean(str(v))) > max_cell for v in cells.values()):
                    continue            # a cell that would need cutting: drop the row, never truncate
                seen.add(sig)
                rows.append(f)
            if len(rows) >= 2:
                out.append((list(key[2]), rows[:max_rows]))
        return out

    def best_table(self, sd, max_rows, max_cols, max_cell=90):
        g = self.table_groups(sd, max_rows, max_cols, max_cell)
        return g[0] if g else None

    # ---------------------------------------------------------------- elements
    def el_table(self, sd, el):
        lim = el.get("limits", {})
        got = self.best_table(sd, lim.get("max_rows", 9), lim.get("max_cols", 6), lim.get("max_chars_cell", 90))
        if not got:
            return self.el_insufficient(sd, "no tabular findings in the mapped modules")
        hdr, rows = got
        cols = [clean(h) for h in hdr] + ["Source"]
        body = [[clean(str((f.get("cells") or {}).get(h, ""))) or "Not provided" for h in hdr]
                + [f["module"]] for f in rows]
        refs = [[f["id"]] for f in rows]
        self.claim(f["id"] for f in rows)
        return {"type": "table", "columns": cols, "rows": body, "row_refs": refs}

    def el_bullets(self, sd, el, skip=0):
        lim = el.get("limits", {})
        n = lim.get("max_items", 5)
        cap = lim.get("max_chars_item", MAXB)
        items, seen = [], set()
        for kinds, kind in ((("field",), "fact"), (("snapshot",), "interpretation"),
                            (("read",), "interpretation"), (("note",), "fact"),
                            (("verdict",), "interpretation"), (("synthesis",), "interpretation")):
            for f in self.pool(sd, kinds=set(kinds)):
                if len(items) >= n:
                    break
                body = clean(f.get("value") or f["text"])
                key = re.sub(r"[^a-z0-9]+", " ", body.lower())[:120]
                if len(body) < 25 or body.lower() in seen or key in self.used_texts:
                    continue
                self.used_texts.add(key)
                lead = clean(f.get("label") or f.get("section_title") or f["module_title"])
                if len(lead) > 34:
                    lead = f["module_title"].split("(")[0].strip()
                body = attribute(body, f)
                if STRONG and STRONG.search(body) and " agent claims:" not in body:
                    continue
                fit = first_sentences(body, cap - len(lead) - 8)
                if not fit:
                    continue
                seen.add(body.lower())
                items.append({"text": f"**{lead}** — {fit}", "refs": [f["id"]], "kind": kind})
                self.claim([f["id"]])
        if not items:
            return self.el_insufficient(sd, "the mapped modules returned no populated findings")
        return {"type": "bullets", "items": items}

    def el_chart(self, sd, el):
        """Plot only a column whose every point parses to one unit/scale basis, with ranges and
        missing values excluded rather than coerced, and forecast categories labelled."""
        lim = el.get("limits", {})
        for hdr, rows in self.table_groups(sd, lim.get("max_points", 12), 12, 400):
            # orientation A: one row, year columns (a time series)
            for f in rows:
                cells = f.get("cells") or {}
                ks = [k for k in cells if re.match(r"^(?:fy)?20\d\d", str(k), re.I)]
                pv = [parse_value(cells[k], k) for k in ks]
                pts = [(k, v) for k, v in zip(ks, pv) if v.chartable and v.kind != "number"]
                ok, _ = same_axis([v for _, v in pts])
                if ok and len(pts) >= 3:
                    self.claim([f["id"]])
                    return {"type": "chart", "chart_type": "column",
                            "categories": [k for k, _ in pts],
                            "series": [{"name": clean(f.get("row_label") or ""), "values": [v.value for _, v in pts]}],
                            "refs": [f["id"]], "kind": "fact", "unit_label": pts[0][1].unit_label(),
                            "note": "P = management plan" if any("P" in k for k, _ in pts) else None}
            # orientation B: one column across rows (categories)
            for h in hdr[1:]:
                if re.search(r"source|ref|citation|rank|zip|code|confidence", str(h), re.I):
                    continue
                pv = [(f, parse_value((f.get("cells") or {}).get(h, ""), h)) for f in rows]
                pts = [(f, v) for f, v in pv if v.chartable and v.kind != "number"]
                ok, _ = same_axis([v for _, v in pts])
                if ok and len(pts) >= 2:
                    cats = [clean(str((f.get("cells") or {}).get(hdr[0], f.get("row_label", "")))) for f, _ in pts]
                    if any(len(c) > 28 for c in cats):
                        continue
                    self.claim([f["id"] for f, _ in pts])
                    return {"type": "chart", "chart_type": "bar" if len(pts) > 6 else "column",
                            "categories": cats,
                            "series": [{"name": clean(h), "values": [v.value for _, v in pts]}],
                            "refs": [f["id"] for f, _ in pts], "point_refs": [[f["id"] for f, _ in pts]],
                            "kind": "fact", "unit_label": pts[0][1].unit_label()}
        return self.el_insufficient(sd, "no series on one consistent unit and basis")

    def el_kpis(self, sd, el):
        lim = el.get("limits", {})
        items = []
        for f in self.pool(sd, kinds={"field"}):
            if len(items) >= lim.get("max_items", 5):
                break
            v = parse_value(f.get("value"), f.get("label", ""))
            if not v.chartable or not v.literal:
                continue
            label = clean(f.get("label") or "")
            if not label or len(label) > 40 or any(i["label"] == label for i in items):
                continue
            items.append({"value": clean(str(f.get("value")))[:18], "label": label, "note": f["module"],
                          "refs": [f["id"]], "kind": "fact"})
            self.claim([f["id"]])
        return {"type": "kpis", "items": items} if items else None

    def el_text(self, sd, el, name):
        cap = el.get("limits", {}).get("max_chars", 320)
        for kinds in ({"verdict"}, {"synthesis"}, {"read"}, {"snapshot"}):
            for f in self.pool(sd, kinds=kinds):
                t = first_sentences(attribute(clean(f["text"]), f), cap)
                if t and len(t) > 40:
                    self.claim([f["id"]])
                    return {"type": "text", "text": t, "refs": [f["id"]], "kind": "interpretation"}
        return self.el_insufficient(sd, "no synthesis available from the mapped modules")

    def el_insufficient(self, sd, why):
        na = [f["id"] for f in self.pool(sd, only_populated=False, fresh=False) if not populated(f)][:3]
        return {"type": "insufficient", "text": f"Insufficient evidence — {why}", "refs": na, "kind": "gap"}

    # ---------------------------------------------------------------- titles
    def title_for(self, sd):
        for roles in (("primary_modules",), ("primary_modules", "fallback_modules"),
                      ("primary_modules", "fallback_modules", "secondary_modules")):
            for kinds in ({"snapshot"}, {"read"}, {"verdict"}, {"synthesis"}):
                for f in self.pool(sd, kinds=kinds, roles=roles, fresh=False):
                    t = first_sentences(attribute(clean(f["text"]), f), MAXT)
                    if not t or len(t) < 40:
                        continue
                    if STRONG and STRONG.search(clean(f["text"])):
                        continue
                    key = t[:70].lower()
                    if key in self.used_titles:
                        continue
                    self.used_titles.add(key)
                    return {"text": t, "refs": [f["id"]], "kind": "interpretation"}
        return {"text": first_sentences(sd["purpose"], MAXT) or sd["blueprint_title"], "refs": [],
                "kind": "interpretation"}

    def subtitle_for(self, sd):
        g = self.gates.get(sd["id"], {})
        if g.get("substituted_with"):
            return {"text": f"Module of record {', '.join(sd['primary_modules'])} was not produced; "
                            f"built from {', '.join(g['substituted_with'])}. Treat as indicative.",
                    "refs": ["CHECK:coverage"], "kind": "interpretation"}
        mods = sd["primary_modules"] or sd["secondary_modules"]
        weak = [c for c in mods if self.cov["modules"].get(c, {}).get("coverage_pct", 0) < 50]
        if weak:
            return {"text": f"Evidence is thin: {', '.join(weak)} returned under half its fact base populated.",
                    "refs": ["CHECK:coverage"], "kind": "interpretation"}
        return {"text": "Evidence base: data-room documents and agent analysis; no primary customer research.",
                "refs": ["CHECK:coverage"], "kind": "interpretation"}

    # ---------------------------------------------------------------- mechanical slides
    def module_verdicts(self, content=None):
        """Verdict table for the modules the report relies on: core modules plus any module cited on
        a rendered page. The rest are counted in the takeaway, not listed page after page."""
        verd = self.checks.get("verdicts", {})
        rows, refs = [], []
        cited = set()
        if content:
            blob = json.dumps(content.get("slides", {}))
            cited = {c for c in self.cov["modules"] if re.search(rf'"{c}-', blob)}
        mods = sorted(((c, m) for c, m in self.cov["modules"].items()
                       if not content or m["criticality"] == "core" or c in cited),
                      key=lambda kv: (kv[1]["criticality"] != "core", kv[0]))
        self._verdicts_listed = {c for c, _ in mods}
        pages = []
        for chunk in balanced(mods, 9):
            rows, refs = [], []
            for code, m in chunk:
                v = verd.get(code) or {}
                stated = v.get("confidence", "—")
                adj = self.adjust_conf(stated, m["coverage_pct"], m["criticality"])
                dfc = m.get("direct_facts", 0)
                if dfc >= 10 and adj == "Low" and m["coverage_pct"] < 60:
                    adj = "Medium (VDR)"          # the data room fills what the agent left empty
                rows.append([code, "yes" if m["present"] and m["coverage_pct"] > 0 else
                             ("VDR only" if dfc else "NOT PRODUCED"),
                             f"{m['coverage_pct']}%", str(dfc), stated, adj])
                refs.append([f"CHECK:coverage.by_module.{code}"])
            pages.append({
                "title": {"text": "Module verdicts, restated at the confidence the evidence supports "
                                  "rather than the confidence each agent claimed",
                          "refs": ["CHECK:coverage"], "kind": "interpretation"},
                "subtitle": {"text": "T7: capped by agent coverage band, downgraded where a core module is "
                                     "missing; lifted to Medium where the data room supplies the facts.",
                             "refs": ["CHECK:coverage"], "kind": "interpretation"},
                "elements": {"table": {"type": "table",
                                       "columns": ["Module", "Agent output", "Agent coverage",
                                                   "VDR items", "Stated", "Adjusted"],
                                       "rows": rows, "row_refs": refs,
                                       "col_widths": [1.3, 1.7, 2.0, 1.5, 1.6, 1.6]},
                             "takeaway": {"type": "text", "text": self.verdict_takeaway(),
                                          "refs": ["CHECK:coverage"], "kind": "interpretation"}},
                "baseline": True})
        return pages

    @staticmethod
    def adjust_conf(stated, cov, crit):
        order = ["Low", "Medium", "High"]
        s = stated if stated in order else "Low"
        cap = "High" if cov >= 80 else ("Medium" if cov >= 60 else "Low")
        out = order[min(order.index(s), order.index(cap))]
        if crit == "core" and cov < 60:
            out = "Low"
        return out

    def verdict_takeaway(self):
        weak = [c for c, m in self.cov["modules"].items()
                if m["present"] and m["coverage_pct"] < 40 and m.get("direct_facts", 0) < 10]
        filled = [c for c, m in self.cov["modules"].items()
                  if m["coverage_pct"] < 40 and m.get("direct_facts", 0) >= 10]
        miss = self.cov["missing_core"]
        parts = []
        if miss:
            parts.append(f"{len(miss)} core module(s) were not produced ({', '.join(miss)})")
        if weak:
            parts.append(f"{len(weak)} modules returned under 40% of their fact base populated "
                         f"({', '.join(sorted(weak))})")
        if filled:
            parts.append(f"{', '.join(sorted(filled))} filled from the data room")
        listed = getattr(self, "_verdicts_listed", None)
        tail = (f" {len(self.cov['modules']) - len(listed)} other modules are not relied on and not listed."
                if listed else "")
        return ((("; ".join(parts) + ". Conclusions resting on weak modules are indicative only.")
                 if parts else "All produced modules cleared the coverage bands.") + tail)

    def source_register(self):
        """Register of what the report rests on. Data-room files read directly come first, under
        their real names; then artefacts only the agents cited (OCR spellings resolved to the real
        file where possible); then analyst web research."""
        norm = lambda x: re.sub(r"[^a-z0-9]", "", x.lower())
        direct = defaultdict(int)
        sect = {}
        for f in self.facts:
            if f.get("source") in ("vdr_direct",) and (f.get("citations") or {}).get("doc"):
                path = f["citations"]["doc"][0]
                parts = path.split("__")
                name = parts[-1]
                direct[name] += 1
                sect[name] = re.sub(r"^\d+_\s*", "", parts[1]) if len(parts) > 2 else "data room"
        inv = []
        vp = self.work / "vdr_evidence.json"
        if vp.exists():
            inv = read_json(vp).get("files", [])
        inv_norm = {norm(x["name"]): x for x in inv if len(norm(x["name"])) >= 6}

        def resolve(ocr_name):
            k = norm(ocr_name)
            if k in inv_norm:
                return inv_norm[k]
            hits = [v for n_, v in inv_norm.items() if k.endswith(n_) or (len(k) >= 12 and k in n_)]
            return max(hits, key=lambda v: len(v["name"])) if hits else None

        rows = [[wcut(n, 62), wcut(sect[n], 34), "read directly (VDR)", str(k)]
                for n, k in sorted(direct.items(), key=lambda kv: -kv[1])]
        cited, csect, other = defaultdict(int), {}, [0, 0]
        seen_norm = {}
        for a_ in self.cov["artifacts"]:
            fn = a_.get("filename")
            if not fn or fn == "None":
                continue
            hit = resolve(fn)
            if hit and hit["name"] in direct:
                continue
            name = hit["name"] if hit else fn
            k = norm(name)
            # OCR variants of one file ("CC,Depreciation..." / "21_4BalanceSheet..._CC,Depreciation...")
            key = next((s_ for s_ in seen_norm if k.endswith(s_) or s_.endswith(k)), k)
            seen_norm.setdefault(key, name)
            cited[seen_norm[key]] += a_["citations"]
            vp_ = a_.get("vdr_path")
            csect[seen_norm[key]] = (re.sub(r"^\d+_\s*", "", hit["section"]) if hit else
                                     (re.sub(r"^\d+_?", "", vp_.split("__")[0]) if vp_ else "path not resolved"))
        for n, k in sorted(cited.items(), key=lambda kv: -kv[1]):
            if k >= 5:
                rows.append([wcut(n, 62), wcut(csect[n], 34), "cited by agents", str(k)])
            else:
                other[0] += 1
                other[1] += k
        if other[0]:
            rows.append([f"{other[0]} further artefacts cited by agents", "various", "cited by agents", str(other[1])])
        web = {}
        for f in self.facts:
            if f.get("source") == "analyst_research":
                web.setdefault(f.get("url", ""), [0, f.get("section_title", "")])[0] += 1
        for u, (k, t) in web.items():
            rows.append([wcut(t or u, 62), wcut(re.sub(r"^https?://(www\.)?", "", u), 34), "web research", str(k)])
        rows = rows[:36]
        pages = []
        for chunk in balanced(rows, 9):
            pages.append({
                "title": {"text": "Every source the report rests on: data-room files read directly, "
                                  "artefacts the agents cited, and web research",
                          "refs": ["CHECK:citation_index"], "kind": "fact"},
                "subtitle": {"text": f"{len(direct)} data-room files read directly; "
                                     f"{self.cov['source_artifacts']['distinct']} artefacts cited by agents; "
                                     f"{len(web)} web sources read by the analyst.",
                             "refs": ["CHECK:citation_index"], "kind": "fact"},
                "elements": {"table": {"type": "table",
                                       "columns": ["Artefact", "Data-room section / site", "How used", "Items"],
                                       "rows": chunk,
                                       "row_refs": [["CHECK:citation_index"] for _ in chunk],
                                       "col_widths": [5.4, 3.4, 2.2, 1.4]},
                             "takeaway": {"type": "text",
                                          "text": "Items = evidence rows extracted (direct reads) or citations "
                                                  "(agent artefacts). Artefacts not in the data room as named are "
                                                  "listed under E10-SOURCE-DRIFT.",
                                          "refs": ["CHECK:citation_index"], "kind": "interpretation"}},
                "baseline": True})
        return pages

    def build_exceptions(self):
        ex = []
        for c in self.cov["missing_core"]:
            ex.append({"severity": "HIGH", "rule": "E1-NOT-PROVIDED",
                       "issue": f"Core module {c} was not produced by the agent run.",
                       "slides": [s["id"] for s in self.sm["slides"] if c in s["primary_modules"]],
                       "source": "coverage.json",
                       "treatment": "Slides built from fallback modules and labelled as substituted; "
                                    "re-run the agent for this module before the report is final."})
        for old, new in (self.cov.get("substituted") or {}).items():
            ex.append({"severity": "LOW", "rule": "E12-SUBSTITUTION",
                       "issue": f"{old} superseded by {', '.join(new)} in this corpus.",
                       "slides": [], "source": "module_registry.supersedes",
                       "treatment": "Accepted; the newer module is the module-of-record."})
        gated = defaultdict(list)
        for g in self.gates.values():
            if not g["render"]:
                gated[(g["exception"], g["reason"].split(":")[0])].append(g["id"])
        for (rule, reason), ids in sorted(gated.items()):
            sev = "HIGH" if rule == "E9-BLOCKER" else "MEDIUM"
            ex.append({"severity": sev, "rule": rule,
                       "issue": f"{len(ids)} slide(s) withheld — {reason}.",
                       "slides": sorted(ids), "source": "gates.json",
                       "treatment": "Page withheld rather than filled with placeholder content; "
                                    + ("supply a customer survey export or interview programme to "
                                       "unlock." if rule == "E11-NO-PRIMARY" else
                                       "raise a data request for the named module.")})
        zero = sorted(c for c, m in self.cov["modules"].items()
                      if m["present"] and m["facts"] > 5 and m["populated_facts"] == 0)
        if zero:
            ex.append({"severity": "HIGH", "rule": "E1-NOT-PROVIDED",
                       "issue": f"{len(zero)} modules returned a full fact template with every value "
                                f"unpopulated: {', '.join(zero)}.",
                       "slides": [], "source": "coverage.json",
                       "treatment": "Treated as no evidence, not as a negative finding. These are the "
                                    "highest-value follow-up requests."})
        ms = self.checks.get("market_size_mentions", {}).get("mentions", [])
        if len({m.get("value") for m in ms}) > 1:
            ex.append({"severity": "HIGH", "rule": "E3-CONFLICT",
                       "issue": "Market-size estimates differ across modules; values shown with "
                                "their sources rather than reconciled.",
                       "slides": ["S021_h1_market_size", "S037_tam_walkdown"],
                       "source": "auto_checks.market_size_mentions",
                       "treatment": "T11-TRIANGULATE: all values shown with source; none adopted."})
        cagrs = self.checks.get("cagr_mentions", {})
        if len(cagrs) > 1:
            ex.append({"severity": "CRITICAL", "rule": "E3-CONFLICT",
                       "issue": "Growth rate is stated at materially different levels across modules "
                                f"({', '.join(sorted(cagrs)[:5])}%) — the CIM claim and the external "
                                "benchmark do not reconcile.",
                       "slides": ["S023_h1_growth_drivers", "S040_growth_factors_overview",
                                  "S046_sam_growth_build"],
                       "source": "auto_checks.cagr_mentions",
                       "treatment": "Divergence shown on the slide; the CIM growth claim is not "
                                    "adopted as a finding."})
        kc = self.checks.get("kpi_conflicts") or []
        for k in (kc.keys() if isinstance(kc, dict) else kc):
            k = k if isinstance(k, str) else str(k)
            ex.append({"severity": "MEDIUM", "rule": "E3-CONFLICT",
                       "issue": f"'{k}' is reported inconsistently across modules.",
                       "slides": [], "source": f"auto_checks.kpi_conflicts.{k}",
                       "treatment": "Module-of-record value used (R3); the divergence is noted."})
        if not set(self.cov["doc_types"]) & {"survey", "interviews"}:
            ex.append({"severity": "HIGH", "rule": "E11-NO-PRIMARY",
                       "issue": "No primary customer research in the data room. Customer-side "
                                "conclusions rest on management materials and contracts only.",
                       "slides": [], "source": "coverage.json",
                       "treatment": "All survey/interview-dependent pages withheld; customer "
                                    "conclusions are qualified throughout."})
        unres = self.cov["source_artifacts"]["unresolved_path"]
        if unres:
            ex.append({"severity": "MEDIUM", "rule": "E10-SOURCE-DRIFT",
                       "issue": f"{unres} cited artefacts could not be resolved to a data-room path "
                                "(version drift between what the agents read and what the VDR holds).",
                       "slides": ["S100_source_register"], "source": "coverage.json",
                       "treatment": "Listed in the source register; figures from them are flagged."})
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        ex.sort(key=lambda e: order.get(e["severity"], 9))
        return ex

    def exceptions_slide(self, ex):
        pages = []
        for chunk in balanced(ex, 8):
            rows = [[e["severity"], e["rule"], e.get("short") or shorten(e["issue"]),
                     (", ".join(s.split("_")[0] for s in e["slides"][:4]) + (f" +{len(e['slides']) - 4} more" if len(e["slides"]) > 4 else ""))
                     or "—", e.get("treatment_short") or shorten(e["treatment"])] for e in chunk]
            pages.append({
                "title": {"text": "What this report could not establish, and the data request that "
                                  "would close each gap", "refs": ["CHECK:exceptions"],
                          "kind": "interpretation"},
                "subtitle": {"text": f"{len(ex)} exceptions; "
                                     f"{sum(1 for e in ex if e['severity'] in ('CRITICAL', 'HIGH'))} "
                                     f"at HIGH or above. Withheld pages are listed, not hidden.",
                             "refs": ["CHECK:exceptions"], "kind": "fact"},
                "elements": {"table": {"type": "table",
                                       "columns": ["Sev", "Rule", "Issue", "Slides", "Treatment"],
                                       "rows": rows,
                                       "row_refs": [["CHECK:exceptions"] for _ in rows],
                                       "col_widths": [0.9, 1.6, 4.6, 1.9, 3.4],
                                       "pill_cols": [{"col": 0, "scale": "bad_high"}]},
                             "takeaway": {"type": "text",
                                          "text": "No figure in this deck rests on an exception marked "
                                                  "CRITICAL without that exception being stated on the "
                                                  "slide itself.", "refs": ["CHECK:exceptions"],
                                          "kind": "interpretation"}},
                "baseline": True})
        return pages

    # ---------------------------------------------------------------- front matter
    DISCLAIMER = (
        "This report has been prepared from the diligence agent outputs and data-room documents listed "
        "in the source register, and is limited to what those sources contain. It is intended solely for "
        "the addressee in evaluating the transaction described. It is not an audit, a legal opinion or "
        "investment advice and provides no assurance. Figures are reproduced or calculated from the stated "
        "sources; where evidence was missing, inconsistent or unverifiable this is stated on the slide and "
        "in the exceptions appendix. Pages of the standard report structure that the evidence could not "
        "support have been withheld rather than filled, and are listed with the reason. Projections are "
        "management's and are shown as plan (P), never as results. No duty of care is accepted towards any "
        "third party.")

    def disclaimer(self):
        synth = self.checks.get("synthetic", {}).get("detected")
        prim = bool(set(self.cov["doc_types"]) & {"survey", "interviews"})
        notice = ("Data notice: inputs carry synthetic-data markers; figures are illustrative only. "
                  if synth else "Data notice: ")
        notice += (f"evidence comprises {len([m for m in self.cov['modules'].values() if m['present']])} "
                   f"diligence modules and {self.cov['source_artifacts']['distinct']} data-room artefacts. ")
        notice += ("No customer survey or interview programme was available; customer-side findings rest "
                   "on company records and management materials." if not prim else
                   "Primary research is included as cited.")
        return {"elements": {
            "disclaimer_body": {"type": "text", "text": self.DISCLAIMER, "refs": ["RUN:disclaimer"], "kind": "fact"},
            "data_notice": {"type": "text", "text": notice, "refs": ["CHECK:coverage"], "kind": "fact"}},
            "baseline": True}

    def glossary(self, content, extra=None):
        terms = load_yaml("glossary.yaml")["terms"]
        terms.update(extra or {})
        blob = json.dumps(content["slides"], ensure_ascii=False)
        used = [(k, v) for k, v in terms.items()
                if re.search(rf"(?<![A-Za-z]){re.escape(k.split(' (')[0])}(?![A-Za-z])", blob, re.I)]
        used.sort(key=lambda kv: kv[0].lower())
        pages = []
        for chunk in balanced(used, 10):
            pages.append({
                "title": {"text": "Terms and abbreviations used in this report", "refs": ["RUN:glossary"],
                          "kind": "fact"},
                "subtitle": {"text": "Definitions as applied here; plan years carry a P suffix and are never results.",
                             "refs": ["RUN:glossary"], "kind": "fact"},
                "elements": {"table": {
                    "type": "table", "columns": ["Term", "Meaning in this report"],
                    "rows": [[k, v] for k, v in chunk], "row_refs": [["RUN:glossary"] for _ in chunk],
                    "col_widths": [2.4, 10.0]},
                    "takeaway": {"type": "text", "text": "Terms are listed only where they appear in this report.",
                                 "refs": ["RUN:glossary"], "kind": "fact"}}, "baseline": True})
        return pages or [{"elements": {"table": {"type": "table", "columns": ["Term", "Meaning"],
                                                 "rows": [["—", "No defined terms used"]],
                                                 "row_refs": [["RUN:glossary"]]}}}]

    def auto_withhold(self, content):
        """A page whose panels are mostly 'insufficient' is unfinished (review finding 5):
        withhold it and say why, rather than ship a half-empty page."""
        for sid, sc in list(content["slides"].items()):
            if isinstance(sc, list) or sid in content.get("force_render", []):
                continue
            els = [e for e in (sc.get("elements") or {}).values() if isinstance(e, dict)]
            if not els:
                continue
            ins = sum(1 for e in els if e.get("type") == "insufficient")
            if ins * 2 >= len(els):
                del content["slides"][sid]
                content.setdefault("withhold", []).append({
                    "id": sid, "exception": "E13-WITHHELD",
                    "reason": f"{ins} of {len(els)} panels had no usable evidence after drafting"})
        w = content.get("withhold") or []
        if w:
            content["exceptions"].append({
                "severity": "MEDIUM", "rule": "E13-WITHHELD",
                "issue": f"{len(w)} page(s) withheld after drafting because most panels lacked usable evidence.",
                "slides": [x["id"] for x in w], "source": "draft_baseline",
                "treatment": "Pages removed; the gaps are listed here. Complete them or leave withheld."})

    # ---------------------------------------------------------------- main
    def run(self):
        content = {"project": self.meta, "slides": {}, "calculations": [],
                   "exceptions": [], "metrics": {}, "force_render": []}
        ex = self.build_exceptions()
        content["exceptions"] = ex
        for sd in self.sm["slides"]:
            sid = sd["id"]
            g = self.gates.get(sid)
            if g and not g["render"]:
                continue
            arch = sd["archetype"]
            if arch == "divider":
                continue
            if sid == "S099_module_verdicts":
                content["slides"][sid] = self.module_verdicts()
                continue
            if sid == "S100_source_register":
                content["slides"][sid] = self.source_register()
                continue
            if sid == "S101_exceptions":
                content["slides"][sid] = self.exceptions_slide(ex)
                continue
            if arch == "contents":
                content["slides"][sid] = {"elements": {}}
                continue
            if arch == "disclaimer":
                content["slides"][sid] = self.disclaimer()
                continue
            if sid == "S007_glossary":
                continue                      # built last, from the words the deck actually uses
            sc = {"elements": {}, "baseline": True}
            if arch == "cover":
                m = self.meta
                sc["elements"] = {
                    "report_title": {"type": "text",
                                     "text": f"Commercial Due Diligence: {m['target']}",
                                     "refs": ["RUN:target"], "kind": "fact"},
                    "report_subtitle": {"type": "text",
                                        "text": f"{m['name']} · {m['status']}",
                                        "refs": ["RUN:project"], "kind": "fact"},
                    "prepared_for": {"type": "text", "text": f"Prepared for {m['client'] or 'the addressee'}",
                                     "refs": ["RUN:client"], "kind": "fact"},
                    "report_date": {"type": "text", "text": m.get("date") or "",
                                    "refs": ["RUN:date"], "kind": "fact"},
                }
                content["slides"][sid] = sc
                continue
            if arch == "back_cover":
                content["slides"][sid] = {"elements": {
                    "back_contact": {"type": "text",
                                     "text": "[Engagement contacts to be completed before issue]",
                                     "refs": ["RUN:project"], "kind": "gap"},
                }, "baseline": True}
                continue
            if arch not in ("disclaimer", "text_panel"):
                sc["title"] = self.title_for(sd)
                sc["subtitle"] = self.subtitle_for(sd)
            col_cursor = 0
            for el in sd.get("elements", []):
                name, t = el["name"], el["type"]
                if t == "auto":
                    continue
                if arch == "columns5" and name.startswith("col"):
                    v = self.el_bullets(sd, el, skip=col_cursor)
                    col_cursor += (el.get("limits", {}) or {}).get("max_items", 4)
                    if v is not None:
                        sc["elements"][name] = v
                    continue
                if t == "table":
                    v = self.el_table(sd, el)
                elif t == "bullets":
                    v = self.el_bullets(sd, el)
                elif t == "chart":
                    v = self.el_chart(sd, el)
                elif t == "kpis":
                    v = self.el_kpis(sd, el)
                elif t == "text":
                    v = self.el_text(sd, el, name)
                else:
                    v = self.el_insufficient(sd, f"unhandled element type {t}")
                if v is not None:
                    sc["elements"][name] = v
            content["slides"][sid] = sc
        self.auto_withhold(content)
        if not self.gates.get("S007_glossary", {}).get("render") is False:
            content["slides"]["S007_glossary"] = self.glossary(content)
        return content


def main():
    global STRONG
    STRONG = re.compile("|".join(f"(?:{p['rx']})" for p in load_yaml("claim_rules.yaml")["patterns"]), re.I)
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--client", default="")
    ap.add_argument("--date", default="")
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--status", default="Draft for discussion")
    ap.add_argument("--out")
    a = ap.parse_args()
    work = Path(a.work)
    meta = {"name": a.project, "target": a.target, "client": a.client, "date": a.date,
            "status": a.status, "currency": a.currency,
            "footer": f"{a.project} · Commercial due diligence · {a.status}"}
    d = Drafter(work, meta)
    content = d.run()
    out = Path(a.out) if a.out else work / "content.json"
    write_json(out, content)
    n = len(content["slides"])
    print(f"[draft-baseline] {n} slides drafted, {len(content['exceptions'])} exceptions -> {out}")
    print("  These are machine-composed titles. Rewrite them before the deck leaves the building.")


if __name__ == "__main__":
    main()
