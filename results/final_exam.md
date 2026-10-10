# Final exam (test splits, models trained on `train` only, raw probabilities)

Frozen at commit `1add760b87`. 95% intervals: paired bootstrap, 1000 resamples.

## test_in_time: 19,431 loans, 375 defaults (1.93%)

| Model | Gini (95% CI) | KS | Brier | mean predicted PD | predicted / observed (95% CI) |
|---|---|---|---|---|---|
| scorecard | 0.735 (0.703 to 0.769) | 0.584 | 0.01754 | 1.97% | 1.02 (0.93 to 1.13) |
| logistic_regression | 0.749 (0.716 to 0.781) | 0.597 | 0.01727 | 1.96% | 1.02 (0.92 to 1.13) |
| xgboost | 0.747 (0.715 to 0.780) | 0.595 | 0.01731 | 1.96% | 1.02 (0.92 to 1.12) |

Gini differences (95% CI; significant = interval excludes 0):

- scorecard minus logistic_regression: -0.014 (-0.028 to +0.001) not significant
- scorecard minus xgboost: -0.013 (-0.028 to +0.001) not significant
- logistic_regression minus xgboost: +0.001 (-0.010 to +0.013) not significant

## test_oot_2019: 49,881 loans, 630 defaults (1.26%)

| Model | Gini (95% CI) | KS | Brier | mean predicted PD | predicted / observed (95% CI) |
|---|---|---|---|---|---|
| scorecard | 0.446 (0.405 to 0.485) | 0.338 | 0.01264 | 1.75% | 1.38 (1.28 to 1.50) |
| logistic_regression | 0.456 (0.418 to 0.493) | 0.337 | 0.01281 | 1.82% | 1.44 (1.34 to 1.57) |
| xgboost | 0.463 (0.423 to 0.497) | 0.354 | 0.01268 | 1.62% | 1.28 (1.18 to 1.39) |

Gini differences (95% CI; significant = interval excludes 0):

- scorecard minus logistic_regression: -0.010 (-0.027 to +0.007) not significant
- scorecard minus xgboost: -0.016 (-0.034 to +0.002) not significant
- logistic_regression minus xgboost: -0.006 (-0.022 to +0.009) not significant

## test_oot_2022: 49,907 loans, 692 defaults (1.39%)

| Model | Gini (95% CI) | KS | Brier | mean predicted PD | predicted / observed (95% CI) |
|---|---|---|---|---|---|
| scorecard | 0.523 (0.487 to 0.557) | 0.409 | 0.01383 | 2.08% | 1.50 (1.40 to 1.62) |
| logistic_regression | 0.529 (0.495 to 0.562) | 0.416 | 0.01390 | 2.07% | 1.49 (1.39 to 1.61) |
| xgboost | 0.528 (0.494 to 0.562) | 0.413 | 0.01385 | 2.00% | 1.44 (1.34 to 1.56) |

Gini differences (95% CI; significant = interval excludes 0):

- scorecard minus logistic_regression: -0.006 (-0.021 to +0.010) not significant
- scorecard minus xgboost: -0.006 (-0.021 to +0.010) not significant
- logistic_regression minus xgboost: +0.000 (-0.015 to +0.016) not significant
