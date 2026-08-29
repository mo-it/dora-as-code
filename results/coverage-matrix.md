# Policy Expressiveness Coverage Matrix


Requirements assessed: **29**


| Coverage measure | Kyverno | OPA Gatekeeper |
|---|---|---|
| Binary coverage (expressible at all) | 86.2% | 86.2% |
| Effective coverage (directly enforced) | 44.8% | 44.8% |

**DIRECT** — the policy inspects the actual resource field the requirement
concerns; enforcement is technical. **ASSERTED** — the policy checks an
annotation claiming compliance, which the admission controller cannot verify;
enforcement is procedural. **ABSENT** — no working policy.


## Per-requirement matrix

| REQ | Article | Requirement | Kyverno | Gatekeeper |
|---|---|---|---|---|
| REQ-012 | 8(6) | Maintain ICT asset inventory | ASSERTED | ASSERTED |
| REQ-025 | 8(1) | Maintain documentation of ICT systems | ASSERTED | ASSERTED |
| REQ-013 | 8(1) | Identify and classify ICT assets by criticality | ASSERTED | ASSERTED |
| REQ-027 | 8(4) | Map ICT asset dependencies and interconnections | ASSERTED | ASSERTED |
| REQ-016 | 8(2) | Establish ICT risk assessment process | ABSENT | ABSENT |
| REQ-017 | 8(1) | Identify and document all ICT assets supporting business functions | ASSERTED | ASSERTED |
| REQ-001 | 9(2) | Ensure confidentiality of data at rest | DIRECT | DIRECT |
| REQ-002 | 9(2) | Ensure integrity and confidentiality of data in transit | DIRECT | DIRECT |
| REQ-009 | 9(2) | Ensure data integrity through immutable container images | DIRECT | DIRECT |
| REQ-008 | 9(4(b)) | Implement network segmentation controls | ABSENT | ABSENT |
| REQ-028 | 9(4(b)) | Implement logical segregation of ICT assets | ASSERTED | ASSERTED |
| REQ-010 | 9(4(c)) | Restrict container runtime privileges - non-root execution | DIRECT | DIRECT |
| REQ-011 | 9(4(c)) | Prevent container breakout - host isolation | DIRECT | DIRECT |
| REQ-018 | 9(4(c)) | Enforce security hardening on container filesystems | DIRECT | DIRECT |
| REQ-003 | 9(4(c)) | Implement least-privilege access controls | DIRECT | DIRECT |
| REQ-004 | 9(4(c)) | Prevent privilege escalation through RBAC bindings | DIRECT | DIRECT |
| REQ-026 | 9(4(d)) | Implement authentication and session management controls | ASSERTED | ASSERTED |
| REQ-019 | 9(4)(c) | Restrict access to ICT resources to authorised service accounts only | DIRECT | DIRECT |
| REQ-023 | 9(4)(d) | Implement cryptographic key management controls | DIRECT | DIRECT |
| REQ-005 | 10(1) | Enable kernel-level security auditing on containers | ASSERTED | ASSERTED |
| REQ-020 | 10(3) | Implement application-level log collection and forwarding | ASSERTED | ASSERTED |
| REQ-006 | 7(c) | Ensure ICT system resilience through resource governance | DIRECT | DIRECT |
| REQ-007 | 11(5) | Ensure high availability of critical ICT services | DIRECT | DIRECT |
| REQ-024 | 11(5) | Implement graceful degradation capabilities | ASSERTED | ASSERTED |
| REQ-021 | 11(6(a)) | Test ICT resilience through scenario-based testing | ABSENT | ABSENT |
| REQ-014 | 12(1) | Establish backup and restoration procedures | ABSENT | ABSENT |
| REQ-015 | 9(4(e)) | Implement ICT change management processes | ASSERTED | ASSERTED |
| REQ-022 | 9(3(c)) | Verify container image provenance and integrity | ASSERTED | ASSERTED |
| REQ-023b | 9(3(c)) | Restrict container images to pre-approved registries | DIRECT | DIRECT |

## Notes on non-direct enforcement

- **REQ-027** — checks dora.io/dependencies annotation; contents are unvalidated free text
- **REQ-016** — classified not-automatable in the requirements register
- **REQ-017** — checks asset-metadata annotations; values are unvalidated free text
- **REQ-026** — checks dora.io/session-timeout-configured annotation; cannot verify ingress auth timeout
- **REQ-005** — checks dora.io/kernel-audit-enabled annotation; cannot verify AppArmor/seccomp audit profiles are active
- **REQ-020** — checks dora.io/logging-configured annotation; cannot verify a log collection agent is running
- **REQ-024** — checks dora.io/pdb-configured annotation; does not verify a PodDisruptionBudget object exists
- **REQ-021** — classified not-automatable in the requirements register
- **REQ-014** — classified not-automatable in the requirements register
- **REQ-015** — checks change-management annotations; cannot verify a change ticket exists or was approved
- **REQ-022** — checks dora.io/image-signature-verified annotation; no cryptographic verification performed | Kyverno: native verifyImages rule type supports Cosign and Notary signature verification. Gatekeeper: no equivalent; requires an external data provider via the externaldata API.
