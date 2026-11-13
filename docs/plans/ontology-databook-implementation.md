# Ontology databook and report switch

Status: Part 2 (five quick fixes and Fixes 1–10) is in the API. Part 1 Steps 1–12 are in: the PostgreSQL 16 databook, a read-only ontology, one fact repository, a confirmed deal profile, a document register with one row per data-room file, statement readers for Excel and PDF tables, a mapper that queues uncertain matches, a calculation and period engine, a resolver that keeps one value per figure, a rule checker whose block failures stay out of the publish set, a publisher that writes schedule tabs from `v_databook_fact`, and CDD and FDD builders that read those tabs. The file-backed databook in `services_databook*.py` stays on disk. The close, five differing data rooms, runs after this step.

Source pack: `DiligenceIQ_Databook_For_Engineering_v1.zip`.

- `2_Data_Model/DiligenceIQ_Databook_Data_Model_v1.sql`
- `2_Data_Model/DiligenceIQ_Databook_Ontology_Seed_v1.sql`
- `2_Data_Model/DiligenceIQ_Databook_Data_Model_v1.schema.json`
- `1_Ontology/DiligenceIQ_Databook_Ontology_v1.json`
- `4_Reference_Code/dbk_reference.py`
- `4_Reference_Code/test_pipeline.py`

The xlsx in the pack is for people. Code never reads it.

## Rules for every step

- Stop at the end of a step until its check passes. Do not start the next step on a failing check.
- Copy `read_statement_grid`, `read_registers`, `run_calculations`, `derive_periods`, `run_identities`, `ebitda_bridge`, `compare_with_source`, `check_fact_contract`, and class `Ontology` from `dbk_reference.py`. Do not rewrite them.
- The app database stays the current SQLite database (`AGETIC_CDD_DATABASE_URL`). The databook is a second database, PostgreSQL 16, on its own URL. Users, deals, and pipeline runs are not moved in this plan.
- No company name, file name, sheet name, or deal figure in code, prompts, configuration, or the ontology. Fixtures that already hold answer-key figures stay fixtures.
- The CDD deck builder and the FDD builders do not change their page behaviour until Step 12. Compost Crew’s deck is not regenerated to “try” an earlier step.
- A new ontology label is a vocabulary row plus a rebuilt seed. An item id is never renamed. The old id is deprecated and an alias is added.

## Step 1 — Migrations

Run `DiligenceIQ_Databook_Data_Model_v1.sql`, then `DiligenceIQ_Databook_Ontology_Seed_v1.sql`, as the databook migrations.

The model is 10 ontology tables (`onto_version` through `onto_record_class`), 9 deal tables (`deal` through `mapping_decision`), and 2 views (`v_databook_fact`, `v_open_flags`).

Done when the database refuses all four of these inserts:

- a 7-month period labelled FY (`fy_is_12_months`, and YTD stays partial)
- a second `SELECTED` or `DERIVED` row for the same figure (`fact_key_selected`)
- a currency amount with no currency code (`currency_needs_code`)
- a fact whose concept is not in the ontology

## Step 2 — Ontology service

Load `DiligenceIQ_Databook_Ontology_v1.json` once at startup, read-only. Copy class `Ontology`. Stamp `ontology_version` on every deal row and every fact row.

Done when every fact row carries that version. The service has no write path to the JSON.

## Step 3 — Fact repository

One module inserts and updates `fact`. It calls `check_fact_contract` and validates the row against `DiligenceIQ_Databook_Data_Model_v1.schema.json` before the insert.

Done when a repository test is the only test that writes `fact`, and a direct insert from any other service is absent. Search the API for `INSERT` into `fact` and for the fact model’s save method.

After this step, point these existing services at the repository. Their current in-memory fact dicts become callers, not stores:

- Fix 5, `services_calculation_library.py`, asks by calculation id and stores the result as a fact id
- Fix 6, `services_agent_result.py`, keeps numbers as those fact ids
- Fix 7, `services_claims.py`, records the chosen fact id when sources disagree
- Fix 8, `services_verification.py`, recomputes from the repository
- Fix 10, `services_report_check.py`, checks a narrative number against the cited fact

Do this wiring before Step 4. The report files still do not read the databook.

## Step 4 — Deal profile required to publish

The confirm screen already blocks an agent run until a person confirms country, currency, sector, business model, deal type, and legal entities. Add the databook fields on that same screen: fiscal year end, latest actual month, sector pack, and EBITDA policy.

Done when a databook publish call for an unconfirmed profile is refused, and two deals confirmed with different currencies keep those currencies on their own fact rows.

## Step 5 — Document register

Write one `document` row per data-room file. Set document type, evidence tier, version, and status from the ontology’s document types. A file that is skipped stays in the register with a reason. Stable ids from `services_document_graph.py` remain the ids for the file, the page or sheet, and the block or cell.

Done when the register count equals the file count in the room, including skipped files.

## Step 6 — Readers

Call `read_statement_grid` for Excel, then the PDF-table path. Read formulas and values. Classify each row as a line, a SUM, an arithmetic subtotal, a ratio, a heading, or a check. Store only lines as chosen values, each with its source cell. Hold a spreadsheet error. Do not store it as zero.

Done when every stored value has a source cell, and a fixture workbook with a `#REF!` or `#DIV/0!` cell produces a held row rather than 0.

A prose PDF is in scope here as a table reader, not as a deal-specific parser. An image-only PDF stays unread until OCR returns text, and the register row says why.

## Step 7 — Mapper

Match each stored line to the ontology vocabulary and the section rules, using the mapper behaviour in the reference reader. A loan under current liabilities stays current. An uncertain match goes to a review queue and is saved as `mapping_decision`.

Done when no extracted line is left without a concept or a review row, and every guess is in that queue.

## Step 8 — Calculation and period engine

Call `run_calculations`, `derive_periods`, and `compare_with_source`. Totals, ratios, FY, YTD, and LTM come from stored lines and the ontology calculations. Period type comes from the months covered and the confirmed fiscal year end, not from the column heading. The source’s own totals stay as comparisons.

Done when each source total matches the derived total, or the difference is stored on `reconciliation` with a reason.

## Step 9 — Resolver

Choose one value per figure with the ontology authority order. Leave the other candidates on `fact` with a status other than `SELECTED` and a reason.

Done when a normal load never hits `fact_key_selected`, and a second document with a different value for the same figure remains visible as a candidate.

## Step 10 — Rule checker

Call `run_identities` and `ebitda_bridge`. Run the ontology rules. A block failure stops that databook tab. Management EBITDA is the company’s own line. Reported EBITDA is computed from the confirmed policy. Costs and cash outflows are stored as positive amounts. The ontology weights carry the sign, and a sign flip is recorded.

Done when a failing rule appears in `v_open_flags` and the blocked tab is absent from the publish set.

## Step 11 — Publisher

Build the schedule tabs from `v_databook_fact`. Every published cell holds a fact id that links to its source cell. A missing required figure goes to the GOV-05 gaps tab.

Done when a published cell with no source cell cannot be written, and a gap has a GOV-05 row. The file-backed databook is still on disk. Report builders do not switch in this step.

## Step 12 — Report builders read the published databook

CDD and FDD take figures from the published tabs only. An agent output is never a chosen value.

Page choice is generic. One page exists per published schedule that has at least one fact. A schedule with no facts for that deal is omitted. A lease schedule renders rent. A statement-of-operations schedule renders revenue and costs. A debt schedule renders debt. No page is added because of a company name, a file name, or a business-model nickname.

The existing CDD page plan keeps its comparisons for the schedules it already draws, and those comparisons take their numbers from fact ids. Chart choice stays the Fix 9 rule: a bridge for a change in a total, a line for a trend, grouped bars for segments over time.

Done when `4_Reference_Code/test_pipeline.py`, pointed at the databook URL, prints `ALL INVARIANTS HOLD` on every test deal. Ontology edits in this step go through a pull request, a seed reload, and that same test.

## Close

Implementation plan: `docs/plans/ontology-close-implementation.md`.

Run this only after Step 12. Use at least five data rooms that differ in sector, country, currency, deal type, and file format. The rooms are fixtures. Their names do not appear in product code.

All of these must pass:

- The four constraint refusals from Step 1.
- R-SRC-01, and R-SRC-02/03 as written in `test_pipeline.py`: mapped lines inside a source subtotal, and derived figures equal to the source’s own subtotals, ratios, and annual columns, or the difference explained.
- A balance sheet that balances.
- Cash-flow cash equal to balance-sheet cash in every month that both exist.
- EBITDA and debt bridges flagged in `v_open_flags` where they do not tie.
- At most 15% of extracted rows waiting in the review queue.
- A completeness score on every published tab.
- No agent figure chosen as a databook value.
- Renaming files, reordering slides, scanning a PDF to an image, or changing the confirmed currency does not change a fact id’s concept or its source cell. The displayed amount converts with the confirmed currency. It does not change the source amount.
- CI rejects a company name, file name, sheet name, or deal figure in code, prompts, configuration, and the ontology JSON.
- Every agent scores 8 or more on quality, coverage, and IC readiness on every test deal.
- The report checker scores the rendered CDD and FDD at 8 or more against the v4 findings.

## What this does to the two live report shapes

A deal whose room is statement grids gets those grids as facts, and the current CDD and FDD pages fill from them. A deal whose room is a lease, a debt agreement, or a site P&L gets a page only for the schedule that published. An image-only file stays a register row with a skip reason until OCR returns text. That is the same path for every deal.
