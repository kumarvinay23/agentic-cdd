# Supplier Dependence

Identify the vendors the business cannot easily replace, and what protection
exists in the contracts — spend is only one measure of dependence, and usually
not the important one.

Do not recommend invest or pass. Rate operational criticality separately from
spend. Do not state contract terms you have not read. A named supplier is not
automatically sole source. Say which dependencies are evidenced and which are
assumed, and reconcile with supply chain resilience.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]
Deal perimeter: [DEAL_PERIMETER]
Transaction type: [TRANSACTION_TYPE]
As-of date: [AS_OF_DATE]
Review periods: [REVIEW_PERIODS]
Decision stage: [DECISION_STAGE]

1. Build the supplier master from the payables ledger and operational
dependencies. Give each supplier's spend and its share of total spend for
each period.

2. Classify supplier roles (BOM / materials, logistics, IT, components,
services / capacity) and rate operational criticality separately from spend:
what stops if this supplier stops?

3. For each critical supplier, take contract terms from the executed
document: duration, renewal, pricing mechanism, service levels, termination
rights, assignment and change-of-control clauses, exclusivity. Do not state
terms you have not read.

4. Test substitutability: are there alternatives in this geography, what
qualification is needed, how long would switching take, and at what cost?

5. Prioritise suppliers by disruption impact (criticality × switch time ×
capacity exposure), not by spend alone. Flag change-of-control consents the
transaction would trigger.

6. Reconcile with Supply Chain Resilience. Run QA that contracts for critical
suppliers were read, sole-source is evidenced not assumed, and switch
cost/time is sized. Include Questions for every material gap (or state none
are missing).

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
