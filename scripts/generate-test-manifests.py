#!/usr/bin/env python3
"""
generate-test-manifests.py — build the Phase 4 test manifest suite.

WHY THIS EXISTS
---------------
The v1 test suite was authored one requirement at a time: each "compliant"
manifest satisfied only its own requirement. That is valid if you evaluate one
policy at a time, but the experiment deploys all 25 policies simultaneously. With
the full set live, every single-requirement manifest fails the other 24 — as the
26 July ArgoCD sync log showed, where all 8 compliant Deployments were rejected.

The consequence is that a rejection could not be attributed to any particular
requirement, so per-requirement precision and recall were not measurable.

THE DESIGN THIS IMPLEMENTS
--------------------------
One variable per manifest.

  * compliant/<req>.yaml      satisfies ALL 25 policies. Expected: 0 violations.
  * non-compliant/<req>.yaml  satisfies ALL 25 policies EXCEPT the one named
                              requirement. Expected: exactly 1 failing policy.

Because a non-compliant manifest deviates in exactly one dimension, a rejection
is attributable and a miss is a clean false negative for that requirement.

Café analogy: to find out which inspector catches contaminated milk, you send
through a tray that is perfect in every other respect and has one bad carton.
The v1 suite sent trays that were wrong in fifteen ways at once, so you learned
only that *something* was refused.

USAGE
    python3 scripts/generate-test-manifests.py --out manifests
    python3 scripts/generate-test-manifests.py --out /tmp/preview --dry-run

Writes manifests/compliant/, manifests/non-compliant/, and
manifests/expected-results.csv (the ground-truth table for scoring).
"""

import argparse
import copy
import csv
import os

import yaml

NS = "dora-test"
SA = "dora-test-sa"
IMAGE_OK = "nginx:1.27"

# --- the compliant baseline ---------------------------------------------------
# Derived from the policy set itself: every label/annotation any policy demands
# of a Deployment. Keep this in sync with policies/kyverno/ if policies change.

BASE_LABELS = {
    "dora.test": "true",
    "app": "dora-test-app",
    "dora.io/owner": "mohit-kumar",           # REQ-012
    "dora.io/team": "platform-engineering",   # REQ-012
    "dora.io/criticality": "low",             # REQ-013
}

BASE_ANNOTATIONS = {
    "dora.io/kernel-audit-enabled": "true",           # REQ-005
    "dora.io/change-id": "CHG-2026-001",              # REQ-015
    "dora.io/approved-by": "mark-lynch",              # REQ-015
    "dora.io/business-function": "compliance-testing",# REQ-017
    "dora.io/data-classification": "internal",        # REQ-017
    "dora.io/asset-owner": "mohit-kumar",             # REQ-017
    "dora.io/logging-configured": "true",             # REQ-020
    "dora.io/image-signature-verified": "true",       # REQ-022
    "dora.io/pdb-configured": "true",                 # REQ-024
    "dora.io/description": "DORA Phase 4 test workload",  # REQ-025
    "dora.io/dependencies": "none",                   # REQ-027
}

BASE_SECURITY_CONTEXT = {
    "runAsNonRoot": True,        # REQ-010
    "runAsUser": 1000,
    "capabilities": {"drop": ["ALL"]},   # REQ-010
    "privileged": False,                 # REQ-011
    "readOnlyRootFilesystem": True,      # REQ-018
    "allowPrivilegeEscalation": False,   # REQ-018
    "seccompProfile": {"type": "RuntimeDefault"},  # REQ-018
}

BASE_RESOURCES = {                       # REQ-006
    "requests": {"cpu": "100m", "memory": "128Mi"},
    "limits": {"cpu": "200m", "memory": "256Mi"},
}


def deployment(name, replicas=1):
    """A Deployment that satisfies every one of the 25 policies."""
    labels = dict(BASE_LABELS)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {
            "name": name,
            "namespace": NS,
            "labels": labels,
            "annotations": dict(BASE_ANNOTATIONS),
        },
        "spec": {
            "replicas": replicas,
            "selector": {"matchLabels": {"app": labels["app"], "test": name}},
            "template": {
                "metadata": {"labels": {"app": labels["app"], "test": name}},
                "spec": {
                    "serviceAccountName": SA,        # REQ-019
                    "containers": [{
                        "name": "test-container",
                        "image": IMAGE_OK,           # REQ-009, REQ-023b
                        "resources": copy.deepcopy(BASE_RESOURCES),
                        "securityContext": copy.deepcopy(BASE_SECURITY_CONTEXT),
                    }],
                },
            },
        },
    }


# --- single-requirement mutations --------------------------------------------
# Each function takes a compliant Deployment and breaks exactly ONE requirement.

def _c(d):
    return d["spec"]["template"]["spec"]["containers"][0]


def _ps(d):
    return d["spec"]["template"]["spec"]


MUTATIONS = {
    "req005": ("Art. 10(1)", "kernel audit annotation absent",
               lambda d: d["metadata"]["annotations"].pop("dora.io/kernel-audit-enabled")),
    "req006": ("Art. 11(1)", "no resource requests or limits",
               lambda d: _c(d).pop("resources")),
    "req009": ("Art. 9(2)", "mutable :latest image tag",
               lambda d: _c(d).update(image="nginx:latest")),
    "req010": ("Art. 9(4)(a)", "runs as root, no capability drop",
               lambda d: _c(d)["securityContext"].update(
                   runAsNonRoot=False, runAsUser=0, capabilities={"drop": []})),
    "req011": ("Art. 9(4)(a)", "privileged container",
               lambda d: _c(d)["securityContext"].update(privileged=True)),
    "req012": ("Art. 5(2)(a)", "inventory labels absent",
               lambda d: [d["metadata"]["labels"].pop(k)
                          for k in ("app", "dora.io/owner", "dora.io/team")]),
    "req013": ("Art. 6(1)(b)", "criticality label absent",
               lambda d: d["metadata"]["labels"].pop("dora.io/criticality")),
    "req015": ("Art. 13(1)", "change-management annotations absent",
               lambda d: [d["metadata"]["annotations"].pop(k)
                          for k in ("dora.io/change-id", "dora.io/approved-by")]),
    "req017": ("Art. 8(1)", "asset-metadata annotations absent",
               lambda d: [d["metadata"]["annotations"].pop(k)
                          for k in ("dora.io/business-function",
                                    "dora.io/data-classification",
                                    "dora.io/asset-owner")]),
    "req018": ("Art. 9(4)(a)", "writable rootfs, escalation allowed, no seccomp",
               lambda d: (_c(d)["securityContext"].update(
                   readOnlyRootFilesystem=False, allowPrivilegeEscalation=True),
                   _c(d)["securityContext"].pop("seccompProfile"))),
    "req019": ("Art. 9(4)(c)", "default ServiceAccount",
               lambda d: _ps(d).update(serviceAccountName="default")),
    "req020": ("Art. 10(3)", "logging annotation absent",
               lambda d: d["metadata"]["annotations"].pop("dora.io/logging-configured")),
    "req022": ("Art. 15(1)", "image signature annotation absent",
               lambda d: d["metadata"]["annotations"].pop("dora.io/image-signature-verified")),
    "req023b": ("Art. 15(1)", "image from unapproved registry",
                lambda d: _c(d).update(image="evil.example.com/malware:v1")),
    "req025": ("Art. 5(2)(d)", "description annotation absent",
               lambda d: d["metadata"]["annotations"].pop("dora.io/description")),
    "req027": ("Art. 6(2)", "dependency annotation absent",
               lambda d: d["metadata"]["annotations"].pop("dora.io/dependencies")),
    # REQ-007 and REQ-024 only apply to criticality high/medium, so these two
    # need a high-criticality baseline rather than the default low.
    "req007": ("Art. 11(1)", "criticality high with a single replica",
               lambda d: (d["metadata"]["labels"].update({"dora.io/criticality": "high"}),
                          d["spec"].update(replicas=1))),
    "req024": ("Art. 11(5)", "criticality high without a PodDisruptionBudget",
               lambda d: (d["metadata"]["labels"].update({"dora.io/criticality": "high"}),
                          d["spec"].update(replicas=2),
                          d["metadata"]["annotations"].pop("dora.io/pdb-configured"))),
}

# Requirements whose compliant form needs a non-default baseline.
HIGH_CRIT = {"req007", "req024"}


def compliant_for(req):
    name = f"test-{req}-compliant"
    d = deployment(name, replicas=2 if req in HIGH_CRIT else 1)
    if req in HIGH_CRIT:
        d["metadata"]["labels"]["dora.io/criticality"] = "high"
    return d


def non_compliant_for(req):
    name = f"test-{req}-violation"
    d = deployment(name, replicas=2 if req in HIGH_CRIT else 1)
    if req in HIGH_CRIT:
        d["metadata"]["labels"]["dora.io/criticality"] = "high"
    MUTATIONS[req][2](d)
    return d


# --- non-Deployment manifests -------------------------------------------------
# These target kinds with no pod template, so the container-path defect does not
# apply. The storage class is the fix here: the v1 PVC referenced "encrypted-gp3",
# an AWS EBS class that does not exist on K3s, so it could never bind
# (ProvisioningFailed) regardless of policy outcome.

STORAGE_CLASS_OK = "local-path-encrypted"   # see docs/storageclass note


def others():
    out = {}
    out[("compliant", "req001")] = {
        "apiVersion": "v1", "kind": "PersistentVolumeClaim",
        "metadata": {"name": "test-req001-compliant", "namespace": NS,
                     "labels": {"dora.test": "true"},
                     "annotations": {"dora.io/encryption-at-rest": "true"}},
        "spec": {"accessModes": ["ReadWriteOnce"],
                 "storageClassName": STORAGE_CLASS_OK,
                 "resources": {"requests": {"storage": "128Mi"}}},
    }
    out[("non-compliant", "req001")] = {
        "apiVersion": "v1", "kind": "PersistentVolumeClaim",
        "metadata": {"name": "test-req001-violation", "namespace": NS,
                     "labels": {"dora.test": "true"}},
        "spec": {"accessModes": ["ReadWriteOnce"],
                 "storageClassName": "local-path",
                 "resources": {"requests": {"storage": "128Mi"}}},
    }
    ing_ann = {"dora.io/session-timeout-configured": "true",
               "dora.io/description": "DORA test ingress",
               "dora.io/dependencies": "none"}
    out[("compliant", "req002")] = {
        "apiVersion": "networking.k8s.io/v1", "kind": "Ingress",
        "metadata": {"name": "test-req002-compliant", "namespace": NS,
                     "labels": dict(BASE_LABELS), "annotations": dict(ing_ann)},
        "spec": {"tls": [{"hosts": ["test.dora.local"], "secretName": "test-tls"}],
                 "rules": [{"host": "test.dora.local",
                            "http": {"paths": [{"path": "/", "pathType": "Prefix",
                                                "backend": {"service": {"name": "test-svc",
                                                                        "port": {"number": 80}}}}]}}]},
    }
    nc = copy.deepcopy(out[("compliant", "req002")])
    nc["metadata"]["name"] = "test-req002-violation"
    nc["spec"].pop("tls")
    out[("non-compliant", "req002")] = nc

    out[("compliant", "req028")] = {
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": "test-req028-compliant",
                     "labels": {"dora.test": "true"},
                     "annotations": {"dora.io/resource-quota-configured": "true"}},
    }
    out[("non-compliant", "req028")] = {
        "apiVersion": "v1", "kind": "Namespace",
        "metadata": {"name": "test-req028-violation", "labels": {"dora.test": "true"}},
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="manifests")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = []
    files = {}

    for req, (article, why, _) in sorted(MUTATIONS.items()):
        files[("compliant", req)] = compliant_for(req)
        files[("non-compliant", req)] = non_compliant_for(req)
        rows.append({"requirement": req.upper().replace("REQ", "REQ-"),
                     "dora_article": article, "variant": "compliant",
                     "manifest": f"compliant/{req}-compliant.yaml",
                     "expected_decision": "allow", "expected_violations": 0,
                     "deviation": "none"})
        rows.append({"requirement": req.upper().replace("REQ", "REQ-"),
                     "dora_article": article, "variant": "non-compliant",
                     "manifest": f"non-compliant/{req}-violation.yaml",
                     "expected_decision": "deny", "expected_violations": 1,
                     "deviation": why})

    for (variant, req), doc in others().items():
        files[(variant, req)] = doc
        rows.append({"requirement": req.upper().replace("REQ", "REQ-"),
                     "dora_article": "see register", "variant": variant,
                     "manifest": f"{variant}/{req}-"
                                 f"{'compliant' if variant == 'compliant' else 'violation'}.yaml",
                     "expected_decision": "allow" if variant == "compliant" else "deny",
                     "expected_violations": 0 if variant == "compliant" else 1,
                     "deviation": "none" if variant == "compliant" else "target requirement broken"})

    print(f"{'FILE':52s} {'KIND':26s} EXPECTED")
    print("-" * 92)
    for (variant, req), doc in sorted(files.items()):
        suffix = "compliant" if variant == "compliant" else "violation"
        path = os.path.join(args.out, variant, f"{req}-{suffix}.yaml")
        print(f"{path:52s} {doc['kind']:26s} "
              f"{'allow' if variant == 'compliant' else 'deny (1 policy)'}")
        if not args.dry_run:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as fh:
                fh.write(f"# AUTO-GENERATED by scripts/generate-test-manifests.py\n"
                         f"# Target: {req.upper()}  Variant: {variant}\n"
                         f"# Expected: {'0 violations' if variant == 'compliant' else 'exactly 1 failing policy'}\n")
                yaml.safe_dump(doc, fh, sort_keys=False, default_flow_style=False)

    if not args.dry_run:
        csv_path = os.path.join(args.out, "expected-results.csv")
        with open(csv_path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"\nGround truth written: {csv_path}  ({len(rows)} rows)")

    print(f"\nTotal manifests: {len(files)}  "
          f"(compliant {sum(1 for k in files if k[0] == 'compliant')}, "
          f"non-compliant {sum(1 for k in files if k[0] == 'non-compliant')})")


if __name__ == "__main__":
    main()
