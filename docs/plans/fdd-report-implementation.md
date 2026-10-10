# FDD Report & Deck — Step-by-Step Implementation Plan

> **Source:** `DiligenceIQ_FDD_Report_and_Deck_Creation_Design.pdf` (Sep 28, 2026)  
> **Requirements:** [`fdd-report-design-requirements-matrix.md`](./fdd-report-design-requirements-matrix.md)  
> **Upstream:** Databook release + consume (`services_databook_*`, `services_databook_consume.py`)  
> **Platform reuse:** `report_store.py`, `report_builder_base.py`, `routers_reports.py`, `DealReports.tsx`  
> **Critical path (PDF §9):** **0 → 1 → 3 → 5a → 6 → 8** (phases 2 & 4 beside 3; renderer 7 after 0)  
> **Status:** Phase 0–3 + **4 evidence (P3)** + 5a + **5b (M1/M2/M3/M7 + M8/M5/M6 + QoE ensure + G3)** + 6 + **7 assembly** + **8 QA (G5–G7)** + **9 goldens/ship gate** + **UX polish (scope editor, G2 UI, DOCX, rounding/axes) landed 2026-10-09**. Next: expand goldens / M9 optional.  
> ([`databook-gap-closure-before-fdd.md`](./databook-gap-closure-before-fdd.md) — G1–G6 FDD-ready).

---

## 1. Product goal

Turn a **validated databook release**, agent leads, VDR evidence and specialist models into an **industry-standard FDD report and IC deck** where:

1. Every number traces to a databook fact ID (or a model output of those facts).
2. Agents never seed exhibits.
3. Humans only approve judgements (scope, material adjustments, key findings, release).
4. One **report specification** renders both deliverables with identical figures.

**Done means:** on 3–5 golden deals, the suite reproduces hand-checked exhibits / QoE register / findings; seeded S1 faults block release; draft mode engages when databook is below contract.

---

## 2. Architecture (target)

```
Approved databook release
        │
        ▼
┌───────────────────┐     ┌─────────────────┐
│ Run manifest      │────▶│ Stage runner P0 │
│ (db/model/prompt  │     │ JSON artefacts  │
│  versions, scope) │     └────────┬────────┘
└───────────────────┘              │
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
   P1 readiness              P2 claims ledger            P3 → databook
   G0 / G1 scope             G2 inputs                   re-entry
        │                          │
        └────────────┬─────────────┘
                     ▼
              P4 models M1–M9 ──▶ Exhibit store (versioned cells)
                     │                    │
                     ▼                    │
              P5 QoE + G4                 │
                     │                    │
                     ▼                    ▼
              P6 tagged commentary ◀── number tokens
                     │
                     ▼
              P7 one report_spec ──▶ Report renderer + Deck renderer
                     │
                     ▼
              P8–P10 QA / G5–G7 ──▶ Final snapshot + evidence pack
```

**Reuse, don’t fork:** extend `REPORT_TYPES` with `fdd_report` + `fdd_deck` (or one type that emits both), keep SSE/generate UX, add a dedicated FDD run store under `{deal}/fdd/runs/{run_id}/`.

---

## 3. Phase plan (build order)

### Phase 0 — Foundations (plumbing first) — **landed 2026-10-06**

**Shipped**

| Work | Module |
|------|--------|
| Run store + manifest under `{deal}/fdd/runs/{run_id}/` | `services_fdd_store.py` |
| Appendix A lite schemas (scope, claims, exhibit cell, adj, section, issue, approval, report_spec) | `fdd_schemas.py` |
| Exhibit store (fact_id, figure type, evidence tier, status, versions) | `services_fdd_exhibit.py` |
| Number tokens `{{ex:exhibit_id.cell_id}}` + resolver | `services_fdd_tokens.py` |
| Dependency graph cell → exhibit → section → gate | `services_fdd_deps.py` |
| Shared report_spec → stub PDF page + stub PPTX slide | `services_fdd_render.py`, `report_fdd.py` |
| Register `fdd_report` / `fdd_deck` in catalog | `report_store.py`, `app.py` |
| API: create/list/get run, exhibits, cell update, render-stub, deps | `routers_fdd.py` |

**Done when (met):** changing one exhibit cell updates both renders; token round-trip in `tests/test_fdd_phase0.py`.

---

### Phase 1 — Databook contract bridge — **landed 2026-10-06**

**Shipped**

| Work | Module |
|------|--------|
| Release → `FddFact` table (eight labels + status) | `services_fdd_bridge.py`, `facts.json` |
| Contract assessment → `draft_mode` / `g6_blocked` | `assess_databook_contract` |
| Every figure `draft_flagged` when incomplete | facts + exhibit cells |
| Pin guard: refuse start if pin ≠ current (unless `allow_pinned_release`) | `check_release_pin` / HTTP 409 |
| Bridge on run create + `POST …/bridge`; `GET …/facts`, `GET …/contract` | `routers_fdd.py` |

**Done when (met):** readiness can read status + labels from a real release (`tests/test_fdd_phase1.py`).

---

### Phase 2 — Readiness & scope (P1, G0, G1) — **landed 2026-10-07**

**Shipped**

| Work | Module |
|------|--------|
| Input inventory scanner (7 IN-1 inputs) | `services_fdd_readiness.py` |
| G0 scoring (≥90% required at tier C+) + request list | `ReadinessReport`, `RequestListDoc` |
| Scope profile seed/update (IN-4 / IN-5 defaults) | `services_fdd_scope.py`, `scope.json` |
| G1 approve gate (blocked until G0 unless overridden) | `POST …/gates/G1/approve` |
| Persist readiness / requests / approvals | `services_fdd_store.py` |
| API: readiness scan, scope GET/PUT, gates, phase2 bootstrap | `routers_fdd.py` |
| Auto-seed on `ensure_phase0_run` | `services_fdd_render.py` |

**Done when (met):** readiness report + lead-approvable scope (`tests/test_fdd_phase2.py`). UI editor still thin (API-first).

---

### Phase 3 — Claims ledger (P2) — **landed 2026-10-07**

**Shipped**

| Work | Module |
|------|--------|
| Agent output → structured claims (financial + qualitative) | `services_fdd_claims.py` |
| Financial tests vs fact table (`agrees` / `contradicted` / `unverifiable`) | `evaluate_financial_claim` |
| Qualitative `narrative_ok` only with `cited_pages` | extract path |
| Module unreliable when fail_rate >50% | `ModuleReliability` / manifest |
| R2 — reject `agent:` fact_ids on exhibit upsert | `assert_fact_id_not_agent_sourced` |
| Lite P4 — open request list rows for failed financial claims | `_append_claim_requests` |
| Persist `claims.json`; API GET/POST build + reliability | `services_fdd_store.py`, `routers_fdd.py` |

**Done when (met for unit path):** `tests/test_fdd_phase3.py`. Golden-deal hand-check fixture still outstanding.

---

### Phase 4 — Evidence retrieval (P3) *[parallel with Phase 3]* — **landed 2026-10-09**

**Shipped**

| Work | Module |
|------|--------|
| Claim-gap inventory + suggested VDR filenames | `list_claim_gaps` / `services_fdd_evidence.py` |
| P3 pass: rescan / reread / deep / rebridge → bridge → P2 claims | `run_p3_evidence_pass` |
| Request list claim links + reconcile to `received` | `RequestListItem.claim_id`, `reconcile_requests_after_claims` |
| API gaps / retrieve / request PATCH | `routers_fdd.py` |
| Audit artefact `evidence.json` | `EvidencePassDoc` |

**Done when:** contradicted claim → new release → bridge → claim `agrees` (unit path in `test_fdd_phase4.py`). Metric-scoped page extract still deferred.

---

### Phase 5a — QoE model (M4) *[critical path]* — **landed 2026-10-07**

**Build**

- QoE workbook/module generator (`services_fdd_qoe.py` → `qoe.json`).
- Candidate merge by event key; evidence status + treatment + consumption ledger.
- Bridge + management↔diligence walk; sensitivities & pro forma **beside** adj. EBITDA.
- **G4** approval (`POST …/gates/G4/approve`; partner required for partly-evidenced pro forma).
- PDF §5 worked example reproducible (`worked_example=True`); tests assert 101.3 / 99.3–104.1 / 108.8 / M=7.25.

**Done when:** section 5 example matches exactly; golden registers match hand-check. ✅

---

### Phase 5b — Remaining models — **partial 2026-10-08 (M1/M2/M7 + M8/M5/M6 + QoE ensure)**

**Order:** M1 → M8 → M5 → M6 → M7 → M2 → M3 → M9 (last, optional).

**Landed (slice):**
- `services_fdd_models.py` — **M1 historical trading** (`ex_m1_trading` / SEC-B): multi-year IS lines, YoY %, derived margins.
- **M2 revenue & margin** (`ex_m2_margin` / SEC-C): GM%/EM% levels, Δpp walk, COGS/GP, optional concentration.
- **M7 cash conversion** (`ex_m7_cash` / SEC-I): OCF, |capex|, FCF = OCF − |capex|, conversion = OCF÷EBITDA.
- M8 BS / M5 NWC / M6 net debt exhibits from fact table (+ store lines).
- QoE (M4) auto-built + synced on ensure so SEC-E unblocks.
- Net debt = gross debt (+ debt-like) − cash; leases disclosed beside.
- NWC = WC assets − WC liabilities; mapped to SEC-F/G/H.
- SEC-B / SEC-C / SEC-I commentary prefer M1 / M2 / M7 tokens.
- `POST …/fdd/runs/{id}/models/build`; wired into `ensure_phase0_run`.

Still open: expand goldens, M9 optional, metric-scoped page extract.

**G3 check packs (landed 2026-10-09):** `services_fdd_checks.py` — formula + fact_id packs per M1–M3/M5–M8; blocking fails demote exhibits to DRAFT (`g3_held:`) and hold commentary; `manifest.g3_passed`; `GET …/gates` + `…/models/checks`.

**Done when:** every model passes checks on goldens or holds back with reason.

---

### Phase 6 — Sections & commentary (P6) *[critical path]* — **landed 2026-10-07**

**Build**

- Section writers A–K + ES (`services_fdd_commentary.py` → `commentary.json`) with tags F/A/M/Q.
- Numbers only as `{{ex:…}}` tokens; typed-figure ban (`assert_no_raw_numeric_literals`).
- Fixed confidence / invest / superlative checks; limitations from request list + QoE blockers.
- QoE bridge figures synced to `ex_qoe_bridge` exhibit for token binding; report_spec commentary nodes.

**Done when:** commentary tests pass; typed-figure faults caught. ✅

---

### Phase 7 — Assembly & renderers (P7) — **landed 2026-10-08**

**Build**

- Single `report_spec` JSON from commentary + exhibits (`services_fdd_assemble.py`).
- Paired `sec_comment_*` / `slide_comment_*` nodes + exhibit sections + presentation standards.
- Report renderer (PDF) + deck renderer (PPTX) via `report_fdd.py` / `render_stub` — identical figures from shared cell_refs.
- `ensure_commentary_and_assemble` on phase0 refresh + report generate; commentary/build reassembles.

**Done when:** report and deck show identical figures from one spec. ✅

---

### Phase 8 — QA & review (P8–P9, G5–G7) *[critical path]* — **landed 2026-10-08**

**Build**

- Check catalogue in `services_fdd_qa.py` (recon, QoE arithmetic, perimeter, double-count, evidence, typed figures, tokens, completeness, deck quality, claims).
- Issue log (`qa.json`) with severity S1–S4 + origin stage; resolve / waive (S1 not waivable).
- Partner challenges (P9); G5 lead QA; G6 partner (requires non-draft + clear challenges); snapshot freeze; G7 hash verify.
- Material cell edits / seeded faults → `reset_gates_on_material_change` supersedes G5–G7.

**Done when:** seeded S1 faults block finalisation; material change resets correct gates. ✅

---

### Phase 9 — Regression & release (P10 + harness) — **landed 2026-10-08**

**Build**

- Golden FDD deals `deal_alpha` / `deal_beta` (`tests/fixtures/fdd/goldens/`) — hand-checked release cells, model cells (NWC / net debt), QoE expectations (facts + PDF §5 worked example).
- Seeded-fault suite (`traps.jsonl`) — typed figures, model formulas, token match, exhibit route, pin version, QoE invariants.
- CI gate: `python -m agetic_cdd_api.fdd_ship_gate` + `.github/workflows/fdd-ship.yml` (mirror databook ship).
- Evidence pack export (`export_evidence_pack`) — run artefacts + `evidence_manifest.json`.
- Bonus fix: Phase 5b line dedupe (fact table ∪ store) so bridged REPORTED cells do not double-count.

**Done when:** suite runs on every build and blocks release on failure. ✅ (2 goldens + 12 traps; expand toward 3–5 deals later.)

---

## 4. Suggested sprint slicing (practical)

| Sprint slice | Phases | Ship artifact |
|--------------|--------|---------------|
| **F0** | 0 | Exhibit store + tokens + dual render stub |
| **F1** | 1 | Draft-mode FDD facts from current release |
| **F2** | 2 | Scope profile + G0/G1 API (UI later) |
| **F3** | 3 (+4 lite) | Claims ledger; failed claims → request list |
| **F4** | 5a | QoE register + G4 + §5 example |
| **F5** | 5b (M1, M8, M5, M6) | Core BS / NWC / net debt / trading |
| **F6** | 6 + 7 skeleton | One section (QoE) in report_spec → PDF + 3 slides |
| **F7** | 5b rest + full P6/P7 | Full section set |
| **F8** | 8 + 9 | Gates G5–G7 + CI goldens |

Do **not** start full narrative or deck polish before F0–F1 and F4.

---

## 5. API / UI surfaces (net-new)

| Surface | Purpose |
|---------|---------|
| `POST …/fdd/runs` | Start run from pinned databook release |
| `GET …/fdd/runs/{id}` | Manifest, stage statuses, readiness |
| `GET/PUT …/fdd/runs/{id}/scope` | Scope profile (Phase 2) |
| `POST …/fdd/runs/{id}/gates/G1/approve` | G1 scope approval |
| `GET/POST …/fdd/runs/{id}/readiness[/scan]` | G0 readiness + request list |
| `GET/POST …/fdd/runs/{id}/claims[/build]` | Claims ledger + extract/test |
| `GET …/fdd/runs/{id}/claims/reliability` | Per-module fail rates |
| `GET/POST …/fdd/runs/{id}/qoe[/build]` | QoE workbook + §5 worked example seed |
| `POST …/fdd/runs/{id}/models/build` | Phase 5b — QoE exhibit + M8/M5/M6 BS/NWC/net debt |
| `PUT …/fdd/runs/{id}/qoe/register` | Upsert adjustments; recompute bridge |
| `GET …/fdd/runs/{id}/qoe/bridge` | Bridge, walk, materiality, ranges |
| `POST …/fdd/runs/{id}/gates/G4/approve` | G4 QoE judgements (+ partner flag) |
| `GET/POST …/fdd/runs/{id}/commentary[/build]` | Section drafts F/A/M/Q + typed-figure ban; build reassembles report_spec |
| `GET …/fdd/runs/{id}/commentary/{section}` | One section draft |
| `POST …/fdd/runs/{id}/commentary/validate` | Re-run narrative checks |
| *(implicit)* `report_spec` assembly | Phase 7 — via commentary/build + `fdd_report`/`fdd_deck` generate |
| `GET/POST …/fdd/runs/{id}/qa[/scan]` | QA catalogue + issue log |
| `POST …/fdd/runs/{id}/qa/issues/{id}/resolve` | Resolve / waive issue |
| `POST …/fdd/runs/{id}/qa/challenges[/…/respond]` | Partner challenge list |
| `POST …/fdd/runs/{id}/gates/G5|G6/approve` | Lead QA / partner challenge |
| `POST …/fdd/runs/{id}/snapshot/freeze` | Freeze artefact hashes |
| `POST …/fdd/runs/{id}/gates/G7/verify` | Hash-match frozen snapshot |
| `GET …/fdd/exhibits` | Exhibit store browse |
| `POST …/fdd/gates/{g}/approve` | G1/G4/G6 |
| `POST …/reports/fdd_report|fdd_deck/generate` | Prefer generate from approved snapshot only |

UI: FDD workspace tabs — Readiness · Scope · Claims · QoE · Exhibits · Review · Release (reuse DealReports preview for final artefacts).

---

## 6. Test strategy

| Layer | What |
|-------|------|
| Unit | Token resolve; eight-label conflict; consumption ledger; bridge re-add; rounding |
| Golden | 3–5 deals: exhibits, QoE register, findings, claim tests |
| Fault injection | Agent figure in exhibit → S1; typed number in commentary → S1; perimeter leak → S1 |
| Integration | P3 → new databook version → P2 refresh |
| CI | `fdd_ship_gate` (hashes + goldens + traps) |

---

## 7. Risks & open design points (PDF §10)

| Risk / gap | Mitigation in build |
|------------|---------------------|
| Databook below contract | Enforce draft mode; no G6 |
| Lease treatment in net debt | Scope profile override; always separate B6 line |
| Prompt pack untested E2E | Schema-validate every stage; temp=0; golden before prompt expand |
| Renderer / approval UX unbuilt | Phase 0 stub + Phase 8 explicit |
| Tax DD bleed | Pointers only; no tax model in FDD |

---

## 8. Immediate next actions

1. ~~Freeze this plan + requirements matrix as FDD context (this folder).~~
2. ~~Implement **Phase 0** exhibit store + number tokens + dual-render stub.~~
3. ~~Wire **Phase 1** to current databook release (draft mode if incomplete).~~
4. ~~Implement **Phase 2** scope profile + G0/G1.~~
5. ~~Implement **Phase 3** claims ledger (+ lite request open-items).~~
6. Stand up first golden deal fixture under `apps/api/tests/fixtures/fdd/`.
7. ~~Deepen Phase 4 (targeted VDR / databook rescan from claim gaps).~~
8. ~~Implement QoE (Phase 5a).~~ ~~Phase 5b M1/M2/M3/M7 + M8/M5/M6 + QoE ensure + G3.~~ ~~Phase 6 commentary.~~ ~~Phase 7 assembly.~~ ~~Phase 8 QA (G5–G7).~~ ~~Phase 9 goldens + ship gate.~~ ~~UX polish: scope editor, G2 gate UI, DOCX, rounding/deck axes.~~ → next: expand goldens / M9 optional.

---

## 9. Traceability

| PDF § | Plan coverage |
|-------|----------------|
| §1 Rules & decisions | Matrix R*/D*; plan §1–2 |
| §2 Workflow & sources | Phases 2–4, 8 |
| §3 Inputs & section maps | Phases 1–2, 6; SEC-* |
| §4–5 Models & QoE | Phases 5a–5b |
| §6–7 Blueprint & prompts | Phases 6–7; P0–P10 table |
| §8 Gates & severity | Phase 8 |
| §9 Build sequence | This document §3–4 |
| §10 Gaps / assumptions | §7 |
| Appendix A–C | Schemas in Phase 0; prompts in stage modules |
