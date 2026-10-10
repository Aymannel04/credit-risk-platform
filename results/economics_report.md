# Money report (scorecard; line chosen on validation; assumptions in config/economics.yaml)

Base case: margin 2.0%, loss per flagged loan 10% (ASSUMPTIONS).
Line chosen on validation: approve if PD <= 0.1471 (approval rate 97.50%); textbook line if the PD were honest: 0.1667.

## Base case: what the line does

| Group | Approval rate | Default rate approved vs all | Defaults refused | Good loans refused | Profit with line (% of exposure) | Approve all | Loss in the data (% of exposure) |
|---|---|---|---|---|---|---|---|
| validation | 97.50% | 1.48% vs 2.04% | 29.4% | 1.9% | 1.77% | 1.75% | 0.65% |
| test_in_time | 97.65% | 1.53% vs 1.93% | 22.7% | 1.9% | 1.77% | 1.76% | 0.65% |
| test_oot_2019 | 99.11% | 1.21% vs 1.26% | 5.2% | 0.8% | 1.84% | 1.84% | 0.01% |
| test_oot_2022 | 99.07% | 1.35% vs 1.39% | 3.5% | 0.9% | 1.83% | 1.84% | 0.01% |

## Gain of the line over 'approve everyone', by loss scenario (% of exposure; margin at base)

| Group | loss 1% | loss 5% | loss 10% | loss 20% |
|---|---|---|---|---|
| validation | -0.027% | -0.005% | 0.024% | 0.081% |
| test_in_time | -0.029% | -0.013% | 0.006% | 0.046% |
| test_oot_2019 | -0.013% | -0.010% | -0.008% | -0.002% |
| test_oot_2022 | -0.015% | -0.013% | -0.010% | -0.005% |

## Sensitivity on validation: best line by margin and loss

| margin | loss | textbook line | best realised line | approval rate | gain vs approve all (% of exposure) |
|---|---|---|---|---|---|
| 0.5% | 1% | 0.333 | 0.3199 | 99.50% | 0.001% |
| 0.5% | 5% | 0.091 | 0.0683 | 93.00% | 0.027% |
| 0.5% | 10% | 0.048 | 0.0421 | 88.50% | 0.093% |
| 0.5% | 20% | 0.024 | 0.0145 | 72.01% | 0.251% |
| 1.0% | 1% | 0.500 | 0.7081 | 100.00% | 0.000% |
| 1.0% | 5% | 0.167 | 0.1471 | 97.50% | 0.012% |
| 1.0% | 10% | 0.091 | 0.0683 | 93.00% | 0.053% |
| 1.0% | 20% | 0.048 | 0.0421 | 88.50% | 0.185% |
| 2.0% | 1% | 0.667 | 0.7081 | 100.00% | 0.000% |
| 2.0% | 5% | 0.286 | 0.3199 | 99.50% | 0.005% |
| 2.0% | 10% | 0.167 | 0.1471 | 97.50% | 0.024% |
| 2.0% | 20% | 0.091 | 0.0683 | 93.00% | 0.107% |
| 3.0% | 1% | 0.750 | 0.7081 | 100.00% | 0.000% |
| 3.0% | 5% | 0.375 | 0.3199 | 99.50% | 0.002% |
| 3.0% | 10% | 0.231 | 0.3199 | 99.50% | 0.013% |
| 3.0% | 20% | 0.130 | 0.1300 | 97.00% | 0.067% |

## Expected loss by risk band (base loss), validation

| band | mean PD | default rate | predicted EL | EL at the observed defaults | ratio |
|---|---|---|---|---|---|
| 1 | 0.05% | 0.00% | 19,920 | 0 | n/a |
| 2 | 0.11% | 0.10% | 51,667 | 65,800 | 0.79 |
| 3 | 0.20% | 0.10% | 86,747 | 30,500 | 2.84 |
| 4 | 0.31% | 0.16% | 134,997 | 73,600 | 1.83 |
| 5 | 0.46% | 0.26% | 204,827 | 97,100 | 2.11 |
| 6 | 0.70% | 0.42% | 308,568 | 303,100 | 1.02 |
| 7 | 1.07% | 0.94% | 448,760 | 430,400 | 1.04 |
| 8 | 1.74% | 2.09% | 711,374 | 954,800 | 0.75 |
| 9 | 3.31% | 3.61% | 1,320,317 | 1,591,700 | 0.83 |
| 10 | 12.42% | 12.75% | 4,774,342 | 5,423,300 | 0.88 |