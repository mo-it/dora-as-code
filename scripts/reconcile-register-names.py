#!/usr/bin/env python3
"""
reconcile-register-names.py — align the register with the deployed policy names.

THE PROBLEM
-----------
The requirements register records the policy names as originally designed, but
the deployed policies were named differently during implementation. Eleven of 25
disagree, and three pairs share no common substring at all:

    register                        deployed
    require-seccomp-audit           dora-art10-require-kernel-audit
    require-pod-disruption-budget   dora-art11-require-pdb
    require-security-context        dora-art9-require-security-hardening

No string-matching heuristic can bridge those. The compliance evidence hook
therefore could not resolve them to a DORA article and emitted req_id UNMAPPED,
which silently reduced the number of articles the evidence document could
attest to -- 12 of an expected ~20.

THE FIX
-------
Read each policy file's `dora.requirement` annotation, which states its REQ ID
directly, and write the actual `metadata.name` back into the register. The link
becomes a declared fact rather than an inferred one.

Policies whose annotation holds descriptive text instead of a REQ ID (an
inconsistency in the v1 policy set) are matched by filename prefix, which encodes
the requirement number, and reported so they can be corrected at source.

USAGE
    python3 scripts/reconcile-register-names.py --dry-run
    python3 scripts/reconcile-register-names.py
"""

import argparse
import csv
import glob
import os
import re
import sys

import yaml



def norm_req(r):
    """REQ IDs use an uppercase prefix but a lowercase sub-letter (REQ-023b)."""
    r = (r or "").strip().upper()
    return re.sub(r"([A-Z])$", lambda m: m.group(1).lower(), r)

def load_policies(kyverno_dir, gatekeeper_dir):
    """REQ ID -> {kyverno: name, gatekeeper: name}, from the files themselves."""
    found = {}
    weak = []

    for path in sorted(glob.glob(f"{kyverno_dir}/*.yaml")):
        base = os.path.basename(path)
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError as e:
            print(f"  [skip] {base}: {e}", file=sys.stderr)
            continue
        if not doc or doc.get("kind") != "ClusterPolicy":
            continue
        ann = doc.get("metadata", {}).get("annotations", {}) or {}
        req = (ann.get("dora.requirement") or "").strip()
        if not re.fullmatch(r"REQ-\d+b?", req, re.I):
            m = re.match(r"req(\d+b?)-", base)
            if not m:
                continue
            req = norm_req(f"REQ-{m.group(1)}")
            weak.append((base, ann.get("dora.requirement", "(absent)")))
        req = norm_req(req)
        found.setdefault(req, {})["kyverno"] = doc["metadata"]["name"]

    for path in sorted(glob.glob(f"{gatekeeper_dir}/*.yaml")):
        base = os.path.basename(path)
        try:
            doc = yaml.safe_load(open(path))
        except yaml.YAMLError:
            continue
        if not doc or doc.get("kind") != "ConstraintTemplate":
            continue
        ann = doc.get("metadata", {}).get("annotations", {}) or {}
        req = (ann.get("dora.requirement") or "").strip().upper()
        if not re.fullmatch(r"REQ-\d+B?", req):
            m = re.match(r"req(\d+b?)-", base)
            if not m:
                continue
            req = f"REQ-{m.group(1)}"
        req = norm_req(req)
        found.setdefault(req, {})["gatekeeper"] = doc["metadata"]["name"]

    return found, weak


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", default="requirements/dora-requirements-register.csv")
    ap.add_argument("--kyverno", default="policies/kyverno")
    ap.add_argument("--gatekeeper", default="policies/gatekeeper/templates")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    policies, weak = load_policies(args.kyverno, args.gatekeeper)
    print(f"Policies discovered: {len(policies)} requirement IDs\n")

    if weak:
        print("Policies without a machine-readable dora.requirement annotation")
        print("(matched by filename; worth correcting at source):")
        for base, val in weak:
            print(f"  {base:46s} annotation = {val!r}")
        print()

    rows = list(csv.DictReader(open(args.register)))
    changes = []
    for r in rows:
        rid = r["req_id"].strip()
        p = policies.get(norm_req(rid)) or {}
        for col, key in (("kyverno_policy", "kyverno"), ("gatekeeper_policy", "gatekeeper")):
            old = (r.get(col) or "").strip()
            new = p.get(key, "")
            if new and old != new:
                changes.append((rid, col, old or "(empty)", new))
                r[col] = new
            elif old and not new:
                changes.append((rid, col, old, "(no policy file found)"))
                r[col] = ""

    print(f"{'REQ':10s}{'COLUMN':20s}{'WAS':38s}NOW")
    print("-" * 110)
    for rid, col, old, new in changes:
        print(f"{rid:10s}{col:20s}{old:38s}{new}")
    print(f"\n{len(changes)} corrections")

    if args.dry_run:
        print("\n(dry run - register not written)")
        return

    with open(args.register, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"\nRegister updated: {args.register}")
    print("Rebuild the evidence hook so the mapping is refreshed:")
    print("  python3 scripts/build-evidence-hook.py")


if __name__ == "__main__":
    main()
