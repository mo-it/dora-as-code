# DORA-as-Code

**A Comparative Evaluation of Policy-as-Code Tools for Automated EU Regulatory Compliance in GitOps-Managed Kubernetes Environments**

MSc DevOps Dissertation — Mohit Kumar Somashekar
Technological University Dublin (Tallaght Campus)

## Overview

This repository contains the research artefacts for the DORA-as-Code dissertation, which maps EU Digital Operational Resilience Act (DORA) ICT risk management requirements (Articles 5–15) to executable Kubernetes admission policies and compares enforcement using Kyverno and OPA Gatekeeper within an ArgoCD GitOps pipeline.

## Repository Structure

```
dora-as-code/
├── requirements/          # Phase 1: DORA requirements register
│   └── dora-requirements-register.csv
├── policies/
│   ├── kyverno/           # Phase 2: Kyverno ClusterPolicies (YAML)
│   └── gatekeeper/        # Phase 2: OPA Gatekeeper (Rego)
│       ├── templates/     #   ConstraintTemplates
│       └── constraints/   #   Constraint instances
├── manifests/
│   ├── compliant/         # Phase 4: Compliant test manifests
│   └── non-compliant/     # Phase 4: Non-compliant test manifests
├── argocd/                # Phase 3: ArgoCD Application definitions
├── evidence/              # Phase 3-4: Compliance audit logs (JSON)
├── results/               # Phase 4: Experiment metrics and analysis
└── scripts/               # Automation scripts (benchmarking, etc.)
```

## Methodology

Design Science Research (DSR) across four phases:
1. **Regulatory Analysis** — Decompose DORA Articles 5–15 into technical requirements
2. **Policy Mapping** — Implement each requirement in Kyverno (YAML) and OPA Gatekeeper (Rego)
3. **GitOps Integration** — Deploy via ArgoCD with pre/post-sync hooks
4. **Comparative Validation** — Measure expressiveness, detection accuracy, and performance

## Test Environment

- K3s (lightweight Kubernetes) on WSL2
- ArgoCD as GitOps controller
- Kyverno (Policy Engine A) and OPA Gatekeeper (Policy Engine B)

## Licence

This research artefact is provided for academic purposes.
