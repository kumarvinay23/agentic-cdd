# Template contract and content.json format

## 1. The fixed template (`assets/cdd_template.pptx`)

* 16:9, 13.333 × 7.5 in; three layouts: `DIQ_COVER`, `DIQ_DIVIDER`, `DIQ_CONTENT` (navy header band,
  "DiligenceIQ" wordmark, footer with project name placeholder `[Project name]` and slide number).
* 48 slides in fixed order (see `02_slide_mapping.md`). Each slide's name (`p:cSld/@name`) is its slide_map id.
* Variable elements are shapes whose **names** equal the element names in `slide_map.yaml`
  (`title`, `subtitle`, `source`, `left`, `right`, `chart`, `table`, `takeaway`, `rows`, `kpi1…kpi4`,
  `q1…q4`, `lead`, `col1_body…col5_body`, `report_title` …). They contain bracketed instruction text that
  QA fails on if it survives.
* Fixed elements (section tags, panel headings `*_head`, workstream headings, disclaimer body, dividers) are
  template-owned. Panel headings may be overridden per slide with `"heads": {"chart_head": "…"}` when the
  default wording would misdescribe the content.
* **Permitted structural changes:** only slides marked `repeatable: true` (S46, S47, S48) may be duplicated,
  by supplying a list of pages in content.json. Unused KPI tiles are removed. Nothing else is added,
  removed or re-ordered. `optional` slides are not used in v1.
* Fonts: Calibri (QA renders with metric-compatible Carlito). Palette in `scripts/template/brand.json`.
* Rebuild after editing slide_map/brand: `node scripts/template/build_masters.js base.pptx && python scripts/template/build_template.py base.pptx assets/cdd_template.pptx`.

### Using a different PowerPoint template
The renderer only needs (1) slide names = slide ids and (2) shape names = element names. To adopt a firm's
own template: rename its slides/shapes to match `slide_map.yaml` (Selection Pane in PowerPoint), save it as
`assets/<name>.pptx`, run `validate_inputs.py --template <file>` (it lists every missing slide/shape), then
pass `--template` to `render_deck.py`. Region shapes should be rectangles sized to the space available –
tables and charts are drawn inside their bounds.

## 2. content.json

```json
{
  "project": {"name": "...", "target": "...", "client": "...", "date": "Month YYYY",
              "status": "Draft for discussion", "footer": "<project> CDD | Draft"},
  "slides": {
    "S09_company_snapshot": {
      "title":    {"text": "...", "refs": ["<evidence id>"], "kind": "interpretation"},
      "subtitle": {"text": "...", "refs": ["<evidence id>"], "kind": "interpretation"},
      "heads":    {"right_head": "optional override"},
      "elements": {
        "left":  {"type": "table", "columns": ["Attribute", "Value", "Source"],
                  "rows": [["Target", "...", "Deal Context"]], "row_refs": [["<evidence id>"]],
                  "col_widths": [1.5, 2.3, 1.4], "pill_cols": [{"col": 2, "scale": "good_high|bad_high|neutral"}]},
        "right": {"type": "chart", "chart_type": "bar|column|stacked_column|stacked_bar|line|doughnut",
                  "categories": ["..."], "series": [{"name": "...", "values": [1.0]}],
                  "number_format": "0.0\"%\"", "value_axis_title": "...", "unit_label": "...",
                  "highlight": 0, "refs": ["..."], "kind": "fact|calc"},
        "takeaway": {"type": "text", "text": "...", "refs": ["..."], "kind": "interpretation"},
        "bul":   {"type": "bullets", "items": [{"text": "**Lead** - detail", "refs": ["..."], "kind": "fact"}]},
        "kpis":  {"type": "kpis", "items": [{"value": "₹<n> cr", "label": "...", "note": "...",
                  "refs": ["..."], "kind": "fact", "rag": "good|med|bad"}]},
        "x":     {"type": "insufficient", "text": "Insufficient evidence - <what is missing>", "refs": ["<NA item>"]}
      }
    },
    "S46_module_verdicts": [ {"title": ..., "elements": {...}}, {"title": ..., "elements": {...}} ]
  },
  "calculations": [{"id": "C11-gross-margin", "formula": "gp / rev * 100",
                    "inputs": {"gp": {"value": 250.0, "ref": "<id>"}, "rev": {"value": 1000.0, "ref": "<id>"}},
                    "output": 25.0, "unit": "%", "rounding": 1, "used_on": ["S36_financial_performance"],
                    "also_shown_as": []}],
  "exceptions":   [{"severity": "CRITICAL|HIGH|MEDIUM|LOW", "issue": "...", "slides": ["S20_market_size"],
                    "source": "evidence ids / check", "treatment": "..."}],
  "metrics":      {"revenue": {"value": "<as shown>", "slides": ["S09_company_snapshot", "S36_financial_performance"]}}
}
```

(The numbers above illustrate the format only; they are not defaults.)

Reference conventions: evidence ids from `evidence.json`; pseudo-refs `RUN:<param>` (run parameters such as
date), `CHECK:<key>` (values computed by scripts into `auto_checks.json`), `CALC` (output of another
calculation). `**bold**` inside text renders as bold. `kind: calc` items and KPI values get a † marker.
