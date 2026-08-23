#!/usr/bin/env python3
"""
robustness-checks.py -- two rigour checks on the reported results.

CHECK 1: BLOCK INTEGRITY
------------------------
A randomised complete block design assumes conditions are homogeneous WITHIN a
block, so that comparing configurations inside a block is a fair comparison.
That assumption is testable after the fact: if the three configurations in a
block did not run close together in time, the block did not hold conditions
constant and the comparison inside it is contaminated.

This check measures each block's wall-clock span and flags any block whose span
is a gross outlier, then repeats the full statistical analysis with that block
removed. The exclusion criterion (elapsed time) is measured independently of the
outcome variable (latency), so this is a data-quality check rather than an
outcome-driven exclusion.

The all-blocks analysis remains the primary, pre-declared result. This is a
sensitivity analysis reported alongside it.

CHECK 2: INTERVAL ESTIMATES FOR PERFECT SCORES
----------------------------------------------
Precision, recall and F1 of 1.000 invite the reading that the engines are
perfectly accurate. They are not: a perfect point estimate from a finite suite
is bounded by the size of that suite. Clopper-Pearson exact intervals are
computed so the write-up can state what the data actually support.

USAGE
    python3 scripts/robustness-checks.py
    python3 scripts/robustness-checks.py --out results/robustness

OUTPUTS
    <out>/block-integrity.csv       per-block span and load spread
    <out>/sensitivity-comparison.csv  all-blocks vs reduced, both metrics
    <out>/detection-intervals.csv   Clopper-Pearson intervals
    <out>/robustness-report.md      narrative summary
"""

import argparse
import csv
import itertools
import os
from datetime import datetime

import numpy as np
from scipy import stats

CONFIGS = ["baseline", "kyverno", "gatekeeper"]
LABELS = {"baseline": "Baseline", "kyverno": "Kyverno",
          "gatekeeper": "OPA Gatekeeper"}
# Exclusion rules as pre-declared in the design chapter.
BAD_FLAG = {"admission_ms": ("clock_error",), "argocd_sync_ms": ("outlier",)}

# Ratio of a block's span to the median span above which the block is treated
# as having broken the homogeneity assumption. Set well above ordinary variation
# so only a gross violation trips it.
SPAN_OUTLIER_RATIO = 5.0


def load(path):
    return list(csv.DictReader(open(path)))


# --------------------------------------------------------- check 1: blocking
def block_spans(rows):
    out = []
    for b in sorted({r["cycle_block"] for r in rows}, key=int):
        sub = [r for r in rows if r["cycle_block"] == b]
        ts = [datetime.fromisoformat(r["timestamp"]) for r in sub]
        span = (max(ts) - min(ts)).total_seconds()
        loads = [float(r["load_before"]) for r in sub]
        out.append({
            "block": b,
            "span_seconds": round(span, 1),
            "load_min": round(min(loads), 2),
            "load_max": round(max(loads), 2),
            "load_spread": round(max(loads) - min(loads), 2),
        })
    med = float(np.median([r["span_seconds"] for r in out]))
    for r in out:
        r["span_vs_median"] = round(r["span_seconds"] / med, 1) if med else 0
        r["homogeneous"] = r["span_vs_median"] < SPAN_OUTLIER_RATIO
    return out, med


def block_medians(rows, metric, drop=()):
    bad = BAD_FLAG[metric]
    out = {}
    for b in sorted({r["cycle_block"] for r in rows}, key=int):
        if b in drop:
            continue
        vals = {}
        for c in CONFIGS:
            x = [float(r[metric]) for r in rows
                 if r["cycle_block"] == b and r["configuration"] == c
                 and r["quality_flag"] not in bad and float(r[metric]) >= 0]
            if x:
                vals[c] = float(np.median(x))
        if len(vals) == len(CONFIGS):
            out[b] = vals
    return out


def cliffs_delta(x, y):
    gt = sum(xi > yj for xi in x for yj in y)
    lt = sum(xi < yj for xi in x for yj in y)
    return (gt - lt) / (len(x) * len(y))


def magnitude(d):
    a = abs(d)
    if a < 0.147:
        return "negligible"
    if a < 0.33:
        return "small"
    if a < 0.474:
        return "medium"
    return "large"


def analyse(rows, metric, drop=()):
    bm = block_medians(rows, metric, drop)
    arr = {c: np.array([bm[b][c] for b in bm]) for c in CONFIGS}
    chi, p = stats.friedmanchisquare(*[arr[c] for c in CONFIGS])

    praw = {}
    for a, b in itertools.combinations(CONFIGS, 2):
        praw[(a, b)] = float(stats.wilcoxon(arr[a], arr[b])[1])

    # Holm step-down correction
    order = sorted(praw, key=lambda k: praw[k])
    adj, prev = {}, 0.0
    for i, k in enumerate(order):
        v = max(min(1.0, (len(order) - i) * praw[k]), prev)
        prev = v
        adj[k] = v

    pairs = []
    for a, b in itertools.combinations(CONFIGS, 2):
        d = cliffs_delta(arr[a], arr[b])
        pairs.append({
            "comparison": f"{LABELS[a]} vs {LABELS[b]}",
            "median_diff_ms": round(float(np.median(arr[a] - arr[b])), 1),
            "p_holm": round(adj[(a, b)], 4),
            "significant": adj[(a, b)] < 0.05,
            "cliffs_delta": round(d, 3),
            "magnitude": magnitude(d),
        })
    return {"n_blocks": len(bm), "friedman_chi2": round(float(chi), 4),
            "friedman_p": round(float(p), 4), "pairs": pairs}


# --------------------------------------------- check 2: intervals on 1.000
def clopper_pearson(k, n, conf=0.95):
    a = 1 - conf
    lo = 0.0 if k == 0 else float(stats.beta.ppf(a / 2, k, n - k + 1))
    hi = 1.0 if k == n else float(stats.beta.ppf(1 - a / 2, k + 1, n - k))
    return lo, hi


def detection_intervals():
    cases = [
        ("Specificity", "compliant manifests admitted", 21, 21),
        ("Recall", "Enforce-mode violations denied", 20, 20),
        ("Overall accuracy", "correct decisions", 41, 41),
    ]
    rows = []
    for name, desc, k, n in cases:
        lo, hi = clopper_pearson(k, n)
        rows.append({
            "measure": name, "basis": desc, "successes": k, "trials": n,
            "point_estimate": 1.000,
            "ci95_lower": round(lo, 3), "ci95_upper": round(hi, 3),
        })
    return rows


# ----------------------------------------------------------------- report
def build_report(spans, med_span, results, intervals):
    L = ["# Robustness checks\n"]

    L.append("\n## 1. Block integrity\n\n")
    L.append(
        "A randomised complete block design assumes conditions are homogeneous "
        "within a block. That is testable after the fact by measuring how long "
        "each block took: if the three configurations did not run close "
        "together, the block did not hold conditions constant.\n\n")
    L.append(f"Median block span: {med_span:.0f} s.\n\n")
    L.append("| Block | Span (s) | vs median | Load spread | Homogeneous |\n")
    L.append("|---|---|---|---|---|\n")
    for r in spans:
        L.append(f"| {r['block']} | {r['span_seconds']:.0f} | "
                 f"{r['span_vs_median']}x | {r['load_spread']:.2f} | "
                 f"{'yes' if r['homogeneous'] else 'NO'} |\n")

    bad = [r["block"] for r in spans if not r["homogeneous"]]
    if bad:
        L.append(
            f"\nBlock(s) {', '.join(bad)} violate the assumption. The exclusion "
            "criterion is elapsed time, measured independently of the outcome "
            "variable, so this is a data-quality judgement rather than an "
            "outcome-driven one.\n")

    L.append("\n## 2. Sensitivity of the conclusions\n\n")
    L.append(
        "The all-blocks analysis is the primary, pre-declared result. The "
        "reduced analysis is reported alongside it so a reader can see which "
        "conclusions depend on the contaminated block.\n")

    for metric, label in [("admission_ms", "Admission-path latency"),
                          ("argocd_sync_ms", "ArgoCD sync duration")]:
        L.append(f"\n### {label}\n\n")
        L.append("| Comparison | All blocks | Reduced | Robust? |\n")
        L.append("|---|---|---|---|\n")
        full, red = results[metric]["full"], results[metric]["reduced"]
        for pf, pr in zip(full["pairs"], red["pairs"]):
            fs = "significant" if pf["significant"] else "not significant"
            rs = "significant" if pr["significant"] else "not significant"
            robust = "YES" if pf["significant"] == pr["significant"] else "NO"
            L.append(f"| {pf['comparison']} | {fs} (p={pf['p_holm']}) | "
                     f"{rs} (p={pr['p_holm']}) | {robust} |\n")

    L.append("\n## 3. Interval estimates for the perfect detection scores\n\n")
    L.append(
        "Precision, recall and F1 of 1.000 are point estimates from a finite "
        "suite. Clopper-Pearson exact intervals show what the data support.\n\n")
    L.append("| Measure | Successes / trials | Point | 95% CI |\n")
    L.append("|---|---|---|---|\n")
    for r in intervals:
        L.append(f"| {r['measure']} | {r['successes']}/{r['trials']} | 1.000 | "
                 f"[{r['ci95_lower']:.3f}, {r['ci95_upper']:.3f}] |\n")
    L.append(
        "\nThe upper bound is 1.000 in every case, but the lower bound is well "
        "below it. A perfect score on this suite is consistent with a true "
        "accuracy materially lower than 1.000. The score certifies the suite, "
        "not the engine.\n")
    return "".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rcbd",
                    default="results/benchmark-rcbd-20260819-113918.csv")
    ap.add_argument("--out", default="results/robustness")
    args = ap.parse_args()

    rows = load(args.rcbd)
    spans, med_span = block_spans(rows)
    drop = tuple(r["block"] for r in spans if not r["homogeneous"])

    results = {}
    for metric in ("admission_ms", "argocd_sync_ms"):
        results[metric] = {
            "full": analyse(rows, metric),
            "reduced": analyse(rows, metric, drop),
        }

    intervals = detection_intervals()
    os.makedirs(args.out, exist_ok=True)

    with open(f"{args.out}/block-integrity.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(spans[0].keys()))
        w.writeheader()
        w.writerows(spans)

    comp = []
    for metric, res in results.items():
        for scope in ("full", "reduced"):
            for p in res[scope]["pairs"]:
                comp.append({"metric": metric, "scope": scope,
                             "n_blocks": res[scope]["n_blocks"],
                             "friedman_p": res[scope]["friedman_p"], **p})
    with open(f"{args.out}/sensitivity-comparison.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(comp[0].keys()))
        w.writeheader()
        w.writerows(comp)

    with open(f"{args.out}/detection-intervals.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(intervals[0].keys()))
        w.writeheader()
        w.writerows(intervals)

    report = build_report(spans, med_span, results, intervals)
    open(f"{args.out}/robustness-report.md", "w").write(report)
    print(report)
    print(f"\nWrote {args.out}/")
    if drop:
        print(f"Block(s) excluded from the sensitivity analysis: {', '.join(drop)}")


if __name__ == "__main__":
    main()
