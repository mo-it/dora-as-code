# Results

Which file is the evidence for which claim.

## Use these

| File | What it supports |
|---|---|
| `benchmark-rcbd-20260819-113918.csv` | The performance dataset. 144 cycles, 48 per configuration, 12 blocks by 4 replicates. |
| `analysis-rcbd/rcbd-analysis-report.md` | Full statistical write-up: normality, Friedman, Wilcoxon with Holm, effect sizes, randomisation check. |
| `analysis-rcbd/rcbd-normality.csv` | Shapiro-Wilk per configuration. This is the evidence that the t-test normality assumption fails. |
| `analysis-rcbd/rcbd-*-descriptives.csv` | Per-configuration summary statistics. |
| `analysis-rcbd/rcbd-*-pairwise.csv` | Pairwise comparisons with corrected p-values and effect sizes. |
| `analysis-rcbd/rcbd-*-block-medians.csv` | One median per block per configuration, the input to Friedman. |
| `coverage-matrix.csv` and `.md` | Expressiveness. Three states per engine: DIRECT, ASSERTED, ABSENT. |
| `sweep-kyverno.txt` | Kyverno detection accuracy, measured in isolation. |
| `sweep-kyverno-fp.txt` | Kyverno false-positive count against compliant manifests. |
| `sweep-gatekeeper.txt` | Gatekeeper detection accuracy, Kyverno held on Audit. |
| `rcbd-run.log` | Execution log for the benchmark run. |

## Do not use these

The July 2026 benchmark files (`benchmark-baseline-*`, `benchmark-kyverno-*`,
`benchmark-gatekeeper-*`) are retained for the forensic record only. They are
invalid for two independent reasons:

1. The run used a sequential design, so run order is confounded with
   configuration.
2. Gatekeeper's validating webhook had been destroyed on 26 July at 13:13:48,
   one second after the first benchmark file was created. Every Gatekeeper
   measurement after that point was taken against an engine disconnected from
   the admission path while reporting healthy.

See `evidence/forensics/` for the webhook backups and the destructive script
that caused it, and `evidence/forensics/invalid-results/` for the superseded
detection sweep.
