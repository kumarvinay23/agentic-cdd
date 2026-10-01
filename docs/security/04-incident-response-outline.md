# Incident Response Outline

**Document:** 04 — Incident response outline  
**Version:** 1.0  
**Status:** Draft playbook (shareable under NDA)  
**Classification:** Confidential  

---

## 1. Purpose

Define how Genovation detects, contains, eradicates, and communicates security incidents affecting Agentic CDD or customer deal data.

## 2. What is an incident

Examples:

- Unauthorised access to an organisation or deal workspace  
- Credential compromise (JWT secret, admin password, API keys)  
- Ransomware / destructive access to deal file stores  
- Accidental disclosure (mis-sent export, wrong org membership)  
- Suspected abuse of an external AI path involving customer content  

## 3. Severity

| Level | Example | Response target |
|---|---|---|
| Critical | Confirmed breach of customer VDR / deal data | Immediate containment; leadership + customer notify per contract |
| High | Credential leak with possible access | Hours |
| Medium | Suspected anomaly, limited blast radius | Same business day |
| Low | Policy deviation without data exposure | Planned fix |

## 4. Response phases

### 4.1 Detect

- Customer report  
- Staff observation  
- Infrastructure / application alerts (where deployed)  
- Unusual databook / export / auth activity  

### 4.2 Triage

- Assign incident lead  
- Preserve evidence (logs, timestamps, affected deal IDs)  
- Classify severity  

### 4.3 Contain

- Revoke refresh tokens / rotate JWT secret if tokens may be forged  
- Disable compromised accounts  
- Isolate host or revoke network access as needed  
- Disable external LLM keys if that path is implicated  

### 4.4 Eradicate & recover

- Patch root cause  
- Restore from known-good backups if integrity lost  
- Re-issue credentials  

### 4.5 Notify

- Internal: Security Owner + Engineering lead  
- External: Affected customers per DPA / MSA (do not wait for perfect forensics if contract requires early notice)  
- Regulators: only if legally required (e.g. personal data under UK GDPR)  

### 4.6 Lessons learned

- Post-incident review within 10 business days for High/Critical  
- Update policies, controls, and this outline  

## 5. Contacts (fill before client use)

| Role | Name | Contact |
|---|---|---|
| Incident lead (primary) | _TBD_ | |
| Deputy | _TBD_ | |
| Customer notification owner | _TBD_ | |
| Legal counsel | _TBD_ | |

## 6. Evidence retention

Retain incident records, timeline, and decisions for at least **12 months** or longer if litigation / regulation requires.
