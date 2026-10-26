# Input template specification — DiligenceIQ agent outputs

The inputs are the per-module reports produced by the DiligenceIQ diligence agents. One project normally
supplies **34 module files** (plus occasional duplicates). Their structure recurs across projects; their
content changes. The machine-readable registry is `config/module_registry.yaml`.

## 1. File format (as observed)

| Property | Observed | Consequence |
|---|---|---|
| Container | PDF produced by jsPDF, US-Letter portrait, one JPEG image per page | **No text layer** – text must be OCR'd (`ingest.py`) |
| Naming | `<Project> Latest_<Module Title>_v<N>[ (k)].pdf` | Filenames are hints only; modules are identified by the H1 title and section headings |
| Versions | `_v1`, `_v2`, browser copy suffixes ` (1)`, ` (2)` | Highest `_vN`, then highest copy suffix, then latest mtime wins; identical copies logged as duplicates |
| Tables | Web-rendered HTML tables: grey 1-px rules, dark navy header band | Detected from ruling lines and OCR'd cell by cell; some tables are **clipped at the right page edge** (flag `TABLE_CLIPPED`) |
| Currency | Indian rupee `₹` frequently misread by OCR as `%`, `¥`, `®`, `§`, `€`, `z`, `7`, `2`, `~` | Repaired where safe (`OCR_CURRENCY`) or flagged (`OCR_CURRENCY_AMBIGUOUS`); every figure used must be checked on the page image |
| Text-native variants | `.md`, `.docx`, `.html`, text-layer PDF | Supported through the same parser (markitdown path); preferred when available |

## 2. Recurring structure of every module

```
<H1 Module title>                      e.g. "Market Volume & Growth"
[Insight Snapshot: ...]                optional module-level overview (section 0)
1. <Section title>                     4–6 numbered sections, titles fixed per module type
   Insight Snapshot: <one-line purpose or finding>
   <table>  and/or  <Label: value> fields  and/or  bullet notes
   Read: <agent's interpretation of the section>
...
Analytical Synthesis & Hidden Insights  prose + bullets (interpretation only)
<N>. <Verdict section>                 last numbered section: "… Verdict …"
Recommendation: <stance>               module verdict block
Confidence: High | Medium | Low
Key conditions: <text>
Sources  [n] <title / file>            present in only a few modules
```

Evidence tags embedded in text:

| Tag | Meaning | Treated as |
|---|---|---|
| `(DOC: <file>)` | data-room document | `data_room_doc`; doc type inferred (survey / interviews / pricing / financials / CIM) |
| `COMPUTED FACTS`, `(computed)`, `FACT BASE` | computed from data-room financials | `data_room_computed` (highest priority for company financials) |
| `[n]` | numbered external web source | `web`; numbering is **module-local in practice** and not reliably consistent |
| `N/A`, "data room did not provide" | missing | not evidence; flag `NA` |
| "Regulation X", "Peer A", "PE Fund X", "Industry Z", "Segment A", "Synergy Lever 1" | template placeholders written by the agent | not evidence; flag `PLACEHOLDER`, excluded |

## 3. Module catalogue (34 types)

Role: **C** context, **F** finding, **S** synthesis, **A** appendix. Criticality **core** = deck materially weaker without it.

| Id | Module | Role | Crit. | Numbered sections | Supports output slides |
|---|---|---|---|---|---|
| DCO | Deal Context & Objectives | C | core | Executive Summary; Key Investment Hypotheses; Critical Risks & Red Flags; Critical Open Questions; Key Data Extract; Preliminary Investment Verdict | S01, S07, S09, S15–S17, S36, S44 |
| SCM | Scope & Methodology | C | core | Scope Definition; Key IC Questions; Analytical Methodology; Deliverable Structure | S03, S05, S06, S09 |
| CBG | Company Background | F | core | Company Snapshot; Historical Evolution; Business & Revenue Model; Products; Organisational Footprint; Execution Verdict | S09, S10 |
| MGQ | Management Quality | F | supp. | Leadership Scorecard; Key Executives; Bench Strength; Succession Risk; Governance; Verdict | S12 |
| STR | Strategic Direction | F | supp. | Roadmap; Execution Integrity; Growth Vectors; Market Fit; Capital Allocation; Verdict | S11, S42 |
| RCO | Regulatory Compliance | F | supp. | Framework; Compliance Status; Litigation; IP Protection; Verdict | S13, S24 |
| IPT | IP & Technology | F | supp. | IP Portfolio; Tech Stack; R&D Pipeline; Tech Debt & Cyber; Verdict | S13 |
| ESG | ESG & Sustainability | F | supp. | Environmental; Social; Governance; Rating & Compliance; Verdict | S12, S40 |
| MDF | Market Definition | F | core | Perimeter; TAM/SAM/SOM; Taxonomy; Boundaries; Verdict | S19, S20 |
| MVG | Market Volume & Growth | F | core | Historical & Forecast Size; Growth Drivers; CAGR Benchmarking; Lifecycle; Growth Integrity | S20, S21 |
| MPR | Market Pricing | F | supp. | Pricing Model; Price Positioning; Pricing Power; Margin Impact; Verdict | S10, S22 |
| DDR | Demand Drivers | F | core | Macro Drivers; Industry Catalysts; Regulatory Drivers; Cyclicality; Verdict | S15, S21 |
| CID | Competitor Identification | F | core | Direct Competitors; Adjacent/Indirect; Capability Matrix; Barriers to Entry; Verdict | S23, S30, S31 |
| CDF | Competitive Differentiation | F | core | Differentiators; Moat; Threats; Evidence of Differentiation; Verdict | S27, S31, S32 |
| MSS | Market Share Strategy | F | core | Market Share; GTM; Win/Loss; Share Growth Potential; Verdict | S06, S27, S33 |
| SWO | SWOT Analysis | S | supp. | Summary Matrix; Strengths; Weaknesses; Opportunities; Threats; Synthesis | S16, S34 |
| CSG | Customer Segmentation | F | core | Verticals; Tiering & Concentration; Geography; Persona; Verdict | S26 |
| CSA | Customer Satisfaction | F | core | NPS/CSAT; External Reviews; Pain Points; Service Quality; Verdict | S27 |
| CST | Customer Stickiness | F | core | Retention & Churn; Switching Costs; Contracts; Churn Drivers; Verdict | S27 |
| SUP | Supplier Dependence | F | supp. | Supplier Landscape; Concentration; Contracts; Substitutability; Verdict | S16, S39 |
| CSC | Cost Structure | F | supp. | Cost Breakdown; Fixed vs Variable; Benchmarking; Margin Levers; Verdict | S37 |
| SCR | Supply Chain Resilience | F | supp. | Supplier Concentration; Input Sensitivity; Logistics; Geopolitical; Verdict | S39 |
| OPR | Operational Risk | F | supp. | Process Vulnerability; IT Risk; Scalability; BCP; Verdict | S16, S39 |
| HPF | Historical Performance | F | core | Top-Line Growth; Margins; Benchmarking; Growth Quality; Verdict | S36 |
| RVQ | Revenue Quality | F | core | Revenue Mix; Subscription Metrics; Visibility & Backlog; Adjustments; Verdict | S28 |
| CFL | Cash Flow | F | supp. | OCF; FCF & Capex; Working Capital; One-Offs; Verdict | S37 |
| CAP | Capital Structure | F | supp. | Debt Profile; Leverage Ratios; Equity Mix; Covenants; Verdict | S37 |
| MRK | Market Risk | F | core | Risk Matrix; Competitive & Substitution; Macro; Market Cycle; Verdict | S16, S23 |
| GRO | Growth Opportunities | F | core | Organic Vectors; Inorganic Pipeline; White Space; Upsell; Verdict | S42 |
| SYN | Synergies | F | supp. | Cost Synergies; Revenue Synergies; Cost-to-Achieve; Phasing; Verdict | S15, S43 |
| IRK | Internal Risk | F | supp. | Risk Matrix; Operational; Financial; Human Capital; Verdict | S12, S16, S36 |
| VAL | Valuation Model | F | supp. | Trading Comps; Precedents; DCF Assumptions; Base Valuation; Verdict | S38 |
| REC | Recommendations | S | core | Investment Decision; Drivers & Catalysts; Conditions Precedent; 100-Day Plan; Verdict | S06, S07, S44 |
| APX | Appendices | A | supp. | Document Log; Citation Index; Data Gaps; Coverage; Coordinator Verdict | S05, S17, S47 |

## 4. Relationships between modules (observed)

* **Module-of-record** (`record_for` in the registry): each metric has one owning module, e.g. NPS → CSA,
  retention → CST, market size → MVG, revenue series → HPF. Other modules frequently restate or contradict it.
* **Synthesis modules** (SWO, REC, DCO §6) summarise finding modules; they add no new evidence and are used
  for structure and stance, not as primary sources for figures.
* **Appendices** logs the documents used, data gaps and the coordinator's certainty verdict – used for the
  methodology, gaps and source-register slides.
* **Web citations** `[n]` are reused across modules but their numbering is not stable (e.g. `[3]` resolves to
  different sources in different modules); resolution is per module, falling back to the SCM data-source list.

## 5. Known gaps and ambiguities in the input format

1. Periods of financial figures are usually not stated (e.g. revenue with no fiscal year).
2. Units and currency labels are inconsistent (`₹ … bn (USD equivalent)`, TAM in crore vs market in USD bn).
3. Metrics are cited to unsuitable sources (valuation multiples, WACC, board composition from a customer survey).
4. Placeholder rows are emitted when the agent lacks data.
5. The entity perimeter can drift between modules (e.g. a ride-hailing framing with scooter-manufacturer evidence).
6. Tables can be clipped at the page edge in the PDF render, truncating source/confidence columns.
7. No machine-readable export is provided; OCR is required for the observed PDFs.

**Recommendation to the input owner:** export each module as Markdown/JSON alongside the PDF. The skill already
parses text-native inputs, which removes all OCR-related exceptions.
