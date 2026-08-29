# DORA citation audit

Register rows checked: 29. Corpus: `dora-articles.json` (https://www.digital-operational-resilience-act.com/DORA_Articles.html).

Checks 1 to 3 (article exists, article binds financial entities, subdivision exists) are questions of fact about the regulation's structure and are decisive. Check 4 (subject match) is advisory: term overlap is a heuristic, and legal interpretation is a matter for the author, not a score.

| Severity | Count |
|---|---|
| ERROR | 0 |
| WARN | 7 |
| INFO | 1 |
| OK | 21 |

## Review: subject may fit another provision better

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-012 | Art. 8(6) | Maintain ICT asset inventory | Cited provision scores 1 on subject terms; Art. 8(4) scores 6. | Consider Art. 8(4). |
| REQ-013 | Art. 8(1) | Identify and classify ICT assets by critical | Cited provision scores 5 on subject terms; Art. 8(4) scores 6. | Consider Art. 8(4). |
| REQ-017 | Art. 8(1) | Identify and document all ICT assets support | Cited provision scores 5 on subject terms; Art. 8(4) scores 6. | Consider Art. 8(4). |
| REQ-026 | Art. 9(4)(d) | Implement authentication and session managem | Cited provision scores 2 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-023 | Art. 9(4)(d) | Implement cryptographic key management contr | Cited provision scores 2 on subject terms; Art. 9(2) scores 4. | Consider Art. 9(2). |
| REQ-006 | Art. 7((c)) | Ensure ICT system resilience through resourc | Cited provision scores 0 on subject terms; Art. 11(5) scores 3. | Consider Art. 11(5). |
| REQ-014 | Art. 12(1) | Establish backup and restoration procedures | Cited provision scores 0 on subject terms; Art. 11(5) scores 3. | Consider Art. 11(5). |

## Not checked

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-016 | Art. 8(2) | Establish ICT risk assessment process | Article and subdivision valid; no subject vocabulary defined for this domain, so subject not scored. | - |

## Verified

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-025 | Art. 8(1) | Maintain documentation of ICT systems | Article, subdivision and subject all consistent (score 2). | - |
| REQ-027 | Art. 8(4) | Map ICT asset dependencies and interconnecti | Article, subdivision and subject all consistent (score 6). | - |
| REQ-001 | Art. 9(2) | Ensure confidentiality of data at rest | Article, subdivision and subject all consistent (score 4). | - |
| REQ-002 | Art. 9(2) | Ensure integrity and confidentiality of data | Article, subdivision and subject all consistent (score 4). | - |
| REQ-009 | Art. 9(2) | Ensure data integrity through immutable cont | Article, subdivision and subject all consistent (score 4). | - |
| REQ-008 | Art. 9(4)(b) | Implement network segmentation controls | Article, subdivision and subject all consistent (score 4). | - |
| REQ-028 | Art. 9(4)(b) | Implement logical segregation of ICT assets | Article, subdivision and subject all consistent (score 4). | - |
| REQ-010 | Art. 9(4)(c) | Restrict container runtime privileges - non- | Article, subdivision and subject all consistent (score 3). | - |
| REQ-011 | Art. 9(4)(c) | Prevent container breakout - host isolation | Article, subdivision and subject all consistent (score 3). | - |
| REQ-018 | Art. 9(4)(c) | Enforce security hardening on container file | Article, subdivision and subject all consistent (score 3). | - |
| REQ-003 | Art. 9(4)(c) | Implement least-privilege access controls | Article, subdivision and subject all consistent (score 3). | - |
| REQ-004 | Art. 9(4)(c) | Prevent privilege escalation through RBAC bi | Article, subdivision and subject all consistent (score 3). | - |
| REQ-019 | Art. 9(4)(c) | Restrict access to ICT resources to authoris | Article, subdivision and subject all consistent (score 3). | - |
| REQ-005 | Art. 10(1) | Enable kernel-level security auditing on con | Article, subdivision and subject all consistent (score 2). | - |
| REQ-020 | Art. 10(3) | Implement application-level log collection a | Article, subdivision and subject all consistent (score 3). | - |
| REQ-007 | Art. 11(5) | Ensure high availability of critical ICT ser | Article, subdivision and subject all consistent (score 3). | - |
| REQ-024 | Art. 11(5) | Implement graceful degradation capabilities | Article, subdivision and subject all consistent (score 3). | - |
| REQ-021 | Art. 11(6)(a) | Test ICT resilience through scenario-based t | Article, subdivision and subject all consistent (score 3). | - |
| REQ-015 | Art. 9(4)(e) | Implement ICT change management processes | Article, subdivision and subject all consistent (score 2). | - |
| REQ-022 | Art. 9(3)(c) | Verify container image provenance and integr | Article, subdivision and subject all consistent (score 4). | - |
| REQ-023b | Art. 9(3)(c) | Restrict container images to pre-approved re | Article, subdivision and subject all consistent (score 4). | - |
