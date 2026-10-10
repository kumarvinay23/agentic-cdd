# DiligenceIQ VDR→Databook — Requirements Matrix

> **Source of truth:** `DiligenceIQ_VDR_to_Databook_Design.pdf` (Sep 28, 2026, 35 pages)  
> **Scope:** Analysis only — gap inventory vs `agetic-cdd`. No implementation commitment.  
> **Related:** [`databook-design-implementation.md`](./databook-design-implementation.md) (earlier MVP plan; Phases 0–3 shipped; not this PDF’s full contract)  
> **Last reviewed:** 2026-10-03  
> **P0 progress:** Versioned release + hard consume shipped (see §13 P0 / IDs AR-6, C-1…C-5).  
> **P1 progress:** File register + set-aside + source ladder + forecast isolation shipped (see §13 P1 / S2-*).  
> **P3 progress:** Eight labels + header parser + notes store + ×1000 scale-step guard shipped (see §13 P3 / S3-*).  
> **P4 progress:** CoA tree + section gate + dual-agree map + generic/saas packs shipped (see §13 P4 / S4-*).  
> **P5 progress:** Proof levels L0–L4 + prove checks + L2+ release gate shipped (see §13 P5 / S5-*, AR-*, AC-8).

---

## Legend

| Status | Meaning |
|--------|---------|
| **Done** | Meets design intent for this row |
| **Partial** | Related capability exists; design contract not met |
| **Gap** | Not present / wrong model vs design |
| **N/A** | Explicitly out of scope for current MVP plan (called out) |

| Owner (workstream) | Owns |
|--------------------|------|
| **Ingest** | VDR unpack, CDL, page/file landing |
| **Read** | Dual extractors, OCR/vision, page register, images |
| **Classify** | Deal profile, file/page register, source ladder, expected docs |
| **Label** | Eight labels, header parser, notes store, magnitude guard |
| **Map** | CoA tree, sector packs, mapping memory, dual-agree map |
| **Prove** | ~20 checks, L0–L4, auto-release proven/doubtful/missing |
| **HITL-Learn** | Validation pack, cards, learning loop, versioning |
| **Consume** | Agents/reports read released databook only (R7) |
| **Harness** | Goldens, traps, repeatability, CI ship gate |
| **API/UI** | Surfaces for databook, DQ, validation |

**Current module shorthand**

| Shorthand | Path / surface |
|-----------|----------------|
| `extract` | `services_databook_extract.py` |
| `header` | `services_databook_header.py` |
| `map` | `services_databook_map.py` |
| `coa` | `services_databook_coa.py` |
| `prove` | `services_databook_prove.py` |
| `blocks` | `services_databook_blocks.py` |
| `resolve` | `services_databook_resolve.py` |
| `decisions` | `services_databook_decisions.py` |
| `store` | `services_databook_store.py` |
| `models` | `services_databook_models.py` |
| `consume` | `services_databook_consume.py` |
| `excel` | `services_databook_excel.py` |
| `orchestrator` | `services_databook.py` |
| `router` | `routers_dealroom.py` (`/cdd/databook*`, `/cdd/data-quality`) |
| `ui-db` | `apps/web/.../DealDatabook.tsx` |
| `ui-dq` | `apps/web/.../DataQualityReview.tsx` |
| `cdl` | library extract / CDL JSON under deal storage |
| `reports` | `report_cdd_deck.py`, `report_ops_dashboard.py` (+ other report_* ) |
| `agents` | `agent_document_*` |

---

## 0. Accuracy contract (PDF §2)

| ID | PDF requirement | Test / target | Current module | Status | Owner | Gap / notes |
|----|-----------------|---------------|----------------|--------|-------|-------------|
| AC-1 | Cell correct = value + **eight labels** match source | 100% of finals vs golden | `ExtractedRow` eight labels + `source_ref` | **Partial** | Label | Labels on extract/release; page crop / golden match still open |
| AC-2 | Every cell ends **proven / doubtful / missing** without a person | Status on every expected cell | Release proven/doubtful/missing + L2 gate | **Partial** | Prove | Missing+request list still thin |
| AC-3 | **Complete**: every expected figure final, doubtful, or missing+request | Golden coverage 100% | Harness + `fill_missing_coverage_cells` + release `request_list` | **Done** (G2+G6) | Classify + Coverage + Release | Full-size A/B goldens; coverage matrix CI-blocking |
| AC-4 | **Clean**: no set-aside / forecast / wrong-scope in history | Contamination scan = 0 | Classify gate + golden `forbid_sources` (H-5) | **Partial** | Classify + Harness | Gate + ship scan; not full ledger UX |
| AC-5 | **Traceable**: click cell → page image + table/row/col + rule | 100% | Pack crops + `SourceRef` page/bbox/crop_ref (G4) | **Partial** | Read + Label | Text PDF crops for text PDFs; scans stay unavailable |
| AC-6 | **Repeatable**: identical inputs → identical databook | Run twice, compare | Harness bit-identical fingerprint (H-6) | **Done** | Harness | Fingerprint compare on goldens |
| AC-7 | **Honest**: unproven never shown as final | Downstream flags | Hard consume + Market/Strategy/IC †; hist perf merge | **Partial→strong** (G1) | Consume | Remaining agent modules beyond hist perf |
| AC-8 | Proof levels **L0–L4**; final only **L2+** | Level on every cell | `ProofLevel` on row/promoted/release; gate in promote+release | **Done** | Prove | |
| AC-9 | Residual risk controls: dual scan methods, calibration sample, trap growth | Process | Dual read (P2) + calibration (P6) + 32 traps (P7) | **Partial** | Read + HITL-Learn + Harness | Vision OCR still open |

---

## 1. Stage 1 — Read every page (PDF §3 / lessons 3–4)

| ID | PDF requirement | Root cause | Current module | Status | Owner | Gap / notes |
|----|-----------------|------------|----------------|--------|-------|-------------|
| S1-1 | **Page register**: every page text / scan / mixed / image / blank | R2 | `services_databook_pages` + extract `pages[]` | **Done** | Read | Heuristic kinds; OCR not required |
| S1-2 | Statement pages read by **two independent methods** | R2 | Method A `rows_from_table` + Method B dual reshape | **Done** | Read | Same grid, independent header/tokenizer |
| S1-3 | Dual methods must agree **to the unit** or mark doubtful | R2, R5 | `read_dual_agree` → assumption / L1 | **Done** | Read + Prove | Disagreement stamps assumption |
| S1-4 | Embedded **images inside PDFs** (e.g. EBITDA bridges) extracted | R2 | Page `has_images` + unread IMAGE/MIXED | **Partial** | Read | Surfaced unread; no vision→table yet |
| S1-5 | Scanned PDFs / leases / screenshots readable | R2 | SCAN/IMAGE unread + Findings flag | **Partial** | Read | Honest unread; OCR still not_available |
| S1-6 | Spreadsheets: **all tabs**, formula+value, hidden rows, each tab as own doc | R1/R2 | XLSX up to 40 sheets; each sheet a table + page | **Partial** | Ingest + Read | Tabs as tables; formula/hidden still open |
| S1-7 | Archives unpacked; **content fingerprint** / dedupe | R1 | VDR unzip / ingest exists | **Partial** | Ingest | Fingerprint + set-aside duplicate role incomplete |
| S1-8 | Token / bbox positions for click-to-page | Traceability | `SourceRef.page` + bbox + rendered crops (G4) | **Partial** | Read | Heuristic bbox; real PDF crops when source file present |
| S1-9 | Sentence numbers go to **notes store**, never statement lines | R2, lesson 10 | `notes.json` via `notes_from_prose` | **Done** | Label | Prose no longer creates statement rows |

---

## 2. Stage 2 — Classify files & pages (PDF §4 / lessons 1–2, 7)

| ID | PDF requirement | Root cause | Current module | Status | Owner | Gap / notes |
|----|-----------------|------------|----------------|--------|-------|-------------|
| S2-1 | Inferred **deal profile** (legal names, sites, FYE, scopes) | R1 | Deal name/company tokens for wrong-deal lite | **Partial** | Classify | No SPA/audit-driven full profile |
| S2-2 | **File register**: relevance, type, scope, date, basis, version, actual/forecast, role | R1 | `file_register.json` + classify heuristics | **Partial** | Classify | Lite fields; date/version/scope still thin |
| S2-3 | Wrong-deal / personal / other-property → **set aside** (zero history facts) | R1, AC-4 | Set-aside gate in extract + Findings | **Partial** | Classify | Heuristic; not full contamination scan |
| S2-4 | **Source ladder** (signed audit ≫ draft ≫ management ≫ adviser ≫ deal papers) | R4 | `ladder_score` on rows; first key in conflict rank | **Done** | Classify + Prove | Draft-to-final bridge still open |
| S2-5 | Version / basis competition resolved by ladder + bridge | R4, lesson 7–8 | Ladder in conflicts | **Partial** | Classify + Prove | No draft-to-final bridge |
| S2-6 | **Expected-document list** from index / deal type → request list | R1, lesson 2 | `expected_doc_templates` + `assess_expected_docs` + `expected_docs.json` | **Done** (G2) | Classify | Generic + SaaS templates; extend packs as needed |
| S2-7 | **Page classes**: IS / BS / CF / equity / note / EBITDA bridge / other | R2 | `PageClass` + register + extract routing (G3) | **Partial** | Classify | PDF page-text OCR still weak |
| S2-8 | Forecast / “Year 1–5” never land in history FY columns | R2, AC-4 | Header isolation + forecast-only file role | **Done** | Classify + Label | |
| S2-9 | Findings trust ledger per file | Product UX | Findings + classify + page_class counts/flags (G3) | **Partial** | API/UI | |

---

## 3. Stage 3 — Extract tables + eight labels (PDF §5 / lessons 4–5, 10)

| ID | PDF requirement | Root cause | Current module | Status | Owner | Gap / notes |
|----|-----------------|------------|----------------|--------|-------|-------------|
| S3-1 | Extract **whole tables as grids** (indent, subtotal flags) | R2 | `extract` + `StatementBlock` line lists | **Partial** | Read + Label | Not full grid/indent model |
| S3-2 | Label: **Scope** | AC-1 | `ExtractedRow.scope` from header | **Done** | Label | Heuristic (company/consolidated/standalone) |
| S3-3 | Label: **Statement** | AC-1 | `ExtractedRow.statement` | **Done** | Label | From table name / header band |
| S3-4 | Label: **Line** | AC-1 | `caption` | **Done** | Label | Mapping still weak |
| S3-5 | Label: **Period end** (date) | R2 | `period_end` + FY convention | **Done** | Label | Calendar / ending_march |
| S3-6 | Label: **Period length** | R2 | `period_length` (FY/H1/Q…) | **Done** | Label | |
| S3-7 | Label: **Basis** (audit / management / QoE / …) | R4 | `source_basis` from file register | **Done** | Label | Stamped at extract (P1) |
| S3-8 | Label: **Unit** (currency, scale, per-unit) | R5 | header → map → caption + sources | **Partial** | Label | Caption fallback marked assumption |
| S3-9 | Label: **Source** (doc, page, table, row, col, rule) | Trace | `SourceRef` on row/release | **Partial** | Label | page still optional (no bbox) |
| S3-10 | **Two grid extractors** agree cell-for-cell | R2 | Method A+B dual (`services_databook_dual`) | **Done** | Read | Disagreement → `read_dual_agree=false` |
| S3-11 | Scale from **table header only**, never sentence “million” | R5, lesson 5 | `services_databook_header` | **Done** | Label | Sentence scale → notes only |
| S3-12 | **Magnitude guard** (×1000 / ÷1000) before release | R5 | `apply_scale_step_guard` | **Done** | Prove | Holds ~×1000 vs leave-one-out centre |
| S3-13 | Equity years / period orientation preserved | R2, lesson 4 | Period parse heuristics | **Partial** | Label | No golden proof of orientation |

---

## 4. Stage 4 — Chart-of-accounts tree mapping (PDF §6 / lessons 6, 11)

| ID | PDF requirement | Root cause | Current module | Status | Owner | Gap / notes |
|----|-----------------|------------|----------------|--------|-------|-------------|
| S4-1 | CoA as **tree** (id, section, parent, sign, definition, captions, checks) | R3 | `CoANode` tree in `coa` | **Done** | Map | Lite tree; checks ids stubbed |
| S4-2 | **Section gate** before caption match | R3 | statement → allowed sections | **Done** | Map | IS/BS/CF/KPI |
| S4-3 | Dual independent map methods must agree | R3 | pattern (A) + alias (B) | **Done** | Map | Soft single-method → assumption; hard disagree → unmapped |
| S4-4 | **Mapping memory** per company / auditor layout | R3 | None | **Gap** | Map + HITL-Learn | |
| S4-5 | Catch-all “other” **look-through** to notes | R3 | None | **Gap** | Map | |
| S4-6 | Derived metrics (EBITDA, net debt) separate from printed facts | R3 | `derived` flag; no auto-promote | **Done** | Map | |
| S4-7 | **Sector packs** (healthcare, fuel-retail, …) | R3 | `generic` + `saas` packs | **Partial** | Map | Healthcare / fuel-retail still open |
| S4-8 | Definitions disambiguate same words (net vs gross, restricted cash, …) | Lesson 11 | node.definition + section gate | **Partial** | Map | Cash gated to BS; more defs TBD |
| S4-9 | Unmapped lines held out / surfaced | R3 | `unmapped` DQ issues | **Done** | Map + Prove | |

---

## 5. Stage 5 — Prove (~20 checks) (PDF §7 / lessons 8–9, 12)

| ID | PDF check family | Root cause | Current module | Status | Owner | Gap / notes |
|----|------------------|------------|----------------|--------|-------|-------------|
| S5-01 | Statement **subtotals** re-add | R6 | `blocks` + `prove_check` subtotal_tie | **Done** | Prove | |
| S5-02 | **Balance sheet** balances | R6 | `check_balance_sheet` | **Done** | Prove | Requires total_assets/liabilities/equity lines |
| S5-03 | **Equity roll-forward** | R6 | `check_equity_roll_forward` (G5) | **Partial** | Prove | Requires equity + NI (± dividends) |
| S5-04 | **Cash / CF roll** | R6 | `check_cash_roll` (G5) | **Partial** | Prove | Requires cash ×2 FY + net_change |
| S5-05 | Profit / NI **cross-statement** (IS ↔ CF ↔ equity) | R6 | `check_ni_cross_statement` (G5) | **Partial** | Prove | |
| S5-06 | **Notes** agree with statements | R6 | `check_notes_vs_statements` (G5) | **Partial** | Prove | Lite — mapped notes only |
| S5-07 | **Draft-to-final** line-by-line bridge | R4/R6 | `check_draft_to_final` (G5) | **Partial** | Prove | Holds draft on mismatch |
| S5-08 | **Cross-document** same basis agree | R4/R6 | L3 when multi-source agree | **Partial** | Prove | Ladder still proposal-first |
| S5-09 | Forecast / scope **isolation** checks | AC-4 | `check_forecast_isolation` | **Done** | Prove | |
| S5-10 | **Sign / section sense** (asset vs liability) | R3/R6 | `check_sign_sense` (cash) | **Partial** | Prove | Lite heuristics |
| S5-11 | Reference / bridge totals (EBITDA bridges) | R2/R6 | — | **Gap** | Prove | Needs image read |
| S5-12 | Series sanity / magnitude | R5 | series drop + scale-step | **Done** | Prove | |
| S5-13 | Failure class: **engine vs source vs definition vs missing** | R6 | `FailureClass` on prove_check (G5 rolls/notes/draft) | **Partial** | Prove | Applied across G5 checks |
| S5-14 | Checks **act** (block release), not advise-only | Lesson 12 | L2+ promote/release gate + G5 holds | **Done** | Prove | |
| S5-15 | Full ~20-check library as design appendix | R6 | Core + G5 rolls/notes/draft | **Partial** | Prove | Bridges/images still open |

---

## 6. Automatic release (PDF §8)

| ID | PDF requirement | Current module | Status | Owner | Gap / notes |
|----|-----------------|----------------|--------|-------|-------------|
| AR-1 | Run ends with every cell **proven / doubtful / missing** | Promote / hold_out / drop; release maps to proven/doubtful/missing | **Partial** | Prove | L2+ gate; expected-cell completeness still open |
| AR-2 | **No person waits inside the run** | Analyst reviews in Databook UI mid-workflow | **Partial** | HITL-Learn | Auto path no longer needs mid-run HITL for L2+ |
| AR-3 | Auto-promote only when dual-agree + arithmetic (L2+) | `min_proof_level` + dual_agree + holds | **Done** | Prove | |
| AR-4 | Unprovable → **doubtful** with best candidate + alternatives | Release cells from held_out + conflict candidates | **Done** | Prove + API/UI | |
| AR-5 | No evidence → **missing** + document request | Coverage synth + `DatabookRelease.request_list` + Findings | **Done** (G2) | Coverage + Release | Missing cells always link an open request |
| AR-6 | Versioned **released databook** artifact | `databook/releases/vN.json` + meta pointer | **Done** | store + Prove | Immutable; auto on rescan/decision/import + manual POST |

---

## 7. Outside the run — validation pack & learning (PDF §9)

| ID | PDF requirement | Current module | Status | Owner | Gap / notes |
|----|-----------------|----------------|--------|-------|-------------|
| OL-1 | Person only **after** run, on doubtful pack | `pack` + Validation Pack UI tab | **Done** | HITL-Learn | Ready only when current release exists |
| OL-2 | Validation **cards**: crops, alternatives, 8 labels, dependents | `services_databook_pack` + crop UI (G4) | **Partial** | API/UI | Crops on conflict/doubtful/calibration; scans unavailable |
| OL-3 | Actions: confirm / pick alternative / correct / remap / exclude | confirm/remap/exclude aliases + Accept | **Done** | decisions | Same authority as vouch/correct/drop |
| OL-4 | **Calibration sample** of proven cells in pack | `select_calibration_sample` | **Done** | HITL-Learn | Deterministic metric-diverse sample |
| OL-5 | Decision → **new databook version** | Auto-release + `decision_lineage.jsonl` | **Partial** | store | Lineage recorded; full versioned UI later |
| OL-6 | Decision → **trap test** | `traps.jsonl` seeded + P7 suite runs in CI | **Done** | Harness | HITL seeds + curated 32-trap fixture |
| OL-7 | Decision → **mapping memory** / threshold tuning | `mapping_memory.json` + `map_caption(deal=)` | **Done** | Map + HITL-Learn | Threshold tuning still open |
| OL-8 | Excel import/export for offline review | `excel` + router import/export | **Partial** | API/UI | Useful; not validation-pack cards |

---

## 8. Agents / workers (PDF §10)

| ID | PDF worker | Role | Current analogue | Status | Owner |
|----|------------|------|------------------|--------|-------|
| W-01 | Intake | Unpack, fingerprint, register files | VDR ingest + CDL | **Partial** | Ingest |
| W-02 | Page reader | Dual page methods + images | CDL text/tables | **Gap** | Read |
| W-03 | Classifier | File/page roles, ladder, expected docs | CDL categories | **Gap** | Classify |
| W-04 | Grid extractor A | Independent table grid | `extract` | **Partial** | Read |
| W-05 | Grid extractor B | Second independent method | — | **Gap** | Read |
| W-06 | Header parser | Scale/period/basis from headers | Heuristics in extract/map | **Gap** | Label |
| W-07 | Mapper | CoA tree dual-agree | `map` keywords | **Gap** | Map |
| W-08 | Resolver | Source ladder + conflicts | `resolve` | **Partial** | Prove |
| W-09 | Prover | ~20 checks, L0–L4 | `blocks` + thin resolve | **Gap** | Prove |
| W-10 | Doubt resolver | Pack + alternatives | `decisions` + UI | **Partial** | HITL-Learn |
| W-11 | Release | Versioned proven/doubtful/missing | `promoted.json` | **Partial** | Prove |
| W-12 | Card writer | Validation cards | `services_databook_pack` + Validation Pack UI | **Partial** | API/UI | Cards ship; heuristic bbox; real crops open |
| W-13 | Learning updater | Traps, memory, thresholds | `learn` + P7 trap suite | **Partial** | HITL-Learn + Harness | Memory+traps; threshold tuning open |
| W-14 | LLM contracts | temp=0, cache-by-fingerprint, unknown+quote | Ad hoc LLM elsewhere; map LLM off | **Gap** | Map + Read |

---

## 9. Test harness & release rule (PDF §11–12)

| ID | PDF requirement | Current module | Status | Owner | Gap / notes |
|----|-----------------|----------------|--------|-------|-------------|
| H-1 | Golden databooks (e.g. Deal A ~195 / Deal B ~252 figures) | `fixtures/databook/goldens/deal_{a,b}.json` | **Done** (G6) | Harness | Deal A 256 / Deal B 326; `expected_min_figures` + ship gate |
| H-2 | **32 trap tests** (grow from 24) | `fixtures/databook/traps.jsonl` (32) | **Done** | Harness | Curated map/conflict/scale/classify traps |
| H-3 | Ship only at **100%** finals on goldens | `run_ship_gate` expected_cells status+value | **Done** | Harness | Proven/doubtful/missing must match golden |
| H-4 | 100% doubt/missing coverage on expected cells | `coverage_keys` synth + assert | **Done** | Harness | Every coverage key×year has a status |
| H-5 | Zero contamination (set-aside / forecast) | Classify gate + `forbid_sources` | **Done** | Harness | Forecast/set-aside docs contribute 0 history rows |
| H-6 | Bit-identical re-run | Cell fingerprint compare | **Done** | Harness | Two pipeline runs → same SHA-256 |
| H-7 | CI gate blocks engine release on failure | `.github/workflows/databook-ship.yml` + CLI | **Done** | Harness | `python -m agetic_cdd_api.databook_ship_gate` |

---

## 10. Downstream consume — R7 (PDF architecture / lesson 13)

| ID | PDF requirement | Current module | Status | Owner | Gap / notes |
|----|-----------------|----------------|--------|-------|-------------|
| C-1 | CDD Deck reads **released** databook for financial history | `prefer_released_pl_lines` in `report_cdd_deck` | **Done** | Consume | Hard consume; † on doubtful |
| C-2 | Ops Dashboard prefers released metrics; suppresses agent WARN when databook present | `report_ops_dashboard` harvest + series sheet | **Done** | Consume | Status column + † note |
| C-3 | IC Memo / Market / Strategy / QoE-style outputs databook-backed | IC Memo + Market trajectory/appendix + Strategy appendix via `released_pl_display_rows` | **Done** | Consume | G1 2026-10-05 |
| C-4 | Downstream shows **doubtful** flags, never silent final | pl_lines `databook_status` / `doubtful_years` / † | **Done** | Consume + API/UI | † footnote on Market/Strategy/IC |
| C-5 | Report refresh when validated version ships | `mark_reports_stale_for_databook_release` on create_release; regenerate clears | **Partial** | Consume | Stale flag + catalog; no auto rebuild job |
| C-6 | Agents never invent scale/period/jurisdiction past databook | `historical_performance` merges release via `merge_promoted_into_historical_spec` | **Partial** | Consume | Hist perf G1; other agents still open |

---

## 11. Root-cause rollup (R1–R7)

| Root cause | PDF stages | Primary IDs | Status today | Primary owner |
|------------|------------|-------------|--------------|---------------|
| **R1** No sorting first | Stage 2 | S2-1…S2-9 | **Partial** (P1) | Classify |
| **R2** Tables flattened / unread pages | Stages 1, 3 | S1-*, S3-1, S3-10, S3-13 | **Partial→strong** (P2) | Read + Label |
| **R3** Keyword mapping | Stage 4 | S4-* | **Partial→strong** (P4) | Map |
| **R4** No source ladder | Stages 2, 5 | S2-4, S2-5, S5-07, S5-08 | **Partial** (P1 ladder) | Classify + Prove |
| **R5** Units read wrongly | Stage 3 | S3-8, S3-11, S3-12 | **Partial→strong** (P3) | Label |
| **R6** No proof, no gate | Stage 5 + AR | S5-*, AR-* | **Partial→strong** (P5) | Prove |
| **R7** Report not wired | Consume | C-* | **Strong** (G1) | Consume |

---

## 12. Lessons → requirement IDs

| Lesson # | Lesson (short) | Requirement IDs |
|----------|----------------|-----------------|
| 1 | Decide what a file is before reading numbers | S2-1, S2-2, S2-3 |
| 2 | Data room bigger than the folder | S2-6, AR-5 |
| 3 | Numbers hide in pictures | S1-4, S1-5, S5-11 |
| 4 | Flattened tables lose meaning | S1-2, S3-1, S3-5, S3-6, S3-13 |
| 5 | Scale belongs to the table | S3-11, S3-12 |
| 6 | Keywords cannot map a BS | S4-1…S4-9 |
| 7 | Versions and bases compete | S2-4, S2-5 |
| 8 | Draft-to-final tells a story | S5-07 |
| 9 | Source errors only arithmetic finds | S5-02…S5-06 |
| 10 | Sentences are not data | S1-9 |
| 11 | Same words, different meanings | S4-8 |
| 12 | Checks must act | S5-14, AR-1…AR-3 |
| 13 | Downstream must read released databook | C-1…C-5 |

---

## 13. Suggested build phases (PDF §12 alignment)

Ordered for dependency, not a commitment to schedule:

| Phase | Focus | Closes | Key requirement IDs |
|-------|-------|--------|---------------------|
| **P0** | Wire & versioned release | R7 partial→strong | AR-6, C-1…C-5 — **landed 2026-10-03** (Market/Strategy + auto report rebuild still open) |
| **P1** | Classify | R1, R4 start | S2-* — **landed 2026-10-03** (lite heuristics; expected-docs + page classes still open) |
| **P2** | Dual read + images | R2 | S1-* — **landed 2026-10-04** (vision OCR / real crops / formula+hidden still open) |
| **P3** | Eight labels + header parser | R5, AC-1 | S3-* — **landed 2026-10-03** (dual grid extractors / page bbox still open) |
| **P4** | CoA tree + sector packs | R3 | S4-* — **landed 2026-10-03** (mapping memory + healthcare packs still open) |
| **P5** | Prove + auto-release | R6 | S5-*, AR-*, AC-2, AC-8 — **landed 2026-10-03** (roll-forwards / full ~20-check library still open) |
| **P6** | Validation pack + learning | Outside loop | OL-* — **landed 2026-10-04** (crops / trap CI / threshold tuning still open) |
| **P7** | Goldens, traps, CI ship rule | Release rule | H-*, AC-3…AC-6 — **landed 2026-10-04**; full-size goldens **G6 2026-10-05** |
| **G1–G6** | Gap closure before FDD | FDD-ready contract | See [`databook-gap-closure-before-fdd.md`](./databook-gap-closure-before-fdd.md) — **G1–G6 landed; FDD-ready checklist green** |

---

## 14. Coverage counts (snapshot)

| Area | Done | Partial | Gap |
|------|------|---------|-----|
| Accuracy contract (AC) | 2 | 6 | 1 |
| Stage 5 Prove (S5) | 5 | 5 | 5 |
| Auto-release (AR) | 0 | 3 | 3 |
| Outside/learn (OL) | 5 | 3 | 0 |
| Workers (W) | 0 | 5 | 9 |
| Harness (H) | 7 | 0 | 0 |
| Consume (C) | 2 | 4 | 0 |
| **Approx. total** | **~20** | **~37** | **~55** |

Counts are indicative (some rows span owners). Use IDs above for tracking, not the totals alone.

---

## 15. What already satisfies (or nearly) the earlier MVP plan

These are **Done/Partial for the internal plan**, not for this PDF:

| Capability | Modules | PDF status |
|------------|---------|------------|
| Extract rows from CDL tables | `extract` | Partial vs Stage 1–3 |
| Keyword map + family gates | `map` | Partial vs Stage 4 |
| Block subtotal + series + conflict proposal | `blocks`, `resolve` | Partial vs Stage 5 |
| HITL Correct / Drop / Vouch / Accept | `decisions`, `ui-db` | Partial vs Outside loop |
| DQ API + Findings | `router`, `ui-dq` | Partial product surface |
| Promoted store + some report prefer | `store`, `consume`, `reports` | Partial R7 |

---

*End of matrix. Update Status/Owner columns as work lands; keep PDF section references stable.*
