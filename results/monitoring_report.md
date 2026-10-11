# Monitoring report (model `b3069001d62e`)

Pre-registration commit: `4098ffe3428cf0fcac0dfdeb0fde63490fb9b3df` (committed before this run). Part B is SIMULATED. Part A on the five development vintages is in-sample (the model was fitted on them).

## Part A: real drift and level per vintage

| Vintage | Sample | Loans | Defaults | Predicted | Observed | Obs / pred | Level flag | Gini | Score PSI | Max CSI (input) |
|---|---|---|---|---|---|---|---|---|---|---|
| 2008 | in | 49,713 | 2,219 | 2.48% | 4.46% | 1.80 | alert | 0.659 | 0.049 (ok) | 0.170 (dti) |
| 2010 | out | 35,304 | 151 | 0.87% | 0.43% | 0.49 | alert | 0.628 | 0.264 (alert) | 0.282 (ltv) |
| 2012 | in | 32,546 | 73 | 0.65% | 0.22% | 0.35 | alert | 0.642 | 0.454 (alert) | 0.311 (purpose) |
| 2014 | out | 42,566 | 206 | 1.28% | 0.48% | 0.38 | alert | 0.599 | 0.042 (ok) | 0.105 (rate_spread) |
| 2016 | in | 47,372 | 288 | 1.42% | 0.61% | 0.43 | alert | 0.643 | 0.014 (ok) | 0.066 (dti) |
| 2018 | out | 49,377 | 420 | 1.80% | 0.85% | 0.47 | alert | 0.543 | 0.038 (ok) | 0.193 (purpose) |
| 2019 | in | 49,881 | 630 | 1.63% | 1.26% | 0.77 | warn | 0.472 | 0.023 (ok) | 0.047 (dti) |
| 2022 | in | 49,907 | 692 | 1.95% | 1.39% | 0.71 | warn | 0.565 | 0.096 (ok) | 0.250 (purpose) |
| 2023 | out | 49,834 | 662 | 1.88% | 1.33% | 0.71 | warn | 0.595 | 0.091 (ok) | 0.714 (purpose) |

## Part B: simulated shifts (fire drills)

Batch 10,000 loans against a reference of 219,419. R-M1 (control clean): **True**. R-M2 (at least 6 of 7 expected alerts): **True** (caught ['S1', 'S3', 'S4', 'S5', 'S6', 'S7', 'S9'], missed []).

| Drill | Shift | Score PSI | Max CSI (input) | Level ratio | Alert monitors |
|---|---|---|---|---|---|
| C0 | none (control) | 0.003 | 0.001 (credit_score) | 0.93 | none |
| S1 | {'kind': 'shift', 'feature': 'credit_score', 'delta': -30} | 0.117 | 0.346 (credit_score) | 0.61 | csi:credit_score, level_ratio |
| S2 | {'kind': 'shift', 'feature': 'credit_score', 'delta': -10} | 0.014 | 0.033 (credit_score) | 0.80 | none |
| S3 | {'kind': 'shift', 'feature': 'dti', 'delta': 10} | 0.122 | 1.005 (dti) | 0.58 | csi:dti, level_ratio |
| S4 | {'kind': 'missing', 'feature': 'credit_score', 'share': 0.1} | 0.026 | 0.613 (credit_score) | 0.75 | csi:credit_score |
| S5 | {'kind': 'new_category', 'feature': 'purpose', 'value': 'X', 'share': 0.2} | 0.002 | 1.560 (purpose) | 0.93 | csi:purpose |
| S6 | {'kind': 'shift_many', 'features': ['ltv', 'cltv'], 'delta': 10} | 0.032 | 0.604 (ltv) | 0.74 | csi:ltv, csi:cltv |
| S7 | {'kind': 'shift', 'feature': 'rate_spread', 'delta': 0.5} | 0.032 | 1.504 (rate_spread) | 0.77 | csi:rate_spread |
| S8 | {'kind': 'default_rate', 'factor': 1.25} | 0.003 | 0.001 (credit_score) | 1.16 | none |
| S9 | {'kind': 'default_rate', 'factor': 2.0} | 0.003 | 0.001 (credit_score) | 1.86 | level_ratio |

## Part C: can history alone repair the level?

Level error = |ln(predicted / observed)|; lower is better. delta = constant added on the log-odds scale.

| Target | Known vintages | Observed | Error A static | Error B last | Error C pooled | delta B | delta C |
|---|---|---|---|---|---|---|---|
| 2012 | [2008] | 0.22% | 1.061 | 1.711 | 1.711 | +0.67 | +0.67 |
| 2014 | [2008, 2010] | 0.48% | 0.969 | 0.262 | 1.428 | -0.73 | +0.48 |
| 2016 | [2008, 2010, 2012] | 0.61% | 0.851 | 0.196 | 1.199 | -1.08 | +0.37 |
| 2018 | [2008, 2010, 2012, 2014] | 0.85% | 0.747 | 0.213 | 0.895 | -1.00 | +0.16 |
| 2019 | [2008, 2010, 2012, 2014, 2016] | 1.26% | 0.257 | 0.591 | 0.248 | -0.88 | -0.01 |
| 2022 | [2008, 2010, 2012, 2014, 2016, 2018, 2019] | 1.39% | 0.342 | 0.085 | 0.184 | -0.27 | -0.17 |
| 2023 | [2008, 2010, 2012, 2014, 2016, 2018, 2019] | 1.33% | 0.345 | 0.087 | 0.186 | -0.27 | -0.17 |

Mean error: static 0.653, B 0.449, C 0.836.
R-C2 (Gini unchanged): **True**.

- **B_last**: mean improvement +31.2% (need 20%: True), improved 5 of 7 targets (need 5: True; [2014, 2016, 2018, 2022, 2023]), worst worsening +0.650 (limit 0.30: False) -> **not recommended**.
- **C_pooled**: mean improvement -28.0% (need 20%: False), improved 3 of 7 targets (need 5: False; [2019, 2022, 2023]), worst worsening +0.650 (limit 0.30: False) -> **not recommended**.

## Pre-registered predictions: hit or miss

| Id | Prediction | Result |
|---|---|---|
| A1 | 2014 and 2018 raise a level ALERT (ratio below 0.67) | HIT |
| A2 | largest score PSI is in 2008, 2010 or 2023 (found: 2012) | MISS |
| A3 | Gini between 0.40 and 0.70 on every vintage | HIT |
| B1 | control raises no warn and no alert | HIT |
| B-S1 | S1 raises an alert | HIT |
| B-S3 | S3 raises an alert | HIT |
| B-S4 | S4 raises an alert | HIT |
| B-S5 | S5 raises an alert | HIT |
| B-S9 | S9 raises an alert | HIT |
| B-S2 | S2 (subtle) raises at most a warning | HIT |
| C1 | arm B (last vintage) is not recommended | HIT |
| C2 | arm C (pooled) improves 2018, 2019, 2022, 2023 and worsens 2012 and 2014 | MISS |
| C3 | arm C (pooled) is not recommended | HIT |

11 of 13 predictions hit.
