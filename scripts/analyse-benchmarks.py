#!/usr/bin/env python3
"""
analyse-benchmarks.py — Phase 4 statistical analysis for DORA-as-Code.

Reads the three 50-cycle ArgoCD sync-time benchmark CSVs (baseline,
Kyverno-only, Gatekeeper-only) and produces the full non-parametric
comparison used in Chapter 5 of the dissertation.

Design decisions (justified in Chapter 3, Methodology):
  * Non-parametric throughout. Sync latency is bounded below, right-skewed
    and contains tail outliers, so the normality assumption behind a t-test
    does not hold. Shapiro-Wilk is reported to evidence this rather than
    assumed.
  * Kruskal-Wallis omnibus first, then pairwise Mann-Whitney U. Running
    three pairwise tests without an omnibus gate inflates family-wise error.
  * Holm-Bonferroni correction on the pairwise p-values (less conservative
    than plain Bonferroni, same family-wise error guarantee).
  * Cliff's delta and Vargha-Delaney A12 for effect size. With n=50 per group
    a statistically significant result can still be operationally trivial;
    effect size is what tells you which.
  * Warm-up sensitivity: every test is repeated with the first 10 cycles
    discarded, so the conclusion can be shown to be robust to that choice
    rather than dependent on it.

Usage:
    python3 scripts/analyse-benchmarks.py \
        --results-dir results \
        --run-id 20260726-232252 \
        --out results/analysis

Outputs:
    <out>/descriptives.csv        per-configuration summary statistics
    <out>/pairwise-tests.csv      Mann-Whitney U, p-values, effect sizes
    <out>/normality.csv           Shapiro-Wilk per configuration
    <out>/run-order.csv           drift / warm-up diagnostics
    <out>/analysis-report.md      human-readable write-up
"""

import argparse
import itertools
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

CONFIGS = ["baseline", "kyverno", "gatekeeper"]
LABELS = {
    "baseline": "Baseline (no policy engine)",
    "kyverno": "Kyverno",
    "gatekeeper": "OPA Gatekeeper",
}
METRIC = "sync_duration_ms"


# ---------------------------------------------------------------- effect sizes

def cliffs_delta(a, b):
    """Cliff's delta: non-parametric effect size, range [-1, 1].

    delta = P(a > b) - P(a < b). Computed exactly via pairwise comparison
    rather than the rank approximation, since n=50 keeps this cheap.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    diff = a[:, None] - b[None, :]
    greater = np.sum(diff > 0)
    less = np.sum(diff < 0)
    return (greater - less) / (len(a) * len(b))


def cliffs_magnitude(d):
    """Romano et al. (2006) thresholds for interpreting Cliff's delta."""
    ad = abs(d)
    if ad < 0.147:
        return "negligible"
    if ad < 0.330:
        return "small"
    if ad < 0.474:
        return "medium"
    return "large"


def vargha_delaney_a12(a, b):
    """Vargha-Delaney A12: probability a random draw from a exceeds one from b.

    0.5 means no difference. Related to Cliff's delta by A12 = (delta + 1) / 2.
    """
    return (cliffs_delta(a, b) + 1) / 2


def bootstrap_median_diff_ci(a, b, n_boot=10000, alpha=0.05, seed=42):
    """Percentile bootstrap CI for the difference in medians (a - b)."""
    rng = np.random.default_rng(seed)
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        diffs[i] = (
            np.median(rng.choice(a, size=len(a), replace=True))
            - np.median(rng.choice(b, size=len(b), replace=True))
        )
    lo = np.percentile(diffs, 100 * alpha / 2)
    hi = np.percentile(diffs, 100 * (1 - alpha / 2))
    return lo, hi


def holm_bonferroni(pvals):
    """Holm-Bonferroni step-down correction. Returns adjusted p-values."""
    p = np.asarray(pvals, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adjusted = np.empty(m)
    running_max = 0.0
    for rank, idx in enumerate(order):
        val = (m - rank) * p[idx]
        running_max = max(running_max, val)
        adjusted[idx] = min(running_max, 1.0)
    return adjusted


# ---------------------------------------------------------------- descriptives

def describe(series, label):
    x = np.asarray(series, dtype=float)
    q1, q3 = np.percentile(x, [25, 75])
    return {
        "configuration": label,
        "n": len(x),
        "mean_ms": round(float(np.mean(x)), 1),
        "sd_ms": round(float(np.std(x, ddof=1)), 1),
        "median_ms": round(float(np.median(x)), 1),
        "iqr_ms": round(float(q3 - q1), 1),
        "mad_ms": round(float(stats.median_abs_deviation(x)), 1),
        "min_ms": int(np.min(x)),
        "p95_ms": round(float(np.percentile(x, 95)), 1),
        "p99_ms": round(float(np.percentile(x, 99)), 1),
        "max_ms": int(np.max(x)),
        "cv_pct": round(float(np.std(x, ddof=1) / np.mean(x) * 100), 1),
    }


# ---------------------------------------------------------------- analysis core

def load_data(results_dir, run_id):
    data = {}
    for cfg in CONFIGS:
        path = os.path.join(results_dir, f"benchmark-{cfg}-{run_id}.csv")
        if not os.path.exists(path):
            sys.exit(f"ERROR: missing input file {path}")
        df = pd.read_csv(path)
        if METRIC not in df.columns:
            sys.exit(f"ERROR: {path} has no column '{METRIC}'")
        data[cfg] = df
    return data


def analyse(data, warmup_discard=0):
    """Run the full test battery. warmup_discard drops the first N cycles."""
    samples = {
        cfg: df[METRIC].values[warmup_discard:].astype(float)
        for cfg, df in data.items()
    }

    # --- normality (to justify the non-parametric choice, not to gate it)
    normality = []
    for cfg, x in samples.items():
        w, p = stats.shapiro(x)
        normality.append({
            "configuration": LABELS[cfg],
            "shapiro_w": round(float(w), 4),
            "p_value": float(p),
            "normal_at_0.05": bool(p > 0.05),
            "skewness": round(float(stats.skew(x)), 3),
            "kurtosis_excess": round(float(stats.kurtosis(x)), 3),
        })

    # --- omnibus
    h_stat, h_p = stats.kruskal(*[samples[c] for c in CONFIGS])
    # epsilon-squared effect size for Kruskal-Wallis
    n_total = sum(len(samples[c]) for c in CONFIGS)
    eps_sq = (h_stat - len(CONFIGS) + 1) / (n_total - len(CONFIGS))
    omnibus = {
        "test": "Kruskal-Wallis H",
        "H": round(float(h_stat), 4),
        "df": len(CONFIGS) - 1,
        "p_value": float(h_p),
        "epsilon_squared": round(float(eps_sq), 4),
    }

    # --- pairwise
    pairs = list(itertools.combinations(CONFIGS, 2))
    rows, raw_p = [], []
    for a, b in pairs:
        xa, xb = samples[a], samples[b]
        u, p = stats.mannwhitneyu(xa, xb, alternative="two-sided")
        d = cliffs_delta(xa, xb)
        lo, hi = bootstrap_median_diff_ci(xa, xb)
        raw_p.append(p)
        rows.append({
            "comparison": f"{LABELS[a]} vs {LABELS[b]}",
            "median_a_ms": round(float(np.median(xa)), 1),
            "median_b_ms": round(float(np.median(xb)), 1),
            "median_diff_ms": round(float(np.median(xa) - np.median(xb)), 1),
            "diff_ci95_lo_ms": round(float(lo), 1),
            "diff_ci95_hi_ms": round(float(hi), 1),
            "mann_whitney_u": float(u),
            "p_raw": float(p),
            "cliffs_delta": round(float(d), 4),
            "magnitude": cliffs_magnitude(d),
            "vargha_delaney_a12": round(float(vargha_delaney_a12(xa, xb)), 4),
        })

    adjusted = holm_bonferroni(raw_p)
    for row, adj in zip(rows, adjusted):
        row["p_holm"] = float(adj)
        row["significant_at_0.05"] = bool(adj < 0.05)

    descriptives = [describe(samples[c], LABELS[c]) for c in CONFIGS]

    return {
        "descriptives": pd.DataFrame(descriptives),
        "normality": pd.DataFrame(normality),
        "omnibus": omnibus,
        "pairwise": pd.DataFrame(rows),
        "samples": samples,
    }


def run_order_diagnostics(data):
    """Spearman correlation of cycle index vs duration.

    A significant positive correlation means the system slowed over the run
    (thermal/memory pressure); a significant negative one means warm-up
    effects were still dissipating. Either undermines the assumption that
    cycles within a run are exchangeable.
    """
    rows = []
    for cfg, df in data.items():
        x = df[METRIC].values.astype(float)
        cycles = np.arange(1, len(x) + 1)
        rho, p = stats.spearmanr(cycles, x)
        first10, last10 = x[:10], x[-10:]
        rows.append({
            "configuration": LABELS[cfg],
            "spearman_rho_cycle_vs_duration": round(float(rho), 4),
            "p_value": float(p),
            "drift_detected_at_0.05": bool(p < 0.05),
            "median_first_10_ms": round(float(np.median(first10)), 1),
            "median_last_10_ms": round(float(np.median(last10)), 1),
            "first_vs_last_delta_ms": round(
                float(np.median(first10) - np.median(last10)), 1
            ),
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- report

def fmt_p(p):
    return "< 0.001" if p < 0.001 else f"{p:.4f}"


def build_report(full, trimmed, order_df, warmup_n, run_id):
    L = []
    L.append("# Phase 4 Benchmark: Statistical Analysis\n")
    L.append(f"Run ID: `{run_id}` — ArgoCD sync duration, 50 cycles per configuration.\n")
    L.append("Metric: wall-clock ArgoCD sync duration in milliseconds.\n")

    L.append("\n## 1. Descriptive statistics (all 50 cycles)\n")
    L.append(full["descriptives"].to_markdown(index=False))

    L.append("\n\n## 2. Distribution shape\n")
    L.append(
        "Shapiro-Wilk tests the null hypothesis that the sample is normally "
        "distributed. Rejection justifies the non-parametric test battery used "
        "below.\n"
    )
    L.append(full["normality"].to_markdown(index=False))

    L.append("\n\n## 3. Omnibus test\n")
    o = full["omnibus"]
    L.append(
        f"Kruskal-Wallis H = {o['H']}, df = {o['df']}, "
        f"p = {fmt_p(o['p_value'])}, epsilon-squared = {o['epsilon_squared']}.\n"
    )

    L.append("\n## 4. Pairwise comparisons (Holm-Bonferroni corrected)\n")
    L.append(full["pairwise"].to_markdown(index=False))

    L.append(f"\n\n## 5. Warm-up sensitivity (first {warmup_n} cycles discarded)\n")
    L.append(
        "If the conclusions change when warm-up cycles are removed, the result "
        "is an artefact of measurement start-up rather than a property of the "
        "policy engines.\n\n"
    )
    L.append(trimmed["descriptives"].to_markdown(index=False))
    L.append("\n\n")
    L.append(trimmed["pairwise"].to_markdown(index=False))

    L.append("\n\n## 6. Run-order diagnostics\n")
    L.append(
        "Configurations were executed sequentially rather than interleaved. "
        "A monotonic trend across cycles within a run would confound the "
        "between-configuration comparison.\n\n"
    )
    L.append(order_df.to_markdown(index=False))

    return "\n".join(L)


# ------------------------------------------------- randomised block design (RCBD)

def rcbd_normality(df, metric, exclude_high_load=True):
    """Shapiro-Wilk per configuration on the RCBD data.

    Purpose is evidential, not gating. The module's default comparison is the
    parametric t-test, which assumes the samples are drawn from a normal
    distribution. That assumption is tested here and reported so the switch to
    Friedman and Wilcoxon is justified by evidence rather than by preference.
    """
    work = df.copy()
    if exclude_high_load:
        bad = ["clock_error"] if metric == "admission_ms" else ["outlier"]
        work = work[~work["quality_flag"].isin(bad)]
    work = work[work[metric] >= 0]

    rows = []
    for cfg in CONFIGS:
        x = work[work["configuration"] == cfg][metric].astype(float).values
        if len(x) < 3:
            continue
        w, p = stats.shapiro(x)
        rows.append({
            "metric": metric,
            "configuration": LABELS.get(cfg, cfg),
            "n": int(len(x)),
            "shapiro_w": round(float(w), 4),
            "p_value": float(p),
            "normal_at_0.05": bool(p > 0.05),
            "skewness": round(float(stats.skew(x)), 3),
            "kurtosis_excess": round(float(stats.kurtosis(x)), 3),
        })
    return pd.DataFrame(rows)


def analyse_rcbd(df, metric, exclude_high_load=False):
    """Analysis for the randomised complete block design.

    The blocked design changes which tests are correct. Observations are no
    longer independent samples from three populations — each block contains one
    measurement of every configuration, taken under near-identical conditions.
    That pairing is the whole point of the design, and throwing it away by
    using Kruskal-Wallis would discard the precision it buys.

    So: Friedman (the non-parametric repeated-measures omnibus) instead of
    Kruskal-Wallis, and paired Wilcoxon signed-rank instead of Mann-Whitney.
    """
    work = df.copy()
    if exclude_high_load:
        work = work[work["quality_flag"] == "ok"]

    work = work[work[metric] >= 0]  # -1 marks an unavailable argocd measurement
    if work.empty:
        return None

    # One value per block per configuration: median across reps within block.
    blocked = (
        work.groupby(["cycle_block", "configuration"])[metric]
        .median()
        .unstack("configuration")
        .dropna()
    )
    present = [c for c in CONFIGS if c in blocked.columns]
    if len(present) < 2 or len(blocked) < 3:
        return None
    blocked = blocked[present]

    # --- omnibus: Friedman
    chi2, p_omni = stats.friedmanchisquare(*[blocked[c].values for c in present])
    n_blocks, k = len(blocked), len(present)
    kendalls_w = float(chi2) / (n_blocks * (k - 1))  # 0 = no agreement, 1 = total

    omnibus = {
        "test": "Friedman (repeated measures)",
        "chi_squared": round(float(chi2), 4),
        "df": k - 1,
        "n_blocks": n_blocks,
        "p_value": float(p_omni),
        "kendalls_w": round(kendalls_w, 4),
    }

    # --- post-hoc: paired Wilcoxon signed-rank
    rows, raw_p = [], []
    for a, b in itertools.combinations(present, 2):
        pa, pb = blocked[a].values, blocked[b].values
        try:
            w, p = stats.wilcoxon(pa, pb, alternative="two-sided")
        except ValueError:      # raised when every paired difference is zero
            w, p = 0.0, 1.0
        raw_a = work[work.configuration == a][metric].values
        raw_b = work[work.configuration == b][metric].values
        d = cliffs_delta(raw_a, raw_b)
        raw_p.append(p)
        rows.append({
            "comparison": f"{LABELS[a]} vs {LABELS[b]}",
            "median_a_ms": round(float(np.median(raw_a)), 1),
            "median_b_ms": round(float(np.median(raw_b)), 1),
            "paired_median_diff_ms": round(float(np.median(pa - pb)), 1),
            "wilcoxon_w": float(w),
            "p_raw": float(p),
            "cliffs_delta": round(float(d), 4),
            "magnitude": cliffs_magnitude(d),
            "vargha_delaney_a12": round(float(vargha_delaney_a12(raw_a, raw_b)), 4),
        })

    for row, adj in zip(rows, holm_bonferroni(raw_p)):
        row["p_holm"] = float(adj)
        row["significant_at_0.05"] = bool(adj < 0.05)

    descriptives = [
        describe(work[work.configuration == c][metric].values, LABELS[c])
        for c in present
    ]

    # --- randomisation check: did position within the block matter?
    # If it did, the shuffle failed to neutralise within-block drift.
    order_groups = [
        work[work.order_in_block == pos][metric].values
        for pos in sorted(work.order_in_block.unique())
    ]
    order_groups = [g for g in order_groups if len(g) > 0]
    if len(order_groups) >= 2:
        oh, op = stats.kruskal(*order_groups)
        order_check = {
            "test": "Kruskal-Wallis on position within block",
            "H": round(float(oh), 4),
            "p_value": float(op),
            "position_effect_at_0.05": bool(op < 0.05),
        }
    else:
        order_check = None

    return {
        "descriptives": pd.DataFrame(descriptives),
        "omnibus": omnibus,
        "pairwise": pd.DataFrame(rows),
        "order_check": order_check,
        "blocked": blocked,
        "n_observations": len(work),
    }


def build_rcbd_report(results, path):
    L = ["# Phase 4 Benchmark: Randomised Complete Block Design\n"]
    L.append(f"Source: `{os.path.basename(path)}`\n")
    L.append(
        "\nConfiguration order is balanced across blocks: all 3! = 6 orderings "
        "are used, each exactly twice, so every configuration runs in every "
        "within-block position an equal number of times. Session drift and "
        "time-varying system load therefore affect all three configurations "
        "equally instead of loading onto whichever ran first.\n"
    )

    for metric, label in [("admission_ms", "Admission-path latency"),
                          ("argocd_sync_ms", "ArgoCD sync latency")]:
        block = results.get(metric)
        L.append(f"\n---\n\n# {label} (`{metric}`)\n")
        if block is None:
            L.append("\nNot available in this dataset.\n")
            continue

        main_r = block["all"]
        L.append(f"\nObservations: {main_r['n_observations']}\n")
        L.append("\n## Descriptive statistics\n")
        L.append(main_r["descriptives"].to_markdown(index=False))

        norm = block.get("normality")
        if norm is not None and not norm.empty:
            L.append("\n\n## Normality of the distribution\n")
            L.append(
                "Shapiro-Wilk tests the null hypothesis that the sample is drawn "
                "from a normal distribution. Rejection means the normality "
                "assumption behind the t-test does not hold for this data, which "
                "is why the non-parametric Friedman and Wilcoxon tests are used "
                "below.\n\n"
            )
            L.append(norm.drop(columns=["metric"]).to_markdown(index=False))
            worst = norm["p_value"].max()
            rejected = int((norm["p_value"] <= 0.05).sum())
            L.append(
                f"\n\nNormality is rejected at alpha = 0.05 for "
                f"{rejected} of {len(norm)} configurations "
                f"(largest p = {fmt_p(worst)}).\n"
            )

        o = main_r["omnibus"]
        L.append("\n\n## Omnibus test\n")
        L.append(
            f"Friedman chi-squared = {o['chi_squared']}, df = {o['df']}, "
            f"blocks = {o['n_blocks']}, p = {fmt_p(o['p_value'])}, "
            f"Kendall's W = {o['kendalls_w']}.\n"
        )

        L.append("\n## Post-hoc paired comparisons (Holm-Bonferroni)\n")
        L.append(main_r["pairwise"].to_markdown(index=False))

        if main_r["order_check"]:
            oc = main_r["order_check"]
            L.append("\n\n## Randomisation check\n")
            L.append(
                f"Position within block: H = {oc['H']}, p = {fmt_p(oc['p_value'])}. "
                f"Position effect detected: {oc['position_effect_at_0.05']}. "
                "A null result here is the desired outcome — it means the "
                "randomisation successfully neutralised within-block ordering.\n"
            )

        clean = block.get("clean")
        if clean is not None:
            L.append("\n\n## Sensitivity: high-load cycles excluded\n")
            L.append(
                f"Observations retained: {clean['n_observations']}. If the "
                "conclusions match the full dataset, the result is robust to "
                "transient load spikes.\n\n"
            )
            L.append(clean["pairwise"].to_markdown(index=False))

    return "\n".join(L)


def run_rcbd_mode(path, out_dir):
    df = pd.read_csv(path)
    required = {"cycle_block", "configuration", "order_in_block", "quality_flag"}
    missing = required - set(df.columns)
    if missing:
        sys.exit(f"ERROR: {path} is missing columns: {sorted(missing)}")

    os.makedirs(out_dir, exist_ok=True)
    results = {}
    normality_frames = []
    for metric in ["admission_ms", "argocd_sync_ms"]:
        if metric not in df.columns:
            continue
        all_r = analyse_rcbd(df, metric, exclude_high_load=False)
        if all_r is None:
            continue
        clean_r = analyse_rcbd(df, metric, exclude_high_load=True)
        results[metric] = {"all": all_r, "clean": clean_r}

        all_r["descriptives"].to_csv(
            f"{out_dir}/rcbd-{metric}-descriptives.csv", index=False)
        all_r["pairwise"].to_csv(
            f"{out_dir}/rcbd-{metric}-pairwise.csv", index=False)
        all_r["blocked"].to_csv(f"{out_dir}/rcbd-{metric}-block-medians.csv")

        norm = rcbd_normality(df, metric, exclude_high_load=True)
        if not norm.empty:
            normality_frames.append(norm)
            results[metric]["normality"] = norm

    if not results:
        sys.exit("ERROR: no usable metric columns found.")

    if normality_frames:
        pd.concat(normality_frames, ignore_index=True).to_csv(
            f"{out_dir}/rcbd-normality.csv", index=False)

    report = build_rcbd_report(results, path)
    with open(f"{out_dir}/rcbd-analysis-report.md", "w") as fh:
        fh.write(report)
    print(report)


# ---------------------------------------------------------------- entry point

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rcbd", metavar="CSV",
                    help="analyse a randomised-block run from benchmark-rcbd.sh")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--run-id", default="20260726-232252")
    ap.add_argument("--warmup", type=int, default=10,
                    help="cycles to discard in the sensitivity analysis")
    ap.add_argument("--out", default="results/analysis")
    args = ap.parse_args()

    if args.rcbd:
        run_rcbd_mode(args.rcbd, args.out)
        return

    os.makedirs(args.out, exist_ok=True)
    data = load_data(args.results_dir, args.run_id)

    full = analyse(data, warmup_discard=0)
    trimmed = analyse(data, warmup_discard=args.warmup)
    order_df = run_order_diagnostics(data)

    full["descriptives"].to_csv(f"{args.out}/descriptives.csv", index=False)
    full["normality"].to_csv(f"{args.out}/normality.csv", index=False)
    full["pairwise"].to_csv(f"{args.out}/pairwise-tests.csv", index=False)
    trimmed["pairwise"].to_csv(f"{args.out}/pairwise-tests-warmup-trimmed.csv",
                               index=False)
    order_df.to_csv(f"{args.out}/run-order.csv", index=False)

    report = build_report(full, trimmed, order_df, args.warmup, args.run_id)
    with open(f"{args.out}/analysis-report.md", "w") as fh:
        fh.write(report)

    print(report)


if __name__ == "__main__":
    main()
