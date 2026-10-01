# Deal Context & Objectives

Establish the factual base for this deal. Your output is the frame; the decision
belongs to synthesis later. Do not issue an investment verdict, a confidence
level, or a recommendation to invest or pass.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]

1. Identify the target legal entity, the perimeter being acquired, the
transaction type, and the buyer context. Anything not stated in the documents
becomes a named information request, not an assumption.

2. Pull the headline facts an IC would expect on page one: revenue and growth
for each historical period, EBITDA and margin, the latest twelve months, the
largest customer's share, headcount, and the plan for the current and final
forecast year. Take them from the accounting records in preference to the CIM.
Where the two differ, record both and flag the difference. Build a fact ledger
of 15–25 facts. Each fact must carry value, unit, period, basis
(actual / LTM / forecast / budget), and a source locator (file + sheet/cell,
page, or slide — not a bare filename).

3. State the investment thesis as three drivers. Each must carry a figure and
a source. A driver with no number is a hypothesis, and must be labelled one.

4. Write three to six must-be-true hypotheses. Each states a threshold that
could be failed — for example "customer X renews at or above $Y", or
"churn returns below Z% within 12 months". Name the agent that will test it
(tested_by_agent). Include fail_test wording.

5. List the critical risks visible in the records already, with size:
customer concentration, earnings trend, cash movement, funding obligations.

6. List the open questions that block the thesis, in priority order, each with
the document that would answer it.

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
