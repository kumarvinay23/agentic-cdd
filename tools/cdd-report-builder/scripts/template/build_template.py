#!/usr/bin/env python3
"""Maintainer script: build assets/cdd_template.pptx from the masters + config/slide_map.yaml.

  node build_masters.js base.pptx && python build_template.py base.pptx ../../assets/cdd_template.pptx

Every template slide:
  * is named with its slide_map id (p:cSld/@name) - the renderer finds slides by this name;
  * carries shapes whose names are the element names in slide_map.yaml (title, subtitle, left, ...);
  * shows instruction text in square brackets inside each variable shape. Instruction text is NOT
    content: the renderer replaces it and QA fails the deck if any bracketed instruction survives;
  * carries the blueprint contract for that page in its speaker notes - purpose, what the slide
    must contain, admissible sources, the analysis it performs, the exhibit form, the quality bar,
    the modules that feed it and the gate that decides whether it renders. The template is
    therefore the slide-by-slide guideline as well as the rendering surface.

Panel headings come from slide_map.yaml -> heads, not from a table in this file.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import yaml
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[1]
B = json.loads((HERE / "brand.json").read_text())
C = {k: RGBColor.from_string(v) for k, v in B["colors"].items()}
FONT = B["fonts"]["body"]
SM = yaml.safe_load((SKILL / "config" / "slide_map.yaml").read_text())

# ------------------------------------------------------------------ geometry (inches)
X0, W = 0.45, 12.43
Y0, YB = 1.85, 6.70
HEAD_H = 0.36
HALF = 6.1
RIGHT_X = 6.78
WIDE_L, NARROW_R, NARROW_X = 7.75, 4.43, 8.45

GEOM = {
    "table_full": {"table": (X0, Y0, W, 4.25), "takeaway": (X0, 6.18, W, 0.52)},
    "two_panel": {"left_head": (X0, Y0, HALF, HEAD_H), "left": (X0, Y0 + 0.46, HALF, 4.39),
                  "right_head": (RIGHT_X, Y0, HALF, HEAD_H), "right": (RIGHT_X, Y0 + 0.46, HALF, 4.39)},
    "table_commentary": {"left_head": (X0, Y0, WIDE_L, HEAD_H), "left": (X0, Y0 + 0.46, WIDE_L, 4.39),
                         "right_head": (NARROW_X, Y0, NARROW_R, HEAD_H), "right": (NARROW_X, Y0 + 0.46, NARROW_R, 4.39)},
    "chart_commentary": {"chart_head": (X0, Y0, WIDE_L, HEAD_H), "chart": (X0, Y0 + 0.46, WIDE_L, 4.39),
                         "right_head": (NARROW_X, Y0, NARROW_R, HEAD_H), "right": (NARROW_X, Y0 + 0.46, NARROW_R, 4.39)},
    "table_chart": {"left_head": (X0, Y0, HALF, HEAD_H), "left": (X0, Y0 + 0.46, HALF, 3.72),
                    "right_head": (RIGHT_X, Y0, HALF, HEAD_H), "right": (RIGHT_X, Y0 + 0.46, HALF, 3.72),
                    "takeaway": (X0, 6.18, W, 0.52)},
    "kpi_panel": {"kpi1": (X0, Y0, 2.36, 1.12), "kpi2": (X0 + 2.53, Y0, 2.36, 1.12),
                  "kpi3": (X0 + 5.06, Y0, 2.36, 1.12), "kpi4": (X0 + 7.59, Y0, 2.36, 1.12),
                  "kpi5": (X0 + 10.12, Y0, 2.36, 1.12),
                  "left_head": (X0, 3.17, HALF, HEAD_H), "left": (X0, 3.63, HALF, 3.07),
                  "right_head": (RIGHT_X, 3.17, HALF, HEAD_H), "right": (RIGHT_X, 3.63, HALF, 3.07)},
    "columns5": {"lead": (X0, Y0, W, 0.72)},
    "numbered_rows": {"rows": (X0, Y0, W, 4.85)},
    "contents": {"contents_body": (1.2, Y0 - 0.25, 11.0, 5.1)},
    "disclaimer": {"disclaimer_body": (X0, Y0, W, 3.6), "data_notice": (X0, 5.7, W, 0.95)},
    # --- archetypes added for the 97-slide blueprint -------------------------
    "text_panel": {"panel_body": (X0, Y0 - 0.2, W, 4.95)},
    "flow_row": {"flow_head": (X0, Y0, WIDE_L, HEAD_H), "flow": (X0, Y0 + 0.46, WIDE_L, 4.39),
                 "right_head": (NARROW_X, Y0, NARROW_R, HEAD_H), "right": (NARROW_X, Y0 + 0.46, NARROW_R, 4.39)},
    "method_flow": {"flow_head": (X0, Y0, WIDE_L, HEAD_H), "flow": (X0, Y0 + 0.46, WIDE_L, 4.39),
                    "right_head": (NARROW_X, Y0, NARROW_R, HEAD_H), "right": (NARROW_X, Y0 + 0.46, NARROW_R, 4.39)},
    "quotes": {"quotes_head": (X0, Y0, WIDE_L, HEAD_H), "quotes": (X0, Y0 + 0.46, WIDE_L, 4.39),
               "right_head": (NARROW_X, Y0, NARROW_R, HEAD_H), "right": (NARROW_X, Y0 + 0.46, NARROW_R, 4.39)},
    "three_panel": {},
    "cover": {},
    "back_cover": {},
    "divider": {},
}
cw5 = (W - 4 * 0.18) / 5
for i in range(5):
    x = X0 + i * (cw5 + 0.18)
    GEOM["columns5"][f"col{i+1}_head"] = (x, 2.72, cw5, 0.5)
    GEOM["columns5"][f"col{i+1}_body"] = (x, 3.30, cw5, 3.40)
cw3 = (W - 2 * 0.22) / 3
for i in range(3):
    x = X0 + i * (cw3 + 0.22)
    GEOM["three_panel"][f"p{i+1}_head"] = (x, Y0, cw3, HEAD_H)
    GEOM["three_panel"][f"p{i+1}"] = (x, Y0 + 0.46, cw3, 4.39)

SECTIONS = {s["id"]: s for s in SM["sections"]}
SEC_ORDER = [s["id"] for s in SM["sections"] if s["id"] != "front"]

DISCLAIMER = [
    "This report has been generated from the diligence agent outputs listed in the appendix and is limited to the information those outputs contain. It is intended solely for the addressee and for the purpose of evaluating the transaction described.",
    "The report does not constitute an audit, legal opinion or investment advice and provides no form of assurance. Figures are reproduced or calculated from the stated sources; where evidence was missing or inconsistent this is disclosed on the relevant slide and in the exception log.",
    "Slides that the evidence base could not support have been withheld rather than filled with placeholder content; every withheld page is listed with its reason in the exceptions appendix.",
    "Recipients should perform their own diligence before making any decision. No duty of care is accepted towards any third party, and the report may not be distributed further without prior written consent.",
]
WORKSTREAMS = ["Business & Market Primer", "Market Dynamics & Opportunity",
               "Decision-Making Dynamics", "Competitive Landscape", "Growth Opportunities"]


# ------------------------------------------------------------------ primitives
def rgb(shape_fill, color):
    shape_fill.solid()
    shape_fill.fore_color.rgb = color


def textbox(slide, name, geom, text, size=12, bold=False, italic=False, color=None,
            align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, wrap=True):
    x, y, w, h = geom
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tb.name = name
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Pt(0)
    tf.margin_top = tf.margin_bottom = Pt(0)
    p = tf.paragraphs[0]
    p.alignment = align
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.italic = italic
    r.font.name = FONT
    r.font.color.rgb = color if color is not None else C["text"]
    return tb


def region(slide, name, geom, instruction):
    x, y, w, h = geom
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.name = name
    rgb(sh.fill, C["tint2"])
    sh.line.color.rgb = C["line"]
    sh.line.width = Pt(0.75)
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Pt(7)
    tf.margin_top = tf.margin_bottom = Pt(6)
    tf.vertical_anchor = MSO_ANCHOR.TOP
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run()
    r.text = instruction
    r.font.size = Pt(9)
    r.font.italic = True
    r.font.name = FONT
    r.font.color.rgb = C["slate"]
    return sh


def chip(slide, name, geom, text, fill=None, color=None, size=11):
    x, y, w, h = geom
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.name = name
    rgb(sh.fill, fill if fill is not None else C["ink"])
    sh.line.fill.background()
    sh.shadow.inherit = False
    tf = sh.text_frame
    tf.word_wrap = True
    tf.margin_left = Pt(8)
    tf.margin_right = Pt(6)
    tf.margin_top = tf.margin_bottom = Pt(2)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = text
    r.font.size = Pt(size)
    r.font.bold = True
    r.font.name = FONT
    r.font.color.rgb = color if color is not None else C["white"]
    return sh


def instruction_for(el):
    t = el["type"]
    lim = el.get("limits", {})
    if t == "table":
        return (f"[TABLE - max {lim.get('max_rows', 9)} rows x {lim.get('max_cols', 6)} cols; "
                f"header row + data; every row carries refs; "
                f"missing values as \"Not provided\", never blank]")
    if t == "bullets":
        return (f"[BULLETS - max {lim.get('max_items', 5)} items, "
                f"{lim.get('max_chars_item', 170)} chars each; finding first, evidence second; "
                f"each item carries refs]")
    if t == "chart":
        return (f"[CHART - max {lim.get('max_series', 4)} series x {lim.get('max_points', 12)} points; "
                f"ONE unit and basis; mixed units are not plotted, they are triangulated in the commentary]")
    if t == "kpis":
        return f"[KPI TILES - max {lim.get('max_items', 5)}; value + label + period; each carries a ref]"
    if t == "text":
        return f"[TEXT - max {lim.get('max_chars', 320)} chars]"
    if t == "auto":
        return "[AUTO - generated from run data]"
    return "[CONTENT]"


def set_slide_name(slide, name):
    slide._element.cSld.set("name", name)


def write_notes(slide, sd):
    """The blueprint contract for this page, carried in the template itself."""
    L = []
    L.append(f"{sd['id']}   (blueprint slide {sd['no']} - {SECTIONS[sd['section']]['name']})")
    L.append(f"WORKING TITLE   {sd['blueprint_title']}")
    L.append(f"PURPOSE         {sd['purpose']}")
    L.append("")
    L.append("WHAT THIS SLIDE MUST CONTAIN")
    for b in sd["must_contain"]:
        L.append(textwrap.fill(f"  - {b}", 104, subsequent_indent="    "))
    L.append("")
    L.append(f"SOURCES         {sd['source_spec']}")
    L.append(textwrap.fill(f"ANALYSIS        {sd['analysis']}", 104, subsequent_indent="                "))
    L.append(f"EXHIBIT         {sd['exhibit_spec']}  (form: {sd['exhibit']})")
    L.append(textwrap.fill(f"QUALITY BAR     {sd['quality_bar']}", 104, subsequent_indent="                "))
    L.append("")
    L.append("DILIGENCEIQ MAPPING")
    L.append(f"  gate            {sd['gate']}")
    if sd["primary_modules"]:
        L.append(f"  primary modules {', '.join(sd['primary_modules'])}")
    if sd.get("fallback_modules"):
        L.append(f"  fallback        {', '.join(sd['fallback_modules'])}  (E12-SUBSTITUTION if used)")
    if sd["secondary_modules"]:
        L.append(f"  secondary       {', '.join(sd['secondary_modules'])}")
    if sd["metrics"]:
        L.append(f"  may state       {', '.join(sd['metrics'])}")
    for k, label in (("transform", "transform"), ("calc", "calculations"),
                     ("source_priority", "source priority"), ("exception", "exceptions")):
        if sd.get(k):
            L.append(f"  {label:<15} {', '.join(sd[k])}")
    slide.notes_slide.notes_text_frame.text = "\n".join(L)


# ------------------------------------------------------------------ build
def build(base, out):
    prs = Presentation(base)
    layouts = {l.name: l for l in prs.slide_layouts}
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        prs.part.drop_rel(sldId.rId)
        sldIdLst.remove(sldId)

    for sd in SM["slides"]:
        arch = sd["archetype"]
        els = {e["name"]: e for e in sd.get("elements", [])}
        heads = sd.get("heads") or {}

        # ---------------------------------------------------------- cover
        if arch == "cover":
            s = prs.slides.add_slide(layouts["DIQ_COVER"])
            set_slide_name(s, sd["id"])
            textbox(s, "cover_brand", (0.55, 0.5, 4.0, 0.45), "DiligenceIQ", 18, True, color=C["white"])
            textbox(s, "cover_tag", (0.55, 0.95, 4.2, 0.3), "Commercial due diligence", 11, color=C["mist"])
            textbox(s, "report_title", (0.55, 2.6, 4.25, 1.5),
                    "[Commercial Due Diligence: <target name>]", 26, True, color=C["white"],
                    anchor=MSO_ANCHOR.BOTTOM)
            textbox(s, "report_subtitle", (0.55, 4.18, 4.25, 0.5), "[Report type - status]", 15,
                    italic=True, color=C["amber_light"])
            textbox(s, "prepared_for", (0.55, 5.75, 4.25, 0.5), "[Prepared for <client>]", 11, color=C["white"])
            textbox(s, "report_date", (0.55, 6.25, 4.25, 0.35), "[Month YYYY]", 11, color=C["mist"])
            textbox(s, "confidential", (0.55, 6.72, 4.25, 0.3), "CONFIDENTIAL", 9, True, color=C["amber"])
            heights = [1.1, 1.6, 1.4, 2.2, 2.7, 3.4, 4.3]
            fills = [C["tint"], C["sky"], C["tint"], C["sky"], C["steel"], C["navy2"], C["amber"]]
            for i, hgt in enumerate(heights):
                x = 6.0 + i * 0.95
                sh = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(6.6 - hgt),
                                        Inches(0.62), Inches(hgt))
                sh.name = f"motif_{i}"
                rgb(sh.fill, fills[i])
                sh.line.fill.background()
                sh.shadow.inherit = False
            ln = s.shapes.add_connector(1, Inches(5.8), Inches(6.62), Inches(12.9), Inches(6.62))
            ln.name = "motif_axis"
            ln.line.color.rgb = C["slate"]
            ln.line.width = Pt(1)
            write_notes(s, sd)
            continue

        # ---------------------------------------------------------- back cover
        if arch == "back_cover":
            s = prs.slides.add_slide(layouts["DIQ_DIVIDER"])
            set_slide_name(s, sd["id"])
            textbox(s, "back_brand", (0.6, 3.0, 8.0, 0.7), "DiligenceIQ", 34, True, color=C["white"])
            textbox(s, "back_tag", (0.6, 3.8, 9.0, 0.4),
                    "Agentic commercial due diligence", 14, italic=True, color=C["amber_light"])
            textbox(s, "back_contact", (0.6, 4.6, 9.0, 0.9),
                    "[Engagement contacts - name, role, email]", 11, color=C["mist"])
            textbox(s, "back_notice", (0.6, 5.7, 11.0, 0.6),
                    "This document is confidential and prepared solely for the addressee. "
                    "Do not distribute without written consent.", 9, italic=True, color=C["slate"])
            write_notes(s, sd)
            continue

        # ---------------------------------------------------------- divider
        if arch == "divider":
            s = prs.slides.add_slide(layouts["DIQ_DIVIDER"])
            set_slide_name(s, sd["id"])
            sec = sd["section"]
            num = SEC_ORDER.index(sec) + 1 if sec in SEC_ORDER else 0
            textbox(s, "div_number", (0.6, 1.5, 3, 1.1), f"{num:02d}", 56, True, color=C["amber"])
            textbox(s, "div_title", (0.6, 2.7, 8.3, 1.2), SECTIONS[sec]["name"], 30, True, color=C["white"])
            textbox(s, "div_blurb", (0.6, 3.95, 8.3, 0.8), SECTIONS[sec].get("blurb", ""), 14,
                    italic=True, color=C["mist"])
            for i, sid in enumerate(SEC_ORDER):
                cur = sid == sec
                textbox(s, f"div_list_{i+1}", (9.3, 1.35 + i * 0.40, 3.7, 0.34),
                        f"{i+1:02d}  {SECTIONS[sid]['name']}", 9.5, bold=cur,
                        color=C["amber_light"] if cur else C["mist"])
            write_notes(s, sd)
            continue

        # ---------------------------------------------------------- content slides
        s = prs.slides.add_slide(layouts["DIQ_CONTENT"])
        set_slide_name(s, sd["id"])
        textbox(s, "section_tag", (X0, 0.12, 9.5, 0.28),
                SECTIONS[sd["section"]]["name"].upper(), 9, color=C["mist"])
        textbox(s, "slide_no_tag", (10.2, 0.12, 2.7, 0.28),
                f"BLUEPRINT {sd['no']:02d}", 8, color=C["slate"], align=PP_ALIGN.RIGHT)

        if arch in ("disclaimer", "contents", "text_panel"):
            fixed = {"disclaimer": "Disclaimer & reliance limitations",
                     "contents": "Contents",
                     "text_panel": sd["blueprint_title"]}[arch]
            textbox(s, "title", (X0, 0.42, 12.4, 0.66), fixed, 20, True, color=C["white"])
        else:
            textbox(s, "title", (X0, 0.40, 12.4, 0.72),
                    "[Action title: the so-what of this slide in one sentence, max 165 characters]",
                    20, True, color=C["white"])
            textbox(s, "subtitle", (X0, 1.12, 12.4, 0.34),
                    "[Supporting message: nuance, caveat or scale, max 150 characters]",
                    13, italic=True, color=C["amber_light"])
            textbox(s, "source", (X0, 6.76, 12.4, 0.26),
                    "[Source line - generated automatically from evidence references]", 8, color=C["slate"])

        g = GEOM.get(arch, {})

        if arch == "disclaimer":
            tb = textbox(s, "disclaimer_body", g["disclaimer_body"], DISCLAIMER[0], 11.5)
            tf = tb.text_frame
            for para in DISCLAIMER[1:]:
                p = tf.add_paragraph()
                p.space_before = Pt(9)
                r = p.add_run()
                r.text = para
                r.font.size = Pt(11.5)
                r.font.name = FONT
                r.font.color.rgb = C["text"]
            region(s, "data_notice", g["data_notice"], instruction_for(els["data_notice"]))
            write_notes(s, sd)
            continue

        if arch == "contents":
            region(s, "contents_body", g["contents_body"],
                   "[AUTO - section list with the first page of each section; "
                   "sections whose pages were all withheld are shown struck through with a reference "
                   "to the exceptions appendix]")
            write_notes(s, sd)
            continue

        if arch == "text_panel":
            region(s, "panel_body", g["panel_body"], instruction_for(els["panel_body"]))
            write_notes(s, sd)
            continue

        if arch == "columns5":
            region(s, "lead", g["lead"], instruction_for(els["lead"]))
            for i in range(5):
                chip(s, f"col{i+1}_head", g[f"col{i+1}_head"], WORKSTREAMS[i], size=10.5)
                region(s, f"col{i+1}_body", g[f"col{i+1}_body"], instruction_for(els[f"col{i+1}_body"]))
            write_notes(s, sd)
            continue

        for name, geom in g.items():
            if name.endswith("_head"):
                if name in heads:
                    fill = C["amber"] if name in ("p3_head",) else None
                    chip(s, name, geom, heads[name])
                elif name.startswith("p") and els.get(name[:-5]):
                    chip(s, name, geom, f"Panel {name[1]}")
                continue
            if name == "takeaway" and "takeaway" not in els:
                continue
            if name.startswith("kpi"):
                if "kpis" in els:
                    region(s, name, geom, f"[KPI {name[-1]} - value + label + period]")
                continue
            if name not in els:
                continue
            region(s, name, geom, instruction_for(els[name]))
        write_notes(s, sd)

    prs.save(out)
    print("wrote", out, "slides:", len(prs.slides))


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
