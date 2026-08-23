# Robustness checks

## 1. Block integrity

A randomised complete block design assumes conditions are homogeneous within a block. That is testable after the fact by measuring how long each block took: if the three configurations did not run close together, the block did not hold conditions constant.

Median block span: 120 s.

| Block | Span (s) | vs median | Load spread | Homogeneous |
|---|---|---|---|---|
| 1 | 131 | 1.1x | 0.43 | yes |
| 2 | 132 | 1.1x | 1.60 | yes |
| 3 | 84 | 0.7x | 0.75 | yes |
| 4 | 82 | 0.7x | 0.51 | yes |
| 5 | 113 | 0.9x | 1.09 | yes |
| 6 | 273 | 2.3x | 2.32 | yes |
| 7 | 115 | 1.0x | 1.55 | yes |
| 8 | 124 | 1.0x | 1.15 | yes |
| 9 | 70 | 0.6x | 1.00 | yes |
| 10 | 82 | 0.7x | 0.32 | yes |
| 11 | 222 | 1.9x | 1.53 | yes |
| 12 | 3814 | 31.9x | 5.28 | NO |

Block(s) 12 violate the assumption. The exclusion criterion is elapsed time, measured independently of the outcome variable, so this is a data-quality judgement rather than an outcome-driven one.

## 2. Sensitivity of the conclusions

The all-blocks analysis is the primary, pre-declared result. The reduced analysis is reported alongside it so a reader can see which conclusions depend on the contaminated block.

### Admission-path latency

| Comparison | All blocks | Reduced | Robust? |
|---|---|---|---|
| Baseline vs Kyverno | significant (p=0.0483) | not significant (p=0.0967) | NO |
| Baseline vs OPA Gatekeeper | not significant (p=0.5137) | not significant (p=0.1289) | YES |
| Kyverno vs OPA Gatekeeper | not significant (p=0.6221) | not significant (p=0.2783) | YES |

### ArgoCD sync duration

| Comparison | All blocks | Reduced | Robust? |
|---|---|---|---|
| Baseline vs Kyverno | not significant (p=0.4805) | not significant (p=0.7793) | YES |
| Baseline vs OPA Gatekeeper | not significant (p=0.1274) | significant (p=0.0059) | NO |
| Kyverno vs OPA Gatekeeper | not significant (p=0.1274) | significant (p=0.0059) | NO |

## 3. Interval estimates for the perfect detection scores

Precision, recall and F1 of 1.000 are point estimates from a finite suite. Clopper-Pearson exact intervals show what the data support.

| Measure | Successes / trials | Point | 95% CI |
|---|---|---|---|
| Specificity | 21/21 | 1.000 | [0.839, 1.000] |
| Recall | 20/20 | 1.000 | [0.832, 1.000] |
| Overall accuracy | 41/41 | 1.000 | [0.914, 1.000] |

The upper bound is 1.000 in every case, but the lower bound is well below it. A perfect score on this suite is consistent with a true accuracy materially lower than 1.000. The score certifies the suite, not the engine.
