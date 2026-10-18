# Customer Stickiness

Measure whether revenue persists — how much of last year's revenue is still
here this year, how much left, and how much grew — and whether contracts
actually protect it.

Do not recommend invest or pass. If retention has moved, say by how much and
in which direction. A falling retention rate is a finding, not a caveat.
Distinguish behaviour from protection: customers who have stayed are not the
same as customers who are contractually committed. Exclude new logos from
retention numerators.

Sector focus (if known): [SECTOR]
Geography focus (if known): [GEOGRAPHY]
Deal perimeter: [DEAL_PERIMETER]
Transaction type: [TRANSACTION_TYPE]
As-of date: [AS_OF_DATE]
Review periods: [REVIEW_PERIODS]
Decision stage: [DECISION_STAGE]

1. Build monthly customer and revenue cohorts by start period. Define the
population precisely and keep it constant: logos, accounts, locations or
subscriptions.

2. Reconcile opening revenue, churn, contraction, expansion and closing
revenue for each period. From that, calculate gross revenue retention, net
revenue retention and logo retention on the same population. Exclude new
customers from retention numerators.

3. Show retention by segment and by tenure, and give the reasons for loss
where the records capture them.

4. Review executed contracts for the largest customers: term, renewal
mechanism, notice period, minimum commitment, price escalator and
termination for convenience. Identify when a material share of revenue
comes up for renewal.

5. Distinguish behaviour from protection. Customers who have stayed are not
the same as customers who are contractually committed.

6. Run QA that new logos / new customers are excluded from retention
numerators. Include Questions for every material gap (or state none are
missing).

Return ONLY JSON matching the schema requested in the user message.
Use citation tags exactly as '(DOC: data room financials)', '(COMPUTED FACTS)',
or '(DOC: [n])' where n indexes the numbered Sources list.
If unknown, write 'N/A (data room did not provide it)' or a named information
request — never invent.
