# Phase 4 Benchmark: Randomised Complete Block Design

Source: `benchmark-rcbd-20260819-102800.csv`


Configuration order was randomised independently within each block, so session drift and time-varying system load affect all three configurations equally instead of loading onto whichever ran first.


---

# Admission-path latency (`admission_ms`)


Observations: 144


## Descriptive statistics

| configuration               |   n |   mean_ms |   sd_ms |   median_ms |   iqr_ms |   mad_ms |   min_ms |   p95_ms |   p99_ms |   max_ms |   cv_pct |
|:----------------------------|----:|----------:|--------:|------------:|---------:|---------:|---------:|---------:|---------:|---------:|---------:|
| Baseline (no policy engine) |  48 |    1866.8 |   386.4 |      1931   |    162.5 |     81.5 |      753 |   2284.8 |   2666.2 |     2967 |     20.7 |
| Kyverno                     |  48 |    1893.6 |   270.8 |      1906.5 |    167.5 |     88   |      880 |   2122.8 |   2385.1 |     2583 |     14.3 |
| OPA Gatekeeper              |  48 |    1974   |   273.3 |      2012.5 |    145   |     67   |     1038 |   2248.6 |   2349.7 |     2400 |     13.8 |


## Omnibus test

Friedman chi-squared = 7.0, df = 2, blocks = 6, p = 0.0302, Kendall's W = 0.5833.


## Post-hoc paired comparisons (Holm-Bonferroni)

| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |   p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|--------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |        1931   |        1906.5 |                    43   |            4 | 0.21875 |         0.0004 | negligible  |               0.5002 |  0.21875 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |        1931   |        2012.5 |                   -86.5 |            1 | 0.0625  |        -0.3854 | medium      |               0.3073 |  0.125   | False                 |
| Kyverno vs OPA Gatekeeper                     |        1906.5 |        2012.5 |                  -110.5 |            0 | 0.03125 |        -0.388  | medium      |               0.306  |  0.09375 | False                 |


## Randomisation check

Position within block: H = 8.8618, p = 0.0119. Position effect detected: True. A null result here is the desired outcome — it means the randomisation successfully neutralised within-block ordering.



## Sensitivity: high-load cycles excluded

Observations retained: 144. If the conclusions match the full dataset, the result is robust to transient load spikes.


| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |   p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|--------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |        1931   |        1906.5 |                    43   |            4 | 0.21875 |         0.0004 | negligible  |               0.5002 |  0.21875 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |        1931   |        2012.5 |                   -86.5 |            1 | 0.0625  |        -0.3854 | medium      |               0.3073 |  0.125   | False                 |
| Kyverno vs OPA Gatekeeper                     |        1906.5 |        2012.5 |                  -110.5 |            0 | 0.03125 |        -0.388  | medium      |               0.306  |  0.09375 | False                 |

---

# ArgoCD sync latency (`argocd_sync_ms`)


Observations: 144


## Descriptive statistics

| configuration               |   n |   mean_ms |   sd_ms |   median_ms |   iqr_ms |   mad_ms |   min_ms |   p95_ms |   p99_ms |   max_ms |   cv_pct |
|:----------------------------|----:|----------:|--------:|------------:|---------:|---------:|---------:|---------:|---------:|---------:|---------:|
| Baseline (no policy engine) |  48 |    1866.8 |   386.4 |      1931   |    162.5 |     81.5 |      753 |   2284.8 |   2666.2 |     2967 |     20.7 |
| Kyverno                     |  48 |    1893.6 |   270.8 |      1906.5 |    167.5 |     88   |      880 |   2122.8 |   2385.1 |     2583 |     14.3 |
| OPA Gatekeeper              |  48 |    1974   |   273.3 |      2012.5 |    145   |     67   |     1038 |   2248.6 |   2349.7 |     2400 |     13.8 |


## Omnibus test

Friedman chi-squared = 7.0, df = 2, blocks = 6, p = 0.0302, Kendall's W = 0.5833.


## Post-hoc paired comparisons (Holm-Bonferroni)

| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |   p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|--------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |        1931   |        1906.5 |                    43   |            4 | 0.21875 |         0.0004 | negligible  |               0.5002 |  0.21875 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |        1931   |        2012.5 |                   -86.5 |            1 | 0.0625  |        -0.3854 | medium      |               0.3073 |  0.125   | False                 |
| Kyverno vs OPA Gatekeeper                     |        1906.5 |        2012.5 |                  -110.5 |            0 | 0.03125 |        -0.388  | medium      |               0.306  |  0.09375 | False                 |


## Randomisation check

Position within block: H = 8.8618, p = 0.0119. Position effect detected: True. A null result here is the desired outcome — it means the randomisation successfully neutralised within-block ordering.



## Sensitivity: high-load cycles excluded

Observations retained: 144. If the conclusions match the full dataset, the result is robust to transient load spikes.


| comparison                                    |   median_a_ms |   median_b_ms |   paired_median_diff_ms |   wilcoxon_w |   p_raw |   cliffs_delta | magnitude   |   vargha_delaney_a12 |   p_holm | significant_at_0.05   |
|:----------------------------------------------|--------------:|--------------:|------------------------:|-------------:|--------:|---------------:|:------------|---------------------:|---------:|:----------------------|
| Baseline (no policy engine) vs Kyverno        |        1931   |        1906.5 |                    43   |            4 | 0.21875 |         0.0004 | negligible  |               0.5002 |  0.21875 | False                 |
| Baseline (no policy engine) vs OPA Gatekeeper |        1931   |        2012.5 |                   -86.5 |            1 | 0.0625  |        -0.3854 | medium      |               0.3073 |  0.125   | False                 |
| Kyverno vs OPA Gatekeeper                     |        1906.5 |        2012.5 |                  -110.5 |            0 | 0.03125 |        -0.388  | medium      |               0.306  |  0.09375 | False                 |