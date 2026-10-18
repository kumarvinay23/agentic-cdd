# Customer Segmentation

Show where revenue comes from and how exposed it is to a small number of
customers. Concentration is usually the single largest value driver an IC
argues about, so it must be calculated, never described.

Do not recommend invest or pass. If concentration cannot be calculated, say
it is unassessed, request the ledger, and withhold any risk rating. An empty
table is not high risk. Reject overlapping segment buckets. Closure must be
reproducible from the ledger inputs.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]
Deal perimeter: [DEAL_PERIMETER]
Transaction type: [TRANSACTION_TYPE]
As-of date: [AS_OF_DATE]
Review periods: [REVIEW_PERIODS]
Decision stage: [DECISION_STAGE]

1. Resolve pointers to the billing ledger or investor workbook and open them.
Build a customer-level view with account, parent and location identifiers.

2. Segment by service, customer type, geography and contract form. Reconcile
segment revenue to total revenue in the accounts; show any unclassified
remainder rather than forcing it into a segment.

3. Calculate concentration: the top 1, top 5 and top 10 shares of revenue,
aggregated to parent level so that related accounts are counted together.
Add a concentration index if the data support it. Repeat for gross profit
if margin data exist.

4. Name the largest contracts, their value, their share of revenue, their end
date and their termination rights.

5. State clearly which population every count refers to — accounts, parents,
locations or subscriptions. Never mix them in one table. Reject overlapping
buckets (shares summing above 100% without explanation).

6. Run a closure reproducibility test: the same ledger inputs must reproduce
the published top-1/5/10 and axis reconciles. Include Questions for every
material gap (or state none are missing).

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
