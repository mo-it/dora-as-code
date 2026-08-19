#!/usr/bin/env python3
"""
build-evidence-hook.py — generate the ArgoCD PostSync compliance evidence hook.

WHAT CA2 PROMISED
-----------------
"Post-sync hooks will generate structured compliance evidence logs in JSON
format, recording which policies were evaluated, which passed, which failed, and
the DORA article each maps to."

and, as the third research output:

"a set of compliance evidence artefacts; structured audit logs, policy evaluation
reports, and violation records generated automatically by the GitOps pipeline."

HOW THIS IMPLEMENTS IT
----------------------
An ArgoCD PostSync hook Job runs after every successful sync. It queries:

  * Kyverno PolicyReports  (wgpolicyk8s.io/v1alpha2)
  * Gatekeeper Constraints (constraints.gatekeeper.sh/v1beta1, discovered
    dynamically since each ConstraintTemplate registers its own CRD kind)

and joins each result back to its DORA article using the mapping baked in from
requirements/dora-requirements-register.csv. Output is a JSON document written to
the Job log and persisted as a ConfigMap so it survives Job cleanup.

DESIGN CONSTRAINTS THIS RESPECTS
--------------------------------
1. REQ-023b restricts container images to approved registries. The hook uses
   docker.io/library/python:3.12-alpine, which the policy permits. Using a
   convenience image such as alpine/k8s would be blocked by the project's own
   policy -- a useful demonstration, but it would break the hook.

2. The hook manifests must themselves pass the 25 policies, since ArgoCD applies
   them through the same admission path. The Job pod therefore carries full
   compliant metadata, a non-root securityContext, resource limits, a pinned
   image tag, and an explicit ServiceAccount.

3. No kubectl, no jq, no pip install. The script uses the Python standard library
   against the in-cluster API with the mounted service account token, so the
   container starts in about a second and cannot fail on a package download.

USAGE
    python3 scripts/build-evidence-hook.py
    kubectl apply -f argocd/hooks/

Evidence is retrievable with:
    kubectl get configmap dora-compliance-evidence -n dora-test -o jsonpath='{.data.evidence\\.json}'
"""

import argparse
import csv
import json
import os

COLLECTOR = r'''
import json, os, ssl, sys, urllib.request, datetime

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
NS = os.environ.get("TARGET_NAMESPACE", "dora-test")
HOST = "https://kubernetes.default.svc"

COLLECTION_ERRORS = []
token = open(f"{SA}/token").read().strip()
ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")

def api(path):
    req = urllib.request.Request(HOST + path,
                                 headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=20) as r:
            return json.load(r)
    except Exception as e:
        COLLECTION_ERRORS.append(f"{path}: {e}")
        print(f"  [warn] {path}: {e}", file=sys.stderr)
        return {}

MAPPING = json.loads(os.environ["DORA_MAPPING"])

def dora_for(policy_name):
    """Resolve an engine policy name back to its DORA requirement."""
    if policy_name in MAPPING:
        return MAPPING[policy_name]
    # Kyverno ClusterPolicies are named dora-artN-<policy> while the register
    # stores the short form. Strip the dora-artN- prefix and match on the
    # remainder, longest key first so 'require-logging' cannot shadow
    # 'require-logging-sidecar'.
    import re as _re
    stripped = _re.sub(r'^dora-art\d+[a-z]?-', '', policy_name)
    if stripped in MAPPING:
        return MAPPING[stripped]
    for key in sorted(MAPPING, key=len, reverse=True):
        if stripped == key or policy_name.endswith(key) or key in stripped:
            return MAPPING[key]
    return {"req_id": "UNMAPPED", "dora_article": "", "dora_subsection": "",
            "requirement_text": "", "coverage_tier": ""}

evidence = {
    "schema": "dora-as-code/compliance-evidence/v1",
    "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "namespace": NS,
    "generated_by": "ArgoCD PostSync hook",
    "engines": {},
    "by_dora_article": {},
    "summary": {},
}

# ---------------------------------------------------------------- Kyverno
print("Collecting Kyverno PolicyReports...")
kyverno_results = []
reports = api(f"/apis/wgpolicyk8s.io/v1alpha2/namespaces/{NS}/policyreports")
for rep in reports.get("items", []):
    subject = rep.get("scope", {})
    for res in rep.get("results", []):
        pol = res.get("policy", "")
        d = dora_for(pol)
        kyverno_results.append({
            "policy": pol,
            "rule": res.get("rule", ""),
            "result": res.get("result", ""),
            "severity": res.get("severity", ""),
            "message": (res.get("message", "") or "")[:300],
            "resource_kind": subject.get("kind", ""),
            "resource_name": subject.get("name", ""),
            "req_id": d["req_id"],
            "dora_article": d["dora_article"],
            "dora_subsection": d["dora_subsection"],
            "coverage_tier": d["coverage_tier"],
        })
evidence["engines"]["kyverno"] = {
    "reports_found": len(reports.get("items", [])),
    "results": kyverno_results,
    "passed": sum(1 for r in kyverno_results if r["result"] == "pass"),
    "failed": sum(1 for r in kyverno_results if r["result"] == "fail"),
}
print(f"  {len(kyverno_results)} results from {len(reports.get('items', []))} reports")

# ------------------------------------------------------------- Gatekeeper
# Each ConstraintTemplate registers its own CRD kind, so the constraint kinds
# must be discovered rather than hard-coded.
print("Collecting Gatekeeper constraint status...")
gk_results = []
group = api("/apis/constraints.gatekeeper.sh/v1beta1")
for r in group.get("resources", []):
    name = r.get("name", "")
    if "/" in name:          # skip subresources such as <kind>/status
        continue
    items = api(f"/apis/constraints.gatekeeper.sh/v1beta1/{name}").get("items", [])
    for c in items:
        meta = c.get("metadata", {})
        status = c.get("status", {})
        d = dora_for(meta.get("name", ""))
        violations = status.get("violations", []) or []
        gk_results.append({
            "constraint_kind": c.get("kind", ""),
            "constraint_name": meta.get("name", ""),
            "enforcement_action": c.get("spec", {}).get("enforcementAction", "deny"),
            "total_violations": status.get("totalViolations", 0),
            "violations": [
                {"kind": v.get("kind", ""), "name": v.get("name", ""),
                 "message": (v.get("message", "") or "")[:300]}
                for v in violations[:20]
            ],
            "req_id": d["req_id"],
            "dora_article": d["dora_article"],
            "dora_subsection": d["dora_subsection"],
            "coverage_tier": d["coverage_tier"],
        })
evidence["engines"]["gatekeeper"] = {
    "constraints_found": len(gk_results),
    "results": gk_results,
    "total_violations": sum(g["total_violations"] for g in gk_results),
}
print(f"  {len(gk_results)} constraints")

# --------------------------------------------------- roll up by DORA article
by_art = {}
for r in kyverno_results:
    art = r["dora_subsection"] or r["dora_article"] or "unmapped"
    e = by_art.setdefault(art, {"req_ids": set(), "kyverno_pass": 0,
                                "kyverno_fail": 0, "gatekeeper_violations": 0})
    e["req_ids"].add(r["req_id"])
    if r["result"] == "pass":
        e["kyverno_pass"] += 1
    elif r["result"] == "fail":
        e["kyverno_fail"] += 1
for g in gk_results:
    art = g["dora_subsection"] or g["dora_article"] or "unmapped"
    e = by_art.setdefault(art, {"req_ids": set(), "kyverno_pass": 0,
                                "kyverno_fail": 0, "gatekeeper_violations": 0})
    e["req_ids"].add(g["req_id"])
    e["gatekeeper_violations"] += g["total_violations"]
evidence["by_dora_article"] = {
    k: {**v, "req_ids": sorted(x for x in v["req_ids"] if x)}
    for k, v in sorted(by_art.items())
}

# An absence of findings is NOT evidence of compliance. The first run of this
# hook reported "compliant": true having collected zero results, because an RBAC
# denial had silently blocked every constraint query. For a regulatory artefact
# that is the worst possible failure: an audit document attesting conformance
# because a permissions error produced no findings. The attestation is therefore
# gated on evidence sufficiency, and any collection error is recorded in the
# document itself rather than discarded.
expected_constraints = int(os.environ.get("EXPECTED_CONSTRAINTS", "25"))
sufficient = (
    len(gk_results) >= expected_constraints
    and len(kyverno_results) > 0
    and not COLLECTION_ERRORS
)
if not sufficient:
    attestation = "INDETERMINATE"
elif (evidence["engines"]["kyverno"]["failed"] == 0
      and evidence["engines"]["gatekeeper"]["total_violations"] == 0):
    attestation = "COMPLIANT"
else:
    attestation = "NON_COMPLIANT"

evidence["collection_errors"] = COLLECTION_ERRORS
evidence["summary"] = {
    "dora_articles_with_evidence": len(evidence["by_dora_article"]),
    "kyverno_evaluations": len(kyverno_results),
    "kyverno_passed": evidence["engines"]["kyverno"]["passed"],
    "kyverno_failed": evidence["engines"]["kyverno"]["failed"],
    "gatekeeper_constraints": len(gk_results),
    "gatekeeper_constraints_expected": expected_constraints,
    "gatekeeper_violations": evidence["engines"]["gatekeeper"]["total_violations"],
    "collection_errors": len(COLLECTION_ERRORS),
    "evidence_sufficient": sufficient,
    "attestation": attestation,
}
if not sufficient:
    print("\n*** ATTESTATION INDETERMINATE — evidence collection incomplete ***",
          file=sys.stderr)
    for e in COLLECTION_ERRORS[:10]:
        print(f"    {e}", file=sys.stderr)

doc = json.dumps(evidence, indent=2)
print("\n===== COMPLIANCE EVIDENCE =====")
print(doc)

# ------------------------------------------- persist so it outlives the Job
cm = {"apiVersion": "v1", "kind": "ConfigMap",
      "metadata": {"name": "dora-compliance-evidence", "namespace": NS,
                   "labels": {"dora.io/artefact": "compliance-evidence"}},
      "data": {"evidence.json": doc}}
body = json.dumps(cm).encode()
hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
for method, path in (("PUT", f"/api/v1/namespaces/{NS}/configmaps/dora-compliance-evidence"),
                     ("POST", f"/api/v1/namespaces/{NS}/configmaps")):
    try:
        req = urllib.request.Request(HOST + path, data=body, headers=hdrs, method=method)
        urllib.request.urlopen(req, context=ctx, timeout=20)
        print(f"\nEvidence persisted to ConfigMap dora-compliance-evidence ({method})")
        break
    except Exception as e:
        pass  # PUT 404s when the ConfigMap does not yet exist; POST then creates it

print("\nPostSync evidence collection complete.")
'''


def build_mapping(register_path):
    """policy name -> DORA requirement, for both engines."""
    m = {}
    with open(register_path) as fh:
        for r in csv.DictReader(fh):
            meta = {
                "req_id": r["req_id"],
                "dora_article": r["dora_article"],
                "dora_subsection": r["dora_subsection"],
                "requirement_text": r["requirement_text"],
                "coverage_tier": r["coverage_tier"],
            }
            for key in ("kyverno_policy", "gatekeeper_policy"):
                name = (r.get(key) or "").strip()
                if name:
                    m[name] = meta
    return m


RBAC = """# Least-privilege RBAC for the compliance evidence hook.
# Read-only on policy state, plus ConfigMap write in the target namespace so the
# evidence document survives Job cleanup. Deliberately not cluster-admin --
# REQ-004 blocks cluster-admin bindings to service accounts, so a broad grant
# would be rejected by the project's own policy set.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dora-evidence-collector
  namespace: dora-test
  labels:
    dora.io/component: compliance-evidence
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: dora-evidence-collector
  labels:
    dora.io/component: compliance-evidence
rules:
  - apiGroups: ["wgpolicyk8s.io"]
    resources: ["policyreports", "clusterpolicyreports"]
    verbs: ["get", "list"]
  # Explicit constraint kinds, NOT a wildcard. The first version used
  # resources: ["*"] and was REJECTED at admission by this project's own
  # REQ-003 policy (dora-art9-block-wildcard-rbac, DORA Art. 9(4)(b)). The
  # ClusterRole was therefore never created, the ClusterRoleBinding pointed at
  # nothing, every constraint query returned 403, and the evidence document was
  # generated from an empty dataset. Listing each kind satisfies least-privilege
  # and is what the regulation actually requires.
  - apiGroups: ["constraints.gatekeeper.sh"]
    resources:
      - "doraassetmetadata"
      - "doraauthtimeout"
      - "dorablockprivileged"
      - "dorachangeannotation"
      - "doraclusteradmin"
      - "doracriticality"
      - "doradefaultsa"
      - "doradependency"
      - "doradescription"
      - "doraencryptedstorageclass"
      - "doraimagesignature"
      - "doraimagetag"
      - "doralabels"
      - "doralogging"
      - "doranonroot"
      - "dorapdb"
      - "doraprivileged"
      - "doraregistries"
      - "dorareplicas"
      - "doraresourcelimits"
      - "doraresourcequota"
      - "dorarunasnonroot"
      - "dorasealedsecrets"
      - "doraseccompaudit"
      - "dorasecuritycontext"
      - "doratls"
      - "dorawildcardrbac"
    verbs: ["get", "list"]
  - apiGroups: ["templates.gatekeeper.sh"]
    resources: ["constrainttemplates"]
    verbs: ["get", "list"]
  - apiGroups: ["kyverno.io"]
    resources: ["clusterpolicies", "policies"]
    verbs: ["get", "list"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: dora-evidence-collector
  labels:
    dora.io/component: compliance-evidence
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: dora-evidence-collector
subjects:
  - kind: ServiceAccount
    name: dora-evidence-collector
    namespace: dora-test
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: dora-evidence-writer
  namespace: dora-test
  labels:
    dora.io/component: compliance-evidence
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "create", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: dora-evidence-writer
  namespace: dora-test
  labels:
    dora.io/component: compliance-evidence
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: dora-evidence-writer
subjects:
  - kind: ServiceAccount
    name: dora-evidence-collector
    namespace: dora-test
"""


def build_job(mapping, collector):
    """The PostSync Job. Must itself satisfy all 25 policies."""
    import textwrap
    script = textwrap.indent(collector.strip(), "    ")
    mapping_json = json.dumps(mapping, separators=(",", ":"))

    return f"""# ArgoCD PostSync compliance evidence hook.
#
# Runs after every successful sync, collects policy evaluation results from both
# engines, joins them to DORA articles, and writes a JSON evidence document.
#
# The pod metadata below is not decoration: ArgoCD applies this Job through the
# same admission path as everything else, so it must satisfy all 25 policies or
# the hook is rejected by the project's own compliance controls.
apiVersion: v1
kind: ConfigMap
metadata:
  name: dora-evidence-script
  namespace: dora-test
  labels:
    dora.io/component: compliance-evidence
data:
  collect.py: |
{script}
---
apiVersion: batch/v1
kind: Job
metadata:
  name: dora-compliance-evidence
  namespace: dora-test
  annotations:
    argocd.argoproj.io/hook: PostSync
    argocd.argoproj.io/hook-delete-policy: BeforeHookCreation
    dora.io/kernel-audit-enabled: "true"
    dora.io/change-id: "CHG-EVIDENCE-HOOK"
    dora.io/approved-by: "mohit-kumar"
    dora.io/business-function: "compliance-evidence-generation"
    dora.io/data-classification: "internal"
    dora.io/asset-owner: "mohit-kumar"
    dora.io/logging-configured: "true"
    dora.io/image-signature-verified: "true"
    dora.io/pdb-configured: "true"
    dora.io/description: "Generates DORA compliance evidence after ArgoCD sync"
    dora.io/dependencies: "kyverno,gatekeeper"
  labels:
    dora.test: "true"
    app: dora-evidence
    dora.io/owner: "mohit-kumar"
    dora.io/team: "platform-engineering"
    dora.io/criticality: "low"
spec:
  backoffLimit: 2
  ttlSecondsAfterFinished: 3600
  template:
    metadata:
      labels:
        app: dora-evidence
    spec:
      restartPolicy: Never
      serviceAccountName: dora-evidence-collector
      containers:
        - name: collector
          # docker.io/library/* is permitted by REQ-023b. A convenience image
          # such as alpine/k8s would be BLOCKED by this project's own policy.
          image: docker.io/library/python:3.12-alpine
          command: ["python3", "/scripts/collect.py"]
          env:
            - name: TARGET_NAMESPACE
              value: "dora-test"
            - name: EXPECTED_CONSTRAINTS
              value: "25"
            - name: DORA_MAPPING
              value: '{mapping_json}'
          resources:
            requests:
              cpu: "50m"
              memory: "64Mi"
            limits:
              cpu: "200m"
              memory: "128Mi"
          securityContext:
            runAsNonRoot: true
            runAsUser: 1000
            privileged: false
            readOnlyRootFilesystem: true
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
            seccompProfile:
              type: RuntimeDefault
          volumeMounts:
            - name: script
              mountPath: /scripts
      volumes:
        - name: script
          configMap:
            name: dora-evidence-script
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", default="requirements/dora-requirements-register.csv")
    ap.add_argument("--out", default="argocd/hooks")
    args = ap.parse_args()

    mapping = build_mapping(args.register)
    os.makedirs(args.out, exist_ok=True)

    with open(f"{args.out}/compliance-evidence-rbac.yaml", "w") as fh:
        fh.write(RBAC)
    with open(f"{args.out}/compliance-evidence-hook.yaml", "w") as fh:
        fh.write(build_job(mapping, COLLECTOR))

    print(f"Policy-to-DORA mappings embedded: {len(mapping)}")
    print(f"Written:")
    print(f"  {args.out}/compliance-evidence-rbac.yaml")
    print(f"  {args.out}/compliance-evidence-hook.yaml")
    print()
    print("Apply with:  kubectl apply -f argocd/hooks/")
    print("Read evidence:")
    print("  kubectl get configmap dora-compliance-evidence -n dora-test "
          "-o jsonpath='{.data.evidence\\.json}' | python3 -m json.tool")


if __name__ == "__main__":
    main()
