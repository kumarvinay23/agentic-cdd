# Cyber Essentials — Control Map (Self-Assessment Aid)

**Document:** 05 — Cyber Essentials control map  
**Version:** 1.0  
**Status:** Internal preparation aid  
**Note:** Completing this table does **not** grant Cyber Essentials certification. Certification requires the official IASME / NCSC scheme assessment.  

---

## How to use

1. For each control theme, record **current state**, **owner**, and **gap action**.  
2. Prefer **Cyber Essentials** first (questionnaire + technical verification for CE+).  
3. Keep evidence links (screenshots, config exports, policies) in a private evidence folder — not in git if they contain secrets.

## Boundary (define before applying)

Document the certification boundary clearly, e.g.:

> Agentic CDD production hosts (API, web, database, deal storage volume) operated by Genovation for Customer X in Region Y. End-user devices are in / out of scope as agreed.

---

## Theme A — Firewalls / boundary

| Requirement (plain language) | Agentic CDD / ops mapping | Status | Gap action |
|---|---|---|---|
| Boundary firewalls / security groups | Deploy behind VPC SG / host firewall; API not exposed without TLS proxy | _TBD_ | Confirm prod SG rules; deny by default |
| Default-deny inbound | Only 443 (and admin jump) open | _TBD_ | Document SG |
| Cloud admin interfaces protected | Cloud console MFA | _TBD_ | Enforce MFA |

## Theme B — Secure configuration

| Requirement | Mapping | Status | Gap action |
|---|---|---|---|
| Remove default passwords | Change / disable seed admin; unique JWT secret | Partial in product defaults | Mandatory prod checklist |
| Unnecessary services disabled | Minimal API + web containers | _TBD_ | Harden images |
| Auto-update or patch process | OS + dependency cadence | _TBD_ | Write patch SLA |

## Theme C — Security update management

| Requirement | Mapping | Status | Gap action |
|---|---|---|---|
| Apply critical patches promptly | Host + container + npm/pip deps | _TBD_ | Dependabot / scheduled reviews |
| Supported software only | Pin supported Node / Python | _TBD_ | Version policy |

## Theme D — User access control

| Requirement | Mapping | Status | Gap action |
|---|---|---|---|
| Unique credentials | App users + host IAM users | Implemented (app) | SSO roadmap |
| MFA for privileged access | Host / IdP MFA | _TBD for hosts_ | Enforce MFA for prod SSH/cloud |
| Least privilege | Org tenancy; limit org members | Partial (RBAC depth) | Route-level perms |
| Remove leavers promptly | Manual process | _TBD_ | Offboarding checklist |

## Theme E — Malware protection

| Requirement | Mapping | Status | Gap action |
|---|---|---|---|
| Malware protection on hosts / endpoints | EDR / AV on servers & admin devices | Ops responsibility | Confirm tooling |
| Upload scanning (optional beyond CE) | VDR uploads | Not productized | Evaluate AV on upload path |

---

## Product-specific notes

- **Deal file store** must sit on encrypted volumes (LUKS / cloud volume encryption).  
- **Browser token storage** is a residual risk; mitigate with short TTL + network controls until cookie-based sessions land.  
- **External LLM keys** — if enabled, document as a subprocessor; for CE boundary, ensure that path is approved.

## Evidence checklist (pre-audit)

- [ ] Network diagram + firewall rules  
- [ ] Patch / update procedure  
- [ ] User list + leaver process  
- [ ] MFA evidence for admin accounts  
- [ ] Malware / EDR status  
- [ ] This assurance pack + Information Security Policy approved  
