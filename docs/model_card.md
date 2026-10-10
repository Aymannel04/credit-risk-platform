# Model card: WoE scorecard for 24-month mortgage default (portfolio project)

Generated from `results/*.json` at commit `2ab1985`. Frozen exam commit: `1add760b87`.

> **Not a lending product.** A learning/portfolio project on public Freddie Mac data. No claim about any real lender, no regulatory compliance claim (Basel / IFRS 9 are used only as vocabulary).

## 1. Purpose and intended use
Estimate the probability that a newly originated, prime, fixed-rate mortgage is flagged as seriously delinquent within 24 months, using only information known at origination, and rank loans by risk. Intended for: demonstration, teaching, and discussing model risk. **Not intended for:** real credit decisions, pricing of real loans, or any group not in the data.

## 2. Data
Freddie Mac Single-Family Loan-Level Dataset, Standard Dataset, 50,000-loan samples of the 2008, 2012, 2016, 2019 and 2022 origination years (data not redistributed: Freddie Mac terms). Mortgages only, fixed rate, US.

| Vintage | loans | relief refinance removed | seasoned/modified removed | too young removed | kept |
|---|---|---|---|---|---|
| 2008 | 49,999 | 0 | 287 | 0 | 49,712 |
| 2009 | 1 | 0 | 0 | 0 | 1 |
| 2012 | 50,000 | 17,399 | 55 | 0 | 32,546 |
| 2016 | 50,000 | 2,525 | 103 | 0 | 47,372 |
| 2019 | 50,000 | 30 | 89 | 0 | 49,881 |
| 2022 | 50,000 | 0 | 22 | 71 | 49,907 |

## 3. Target
`default_24m` = 1 if, within 24 months of the loan's first month, the loan is 90+ days delinquent (or REO) **while no borrower assistance plan is active**, or ends with a credit-event zero balance code (02, 03, 09, 15). Definition choice and alternatives: `docs/decision-log.md`. The assistance-plan field exists only from 2014, so the rule is not symmetric across years.

## 4. Model
Weight-of-Evidence logistic scorecard, unweighted (no resampling, no class weights), fitted on 78,007 training loans. Features kept (Information Value >= 0.05): credit_score, mi_pct, cltv, dti, ltv, rate_spread, orig_term, n_borrowers, channel, state, super_conforming. Points: 600 points = 50:1 odds, +20 points double the odds (ILLUSTRATIVE convention, `config/assumptions.yaml`). Challengers: logistic regression and XGBoost (statistically tied in the exam).

Not used as inputs on purpose: zip3, MSA, seller name, affordable-housing program flag, vintage year, raw interest rate (replaced by the rate spread against the same quarter and term).

## 5. Performance (final exam, run once after a committed freeze; 95% paired-bootstrap intervals)

| Exam | loans / defaults | Gini scorecard | Gini logistic | Gini XGBoost | predicted vs real default rate (scorecard) |
|---|---|---|---|---|---|
| test_in_time | 19,431 / 375 | 0.735 (0.703-0.769) | 0.749 (0.716-0.781) | 0.747 (0.715-0.780) | 1.97% vs 1.93% |
| test_oot_2019 | 49,881 / 630 | 0.446 (0.405-0.485) | 0.456 (0.418-0.493) | 0.463 (0.423-0.497) | 1.75% vs 1.26% |
| test_oot_2022 | 49,907 / 692 | 0.523 (0.487-0.557) | 0.529 (0.495-0.562) | 0.528 (0.494-0.562) | 2.08% vs 1.39% |

No difference between the three models is statistically significant. The scorecard is recommended for being readable.

## 6. Calibration and level
Unweighted models are well calibrated in time (predicted/observed 1.02). Out of time the models over-predict by about 1.4x (2019) and 1.5x (2022): the model is a through-the-cycle model and cannot see the macro regime. Calibration (Platt) brought no gain on validation, so none is applied. Class weights and SMOTE inflate the PD (27.3% and 17.6% average predicted vs 2.04% real, validation ablation) and are not used.

## 7. Money (assumptions!)
Base case margin 2.0%, loss per flagged loan 10% (assumptions; measured loss per flagged loan: 2008: 20.1%, 2012: 4.4%, 2016: 1.1%, 2019: 0.4%, 2022: 0.5%). The line chosen on validation approves 97.5% of loans and adds about 0.024% of exposure over approving everyone; out of time it is slightly negative. The score is more useful for pricing and provisioning than for refusing prime loans.

## 8. Explainability
Scorecard points are additive: reasons are the features where a loan loses the most points (>= 5), with fixed sentences (`config/reason_codes.yaml`). On 2,000 validation loans, the scorecard's top reason is among XGBoost's top-3 SHAP features for 74% of loans.

## 9. Fairness (limits first)
No sex, race or age in the data: protected characteristics **cannot** be tested. Group differences that can be measured: first-time buyers, occupancy, purpose, property type, channel, state (`results/fairness_report.md`). In later years the model over-predicts first-time buyers more than repeat buyers, investors, broker-channel loans and Florida; refusal rates differ by group (the four-fifths rule is uninformative when 97-99% are approved).

## 10. Known flaws and limits
- **Era proxies.** `super_conforming` (exists only after Oct 2008) and `state` (2008 housing-bust map) act as era/geography proxies; `rate` was one and was replaced. A model v2 without them is planned and must be tested on fresh vintages (the current test sets are used).
- **Crisis-dominated training.** 76% of the training-period defaults come from the 2008 vintage.
- **Ranking falls out of time** (Gini 0.45-0.53 vs 0.74 in time); causes are hypotheses, not proven.
- Only five 50,000-loan samples; margin is illustrative; 2019 and 2022 losses are incomplete; PD is for a *flagged* delinquency, not a loss.
- The default definition and every number above depend on assumptions listed in `docs/decision-log.md`.

## 11. Monitoring (planned, Phase 3)
Predicted vs observed by period and by group, PSI of the score and main features, refusal-rate ratios by group, and a recalibration or macro-overlay trigger. Promotion of any new model is manual.
