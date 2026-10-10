# DiligenceIQ FDD Report & Deck — Requirements Matrix

> **Source of truth:** `DiligenceIQ_FDD_Report_and_Deck_Creation_Design.pdf` (Sep 28, 2026, 71 pages)  
> **Scope:** Gap inventory vs `agetic-cdd` + contract for FDD report/deck build.  
> **Companion:** [`fdd-report-implementation.md`](./fdd-report-implementation.md) (phased build plan)  
> **Upstream dependency:** [`databook-design-requirements-matrix.md`](./databook-design-requirements-matrix.md) — FDD numbers come only from an approved databook release.  
> **Last reviewed:** 2026-10-08

---

## Legend

| Status | Meaning |
|--------|---------|
| **Done** | Meets design intent for this row |
| **Partial** | Related capability exists; design contract not met |
| **Gap** | Not present / wrong model vs design |
| **N/A** | Explicitly out of scope (e.g. completed live deal report) |

| Owner | Owns |
|-------|------|
| **Foundations** | Run store, manifest, exhibit store, number tokens, schemas |
| **Databook-bridge** | Consume released databook; draft mode; eight labels |
| **Readiness** | P1 inputs, G0 score, G1 scope profile |
| **Claims** | Agent → claims ledger; financial claim tests |
| **Evidence** | Targeted VDR retrieval → databook re-entry (P3) |
| **Models** | M1–M9 workbooks / modules + checks |
| **QoE** | Adjustment register, G4, bridge / sensitivities |
| **Narrative** | Tagged commentary + number tokens (P6) |
| **Assemble** | One report_spec → report + deck (P7) |
| **QA-Review** | P8–P10, gates G5–G7, change control |
| **Harness** | Golden deals, seeded faults, CI ship gate |
| **API/UI** | Gates, approvals, FDD workspace |

**Current module shorthand**

| Shorthand | Path / surface |
|-----------|----------------|
| `report_*` | `report_builder_base.py`, `report_ic_memo.py`, `report_cdd_deck.py`, … |
| `report_store` | `report_store.py` (`REPORT_TYPES` — no `fdd_*` yet) |
| `consume` | `services_databook_consume.py` |
| `release` | `services_databook_release.py` |
| `databook` | VDR→databook pipeline (P0–P7 landed as substrate) |
| `agents` | `agent_document_*` |
| `ui-reports` | `DealReports.tsx` |

---

## 0. Five non-negotiable rules (PDF §1)

| ID | Rule | Test | Current | Status | Owner | Gap / notes |
|----|------|------|---------|--------|-------|-------------|
| R1 | Numbers only from **approved databook** via versioned models | No exhibit cell without fact ID / databook version | IC Memo / CDD / Ops read release PL lines | **Partial→strong** (Phase 1) | Databook-bridge | Release→fact→exhibit path; agents still emit figures elsewhere |
| R2 | Agents supply **questions / leads / qualitative evidence**, never figures | Claims ledger rejects numeric exhibit sources from agents | Agents write free prose + some figures | **Partial→strong** (Phase 3) | Claims | Ledger + `agent:` fact_id ban on exhibits; consume strip still applies |
| R3 | VDR used for **missing / doubtful / disputed** only; finds re-enter databook | No direct VDR→report number path | Databook has targeted extract; FDD P3 missing | **Partial→strong** (Phase 4) | Evidence | P3 rescan→release→bridge→P2; page-scoped extract later |
| R4 | People approve **judgements** (scope, material adj, conclusions); not arithmetic | Gates G1/G4/G6 logged | Databook HITL exists; no FDD gates | **Partial→strong** (G1+G4+G5+G6) | QA-Review | G7 hash verify landed Phase 8 |
| R5 | **One report specification** drives report + deck; figure change re-runs dependents | Same cell hash in both renders | Separate builders per report type | **Partial→strong** (Phase 7) | Assemble | Assembled `report_spec` → multi-section PDF + PPTX; identical figures |

---

## 1. Seven design decisions (PDF §1)

| ID | Decision | Status | Notes |
|----|----------|--------|-------|
| D1 | Scope & perimeter first (G1) before analysis | **Partial→strong** (Phase 2) | Scope + G1 API; enforce before models in later phases |
| D2 | Databook sole numeric source; doubtful flagged; material + doubtful needs partner limitation | **Partial** | Release statuses exist; no FDD limitation gate |
| D3 | Agent outputs → claims ledger; financial claims tested vs databook | **Done** (Phase 3) | `claims.json` + agrees/contradicted/unverifiable |
| D4 | Targeted VDR retrieval; results → new databook version → P2 | **Partial→strong** (Phase 4) | `run_p3_evidence_pass`; metric-scoped extract later |
| D5 | Models compute; prose uses tokens bound to exhibit cells + basis label | **Partial→strong** (Phase 6) | Tokens + typed-figure ban; QoE exhibit binding |
| D6 | One adjustment register (mgmt / diligence / sensitivity / pro forma separated) | **Done** (Phase 5a) | `qoe.json` register_rows + treatments; sens/PF beside adj. EBITDA |
| D7 | One report_spec; change control + dependency graph | **Partial→strong** (Phase 7) | Assembled report_spec + deps; full change-control graph later |

---

## 2. Source trust contract (PDF §2)

| Source | Trusted for | Never used for | Status |
|--------|-------------|----------------|--------|
| Approved databook | Every schedule / exhibit figure | Opinions | **Partial** — consume exists |
| Agent outputs | Questions, leads, qualitative context | Exhibit figures; facts databook contradicts | **Gap** — not enforced |
| VDR | Missing detail, disagreements, adj evidence | Re-typing proved numbers into report | **Partial** |
| Specialist models (M1–M9) | Derived figures | Own invented inputs | **Gap** |
| Management answers | Explanations / confirmations | Figures unless document-backed | **Gap** |

**Conflict resolution order (must implement):** (1) eight-label definition check → (2) databook status → (3) targeted VDR via databook pipeline → (4) lead decision / limitation. Never average; never take agent-only number; never edit figure in report.

---

## 3. Inputs & readiness (PDF §3 / P1 / G0–G1)

| ID | Requirement | Status | Owner | Gap / notes |
|----|-------------|--------|-------|-------------|
| IN-1 | Seven inputs: databook, agents, VDR, models, management answers, engagement brief, house template | **Partial→strong** (Phase 2) | Readiness | Scanner + G0; models/mgmt optional until later phases |
| IN-2 | Databook minimum: eight labels + status + source page + tie-outs | **Partial→strong** (Phase 1) | Databook-bridge | Fact table maps labels+status; page crops still thin |
| IN-3 | Below databook standard → **draft mode**; G6 unavailable | **Done** (Phase 1) | Databook-bridge | `draft_mode` + `g6_blocked`; gate check API |
| IN-4 | Scope profile: entities in/out, deal type, periods, currency, materiality M, sections in scope | **Done** (Phase 2 + UX) | Readiness | `scope.json` + G1 API + Deal FDD scope editor |
| IN-5 | Materiality default 5% adj. EBITDA (band 0.5–1% revenue); trivial &lt; 5% of M | **Done** (Phase 5a) | Readiness/QoE | Scope defaults + B4 `compute_materiality_m`; trivial band on register rows |
| IN-6 | Figure types: reported / calculated / estimated / judgement | **Gap** | Models | |
| IN-7 | Evidence tiers A (ledgers) / B (mgmt) / C (audited only) | **Gap** | Models | |
| IN-8 | Agent modules mapped (Historical Perf, Revenue Quality, …); valuation/synergies **out of FDD figures** | **Partial** | Claims | Modules exist; mapping contract not enforced |

---

## 4. FDD sections A–K (PDF §3 / §6)

| ID | Section | Primary model | Status | Notes |
|----|---------|---------------|--------|-------|
| SEC-A | Scope, perimeter, basis | Profile | **Partial→strong** (Phase 6) | Tagged draft + limitations |
| SEC-B | Historical trading | M1 | **Partial→strong** (Phase 5b M1) | `ex_m1_trading` multi-year + YoY/margins |
| SEC-C | Revenue and margin | M2 | **Partial→strong** (Phase 5b M2) | `ex_m2_margin` GM/EM + Δpp walk |
| SEC-D | Costs and people | M3 | **Partial→strong** (Phase 5b M3) | `ex_m3_costs` COGS/SG&A/labour + ratios |
| SEC-E | Quality of earnings | M4 | **Partial→strong** (Phase 6) | QoE tokens via `ex_qoe_bridge` |
| SEC-F | Balance sheet / NAV | M8 | **Partial→strong** (Phase 5b) | `ex_m8_bs` when BS facts present |
| SEC-G | Net working capital | M5 | **Partial→strong** (Phase 5b) | `ex_m5_nwc` when WC facts present |
| SEC-H | Net debt / debt-like | M6 | **Partial→strong** (Phase 5b) | `ex_m6_net_debt`; needs cash+debt in release |
| SEC-I | Cash flow / capex | M7 | **Partial→strong** (Phase 5b M7) | `ex_m7_cash` OCF/capex/FCF/conversion |
| SEC-J | Forecast review (optional) | M9 | **Partial** (Phase 6) | Opt-in via scope |
| SEC-K | Key findings / completion | Findings register | **Gap→partial** (Phase 6) | Open-item Q tags |
| SEC-ES | Executive summary | All models | **Partial→strong** (Phase 6) | No new facts; token headlines |

Report blueprint also expects: business overview (CDD-labelled), presentation standards (units, rounding, signs, sources on every exhibit).

---

## 5. Models M1–M9 (PDF §4–5 / Appendix B)

**Shared model standards:** inputs by fact ID; Inputs / Calculations / Checks / Outputs sheets; unrounded until display; sign convention; status inheritance; version stamp; blocking checks gate outputs.

| ID | Model | Depends on | Status |
|----|-------|------------|--------|
| M1 | Historical trading | Databook IS/CF | **Partial→strong** (Phase 5b) — `ex_m1_trading`; CF depth later |
| M2 | Revenue and margin | M1 | **Partial→strong** (Phase 5b) — `ex_m2_margin`; mix depth later |
| M3 | Costs and people | M1 | **Partial→strong** (Phase 5b) — `ex_m3_costs`; people depth later |
| M4 | Quality of earnings (QoE) | M1 | **Partial→strong** (Phase 5a) — register/bridge/walk/G4 + §5 example; monthly/LTM tabs later |
| M5 | Net working capital | M8 | **Partial** (Phase 5b) | Exhibit `ex_m5_nwc` from AR/Inv/AP facts |
| M6 | Net debt / debt-like | M8 | **Partial** (Phase 5b) | Exhibit `ex_m6_net_debt`; leases beside |
| M7 | Cash conversion / capex | M4 | **Partial→strong** (Phase 5b) — `ex_m7_cash`; maint vs growth split later |
| M8 | Balance sheet / NAV | Databook BS | **Partial** (Phase 5b) | Exhibit `ex_m8_bs` from BS lines |
| M9 | Forecast review | M1–M7 | **Gap** / optional |

**QoE (M4) must-haves:** Inputs → Baseline → Candidates → Evidence → Register → Consumption → Bridge → Walks → Sensitivities → Pro forma → Monthly/LTM; no double-counting via consumption ledger; sensitivities/pro forma never fold into adjusted EBITDA without treatment rules; G4 lead (+ partner for conclusion).

---

## 6. Workflow stages P0–P10 & gates (PDF §2, §7–8)

| Stage | Prompt | Writes | Gate | Status |
|-------|--------|--------|------|--------|
| Orchestration | P0 | Run manifest, stage calls, retries | — | **Partial** (Phase 0) |
| Inventory / readiness | P1 | Source register, readiness, draft scope, requests | **G0** auto → **G1** lead | **Gap** |
| Databook + agent mapping | P2 | Section input map, claims ledger | **G2** auto | **Partial→strong** (Phase 3 + UX) | Claims ledger + reliability + G2 gate UI / acknowledge |
| Evidence / VDR | P3 | Retrieval → databook pipeline; open items | auto (facts return via P2) | **Partial→strong** (Phase 4) |
| Models | P4 | Model outputs, checks, exhibits | **G3** auto | **Partial→strong** (G3 packs) |
| QoE | P5 | Register, bridge, sensitivities, approval requests | **G4** lead/partner | **Partial→strong** (Phase 5a) |
| Sections / commentary | P6 | Tagged drafts + number tokens | auto narrative checks | **Partial→strong** (Phase 6) |
| Assembly | P7 | Report + deck from one spec | — | **Partial→strong** (Phase 7 + UX) | Multi-section DOCX+PDF / PPTX; labelled chart axes |
| QA | P8 | Issue log (S1–S4) | **G5** | **Partial→strong** (Phase 8) |
| Reviewer challenge | P9 | Challenge list, corrections | **G6** partner | **Partial→strong** (Phase 8) |
| Final generation | P10 | Final artefacts + evidence pack | **G7** hash match | **Partial→strong** (Phase 9) | Evidence pack export + ship gate; G7 still via Phase 8 API |

**Artefact rules:** draft / checked / approved / superseded; stages only read checked|approved; two retries then escalate; temp=0; JSON schema validation; approvals are versioned artefacts.

**Severity:** S1 blocker · S2 judgement · S3 disclose · S4 cosmetic.

---

## 7. Report / deck assembly & commentary (PDF §6–7)

| ID | Requirement | Status |
|----|-------------|--------|
| AS-1 | Sentence tags: F (fact), A (analysis), M (management), Q (open) | **Done** (Phase 6) | Tags on section drafts |
| AS-2 | Number tokens resolve to one exhibit cell; no typed figures in prose | **Done** (Phase 6) | Resolve + typed-figure ban enforced on drafts |
| AS-3 | Fixed confidence vocabulary tied to evidence tier | **Partial→strong** (Phase 6) | Allowed list + invest/superlative bans |
| AS-4 | No invest / not-invest advice | **Partial→strong** (Phase 6) | Invest/superlative bans in commentary checks |
| AS-5 | One report_spec → Word/PDF report **and** IC deck with identical figures | **Partial→strong** (Phase 7 + UX) | Assembled multi-section DOCX + PDF twin + PPTX |
| AS-6 | Presentation: one scale/exhibit; unrounded compute; periods FY24A…; negatives in brackets | **Partial→strong** (Phase 7 + UX) | HALF_UP displays; negatives in brackets; standards node |
| AS-7 | Deck quality: one message/slide, ≤6 bullets, labelled axes (S4/S2) | **Partial→strong** (Phase 7 + UX) | ≤6 bullets; multi-year exhibits get Period / scale chart axes |

---

## 8. Codebase gap snapshot (2026-10-06)

| Area | What exists today | Distance to PDF |
|------|-------------------|-----------------|
| Databook release consume | `prefer_released_pl_lines`, doubtful flags in IC/CDD/Ops | Substrate for R1; Phase 1 binds release → exhibit facts |
| FDD foundations | `fdd_schemas`, run/exhibit store, tokens, deps, stub dual render | Phase 0 landed |
| FDD readiness/scope | `services_fdd_readiness`, `services_fdd_scope`, G0/G1 APIs | Phase 2 landed |
| FDD claims ledger | `services_fdd_claims`, `claims.json`, agent figure ban | Phase 3 landed |
| FDD QoE (M4) | `services_fdd_qoe`, `qoe.json`, G4 approve, §5 worked example | Phase 5a landed |
| FDD commentary | `services_fdd_commentary`, `commentary.json`, F/A/M/Q + typed-figure ban | Phase 6 landed |
| FDD assembly | `services_fdd_assemble`, multi-section `report_spec`, dual render | Phase 7 landed |
| FDD QA / G5–G7 | `services_fdd_qa`, `qa.json`, snapshot freeze, gate approvals | Phase 8 landed |
| FDD goldens / ship gate | `services_fdd_harness`, `fdd_ship_gate`, fixtures/fdd | Phase 9 landed |
| FDD databook bridge | `services_fdd_bridge` fact table + draft mode + pin guard | Phase 1 landed |
| Report platform | `REPORT_TYPES` includes `fdd_report` / `fdd_deck` | Phase 7 multi-section PDF/PPTX from assembled spec |
| Storyline / SSE generate | `routers_reports.py`, `report_builder_base` | Reuse orchestration shell; not FDD gates |
| Agents | Rich agent docs | Must stop being numeric SoT for FDD |
| Approvals | Databook HITL pack | Different product surface (G1/G4/G6) |
| Models / QoE register | — | Greenfield |
| Golden FDD deals | `tests/fixtures/fdd/goldens/` + `fdd_ship_gate` CI | Phase 9 landed (deal_alpha / deal_beta + 12 traps); expand to 3–5 |

**Approx coverage:** Done ~0 · Partial ~12 · Gap ~50+ (indicative).

---

## 9. External dependency

Until databooks meet the VDR→databook contract (eight labels, proven/doubtful/missing, L2+ finals), **every FDD run is draft mode** and **G6 is unavailable**. Continue databook hardening in parallel; do not block Phase 0 plumbing on perfect goldens.

---

## 10. Out of scope (PDF)

- A completed FDD report for a live transaction (design deliverable is the process).
- Tax DD as a workstream (tax appears as pointers only).
- Valuation / synergies figures inside FDD exhibits.
- Averaging conflicts or editing numbers in the rendered report.
