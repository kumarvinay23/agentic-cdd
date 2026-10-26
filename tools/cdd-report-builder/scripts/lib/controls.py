"""Diligence controls C1-C6 applied to every claim, calculation and chart.

    C1 contract    'contracted / committed / backlog' needs a reviewed contract behind it
    C2 reconcile   a figure that disagrees across sources must be reconciled or excepted
    C3 integrity   a calculation may not silently mix actual and plan, or record and model
    C4 population  retention / counts compared only on the same population and period
    C5 evidence    claim-level grade from the *class* of each source, not the count of citations
    C6 net value   benefits (synergy, savings, uplift) stated net of costs, capex and timing

Config: config/controls.yaml. Guide: references/08_diligence_controls.md.
Each check returns (where, message, severity); messages start with the control id so
review_register.py can file them.
"""
from __future__ import annotations

import re

from .common import load_yaml

CFG = None


def cfg():
    global CFG
    if CFG is None:
        CFG = load_yaml("controls.yaml")
    return CFG


ATTRIBUTED = re.compile(r"\b(management|the cim|per the company|the company (?:states|expects|says)|claims?|"
                        r"asserts?|self-assess\w*|the plan (?:assumes|needs|takes)|the model (?:uses|assumes)|"
                        r"agents?|stated|according to|advertises|quotes|lists|per (?:the )?(?:cim|company|model)|cim definition)\b|\(per cim\)|\(cim\)", re.I)


# ----------------------------------------------------------------------------- C5 classification
def artefact_of(f):
    docs = (f.get("citations") or {}).get("doc") or []
    return (docs[0].split("__")[-1] if docs else "") or ""


def artefact_class(name):
    for cls, rx in cfg()["artefact_classes"].items():
        if re.search(rx, name or "", re.I):
            return cls
    return None


def classify(ref, facts, calcs=None):
    """Source class of one ref (see config/controls.yaml source_classes)."""
    if not isinstance(ref, str):
        return "unsupported"
    if ref.startswith("CALC"):
        return "computed"
    if ref.startswith(("RUN:", "CHECK:")):
        return "assumption" if ref.startswith("RUN:") else "computed"
    f = facts.get(ref)
    if not f:
        return "unsupported"
    flags = set(f.get("flags") or [])
    if f.get("source") == "analyst_research" or f.get("basis") == "web":
        return "external"
    if "MGMT_REPRESENTATION" in flags:
        return "management_assertion"
    if f.get("source") != "vdr_direct":
        # agent output: an interpretation, or a restatement of a document the agent cited
        return "agent_restatement"
    if "MODEL_BASIS" in flags:
        return "assumption"
    if f.get("recipe") == "cim_crosswalk" and not re.search(r"\d", str((f.get("cells") or {}).get("Support", ""))):
        return "management_assertion"         # a tie-out row whose 'support' is only a description
    ac = artefact_class(artefact_of(f))
    if ac in ("record", "contract"):
        return "reviewed_record"
    if ac == "management_assertion":
        return "management_assertion"
    return "management_analysis"


INDEPENDENT = {"reviewed_record", "primary_research", "external"}


PLAN_TEXT = re.compile(r"\b(20\d\dP|plan|planned|modell?ed|scenario|upside|downside|forecast|budget|projected|"
                       r"target|option years? exercised|full contract|assum\w+)\b", re.I)


def claim_grade(refs, facts, calcs=None, text=None):
    """Grade a claim from the classes of its sources. A forward-looking claim (plan year, scenario,
    'modelled') supported only by management's own model is an assumption, not evidence: the
    workbook proves management modelled it, not that it will happen."""
    classes = [classify(r, facts, calcs) for r in refs]
    if text and PLAN_TEXT.search(text):
        classes = ["assumption" if c == "management_analysis" else c for c in classes]
    arts = {artefact_of(facts[r]) for r in refs if r in facts and classify(r, facts) == "reviewed_record"}
    cs = set(classes)
    if "reviewed_record" in cs and (len(arts) >= 2 or (cs & (INDEPENDENT - {"reviewed_record"}))):
        return "established", classes
    if cs & {"reviewed_record", "management_analysis", "external", "primary_research"}:
        return "indicated", classes
    if cs & {"management_assertion", "agent_restatement", "assumption", "computed"}:
        return "asserted", classes
    return "unsupported", classes


def is_contract_ref(ref, facts):
    f = facts.get(ref)
    return bool(f) and f.get("source") == "vdr_direct" and artefact_class(artefact_of(f)) == "contract"


# ----------------------------------------------------------------------------- claim iteration
def claims(content):
    """Every text-bearing claim: (slide, where, label, text, refs, kind)."""
    for sid, sc in (content.get("slides") or {}).items():
        pages = sc if isinstance(sc, list) else [sc]
        for pi, page in enumerate(pages, 1):
            if not isinstance(page, dict):
                continue
            where = sid if len(pages) == 1 else f"{sid} p{pi}"
            for k in ("title", "subtitle"):
                v = page.get(k)
                if isinstance(v, dict):
                    yield sid, where, k, v.get("text", ""), v.get("refs", []), v.get("kind")
            for name, el in (page.get("elements") or {}).items():
                if not isinstance(el, dict):
                    continue
                t = el.get("type")
                if t == "text":
                    yield sid, where, name, el.get("text", ""), el.get("refs", []), el.get("kind")
                elif t == "bullets":
                    for i, it in enumerate(el.get("items") or [], 1):
                        if isinstance(it, dict):
                            yield sid, where, f"{name}.item{i}", it.get("text", ""), it.get("refs", []), it.get("kind")
                elif t == "table":
                    rr = el.get("row_refs") or []
                    for i, row in enumerate(el.get("rows") or [], 1):
                        refs = rr[i - 1] if i - 1 < len(rr) else []
                        yield sid, where, f"{name}.row{i}", " | ".join(map(str, row)), refs, "table_row"
                elif t == "kpis":
                    for i, it in enumerate(el.get("items") or [], 1):
                        yield (sid, where, f"{name}.kpi{i}", f"{it.get('value', '')} {it.get('label', '')}",
                               it.get("refs", []), it.get("kind"))


SKIP_SLIDES = re.compile(r"^S(001|002|004|007|097|099|100|101)_")


def claim_register(content, facts):
    out = []
    for sid, where, label, text, refs, kind in claims(content):
        if SKIP_SLIDES.match(sid) or not text.strip():
            continue
        grade, classes = claim_grade(refs, facts, text=text)
        out.append({"slide": where, "element": label, "claim": text, "refs": refs, "kind": kind,
                    "grade": grade, "source_classes": sorted(set(classes))})
    return out


# ----------------------------------------------------------------------------- checks
def check_c1_contract(content, facts):
    rx = re.compile(cfg()["contract_claim_rx"], re.I)
    issues = []
    attributed_pages = _page_attribution(content)
    for sid, where, label, text, refs, kind in claims(content):
        if SKIP_SLIDES.match(sid):
            continue
        if (sid in attributed_pages and label not in ("title", "subtitle", "takeaway")) or ATTRIBUTED.search(text or ""):
            continue                                   # reported as management's description
        m = rx.search(text or "")
        if not m:
            continue
        neg = re.search(r"\b(not|no|un|none|neither|nothing|without|beyond)\b[^.;]{0,40}" + re.escape(m.group(0)), text, re.I) \
            or re.search(r"\bun" + re.escape(m.group(0)), text, re.I)
        if neg:
            continue                                   # "not contracted", "uncontracted"
        if any(is_contract_ref(r, facts) for r in refs):
            continue
        sev = "e" if label in ("title", "subtitle", "takeaway", "lead") else "w"
        issues.append((f"{where}.{label}", f"C1: '{m.group(0)}' asserts a contractual commitment but no reviewed "
                                           f"contract is cited - state duration, options, termination rights and "
                                           f"minimums from the contract, or call it recurring / management-stated", sev))
    return issues


def check_c3_integrity(content, facts):
    issues = []
    for c in content.get("calculations", []):
        if c.get("mixes_bases"):
            continue
        status, klass = set(), set()
        for k, v in (c.get("inputs") or {}).items():
            refs = v.get("ref") if isinstance(v.get("ref"), list) else [v.get("ref")]
            for r in refs:
                f = facts.get(r) if isinstance(r, str) else None
                if not f:
                    continue
                per = v.get("period")
                ps = f.get("period_status") or {}
                st = ps.get(per) if per else (next(iter(set(ps.values())), None) if len(set(ps.values())) == 1 else None)
                if "MODEL_BASIS" in (f.get("flags") or []):
                    st = "plan"
                if st in ("actual", "ytd"):
                    status.add("actual")
                elif st == "plan":
                    status.add("plan")
                cl = classify(r, facts)
                if cl in ("reviewed_record", "management_analysis"):
                    klass.add("record" if cl == "reviewed_record" else "management_analysis")
        for a, b in cfg()["incompatible_bases"]:
            if {a, b} <= status | klass:
                issues.append((f"calc {c['id']}", f"C3: calculation mixes {a} and {b} inputs - declare "
                                                  f"`mixes_bases` with the reason, or restate on one basis", "w"))
    return issues


def _pops(text):
    return {p for p, rx in cfg()["populations"].items() if re.search(rx, text or "", re.I)}


def check_c4_population(content, facts):
    comp = re.compile(cfg()["comparison_rx"], re.I)
    issues = []
    for sid, where, label, text, refs, kind in claims(content):
        if SKIP_SLIDES.match(sid) or not comp.search(text or "") or not re.search(r"retention|churn|\bcounts?\b|\bper (?:account|location|home|subscri|customer)", text, re.I):
            continue
        pops = [(_pops(" ".join(str(facts[r].get(k, "")) for k in ("row_label", "section_title", "text")))) for r in refs if r in facts]
        pops = [p for p in pops if p]
        if len(pops) >= 2 and not set.intersection(*pops) and not re.search(r"not (?:strictly |directly )?(?:like[- ]for[- ]like|comparable)|different (?:\(\w+\) )?(?:bases|basis|populations)|basis differs", text, re.I):
            issues.append((f"{where}.{label}", f"C4: compares figures on different populations "
                                               f"({' vs '.join('/'.join(sorted(p)) for p in pops[:2])}) - align the "
                                               f"population and period, or say they are not like for like", "w"))
    return issues


def _page_attribution(content):
    """Slides whose title / subtitle / headings / table columns attribute the page to management."""
    out = set()
    for sid, sc in (content.get("slides") or {}).items():
        pages = sc if isinstance(sc, list) else [sc]
        for page in pages:
            if not isinstance(page, dict):
                continue
            bits = [str((page.get(k) or {}).get("text", "")) if isinstance(page.get(k), dict) else "" for k in ("title", "subtitle")]
            bits += list((page.get("heads") or {}).values())
            for el in (page.get("elements") or {}).values():
                if isinstance(el, dict) and el.get("type") == "table":
                    bits += [str(c) for c in el.get("columns", [])]
            if ATTRIBUTED.search(" ".join(bits)) or re.search(r"\((?:cim|plan|management)\)|\bplan\b|\bcim\b",
                                                                " ".join(bits), re.I):
                out.add(sid)
    return out


def check_c5_evidence(content, facts):
    issues = []
    attributed_pages = _page_attribution(content)
    for sid, where, label, text, refs, kind in claims(content):
        if SKIP_SLIDES.match(sid) or kind not in ("fact", None, "table_row"):
            continue
        grade, classes = claim_grade(refs, facts)
        page_attr = sid in attributed_pages and label not in ("title", "subtitle")
        if refs and set(classes) <= {"management_assertion", "agent_restatement"} and not ATTRIBUTED.search(text or "") \
                and not page_attr:
            issues.append((f"{where}.{label}", "C5: stated as fact but rests only on management assertion or an "
                                               "agent restatement - attribute it ('the CIM states') or cite the record", "w"))
        years = set(re.findall(r"\b(20\d\d)\b", text or ""))
        if years and refs:
            blob = " ".join(" ".join(map(str, (facts[r].get("cells") or {}).keys())) + " " + str(facts[r].get("text", ""))
                            for r in refs if r in facts)
            missing = [y for y in years if y not in blob]
            if missing and all(r in facts for r in refs) and not any(str(r).startswith("CALC") for r in refs):
                issues.append((f"{where}.{label}", f"C5: period {', '.join(sorted(missing))} is not in the cited evidence "
                                                   f"- the citation may not support the exact claim", "w"))
    return issues


def check_c6_net_value(content, facts):
    brx = re.compile(cfg()["benefit_rx"], re.I)
    nrx = re.compile(cfg()["net_markers"], re.I)
    issues = []
    net_calc_slides = {s for c in content.get("calculations", []) if c.get("net_of") for s in c.get("used_on", [])}
    for sid, where, label, text, refs, kind in claims(content):
        if SKIP_SLIDES.match(sid):
            continue
        m = brx.search(text or "")
        if m and not nrx.search(text) and sid not in net_calc_slides:
            issues.append((f"{where}.{label}", f"C6: '{m.group(0)}' stated without netting - show gross benefit, "
                                               f"operating and implementation costs, capex, timing and overlap with the "
                                               f"plan, and keep acquired earnings apart from synergies", "w"))
    return issues


def check_c2_reconciled(content, facts, recon):
    """A slide citing a figure in an unreconciled conflict must name it in an exception."""
    if not recon:
        return []
    ex_text = " ".join(f"{e.get('issue', '')} {e.get('source', '')}" for e in content.get("exceptions", [])).lower()
    ack = {(r.get("metric"), r.get("period")) for r in content.get("reconciliations", [])}
    issues = []
    conflict_refs = {}
    for c in recon.get("conflicts", []):
        if (c["metric"], c["period"]) in ack:
            continue
        for v in c["values"]:
            conflict_refs.setdefault(v["ref"], c)
    seen = set()
    for sid, where, label, text, refs, kind in claims(content):
        for r in refs:
            c = conflict_refs.get(r)
            if not c or (sid, c["metric"], c["period"]) in seen:
                continue
            seen.add((sid, c["metric"], c["period"]))
            if not any(v["ref"].lower() in ex_text for v in c["values"]) and c["metric"].replace("_", " ") not in ex_text:
                issues.append((f"{where}.{label}", f"C2: {c['metric']} {c['period']} differs across sources "
                                                   f"({'; '.join(v['source'] + ' ' + v['raw'] for v in c['values'])}; spread "
                                                   f"{c['spread_pct']}%) - reconcile or record the difference in an exception", "w"))
    return issues


def run_all(content, facts, recon=None):
    out = []
    for fn in (check_c1_contract, check_c3_integrity, check_c4_population, check_c5_evidence, check_c6_net_value):
        out += fn(content, facts)
    out += check_c2_reconciled(content, facts, recon)
    return out
