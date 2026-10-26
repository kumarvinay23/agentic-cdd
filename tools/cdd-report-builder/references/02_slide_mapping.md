# Slide-by-slide mapping specification

_Generated from `config/slide_map.yaml` by `scripts/export_mapping.py` — edit the YAML, not this file._

101 slides: the 97-page CDD reporting blueprint plus a DiligenceIQ evidence-and-audit appendix.

Each slide carries two contracts. The **blueprint contract** (purpose, must contain, sources, analysis, exhibit, quality bar) is what the page owes the reader. The **mapping** is how this skill satisfies it from agent outputs: which modules feed it, which metrics it may state, which rules govern the transformation, and the coverage **gate** that decides whether the page can be produced at all.

Evidence rule for every element: every text unit, bullet and table row carries `refs` to evidence ids (`MOD-sec-kind-row`); the renderer builds the source line and a speaker-note evidence trail; calculated values carry † and a calculation id.

## Index

| # | Slide | Section | Gate | Exhibit | Primary modules |
|---|---|---|---|---|---|
| 01 | `S001_cover` | Engagement Overview | always | cover | — |
| 02 | `S002_disclaimer` | Engagement Overview | always | text_panel | — |
| 03 | `S003_engagement` | Engagement Overview | core | banded_table | SCM |
| 04 | `S004_contents` | Engagement Overview | derived | text_panel | — |
| 05 | `S005_research_approach` | Engagement Overview | core | banded_table | SCM |
| 06 | `S006_survey_sample` | Engagement Overview | research_gated | stacked_bar | SCM |
| 07 | `S007_glossary` | Engagement Overview | derived | text_panel | — |
| 08 | `S008_div_business` | Business Introduction & Market Primer | always | divider | — |
| 09 | `S009_company_snapshot` | Business Introduction & Market Primer | core | kpi_strip | CBG, HPF |
| 10 | `S010_platform_evolution` | Business Introduction & Market Primer | conditional | lifecycle_flow | CBG, STR |
| 11 | `S011_value_chain` | Business Introduction & Market Primer | core | banded_table | MDF |
| 12 | `S012_business_model_flow` | Business Introduction & Market Primer | core | lifecycle_flow | CBG, MDF |
| 13 | `S013_business_model_comparison` | Business Introduction & Market Primer | conditional | scorecard | CDF, CID |
| 14 | `S014_model_scorecard` | Business Introduction & Market Primer | research_gated | scorecard | BBH, CDF |
| 15 | `S015_barriers` | Business Introduction & Market Primer | conditional | banded_table | CDF, IPT |
| 16 | `S016_pain_points` | Business Introduction & Market Primer | conditional | banded_table | CDF, CSA |
| 17 | `S017_roadmap` | Business Introduction & Market Primer | conditional | lifecycle_flow | STR, GRO |
| 18 | `S018_industry_trends` | Business Introduction & Market Primer | core | banded_table | MDF, DDR |
| 19 | `S019_div_highlights` | Investment Highlights | always | divider | — |
| 20 | `S020_highlights_summary` | Investment Highlights | derived | banded_table | EXS, REC |
| 21 | `S021_h1_market_size` | Investment Highlights | core | walkdown | MVG |
| 22 | `S022_h1_sam_walkup` | Investment Highlights | conditional | walkup | MVG, GRO |
| 23 | `S023_h1_growth_drivers` | Investment Highlights | core | banded_table | DDR, MVG |
| 24 | `S024_h1_recession` | Investment Highlights | conditional | line_series | MRK |
| 25 | `S025_h2_demand_alignment` | Investment Highlights | research_gated | scorecard | DDR, BBH |
| 26 | `S026_h2_lifecycle_fit` | Investment Highlights | research_gated | lifecycle_flow | CST, BBH |
| 27 | `S027_h3_satisfaction` | Investment Highlights | research_gated | nps_bar | CSA |
| 28 | `S028_h4_incumbent_dissatisfaction` | Investment Highlights | research_gated | grouped_bar | CSA, CID |
| 29 | `S029_h4_differentiation` | Investment Highlights | core | scorecard | CDF |
| 30 | `S030_h4_full_suite` | Investment Highlights | research_gated | grouped_bar | GRO, CDF |
| 31 | `S031_h5_growth_levers` | Investment Highlights | core | banded_table | GRO |
| 32 | `S032_div_market` | Market Dynamics & Opportunity | always | divider | — |
| 33 | `S033_icp_mapping` | Market Dynamics & Opportunity | conditional | heat_grid | CSG |
| 34 | `S034_market_definitions` | Market Dynamics & Opportunity | core | banded_table | MDF |
| 35 | `S035_volume_narrowing` | Market Dynamics & Opportunity | conditional | walkdown | MVG, MDF |
| 36 | `S036_volume_by_channel` | Market Dynamics & Opportunity | conditional | stacked_bar | MVG, MSS |
| 37 | `S037_tam_walkdown` | Market Dynamics & Opportunity | core | walkdown | MVG, MDF |
| 38 | `S038_sam_by_endmarket` | Market Dynamics & Opportunity | conditional | stacked_bar | MVG, MSS |
| 39 | `S039_value_added_services` | Market Dynamics & Opportunity | conditional | banded_table | GRO, MPR |
| 40 | `S040_growth_factors_overview` | Market Dynamics & Opportunity | core | banded_table | DDR, MVG |
| 41 | `S041_gf1_demand` | Market Dynamics & Opportunity | conditional | line_series | DDR |
| 42 | `S042_gf2_mix_shift` | Market Dynamics & Opportunity | conditional | stacked_bar | DDR, CSG |
| 43 | `S043_gf3_channel_adoption` | Market Dynamics & Opportunity | research_gated | line_series | MSS, DDR |
| 44 | `S044_gf3_channel_stickiness` | Market Dynamics & Opportunity | research_gated | nps_bar | CST, MSS |
| 45 | `S045_gf4_pricing_stability` | Market Dynamics & Opportunity | conditional | line_series | MPR |
| 46 | `S046_sam_growth_build` | Market Dynamics & Opportunity | conditional | walkup | MVG |
| 47 | `S047_scenario_analysis` | Market Dynamics & Opportunity | conditional | scenario_table | SNS |
| 48 | `S048_downturn_resilience` | Market Dynamics & Opportunity | conditional | line_series | MRK, SNS |
| 49 | `S049_risk_assessment` | Market Dynamics & Opportunity | core | risk_matrix | MRK, IRK |
| 50 | `S050_div_decisions` | Decision-Making Dynamics | always | divider | — |
| 51 | `S051_partner_switching_lifecycle` | Decision-Making Dynamics | research_gated | lifecycle_flow | BBH, SUP |
| 52 | `S052_switching_drivers` | Decision-Making Dynamics | conditional | banded_table | BBH, CST |
| 53 | `S053_decision_tree` | Decision-Making Dynamics | research_gated | decision_tree | BBH |
| 54 | `S054_decision_process` | Decision-Making Dynamics | conditional | heat_grid | BBH, CSG |
| 55 | `S055_purchase_criteria` | Decision-Making Dynamics | conditional | scorecard | BBH, CSG |
| 56 | `S056_vertical_needs` | Decision-Making Dynamics | research_gated | heat_grid | CSG, BBH |
| 57 | `S057_switching_complexity` | Decision-Making Dynamics | conditional | heat_grid | CST, BBH |
| 58 | `S058_div_competition` | Competitive Landscape | always | divider | — |
| 59 | `S059_routes_to_market` | Competitive Landscape | conditional | lifecycle_flow | MSS, CID |
| 60 | `S060_competitor_archetypes` | Competitive Landscape | core | banded_table | CID |
| 61 | `S061_positioning_map` | Competitive Landscape | core | positioning_map | CID, CDF |
| 62 | `S062_criteria_vs_archetypes` | Competitive Landscape | conditional | scorecard | CDF, CID |
| 63 | `S063_feature_benchmarking` | Competitive Landscape | conditional | heat_grid | CDF, IPT |
| 64 | `S064_price_benchmarking` | Competitive Landscape | conditional | grouped_bar | MPR, CID |
| 65 | `S065_incumbent_nps` | Competitive Landscape | research_gated | nps_bar | CSA |
| 66 | `S066_competitor_painpoints` | Competitive Landscape | conditional | banded_table | CID, CDF |
| 67 | `S067_full_suite_wtp` | Competitive Landscape | research_gated | grouped_bar | GRO, MPR |
| 68 | `S068_churn_triggers` | Competitive Landscape | conditional | banded_table | CST, CSA |
| 69 | `S069_target_strengths` | Competitive Landscape | research_gated | quote_wall | CSA, CDF |
| 70 | `S070_target_development_areas` | Competitive Landscape | research_gated | quote_wall | CSA, SWO |
| 71 | `S071_div_growth` | Growth Opportunities | always | divider | — |
| 72 | `S072_growth_levers_overview` | Growth Opportunities | core | banded_table | GRO |
| 73 | `S073_l1_new_customers` | Growth Opportunities | conditional | walkup | GRO, MSS |
| 74 | `S074_l1_right_to_win` | Growth Opportunities | conditional | scorecard | MSS, CDF |
| 75 | `S075_l1_channel_expansion` | Growth Opportunities | conditional | banded_table | MSS, GRO |
| 76 | `S076_l2_partner_whitespace` | Growth Opportunities | research_gated | heat_grid | GRO, SUP |
| 77 | `S077_l2_partner_willingness` | Growth Opportunities | research_gated | grouped_bar | GRO, SUP |
| 78 | `S078_l2_partner_scaling` | Growth Opportunities | research_gated | banded_table | GRO, SUP |
| 79 | `S079_l3_expand_accounts` | Growth Opportunities | conditional | walkup | CST, RVQ |
| 80 | `S080_l4_pricing` | Growth Opportunities | conditional | banded_table | MPR, RVQ |
| 81 | `S081_l5_adjacent_segments` | Growth Opportunities | conditional | scorecard | GRO, MDF |
| 82 | `S082_l6_product_expansion` | Growth Opportunities | conditional | banded_table | IPT, GRO |
| 83 | `S083_l7_ma` | Growth Opportunities | conditional | banded_table | SYN, STR |
| 84 | `S084_div_appx_partners` | Appendix A - Partner & Vendor Landscape | always | divider | — |
| 85 | `S085_landscape_by_category` | Appendix A - Partner & Vendor Landscape | conditional | banded_table | CID |
| 86 | `S086_landscape_by_size` | Appendix A - Partner & Vendor Landscape | conditional | banded_table | CID |
| 87 | `S087_partner_counts` | Appendix A - Partner & Vendor Landscape | research_gated | banded_table | SUP, CST |
| 88 | `S088_div_appx_sizing` | Appendix B - Market Sizing Methodology | always | divider | — |
| 89 | `S089_sizing_method_core` | Appendix B - Market Sizing Methodology | core | method_flow | MVG, MDF |
| 90 | `S090_sizing_method_adjacent` | Appendix B - Market Sizing Methodology | conditional | method_flow | MVG, GRO |
| 91 | `S091_div_appx_cases` | Appendix C - Case Studies | always | divider | — |
| 92 | `S092_case_lost_prospect` | Appendix C - Case Studies | research_gated | case_study | BBH, CSA |
| 93 | `S093_case_competitor_customer` | Appendix C - Case Studies | research_gated | case_study | CID, CSA |
| 94 | `S094_case_existing_customer` | Appendix C - Case Studies | research_gated | case_study | CSA, CST |
| 95 | `S095_div_appx_supp` | Appendix D - Supplementary Data | always | divider | — |
| 96 | `S096_supp_entrenchment` | Appendix D - Supplementary Data | research_gated | heat_grid | CST |
| 97 | `S097_back_cover` | Appendix D - Supplementary Data | always | cover | — |
| 98 | `S098_div_appx_audit` | Appendix E - Evidence & Audit Trail | always | divider | — |
| 99 | `S099_module_verdicts` | Appendix E - Evidence & Audit Trail | always | banded_table | — |
| 100 | `S100_source_register` | Appendix E - Evidence & Audit Trail | always | banded_table | — |
| 101 | `S101_exceptions` | Appendix E - Evidence & Audit Trail | always | banded_table | — |

## 01 · S001_cover — Cover Page
_Engagement Overview · archetype `cover` · exhibit `cover` · gate **always**_

**Purpose** — Identify the engagement, the parties, and confidentiality status at a glance.

**Must contain**
- Project codename ('Project [X]'), engagement type (sell-side / buy-side support) and report status (Draft / Final).
- Advisory team with named leads and contact details; client identified per the engagement letter.
- Date of issue and a clear CONFIDENTIAL designation in the top corner.
- Clean, brand-led layout — no findings, data, or claims on the cover.

**Admissible sources** — Engagement letter / SOW; deal-team roster; client naming conventions.
**Analysis** — None — purely identifying. Confirm codename and permitted recipients with the client first.
**Exhibit** — Full-bleed branded cover: title block + team block, no data.
**Quality bar** — Confirm the confidentiality designation and approved recipient list before any draft circulates.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `report_title` | text | — | {'max_chars': 320} |
| `report_subtitle` | text | — | {'max_chars': 320} |
| `prepared_for` | text | — | {'max_chars': 320} |
| `report_date` | text | — | {'max_chars': 320} |

## 02 · S002_disclaimer — Disclaimer & Reliance Limitations
_Engagement Overview · archetype `disclaimer` · exhibit `text_panel` · gate **always**_

**Purpose** — Define scope, reliance, and the limits of assurance before any finding is read.

**Must contain**
- State the report was prepared for the named client, on topics the client identified, using only the procedures the client requested.
- Clarify the report provides no assurance and is subject to limitations; recipients accept its scope.
- Set third-party terms: recipients must perform their own diligence and acquire no rights against the advisor.
- Prohibit redistribution except by legal process, with indemnification language for downstream claims.

**Admissible sources** — Firm legal / risk template; reliance language from the engagement letter.
**Analysis** — None — legal boilerplate tailored to scope; route new client types or geographies through legal review.
**Exhibit** — Text-only bullet slide, kept identical across every report.
**Quality bar** — Never soften reliance language to please a prospective buyer — disclaimer scope creep is a liability.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T1-EXTRACT, T12-COMPANY-VS-MARKET, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `disclaimer_body` | text | — | {'max_chars': 1500} |
| `data_notice` | text | — | {'max_chars': 420} |

## 03 · S003_engagement — Engagement Overview & Objectives
_Engagement Overview · archetype `columns5` · exhibit `banded_table` · gate **core**_

**Purpose** — State the mandate in one sentence and decompose it into the five diligence workstreams.

**Must contain**
- Action title naming what the client engaged the firm to assess (market opportunity, customer sentiment, competitive positioning, growth avenues).
- A 'Primary Objectives' strip summarising the mandate in one full sentence.
- Five numbered workstreams — Business Primer · Market Dynamics & Opportunity · Customer Dynamics & Feedback · Competitive Landscape & Positioning · Growth Opportunities.
- Three to five scope bullets under each workstream stating exactly what will be assessed, defined, or validated.

**Admissible sources** — Kick-off materials; the sponsor's underwriting questions and stated IC concerns.
**Analysis** — Translate the buyer's underwriting questions into testable workstreams and scope bullets.
**Exhibit** — Objectives banner + five-column workstream grid with scope bullets.
**Quality bar** — Objectives must mirror the buyer's actual decision criteria — not a generic checklist.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | SCM |
| Fallback modules | EXS, REC — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | EXS, DCO |
| Transformation rules | T1-EXTRACT, T12-COMPANY-VS-MARKET, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `lead` | text | — | {'max_chars': 320} |
| `col1_body` | bullets | — | {'max_items': 4, 'max_chars_item': 95} |
| `col2_body` | bullets | — | {'max_items': 4, 'max_chars_item': 95} |
| `col3_body` | bullets | — | {'max_items': 4, 'max_chars_item': 95} |
| `col4_body` | bullets | — | {'max_items': 4, 'max_chars_item': 95} |
| `col5_body` | bullets | — | {'max_items': 4, 'max_chars_item': 95} |

## 04 · S004_contents — Contents
_Engagement Overview · archetype `contents` · exhibit `text_panel` · gate **derived**_

**Purpose** — Give the reader a two-level map of the report with page references.

**Must contain**
- Top-level sections in reading order: Engagement Overview · Business Introduction & Market Primer · Investment Highlights · Detailed Findings · Appendix.
- Detailed Findings expanded into its four workstream chapters, each with its page number.
- Appendix expanded into its lettered parts (landscape, sizing methodology, case studies, supplementary data).
- Page references verified against final pagination.

**Admissible sources** — Final deck pagination.
**Analysis** — None — navigation only.
**Exhibit** — Two-level indented contents list with right-aligned page numbers.
**Quality bar** — Section titles and page numbers must match the dividers and footers exactly.
**Gate** — derived: built from run data

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `contents_body` | auto | — | — |

## 05 · S005_research_approach — Research Approach & Interview Sample
_Engagement Overview · archetype `table_commentary` · exhibit `banded_table` · gate **core**_

**Purpose** — Show the evidence base — how many conversations, of what type, from which perspectives.

**Must contain**
- Statement that findings combine primary research (interviews, survey) with secondary data analysis, and what the interviews focused on.
- Phone interview table by interviewee type (target customers, competitor customers, competitors, partners) with counts and total [n = X].
- Survey sample table by respondent type with counts and total [n = X].
- Logo wall of organizations interviewed (anonymise where required).

**Admissible sources** — Interview tracker; survey-platform export; primary-research logs.
**Analysis** — Report every n transparently; note the sample is built for triangulation, not statistical precision.
**Exhibit** — Two count tables + interviewed-organizations logo wall.
**Quality bar** — Disclose every sample size — findings from a handful of calls must never be dressed as consensus.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | SCM |
| Fallback modules | EXS, APX — use raises E12-SUBSTITUTION and must be stated on the slide |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Evidence base by source type | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Coverage, limitations and what was not available | {'max_items': 5, 'max_chars_item': 170} |

## 06 · S006_survey_sample — Survey Sample Distribution
_Engagement Overview · archetype `chart_commentary` · exhibit `stacked_bar` · gate **research_gated**_

**Purpose** — Break the survey base down by respondent type, size, and industry so cuts can be judged.

**Must contain**
- 100% stacked bars for the overall respondent-type split, firm-size mix within each type, and industry mix.
- A multi-select horizontal bar for focus industries served by one respondent group (sums >100%).
- The n beneath every column so each cut can be evaluated independently.
- Survey field dates and method noted in the source line.

**Admissible sources** — Web-survey export.
**Analysis** — Check sample representativeness against the target's ICP; flag skews before findings are generalised.
**Exhibit** — Three 100% stacked columns + one multi-select bar panel, all with n labels.
**Quality bar** — Any sample skew acknowledged here — not discovered by the IC later.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | SCM |
| Secondary modules | CSG |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Survey sample by segment (n) | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Sampling approach and representativeness | {'max_items': 5, 'max_chars_item': 170} |

## 07 · S007_glossary — Glossary
_Engagement Overview · archetype `table_full` · exhibit `text_panel` · gate **derived**_

**Purpose** — Standardise the specialist language the rest of the report depends on.

**Must contain**
- Two-column table: key term | plain-English description, one row per term.
- Cover the industry value chain roles, the target's model-specific terms, and adjacent provider archetypes.
- Include sizing and metric definitions used later: TAM, SAM, served market, gross vs net revenue, volume metrics.
- Order terms from ecosystem roles to metrics so the table reads as a primer.

**Admissible sources** — Industry references; management materials; firm's standard definitions.
**Analysis** — None — alignment only; ensure definitions match how terms are used in the body.
**Exhibit** — Clean term / description table.
**Quality bar** — Every specialist term used later in the deck appears here first.
**Gate** — derived: built from run data

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO, T10-NARRATIVE-TO-TABLE, T2-COMBINE, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 10, 'max_cols': 2, 'max_chars_cell': 140} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 08 · S008_div_business — Section Divider — Business Introduction & Market Primer
_Business Introduction & Market Primer · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Signal the start of the primer chapter with the standard divider design.

**Must contain**
- Section title only, on the firm's standard divider layout.
- Consistent branding (logo, tagline, copyright) identical across all dividers.
- No findings or data on divider pages.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Full-bleed branded section divider.
**Quality bar** — Divider titles must match the contents page word-for-word.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 09 · S009_company_snapshot — Company Overview & Financial Snapshot
_Business Introduction & Market Primer · archetype `kpi_panel` · exhibit `kpi_strip` · gate **core**_

**Purpose** — Introduce the Target's model, scale, and trajectory on a single page.

**Must contain**
- Action title stating the growth story and the strategic shift under way; sub-line giving the forward implication.
- Revenue bar chart (last 2–3 fiscal years + budget year) with CAGR callout and 1–2 interpretation bullets.
- Company description bullets: what it does, proprietary technology, focus verticals, headline profitability with YoY growth.
- Stat rail: revenue, volume processed / delivered, customer count, founding year, headquarters.
- End-market mix pie and go-to-market channel split for the most recent period.

**Admissible sources** — Management accounts / CIM; KPI pack; QofE where available.
**Analysis** — Reconcile revenue and EBITDA to QofE; recompute CAGR; verify mix splits against management data.
**Exhibit** — Revenue bars + stat rail + end-market pie + channel donut.
**Quality bar** — Every figure on this page ties to management data or QofE — no marketing numbers.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | CBG, HPF |
| Fallback modules | EXS, RVQ, CSC, CFL, CAP — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | RVQ, CAP, MGQ, CFL, CSC, EXS, CSG |
| Metrics this slide may state | `fin.revenue`, `fin.revenue_growth`, `fin.ebitda_margin`, `cust.count`, `ops.headcount` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T3-SUMMARISE, T5-CALCULATE, T6-CONCLUDE, T8-FACT-VS-VIEW |
| Calculations | C11-MARGIN, C4-MIX |
| Source priority | R1, R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `kpis` | kpis | — | {'max_items': 5, 'max_chars_item': 42} |
| `left` | bullets | Key facts | {'max_items': 5, 'max_chars_item': 170} |
| `right` | chart | Revenue mix and financial trajectory | {'max_series': 3, 'max_points': 8} |

## 10 · S010_platform_evolution — Platform Evolution & Acquisition Integration
_Business Introduction & Market Primer · archetype `flow_row` · exhibit `lifecycle_flow` · gate **conditional**_

**Purpose** — Show how acquisitions and organic build created today's differentiated platform.

**Must contain**
- Timeline of acquisitions and organic build phases with dates and the capability each added.
- Capability inventory grouped by product family (vertical features, segment-specific processing, partner APIs, value-added services), marked non-exhaustive.
- Before / after right-to-win schematic: capabilities pre-acquisition vs the differentiated model today.
- Closing statement of how the evolution increased right-to-win across channels and end-markets.

**Admissible sources** — Management information; management and market interviews.
**Analysis** — Link each acquisition to the specific capabilities and customer segments it unlocked.
**Exhibit** — Timeline + capability grid + before/after panel.
**Quality bar** — 'Differentiated' claims trace to named capabilities — not asserted.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CBG, STR |
| Secondary modules | SYN, IPT |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | How the platform was built | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Integration record and what it implies | {'max_items': 5, 'max_chars_item': 170} |

## 11 · S011_value_chain — Value Chain & Stakeholder Map
_Business Introduction & Market Primer · archetype `table_full` · exhibit `banded_table` · gate **core**_

**Purpose** — Orient the reader: who does what in this industry, and where the Target sits.

**Must contain**
- Stakeholder table grouped into three bands: infrastructure providers, competitors, customers.
- One row per stakeholder type with example providers (logos) and a 1–2 line description of the role.
- The Target's archetype row visually distinguished within the competitor band.
- Descriptions written for a reader new to the industry.

**Admissible sources** — Secondary research; expert interviews.
**Analysis** — Position the Target precisely; make competitor vs supplier vs customer unambiguous.
**Exhibit** — Banded stakeholder table with logo cells and role descriptions.
**Quality bar** — A generalist IC member can navigate the rest of the report from this page alone.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MDF |
| Fallback modules | CSG, CID, SUP — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | SUP, CSG, CID |
| Metrics this slide may state | `mkt.definition` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 12 · S012_business_model_flow — Business Model Routes & Value-Chain Flow
_Business Introduction & Market Primer · archetype `flow_row` · exhibit `lifecycle_flow` · gate **core**_

**Purpose** — Map the numbered routes customers take to the service — and which the Target addresses.

**Must contain**
- Value-chain schematic with numbered routes (direct to infrastructure, via traditional intermediary, via the Target's model, via the incumbent alternative).
- Detail panel explaining each numbered route: who uses it, why, and its economics and trade-offs.
- Markers showing which routes are addressable to the Target, including legacy / resale offerings.
- Sub-line stating the structural takeaway about the Target's differentiated route.

**Admissible sources** — Expert interviews; secondary research; management materials.
**Analysis** — Locate the Target's addressability by route; identify structural advantages per route.
**Exhibit** — Flow diagram with numbered routes + matching numbered detail column.
**Quality bar** — Every route drawn on the diagram has a corresponding detail entry — no orphan arrows.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | CBG, MDF |
| Fallback modules | EXS, RVQ, MSS — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | RVQ, MSS |
| Metrics this slide may state | `fin.revenue_mix` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C11-MARGIN, C4-MIX |
| Source priority | R1, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Route to market, end to end | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Where value is captured | {'max_items': 5, 'max_chars_item': 170} |

## 13 · S013_business_model_comparison — Business Model Comparison
_Business Introduction & Market Primer · archetype `table_full` · exhibit `scorecard` · gate **conditional**_

**Purpose** — Contrast the Target's model with the two incumbent archetypes it must beat.

**Must contain**
- Three side-by-side schematics: incumbent model A, the Target's model, incumbent model B.
- Callout annotations on each schematic explaining flexibility, control, and integration differences.
- Strengths and weaknesses lists under each model, written from the customer's perspective.
- Title asserting what the Target's model uniquely combines from the other two.

**Admissible sources** — Management information; expert and customer interviews.
**Analysis** — Contrast architecture, economics, and service posture; isolate the genuine combination advantage.
**Exhibit** — Three-panel model schematic with strengths / weaknesses blocks.
**Quality bar** — Comparison built on customers' selection criteria — not the Target's marketing deck.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CDF, CID |
| Secondary modules | MDF, MPR |
| Metrics this slide may state | `comp.archetypes` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 14 · S014_model_scorecard — Model Scorecard vs Customer Selection Criteria
_Business Introduction & Market Primer · archetype `table_full` · exhibit `scorecard` · gate **research_gated**_

**Purpose** — Score each model against what customers actually weigh — and read off right-to-win.

**Must contain**
- Matrix rows = selection considerations (risk / liability, revenue model, technical flexibility, branding control, onboarding speed).
- Columns = the competing models, each cell rated (most / more / less favourable) with a one-line rationale.
- Right-to-win impact gauges by customer segment for each consideration.
- Implications column translating each row into a consequence for the Target.

**Admissible sources** — Web survey; expert and customer interviews.
**Analysis** — Score each model per criterion from evidence; convert scores into segment-level right-to-win.
**Exhibit** — Criteria × model matrix with favourability ratings, impact gauges, implications rail.
**Quality bar** — Each rating supported by at least one interview or survey datapoint.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | BBH, CDF |
| Secondary modules | CSA |
| Metrics this slide may state | `cust.purchase_criteria` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 15 · S015_barriers — Structural Barriers to Replication
_Business Introduction & Market Primer · archetype `two_panel` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Argue why incumbents cannot copy the Target's proposition — from economics, not hope.

**Must contain**
- Two panels, one per incumbent archetype, each listing 2–3 structural barriers (technology model, cost structure, historical positioning, channel conflict).
- A short explanation under each barrier of why it is structural rather than a current-state gap.
- Synthesis banner per archetype stating the conclusion in one sentence.

**Admissible sources** — Expert interviews; secondary research.
**Analysis** — Stress-test each barrier: what investment or pivot would erode it, and how likely is that?
**Exhibit** — Two-column barrier panels + synthesis banners.
**Quality bar** — 'Cannot replicate' is argued from business-model economics — never merely asserted.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CDF, IPT |
| Secondary modules | MSS, RCO |
| Metrics this slide may state | `comp.barrier` |
| Transformation rules | T1-EXTRACT, T12-COMPANY-VS-MARKET, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | bullets | Structural barriers | {'max_items': 5, 'max_chars_item': 170} |
| `right` | bullets | Durability and what would erode them | {'max_items': 5, 'max_chars_item': 170} |

## 16 · S016_pain_points — Incumbent Pain Points vs Target Value Proposition
_Business Introduction & Market Primer · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Pair every incumbent weakness with the Target capability that exploits it — and prove it with quotes.

**Must contain**
- Numbered pain points with the dominant incumbent model (cost, inflexibility, missing vertical depth, weak support).
- The matching Target value proposition beside each pain point.
- Verbatim market commentary for each pair, quoted with the speaker's role and organisation type.
- Sub-line framing the displacement opportunity this creates.

**Admissible sources** — Competitor, customer, and churned-account interviews.
**Analysis** — Map each pain point to a verified Target capability; let the market's own words carry the claim.
**Exhibit** — Three-column layout: pain point → value proposition → supporting quote.
**Quality bar** — Every pain point is paired with a real, attributed quote — no orphan claims.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CDF, CSA |
| Secondary modules | CID, BBH |
| Metrics this slide may state | `comp.differentiation` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Incumbent pain point vs target response | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Strength of the evidence | {'max_items': 5, 'max_chars_item': 170} |

## 17 · S017_roadmap — Platform Roadmap Beyond the Core
_Business Introduction & Market Primer · archetype `flow_row` · exhibit `lifecycle_flow` · gate **conditional**_

**Purpose** — Show how the platform evolves from product to infrastructure — and label plans as plans.

**Must contain**
- Current capability inventory grouped by product area (onboarding, core service, value-added solutions, partner tooling).
- Planned extensions per area in a parallel 'to evolve into' column.
- Framing line: the platform becomes infrastructure that lets customers scale, monetise, and differentiate.
- Monetisation implications of each extension noted briefly.

**Admissible sources** — Management roadmap; product materials; market interviews.
**Analysis** — Assess roadmap credibility and sequencing against evidence of market demand.
**Exhibit** — Two-column now → next capability map by product area.
**Quality bar** — Roadmap items are clearly labelled as plans, never blended with current capability.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | STR, GRO |
| Secondary modules | IPT |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Roadmap beyond the core | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Feasibility and dependencies | {'max_items': 5, 'max_chars_item': 170} |

## 18 · S018_industry_trends — Industry Trends & Implications
_Business Introduction & Market Primer · archetype `table_commentary` · exhibit `banded_table` · gate **core**_

**Purpose** — Close the primer with the structural tailwinds and headwinds that frame the thesis.

**Must contain**
- Three to five industry trends, each with a 2–3 sentence description grounded in market evidence.
- Degree-of-impact rating per trend (high / medium) with a one-line justification.
- An explicit impact / implication statement for the Target on every trend.
- Trends chosen because they bear on the investment thesis — not generic sector commentary.

**Admissible sources** — Expert interviews; secondary research.
**Analysis** — Rate impact and direction; connect each trend to a specific Target lever or risk.
**Exhibit** — Trend table: trend | description | impact chip + implication.
**Quality bar** — Every trend ends in a so-what for the Target; no trend is decoration.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MDF, DDR |
| Fallback modules | MRK, RCO, GRO — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MRK, RCO, ESG |
| Metrics this slide may state | `mkt.demand_driver` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Trend and its implication | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Net read for the target | {'max_items': 5, 'max_chars_item': 170} |

## 19 · S019_div_highlights — Section Divider — Investment Highlights
_Investment Highlights · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Signal the synthesis chapter — the case the IC can stop after.

**Must contain**
- Section title only, on the standard divider layout.
- Consistent branding identical to other dividers.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Full-bleed branded section divider.
**Quality bar** — Divider title matches the contents page word-for-word.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 20 · S020_highlights_summary — Investment Highlights Summary
_Investment Highlights · archetype `numbered_rows` · exhibit `banded_table` · gate **derived**_

**Purpose** — The whole case on one page — written last, placed first.

**Must contain**
- One banner row per workstream, numbered 1–5 (market · decision-making · customer feedback · competitive positioning · growth).
- Two to three bolded highlight statements per row, each followed by its supporting clause.
- Quantified claims carry their key figures (market size, growth rate, satisfaction metrics) inline.
- Action title synthesising the transformation story and why dynamics favour the Target.

**Admissible sources** — The detailed findings sections of this report.
**Analysis** — Distil each workstream to its 2–3 most defensible claims; cut anything not proven later.
**Exhibit** — Numbered highlight banner, one row per workstream.
**Quality bar** — The IC can stop here and know the answer — and every claim traces to a findings page.
**Gate** — derived: built from run data

| Mapping | Value |
|---|---|
| Primary modules | EXS, REC |
| Secondary modules | SWO, DCO |
| Transformation rules | T0-AUTO, T10-NARRATIVE-TO-TABLE, T2-COMBINE, T3-SUMMARISE, T6-CONCLUDE, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `rows` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |

## 21 · S021_h1_market_size — Highlight 1 — Market Size (TAM / SAM / Served)
_Investment Highlights · archetype `chart_commentary` · exhibit `walkdown` · gate **core**_

**Purpose** — Establish the headline opportunity: how big, how serviceable, how contested.

**Must contain**
- Opportunity pyramid: TAM, SAM, and served market with $ values and component splits (core + adjacent offering).
- Segmented bar of the opportunity by customer size band, with channel mix inside each band.
- Opportunity definition strip stating what the TAM captures and at what economics.
- Workstream number chip tying the page to Highlight 1.

**Admissible sources** — Market model; web survey; secondary sizing sources; management data.
**Analysis** — Size top-down, validate bottom-up; state inclusion / exclusion rules on-page.
**Exhibit** — Opportunity pyramid + segmented size-band bar.
**Quality bar** — Sizing traces to the appendix methodology page step-by-step.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MVG |
| Fallback modules | MDF, GRO — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MDF |
| Metrics this slide may state | `mkt.tam`, `mkt.sam`, `mkt.som` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | TAM / SAM / served market | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Basis, sources and confidence | {'max_items': 5, 'max_chars_item': 170} |

## 22 · S022_h1_sam_walkup — Highlight 1 — SAM Expansion Walkup
_Investment Highlights · archetype `chart_commentary` · exhibit `walkup` · gate **conditional**_

**Purpose** — Show the incremental opportunity the Target's new model unlocked.

**Must contain**
- Walkup waterfall from core serviceable market to the expanded SAM, with the increment attributable to the new offering.
- Channel / customer-type stacking inside each bar.
- Annotation of what product innovation added ($ value) and the new monetisation pathways opened.
- Sub-line stating what SAM excludes and why.

**Admissible sources** — Market model; management data.
**Analysis** — Isolate the increment honestly; check for double counting between core and new opportunity.
**Exhibit** — Two-bar walkup waterfall with stacked channel splits and annotation.
**Quality bar** — The increment reconciles exactly with the TAM / SAM definitions used elsewhere.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG, GRO |
| Secondary modules | MDF, MSS |
| Metrics this slide may state | `mkt.sam` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | SAM expansion build | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | What each step assumes | {'max_items': 5, 'max_chars_item': 170} |

## 23 · S023_h1_growth_drivers — Highlight 1 — Market Growth Drivers
_Investment Highlights · archetype `table_commentary` · exhibit `banded_table` · gate **core**_

**Purpose** — Decompose the growth outlook into named levers the IC can interrogate.

**Must contain**
- Waterfall from current SAM to the 5-year SAM, one bar per growth lever, with the headline CAGR.
- Side rail defining each lever and its approximate share of total growth.
- Mix-shift-only levers flagged explicitly as channel shift, not incremental market growth.
- Channel-level CAGRs (faster-growing vs slower channel) beneath the chart.

**Admissible sources** — Market model; web survey; interviews; secondary sources.
**Analysis** — Decompose the CAGR into levers; separate real expansion from channel mix shift.
**Exhibit** — Growth waterfall + lever definition rail with %-of-growth chips.
**Quality bar** — Lever contributions sum to the headline CAGR — arithmetic checked.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | DDR, MVG |
| Fallback modules | MVG, MRK — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MRK |
| Metrics this slide may state | `mkt.demand_driver`, `mkt.cagr` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Driver, magnitude and evidence | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Net growth read | {'max_items': 5, 'max_chars_item': 170} |

## 24 · S024_h1_recession — Highlight 1 — Recession Resilience
_Investment Highlights · archetype `chart_commentary` · exhibit `line_series` · gate **conditional**_

**Purpose** — Prove the market grows through downturns, not just in good times.

**Must contain**
- Long-run market size vs GDP-growth dual-axis chart (20+ years).
- Recession windows annotated with period CAGRs for both series (market vs GDP).
- Takeaway banner stating the resilience conclusion in one sentence.
- Workstream chip and sub-line tying resilience to the Target's diversified exposure.

**Admissible sources** — Historical market estimates; macroeconomic data (e.g., FRED).
**Analysis** — Compare market vs GDP growth through at least two downturns; test the durability argument.
**Exhibit** — Dual-axis time series with recession callout boxes.
**Quality bar** — The resilience claim is grounded in two or more historical downturns.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MRK |
| Secondary modules | SNS, DDR, RVQ |
| Metrics this slide may state | `mkt.recession_sensitivity` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Behaviour through the last downturn | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Why demand held or did not | {'max_items': 5, 'max_chars_item': 170} |

## 25 · S025_h2_demand_alignment — Highlight 2 — Demand Alignment
_Investment Highlights · archetype `table_commentary` · exhibit `scorecard` · gate **research_gated**_

**Purpose** — Chain the market's buying behaviour to the Target's platform fit.

**Must contain**
- Four-panel argument chain: customers shifting to the new model → shared buying criteria varying by size → vertical functionality mattering → the Target flexibly serving both groups.
- Two to four evidence bullets per panel, grounded in survey and interview findings.
- Footer proof bar linking the argument to named Target capabilities.
- Panel headers written as a connected sentence across the page.

**Admissible sources** — Web survey; interviews.
**Analysis** — Build the argument chain so each panel is evidenced, then land on capability fit.
**Exhibit** — Four-column argument panels + footer capability bar.
**Quality bar** — Each panel cites its evidence base — this page argues, it does not assert.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | DDR, BBH |
| Secondary modules | CSG, CDF |
| Metrics this slide may state | `cust.purchase_criteria` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | What buyers need vs what the target offers | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Where alignment is weakest | {'max_items': 5, 'max_chars_item': 170} |

## 26 · S026_h2_lifecycle_fit — Highlight 2 — Customer Lifecycle Fit
_Investment Highlights · archetype `flow_row` · exhibit `lifecycle_flow` · gate **research_gated**_

**Purpose** — Show where in the customer lifecycle the Target wins, and why it keeps winning.

**Must contain**
- Lifecycle / maturity curve locating when customers start evaluating providers like the Target, with the GTM sweet spot annotated (size band).
- Notes on stickiness once adopted and the minimal graduation risk below the largest tier.
- Ranked purchase-criteria index chart from the survey [n = X] beside the curve.
- Synthesis rail linking the Target's strengths to the top-ranked criteria.

**Admissible sources** — Web survey; interviews.
**Analysis** — Locate the switching window; align the Target's strengths against the highest-ranked criteria.
**Exhibit** — Annotated lifecycle curve + indexed criteria bar chart + synthesis rail.
**Quality bar** — The sweet-spot claim is consistent with the decision-making chapter's evidence.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CST, BBH |
| Secondary modules | CSG |
| Metrics this slide may state | `cust.retention` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Customer lifecycle and where the target fits | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Evidence and gaps | {'max_items': 5, 'max_chars_item': 170} |

## 27 · S027_h3_satisfaction — Highlight 3 — Customer Satisfaction
_Investment Highlights · archetype `chart_commentary` · exhibit `nps_bar` · gate **research_gated**_

**Purpose** — Let the Target's customers make the satisfaction case in their own words.

**Must contain**
- Driver rows for the recurring satisfaction themes (ease of use, customer service, speed of delivery, competitive pricing).
- Commentary column summarising the evidence per driver.
- One to two verbatim customer quotes per driver, attributed by role.
- Sub-line framing the base as stable and satisfied.

**Admissible sources** — Customer interviews.
**Analysis** — Extract recurring drivers across interviews; separate satisfaction from active advocacy.
**Exhibit** — Driver | commentary | quote table.
**Quality bar** — Quotes are attributed and representative — not cherry-picked outliers.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA |
| Secondary modules | CST |
| Metrics this slide may state | `cust.nps`, `cust.satisfaction` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C10-DELTA |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Satisfaction and advocacy | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | What drives the score | {'max_items': 5, 'max_chars_item': 170} |

## 28 · S028_h4_incumbent_dissatisfaction — Highlight 4 — Incumbent Dissatisfaction
_Investment Highlights · archetype `chart_commentary` · exhibit `grouped_bar` · gate **research_gated**_

**Purpose** — Quantify the frustration with incumbents that creates the Target's wedge.

**Must contain**
- Numbered structural pain points with the legacy model (economics, undifferentiated product, missing vertical expertise, poor support).
- NPS stacked bars for the incumbent's customer groups: detractor / passive / promoter splits with NPS values and n.
- Framing line connecting dissatisfaction to switching potential for the Target.

**Admissible sources** — Web survey; interviews.
**Analysis** — Compute NPS by segment; link each pain point to observed switching intent.
**Exhibit** — Pain-point list + NPS stacked bars with n labels.
**Quality bar** — NPS sample sizes shown; small-n cells flagged rather than hidden.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA, CID |
| Secondary modules | CDF, BBH |
| Metrics this slide may state | `cust.satisfaction` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Dissatisfaction with incumbents | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | The opening this creates | {'max_items': 5, 'max_chars_item': 170} |

## 29 · S029_h4_differentiation — Highlight 4 — Competitive Differentiation
_Investment Highlights · archetype `table_full` · exhibit `scorecard` · gate **core**_

**Purpose** — Position the Target against competitor archetypes on the criteria that decide deals.

**Must contain**
- Three numbered differentiation claims (platform performance, support quality, flexibility), each with supporting evidence bullets.
- Heat matrix of competitor archetypes vs key criteria (functionality, flexibility, adaptability, support, cost).
- Synthesis banner stating the opportunity as demands evolve toward the Target's model.

**Admissible sources** — Web survey; interviews.
**Analysis** — Benchmark archetypes on the criteria customers rank highest; validate the Target's cells externally.
**Exhibit** — Archetype × criteria heat matrix + numbered claims rail.
**Quality bar** — The Target's scores are third-party evidenced — never self-reported by management.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | CDF |
| Fallback modules | CID, SWO, CSA — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | CID, CSA |
| Metrics this slide may state | `comp.differentiation` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 30 · S030_h4_full_suite — Highlight 4 — Full-Suite Offering Receptivity
_Investment Highlights · archetype `chart_commentary` · exhibit `grouped_bar` · gate **research_gated**_

**Purpose** — Show the market wants the integrated model the Target is building.

**Must contain**
- Capability panel: core capabilities + value-added services, including vertical-specific modules, with an upside note on expansion.
- Survey stacked bars: likelihood to switch to a full-suite provider by customer type, with means, top-2 shares, and n.
- Sub-line noting the model lets customers easily replace or upgrade incumbents.

**Admissible sources** — Web survey; management materials.
**Analysis** — Quantify receptivity by customer type; connect stated appetite to the capability inventory.
**Exhibit** — Capability inventory panel + likelihood-to-switch stacked bars.
**Quality bar** — Receptivity is read alongside stated switching barriers — not in isolation.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | GRO, CDF |
| Secondary modules | BBH, MPR |
| Metrics this slide may state | `cust.wtp` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Receptivity to a full-suite offer | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Willingness to pay and caveats | {'max_items': 5, 'max_chars_item': 170} |

## 31 · S031_h5_growth_levers — Highlight 5 — Growth Levers
_Investment Highlights · archetype `numbered_rows` · exhibit `banded_table` · gate **core**_

**Purpose** — Lay out the growth agenda: seven levers, sequenced by proximity to the core.

**Must contain**
- Opportunity matrix plotting the numbered levers by proximity to core (x) and horizon (grouping: core / near adjacency / expansion).
- Lever table: each numbered growth area with the advisor's perspective and considerations.
- Levers span new customers, new partners, product utilisation, pricing, new segments, product expansion, and M&A.
- Every lever cross-references its deep-dive page in the growth chapter.

**Admissible sources** — Findings sections; management strategy materials.
**Analysis** — Sequence levers by readiness and proximity; separate core momentum from expansion bets.
**Exhibit** — 2-axis opportunity matrix + lever perspective table.
**Quality bar** — Every lever on the matrix has a perspective row — and vice versa.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | GRO |
| Fallback modules | STR, REC, SYN — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | STR, SYN, MSS |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T3-SUMMARISE, T6-CONCLUDE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `rows` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |

## 32 · S032_div_market — Section Divider — Detailed Findings
_Market Dynamics & Opportunity · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Open the findings section and list its four chapters.

**Must contain**
- Section title with the four workstream chapters listed: Market Dynamics & Opportunity · Decision-Making Dynamics · Competitive Landscape · Growth Opportunities.
- Standard divider branding; repeated before each chapter with the current chapter highlighted.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with chapter list.
**Quality bar** — Chapter list matches the contents page exactly.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 33 · S033_icp_mapping — Ideal Customer Profile Mapping
_Market Dynamics & Opportunity · archetype `table_full` · exhibit `heat_grid` · gate **conditional**_

**Purpose** — Define precisely who the Target's model is built for — by size, vertical, and type.

**Must contain**
- Heat grid: customer size band (rows) × industry vertical (columns) × customer type (sub-rows), rated very low → very high fit.
- The ICP zone outlined and labelled; enterprise-tier rows annotated with why addressability is limited.
- Side callouts explaining what drives high fit (purpose-built functionality) and where fit could be built.
- Sub-line noting this reflects the new model specifically, distinct from legacy offerings.

**Admissible sources** — Management data; interviews.
**Analysis** — Define ICP from demonstrated fit and win evidence — not aspiration.
**Exhibit** — ICP heat grid with outlined zone and explanatory callouts.
**Quality bar** — ICP boundaries are consistent with the sizing exclusions used in the market chapter.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CSG |
| Secondary modules | BBH, RVQ |
| Metrics this slide may state | `cust.segments` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 34 · S034_market_definitions — Market Opportunity Definitions
_Market Dynamics & Opportunity · archetype `table_full` · exhibit `banded_table` · gate **core**_

**Purpose** — Make every sizing boundary explicit before any number is shown.

**Must contain**
- Left rail: TAM / SAM / served market pyramid with $ values for each component (core opportunity + adjacent offering).
- Definition columns for each component: what each level includes, what it excludes, and why.
- Explicit notes on exclusions (segments that self-serve, uneconomic micro tiers) and where TAM equals SAM and why.
- Component tags (A / B) reused on every subsequent sizing page.

**Admissible sources** — Market model.
**Analysis** — Write inclusion / exclusion logic that survives IC interrogation; tag components consistently.
**Exhibit** — Definition table: opportunity level × component, with the value rail.
**Quality bar** — These definitions match every later chart that uses them — no silent redefinition.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MDF |
| Fallback modules | MVG, CSG — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MVG |
| Metrics this slide may state | `mkt.definition` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 35 · S035_volume_narrowing — Addressable Volume Narrowing
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `walkdown` · gate **conditional**_

**Purpose** — Walk from total market volume to what is structurally addressable.

**Must contain**
- Three-bar narrowing waterfall: total volume → volume in less-addressable verticals removed → addressable volume.
- Vertical composition (%) inside each bar; excluded verticals in grey, retained in brand colour.
- Note box explaining the exclusion logic: structural misalignment, direct relationships, internalised alternatives.
- Percentage retained annotated between bars.

**Admissible sources** — Government / industry statistics; secondary sizing sources.
**Analysis** — Exclude verticals by stated structural criteria — never by convenience.
**Exhibit** — Three-bar waterfall with per-vertical stacking and exclusion note.
**Quality bar** — Every removed vertical has its exclusion rationale stated on-page.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG, MDF |
| Metrics this slide may state | `mkt.volume` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | From universe to addressable volume | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Each narrowing step and its source | {'max_items': 5, 'max_chars_item': 170} |

## 36 · S036_volume_by_channel — Addressable Volume by Channel
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `stacked_bar` · gate **conditional**_

**Purpose** — Split addressable volume by route-to-customer across the retained verticals.

**Must contain**
- 100% stacked bars per vertical showing channel mix (partner-led vs independent), ordered by volume.
- Absolute volume totals above each vertical bar and sigma totals per channel at the right.
- Commentary on where channel adoption lags or leads by vertical.
- Total addressable volume callout in the corner.

**Admissible sources** — Market model; web survey; secondary sources.
**Analysis** — Estimate channel mix per vertical from survey base rates plus secondary evidence.
**Exhibit** — 100% stacked vertical bars with absolute totals and channel sigmas.
**Quality bar** — Channel splits are consistent with the survey base rates reported earlier.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG, MSS |
| Secondary modules | CSG |
| Metrics this slide may state | `mkt.volume`, `mkt.segment_share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Addressable volume by channel | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Channel economics and reach | {'max_items': 5, 'max_chars_item': 170} |

## 37 · S037_tam_walkdown — TAM by Segment & Walkdown to SAM
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `walkdown` · gate **core**_

**Purpose** — Quantify the revenue opportunity and remove the segments the Target cannot serve.

**Must contain**
- Left panel: TAM split by customer size band (100% stacked with channel mix inside each band, absolute $ above).
- Right panel: walkdown waterfall TAM → less-serviceable segments removed → SAM.
- Explicit statement of the removed segments (top tier that self-serves; micro tier that is uneconomic).
- Draft pages carry a 'Preliminary' tag until the model is locked.

**Admissible sources** — Market model; survey; secondary sources.
**Analysis** — Apply the serviceability filters defined on the definitions page; keep the arithmetic visible.
**Exhibit** — Segmented TAM bar + walkdown waterfall.
**Quality bar** — Walkdown arithmetic sums exactly; removals match the ICP page.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MVG, MDF |
| Fallback modules | MDF, CSG — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | CSG |
| Metrics this slide may state | `mkt.tam`, `mkt.sam` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | TAM by segment, walked down to SAM | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Exclusions and why | {'max_items': 5, 'max_chars_item': 170} |

## 38 · S038_sam_by_endmarket — SAM by End-Market & Channel — Served Market
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `stacked_bar` · gate **conditional**_

**Purpose** — Locate the competitive battleground: who currently serves the serviceable market.

**Must contain**
- Twin panels: SAM for each channel (independent vs partner-led), split by end-market, ordered by size.
- Served-market shading inside every bar: share via third-party providers vs direct / in-house.
- Provider-type totals in the legend ($ via third parties vs direct).
- Sub-line stating the served-market estimate and the displacement logic it implies.

**Admissible sources** — Market model; web survey; secondary sources.
**Analysis** — Estimate current provider mix per end-market; define the near-term contestable pool.
**Exhibit** — Twin stacked-bar panels with served-market shading and totals.
**Quality bar** — The served-market estimate reconciles with competitor share evidence.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG, MSS |
| Secondary modules | CSG |
| Metrics this slide may state | `mkt.sam`, `mkt.som`, `mkt.segment_share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | SAM by end-market and channel | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Served share and headroom | {'max_items': 5, 'max_chars_item': 170} |

## 39 · S039_value_added_services — Value-Added Services Opportunity
_Market Dynamics & Opportunity · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Size the attach opportunity beyond the core service.

**Must contain**
- Left panel: VAS TAM split by customer type, stacked by monetisation mechanism (subscription fee vs per-unit uplift), with the pricing assumptions named.
- Right panel: served vs whitespace split of the VAS market by customer type.
- Per-customer economics stated in the legend ($ per customer per year; uplift rate).
- Sub-line: how VAS is monetised and why it is upside to the core opportunity.

**Admissible sources** — Market model; price benchmarks; management price sheets.
**Analysis** — Size the attach opportunity from stated per-customer economics; separate served from whitespace.
**Exhibit** — Two stacked-bar panels with assumption footnotes.
**Quality bar** — Pricing assumptions are benchmarked to real price points — not invented.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | GRO, MPR |
| Secondary modules | RVQ |
| Metrics this slide may state | `mkt.price_benchmark` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Service, attach rate and price point | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Revenue potential and evidence | {'max_items': 5, 'max_chars_item': 170} |

## 40 · S040_growth_factors_overview — Market Growth Factors — Overview
_Market Dynamics & Opportunity · archetype `numbered_rows` · exhibit `banded_table` · gate **core**_

**Purpose** — Name the five forces expanding the market before deep-diving each one.

**Must contain**
- Numbered market factors (~5): underlying demand growth, mix shift to monetizable modes, channel adoption, pricing stability, attach-rate growth.
- Description and implication for each factor in 2–3 sentences.
- Numbered chips that recur on the following deep-dive pages (one page per factor).
- Direction / magnitude of each factor noted.

**Admissible sources** — Web survey; interviews; secondary research.
**Analysis** — Identify the forces that genuinely expand or shift the addressable pool.
**Exhibit** — Factor table with numbered chips and implication column.
**Quality bar** — Every factor listed here has a dedicated evidence page immediately following.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | DDR, MVG |
| Fallback modules | MVG, MRK — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MRK |
| Metrics this slide may state | `mkt.cagr`, `mkt.demand_driver` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `rows` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |

## 41 · S041_gf1_demand — Growth Factor 1 — Underlying Demand Growth
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `line_series` · gate **conditional**_

**Purpose** — Evidence that spend in the Target's verticals grows consistently.

**Must contain**
- Target's current mix by vertical (snapshot panel) for context.
- Long-run (~20-year) revenue index by core vertical with per-vertical CAGRs listed.
- Recession-window annotation showing growth stayed positive through the downturn.
- Methodology note naming the statistical proxy used for each vertical.

**Admissible sources** — Government statistical series (census, economic data); management data.
**Analysis** — Build defensible per-vertical growth proxies; compute long-run and recession-period CAGRs.
**Exhibit** — Multi-line indexed time series + mix snapshot + CAGR rail.
**Quality bar** — The proxy series behind each vertical is documented in the note.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | DDR |
| Secondary modules | MVG |
| Metrics this slide may state | `mkt.demand_driver`, `mkt.cagr` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Underlying demand series | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Driver mechanics and durability | {'max_items': 5, 'max_chars_item': 170} |

## 42 · S042_gf2_mix_shift — Growth Factor 2 — Mix Shift to Monetizable Modes
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `stacked_bar` · gate **conditional**_

**Purpose** — Show behaviour shifting toward the modes the Target monetises.

**Must contain**
- Horizontal 100% stacked bars by year (~8-year series) of end-user behaviour mix, with the monetizable modes gaining share.
- Commentary rail: the structural drivers of the shift, with 1–2 verbatim quotes (e.g., generational behaviour, omnichannel expectations).
- Framing line: the shift expands the monetizable base for providers like the Target.
- Data-gap footnote where series years are missing.

**Admissible sources** — Public statistical series; interviews.
**Analysis** — Quantify the displacement trend; translate share shift into volume implications.
**Exhibit** — Stacked-bar time series + quote commentary rail.
**Quality bar** — Series source and any data gaps are disclosed in footnotes.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | DDR, CSG |
| Secondary modules | MSS, RVQ, MVG |
| Metrics this slide may state | `mkt.segment_share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Mix shift to monetizable modes | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Why the shift is happening | {'max_items': 5, 'max_chars_item': 170} |

## 43 · S043_gf3_channel_adoption — Growth Factor 3 — Channel Adoption
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `line_series` · gate **research_gated**_

**Purpose** — Triangulate preference, current behaviour, and intent for the emerging channel.

**Must contain**
- Panel 1: customer preference for embedded / integrated vs standalone (1–7 scale stacked bar; mean, top-2, n).
- Panel 2: current approach mix among partner organisations (% by approach).
- Panel 3: non-adopters' likelihood to adopt via a third party (scale stacked bar; mean, n).
- Commentary rail synthesising the three panels with a supporting quote.

**Admissible sources** — Web survey; interviews.
**Analysis** — Keep stated preference and behavioural intent distinct; report all scales and n's.
**Exhibit** — Three survey stacked-bar panels + commentary rail.
**Quality bar** — Preference vs intent distinction preserved — they are different claims.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | MSS, DDR |
| Secondary modules | BBH, MVG |
| Metrics this slide may state | `mkt.segment_share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Adoption of the emerging channel | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Adoption drivers and blockers | {'max_items': 5, 'max_chars_item': 170} |

## 44 · S044_gf3_channel_stickiness — Growth Factor 3 — Stickiness of the Emerging Channel
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `nps_bar` · gate **research_gated**_

**Purpose** — Show that once adopted, the emerging channel is harder to leave.

**Must contain**
- Difficulty-to-switch stacked bars: emerging channel vs legacy standalone (1–7 scale; means, top-2, n).
- Commentary: why deep workflow integration raises switching costs, with 2 verbatim quotes on mechanism.
- Implication line: as the Target grows in this channel, retention economics improve.

**Admissible sources** — Web survey; interviews.
**Analysis** — Compare switching friction across channels; tie the gap to a causal mechanism.
**Exhibit** — Paired stacked bars + mechanism commentary with quotes.
**Quality bar** — The stickiness claim rests on mechanism plus data — not scores alone.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CST, MSS |
| Secondary modules | CSA |
| Metrics this slide may state | `cust.retention` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C10-DELTA |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Stickiness once adopted | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | What keeps buyers in the channel | {'max_items': 5, 'max_chars_item': 170} |

## 45 · S045_gf4_pricing_stability — Growth Factor 4 — Pricing & Margin Stability
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `line_series` · gate **conditional**_

**Purpose** — Decompose pricing to show provider economics hold or improve.

**Must contain**
- Stacked bar decomposing gross pricing into pass-through cost vs provider residual, with typical ranges.
- Expected-trajectory table per layer (overall rate / provider residual / pass-through) with direction arrows.
- Commentary rail: quotes supporting stability or modest growth per layer.
- Note on the structural reasons providers defend their share (service quality, value-added tools).

**Admissible sources** — Interviews; industry benchmarks.
**Analysis** — Decompose the price stack; assess compression risk layer by layer.
**Exhibit** — Pricing decomposition bar + trajectory table + quote rail.
**Quality bar** — Trajectory claims are sourced to market participants, not extrapolation.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MPR |
| Secondary modules | CSC, RVQ |
| Metrics this slide may state | `mkt.price_benchmark`, `fin.gross_margin` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C11-MARGIN, C4-MIX, C7-CAGR |
| Source priority | R1, R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Price and margin through the cycle | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Pricing power and pass-through | {'max_items': 5, 'max_chars_item': 170} |

## 46 · S046_sam_growth_build — SAM Growth Build (Detailed)
_Market Dynamics & Opportunity · archetype `table_chart` · exhibit `walkup` · gate **conditional**_

**Purpose** — The full 5-year growth model behind the highlights-page waterfall.

**Must contain**
- Growth waterfall from current SAM to 5-year SAM, one bar per lever, with headline CAGR.
- Left rail: each lever defined with its ~% share of total growth.
- Mix-shift-only levers flagged as structural channel change, not incremental growth.
- End-state definition note: what the terminal-year figure includes; channel CAGRs beneath.

**Admissible sources** — Market model; survey; interviews; secondary sources.
**Analysis** — Quantify each lever's contribution and document its assumptions.
**Exhibit** — Waterfall + lever contribution rail with % chips.
**Quality bar** — Matches the Investment Highlights version to the dollar.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG |
| Secondary modules | DDR, MSS |
| Metrics this slide may state | `mkt.sam`, `mkt.cagr` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Growth build by factor | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | chart | SAM trajectory | {'max_series': 4, 'max_points': 12} |
| `takeaway` | text | — | {'max_chars': 320} |

## 47 · S047_scenario_analysis — Scenario Analysis
_Market Dynamics & Opportunity · archetype `table_full` · exhibit `scenario_table` · gate **conditional**_

**Purpose** — Bound the outlook with honest bear / base / bull cases per channel.

**Must contain**
- Twin panels (one per channel): current vs terminal-year SAM under bear / base / bull, with CAGR per case.
- Annotation of what differentiates the cases (the highest-impact assumptions flexed).
- Note on which channel benefits disproportionately and why.
- Range framing: both channels grow meaningfully within a narrow band.

**Admissible sources** — Market model sensitivity runs.
**Analysis** — Flex the assumptions that matter most; name them — avoid arbitrary ±% cases.
**Exhibit** — Grouped scenario bars, twin panels by channel.
**Quality bar** — Scenario drivers are named on-page; ranges are defensible.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | SNS |
| Secondary modules | MVG, FVR, MRK |
| Metrics this slide may state | `val.sensitivity`, `mkt.cagr` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T2-COMBINE, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C14-SUM, C15-NET, C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R1, R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 48 · S048_downturn_resilience — Downturn Resilience (Detailed)
_Market Dynamics & Opportunity · archetype `chart_commentary` · exhibit `line_series` · gate **conditional**_

**Purpose** — The full evidence base for the countercyclical claim.

**Must contain**
- Long-run SAM vs GDP-growth series with recession windows and period CAGRs annotated.
- Mechanism callouts: (1) mission-critical nature of the service; (2) countercyclical pricing dynamics — each with a supporting quote.
- Takeaway banner restating the resilience conclusion.
- Indexing note: how the historical series was constructed.

**Admissible sources** — Historical market estimates; macro data; interviews.
**Analysis** — Evidence both resilience mechanisms independently; index the series transparently.
**Exhibit** — Annotated dual-axis time series + two mechanism callouts.
**Quality bar** — Each mechanism is supported by a quote or datapoint — not narrative alone.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MRK, SNS |
| Secondary modules | RVQ, DDR, CFL, CSC |
| Metrics this slide may state | `mkt.recession_sensitivity` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Downturn behaviour, modelled | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Resilience mechanisms and their limits | {'max_items': 5, 'max_chars_item': 170} |

## 49 · S049_risk_assessment — Risk Assessment
_Market Dynamics & Opportunity · archetype `table_commentary` · exhibit `risk_matrix` · gate **core**_

**Purpose** — Carry every thesis risk to a named severity and a mitigant.

**Must contain**
- Risk rows: disintermediation (customers going direct), macro pressure on the core segment, technology substitution, margin compression from price transparency.
- Severity gauge per risk (low → high) set by evidence.
- Market assessment column: what the evidence says, with a quote or datapoint per risk.
- Implication column: the Target's mitigants and residual exposure.

**Admissible sources** — Interviews; web survey; secondary research.
**Analysis** — Rate likelihood and severity from evidence; test each mitigant honestly.
**Exhibit** — Risk table with severity gauges and implication rail.
**Quality bar** — Every risk raised anywhere in the deck is resolved or carried here.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MRK, IRK |
| Fallback modules | IRK, OPR, SCR, RCO — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | OPR, SCR, RCO |
| Metrics this slide may state | `risk.item`, `risk.regulatory` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C6-RISK-SCORE |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Risk register - impact x likelihood | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Mitigations and residual exposure | {'max_items': 5, 'max_chars_item': 170} |

## 50 · S050_div_decisions — Section Divider — Decision-Making Dynamics
_Decision-Making Dynamics · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the findings divider with this chapter highlighted.

**Must contain**
- Four-chapter list with Decision-Making Dynamics highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with chapter list, current chapter emphasised.
**Quality bar** — Highlight state matches the reader's position in the deck.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 51 · S051_partner_switching_lifecycle — Partner Switching Lifecycle
_Decision-Making Dynamics · archetype `flow_row` · exhibit `lifecycle_flow` · gate **research_gated**_

**Purpose** — Locate the window in a partner's maturity when providers get switched.

**Must contain**
- Maturity curve (adoption vs time) with early-stage priorities (speed, simplicity) vs scaled priorities (economics, control) annotated.
- The switching window highlighted: where most provider reassessment occurs, with the adoption-range trigger.
- Note on the largest tier that eventually goes direct — and why that is rare.
- Synthesis bar: why these dynamics favour the Target's economics and flexibility.

**Admissible sources** — Interviews.
**Analysis** — Define switching triggers by lifecycle stage; identify where the Target should intercept.
**Exhibit** — Annotated lifecycle curve with highlighted switching window.
**Quality bar** — The window claim is consistent with the churn-trigger data later in the deck.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | BBH, SUP |
| Secondary modules | CST |
| Metrics this slide may state | `cust.switching_trigger` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Partner switching lifecycle | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Where partners are won and lost | {'max_items': 5, 'max_chars_item': 170} |

## 52 · S052_switching_drivers — Customer Switching Drivers
_Decision-Making Dynamics · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Explain why end customers move, and what they gain when they do.

**Must contain**
- Driver rows (e.g., partner rolls out an integrated solution; customer scales past its current provider) with descriptions.
- Benefit chips per driver: integration depth, experience, economics, support.
- Overview column detailing each benefit in 1–2 sentences.
- Implication rail: how the Target captures volume from each driver.

**Admissible sources** — Interviews; web survey.
**Analysis** — Separate push factors (incumbent failure) from pull factors (new-model advantages).
**Exhibit** — Driver → benefits → overview table with implication rail.
**Quality bar** — Each driver is evidenced by a quote or survey statistic.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | BBH, CST |
| Secondary modules | CSA, MPR |
| Metrics this slide may state | `cust.switching_trigger` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Trigger, frequency and evidence | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Implication for win rate | {'max_items': 5, 'max_chars_item': 170} |

## 53 · S053_decision_tree — Customer Decision Tree
_Decision-Making Dynamics · archetype `flow_row` · exhibit `decision_tree` · gate **research_gated**_

**Purpose** — Map every path a switching customer can take — and where the Target wins.

**Must contain**
- Trigger events on the left feeding yes / no decision nodes.
- Branches resolving to outcomes: adopt the partner-embedded option, choose a standalone third party (which type?), or stay.
- Markers on every path where the Target is addressable (embedded, standalone, resale).
- Annotations explaining what drives each branch choice.

**Admissible sources** — Interviews.
**Analysis** — Trace decision paths from real switching stories; locate the Target's entry points on each.
**Exhibit** — Left-to-right decision tree with outcome rail and addressability markers.
**Quality bar** — Every leaf node states who wins that path and why.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | BBH |
| Secondary modules | CSG |
| Metrics this slide may state | `cust.decision_process` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | How a buyer reaches a decision | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Where deals are lost | {'max_items': 5, 'max_chars_item': 170} |

## 54 · S054_decision_process — Decision Process & Stakeholders by Segment
_Decision-Making Dynamics · archetype `table_full` · exhibit `heat_grid` · gate **conditional**_

**Purpose** — Contrast how small, startup, and sophisticated buyers actually decide.

**Must contain**
- Three columns: small customers · small startup partners · large sophisticated organisations.
- Decision-making process per column (owner-led and fast → default-brand quick picks → formal multi-stakeholder RFP).
- Decision timeline stats per column with survey n's (e.g., % deciding within 4–12 months).
- Key decision-makers and influencers mapped per column (owner; C-suite; cross-functional + external influencers).

**Admissible sources** — Web survey; interviews.
**Analysis** — Contrast processes across segments; extract the GTM motion each requires.
**Exhibit** — Three-column comparison with stakeholder icon rows and timeline stats.
**Quality bar** — Timeline statistics carry their survey n's on-page.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | BBH, CSG |
| Metrics this slide may state | `cust.decision_process` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 55 · S055_purchase_criteria — Purchase Criteria by Customer Type & Size
_Decision-Making Dynamics · archetype `table_full` · exhibit `scorecard` · gate **conditional**_

**Purpose** — Rank what buyers weigh — and test the Target against every criterion.

**Must contain**
- Twin indexed bar charts ranking purchase criteria for each customer type [n's shown].
- Size-index chips per criterion showing how importance shifts from small to large buyers.
- Commentary column with a supporting quote per major criterion.
- Target-alignment column: evidence-based fit assessment per criterion.

**Admissible sources** — Web survey; interviews.
**Analysis** — Index criteria importance; validate the Target's fit per criterion with customer evidence.
**Exhibit** — Twin indexed bars + criteria table with size chips, quotes, and alignment column.
**Quality bar** — The alignment column is grounded in customer evidence, not management's view.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | BBH, CSG |
| Secondary modules | MPR, CDF |
| Metrics this slide may state | `cust.purchase_criteria` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 56 · S056_vertical_needs — Vertical-Specific Functionality Needs
_Decision-Making Dynamics · archetype `table_full` · exhibit `heat_grid` · gate **research_gated**_

**Purpose** — Show how much vertical depth matters — differently — to each buyer group.

**Must contain**
- Importance stacked bars (1–7 scale) by size band for each customer type, with means and n's.
- Commentary: one group values vertical features as operational necessity, the other as product differentiator.
- Supporting quotes for each framing.
- Implication panel: what the Target's vertical toolset earns it in each group.

**Admissible sources** — Web survey; interviews.
**Analysis** — Segment importance scores; interpret the different reasons behind similar scores.
**Exhibit** — Stacked-bar panels by segment + commentary and implication rail.
**Quality bar** — Differences are interpreted, not just displayed.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSG, BBH |
| Secondary modules | CDF, IPT |
| Metrics this slide may state | `cust.segments` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 57 · S057_switching_complexity — Switching Complexity by Segment
_Decision-Making Dynamics · archetype `table_commentary` · exhibit `heat_grid` · gate **conditional**_

**Purpose** — Grade the friction of switching for every sub-segment — and derive the entry strategy.

**Must contain**
- Rows per sub-segment (small / medium / large partners; embedded, large-direct, small-direct customers) with low→high difficulty gauges.
- Overview column explaining what drives friction (infrastructure investment, integration depth, contracts).
- Implication column: where the Target should fully replace vs supplement incumbents.
- Footnote defining the size boundaries used.

**Admissible sources** — Interviews.
**Analysis** — Map friction to prior infrastructure investment; convert into a replace-vs-supplement strategy.
**Exhibit** — Difficulty gauge table with overview and implication columns.
**Quality bar** — Entry-strategy implications follow logically from the friction evidence.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CST, BBH |
| Secondary modules | OPR |
| Metrics this slide may state | `cust.switching_trigger` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Switching complexity by segment | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | What this means for retention and for attack | {'max_items': 5, 'max_chars_item': 170} |

## 58 · S058_div_competition — Section Divider — Competitive Landscape
_Competitive Landscape · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the findings divider with this chapter highlighted.

**Must contain**
- Four-chapter list with Competitive Landscape highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with chapter list, current chapter emphasised.
**Quality bar** — Highlight state matches the reader's position in the deck.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 59 · S059_routes_to_market — Routes to Market & Where Competition Happens
_Competitive Landscape · archetype `flow_row` · exhibit `lifecycle_flow` · gate **conditional**_

**Purpose** — Map how the Target reaches customers, and who it meets in each route.

**Must contain**
- Three-panel schematic: direct to customers / partners; indirectly via intermediaries; servicing incumbent-model providers.
- Actor boxes per panel showing customer tiers reached and the intermediaries involved.
- Explanatory captions on how each route works and where the Target competes vs supplies.
- Legend distinguishing core competition, service suppliers, and adjacent suppliers.

**Admissible sources** — Interviews; management materials.
**Analysis** — Clarify where competition actually occurs by route — not just who exists in the market.
**Exhibit** — Route schematic with actor boxes and relationship legend.
**Quality bar** — Consistent with the value-chain map in the primer chapter.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MSS, CID |
| Secondary modules | CSG |
| Metrics this slide may state | `comp.set` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Routes to market and where competition happens | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Where the target wins and loses | {'max_items': 5, 'max_chars_item': 170} |

## 60 · S060_competitor_archetypes — Competitor Archetype Comparison
_Competitive Landscape · archetype `table_full` · exhibit `banded_table` · gate **core**_

**Purpose** — Benchmark the archetypes head-to-head on customers' criteria — with the market's own words.

**Must contain**
- One row per archetype (legacy infrastructure providers, incumbent full-stack model, traditional intermediaries, the Target's model) with key players (logos).
- Key characteristics bullets per archetype (2–3, balanced).
- Heat ratings across the criteria set: customization, adaptability, support, cost.
- Market feedback quote per archetype, attributed by role.

**Admissible sources** — Interviews; secondary research.
**Analysis** — Benchmark archetypes on customers' decision criteria; keep ratings evidence-based.
**Exhibit** — Archetype table with logo cells, heat chips, and quote column.
**Quality bar** — Every rating is triangulated across at least two independent source types.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | CID |
| Fallback modules | CDF, MSS — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | CDF, MSS |
| Metrics this slide may state | `comp.set`, `comp.archetypes` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 61 · S061_positioning_map — Competitive Positioning Map
_Competitive Landscape · archetype `chart_commentary` · exhibit `positioning_map` · gate **core**_

**Purpose** — Plot the landscape on the two axes customers actually choose on.

**Must contain**
- 2×2 logo scatter: value-added capability (y) vs vertical specialization (x), all significant players plotted.
- Key takeaways rail: 3–4 landscape conclusions, each with a supporting quote.
- Note box handling edge cases (large vertical players with in-house models) and why they are the exception.
- Positioning banner: where the Target plays and what that intersection wins.

**Admissible sources** — Interviews; secondary research.
**Analysis** — Choose axes reflecting customers' choice drivers; plot positions from evidence, not websites alone.
**Exhibit** — Logo scatter 2×2 + takeaways rail + exception note.
**Quality bar** — Axis choice is justified, and the Target's plotted position is defensible from data.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | CID, CDF |
| Fallback modules | CDF, MSS — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | MPR, MSS |
| Metrics this slide may state | `comp.positioning`, `comp.share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Positioning on capability and price | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Reading the map | {'max_items': 5, 'max_chars_item': 170} |

## 62 · S062_criteria_vs_archetypes — Criteria Performance vs Key Archetypes
_Competitive Landscape · archetype `table_full` · exhibit `scorecard` · gate **conditional**_

**Purpose** — Score the Target against the two main alternatives on every purchase criterion.

**Must contain**
- Heat matrix: purchase criteria (rows) × incumbent archetype A / archetype B / the Target (columns).
- Side commentary per archetype: why customers choose it, with quotes.
- Where gaps open for the Target: flexibility and margin control without the incumbent's overhead, with quote support.

**Admissible sources** — Interviews; web survey; company materials.
**Analysis** — Score performance per criterion from customer evidence; identify the winnable rows.
**Exhibit** — Criteria × archetype heat matrix + commentary rail.
**Quality bar** — The Target's column is customer-evidenced — never self-reported.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CDF, CID |
| Secondary modules | BBH |
| Metrics this slide may state | `comp.differentiation`, `cust.purchase_criteria` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 63 · S063_feature_benchmarking — Feature-Module Performance Benchmarking
_Competitive Landscape · archetype `table_full` · exhibit `heat_grid` · gate **conditional**_

**Purpose** — Benchmark satisfaction with specific feature modules by provider type.

**Must contain**
- Score tables (1–7 scale) per respondent group: feature modules rated overall and split by provider type, with n per table.
- A combined-respondents table beneath the segment tables.
- Commentary rail: which modules drive selection, which are vertical-critical, with quotes.
- Small-sample flags footnoted wherever n is thin.

**Admissible sources** — Web survey; interviews.
**Analysis** — Benchmark module-level performance; find the gaps worth attacking.
**Exhibit** — Stacked score tables by respondent group + commentary rail.
**Quality bar** — Every small-n cell is footnoted — no silent thin samples.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CDF, IPT |
| Secondary modules | CID |
| Metrics this slide may state | `ops.tech_stack` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 64 · S064_price_benchmarking — Price Benchmarking
_Competitive Landscape · archetype `chart_commentary` · exhibit `grouped_bar` · gate **conditional**_

**Purpose** — Compare effective pricing across providers on a genuinely comparable basis.

**Must contain**
- Grouped bars: median effective pricing for the Target vs industry vs the key incumbent, across customer size bands.
- Methodology note: the standard basis used to blend prices for comparability.
- Sub-line on the economics story the comparison supports (attractive to both sides of the market).
- Data-gap caveat: what management data would sharpen the benchmark.

**Admissible sources** — Benchmarks; interviews; management data where available.
**Analysis** — Normalise all prices to one stated basis before comparing; resist mixing bases.
**Exhibit** — Grouped bar chart by size band with methodology footnote.
**Quality bar** — The comparison basis is stated on-page; gross and net are never mixed.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MPR, CID |
| Secondary modules | CDF |
| Metrics this slide may state | `mkt.price_benchmark` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Price benchmarking by archetype | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Where the target sits and why | {'max_items': 5, 'max_chars_item': 170} |

## 65 · S065_incumbent_nps — Incumbent NPS by Provider Type
_Competitive Landscape · archetype `chart_commentary` · exhibit `nps_bar` · gate **research_gated**_

**Purpose** — Measure advocacy for incumbents — and read the switching potential in the gaps.

**Must contain**
- Twin NPS stacked-bar panels (0–10 scale): incumbent model A and incumbent model B, split by customer group.
- Detractor / passive / promoter shares with NPS value and n beneath every bar.
- Callout annotations on the striking results (e.g., heavy detractor concentrations).
- Small-sample flags where applicable.

**Admissible sources** — Web survey.
**Analysis** — Compute NPS by provider type and customer group; interpret as openness to alternatives.
**Exhibit** — Twin NPS stacked panels with callouts.
**Quality bar** — NPS is not over-read where n is small — flags stay attached to the numbers.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA |
| Secondary modules | CID |
| Metrics this slide may state | `cust.nps` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C10-DELTA |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | NPS by provider type | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | What the spread reveals | {'max_items': 5, 'max_chars_item': 170} |

## 66 · S066_competitor_painpoints — Competitor Pain-Point Synthesis
_Competitive Landscape · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Cluster the market's complaints into the structural themes the Target attacks.

**Must contain**
- Pain-point rows: support quality, delivery / settlement speed, pricing rigidity, fragmented technology, missing differentiated features.
- Named-competitor evidence flags per row (logo chips) showing who the complaint attaches to.
- One verbatim quote per row, attributed by role, carrying the specific grievance.
- Sub-line: recurring pain points open the door for challengers like the Target.

**Admissible sources** — Interviews.
**Analysis** — Cluster complaints into structural themes; attribute to specific competitors carefully.
**Exhibit** — Pain-point table with competitor flags and quote cells.
**Quality bar** — Quotes are role-attributed and first-hand — hearsay is excluded.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CID, CDF |
| Secondary modules | CSA |
| Metrics this slide may state | `comp.set` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Pain point by competitor archetype | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Which the target can exploit | {'max_items': 5, 'max_chars_item': 170} |

## 67 · S067_full_suite_wtp — Full-Suite Demand & Willingness to Pay
_Competitive Landscape · archetype `chart_commentary` · exhibit `grouped_bar` · gate **research_gated**_

**Purpose** — Pair switching intent with willingness to pay for the integrated model.

**Must contain**
- Likelihood-to-switch stacked bars (1–7) by customer type, with means, top-2 shares, and n.
- Willingness-to-pay panel: % who would increase / hold / decrease spend for a full-suite provider, with average uplift.
- Commentary rail: what full-suite means to buyers, with supporting quotes.
- Framing line connecting demand to the Target's positioning.

**Admissible sources** — Web survey; interviews.
**Analysis** — Read intent and willingness to pay together; quantify the monetisation upside honestly.
**Exhibit** — Intent stacked bars + WTP panel + commentary.
**Quality bar** — Upside claims always carry the survey base they rest on.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | GRO, MPR |
| Secondary modules | BBH, CDF |
| Metrics this slide may state | `cust.wtp` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Full-suite demand and willingness to pay | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Pricing headroom and risk | {'max_items': 5, 'max_chars_item': 170} |

## 68 · S068_churn_triggers — Churn Triggers
_Competitive Landscape · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Rank what actually makes customers leave — beyond price.

**Must contain**
- Paired horizontal multi-select bars: churn triggers ranked for each customer type (% selecting, n).
- Triggers spanning cost, integration quality, support, reliability, outgrowing the solution, vendor consolidation.
- Commentary rail mapping the top triggers to what a winning provider must deliver, with quotes.
- Note that operational friction rivals price as the leading trigger.

**Admissible sources** — Web survey; interviews.
**Analysis** — Rank triggers per segment; convert into the Target's retention and displacement playbook.
**Exhibit** — Paired ranked bars + commentary rail.
**Quality bar** — Trigger ranking is consistent with the pain-point synthesis page.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CST, CSA |
| Secondary modules | BBH |
| Metrics this slide may state | `cust.churn`, `cust.switching_trigger` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Churn trigger, frequency and severity | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Addressability | {'max_items': 5, 'max_chars_item': 170} |

## 69 · S069_target_strengths — Target Strengths — Customer Evidence
_Competitive Landscape · archetype `quotes` · exhibit `quote_wall` · gate **research_gated**_

**Purpose** — Document the drivers of satisfaction and loyalty in customers' own words.

**Must contain**
- Driver rows: ease of use, customer service, speed of delivery, competitive rates.
- Commentary per driver summarising the interview evidence.
- One to two verbatim quotes per driver, attributed by role.
- Framed as key drivers of satisfaction and loyalty.

**Admissible sources** — Customer interviews.
**Analysis** — Identify repeatable satisfaction drivers echoed across multiple customers.
**Exhibit** — Driver | commentary | quote table.
**Quality bar** — Each strength is echoed by more than one customer.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA, CDF |
| Secondary modules | SWO |
| Metrics this slide may state | `comp.differentiation` |
| Transformation rules | T1-EXTRACT, T12-COMPANY-VS-MARKET, T3-SUMMARISE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `quotes` | table | What customers say the target does well | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Pattern across respondents | {'max_items': 5, 'max_chars_item': 170} |

## 70 · S070_target_development_areas — Target Development Areas — Customer Evidence
_Competitive Landscape · archetype `quotes` · exhibit `quote_wall` · gate **research_gated**_

**Purpose** — Report the improvement areas honestly — credibility depends on it.

**Must contain**
- Development-area rows (e.g., issue-resolution support, specific feature polish) with commentary.
- Verbatim quotes per area carrying the specific criticism, attributed by role.
- Context on severity and frequency: irritant vs churn risk.
- Product implication noted where the fix is clear.

**Admissible sources** — Customer interviews.
**Analysis** — Surface fixable gaps; distinguish irritants from genuine churn risks.
**Exhibit** — Development-area table with quote cells.
**Quality bar** — Weaknesses are reported unvarnished — a sanitized page destroys report credibility.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA, SWO |
| Secondary modules | IRK, OPR |
| Transformation rules | T1-EXTRACT, T12-COMPANY-VS-MARKET, T3-SUMMARISE, T8-FACT-VS-VIEW |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `quotes` | table | Where customers say the target falls short | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Severity and remediability | {'max_items': 5, 'max_chars_item': 170} |

## 71 · S071_div_growth — Section Divider — Growth Opportunities
_Growth Opportunities · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the findings divider with this chapter highlighted.

**Must contain**
- Four-chapter list with Growth Opportunities highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with chapter list, current chapter emphasised.
**Quality bar** — Highlight state matches the reader's position in the deck.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 72 · S072_growth_levers_overview — Growth Levers — Overview
_Growth Opportunities · archetype `numbered_rows` · exhibit `banded_table` · gate **core**_

**Purpose** — Restate the seven-lever agenda that the chapter now proves lever by lever.

**Must contain**
- Opportunity matrix plotting numbered levers by proximity to core vs horizon (core / near adjacency / expansion).
- Lever table: growth area, horizon, and the advisor's perspectives / considerations per lever.
- Identical structure to the Investment Highlights lever page.
- Each lever numbered to match its deep-dive pages that follow.

**Admissible sources** — Findings sections; management strategy materials.
**Analysis** — Sequence levers by readiness and proximity; keep perspectives specific and actionable.
**Exhibit** — Opportunity matrix + lever perspective table.
**Quality bar** — Mirrors the Investment Highlights lever page exactly — no drift.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | GRO |
| Fallback modules | STR, REC, SYN — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | STR, SYN |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T3-SUMMARISE, T6-CONCLUDE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `rows` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |

## 73 · S073_l1_new_customers — Lever 1 — New Customer Acquisition & Market Liquidity
_Growth Opportunities · archetype `chart_commentary` · exhibit `walkup` · gate **conditional**_

**Purpose** — Quantify the annually contestable spend the Target can win.

**Must contain**
- Left panel: SAM walkdown recap ($ by size band, removals shown) to anchor the runway.
- Right panel: likelihood-to-continue distribution from the survey (mean, top-2, n).
- Callout: estimated % of the ICP market turning over annually and the resulting $ 'jump ball' opportunity.
- Derivation of the jump-ball figure shown or referenced.

**Admissible sources** — Market model; web survey.
**Analysis** — Convert switching rates into annually contestable spend; keep the arithmetic visible.
**Exhibit** — Walkdown bars + likelihood stacked bar + jump-ball callout stat.
**Quality bar** — The jump-ball arithmetic is shown on-page or referenced to the appendix.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | GRO, MSS |
| Secondary modules | MVG, CSG |
| Metrics this slide may state | `mkt.som`, `comp.share` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW |
| Calculations | C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Contestable pool and capture path | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Assumptions behind the build | {'max_items': 5, 'max_chars_item': 170} |

## 74 · S074_l1_right_to_win — Lever 1 — Right to Win the Contestable Pool
_Growth Opportunities · archetype `table_full` · exhibit `scorecard` · gate **conditional**_

**Purpose** — Match the contestable spend to the criteria where the Target outperforms.

**Must contain**
- Left panel: SAM by channel and end-market with served-market shading and provider-mix note.
- Right panel: performance-by-competitor-type table across purchasing criteria, ordered by increasing customer importance, heat-rated.
- Note on the share of the provider mix held by the most displaceable incumbent type.
- Sub-line connecting differentiated capabilities to capture of available liquidity.

**Admissible sources** — Market model; web survey; interviews.
**Analysis** — Overlay the Target's comparative strengths onto the contestable pools.
**Exhibit** — Stacked SAM bars + criteria × competitor heat table.
**Quality bar** — Win-rate logic is consistent with the competitive chapter's evidence.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MSS, CDF |
| Secondary modules | GRO, BBH |
| Metrics this slide may state | `comp.differentiation` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 75 · S075_l1_channel_expansion — Lever 1 — Go-to-Market Channel Expansion
_Growth Opportunities · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Grade each acquisition channel for headroom and economics.

**Must contain**
- Channel rows: direct salesforce, reseller / intermediary partners, institutional referral partners.
- Estimated share of economics per channel (management-sourced) with the margin trade-off noted.
- Growth-potential commentary per channel with supporting quotes from market participants.
- Implication column; the nascent high-headroom channel highlighted as the near-term opportunity.

**Admissible sources** — Interviews; management data.
**Analysis** — Evaluate channel headroom, margin profile, and scalability; prioritise accordingly.
**Exhibit** — Channel table with economics chips, quote cells, and implication rail.
**Quality bar** — Channel economics are management-sourced or triangulated — not guessed.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MSS, GRO |
| Secondary modules | CSG |
| Metrics this slide may state | `comp.share` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Channel, reach and economics | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Build, buy or partner | {'max_items': 5, 'max_chars_item': 170} |

## 76 · S076_l2_partner_whitespace — Lever 2 — Partner Whitespace Mapping
_Growth Opportunities · archetype `table_full` · exhibit `heat_grid` · gate **research_gated**_

**Purpose** — Locate the unpenetrated partner cells worth the most.

**Must contain**
- Twin 100% stacked panels: whitespace by vertical (count of firms) and by size tier ($ value), each split penetrated vs unpenetrated.
- Totals above every column (firm counts; $ values).
- Framing bullets: where penetration remains lowest and new-logo potential is highest.
- Note that most of the $ whitespace concentrates in the largest tier.

**Admissible sources** — Web survey; firmographic data.
**Analysis** — Cross low-penetration cells with high value to rank the whitespace.
**Exhibit** — Twin stacked panels with totals and whitespace shading.
**Quality bar** — Whitespace is defined identically in both panels — count and value views reconcile.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | GRO, SUP |
| Secondary modules | MSS |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 77 · S077_l2_partner_willingness — Lever 2 — Partner Adoption Willingness
_Growth Opportunities · archetype `chart_commentary` · exhibit `grouped_bar` · gate **research_gated**_

**Purpose** — Show the whitespace is willing, not just present.

**Must contain**
- Panel 1: non-adopters' likelihood-to-adopt distribution (1–7 scale; mean, likely-share, n).
- Panel 2: adopters' willingness to extend to a full-suite solution (same scale; mean, likely-share, n).
- Commentary rail: adoption barriers are largely perceptual, not technical — with quotes; where the Target eases friction (security, compliance, onboarding).
- Conversion implication stated plainly.

**Admissible sources** — Web survey; interviews.
**Analysis** — Quantify the conversion runway; identify the friction the Target must remove.
**Exhibit** — Paired distribution stacks + commentary rail.
**Quality bar** — The 'likely to adopt' threshold is defined on-page.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | GRO, SUP |
| Secondary modules | BBH |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C12-AVERAGE, C9-INDEX |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Partner adoption willingness | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | What partners need to say yes | {'max_items': 5, 'max_chars_item': 170} |

## 78 · S078_l2_partner_scaling — Lever 2 — Scaling Within Partner Ecosystems
_Growth Opportunities · archetype `table_commentary` · exhibit `banded_table` · gate **research_gated**_

**Purpose** — Show adoption deepening inside existing partners — volume growth without new logos.

**Must contain**
- Trend bars: share of partner-customer volume flowing through the embedded solution — past, present, and expected future — with deltas.
- Commentary: what accelerates end-customer uptake inside a partner base, with quotes (integration value, faster delivery, packaged incentives).
- The Target's role in accelerating adoption stated explicitly.

**Admissible sources** — Web survey; interviews.
**Analysis** — Project embedded adoption within existing partner bases from respondent expectations.
**Exhibit** — Three-bar adoption trend with delta chips + quote commentary.
**Quality bar** — The forecast bar is labelled as respondent expectation — not an advisor projection.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | GRO, SUP |
| Secondary modules | SCR |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Scaling mechanics within a partner | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Evidence and constraints | {'max_items': 5, 'max_chars_item': 170} |

## 79 · S079_l3_expand_accounts — Lever 3 — Expanding Existing Accounts
_Growth Opportunities · archetype `chart_commentary` · exhibit `walkup` · gate **conditional**_

**Purpose** — Prove the base itself grows: volume expansion plus service attach.

**Must contain**
- Left panel: average account value trend over the last 3 periods (rising bars).
- Middle panel: customers' spend trajectory — past 3 years vs next 3 years (increased / unchanged / decreased, n).
- Right rail: the two expansion mechanisms labelled — growing transaction volume and value-added service attach — each with a supporting quote.
- Stickiness evidence quoted to underpin the expansion runway.

**Admissible sources** — Management KPIs; web survey; interviews.
**Analysis** — Decompose account growth into volume vs attach; evidence both.
**Exhibit** — Account-value bars + spend-trajectory panel + mechanism rail.
**Quality bar** — The expansion claim rests on data and quotes together.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CST, RVQ |
| Secondary modules | GRO, MPR, CFL |
| Metrics this slide may state | `fin.recurring_share`, `cust.retention` |
| Transformation rules | T1-EXTRACT, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T5-CALCULATE, T8-FACT-VS-VIEW |
| Calculations | C11-MARGIN, C4-MIX, C7-CAGR, C8-UNIT-NORMALISE |
| Source priority | R1, R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `chart` | chart | Expansion within existing accounts | {'max_series': 4, 'max_points': 12} |
| `right` | bullets | Cross-sell and upsell evidence | {'max_items': 5, 'max_chars_item': 170} |

## 80 · S080_l4_pricing — Lever 4 — Pricing Optimization
_Growth Opportunities · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Show the market will absorb price moves — then name the structures to use.

**Must contain**
- Expected price-change distribution stack (increase / no change / decrease bands with %, mean expected change, n).
- Commentary: share anticipating increases; the pricing structures available (differentiated models, value-based, service-backed).
- Headroom evidence: quotes indicating the Target is competitively priced with room to move.
- Positioning: optimization framed as opportunity, sequenced after value delivery.

**Admissible sources** — Web survey; interviews.
**Analysis** — Read elasticity signals; match pricing structures to segments and value delivered.
**Exhibit** — Price-expectation stack + commentary rail with quotes.
**Quality bar** — Pricing recommendations are flagged as opportunities — not committed plans.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MPR, RVQ |
| Secondary modules | CSC, BBH |
| Metrics this slide may state | `mkt.price_benchmark`, `fin.gross_margin` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C11-MARGIN, C4-MIX |
| Source priority | R1, R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Pricing action, uplift and risk | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Evidence of headroom | {'max_items': 5, 'max_chars_item': 170} |

## 81 · S081_l5_adjacent_segments — Lever 5 — Adjacent Segment Expansion
_Growth Opportunities · archetype `table_full` · exhibit `scorecard` · gate **conditional**_

**Purpose** — Size the adjacencies and show the capabilities that carry over.

**Must contain**
- Walkup waterfall: current SAM + named adjacent verticals ($ increment each) = expanded SAM.
- Resonance annotations on the waterfall: which existing capabilities transfer to each adjacency.
- Key-levers rail: numbered actions to unlock the expansion (tailored onboarding, distribution partnerships, workflow alignment, bundled services).
- Vertical composition stacked inside each bar.

**Admissible sources** — Market model; interviews.
**Analysis** — Size adjacencies with the same rigor as the core; test capability transfer honestly.
**Exhibit** — Walkup waterfall with resonance callouts + numbered lever rail.
**Quality bar** — Adjacency sizing uses the identical methodology as core sizing.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | GRO, MDF |
| Secondary modules | CSG, MVG |
| Metrics this slide may state | `mkt.sam` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 82 · S082_l6_product_expansion — Lever 6 — Product Expansion Requirements
_Growth Opportunities · archetype `table_commentary` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Specify what must be built to win each expansion vertical.

**Must contain**
- Rows per target vertical (the named adjacencies).
- Column 1: vertical-specific integration / API requirements, 2–3 per vertical with use cases.
- Column 2: vertical-specific value-added service chips (6–9 per vertical).
- Requirements sourced from operators in each vertical; build-vs-buy noted where relevant.

**Admissible sources** — Interviews with vertical operators; product benchmarking.
**Analysis** — Map required capabilities per vertical against the current stack; gap-list the build.
**Exhibit** — Vertical × capability requirement grid with service chips.
**Quality bar** — Requirements come from vertical operators — not internal assumption.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | IPT, GRO |
| Secondary modules | STR, CDF |
| Metrics this slide may state | `ops.tech_stack` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `left` | table | Capability required vs capability held | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Build effort and sequencing | {'max_items': 5, 'max_chars_item': 170} |

## 83 · S083_l7_ma — Lever 7 — Strategic M&A
_Growth Opportunities · archetype `table_full` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Use the acquisition track record to underwrite the forward M&A thesis.

**Must contain**
- Track-record table: numbered past acquisitions with dates and one-line rationale each.
- Forward thesis panels grouped by objective: distribution expansion · technology / product enhancement · vertical market entry.
- Sample acquisition criteria per objective (target profiles, characteristics).
- Integration-capability note: playbook and tools that de-risk execution.

**Admissible sources** — Management information; interviews.
**Analysis** — Derive repeatable acquisition criteria from what past integrations actually delivered.
**Exhibit** — Track-record table + three objective panels with criteria.
**Quality bar** — Forward criteria are consistent with demonstrated integration capacity.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | SYN, STR |
| Secondary modules | GRO, FVR, VAL |
| Metrics this slide may state | `val.synergy`, `val.multiple` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C14-SUM, C15-NET |
| Source priority | R1, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E6-SUITABILITY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

## 84 · S084_div_appx_partners — Section Divider — Appendices
_Appendix A - Partner & Vendor Landscape · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Open the appendix and list its lettered parts.

**Must contain**
- Appendix list: A — Landscape · B — Market Sizing Methodology · C — Case Studies · D — Supplementary Data.
- Standard divider branding; re-shown before each part with the current part highlighted.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with lettered appendix list.
**Quality bar** — Appendix letters and titles match the contents page.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 85 · S085_landscape_by_category — Landscape Map (1 of 2) — By Category
_Appendix A - Partner & Vendor Landscape · archetype `table_full` · exhibit `banded_table` · gate **conditional**_

**Purpose** — Reference map of the partner / vendor universe, grouped by category.

**Must contain**
- Logo wall grouped into major categories (generalist tools, vertical specialists by industry, marketplaces).
- Sub-category labels inside each group (by function or industry).
- Non-exhaustive marker.
- Categorization consistent with the segmentation used in the body.

**Admissible sources** — Secondary research.
**Analysis** — None — reference material supporting the market and growth chapters.
**Exhibit** — Category-grouped logo wall with sub-labels.
**Quality bar** — The categorization scheme matches the market chapters exactly.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CID |
| Secondary modules | MDF |
| Metrics this slide may state | `comp.set` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 86 · S086_landscape_by_size — Landscape Map (2 of 2) — By Category & Size
_Appendix A - Partner & Vendor Landscape · archetype `table_full` · exhibit `banded_table` · gate **conditional**_

**Purpose** — The same universe cut by customer-size tier.

**Must contain**
- Table: category rows (one per vertical / function) × two logo columns (smaller-tier examples vs enterprise examples).
- Row grouping mirrors page 1 of the landscape.
- Logos current and correctly classified.

**Admissible sources** — Secondary research.
**Analysis** — None — reference material.
**Exhibit** — Category × size-tier logo table.
**Quality bar** — Examples are current, correctly tiered, and correctly categorized.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | CID |
| Secondary modules | MSS |
| Metrics this slide may state | `comp.set`, `comp.share` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 87 · S087_partner_counts — Partner Counts & Retention Data
_Appendix A - Partner & Vendor Landscape · archetype `table_full` · exhibit `banded_table` · gate **research_gated**_

**Purpose** — The reference table behind the whitespace and retention claims.

**Must contain**
- Table rows by partner size tier: revenue opportunity per partner, firm count, total opportunity, retention benchmarks by relationship type.
- Retention shown for both relationship archetypes (embedded customer-level and partner-level).
- Sourcing note for counts and retention estimates.

**Admissible sources** — Firmographic data; web survey; interviews.
**Analysis** — Reconcile counts × per-firm value against the whitespace sizing in the growth chapter.
**Exhibit** — Single reference table with tier rows.
**Quality bar** — Totals tie to the whitespace page — one source of truth.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | SUP, CST |
| Secondary modules | GRO |
| Metrics this slide may state | `ops.supplier_concentration` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 88 · S088_div_appx_sizing — Section Divider — Appendix B
_Appendix B - Market Sizing Methodology · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the appendix divider with Market Sizing Methodology highlighted.

**Must contain**
- Lettered appendix list with part B highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with appendix list, current part emphasised.
**Quality bar** — Highlight state matches the reader's position.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 89 · S089_sizing_method_core — Market Sizing Methodology — Core Opportunity
_Appendix B - Market Sizing Methodology · archetype `method_flow` · exhibit `method_flow` · gate **core**_

**Purpose** — Document the core-market model step by step so it can be rebuilt.

**Must contain**
- Top flow: total volume (by size / vertical) → channel share → maximum economics → TAM, with source and approach labels per step.
- Bottom flow: addressable volume → observed economics by mode → adoption % → penetration % → vended market.
- Source tags on every box (statistical data, primary research, survey, benchmarks).
- Key assumptions stated inline (e.g., mode mix, excluded volumes, tier boundaries).

**Admissible sources** — Statistical series; web survey; primary research; benchmarks.
**Analysis** — Document every step and assumption so the model is fully reproducible.
**Exhibit** — Left-to-right methodology flow diagrams with source tags.
**Quality bar** — A reviewer can rebuild the model from this page alone.
**Gate** — core: must render; built from fallback modules if the module-of-record is absent (E12), blocker if neither is available (E9)

| Mapping | Value |
|---|---|
| Primary modules | MVG, MDF |
| Fallback modules | MDF, SCM — use raises E12-SUBSTITUTION and must be stated on the slide |
| Secondary modules | SCM |
| Metrics this slide may state | `mkt.tam`, `mkt.sam` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T2-COMBINE, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C2-COVERAGE, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E3-CONFLICT, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Core opportunity - step by step | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Assumptions, sources and sensitivity | {'max_items': 5, 'max_chars_item': 170} |

## 90 · S090_sizing_method_adjacent — Market Sizing Methodology — Adjacent Opportunity
_Appendix B - Market Sizing Methodology · archetype `method_flow` · exhibit `method_flow` · gate **conditional**_

**Purpose** — Document the value-added opportunity model to the same standard.

**Must contain**
- Top flow: eligible customer counts × average spend per period × annualization → TAM, with sources per input.
- Bottom flow: TAM → adoption % → penetration % → vended market, survey-sourced.
- Eligibility filter stated (only adopters of the core service count).
- Segmentation note: primary cuts by vertical and size.

**Admissible sources** — Firmographic counts; price benchmarks / management price sheets; web survey.
**Analysis** — Apply the same reproducibility standard as the core model; keep segmentation consistent.
**Exhibit** — Two methodology flow rows with source tags.
**Quality bar** — Segmentation is consistent with the core model — the two reconcile.
**Gate** — conditional: rendered only if the primary modules supply >= 3 populated facts; otherwise withheld and logged E1

| Mapping | Value |
|---|---|
| Primary modules | MVG, GRO |
| Secondary modules | MPR |
| Metrics this slide may state | `mkt.sam` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T11-TRIANGULATE, T12-COMPANY-VS-MARKET, T2-COMBINE, T5-CALCULATE, T7-CONFIDENCE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C2-COVERAGE, C8-UNIT-NORMALISE |
| Source priority | R2, R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E4-UNIT-MISMATCH |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `flow` | table | Adjacent opportunity - step by step | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `right` | bullets | Assumptions, sources and sensitivity | {'max_items': 5, 'max_chars_item': 170} |

## 91 · S091_div_appx_cases — Section Divider — Appendix C
_Appendix C - Case Studies · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the appendix divider with Case Studies highlighted.

**Must contain**
- Lettered appendix list with part C highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with appendix list, current part emphasised.
**Quality bar** — Highlight state matches the reader's position.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 92 · S092_case_lost_prospect — Case Study — Lost Prospect
_Appendix C - Case Studies · archetype `three_panel` · exhibit `case_study` · gate **research_gated**_

**Purpose** — Tell the story of a deal the Target lost — and what would reopen it.

**Must contain**
- Profile rail: organisation logo, name, and descriptor.
- Adoption history: how and why the organisation built its current approach, with quotes.
- Evaluation & decision: why the winning competitor was chosen; how the Target was perceived, including the specific concern that lost the deal — quoted verbatim.
- Future outlook: openness to adding providers, and the conditions that would favour the Target.

**Admissible sources** — Prospect interview.
**Analysis** — Extract the loss reasons and re-entry conditions without varnish.
**Exhibit** — Profile rail + three-block narrative (adoption / decision / outlook) with quotes.
**Quality bar** — Loss reasons are reported unvarnished — this page is credibility currency.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | BBH, CSA |
| Secondary modules | CDF |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T3-SUMMARISE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `p1` | bullets | Situation | {'max_items': 5, 'max_chars_item': 120} |
| `p2` | bullets | Evaluation | {'max_items': 5, 'max_chars_item': 120} |
| `p3` | bullets | Outcome and lesson | {'max_items': 5, 'max_chars_item': 120} |

## 93 · S093_case_competitor_customer — Case Study — Competitor's Customer
_Appendix C - Case Studies · archetype `three_panel` · exhibit `case_study` · gate **research_gated**_

**Purpose** — Profile a customer of a competitor whose dissatisfaction creates an opening.

**Must contain**
- Profile rail: organisation logo, name, descriptor.
- Adoption history: initial provider choices and the rationale, quoted.
- Evaluation & decision: the criteria that drove the current selection (liability, coverage, economics), quoted.
- Future outlook: the pain points (e.g., vertical-support limits, onboarding friction) that open the door for the Target — mapped to Target capabilities.

**Admissible sources** — Competitor-customer interview.
**Analysis** — Identify whether the opening is displacement or supplement; map pains to Target strengths.
**Exhibit** — Profile rail + three-block narrative with quotes.
**Quality bar** — Opening claims tie directly to the customer's stated pain points.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CID, CSA |
| Secondary modules | BBH |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T3-SUMMARISE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `p1` | bullets | Situation | {'max_items': 5, 'max_chars_item': 120} |
| `p2` | bullets | Evaluation | {'max_items': 5, 'max_chars_item': 120} |
| `p3` | bullets | Outcome and lesson | {'max_items': 5, 'max_chars_item': 120} |

## 94 · S094_case_existing_customer — Case Study — Existing Customer
_Appendix C - Case Studies · archetype `three_panel` · exhibit `case_study` · gate **research_gated**_

**Purpose** — Evidence entrenchment and expansion potential inside the Target's own base.

**Must contain**
- Profile rail: customer logo, name, respondent title, plus scored metrics (advocacy score, likelihood-to-continue) with scales.
- Usage journey: how the customer adopted and how the solution is embedded in daily operations, quoted.
- Satisfaction and future expectations: what they value, what they would improve, and expansion asks — quoted.
- Key-takeaways rail: 3 synthesis bullets (mission-critical integration; retention with upside; scalability).

**Admissible sources** — Customer interview.
**Analysis** — Evidence entrenchment mechanisms and the concrete product asks that unlock expansion.
**Exhibit** — Profile rail with score chips + narrative blocks + takeaways column.
**Quality bar** — Scores are displayed with their scales; improvement asks are included, not filtered.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CSA, CST |
| Secondary modules | CDF |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T3-SUMMARISE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `p1` | bullets | Situation | {'max_items': 5, 'max_chars_item': 120} |
| `p2` | bullets | Evaluation | {'max_items': 5, 'max_chars_item': 120} |
| `p3` | bullets | Outcome and lesson | {'max_items': 5, 'max_chars_item': 120} |

## 95 · S095_div_appx_supp — Section Divider — Appendix D
_Appendix D - Supplementary Data · archetype `divider` · exhibit `divider` · gate **always**_

**Purpose** — Re-show the appendix divider with Supplementary Data highlighted.

**Must contain**
- Lettered appendix list with part D highlighted as current.
- Standard divider branding.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Branded divider with appendix list, current part emphasised.
**Quality bar** — Highlight state matches the reader's position.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 96 · S096_supp_entrenchment — Supplementary Data — Entrenchment Evidence
_Appendix D - Supplementary Data · archetype `table_full` · exhibit `heat_grid` · gate **research_gated**_

**Purpose** — Backing detail for the stickiness claims made in the body.

**Must contain**
- Twin distribution panels (1–7 scale): likelihood to continue using the current solution, one per customer group.
- Means, top-2 shares, and n beneath each panel.
- Framing line: both relationship archetypes exhibit similar stickiness.
- Cross-reference to the body pages this data supports.

**Admissible sources** — Web survey.
**Analysis** — Hold the full distributions here so body pages stay clean; keep scales identical.
**Exhibit** — Paired distribution stacks with stat labels.
**Quality bar** — Cross-referenced from the body — supplementary data is never orphaned.
**Gate** — research_gated: rendered only if the corpus contains a survey or interview source; otherwise withheld and logged E11

| Mapping | Value |
|---|---|
| Primary modules | CST |
| Secondary modules | CSA, RVQ, APX |
| Metrics this slide may state | `cust.retention`, `cust.tenure` |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T4-RECLASSIFY, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R4, R5 |
| Exception handling | E1-NOT-PROVIDED, E11-NO-PRIMARY, E3-CONFLICT |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 97 · S097_back_cover — Back Cover
_Appendix D - Supplementary Data · archetype `back_cover` · exhibit `cover` · gate **always**_

**Purpose** — Close the report with the standard brand page.

**Must contain**
- Firm logo, tagline, and copyright / web line only.
- No content, findings, or contact-specific data beyond the standard block.
- Design identical to the front-cover brand treatment.

**Admissible sources** — Brand assets.
**Analysis** — None.
**Exhibit** — Full-bleed branded closing page.
**Quality bar** — Branding matches the front cover exactly.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `back_contact` | text | — | {'max_chars': 320} |

## 98 · S098_div_appx_audit — Section Divider — Evidence & Audit Trail
_Appendix E - Evidence & Audit Trail · archetype `divider` · exhibit `divider` · gate **always**_  · _DiligenceIQ extension, not in the blueprint_

**Purpose** — Open the audit trail that makes every preceding page checkable.

**Must contain**
- Section number and name.
- One line naming what the appendix contains.

**Admissible sources** — Deck template.
**Analysis** — None.
**Exhibit** — Section divider.
**Quality bar** — A reviewer knows, before turning the page, that every figure in the report can be traced.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T0-AUTO |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

## 99 · S099_module_verdicts — Module Verdicts & Confidence
_Appendix E - Evidence & Audit Trail · archetype `table_full` · exhibit `banded_table` · gate **always**_  · _DiligenceIQ extension, not in the blueprint_

**Purpose** — Show what each diligence module concluded and how much weight its conclusion carries.

**Must contain**
- One row per agent module: verdict, stated confidence, evidence-adjusted confidence (T7), coverage %.
- Modules that returned insufficient or inconclusive findings visually marked.
- Core modules distinguished from supporting modules.
- Slides that depend on a weak module cross-referenced.

**Admissible sources** — Run data: module registry, evidence index, coverage computation.
**Analysis** — Apply T7-CONFIDENCE. Do not restate the module's own confidence without the coverage adjustment.
**Exhibit** — Banded table, one band per module role, RAG pills on confidence.
**Quality bar** — A reader can see at a glance which conclusions in the report are thinly evidenced.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C2-COVERAGE, C3-VERDICT-COUNT |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 100 · S100_source_register — Source Register
_Appendix E - Evidence & Audit Trail · archetype `table_full` · exhibit `banded_table` · gate **always**_  · _DiligenceIQ extension, not in the blueprint_

**Purpose** — List every source the report rests on, with what it evidenced.

**Must contain**
- One row per distinct source artefact: name, data-room node, doc type, provenance class, citation count.
- Web and analyst sources listed separately from data-room documents.
- Sources cited by the agents but absent from the data room flagged (E10).
- Synthetic or illustrative sources marked.

**Admissible sources** — Run data: evidence index citation graph.
**Analysis** — Mechanical. No interpretation.
**Exhibit** — Banded table grouped by provenance class.
**Quality bar** — Every source line on every slide resolves to exactly one row here.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Secondary modules | APX |
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Calculations | C1-COUNT |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._

## 101 · S101_exceptions — Exceptions & Diligence Gaps
_Appendix E - Evidence & Audit Trail · archetype `table_full` · exhibit `banded_table` · gate **always**_  · _DiligenceIQ extension, not in the blueprint_

**Purpose** — State plainly what the report could not establish and what follow-up is required.

**Must contain**
- One row per exception: severity, rule id, issue, slides affected, source, treatment applied.
- Slides dropped by a coverage gate listed with the reason and what would unlock them.
- Critical exceptions repeated at the top, not buried in severity order alone.
- A named follow-up request for each HIGH and CRITICAL item.

**Admissible sources** — Run data: exception log from ingest, evidence index, content check and QA.
**Analysis** — Mechanical assembly; severity per the E-rules.
**Exhibit** — Banded table grouped by severity, critical band first.
**Quality bar** — Nothing the deck could not evidence is invisible: every gap appears here with a named next step.
**Gate** — always: rendered unconditionally

| Mapping | Value |
|---|---|
| Transformation rules | T1-EXTRACT, T10-NARRATIVE-TO-TABLE, T12-COMPANY-VS-MARKET, T2-COMBINE, T8-FACT-VS-VIEW, T9-DEDUP |
| Source priority | R3, R5 |
| Exception handling | E1-NOT-PROVIDED |

| Element | Type | Panel heading | Limits |
|---|---|---|---|
| `table` | table | — | {'max_rows': 9, 'max_cols': 6, 'max_chars_cell': 90} |
| `takeaway` | text | — | {'max_chars': 320} |

_Repeatable: supply a list of pages in content.json when the content exceeds one page._
