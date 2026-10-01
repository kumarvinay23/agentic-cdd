# Databook — Design & Implementation Plan

> **Status:** Design locked; **Phase 0–3 implemented** (extract/conflicts, HITL, statement-block reconcile, Findings trust ledger, uploaded-files triage). Phase 4 (agents/reports reading promoted metrics) still deferred.  
> **Repo:** `agetic-cdd` (not `agetic-cdd-guided`).  
> **Requirements:** `CONTEXT.md` § CDD Databook + [`diligenceiq-cdd-databook-user-guide.txt`](../reference/diligenceiq-cdd-databook-user-guide.txt)  
> **Verification contract:** [`diligenceiq-data-quality-test2-fixture.json`](../reference/diligenceiq-data-quality-test2-fixture.json)

---

## 1. Problem & product goal

Agents and reports today consume **OCR/heuristic numbers** from CDL excerpts and agent specs. DiligenceIQ’s Databook exists so that **only proven or explicitly reviewed numbers** become the deal’s financial history.

**Chain of evidence (non-negotiable):**

```
source document → extracted row → mapped metric → arithmetic / series check
  → reviewer decision → promoted databook metric → agents & reports
```

**Working principle:** zero trust. If a row cannot be proven, it stays **visible but held out** until Correct / Drop / Vouch / Re-read.

**Done means:** material rows tie (or judgement is recorded); another teammate can see *why* each material number was accepted.

---

## 2. What we will *not* copy from live DiligenceIQ

| Live DIQ behaviour | Our stance |
|---|---|
| Flat ~22k issue list | **Triage + materiality** first (trial feedback) |
| Auto-`chosen` can pick Units Sold as Revenue | **Metric-identity gates**; auto-choice never silent-final |
| Duplicate conflict rows across extract passes | Dedupe by `(metric, fiscal_year, value set, sources)` |
| No dedicated review screen | Ship a **Databook** nav surface (enable Financial DD / replace placeholder) |
| Disagreement panel cannot overwrite | Same discipline: resolve via Correct / Drop / Vouch / governing source, not silent panel override |

---

## 3. Architecture overview

```
┌─────────────┐   extract/tables    ┌──────────────────┐
│ VDR / CDL   │ ──────────────────► │ Databook extract │
│ library/*.json│                   │ (rows + blocks)  │
└─────────────┘                     └────────┬─────────┘
                                             │
                    map + check + conflict   ▼
                                    ┌──────────────────┐
                                    │ Issue engine     │
                                    │ flags + DQ items │
                                    └────────┬─────────┘
                                             │
                    Correct/Drop/Vouch       ▼
                                    ┌──────────────────┐
                                    │ Promotion store  │
                                    │ (canonical FY×M) │
                                    └────────┬─────────┘
                          agents/reports read │
                                             ▼
                                    historical_performance,
                                    ops dashboard, CDD deck, …
```

**Storage recommendation (MVP):** file-backed under `data/deals/{deal_id}/databook/` (matches VDR/CDL/agent docs pattern). Add SQL later only if multi-user concurrency / query load demands it.

```
databook/
  extract.json          # all candidate rows (source-linked)
  blocks.json           # statement blocks × period check results
  issues.json           # flags + data-quality items (deduped)
  decisions.jsonl       # append-only audit (correct/drop/vouch/re-read)
  promoted.json         # canonical metric × fiscal_year (only trusted)
  meta.json             # last Rescan/Deep timestamps, deal params snapshot
```

---

## 4. Domain model

### 4.1 Extracted row

| Field | Notes |
|---|---|
| `row_id` | Stable hash of `(doc_id, page/sheet, caption, period, raw_value)` |
| `doc_id` / `source_name` | VDR library stem / filename |
| `caption` | Printed label |
| `metric_key` | Mapped canonical key or `null` (unmapped) |
| `metric_family` | e.g. `revenue`, `units`, `retention`, `growth` — **gates conflicts** |
| `fiscal_year` / `period` | Missing ≠ zero |
| `value` | Numeric |
| `unit` / `currency` / `scale` | Explicit or assumed (+ assumption flag) |
| `block_id` | Statement block membership |
| `status` | `candidate` \| `held_out` \| `dropped` \| `promoted` \| `vouched` |

### 4.2 Statement block

One check = **one block × one period**.

| Field | Notes |
|---|---|
| `block_id` | Doc + table region |
| `period` | FY / quarter |
| `line_row_ids` | Constituent rows |
| `printed_subtotal` | From source |
| `computed_sum` | Sum of lines |
| `ties` | bool within tolerance |
| `outcome` | `pass` \| `fail` \| `no_table` (silence ≠ pass) |

**Rule:** failed block → constituent rows **held out** (never silent promote).

### 4.3 Issue / flag

Triage order (product):

1. Assumption made  
2. Sources disagree  
3. Unread  
4. Not landed  

Plus check outcomes: Failed its check, Unmapped, No financial table found.

Map to DIQ `data-quality` kinds for API parity:

| Flag / event | `kind` (API) |
|---|---|
| Series outlier / ratio-as-amount | `dropped` |
| Same metric+year, competing values | `conflict` |
| (Later) unread / not landed / assumption | extend `kind` or `flag` field |

### 4.4 Decision (audit)

| Action | Meaning | Effect |
|---|---|---|
| **Correct** | Machine misread | Patch value/metric/unit + reason → re-check → may promote |
| **Drop** | Not a figure | Remove from candidates |
| **Vouch** | Read OK; release on human authority | Promote despite failed check (reason required) |
| **Re-read** | Re-extract one file | Deep for that doc only |

Correcting ≠ vouching. Never vouch to clear a list.

### 4.5 Promoted metric

Canonical `(metric_key, fiscal_year)` → value + provenance (`row_id`, sources, decision_id).  
**Agents/reports must prefer this store** over raw agent `pl_lines` when present.

---

## 5. Pipeline stages

### Stage A — Extract (from CDL)

**Reuse:** `services_extract.py`, library `tables` / `text`, `deep_dive_financial._parse_pnl_table` as seed heuristics.

**Produce:** rows + blocks for financial-classified docs only (CDL route). Non-financial → Unread / no_table finding for that file (silence logged).

**Out of scope MVP:** new OCR. Scanned PDFs stay weak; surface Unread / Not landed honestly.

### Stage B — Map

- Caption → `metric_key` + `metric_family` via dictionary + light LLM assist for unknowns.
- **Family gates (critical):** `Units Sold`, NRR/GRR/Churn, YoY Growth **must not** enter `revenue` family conflicts.
- Unit/currency/scale from deal params or caption; else flag **Assumption made**.

### Stage C — Check

1. **Block reconcile:** lines vs printed subtotal (tolerance e.g. 0.5% or 1 unit).  
2. **Series sanity:** drop values orders of magnitude off series centre (fixture reason string).  
3. **Conflict resolve (proposal only):**
   - Group by `(metric_key, fiscal_year)` within same family only.
   - Rank candidates (DIQ-like rule): stated_by → source metric coverage → source fact share → caption plainness → centrality.
   - Emit `conflict` with `chosen` = **proposal**; status remains held_out until review or auto-promote only when **single candidate + block ties + no assumption**.

### Stage D — Promote

| Condition | Result |
|---|---|
| Unique value, block ties, mapped, no assumption | Auto-promote |
| Conflict / fail / assumption / unmapped | Hold out + issue |
| After Correct/Vouch | Promote with audit |

### Stage E — Data-quality projection

`GET …/cdd/data-quality` → `{ items, summary }` matching fixture shape (deduped).  
UI maps `conflict` → Sources disagree; series `dropped` → Not landed / noise triage.

---

## 6. API design

Host on existing CDD namespace (`routers_dealroom.py`):

| Method | Path | Role |
|---|---|---|
| `GET` | `/portfolios/{id}/cdd/databook` | Summary: promoted counts, held-out, flags by kind |
| `GET` | `/portfolios/{id}/cdd/databook/rows` | Derived data list (filters: status, flag, metric, doc) |
| `GET` | `/portfolios/{id}/cdd/databook/findings` | Per-file trust ledger (checks pass/fail/held-out) |
| `GET` | `/portfolios/{id}/cdd/data-quality` | DIQ-compatible `{items,summary}` |
| `POST` | `/portfolios/{id}/cdd/databook/rows/{row_id}/correct` | body: value?, metric?, unit?, reason |
| `POST` | `…/drop` | reason |
| `POST` | `…/vouch` | reason (required) |
| `POST` | `/portfolios/{id}/cdd/databook/rescan` | Cached text; remap/check |
| `POST` | `…/reread` | `{ doc_id }` deep one file |
| `POST` | `…/deep` | Re-extract all originals |
| `GET` | `…/databook/promoted` | Canonical series for agents |

Permissions: same deal membership as other `/cdd/*` routes.

---

## 7. UI design

**Nav:** enable **Financial DD** (or rename **Databook**) in `DealWorkspace` — primary home.

Three surfaces (guide parity), one composition:

| Tab | Content |
|---|---|
| **Uploaded files** | Queue: flags per file; open source; trigger Re-read |
| **Derived data** | Promoted summary + held-out worklist; Correct / Drop / Vouch |
| **Findings** | Trust ledger per doc (`N/N checks failed`, held-out count); silence ≠ pass |

**Triage UX (avoid overload):**

- Default worklist = **material** issues only (Revenue/EBITDA/cash + conflicts + failed blocks).
- Secondary “All line items” behind filter.
- Conflict detail: candidates table (value, caption, sources, stated_by) + **proposed** chosen + “Accept proposal” / “Pick other” / Drop noise captions.

**VDR link:** badge “N databook issues” → Databook Uploaded files (like DIQ VDR adjacency).

**Do not** put Databook HITL into agent Document workspace (wrong unit of work).

---

## 8. Agent & report integration

| Consumer | Change |
|---|---|
| `historical_performance` / financial agents | Prefer `promoted.json` for FY metrics; cite databook provenance |
| `report_ops_dashboard.harvest_metric_facts` | Merge promoted facts first; demote raw agent conflicts when databook resolved |
| CDD deck / IC memo | Pull headline revenue/growth from promoted store |
| Phase orchestration | Optional: after library reingest, enqueue databook Rescan (not block whole pipeline) |

---

## 9. Phased implementation

### Phase 0 — Foundations (½–1 week)

- [ ] `databook/` FS layout + pydantic models  
- [ ] Deal params stub: currency, scale, FY convention  
- [ ] Golden tests from Test2 fixture (parse/serialize `conflict`/`dropped`)  
- [ ] Empty `GET …/cdd/data-quality` + `GET …/cdd/databook`  

### Phase 1 — MVP extract → issues → UI read path (1.5–2 weeks)

- [ ] Table → rows from CDL financial docs (seed with P&L parser)  
- [ ] Metric map + **family gates** (revenue vs units vs retention)  
- [ ] Series drop + across/within-doc conflict detection  
- [ ] `data-quality` populated (deduped); verify against fixture patterns  
- [ ] UI: Databook tabs **read-only** (Derived + Findings summary)  
- [ ] Acceptance: Test2-like pack shows Exec Summary vs Commercial DD Revenue conflicts; Units Sold **not** chosen as Revenue  

### Phase 2 — HITL decisions (1–1.5 weeks)

- [ ] Correct / Drop / Vouch APIs + `decisions.jsonl`  
- [ ] Promotion rules + `promoted.json`  
- [ ] UI actions with mandatory reason  
- [ ] Re-read single file; Rescan remap  

### Phase 3 — Statement-block reconcile (1.5–2 weeks)

- [x] Detect blocks + printed subtotals  
- [x] Fail → hold-out constituents  
- [x] Findings trust ledger (`checks failed`, held-out counts)  
- [x] Uploaded files triage order (assumption → disagree → unread → not landed)  

### Phase 4 — Downstream + polish (1 week)

- [x] Agents/reports read promoted metrics  
- [x] Deep / Refresh semantics  
- [x] Materiality filters; export CSV of promoted series  
- [x] Ops dashboard uses databook before agent WARNs  

**Total MVP useful (Phases 0–2):** ~3–4.5 weeks. Full guide parity through Phase 3–4: ~6–8 weeks.

---

## 10. Verification plan

| Check | Source |
|---|---|
| Response shape `{items, summary}` | Fixture meta |
| Dropped ratio-as-amount reason | Fixture representative |
| Across-doc Revenue conflict candidates | Fixture / live Test2 |
| Within-doc share/growth multi-value | Fixture |
| **Anti-goal:** Units Sold / NRR never win Revenue | Fixture `danger: true` case |
| Deduped needs_review (no 3× duplicate passes) | Compare to live 77 inflation |
| Missing period ≠ 0 in UI/API | Guide language |
| Vouch requires reason; Correct ≠ Vouch | Unit tests + UI |

Manual: run against uploaded Test2 VDR on staging; compare issue set to live DIQ qualitatively (same disagreements, better auto-choice).

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Extract quality without OCR | Honest Unread/Not landed; clean-schedule upload tips |
| Metric map pollution | Family gates + caption plainness; human review on conflicts |
| Scope creep to full FDD suite | Databook = trust layer; Financial DD agents stay separate |
| Reviewer overload | Materiality default; Findings-first file triage |
| Agents ignore promoted store | Explicit reader helper `load_promoted_metrics(deal)` wired into financial agents |

---

## 12. Suggested first code slices (when implementation starts)

1. `services_databook_models.py` + FS IO  
2. `services_databook_extract.py` (CDL tables → rows)  
3. `services_databook_resolve.py` (map, series drop, conflict, family gates)  
4. Routes on `routers_dealroom.py`  
5. `DealDatabook.tsx` + enable nav item  
6. Wire Correct/Drop/Vouch  
7. Block reconcile + Findings  
8. `load_promoted_metrics` into deep-dive financial / ops dashboard  

---

## 13. Kickoff decisions (locked)

| Decision | Choice |
|---|---|
| Nav label | **Databook** (replaces disabled Financial DD) |
| Auto-promote | Only **unique + block ties + mapped** (no assumption); conflict auto-`chosen` is proposal only |
| Tolerances | Block tie **0.5%** (or 1 unit); series magnitude drop at **100×** below centre |
| Metric mapping | **Dictionary-first**; optional LLM behind `DATABOOK_LLM_MAP=1` (off by default) |

Implementation started against these choices (Phase 0 → Phase 1).
