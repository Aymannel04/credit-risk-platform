# Model v2 exam (fresh vintages, run once after the freeze)

Frozen at commit `ee7f19162c`. 95% paired-bootstrap intervals, 1000 resamples.

| Vintage | loans / defaults | arm | Gini (95% CI) | KS | Brier | predicted vs real | ratio (95% CI) |
|---|---|---|---|---|---|---|---|
| 2010 | 35,304 / 151 | v1 | 0.598 (0.530-0.668) | 0.455 | 0.00435 | 0.87% vs 0.43% | 2.04 (1.74-2.41) |
| 2010 | 35,304 / 151 | v1b | 0.616 (0.547-0.686) | 0.487 | 0.00427 | 0.77% vs 0.43% | 1.80 (1.54-2.12) |
| 2010 | 35,304 / 151 | v2 | 0.628 (0.563-0.698) | 0.497 | 0.00432 | 0.87% vs 0.43% | 2.03 (1.73-2.40) |
| 2014 | 42,566 / 206 | v1 | 0.580 (0.516-0.637) | 0.447 | 0.00512 | 1.32% vs 0.48% | 2.73 (2.40-3.17) |
| 2014 | 42,566 / 206 | v1b | 0.586 (0.520-0.647) | 0.442 | 0.00496 | 1.18% vs 0.48% | 2.44 (2.15-2.83) |
| 2014 | 42,566 / 206 | v2 | 0.599 (0.535-0.656) | 0.479 | 0.00500 | 1.28% vs 0.48% | 2.64 (2.32-3.06) |
| 2018 | 49,377 / 420 | v1 | 0.523 (0.474-0.566) | 0.425 | 0.00893 | 1.89% vs 0.85% | 2.22 (2.02-2.45) |
| 2018 | 49,377 / 420 | v1b | 0.543 (0.497-0.585) | 0.443 | 0.00861 | 1.62% vs 0.85% | 1.91 (1.74-2.10) |
| 2018 | 49,377 / 420 | v2 | 0.543 (0.498-0.585) | 0.429 | 0.00871 | 1.80% vs 0.85% | 2.11 (1.92-2.33) |
| 2023 | 49,834 / 662 | v1 | 0.570 (0.537-0.602) | 0.451 | 0.01325 | 2.13% vs 1.33% | 1.60 (1.48-1.73) |
| 2023 | 49,834 / 662 | v1b | 0.585 (0.552-0.617) | 0.451 | 0.01297 | 1.76% vs 1.33% | 1.33 (1.23-1.44) |
| 2023 | 49,834 / 662 | v2 | 0.595 (0.565-0.625) | 0.465 | 0.01299 | 1.88% vs 1.33% | 1.41 (1.30-1.53) |

## Gini differences per vintage (95% CI)

- 2010: v2 minus v1 +0.030 (+0.003 to +0.057); v2 minus v1b +0.013 (-0.007 to +0.032); v1b minus v1 +0.018 (-0.002 to +0.039)
- 2014: v2 minus v1 +0.019 (-0.004 to +0.040); v2 minus v1b +0.013 (-0.004 to +0.031); v1b minus v1 +0.006 (-0.011 to +0.023)
- 2018: v2 minus v1 +0.021 (-0.000 to +0.042); v2 minus v1b +0.000 (-0.012 to +0.013); v1b minus v1 +0.020 (+0.005 to +0.035)
- 2023: v2 minus v1 +0.025 (+0.008 to +0.042); v2 minus v1b +0.011 (-0.002 to +0.022); v1b minus v1 +0.014 (+0.004 to +0.025)

## Pre-registered criteria

- mean gini difference v2 minus v1: {'difference': 0.023605651657108206, 'ci95': [0.012898994020069126, 0.03505642322481799], 'non_inferior_margin_0.03': True, 'superior': True}
- mean gini difference v2 minus v1b: {'difference': 0.00915952941978826, 'ci95': [0.0015075474140426718, 0.01663435084470567], 'non_inferior_margin_0.03': True, 'superior': True}
- mean gini difference v1b minus v1: {'difference': 0.014446122237319947, 'ci95': [0.006066991201635066, 0.02249803545114092], 'non_inferior_margin_0.03': True, 'superior': True}
- slice variables where v2 has the smaller spread than v1: {'count': 4, 'variables': ['occupancy', 'purpose', 'channel', 'state'], 'needed': 4}

## Group calibration spread

- v1: first_time_homebuyer 1.02, occupancy 1.85, purpose 1.33, property_type 3.04, channel 1.72, state 2.20
- v1b: first_time_homebuyer 1.05, occupancy 1.66, purpose 1.35, property_type 3.17, channel 1.50, state 2.07
- v2: first_time_homebuyer 1.15, occupancy 1.60, purpose 1.11, property_type 3.20, channel 1.13, state 2.17