# Agentic CDD — Information Security Assurance Pack

**Organisation:** Genovation Technological Solutions  
**Product:** Agentic CDD (Commercial Due Diligence platform)  
**Document set version:** 1.0  
**Status:** Internal / client-facing assurance documentation  
**Last updated:** 2026-09-17  

---

## Important — read first

These documents describe **how we design and operate security controls** for Agentic CDD. They are **not**:

- An ISO/IEC 27001 certificate  
- A Cyber Essentials or Cyber Essentials+ certificate  
- A SOC 2 Type I or Type II report  
- An independent auditor attestation  

Certificates and SOC reports are issued only by accredited third parties after assessment. **We do not currently hold ISO 27001, Cyber Essentials+, or SOC 2.** Sharing this pack is an interim transparency measure while certification is pursued (see [07-certification-roadmap.md](./07-certification-roadmap.md)).

Do not alter branding or wording to imply certification that has not been obtained.

---

## Pack contents

| # | Document | Audience | Purpose |
|---|---|---|---|
| 01 | [Security overview](./01-security-overview.md) | Client / prospect | Architecture, tenancy, data classes, honest scope |
| 02 | [Information security policy](./02-information-security-policy.md) | Internal (+ client under NDA) | ISMS-oriented policy commitments |
| 03 | [Access control & data handling](./03-access-control-and-data-handling.md) | Internal (+ client under NDA) | Auth, tenancy, data lifecycle |
| 04 | [Incident response outline](./04-incident-response-outline.md) | Internal (+ client under NDA) | Detect → contain → notify |
| 05 | [Cyber Essentials control map](./05-cyber-essentials-control-map.md) | Internal | Self-assessment vs CE themes |
| 06 | [Client security FAQ](./06-client-security-faq.md) | Client | Questionnaire-style answers |
| 07 | [Certification roadmap](./07-certification-roadmap.md) | Client / leadership | Path to CE → CE+ → ISO / SOC 2 |

---

## Suggested client send set (under NDA)

1. This README (disclaimer)  
2. `01-security-overview.md`  
3. `06-client-security-faq.md`  
4. `07-certification-roadmap.md`  
5. Optionally `02`–`04` if the client asks for policy depth  

---

## Ownership

| Role | Responsibility |
|---|---|
| Product / Engineering lead | Keep technical facts accurate as the platform evolves |
| Security / Compliance owner (designate) | Policy approval, client responses, certification programme |
| Legal / commercial | NDA, DPA, contract security schedules |

**Classification:** Confidential — client distribution only under NDA unless otherwise approved.
