# Phase 4 Benchmark: Randomised Complete Block Design

Source: `benchmark-rcbd-20260819-113918.csv`


Configuration order is balanced across blocks: all 3! = 6 orderings are used, each exactly twice, so every configuration runs in every within-block position an equal number of times. Session drift and time-varying system load therefore affect all three configurations equally instead of loading onto whichever ran first.


---

# Admission-path latency (`admission_ms`)


Observations: 141


## Descriptive statistics

| configuration               |   n |   mean_ms |   sd_ms |   median_ms |   iqr_ms |   mad_ms |   min_ms |   p95_ms |   p99_ms |   max_ms |   cv_pct |
|:----------------------------|----:|----------:|--------:|------------:|---------:|---------:|---------:|---------:|---------:|---------:|---------:|
| Baseline (no policy engine) |  47 |     334.1 |    26.3 |       322   |     26   |      5   |      312 |    384   |    420.8 |      441 |      7.9 |
| Kyverno                     |  48 |     348.6 |    28   |       338   |     18.8 |      8   |      325 |    419.9 |    444.1 |      454 |      8   |
| OPA Gatekeeper              |  46 |     343.5 |    19   |       338.5 |     14.2 |      6.5 |      325 |    375.8 |    415.1 |      430 |      5.5 |


## Normality of the distribution

Shapiro-Wilk tests the null hypothesis that the sample is drawn from a normal distribution. Rejection means the normality assumption behind the t-test does not hold for this data, which is why the non-parametric Friedman and Wilcoxon tests are used below.


| configuration               |   n |   shapiro_w |     p_value | normal_at_0.05   |   skewness |   kurtosis_excess |
|:----------------------------|----:|------------:|------------:|:-----------------|-----------:|------------------:|
| Baseline (no policy engine) |  47 |      0.7334 | 6.83318e-08 | False            |      2.072 |             4.571 |
| Kyverno                     |  48 |      0.667  | 3.6274e-09  | False            |      2.371 |             5.061 |
| OPA Gatekeeper              |  46 |      0.708  | 2.96324e-08 | False            |      2.727 |             8.719 |


Normality is rejected at alpha = 0.05 for 3 of 3 configurations (largest p = < 0.001).



## Omnibus test

Friedman chi-squared = 8.6667, df = 2, blocks = 12, p = 0.0131, Kendall's W = 0.3611.


## Post-hoc paired comparisons (Holm-Bonferroni)

| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |     p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |    p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|----------:|---------------:|:------------|---------------------:|----------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |           322 |         338   |                   -12.2 |            9 | 0.0161133 |        -0.5066 | large       |               0.2467 | 0.0483398 | True                  |
| Baseline (no policy engine) vs OPA Gatekeeper |           322 |         338.5 |                   -15.5 |           24 | 0.256836  |        -0.4741 | large       |               0.263  | 0.513672  | False                 |
| Kyverno vs OPA Gatekeeper                     |           338 |         338.5 |                    -3   |           32 | 0.62207   |         0.0439 | negligible  |               0.522  | 0.62207   | False                 |


## Randomisation check

Position within block: H = 1.2839, p = 0.5263. Position effect detected: False. A null result here is the desired outcome — it means the randomisation successfully neutralised within-block ordering.



## Sensitivity: high-load cycles excluded

Observations retained: 137. If the conclusions match the full dataset, the result is robust to transient load spikes.


| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |     p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |    p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|----------:|---------------:|:------------|---------------------:|----------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |           322 |         338   |                   -12   |          9   | 0.0161133 |        -0.4944 | large       |               0.2528 | 0.0483398 | True                  |
| Baseline (no policy engine) vs OPA Gatekeeper |           322 |         338.5 |                   -15.5 |         24   | 0.256836  |        -0.459  | medium      |               0.2705 | 0.513672  | False                 |
| Kyverno vs OPA Gatekeeper                     |           338 |         338.5 |                    -3.5 |         32.5 | 0.637207  |         0.0459 | negligible  |               0.523  | 0.637207  | False                 |

---

# ArgoCD sync latency (`argocd_sync_ms`)


Observations: 144


## Descriptive statistics

| configuration               |   n |   mean_ms |   sd_ms |   median_ms |   iqr_ms |   mad_ms |   min_ms |   p95_ms |   p99_ms |   max_ms |   cv_pct |
|:----------------------------|----:|----------:|--------:|------------:|---------:|---------:|---------:|---------:|---------:|---------:|---------:|
| Baseline (no policy engine) |  48 |    1852.2 |   338.7 |      1886   |    107   |     54.5 |      607 |   2162.5 |   2474.4 |     2637 |     18.3 |
| Kyverno                     |  48 |    4248.9 | 15747.5 |      1893.5 |    145.8 |     59   |      803 |   2897.4 |  61240.8 |   111010 |    370.6 |
| OPA Gatekeeper              |  48 |    5231.3 | 22587.5 |      1982.5 |    131.8 |     67   |      681 |   2290.9 |  85182.9 |   158454 |    431.8 |


## Normality of the distribution

Shapiro-Wilk tests the null hypothesis that the sample is drawn from a normal distribution. Rejection means the normality assumption behind the t-test does not hold for this data, which is why the non-parametric Friedman and Wilcoxon tests are used below.


| configuration               |   n |   shapiro_w |     p_value | normal_at_0.05   |   skewness |   kurtosis_excess |
|:----------------------------|----:|------------:|------------:|:-----------------|-----------:|------------------:|
| Baseline (no policy engine) |  47 |      0.6396 | 1.7016e-09  | False            |     -2.291 |             9.664 |
| Kyverno                     |  47 |      0.5156 | 3.10182e-11 | False            |      3.575 |            19.21  |
| OPA Gatekeeper              |  46 |      0.7647 | 3.47103e-07 | False            |      2.431 |             8.132 |


Normality is rejected at alpha = 0.05 for 3 of 3 configurations (largest p = < 0.001).



## Omnibus test

Friedman chi-squared = 8.0, df = 2, blocks = 12, p = 0.0183, Kendall's W = 0.3333.


## Post-hoc paired comparisons (Holm-Bonferroni)

| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |     p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|----------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |        1886   |        1893.5 |                   -11.8 |         29.5 | 0.485352  |        -0.1163 | negligible  |               0.4418 | 0.485352 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |        1886   |        1982.5 |                   -96.5 |         13   | 0.0424805 |        -0.474  | medium      |               0.263  | 0.127441 | False                 |
| Kyverno vs OPA Gatekeeper                     |        1893.5 |        1982.5 |                   -91.8 |         13   | 0.0424805 |        -0.342  | medium      |               0.329  | 0.127441 | False                 |


## Randomisation check

Position within block: H = 1.101, p = 0.5767. Position effect detected: False. A null result here is the desired outcome — it means the randomisation successfully neutralised within-block ordering.



## Sensitivity: high-load cycles excluded

Observations retained: 137. If the conclusions match the full dataset, the result is robust to transient load spikes.


| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |     p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|----------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |          1889 |          1889 |                   -11.8 |         29.5 | 0.480469  |        -0.0629 | negligible  |               0.4685 | 0.480469 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |          1889 |          1990 |                  -103.5 |         13   | 0.0424805 |        -0.5005 | large       |               0.2498 | 0.127441 | False                 |
| Kyverno vs OPA Gatekeeper                     |          1889 |          1990 |                   -98.8 |         13   | 0.0424805 |        -0.4192 | medium      |               0.2904 | 0.127441 | False                 |