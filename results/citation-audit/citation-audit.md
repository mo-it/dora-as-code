# DORA citation audit

Register rows checked: 30. Corpus: `dora-articles.json` (https://www.digital-operational-resilience-act.com/DORA_Articles.html).

Checks 1 to 3 (article exists, article binds financial entities, subdivision exists) are questions of fact about the regulation's structure and are decisive. Check 4 (subject match) is advisory: term overlap is a heuristic, and legal interpretation is a matter for the author, not a score.

| Severity | Count |
|---|---|
| ERROR | 3 |
| WARN | 15 |
| INFO | 3 |
| OK | 9 |

## Errors: citations that cannot stand

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-016 | Art. 7(1) | Establish ICT risk assessment process | Article 7 has no numbered paragraphs, only lettered points, so '(1)' cannot exist. | Valid subdivisions: (a), (b), (c), (d) |
| REQ-022 | Art. 15(1) | Verify container image provenance and integr | Article 15 (Further harmonisation of ICT risk management tools, methods, processes and policies) mandates the ESAs to develop regulatory technical standards. It imposes no obligation on financial entities, so it cannot be the legal basis for a technical control. | Re-cite to the substantive article this control implements. |
| REQ-023b | Art. 15(1) | Restrict container images to pre-approved re | Article 15 (Further harmonisation of ICT risk management tools, methods, processes and policies) mandates the ESAs to develop regulatory technical standards. It imposes no obligation on financial entities, so it cannot be the legal basis for a technical control. | Re-cite to the substantive article this control implements. |

## Review: subject may fit another provision better

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-012 | Art. 5(2)(a) | Maintain ICT asset inventory | Cited provision scores 0 on subject terms; Art. 8(4) scores 6. | Consider Art. 8(4). |
| REQ-025 | Art. 5(2)(d) | Maintain documentation of ICT systems | Cited provision scores 0 on subject terms; Art. 8(1) scores 2. | Consider Art. 8(1). |
| REQ-017 | Art. 8(1) | Identify and document all ICT assets support | Cited provision scores 5 on subject terms; Art. 8(4) scores 6. | Consider Art. 8(4). |
| REQ-008 | Art. 9(3)(a) | Implement network segmentation controls | Cited provision scores 0 on subject terms; Art. 9(4(b)) scores 4. | Consider Art. 9(4(b)). |
| REQ-028 | Art. 9(3)(b) | Implement logical segregation of ICT assets | Cited provision scores 0 on subject terms; Art. 9(4(b)) scores 4. | Consider Art. 9(4(b)). |
| REQ-010 | Art. 9(4)(a) | Restrict container runtime privileges - non- | Cited provision scores 0 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-011 | Art. 9(4)(a) | Prevent container breakout - host isolation | Cited provision scores 0 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-018 | Art. 9(4)(a) | Enforce security hardening on container file | Cited provision scores 0 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-003 | Art. 9(4)(b) | Implement least-privilege access controls | Cited provision scores 0 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-004 | Art. 9(4)(b) | Prevent privilege escalation through RBAC bi | Cited provision scores 0 on subject terms; Art. 9(4(c)) scores 3. | Consider Art. 9(4(c)). |
| REQ-023 | Art. 9(4)(d) | Implement cryptographic key management contr | Cited provision scores 2 on subject terms; Art. 9(2) scores 4. | Consider Art. 9(2). |
| REQ-006 | Art. 11(1) | Ensure ICT system resilience through resourc | Cited provision scores 1 on subject terms; Art. 11(5) scores 3. | Consider Art. 11(5). |
| REQ-007 | Art. 11(1) | Ensure high availability of critical ICT ser | Cited provision scores 1 on subject terms; Art. 11(5) scores 3. | Consider Art. 11(5). |
| REQ-021 | Art. 11(3) | Test ICT resilience through scenario-based t | Cited provision scores 0 on subject terms; Art. 11(5) scores 3. | Consider Art. 11(5). |
| REQ-015 | Art. 13(1) | Implement ICT change management processes | Cited provision scores 0 on subject terms; Art. 9(4(e)) scores 2. | Consider Art. 9(4(e)). |

## Not checked

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-013 | Art. 6(1)(b) | Identify and classify ICT assets by critical | Article 6 text is not yet in the corpus, so this citation could not be checked. | - |
| REQ-027 | Art. 6(2) | Map ICT asset dependencies and interconnecti | Article 6 text is not yet in the corpus, so this citation could not be checked. | - |
| REQ-014 | Art. 12(1) | Establish backup and restoration procedures | Article 12 text is not yet in the corpus, so this citation could not be checked. | - |

## Verified

| REQ | Cited | Requirement | Finding | Suggestion |
|---|---|---|---|---|
| REQ-001 | Art. 9(2) | Ensure confidentiality of data at rest | Article, subdivision and subject all consistent (score 4). | - |
| REQ-002 | Art. 9(2) | Ensure integrity and confidentiality of data | Article, subdivision and subject all consistent (score 4). | - |
| REQ-009 | Art. 9(2) | Ensure data integrity through immutable cont | Article, subdivision and subject all consistent (score 4). | - |
| REQ-026 | Art. 9(4)(c) | Implement authentication and session managem | Article, subdivision and subject all consistent (score 3). | - |
| REQ-019 | Art. 9(4)(c) | Restrict access to ICT resources to authoris | Article, subdivision and subject all consistent (score 3). | - |
| REQ-005 | Art. 10(1) | Enable kernel-level security auditing on con | Article, subdivision and subject all consistent (score 2). | - |
| REQ-020 | Art. 10(3) | Implement application-level log collection a | Article, subdivision and subject all consistent (score 3). | - |
| REQ-024 | Art. 11(5) | Implement graceful degradation capabilities | Article, subdivision and subject all consistent (score 3). | - |
| REQ-029 | Art. 14(1) | Establish crisis communication plans and des | Article, subdivision and subject all consistent (score 2). | - |
