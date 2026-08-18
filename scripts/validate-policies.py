#!/usr/bin/env python3
"""
validate-policies.py — pre-flight checks that catch silent Gatekeeper failures.

WHY THIS EXISTS
---------------
Gatekeeper requires a ConstraintTemplate's metadata.name to equal the lowercase
of spec.crd.spec.names.kind. When it does not, Gatekeeper does not error loudly:
the mismatched file is accepted as a NEW template, the original stays in place,
and the Constraint keeps binding to the original's CRD.

That is exactly what happened on 17 Aug 2026. A corrected template was named
`doranonroot` while its CRD kind was `DoraRunAsNonRoot`. `kubectl apply` reported
"created" rather than "configured", the count went from 25 to 26 templates, and
the old broken Rego stayed live. Verifying the file on disk showed the fix was
present; the cluster was still running the old logic. Cost: a full day.

Run this before every apply. It takes under a second.

USAGE
    python3 scripts/validate-policies.py
    python3 scripts/validate-policies.py --policies-dir policies

Exit code 0 = safe to apply. Non-zero = do not apply.
"""

import argparse
import glob
import os
import sys

import yaml

POD_FIELDS = {"containers", "initContainers", "serviceAccountName",
              "securityContext", "volumes", "hostNetwork", "hostPID", "hostIPC"}
CONTROLLER_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}

RED = "\033[0;31m"; GREEN = "\033[0;32m"; YELLOW = "\033[1;33m"; NC = "\033[0m"


def check_gatekeeper_templates(d):
    """The naming rule, plus controller-path coverage in the Rego."""
    errors, warnings = [], []
    for path in sorted(glob.glob(f"{d}/gatekeeper/templates/*.yaml")):
        name = os.path.basename(path)
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError as e:
            errors.append((name, f"unparseable YAML: {e}"))
            continue
        if not doc or doc.get("kind") != "ConstraintTemplate":
            continue

        meta = doc.get("metadata", {}).get("name", "")
        kind = doc.get("spec", {}).get("crd", {}).get("spec", {}).get("names", {}).get("kind", "")

        # THE rule. A mismatch here fails silently in-cluster.
        if meta != kind.lower():
            errors.append((name,
                f"metadata.name is '{meta}' but must be '{kind.lower()}' "
                f"(lowercase of CRD kind '{kind}'). Gatekeeper will create a "
                f"SECOND template and leave the original live."))

        rego = doc.get("spec", {}).get("targets", [{}])[0].get("rego", "")
        # Rego that touches pod fields but never resolves the controller path
        # will be silent on Deployments -- no error, no violation.
        if "spec.containers" in rego and "spec.template.spec" not in rego:
            errors.append((name,
                "Rego reads spec.containers with no spec.template.spec fallback. "
                "This is SILENT on controller kinds (no bindings, no violation)."))
        if "not input.review.object.spec." in rego and "pod_spec" not in rego:
            warnings.append((name,
                "negation on a possibly-absent scalar: undefined is truthy in "
                "Rego, so this fires on every controller object (false positive)."))
    return errors, warnings


def check_kyverno_policies(d):
    """Autogen is disabled by naming controllers explicitly."""
    errors, warnings = [], []
    for path in sorted(glob.glob(f"{d}/kyverno/*.yaml")):
        name = os.path.basename(path)
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError as e:
            errors.append((name, f"unparseable YAML: {e}"))
            continue
        if not doc or doc.get("kind") != "ClusterPolicy":
            continue

        for rule in doc.get("spec", {}).get("rules", []):
            kinds = set()
            for m in (rule.get("match", {}).get("any") or []):
                kinds |= set(m.get("resources", {}).get("kinds", []))

            validate = rule.get("validate") or {}
            pattern = validate.get("pattern") or {}
            spec = pattern.get("spec") if isinstance(pattern.get("spec"), dict) else {}
            touches_pod = bool(POD_FIELDS & set(spec.keys()))

            if touches_pod and (CONTROLLER_KINDS & kinds):
                errors.append((name,
                    f"rule '{rule.get('name')}' names controller kinds in "
                    f"match.kinds AND uses a pod-level path. This DISABLES "
                    f"autogen; the path is applied literally to the controller "
                    f"object where it does not exist. Match Pod only."))

            # Autogen does not rewrite JMESPath inside deny conditions.
            for cond in (validate.get("deny", {}).get("conditions", {}).get("any") or []):
                key = str(cond.get("key", ""))
                if "request.object.spec.containers" in key:
                    errors.append((name,
                        f"rule '{rule.get('name')}' uses "
                        f"request.object.spec.containers in a deny condition. "
                        f"Autogen does not rewrite JMESPath strings, so this "
                        f"never fires on controllers. Express it as a pattern."))
    return errors, warnings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policies-dir", default="policies")
    args = ap.parse_args()

    all_err, all_warn = [], []
    for fn in (check_gatekeeper_templates, check_kyverno_policies):
        e, w = fn(args.policies_dir)
        all_err += e
        all_warn += w

    print("=" * 78)
    print("POLICY PRE-FLIGHT VALIDATION")
    print("=" * 78)

    if all_warn:
        print(f"\n{YELLOW}WARNINGS ({len(all_warn)}){NC}")
        for f, m in all_warn:
            print(f"  {f}\n    {m}")

    if all_err:
        print(f"\n{RED}ERRORS ({len(all_err)}) — DO NOT APPLY{NC}")
        for f, m in all_err:
            print(f"  {f}\n    {m}")
        print(f"\n{RED}FAILED{NC} — fix the above before running kubectl apply.\n")
        return 1

    print(f"\n{GREEN}PASSED{NC} — no silent-failure conditions detected.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
