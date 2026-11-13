# Databook UI ↔ ontology parity

Status: **signed off** (2026-11-04). Contract frozen. **Slices A–F** implemented (read API, Financial history, All line items, extraction parity, HITL, source flag, Close checks).

Reference live surface: Compost Crew Latest on DiligenceIQ

### Sign-off decisions (locked)

| Decision | Choice |
| --- | --- |
| Inventory body key | **`rows`** (remote-compatible). Do not rename to `lines`. |
| Chip counts on `/lines` | **Not required** on the wire. Overview `totals` + client aggregation over `rows[].dq` / `rows[].metric` (remote behaviour). Optional local `totals` enrichment only if UI needs it later. |
| Local paths | Prefer `/cdd/databook/view` + `/cdd/databook/lines`; optional `/cdd/vdr/databook*` shims. |
| DQ id space | Shared `n` across overview `dq_cells` and `rows[].dq`. |
| Unmapped | `metric == ""` (not `null`). |
| `scale_applied` | **boolean** on the UI wire (whether scale was applied). Ontology numeric multiplier stays internal to fact rows; map at the view layer. |
| Company/file/sheet names in product code | Never.

| Endpoint | Role |
| --- | --- |
| `GET /api/v1/portfolios/{id}/cdd/vdr/databook` | Overview: `{ files, series, model, totals, reporting_currency, actual_through, dq_cells }` |
| `GET /api/v1/portfolios/{id}/cdd/vdr/databook/lines?q=` | Full extraction inventory: `{ rows: Line[] }` → **All line items** (searchable, statement-grouped, per-row scale + DQ) |

UI: VDR → Derived data → Databook header + Financial history + All line items with `#n` quality chips.

Local app today has **two** databook lineages that do not meet in the UI.

**Evidence (frozen):** Overview JSON + UI screenshots captured in-chat. `/lines` field set, types, and envelope below are frozen from the Compost Crew `…/databook/lines?q=` dump analyzed in-chat (`{"rows":[…]}`). Live URL returns `401` without a session cookie — do not re-fetch for contract. If any typed field disagrees with a retained copy of that dump, correct this section before Phase 0 tests lock.

---

## What the remote response is

It is the **file-backed DiligenceIQ Databook**, not Postgres `v_databook_fact`.

### Overview (`…/databook`) — observed

| Signal in the JSON | Meaning |
| --- | --- |
| `files[].extraction.method` structural / text / ocr | Classic statement readers |
| `totals.rows` 4603, `mapped_rows` 101, `metrics` 9 | Line inventory size + promoted series |
| `series.revenue` … `series.equity` (9 keys) | Metric × fiscal year cells for Financial history |
| Series cell: `value`, `currency`, `source`, `line_item`, `statement`, `raw`, `suspect`, `foreign`, `edited`, `original` | Promoted cell lineage (subset of a full line row) |
| `dq_cells["revenue\|2023"]` → `{ n, kind, label, detail }` | Shared DQ chip ids (`conflict` / `assumed` / `untyped`) |
| `doc_facts: 0` on most workbooks | Numbers came from grids, not prose fact extract |
| Many `empty: true` stubs / “Please see …” txt | Room placeholders correctly declined |

Screenshots match that payload: Financial history matrix (metric × FY), orange `#n+k` DQ tags, All line items with Assumption made / Sources disagree.

### Lines inventory (`…/databook/lines`) — observed wire freeze

Remote Derived data loads the overview for Financial history / totals, then a second call for the inventory table:

```text
GET /api/v1/portfolios/{id}/cdd/vdr/databook/lines?q=
```

#### Wire envelope (remote, Phase 0 source of truth)

```text
{ "rows": Line[] }
```

- Empty `q` returns the full inventory (Compost: 4,603 rows — same count as overview `totals.rows`).
- `q=` is a case-insensitive substring filter on caption **or** file path (`line_item` / `source`; `raw` / `sheet` also match in practice).
- Chip counts (`any issue` / Sources disagree / Assumption made) and mapped/unmapped totals are **not** on this response; the UI takes them from overview `totals` + client-side aggregation over `rows[].dq` / `rows[].metric` (or we may add a local `totals` enrichment — see below). Display cap (~4,000 of 4,603) is a UI/list concern.

#### UI behaviour this payload must support

| UI control | Behaviour |
| --- | --- |
| Search “filter by caption or file” | `q=` substring on `line_item` **or** `source` |
| Toggle “unmapped only” | Keep rows where `metric == ""` (unrecognised / not landed) |
| Chip `any issue: N` | Rows whose `dq[]` is non-empty |
| Chip `Sources disagree: N` | Rows with any `dq.kind == "conflict"` |
| Chip `Assumption made: N` | Rows with any `dq.kind == "assumed"` |
| Table columns | Line item (+ secondary `sheet` under caption), Statement, Period (`FY{period}`), Value |
| Row DQ chrome | `#n Assumption made` / `#n Sources disagree` / `#n … +k more` — same `n` space as overview `dq_cells` |
| Cap | “Showing 4,000 of 4,603” over overview `totals.rows` |
| Row action | “Show this line in its document” → `source` (+ `block` / `token` when present) |

Statement / sheet split (observed, not hardcoded forever):

- `statement` is often the coarse class `"schedule"` (matches UI Statement column and overview series cells).
- `sheet` carries the workbook tab: `Monthly P&L`, `Monthly BS`, `Monthly SoCF`, `Comparison`, `GL`, debt tabs (`105-Ascentium`, `110-Verdant`, `204-Wells Fargo`, …), misc (`Sheet4`, …).
- `raw` is `"{sheet} · {line_item}"` (same pattern as overview series `raw`).

#### `Line` object — all fields **Observed**

Types and examples from the Compost `/lines` dump (no company-specific keys in the contract):

| Field | Type | Role / observed values |
| --- | --- | --- |
| `key` | string | Composite id: `"{source}\|{statement}\|{line_item}\|{period}"` |
| `statement` | string | Coarse class; commonly `"schedule"` |
| `sheet` | string | Workbook tab / block label (secondary UI label) |
| `line_item` | string | Caption in Line item column |
| `period` | **integer** | Fiscal year (`2018`, `2023`, `2024`, `2025`, `2026`, …). UI renders `FY{period}` |
| `value` | float | Analysis value shown in Value column |
| `value_base` | float | Canonical/base amount after scale transforms |
| `printed` | float | Parsed printed number (editor / audit) |
| `printed_number` | float | Alias/companion parsed number |
| `printed_raw` | string | Raw token as read (e.g. `"1651358.3800000001"`) |
| `scale` | float | Effective scale factor (e.g. `1.0`) |
| `scale_declared` | float | Declared scale from sheet/header |
| `scale_source` | string | Provenance; observed `"sheet"` (also expect header/caption/map/assumed-class values in other rooms) |
| `scale_confidence` | string | e.g. `"high"` |
| `scale_applied` | **boolean** | Whether scale was applied (`true` / `false`) — **not** the numeric multiplier |
| `kind` | string | `"money"` \| `"percent"` |
| `unit` | string | `""` or `"%"` (and similar) |
| `currency` | string | `""` \| `"USD"` \| `"EUR"` (empty drives assumed/untyped) |
| `metric` | string | Ontology key when mapped (`cogs`, `gross_profit`, `ebit`, `net_income`, `ebitda`, `cash`, `total_assets`, `equity`, …); **`""` ⇒ unmapped** |
| `subtotal` | boolean | Printed subtotal / total row |
| `note` | string | Sheet / context annotation (may be empty) |
| `suspect` | boolean | Soft quality bit |
| `forecast` | boolean? | Present and `true` for forecast periods (e.g. past `actual_through` / future years like `2026+`); omit or false for actuals |
| `source` | string | Relative VDR document path |
| `raw` | string | `"{sheet} · {line_item}"` |
| `token` | string | Parse token for re-read / editor |
| `block` | string | Statement-block name within the sheet |
| `dq` | object[] | `[{ n: int, kind: "assumed"\|"conflict"\|"untyped", label: str, detail: str }]` |

Example skeleton (illustrative — field set is normative, values are not):

```json
{
  "statement": "schedule",
  "sheet": "Monthly BS",
  "line_item": "Cash",
  "period": 2023,
  "value": 2982153.56,
  "value_base": 2982153.56,
  "printed": 2982153.56,
  "printed_number": 2982153.56,
  "printed_raw": "2982153.56",
  "scale": 1.0,
  "scale_declared": 1.0,
  "scale_source": "sheet",
  "scale_confidence": "high",
  "scale_applied": true,
  "kind": "money",
  "unit": "",
  "currency": "",
  "metric": "cash",
  "subtotal": false,
  "note": "",
  "suspect": false,
  "source": "…/Compost Crew Monthly Financials 23YTD26.xlsx",
  "raw": "Monthly BS · Cash",
  "token": "",
  "block": "",
  "key": "…xlsx|schedule|Cash|2023",
  "dq": [
    {"n": 2223, "kind": "assumed", "label": "Assumption made", "detail": "…"}
  ]
}
```

`dq.kind` vocabulary (overview + lines): `conflict` → “Sources disagree”; `assumed` → “Assumption made”; `untyped` → typing / unread-adjacent failures (product guide also names Unread / Not landed as triage buckets).

**DQ join rule:** Financial history cell tint `#n+k` and All line items `#n …` share one id space. Overview `dq_cells["metric|year"]` lists cell flags; each listed `n` must appear on contributing `rows[].dq[].n` (and mapped-series flags must be reachable from line rows).

#### Local read API preference (additive, after wire parity)

Prefer path `/portfolios/{deal_id}/cdd/databook/lines` with optional shim `/cdd/vdr/databook/lines`. Keep remote-compatible body key **`rows`**. Optionally enrich:

```text
{
  rows: Line[]                 # required — same Line schema as remote
  totals?: {                   # optional local enrichment for chip headers
    rows, matched, shown,
    mapped_rows, unmapped_rows, metrics,
    issues: { any, conflict, assumed, untyped }
  }
  reporting_currency?
  actual_through?
  q? / limit? / offset?
}
```

Optional query flags for server-side filter: `unmapped=0|1`, `issue=any|conflict|assumed|untyped`, `limit`/`offset`. If omitted, UI may filter client-side the way remote appears to.
---

## What our app has

### A. File-backed Databook (still the reviewer UI)

- API: `/cdd/databook`, `/rows`, `/findings`, `/release`, Excel import/export, HITL correct/drop/vouch/…
- UI: `DealDatabook.tsx` in Deal workspace (tabs: quality, derived, findings, pack, files)
- Store: `services_databook*.py` on disk (intentional after ontology Steps 1–12)

**Missing vs remote UX**

1. No `GET …/cdd/vdr/databook` shape (`files` + `series` + `dq_cells` in one response).
2. No `GET …/cdd/vdr/databook/lines?q=` inventory returning `{ rows: Line[] }` with statement/sheet split, scale provenance, `forecast`, and per-row `dq[]` joined to overview chip ids.
3. No **Financial history** metric×year grid as the primary Databook view.
4. Databook is not the same “Derived data” panel inside VDR that the remote product shows; it is a separate workspace surface with a release-centric copy model.
5. Local `/cdd/databook/rows` dumps `ExtractedRow` (related scale_source fields, but `scale` as string and no remote `printed_*` / boolean `scale_applied` / `forecast` wire) and the UI does not offer remote filters (`q=`, unmapped only, DQ chips) or `#n` chips shared with a series grid.
6. DQ is a separate `DataQualityReview` / validation-pack flow, not `#n` chips glued onto series cells and every line row the way the screenshots show.

### B. Ontology Postgres Databook (pipeline + thin report overlay)

- Confirm → deal row → statement read → map → calc/period → resolve → rules → publish tabs from `v_databook_fact`
- CDD/FDD read published pages (YoY / thin schedules)
- Open flags live in `v_open_flags`; currency without ISO is refused at insert

**Missing vs remote UX**

1. Ontology never feeds `DealDatabook` or any Financial history UI.
2. Reviewers still judge the file-backed store; reports (when ontology has pages) can show a **different** number set than the Databook tab.
3. No reviewer affordances on ontology candidates (accept conflict, remap, vouch) writing `mapping_decision` / resolver status from the Databook screen.
4. Compost-style richness (thousands of rows, 9-metric series, dense DQ) only appears if the file-backed path ran; ontology coverage on Baytown-class rooms is still sparse (e.g. revenue/opex only) until readers + mapper cover the same statement grids.

### C. Product gap that is data quality, not missing chrome

Remote `dq_cells` already show the hard problems any plan must keep solving:

- Unit / scale clashes (0.08 vs 4.16 vs 7.5 “revenue” across ESG, TAM, and model sheets)
- Beginning vs ending cash treated as conflict
- Unsigned / empty currency → “Assumption made” / `untyped` floods
- Investor workbook vs monthly financials both mapping to EBITDA / gross profit

Ontology constraints (`currency_needs_code`, authority order, block rules) are the right long-term fix; the UI must surface those flags the way DiligenceIQ already surfaces `dq_cells`.

---

## Goal

One Databook experience for reviewers:

1. **Read** selected facts + open flags from Postgres (`/view` series + `/lines` `{ rows }` inventory + shared DQ ids).
2. **Decide** in UI → write ontology review rows (`mapping_decision`, resolver choice, exclude).
3. **Publish** unchanged (tabs from `v_databook_fact`).
4. File-backed `services_databook*.py` becomes a bridge or retires after parity; do not hardcode company/file/sheet names.

Do **not** rebuild the 109-slide Baytown CDD. Page shape stays generic published schedules.

---

## Implementation plan (build order)

Ontology pipeline (Steps 1–12 in `ontology-databook-implementation.md`) stays the write path. This plan is the **read + review UI** on top of Postgres. Do not extend `services_databook*.py` for new metrics.

### PR / delivery slices

| Slice | Phases | Approx | Outcome |
| --- | --- | --- | --- |
| **A** | 0 + 1 | 3–4 days | Contract tests + ontology-backed `/view` + `/lines` |
| **B** | 2 | 2 days | Financial history grid in `DealDatabook` |
| **C** | 3 | 2 days | All line items + filters + DQ chips |
| **D** | 6 (parallel) | ongoing | Reader/mapper fill so grids are dense |
| **E** | 4 | 3–4 days | HITL writes into ontology |
| **F** | 5 + 7 | 3–4 days | Flag flip, retire bridge, Close UI checks |

---

### Phase 0 — Contract fixtures (½ day) — start here

Wire freeze is already documented above. Phase 0 = lock it in tests (no company-specific fields).

**Add**

| File | Role |
| --- | --- |
| `apps/api/src/agetic_cdd_api/services_databook_view_models.py` | Pydantic: `DatabookViewResponse`, `DatabookLinesResponse`, `DatabookLineRow`, `DatabookDqIssue`, series cell |
| `apps/api/tests/fixtures/databook_view_contract.json` | Minimal overview shape (`files`, `series`, `totals`, `dq_cells`, `reporting_currency`, `actual_through`) |
| `apps/api/tests/fixtures/databook_lines_contract.json` | Small `{ rows: [...] }` covering money + percent, mapped + `metric:""`, `forecast:true`, non-empty `dq`, bool `scale_applied`, int `period` |
| `apps/api/tests/test_databook_view_contract.py` | Schema round-trip + invariants |

**Invariants to assert**

1. Overview parses to `DatabookViewResponse`; lines to `{ rows: DatabookLineRow[] }`.
2. `period` is `int`; `scale_applied` is `bool`; unmapped `metric == ""`.
3. Every `dq_cells[*][].n` appears on ≥1 `rows[].dq[].n` in the paired fixture.
4. `q=` filter helper: case-insensitive match on `line_item` **or** `source` (also `raw`/`sheet`); empty `q` keeps all.

**Ontology mapping (view layer)**

| UI field | Source |
| --- | --- |
| `series` | `v_databook_fact` SELECTED/DERIVED, pivot concept × fiscal year |
| `dq_cells` / row `dq` conflict | non-SELECTED candidates for same figure key; shared flag `n` |
| `dq_cells` / row `dq` assumed / untyped | `v_open_flags` + held currency/period/scale failures |
| `files` | `document` register + reader stats |
| `rows[]` | candidate + SELECTED + HELD (+ mapping queue) → Line shape |
| `rows[].forecast` | period past confirmed `actual_through` / forecast basis |
| `actual_through` | confirmed `latest_actual_month` / derived periods |
| Wire `scale_applied: bool` | derive from whether a scale transform ran; keep ontology numeric scale internal |

Done when contract tests pass on fixtures alone (no Postgres required for Phase 0).

---

### Phase 1 — Read API from ontology (2–3 days)

**Add / touch**

| File | Role |
| --- | --- |
| `apps/api/src/agetic_cdd_api/services_databook_view.py` | Build view + lines from Postgres when `AGETIC_CDD_DATABOOK_DATABASE_URL` set |
| `apps/api/src/agetic_cdd_api/routers_dealroom.py` | `GET …/cdd/databook/view`, `GET …/cdd/databook/lines`; optional `…/cdd/vdr/databook*` shims |
| `apps/api/src/agetic_cdd_api/services_fact_repository.py` | Read helpers only (no new insert paths) |
| `apps/api/src/agetic_cdd_api/services_publisher.py` / `services_published_pages.py` | Reuse published / SELECTED reads if already there |
| `apps/api/tests/test_databook_view.py` | Integration against databook Postgres fixture |

**Behaviour**

1. `/view` → `{ files, series, model?, totals, reporting_currency, actual_through, dq_cells }`.
2. `/lines?q=` → `{ rows }` only (no required `totals`); support optional `unmapped`, `issue`, `limit`, `offset` for later UI.
3. Postgres unset or deal unpublished → empty `series`/`rows` + explicit `building` / unpublished state. **Never** silent fall back to file-backed promote.
4. Assign stable integer `n` for open flags so overview cells and line rows share ids.

**Reuse (do not reimplement):** `services_ontology.py`, `services_fact_repository.py`, `services_resolver.py`, `services_rule_checker.py`, `services_document_register.py`, `services_deal_profile.py`.

Done when a workflow/statement fixture returns non-empty `series` **and** `rows` without calling file-backed promote.

---

### Phase 2 — Financial history UI (2 days)

**Touch**

| File | Role |
| --- | --- |
| `apps/web/src/lib/api.ts` | `databookViewRequest(dealId)` |
| `apps/web/src/lib/config.ts` | endpoints for `/cdd/databook/view` |
| `apps/web/src/components/deal/DealDatabook.tsx` | Default / top panel: metric × FY grid |
| New small presentational pieces under `components/deal/` if needed | `FinancialHistoryGrid`, cell tooltip/drawer shell |

**Behaviour**

1. Metric rows × period columns from `series`.
2. Cell chrome: value; currency when present; italic when forecast / past `actual_through`; tint + `#n` / `#n+k` from `dq_cells`; tooltip = source + line_item + fact id.
3. Empty cell tooltip: “No document read so far states this figure…” (remote copy).
4. Click cell → drawer stub (candidates / flags / show in document) — full HITL in Phase 4.
5. Export/Import Excel stays on existing file-backed paths for now.

Done when local grid matches remote layout for a fixture with ≥3 metrics × ≥3 years.

---

### Phase 3 — All line items + DQ chips (2 days)

**Touch**

| File | Role |
| --- | --- |
| `apps/web/src/lib/api.ts` | `databookLinesRequest(dealId, { q, unmapped, issue, limit, offset })` |
| `apps/web/src/components/deal/DealDatabook.tsx` | Replace/augment file-backed rows table with `/lines` `{ rows }` |
| Bridge (API) | Map legacy `GET …/databook/rows` → Line shape only if dual-mode still needs it |

**Behaviour**

1. Filters: `q` (caption or file), unmapped only (`metric == ""`), chips any / conflict / assumed (client counts over loaded `rows`, header totals from overview).
2. Columns: line_item + secondary `sheet`, statement, `FY{period}`, value; `#n` (+k more) from `dq[]`.
3. Italic when `forecast === true`.
4. Cap ~4000 via limit/offset or existing pagination; copy reconciles shown vs overview `totals.rows`.
5. Row click → show in document via `source` + `block`/`token`.

Done when chip membership and `q=` match Phase 0 filter tests for the fixture.

---

### Phase 4 — HITL writes into ontology (3–4 days) — **Slice E landed**

Route existing DealDatabook actions to ontology writers (dual-write to file-backed only while flag=`dual`):

| UI action | Ontology write | Existing hooks to retarget |
| --- | --- | --- |
| Accept conflict | resolver SELECTED + reason on others | `…/conflicts/accept`, `services_resolver.py` |
| Remap caption → concept | `mapping_decision` + rematerialize | `…/rows/{id}/remap`, `services_mapper.py` |
| Drop / exclude | not publishable + reason | `…/drop`, `…/exclude` |
| Vouch / confirm assumption | explicit reviewer status (no silent ISO invent) | `…/vouch`, `…/confirm` |
| Reread document | statement reader for one `document_id` | `…/reread`, `services_statement_reader.py` |

After each decision: refresh open flags for affected keys; optional auto-publish if profile confirmed.

Done when accepting a conflict changes SELECTED in `v_databook_fact` and the next CDD YoY / schedule page cites that fact id.

---

### Phase 5 — Feature flag + retire file-backed bridge (2–3 days) — **Slice F landed**

1. Setting / flag: `databook_ui_source = ontology | file | dual` (default `ontology`). **Done.**
2. `dual`: `/view`+`/lines` prefer ontology; HITL may still mirror file store.
3. Keep `services_databook*.py` on disk until ontology Close (five rooms) passes; then stop calling promote/summary for the UI series path.

Done when `DealDatabook` with `ontology` never calls file-backed `get_databook_summary` for series.

---

### Phase 6 — Extraction parity (parallel with B/C/E) — **Slice D landed**

UI chrome is empty without facts. Continue ontology Steps 6–10 work generically:

1. Monthly P&L / BS → cash, equity, total_assets, cogs, ebit, net_income (concepts exist). **Done:** expanded synonyms; store series-mapped COMPARATIVE source totals; `/view` fills series gaps from those.
2. Decline non-statement sheets (TAM, ESG “Revenue”, cap tables) via document type / section rules. **Done:** sheet-title + doc-type gates in the statement reader.
3. Inherit deal `reporting_currency` onto grids missing ISO — flag as assumed, never silent empty. **Done:** `currency_source=assumed` on mapping; DQ chip on `/view` + `/lines`.
4. Authority: audited/monthly statements beat investor model for historical actuals; model for forecast. **Done:** `basis_for_document` + resolver family `FINANCIAL_PLAN` / `FINANCIAL_ACTUAL_MONTHLY`.

Done when a Compost-like fixture yields ~nine series keys for actual years with fewer bogus cross-doc conflicts.

---

### Phase 7 — Close UI alignment — **Slice F landed**

Reuse ontology Close checklist; add UI checks:

- Empty Financial history cells explain “no sourced fact”.
- Every tinted cell has a resolvable `n`.
- Optional: Excel export/import round-trips ontology fact ids (not orphaned file row ids).

---

## What to replace vs update vs leave

| Piece | Action |
| --- | --- |
| `GET /cdd/vdr/databook` | Optional shim; prefer `/cdd/databook/view` |
| `GET /cdd/vdr/databook/lines?q=` | Optional shim; prefer `/cdd/databook/lines` → `{ rows }` |
| `DealDatabook.tsx` | Update: Financial history + All line items |
| Local `/cdd/databook/rows` | Bridge → Line shape during dual; do not invent a third model |
| `services_databook*.py` | Bridge then retire; no new metrics here |
| Ontology publisher / published pages | Keep; reports already consume |
| DQ labels | Assumption made / Sources disagree / Unread / Not landed from `v_open_flags` + `dq[]` |
| CDD/FDD builders | No Baytown clone; richer tabs as Phase 6 fills them |
| Hardcoded Compost/Baytown paths | Never |

---

## Suggested order of work

1. **Slice A** — Phase 0 fixtures + Phase 1 read API (unblocks UI).  
2. **Slice B** — Phase 2 Financial history.  
3. **Slice C** — Phase 3 All line items.  
4. **Slice D** — Phase 6 in parallel (dense series + rows).  
5. **Slice E** — Phase 4 HITL.  
6. **Slice F** — Phase 5 flag + Phase 7 Close.

---

## Out of scope for this plan

- Matching `Baytown_Travel_Centre_CDD.pptx` slide count or narrative.
- Redeploy / commit (ask explicitly).
- Changing SQLite app DB or merging Postgres into it.
- Re-fetching the live `/lines` URL; contract is frozen above.
