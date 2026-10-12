# Exploratory: the model refitted WITHOUT the 2008 vintage

Exploratory, not pre-registered, no decision depends on it. The committed model is untouched. Sanity check (refit on all development rows reproduces model `b3069001d62e`): **True**. Vintages 2008, 2012, 2016, 2019, 2022 are in-sample for the committed model; for the refit, 2008 is out-of-sample.

Training default rate: 1.70% with 2008, 0.94% without. Spearman correlation between the two scores on all loans: 0.924.

| Vintage | Observed | Predicted (committed) | Ratio (committed) | Predicted (no 2008) | Ratio (no 2008) | Gini (committed) | Gini (no 2008) | Default-count miss (committed) | (no 2008) |
|---|---|---|---|---|---|---|---|---|---|
| 2008 | 4.46% | 2.48% | 1.80 | 1.11% | 4.03 | 0.659 | 0.615 | 988 | 1,668 |
| 2010 | 0.43% | 0.87% | 0.49 | 0.51% | 0.84 | 0.628 | 0.617 | 155 | 29 |
| 2012 | 0.22% | 0.65% | 0.35 | 0.44% | 0.51 | 0.642 | 0.655 | 138 | 70 |
| 2014 | 0.48% | 1.28% | 0.38 | 0.83% | 0.59 | 0.599 | 0.627 | 337 | 146 |
| 2016 | 0.61% | 1.42% | 0.43 | 0.90% | 0.68 | 0.643 | 0.666 | 386 | 136 |
| 2018 | 0.85% | 1.80% | 0.47 | 1.09% | 0.78 | 0.543 | 0.549 | 466 | 118 |
| 2019 | 1.26% | 1.63% | 0.77 | 1.00% | 1.26 | 0.472 | 0.476 | 185 | 131 |
| 2022 | 1.39% | 1.95% | 0.71 | 1.22% | 1.14 | 0.565 | 0.578 | 283 | 85 |
| 2023 | 1.33% | 1.88% | 0.71 | 1.12% | 1.19 | 0.595 | 0.599 | 272 | 105 |

Plain average of the nine level errors: committed 0.652, without 2008 0.439. Total default-count miss over the nine vintages: committed 3,210, without 2008 2,490.

## Predictions written before running

| Id | Prediction | Result |
|---|---|---|
| E1 | 2010-2018 ratios move closer to 1 | HIT |
| E2 | 2019, 2022, 2023 cross above 1 | HIT |
| E3 | 2008 ratio rises to at least 2.5 | HIT |
| E4 | |Gini difference| < 0.02 everywhere and Spearman > 0.95 | MISS |
| E5 | average level error falls while the 2008 default-count miss rises | HIT |

4 of 5 predictions hit.
