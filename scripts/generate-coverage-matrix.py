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
import json
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



# ---------------------------------------------------------------------------
# Coverage class is DERIVED from policy source, not from a hand-maintained list.
#
# Rule (stated in the design chapter and applied mechanically here):
#
#   DIRECT    the validate logic inspects at least one field that governs
#             runtime behaviour (a spec field, or a top-level functional field
#             such as ClusterRole.rules or Secret.type).
#
#   ASSERTED  the validate logic inspects only metadata that a human wrote
#             (labels or annotations). Such a policy verifies that a claim was
#             made, not that the claim is true.
#
#   ABSENT    no policy exists, or the requirement is not automatable.
#
# `kind` and `apiVersion` are treated as non-functional: they identify the
# object under test rather than describing its configuration.
#
# Deriving this rather than listing it is deliberate. An earlier hand-maintained
# list classified REQ-028 as DIRECT while REQ-024, which has the identical
# annotation-proxy shape, was ASSERTED. A mapping that nothing mechanically
# consumes drifts -- the same failure this study documents for the requirements
# register itself.
# ---------------------------------------------------------------------------
NON_FUNCTIONAL_PREFIXES = ("metadata", "kind", "apiVersion")


def _pattern_paths(obj, prefix=""):
    """Every leaf path referenced by a Kyverno validate pattern."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "message":
                continue
            # Kyverno conditional-anchor syntax: =(field), &(field), ~(field)
            key = re.sub(r"^[=&~^<>!+]?\((.*)\)$", r"\1", str(k))
            yield from _pattern_paths(v, f"{prefix}.{key}" if prefix else key)
    elif isinstance(obj, list):
        for v in obj:
            yield from _pattern_paths(v, prefix)
    else:
        if prefix:
            yield prefix


def _jmespath_refs(blob):
    """Object paths referenced inside {{ ... }} expressions."""
    out = []
    for expr in re.findall(r"\{\{(.*?)\}\}", blob, re.S):
        for m in re.findall(r"request\.object\.([A-Za-z0-9_.\[\]]+)", expr):
            out.append(m.strip("."))
    return out


def derive_kyverno_class(policy_path):
    """DIRECT or ASSERTED for one Kyverno ClusterPolicy file."""
    doc = yaml.safe_load(open(policy_path))
    refs = []
    for rule in (doc.get("spec", {}).get("rules") or []):
        v = rule.get("validate") or {}
        for key in ("pattern", "anyPattern", "deny", "foreach"):
            if key in v:
                refs += list(_pattern_paths(v[key]))
        refs += _jmespath_refs(json.dumps(v))
    functional = [r for r in refs
                  if not any(r == p or r.startswith(p)
                             for p in NON_FUNCTIONAL_PREFIXES)]
    return ("DIRECT" if functional else "ASSERTED"), sorted(set(refs))


def derive_gatekeeper_class(template_path):
    """DIRECT or ASSERTED for one Gatekeeper ConstraintTemplate file."""
    doc = yaml.safe_load(open(template_path))
    rego = doc["spec"]["targets"][0].get("rego", "")
    # Strip comments and message strings so prose does not count as a reference.
    body = "\n".join(l.split("#")[0] for l in rego.splitlines())
    body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', body)
    # Only count real object-path references. Matching bare identifiers such as
    # `pod_spec` or `containers` would count the boilerplate helper that every
    # template defines, whether or not the violation rule uses it.
    refs = re.findall(r"input\.review\.object\.([A-Za-z0-9_.\[\]]+)", body)
    # `object.get(input.review.object.metadata, "annotations", {})` puts the
    # field name in the second argument rather than the path, so the path above
    # reads as bare `metadata`; that is still metadata and stays non-functional.
    refs += re.findall(r"pod_spec\[_\]\.([A-Za-z0-9_.\[\]]+)", body)
    refs += re.findall(r"\bpod\.([A-Za-z0-9_.\[\]]+)", body)
    refs += re.findall(r"\bcontainer\.([A-Za-z0-9_.\[\]]+)", body)
    functional = [r for r in refs
                  if not any(r == p or r.startswith(p)
                             for p in NON_FUNCTIONAL_PREFIXES)]
    return ("DIRECT" if functional else "ASSERTED"), sorted(set(refs))


def _find_policy(directory, name):
    if not name or not os.path.isdir(directory):
        return None
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith((".yaml", ".yml")):
            continue
        try:
            doc = yaml.safe_load(open(os.path.join(directory, fn)))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        if (doc.get("metadata") or {}).get("name") == name:
            return os.path.join(directory, fn)
    return None


def classify(req_id, kyverno_policy, gatekeeper_policy, tier):
    """Return (kyverno_state, gatekeeper_state, note)."""
    note = ""
    k_state = "ABSENT"
    g_state = "ABSENT"

    kp = _find_policy("policies/kyverno", (kyverno_policy or "").strip())
    if kp:
        k_state, _ = derive_kyverno_class(kp)
    gt = _find_policy("policies/gatekeeper/templates",
                      (gatekeeper_policy or "").strip())
    if gt:
        g_state, _ = derive_gatekeeper_class(gt)

    if req_id in ASSERTION_PROXIED:
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
