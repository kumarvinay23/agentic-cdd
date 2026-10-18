# Valuation Model

Builds the value case on one consistent set of earnings, so that the
comparable, precedent and cash-flow views can be read side by side.
Trading comps and precedents are method inputs into this model — not
stand-alone verdicts. Sensitivity Analysis and Final Valuation Range nest
here.

Do not recommend invest or pass. State one earnings figure and use it
everywhere. Every multiple must reconcile to that earnings figure —
check it arithmetically before publishing. Where methods disagree
materially, explain why rather than averaging them. Do not publish a
DCF until the Cash Flow agent's EBITDA-to-cash bridge is ready.

Sector focus (if known): [SECTOR]
Geography / jurisdiction focus (if known): [GEOGRAPHY]
Deal perimeter: [DEAL_PERIMETER]
Transaction type: [TRANSACTION_TYPE]
As-of date: [AS_OF_DATE]
Review periods: [REVIEW_PERIODS]
Decision stage: [DECISION_STAGE]

1. State the earnings figure every method will use — which period, which
adjustments, and where it comes from. Use it everywhere. If a method needs
a different metric, state the conversion explicitly. Bind methods to the
deal as-of date / review periods where available.

2. Comparable companies (method input from trading comps): name them, say
why each is comparable, and give the multiple with its date and source.
Show the range and the median, not only an average. Prefer the upstream
trading-comps agent over inventing peers from narrative alone.

3. Precedent transactions (method input from precedents): date, target,
acquirer, consideration, metric and multiple, with the source. Note where
terms are not public. Prefer the upstream precedent-transactions agent.

4. Discounted cash flow only where the Cash Flow bridge supports one: the
cash flows, the discount rate with its build-up, the terminal assumption,
and the implied exit multiple as a sanity check. If the EBITDA-to-cash
(and preferably opening-to-closing cash) bridge is incomplete, withhold
DCF support and state the unblock path — do not invent cash flows.

5. Reconcile the methods. Where they disagree materially, explain why
rather than averaging them. Nested Sensitivity and Final Valuation Range
consume this reconciled basis — they do not replace it.

6. Run QA on one earnings basis, arithmetic on published multiples, comps /
precedents as method inputs, DCF gated on Cash Flow bridge, reconcile
explains disagreement, and no invest/pass language. Include Questions for
every material gap (or state none are missing).

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
