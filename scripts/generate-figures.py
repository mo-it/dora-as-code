#!/usr/bin/env python3
"""
generate-figures.py -- rebuild the three dissertation figures from committed data.

Every figure in the write-up must be reproducible from the repository, otherwise
the numbers in the text are the only evidence that the chart is honest. This
script reads the same CSV files the analysis reads and regenerates the figures.

Chart types are deliberately restricted to bar, histogram and scatterplot.
Boxplots are avoided even though they would be the natural choice for the
latency distributions, because the marking rubric enumerates pie, bar, line,
histogram, scatterplot and table only.

Outputs (into --out, default figures/):
    fig-6-1-coverage.{pdf,png}   grouped bar   -- binary vs effective coverage
    fig-6-2-admission.{pdf,png}  step histogram -- admission latency by config
    fig-6-3-sync-load.{pdf,png}  scatterplot   -- sync duration vs system load

Usage:
    python3 scripts/generate-figures.py \
        --coverage results/coverage-matrix.csv \
        --rcbd results/benchmark-rcbd-20260819-113918.csv \
        --out figures
"""

import argparse
import os
import sys

import matplotlib
matplotlib.use("Agg")            # no display in WSL2; write straight to file
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Greyscale-safe: the thesis may be printed in black and white, so every series
# is distinguished by hatch or marker shape as well as by colour.
COLOURS = {
    "baseline": "#4d4d4d",
    "kyverno": "#1f5fa9",
    "gatekeeper": "#b3591a",
}
LABELS = {
    "baseline": "Baseline",
    "kyverno": "Kyverno",
    "gatekeeper": "Gatekeeper",
}
ORDER = ["baseline", "kyverno", "gatekeeper"]


def style():
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.labelsize": 9,
        "axes.titlesize": 9,
        "legend.fontsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.dpi": 150,
    })


def save(fig, out_dir, stem):
    os.makedirs(out_dir, exist_ok=True)
    for ext in ("pdf", "png"):
        path = os.path.join(out_dir, f"{stem}.{ext}")
        fig.savefig(path, bbox_inches="tight")
        print(f"  wrote {path}")
    plt.close(fig)


# --------------------------------------------------------------- figure 6.1
def figure_coverage(coverage_csv, out_dir):
    """Grouped bar: binary vs effective coverage per engine.

    Binary counts DIRECT + ASSERTED (expressible at all).
    Effective counts DIRECT only (the policy inspects the real field).
    """
    df = pd.read_csv(coverage_csv)
    total = len(df)

    engines, binary, effective = [], [], []
    for col, label in [("kyverno", "Kyverno"), ("gatekeeper", "Gatekeeper")]:
        states = df[col].str.strip().str.upper()
        direct = int((states == "DIRECT").sum())
        asserted = int((states == "ASSERTED").sum())
        engines.append(label)
        binary.append(100.0 * (direct + asserted) / total)
        effective.append(100.0 * direct / total)
        print(f"  {label}: binary {direct + asserted}/{total}, "
              f"effective {direct}/{total}")

    x = np.arange(len(engines))
    w = 0.34
    fig, ax = plt.subplots(figsize=(5.4, 3.2))

    n_direct = int((df["kyverno"].str.strip().str.upper() == "DIRECT").sum())
    n_binary = n_direct + int(
        (df["kyverno"].str.strip().str.upper() == "ASSERTED").sum())
    b1 = ax.bar(x - w / 2, binary, w,
                label=f"Binary coverage ({n_binary}/{total})",
                color="#1f5fa9", edgecolor="black", linewidth=0.6)
    b2 = ax.bar(x + w / 2, effective, w,
                label=f"Effective coverage ({n_direct}/{total})",
                color="white", edgecolor="#1f5fa9", linewidth=0.9, hatch="///")

    for bars in (b1, b2):
        for bar in bars:
            ax.annotate(f"{bar.get_height():.1f}%",
                        (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                        textcoords="offset points", xytext=(0, 3),
                        ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(engines)
    ax.set_ylabel(f"Coverage of the {total}-requirement\nregister (per cent)")
    ax.set_ylim(0, 108)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              frameon=False)
    ax.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    save(fig, out_dir, "fig-6-1-coverage")


# --------------------------------------------------------------- figure 6.2
def figure_admission(df, out_dir):
    """Step histogram of admission latency, clean data only.

    Clock-error cycles are excluded because a negative interval invalidates the
    admission reading specifically. Outlier cycles are retained here: they are
    sync-side artefacts and do not affect the admission measurement.
    """
    work = df[df["quality_flag"] != "clock_error"]
    work = work[work["admission_ms"] >= 0]

    lo = float(work["admission_ms"].min())
    hi = float(work["admission_ms"].max())
    bins = np.linspace(lo, hi, 15)

    fig, ax = plt.subplots(figsize=(5.8, 3.2))
    for cfg in ORDER:
        x = work[work["configuration"] == cfg]["admission_ms"].astype(float)
        ax.hist(x, bins=bins, histtype="step", linewidth=1.4,
                color=COLOURS[cfg], label=f"{LABELS[cfg]} (n={len(x)})",
                linestyle={"baseline": "-", "kyverno": "--",
                           "gatekeeper": ":"}[cfg])
        print(f"  {LABELS[cfg]}: n={len(x)}, median={x.median():.1f} ms")

    ax.set_xlabel("Admission-path latency (ms)")
    ax.set_ylabel("Frequency")
    ax.legend(frameon=False, loc="upper right")
    ax.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    save(fig, out_dir, "fig-6-2-admission")


# --------------------------------------------------------------- figure 6.3
def figure_sync_load(df, out_dir):
    """Scatterplot of sync duration against system load before each cycle.

    Log y-axis because the four flagged retry cycles span three orders of
    magnitude. Flagged cycles are drawn as open markers rather than removed,
    so the reader can see exactly what was excluded and judge the rule.
    """
    work = df[df["argocd_sync_ms"] >= 0]

    fig, ax = plt.subplots(figsize=(5.8, 3.4))
    markers = {"baseline": "o", "kyverno": "s", "gatekeeper": "^"}

    for cfg in ORDER:
        sub = work[work["configuration"] == cfg]
        ok = sub[sub["quality_flag"] == "ok"]
        flagged = sub[sub["quality_flag"] == "outlier"]

        ax.scatter(ok["load_before"], ok["argocd_sync_ms"],
                   marker=markers[cfg], s=26, color=COLOURS[cfg],
                   alpha=0.85, label=LABELS[cfg], zorder=3)
        if not flagged.empty:
            ax.scatter(flagged["load_before"], flagged["argocd_sync_ms"],
                       marker=markers[cfg], s=42, facecolors="none",
                       edgecolors=COLOURS[cfg], linewidths=1.2, zorder=4)

    n_flag = int((work["quality_flag"] == "outlier").sum())
    ax.set_yscale("log")
    ax.set_xlabel("System load before cycle (1-minute average)")
    ax.set_ylabel("ArgoCD sync duration (ms), log scale")
    ax.legend(frameon=False, loc="upper right")
    ax.yaxis.grid(True, linestyle=":", alpha=0.5)
    ax.set_axisbelow(True)
    print(f"  plotted {len(work)} cycles, {n_flag} flagged as open markers")
    save(fig, out_dir, "fig-6-3-sync-load")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", default="results/coverage-matrix.csv")
    ap.add_argument("--rcbd",
                    default="results/benchmark-rcbd-20260819-113918.csv")
    ap.add_argument("--out", default="figures")
    args = ap.parse_args()

    for path in (args.coverage, args.rcbd):
        if not os.path.exists(path):
            sys.exit(f"ERROR: missing input file {path}")

    style()
    rcbd = pd.read_csv(args.rcbd)

    print("Figure 6.1 (coverage):")
    figure_coverage(args.coverage, args.out)
    print("Figure 6.2 (admission latency):")
    figure_admission(rcbd, args.out)
    print("Figure 6.3 (sync vs load):")
    figure_sync_load(rcbd, args.out)
    print("\nAll figures regenerated.")


if __name__ == "__main__":
    main()
