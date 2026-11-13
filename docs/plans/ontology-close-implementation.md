# Ontology Close

Status: **Slices 1–7 implemented**. Steps 1–12 in `ontology-databook-implementation.md` are in the API. Databook UI slices A–F in `databook-ui-ontology-parity.md` are in. This plan is only the Close: five fixture rooms through the same pipeline, then stop the file-backed series path.

The reference check is `4_Reference_Code/test_pipeline.py` in `DiligenceIQ_Databook_For_Engineering_v1.zip`. It reads `example_run.json` per room and prints `ALL INVARIANTS HOLD`. `services_case_run.py` already writes that file for one workbook and one hardcoded deal id. `debt_tie` and `schedule_vs_book` are empty lists. Those two gaps are in scope here.

## Rules for every slice

- Stop at the end of a slice until its check passes. Do not start the next slice on a failing check.
- Do not rewrite `read_statement_grid`, `run_calculations`, `derive_periods`, `run_identities`, `ebitda_bridge`, `compare_with_source`, or `check_fact_contract`.
- The app database stays SQLite. The databook stays PostgreSQL 16 on `AGETIC_CDD_DATABOOK_DATABASE_URL`. A missing URL skips the Postgres assertions and still runs the in-memory invariant file.
- No company name, file name, sheet name, or deal figure in product code, prompts, configuration, or the ontology JSON. Fixture files may hold answer-key figures. Fixture directory names are `room_01` … `room_05`.
- `services_databook*.py` stays on disk until Slice 6 passes. Do not delete it in an earlier slice.
- A genuine bridge gap is a finding when `v_open_flags` records it. It is a failure only when the gap is silent.
- Do not regenerate a deck to “try” a slice. Report scores are Slice 5.

## What “done” means for one room

`example_run.json` must satisfy the six reference invariants:

| Invariant | Pass |
| --- | --- |
| Statements found | The room’s expected set is present (`PL`+`BS`+`CF` for a full statements room; the schedules that room is built to publish for a lease, debt, or site room) |
| R-SRC-01 | Every line inside a source subtotal is mapped |
| R-SRC-02/03 | Derived figures equal the source subtotals, ratios, and annual columns, or `explained_by` is set |
| Identities | `rules[].passed` is true, except a block that is also an open flag and is absent from the publish set |
| Contract | `check_fact_contract` returns no errors |
| Unmapped lines | No `LINE` row lacks a concept. A guess sits on `review_queue` |

Plus the Close checklist below, applied to all five rooms together.

## The five rooms

One code path. The rooms differ. Their names do not appear outside `apps/api/tests/fixtures/close/`.

| Room | What it is | How it differs |
| --- | --- | --- |
| `room_01` | Monthly Excel P&L, balance sheet, and cash flow | USD, fiscal year end December, actuals through a full year |
| `room_02` | Same statements, other currency and a non-December fiscal year end | Second ISO code, FYE not December |
| `room_03` | Workbook plus one non-statement sheet (market or cap table) and one image-only PDF | File mix. The non-statement sheet and the image PDF add no statement facts. The PDF register row says why it was skipped |
| `room_04` | Lease or rent schedule, not a full P&L | Publishes a rent page only. No revenue page is added |
| `room_05` | Debt agreement or borrowings schedule | Publishes a debt page. A bridge that does not tie is an open flag |

Sector pack and deal type live on the confirmed profile JSON next to each room, not in a branch in product code.

---

## Slice 1 — Runner emits the reference file for any room

Landed. `run_case` takes `deal_id` and optional `latest_actual`. A databook load deletes only that deal. `tests/test_close_invariants.py` applies the six reference checks in-process. The temporary P&L workbook fails “every statement found” (no balance sheet or cash flow) and passes the other five. Full statements are Slice 2.

**Touch**

| File | Role |
| --- | --- |
| `apps/api/src/agetic_cdd_api/services_case_run.py` | Take `deal_id` and profile. Stop hardcoding `step12-case` and `d-step12` |
| `apps/api/tests/test_close_invariants.py` | Load `example_run.json` and apply the six invariants from the reference script |

**Behaviour**

1. `run_case(workbook, *, deal_id, currency, fye, latest_actual, out_dir, database_url="")` writes `example_run.json`.
2. The Postgres load, when a URL is set, uses that `deal_id` and deletes only that deal’s rows.
3. The pytest copies the six invariant lambdas. It does not shell out to the zip.

Done when `room_01` (Slice 2 may land the file in the same change if Slice 1 has nothing to read) prints a pass or a named invariant failure, and a second call with another `deal_id` does not delete the first deal.

---

## Slice 2 — Five fixture rooms

Landed. `apps/api/tests/fixtures/close/room_01` … `room_05`, rebuilt by `build_rooms.py`. `test_close_invariants.py` runs each profile. All five pass the statement check for that room and the other five reference invariants. The rent sheet stores revenue, gross profit, and rent as separate lines. The borrowings sheet balances assets to equity plus short-term debt.

**Add**

`apps/api/tests/fixtures/close/room_01` … `room_05`. Each directory holds the files plus `profile.json`:

```json
{
  "reporting_currency": "USD",
  "fiscal_year_end": "12-31",
  "latest_actual_month": "2025-12-31",
  "sector_pack": "",
  "deal_type": "statements",
  "expected_statements": ["PL", "BS", "CF"]
}
```

`deal_type` is `statements`, `lease`, or `debt`. `expected_statements` is what Slice 1 checks instead of always requiring PL, BS, and CF.

Build the workbooks in the test fixture generator or check them in as xlsx/pdf. Do not point product code at a company folder or at `uk_mgmt_synthetic.xlsx` by that name. A generator may start from the pack’s synthetic grid and rewrite captions to ontology synonyms already in the bundle.

Done when `test_close_invariants.py` runs all five profiles and each room passes its expected-statement invariant and the other five reference invariants.

---

## Slice 3 — Ties, flags, and the four refusals

Landed. `cash_tie`, `debt_tie`, and `schedule_vs_book` are filled from the rule checker. A room with no facility schedule is `UNVERIFIABLE`. A balance-sheet, cash, EBITDA, or debt gap is an open flag, and a block failure stays out of `publish_set`. The four insert refusals run again in `test_close_invariants.py`, and against Postgres when `AGETIC_CDD_DATABOOK_DATABASE_URL` is set.

**Touch**

| File | Role |
| --- | --- |
| `services_case_run.py` | Fill `debt_tie` and cash-tie rows from the rule checker. Leave `schedule_vs_book` as `UNVERIFIABLE` only when the room has no facility schedule |
| `services_rule_checker.py` | Persist the same failures to `v_open_flags` when a URL is set |
| `tests/test_close_invariants.py` | Assert the Close tie rules |
| Existing Step 1 repository tests | Keep the four insert refusals. Re-run them in this slice against the databook URL when it is set |

**Checks on every room that has the statements**

- A 7-month period labelled FY is refused. A second `SELECTED` or `DERIVED` row for the same figure is refused. A currency amount with no ISO code is refused. A fact whose concept is not in the ontology is refused.
- The balance sheet identities pass, or the failure is an open flag and that tab is absent from the publish set.
- In every month where both exist, cash-flow cash equals balance-sheet cash, or the difference is an open flag.
- An EBITDA or debt bridge that does not tie is present in `v_open_flags` (and in `ebitda_bridge` / `debt_tie` on the example file). A silent gap fails the slice.

Done when all five rooms satisfy those checks. `room_04` and `room_05` are not required to have a balancing P&L.

---

## Slice 4 — Queue, completeness, and agent figures

Landed. `review_queue_ratio` is queued `LINE` rows over extracted `LINE` rows, and 0 when a room has no lines. `publish` returns `completeness` for every tab, including GOV-05. A tab with no required concepts scores 1. A chosen fact whose source method starts with `AGENT`, or whose document type is `AGENT_OUTPUT`, is listed on `agent_chosen` and, when the databook URL is set, excluded from `v_databook_fact` by `agent_chosen_in_view`.

**Touch**

| File | Role |
| --- | --- |
| `services_publisher.py` | Add `completeness` on each published tab: sourced required concepts / required concepts. A tab with no required concepts scores 1 |
| `services_case_run.py` | Write `review_queue_ratio` = queued lines / extracted `LINE` rows |
| `tests/test_close_invariants.py` | Assert the ratio and the score |

**Checks**

- `review_queue_ratio` ≤ 0.15 on every room. A room with no lines scores 0.
- Every published tab, including GOV-05, has a completeness number.
- No `SELECTED` or `DERIVED` fact has an agent extraction method or an agent document type. Agent outputs stay citations of fact ids, not chosen values.

Done when the five example files and, when a URL is set, `v_databook_fact` meet those three checks.

---

## Slice 5 — Identity is stable when the room is shaken

Landed. `tests/test_close_stability.py` re-reads `room_01` after a rename, a sheet reorder, and an image-only PDF. The concept and source cell of each selected fact stay the same, and a fact id that appears in both reads still points at that pair. The series cell is labeled with the confirmed reporting currency. The stored amount and stored currency are not rewritten, and no exchange rate is applied.

**Touch**

`tests/test_close_stability.py` only, unless display conversion is missing. If the view layer has no conversion, add it in `services_databook_view.py`: the stored `value` and `currency` stay the source amount and source code; the series cell may show the confirmed reporting currency. Do not overwrite the fact row.

**Checks, on `room_01`**

1. Read the room. Record `fact_id → (concept_id, source cell)` for every selected fact.
2. Rename the files, reorder the sheets, and add an image-only PDF. Read again.
3. The concept and the source cell for each surviving fact id are unchanged.
4. Change the confirmed reporting currency. The stored amount and stored currency are unchanged. The displayed amount uses the confirmed currency.

Done when those four assertions pass without a new company, file, or sheet name in product code.

---

## Slice 6 — CI name ban, then stop the series bridge

Landed. `tests/test_close_names.py` scans the API, the web app, the prompt book, and the ontology JSON. The denylist is in that test. Ontology mode of `view_for_deal` and `lines_for_deal` returns before the file store. File mode and an empty dual read still use it. `services_databook*.py` stays on disk.

**Touch**

| File | Role |
| --- | --- |
| `apps/api/tests/test_close_names.py` | Scan `apps/api/src`, `apps/web/src`, prompt files, and `DiligenceIQ_Databook_Ontology_v1.json` |
| `services_databook_source.py` | After this slice’s name check is green, `file` remains a flag value but the series path used by `DealDatabook` in the default `ontology` mode stays off `get_databook_summary` (already true). Remove any remaining series call that still promotes file rows when the flag is `ontology` |

The scanner fails on a denylist of company names, data-room file names, sheet titles, and deal figures. The denylist lives in the test, not in the ontology. Paths under `tests/fixtures`, `tests/foundation_inputs.py`, and generated decks are out of the scan.

Do not delete `services_databook*.py`. Quality, findings, and the validation pack may still read the file store when those tabs are opened.

Done when the scanner passes, and a test that the ontology series entry point does not call `get_databook_summary`.

---

## Slice 7 — Agent and report scores

Landed. `tests/test_close_scores.py` reads `tests/fixtures/close/scores/room_01.json` through `room_05.json` and checks them against a fresh room run. The agents scored are the ones `run_case` runs. CDD and FDD are the published schedule pages, scored by the v4 report checker. A live model call runs only when `AGETIC_CDD_CLOSE_SCORES=1`. A missing model key skips that call, and the skip fails the test only when the flag is set.

Run only after Slices 1–6 pass.

On each of the five rooms, every agent that the pipeline runs scores 8 or more on quality, coverage, and IC readiness. The report checker scores the rendered CDD and FDD at 8 or more against the v4 findings fixture. An agent number is not written into `fact` as `SELECTED`.

This slice does not change page choice. Pages still come from published schedules.

Done when the score file for all five rooms is stored under `apps/api/tests/fixtures/close/scores/` and the test reads it. A missing model key skips the live agent call and fails the slice only when `AGETIC_CDD_CLOSE_SCORES=1`.

---

## Order

1. Slice 1 — runner and invariant test.
2. Slice 2 — five rooms.
3. Slice 3 — ties, flags, four refusals.
4. Slice 4 — queue, completeness, no agent values.
5. Slice 5 — rename, reorder, image PDF, currency display.
6. Slice 6 — name ban, then leave the file store off the series path.
7. Slice 7 — scores, behind `AGETIC_CDD_CLOSE_SCORES`.

---

## Out of scope

- Matching a live deck’s slide count or narrative.
- Deleting `services_databook*.py`.
- Merging Postgres into the SQLite app database.
- New ontology concept ids. A missing synonym is a fixture caption change or a vocabulary row plus a rebuilt seed, in a separate change.
- Redeploy or commit, unless asked.
