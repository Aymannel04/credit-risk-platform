# Model v2: pre-registration (written and committed BEFORE the fresh labels are opened)

Date: 2026-10-11. Nothing in this file may be edited after the freeze (a hash of it is part of the frozen manifest).

## What is being tested
Three scorecard arms, all with the same scorecard method (bands, WoE, logistic regression, no resampling, no weights,
no calibration):

| Arm | Features | Training rows |
|---|---|---|
| v1 | the frozen v1 model (v1 features including state, channel, super_conforming, numeric n_borrowers) | v1 training split (60% of vintages 2008/2012/2016) |
| v1b | the same v1 features | **all** rows of the five known vintages (2008, 2012, 2016, 2019, 2022) |
| v2 | credit_score, dti, rate_spread, ltv, cltv, several_borrowers, mi_pct, orig_term, purpose | the same rows as v1b |

v2 feature rule (decided on the known vintages only, see `docs/decision-log.md` of 2026-10-11): keep a feature if its
information inside a vintage (above the noise floor) is at least 0.05; then remove `state` for fairness reasons (no cost in
leave-one-vintage-out ranking). `n_borrowers` becomes "several borrowers" (its definition changed in 2018Q2). The pooled-IV
keep threshold is not used for v2 (min_iv = 0): the list above is final.

## The exam
Fresh vintages (never used for any decision): **2010, 2014, 2018, 2023**, 50,000-loan Freddie Mac samples with the same
exclusions as before (relief refinance, seasoned/modified, not observable for 24 months) and the same target definition B.
Kept loans: 2010 35,304; 2014 42,566; 2018 49,377; 2023 49,834. Their labels (defaults) have not been read by anyone before
this file was written. Run once; paired bootstrap, 1000 resamples, seed 20261011.

## Predictions (honest expectations, informed by the leave-one-vintage-out results)
- **P1 ranking:** every arm has a Gini between 0.45 and 0.70 on 2010, 2014 and 2018 and between 0.40 and 0.60 on 2023.
- **P2 v2 vs v1:** the mean Gini difference over the four vintages lies between -0.03 and +0.03. I give about 70% to
  "non-inferior" and under 25% to "superior".
- **P3 data effect:** |Gini(v1b) - Gini(v1)| < 0.03 on average.
- **P4 level (predicted / observed default rate):** calm vintages 2014 and 2018 are over-predicted by a factor between 1.2 and
  3.0; 2010 between 0.5 and 1.6; 2023 between 1.0 and 3.0. v2's ratios stay within 0.25 of v1b's.
- **P5 groups:** v2 has a smaller spread of predicted/observed between groups than v1 for at least 4 of the 6 slice variables
  (first-time buyer, occupancy, purpose, property type, channel, state), measured on the four vintages pooled.

## Success rules (fixed in advance)
- **R1 (ranking, non-inferiority):** v2 is non-inferior to v1 if the 95% interval of the mean (over the four vintages) Gini
  difference v2 - v1 has its lower end above **-0.03**. It is superior if the lower end is above 0.
- **R2 (fairness):** v2 has the smaller group spread than v1 in at least **4 of the 6** slice variables.
- **Verdict:** v2 becomes the recommended model **only if R1 and R2 both hold**. Otherwise v1 remains the recommended model
  and the reasons are reported. The level of the predictions (macro effect) is reported but is not a success criterion.

## After the exam
No model, feature, setting or rule may be changed to improve these numbers. Any later idea is a new, labelled experiment
that needs new data. The results are reported in full whatever they are, including the predictions that turn out wrong.
