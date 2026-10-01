# Access Control & Data Handling Standard

**Document:** 03 — Access control and data handling  
**Version:** 1.0  
**Status:** Draft for internal adoption (shareable under NDA)  
**Classification:** Confidential  

---

## 1. Identity and authentication

| Control | Implementation |
|---|---|
| Unique user accounts | Email-based registration / login |
| Password storage | bcrypt hashes in application DB |
| Session | Short-lived JWT access token + hashed refresh token |
| Logout | Refresh token revoked |
| Production hardening | Unique `JWT_SECRET`; disable or change seed admin; prefer shorter access TTL |

**Client guidance:** Prefer SSO / IdP federation for enterprise deployments — roadmap item if not yet available in a given release.

## 2. Authorisation model

### 2.1 Organisation tenancy (enforced)

1. Authenticated request establishes user ↔ membership ↔ organisation.  
2. Deal identifiers are resolved only where `deal.organization_id` matches the caller’s organisation.  
3. VDR upload/download, pipeline, documents, reports, and databook APIs inherit that binding.

### 2.2 Role catalogue (present)

Roles such as `owner`, `admin`, and `user` map to permission strings (organisation administration, deals, pipeline, reports, audit read, etc.).

### 2.3 Enforcement maturity

| Layer | Status |
|---|---|
| Org-level deal isolation | Implemented |
| Route-level permission checks per string | Incomplete — treat all org members as deal-capable unless host IAM further restricts |
| Admin audit of permission changes | Roadmap |

Until fine-grained RBAC is fully enforced, **limit organisation membership** to trusted deal-team users and use separate organisations per client confidentiality boundary where required.

## 3. Data classification

| Level | Examples | Handling |
|---|---|---|
| Restricted | VDR files, agent findings, reports, databook promoted figures | Org-scoped; no public sharing; encrypt backups; NDA |
| Internal | Config, non-production logs | Least privilege |
| Public | Marketing site copy | No deal data |

## 4. Data lifecycle

| Stage | Control |
|---|---|
| Collection | Users upload only authorised VDR materials |
| Processing | Agents and databook operate inside the deal workspace |
| Storage | Metadata in DB; blobs under deal path (configurable storage root) |
| Retention | Per customer contract; default = retain until deal deletion / contract end |
| Deletion | Delete deal workspace + metadata on authorised request; confirm backup purge as contracted |
| Export | Report downloads and databook Excel/CSV export are authenticated org-scoped actions |

## 5. Databook-specific handling

- Held-out figures remain visible for review but are **not** treated as promoted canon until Correct / Vouch / Accept.  
- Import of edited Excel applies **Correct** decisions with audit reasons.  
- Promoted metrics may feed agents and reports — integrity depends on reviewer discipline as well as controls.

## 6. Subprocessors / external AI

| Path | Default | Customer action |
|---|---|---|
| Local heuristics / local models | Preferred for private mode | Leave provider keys unset |
| External LLM API (if configured) | Opt-in | Approve in contract; review provider DPA |

## 7. Administrative access

- Host / database / filesystem access for operators uses separate credentials from application users.  
- Production access is logged at the infrastructure layer where available.  
- Break-glass access is time-limited and recorded.

## 8. Prohibited

- Sharing deal data outside the organisation without authorisation  
- Using production deal data in uncontrolled personal AI tools  
- Committing secrets or customer VDR samples to public repositories  
