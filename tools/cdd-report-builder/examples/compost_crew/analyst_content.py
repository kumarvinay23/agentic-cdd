#!/usr/bin/env python3
"""Analyst pass for Project Compost (Compost Crew) - run 3.

Starts from the mechanical baseline (baseline_content.json) and replaces the findings pages with
evidence-graded analysis built from the data room (QBO monthly P&L, investor workbook, market
sizing workbooks), the CIM (management representation), the agent outputs and six items of web
research. Every number is either an evidence cell or a declared calculation.

Grades used on the pages (config/claim_rules.yaml):
  established - a reviewed primary record plus an independent source (lib/controls.claim_grade)
  indicated   - one data-room fact, or web research
  asserted    - management representation (CIM) or agent view only
"""
import copy
import json
import math
import sys
from pathlib import Path

W = Path(__file__).resolve().parent
base = json.loads((W / "baseline_content.json").read_text())
facts = {f["id"]: f for f in json.loads((W / "evidence.json").read_text())["facts"]}

C = copy.deepcopy(base)
C["project"].update({"name": "Project Compost", "target": "Compost Crew", "client": "DiligenceIQ",
                     "date": "September 2026", "status": "Draft for discussion",
                     "footer": "Project Compost · Commercial due diligence · Draft for discussion"})
S = C["slides"]
CALCS = []
EXC = []


# ------------------------------------------------------------------------------------ helpers
def need(*ids):
    for i in ids:
        if i not in facts and not i.startswith(("CALC", "CHECK:", "RUN:")):
            sys.exit(f"unknown evidence id {i}")
    return list(ids)


def calc(cid, formula, inputs, unit, rounding, used_on, note=""):
    names = {k: v[0] for k, v in inputs.items()}
    out = eval(formula, {"__builtins__": {}, "math": math}, names)  # noqa: S307 - our own formulas
    out = round(out, rounding)
    for k, (v, r) in inputs.items():
        rr = r if isinstance(r, list) else [r]
        need(*[x for x in rr if x])
    CALCS.append({"id": cid, "formula": formula,
                  "inputs": {k: {"value": v[0], "ref": v[1]} for k, v in inputs.items()},
                  "output": out, "unit": unit, "rounding": rounding, "used_on": used_on,
                  **({"note": note} if note else {})})
    return out


def also(out_value, *sids):
    for c in CALCS:
        if c["output"] == out_value:
            c["used_on"] = sorted(set(c["used_on"]) | set(sids))
            return out_value
    raise SystemExit(f"no calc with output {out_value}")


def txt(text, refs, kind="interpretation"):
    return {"text": text, "refs": need(*refs), "kind": kind}


def bl(items):
    return {"type": "bullets", "items": [{"text": t, "refs": need(*r), "kind": k} for t, r, k in items]}


def table(cols, rows, widths=None, pills=None):
    el = {"type": "table", "columns": cols, "rows": [r[0] for r in rows],
          "row_refs": [[("CALC:analyst" if x == "CALC" else x) for x in need(*r[1])] for r in rows]}
    if widths:
        el["col_widths"] = widths
    if pills:
        el["pill_cols"] = pills
    return el


def chart(ctype, cats, series, unit, fmt, axis, refs_by_series, highlight=None):
    el = {"type": "chart", "chart_type": ctype, "categories": cats,
          "series": [{"name": n, "values": v} for n, v in series],
          "unit_label": unit, "number_format": fmt, "value_axis_title": axis,
          "refs": sorted({("CALC:analyst" if r == "CALC" else r) for s in refs_by_series for r in s}),
          "point_refs": refs_by_series, "kind": "fact"}
    if highlight is not None:
        el["highlight"] = highlight
    return el


def slide(sid, title, subtitle, elements, heads=None):
    sc = {"title": title, "subtitle": subtitle, "elements": elements}
    if heads:
        sc["heads"] = heads
    S[sid] = sc


def m(x):          # $M display, 2 dp
    return f"${x:,.2f}M" if x >= 0 else f"-${abs(x):,.2f}M"


GRADE_PILL = [{"col": -1, "scale": "good_high"}]

# =========================================================================== 0. front matter
S["S097_back_cover"] = {"elements": {"back_contact": {
    "type": "text", "text": "DiligenceIQ · Project Compost · Commercial due diligence on Compost Crew. "
                            "Draft for discussion, September 2026. Prepared for DiligenceIQ.",
    "refs": ["RUN:project"], "kind": "fact"}}}

S["S003_engagement"] = {
    "title": txt("The mandate: test whether Compost Crew's actual trading, customers and market support "
                 "the management plan to grow revenue to $50.2M by 2030P", ["HPF-V91-R1", "RUN:scope"]),
    "subtitle": txt("Five workstreams; each finding is graded established, indicated or asserted by the "
                    "evidence behind it.", ["RUN:scope"]),
    "elements": {
        "lead": {"type": "text", "text": (
            "Scope: commercial due diligence on Compost Crew (Washington DC, Maryland and Northern Virginia) "
            "using the data room, the management CIM, 36 diligence-agent modules and targeted web research. "
            "No customer survey or interviews were available."), "refs": ["RUN:scope", "CHECK:coverage"],
            "kind": "fact"},
        "col1_body": bl([("What has the business actually delivered, 2023 to Jul-2026?", ["RUN:scope"], "fact"),
                         ("How do segments, margins and cash earnings trend?", ["RUN:scope"], "fact"),
                         ("How much of the plan rests on enforceable contracts?", ["RUN:scope"], "fact")]),
        "col2_body": bl([("How big is the serviceable market by segment and territory?", ["RUN:scope"], "fact"),
                         ("Is the company's sizing method sound?", ["RUN:scope"], "fact"),
                         ("Which geographies come next?", ["RUN:scope"], "fact")]),
        "col3_body": bl([("How well are customers retained, by segment and cohort?", ["RUN:scope"], "fact"),
                         ("How concentrated is revenue?", ["RUN:scope"], "fact"),
                         ("Customer voice: not testable without survey or interviews", ["RUN:scope"], "fact")]),
        "col4_body": bl([("Who competes for the same customers, and how?", ["RUN:scope"], "fact"),
                         ("Is pricing in line with local alternatives?", ["RUN:scope"], "fact"),
                         ("Which claimed differentiators hold up?", ["RUN:scope"], "fact")]),
        "col5_body": bl([("Which levers deliver the plan, and how much each?", ["RUN:scope"], "fact"),
                         ("What must be true for each lever?", ["RUN:scope"], "fact"),
                         ("What would change the view?", ["RUN:scope"], "fact")]),
    },
    "heads": {"col1_head": "Business & Financials", "col2_head": "Market & Geography",
              "col3_head": "Customers & Retention", "col4_head": "Competitive Landscape",
              "col5_head": "Growth Opportunities"}}

n_vdr = sum(1 for f in facts.values() if f.get("source") == "vdr_direct" and not f["id"].startswith("CBG-C"))
n_cim = sum(1 for f in facts.values() if f["id"].startswith("CBG-C"))
n_web = sum(1 for f in facts.values() if f.get("source") == "analyst_research")
slide("S005_research_approach",
      txt("The findings rest on the data room first: company accounts and workbooks outrank the CIM, "
          "and the CIM outranks the agent outputs", ["CHECK:coverage"]),
      txt("Where the agents and the data room disagree the data room is used and the agent finding is "
          "logged as an exception.", ["CHECK:coverage"]),
      {"left": table(
          ["Source", "What it holds", "Items", "Basis", "Grade ceiling"],
          [(["QBO monthly financials", "P&L by month, Jan-2023 to Jul-2026", "56", "reviewed record (unaudited)",
             "indicated alone; established with a second source"], ["CHECK:vdr_items"]),
           (["Investor workbook", "Segments, ARR, retention, cohorts, concentration, CIM tie-out",
             f"{sum(1 for f in facts.values() if f.get('recipe') and 'Investor' in str(f.get('citations')))}",
             "management analysis", "indicated"], ["CHECK:vdr_items"]),
           (["Market sizing workbooks", "Company TAM/SAM/SOM model; ZIP expansion scoring", "64",
             "management analysis (model)", "asserted for forecasts"], ["CHECK:vdr_items"]),
           (["CIM (Aug-2026)", "Management presentation of the business and plan", f"{n_cim}",
             "management representation", "asserted"], ["CHECK:vdr_items"]),
           (["Diligence agents", "36 modules of findings and verdicts", "36 modules", "agent view",
             "asserted"], ["CHECK:coverage"]),
           (["Web research", "Named local competitors and published prices", f"{n_web}", "web, dated",
             "indicated"], ["CHECK:vdr_items"])],
          widths=[2.3, 3.6, 1.1, 2.0, 1.6]),
       "right": bl([
           ("**No primary research** - no survey or interviews, so customer needs, purchase criteria and "
            "switching intent are not evidenced; those pages are withheld.",
            ["CHECK:coverage"], "fact"),
           ("**CIM tie-out** - the investor workbook traces each CIM figure to a schedule; CIM revenue "
            "(2025 $13.3mn) uses the model, not QBO.",
            ["CBG-V98-R3", "HPF-V90-R8"], "fact"),
           ("**Agent errors found** - the market-size and competitor modules contain material errors; "
            "both are replaced here from the data room and web research (see exceptions).",
            ["MVG-1-R", "CID-1-R"], "interpretation"),
           ("**Plan years carry a P** and are management's forecast, never results; actuals end at "
            "Jul-2026 (QBO) and Jun-2026 (workbook).", ["HPF-V91-R1", "HPF-V90-R8"], "fact")])},
      heads={"left_head": "Evidence base by source", "right_head": "Limitations and how they are handled"})

# =========================================================================== 1. business primer
rev23, rev24, rev25 = 7.56, 11.87, 13.41
g24 = calc("C7-growth-2024", "(b / a - 1) * 100", {"a": (7.56, "HPF-V90-R8"), "b": (11.87, "HPF-V90-R8")},
           "%", 1, ["S009_company_snapshot", "S023_h1_growth_drivers", "S020_highlights_summary"])
g25 = calc("C7-growth-2025", "(b / a - 1) * 100", {"a": (11.87, "HPF-V90-R8"), "b": (13.41, "HPF-V90-R8")},
           "%", 1, ["S009_company_snapshot", "S023_h1_growth_drivers", "S046_sam_growth_build",
                    "S020_highlights_summary", "S049_risk_assessment"])
cagr2325 = calc("C7-cagr-2023-25", "((b / a) ** 0.5 - 1) * 100",
                {"a": (7.56, "HPF-V90-R8"), "b": (13.41, "HPF-V90-R8")}, "%", 1, ["S009_company_snapshot"])
slide("S009_company_snapshot",
      txt(f"A $13.4M regional organics collector: revenue grew {g24:.0f}% in 2024 on the DC contract, "
          f"{g25:.0f}% in 2025 and 3% in the first seven months of 2026", ["HPF-V90-R8", "HPF-V90-YTD-revenue"]),
      txt("Actuals from the QBO monthly accounts; EBITDA-positive since 2024 but thin, and net income "
          "negative in 2025.", ["HPF-V90-R40", "HPF-V90-R39"]),
      {"kpis": {"type": "kpis", "items": [
          {"value": "$13.41M", "label": "Revenue 2025 (QBO actual)", "note": "HPF", "refs": ["HPF-V90-R8"], "kind": "fact"},
          {"value": "$13.61M", "label": "TTM revenue to Jun-2026", "note": "HPF", "refs": ["HPF-V90-TTM-revenue-Jun26"], "kind": "fact"},
          {"value": "30.4%", "label": "Gross margin 2025", "note": "HPF", "refs": ["HPF-V90-R22"], "kind": "fact"},
          {"value": "$0.57M", "label": "EBITDA 2025 (4.3% margin)", "note": "HPF", "refs": ["HPF-V90-R40", "HPF-V90-R41"], "kind": "fact"},
          {"value": "25,546", "label": "Active locations, Jun-2026", "note": "CST", "refs": ["CST-V91-R1"], "kind": "fact"}]},
       "left": bl([
           ("**What it does** - per the CIM, food-scrap collection for municipal programmes, businesses and "
            "households, composted at own outposts and third-party sites; plus products.",
            ["CBG-C10-N2", "CBG-C10-N3"], "fact"),
           (f"**Growth record** - revenue $7.56M (2023), $11.87M (2024), $13.41M (2025): a {cagr2325}% "
            "two-year CAGR, most of it in 2024.", ["HPF-V90-R8"], "calc"),
           ("**Current trading** - Jan-Jul 2026 revenue $8.05M vs $7.82M (+3.0%); EBITDA $0.44M vs $0.50M "
            "(-12.9%).", ["HPF-V90-YTD-revenue", "HPF-V90-YTD-EBITDA"], "fact"),
           ("**Earnings** - EBITDA -$0.72M, $1.14M, $0.57M and net income -$1.40M, $0.24M, -$0.56M for "
            "2023-2025.", ["HPF-V90-R40", "HPF-V90-R39"], "fact"),
           ("**Plan, shown separately** - management's $50.17M 2030P revenue is a forecast and is tested "
            "in the growth section, not used here.", ["HPF-V91-R1"], "fact")]),
       "right": chart("column", ["2023", "2024", "2025"],
                      [("Revenue", [7.56, 11.87, 13.41]), ("Gross profit", [1.54, 3.77, 4.08]),
                       ("EBITDA", [-0.72, 1.14, 0.57])],
                      "$M", '"$"0.0"M"', "$M, actual (QBO)",
                      [["HPF-V90-R8"] * 3, ["HPF-V90-R21"] * 3, ["HPF-V90-R40"] * 3])},
      heads={"left_head": "Key facts", "right_head": "Actual revenue, gross profit and EBITDA, 2023-2025 ($M, QBO)"})

slide("S010_platform_evolution",
      txt("The platform was assembled from small acquisitions and one large municipal contract; the "
          "next steps (Utica, Agricity) are bigger than anything integrated so far", ["CBG-C7-N1", "CBG-C31-N1", "CBG-C50-N1"]),
      txt("Milestones from the CIM, checked against the accounts where the accounts can show them.",
          ["CBG-C7-N1", "HPF-V90-R5"]),
      {"flow": table(["When", "Milestone", "What it added", "Grade"], [
          (["2018", "Ben Parry acquires Compost Crew and Fat Worm", "Owner-led platform; commercial routes", "asserted"],
           ["CBG-C7-N3", "CBG-C30-T1-R1"]),
          (["2023", "DC pilot agreement", "DC revenue $0.85M in the first year (model basis)", "established"],
           ["CBG-C16-N7", "RVQ-V91-R3"]),
          (["2024", "Key City acquired; Series A closed", "20,000+ active locations; 6 composting sites",
            "indicated"], ["CBG-C7-N1"]),
          (["2025", "DC five-year contract signed", "Municipal revenue $4.79M (QBO)", "established"],
           ["CBG-C16-N7", "HPF-V90-R2"]),
          (["2Q25", "Utica county site plan approved", "Route to own processing capacity", "indicated"],
           ["CBG-C50-N3"]),
          (["4Q27P", "Utica facility go-live planned", "20k tons a year of permitted capacity", "asserted"],
           ["CBG-C50-N1", "CBG-C50-N3"])], widths=[1.0, 3.6, 3.4, 1.4]),
       "right": bl([
           ("**Acquired lines are visible in the accounts** - Key Compostables revenue $0.31M (2024) and "
            "$0.70M (2025).", ["HPF-V90-R5"], "fact"),
           ("**Volume** - tons collected 2,500 (2020), 13,000 (2024), 16,000 (2025), per company records.",
            ["CBG-C7-T1-R3"], "fact"),
           ("**Integration record is small-scale** - each prior deal added about $0.3M of ARR; Agricity "
            "(~$2.8M revenue) would be roughly nine times larger.", ["CBG-C30-T1-R1", "CBG-C30-T1-R2", "CBG-C31-N1"], "interpretation"),
           ("**Utica is not yet built** - road widening and a grading permit precede go-live.",
            ["CBG-C50-N3"], "fact")])},
      heads={"flow_head": "How the platform was built", "right_head": "Integration record and what it implies"})

labour_pct = calc("C11-labour-share", "a / r * 100", {"a": (4.47, "HPF-V90-R9"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
sub_pct = calc("C11-subcon-share", "a / r * 100", {"a": (1.18, "HPF-V90-R18"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
fleet = calc("C14-fleet-cost", "a + b + c", {"a": (0.43, "HPF-V90-R12"), "b": (0.48, "HPF-V90-R13"), "c": (0.35, "HPF-V90-R14")}, "$M", 2, ["S011_value_chain"])
fleet_pct = calc("C11-fleet-share", "a / r * 100", {"a": (fleet, "CALC"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
proc = calc("C14-processing-cost", "a + b", {"a": (0.99, "HPF-V90-R10"), "b": (0.31, "HPF-V90-R17")}, "$M", 2, ["S011_value_chain"])
proc_pct = calc("C11-processing-share", "a / r * 100", {"a": (proc, "CALC"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
cogs_pct = calc("C11-cogs-share", "a / r * 100", {"a": (0.94, "HPF-V90-R16"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
sga_pct = calc("C11-sga-share", "a / r * 100", {"a": (4.23, "HPF-V90-R36"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S011_value_chain"])
slide("S011_value_chain",
      txt("Collection is the cost base: own crews take a third of revenue and subcontracted routes a "
          f"further {sub_pct}%, which the Agricity deal would bring in-house",
          ["HPF-V90-R9", "HPF-V90-R18"]),
      txt("2025 cost structure from the QBO accounts, by stage of the value chain.", ["HPF-V90-R20"]),
      {"table": table(["Stage", "What Compost Crew does", "2025 cost", "% of revenue", "Grade"], [
          (["Collection - own crews", "Curbside and commercial routes", "$4.47M", f"{labour_pct}%", "established"], ["HPF-V90-R9", "HPF-V90-R8"]),
          (["Collection - subcontracted", "DC routes run by the delivery partner", "$1.18M", f"{sub_pct}%", "established"], ["HPF-V90-R18", "CBG-C31-N1"]),
          (["Fleet", "Fuel, maintenance and risk management", m(fleet), f"{fleet_pct}%", "established"], ["HPF-V90-R12", "HPF-V90-R13", "HPF-V90-R14"]),
          (["Processing and disposal", "Own outposts, third-party sites, transfer", m(proc), f"{proc_pct}%", "established"], ["HPF-V90-R10", "HPF-V90-R17"]),
          (["Products", "Cost of KeyCompostables and compost sold", "$0.94M", f"{cogs_pct}%", "established"], ["HPF-V90-R16"]),
          (["Overheads (SG&A)", "Sales, admin, rent, professional fees", "$4.23M", f"{sga_pct}%", "established"], ["HPF-V90-R36"]),
          (["EBITDA", "What is left", "$0.57M", "4.3%", "established"], ["HPF-V90-R40", "HPF-V90-R41"])],
          widths=[2.4, 4.2, 1.5, 1.5, 1.6]),
       "takeaway": {"type": "text", "text": (
           "Gross margin of 30.4% (2025) leaves little room once overheads are paid. Owning processing "
           "(Utica) and in-sourcing DC collection are the two cost levers management proposes; neither "
           "is yet in the accounts."), "refs": need("HPF-V90-R22", "CBG-C50-N2", "CBG-C31-N3"),
           "kind": "interpretation"}})

muni_share = calc("C4-muni-share-2025", "a / r * 100", {"a": (4.79, "HPF-V90-R2"), "r": (13.41, "HPF-V90-R8")}, "%", 1,
                  ["S012_business_model_flow", "S021_h1_market_size", "S042_gf2_mix_shift", "S029_h4_differentiation"])
slide("S012_business_model_flow",
      txt("Three segments of similar ARR: municipal runs on programme contracts at a low price per home; "
          "commercial is pay as you go and high-value per location",
          ["CST-V91-R2", "CST-V91-R3", "CBG-C16-N7", "WEB-CID-06"]),
      txt("Company workbook at 30-Jun-2026. Locations mix households, business sites and subscribers, so the total is not one unit.",
          ["CST-V91-R1", "HPF-V90-R8"]),
      {"flow": table(["Segment", "Customer and contract", "Locations", "ARR", "Per month"], [
          (["Municipal", "Local-government programmes; multi-year contracts", "19,195", "$5.72M", "$24.84"],
           ["CST-V91-R1", "CST-V91-R2", "CST-V91-R3", "CBG-C16-N7"]),
          (["Commercial", "Businesses and institutions; no contract", "856", "$5.81M", "$566"],
           ["CST-V91-R1", "CST-V91-R2", "CST-V91-R3", "WEB-CID-06"]),
          (["Residential", "Household subscriptions; no contract", "5,495", "$1.93M", "$29.19"],
           ["CST-V91-R1", "CST-V91-R2", "CST-V91-R3", "CST-V97-R3"]),
          (["KeyCompostables and compost", "Products sold online and in bags (per CIM)", "-", "not recurring", "-"], ["CBG-C47-N2"]),
          (["Total", "", "25,546", "$13.46M", "$43.91"], ["CST-V91-R1", "CST-V91-R2", "CST-V91-R3"])],
          widths=[2.2, 4.4, 1.5, 1.6, 1.5]),
       "right": bl([
           (f"**Municipal is {muni_share}% of 2025 revenue** and one DC contract is about 12,000 of its "
            "19,195 households.", ["HPF-V90-R2", "HPF-V90-R8", "CBG-C15-N2"], "calc"),
           ("**Commercial carries the value per location** - $566 a month against $24.84 municipal and "
            "$29.19 residential.", ["CST-V91-R3"], "fact"),
           ("**Residential is flat** - revenue $1.97M (2024) and $1.98M (2025); the paying book is 5,495 "
            "subscribers.", ["HPF-V90-R1", "CST-V97-R3"], "fact"),
           ("**Recurring is not contracted** - only municipal work has written contracts (terms not reviewed); "
            "commercial and residential customers can leave at any time.", ["CBG-C16-N7", "WEB-CID-06"], "interpretation")])},
      heads={"flow_head": "Segments, contracts and unit economics", "right_head": "Where value is captured"})
calc("C14-compost-other-2025", "a + b", {"a": (0.18, "HPF-V90-R4"), "b": (0.14, "HPF-V90-R7")}, "$M", 2, ["S012_business_model_flow"])

slide("S015_barriers",
      txt("Protection rests on one municipal contract and a planned facility, not on structure: the DC terms are "
          "unreviewed and other customers can leave at will", ["CBG-C16-N7", "CBG-C50-N1", "WEB-CID-06"]),
      txt("No evidence supports a broad moat; the agents' 'market moat' view is not adopted.",
          ["REC-2-T1-R1", "CID-4-T1-R3"]),
      {"left": bl([
          ("**DC contract** - the CIM describes one firm year plus four option years, with escalating caps "
           "and price escalators; the contract itself was not reviewed.", ["CBG-C16-N7"], "fact"),
          ("**Permitted processing** - per the CIM, Utica is permitted for 20k tons a year and grant-funded "
           "($2.68 million USDA); not yet operating.", ["CBG-C50-N1"], "fact"),
          ("**Route density** - management cites density for gross margin expansion; the data room holds no "
           "route-level cost data to test it.", ["CBG-C34-N3"], "interpretation"),
          ("**Municipal record** - DC billings of $8.50M lifetime to 2026H1 show the contract is live "
           "and scaling.", ["RVQ-V93-R1"], "fact")]),
       "right": bl([
           ("**No lock-in outside municipal** - Compost Crew advertises no commitment, pay as you go, for "
            "residential and commercial service.", ["WEB-CID-06"], "fact"),
           ("**Competitors own processing too** - Veteran Compost runs permitted sites in Aberdeen MD and "
            "Alexandria VA.", ["WEB-CID-02"], "fact"),
           ("**Brand** - the competition agent rates the brand barrier low; no customer research tests it.",
            ["CID-4-T1-R3"], "interpretation"),
           ("**What would erode the contract barrier** - a DC re-tender at the end of the option years, or "
            "participation stalling below the modelled 50%.", ["CBG-C16-N7", "RVQ-V96-R1"], "interpretation")])},
      heads={"left_head": "What protects the business", "right_head": "Limits and what would erode them"})

# =========================================================================== 2. highlights
calc("C4-muni-share-rounded", "a / r * 100", {"a": (4.79, "HPF-V90-R2"), "r": (13.41, "HPF-V90-R8")}, "%", 0, ["S020_highlights_summary"])
calc("C14-som-current-hl", "a + b", {"a": (65.42, "MVG-V90-R7"), "b": (73.74, "MVG-V90-R15")}, "$M", 0, ["S020_highlights_summary"])
calc("C14-som-expanded-hl", "a + b", {"a": (98.13, "MVG-V90-R8"), "b": (107.73, "MVG-V90-R16")}, "$M", 0, ["S020_highlights_summary"])
calc("C9-reps-multiple", "b / a", {"a": (8, "CBG-C29-T1-R6"), "b": (19, "CBG-C29-T1-R6")}, "x", 1, ["S020_highlights_summary", "S075_l1_channel_expansion"])

# =========================================================================== 3. market
tam_c = calc("C14-tam-current", "a + b", {"a": (726.90, "MVG-V90-R7"), "b": (819.31, "MVG-V90-R15")}, "$M", 2, ["S021_h1_market_size"])
tam_e = calc("C14-tam-expanded", "a + b", {"a": (1090.31, "MVG-V90-R8"), "b": (1196.96, "MVG-V90-R16")}, "$M", 2, ["S021_h1_market_size"])
sam_c = calc("C14-sam-current", "a + b", {"a": (218.07, "MVG-V90-R7"), "b": (245.79, "MVG-V90-R15")}, "$M", 2, ["S021_h1_market_size", "S037_tam_walkdown"])
som_c = calc("C14-som-current", "a + b", {"a": (65.42, "MVG-V90-R7"), "b": (73.74, "MVG-V90-R15")}, "$M", 2, ["S021_h1_market_size", "S089_sizing_method_core"])
som_e = calc("C14-som-expanded", "a + b", {"a": (98.13, "MVG-V90-R8"), "b": (107.73, "MVG-V90-R16")}, "$M", 2, ["S021_h1_market_size"])
pen_cim = calc("C9-penetration-cim", "r / s * 100", {"r": (13.41, "HPF-V90-R8"), "s": (som_e, "CALC")}, "%", 1, ["S021_h1_market_size"])
nonmuni = calc("C14-nonmuni-rev-2025", "a + b + c + d", {"a": (1.98, "HPF-V90-R1"), "b": (5.62, "HPF-V90-R3"),
                                                          "c": (0.18, "HPF-V90-R4"), "d": (0.70, "HPF-V90-R5")}, "$M", 2, ["S021_h1_market_size"])
pen_lfl = calc("C9-penetration-lfl", "r / s * 100", {"r": (nonmuni, "CALC"), "s": (som_c, "CALC")}, "%", 1, ["S021_h1_market_size"])
pen_lfl_e = calc("C9-penetration-lfl-expanded", "r / s * 100", {"r": (nonmuni, "CALC"), "s": (som_e, "CALC")}, "%", 1, ["S021_h1_market_size"])
slide("S021_h1_market_size",
      txt(f"On the company's own model the obtainable market is ${som_c:,.0f}M today and ${som_e:,.0f}M in the "
          "expanded territory; the sizing is management's and leaves out municipal revenue", ["MVG-V90-R7", "MVG-V90-R15", "MVG-V90-R8", "MVG-V90-R16"]),
      txt("Residential and commercial TAM, SAM and SOM from the company's bottom-up workbook; no third-party "
          "sizing was available.", ["MVG-V90-R7", "MVG-V90-R15"]),
      {"chart": chart("stacked_column",
                      ["TAM current", "TAM expanded", "SAM current", "SAM expanded", "SOM current", "SOM expanded"],
                      [("Residential", [726.90, 1090.31, 218.07, 327.09, 65.42, 98.13]),
                       ("Commercial", [819.31, 1196.96, 245.79, 359.09, 73.74, 107.73])],
                      "$M", '"$"#,##0"M"', "$M a year, company model",
                      [["MVG-V90-R7", "MVG-V90-R8"] * 3, ["MVG-V90-R15", "MVG-V90-R16"] * 3]),
       "right": bl([
           (f"**Combined** - TAM ${tam_c:,.0f}M current / ${tam_e:,.0f}M expanded; SAM ${sam_c:,.0f}M current. "
            "SAM and SOM are flat 30% participation and 30% share assumptions.", ["MVG-V90-R1", "MVG-V90-R7", "MVG-V90-R15"], "calc"),
           (f"**Municipal is outside the model** although it is {muni_share}% of 2025 revenue; the DC "
            "contract alone is worth $20.83M a year at full participation.", ["HPF-V90-R2", "RVQ-V96-R3"], "calc"),
           (f"**The CIM's 6.5% penetration** divides total revenue, municipal included, by the $206M SOM; "
            f"excluding municipal it is {pen_lfl}% of today's SOM ({pen_lfl_e}% of the expanded one).", ["CBG-C6-N5", "HPF-V90-R8"], "calc"),
           ("**Agent figure rejected** - the market-size agent's $210.31M-$256.00M is a North American "
            "waste-management market (in billions), not this market.", ["MVG-1-R", "CID-Y5"], "interpretation"),
           ("**Grade: asserted** - a company model, unverified by third-party data or customer research.",
            ["MVG-V90-R7"], "interpretation")])},
      heads={"chart_head": "TAM / SAM / SOM by segment and territory ($M, company model)",
             "right_head": "Basis, gaps and confidence"})

# growth drivers (actual decomposition)
d = {}
for seg, rid, a, b, c_ in [("muni", "HPF-V90-R2", 1.72, 4.24, 4.79), ("comm", "HPF-V90-R3", 4.14, 4.97, 5.62),
                           ("res", "HPF-V90-R1", 1.65, 1.97, 1.98), ("key", "HPF-V90-R5", 0, 0.31, 0.70)]:
    d[seg] = (calc(f"C15-delta24-{seg}", "b - a", {"a": (a, rid), "b": (b, rid)}, "$M", 2, ["S023_h1_growth_drivers"]),
              calc(f"C15-delta25-{seg}", "c - b", {"b": (b, rid), "c": (c_, rid)}, "$M", 2, ["S023_h1_growth_drivers"]))
oth23 = calc("C14-other-2023", "(a + b) / 1000000", {"a": (13969, "HPF-V90-R4"), "b": (30299, "HPF-V90-R7")}, "$M", 2, ["S023_h1_growth_drivers", "S042_gf2_mix_shift"])
oth24 = calc("C14-other-2024", "a + b", {"a": (0.25, "HPF-V90-R4"), "b": (0.13, "HPF-V90-R7")}, "$M", 2, ["S023_h1_growth_drivers", "S042_gf2_mix_shift"])
oth25 = calc("C14-other-2025", "a + b", {"a": (0.18, "HPF-V90-R4"), "b": (0.14, "HPF-V90-R7")}, "$M", 2, ["S023_h1_growth_drivers", "S042_gf2_mix_shift"])
do24 = calc("C15-delta24-other", "b - a", {"a": (oth23, "CALC"), "b": (oth24, "CALC")}, "$M", 2, ["S023_h1_growth_drivers"])
do25 = calc("C15-delta25-other", "b - a", {"a": (oth24, "CALC"), "b": (oth25, "CALC")}, "$M", 2, ["S023_h1_growth_drivers"])
dt24 = calc("C15-delta24-total", "b - a", {"a": (7.56, "HPF-V90-R8"), "b": (11.87, "HPF-V90-R8")}, "$M", 2, ["S023_h1_growth_drivers"])
dt25 = calc("C15-delta25-total", "b - a", {"a": (11.87, "HPF-V90-R8"), "b": (13.41, "HPF-V90-R8")}, "$M", 2, ["S023_h1_growth_drivers"])
sh_c25 = calc("C4-share-growth25-comm", "a / t * 100", {"a": (d["comm"][1], "CALC"), "t": (dt25, "CALC")}, "%", 0, ["S023_h1_growth_drivers"])
sh_m25 = calc("C4-share-growth25-muni", "a / t * 100", {"a": (d["muni"][1], "CALC"), "t": (dt25, "CALC")}, "%", 0, ["S023_h1_growth_drivers"])
sh_k25 = calc("C4-share-growth25-key", "a / t * 100", {"a": (d["key"][1], "CALC"), "t": (dt25, "CALC")}, "%", 0, ["S023_h1_growth_drivers"])
dc24 = calc("C15-dc-delta24", "b - a", {"a": (0.85, "RVQ-V91-R3"), "b": (2.89, "RVQ-V91-R3")}, "$M", 2, ["S023_h1_growth_drivers"])
sh_dc24 = calc("C4-dc-share-growth24", "a / t * 100", {"a": (dc24, "CALC"), "t": (dt24, "CALC")}, "%", 0, ["S023_h1_growth_drivers"])


def sgn(x):
    return f"+{m(x)}" if x >= 0 else m(x)


slide("S023_h1_growth_drivers",
      txt(f"2024's growth was the DC contract; 2025 added only ${dt25:.1f}M, led by commercial and "
          "KeyCompostables, with residential flat", ["HPF-V90-R8", "RVQ-V91-R3", "HPF-V90-R3", "HPF-V90-R5"]),
      txt("Revenue by segment from the QBO accounts; the change each year is decomposed by segment.",
          ["HPF-V90-R8"]),
      {"left": table(["Segment", "2023", "2024", "2025", "Change 2024", "Change 2025"], [
          (["Municipal", "$1.72M", "$4.24M", "$4.79M", sgn(d["muni"][0]), sgn(d["muni"][1])], ["HPF-V90-R2", "CALC"]),
          (["Commercial", "$4.14M", "$4.97M", "$5.62M", sgn(d["comm"][0]), sgn(d["comm"][1])], ["HPF-V90-R3", "CALC"]),
          (["Residential", "$1.65M", "$1.97M", "$1.98M", sgn(d["res"][0]), sgn(d["res"][1])], ["HPF-V90-R1", "CALC"]),
          (["KeyCompostables", "$0", "$0.31M", "$0.70M", sgn(d["key"][0]), sgn(d["key"][1])], ["HPF-V90-R5", "CALC"]),
          (["Compost and other", m(oth23), m(oth24), m(oth25), sgn(do24), sgn(do25)], ["HPF-V90-R4", "HPF-V90-R7", "CALC"]),
          (["Total", "$7.56M", "$11.87M", "$13.41M", sgn(dt24), sgn(dt25)], ["HPF-V90-R8", "CALC"])],
          widths=[2.2, 1.3, 1.3, 1.3, 1.6, 1.6]),
       "right": bl([
           (f"**2024: DC** - DC contract revenue rose {sgn(dc24)} (model basis), {sh_dc24}% of the year's "
            f"{sgn(dt24)} growth.", ["RVQ-V91-R3", "HPF-V90-R8"], "calc"),
           (f"**2025: broad but small** - commercial {sh_c25}%, municipal {sh_m25}% and KeyCompostables "
            f"{sh_k25}% of the {sgn(dt25)} increase.", ["HPF-V90-R3", "HPF-V90-R2", "HPF-V90-R5"], "calc"),
           ("**Residential did not grow** - $1.97M to $1.98M, despite 2,532 new Stripe subscriptions, most "
            "of them nominal-rate government households.", ["HPF-V90-R1", "CST-V94-R4", "CST-V97-N1"], "fact"),
           ("**2026 so far** - Jan-Jul revenue +3.0% on 2025.", ["HPF-V90-YTD-revenue"], "fact"),
           ("**Market growth is not evidenced** - no third-party market growth rate; the agents' 4.01% is a "
            "North American waste-market figure.", ["MVG-1-R"], "interpretation")])},
      heads={"left_head": "Revenue by segment and the change each year (QBO, actual)",
             "right_head": "What drove growth"})

res_mo = calc("C8-res-asp-month", "a / 12", {"a": (300, "MVG-V90-R1")}, "$ per month", 2, ["S037_tam_walkdown"])
com_mo = calc("C8-com-arr-month", "a / 12", {"a": (7462, "MVG-V90-R9")}, "$ per month", 0, ["S037_tam_walkdown"])
haul_sh = calc("C4-hauling-share-sam", "(a + b) / s * 100", {"a": (149.53, "MVG-V90-R1"), "b": (200.70, "MVG-V90-R9"), "s": (sam_c, "CALC")}, "%", 1, ["S037_tam_walkdown"])
slide("S037_tam_walkdown",
      txt(f"Hauling is {haul_sh:.0f}% of the current-territory SAM; the model prices residential homes below, and "
          "businesses above, what Compost Crew actually bills", ["MVG-V90-R1", "MVG-V90-R9", "CST-V91-R3"]),
      txt("Serviceable market (SAM) by revenue line and segment, current territory, company model.",
          ["MVG-V90-R1", "MVG-V90-R9"]),
      {"chart": chart("stacked_bar", ["KeyCompostables", "Compost and soil", "Hauling"],
                      [("Residential SAM", [45.36, 23.18, 149.53]), ("Commercial SAM", [33.08, 12.01, 200.70])],
                      "$M", '"$"#,##0"M"', "$M a year, current territory",
                      [["MVG-V90-R5", "MVG-V90-R3", "MVG-V90-R1"], ["MVG-V90-R13", "MVG-V90-R11", "MVG-V90-R9"]]),
       "right": bl([
           (f"**Residential price** - the model uses $300 a year (${res_mo} a month) against $29.19 billed "
            "to the paying book.", ["MVG-V90-R1", "CST-V91-R3"], "calc"),
           (f"**Commercial price** - $7,462 ARR per business (${com_mo:,.0f} a month) against $566 actual "
            "ARPA per location.", ["MVG-V90-R9", "CST-V91-R3"], "calc"),
           ("**Unit base** - 1,661,465 single-family homes and 89,653 businesses in the current territory; "
            "the source of the counts is not stated.", ["MVG-V90-R1", "MVG-V90-R9"], "fact"),
           ("**Excluded** - municipal programmes, multi-family buildings and schools and hospitals are not "
            "modelled.", ["MVG-V90-R7", "GRO-V91-R9"], "interpretation")])},
      heads={"chart_head": "Current-territory SAM by revenue line ($M, company model)",
             "right_head": "What each line assumes"})

slide("S034_market_definitions",
      txt("The market is defined as residential and commercial collection plus products in DC, Maryland "
          "and Northern Virginia; municipal programmes sit outside it", ["MVG-V90-R7", "CBG-C6-N8"]),
      txt("Segment definitions and bases in the company's market model, with what each leaves out.", ["MVG-V90-R7"]),
      {"table": table(["Segment", "Definition", "Territory", "TAM current / expanded", "Grade"], [
          (["Residential", "Single-family homes: hauling, compost, KeyCompostables", "Current; expanded", "$726.90M / $1,090.31M", "asserted"], ["MVG-V90-R7", "MVG-V90-R8"]),
          (["Commercial", "Businesses: hauling, compost, KeyCompostables", "Current; expanded", "$819.31M / $1,196.96M", "asserted"], ["MVG-V90-R15", "MVG-V90-R16"]),
          (["Municipal", "Government programmes; only the DC contract is sized", "DC", "$20.83M at full take-up", "indicated"], ["RVQ-V96-R3"]),
          (["Not included", "Multi-family buildings, schools and hospitals, events", "-", "not sized", "-"], ["CBG-C36-N5", "GRO-V91-R9"]),
          (["Expanded territory", "NOVA to Spotsylvania County, all of Maryland, DC (CIM definition)", "-", "-", "-"], ["CBG-C6-N8"])],
          widths=[1.8, 4.4, 1.8, 2.6, 1.2]),
       "takeaway": {"type": "text", "text": (
           "Territory: DC, all of Maryland and Northern Virginia (Spotsylvania County and north). The model "
           "adds three revenue lines per segment. Municipal is sized here only from the DC contract; other "
           "municipal opportunities are not sized anywhere in the data room."),
           "refs": need("CBG-C6-N8", "CBG-C36-N5", "RVQ-V96-R3"), "kind": "interpretation"}})

alt = calc("C8-alt-participation", "p", {"p": (20, "RUN:sensitivity")}, "%", 0, ["S089_sizing_method_core"])
sens = calc("C8-som-at-20pct", "s * p / 30", {"s": (som_c, "CALC"), "p": (alt, "RUN:sensitivity")}, "$M", 2, ["S089_sizing_method_core"])
slide("S089_sizing_method_core",
      txt("Core sizing is a simple count-times-price build with two flat 30% haircuts, so every SOM figure "
          "moves one-for-one with an unsourced assumption", ["MVG-V90-R1", "MVG-V90-R9"]),
      txt("Method as built in the company's TAM, SAM and SOM workbook, hauling line.", ["MVG-V90-R1"]),
      {"flow": table(["Step", "Residential", "Commercial", "Source and grade"], [
          (["1 Count", "1,661,465 single-family homes", "89,653 businesses", "Not stated - asserted"], ["MVG-V90-R1", "MVG-V90-R9"]),
          (["2 Price", "$300 ASP a year", "$7462 ARR", "Company assumption - asserted"], ["MVG-V90-R1", "MVG-V90-R9"]),
          (["3 TAM = count x price", "$498.44M", "$668.99M", "Arithmetic - established"], ["MVG-V90-R1", "MVG-V90-R9"]),
          (["4 SAM = 30% participation", "$149.53M", "$200.70M", "Flat assumption - asserted"], ["MVG-V90-R1", "MVG-V90-R9"]),
          (["5 SOM = 30% share of SAM", "$44.86M", "$60.21M", "Flat assumption - asserted"], ["MVG-V90-R1", "MVG-V90-R9"]),
          (["6 Add compost and KeyCompostables", "see adjacent method", "see adjacent method", "-"], ["MVG-V90-R3", "MVG-V90-R11"])],
          widths=[3.0, 2.6, 2.6, 3.0]),
       "right": bl([
           (f"**Sensitivity** - at 20% participation instead of 30%, the current-territory SOM falls from "
            f"{m(som_c)} to {m(sens)}.", ["MVG-V90-R7", "MVG-V90-R15"], "calc"),
           ("**Price check** - residential ASP sits near the actual paying ARPU; commercial ARR is above "
            "actual ARPA (see previous page).", ["CST-V91-R3"], "interpretation"),
           ("**To upgrade the grade** - source household and business counts, and test participation "
            "with a customer survey.", ["RUN:analyst_view"], "interpretation")])},
      heads={"flow_head": "Core opportunity (hauling) - step by step", "right_head": "Assumptions, sources and sensitivity"})

cap_comp = calc("C9-compost-capture", "r / (a + b) * 100", {"r": (0.18, "HPF-V90-R4"), "a": (6.95, "MVG-V90-R3"), "b": (3.60, "MVG-V90-R11")}, "%", 1, ["S090_sizing_method_adjacent"])
CALCS[-1]["mixes_bases"] = "actual sales against the company's market model - a capture ratio by construction"
cap_key = calc("C9-key-capture", "r / (a + b) * 100", {"r": (0.70, "HPF-V90-R5"), "a": (13.61, "MVG-V90-R5"), "b": (9.92, "MVG-V90-R13")}, "%", 1, ["S090_sizing_method_adjacent"])
CALCS[-1]["mixes_bases"] = "actual sales against the company's market model - a capture ratio by construction"
slide("S090_sizing_method_adjacent",
      txt(f"Adjacent product lines are sized from volume and order assumptions; actual 2025 sales equal "
          f"{cap_comp}% of the compost SOM and {cap_key}% of the KeyCompostables SOM", ["MVG-V90-R3", "MVG-V90-R5", "HPF-V90-R4", "HPF-V90-R5"]),
      txt("Compost and soil amendments, and KeyCompostables, current territory, company model.", ["MVG-V90-R3", "MVG-V90-R5"]),
      {"flow": table(["Line", "Residential basis", "Commercial basis", "SOM res / com"], [
          (["Compost and soil", "0.5 cyds per home x $93 ASP (bagged)", "10 cyds per business x $45 ASP (bulk)", "$6.95M / $3.60M"], ["MVG-V90-R3", "MVG-V90-R11"]),
          (["KeyCompostables", "$84 AOV x 1.1 orders a year", "$410 AOV x 3 orders a year", "$13.61M / $9.92M"], ["MVG-V90-R5", "MVG-V90-R13"]),
          (["Actual 2025 revenue", "Compost $0.18M", "KeyCompostables $0.70M", "QBO"], ["HPF-V90-R4", "HPF-V90-R5"])],
          widths=[2.2, 3.4, 3.4, 2.2]),
       "right": bl([
           ("**Every home is assumed to buy compost** - 0.5 cubic yards a year; there is no survey of "
            "purchase incidence.", ["MVG-V90-R3"], "interpretation"),
           ("**KeyCompostables** grew from $0.31M to $0.70M in 2025; the plan takes it to $3.24M by 2030P.",
            ["HPF-V90-R5", "RVQ-V91-R6"], "fact"),
           ("**Grade: asserted** - volume and order assumptions are unsourced.", ["MVG-V90-R3"], "interpretation")])},
      heads={"flow_head": "Adjacent opportunity - step by step", "right_head": "Assumptions and evidence"})

# mix shift (actual)
ms23 = calc("C4-muni-share-2023", "a / r * 100", {"a": (1.72, "HPF-V90-R2"), "r": (7.56, "HPF-V90-R8")}, "%", 1, ["S042_gf2_mix_shift"])
cs23 = calc("C4-comm-share-2023", "a / r * 100", {"a": (4.14, "HPF-V90-R3"), "r": (7.56, "HPF-V90-R8")}, "%", 1, ["S042_gf2_mix_shift"])
cs25 = calc("C4-comm-share-2025", "a / r * 100", {"a": (5.62, "HPF-V90-R3"), "r": (13.41, "HPF-V90-R8")}, "%", 1, ["S042_gf2_mix_shift"])
slide("S042_gf2_mix_shift",
      txt(f"The mix has shifted to municipal, from {ms23:.0f}% of revenue in 2023 to {muni_share:.0f}% in 2025, "
          "concentrating the business on one contract", ["HPF-V90-R2", "HPF-V90-R8", "RVQ-V93-R7"]),
      txt("Actual revenue by segment, QBO; products and other combined.", ["HPF-V90-R8"]),
      {"chart": {**chart("stacked_column", ["2023", "2024", "2025"],
                         [("Municipal", [1.72, 4.24, 4.79]), ("Commercial", [4.14, 4.97, 5.62]),
                          ("Residential", [1.65, 1.97, 1.98]), ("Products and other", [oth23 + 0, oth24 + 0.31, oth25 + 0.70])],
                         "$M", '"$"0.0"M"', "$M, actual (QBO)",
                         [["HPF-V90-R2"] * 3, ["HPF-V90-R3"] * 3, ["HPF-V90-R1"] * 3, ["CALC"] * 3])},
       "right": bl([
           (f"**Commercial share fell** from {cs23}% to {cs25}% although commercial revenue grew every year.",
            ["HPF-V90-R3", "HPF-V90-R8"], "calc"),
           ("**DC contract** - 63.2% of municipal revenue in 2025 and 67.8% in 2026H1.", ["RVQ-V93-R7"], "fact"),
           ("**Five contracts** make up 88.1% of municipal revenue (2025).", ["RVQ-V93-R8"], "fact"),
           ("**Products** (KeyCompostables, compost) are small: $0.70M and $0.18M in 2025.",
            ["HPF-V90-R5", "HPF-V90-R4"], "fact")])},
      heads={"chart_head": "Actual revenue by segment ($M, QBO)", "right_head": "Why the mix matters"})
calc("C14-products-2023", "a + b", {"a": (oth23, "CALC"), "b": (0, "HPF-V90-R5")}, "$M", 2, ["S042_gf2_mix_shift"])
calc("C14-products-2024", "a + b", {"a": (oth24, "CALC"), "b": (0.31, "HPF-V90-R5")}, "$M", 2, ["S042_gf2_mix_shift"])
calc("C14-products-2025", "a + b", {"a": (oth25, "CALC"), "b": (0.70, "HPF-V90-R5")}, "$M", 2, ["S042_gf2_mix_shift"])
S["S042_gf2_mix_shift"]["elements"]["chart"]["series"][3]["values"] = [round(oth23, 2), round(oth24 + 0.31, 2), round(oth25 + 0.70, 2)]

dl = calc("C15-labour-increase-2025", "b - a", {"a": (3.77, "HPF-V90-R9"), "b": (4.47, "HPF-V90-R9")}, "$M", 2, ["S045_gf4_pricing_stability"])
ds = calc("C15-sga-increase-2025", "b - a", {"a": (3.27, "HPF-V90-R36"), "b": (4.23, "HPF-V90-R36")}, "$M", 2, ["S045_gf4_pricing_stability"])
gm_ttm = calc("C11-gm-ttm-jun26", "g / r * 100", {"g": (3.95, "HPF-V90-TTM-grossprofit-Jun26"), "r": (13.61, "HPF-V90-TTM-revenue-Jun26")}, "%", 1, ["S045_gf4_pricing_stability"])
slide("S045_gf4_pricing_stability",
      txt("Gross margin stepped up to about 31% with the DC contract and has held; EBITDA margin halved in "
          "2025 as labour and overheads outgrew revenue", ["HPF-V90-R22", "HPF-V90-R41", "HPF-V90-R9", "HPF-V90-R36"]),
      txt("Margins from the QBO accounts; 2026 is January to July.", ["HPF-V90-R22"]),
      {"chart": chart("line", ["2023", "2024", "2025", "2026 YTD (Jul)"],
                      [("Gross margin", [20.4, 31.8, 30.4, 31.2]), ("EBITDA margin", [-9.5, 9.6, 4.3, 5.5])],
                      "%", '0.0"%"', "% of revenue, actual (QBO)", [["HPF-V90-R22"] * 4, ["HPF-V90-R41"] * 4]),
       "right": bl([
           (f"**2025 costs** - labour +{m(dl)} and SG&A +{m(ds)} against revenue +{m(also(dt25, 'S045_gf4_pricing_stability'))}.",
            ["HPF-V90-R9", "HPF-V90-R36", "HPF-V90-R8"], "calc"),
           (f"**CIM vs accounts** - the CIM states a 28.7% TTM gross margin; QBO gives {gm_ttm}% to Jun-2026.",
            ["CBG-V98-R18", "HPF-V90-TTM-grossprofit-Jun26", "HPF-V90-TTM-revenue-Jun26"], "calc"),
           ("**Plan** - gross margin rising to 40.6% by 2030P on route density and Utica; no route-level "
            "data supports the step.", ["HPF-V91-R3", "CBG-C34-N3"], "interpretation"),
           ("**Pricing power is not shown** - price escalators are contractual in DC only; elsewhere price "
            "moves cannot be separated from mix.", ["CBG-C16-N7", "CST-V92-R3"], "interpretation")])},
      heads={"chart_head": "Gross and EBITDA margin, actual (QBO)", "right_head": "What moved the margin"})

# plan bridge
sh = {}
for k, v in [("existing", 7.0), ("dc", 10.4), ("netnew", 19.0), ("accel", 13.7)]:
    sh[k] = calc(f"C4-bridge-share-{k}", "a / t * 100", {"a": (v, "CBG-C28-T1-R1" if k == "existing" else
                                                             {"dc": "CBG-C28-T1-R2", "netnew": "CBG-C28-T1-R3", "accel": "CBG-C28-T1-R5"}[k]),
                                                       "t": (50.2, "CBG-C28-T1-R6")}, "%", 0, ["S046_sam_growth_build"])
mult = calc("C9-plan-multiple", "p / a", {"p": (50.17, "HPF-V91-R1"), "a": (13.28, "HPF-V91-R1")}, "x", 1, ["S046_sam_growth_build", "S072_growth_levers_overview"])
prod_inc = calc("C15-plan-inc-products", "(a2 - a1) + (b2 - b1) + (c2 - c1) + (d2 - d1)",
                {"a1": (0.69, "RVQ-V91-R6"), "a2": (3.24, "RVQ-V91-R6"), "b1": (0.00, "RVQ-V91-R5"), "b2": (1.64, "RVQ-V91-R5"),
                 "c1": (0.18, "RVQ-V91-R7"), "c2": (1.01, "RVQ-V91-R7"), "d1": (0.01, "RVQ-V91-R8"), "d2": (0.23, "RVQ-V91-R8")},
                "$M", 2, ["S046_sam_growth_build"])
for _nm, _a, _b, _r in [("comm", 5.62, 19.27, "RVQ-V91-R1"), ("dc", 3.00, 10.42, "RVQ-V91-R3"),
                        ("muni", 1.79, 7.76, "RVQ-V91-R2"), ("res", 1.98, 6.60, "RVQ-V91-R4")]:
    calc(f"C15-bridge-{_nm}", "b - a", {"a": (_a, _r), "b": (_b, _r)}, "$M", 2, ["S046_sam_growth_build"])
g26 = calc("C7-plan-growth-2026", "(b / a - 1) * 100", {"a": (13.28, "HPF-V91-R1"), "b": (14.30, "HPF-V91-R1")}, "%", 1, ["S046_sam_growth_build"])
slide("S046_sam_growth_build",
      txt(f"The 2030P plan of $50.2M is {mult}x 2025 revenue; the existing book and DC supply {sh['existing'] + sh['dc']:.0f}% of it, "
          "and neither is committed to 2030",
          ["HPF-V91-R1", "HPF-V90-R8", "CBG-C28-T1-R1", "CBG-C28-T1-R2"]),
      txt("Management's bridge (CIM p28) and the plan by segment; all 2026P-2030P figures are plan, not results.",
          ["CBG-C28-T1-R6", "HPF-V91-R1"]),
      {"left": table(["Component of 2030P revenue", "2030P", "Share", "What it rests on", "Grade"], [
          (["Existing ARR (non-DC), after attrition", "$7.0M", f"{sh['existing']:.0f}%", "Recurring, pay as you go; model attrition", "asserted"], ["CBG-C28-T1-R1", "CBG-C22-N5"]),
          (["DC contract", "$10.4M", f"{sh['dc']:.0f}%", "Option years + 30,000 homes (50%)", "asserted"], ["CBG-C28-T1-R2", "RVQ-V96-R1"]),
          (["Baseline net new ARR", "$19.0M", f"{sh['netnew']:.0f}%", "Sales reps 8 to 19 at flat quotas", "asserted"], ["CBG-C28-T1-R3", "CBG-C29-T1-R6"]),
          (["Growth acceleration", "+$13.7M", f"{sh['accel']:.0f}%", "New capital; reps to 23", "asserted"], ["CBG-C28-T1-R5", "CBG-C29-T1-R6"]),
          (["Total", "$50.2M", f"{calc('C4-bridge-total', 'a / t * 100', {'a': (50.2, 'CBG-C28-T1-R6'), 't': (50.2, 'CBG-C28-T1-R6')}, '%', 0, ['S046_sam_growth_build']):.0f}%", "CIM states ~30.4% CAGR 2025A-2030P", "-"], ["CBG-C28-T1-R6"])],
          widths=[3.2, 1.1, 0.9, 3.0, 1.3]),
       "right": {"type": "chart", "chart_type": "waterfall",
                 "categories": ["2025", "Commercial", "DC", "Municipal other", "Residential", "Products and Utica", "2030P"],
                 "series": [{"name": "Plan revenue bridge", "values": [13.28, 13.65, 7.42, 5.97, 4.62, prod_inc, 50.17]}],
                 "totals": [0, 6], "unit_label": "$M", "number_format": '"$"0.0"M"',
                 "value_axis_title": "$M, management plan (2025 = model actual)",
                 "refs": ["RVQ-V91-R9", "CALC:analyst"],
                 "point_refs": [["RVQ-V91-R9", "CALC:analyst", "CALC:analyst", "CALC:analyst", "CALC:analyst", "CALC:analyst", "RVQ-V91-R9"]],
                 "kind": "calc"},
       "takeaway": {"type": "text", "text": (
           f"2026P needs {g26}% growth; Jan-Jul 2026 delivered 3.0%. Growth then accelerates to 47.3% in "
           "2029P and 39.3% in 2030P, when most of the net new ARR lands. The plan is a hypothesis to "
           "test, not a base case."), "refs": need("HPF-V91-R1", "HPF-V90-YTD-revenue"), "kind": "interpretation"}},
      heads={"left_head": "Management bridge to 2030P (CIM)", "right_head": "Plan revenue bridge by segment, 2025 to 2030P ($M)"})
calc("C7-plan-growth-2029", "(b / a - 1) * 100", {"a": (24.48, "HPF-V91-R1"), "b": (36.01, "HPF-V91-R1")}, "%", 1, ["S046_sam_growth_build"])
calc("C7-plan-growth-2030", "(b / a - 1) * 100", {"a": (36.01, "HPF-V91-R1"), "b": (50.17, "HPF-V91-R1")}, "%", 1, ["S046_sam_growth_build"])
calc("C4-bridge-contracted", "a + b", {"a": (sh["existing"], "CALC"), "b": (sh["dc"], "CALC")}, "%", 0, ["S046_sam_growth_build"])

rev_home = calc("C9-dc-rev-per-home", "r * 1000000 / h", {"r": (10.42, "RVQ-V96-R1"), "h": (30000, "RVQ-V96-R1")}, "$ per home a year", 0, ["S047_scenario_analysis"])
x = {}
for k, v, rid in [("mod", 10.42, "RVQ-V96-R1"), ("up", 15.63, "RVQ-V96-R2"), ("full", 20.83, "RVQ-V96-R3")]:
    x[k] = calc(f"C9-dc-multiple-{k}", "a / b", {"a": (v, rid), "b": (3.00, "RVQ-V91-R3")}, "x", 1, ["S047_scenario_analysis"])
dc_rr = calc("C8-dc-runrate-h1x2", "h1 * 2", {"h1": (1.59, "RVQ-V93-R1")}, "$M", 2, ["S047_scenario_analysis", "S020_highlights_summary"],
              note="Municipal Account 01 = DC contract (its 2025 billing $3.08M equals 63.2% of municipal); H1 doubled, seasonality not tested")
dc_gap = calc("C10-dc-2026p-vs-runrate", "(p / r - 1) * 100", {"p": (3.96, "RVQ-V91-R3"), "r": (dc_rr, "CALC")}, "%", 0, ["S047_scenario_analysis"])
also(g25, "S047_scenario_analysis")
mom13 = calc("C7-momentum-2025-rate", "a * (1 + g / 100) ** 5", {"a": (13.28, "HPF-V91-R1"), "g": (13.0, "CALC")}, "$M", 2, ["S047_scenario_analysis", "S020_highlights_summary"],
             note="cross-check, not a forecast: 2025 growth rate (QBO, 13.0%) held for five years on the model's 2025 base")
calc("C7-growth-2025-model-basis", "(b / a - 1) * 100", {"a": (11.74, "HPF-V91-R1"), "b": (13.28, "HPF-V91-R1")}, "%", 1, ["S047_scenario_analysis"])
mom3 = calc("C7-momentum-ytd-rate", "a * (1 + g / 100) ** 5", {"a": (13.28, "HPF-V91-R1"), "g": (3.0, "HPF-V90-YTD-revenue")}, "$M", 2, ["S047_scenario_analysis", "S020_highlights_summary"],
            note="cross-check: Jan-Jul 2026 growth (+3.0%) held for five years")
CALCS[-1]["mixes_bases"] = "ledger growth rate applied to the model's 2025 base so the result compares with the plan"
flat_dc = calc("C15-plan-ex-dc-growth", "t - (a - b)", {"t": (50.17, "HPF-V91-R1"), "a": (10.42, "RVQ-V91-R3"), "b": (3.96, "RVQ-V91-R3")}, "$M", 2, ["S047_scenario_analysis"])
slide("S047_scenario_analysis",
      txt(f"Recent trading points to ${mom3:.0f}M-${mom13:.0f}M of 2030 revenue against a $50.2M plan; DC billings run at "
          f"about ${dc_rr:.1f}M a year today, not the $4.0M the plan books for 2026",
          ["HPF-V91-R1", "RVQ-V93-R1", "RVQ-V91-R3", "HPF-V90-YTD-revenue"]),
      txt("Momentum rows are arithmetic cross-checks, not forecasts. All on the model's revenue basis; DC at contract prices.",
          ["HPF-V91-R1"]),
      {"table": table(["Case", "Basis", "Revenue", "Comparison", "Grade"], [
          (["Management plan, 2030P", "Model, 30.4% CAGR", "$50.17M", "-", "asserted"], ["HPF-V91-R1"]),
          (["Momentum to 2030 at 2025 growth (13.0%)", "Model 2025 base, 5 years", m(mom13), f"{mom13 / 50.17 * 100:.0f}% of plan", "calc"], ["HPF-V91-R1", "HPF-V90-R8", "CALC"]),
          (["Momentum to 2030 at Jan-Jul 2026 growth (3.0%)", "Model 2025 base, 5 years", m(mom3), f"{mom3 / 50.17 * 100:.0f}% of plan", "calc"], ["HPF-V91-R1", "HPF-V90-YTD-revenue", "CALC"]),
          (["2030P plan with DC held at its 2026P level", "Plan less DC growth", m(flat_dc), "-", "calc"], ["HPF-V91-R1", "RVQ-V91-R3", "CALC"]),
          (["DC today: 2026H1 billings x 2", "Account 01, 12,000 homes", f"{m(dc_rr)} a year", f"2026P needs +{dc_gap:.0f}%", "indicated"], ["RVQ-V93-R1", "CBG-C16-N8", "RVQ-V91-R3", "CALC"]),
          (["DC 2030P modelled, 50% of 60,000 homes", "Option years exercised", "$10.42M", "in plan", "asserted"], ["RVQ-V96-R1"]),
          (["DC 2030P upside, 75%", "Option years exercised", "$15.63M", "+$5.21M", "asserted"], ["RVQ-V96-R2", "CALC"]),
          (["DC 2030P full contract, 100%", "Option years exercised", "$20.83M", "+$10.41M", "asserted"], ["RVQ-V96-R3", "CALC"])],
          widths=[3.6, 3.0, 1.8, 2.0, 1.2]),
       "takeaway": {"type": "text", "text": (
           "Only the first contract year is firm; every DC row beyond today assumes the option years are exercised. "
           "The v3 run-rate estimate, which multiplied today's homes by 2030 prices, is withdrawn."),
           "refs": need("CBG-C16-N7", "RVQ-V93-R1"), "kind": "interpretation"}})
calc("C15-dc-upside-inc", "b - a", {"a": (10.42, "RVQ-V96-R1"), "b": (15.63, "RVQ-V96-R2")}, "$M", 2, ["S047_scenario_analysis"])
calc("C15-dc-full-inc", "b - a", {"a": (10.42, "RVQ-V96-R1"), "b": (20.83, "RVQ-V96-R3")}, "$M", 2, ["S047_scenario_analysis"])
calc("C9-mom13-share", "a / p * 100", {"a": (mom13, "CALC"), "p": (50.17, "HPF-V91-R1")}, "%", 0, ["S047_scenario_analysis"])
calc("C9-mom3-share", "a / p * 100", {"a": (mom3, "CALC"), "p": (50.17, "HPF-V91-R1")}, "%", 0, ["S047_scenario_analysis"])
calc("C8-dc-2026p-rounded", "a", {"a": (3.96, "RVQ-V91-R3")}, "$M", 1, ["S047_scenario_analysis"])
calc("C8-dc-runrate-1dp", "a", {"a": (dc_rr, "CALC")}, "$M", 1, ["S047_scenario_analysis"])
calc("C8-mom-round-hi", "a", {"a": (mom13, "CALC")}, "$M", 0, ["S047_scenario_analysis"])
calc("C8-mom-round-lo", "a", {"a": (mom3, "CALC")}, "$M", 0, ["S047_scenario_analysis"])
acct01 = calc("C4-acct01-share", "a / r * 100", {"a": (3.08, "RVQ-V93-R1"), "r": (13.28, "HPF-V91-R1")}, "%", 1, ["S049_risk_assessment"])
calc("C9-dc-homes-multiple", "a / b", {"a": (30000, "RVQ-V96-R1"), "b": (12000, "CBG-C16-N8")}, "x", 1, ["S072_growth_levers_overview"])
risks = [
    ("Plan execution", "2030P needs 30.4% CAGR; Jan-Jul 2026 grew 3.0%", 5, 4, ["HPF-V91-R1", "HPF-V90-YTD-revenue"]),
    ("DC contract concentration", f"Account 01 (DC): $3.08M, {acct01}% of 2025 revenue (model)", 5, 3, ["RVQ-V93-R1", "HPF-V91-R1"]),
    ("DC contract durability", "One firm year plus four option years; contract not reviewed", 5, 3, ["CBG-C16-N7"]),
    ("Commercial acquisition", "New logos 171 (2024) to 81 (2025); accounts 663 to 591 (H1)", 4, 3, ["CST-V92-R4", "CST-V92-R1"]),
    ("Thin earnings", "EBITDA 4.3% (2025); Jan-Jul 2026 EBITDA -12.9%", 4, 3, ["HPF-V90-R41", "HPF-V90-YTD-EBITDA"]),
    ("Municipal pipeline", "Top-5 contracts 88.1% of municipal revenue", 3, 3, ["RVQ-V93-R8"]),
    ("Residential churn", "Subscriber retention 84.8% (2025) vs 86.1% plan", 3, 3, ["CST-V94-R9", "CBG-V98-R23"]),
    ("Utica delivery", "Go-live 4Q27 after road widening and grading permit", 3, 3, ["CBG-C50-N3"]),
    ("Reporting quality", "Duplicate top-20 account; 2,071 government homes in the Stripe count", 2, 3, ["RVQ-V94-DQ1", "CST-V97-R2"]),
]
rows = []
for i, (nm, ev, imp, lik, refs) in enumerate(risks, 1):
    sc = calc(f"C6-risk-{i}", "i * l", {"i": (imp, "RUN:risk_scoring"), "l": (lik, "RUN:risk_scoring")}, "score", 0, ["S049_risk_assessment"])
    rows.append(([nm, ev, str(imp), str(lik), str(int(sc))], refs + ["RUN:risk_scoring"]))
slide("S049_risk_assessment",
      txt("The largest risks are the plan itself and reliance on one DC contract; both are measurable "
          "before signing", ["HPF-V91-R1", "RVQ-V93-R1"]),
      txt("Impact and likelihood scored 1-5 by the analyst from the evidence cited; score = impact x likelihood.",
          ["RUN:risk_scoring"]),
      {"left": table(["Risk", "Evidence", "Impact", "Likelihood", "Score"], rows,
                     widths=[2.2, 5.0, 0.9, 1.1, 0.9], pills=[{"col": 4, "scale": "bad_high"}]),
       "right": bl([
           ("**Plan** - rebuild 2026P-2027P from the Jul-2026 run-rate and the signed pipeline before "
            "relying on 2030P.", ["HPF-V90-YTD-revenue", "HPF-V91-R1"], "interpretation"),
           ("**DC** - obtain the contract, participation caps by year and the option-year terms.",
            ["CBG-C16-N7"], "interpretation"),
           ("**Commercial** - request 2025-2026 sales capacity and win rates to explain the fall in new logos.",
            ["CST-V92-R4"], "interpretation"),
           ("**Reporting** - reconcile QBO revenue ($13.41M) to the model ($13.28M) and clean the "
            "concentration schedule.", ["HPF-V90-R8", "HPF-V91-R1", "RVQ-V94-DQ1"], "interpretation")])},
      heads={"left_head": "Risk register - impact x likelihood", "right_head": "What to test before signing"})

# =========================================================================== 4. competition
slide("S060_competitor_archetypes",
      txt("Compost Crew competes with a handful of local composters, one of which also owns processing sites, "
          "rather than with the national haulers the agents highlight", ["WEB-CID-01", "WEB-CID-02", "CBG-C53-T1-R1"]),
      txt("Named competitors from web research (Sep-2026) and archetypes from the CIM; the agent list is "
          "not used (see note).", ["WEB-CID-05", "CID-1-R"]),
      {"table": table(["Competitor", "Type", "Footprint", "Segments", "Processing", "Source"], [
          (["Compost Cab", "Local composter", "DC and Baltimore regions", "Residential, multi-unit, commercial", "Partner farms and facilities", "web"], ["WEB-CID-01"]),
          (["Veteran Compost", "Local composter", "DC metro; Baltimore / Annapolis", "Residential, commercial, events", "Own sites, Aberdeen MD and Alexandria VA", "web"], ["WEB-CID-02"]),
          (["Monster Organics", "Commercial organics hauler", "DC, MD, VA and NC", "Commercial and industrial", "Not disclosed", "web"], ["WEB-CID-03"]),
          (["Pluvr", "Commercial collector", "Washington DC", "Restaurants", "Not disclosed", "web"], ["WEB-CID-04"]),
          (["Major waste companies", "National haulers", "National", "Municipal solid waste", "Landfill and transfer", "CIM"], ["CBG-C53-T1-R1", "CBG-C44-T1-R1"]),
          (["Brokers, technology and soil firms", "Adjacent archetypes", "-", "Varies", "-", "CIM"], ["CBG-C53-T1-R2"]),
          (["Not competitors (agent list)", "KeyCompostables, Agricity, Fat Worm, ECO City Farms", "-", "Own brand, subcontractor, acquired, host", "-", "corrected"], ["CID-1-R", "CBG-C31-N1", "CBG-C30-T1-R1"])],
          widths=[2.2, 2.2, 2.2, 2.4, 2.4, 1.0]),
       "takeaway": {"type": "text", "text": (
           "Competition is local and fragmented. No market shares are available for any player, so the "
           "position is described, not ranked. Grade: indicated (public websites, dated Sep-2026)."),
           "refs": need("WEB-CID-05", "WEB-CID-01"), "kind": "interpretation"}})

slide("S062_criteria_vs_archetypes",
      txt("Management's own comparison ticks every criterion for Compost Crew and against most rivals; it "
          "is a self-assessment and is shown as such", ["CBG-C53-T1-R1"]),
      txt("CIM p53 as presented; soil manufacturers omitted for space. Not validated by customers.", ["CBG-C53-T1-R1"]),
      {"table": table(["Criterion (CIM)", "Compost Crew", "Major waste", "Local composters", "Brokers", "Tech providers"], [
          (["Composting is the core business", "yes", "no", "yes", "no", "no"], ["CBG-C53-T1-R1"]),
          (["Innovation in collection and processing", "yes", "no", "no", "yes", "yes"], ["CBG-C53-T1-R2"]),
          (["Flexible, locally tailored service", "yes", "no", "yes", "yes", "-"], ["CBG-C53-T1-R3"]),
          (["Technology-enabled operations", "yes", "yes", "no", "yes", "yes"], ["CBG-C53-T1-R4"]),
          (["Vertically integrated model", "yes", "yes", "no", "no", "no"], ["CBG-C53-T1-R5"]),
          (["Clear regional growth strategy", "yes", "yes", "yes", "no", "yes"], ["CBG-C53-T1-R6"]),
          (["Trained program managers", "yes", "no", "no", "no", "no"], ["CBG-C53-T1-R7"]),
          (["Financial strength and scalability", "yes", "yes", "no", "no", "yes"], ["CBG-C53-T1-R8"])],
          widths=[3.6, 1.6, 1.6, 1.8, 1.4, 1.6]),
       "takeaway": {"type": "text", "text": (
           "Two ticks are contradicted by the evidence: Veteran Compost, a local composter, runs its own "
           "processing sites, and 'financial strength' sits oddly with 2025 net income of -$0.56M. Grade: "
           "asserted."), "refs": need("WEB-CID-02", "HPF-V90-R39", "CBG-C53-T1-R5", "CBG-C53-T1-R8"),
           "kind": "interpretation"}})

gap_cab = calc("C10-arpu-vs-compost-cab", "(a / b - 1) * 100", {"a": (29.19, "CST-V91-R3"), "b": (32, "WEB-CID-01")}, "%", 0, ["S064_price_benchmarking"])
slide("S064_price_benchmarking",
      txt(f"Residential pricing sits close to the one published local price: the paying book averages $29.19 "
          f"a month, {abs(gap_cab):.0f}% below Compost Cab's $32 list price", ["CST-V91-R3", "WEB-CID-01"]),
      txt("Residential dollars per month; list price vs realised ARPU, so not like for like.",
          ["WEB-CID-01", "CST-V91-R3"]),
      {"chart": chart("bar", ["Plan AAOV (CIM)", "Compost Crew Stripe blended ARPU", "Compost Crew paying book ARPU", "Compost Cab list price (web)"],
                      [("Residential $ per month", [21.31, 21.46, 29.19, 32])],
                      "$ per month", '"$"0.00', "$ per month",
                      [["CBG-V98-R25", "CST-V94-R6", "CST-V91-R3", "WEB-CID-01"]], highlight=2),
       "right": bl([
           ("**Blended ARPU is diluted** - 2,071 government-programme homes billed at $1.94 a month sit in "
            "the Stripe count; excluding them gives $29.19.", ["CST-V97-R2", "CST-V97-R3"], "fact"),
           ("**The plan prices below today** - residential AAOV of $21.31 a month, held flat.",
            ["CBG-V98-R25", "CBG-C29-T1-R9"], "fact"),
           ("**Commercial is not comparable** - Compost Cab quotes 'from $90 per month'; Compost Crew's "
            "average is $566 a location.", ["WEB-CID-01", "CST-V91-R3"], "fact"),
           ("**Competitive pricing is indicated, not established** - one published competitor price, and "
            "no win-loss or price-sensitivity data.", ["WEB-CID-01", "WEB-CID-02"], "interpretation")])},
      heads={"chart_head": "Residential price benchmark ($ per month)", "right_head": "Where the target sits and why"})

slide("S029_h4_differentiation",
      txt("Of the CIM's claimed differentiators, only retention and scale have data-room figures behind them; "
          "service quality, NPS and integration are management's word", ["CBG-C12-T1-R1", "CST-V91-R7"]),
      txt("Each claim set against what the data room shows; grade per the claim rules.", ["CBG-C12-T1-R1"]),
      {"table": table(["Claim (CIM)", "What the data room shows", "Grade"], [
          (["98-99% monthly customer retention", "99.3% / 98.6% monthly = 92.4% / 84.8% a year (2025)", "established"], ["CBG-C12-T1-R1", "CST-V91-R7", "CST-V91-R8"]),
          (["25,000+ active locations", "25,546 = 19,195 homes + 856 sites + 5,495 subscribers (mixed units)", "indicated"], ["CBG-C3-N2", "CST-V91-R1"]),
          (["Contracted, multi-year municipal revenue", f"Municipal {muni_share}% of 2025 revenue; DC: 1 firm + 4 option years, unreviewed", "indicated"], ["CBG-C16-N1", "HPF-V90-R2", "CBG-C16-N7"]),
          (["Serve 20 municipal partners", "Five contracts are 88.1% of municipal revenue", "established"], ["CBG-C12-T1-R1", "RVQ-V93-R8"]),
          (["Vertically integrated", "6 outposts; Utica not live; $1.18M subcontracted (2025)", "indicated"], ["CBG-C10-N3", "CBG-C50-N1", "HPF-V90-R18"]),
          (["99.5%+ on-time service", "No service log in the data room", "asserted"], ["CBG-C12-T1-R1", "CBG-V98-R54"]),
          (["70+ NPS", "Company survey not in the data room", "asserted"], ["CBG-C12-T1-R1", "CBG-V98-R55"])],
          widths=[3.6, 6.4, 1.6]),
       "takeaway": {"type": "text", "text": (
           "The data room supports a reliable, recurring collection business with a concentrated municipal "
           "book. It does not support a claim of superior service or brand; that would need customer "
           "research."), "refs": need("CST-V91-R7", "RVQ-V93-R8"), "kind": "interpretation"}})

# =========================================================================== 5. customers / retention
slide("S068_churn_triggers",
      txt("Commercial accounts renew at about 92% a year with net expansion; residential churns faster; the "
          "model's higher retention is on a different (location) basis", ["CST-V92-R7", "CST-V92-R10", "CST-V94-R9", "CST-V91-R5"]),
      txt("Actual retention from the investor workbook (commercial accounts, Stripe residential book); plan "
          "values labelled.", ["CST-V92-R7", "CST-V94-R9"]),
      {"left": table(["Measure", "2023", "2024", "2025", "Latest", "Plan / model"], [
          (["Commercial logo retention", "92.2%", "92.9%", "92.4%", "-", "91.5% (CIM)"], ["CST-V92-R7", "CBG-V98-R22"]),
          (["Commercial GRR", "85.6%", "79.8%", "87.3%", "-", "90.9% (model)"], ["CST-V92-R9", "CST-V91-R6"]),
          (["Commercial NRR", "124.5%", "102.4%", "106.6%", "-", "-"], ["CST-V92-R10"]),
          (["2021 commercial cohort, logos left", "89.6%", "83.1%", "75.4%", "66.9% (2026H1)", "-"], ["CST-V93-R1"]),
          (["Residential subscriber retention", "51.1%", "86.0%", "84.8%", "87.8% (2026H1)", "86.1% (CIM)"], ["CST-V94-R9", "CBG-V98-R23"]),
          (["Residential GRR", "50.8%", "85.2%", "84.6%", "90.2% (2026H1)", "88.2% (model)"], ["CST-V94-R7", "CST-V91-R6"]),
          (["Annual retention, model (per location)", "-", "-", "-", "-", "96.3% com / 93.8% res"], ["CST-V91-R5"]),
          (["Municipal", "not tracked by cohort", "-", "-", "-", "97.2% (model driver)"], ["CBG-V98-R24"])],
          widths=[3.2, 1.3, 1.3, 1.3, 1.7, 2.2]),
       "right": bl([
           ("**Commercial** - NRR of 106.6% with GRR of 87.3%: expansion more than offsets a 7.6% logo churn.",
            ["CST-V92-R10", "CST-V92-R9", "CST-V92-R8"], "fact"),
           ("**Residential is not one population** - from Jun-2025 Stripe includes 2,071 programme homes; "
            "2025 and 2026 retention mix them in.", ["CST-V97-R2", "CST-V97-N4", "CST-V94-R9"], "fact"),
           ("**Tenure** - 81.2% of residential subscribers remain at 12 months and 51.5% at 60 months.",
            ["CST-V95-R4", "CST-V95-R10"], "fact"),
           ("**Model vs actual, basis differs** - the ARR model's 96.3% / 93.8% is per location; 92.4% / 84.8% "
            "is per account and per Stripe subscription.", ["CST-V91-R5", "CST-V91-R8"], "fact"),
           ("**Churn triggers are unknown** - no exit reasons or customer research in the data room.",
            ["CST-V94-R5"], "interpretation")])},
      heads={"left_head": "Retention by segment: actual vs plan", "right_head": "What it means"})

slide("S079_l3_expand_accounts",
      txt("Commercial accounts expand: net revenue retention has exceeded gross retention every year, "
          "normalising from 196% (2022) to 107% (2025)", ["CST-V92-R10", "CST-V92-R9"]),
      txt("Commercial cohort revenue retention, investor workbook; 2022 reflects a small base of 260 accounts.",
          ["CST-V92-R10", "CST-V92-R1"]),
      {"chart": chart("column", ["2022", "2023", "2024", "2025"],
                      [("NRR", [196.0, 124.5, 102.4, 106.6]), ("GRR", [98.1, 85.6, 79.8, 87.3])],
                      "%", '0.0"%"', "% of prior-year cohort revenue", [["CST-V92-R10"] * 4, ["CST-V92-R9"] * 4]),
       "right": bl([
           ("**Spend per account rose** - ARPA $273 a month (2021) to $706 (2025).", ["CST-V92-R3"], "fact"),
           ("**Less concentrated** - top-10 accounts fell from 35.3% (2022) to 22.6% (2025) of commercial revenue.",
            ["CST-V92-R11"], "fact"),
           ("**Plan upsell engine** - the plan assumes 52 upsells a year at $1,885 (AAOV +3.0%); no upsell "
            "history tests it.", ["CBG-C29-T1-R17"], "fact"),
           ("**Grade: indicated** - company-prepared history, not tested to billing; the plan's expansion rate is asserted.", ["CST-V92-R10"], "interpretation")])},
      heads={"chart_head": "Commercial net and gross revenue retention (%)", "right_head": "Expansion evidence"})

net = [calc(f"C15-net-adds-{y}", "a - b", {"a": (a_, "CST-V92-R4"), "b": (b_, "CST-V92-R5")}, "count", 0, ["S073_l1_new_customers"])
       for y, a_, b_ in [(2022, 142, 3), (2023, 126, 31), (2024, 171, 35), (2025, 81, 48)]]
reps_eq = calc("C9-logos-in-rep-quotas", "a / q", {"a": (81, "CST-V92-R4"), "q": (52, "CBG-C29-T1-R7")}, "reps", 1, ["S073_l1_new_customers", "S075_l1_channel_expansion"])
slide("S073_l1_new_customers",
      txt(f"New commercial logos halved to 81 in 2025 while churn rose to 48, cutting net additions to "
          f"{int(net[3])}; the plan needs the sales engine to multiply", ["CST-V92-R4", "CST-V92-R5"]),
      txt("Commercial new and churned logos, investor workbook.", ["CST-V92-R4"]),
      {"chart": chart("column", ["2022", "2023", "2024", "2025"],
                      [("New logos", [142, 126, 171, 81]), ("Churned logos", [3, 31, 35, 48])],
                      "accounts", "#,##0", "Commercial accounts", [["CST-V92-R4"] * 4, ["CST-V92-R5"] * 4]),
       "right": bl([
           (f"**Net additions** - {int(net[0])}, {int(net[1])}, {int(net[2])} and {int(net[3])} accounts, "
            "2022-2025.", ["CST-V92-R4", "CST-V92-R5"], "calc"),
           ("**Active accounts fell** from 663 (2025) to 591 at 2026H1.", ["CST-V92-R1"], "fact"),
           (f"**Plan quota** - 52 new accounts a year per commercial rep at $7,000 AAOV; 2025's 81 logos "
            f"equal {reps_eq} reps' quota.", ["CBG-C29-T1-R7", "CST-V92-R4"], "calc"),
           ("**Unexplained** - no sales-capacity or win-rate history explains the 2025 fall; this is a "
            "priority data request.", ["CST-V92-R4"], "interpretation")])},
      heads={"chart_head": "Commercial new vs churned logos", "right_head": "Assumptions behind the plan"})

# =========================================================================== 6. growth
segs = [("Commercial", "RVQ-V91-R1", 5.62, 19.27, "New logos recover; NRR stays above 100%", "asserted"),
        ("Municipal - DC", "RVQ-V91-R3", 3.00, 10.42, "Option years exercised; 30,000 homes, 2.5x today", "asserted"),
        ("Municipal - other", "RVQ-V91-R2", 1.79, 7.76, "New contracts; none named in the data room", "asserted"),
        ("Residential", "RVQ-V91-R4", 1.98, 6.60, "Flat to 2028P, then 3.2x by 2030P", "asserted"),
        ("KeyCompostables", "RVQ-V91-R6", 0.69, 3.24, "Online sales keep compounding", "asserted"),
        ("Utica", "RVQ-V91-R5", 0.00, 1.64, "Facility live 4Q27; tipping fees", "indicated"),
        ("Compost and products", "RVQ-V91-R7", 0.18, 1.01, "Utica output sold", "asserted"),
        ("Other", "RVQ-V91-R8", 0.01, 0.23, "-", "-")]
tot_inc = calc("C15-plan-increment", "b - a", {"a": (13.28, "RVQ-V91-R9"), "b": (50.17, "RVQ-V91-R9")}, "$M", 2, ["S072_growth_levers_overview"])
rows = []
XREF = {"Municipal - DC": ["RVQ-V96-R1"], "Residential": [], "Utica": ["CBG-C50-N1"]}
for i, (nm, rid, a_, b_, cond, gr) in enumerate(segs, 1):
    inc = calc(f"C15-inc-lever{i}", "b - a", {"a": (a_, rid), "b": (b_, rid)}, "$M", 2, ["S072_growth_levers_overview"])
    share = calc(f"C4-incshare-lever{i}", "i / t * 100", {"i": (inc, "CALC"), "t": (tot_inc, "CALC")}, "%", 0, ["S072_growth_levers_overview"])
    rows.append(([nm, m(a_), m(b_), f"+{m(inc)} ({share:.0f}%)", cond, gr], [rid, "CALC"] + XREF.get(nm, [])))
rows.append((["Total", "$13.28M", "$50.17M", f"+{m(tot_inc)} (100%)", "30.4% CAGR 2025-2030P", "-"], ["RVQ-V91-R9", "HPF-V91-R1"]))
calc("C7-res-2028-30", "b / a", {"a": (2.09, "RVQ-V91-R4"), "b": (6.60, "RVQ-V91-R4")}, "x", 1, ["S072_growth_levers_overview"])
slide("S072_growth_levers_overview",
      txt("Commercial and DC deliver more than half of the plan's $36.9M of growth; none of the levers is "
          "committed, and only DC and Utica have a contract or permit behind them", ["RVQ-V91-R1", "RVQ-V91-R3", "RVQ-V91-R9"]),
      txt("Plan revenue by segment, 2025 (model actual) to 2030P, investor workbook; grades per lever.",
          ["RVQ-V91-R9"]),
      {"rows": table(["Lever", "2025", "2030P", "Increment (share)", "What must be true", "Grade"], rows,
                     widths=[2.0, 1.2, 1.2, 2.0, 4.0, 1.2])})

slide("S075_l1_channel_expansion",
      txt("The plan more than doubles the sales team and holds quotas flat; the data room has no sales "
          "productivity history to show today's reps achieve those quotas", ["CBG-C29-T1-R6", "CBG-C25-N2"]),
      txt("Go-to-market drivers in the baseline plan and the growth-capital case, CIM p29.", ["CBG-C29-T1-R6"]),
      {"left": table(["Driver", "Baseline plan", "With growth capital", "Grade"], [
          (["Quota-carrying sales reps, 2026 to 2030", "8 to 19", "9 to 23", "asserted"], ["CBG-C29-T1-R6"]),
          (["Commercial AE quota", "52 accounts a year x $7,000 AAOV", "+3.5% quota, +4.0% AAOV", "asserted"], ["CBG-C29-T1-R7"]),
          (["Municipal AE quota", "1,200 homes a year x $20 a month", "+3.5% quota, +3.0% price", "asserted"], ["CBG-C29-T1-R8"]),
          (["Residential AE quota", "2,700 homes a year x $21.31 a month", "+3.5% quota, +2.0% AAOV", "asserted"], ["CBG-C29-T1-R9"]),
          (["New-rep ramp", "5 months to 90% of quota", "100% of quota", "asserted"], ["CBG-C29-T1-R10"]),
          (["Account managers, 2030", "11 (5 commercial, 6 residential)", "11", "asserted"], ["CBG-C29-T1-R16"]),
          (["Marketing spend", "+15% in 2027, flat after", "+25% in 2027, +30% a year after", "asserted"], ["CBG-C29-T1-R11"])],
          widths=[3.4, 3.0, 2.8, 1.4]),
       "right": bl([
           ("**Management's own view** - the current GTM organisation lacks scale to drive growth acceleration.",
            ["CBG-C55-N1"], "fact"),
           (f"**Reality check** - 81 new commercial logos in 2025 equal {reps_eq} reps' annual quota.",
            ["CST-V92-R4", "CBG-C29-T1-R7"], "calc"),
           ("**Request** - rep-level bookings, ramp and attrition for 2024-2026 before accepting the quotas.",
            ["CBG-C29-T1-R6"], "interpretation")])},
      heads={"left_head": "Sales capacity and quotas in the plan", "right_head": "Build, hire and evidence"})

aup = calc("C10-arpa-change-2025", "(b / a - 1) * 100", {"a": (647, "CST-V92-R3"), "b": (706, "CST-V92-R3")}, "%", 1, ["S080_l4_pricing"])
slide("S080_l4_pricing",
      txt("Only the DC price escalator is written into a contract, per the CIM; elsewhere the plan's uplifts "
          "cannot yet be separated from mix", ["CBG-V98-R51", "CBG-C29-T1-R7", "CST-V92-R3"]),
      txt("Pricing assumptions in the plan and the evidence available for each.", ["CBG-C29-T1-R8"]),
      {"left": table(["Price lever", "Plan assumption", "Evidence", "Grade"], [
          (["DC contract", "Escalator ~2.6% a year", "Contract cited in the CIM tie-out; not read", "indicated"], ["CBG-V98-R51", "CBG-C16-N7"]),
          (["Municipal (other)", "+2.5% price a year", "No contract terms in the data room", "asserted"], ["CBG-C29-T1-R8"]),
          (["Commercial", "AAOV +3.0% from 2028", f"ARPA $647 to $706 in 2025 (+{aup}%), mix unknown", "indicated"], ["CBG-C29-T1-R7", "CBG-C22-N3", "CST-V92-R3"]),
          (["Residential", "AAOV $21.31 a month, flat", "Paying ARPU $29.19; Compost Cab lists $32", "indicated"], ["CBG-C29-T1-R9", "CST-V91-R3", "WEB-CID-01"])],
          widths=[2.0, 2.6, 4.6, 1.4]),
       "right": bl([
           ("**No list prices** - Compost Crew does not publish prices; residential and commercial service "
            "is pay as you go.", ["WEB-CID-06"], "fact"),
           ("**Headroom is plausible in residential** - the paying book is below the one published local "
            "price, but one data point is not a benchmark.", ["CST-V91-R3", "WEB-CID-01"], "interpretation"),
           ("**Request** - price-increase history by segment and churn after each increase.", ["CST-V92-R3"], "interpretation")])},
      heads={"left_head": "Pricing lever, assumption and evidence", "right_head": "Evidence of headroom"})

slide("S081_l5_adjacent_segments",
      txt("Geographic expansion is prioritised by a company ZIP-scoring model led by Arlington and "
          "Montgomery County; revenue potential per ZIP was not modelled", ["GRO-V92-R1", "GRO-V90-R1"]),
      txt("Top-scoring ZIPs from the company's MD and NOVA expansion analysis (scores 0-10).", ["GRO-V90-R1", "GRO-V92-R1"]),
      {"table": table(["Territory", "Area", "County", "ZIP", "Score"], [
          (["NOVA", "Arlington", "Arlington", "22201", "6.18"], ["GRO-V92-R1"]),
          (["MD", "Rockville", "Montgomery", "20852", "5.88"], ["GRO-V90-R1"]),
          (["MD", "Rockville", "Montgomery", "20850", "5.81"], ["GRO-V90-R2"]),
          (["NOVA", "Fairfax", "Fairfax City", "22030", "5.52"], ["GRO-V92-R2"]),
          (["MD", "Bethesda", "Montgomery", "20814", "5.48"], ["GRO-V90-R3"]),
          (["MD", "Silver Spring", "Montgomery", "20910", "5.27"], ["GRO-V90-R4"]),
          (["NOVA", "Arlington", "Arlington", "22203", "5.10"], ["GRO-V92-R3"]),
          (["MD", "Annapolis", "Anne Arundel", "21401", "5.05"], ["GRO-V90-R5"]),
          (["NOVA", "Arlington", "Arlington", "22209", "5.01"], ["GRO-V92-R4"])],
          widths=[1.6, 2.6, 2.6, 1.6, 1.4]),
       "takeaway": {"type": "text", "text": (
           "Scores weight residential factors 60% and business factors 40% (households, density, income; "
           "ICP business counts, payroll). They rank where to go, not what it is worth; the expanded-"
           "territory SOM is the only value attached. Grade: asserted."),
           "refs": need("GRO-V91-R16", "GRO-V91-R17", "GRO-V91-R2", "GRO-V91-R10", "MVG-V90-R8"), "kind": "interpretation"}},
      heads={})

key_cagr = calc("C7-key-cagr-plan", "((b / a) ** 0.2 - 1) * 100", {"a": (0.69, "RVQ-V91-R6"), "b": (3.24, "RVQ-V91-R6")}, "%", 1, ["S082_l6_product_expansion"])
slide("S082_l6_product_expansion",
      txt("Utica and KeyCompostables are real but early: together they are 5.2% of 2025 revenue and 9.7% "
          "of the 2030P plan", ["RVQ-V91-R6", "RVQ-V91-R5", "RVQ-V91-R9"]),
      txt("Product and capacity initiatives: status, 2025 actual (model basis) and 2030P plan.", ["RVQ-V91-R6"]),
      {"left": table(["Initiative", "Status", "2025", "2030P", "Depends on", "Grade"], [
          (["Utica compost facility", "Permitted 20k tons a year; partly operational", "$0.00M", "$1.64M", "Road widening, grading permit, 4Q27", "indicated"], ["CBG-C50-N1", "CBG-C50-N3", "RVQ-V91-R5"]),
          (["KeyCompostables", "Acquired with Key City, 2024", "$0.69M", "$3.24M", f"{key_cagr}% a year growth", "asserted"], ["CBG-C30-T1-R3", "RVQ-V91-R6"]),
          (["Compost and products", "Compost Dividend; bagged sales", "$0.18M", "$1.01M", "Utica output", "asserted"], ["RVQ-V91-R7", "CBG-C47-N2"]),
          (["Compost Outposts", "6 active modular sites (per CIM)", "-", "-", "Municipal adoption", "asserted"], ["CBG-C10-N3", "CBG-C48-N4"])],
          widths=[2.2, 3.0, 1.0, 1.0, 2.6, 1.2]),
       "right": bl([
           ("**Utica funding** - per the CIM, a USDA $2.68 million grant; go-live planned 4Q27 after road "
            "widening (3Q26) and grading permit (2Q27).", ["CBG-C50-N1", "CBG-C50-N3"], "fact"),
           ("**Utica economics** - management expects gross self-tipping savings (2025 transfer and disposal "
            "cost: $0.99M) and tipping fees; no facility P&L or capex budget.", ["CBG-C50-N2", "HPF-V90-R10"], "interpretation"),
           ("**KeyCompostables** more than doubled in 2025 ($0.31M to $0.70M, QBO).", ["HPF-V90-R5"], "fact")])},
      heads={"left_head": "Initiative, status and plan", "right_head": "Build effort and sequencing"})
calc("C4-products-share-2025", "(a + b) / t * 100", {"a": (0.69, "RVQ-V91-R6"), "b": (0.00, "RVQ-V91-R5"), "t": (13.28, "RVQ-V91-R9")}, "%", 1, ["S082_l6_product_expansion"])
calc("C4-products-share-2030", "(a + b) / t * 100", {"a": (3.24, "RVQ-V91-R6"), "b": (1.64, "RVQ-V91-R5"), "t": (50.17, "RVQ-V91-R9")}, "%", 1, ["S082_l6_product_expansion"])

agri_e = calc("C9-agricity-ebitda", "p / x", {"p": (3.0, "CBG-C31-N2"), "x": (5.1, "CBG-C31-N2")}, "$M", 2, ["S083_l7_ma"])
syn_gap = calc("C15-agricity-synergy-residual", "t - e", {"t": (1.5, "CBG-C31-N3"), "e": (agri_e, "CALC")}, "$M", 2, ["S083_l7_ma"],
               note="management's +$1.5M EBITDA by 2030 less the acquired EBITDA implied by the price")
slide("S083_l7_ma",
      txt(f"Agricity's '+$1.5M EBITDA' mixes about ${agri_e:.1f}M of acquired earnings with a gross in-sourcing synergy "
          "that has no cost, capex or plan-overlap analysis", ["CBG-C31-N2", "CBG-C31-N3"]),
      txt("Acquisition record and proposal as described in the CIM; synergies are management's, gross, and shown on this page only.",
          ["CBG-C30-T1-R1", "CBG-C31-N3"]),
      {"table": table(["Target", "Status", "Scale", "Terms", "What management expects", "Grade"], [
          (["Fat Worm Compost", "Closed 2018", "~$250K commercial ARR", "-", "Density in existing footprint", "asserted"], ["CBG-C30-T1-R1"]),
          (["WB Waste", "Closed 2023", "~$300K commercial ARR", "-", "Contracts for route density", "asserted"], ["CBG-C30-T1-R2"]),
          (["Key City Compost", "Closed 2024", "Frederick curbside; KeyCompostables", "-", "Geography, products, Utica rights", "indicated"], ["CBG-C30-T1-R3", "HPF-V90-R5"]),
          (["Agricity - acquired earnings", "Proposed", "~$2.8M revenue; 40% of DC collections", "$3.0M = 5.1x adjusted EBITDA", f"~{m(agri_e)} EBITDA bought (implied)", "asserted"], ["CBG-C31-N1", "CBG-C31-N2", "CALC"]),
          (["Agricity - synergy (gross)", "Proposed", "In-source DC subcontract", "Cash, note, 6% equity, 2.4% warrants", f"~$1.0M a year by 2030; {m(syn_gap)} of the +$1.5M", "asserted"], ["CBG-C31-N2", "CBG-C31-N3", "CALC"])],
          widths=[2.3, 1.2, 2.6, 2.4, 3.0, 1.1]),
       "takeaway": {"type": "text", "text": (
           "Net value is not established: the saving is gross of the crews and fleet Compost Crew would add, it is capped by "
           "the $1.18M paid to subcontractors in 2025, integration cost and the equity component are unpriced, and the plan's "
           "margin expansion may already count it."), "refs": need("CBG-C31-N3", "HPF-V90-R18", "CBG-C31-N2"), "kind": "interpretation"}})

slide("S020_highlights_summary",
      txt("A real, thinly profitable collector with recurring but mostly uncontracted revenue; the $50.2M plan "
          "cannot anchor value until DC and sales capacity are tested",
          ["HPF-V90-R40", "HPF-V91-R1", "CBG-C16-N7", "WEB-CID-06"]),
      txt("Revised after the C1-C6 review. Grades are by source class; the issue register lists what each open item needs.",
          ["CHECK:coverage"]),
      {"rows": table(["#", "Area", "Finding (usable now unless marked)", "Key figures", "Grade"], [
          (["1", "Trading", "Growth slowed sharply after the 2024 DC step-up; thin, volatile EBITDA",
            f"+{g24:.0f}%, +{g25:.0f}%, +3% YTD; EBITDA 4.3% (2025)", "indicated"],
           ["HPF-V90-R8", "HPF-V90-YTD-revenue", "HPF-V90-R41"]),
          (["2", "Revenue quality", "Recurring, not contracted: only municipal has contracts, DC terms unreviewed",
            "DC 23% of 2025 revenue; 1 firm + 4 option years", "asserted"],
           ["RVQ-V93-R1", "HPF-V91-R1", "CBG-C16-N7", "WEB-CID-06", "CALC"]),
          (["3", "Customers", "Commercial accounts retained and expanding; residential basis is mixed",
            "Commercial NRR 106.6%; residential 84.8% (mixed)", "indicated"], ["CST-V92-R10", "CST-V94-R9"]),
          (["4", "Market", "Company model only; municipal unsized; no independent size",
            "SOM $139M current, $206M expanded", "asserted"], ["MVG-V90-R7", "MVG-V90-R15", "CALC"]),
          (["5", "Plan", "2030P rests on option years, 2.4x sales reps and new municipal wins (open)",
            f"$50.2M plan vs ${mom3:.0f}M-${mom13:.0f}M on recent momentum", "asserted"],
           ["HPF-V91-R1", "CBG-C29-T1-R6", "CALC"]),
          (["6", "Value add-ons", "Agricity and Utica benefits are gross; net value not shown (open)",
            f"Agricity ~{m(also(agri_e, 'S020_highlights_summary'))} bought + ~$1.0M gross synergy", "asserted"], ["CBG-C31-N2", "CBG-C31-N3", "CALC"])],
          widths=[0.5, 1.7, 4.6, 3.8, 1.2])})
calc("C4-dc-share-2025-hl", "a / r * 100", {"a": (3.08, "RVQ-V93-R1"), "r": (13.28, "HPF-V91-R1")}, "%", 0, ["S020_highlights_summary"])

# =========================================================================== withheld pages
WITHHOLD = {
    "S013_business_model_comparison": "No peer business-model data; the segment economics are on S012.",
    "S016_pain_points": "Customer pain points need customer research; none in the data room.",
    "S017_roadmap": "Roadmap items are covered with evidence on S010 and S082.",
    "S018_industry_trends": "Agent trend findings are generic (digitalisation, regulation) and uncited to this market.",
    "S022_h1_sam_walkup": "Current-to-expanded SAM is shown on S021; a separate walk-up would repeat it.",
    "S024_h1_recession": "No through-cycle data: the business has three years of history.",
    "S031_h5_growth_levers": "Growth levers are quantified on S072; the highlight row is on S020.",
    "S035_volume_narrowing": "No volume funnel beyond the company's 30% x 30% assumptions (S089).",
    "S036_volume_by_channel": "No channel-level market volumes in the data room.",
    "S038_sam_by_endmarket": "End-market split is the residential / commercial split on S021 and S037.",
    "S039_value_added_services": "Products are covered on S082 with the plan figures.",
    "S040_growth_factors_overview": "Market growth factors are not evidenced; company growth is decomposed on S023.",
    "S041_gf1_demand": "No demand data beyond the company model.",
    "S048_downturn_resilience": "No downturn history to test.",
    "S052_switching_drivers": "Switching drivers need customer research; contract status is on S015.",
    "S054_decision_process": "Buyer decision process needs interviews; none available.",
    "S055_purchase_criteria": "Only management's stated criteria exist; not a customer view.",
    "S057_switching_complexity": "Contract and switching position is covered on S015 and S068.",
    "S059_routes_to_market": "Routes to market are shown by segment on S012.",
    "S061_positioning_map": "No market-share or price-quality data to position competitors.",
    "S063_feature_benchmarking": "Feature comparison is management's self-assessment, shown once on S062.",
    "S066_competitor_painpoints": "Needs customer research.",
    "S074_l1_right_to_win": "Right to win needs win-loss data; none available.",
    "S085_landscape_by_category": "Competitor landscape consolidated on S060.",
    "S086_landscape_by_size": "No competitor revenue or size data.",
}
C["withhold"] = [{"id": k, "exception": "E13-WITHHELD", "reason": v} for k, v in WITHHOLD.items()]
for k in WITHHOLD:
    S.pop(k, None)
C["force_render"] = []

# =========================================================================== exceptions
keep_rules = {"E1-NOT-PROVIDED", "E11-NO-PRIMARY", "E10-SOURCE-DRIFT", "E12-SUBSTITUTION"}
EXC = [e for e in C["exceptions"] if e["rule"] in keep_rules]
EXC += [
    {"severity": "CRITICAL", "rule": "E3-CONFLICT",
     "issue": "The CIM states three growth rates for one plan: 45% five-year CAGR (p6), ~30.4% (p28) and 31% ARR CAGR (p33).",
     "short": "CIM gives 45%, ~30.4% and 31% growth for the same plan",
     "slides": ["S046_sam_growth_build", "S072_growth_levers_overview"], "source": "CBG-C6-N3, CBG-C28-T1-R1, CBG-C33-N2, HPF-V91-R1",
     "treatment": "The model's 30.4% revenue CAGR (2025-2030P) is used; the 45% figure is not adopted.",
     "treatment_short": "Model 30.4% used; 45% not adopted"},
    {"severity": "HIGH", "rule": "E14-AGENT-ERROR",
     "issue": "Market-size agent reports $210.31M-$256.00M for 'North America waste management'; the source is in billions and is not this market.",
     "short": "Market agent's $256.00M is a North American waste market, in billions",
     "slides": ["S021_h1_market_size"], "source": "MVG-1-R, CID-Y5",
     "treatment": "Rejected. The company's bottom-up model is shown instead, graded asserted.",
     "treatment_short": "Rejected; company model shown, graded asserted"},
    {"severity": "HIGH", "rule": "E14-AGENT-ERROR",
     "issue": "Competition agent lists the target's own brand, its subcontractor, an acquired company and a site host as competitors; its matrix uses placeholders.",
     "short": "Competitor agent lists own brand, subcontractor and acquisitions as rivals",
     "slides": ["S060_competitor_archetypes"], "source": "CID-1-R, CID-3-T1-R1",
     "treatment": "Replaced by six items of dated web research and the CIM archetypes.",
     "treatment_short": "Replaced by web research and CIM archetypes"},
    {"severity": "HIGH", "rule": "E14-AGENT-ERROR",
     "issue": "Recommendation and competition agents conclude 'Proceed' / 'Invest' and a 'market moat' on a 45% CAGR the plan does not contain.",
     "short": "Agent 'Invest' and 'moat' verdicts rest on the unadopted 45% CAGR",
     "slides": ["S020_highlights_summary", "S015_barriers"], "source": "REC-1-T1-R1, CID-V, REC-2-T1-R1",
     "treatment": "Not adopted. Findings are stated at their evidence grade with explicit conditions.",
     "treatment_short": "Not adopted; graded findings with conditions"},
    {"severity": "HIGH", "rule": "E3-CONFLICT",
     "issue": "2025 revenue is $13.41M in the QBO accounts and $13.28M in the model and CIM.",
     "short": "2025 revenue: QBO $13.41M vs model and CIM $13.28M",
     "slides": ["S009_company_snapshot", "S046_sam_growth_build"], "source": "HPF-V90-R8, HPF-V91-R1, CBG-V98-R3",
     "treatment": "QBO used for actuals, model for plan comparisons; reconciliation requested.",
     "treatment_short": "QBO for actuals, model for plan; reconcile"},
    {"severity": "HIGH", "rule": "E1-NOT-PROVIDED",
     "issue": "Municipal revenue (36% of 2025) is outside the company market model; only the DC contract can be sized.",
     "short": "Municipal (36% of revenue) is not in the market model",
     "slides": ["S021_h1_market_size", "S034_market_definitions"], "source": "MVG-V90-R7, HPF-V90-R2",
     "treatment": "DC sized from contract scenarios; request a municipal pipeline and addressable-programme list.",
     "treatment_short": "DC sized from scenarios; request municipal pipeline"},
    {"severity": "MEDIUM", "rule": "E4-UNIT-MISMATCH",
     "issue": "The Stripe residential count includes 2,071 government-programme homes billed at a nominal rate and already counted as municipal.",
     "short": "Stripe residential count double-counts 2,071 municipal homes",
     "slides": ["S064_price_benchmarking", "S023_h1_growth_drivers"], "source": "CST-V97-R2, CST-V97-N2",
     "treatment": "Paying book (5,495; $29.19) used for price and unit economics.",
     "treatment_short": "Paying book used"},
    {"severity": "MEDIUM", "rule": "E3-CONFLICT",
     "issue": "Commercial Account 0007 appears twice in the concentration schedule (ranks 7 and 19).",
     "short": "Duplicate account in the concentration schedule",
     "slides": ["S049_risk_assessment"], "source": "RVQ-V94-DQ1",
     "treatment": "Top-10 share from the commercial summary (22.6%) used; schedule to be corrected.",
     "treatment_short": "Summary share used; schedule to be corrected"},
    {"severity": "MEDIUM", "rule": "E3-CONFLICT",
     "issue": "The ARR model assumes 96.3% commercial and 93.8% residential annual logo retention against 92.4% and 84.8% achieved in 2025.",
     "short": "Model retention above 2025 actuals",
     "slides": ["S068_churn_triggers"], "source": "CST-V91-R5, CST-V91-R8",
     "treatment": "Both shown; plan sensitivity to actual retention requested.",
     "treatment_short": "Both shown; sensitivity requested"},
]

# =========================================================================== diligence review (C1-C6)
EXC += [
    {"severity": "HIGH", "rule": "E3-CONFLICT",
     "issue": "Revenue 2023-2025 in the QBO ledger exceeds the model and CIM by $0.03M, $0.13M and $0.13M; the gap equals QBO 'Other revenue', which the model omits. 2025 EBITDA nevertheless agrees within $0.01M, so about $0.12M of model cost differences is unexplained.",
     "short": "QBO vs model revenue gap = 'Other revenue'; ~$0.12M EBITDA offset unexplained",
     "slides": ["S009_company_snapshot", "S045_gf4_pricing_stability", "S011_value_chain"],
     "source": "reconciliation.md; HPF-V90-R7, HPF-V90-R8, HPF-V91-R1, HPF-V91-R4",
     "treatment": "QBO used for actuals, model for plan comparisons, each labelled; model-to-ledger bridge requested.",
     "treatment_short": "Both bases labelled; ledger-to-model bridge requested"},
]
C["reconciliations"] = [
    {"metric": "revenue", "period": p_, "basis_used": "QBO for actuals; model for plan", "explanation":
     "QBO includes 'Other revenue' excluded from the model"} for p_ in ("2023", "2024", "2025")] + [
    {"metric": "gross_profit", "period": p_, "basis_used": "QBO", "explanation": "same 'Other revenue' difference (no cost attached)"} for p_ in ("2024", "2025")] + [
    {"metric": "gross_margin", "period": "2025", "basis_used": "QBO 30.4%; model 29.8%", "explanation": "revenue basis difference"},
    {"metric": "ebitda_margin", "period": "2023", "basis_used": "QBO -9.5%; model -9.9%", "explanation": "revenue and EBITDA basis difference ($0.02M)"},
    {"metric": "ebitda_margin", "period": "2024", "basis_used": "QBO 9.6%; model 9.5%; CIM rounds to 9%", "explanation": "rounding and basis"}]

C["issues"] = [
    {"id": "I01", "priority": 1, "control": "C1", "claim": "DC municipal contract treated as secured revenue to 2030P",
     "slides": ["S012", "S015", "S029", "S046", "S047", "S072"],
     "problem": "The CIM describes one firm year plus four option years; the contract has not been reviewed. Duration, option-exercise mechanics, termination for convenience, participation caps, minimum volumes and appropriation dependency are unknown.",
     "impact": "DC is ~23% of 2025 revenue ($3.08M) and $10.42M (21%) of 2030P; the full-take-up case is $20.83M. All depend on option exercise.",
     "correction": "Reworded to 'option-year contract, terms unreviewed' and graded asserted on every page; DC rows beyond today labelled as assuming option exercise.",
     "evidence_required": "Executed DC contract and all modifications/CLINs; option-exercise history and notices; termination clauses; participation caps and price escalators by year; funding/appropriation source; re-tender timing.",
     "could_change": ["price", "structure", "decision"], "pre_decision": "mandatory", "status": "qualified"},
    {"id": "I02", "priority": 1, "control": "T20", "claim": "No diligence case against the $50.2M plan",
     "slides": ["S046", "S047", "S020"],
     "problem": "The deck tests the plan but offers no diligence view. Momentum cross-checks give $15.40M (Jan-Jul 2026 growth) to $24.47M (2025 growth) of 2030 revenue.",
     "impact": f"Plan is 2.0x-3.3x the momentum range; valuation on plan would overstate 2030 revenue by $25.7M-$34.8M.",
     "correction": "Momentum cross-check added (labelled as arithmetic, not a forecast); plan graded asserted; no case invented.",
     "evidence_required": "Resolution of I01, I03, I04, I05; partner assumptions for DC ramp, sales capacity and retention; 2026 budget vs actual by month.",
     "could_change": ["price", "decision"], "pre_decision": "mandatory", "status": "open"},
    {"id": "I03", "priority": 1, "control": "C5", "claim": "Commercial growth engine (largest plan lever, +$13.65M)",
     "slides": ["S072", "S073", "S075"],
     "problem": "New commercial logos fell from 171 (2024) to 81 (2025) and accounts from 663 to 591 (2026H1); the plan needs reps 8 to 19 at 52 accounts each a year. No rep-level productivity history exists.",
     "impact": "Commercial is 37% of plan growth; 2025 new logos equal 1.6 reps' quota.",
     "correction": "Lever graded asserted; decline and quota gap stated.",
     "evidence_required": "Rep-level bookings, ramp and attrition 2023-2026; pipeline with stage and age; win/loss; CRM export reconciled to new-logo counts.",
     "could_change": ["price", "decision"], "pre_decision": "mandatory", "status": "open"},
    {"id": "I04", "priority": 1, "control": "C4", "claim": "Model retention above actual retention",
     "slides": ["S068", "S046"],
     "problem": "Model annual retention (96.3% commercial / 93.8% residential) is per location (ARR roll); actuals (92.4% / 84.8%) are per account and per Stripe subscription. The gap may be partly definitional; neither is restated on the other basis.",
     "impact": "Drives the run-off of $9.8M existing non-DC ARR to $7.0M in 2030P; each point of annual retention on ~$9.8M is ~$0.1M a year, compounding.",
     "correction": "Labelled 'basis differs'; no retention figure is compared across bases in the deck.",
     "evidence_required": "ARR roll by location with churn events; retention restated per account and per location for 2023-2026; definition of 'location' vs 'account'.",
     "could_change": ["price"], "pre_decision": "mandatory", "status": "qualified"},
    {"id": "I05", "priority": 1, "control": "C3", "claim": "Today's DC run-rate",
     "slides": ["S047"],
     "problem": "The v3 deck multiplied today's 12,000 homes by the 2030 modelled revenue per home ($347, including escalators), giving $4.17M. That mixes a 2026 volume with a 2030 price.",
     "impact": "Run-rate overstated by ~$1.0M (31%). On 2026H1 billings x 2 the run-rate is $3.18M; 2026P DC of $3.96M needs +25%.",
     "correction": "Replaced with 2026H1 billings annualised (Account 01 identified as DC by its 63.2% share); old figure withdrawn on the page.",
     "evidence_required": "Monthly DC billings and active homes 2025-2026; confirmation that Account 01 is the DC contract; seasonality.",
     "could_change": ["price"], "pre_decision": "mandatory", "status": "corrected"},
    {"id": "I06", "priority": 1, "control": "C6", "claim": "Growth acceleration (+$13.7M, 27% of 2030P) stated gross",
     "slides": ["S046", "S075"],
     "problem": "The acceleration case needs new capital and reps 9 to 23; the capital amount, hiring cost and payback are not shown alongside the revenue.",
     "impact": "27% of 2030P revenue has no stated cost or funding; a buyer funding it would pay for its own growth.",
     "correction": "Graded asserted; stated as needing capital.",
     "evidence_required": "Use-of-proceeds and capital requirement by year; sales and marketing cost build; EBITDA bridge baseline vs acceleration.",
     "could_change": ["price", "structure"], "pre_decision": "mandatory", "status": "open"},
    {"id": "I07", "priority": 2, "control": "C2", "claim": "Revenue and margin history",
     "slides": ["S009", "S011", "S045"],
     "problem": "QBO exceeds model/CIM revenue by $0.03M / $0.13M / $0.13M (2023-25) = QBO 'Other revenue'; EBITDA agrees within $0.01M, leaving ~$0.12M of cost differences unexplained. CIM TTM $13.5mn vs QBO $13.61M; CIM TTM GM 28.7% vs QBO 29.0%.",
     "impact": "~1% of revenue; ~20% of 2025 EBITDA ($0.57M) if the cost offset reverses.",
     "correction": "Both bases labelled; reconciliation table produced; exception added.",
     "evidence_required": "Model-to-ledger bridge by line; nature of 'Other revenue'; QoE on 2025 and TTM EBITDA.",
     "could_change": ["price"], "pre_decision": "mandatory", "status": "qualified"},
    {"id": "I08", "priority": 2, "control": "C5", "claim": "Customer metrics graded 'established' in v3",
     "slides": ["S012", "S029", "S068", "S079"],
     "problem": "Retention, cohort, concentration and unit-economics figures come from a management-prepared investor workbook; none was tested to billing data. QBO is an unaudited ledger.",
     "impact": "Grades fall from established to indicated across customer pages.",
     "correction": "Grades recomputed by source class on every table; workbook figures labelled company-prepared.",
     "evidence_required": "Billing / Stripe / invoicing exports to rebuild retention and concentration independently; audited or QoE financials.",
     "could_change": ["price"], "pre_decision": "mandatory", "status": "corrected"},
    {"id": "I09", "priority": 2, "control": "C4", "claim": "Residential subscriber trends",
     "slides": ["S023", "S064", "S068"],
     "problem": "From Jun-2025 the Stripe base includes 2,071 government-programme homes at ~$1.94 a month, already counted as municipal; Mar-2026 churn of 479 is a clean-up of that block. 2025-26 new subscriptions, retention and blended ARPU mix two populations.",
     "impact": "Residential is 15% of revenue; blended ARPU $21.46 vs paying book $29.19.",
     "correction": "Paying book used for price and unit economics; residential retention marked mixed.",
     "evidence_required": "Stripe export split programme vs paying, monthly 2021-2026.",
     "could_change": [], "pre_decision": "residual", "status": "qualified"},
    {"id": "I10", "priority": 2, "control": "C6", "claim": "Agricity '+$1.5M EBITDA by 2030'",
     "slides": ["S083", "S011"],
     "problem": "Combines ~$0.59M of acquired EBITDA (implied by $3.0M at 5.1x) with a ~$1.0M in-sourcing synergy stated gross. In-sourcing adds crews and fleet; integration cost, the 6% equity and 2.4% warrant consideration are unpriced; overlap with the plan's margin expansion is unknown.",
     "impact": "Synergy capped by $1.18M 2025 subcontract spend; net value could be a fraction of $1.0M.",
     "correction": "Acquired earnings and gross synergy split on the page; net value stated as not established.",
     "evidence_required": "Agricity financials (3 years) and QoE; subcontract P&L by route; integration budget; valuation of equity/warrants; plan bridge showing whether in-sourcing is in 2030P margins.",
     "could_change": ["price", "structure"], "pre_decision": "mandatory", "status": "corrected"},
    {"id": "I11", "priority": 2, "control": "C6", "claim": "Utica facility benefits",
     "slides": ["S082", "S015"],
     "problem": "Utica revenue ($1.64M 2030P) and 'self-tipping' savings are gross; facility opex, capex beyond the $2.68M grant, grant conditions and timing risk (road widening, grading permit) are not modelled.",
     "impact": "3% of 2030P revenue; savings capped by $0.99M 2025 transfer and disposal cost.",
     "correction": "Stated gross, with the cost cap.",
     "evidence_required": "Utica business case and capex budget; grant agreement (conditions, clawback); permit status.",
     "could_change": ["structure"], "pre_decision": "residual", "status": "qualified"},
    {"id": "I12", "priority": 2, "control": "C1", "claim": "Existing book described as a contracted foundation",
     "slides": ["S046", "S012"],
     "problem": "Commercial and residential service is pay as you go; the $7.0M 'existing ARR' in the bridge is recurring, not contracted, and run off at model retention.",
     "impact": "14% of 2030P; sensitive to I04.",
     "correction": "Title and bridge rewritten ('neither is committed to 2030').",
     "evidence_required": "Commercial terms sample (notice periods, auto-renewal); churn by notice type.",
     "could_change": ["price"], "pre_decision": "residual", "status": "corrected"},
    {"id": "I13", "priority": 2, "control": "C5", "claim": "Municipal pipeline and market size",
     "slides": ["S021", "S034"],
     "problem": "Market size is the company's own count-times-price model with flat 30% x 30% haircuts; municipal (36% of revenue) is unsized; no regulation or programme-pipeline evidence.",
     "impact": "Market is not binding at ~6% of today's SOM, but the plan's +$5.97M municipal ex-DC growth has no named pipeline.",
     "correction": "Graded asserted; penetration restated like for like (6.1% current / 4.1% expanded).",
     "evidence_required": "Named municipal pipeline with stage, value and timing; relevant diversion mandates; third-party or top-down sizing.",
     "could_change": ["price"], "pre_decision": "mandatory", "status": "qualified"},
    {"id": "I14", "priority": 3, "control": "C3", "claim": "Plan multiple and penetration bases",
     "slides": ["S046", "S021"],
     "problem": "v3 divided the plan (model) by QBO revenue and divided current revenue by the expanded-territory SOM.",
     "impact": "3.7x restated to 3.8x; penetration 4.1% restated to 6.1% on today's territory.",
     "correction": "Restated on one basis each.", "evidence_required": "none", "could_change": [],
     "pre_decision": "residual", "status": "corrected"},
    {"id": "I15", "priority": 3, "control": "C4", "claim": "'25,546 active locations'",
     "slides": ["S009", "S012", "S029"],
     "problem": "Sums municipal households (19,195), commercial sites (856) and residential subscribers (5,495); commercial accounts are 591, not 856.",
     "impact": "Presentation only.", "correction": "Components stated wherever the total appears.",
     "evidence_required": "none", "could_change": [], "pre_decision": "residual", "status": "corrected"},
    {"id": "I16", "priority": 3, "control": "C5", "claim": "CIM service claims (99.5% on time, 70+ NPS, 20 partners)",
     "slides": ["S029"],
     "problem": "No service log, NPS data or municipal contract list in the data room.",
     "impact": "Supports quality narrative only.", "correction": "Attributed to the CIM, graded asserted.",
     "evidence_required": "Service-level reports; NPS survey raw data; list of municipal contracts with terms.",
     "could_change": [], "pre_decision": "residual", "status": "qualified"},
    {"id": "I17", "priority": 3, "control": "C2", "claim": "Commercial concentration schedule",
     "slides": ["S049"],
     "problem": "Account 0007 appears twice (ranks 7 and 19); cumulative shares below rank 19 overstated.",
     "impact": "Top-10 share unaffected (22.6% from the summary).", "correction": "Summary share used.",
     "evidence_required": "Corrected schedule from billing data.", "could_change": [], "pre_decision": "residual", "status": "qualified"},
    {"id": "I18", "priority": 3, "control": "C5", "claim": "Competitive pricing",
     "slides": ["S064", "S080"],
     "problem": "One published competitor list price (web) against realised ARPU; no win/loss or price-sensitivity evidence.",
     "impact": "Price headroom unproven.", "correction": "Graded indicated; 'competitive pricing' not asserted.",
     "evidence_required": "Price lists and discount history; churn after price increases; 10-15 customer interviews.",
     "could_change": [], "pre_decision": "residual", "status": "qualified"},
]
C["conclusion"] = {
    "confidence": "Moderate on historical trading; low on contract durability, retention, market and all forward value",
    "statement": (f"Compost Crew is a ~$13.4M-revenue (2025, unaudited ledger), thinly profitable (EBITDA 4.3%; TTM Jun-2026 $0.39M) "
                  "regional food-scrap collector whose revenue is recurring but largely uncontracted, with ~23% from one municipal "
                  "contract whose firm term and options have not been reviewed. Recent trading (+13% in 2025, +3% Jan-Jul 2026) "
                  f"supports valuing the business on current earnings, not on the $50.2M 2030P plan, which recent momentum puts at "
                  f"${mom3:.1f}M-${mom13:.1f}M. The investment case cannot be supported at plan-based pricing until I01-I06 close; "
                  "DC upside, sales-led growth, Agricity and Utica are candidates for deferred or contingent consideration rather than price."),
    "usable": [
        "Revenue, gross margin and EBITDA history 2023-2025 and Jan-Jul 2026 from the ledger (differences to the model quantified, ~1%)",
        "Growth decomposition: 2024 driven by DC; 2025 +$1.54M led by commercial and KeyCompostables; residential flat",
        "Commercial account retention ~92% a year with NRR above 100% (company-prepared; indicated)",
        "Cost structure: collection labour a third of revenue; subcontracting $1.18M (2025)",
        "Concentration: DC ~23% of revenue; five contracts 88% of municipal revenue",
        "The plan requires ~30% annual growth against 13% (2025) and 3% (YTD 2026)",
    ],
    "dependent": [
        {"finding": "Durability of DC revenue and any value for DC upside", "depends_on": ["I01", "I05"]},
        {"finding": "Any forecast above momentum, including the 2030P plan", "depends_on": ["I02", "I03", "I04", "I06", "I13"]},
        {"finding": "Run-off of the existing book and model retention", "depends_on": ["I04", "I12"]},
        {"finding": "EBITDA base for valuation", "depends_on": ["I07", "I08"]},
        {"finding": "Net value of Agricity and Utica", "depends_on": ["I10", "I11"]},
    ],
}
C["exceptions"] = EXC
C["calculations"] = CALCS
C["glossary_extra"] = {"QBO": "QuickBooks Online - the company's accounting ledger; source of the actuals.",
                       "Paying book": "Residential subscribers billed at the standard rate (5,495 at 30-Jun-2026), "
                                      "excluding government-programme homes billed through Stripe.",
                       "Grade (evidence)": "established / indicated / asserted - the strength of evidence behind a finding (see S005)."}
C["metrics"] = {"revenue_2025": {"value": "$13.41M", "slides": ["S009_company_snapshot", "S023_h1_growth_drivers"]},
                "plan_2030": {"value": "$50.17M", "slides": ["S072_growth_levers_overview"]}}
for sid, sc in S.items():
    if isinstance(sc, dict):
        sc.pop("baseline", None)
(W / "content.json").write_text(json.dumps(C, indent=1, ensure_ascii=False))
print(f"slides {len(S)}; calcs {len(CALCS)}; exceptions {len(EXC)}; withheld {len(WITHHOLD)}")
