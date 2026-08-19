#!/usr/bin/env python3
"""
generate-coverage-matrix.py — CA2 policy expressiveness coverage matrix.

WHAT CA2 ASKED FOR
------------------
"Policy expressiveness: For each of the 20-30 DORA requirements, can the tool
express a working admission policy? This will be recorded as a binary coverage
matrix (expressible / not expressible) for each tool, producing a percentage
coverage score."

WHY A PURE BINARY IS MISLEADING
-------------------------------
Taken literally, every requirement in this study is "expressible" by both engines,
because a policy file exists for all 25 in both. That would yield 100% / 100% and
say nothing at all.

The reason is that several policies do not validate the property the regulation
demands. They validate an ANNOTATION ASSERTING that property. REQ-022 is the
clearest case: DORA Art. 15(1) requires image signature verification, but the
implemented policy checks for `dora.io/image-signature-verified: "true"`. Any
author can add that annotation to an unsigned image. The policy is syntactically
valid and enforces nothing.

This matrix therefore reports THREE states per engine, and two coverage figures:

  DIRECT    the policy inspects the actual resource field the requirement
            concerns (e.g. securityContext.runAsNonRoot). Enforcement is real.
  ASSERTED  the policy checks an annotation claiming compliance. The claim is
            unverifiable by the admission controller; enforcement is procedural,
            not technical.
  ABSENT    no working policy exists.

  Binary coverage    = (DIRECT + ASSERTED) / total   — CA2's literal question
  Effective coverage = DIRECT / total                — what is actually enforced

The gap between those two numbers is the honest expressiveness finding, and it
is the same for both engines except at REQ-022, where Kyverno has a native
`verifyImages` rule type (Cosign/Notary) and Gatekeeper has no equivalent.

USAGE
    python3 scripts/generate-coverage-matrix.py
    python3 scripts/generate-coverage-matrix.py --out results/coverage-matrix.csv
"""

import argparse
import csv
import os
import re
import sys

import yaml

# Requirements whose policy validates only an annotation asserting compliance,
# rather than the underlying property. Determined by inspecting each policy: if
# the sole validated path is metadata.annotations.<x> and the requirement
# concerns a runtime property, it is an assertion proxy.
ASSERTION_PROXIED = {
    "REQ-005": "checks dora.io/kernel-audit-enabled annotation; cannot verify AppArmor/seccomp audit profiles are active",
    "REQ-020": "checks dora.io/logging-configured annotation; cannot verify a log collection agent is running",
    "REQ-022": "checks dora.io/image-signature-verified annotation; no cryptographic verification performed",
    "REQ-024": "checks dora.io/pdb-configured annotation; does not verify a PodDisruptionBudget object exists",
    "REQ-026": "checks dora.io/session-timeout-configured annotation; cannot verify ingress auth timeout",
    "REQ-027": "checks dora.io/dependencies annotation; contents are unvalidated free text",
    "REQ-017": "checks asset-metadata annotations; values are unvalidated free text",
    "REQ-015": "checks change-management annotations; cannot verify a change ticket exists or was approved",
}

# Native capability differences between the engines, beyond the shared proxying.
NATIVE_GAP = {
    "REQ-022": {
        "kyverno": "native verifyImages rule type supports Cosign and Notary signature verification",
        "gatekeeper": "no equivalent; requires an external data provider via the externaldata API",
    },
}


def classify(req_id, kyverno_policy, gatekeeper_policy, tier):
    """Return (kyverno_state, gatekeeper_state, note)."""
    k_state = "ABSENT" if not (kyverno_policy or "").strip() else "DIRECT"
    g_state = "ABSENT" if not (gatekeeper_policy or "").strip() else "DIRECT"

    note = ""
    if req_id in ASSERTION_PROXIED:
        if k_state == "DIRECT":
            k_state = "ASSERTED"
        if g_state == "DIRECT":
            g_state = "ASSERTED"
        note = ASSERTION_PROXIED[req_id]

    if req_id in NATIVE_GAP:
        gap = NATIVE_GAP[req_id]
        note = (note + " | " if note else "") + \
               f"Kyverno: {gap['kyverno']}. Gatekeeper: {gap['gatekeeper']}."

    if (tier or "").strip() == "not-automatable":
        k_state = g_state = "ABSENT"
        note = note or "classified not-automatable in the requirements register"

    return k_state, g_state, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--register", default="requirements/dora-requirements-register.csv")
    ap.add_argument("--out", default="results/coverage-matrix.csv")
    ap.add_argument("--md", default="results/coverage-matrix.md")
    args = ap.parse_args()

    if not os.path.exists(args.register):
        sys.exit(f"ERROR: register not found: {args.register}")

    rows = []
    with open(args.register) as fh:
        for r in csv.DictReader(fh):
            rid = (r.get("req_id") or "").strip()
            if not rid:
                continue
            k, g, note = classify(rid, r.get("kyverno_policy"),
                                  r.get("gatekeeper_policy"), r.get("coverage_tier"))
            rows.append({
                "req_id": rid,
                "dora_article": r.get("dora_subsection") or r.get("dora_article", ""),
                "requirement": (r.get("requirement_text") or "")[:70],
                "domain": r.get("technical_domain", ""),
                "kyverno": k,
                "gatekeeper": g,
                "note": note,
            })

    n = len(rows)
    def pct(state_fn):
        return 100.0 * sum(1 for x in rows if state_fn(x)) / n if n else 0.0

    k_binary = pct(lambda x: x["kyverno"] in ("DIRECT", "ASSERTED"))
    g_binary = pct(lambda x: x["gatekeeper"] in ("DIRECT", "ASSERTED"))
    k_direct = pct(lambda x: x["kyverno"] == "DIRECT")
    g_direct = pct(lambda x: x["gatekeeper"] == "DIRECT")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    L = ["# Policy Expressiveness Coverage Matrix\n",
         f"\nRequirements assessed: **{n}**\n",
         "\n| Coverage measure | Kyverno | OPA Gatekeeper |",
         "|---|---|---|",
         f"| Binary coverage (expressible at all) | {k_binary:.1f}% | {g_binary:.1f}% |",
         f"| Effective coverage (directly enforced) | {k_direct:.1f}% | {g_direct:.1f}% |",
         "\n**DIRECT** — the policy inspects the actual resource field the requirement",
         "concerns; enforcement is technical. **ASSERTED** — the policy checks an",
         "annotation claiming compliance, which the admission controller cannot verify;",
         "enforcement is procedural. **ABSENT** — no working policy.\n",
         "\n## Per-requirement matrix\n",
         "| REQ | Article | Requirement | Kyverno | Gatekeeper |",
         "|---|---|---|---|---|"]
    for x in rows:
        L.append(f"| {x['req_id']} | {x['dora_article']} | {x['requirement']} "
                 f"| {x['kyverno']} | {x['gatekeeper']} |")

    noted = [x for x in rows if x["note"]]
    if noted:
        L.append("\n## Notes on non-direct enforcement\n")
        for x in noted:
            L.append(f"- **{x['req_id']}** — {x['note']}")

    with open(args.md, "w") as fh:
        fh.write("\n".join(L) + "\n")

    print(f"{'REQ':10s}{'KYVERNO':12s}{'GATEKEEPER':12s}")
    print("-" * 40)
    for x in rows:
        print(f"{x['req_id']:10s}{x['kyverno']:12s}{x['gatekeeper']:12s}")
    print()
    print(f"Requirements: {n}")
    print(f"Binary coverage    — Kyverno {k_binary:.1f}%  Gatekeeper {g_binary:.1f}%")
    print(f"Effective coverage — Kyverno {k_direct:.1f}%  Gatekeeper {g_direct:.1f}%")
    print(f"\nWritten: {args.out} and {args.md}")


if __name__ == "__main__":
    main()
