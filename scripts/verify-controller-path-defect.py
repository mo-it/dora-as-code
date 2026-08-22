#!/usr/bin/env python3
"""
verify-controller-path-defect.py -- offline reproduction of Finding 1.

WHAT THIS PROVES
----------------
Seven Gatekeeper ConstraintTemplates originally read container fields at
`input.review.object.spec.containers` while their Constraints matched controller
kinds (Deployment, StatefulSet, DaemonSet, CronJob). On a controller that path
does not exist: the containers live at `spec.template.spec.containers`.

In Rego, iteration over a path that does not exist binds nothing, so the rule
body never runs and the template reports no violation. The engine does not
error. It returns success. That means the v1 templates produced the SAME output
for a compliant object and a violating object of the same controller kind, so
detection accuracy was not poor, it was UNDEFINED -- there was no input the
policy could distinguish.

The v2 templates add a `pod_spec` partial-set helper that resolves the pod spec
for each kind, restoring discrimination.

This script evaluates both versions against the same inputs with the OPA binary
and reports the verdicts, so the claim in the write-up is checkable rather than
asserted.

WHY THIS IS SAFE TO RUN ANY TIME
--------------------------------
No cluster is required. The v1 Rego is recovered from git history (the parent of
the fix commit) and the v2 Rego from the working tree. Evaluation is entirely
offline against synthetic AdmissionReview inputs.

USAGE
    python3 scripts/verify-controller-path-defect.py            # needs `opa` on PATH
    python3 scripts/verify-controller-path-defect.py --opa ./opa
    python3 scripts/verify-controller-path-defect.py --out results/controller-path-defect

OUTPUTS
    <out>/controller-path-verdicts.csv   one row per (version, template, kind, variant)
    <out>/controller-path-report.md      human-readable summary
"""

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile

import yaml

# The seven templates changed by the controller-path fix. Recovered from the
# parent of commit 9182832 for v1; working tree for v2.
FIX_COMMIT = "9182832"

TEMPLATES = [
    "req006-resource-limits-template.yaml",
    "req009-image-tag-template.yaml",
    "req010-non-root-template.yaml",
    "req011-privileged-template.yaml",
    "req018-security-context-template.yaml",
    "req019-default-sa-template.yaml",
    "req023b-registries-template.yaml",
]

KINDS = ["Pod", "Deployment", "StatefulSet", "DaemonSet", "CronJob"]


# ----------------------------------------------------------------- fixtures
def compliant_pod_spec():
    """A pod spec that satisfies all seven requirements under test."""
    return {
        "serviceAccountName": "dora-app-sa",          # REQ-019
        "containers": [{
            "name": "app",
            "image": "docker.io/library/nginx:1.27.3",  # REQ-009, REQ-023b
            "resources": {                              # REQ-006
                "requests": {"cpu": "100m", "memory": "128Mi"},
                "limits": {"cpu": "500m", "memory": "512Mi"},
            },
            "securityContext": {
                "runAsNonRoot": True,                   # REQ-010
                "privileged": False,                    # REQ-011
                "readOnlyRootFilesystem": True,         # REQ-018
                "allowPrivilegeEscalation": False,      # REQ-018
                "capabilities": {"drop": ["ALL"]},      # REQ-010
                "seccompProfile": {"type": "RuntimeDefault"},  # REQ-018
            },
        }],
    }


def violating_pod_spec():
    """A pod spec that breaks all seven requirements at once.

    Deliberately maximal: the point is to show the v1 templates return the same
    answer here as for the compliant spec, so the violation count must be
    unambiguously non-zero under a working policy.
    """
    return {
        "serviceAccountName": "default",               # REQ-019 violation
        "hostPID": True,                               # REQ-011 violation
        "containers": [{
            "name": "app",
            "image": "evil.example.com/app:latest",    # REQ-009 + REQ-023b violation
            # no resources block                        # REQ-006 violation
            "securityContext": {
                "runAsNonRoot": False,                 # REQ-010 violation
                "privileged": True,                    # REQ-011 violation
                "readOnlyRootFilesystem": False,       # REQ-018 violation
                "allowPrivilegeEscalation": True,      # REQ-018 violation
                # no capabilities.drop                  # REQ-010 violation
            },
        }],
    }


def wrap(kind, pod_spec):
    """Wrap a pod spec in the given workload kind, at the correct nesting depth."""
    meta = {"name": f"test-{kind.lower()}", "namespace": "dora-test"}
    if kind == "Pod":
        return {"apiVersion": "v1", "kind": "Pod",
                "metadata": meta, "spec": pod_spec}
    if kind == "CronJob":
        return {
            "apiVersion": "batch/v1", "kind": "CronJob", "metadata": meta,
            "spec": {"schedule": "0 * * * *", "jobTemplate": {
                "spec": {"template": {"metadata": meta, "spec": pod_spec}}}},
        }
    api = "apps/v1"
    spec = {"template": {"metadata": meta, "spec": pod_spec}}
    if kind in ("Deployment", "StatefulSet"):
        spec["replicas"] = 2
    return {"apiVersion": api, "kind": kind, "metadata": meta, "spec": spec}


def constraint_parameters(repo_root, template_file):
    """Load the Constraint's `spec.parameters` for a given template.

    Gatekeeper passes these to the Rego as `input.parameters`. They live on the
    Constraint, not the ConstraintTemplate, so evaluating a template without
    them makes any parameterised rule fail open or fail closed depending on how
    it is written. REQ-023b reads `input.parameters.allowedRegistries`; omitting
    it produces a spurious violation on a perfectly compliant image.
    """
    stem = template_file.replace("-template.yaml", "")
    cdir = os.path.join(repo_root, "policies/gatekeeper/constraints")
    if not os.path.isdir(cdir):
        return {}
    for fn in os.listdir(cdir):
        if fn.startswith(stem):
            doc = yaml.safe_load(open(os.path.join(cdir, fn)))
            return (doc.get("spec") or {}).get("parameters") or {}
    return {}


def admission_input(obj, parameters=None):
    """Minimal AdmissionReview shape, matching what Gatekeeper passes to Rego."""
    return {"input": {
        "parameters": parameters or {},
        "review": {
            "kind": {"kind": obj["kind"]},
            "operation": "CREATE",
            "object": obj,
        },
    }}


# ----------------------------------------------------------------- evaluation
def extract_rego(path):
    doc = yaml.safe_load(open(path))
    return doc["spec"]["targets"][0]["rego"]


def package_name(rego):
    for line in rego.splitlines():
        if line.startswith("package "):
            return line.split()[1].strip()
    raise ValueError("no package declaration found")


def evaluate(opa_bin, rego, inp):
    """Run one OPA evaluation, returning the violation count.

    Returns (count, error_string). A template that errors is reported rather
    than silently counted as zero, because 'errored' and 'found nothing' are
    exactly the two outcomes this experiment must distinguish.
    """
    pkg = package_name(rego)
    with tempfile.TemporaryDirectory() as d:
        rf = os.path.join(d, "policy.rego")
        inf = os.path.join(d, "input.json")
        open(rf, "w").write(rego)
        json.dump(inp["input"], open(inf, "w"))
        # --v0-compatible is required: Gatekeeper ConstraintTemplates are
        # written in Rego v0 (bare `violation[...] { }` bodies), while OPA 1.x
        # defaults to Rego v1, which mandates the `if` and `contains` keywords.
        # Without this flag every template fails to parse and returns zero
        # violations, which would fake the very defect being measured.
        cmd = [opa_bin, "eval", "--v0-compatible", "--format", "json",
               "-d", rf, "-i", inf, f"data.{pkg}.violation"]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            return None, (p.stderr or "").strip().split("\n")[0][:160]
        try:
            out = json.loads(p.stdout)
            # OPA reports parse and type errors in the JSON body with exit
            # code 0. Treating those as "no violations" is exactly the failure
            # this experiment exists to expose, so they are surfaced instead.
            if out.get("errors"):
                return None, str(out["errors"][0].get("message", ""))[:160]
            res = out.get("result", [])
            if not res:
                return 0, ""
            exprs = res[0].get("expressions", [])
            if not exprs:
                return 0, ""
            val = exprs[0].get("value")
            return (len(val) if val else 0), ""
        except Exception as e:  # noqa: BLE001
            return None, f"parse error: {e}"


def load_version(repo_root, version):
    """Return {template_filename: rego}. v1 comes from git history."""
    out = {}
    for t in TEMPLATES:
        rel = f"policies/gatekeeper/templates/{t}"
        if version == "v2":
            path = os.path.join(repo_root, rel)
            if not os.path.exists(path):
                sys.exit(f"ERROR: missing {rel}")
            out[t] = extract_rego(path)
        else:
            p = subprocess.run(
                ["git", "-C", repo_root, "show", f"{FIX_COMMIT}^:{rel}"],
                capture_output=True, text=True)
            if p.returncode != 0:
                sys.exit(f"ERROR: cannot recover v1 of {rel} from git history.\n"
                         f"       Run this inside a full clone (not a shallow one).")
            out[t] = yaml.safe_load(p.stdout)["spec"]["targets"][0]["rego"]
    return out


# ----------------------------------------------------------------- reporting
def build_report(rows):
    L = ["# Finding 1: the controller-path defect, reproduced offline\n"]
    L.append(
        "\nSeven Gatekeeper ConstraintTemplates read container fields at "
        "`spec.containers` while their Constraints matched controller kinds. "
        "On a controller the containers are at `spec.template.spec.containers`, "
        "so the path does not exist. Rego iteration over a missing path binds "
        "nothing, the rule body never executes, and the template reports no "
        "violation without raising an error.\n")
    L.append(
        "\nThe table below evaluates both template versions against identical "
        "inputs. The column that matters is whether the compliant and violating "
        "counts DIFFER: if they are equal, the policy cannot discriminate and "
        "its detection accuracy is undefined rather than merely poor.\n")

    for version, label in [("v1", "v1 (before the fix)"),
                           ("v2", "v2 (after the fix)")]:
        L.append(f"\n## {label}\n\n")
        L.append("| Kind | Compliant input | Violating input | Discriminates? |\n")
        L.append("|---|---|---|---|\n")
        for kind in KINDS:
            c = sum(r["violations"] for r in rows
                    if r["version"] == version and r["kind"] == kind
                    and r["variant"] == "compliant" and r["violations"] is not None)
            v = sum(r["violations"] for r in rows
                    if r["version"] == version and r["kind"] == kind
                    and r["variant"] == "violating" and r["violations"] is not None)
            L.append(f"| {kind} | {c} | {v} | "
                     f"{'YES' if c != v else 'NO -- constant output'} |\n")

    # Per-template breakdown on a controller kind. This is where the two
    # opposite failure modes become visible in one table.
    L.append("\n## Per-template behaviour on a Deployment (v1)\n\n")
    L.append("| Template | Compliant | Violating | Failure mode |\n")
    L.append("|---|---|---|---|\n")
    for tname in sorted({r["template"] for r in rows}):
        c = next((r["violations"] for r in rows if r["version"] == "v1"
                  and r["template"] == tname and r["kind"] == "Deployment"
                  and r["variant"] == "compliant"), None)
        v = next((r["violations"] for r in rows if r["version"] == "v1"
                  and r["template"] == tname and r["kind"] == "Deployment"
                  and r["variant"] == "violating"), None)
        if c == 0 and v == 0:
            mode = "Silent -- iteration binds nothing (false negatives)"
        elif c == v and c and c > 0:
            mode = "Always fires -- missing field defaults (false positives)"
        else:
            mode = "Discriminates"
        L.append(f"| {tname} | {c} | {v} | {mode} |\n")
    L.append(
        "\nSix templates iterate with `collection[_]` over a path that does not "
        "exist on a controller. Iteration over a missing path binds nothing, so "
        "the body never runs and no violation is reported: false negatives, "
        "silently. One template, REQ-019, instead reads a scalar with "
        "`object.get(spec, \"serviceAccountName\", \"default\")`. On a controller "
        "that field is absent, so the fallback `\"default\"` is returned and the "
        "rule matches every object including compliant ones: false positives, "
        "loudly. The same authoring mistake produces opposite failures depending "
        "only on whether the rule iterates a collection or tests a scalar.\n")

    L.append("\n## Interpretation\n\n")
    L.append(
        "Both versions behave correctly on a bare `Pod`, which is the shape used "
        "in most Gatekeeper documentation and in most tutorial examples. That is "
        "why the defect survived review: the policies were demonstrably working "
        "on the object everyone tests with, and silently inert on the objects "
        "actually deployed.\n")
    return "".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="repository root")
    ap.add_argument("--opa", default="opa", help="path to the opa binary")
    ap.add_argument("--out", default="results/controller-path-defect")
    args = ap.parse_args()

    opa_bin = shutil.which(args.opa) or (
        args.opa if os.path.exists(args.opa) else None)
    if not opa_bin:
        sys.exit("ERROR: opa binary not found.\n"
                 "  Install:  curl -sL -o opa https://openpolicyagent.org/downloads/latest/opa_linux_amd64_static\n"
                 "            chmod +x opa\n"
                 "  Then:     python3 scripts/verify-controller-path-defect.py --opa ./opa")

    versions = {v: load_version(args.repo, v) for v in ("v1", "v2")}

    rows = []
    for version, templates in versions.items():
        for tname, rego in templates.items():
            params = constraint_parameters(args.repo, tname)
            for kind in KINDS:
                for variant, spec in [("compliant", compliant_pod_spec()),
                                      ("violating", violating_pod_spec())]:
                    inp = admission_input(wrap(kind, spec), params)
                    n, err = evaluate(opa_bin, rego, inp)
                    rows.append({
                        "version": version,
                        "template": tname.replace("-template.yaml", ""),
                        "kind": kind,
                        "variant": variant,
                        "violations": n,
                        "error": err,
                    })

    os.makedirs(args.out, exist_ok=True)
    csv_path = os.path.join(args.out, "controller-path-verdicts.csv")
    with open(csv_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "version", "template", "kind", "variant", "violations", "error"])
        w.writeheader()
        w.writerows(rows)

    report = build_report(rows)
    md_path = os.path.join(args.out, "controller-path-report.md")
    open(md_path, "w").write(report)

    print(report)
    print(f"\nWrote {csv_path}")
    print(f"Wrote {md_path}")

    # Summary assertion, printed so a reader sees the headline immediately.
    def total(version, kind, variant):
        return sum(r["violations"] for r in rows
                   if r["version"] == version and r["kind"] == kind
                   and r["variant"] == variant and r["violations"] is not None)

    controllers = [k for k in KINDS if k != "Pod"]
    v1_constant = all(total("v1", k, "compliant") == total("v1", k, "violating")
                      for k in controllers)
    v2_discriminates = all(total("v2", k, "compliant") < total("v2", k, "violating")
                           for k in KINDS)
    print(f"\nv1 output constant on all controller kinds : {v1_constant}")
    print(f"v2 discriminates on every kind             : {v2_discriminates}")


if __name__ == "__main__":
    main()
