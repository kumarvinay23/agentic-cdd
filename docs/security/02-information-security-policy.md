# Information Security Policy

**Document:** 02 — Information Security Policy  
**Version:** 1.0  
**Status:** Draft for internal adoption (shareable under NDA)  
**Aligned to:** ISO/IEC 27001:2022 themes (control intent — **not** a certified ISMS)  
**Classification:** Confidential  

---

## 1. Purpose

This policy establishes Genovation’s commitments for protecting information processed by **Agentic CDD**, including customer deal-room data, identity data, and derived diligence artefacts.

## 2. Scope

Applies to:

- Agentic CDD application components (web, API, databases, deal file stores)  
- Personnel and contractors with access to production or customer environments  
- Supporting infrastructure under Genovation or customer control for a given deployment  

Out of scope of this policy text alone: issuance of third-party certificates (ISO / CE+ / SOC 2).

## 3. Policy statements

### 3.1 Leadership and accountability

- A named **Information Security Owner** is responsible for this policy and for the certification roadmap.  
- Material security incidents are escalated to leadership and, where contractually required, to affected customers.

### 3.2 Risk management

- Security risks to confidentiality, integrity, and availability of deal data are identified, assessed, and treated.  
- Residual risks (including uncertified status) are disclosed to customers when relevant.

### 3.3 Access control

- Access is granted on least privilege and need-to-know.  
- Organisation tenancy is enforced for deal data.  
- Accounts are removed or disabled promptly on offboarding.

### 3.4 Cryptography and secrets

- Passwords are stored using modern one-way hashing (bcrypt).  
- JWT signing secrets and API keys are environment secrets — never committed to source control.  
- Production secrets are unique and rotated on compromise or personnel change.  
- TLS is required for production network paths.

### 3.5 Operations security

- Changes to production follow review and controlled release practices appropriate to deployment size.  
- Backups of metadata and deal workspaces are defined per deployment (customer or Genovation responsibility as contracted).  
- Vulnerability management: dependencies and base images are updated on a defined cadence; critical issues are prioritised.

### 3.6 Secure development

- Security-relevant changes (auth, tenancy, export, databook decisions) receive heightened review.  
- Default credentials and sample secrets must not ship to production.

### 3.7 Supplier and AI processing

- Use of external AI / cloud subprocessors is **opt-in by configuration** and documented to the customer.  
- Where the customer forbids external processing, Genovation configures deployments without provider API keys.

### 3.8 Logging and evidence

- Databook reviewer decisions are retained in append-only deal audit trails.  
- Platform-wide security event logging is a continuous improvement item; interim evidence may include application logs and infrastructure logs from the host environment.

### 3.9 Incident management

- Suspected incidents follow the Incident Response Outline (document 04).  
- Customer notification timelines follow contract / DPA terms.

### 3.10 Business continuity

- Recovery objectives (RTO/RPO) are agreed per deployment.  
- Deal workspace and database backup restore is tested periodically.

## 4. Roles

| Role | Duties |
|---|---|
| Information Security Owner | Policy ownership, risk register, client assurance responses |
| Engineering lead | Control implementation, secure defaults, dependency hygiene |
| Deal / customer success | Ensure customers understand shared responsibilities |
| All staff | Report incidents; protect credentials; follow least privilege |

## 5. Exceptions

Exceptions require written approval by the Information Security Owner, time bounds, and compensating controls.

## 6. Review

This policy is reviewed at least annually, and after material architecture or certification milestones.

---

**Approval**

| Name | Role | Date | Signature |
|---|---|---|---|
| _TBD_ | Information Security Owner | | |
| _TBD_ | Engineering lead | | |
