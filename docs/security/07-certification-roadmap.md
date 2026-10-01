# Certification Roadmap

**Document:** 07 — Certification & assurance roadmap  
**Version:** 1.0  
**Status:** Planning (dates are targets — replace with committed milestones)  
**Classification:** Internal / client-facing under NDA  

---

## 1. Current state

| Scheme | Status |
|---|---|
| Cyber Essentials | Not certified — control map drafted |
| Cyber Essentials+ | Not certified |
| ISO/IEC 27001 | Not certified — policy pack drafted |
| SOC 2 Type I / II | Not certified |

**Interim assurance:** This documentation pack (overview, policies, FAQ, CE map).

## 2. Recommended sequence

```text
Stabilise prod hardening
        ↓
Cyber Essentials (baseline)
        ↓
Cyber Essentials+ (verified technical testing)
        ↓
ISO 27001 (ISMS)  and/or  SOC 2 Type I → Type II
```

Rationale: CE is faster for UK buyers; ISO/SOC demonstrate ongoing management system / trust services criteria for larger enterprises.

## 3. Target milestones (edit before sending)

| Milestone | Target window | Exit criteria |
|---|---|---|
| M0 — Hardening baseline | _e.g. 0–4 weeks_ | Unique secrets, TLS, MFA for admin, backups defined, seed admin disabled, LLM policy decided |
| M1 — Cyber Essentials | _e.g. 1–2 months_ | Scope defined; questionnaire passed; certificate issued |
| M2 — Cyber Essentials+ | _e.g. +1–2 months_ | Vulnerability assessment / test passed; CE+ certificate |
| M3 — ISO 27001 Stage 1/2 **or** SOC 2 Type I | _e.g. 4–9 months_ | SoA / control evidence; auditor report or certificate |
| M4 — SOC 2 Type II (if pursued) | _e.g. +3–12 months observation_ | Type II report covering operating period |

## 4. Workstreams

| Workstream | Examples |
|---|---|
| People | Security Owner named; security awareness; offboarding |
| Process | Risk register; change; incident; supplier; access reviews |
| Technology | RBAC enforcement; platform audit log; session hardening; upload malware scanning; volume encryption verified |
| Evidence | Screenshots, tickets, logs, pen-test report, training records |
| Commercial | DPA, subprocessor list, security schedule in MSA |

## 5. Product engineering priorities that unlock audits

1. Enforce permission checks on sensitive routes (not only org membership)  
2. Platform audit events: login, failed auth, export, membership change, deal delete  
3. HttpOnly secure cookie sessions or equivalent (reduce XSS token theft)  
4. Documented private mode (no external LLM) as a first-class deploy profile  
5. Backup/restore runbook with test evidence  

## 6. Budget & partners (placeholders)

| Item | Notes |
|---|---|
| CE / CE+ assessor | IASME-certified body |
| ISO CB | UKAS-accredited certification body |
| SOC 2 CPA firm | AICPA AT-C 105/205 engagement |
| Pen test firm | CREST / CHECK preferred for CE+ / ISO evidence |

## 7. What we will tell customers until then

> Genovation has not yet completed ISO 27001, Cyber Essentials+, or SOC 2. We provide an assurance documentation pack describing current controls and limitations, and a roadmap toward formal certification. We will share certificates and reports only when independently issued.

---

## Approval

| Name | Role | Date |
|---|---|---|
| _TBD_ | Leadership sponsor | |
| _TBD_ | Information Security Owner | |
