# Agentic CDD — Security Overview

**Document:** 01 — Client-facing security overview  
**Version:** 1.0  
**Status:** Assurance documentation (not a certificate)  
**Classification:** Confidential — under NDA  

---

## 1. Purpose

This overview summarises how Agentic CDD protects deal-room data today, what is in scope for a typical private deployment, and what is still on the hardening roadmap. It is intended for security / procurement review.

## 2. Product summary

**Agentic CDD** is an AI multi-agent Commercial Due Diligence platform. Users manage a portfolio of deal rooms, upload Virtual Data Room (VDR) materials, run analytical agents, review a reconciled **Databook** of financial figures, and generate diligence reports.

**Vendor context:** Genovation Technological Solutions.

## 3. Deployment model (current)

| Layer | Technology | Notes |
|---|---|---|
| Web UI | Next.js | Browser application; authenticates to the API with Bearer tokens |
| API | FastAPI (`/api/v1`) | Business logic, auth, deal / VDR / pipeline / reports / databook |
| Metadata | SQLite | Users, organisations, membership, deal metadata, refresh tokens, pipeline runs |
| Deal content | File system under deal workspace | VDR documents, library extracts, agent outputs, reports, databook store |

**Typical private deployment:** API and UI hosted in the customer’s or Genovation’s controlled environment (localhost / VPC / on-prem). Cloud marketplace, air-gapped appliance, and hardware-level crypto envelopes described in executive materials are **target options**, not claims about every current install.

## 4. Data we process

| Class | Examples | Storage |
|---|---|---|
| Identity | Email, name, password hash, org membership | Application database |
| Deal metadata | Deal name, slug, org ownership | Application database |
| VDR content | Financials, legal, commercial, HR packs uploaded by the deal team | Deal workspace `documents/` |
| Derived analytics | Library extracts, agent JSON/findings, reports | Deal workspace `library/`, `outputs/`, `reports/` |
| Databook | Extracted rows, conflicts, promoted metrics, reviewer decisions | Deal workspace `databook/` |

Deal content is typically **highly confidential** (M&A diligence). Treat all deal workspaces as restricted.

## 5. Security controls (implemented)

### 5.1 Authentication

- User registration / login with **bcrypt**-hashed passwords  
- **JWT** access tokens (organisation and membership claims bound on each request)  
- **Refresh tokens** stored hashed (SHA-256); revocable on logout  
- API routes require `Authorization: Bearer <access_token>`

### 5.2 Tenancy / isolation

- Deals are **organisation-scoped**  
- Deal, VDR, pipeline, document, report, and databook APIs resolve the deal only within the caller’s organisation  
- Cross-organisation access by ID alone is rejected by server-side org binding

### 5.3 Application roles (model)

- Membership roles such as `owner`, `admin`, and `user` map to a permission catalogue (organisation, deals, pipeline, reports, audit, etc.)  
- Permission strings are exposed to the client session for UI; **fine-grained permission enforcement on every route is a hardening item** (see §7)

### 5.4 Databook integrity & audit

- Financial figures follow a zero-trust path: extract → map → arithmetic check → hold-out → human decision → promote  
- Reviewer actions (**Correct / Drop / Vouch / Accept**) require a reason and are appended to an audit log (`decisions.jsonl`) in the deal databook store  
- Promoted metrics are preferred by financial agents and selected reports over raw unverified extracts

### 5.5 Transport & CORS

- Production deployments should terminate **TLS** at the reverse proxy / load balancer  
- API CORS uses an **explicit origin allowlist** (`AGETIC_CDD_CORS_ORIGINS`); wildcards (`*`) are rejected  
- Prefer same-origin in production (UI and API behind one reverse proxy) so CORS can stay empty/minimal  
- `AGETIC_CDD_APP_ENV=development` may allow any `localhost` / `127.0.0.1` port via regex; that regex is **disabled in production**, which also rejects loopback and `http://` origins

## 6. Optional external AI processing

If a generative AI provider API key is configured (e.g. for document synthesis), selected content may be sent to that provider under that provider’s terms.  

**For customers who require data to remain on-prem / private:** disable external LLM keys and related synthesis flags so analysis stays on local / customer-controlled models and heuristics.

## 7. Current limitations (transparent)

We disclose these so reviewers can judge residual risk:

| Topic | Current state |
|---|---|
| ISO 27001 / CE+ / SOC 2 | **Not certified** — roadmap documented separately |
| Application-level encryption at rest | Rely on host / volume encryption; app-layer AES envelope not productized in this codebase |
| Platform-wide audit log (login, export, admin) | Permission catalogue includes audit; full platform audit module is roadmap |
| Fine-grained RBAC enforcement | Org tenancy enforced; per-permission route gates incomplete |
| OCR for scanned PDFs | Limited / out of scope for weak scans — may yield incomplete extract |
| Default secrets in sample env | Must be rotated for any shared or production environment |
| Browser token storage | Access/refresh material in client storage — harden with HttpOnly cookies / shorter TTL for production |

## 8. Customer responsibilities (shared model)

- Provide and manage identity of authorised deal-team users  
- Classify and upload only authorised VDR content  
- Configure TLS, backups, host hardening, and network controls for the deployment environment  
- Decide whether external LLM providers are permitted  
- Apply organisational policies for device security and offboarding  

## 9. Contact

For security questionnaires, DPAs, or certification status updates, contact your Genovation commercial lead, who will route to the designated security owner.

---

*This document does not constitute a certification, warranty of fitness for a particular regulatory regime, or independent audit opinion.*
