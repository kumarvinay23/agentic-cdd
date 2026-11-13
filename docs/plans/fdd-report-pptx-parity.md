# FDD Report → Expected PPTX Parity Plan

> **Target look/feel & storyline:** `Project_Crew_FDD_1 (2).pptx` (37-slide advisory FDD pack)  
> **Product decision:** **PPTX only** for the FDD Report deliverable — **no DOCX, no PDF twin**  
> **Baseline today:** `fdd_report` = DOCX + landscape PDF; `fdd_deck` = thin IC PPTX  
> **Companion (prior engine plan):** [`fdd-report-implementation.md`](./fdd-report-implementation.md)  
> **Gap inventory (this conversation):** expected chapters 01–09 vs current `SEC-*` assemble/render  

---

## 0. Goal & non-goals

### Goal

Ship a single **FDD Report** artifact that is a **widescreen PPTX** matching the expected pack’s:

1. Chapter storyline (01–09 + appendices)
2. Slide chrome (banner, narrative headline, KPI/table, Observations, Source, Evidence A/B/C, page #, confidentiality)
3. Dense table-first exhibits (period × metric), not bullet figure dumps
4. Advisory narrative depth (transaction, QoE ADJs, deal protections, R## requests, appendices)

Every figure still traces to the approved databook / exhibit store (R1–R5 unchanged).

### Non-goals (this plan)

- Matching every Compost Crew deal-specific judgement verbatim (content engines may still be empty on a given run)
- Keeping Word/PDF as parallel FDD Report outputs
- Redesigning databook extract itself (only consume/render/storyline)
- Pixel-perfect PowerPoint theme cloning on day one (chrome contract first, then visual polish)

### Product shape decision

| Today | Target |
|-------|--------|
| `fdd_report` → DOCX + PDF | `fdd_report` → **PPTX only** (expected-pack format) |
| `fdd_deck` → thin IC PPTX | **Deprecate or fold** into the report (recommended: retire `fdd_deck` from UI; keep builder stub redirecting to `fdd_report` for one release) |

**Recommendation:** Make `fdd_report` the only user-facing FDD download. Do not maintain a second “IC deck” storyline unless product explicitly wants a short ES-only pack later.

---

## 1. Expected pack contract (acceptance reference)

### 1.1 Chapter map (must produce these sections)

| # | Chapter | Expected slides (ref) | Required page types |
|---|---------|----------------------|---------------------|
| 00 | Cover | 1 | Deal/engagement cover |
| — | Contents | 2 | Numbered TOC with page refs |
| 01 | Introduction | 3 | Scope/basis/materiality/limitations/reader/entity/EBITDA def |
| 02 | Executive summary | 4–7 | KPI strip; ranked findings; EBITDA views; deal asks |
| 03 | Transaction and business | 8–9 | Round/terms; revenue-by-stream |
| 04 | Quality of earnings | 10–15 | QoE summary table; walks; ADJ cards; CIM; sensitivities |
| 05 | Trading | 16–19 | Margin/cost intensity; mix/concentration; EBITDA bridge; YTD |
| 06 | Cash flow | 20–21 | OCF/FCF/dividends; cash bridge / grant if in evidence |
| 07 | Balance sheet, debt and leases | 22–26 | NAV; net debt + debt-like; leases; NWC; equity/dividends |
| 08 | Deal considerations | 27–29 | Protections map; information-request book (R##) |
| 09 | Appendices | 30–37 | Claims ledger; document register; inconsistencies; glossary |

### 1.2 Slide chrome contract (every content slide)

```
[SECTION BANNER] ............................. Project Crew | Draft basis
Narrative headline (one sentence, claim-led)
┌──────────────┐  ┌─────────────────────────┐
│ Table/Chart  │  │ Observations (bullets)  │
└──────────────┘  └─────────────────────────┘
Source: … [D##] …                              Evidence A/B/C     {n}
```

Cover + TOC + pure-table appendix slides may omit Observations; they still need Source/Evidence where figures appear.

### 1.3 Presentation standards

- Widescreen **13.33 × 7.5 in**
- Scale default for this pack: **$k** (configurable via scope; one scale per exhibit)
- Negatives in brackets; compute unrounded; display HALF_UP
- Period labels as on exhibits (`FY25A`, `LTM Jul-26`, `YTD Jul-26`, …)
- Font stack: Arial (or house template equivalent) with section ~20pt, body 7–11pt

---

## 2. Architecture change

### 2.1 From dual-render sections → chaptered slide spec

```
Approved databook + models + QoE + claims + findings + readiness
        │
        ▼
   Chapter planners (01–09)  ──▶  SlideSpec[]  (typed layouts)
        │
        ▼
   Figure binder (exhibit cells / tokens only)
        │
        ▼
   PPTX renderer (layout templates)
        │
        ▼
   fdd_report artifact: *.pptx
```

Replace today’s `assemble_report_spec(kind=report|deck)` split (DOCX sections vs thin slides) with **one slide-oriented `report_spec`**.

### 2.2 New / extended types (schemas)

Add to `fdd_schemas.py` (names indicative):

- `FddChapterId` — `cover|contents|intro|es|transaction|qoe|trading|cash|bs|deal|appendix`
- `SlideLayoutId` — `cover|toc|kpi_strip|table_obs|chart_obs|adj_card|two_table|protections|request_list|ledger|glossary|findings_rank`
- `SlideSpec` — `slide_id`, `chapter`, `layout`, `banner`, `headline`, `kpis[]`, `table`, `chart_ref`, `observations[]`, `source`, `evidence_tier`, `page_no`, `figure_ids[]`
- `ChapterPlan` — ordered `SlideSpec` list + held-back reasons

Keep exhibit store + tokens as SoT for numbers. Slides reference `figure_ids` / tokens; renderer resolves display strings.

### 2.3 Module map

| Concern | Primary modules |
|---------|-----------------|
| Chapter planning | new `services_fdd_chapters.py` (or package `fdd_chapters/`) |
| Assemble | rewrite `services_fdd_assemble.py` → emit `SlideSpec` nodes only |
| PPTX chrome + tables | new `services_fdd_pptx.py` (templates); slim `report_fdd.py` |
| Retire DOCX/PDF report path | remove/guard `_write_fdd_docx`, `_write_fdd_pdf` from `fdd_report` export |
| Commentary | extend `services_fdd_commentary.py` for chapter headlines + Observations |
| QoE / requests / register | `services_fdd_qoe.py`, `services_fdd_readiness.py`, `services_fdd_claims.py`, document register services |
| UI | `DealReports.tsx`, `report_store.py` — PPTX download only; drop PDF twin preview for FDD |

---

## 3. Phased implementation

### Phase A — Product cutover: PPTX-only report shell (1–2 days) — **DONE**

**Intent:** Stop emitting DOCX/PDF for `fdd_report`; establish PPTX as the only artifact even before full parity.

**Work**

1. `FddReportBuilder.export_artifact` writes **PPTX** (initially can wrap improved deck renderer).
2. Remove `ctx.pdf_artifact_path` for `fdd_report`; UI preview uses PPTX download / first-slide thumbnail if available.
3. Catalog copy: “FDD Report (PowerPoint)”.
4. Deprecate `fdd_deck` in UI (`hidden` or alias to `fdd_report`).
5. Update tests that assert DOCX/PDF paths (`test_fdd_report_pdf.py` → PPTX contract tests).

**Done when:** Generate FDD Report returns a `.pptx` only; no DOCX/PDF twin created.

**Landed:** `FddReportBuilder` exports `*_FDD_Report.pptx` from deck slide nodes; no DOCX/PDF twin; catalog `export=pptx`; `fdd_deck` marked `deprecated` and hidden in UI; preview uses PPTX path.

---

### Phase B — Slide template system (3–5 days) — **DONE**

**Intent:** Implement chrome layouts that can host any chapter page.

**Work**

1. Build layout builders in `services_fdd_pptx.py`:
   - `cover`, `toc`, `section_table_obs`, `section_chart_obs`, `kpi_strip`, `findings_rank`, `adj_detail`, `request_table`, `ledger_table`, `glossary`
2. Shared chrome helpers: banner, subtitle basis line, Source footer, Evidence badge, page number, confidentiality footer on cover.
3. Table helper: build PowerPoint tables from `Exhibit` / matrix DTOs (periods as columns).
4. Snapshot tests: render each layout with fixture figures → compare shape counts / key text / table dims (not pixels).

**Done when:** A hand-built fixture `report_spec` of ~8 slides visually matches expected chrome patterns (banner/headline/obs/source/evidence).

**Landed:** `SlideSpec` + layout schemas in `fdd_schemas.py`; `services_fdd_pptx.py` chrome layouts + fixture; `FddReportBuilder` renders via chrome adapter (`stub_pages_to_slides`); tests in `test_fdd_pptx_chrome.py`.

---

### Phase C — Storyline remap (assemble) (3–4 days) — **DONE**

**Intent:** Replace SEC-A…K report nodes with expected chapters 01–09.

**Work**

1. Define `DEFAULT_CHAPTER_ORDER` matching expected TOC.
2. Map existing engines → chapters:

| Chapter | Existing sources to reuse |
|---------|---------------------------|
| Intro | scope profile, readiness, materiality, limitations |
| ES | findings dashboard, KPI figures from M1/M2/M6/M7, QoE headline |
| Transaction | deal profile / CIM claims / revenue mix if available; else held + R## |
| QoE | `qoe.json` bridge, register rows, sensitivities, CIM crosswalk exhibit |
| Trading | M1/M2/M3 + mix schedules |
| Cash | M7 + databook SoCF + dividend/grant facts when present |
| BS / debt / leases | M5/M6/M8 + lease/debt-like schedules + equity rolls |
| Deal | protections derived from high findings + `build_request_list` |
| Appendices | claims ledger, document register, inconsistency report, glossary |

3. Held-back policy: if a chapter lacks evidence, emit the slide shell with explicit held/limitation Observations + request IDs (do not omit the chapter).
4. Page numbering stable enough for TOC (two-pass assemble: plan slides → assign page_no → fill TOC).

**Done when:** Generated PPTX has the same chapter sequence as expected (slide count may differ slightly while content is thin).

**Landed:** `services_fdd_chapters.py` planners; `ReportSpec.slides`; assemble emits 01–09 (+ cover/TOC) with held shells; two-pass TOC page refs; `FddReportBuilder` renders `spec.slides`; tests in `test_fdd_chapters.py`. SEC-* section nodes retained for legacy report render.

---

### Phase D — Content depth per chapter (5–8 days) — **DONE**

**Intent:** Close the analysis gaps that are structural, not just layout.

Build in priority order (IC-critical first):

1. **ES KPI strip + ranked findings + deal asks**
2. **QoE summary table + bridge walk + ADJ cards** (even if many ADJs are nil / pending)
3. **Trading margin table + cost bridge + concentration** (DC/municipal when facts exist)
4. **Net debt + debt-like** (include accrued dividends when in BS)
5. **NWC table + peg rule** (“no peg” when policy says so)
6. **Deal protections map + R## request book** (from readiness/findings)
7. **Introduction** full narrative blocks
8. **Transaction / revenue streams**
9. **Leases / equity rolls / cash dividend leakage**
10. **Appendices** (claims ledger pages, document register, inconsistencies, glossary)

For each: planner → table DTO → Observations tokens → Source line builder (document register ids).

**Done when:** On Test6 / Compost Crew, chapters 02/04/05/07/08 are recognizably the same *shape* as expected; missing evidence shows as held/R## rather than blank omission.

**Landed:** Deepened `services_fdd_chapters.py` — ES KPIs from M1/M5/M6 + findings/asks; QoE bridge + empty-ADJ pending card + sensitivities; Trading margin/cost tables + held mix; Cash OCF/FCF + dividends payable; BS net debt/debt-like + NWC no-peg + leases held; Deal protections + synthesized R##; Appendix claims/inconsistencies/glossary. Tests in `test_fdd_phase_d_content.py`.

---

### Phase E — Scale, periods, source basis (2–3 days) — **DONE**

**Work**

1. Scope option / report default: display scale `$k` for FDD Report PPTX (keep internal exhibit store units; convert at render).
2. Period pack: ensure LTM / YTD closed periods appear when databook has them (not only FY + plan years).
3. Basis labels on every table (“unaudited monthly management accounts…”) via scope + source register.
4. Evidence tier propagation onto slides from exhibit cells / QoE rows.

**Done when:** A generated ES + QoE slide shows `$k` and LTM/YTD when inputs exist; Source lines cite register ids.

**Landed:** `ScopeProfile.report_display_scale` / `basis_of_preparation`; chapter `DisplayCtx` converts store `M` → PPTX `$k` in `_fmt_num`; `_period_table` adds YTD/LTM columns + basis/source/evidence; PPTX renders table basis lines; tests in `test_fdd_phase_e_scale.py`.

---

### Phase F — UI / API / catalog cleanup (1–2 days) — **DONE**

**Work**

1. `report_store.py`: `fdd_report` formats = `["pptx"]` only; remove pdf twin flags.
2. `DealReports.tsx`: stop PDF preview path for FDD; download PPTX; update help text.
3. Optional: keep `fdd_deck` API id as alias → same builder for back-compat, marked deprecated.
4. Publish/export paths in `services_published_pages.py` / publisher: PPTX only.

**Done when:** UI never offers Word/PDF for FDD Report.

**Landed:** `formats: ["pptx"]` on FDD catalog entries; `is_fdd_pptx_only` strips PDF twin meta; download/preview reject PDF for FDD; `FddDeckBuilder` aliases chaptered PPTX; UI hides deprecated deck, blocks PDF twin, copy says PowerPoint only; tests in `test_fdd_phase_f_catalog.py`.

---

### Phase G — Parity harness & goldens (3–4 days) — **DONE**

**Work**

1. Golden: structural checklist against `Project_Crew_FDD_1 (2).pptx` (chapter presence, required layouts, chrome fields).
2. Test6 smoke: generate PPTX; assert min slides, required banners, at least one table per core chapter, no DOCX/PDF artifacts.
3. Optional visual diff later (render slide → PNG) — not blocking Phase D.
4. Update design matrix row R5: one report_spec → **one PPTX deliverable**.

**Done when:** CI fails if cover/TOC/ES/QoE/Trading/BS/Deal/Appendix chapters or chrome fields are missing.

**Landed:** `tests/fixtures/fdd/pptx_parity_contract.json`; `services_fdd_parity.py` checkers; `@pytest.mark.fdd_ship` tests in `test_fdd_phase_g_parity.py` (structural golden + Test6 smoke + missing-chapter CI guard); design matrix R5/AS-5 updated to one PPTX deliverable.

**Optional visual diffs (landed):** `services_fdd_visual_diff.py` — PPTX→PDF (LibreOffice) → PNG (PyMuPDF/pdftoppm) → mean-abs pixel compare. Off unless `FDD_VISUAL_DIFF=1`; reference via `FDD_VISUAL_REF_PPTX`. Contract block `visual_diff` in `pptx_parity_contract.json`. Tests: `test_fdd_visual_diff.py` (`@pytest.mark.fdd_visual`). CLI: `python -m agetic_cdd_api.services_fdd_visual_diff --candidate ours.pptx --reference Project_Crew.pptx --force`.

---

## 4. Suggested file-level worklist

| Action | Path |
|--------|------|
| Add | `apps/api/src/agetic_cdd_api/services_fdd_chapters.py` (planners) |
| Add | `apps/api/src/agetic_cdd_api/services_fdd_pptx.py` (layouts) |
| Extend | `fdd_schemas.py` (`SlideSpec`, layouts, chapters) |
| Rewrite | `services_fdd_assemble.py` (chaptered slide nodes) |
| Slim/rewrite | `report_fdd.py` (`FddReportBuilder` → PPTX only) |
| Gate/retire | `services_fdd_report_pdf.py` usage from report export (keep only if needed for internal QA screenshots) |
| Extend | `services_fdd_commentary.py`, `services_fdd_findings.py`, `services_fdd_qoe.py`, `services_fdd_readiness.py` |
| Update | `report_store.py`, `DealReports.tsx`, `api.ts` |
| Add tests | `tests/test_fdd_report_pptx.py`, chapter planner unit tests, chrome contract tests |
| Fixture | optional checked-in expected TOC JSON extracted from `Project_Crew_FDD_1 (2).pptx` |

---

## 5. Mapping: expected slide → implementation owner

| Ref slides | Owner planner | Figure sources |
|-----------|---------------|----------------|
| 1 Cover | `plan_cover` | scope, deal profile |
| 2 Contents | `plan_toc` | chapter page index |
| 3 Intro | `plan_intro` | scope, readiness, materiality |
| 4–7 ES | `plan_es` | M1/M2/M6/M7, findings, QoE |
| 8–9 Transaction | `plan_transaction` | deal profile, mix facts, CIM claims |
| 10–15 QoE | `plan_qoe` | qoe workbook, bridge, CIM |
| 16–19 Trading | `plan_trading` | M1–M3, concentration |
| 20–21 Cash | `plan_cash` | M7, SoCF, dividends/grant |
| 22–26 BS/Debt/Leases | `plan_bs` | M5/M6/M8, leases, equity |
| 27–29 Deal | `plan_deal` | findings, request list |
| 30–37 Appendices | `plan_appendix` | claims, doc register, glossary |

---

## 6. Sequencing & dependencies

```
A PPTX-only cutover
    └─▶ B Template chrome
            └─▶ C Chapter assemble
                    ├─▶ D1 ES/QoE/Trading/Deal content
                    ├─▶ D2 BS/Cash/Intro/Transaction/Appendix
                    └─▶ E Scale/periods/source
                            └─▶ F UI cleanup
                                    └─▶ G Goldens/CI
```

Critical path: **A → B → C → D(ES/QoE/Deal) → G**.  
Transaction/leases/appendix depth can trail without blocking first parity milestone.

---

## 7. Milestones & acceptance

### M1 — PPTX-only shell
- [x] `fdd_report` artifact is `.pptx`
- [x] No DOCX/PDF written on generate
- [x] UI download is PPTX

### M2 — Chrome parity
- [x] Content slides have banner, headline, Observations, Source, Evidence, page #
- [x] At least one real PowerPoint table layout in use

### M3 — Storyline parity
- [x] TOC lists chapters 01–09 matching expected names
- [x] All chapters present (held slides allowed)

### M4 — Content parity (Test6)
- [x] ES shows KPI strip + ranked findings
- [x] QoE chapter has summary table + bridge/ADJ structure
- [x] Deal chapter has protections + request list structure
- [x] Appendices include claims ledger + glossary at minimum

### M5 — Hardening
- [x] Structural golden vs expected TOC/layouts in CI
- [x] `fdd_deck` deprecated or removed from UI
- [x] Design docs updated (this plan + matrix R5)

---

## 8. Risks & decisions

| Risk / decision | Mitigation |
|-----------------|------------|
| Empty QoE register → thin QoE chapter | Always emit structure; mark pending; create R##; do not skip chapter |
| Mix/DC/lease facts missing in databook | Held Observations + requests; don’t invent figures |
| `$k` vs internal `M` store | Convert only at PPTX render; keep tokens bound to store cells |
| Dual maintenance of deck + report | Retire `fdd_deck` user surface |
| Exact visual match to expected theme | Phase B contract first; optional theme polish sprint after M4 |
| Large PPTX tables overflowing | Pagination rules (1/2, 2/2) like expected request/claims slides |

**Open product confirmations (defaults assumed in this plan):**

1. Retire `fdd_deck` from UI — **Yes (assumed)**  
2. Default display scale `$k` — **Yes (assumed to match expected)**  
3. No PDF preview at all — **Yes (PPTX download only)**  

---

## 9. Immediate next step when implementation starts

1. Land **Phase A** (PPTX-only export + test/UI path flip).  
2. Extract a frozen **TOC + layout checklist JSON** from `Project_Crew_FDD_1 (2).pptx` as the golden contract.  
3. Implement **Phase B** `table_obs` + `kpi_strip` layouts and wire ES + one Trading slide as the first vertical slice.

---

## 10. Out of scope reminders

- Do not reintroduce DOCX/PDF as FDD Report outputs under this plan.  
- Do not treat bullet exhibit dumps as chapter body once table layouts exist.  
- Do not average or invent figures to “look like” the expected pack; match **format and structure**, fill numbers only from databook-backed exhibits.
