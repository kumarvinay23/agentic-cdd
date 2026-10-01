# Client Security FAQ

**Document:** 06 — Client security questionnaire answers  
**Version:** 1.0  
**Product:** Agentic CDD  
**Vendor:** Genovation Technological Solutions  
**Classification:** Confidential — under NDA  

**Disclaimer:** Answers describe current product and operating intent. They are **not** an ISO 27001, Cyber Essentials+, or SOC 2 attestation.

---

## A. Certification & compliance

**Q: Do you hold ISO 27001?**  
**A:** Not at this time. We maintain an ISO-aligned policy set and a certification roadmap. We can share progress and target dates on request.

**Q: Do you hold Cyber Essentials / Cyber Essentials+?**  
**A:** Not at this time. We have prepared an internal Cyber Essentials control map and intend CE as the first formal scheme.

**Q: Do you have a SOC 2 report?**  
**A:** Not at this time. SOC 2 Type I/II is on the roadmap after baseline CE / ISMS maturity.

**Q: Can you provide a certificate PDF for diligence?**  
**A:** We will only provide certificates issued by accredited bodies. We will not fabricate or simulate certificates. We can provide this assurance pack, policies, and (when available) real reports under NDA.

## B. Architecture & data

**Q: Where does customer data reside?**  
**A:** Deal metadata in the application database; VDR files and derived artefacts in an organisation-scoped deal workspace on the configured storage path. Location is determined by the deployment (customer VPC / Genovation-hosted private environment as contracted).

**Q: Is data encrypted in transit?**  
**A:** Production deployments should use TLS terminated at the reverse proxy / load balancer. HTTP-only local development is not a production posture.

**Q: Is data encrypted at rest?**  
**A:** We rely on infrastructure volume / disk encryption for the database and deal file store. Application-layer field encryption is not the primary control in the current release.

**Q: Do you use our data to train public AI models?**  
**A:** We do not use customer deal data to train Genovation public models. If an optional third-party LLM API is enabled for a deployment, content may be processed under that provider’s terms — this path is configuration-controlled and can be left disabled for private mode.

**Q: Multi-tenant isolation?**  
**A:** Yes at organisation level. Deals and APIs are resolved only within the authenticated user’s organisation.

## C. Access control

**Q: How do users authenticate?**  
**A:** Email and password (bcrypt). API access uses JWT bearer tokens with revocable refresh tokens.

**Q: SSO / SAML / OIDC?**  
**A:** Enterprise SSO is a common customer requirement and is tracked as a hardening / roadmap item for deployments that need it. Confirm availability for your contracted release.

**Q: MFA?**  
**A:** Application MFA may not be universal in all builds; production **operator** access should use MFA via IdP / cloud console. Confirm app MFA status for your release.

**Q: Role-based access?**  
**A:** Organisation roles and a permission catalogue exist. Deal access is org-scoped. Fine-grained permission enforcement on every API route is still maturing — we recommend tight membership lists.

## D. Logging, audit, monitoring

**Q: Are security events logged?**  
**A:** Infrastructure and application logs depend on deployment. Databook reviewer decisions (Correct / Drop / Vouch / Accept) are written to an append-only deal audit trail with reasons. A full platform security audit module is on the roadmap.

**Q: Log retention?**  
**A:** Agreed per contract / hosting design (recommend ≥ 90 days online, longer cold storage for regulated customers).

## E. Secure development & testing

**Q: Do you perform penetration tests?**  
**A:** We recommend / schedule independent pen tests as part of the certification programme. Share the latest executive summary under NDA when available; absence of a recent test should be treated as a gap, not as “secure by default.”

**Q: Vulnerability management?**  
**A:** Dependency and host patching on a defined cadence; critical issues prioritised. Ask for the current patch SLA in your security schedule.

## F. Operations & continuity

**Q: Backups?**  
**A:** Database and deal workspace backups are a deployment responsibility (Genovation or customer) with restore testing. RPO/RTO are set in the contract.

**Q: Incident notification?**  
**A:** Per MSA / DPA. Critical confidentiality incidents are escalated immediately to the named customer contact.

**Q: Subprocessors?**  
**A:** Hosting provider (if Genovation-hosted), and optional AI API provider if enabled. A current subprocessor list is maintained for each production contract.

## G. Privacy

**Q: Is Agentic CDD a processor or controller?**  
**A:** Typically a **processor** of deal-room content supplied by the customer (controller). Exact roles are defined in the DPA.

**Q: Data subject requests / deletion?**  
**A:** Supported via authorised admin request to delete user accounts and/or deal workspaces per contract.

---

## Document control

Update this FAQ when architecture, certification status, or subprocessors change. Do not answer “yes” to certification questions until a valid certificate or report exists.
