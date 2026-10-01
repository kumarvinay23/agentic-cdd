# Databook sample VDR pack

Upload these into a deal’s **Deal room (VDR)**, then:

1. **Workflow → Data ingestion → Run phase**
2. **Databook → Rescan**

## Files

| File | What it tests |
|------|----------------|
| `01_Sample_Executive_Summary.xlsx` | Table extract; Revenue/Units/Margin; **passing** statement-block (Total income ties) |
| `04_Sample_Commercial_Due_Diligence.xlsx` | **Conflict** on Revenue FY2024 (3,140 vs Exec 4,900); NRR family gate |
| `05_Sample_Failed_Block_Check.xlsx` | **Failed check** — Total income 999 ≠ 100+20; constituents held out |
| `01_Sample_Executive_Summary_prose.pdf` | Prose-series path (no tables); Revenue / Units / Margin / EBITDA from text |

## Expected after Rescan (xlsx pair 01+04)

- Derived rows for revenue / units_sold / gross_margin / nrr
- Needs review: **Sources disagree** on Revenue FY2024 (4,900 vs 3,140)
- Findings: checks passed on tying totals; failed_check on file 05 if uploaded

## Optional

Upload only `05_…` to see Failed its check without conflicts.
Upload only the PDF to verify prose extraction without Excel.
