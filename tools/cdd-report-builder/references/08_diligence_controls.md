# Diligence controls C1–C6 and the issue register

The deck is a **working diligence draft for a human deal team**. Every material claim, calculation,
chart and conclusion passes six controls before it is shown. Where the evidence permits, correct
the claim; where it does not, **qualify or withhold** it. Never invent support.

Machine checks: `scripts/lib/controls.py` (config `config/controls.yaml`), run by `check_content.py`.
Reconciliation: `scripts/reconcile.py`. Register: `scripts/review_register.py`.

## C1 — Recurring revenue is not contracted revenue

Separate four things that decks routinely merge:

| Term | Means | Evidence needed |
|---|---|---|
| Recurring | Customers keep buying (subscription, repeat, pay as you go) | Billing history |
| Contracted | An enforceable commitment for a stated term | The executed contract |
| Renewal / option | The customer may extend; the vendor cannot compel it | Contract option clauses and exercise history |
| Pipeline | Not yet won | CRM with stage, value, age |

For every contract behind a material revenue line, record duration, firm term vs option years,
termination rights (for convenience / cause), minimum volumes or take-or-pay, price escalators,
caps, funding or appropriation dependencies, and key-person or permit dependencies.
**Check:** "contracted / committed / locked-in / backlog / guaranteed" needs a reviewed contract in
the refs (file class `contract`), else C1 (error in titles and takeaways, warning elsewhere).
Management's own description may be reported only as attributed ("the CIM describes…").

## C2 — Reconcile measures and versions; never pick silently

Run `python scripts/reconcile.py --work <work>`. It groups every revenue, gross profit / margin,
EBITDA / margin, net income and ARR value by period and status (actual vs plan) across the ledger,
company workbooks, the model and the CIM, allows for the rounding of the least precise source, and
writes `reconciliation.md` with each difference quantified.

For each conflict: choose a basis per purpose (ledger for actuals, model for plan comparisons), say
so on the page, show the adjustment, quantify the unexplained remainder, and record it in
`content.exceptions` and `content.reconciliations` (`{metric, period, basis_used, explanation}`).
**Check:** a slide citing a figure in an unacknowledged conflict raises C2.

## C3 — Preserve each figure's identity

Every figure keeps metric, unit, scale, period, actual / forecast status, population and source
(`lib/values.py`, `vdr_extract.py`). A calculation may not mix actual with plan inputs, or ledger with
management-model inputs, unless it declares `mixes_bases: "<reason>"`. Label scenarios and
cross-checks explicitly ("momentum cross-check, not a forecast"). Keep enough precision in
`calculations` to reproduce every output; round only in titles.
Typical failure: today's volume × a future-year price; current revenue ÷ a future-territory market.

## C4 — Compare like populations and periods

Accounts, locations, sites, subscriptions, households and logos are different populations; logo
retention, gross revenue retention and net revenue retention are different measures. State the
population and period of every retention or count; explain annualisation (monthly 99.3% =
annual 92.4%); never compare a model's per-location retention with an actual per-account figure
without saying so. Watch for population breaks (a block of programme subscribers added to a
billing file) that make later periods incomparable with earlier ones.
**Check:** a comparison between figures whose sources carry different population tags raises C4
unless the text says the bases differ.

## C5 — Grade at the claim level, by source class

| Class | Examples | Alone gives |
|---|---|---|
| reviewed_record | ledger / management accounts, bank or billing export, executed contract | indicated |
| computed | declared calculation on cited inputs | inherits its inputs |
| primary_research | survey, interviews run for this diligence | indicated |
| management_analysis | company workbook, model, databook, KPI pack | indicated (history) / asserted (forecast) |
| external | dated web research, third-party report | indicated |
| management_assertion | CIM, teaser, presentation; a tie-out row with no numeric support | asserted |
| agent_restatement | an agent output repeating a document | asserted |
| assumption | plan driver, scenario, analyst scoring input | asserted |

**Established** needs a reviewed record plus an independent source. Populated fields and repeated
citations are not verification: ten agent modules citing the CIM are one management assertion.
Confirm that each citation supports the exact claim (metric, period, population).
**Checks:** a "fact" resting only on assertion or restatement and not attributed raises C5; a year in
the claim absent from its cited evidence raises C5; `finalize_content.py` recomputes every table's
`Grade` column from its row refs.

## C6 — Net incremental value

For any synergy, saving, uplift, in-sourcing, new facility or growth-capital case, show gross benefit,
operating cost, implementation / integration cost, capital requirement, timing and overlap with the
base plan (double counting). Keep **acquired earnings** (what the price buys) separate from
**synergies** (what the buyer must create). A benefit capped by an existing cost line (e.g. a saving
cannot exceed the spend it replaces) states the cap.
**Check:** a benefit word without "gross / net of / capex / cost to achieve" or a calculation marked
`net_of` raises C6.

## Issue register

Record each reviewed issue in `content.issues`:

```json
{"id": "I01", "priority": 1, "control": "C1", "claim": "...", "slides": ["S046"],
 "problem": "...", "impact": "quantified where possible", "correction": "what was changed in the deck",
 "evidence_required": "exact documents / data", "could_change": ["price", "structure", "decision"],
 "pre_decision": "mandatory | residual", "status": "corrected | qualified | withheld | open"}
```

Priority: **P1** could change price, structure or the decision and must close before a decision;
**P2** must close before signing (confirmatory); **P3** residual uncertainty the team can accept.
`python scripts/review_register.py --work <work>` writes `issue_register.xlsx` (register, revised
conclusion, reconciliation, claim grades, automated flags) and `issue_register.md`; automated C1–C6
flags not covered by a reviewed issue are filed as P2/P3 review rows.

## Revised conclusion

`content.conclusion = {confidence, statement, usable[], dependent[{finding, depends_on[]}]}` —
state the view at the confidence the evidence supports, list the findings usable now, and tie every
finding that depends on open work to its issue ids. The executive summary page (S020) carries the
same conclusion.
