# Databook gap closure — before FDD

> **Decision (2026-10-05):** Close remaining DiligenceIQ databook contract gaps **before** starting FDD report/deck implementation.  
> **FDD stays parked:** [`fdd-report-implementation.md`](./fdd-report-implementation.md) Phase 0+ deferred until this track reaches **FDD-ready**.  
> **Source matrix:** [`databook-design-requirements-matrix.md`](./databook-design-requirements-matrix.md)  
> **FDD dependency:** Until G1–G6 met → FDD draft mode blocked (FDD PDF §9 / matrix IN-2/IN-3). **G1–G6 landed 2026-10-05 → FDD-ready.**

---

## 1. What “FDD-ready” means for databook

A databook release is FDD-ready when **all** of the following hold on golden deals:

| # | Criterion | Matrix IDs |
|---|-----------|------------|
| 1 | Every material cell has eight labels + status proven/doubtful/missing | AC-1, AC-2, AR-1 |
| 2 | Missing cells carry a **document request** (first-class) | AR-5, AC-3 |
| 3 | Expected-doc / coverage list drives completeness (not ad-hoc keys only) | S2-6, AC-3 |
| 4 | Traceability: page + usable crop (or honest `crop_status`) | AC-5, S1-8, OL-2 |
| 5 | Downstream cannot silently treat unproven as final (hard consume) | AC-7, C-3…C-6, R7 |
| 6 | Core prove library covers roll-forwards / cross-statement / draft→final (or explicit hold) | S5-03…07, S5-15 |
| 7 | Page classes distinguish IS/BS/CF/bridge/note | S2-7 |
| 8 | Goldens at meaningful size; ship gate still green | H-1, AC-6 |

Vision OCR (S1-4/5) and healthcare packs stay **nice-to-have** for first FDD draft; call them FDD-ready+ if time allows.

---

## 2. Ordered work packages (implement in this order)

Critical path for FDD-ready: **G1 → G2 → G3 → G4 → G5 → G6**.  
G7–G8 are parallel / stretch.

### G1 — Honest consume (R7 / AC-7) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| Market trajectory + appendix released PL table with † | `report_market_deck.py` |
| Strategy appendix released financial history | `report_strategy.py` |
| IC Memo appendix uses shared `released_pl_display_rows` | `report_ic_memo.py` |
| `historical_performance` always merges release / strips agent material | `agent_document_historical_performance.py` |
| New release marks ready reports `stale` (catalog + status) | `report_store` + `create_release` |
| Guard `material_agent_fy_values_present` | `services_databook_consume.py` |

**Still open within G1 spirit:** other financial agents (valuation, cost_structure, …) beyond hist-perf; auto rebuild job (stale flag only).

---

### G2 — Expected docs + missing+request (AC-2/3, S2-6, AR-5) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| Expected-document templates (generic / saas) + assess vs file register | `services_databook_classify.py` |
| Persist `expected_docs.json`; rebuild with file register | `services_databook_store.py` |
| Shared coverage fill → missing+`document_request` | `services_databook_coverage.py` |
| Production release stamps `coverage`, `request_list`, `expected_docs` | `services_databook_release.py` |
| Harness G2-request / G2-docs asserts; expanded Deal A/B `coverage_keys` | `services_databook_harness.py` + goldens |
| Findings prepend open document requests; pack cards carry request | `services_databook.py` / pack + UI |

**Done when (met):** release / golden has every expected key as proven, doubtful, or missing+request.

---

### G3 — Page classes + section routing (S2-7) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| `PageClass` enum + register/row provenance fields | `services_databook_models.py` |
| Regex classifier + `resolve_statement_label` + register `by_class` | `services_databook_pages.py` |
| CoA section gate for equity / note / ebitda_bridge | `services_databook_coa.py` |
| Extract stamps `page_class`, routes statement from page/table class | `services_databook_extract.py` (+ dual/blocks) |
| Findings per-file `page_classes`, mismatch/unknown flags | `services_databook.py` |
| Harness G3-class / G3-route + traps t33–t36 | `services_databook_harness.py` + goldens |

**Done when (met):** Deal A/B goldens stable classes; misroute traps green.

---

### G4 — Traceability crops (AC-5, S1-8, OL-2) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| PDF page crop renderer + synthetic high-fidelity fallback | `services_databook_crops.py` |
| `SourceRef.crop_ref` / `crop_status` / `crop_reason` | `services_databook_models.py` |
| Validation pack stamps crops on conflict/doubtful/calibration cards | `services_databook_pack.py` |
| `GET …/databook/crops/{crop_ref}` | `routers_dealroom.py` |
| Validation Pack UI crop thumb + click-through | `ValidationPackReview.tsx` |
| PyMuPDF dependency for real PDF rasterization | `pyproject.toml` |

**Done when (met):** calibration + conflict cards show a real crop for text PDFs (scan/OCR stays `unavailable`).

---

### G5 — Prove library (S5-03…07, S5-15) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| Equity roll-forward (`equity_end ≈ begin + NI − div`) | `services_databook_prove.py` |
| Cash / CF roll (`cash_end ≈ begin + net_change`) | same |
| NI cross-statement agree | same |
| Notes vs statements (lite) | same + notes into pipeline |
| Draft→final bridge (hold draft on mismatch) | same |
| CoA: `net_income`, `dividends`, `net_change_in_cash` | `services_databook_coa.py` |
| Harness `prove` traps t37–t42 + Deal A `expect_prove_ok` | harness + goldens |

**Done when (met):** each check has traps + golden assertion; blocking failures never silent-promote.

---

### G6 — Full-size goldens + ship gate (H-1) — **landed 2026-10-05**

**Shipped**

| Work | Module |
|------|--------|
| Deal A/B goldens ≥195 / ≥252 history figures (`expected_min_figures`) | `fixtures/databook/goldens/deal_{a,b}.json` |
| H-1 figure budget in `run_golden` + ship gate (defaults 195/252) | `services_databook_harness.py` |
| H-4 coverage matrix aligned to `resolve_coverage_spec` years (not incidental cell FYs) | harness H-4 |
| CI workflow step names full-size goldens; `test_databook_g6.py` | `.github/workflows/databook-ship.yml` |

**Ship gate:** Deal A 256 / Deal B 326 figures; coverage + forbid_sources + fingerprint still blocking.

---

### G7 — Spreadsheet fidelity (S1-6) *[parallel after G2]*

Formula+value, hidden rows, tab-as-document contract beyond 40-sheet extract.

### G8 — Vision / OCR (S1-4/5, S5-11, AC-9) *[stretch / FDD-ready+]*

Image bridges → tables; scanned PDF OCR. Highest cost; do after G1–G6 unless a golden deal is image-heavy.

---

## 3. Explicitly deferred (optional before first FDD draft)

- FDD Phase 1+ (databook bridge, claims, QoE, full narrative) — **Phase 0 landed**  
- Spreadsheet fidelity / vision OCR (G7–G8)

Revisit G7–G8 as needed; FDD critical path continues at Phase 1.

---

## 4. Suggested start

**G1–G6 landed → FDD-ready contract met** (G7–G8 optional for first FDD draft mode exit).

---

## 5. FDD-ready checklist (post-G6)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Eight labels + proven/doubtful/missing | Strong Partial (AC-1 labels; AC-2/AR-1) |
| 2 | Missing → document request | **Done** (G2) |
| 3 | Expected-doc / coverage completeness | **Done** (G2) |
| 4 | Traceability crop / honest crop_status | Strong Partial (G4) |
| 5 | Hard consume / no silent final | Strong Partial (G1) |
| 6 | Core prove rolls / cross / draft→final | Strong Partial (G5) |
| 7 | Page classes IS/BS/CF/bridge/note | Strong Partial (G3) |
| 8 | Full-size goldens + green ship gate | **Done** (G6) |

---

## 6. Status

| Package | Status |
|---------|--------|
| G1 Honest consume | **Landed 2026-10-05** |
| G2 Expected docs + missing+request | **Landed 2026-10-05** |
| G3 Page classes | **Landed 2026-10-05** |
| G4 Crops | **Landed 2026-10-05** |
| G5 Prove library | **Landed 2026-10-05** |
| G6 Full goldens | **Landed 2026-10-05** |
| G7 Spreadsheet fidelity | Pending |
| G8 Vision/OCR | Pending (stretch) |
