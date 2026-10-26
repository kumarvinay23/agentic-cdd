# Validation findings

What has actually been tested, what the tests showed, and what remains inferred. Rules marked
**[I]** in `03_transformation_rules.md` are design decisions that no completed, human-reviewed
deck has yet confirmed; rules marked **[O]** were observed in a real corpus.

## Run 2 — Compost Crew, September 2026 (current)

**Corpus.** 34 agent modules (v3 / v4 / v7), image-only jsPDF PDFs, ~110 pages, OCR-ingested.
Data room: the Compost Crew VDR, 8 sections, 39 distinct artefacts cited, 35 web citations.
Target template: the 101-slide blueprint (97-page CDD reporting standard + 4-page evidence
appendix).

**Result.** 1,065 evidence items · 62 % coverage · 0 content errors · 0 render overflows ·
0 structural QA findings · 74 of 101 pages rendered (82 physical slides after repeatable
appendix pages) · 16 exceptions.

### What the run established

1. **The module taxonomy had moved.** The corpus carries four modules the v1 registry did not
   know — Executive Summary, Buying Behavior, Sensitivity Analysis, Final Valuation Range — and
   lacks four it expected: Deal Context & Objectives, Company Background, Historical Performance,
   Valuation Model. EXS supersedes DCO and FVR supersedes VAL; CBG and HPF are genuinely missing.
   Registry now at 38 modules with a `supersedes` relation (R8).

2. **Buying Behavior is the module that unlocks a whole section.** Its four sections
   (procurement cycle, purchase drivers, seasonality, switching triggers) map directly onto the
   blueprint's Decision-Making Dynamics section (slides 50–57), which the v1 48-slide deck had
   no home for at all.

3. **Six modules returned a full fact template with every value N/A** — CSA, CSC, CSG, CST, IPT,
   MSS, all at 0 % populated. This is the single most important finding about the data room, and
   it is a *data* finding, not a *business* finding. Rule T15 now states this explicitly:
   an empty template evidences nothing and must never be written up as a negative result.

4. **No primary customer research exists in this data room.** No survey export, no interview
   programme. 24 blueprint slides depend on one or the other. Gating withholds them and names
   them; the alternative — 24 pages of placeholder — would have been worse.

5. **Growth rates do not reconcile.** The CIM claims 45 % and 13 %; the external benchmark gives
   4.01 %. MVG's own "Growth Integrity & Divergence" section flags it. Logged CRITICAL under
   E3-CONFLICT; the CIM claim is shown, not adopted.

6. **Market sizing looks wrong in the source, not in the pipeline.** MVG reports the North
   America waste-management market at $210.31M (2025) rising to $256.00M (2030). For that market
   those magnitudes are implausible — most likely a unit error upstream ($M for $B). The pipeline
   reproduces what the agent said and triangulates it; **a human must resolve this before the
   deck is issued.** It is the clearest example of why T11 shows all values rather than picking one.

7. **Six cited artefacts are not in the data room as named** — the agents read a CIM dated 082426
   while the VDR holds 090126. New rule E10-SOURCE-DRIFT; listed in the source register.

### Defects this run found in the skill itself

| Defect | Fix |
|---|---|
| Duplicating a repeatable slide after gating produced two package parts with the same name; the .pptx would not open in LibreOffice or PowerPoint. | `duplicate_slide` now allocates an explicitly free partname instead of relying on python-pptx's counter. |
| `check_content` treated a gated-out slide as "missing from content.json". | It now reads `gates.json`, skips withheld slides, and instead warns when a withheld slide is not named in any exception. |
| Numbers inside a section heading used as a bullet lead ("Post-Closing 100-Day Action Plan") were reported untraceable. | `evidence_numbers` now also scans the item's section title, label and row label — all printed on the source page. |
| `validate_inputs` demanded `subtitle` / `source` shapes on archetypes that legitimately have neither. | Fixed-title archetypes (cover, back cover, contents, disclaimer, text panel) are exempt. |
| The five-column engagement slide overflowed at any sensible font size. | Per-archetype element limits: narrow columns cap at 4 items × 95 chars. |
| The contents page showed a gap in section numbering when a whole appendix was withheld. | Surviving sections are renumbered contiguously; the withholding is stated in the exceptions instead. |
| KPI tiles only supported four; the blueprint's company snapshot wants five. | `render_kpis` handles five and removes unused tiles. |

## Run 1 — Ola latest, September 2026

51-slide sample deck against the v1 48-slide template, 0 check errors, 15 exceptions, 2 of them
critical (synthetic input data; target perimeter ambiguous between the ride-hailing business and
Ola Electric). Superseded by run 2 but still the only test of the synthetic-data path (E7) and of
the perimeter conflict path (E8).

## Still not validated

* **No input → human-reviewed final deck pair exists.** Every transformation rule remains
  inferred against a real reviewed output. The two runs prove the pipeline is internally
  consistent and traceable; they do not prove the deck says what a CDD partner would have said.
* **T7 confidence bands** (80 / 60 %) and **C6 risk scoring** (impact × likelihood) are chosen,
  not calibrated.
* **Gate thresholds** — `min_facts: 3` for conditional, `min_n: 30` for survey charting — are
  judgement calls. They decide how long the deck is, so they deserve a partner's opinion.
* **The research-gated slides have never rendered.** No corpus with survey or interview sources
  has been run through this template, so the exhibits for slides 51–57, 65–70 and 92–94
  (decision trees, NPS bars, quote walls, case studies) are untested against real content.
* **Workstream names** on the engagement slide are the skill's, not the firm's.
* **The baseline drafter is a floor.** It restates each module's own verdict as an action title.
  It does not synthesise across modules, weigh evidence quality, or say what the IC should do.
  Every title it writes is meant to be rewritten.

## Run 3 — Compost Crew, review findings and fixes (September 2026)

A partner review of the run-2 deck raised five findings. Each is now enforced by code, not by
drafting discipline alone.

| Finding | Root cause | Fix (where) |
|---|---|---|
| Numbers mis-extracted; charts mixed units, plotted citation markers and file-name digits, lost forecast labels | Drafter took the first digit run in a cell | `lib/values.py` typed parser (unit, scale, per-unit, range, missing, forecast, sign before `$`); `vdr_extract.py` column-unit rules and sub-header blocks (`MODEL_BASIS`); `chart_audit` checks every point against its cell (`point_refs`) — T19 |
| No financial foundation; FY2030 ambition presented as if it were the business | Agents' HPF/CBG modules were empty; the data room was never read directly | `vdr_extract.py` reads the monthly P&L (annual actuals, TTM, YTD vs PY), segment plan, ARR, unit economics, cohorts, concentration, market model, ZIP scoring and the CIM crosswalk; T17 keeps actual and plan apart — R9 |
| Core commercial exhibits missing (market model, retention, competitors, growth levers) | Pages built only from agent text | Analyst pass (`analyst_content.py` pattern) builds segment × territory TAM/SAM/SOM, retention actual vs plan, named competitors from dated web research (`add_research.py`, R10) and a quantified lever table |
| Unsupported "Invest", "High moat", "competitive pricing" | Agent verdicts copied as findings | `claim_rules.yaml` grades + `claim_strength` check — T16; agent errors logged as E14 |
| Repetition and unfinished pages (duplicate competitor/synergy tables, empty glossary, "[Engagement contacts…]", "…" cut-offs) | No repetition or completeness checks; mechanical `wcut` | `repetition`, `truncation`, `completeness` checks; `content.withhold` + E13; `finalize_content.py` rebuilds exceptions, glossary, verdicts and register from the final deck with balanced pages; dividers, appendix letters and back cover renumbered by the renderer — T18 |

What the data room changed in the Compost Crew findings:

* **Actuals** (QBO): revenue $7.56M / $11.87M / $13.41M (2023–25), +3.0% YTD Jul-2026; EBITDA
  4.3% in 2025. The plan's $50.17M 2030P needs a 30.4% CAGR.
* **Agent errors rejected:** market size ($256M "North America waste" — a $B figure for another
  market), competitor list (own brand, subcontractor, acquisitions), "Proceed/Invest" on a 45%
  CAGR the model does not contain.
* **Data quality found by extraction:** duplicate top-20 commercial account; 2,071 government
  households double-counted in the Stripe residential count; QBO vs model 2025 revenue gap;
  model retention above 2025 actuals.

Still open: no primary research (24 pages withheld under E11); no municipal market sizing beyond
the DC contract; no sales-productivity history; the full VDR (non-workbook documents) was not
inventoried in this run, so some agent-cited files could not be resolved to their real names.

### Run 3 partner rating (v3 deck, 55 slides): 6.5 / 10

Evidence and traceability 9 · financial foundation 8 · growth 7 · customers 6 · design 6 ·
storyline 5 · market 5 · competition 5 · structure 5. Strong fact base; not yet IC-ready because it
tests the plan without offering a diligence case, puts the answer on slide 16, sizes the market
only from the company model (no regulation driver, municipal unsized), has no customer voice, and
spends ~18% of pages on the audit appendix. Codified as T20–T22, the IC-readiness section of
SKILL.md, the `ic_readiness` checks, waterfall charts, small-label suppression on stacked charts
and glossary-at-back. The Compost Crew example still carries the two open warnings (no diligence
case; long titles) because the diligence case needs a partner's judgement on the adjustments.

## Run 4 — diligence-control review (C1–C6) and generalisation

The skill was made deal-agnostic (generic extraction recipes plus a fallback; deal specifics moved
to `examples/compost_crew/`) and six diligence controls were added. Applied to the Compost Crew
deck they found and corrected: a DC run-rate that multiplied 2026 homes by 2030 prices ($4.17M →
$3.18M on H1 billings); "contracted" language for a one-firm-year option contract that had not been
reviewed; a plan multiple and a penetration ratio on mixed bases; model retention (per location)
compared with actual retention (per account / subscription); customer metrics graded "established"
on a management-prepared workbook; Agricity's "+$1.5M EBITDA" combining ~$0.59M of acquired
earnings with a gross synergy. Reconciliation traced the 1% ledger-vs-model revenue gap to
"Other revenue" and exposed a ~$0.12M unexplained cost offset. 18 reviewed issues, six P1.
