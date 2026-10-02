# Agentic CDD — Application Architecture & Design

**Product:** Agentic CDD — AI multi-agent Commercial Due Diligence platform  
**Brand layout target:** DiligenceIQ-compatible UI contracts (`/api/v1`)  
**Document purpose:** End-to-end system design with flowcharts for engineers, reviewers, and cloud deployers  

| Companion doc | Focus |
|---------------|--------|
| [GCP Architecture & Deploy](../deploy/GCP_ARCHITECTURE.md) | Google Cloud topology, Artifact Registry, Path A/B deploy |
| [Docker & Artifact Registry](../deploy/DOCKER_ARTIFACT_REGISTRY.md) | Build/run container images |
| [Security overview](../security/01-security-overview.md) | Security controls & policies |

---

## 1. Vision & design principles

Agentic CDD turns a **Virtual Deal Room (VDR)** into an **investment-grade diligence pack** by running specialized agents in a gated pipeline, then composing IC-ready reports.

| Principle | How it shows up in the design |
|-----------|-------------------------------|
| **Single-responsibility agents** | ~44 slug agents; each owns one diligence question |
| **Evidence over invention** | Heuristics + VDR text first; Gemini optional; databook promotes reconciled figures |
| **Deal-scoped persistence** | All analysis lives under `data/deals/<slug>/` |
| **Phase gating** | Ingestion → Foundations → Deep Dive → Verdict → Reports |
| **UI / API contract stability** | Next.js UI consumes DiligenceIQ-style `/api/v1` JSON |
| **Graceful degradation** | Empty Gemini key → heuristic-only; missing VDR → explicit info requests |

---

## 2. System context

```mermaid
C4Context
title Agentic CDD — System Context

Person(analyst, "Diligence Analyst", "Runs dealrooms, reviews agents, exports reports")
Person(admin, "Org Admin", "Manages workspace users / org")

System(agetic, "Agentic CDD", "Portfolio of dealrooms, multi-agent CDD pipeline, report generation")

System_Ext(gemini, "Google Gemini", "Optional LLM for document synthesis / refine")
System_Ext(browser, "Web Browser", "HTTPS client")

Rel(analyst, browser, "Uses")
Rel(admin, browser, "Uses")
Rel(browser, agetic, "JWT + REST /api/v1")
Rel(agetic, gemini, "generateContent JSON (optional)")
```

If C4 Mermaid is unavailable in your viewer, use this equivalent flowchart:

```mermaid
flowchart TB
  Analyst[Diligence Analyst]
  Admin[Org Admin]
  Browser[Web Browser]

  subgraph AgenticCDD["Agentic CDD Platform"]
    Web[Next.js UI]
    API[FastAPI /api/v1]
    Store[(SQLite + Deal Files)]
  end

  Gemini[Google Gemini API<br/>optional]

  Analyst --> Browser
  Admin --> Browser
  Browser -->|Login · Deal workspace · Reports| Web
  Browser -->|REST + JWT| API
  Web -->|NEXT_PUBLIC_API_URL| API
  API --> Store
  API -.->|optional synthesis| Gemini
```

---

## 3. Logical architecture (layers)

```mermaid
flowchart TB
  subgraph Presentation
    Pages[App Router pages]
    DealViews[Deal views<br/>dashboard · VDR · workflow · documents · reports · databook]
    AuthUI[Login / Register]
  end

  subgraph Application
    AuthAPI[Auth service]
    DealAPI[Deals / Dealroom]
    PipeAPI[Pipeline orchestration]
    DocAPI[Document workspace]
    ReportAPI[Report builders]
    DBAPI[Databook services]
  end

  subgraph Domain
    Agents[44 Agents<br/>Foundations · Deep Dive · Verdict]
    CDL[Central Data Library<br/>classify · route · FTS]
    Storyline[Report storylines]
  end

  subgraph Infrastructure
    SQLite[(SQLite<br/>users · orgs · deals · runs)]
    FS[(Deal filesystem)]
    GeminiClient[Gemini client]
  end

  Pages --> DealViews
  Pages --> AuthUI
  AuthUI --> AuthAPI
  DealViews --> DealAPI
  DealViews --> PipeAPI
  DealViews --> DocAPI
  DealViews --> ReportAPI
  DealViews --> DBAPI

  DealAPI --> CDL
  PipeAPI --> Agents
  Agents --> CDL
  ReportAPI --> Agents
  ReportAPI --> Storyline
  DBAPI --> CDL

  AuthAPI --> SQLite
  DealAPI --> SQLite
  DealAPI --> FS
  PipeAPI --> FS
  Agents --> FS
  Agents -.-> GeminiClient
  DocAPI --> FS
  ReportAPI --> FS
  DBAPI --> FS
  CDL --> FS
```

---

## 4. Physical / monorepo structure

```text
agetic-cdd/
├── apps/
│   ├── web/                 # Next.js 15 UI (:3000)
│   │   └── src/
│   │       ├── app/         # Routes: /, /login, /register, /deals/[id], …
│   │       ├── components/  # deal · auth · portfolio
│   │       └── lib/         # api.ts · auth-store
│   └── api/                 # FastAPI (:4600)
│       └── src/agetic_cdd_api/
│           ├── app.py · main.py · settings.py · db.py
│           ├── routers_*.py
│           ├── services_*.py · agent_document_*.py
│           ├── pipeline_catalog.py · deep_dive_roles.py
│           └── report_*.py
├── docs/
│   ├── architecture/        # This document
│   ├── deploy/              # Docker · GCP
│   └── security/
├── Dockerfile.api · Dockerfile.web · docker-compose.yml
└── scripts/deploy-artifact-registry.sh
```

| Process | Port | Image |
|---------|------|--------|
| Web | 3000 (host may remap) | `agetic-cdd-web` |
| API | 4600 | `agetic-cdd-api` |

---

## 5. Component design

### 5.1 Web application (`apps/web`)

```mermaid
flowchart LR
  subgraph Routes
    Home["/  Portfolio"]
    Login["/login"]
    Reg["/register"]
    Deal["/deals/[id]"]
    Cov["/deals/[id]/coverage"]
    Status["/status"]
  end

  subgraph DealWorkspace
    D[Dashboard]
    V[VDR]
    W[Workflow]
    Doc[Documents]
    R[Reports]
    DB[Databook]
  end

  Home --> Deal
  Deal --> DealWorkspace
  Login --> Home
  Reg --> Home
```

**Deal workspace views** (`?view=`):

| View | Responsibility |
|------|----------------|
| `dashboard` | Deal summary / status |
| `vdr` | Upload & inventory Virtual Deal Room files |
| `workflow` | Run / monitor 5-phase agent pipeline |
| `documents` | Per-agent Document Workspace + copilot |
| `reports` | Generate / download IC packs |
| `databook` | Financial fact extract · DQ · promote |

Auth state: client JWT + refresh via `lib/auth-store` calling `/api/v1/auth/*`.

### 5.2 API application (`apps/api`)

```mermaid
flowchart TB
  Uvicorn[Uvicorn · agetic_cdd_api.app:app]

  subgraph Routers["/api/v1"]
    A["/auth"]
    D["/deals · portfolios"]
    DR["dealroom · VDR · library · databook"]
    DOC["documents · agent docs"]
    P["pipeline · SSE"]
    R["reports"]
    H["/health"]
  end

  Uvicorn --> Routers
  A --> AuthSvc[services_auth]
  D --> DealSvc[services_deals]
  DR --> VDR[services_vdr]
  DR --> Lib[services_library]
  DR --> DataB[services_databook_*]
  DOC --> DocSvc[services_documents]
  P --> Pipe[services_pipeline_run]
  R --> Builders[report_* builders]
```

| Router module | Surface |
|---------------|---------|
| `routers_auth.py` | register · login · refresh · logout · me |
| `routers_deals.py` | portfolio / deal CRUD helpers |
| `routers_dealroom.py` | VDR, library, databook, dashboard |
| `routers_documents.py` | Document Workspace + agent markdown |
| `routers_pipeline.py` | Roadmap, phase run, SSE progress |
| `routers_reports.py` | Generate, status, download, storyline |

---

## 6. Authentication & session design

```mermaid
sequenceDiagram
  participant U as Browser
  participant W as Next.js
  participant A as API /auth
  participant DB as SQLite

  U->>W: Open /login
  U->>A: POST /auth/login {email, password}
  A->>DB: Verify user + org membership
  A-->>U: access_token (JWT) + refresh_token
  Note over U: Access JWT: sub, org, member, type=access

  U->>A: API calls Authorization: Bearer access
  A-->>U: 200 / 401

  U->>A: POST /auth/refresh {refresh_token}
  A->>DB: Rotate refresh (hash store)
  A-->>U: New access + refresh

  U->>A: POST /auth/logout
  A->>DB: Revoke refresh family
```

| Token | Lifetime (default) | Storage |
|-------|--------------------|---------|
| Access JWT (HS256) | 24 hours | Client memory / store |
| Refresh (opaque) | 30 days | Hashed in SQLite `refresh_tokens` |

Production: set `AGETIC_CDD_JWT_SECRET` via Secret Manager; never ship defaults.

---

## 7. Deal room & data architecture

### 7.1 Logical entities

```mermaid
erDiagram
  ORGANIZATION ||--o{ MEMBERSHIP : has
  USER ||--o{ MEMBERSHIP : joins
  ORGANIZATION ||--o{ DEAL : owns
  DEAL ||--o{ PIPELINE_RUN : tracks
  DEAL ||--o{ VDR_FILE : contains
  DEAL ||--o{ AGENT_OUTPUT : produces
  DEAL ||--o{ REPORT : exports
  DEAL ||--o| DATABOOK : has

  ORGANIZATION {
    string id
    string name
  }
  USER {
    string id
    string email
  }
  DEAL {
    string id
    string slug
    string company
    string sector
  }
```

Metadata (users, orgs, deals, pipeline run rows) → **SQLite**.  
Heavy artifacts (VDR bytes, extracts, agent JSON, reports) → **deal filesystem**.

### 7.2 Deal filesystem layout

```text
{AGETIC_CDD_DEALS_STORAGE_PATH}/<slug>/
├── documents/              # Raw VDR uploads
├── library/                # Central Data Library (CDL)
│   ├── index.json
│   ├── routing.json
│   ├── search.db           # FTS
│   ├── documents/*.json    # Extracted text / tables / chunks
│   ├── foundation_roles/   # F-01… context packs
│   ├── agents/<slug>/      # document.md · versions · messages
│   ├── deep_dive_findings.json
│   └── verdict_store.json
├── outputs/<agent_key>.json
├── reports/
│   ├── report_meta.json
│   └── <report_type>/      # .pptx .pdf .docx .xlsx
└── databook/
    ├── meta.json · extract.json · blocks.json
    ├── issues.json · promoted.json · decisions.jsonl
```

```mermaid
flowchart LR
  Upload[VDR upload] --> Documents[documents/]
  Documents --> Ingest[Ingest / extract / classify]
  Ingest --> Library[library/]
  Library --> Agents[Agent runs]
  Agents --> Outputs[outputs/*.json]
  Library --> Databook[databook/]
  Databook -->|promoted metrics| Reports
  Outputs --> Reports[reports/]
```

---

## 8. Pipeline architecture (44 agents, 5 phases)

Source of truth: `pipeline_catalog.py`.

```mermaid
flowchart TB
  subgraph P1["Phase 1 — Data Ingestion (2)"]
    A1[deal_context_and_objectives]
    A2[scope_and_methodology]
  end

  subgraph P2["Phase 2 — Foundations (6)"]
    F1[company_background]
    F2[strategic_direction]
    F3[management_quality]
    F4[regulatory_compliance]
    F5[ip_and_technology]
    F6[esg_and_sustainability]
  end

  subgraph P3["Phase 3 — Deep Dive (24)"]
    M[Market track]
    C[Competitive track]
    Cu[Customer track]
    O[Ops track]
    Fi[Financial track]
    R[Risk / Opportunity track]
  end

  subgraph P4["Phase 4 — Final Verdict (7)"]
    V1[execution_risk]
    V2[compensation_alignment]
    V3[trading_comps]
    V4[precedent_transactions]
    V5[valuation_modeling]
    V6[ic_synthesis]
    V7[recommendation]
  end

  subgraph P5["Phase 5 — Reports (5)"]
    R1[strategy_report]
    R2[market_intel_deck]
    R3[operations_dashboard]
    R4[ic_memo]
    R5[cdd_deck]
  end

  P1 --> P2 --> P3 --> P4
  P4 --> P5
  P3 --> P5
```

### 8.1 Phase run control flow

```mermaid
sequenceDiagram
  participant UI as Workflow UI
  participant API as Pipeline API
  participant Lib as CDL / Library
  participant Ag as Agent composers
  participant Out as outputs/

  UI->>API: Start phase N (or Run all)
  API->>API: Assert phase N-1 complete
  API-->>UI: SSE progress events

  alt Phase 1 Ingestion
    API->>Lib: ingest_vdr_to_library
    API->>Ag: deal_context · scope
  else Foundations / Deep Dive / Verdict
    API->>Lib: Bind docs by routing / needles
    API->>Ag: Run agent specs + markdown
  end

  Ag->>Out: Write outputs/{slug}.json
  Ag->>Lib: Update agent document / stores
  API-->>UI: Phase complete / blocked / error
```

### 8.2 Deep Dive dependency idea

Deep Dive agents form a **DAG** (`deep_dive_roles.py`): many depend on `market_definition` approval and selected Foundation codes (F-01…F-06). Downstream market agents wait until perimeter is approved.

```mermaid
flowchart LR
  F05[F-05 Company Background] --> MD[market_definition]
  MD --> MV[market_volume_and_growth]
  MD --> MP[market_pricing]
  MD --> DD[demand_drivers]
  MD --> CI[competitor_identification]
  CI --> CD[competitive_differentiation]
  MV --> MSS[market_share_strategy]
```

---

## 9. End-to-end diligence journey

```mermaid
flowchart TB
  Start([Create dealroom]) --> Upload[Upload VDR files]
  Upload --> Ingest[Run Data Ingestion]
  Ingest --> Found[Run Foundations]
  Found --> OptionalDB[Optional: Databook extract & promote]
  OptionalDB --> DD[Run Deep Dive]
  DD --> FV[Run Final Verdict]
  FV --> Gen[Generate reports]
  Gen --> Review[Analyst review in Documents / Reports]
  Review --> Export[Download pptx / pdf / docx / xlsx]
  Export --> End([IC pack ready])
```

### 9.1 VDR → Library → Agent → Report (detail)

```mermaid
flowchart LR
  subgraph Ingest
    ZIP[PDF · XLSX · DOCX · PPTX · TXT]
    Ext[Extract text / tables]
    Class[CDL classify + route]
    FTS[FTS index]
  end

  subgraph Analyze
    Found[Foundation agents]
    Deep[Deep Dive agents]
    Verd[Verdict agents]
  end

  subgraph Compose
    Story[Storyline sections]
    Build[Report builders]
    Art[Artifacts]
  end

  ZIP --> Ext --> Class --> FTS
  Class --> Found --> Deep --> Verd
  Found --> Story
  Deep --> Story
  Verd --> Story
  Story --> Build --> Art
```

---

## 10. Databook design

**Role:** Reconciled financial fact layer so reports don’t invent P&L / KPI arithmetic from prose alone.

```mermaid
flowchart TB
  Lib[Library tables / workbooks] --> Extract[Extract blocks]
  Extract --> Issues[DQ / conflicts]
  Issues --> Decide{Analyst decision}
  Decide -->|accept / correct / vouch / drop| Promote[promoted.json]
  Promote --> Reports[CDD Deck · IC Memo · …]
  Promote --> Agents[Optional agent consumption]
```

| Artifact | Meaning |
|----------|---------|
| `extract.json` / `blocks.json` | Candidate figures from VDR |
| `issues.json` | Conflicts, gaps, DQ flags |
| `decisions.jsonl` | Audit of analyst actions |
| `promoted.json` | Figures safe for report builders |

UI: Deal → **Databook** (+ DQ affordances on VDR).

---

## 11. Document Workspace & LLM boundary

```mermaid
flowchart TB
  AgentOut[Agent structured spec + markdown] --> DocWS[Document Workspace UI]
  DocWS --> Copilot[Copilot messages / suggestions]
  Copilot --> Synth{document_synthesis_llm<br/>+ Gemini key?}
  Synth -->|yes| Gemini[services_gemini.generate_json]
  Synth -->|no| Heur[Heuristic / template only]
  Gemini --> DocWS
  Heur --> DocWS
```

| Flag | Effect |
|------|--------|
| `AGETIC_CDD_DOCUMENT_SYNTHESIS_LLM` | Document Workspace synthesis |
| `AGETIC_CDD_DEEP_DIVE_LLM` | Optional hybrid refine on selected Deep Dive agents |
| Empty `AGETIC_CDD_GEMINI_API_KEY` | Always safe heuristic path |

Central LLM adapter: `services_gemini.py` → `generate_json(system, user) → dict | None`.

---

## 12. Report architecture

| Store key | Catalog / UI name | Format | Builder |
|-----------|-------------------|--------|---------|
| `cdd_deck` | CDD Deck | `.pptx` | `report_cdd_deck.py` |
| `ic_memo` | IC Memo | `.pdf` | `report_ic_memo.py` |
| `market_deck` | Market Intel Deck | `.pptx` | `report_market_deck.py` |
| `strategy_report` | Strategy Report | `.docx` | `report_strategy.py` |
| `ops_dashboard` | Operations Dashboard | `.xlsx` | `report_ops_dashboard.py` |

```mermaid
flowchart TB
  Out[outputs/*.json] --> Ctx[BuildContext]
  Promo[databook promoted] --> Ctx
  Ctx --> Sections[Storyline sections]
  Sections --> Export[export_artifact]
  Export --> Files[reports/<type>/artifact]
  Export --> Meta[report_meta.json + Sources / decision chain]
```

Builders **prefer structured agent specs** (TAM/SAM/SOM, ownership, KPIs) over re-deriving from raw VDR inside the report UI.

---

## 13. Cross-cutting consistency (design rule)

Same deal, same pipeline run → **shared agent outputs are the source of truth**.

```mermaid
flowchart LR
  SoT[Agent output SoT<br/>outputs + library specs]
  SoT --> IC[IC Memo]
  SoT --> CDD[CDD Deck]
  SoT --> Mkt[Market Deck]
  SoT --> Strat[Strategy Report]
  SoT --> Ops[Ops Dashboard]
```

Report-layer patches may sanitize display, but **numbers and perimeter text must be fixed in agents** (e.g. `market_definition`, `company_background`) so all five reports agree.

---

## 14. Technology stack

| Layer | Choice |
|-------|--------|
| UI | Next.js 15 · React 19 · TypeScript · Tailwind |
| API | Python 3.12 · FastAPI · Uvicorn · Pydantic Settings |
| ORM / auth DB | SQLAlchemy 2 · SQLite (Postgres-ready URL later) |
| Documents | pypdf · python-docx · openpyxl · python-pptx · reportlab |
| Search | SQLite FTS in `library/search.db` |
| LLM | Google Gemini REST (optional) |
| Containers | Docker multi-stage · Compose · Artifact Registry |
| Config | `AGETIC_CDD_*` env vars |

---

## 15. Non-functional design

| Concern | Approach |
|---------|----------|
| **Security** | JWT + refresh rotation; CORS allowlist; production forbids localhost/HTTP origins; secrets outside images |
| **Multi-tenancy** | Org membership on every deal access |
| **Durability** | Persist `/data` (SQLite + deals); snapshots on GCP PD |
| **Scalability (today)** | Single API writer for filesystem + SQLite |
| **Scalability (target)** | Cloud SQL + object storage adapter before horizontal API |
| **Observability** | `/api/v1/health`; pipeline SSE; Cloud Logging on GCP |
| **Performance** | Long pipeline/report jobs need raised timeouts / always-on CPU in Cloud Run |

---

## 16. Deployment architecture (summary)

```mermaid
flowchart TB
  Dev[Git / local] --> CB[Cloud Build]
  CB --> AR[Artifact Registry<br/>agetic-cdd-api · agetic-cdd-web]

  AR --> PathA[Path A: GCE + Compose + Persistent Disk]
  AR --> PathB[Path B: Cloud Run + shared store]

  PathA --> UsersA[Users via HTTPS]
  PathB --> UsersB[Users via HTTPS LB]
```

**Recommended first production:** Path A (matches current filesystem design).  
Full GCP detail: [GCP_ARCHITECTURE.md](../deploy/GCP_ARCHITECTURE.md).

---

## 17. Key API surface (quick map)

```text
POST   /api/v1/auth/register|login|refresh|logout
GET    /api/v1/auth/me
GET    /api/v1/health

# Deals / VDR / library / databook  (dealroom + deals routers)
# Documents / agent workspace
# Pipeline roadmap + phase execution (SSE)
# Reports generate / events / download / status
```

Exact paths live in `routers_*.py`; web client wrappers in `apps/web/src/lib/api.ts`.

---

## 18. Design decisions log (selected)

| Decision | Rationale |
|----------|-----------|
| Filesystem deal rooms | Fast iteration; rich binary + JSON artifacts; simple backup |
| Phase-gated pipeline | Prevents Deep Dive/Verdict on empty library |
| Heuristic-first agents | Deterministic extraction; LLM is enrichment not sole source |
| Shared agent SoT for reports | Stops cross-document number drift |
| Separate web/API containers | Independent scale and release of UI vs compute |
| Gemini behind thin adapter | Swap provider later without rewriting agents |

---

## 19. How to read this document

| Audience | Start here |
|----------|------------|
| New engineer | §§2–5, 7–9 |
| Pipeline / agent owner | §§8–11, 13 |
| Report / UI owner | §§5.1, 11–13 |
| DevOps / GCP | §§16 + [GCP deploy doc](../deploy/GCP_ARCHITECTURE.md) |
| Security review | §15 + `docs/security/` |

---

## 20. Related source anchors

| Topic | Path |
|-------|------|
| App wiring | `apps/api/src/agetic_cdd_api/app.py` |
| Pipeline catalog | `pipeline_catalog.py` |
| Deep Dive DAG | `deep_dive_roles.py` |
| Phase runner | `services_pipeline_run.py` |
| VDR / library | `services_vdr.py`, `services_library.py` |
| Databook | `services_databook_*.py` |
| Reports registry | `report_store.py` |
| Settings | `settings.py` |
| Deal UI shell | `apps/web/src/components/deal/DealWorkspace.tsx` |

---

*Version: 2026-04-02 · Application architecture with flowcharts and design rationale for Agentic CDD.*
