# Market Volume & Growth

Size the served market from the ground up and separate how fast the market
grows from how fast the company grows. The difference is share gain — what
the investment case usually rests on.

Do not recommend invest or pass. Never label a one-year rate as a multi-year
rate. If company historical growth is computable from the accounts in the
data room, compute it — "Not available" is not acceptable when the accounts
are present. Bind every series to the approved Market Definition perimeter.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]
Deal perimeter: [DEAL_PERIMETER]
Transaction type: [TRANSACTION_TYPE]
As-of date: [AS_OF_DATE]
Review periods: [REVIEW_PERIODS]
Decision stage: [DECISION_STAGE]

1. Bind the market series to the Market Definition four-axis perimeter
(service, customer type, geography, value-chain stage), as-of date and unit.
Reject or relabel any published series whose perimeter does not match.

2. Separate volume (units) from value (currency). Do not mix them in one
growth rate without an explicit bridge.

3. Build the market series for historical and forecast periods with source
dates, currency and consistent units. Label each point as actual, forecast
or unavailable. Calculate growth from the endpoints and years elapsed;
reperform endpoint CAGR. Never label a one-year rate as a multi-year rate.

4. Build the market bottom-up: countable units in the served geography,
the share realistically capturable, and the realised annual price per unit.
Show the arithmetic. Cross-check top-down against a published source whose
perimeter matches; otherwise rely on bottom-up.

5. Put the company's own growth beside it on the same geography, segment and
period, from the accounting records. Decompose into organic, share gain,
price, mix and M&A / acquisition.

6. Compare the plan's implied growth rate with the market rate and state the
multiple. State scenario / adoption sensitivities that change the multiple.
If the plan requires growing several times faster than the market, say so
plainly and state what must be true for it to happen.

7. Include Questions and inputs required for every material gap (missing
units/price, unmatched top-down, unlabelled vintage, untested decomposition),
each with required records, decision effect, priority, owner, timing, closure
test and interim treatment. If no material inputs are missing, state that
explicitly.

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent. Prefer a computed figure from accounts over 'Not available'.
