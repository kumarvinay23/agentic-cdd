# Customer Segmentation

Show where revenue comes from and how exposed it is to a small number of
customers. Concentration is usually the single largest value driver an IC
argues about, so it must be calculated, never described.

Do not recommend invest or pass. If concentration cannot be calculated, say
it is unassessed, request the ledger, and withhold any risk rating. An empty
table is not high risk.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]

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
locations or subscriptions. Never mix them in one table.

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
