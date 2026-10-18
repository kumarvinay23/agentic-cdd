# DiligenceIQ Agent Prompt Framework — Gap Analysis & Per-Agent Implementation Plan

**Source:** `DiligenceIQ_Reusable_Agent_Prompt_Framework_Latest.docx` (Version 3)  
**Compared to:** `prompt_book/*`, `agent_document_*.py`, `pipeline_catalog.py` PHASE1–4  
**Goal:** Close framework gaps **agent by agent**, starting with shared controls then Cash Flow (largest hole).

---

## How the framework says to run each agent

1. Shared analysis prompt + agent required standard + default analysis prompt + evidence checklist  
2. Draft output  
3. Shared QA prompt + agent-specific QA  
4. Repair, rerun failed checks, reconcile shared findings  

Every output must include **Questions and inputs required** (exact records, decision effect, owner, timing, closure test, interim treatment).  
Quality and reliance are **separate**: PASS + BLOCKED is valid.

---

## Shared gaps (do once — benefits all agents)

| # | Work | Effort |
|---|---|---|
| S0 | Extend `house_rules.md`: claim-ID + source categories (VDR primary / management assertion / computed / interview / external); six-section skeleton; fuller deal slots (perimeter, transaction type, as-of, decision stage) | L |
| S1 | Add `prompt_book/shared_qa.md` + post-draft QA path: cite-reopen, recalculation, **QA issue register** (Critical/Major/Minor) | L |
| S2 | Standardise **Questions and inputs required** schema across all agents | M |
| S3 | Shared cite-reopen + bridge recalculation helpers | M |

**Status today:** `house_rules.md` covers numbers, no-invention, dual Quality/Reliance; it does **not** yet mandate claim taxonomy, six-section layout, or a QA issue register.

---

## Inventory deltas

### Framework agents missing or stubbed in code

| Framework agent | Code status |
|---|---|
| **Cash Flow** | ✅ Done — `prompt_book/cash_flow.md` + `agent_document_cash_flow.py` (overlays thin deep_dive heuristic) |
| **Appendices** | ✅ Done — `appendices` (FV-08) aggregator; reports consume registers |
| Sensitivity Analysis / Final Valuation Range | Nested under `valuation_modeling`, not first-class Phase-4 keys |
| Executive Summary | Mapped to `ic_synthesis` |

### Code agents not in framework H1 list (keep — they feed others)

`deal_context_and_objectives`, `company_background`, `historical_performance`, `execution_risk`, `compensation_alignment`, `trading_comps`, `precedent_transactions`, `valuation_modeling`

---

## Suggested execution order

Execute **one agent at a time**. After each: unit tests for that agent’s schema/QA, run on a sample deal (e.g. test6 / Compost Crew), then move on.

| Order | Agent | Slug | Effort | Status | Why this order |
|---:|---|---|---|---|---|
| 0 | Shared house_rules + shared QA | — | L | DONE | Unlocks every later agent |
| 1 | Deal Context | `deal_context_and_objectives` | M | DONE | Perimeter / thesis for all |
| 2 | Scope and Methodology | `scope_and_methodology` | M | DONE | Coverage matrix / blockers |
| 3 | Company Background | `company_background` | M | DONE | Operating model facts |
| 4 | Historical Performance | `historical_performance` | M | DONE | P&L fact register |
| **5** | **Cash Flow** | `cash_flow` | **L** | **DONE** | Bridges + WC + liquidity; dual-write metrics |
| 6 | Market Definition | `market_definition` | M | DONE | Perimeter for market stack |
| 7 | Market Volume and Growth | `market_volume_and_growth` | M | DONE | Depends on 6 |
| 8 | Market Pricing | `market_pricing` | M | DONE | |
| 9 | Demand Drivers | `demand_drivers` | M | DONE | |
| 10 | Competitor Identification | `competitor_identification` | M | strong | ✅ DONE |
| 11 | Competitive Differentiation | `competitive_differentiation` | M | strong | ✅ DONE |
| 12 | Market Share Strategy | `market_share_strategy` | M | strong | ✅ DONE |
| 13 | Customer Segmentation | `customer_segmentation` | S–M | strong | ✅ DONE |
| 14 | Customer Stickiness | `customer_stickiness` | S–M | strong | ✅ DONE |
| 15 | Customer Satisfaction | `customer_satisfaction` | M | partial | ✅ DONE |
| 16 | Buying Behavior | `buying_behavior` | M | partial | ✅ DONE |
| 17 | Supplier Dependence | `supplier_dependence` | M | partial | ✅ DONE |
| 18 | Cost Structure | `cost_structure` | M | strong | ✅ DONE |
| 19 | Supply Chain Resilience | `supply_chain_resilience` | M | strong | ✅ DONE |
| 20 | Operational Risk | `operational_risk` | M | strong | ✅ DONE |
| 21 | Revenue Quality | `revenue_quality` | M | ✅ DONE | billing↔recognised / taxonomy / ARR / Stickiness+CF |
| 22 | Capital Structure | `capital_structure` | M | ✅ DONE | schedule gate / cap table / approved EBITDA / financing link |
| 23 | Management Quality | `management_quality` | M | ✅ DONE | roster / incentives / vacancy enum / checklist |
| 24–27 | Foundations depth: Strategy / Regulatory / IP / ESG | (phase 2 slugs) | M each | partial | After financial spine |
| 28–31 | Market Risk / Internal Risk / Growth / Synergies | (phase 3) | M each | partial | 28–31 ✅ |
| 32 | SWOT | `swot_analysis` | M | strong | ✅ DONE |
| 33–35 | Sensitivity / Final Valuation / Valuation Modeling | nested + `valuation_modeling` | M | ✅ DONE | nest + CF DCF gate |
| 36 | Recommendations | `recommendation` | M | ✅ DONE | decision stage / CP schema / blocked WS |
| 37 | Executive Summary (IC Synthesis) | `ic_synthesis` | M | ✅ DONE | register-only / thesis 3–5 / decision support |
| 38 | Appendices | `appendices` | L | ✅ DONE | FV-08 aggregator; reports consume registers |

---

## Per-agent implementation plans

Each plan is self-contained. When you say “do Agent N”, implement only that agent’s steps + its tests.

### 0 — Shared controls ✅ DONE

1. Extend `house_rules.md` with claim-ID + source categories and six-section skeleton. ✅  
2. Add deal-slot vars: perimeter, transaction type, as-of, decision stage. ✅  
3. Add `prompt_book/shared_qa.md` (cite-reopen, recalc, issue register). ✅  
4. Wire post-draft QA compose (`compose_qa` / `shared_qa_prompt`) in `prompt_book`. ✅  
   (Per-agent runners adopt `compose_qa` as each agent is executed.)  
5. Standardise Questions schema in `prompt_book/shared_controls.py`. ✅  
6. Shared helpers: `cite_reopen`, `recalculate_bridge`, claim/QA normalisers. ✅  
7. Tests: `tests/test_prompt_book_shared.py`. ✅

### 1 — Deal Context (`deal_context_and_objectives`) ✅ DONE

1. Export full deal-slot set into compose fill. ✅  
2. Harden fact ledger (15–25 facts) with locators. ✅ (existing + kept)  
3. Must-be-true hypotheses with `tested_by_agent`. ✅  
4. Questions for perimeter unknowns with closure tests. ✅  
5. Dual Quality/Reliance already present — keep. ✅  
6. Tests on sample deal perimeter export. ✅

### 2 — Scope and Methodology (`scope_and_methodology`) ✅ DONE

1. Coverage matrix auto-includes every Phase 2–4 slug status. ✅  
2. Columns: completed / planned / unavailable + reliance limitation. ✅  
3. Persist VDR retrieval log + engagement scope as evidence. ✅  
4. Pack-wide interview register (date/participants/status). ✅ (existing fieldwork)  
5. Prioritise unfinished work by price/structure/decision impact. ✅  
6. Questions with closure tests. ✅  
7. QA: fail “comprehensive” if critical question unfinished. ✅

### 3 — Company Background (`company_background`) ✅ DONE

1. Service / customer / geo splits reconciled to revenue. ✅ (existing)  
2. Sites, capacity, headcount. ✅ (existing)  
3. Ownership / legal entities. ✅ (existing)  
4. Operating model clear enough that market agents don’t invent one. ✅ (existing)  
5. Omit-inapplicable with reason. ✅ (existing)  
6. Questions + dual verdicts. ✅

### 4 — Historical Performance (`historical_performance`) ✅ DONE

1. Period-labelled P&L (actual / YTD / forecast never mixed). ✅  
2. Growth and margin direction with formulas. ✅  
3. CIM vs accounts reconcile. ✅ (existing + kept)  
4. Seasonality / YTD shape. ✅ (existing + kept)  
5. Comparability distortions called out. ✅ (existing + kept)  
6. Publish as shared fact register for Cash Flow / Valuation. ✅  
7. Questions closure schema + deal slots. ✅

### 5 — Cash Flow (`cash_flow`) ✅ DONE

1. Add `prompt_book/cash_flow.md` from framework default analysis + checklist. ✅  
2. Register in `prompt_book` agent files. ✅  
3. Create `agent_document_cash_flow.py` (pattern: capital_structure). ✅  
4. Spec: monthly open→close cash; EBITDA→OCF→FCF; WC; maint vs growth capex; financing; one-offs. ✅  
5. DSO/DPO/inventory only with matching denominators. ✅  
6. Liquidity / runway / downside; missing ≠ distress. ✅  
7. Dual verdicts + Questions closure schema. ✅  
8. Wire documents / library / render / SWOT upstream. ✅  
9. Replace thin `deep_dive_financial` heuristic. ✅ (composer overlays legacy extract)  
10. QA recalculation of bridges. ✅

### 6 — Market Definition (`market_definition`) ✅ DONE

1. Four-axis perimeter object as shared fact. ✅  
2. Double-count exclusions. ✅  
3. TAM/SAM/SOM with assumption list + formulas. ✅  
4. Broad market = context unless matched. ✅  
5. Right-to-win deferred flag. ✅  
6. Export perimeter for Volume / Pricing / Share. ✅ (`perimeter_export`)  
7. QA: same perimeter/date/unit across comparisons. ✅  
8. Questions closure schema + deal slots. ✅  
9. SWOT harvest + deep_dive volume prefers export. ✅

### 7 — Market Volume and Growth (`market_volume_and_growth`) ✅ DONE

1. Bind series to Market Definition perimeter. ✅ (`perimeter_binding`)  
2. Separate volume vs value. ✅  
3. Endpoint CAGR reperform. ✅  
4. Organic vs share vs M&A bridge. ✅  
5. Bottom-up vs external triangulation. ✅ (existing + kept)  
6. Scenario / adoption sensitivity. ✅  
7. Vintage / unavailable actual labelling. ✅  
8. Questions closure schema + deal slots. ✅  
9. SWOT harvest prefers growth note / plan multiple. ✅

### 8 — Market Pricing (`market_pricing`) ✅ DONE

1. Realised net price from invoices/contracts by segment. ✅  
2. Normalise scope / discounts / taxes. ✅  
3. Named competitor like-for-like comps. ✅ (existing + kept)  
4. List vs realised vs mix. ✅  
5. Post-increase volume/churn response (not invented elasticity). ✅  
6. Price-volume-cost → GP/EBITDA. ✅  
7. Cross-check Growth Opportunities / Revenue Quality / Sensitivity. ✅  
8. Questions closure schema + deal slots. ✅  
9. SWOT harvest. ✅

### 9 — Demand Drivers (`demand_drivers`) ✅ DONE

1. Driver schema: mechanism, population, timing, magnitude, persistence, evidence. ✅  
2. Mandate vs grant vs voluntary vs opex saving. ✅  
3. Transmission to volume/price. ✅  
4. Cyclicality from company history. ✅  
5. Rank by evidenced contribution. ✅  
6. Anti-double-count with Volume/Growth. ✅  
7. Regulatory cross-check. ✅  
8. Hypothesis register for untested drivers. ✅  
9. Questions closure schema + deal slots. ✅  
10. SWOT harvest. ✅

### 10 — Competitor Identification (`competitor_identification`) ✅ DONE

1. Named competitor rows (geography, overlap, source). ✅
2. Role taxonomy. ✅
3. Target as reference row only. ✅
4. Win/loss / tender evidence fields. ✅
5. Barrier evidence fields. ✅
6. Entity/geography QA; reject anonymous columns. ✅
7. Uncertainty for unverified capabilities. ✅
8. Questions schema + deal slots + prompt/SWOT/tests. ✅

### 11 — Competitive Differentiation (`competitive_differentiation`) ✅ DONE

1. Claim → test schema (benefit, alternative, metric, evidence, economics, durability). ✅
2. Ordinary vs assertion vs demonstrated. ✅
3. Economic effect quantification. ✅
4. Replication cost/time. ✅
5. Hold-period erosion. ✅
6. Cross-check NPS/retention/IP before “moat”. ✅
7. Reject unsupported benchmarks. ✅
8. Questions schema + deal slots + prompt/SWOT/tests. ✅

### 12 — Market Share Strategy (`market_share_strategy`) ✅ DONE

1. Share only on matched perimeter/date/unit. ✅
2. Share change vs market growth vs M&A. ✅
3. Funnel metrics. ✅
4. Bottom-up attainable vs management ambition. ✅
5. Capacity constraints. ✅
6. Numerator↔accounts / denominator↔market reconcile. ✅
7. Gate: missing share data ≠ leader/laggard conclusion. ✅
8. Questions schema + deal slots + prompt/SWOT/tests. ✅

### 13 — Customer Segmentation (`customer_segmentation`) ✅ DONE

1. Harden ledger pointer resolution. ✅
2. Parent + location IDs. ✅
3. Mix reconcile + unclassified remainder. ✅
4. Top-1/5/10 + GP concentration. ✅
5. Top contracts expiry/termination. ✅
6. Population definition QA; reject overlapping buckets. ✅
7. Closure reproducibility test. ✅
8. Questions schema + deal slots + prompt/SWOT/tests. ✅

### 14 — Customer Stickiness (`customer_stickiness`) ✅ DONE

1. Cohort builder from customer-month ledger. ✅ (existing + kept)
2. Opening / churn / contraction / expansion / close reconcile. ✅ (existing + kept)
3. Same-population GRR/NRR/logo. ✅ (existing + kept)
4. Segment / tenure / loss reasons. ✅ (existing + kept)
5. Contract term / renewal / cancellation extract. ✅ (existing + kept)
6. Renewal cliff revenue-weighted. ✅ (existing + kept)
7. QA: exclude new logos from retention numerators. ✅ (+ Questions, deal slots, SWOT falling / exclusion harvest)

### 15 — Customer Satisfaction (`customer_satisfaction`) ✅ DONE

1. Survey metadata schema (frame, response rate, bias). ✅ (existing + kept)
2. Valid-response NPS/CSAT only. ✅ (withhold scores when unconfirmed)
3. Ops quality metrics from complaints/support. ✅ (existing + kept)
4. Association ≠ causation with Stickiness. ✅ (`related_agent` + association_only)
5. Public reviews labelled selected. ✅ (existing + kept)
6. Research design when thin. ✅ (existing + kept)
7. QA: no poor-focus-from-missing-file. ✅ (+ survey_evidence_qa, Questions, deal slots, SWOT)

### 16 — Buying Behavior (`buying_behavior`) ✅ DONE

1. Segmented buying maps (no universal cycle). ✅ (existing + QA gate)
2. Decision-maker / budget / trigger / approvals. ✅ (existing + kept)
3. Sales-cycle distributions from CRM. ✅ (CRM provenance QA)
4. Stated vs behavioural criteria. ✅ (say-vs-did QA)
5. Seasonality with controls. ✅ (controls QA)
6. Link to capacity / conversion / pricing. ✅ (existing + kept)
7. Interview sample/date/method required. ✅ (+ buying_evidence_qa, Questions, deal slots, SWOT)

### 17 — Supplier Dependence (`supplier_dependence`) ✅ DONE

1. Supplier master from AP + ops deps. ✅ (existing + QA)
2. Role classification. ✅ (`supplier_roles`)
3. Spend vs critical capacity exposure. ✅ (criticality separate + capacity in disruption)
4. Contract clause extract. ✅ (existing + kept)
5. Alternatives + switch cost/time. ✅ (existing + QA)
6. Prioritise by disruption impact. ✅ (`disruption_priority`)
7. Reconcile Supply Chain Resilience. ✅ (`scr_reconcile` + QA/Questions/deal slots/SWOT)

### 18 — Cost Structure (`cost_structure`) — ✅ DONE

1. COA map + FS reconcile (show unexplained).  
2. Driver-based fixed / variable / step.  
3. Unit economics.  
4. Inflation by category vs plan.  
5. Efficiency net of implementation cost.  
6. Non-overlap with Synergies.  
7. Allocation vs avoidable QA.  
8. No SaaS/R&D peer ratios by default.

**Shipped:** `prompt_book/cost_structure.md` deal slots + QA/Questions; `_cost_evidence_qa` /
`_questions_from_cost_gaps`; READY→LIMITED on open QA FAILs; render §§6–8; SWOT harvest on
current keys (`operating_categories`, `unit_economics`, `efficiency_opportunities`,
`cost_evidence_qa`).

### 19 — Supply Chain Resilience (`supply_chain_resilience`) — ✅ DONE

1. Physical/digital chain map.  
2. Verified deps from Supplier Dependence.  
3. Disruption scenarios (duration, output, cost, cash, recovery).  
4. Contingency plan vs tested.  
5. Alt capacity + permissions + transition time.  
6. Avoid duplicated cost impacts.  
7. Unknown resilience ≠ low resilience.

**Shipped:** `prompt_book/supply_chain_resilience.md` deal slots + QA/Questions;
`_scr_evidence_qa` / `_questions_from_scr_gaps`; chain layers + verified deps +
scenarios + alt capacity + cost dedupe; READY→LIMITED on open QA FAILs; render §§6–8;
SWOT `_harvest_supply_chain_resilience`.

### 20 — Operational Risk (`operational_risk`) — ✅ DONE

1. Process / asset / site / labour map.  
2. Capacity & utilisation.  
3. Incident / maintenance / insurance review.  
4. Disruption → revenue / EBITDA / cash.  
5. Continuity tested vs untested.  
6. Growth-plan bottleneck reconcile (needs Cash Flow).  
7. Don’t invent cyber/insurance from weak proxies.

**Shipped:** `prompt_book/operational_risk.md` deal slots + QA/Questions;
`_ops_evidence_qa` / `_questions_from_ops_gaps`; ops map + utilisation +
incident/maintenance/insurance + cash sizing + continuity + Cash Flow bottleneck
reconcile + cyber/insurance proxy guard; READY→LIMITED on open QA FAILs; render §§6–8;
SWOT `_harvest_operational_risk`.

### 21 — Revenue Quality (`revenue_quality`) ✅ DONE

1. Billing ↔ recognised reconcile.  
2. Contracted / cancellable / habitual / one-off taxonomy.  
3. Price / volume / mix / acquisition.  
4. Renewal / cancellation exposure.  
5. Pipeline vs backlog.  
6. ARR only if defined.  
7. Cross-check Stickiness + Cash Flow.  
8. Recurring ≠ enforceable backlog.

**Shipped:** `prompt_book/revenue_quality.md` deal slots + QA/Questions;
`_rq_evidence_qa` / `_questions_from_rq_gaps`; billing↔recognised + taxonomy +
PVMA bridge + renewal/cancellation + pipeline vs backlog + ARR discipline +
Stickiness/Cash Flow cross-check + recurring≠backlog; READY→LIMITED on open QA
FAILs; render §§6–8; SWOT `_harvest_revenue_quality`; deep_dive priors.

### 22 — Capital Structure (`capital_structure`) ✅ DONE

1. Facility schedule completeness gate.  
2. Debt-like catalogue.  
3. Cash split free / restricted / minimum.  
4. Change-of-control / consents.  
5. Net debt bridge sourced.  
6. Cap table fully diluted.  
7. Leverage only on approved EBITDA; alt metrics if negative EBITDA.  
8. Link financing vs acquisition debt.

**Shipped:** `prompt_book/capital_structure.md` deal slots + QA/Questions;
`_cap_evidence_qa` / `_questions_from_cap_gaps`; schedule completeness gate +
debt-like + cash split + CoC + sourced net-debt + fully diluted cap table +
approved-EBITDA leverage (alt if negative) + financing vs acquisition;
READY→LIMITED on open QA FAILs; render §§6–8; SWOT `_harvest_capital_structure`;
deep_dive Historical Performance prior for EBITDA.

### 23 — Management Quality (`management_quality`) ✅ DONE

1. Role roster: tenure, scale, plan-vs-actual.  
2. Incentive / retention clause extract.  
3. Vacancy vs capability vs info-gap enum (never infer vacancy from missing bio).  
4. Board / succession tables.  
5. Cross-check Strategic Direction / IC Synthesis / ESG.  
6. Evidence for each score.  
7. Evidence checklist closure (CVs, contracts, incentives, references).

**Shipped:** `prompt_book/management_quality.md` deal slots + QA/Questions;
`_mq_evidence_qa` / `_questions_from_mq_gaps`; roster enrichment (scale /
plan-vs-actual) + incentive clause extract + vacancy enum discipline +
board/succession + score evidence + evidence checklist + Strategy/IC/ESG
cross-check; READY→LIMITED on open QA FAILs; render §§6–8; SWOT
`_harvest_management_quality`; foundations priors.

### 24 — Strategic Direction (`strategic_direction`) ✅ DONE

1. Ambition vs approved budget vs independently tested case.
2. Revenue/EBITDA bridge by price/volume/mix/geo/M&A/costs.
3. Initiative rows: investment, capacity, owner, milestone.
4. Historical commitment vs dated actual.
5. Funding vs Cash Flow / Capital Structure.
6. Synergy vs stand-alone flag.
7. QA: no high-confidence while funding/capacity untested.

**Shipped:** `prompt_book/strategic_direction.md` deal slots + synergy/CF-CS +
QA/Questions; `_sd_evidence_qa` / `_questions_from_sd_gaps`; initiative
synergy flags; funding soft-fill from Cash Flow / Capital Structure priors;
READY→LIMITED on open QA FAILs / untested funding; render §§7–9; SWOT
`_harvest_strategic_direction`; foundations priors.

### 25 — Regulatory Compliance (`regulatory_compliance`) ✅ DONE

1. Obligation register by entity / site / activity.  
2. Permit fields + change-of-control.  
3. Litigation register (alleged / provision / insurance / counsel).  
4. Counsel letter as closure.  
5. Quantify effects only when supported.  
6. Cross-check IP; carry critical permits to Recommendations.  
7. Reject invented laws/cases/probabilities.

**Shipped:** `prompt_book/regulatory_compliance.md` deal slots + counsel /
quantify / IP / QA/Questions; `_rc_evidence_qa` / `_questions_from_rc_gaps`;
counsel-letter closure; quantified effects (pack-supported only); critical
permits → Recommendations; IP prior cross-check; READY→LIMITED on open QA /
OPEN counsel letter; render §§6–9; SWOT `_harvest_regulatory_compliance`;
foundations IP prior.

### 26 — IP and Technology (`ip_and_technology`) ✅ DONE

1. Asset map: owned / licensed / ordinary / vendor.  
2. Registration / assignment verify.  
3. Licence transfer / CoC.  
4. Systems / cyber / incident / restore-test checklist.  
5. Moat test: proprietary + economic + hard to replicate.  
6. Replacement cost schedule.  
7. Cross-check Competitive Differentiation.  
8. Omit inapplicable software metrics with reason.

**Shipped:** `prompt_book/ip_and_technology.md` deal slots + moat/cyber/metrics
+ QA/Questions; `_ip_evidence_qa` / `_questions_from_ip_gaps`; cyber checklist;
moat test (3 legs); omitted software metrics; READY→LIMITED on open QA FAILs;
render §§6–9; SWOT harvest enrichment; Competitive Differentiation prior
(already in foundations).

### 27 — ESG and Sustainability (`esg_and_sustainability`) ✅ DONE

1. Materiality screen by sector/jurisdiction.  
2. Product impact vs ops footprint split.  
3. Metric boundary / method / baseline table.  
4. Targets vs measured results.  
5. Workforce / safety where material.  
6. Financial / regulatory consequence column.  
7. Cross-check Regulatory.  
8. Don’t infer emissions from revenue/location count.

**Shipped:** `prompt_book/esg_and_sustainability.md` deal slots + Regulatory
cross-check + QA/Questions; `_esg_evidence_qa` / `_questions_from_esg_gaps`;
READY→LIMITED on open QA FAILs; render §§6–9; SWOT
`_harvest_esg_and_sustainability`; foundations Regulatory prior.

### 28 — Market Risk (`market_risk`) ✅ DONE

1. Risk rows: trigger, population, timing, mechanism, mitigation.  
2. Quantify $ exposure.  
3. Evidence-based likelihood (ranges, not invented probabilities).  
4. Early-warning indicators.  
5. Price vs structure impact.  
6. Non-overlap with Internal Risk.  
7. Reject unnamed threats.

**Shipped:** `prompt_book/market_risk.md` deal slots + row schema + Internal
boundary + QA/Questions; `_mr_evidence_qa` / `_questions_from_mr_gaps`;
unnamed-threat rejection; Internal Risk handoff/cross-check; READY→LIMITED
on open QA FAILs; render §§6–9; deep_dive Internal prior; SWOT harvest
trigger enrichment.

### 29 — Internal Risk (`internal_risk`) ✅ DONE

1. Pull validated registers from ops / mgmt / fin / tech / compliance (+ Cash Flow).  
2. Row schema: root cause, event, exposure, controls, residual, owner, action.  
3. Known weakness vs uncertainty.  
4. Quantify where possible.  
5. Conflict reconcile before rank.  
6. Pre-decision vs post-close.  
7. No “manageable risk” that silently excludes blockers.

**Shipped:** `prompt_book/internal_risk.md` deal slots + register schema +
known-vs-uncertainty + QA/Questions; `_build_risk_register` /
`_reconcile_conflicts` / `_ir_evidence_qa` / `_questions_from_ir_gaps`;
upstream priors (mgmt/CS/CF/ops/RC/tech); READY→LIMITED on open QA FAILs;
render §§6–9; deep_dive priors; SWOT register harvest.

### 30 — Growth Opportunities (`growth_opportunities`) ✅ DONE

1. Initiative inventory fit to model.  
2. Incremental economics with formulas.  
3. Capex / opex / WC / timing.  
4. Addressability + capacity + regulatory deps.  
5. Evidence vs hypothesis.  
6. Rank net value / payback / feasibility.  
7. Anti-overlap Synergies / Strategy.  
8. No arbitrary success probabilities.

**Shipped:** `prompt_book/growth_opportunities.md` deal slots + economics /
requirements + ranking + anti-overlap + QA/Questions; `_go_overlap_cross_check`
/ `_go_evidence_qa` / `_questions_from_go_gaps`; READY→LIMITED on open QA
FAILs; render §§6–9; deep_dive Strategy/Synergies priors; SWOT harvest
enrichment.

### 31 — Synergies (`synergies`) ✅ DONE

1. Require named buyer + baselines or hypothesis-only mode.
2. Lever: gross, overlap, cannibalisation, one-off, tax, timing, net cash.
3. Phase with owner.
4. Reconcile Growth Opportunities / stand-alone forecast.
5. Execution risks.
6. QA: no uplift without buyer.
7. Exclude unverified from Final Valuation Range.

**Shipped:** `prompt_book/synergies.md` deal slots + lever schema + GO
reconcile + execution risks + FVR + QA/Questions; `_enrich_lever_fields` /
`_sy_go_reconcile` / `_build_execution_risks` / `_fvr_exclusion` /
`_sy_evidence_qa` / `_questions_from_sy_gaps`; READY→LIMITED on open QA
FAILs; render §§6–9; deep_dive Growth Opportunities prior; SWOT harvest
enrichment.

### 32 — SWOT (`swot_analysis`) ✅ DONE

1. Expand upstream once Cash Flow exists.  
2. Finding-ID + evidence status mandatory.  
3. Gap ≠ weakness.  
4. Action rows (owner/timing/success measure) for priority combos.  
5. Dedup / conflict QA.  
6. Blockers not overridden by net-positive narrative.

**Shipped:** `prompt_book/swot_analysis.md` deal slots + finding-ID + action
rows + QA/Questions; `_assign_finding_ids` / `_build_priority_action_rows` /
`_swot_evidence_qa` / `_questions_from_swot_gaps`; assertion→proper classes;
READY→LIMITED on open QA FAILs (blockers stay BLOCKED); render §§7–10;
documents catalog prompts.

### 33 — Sensitivity Analysis (`sensitivity_analysis`, nested) ✅ DONE

1. Bind to reconciled valuation model date/basis.  
2. One-at-a-time ranks + 2-driver grid.  
3. Upside / base / downside assumption sets.  
4. Break-evens vs hurdles / covenants / cash.  
5. Evidenced vs judgement labels.  
6. MoM / hold / IRR arithmetic.  
7. Optional promote to Phase-4 catalog key.  
8. QA: no “highly sensitive” without compute.

**Shipped:** `prompt_book/sensitivity_analysis.md` deal slots + basis bind +
sized-sensitivity QA + covenants/cash; `_valuation_basis_binding` /
covenant+cash break-evens / `_sensitivity_evidence_qa` /
`_questions_from_sensitivity_gaps`; READY→LIMITED on open QA FAILs
(direction fail stays BLOCKED); render §§6–8; remains nested under
`valuation_modeling` (Phase-4 promote deferred).

### 34 — Final Valuation Range (nested under valuation_modeling) ✅ DONE

1. Multi-method common date/basis.  
2. Comp selection rationale + LTM vs forward.  
3. EV → equity bridge (needs complete net debt / WC).  
4. Stand-alone vs synergy split.  
5. Offer / walk-away vs hurdles.  
6. Block publish if earnings / net debt / WC unready.  
7. Single consistent verdict; no Go/bid endorsement here.  
8. Catalog visibility decision.

**Shipped:** `prompt_book/final_valuation_range.md` deal slots + LTM/forward +
QA/Questions; `_common_date_basis` / comps rationale / `_walk_away` offer+hurdles /
`_standalone_vs_synergies` (synergies prior / FVR exclusion) /
`_fvr_evidence_qa` / `_questions_from_fvr_gaps`; READY→LIMITED on open QA FAILs
(publish blockers stay BLOCKED); render §§6–8; remains nested under
`valuation_modeling` (Phase-4 promote deferred); documents chips updated.

### 35 — Valuation Modeling (`valuation_modeling` + comps stack) ✅ DONE

1. Treat trading comps / precedents as method inputs.  
2. Nest or promote Sensitivity / FVR consistently.  
3. Block DCF without Cash Flow bridge.  
4. Document mapping framework H1s ↔ Phase-4 keys.  
5. Execution risk / compensation alignment remain code-only Phase-4 (map or keep).

**Shipped:** `prompt_book/valuation_modeling.md` deal slots + CF gate +
method-input language + QA/Questions; `_cash_flow_bridge_ready` /
`_build_dcf` gate / `_valuation_modeling_evidence_qa` /
`_questions_from_vm_gaps`; READY→LIMITED on open QA FAILs; nest Sensitivity
+ FVR with CF/capital priors; render §§6–8; `verdict_roles.deep_dive_deps`
adds `cash_flow`; documents chips updated.

**Framework H1 ↔ Phase-4 mapping (valuation stack):**

| Framework H1 | Phase-4 / code key | Notes |
|---|---|---|
| Valuation Modeling | `valuation_modeling` (FV-05) | Parent; comps/prec/DCF + QA |
| Trading comps | `trading_comps` (FV-03) | Method input into VM |
| Precedent transactions | `precedent_transactions` (FV-04) | Method input into VM |
| Sensitivity Analysis | nested `sensitivity_analysis` | Under VM; Phase-4 promote deferred |
| Final Valuation Range | nested `final_valuation_range` | Under VM; Phase-4 promote deferred |
| Cash Flow (DCF prior) | `cash_flow` (deep-dive) | EBITDA→cash bridge gates DCF |
| Execution Risk | `execution_risk` (FV-01) | Code-only Phase-4 — keep |
| Compensation Alignment | `compensation_alignment` (FV-02) | Code-only Phase-4 — keep |

### 36 — Recommendations (`recommendation`) ✅ DONE

1. Align decision-stage vocabulary with framework (continue diligence / conditional offer / etc.) without inventing invest/pass.  
2. Finding → action classification.  
3. Condition schema: evidence, owner, deadline, acceptance, failure consequence.  
4. Carry blocked workstreams.  
5. Reconcile FVR / Regulatory / Internal Risk / Cash Flow.  
6. Separate price / structure / protection.  
7. Ban post-close mitigation as disguise for pre-decision unknown.

**Shipped:** `prompt_book/recommendation.md` deal slots + decision-stage vocab +
CP schema + blocked/reconcile/post-close ban + QA/Questions;
`_DECISION_STAGES` / `_derive_decision_stage` / `_harvest_cash_flow` /
`_collect_blocked_workstreams` / `_scrub_post_close_disguise` /
`_recommendation_evidence_qa` / `_questions_from_rec_gaps`; READY→LIMITED on
open QA FAILs (open blockers stay BLOCKED); render §§0/7–10; documents chips +
pipeline catalog wording updated (no Go/No-Go).

### 37 — Executive Summary / IC Synthesis (`ic_synthesis`) ✅ DONE

1. Opening from register only (no new facts).  
2. Direction of travel explicit.  
3. 3–5 thesis points with evidence + counter-evidence.  
4. Blockers with owner / effect.  
5. Decision supportable today + prerequisites.  
6. Compact Questions linked to central register.  
7. Forecasts cannot stand in for achieved results.  
8. Align UI naming Executive Summary vs IC Synthesis.

**Shipped:** `prompt_book/ic_synthesis.md` deal slots + thesis 3–5 + decision
support + forecast rule + QA/Questions; `_thesis_points` /
`_counter_evidence_for` / `_decision_support` / `_ic_synthesis_evidence_qa` /
`_questions_from_ic_gaps`; READY→LIMITED on open QA FAILs (open blockers stay
BLOCKED); render §§3–9; documents chips + pipeline catalog / verdict_roles
UI name **Executive Summary** (slug `ic_synthesis`, also known as IC Synthesis).

### 38 — Appendices (`appendices`) ✅ DONE

1. Decide: new analysis agent vs report post-pass.  
2. If agent: slug + `prompt_book/appendices.md`.  
3. Aggregate claim / evidence / calculation registers.  
4. Source inventory versions + interviews + external URLs.  
5. Bidirectional citation check.  
6. Consolidate open requests / contradictions / exclusions.  
7. Distinguish availability vs verification.  
8. Agent-specific QA gates.  
9. Wire into Phase 4 or report assembly.

**Decision:** New Phase-4 aggregator agent (`appendices`, FV-08) depending on
`recommendation`; IC Memo / Strategy report `_compose_appendices` consume its
registers when present (fallback to thin source index).

**Shipped:** `prompt_book/appendices.md`; `agent_document_appendices.py`
(`_aggregate_claim_register` / evidence / calculation / `_bidirectional_citation_check`
/ availability≠verification / QA + Questions); pipeline + verdict_roles FV-08;
render + documents chips; report consumers updated; READY→LIMITED on open QA FAILs.

---

## Definition of done (per agent)

- [ ] Prompt book matches framework required standard + default analysis + agent QA + checklist  
- [ ] Document composer emits required exhibits / tables  
- [ ] Questions and inputs required uses shared schema  
- [ ] Dual Quality / Reliance assigned correctly  
- [ ] Agent-specific QA checks enforced (not prompt-only)  
- [ ] Unit tests for schema + key QA gates  
- [ ] Sample deal run shows expected sections without fabricated claims  

---

## Recommended next execution

Agents **0–38** are done — the framework gap plan for analysis agents is complete.

Optional follow-ups:
1. Shared controls S0–S3 rollout depth across remaining agents still marked partial (24–27 Foundations depth).
2. Promote nested Sensitivity / FVR to first-class Phase-4 keys if product wants separate pipeline chips.
3. Tighten Appendices cite-reopen with true locator page/sheet reopen when VDR text is bound.

Say which follow-up to implement next.
