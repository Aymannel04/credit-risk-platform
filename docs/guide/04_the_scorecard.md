# 4. The scorecard and the other two models

We built three models and compared them. The **scorecard** is the one we recommend, so it gets most of this file.

## 4.1 The scorecard idea: a points system

Like a driving test or a video game, you collect points for each good answer. The total is the **score**: higher = safer.
Here is a real piece of our scorecard (the credit-score part):

| Credit score band | Loans | Defaults | Default rate | WoE | **Points** |
|---|---|---|---|---|---|
| 662 or less | 3,950 | 454 | 11.5% | -1.85 | **13** |
| 663 to 685 | 4,258 | 280 | 6.6% | -1.23 | **27** |
| 686 to 715 | 9,613 | 321 | 3.3% | -0.52 | **43** |
| 716 to 742 | 11,185 | 209 | 1.9% | +0.07 | **56** |
| 743 to 766 | 12,908 | 151 | 1.2% | +0.55 | **67** |
| above 766 | 36,071 | 148 | 0.4% | +1.60 | **91** |
| missing | 22 | 3 | 13.6% | -2.17 | **5** |

The same is done for every kept feature (debt-to-income, loan-to-value, rate spread, loan term, channel, number of
borrowers...). A loan's **total score** is the sum of its points. A loan officer can read it and explain a refusal:
*"you lost 78 points because of your credit score band."*

## 4.2 The four steps to build it

### Step 1: bands (bins)
Cut each number into a few ranges. We let a tiny decision tree find the cut points on the training data, with rules:
at most 6 bands, each holding at least 5% of the loans. **Missing values get their own band** (a missing value can be
informative: "credit score missing" had a 13.6% default rate).

### Step 2: WoE (Weight of Evidence)
For each band: *is this band safer or riskier than average?*

> **WoE = ln ( share of all good loans in the band / share of all bad loans in the band )**
> (ln = natural logarithm; you only need to know that ln(1) = 0, positive for ratios above 1, negative below 1)

Worked example, band "662 or less":
- of the 1,566 bad loans in training, 454 are in this band -> **29.0%** of all bad loans
- of the 76,441 good loans, 3,496 are in it -> **4.6%** of all good loans
- ratio good/bad = 4.6 / 29.0 = 0.158 -> ln(0.158) = **-1.85**

Negative = riskier than average (this band holds 29% of the defaults but only 4.6% of the good loans). Positive = safer. Zero = average.

### Step 3: IV (Information Value): which features are worth keeping?

> **IV = sum over bands of (share of good - share of bad) x WoE**

For the band above: (0.046 - 0.290) x (-1.85) = **0.45**; add all bands to get the feature's IV (1.29 for the credit score).
Rule of thumb (a convention, not a law):

| IV | Reading |
|---|---|
| under 0.02 | useless |
| 0.02 - 0.1 | weak |
| 0.1 - 0.3 | medium |
| 0.3 - 0.5 | strong |
| **above 0.5** | **suspiciously good: check for leakage or an era proxy** |

Our real IV values: credit_score 1.29, rate_spread 0.58, dti 0.54, channel 0.42, orig_term 0.30, cltv 0.28, ltv 0.28,
n_borrowers 0.26, state 0.15, mi_pct 0.14, super_conforming 0.055. Dropped (weak): purpose 0.048, property_type 0.042,
loan size 0.027, occupancy 0.011, first-time buyer 0.004, prepayment penalty 0.002, number of units 0.000.

**A lesson we learned:** we tested the IV rule on columns of pure random noise. Because the bands are cut using the
answers, even noise reached IV 0.03-0.04. So we raised our keep-line from the textbook 0.02 to **0.05** (above the noise
level we measured). A rule of thumb must be tested, not trusted.

### Step 4: a logistic regression on the WoE values, then points
The logistic regression combines the WoE numbers with weights and turns the result into a probability between 0 and 100%:

```
 log-odds = intercept + w1 x WoE(credit score band) + w2 x WoE(dti band) + ...
 probability of default = 1 / (1 + e^(-log-odds))      (an S-shaped curve squeezing any number into 0-100%)
```
We checked that **every weight has the right sign**: a safer band must never raise the risk.

**Points** are just this log-odds rescaled with a bank convention. We chose (an **assumption**, in `config/assumptions.yaml`):

> a score of **600 means odds of 50 good loans per bad loan**, and **every +20 points doubles those odds**.

So two loans 20 points apart: the higher one has twice the odds of being good. Odds of 50:1 means a default
probability of about 2%. 620 points = 100:1 (about 1%). 580 points = 25:1 (about 3.8%). (Points are only a
scale; the real probability comes from the model.)

## 4.3 The other two models

| Model | How it works (simple) | Good | Weak |
|---|---|---|---|
| **Logistic regression** | The same weighted sum, but on the raw features | Simple, stable | Less readable than points |
| **XGBoost** | Hundreds of small decision trees; each new tree corrects the previous ones' mistakes; the votes are added | Finds combinations (low score *and* high debt) | A black box; can memorise training data |

A **decision tree** is a flowchart of questions ("credit score below 700? -> debt ratio above 40%? -> ..."). One tree is
weak; many small trees working in a chain are strong. To avoid memorising, we use shallow trees (depth 3), small steps,
and **early stopping** (stop adding trees when a held-out slice of the *training* data stops improving).

**Result of the comparison (final exam):** the three models are **statistically tied**. When a complex model does not
beat a simple one, the simple one wins: it is readable, auditable and explainable.

## 4.4 Explaining a decision

**Scorecard = self-explaining.** Because points add up, "points lost compared with the best band, per feature" is an
**exact** explanation. Real example for a risky loan (score 491, predicted default 47%):

```
 R01 Credit score is lower than for the safest applicants      [662 or less]   -78 points
 R03 Monthly debts are a high share of income (DTI)            [above 50.5]    -41 points
 R04 Loan came through a channel with a higher default rate    [T]             -31 points
 R05 Loan term differs from the lowest-risk term group         [above 347]     -25 points
```
The sentences are **fixed, written by a human** in `config/reason_codes.yaml`. No AI invents them.
Safe loans get **no reasons** (a reason needs at least 5 points lost).

**SHAP (for the black box):** imagine a team that scored a goal: SHAP asks "how much did each player contribute?".
It splits one prediction into one contribution per feature (positive = pushes the risk up). We used it to **check the
scorecard against XGBoost**: the scorecard's top reason is among XGBoost's top-3 SHAP features for **74%** of loans.

## 4.5 Calibration, class weights and SMOTE (a reminder)

- **Class weights**: tell the model "a default counts 49 times more" during training.
- **SMOTE**: invent artificial defaults until defaults are 50% of the training data.

Both are popular "fixes" for rare defaults, but they teach the model that defaults are common, so its **percentages
become wrong** (file 5). For a probability of default, we train on the data as it is.
