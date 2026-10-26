# Quality checklist (run before delivering any deck)

Automated gates (must all pass):

- [ ] `validate_inputs.py` – no blockers; issues copied to the exception report
- [ ] `check_content.py --render-log …` – **0 errors** (refs, numbers, calculations, limits, banned text, overflow)
- [ ] `render_deck.py` – overflow 0, errors 0
- [ ] `qa_deck.py` – 0 structural findings (no instructions left, nothing off-slide, no overlaps, order = template)
- [ ] pptx skill validator (if available): `python /mnt/skills/public/pptx/scripts/office/validate.py deck.pptx --original assets/cdd_template.pptx`

Evidence and accuracy:

- [ ] Every figure on a slide traced to an evidence id; OCR-flagged figures verified on the page image and recorded in `verified.json`
- [ ] Every calculation recomputes; inputs cited; outputs marked †
- [ ] Facts, calculations and interpretations distinguished (kinds; "rated … by the agent"; "Our view")
- [ ] Market statistics not presented as company metrics (T12)
- [ ] Conflicts resolved by R1–R6 or shown as triangulation, and logged
- [ ] Placeholders excluded; N/A shown as "Not provided" rather than hidden
- [ ] Same metric identical wherever it appears (`metrics` block in content.json)
- [ ] Recommendation consistent across S06, S07 and S44; confidence adjusted by T7 and both values shown
- [ ] No reference-report names, template instruction text or example numbers (`banned_terms.yaml`)
- [ ] Synthetic-data notice present whenever the inputs carry synthetic markers

Visual (inspect **every** slide image in `<work>/qa/`):

- [ ] No clipped, overlapping or overflowing text; table rows readable (≥ 9 pt); body ≥ 10 pt
- [ ] Titles ≤ 2 lines; source line ≤ 2 lines and not colliding with content
- [ ] Charts: correct values, units in axis title / number format, labelled, period stated
- [ ] RAG pills use the right polarity (risk columns `bad_high`, strength columns `good_high`)
- [ ] Empty space acceptable (short tables are fine; do not pad with invented content)

Deliverables:

- [ ] Editable .pptx (native tables and charts), exception report (.md), content.json + evidence.json for audit

Investment-committee readiness (warnings from `check_content` count as blockers for an IC issue):

- [ ] Executive summary (S020) answers first: view, 3–5 graded findings with figures, risks, conditions
- [ ] Diligence case shown against the management plan (management / diligence / downside)
- [ ] Market driver (regulation, mandates, pipeline) researched and cited; sizing triangulated where possible
- [ ] One revenue basis per section, named in the subtitle
- [ ] Titles rounded and, where possible, one line; bridges as waterfalls, retention as curves
- [ ] Audit appendix ≈ 3 pages; glossary at the back; no agent-quality language in findings pages
- [ ] Primary-research gap stated with the interviews that would close it

Diligence controls (reference 08) — for a deal-team working draft:

- [ ] C1 every "contracted / committed / backlog" claim cites a reviewed contract, or is reworded
- [ ] C2 `reconcile.py` run; every conflict explained, quantified and acknowledged
- [ ] C3 no calculation mixes actual/plan or ledger/model without `mixes_bases`; scenarios labelled
- [ ] C4 every retention or count comparison on the same population and period
- [ ] C5 grades recomputed by source class (finalize); no assertion stated as fact
- [ ] C6 benefits shown net, with acquired earnings apart from synergies
- [ ] `issue_register.xlsx` produced: priorities, evidence required, price / structure / decision impact
- [ ] Revised conclusion on S020 and in the register, with usable vs dependent findings
