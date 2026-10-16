# Decision log

Each entry: date, decision, reasons, what was checked, what is still open.

## 2026-10-08: dataset = Freddie Mac Single-Family Loan-Level (Standard Dataset)

**Decision.** Main dataset is Freddie Mac's Single-Family Loan-Level Dataset. German Credit (UCI) stays as the small test fixture. Backup: UCI "Default of Credit Card Clients" (CC BY 4.0).

**Rejected: Home Credit Default Risk (Kaggle).** Its competition-specific rules replace the general data rule with: data may be used "only for the purposes of the Competition". The competition ended in August 2018, so a portfolio project is not covered. Source read on 2026-10-08: the competition's Rules page.

**Why Freddie Mac.**
- Terms (additional terms for the dataset, read via search results on 2026-10-08): free registration; personal or internal use for analysing credit performance; academic/research results and derived products may be made public if the distribution is non-commercial; no licensing or redistribution of the data to third parties; commercial distribution needs a paid licence. The owner registered on 2026-10-08.
- Real dates (loans from 1999): real out-of-time validation and real drift between vintages.
- Real loss data: LGD can be compared with data instead of being only an assumption.
- Free sample (50,000 loans per vintage year) for development.
- Two-table structure joined by loan sequence number (origination file and monthly performance file, pipe-delimited, no header row), per the General User Guide (January 2026).

**Consequences.**
- Mortgages, not consumer credit. Say so in the README.
- Raw data never in git, never in a public bucket, never shown row by row in the public demo.
- No sex, race or age fields: fairness slices are limited (first-time buyer, state, occupancy, loan purpose). Not a protected-class analysis.
- Dev-time simulated drift becomes an extra; real vintage drift is the main method.

**Not checked / open.**
- The exact definition of default (delinquency rule, zero balance codes). Read pages 10 to 23 of the user guide before building the target; record it here.
- The terms were read through search-result summaries of the official pages, not as a signed document. The owner must read the terms they accepted at registration and keep a copy before publishing anything.
- Whether the Standard or Non-Standard dataset is used (Standard planned), and which vintages (to be decided after inspecting the sample).
- This is not legal advice.

## 2026-10-08: imbalance handling

Unweighted model is the PD baseline; class weights and SMOTE are ablations; every variant is calibrated on a separate calibration split. First evidence (German Credit, out-of-fold, 3 seeds): calibration lowers Brier for all variants (about 0.168 to 0.161 for unweighted, 0.177 to 0.161 for class weights, 0.176 to 0.162 for SMOTE); raw average predicted PD is 0.287 (unweighted), 0.356 (class weights), 0.338 (SMOTE) against a true 0.300. See `docs/calibration_experiment.txt`.

## 2026-10-08: Dagster run history

A Cloud Run Job starts from an empty container, so Dagster's run history is not kept. The durable record is the `model_runs` table in BigQuery plus Cloud Logging. Persistent Dagster storage (Postgres on Cloud SQL) was rejected as extra cost and a server to manage.

## 2026-10-08: serving snapshot

The API holds a fixed sample of 5,000 applicants in memory (starting point; set the Cloud Run memory limit from a measurement), not the full table.

## 2026-10-09: cloud = AWS (was GCP); local-first

**Decision.** Deploy on AWS. Phases 1 and 2 run locally first (DuckDB + Parquet, Dagster on the PC); the cloud layer stays thin.

**Why.** Google Cloud billing setup failed with `OR_BACR2_59` ("Impossible de configurer votre compte"): a billing-account creation error that forum reports show for other users too, with no confirmed fix. The AWS account was created without problems. SafeSite used AWS S3 only through LocalStack, so real AWS deployment is still new for the portfolio.

**Mapping.** Cloud Storage -> S3; BigQuery -> Athena over Parquet in S3 (Glue Data Catalog), DuckDB locally; Cloud Run service -> Lambda container image behind a Function URL with IAM auth (to verify; fall back to ECS Fargate or App Runner); Cloud Run Job -> ECS Fargate task; Cloud Scheduler -> EventBridge Scheduler; Artifact Registry -> ECR; Secret Manager -> SSM Parameter Store or Secrets Manager; Workload Identity Federation -> GitHub OIDC with an IAM role; budget -> AWS Budgets; `maximum_bytes_billed` -> Athena workgroup per-query scan limit (to verify).

**Constraints found (from search results on 2026-10-09; verify in the Billing console).**
- AWS Free plan (accounts created after 2025-07-15): about $100 credits plus up to about $100 more for trying services. The plan ends after 6 months or when credits run out, whichever comes first; the account then closes instead of billing, data is kept about 90 days, and upgrading to a Paid plan reopens it (and can charge the card). So the demo and results must be produced early.
- Account security baseline: MFA on the root user, no root access keys, a non-root admin identity for daily work.

**Open.** Which plan the account is on; the region; Lambda limits and cold start with the model loaded; whether Athena's per-query scan limit works as assumed. Nothing has been created in AWS yet.

## 2026-10-09: AWS account setup (Phase 0 gate)

Done by the owner in the console (no resource created by the agent):
- Plan: **Free plan**. Region: **Europe (Stockholm), eu-north-1**.
- Root user: MFA with a passkey on one device; no access keys (checked in the console). A second MFA device could not be added yet; to retry later. Root is used only for billing and account tasks.
- Daily identity: IAM Identity Center user `ayman-admin` (single-Region instance in Stockholm, chosen over multi-Region to avoid KMS charges and replication to Oregon) with the `AdministratorAccess` permission set and an authenticator-app MFA device. Jobs and the API will get least-privilege roles later, not this permission set.
- Budgets: a zero-spend budget and a monthly cost budget of about 5 USD, both alerting by email. Budgets only warn; they do not stop spending.

Reminder: the Free plan ends after 6 months or when credits run out, whichever comes first (check the dates and credit balance in the Billing console). No AWS resource exists yet; Phases 1 and 2 run locally.

## 2026-10-09: target definition and model scope (Freddie Mac)

**Source.** Freddie Mac Single-Family Loan-Level Dataset General User Guide (January 2026), pages 10 to 23. The guide gives delinquency status, zero balance codes and actual loss fields, but **does not define "default"**. The definition below is this project's own assumption, to be validated on the data.

**Model scope (option A).** An *application* PD model: it scores a loan at origination using only fields of the origination file. Performance-file fields are used only to build the target (and, later, LGD). A second *behavioural* model (score after 12 months of payment history, using both files) is an optional extension, not in the core scope.

**Target.** `default_24m = 1` if, within 24 months after the loan's first reporting period, the loan either (a) reaches Current Loan Delinquency Status >= 3 (90+ days delinquent, or `RA` REO acquisition), or (b) ends with Zero Balance Code 02, 03, 09 or 15. Otherwise 0. Loans that end by voluntary payoff (01) or have a defect (96) without a prior default are 0 (not a credit loss event); to be checked on the data.

**Window and censoring.** 24 months. Only loans with at least 24 months of observable history (or a termination event inside the window) are used, so that "no default yet" is not confused with "not observed long enough". Loans from the most recent vintages are excluded. The exact cutoff depends on the Performance Cutoff Date of the downloaded release (to read from the Release Notes).

**Leakage rule.** No feature may come from the performance file for the application model. Allowed: credit score, first-time buyer flag, MI percentage, number of units, occupancy, original CLTV, original DTI, original UPB, original LTV, original interest rate, channel, property state/type, loan purpose, loan term, number of borrowers, and similar origination fields (to verify from the layout). Special values (e.g. 9999 credit score, 999 CLTV/DTI/LTV = not available) become missing, not numbers.

**Sensitive attributes.** The dataset has no sex, race or age. Geography (state, zip3) can act as a proxy for protected characteristics: report disparities by state/region and treat zip3 with care (likely excluded from the model).

**LGD.** Estimated from Actual Loss / Zero Balance Removal UPB on loans ending with codes 02, 03, 09, 15 (only where Actual Loss is populated; it is set to null for loans disposed in the last three months before the cutoff and for defect loans). Compared with the assumed LGD in `config/assumptions.yaml`; the assumption stays labelled as an assumption.

**Known data issues (from the guide).** Reporting gaps and irregular delinquency progressions exist; dates are month-level only; balances rounded; the dataset is "as is" and may be corrected. Data checks must tolerate these and log counts.

**Open.** Real column positions to be taken from the official file layout; the vintages to use; the default rate by vintage; whether voluntary payoff after a long delinquency should count; whether the Standard dataset sample has enough defaults per vintage (to measure before modelling).

## 2026-10-09: Freddie Mac sample layout verified against the real files

Checked on `sample_2016` (all 50,000 origination rows, 400,000 performance rows) against the January 2026 user guide. The guide and the files differ:
- Origination has **31** fields (guide: 32). Fields 1-23 match the guide. Field 25 is the super conforming flag (Y/N), so the servicer name is **not** in the origination file. Field 31 is always `9999` (unknown, unused).
- Performance has **35** fields (guide: 32). Fields 1-32 match; 33 = MI cancellation indicator (`7`/`N`/`Y`), 34 = servicer name, 35 = unused amount (blank or `0.00`).
- `Current Loan Delinquency Status` is **text** (`00`, `01`, ..., plus letters such as `RA`; 46 distinct values in the first 400,000 rows). Never read it as a number without handling the letters.
- File names are `sample_orig_YYYY.txt` and `sample_perf_YYYY.txt` (the guide calls the second `svcg`).
- Join key: `loan_seq` (origination column 20, performance column 1).

Loaded 2008, 2012, 2016, 2019, 2022 to raw Parquet (all columns as text): 50,000 loans each; performance rows 2,456,504 / 4,510,559 / 3,379,650 / 1,934,614 / 2,034,798. Code: `credit/freddie/layout.py`, `credit/freddie/load.py`; tests: `tests/test_freddie_layout.py`. Data lives only in `data/raw/freddie/` and `data/interim/` (git-ignored; the terms forbid redistribution).

Correction to the earlier year choice: 2010/2012/2015 was not a good spread (calm vintages have few defaults). Chosen instead: 2008 (crisis), 2012 (calm), 2016 (normal), 2019 (pre-COVID), 2022 (higher rates). The train/test split by year will be decided after measuring default rates per vintage.

## 2026-10-09: default definition B and exclusions (decided by the owner)

**Profile of the raw samples (read-only, 50,000 loans per vintage; 24-month window).** Default counts under three definitions:
- A (90+ days late or loss event): 2008 4.47%, 2012 0.75%, 2016 0.81%, 2019 4.63%, 2022 1.85%.
- B (90+ days late only when no borrower assistance plan is active, or loss event): 2008 4.46%, 2012 0.74%, 2016 0.66%, 2019 1.26%, 2022 1.52%.
- C (loss event only, zero balance codes 02/03/09/15): 0.46%, 0.17%, 0.02%, 0.01%, 0.02% (too few to train on).
The 2019 vintage drops from 4.63% to 1.26% under B because most of its 90+ day delinquencies happened during COVID-era borrower assistance (forbearance), not credit trouble.

**Decision 1: use definition B** as the target `default_24m`. A is reported as a sensitivity check. Limitation: the borrower assistance code is only populated from January 2014, so for vintages whose 24-month window ends before then (2008) B cannot exclude anything; the rule is not symmetric across years and the README must say so.

**Decision 2: exclude from the main model** (a) relief refinance loans (`relief_refi = 'Y'`: 17,399 loans in the 2012 sample, 2,525 in 2016, 30 in 2019) and (b) loans whose first payment date is more than 6 months after the vintage quarter in `loan_seq` (seasoned or modified at acquisition: 287 / 55 / 103 / 89 / 22 loans in 2008 / 2012 / 2016 / 2019 / 2022). Counts of excluded loans are logged at each run. Also excluded: loans without 24 months of observable history (73 loans of the 2022 sample).

**Other cleaning rules.** `9999` credit score, `999` for CLTV/LTV/DTI/MI percentage, `99` for number of units or borrowers, `9` for first-time buyer flag become missing. Empty fields are NULL in the Parquet files. Delinquency status is text: numbers `00`..`99` or `RA`.

**Correction logged.** A first profiling query dropped loans through SQL NULL logic (a comparison with NULL returns NULL, not TRUE or FALSE). It was caught because two columns were identical in every year. Always wrap nullable comparisons in COALESCE.

## 2026-10-09: staging layer built (silver)

Code: `credit/freddie/staging.py`; tests: `tests/test_staging.py` (toy loans, one rule each, plus failing-check tests). Output (git-ignored): `data/interim/stg/stg_orig_<year>.parquet`, `stg_label_<year>.parquet`, `report_<year>.json`.

Staging types the data and **flags** (does not remove) relief refinance and seasoned/modified loans; exclusions are applied in the features layer and counted there. Checks that stop the run: unique `loan_seq`, no performance rows without an origination row, ranges for `orig_upb`, `int_rate`, `orig_term`, `dti`, `credit_score`, at most 1% missing credit scores, labels only 0/1, default rate between 0 and 20%, and a leakage test (no label-like column in the origination table). The sanity limits are parameters (relaxed only in toy tests).

Results on the real samples (default definition B = `default_24m`; A = all 90+ late; C = loss events only; counts among observable loans):
| Vintage | Loans | Relief refi | Seasoned/modified | Not observable | Defaults B | A | C |
|---|---|---|---|---|---|---|---|
| 2008 | 50,000 | 0 | 287 | 0 | 2,228 | 2,237 | 229 |
| 2012 | 50,000 | 17,399 | 55 | 0 | 369 | 376 | 86 |
| 2016 | 50,000 | 2,525 | 103 | 0 | 328 | 407 | 12 |
| 2019 | 50,000 | 30 | 89 | 0 | 632 | 2,315 | 3 |
| 2022 | 50,000 | 0 | 22 | 73 | 692 | 856 | 8 |

Note: the earlier profile showed 761 (B) and 926 (A) for 2022 because it counted all loans, including the 73 not observable for 24 months; the pipeline counts only observable loans.

## 2026-10-09: features layer and splits (gold)

Code: `credit/freddie/features.py`; tests: `tests/test_features.py`. Output (git-ignored): `data/interim/features/features.parquet`, `report.json`.

**Exclusions (applied in this order, counted per vintage).** Relief refinance, then seasoned/modified, then not observable for 24 months. Kept loans: 2008: 49,712; 2009 (one odd loan in the 2008 file): 1; 2012: 32,546; 2016: 47,372; 2019: 49,881; 2022: 49,907. Relief refinance removed 35% of the 2012 sample (17,399 loans); this is a notable choice and must be stated in the README.

**Model inputs (day-one, origination file only).** Numeric: credit_score, mi_pct, n_units, cltv, dti, orig_upb, ltv, int_rate, orig_term, n_borrowers. Categorical: first_time_homebuyer, occupancy, channel, ppm_flag, property_type, purpose, state, super_conforming.
**Deliberately not inputs:** zip3 and msa (geography proxies), seller_name (lender identity), program_indicator (affordable-housing programme: proxy for income), vintage_year (does not transfer across time; used for splitting only), maturity_date (redundant with term), amort_type / io_indicator / property_valuation_method (constant in these samples). `state` is kept for now and is a candidate to drop after the fairness review.

**Splits (reproducible: hash of loan_seq with seed `split-v1`).** Development pool = vintages <= 2018 (files 2008, 2012, 2016): train 60% / calibration 10% / validation 15% / in-time test 15%. Out-of-time tests: 2019-2021 vintages (`test_oot_2019`) and 2022+ vintages (`test_oot_2022`). Vintage ranges are used rather than exact years because the 2008 file contains one 2009 loan.

| Split | Loans | Defaults (B) | Default rate |
|---|---|---|---|
| train | 78,007 | 1,566 | 2.01% |
| calibration | 13,064 | 248 | 1.90% |
| validation | 19,129 | 391 | 2.04% |
| test_in_time | 19,431 | 375 | 1.93% |
| test_oot_2019 | 49,881 | 630 | 1.26% |
| test_oot_2022 | 49,907 | 692 | 1.39% |

**Consequences.** The calibration split has only 248 defaults: isotonic calibration would overfit, so Platt scaling (2 parameters) is the default choice there; isotonic only as a comparison. Default rates differ across vintages (2008 pool is crisis-heavy, 2019/2022 are not): this is the drift that Phase 3 monitors. The out-of-time sets are never used to choose models or thresholds.

**Honest limits.** 5 vintages sampled at 50,000 loans each, not the full dataset; the assistance-plan rule behind label B only exists from 2014 (see 2026-10-09 entry on definition B).

## 2026-10-09: baseline logistic regression and the "era mix" finding (validation only)

Code: `credit/models/{data,metrics,baseline_logreg}.py`; tests: `tests/test_models_basics.py` (test splits are locked in `load`: they raise unless `allow_test=True`). Results: `results/baseline_validation.json`. Model: unweighted logistic regression (C=1, median imputation + missing flags, standardised numbers, one-hot categories), trained on `train`, measured on `train` and `validation` only.

| | n | defaults | AUC | Gini | KS | Brier | mean predicted PD vs real |
|---|---|---|---|---|---|---|---|
| train | 78,007 | 1,566 | 0.906 | 0.812 | 0.662 | 0.01710 | 2.01% vs 2.01% |
| validation (pooled) | 19,129 | 391 | 0.913 | 0.826 | 0.687 | 0.01736 | 2.07% vs 2.04% |
| validation, vintage 2008 only | 7,435 | 346 | 0.872 | 0.743 | 0.607 | | |
| validation, vintage 2016 only | 6,888 | 41 | 0.789 | 0.577 | 0.490 | | |

**Finding.** The pooled Gini (0.83) looks too good because it mixes eras: the 2008 vintage has both high interest rates (avg 6.05%) and high defaults (4.50%), while 2012 and 2016 have rates of about 3.6-3.8% and defaults of 0.26% and 0.61% (train). The model earns part of its ranking by recognising the era, not by judging one borrower. The model also ranks well inside a single vintage (0.87 within 2008), so it is not only an artefact, and there is no leakage (no performance-file field is used; `int_rate` is known at origination). Single-feature AUC on validation: int_rate 0.84, credit_score 0.80, dti 0.71, ltv 0.63.

**Consequences.** (1) Never quote pooled development metrics alone: always report per vintage and on the out-of-time tests. (2) The 2016 vintage has only 41 validation defaults: its numbers are noisy. (3) The out-of-time 2019 and 2022 exams are the honest test of whether the model works in an era it never saw. (4) Options to examine later, not decided: weight vintages equally, add a vintage-adjusted metric, or report a within-vintage average Gini as the headline. The calibration of the raw probabilities is already close on average (2.07% vs 2.04%) but not yet checked per risk band or per vintage.

## 2026-10-09: XGBoost vs logistic regression (validation only)

Code: `credit/models/xgboost_model.py`; tests: `tests/test_xgboost_model.py`; results: `results/xgboost_validation.json`. Unweighted XGBoost (max depth 3, learning rate 0.05, min child weight 5, subsample 0.8, column sample 0.8, L2 penalty 5), same preprocessing as the baseline. Early stopping on a 15% inner holdout of `train` (validation is never used for stopping): 219 trees used. Test splits not used.

| | AUC | Gini | KS | PR-AUC | Brier | mean PD | real |
|---|---|---|---|---|---|---|---|
| logistic, train | 0.906 | 0.812 | 0.662 | 0.234 | 0.01710 | 2.01% | 2.01% |
| xgboost, train | 0.917 | 0.834 | 0.677 | 0.271 | 0.01664 | 2.01% | 2.01% |
| logistic, validation | 0.913 | 0.826 | 0.687 | 0.240 | 0.01736 | 2.07% | 2.04% |
| xgboost, validation | 0.913 | 0.825 | 0.675 | 0.248 | 0.01728 | 2.05% | 2.04% |
| logistic, val. vintage 2008 | 0.872 | 0.743 | 0.607 | 0.264 | 0.03867 | 4.52% | 4.65% |
| xgboost, val. vintage 2008 | 0.864 | 0.728 | 0.589 | 0.272 | 0.03853 | 4.51% | 4.65% |
| logistic, val. vintage 2016 | 0.789 | 0.577 | 0.490 | 0.036 | 0.00586 | 0.66% | 0.60% |
| xgboost, val. vintage 2016 | 0.815 | 0.629 | 0.534 | 0.050 | 0.00581 | 0.62% | 0.60% |

**Reading.** On the pooled validation set the two models tie (AUC 0.913 each). Inside 2008 the logistic regression is slightly better (Gini 0.743 vs 0.728); inside 2016 XGBoost is better (0.629 vs 0.577) but that vintage has only 41 validation defaults. With 391 validation defaults the AUC standard error is about 0.01, so these differences are within noise. XGBoost fits the training data a little better (train Gini 0.834 vs 0.812) without winning on validation: mild overfitting, no real gain. Both models are already well matched to the real default rate on average.

**Consequence.** On this data (few features, mostly monotonic effects) the interpretable model is competitive. The WoE scorecard is therefore a serious candidate, not only a benchmark; the decision between the models is deferred to the out-of-time exams and the calibration comparison. Bootstrap intervals are needed before claiming any winner.

## 2026-10-09: calibration on validation (Platt vs isotonic)

Code: `credit/models/calibration.py` (Platt scaling = 2 numbers on the log-odds; isotonic = free staircase), `credit/models/calibrate.py`; tests: `tests/test_calibration.py`; new metric `ece` (expected calibration error over 10 equal-sized risk groups). Both calibrators are fitted only on the calibration split (13,064 loans, 248 defaults) and measured on validation. Results: `results/calibration_validation.json`, chart `docs/calibration_validation.png`.

| Model | Version | Brier | ECE | AUC | mean PD | real |
|---|---|---|---|---|---|---|
| logistic | raw | 0.01736 | 0.00169 | 0.913 | 2.07% | 2.04% |
| logistic | Platt | 0.01736 | 0.00239 | 0.913 | 1.93% | 2.04% |
| logistic | isotonic | 0.01738 | 0.00209 | 0.911 | 1.92% | 2.04% |
| xgboost | raw | 0.01728 | 0.00251 | 0.913 | 2.05% | 2.04% |
| xgboost | Platt | 0.01730 | 0.00282 | 0.913 | 1.93% | 2.04% |
| xgboost | isotonic | 0.01736 | 0.00273 | 0.910 | 1.93% | 2.04% |

Platt parameters: logistic slope 0.995 / offset -0.094; xgboost slope 1.013 / offset -0.038. A slope of 1 and a small offset mean the raw probabilities were already well calibrated.

**Findings.**
1. The unweighted models are already calibrated on average, so calibration brings no gain here (Brier unchanged, ECE slightly worse). The small shift comes from the calibration split having a lower default rate (1.90%) than validation (2.04%) with only 248 defaults: the correction learned a bit of noise. A calibrator must earn its place on validation; here it does not.
2. Isotonic is dangerous for the safest loans: its staircase assigns predicted risks near 0.0001% to the lowest group while about 0.15% of those loans default (visible on the chart), and it creates ties (AUC 0.913 -> 0.910-0.911). Platt keeps the ranking exactly.
3. By vintage the average is close: observed 4.65% (2008) vs predicted 4.52% raw; observed 0.60% (2016) vs 0.66% raw. Calibration across eras is the weak point to watch on the out-of-time tests.

**Consequence.** Calibration stays in the pipeline as a step that is applied only if it improves validation. Its real test is the ablation (class weights and SMOTE), where the training distortion we measured on German Credit should appear again; that comparison is next. A larger calibration set or cross-fitted calibration is an option if noise remains a problem.

## 2026-10-09: imbalance ablation on validation (unweighted vs class weights vs SMOTE)

Code: `credit/models/ablation.py`; tests: `tests/test_ablation.py`; results: `results/ablation_validation.json`, chart `docs/ablation_validation.png`. Same XGBoost (219 trees, no early stopping) for all variants; only the imbalance treatment differs. Trained on `train` (78,007 loans, 1,566 defaults), calibrators fitted on `calibration`, measured on `validation` (19,129 loans, real default rate 2.04%). Test splits not used.

| Variant | Version | Brier | ECE | AUC | mean predicted PD |
|---|---|---|---|---|---|
| unweighted | raw | **0.01725** | 0.00295 | **0.915** | 2.04% |
| unweighted | Platt | 0.01727 | 0.00295 | 0.915 | 1.92% |
| class weights (x48.8) | raw | 0.12280 | 0.22746 | 0.913 | **24.79%** |
| class weights | Platt | 0.01746 | 0.00285 | 0.913 | 1.92% |
| class weights | isotonic | 0.01756 | 0.00400 | 0.909 | 1.93% |
| SMOTE (50/50) | raw | 0.06543 | 0.14659 | 0.904 | **16.70%** |
| SMOTE | Platt | 0.01775 | 0.00168 | 0.904 | 1.92% |
| SMOTE | isotonic | 0.01793 | 0.00147 | 0.901 | 1.94% |

**Findings.**
1. Class weights and SMOTE inflate the predicted risk 12x and 8x (24.8% and 16.7% against a real 2.04%): Brier is 7.1x and 3.8x worse than the unweighted model. This is the v1 flaw, now reproduced on 100,000 real loans.
2. Class weights distort only the level, not the ranking: AUC 0.913 vs 0.915. Platt scaling repairs it almost completely (Brier 0.01746). Its offset is -3.856, which matches -ln(n_non-default / n_default) = -ln(76,441 / 1,566) = -3.888 (the classic prior-shift correction), with a slope near 1.
3. SMOTE distorts both level and ranking: AUC falls from 0.915 to 0.904 (synthetic defaults blur the boundary), and calibration cannot restore ranking. After calibration SMOTE is still worse than the unweighted model (Brier 0.01775 vs 0.01725).
4. Conclusion for the project: the unweighted model is the best PD baseline; class weights plus calibration is acceptable but gains nothing; SMOTE is not recommended. Isotonic does not beat Platt except on ECE for SMOTE, and carries the low-risk-tail danger noted earlier.

**Bug found and fixed during this step (keep for the interview).** A first SMOTE run showed predicted risk of 0.7% (below the real 2.04%), which contradicted theory (balanced training should inflate risk). Cause: XGBoost treats empty cells of a SPARSE table as missing values, not zeros; I trained SMOTE on a dense table and predicted on the sparse output of the preprocessor. Same model, three different answers: dense/dense 16.7%, dense/sparse 0.7%, sparse/sparse 13.3%. Fix: `make_preprocessor` now always outputs a dense array (`sparse_threshold=0`), guarded by a test. The logistic and XGBoost results were re-run and are unchanged (they trained and predicted in the same format), so earlier entries stand.

## 2026-10-09: WoE scorecard (validation only)

Code: `credit/models/scorecard.py`, `credit/models/scorecard_report.py`; tests: `tests/test_scorecard.py`; config: `config/assumptions.yaml` (scaling 600 points = 50:1 odds, +20 points doubles the odds: ILLUSTRATIVE; binning rules). Results: `results/scorecard_validation.json`, `results/scorecard_table.csv` (points per band), `results/scorecard_iv.csv`. Bands from a small decision tree on `train` (max 6 numeric bands, >= 5% of loans each; missing values get their own band; categories under 1% grouped as "other"), WoE with +0.5 smoothing, logistic regression on the WoE values (L2, C=1, unweighted), points = rescaled log-odds.

**IV screen.** Kept (IV >= 0.05): int_rate 1.49, credit_score 1.29, dti 0.54, channel 0.42, orig_term 0.30, cltv 0.28, ltv 0.28, n_borrowers 0.26, state 0.15, mi_pct 0.14, super_conforming 0.055. Dropped: purpose 0.048, property_type 0.041, orig_upb 0.027, occupancy 0.011, first_time_homebuyer 0.004, ppm_flag 0.002, n_units 0.000. No coefficient has the wrong sign.

**Threshold change (measured).** The textbook IV >= 0.02 let pure-noise columns in: bands are cut using the defaults, so noise columns reach IV 0.03-0.04 (max over 10 noise features, 78k loans / 2% defaults, first settings); with 6 bands of >= 5% the noise max is 0.029, so the threshold was set to 0.05. A feature with a true IV between 0.02 and 0.05 would be lost: purpose (0.048) and property_type (0.041) are close; revisit if needed.

| | n | AUC | Gini | KS | Brier | mean PD | real |
|---|---|---|---|---|---|---|---|
| scorecard, train | 78,007 | 0.900 | 0.799 | 0.643 | 0.01757 | 2.01% | 2.01% |
| scorecard, validation | 19,129 | 0.908 | 0.816 | 0.672 | 0.01781 | 2.06% | 2.04% |
| scorecard, val. 2008 | 7,435 | 0.850 | 0.699 | 0.548 | 0.03986 | 4.46% | 4.65% |
| scorecard, val. 2016 | 6,888 | 0.826 | 0.651 | 0.593 | 0.00583 | 0.69% | 0.60% |

Compared with the logistic regression (validation Gini 0.826; 2008: 0.743; 2016: 0.577) and XGBoost (0.825; 0.728; 0.629): the scorecard is about 0.01 Gini lower pooled and lower inside 2008, higher inside 2016 (41 defaults: noise). Score range on validation: 465 to 751 points. Example points: credit score <= 662 -> 16, > 766 -> 88; dti <= 29.5 -> 65, > 50.5 -> 38.

**Warning found: interest rate is an era proxy.** IV above 0.5 is the textbook warning sign. No leakage (the rate is known at origination), but `int_rate` mixes two things: the lender's risk pricing and the market level of the year. Average rate by vintage (kept loans, inputs only, no outcomes): 2008 6.05%, 2012 3.60%, 2016 3.78%, 2019 4.24%, 2022 5.09%. The pooled model therefore partly learns "high rate = 2008-like crisis". On the 2022 vintage (rates back near 5%) it will likely over-predict risk. This is an input shift, observed without touching test labels. Proposed fix (not yet done): replace the raw rate by a rate spread (rate minus the median rate of the same vintage quarter and term), which keeps the lender's risk pricing and removes the market level.

## 2026-10-09: rate spread replaces the raw interest rate (decision by the owner: "go")

**Change.** `rate_spread` = a loan's `int_rate` minus the median `int_rate` of the kept loans with the same vintage quarter and term class (<= 180 months vs longer). It is a model input; `int_rate` stays in the features table as a tracing/monitoring column (META) and a check forbids it as a feature. Only inputs are used, no outcomes. Deployment note: the median would come from a market rate series, since a single loan has no "same quarter" peers at scoring time. Sanity: average spread per vintage 2008 0.044, 2012 0.004, 2016 0.050, 2019 0.061, 2022 -0.014 (average raw rate 6.05 / 3.60 / 3.78 / 4.24 / 5.09). Code: `credit/freddie/features.py`; tests added in `tests/test_features.py`; 48 tests pass.

**Effect on validation Gini (before with raw rate -> after with spread).**
| Model | pooled | inside 2008 | inside 2016 |
|---|---|---|---|
| logistic | 0.826 -> 0.784 | 0.743 -> 0.726 | 0.577 -> 0.590 |
| xgboost | 0.825 -> 0.785 | 0.728 -> 0.711 | 0.629 -> 0.597 |
| scorecard | 0.816 -> 0.779 | 0.699 -> 0.691 | 0.651 -> 0.653 |
About 0.04 of the pooled Gini was the era proxy; ranking inside a year is almost unchanged, which is the evidence that the spread keeps the lender's risk pricing. IV of the spread 0.578 (raw rate was 1.491). Validation Brier / mean PD: logistic 0.01782 / 2.06%, xgboost 0.01763 / 2.03%, scorecard 0.01811 / 2.04% (real 2.04%).

**New finding: the models no longer know the era, so their average risk is about the same for every vintage, while the real default rate is not.** Logistic on validation by vintage: 2008 observed 4.65% vs predicted 3.46%; 2016 observed 0.60% vs predicted 1.51%. Loan-level day-one data cannot tell whether a year is a crisis year (a macro effect). This is a through-the-cycle model: it ranks borrowers within an era well and gives an average-era level of risk. Consequences: (1) expect the out-of-time tests (2019: 1.26%, 2022: 1.39% real) to be slightly over-predicted; (2) a bank would add a macroeconomic overlay or recalibrate per period; (3) monitoring must track observed vs predicted by period (Phase 3).

**Re-run after the change (supersedes the earlier numeric tables for calibration and ablation; conclusions unchanged).** Ablation on validation (real 2.04%): unweighted raw Brier 0.01764, mean PD 2.03%, AUC 0.894; class weights raw Brier 0.13133, mean PD 27.29%, after Platt 0.01773 (offset -3.848); SMOTE raw Brier 0.06520, mean PD 17.61%, AUC 0.879 and after Platt 0.01813 (the ranking loss remains). Calibration of unweighted models: Platt slope 1.00 and 0.99, no gain (ECE rises slightly), as before.

## 2026-10-10: FINAL EXAM (run once; frozen at commit 1add760, manifest committed in 178ed74 before the run)

Models trained on `train` only (78,007 loans), raw probabilities (no calibration), as frozen. Code: `credit/models/final_exam.py`; the exam refused to run before the freeze (verified), and refuses if the features file, the config, or the code changed after the freeze commit. Results: `results/final_exam.json`, `results/final_exam.md`, `docs/final_exam.png` (redrawn by `scripts/plot_final_exam.py`, cosmetic). 95% intervals: paired bootstrap over loans, 1000 resamples, seed 20261010.

| Exam | Loans / defaults | Model | Gini (95% CI) | KS | Brier | predicted vs real | ratio (95% CI) |
|---|---|---|---|---|---|---|---|
| in time (2008/2012/2016) | 19,431 / 375 | scorecard | 0.735 (0.703-0.769) | 0.584 | 0.01754 | 1.97% vs 1.93% | 1.02 (0.93-1.13) |
| | | logistic | 0.749 (0.716-0.781) | 0.597 | 0.01727 | 1.96% | 1.02 |
| | | xgboost | 0.747 (0.715-0.780) | 0.595 | 0.01731 | 1.96% | 1.02 |
| out of time 2019 | 49,881 / 630 | scorecard | 0.446 (0.405-0.485) | 0.338 | 0.01264 | 1.75% vs 1.26% | 1.38 (1.28-1.50) |
| | | logistic | 0.456 (0.418-0.493) | 0.337 | 0.01281 | 1.82% | 1.44 |
| | | xgboost | 0.463 (0.423-0.497) | 0.354 | 0.01268 | 1.62% | 1.28 |
| out of time 2022 | 49,907 / 692 | scorecard | 0.523 (0.487-0.557) | 0.409 | 0.01383 | 2.08% vs 1.39% | 1.50 (1.40-1.62) |
| | | logistic | 0.529 (0.495-0.562) | 0.416 | 0.01390 | 2.07% | 1.49 |
| | | xgboost | 0.528 (0.494-0.562) | 0.413 | 0.01385 | 2.00% | 1.44 |

No Gini difference between models is significant in any exam (all paired 95% intervals include 0; scorecard minus logistic in time: -0.014, interval -0.028 to +0.001, borderline). Inside the in-time exam by vintage (point estimates): 2008 scorecard 0.654 / logistic 0.700 / xgboost 0.686; 2016 0.682 / 0.638 / 0.637.

**Predictions written before the run vs outcome.** In-time Gini 0.75-0.80: observed 0.735-0.749 (low edge). Out-of-time "a bit lower": observed 0.45 (2019) and 0.52-0.53 (2022): a much larger drop than predicted. Over-prediction ratio 1.4-1.6x: observed 1.28-1.50x. No clear winner: confirmed.

**Findings.**
1. Ranking power is much weaker out of time (Gini about 0.45-0.53 vs about 0.74 in time). Untested hypotheses: (a) the training defaults are dominated by the 2008 crisis vintage (2,228 of the 2,925 defaults of the 2008/2012/2016 samples, i.e. 76%, before splitting and before exclusions; corrected on 2026-10-10: a first version of this line said 4,225), so the models learned crisis-type risk patterns; (b) defaults in calm years are driven by events a day-one application cannot see (job loss, illness, divorce); (c) the 2019 label depends on the assistance-plan rule (definition B) and COVID-era servicing. To be tested only as NEW, labelled experiments (for example training on non-crisis vintages only, or vintage weights); these exam numbers stay in the record and are not to be tuned.
2. The level is off out of time: the models predict about 1.3-1.5x the real default rate in 2019 and 2022 (as expected from the through-the-cycle design noted on 2026-10-09). Their Brier is slightly worse than a flat forecast that already knows the true rate (2019: 0.01264-0.01281 vs 0.01247; 2022: 0.01383-0.01390 vs 0.01367), whereas in time they beat the flat forecast (0.0173-0.0175 vs 0.0189): the level error out of time costs more than the ranking brings. A macro overlay or per-period recalibration is the standard remedy and belongs to the monitoring phase.
3. Model choice: the three models are statistically indistinguishable, so the WoE scorecard is the recommended primary model (readable points, full audit trail), with logistic regression and XGBoost kept as challengers. The cost is at most about 0.01-0.02 Gini, within the noise.
4. Calibration of the unweighted models in time is right (ratio 1.02, interval 0.93-1.13).

## 2026-10-10: LGD measured from the real loss data (all five samples, after exclusions)

Code: `credit/economics/lgd.py` (+ `tests/test_lgd.py`, checked against a hand calculation); result: `results/lgd_estimate.json`. EAD = original loan amount (approximation). Actual Loss = (unpaid balance + unpaid interest) - sale proceeds - insurance and other recoveries - expenses; NULL for loans disposed in the last 3 months before the cutoff and for defect loans; gains (negative losses) are kept. This is an analysis of what happened, not a model parameter fitted for the exam.

| Vintage | flagged defaults (B) | of which ended in a loss event (ever) | LGD of loss events (loss / balance at end) | median loss share | loss events with no loss or a gain | **loss per flagged loan** (sum of losses / sum of original amounts) |
|---|---|---|---|---|---|---|
| 2008 | 2,219 | 1,048 (47%) | **45.8%** | 45.9% | 3.1% | **20.1%** |
| 2012 | 73 | 20 (27%) | 20.9% | 20.5% | 8.5% | 4.4% |
| 2016 | 288 | 32 (11%) | 10.8% | 4.6% | 13.9% | 1.07% |
| 2019 | 630 | 27 (4%) | 13.4% | 11.3% | 15.2% | 0.37% |
| 2022 | 692 | 48 (7%) | 10.7% | 10.3% | 17.8% | 0.46% |

**Findings.**
1. Two different LGDs. The severity once a loan really ends in a loss is 11-46% (crisis 2008: 46%; calm years: about 11-21%). But most flagged defaults never end in a loss: in calm vintages only 4-27% of flagged loans have a loss event at all (2008: 47%), the others cure or are paid off.
2. The multiplier that matches our PD (which counts every flagged loan) is the loss per flagged loan: 20.1% in the 2008 crisis vintage, 4.4% in 2012, about 1.1% in 2016, and 0.4% in 2019/2022 (2019 and 2022 are right-censored: foreclosure and sale take years, so their losses are still incomplete; the true values are higher).
3. The economics therefore depend strongly on the era (a macro effect, like the default rate itself). A cut-off derived from a single LGD would be wrong in one regime or the other: the sensitivity analysis must span LGD from below 1% to 20% of the loan amount.
4. Definition B (90+ days late without an assistance plan) is a conservative risk flag in calm times: it flags many loans that cure. PD under B is a "serious delinquency" probability, not a loss probability; expected loss must use loss per flagged loan, not the loss severity of foreclosures. This must be stated in the model card.
5. Only loans flagged within the first 24 months are counted: loss events after month 24 (about half of the 2008 loss events) are outside the label.

## 2026-10-10: cut-off, profit, expected loss and sensitivity (scorecard; analysis made AFTER the final exam)

Code: `credit/economics/cutoff.py`, `credit/economics/decision_report.py`; tests: `tests/test_cutoff.py`; assumptions: `config/economics.yaml` (margin 2% over 24 months, base loss per flagged loan 10%: ASSUMPTIONS; the loss grid 1/5/10/20% comes from the measured 0.4-20% range). Results: `results/economics_report.json|md`, `docs/economics_report.png`. Scorecard fitted on `train`, raw PD. The line (PD threshold) is chosen on validation by realised profit; test splits only report. Adding code under `credit/` means `credit.models.final_exam` now refuses to run again (by design); the exam results are not touched.

**Chosen line (base case, validation).** Approve if PD <= 0.1471 (97.5% of loans approved); the textbook line margin/(margin+loss) = 0.1667. The profit curve is nearly flat near its top (chart).

| Group | Approval | Default rate approved vs all | Defaults refused | Good loans refused | Profit with line | Approve all | Realised loss in the data |
|---|---|---|---|---|---|---|---|
| validation | 97.50% | 1.48% vs 2.04% | 29.4% | 1.9% | 1.77% of exposure | 1.75% | 0.65% |
| test_in_time | 97.65% | 1.53% vs 1.93% | 22.7% | 1.9% | 1.77% | 1.76% | 0.65% |
| test_oot_2019 | 99.11% | 1.21% vs 1.26% | 5.2% | 0.8% | 1.84% | 1.84% | 0.01% (incomplete) |
| test_oot_2022 | 99.07% | 1.35% vs 1.39% | 3.5% | 0.9% | 1.83% | 1.84% | 0.01% (incomplete) |

Gain of the line over "approve everyone" (% of exposure, margin 2%): at loss 1% / 5% / 10% / 20%: validation -0.027 / -0.005 / +0.024 / +0.081; in time -0.029 / -0.013 / +0.006 / +0.046; 2019 -0.013 / -0.010 / -0.008 / -0.002; 2022 -0.015 / -0.013 / -0.010 / -0.005.

**Sensitivity (validation).** The best line gets stricter when the margin is lower or the loss higher, as the formula says: margin 0.5% with loss 20% refuses 28% of loans (gain +0.251% of exposure); margin 3% with loss 1-5% refuses almost nothing (gain about 0). See `results/economics_report.md` for all 16 cells.

**Findings.**
1. For these prime mortgages, refusing loans adds very little profit under the base assumptions (+0.02% of exposure on validation): approving everyone already earns about 1.75%, because only about 2% of loans are flagged and the margin on the other 98% pays for them. The scorecard separates risk well (the riskiest decile has a 12.75% default rate against 2.04% on average) but the money gain from refusing is small unless loss severity is high or margins are thin.
2. Out of time the line does slightly harm (-0.01% of exposure in 2019 and 2022 at base loss): the PD is over-predicted by about 1.4x (see the final exam), so the line refuses loans that would have been fine, and the actual losses of those years are small. A single line chosen on a pooled validation set that includes the 2008 crisis does not transfer to calm years: the line should depend on the regime (macro overlay) or be tied to a recalibrated PD.
3. The score has more value for pricing and provisioning than for accept/refuse: expected loss by risk band is reasonably matched in the middle bands (ratio 1.02-1.04 for bands 6-7), over-predicted in the safest bands (0.79-2.84, tiny amounts) and slightly under-predicted in the top bands (0.75-0.88).
4. The assumed base loss (10%) gives an expected loss of about 0.2% of exposure (2% x 10%), while the realised loss in the in-time data is 0.65%: the in-time period contains the 2008 crisis (loss per flagged loan 20%). The base loss is an assumption and is shown against the measured values; the grid covers both.
5. Limits: margin is illustrative (no margin data in the files); flagged loans earn no margin; EAD is the original amount; losses are over the whole life of loans flagged within 24 months; 2019 and 2022 realised losses are still incomplete.

## 2026-10-10: reason codes, SHAP agreement, and a flaw found in the model (super_conforming)

Code: `credit/models/reasons.py`, `credit/models/explain.py`, `credit/models/explain_report.py`; config: `config/reason_codes.yaml` (fixed human-written sentences, one code per feature; never generated by a language model); tests: `tests/test_reasons.py` (67 tests pass). Results: `results/explain_report.json`. A scorecard is additive, so "points lost per feature = best band of the feature minus the loan's band" is an exact explanation. A reason is shown only if the loss is >= 5 points, at most 4 per loan; a feature without an approved sentence raises an error (never skipped or improvised).

**Flaw found (after the final exam).** The first run showed "Loan size is above the standard conforming limit" as the first reason for 73% of loans, also for loans whose answer was no. Cause: `super_conforming` only exists for loans after October 2008 (Y for 59 of 49,712 loans of the 2008 sample, 2-5% of later vintages), so in these data N mostly means "crisis-era loan": an era proxy like the raw interest rate. It passed my IV screen only narrowly (0.055 vs the 0.05 threshold). The frozen exam models contain it. Decisions: (1) the exam numbers are NOT changed and nothing is tuned on them; (2) the feature is marked `reportable: false` in the reason codes so it is never shown to an applicant; (3) a model v2 without the feature (and a review of other era-dependent features) is a NEW, labelled experiment, to be evaluated on validation and then on FRESH vintages not yet looked at (the current test splits are already used); (4) the flaw goes into the model card and README limitations. Lesson: an IV screen does not detect an era proxy; every feature needs a "does this exist in every era?" check.

**SHAP vs scorecard (2,000 validation loans, `super_conforming` excluded from both).** The scorecard's first reason is among XGBoost's top-3 SHAP risk features for 74% of loans; its top-3 reasons overlap 53% with XGBoost's top-3 (45% for the first reason exactly). Rankings by importance agree on the leaders: credit_score (IV 1.29; mean |SHAP| 0.87), then dti, rate_spread, orig_term, cltv, channel; XGBoost also uses n_borrowers (#2 by SHAP, 0.41), purpose and orig_upb, which the scorecard dropped (IV < 0.05 or not selected). Most common first reasons: credit_score 753, orig_term 468, cltv 342, dti 170, state 136 (of 1,996 loans with a reason; loans with no material loss get no reason).

**Open point for the fairness review.** `state` appears as a reportable reason for 136 loans; geography can proxy for protected characteristics. To be reviewed with the fairness slices; candidate to make non-reportable or to remove.

## 2026-10-10: fairness slices (scorecard; line = approve if PD <= 0.1471)

Code: `credit/models/fairness.py`; tests: `tests/test_fairness.py` (72 tests pass); results: `results/fairness_report.md|json` (validation, and the 2019 + 2022 exams pooled as a post-exam diagnostic). **Limits first:** Freddie Mac has no sex, race or age, so no protected characteristic can be tested; only groups in the file are compared (first-time buyer, occupancy, purpose, property type, channel, state). This is a report of differences, NOT a legal fairness certification. Groups under 500 loans are not reported; calibration intervals need >= 30 defaults.

**Findings.**
1. The classic four-fifths rule on approval rates flags nothing (all ratios >= 0.95) but is uninformative here: 97-99% of everyone is approved, so the ratio cannot fall below 0.8. The refusal-rate ratio (group refusal rate / lowest group, floored at 0.1%) shows what it hides. On validation: Florida refused 9.8% (x14), channel T (TPO not specified) 16.6% (x20) and broker channel 4.3% (x5) against 0.8% for retail. Part of this is risk-driven (those groups default more: FL 5.22%, channel T 7.49%, B 3.54% in validation).
2. In later years the over-prediction is uneven across groups (predicted/observed, 2019+2022 pooled, 95% interval): overall about 1.4; first-time buyers 1.69 (1.53-1.88) vs repeat buyers 1.35 (1.27-1.45); purchase loans 1.72 vs cash-out refinance 1.12; investor occupancy 2.70 (2.14-3.66; only 56 defaults); broker channel 2.04 vs retail 1.27; Florida 2.18 (1.87-2.61) with 4.5% of its loans refused (x42 vs Ohio) although its default rate is only 1.87%. Validation shows the same direction for first-time buyers (1.48, 1.15-2.09).
3. Likely cause for geography: `state` captured the 2008 housing-bust map (Florida, Arizona, Michigan...), which does not hold in later years, so the model over-penalises the same states. `state` is therefore an era-and-geography proxy like `rate` and `super_conforming`: recommended to drop or to review in model v2, and it must not be a reportable reason until reviewed. First-time buyer is a plausible proxy for age or wealth: it is not a model input, but it is systematically over-predicted, so the model's errors fall more on that group.
4. Consequence for use: the economic line refuses few loans (1-3%), so refusal differences are small in absolute terms, but any use of the PD for pricing or provisioning would carry these group biases. A per-group recalibration check belongs to monitoring (Phase 3).

## 2026-10-11: model v2 protocol, step 1-2 (fresh vintages downloaded and staged; labels deliberately unseen)

**Protocol (agreed with the owner before any v2 work).** Model v2 fixes the v1 flaws and is judged on FRESH vintages. v1 stays frozen (its exam numbers are the record). Three arms are compared: v1 (frozen), v1b (v1 features, retrained on the new data with equal weight per vintage), v2 (fixed features, same new data). v1b vs v1 isolates the effect of the training data; v2 vs v1b isolates the effect of the feature fixes. Planned changes: remove `state` and `super_conforming`; replace `n_borrowers` (its definition changed in 2018Q2 according to the Freddie Mac guide: before 2018Q2 only "1" or "more than 1") by a yes/no "several borrowers"; review every feature for era dependence with leave-one-vintage-out checks on the five known vintages only. v2 may learn from all five known vintages (2008, 2012, 2016, 2019, 2022). Success rules and predictions will be written and committed BEFORE the exam (pre-registration), then a freeze, then one run with paired-bootstrap intervals.

**Fresh vintages (the v2 exam).** Samples downloaded by the owner: 2010 (post-crisis), 2014 (calm), 2018 (just before COVID), 2023 (the real future: loans originated in 2023 have 24+ months of history in the data that ends in March 2026). Files are in `data/raw/freddie/` (git-ignored). Raw Parquet in `data/interim/raw/`. Staged into a SEPARATE folder `data/interim/stg_fresh/` so that they cannot enter the v1 features by accident. Only structural counts were printed; the default counts of these vintages (written inside `report_<year>.json` and the label files) have NOT been looked at and must stay unread until the freeze.

| Vintage | Loans | Relief refinance | Seasoned/modified | Not observable for 24 months |
|---|---|---|---|---|
| 2010 | 50,000 | 14,641 | 55 | 0 |
| 2014 | 50,000 | 7,307 | 127 | 0 |
| 2018 | 50,000 | 511 | 112 | 0 |
| 2023 | 50,000 | 0 | 52 | 144 |

**Guard corrected.** The 2010 sample was stopped by the staging check "orig_term outside 60-480 months": one real loan has a 513-month term (first payment May 2010, maturity January 2053). The 480 limit was my own assumption (a 40-year maximum), not a rule of the data. The limit is now 60-600 months, with a test for both sides (513 passes, 900 fails). A guard that rejects real data means the assumption was wrong; the check stays.

## 2026-10-11: v2 step 3, era-stability review and leave-one-vintage-out (five known vintages only; fresh vintages not read)

Code: `credit/models/era_review.py` (+ `tests/test_era_review.py`: a made-up era proxy is exposed, a genuine feature is kept, a vanishing level and a direction flip are detected); the scorecard now accepts a chosen feature list (defaults unchanged). Results: `results/v2_feature_review.json`. Method: bands fitted on all five vintages pooled; for each feature and vintage the information value INSIDE that vintage minus the IV of a randomly shuffled copy of the feature (noise floor); `keep ratio` = median within-vintage excess / pooled IV.

| Feature | pooled IV | median within-vintage excess IV | min | keep ratio | notes |
|---|---|---|---|---|---|
| credit_score | 0.978 | 0.842 | 0.444 | 0.86 | real in every era |
| dti | 0.375 | 0.214 | 0.120 | 0.57 | |
| rate_spread | 0.328 | 0.180 | 0.045 | 0.55 | |
| channel | 0.271 | 0.040 | 0.007 | **0.15** | mostly era; levels B, C, T change a lot between vintages |
| n_borrowers | 0.194 | 0.177 | 0.098 | 0.91 | real, but definition changed in 2018Q2 |
| orig_term | 0.163 | 0.059 | 0.009 | 0.36 | partly era |
| cltv / ltv | 0.147 / 0.139 | 0.089 / 0.109 | 0.020 / 0.018 | 0.61 / 0.78 | |
| state | 0.099 | 0.115 | 0.013 | 1.16 | carries information inside each era (NOT a pure era proxy) |
| mi_pct | 0.069 | 0.136 | 0.010 | 1.99 | real, masked when pooling |
| purpose | 0.047 | 0.077 | 0.003 | 1.65 | real, masked when pooling (dropped by the v1 pooled IV rule) |
| property_type | 0.028 | 0.010 | 0.001 | 0.35 | weak |
| super_conforming | 0.011 | -0.0002 | -0.012 | **-0.01** | NO information inside any era: pure era flag |
| orig_upb | 0.006 | 0.025 | 0.004 | 4.2 | weak, direction flips across vintages |
| occupancy, ppm_flag, first_time_homebuyer, n_units | ~0 | <= 0.025 | | | nothing |

**Leave-one-vintage-out (scorecard trained on four vintages, Gini and predicted/observed on the held-out one).**
| Feature set | 2008 | 2012 | 2016 | 2019 | 2022 | mean Gini |
|---|---|---|---|---|---|---|
| A v1 features | 0.620 / 0.25 | 0.633 / 2.92 | 0.658 / 2.43 | 0.471 / 1.20 | 0.523 / 1.36 | 0.581 |
| D minus state and super_conforming | 0.614 / 0.25 | 0.642 / 3.01 | 0.646 / 2.38 | 0.461 / 1.20 | 0.529 / 1.33 | 0.579 |
| H D minus channel (several_borrowers) | 0.614 / 0.25 | 0.644 / 3.26 | 0.638 / 2.67 | 0.462 / 1.37 | 0.528 / 1.52 | 0.577 |
| G core only (6 features) | 0.608 / 0.25 | 0.633 / 3.57 | 0.642 / 2.79 | 0.460 / 1.38 | 0.529 / 1.49 | 0.575 |

**Findings (they correct earlier statements).**
1. Removing `state`, `super_conforming` and `channel` costs at most 0.005 Gini (noise): dropping them is free in ranking power.
2. `super_conforming` and `channel` are era proxies (no or little information inside an era). **`state` is NOT an era proxy by this test** (information inside every vintage, keep ratio 1.16): my earlier statement that it "captured only the 2008 housing-bust map" was too strong. The reasons to drop it are different: its removal costs nothing, it is a geography stand-in (fairness), and it drives the Florida over-prediction seen in later years.
3. `channel` was the 4th strongest v1 feature (IV 0.42) and is mostly an era effect: another case where the pooled IV screen misled. Selection by within-era information is the right rule: the pooled IV dropped `purpose`, `mi_pct`-type features that are informative inside eras.
4. **Hypothesis (a) of the exam findings is not supported.** The weak ranking of 2019 (Gini 0.46-0.47) and 2022 (0.52-0.53) persists when the held-out vintage is predicted by models trained on the other four vintages, which include the other recent vintage and have different 2008 weight. So the weak out-of-time ranking is not caused by the 2008 dominance of the training defaults; it looks intrinsic (defaults in calm years are harder to predict from day-one data).
5. The LEVEL is a macro effect that no feature choice fixes: predicted/observed on the held-out vintage ranges from 0.25 (2008 predicted by calm-year models) to 3.0-3.6 (2012, 2016 predicted by models that saw 2008). Equal weighting of vintages is therefore not expected to fix the level.
6. `several_borrowers` gives the same results as `n_borrowers` (the scorecard bands n_borrowers into 1 versus 2 or more anyway); it is still safer because the definition changed in 2018Q2.

## 2026-10-11: MODEL v2 EXAM (fresh vintages 2010, 2014, 2018, 2023; run once; frozen at commit ee7f191, manifest committed in 1b78c97 before the run)

Pre-registration: `docs/v2_preregistration.md` (arms, features, predictions and success rules written and committed before any fresh label was opened; the exam refused to run before the freeze, verified). Code: `credit/models/v2_exam.py`, `credit/freddie/fresh.py` (labels of the fresh table are locked behind `allow_exam`; a test shows that the fresh builder reproduces the development `rate_spread` exactly on the known vintages). Results: `results/v2_exam.json|md`, `docs/v2_exam.png`. Paired bootstrap, 1000 resamples, seed 20261011.

| Vintage | loans / defaults / real rate | Gini v1 | Gini v1b | Gini v2 | predicted/observed v1 / v1b / v2 |
|---|---|---|---|---|---|
| 2010 | 35,304 / 151 / 0.43% | 0.598 | 0.616 | **0.628** | 2.04 / 1.80 / 2.03 |
| 2014 | 42,566 / 206 / 0.48% | 0.580 | 0.586 | **0.599** | 2.73 / 2.44 / 2.64 |
| 2018 | 49,377 / 420 / 0.85% | 0.523 | 0.543 | **0.543** | 2.22 / 1.91 / 2.11 |
| 2023 | 49,834 / 662 / 1.33% | 0.570 | 0.585 | **0.595** | 1.60 / 1.33 / 1.41 |

Mean Gini difference over the four vintages (95% paired-bootstrap interval): **v2 minus v1 +0.024 (+0.013 to +0.035)**; v2 minus v1b +0.009 (+0.002 to +0.017); v1b minus v1 +0.014 (+0.006 to +0.022). So of the +0.024, about +0.014 comes from retraining on more and more varied data and about +0.009 from the feature changes.

**Verdict by the pre-registered rules.** R1 (non-inferior: lower bound above -0.03): yes; v2 is even superior (lower bound above 0). R2 (smaller group spread than v1 in at least 4 of 6 slice variables): yes, but only just, exactly 4 (occupancy 1.85 -> 1.60, purpose 1.33 -> 1.11, channel 1.72 -> 1.13, state 2.20 -> 2.17); first-time buyer got worse (1.02 -> 1.15) and property type slightly worse (3.04 -> 3.20). **v2 is adopted as the recommended model; v1 stays in the record.**

**Predictions vs outcome.** P1 (Gini 0.45-0.70 on 2010/2014/2018, 0.40-0.60 on 2023): right. P2 (mean difference within +/-0.03, "superior" under 25%): the difference is inside the range but it was statistically superior, which I had rated unlikely. P3 (|v1b - v1| < 0.03): right (+0.014, but significant). P4 (level): right for 2014 (2.4-2.7), 2018 (1.9-2.2) and 2023 (1.3-1.6); **wrong for 2010** (I said 0.5-1.6; observed 1.8-2.0). v2 within 0.25 of v1b: right. P5 (>= 4 of 6 variables): right, with no margin.

**Findings.**
1. Ranking on fresh years is clearly useful: Gini 0.52-0.63. The 2023 vintage, the real future, scores 0.57-0.60, better than the 0.52 of the 2022 vintage in the v1 exam: the weak 2019/2022 ranking is not a general "future drops" law. With 151 to 662 defaults per vintage the intervals are wide (for example 2010: 0.56-0.70 for v2).
2. The level is wrong in every fresh vintage: the models predict 1.3 to 2.7 times the real default rate (real rates 0.43%, 0.48%, 0.85%, 1.33% against a training mix of about 2%). This confirms on four new years that the scorecard is a through-the-cycle model and that the level needs a macro overlay or a per-period recalibration. v2 does not change that (within 0.25 of v1b).
3. The geographic pattern in group over-prediction persists without the state feature (state spread 2.20 -> 2.17): it does not come from the feature itself, so removing `state` is not enough to remove it; other features correlate with geography. First-time buyers are slightly worse off in v2.
4. Honest limits: R2 passed with no margin; fairness here covers only groups present in the data; 2010 has only 151 defaults.

**Follow-ups done after the exam (the exam numbers were not touched).** (a) `scripts/export_v2_scorecard.py` exports the adopted v2 scorecard (`results/scorecard_v2_table.csv`, `scorecard_v2_iv.csv`; 9 features; no sign violations; score range 486-738 on the development rows). (b) Reason sentences R12 (purpose) and R13 (several borrowers) added to `config/reason_codes.yaml`. (c) Flaw found while exporting: a band never seen in training (unseen category, never-observed missing) got a very negative WoE (smoothing: ln(bad total / good total), about -3.9, i.e. -38 points), so an unusual applicant would have been punished only for being unusual. Now such a band is neutral (WoE 0); test added. Impact on the exam: 1 of 177,081 fresh loans (v1 arm, `mi_pct`) fell in such a band, none for v1b and v2, so the results stand.

**Next experiments (new data needed, not tuning).** Per-period or macro recalibration of the level; a calibration check on 2019/2022-type data used as an anchor; monitoring of predicted vs observed by period and group (Phase 3).

## 2026-10-11: CI (GitHub Actions)

File: `.github/workflows/ci.yml`. On every push and pull request: checkout, Python 3.13 with the pinned libraries (`requirements-dev.txt`, pip cache), `ruff check .`, `pytest -q`. Safety choices: `permissions: contents: read` (the workflow can only read the code), no secrets, no data (tests use made-up data; the two tests that need the real Freddie Mac files skip themselves when the files are absent), `concurrency` cancels superseded runs, 20-minute timeout. Actions are referenced by major version tags (`@v4`, `@v5`); pinning them to commit hashes would be stricter against supply-chain attacks and is a later hardening step.

**Rehearsal before the first run.** A fresh clone of the tracked files only (no data, no virtual environment, no results folders) gave 89 passed and 2 skipped, which caught nothing but confirmed that the tests do not depend on local files. `pyarrow` (used by pandas for Parquet in a test) was only installed indirectly through streamlit, so it was pinned explicitly (`pyarrow==25.0.1`).

**Run 1 (commit 2811682, branch v2-prep):** success in about 81 seconds (all nine steps green).
**Self-test of the guard:** a deliberately failing test was pushed to a throwaway branch `ci-selftest`: the run ended in **failure at the Tests step** (ruff passed, pytest failed), proving that CI turns red when something is broken. The branch was then deleted (local and remote). A guard that has never failed proves nothing.

**Discovery.** The repository is **public** (the GitHub API answers without login), which is why Actions are free and unlimited here. A scan of the tracked files found no AWS account number, email, key or password, and no data files except the public German Credit dataset. Rules from now on: never commit anything under `data/`, never commit a key; the `.gitignore` and the guards exist for that. The README status badge shows the result of the latest run on `v2-prep`. A stale "platform on GCP" sentence in the README intro was corrected to AWS.

## 2026-10-11: model file and file-only scorer (step 3.2)

Code: `credit/serving/model_file.py` (loads, validates and scores; **standard library only**, checked by a test that parses its imports), `credit/serving/export.py` (training side, turns a fitted scorecard into the file); tests: `tests/test_model_file.py` (12 tests). Artifact: `models/scorecard_v2.json` (6.9 KB, model_id `b3069001d62e`, committed; it contains only band edges, categories, points, fixed reason sentences, scaling and known limits: aggregate numbers, no loan data, compatible with the Freddie Mac terms).

**What the file is.** The adopted v2 scorecard (9 features, 50 bands). A loan's score is the sum of the points of the bands it falls in; probability of default = 1 / (1 + e^((score - offset) / factor)) with factor = 20 / ln 2 = 28.854 and offset = 600 - factor x ln 50 = 487.123 (the scaling convention, an assumption in `config/assumptions.yaml`). Points alone are enough, so the scorer needs no scikit-learn, numpy or training data. Reasons use the stored best points per feature and the stored fixed sentences. A `known_limits` list travels with the model (through-the-cycle level 1.4-2.6x too high in calm years, flagged serious delinquency not loss, prime US mortgages only, no protected attributes, rate_spread needs a reliable reference rate).

**Verification.** (1) On made-up data with missing values, unseen categories and values exactly on a band edge, the file scorer equals the scikit-learn scorecard (scores within 1e-9, probabilities within 1e-12) and its reasons equal `credit.models.reasons` exactly. (2) On 20,000 real loans from the five known vintages, the committed file reproduces a freshly fitted v2 scorecard to the same tolerance. (3) Validation rejects a missing key, a changed schema version, unsorted edges, a wrong number of points and non-finite points. (4) The scorer rejects unknown fields, missing fields (a value must be given or null), numbers sent as text, booleans, infinities and non-text categories. (5) The model id is a hash of what the model computes (scaling, order, features), unchanged by descriptive metadata and changed by any change of a point. (6) A golden loan (credit score 700, DTI 44, LTV 85, CLTV 85, rate spread 0.55, one borrower, MI 25, 30-year term, purchase) must score 553.3 points (+/-0.2) and 9.17% (+/-0.06 pp) with top reasons credit_score (-45.8), cltv (-35.6), dti (-32.5): if this test fails the model changed and that must be a deliberate, versioned decision.

**Design points for the API (step 3.3).** The API will take the loan facts directly (no feature store), with `interest_rate` and a `reference_rate` so that the spread can be computed from a reliable reference; it will reject unknown fields and out-of-range values; it will not decide approve or refuse (the cut-off logic stays outside) and will carry the known limits in `/model-info`.

## 2026-10-11: the scoring API (step 3.3)

Code: `service/schemas.py` (strict input and output shapes), `service/main.py` (app factory `create_app`, four endpoints); tests: `tests/test_api.py` (34 cases). Libraries pinned: fastapi 0.143.0, pydantic 2.14.0, starlette 1.7.0, uvicorn 0.54.0 (runtime), httpx 0.28.1 (tests only). Run: `uvicorn service.main:create_app --factory --reload`, then open `/docs`.

**Endpoints.** `GET /health` (alive, model id and version), `GET /model-info` (scale, inputs and their bands, training ranges, known limits), `POST /score` (points and probability of default), `POST /explain` (same plus the top reasons as fixed sentences, `top_k` 1-9, default 4).

**Choices.** (1) Strict input: unknown fields rejected, no type guessing (`"700"` is refused), valid ranges taken from the data dictionary (wider than the training ranges, so a valid loan is never refused), every field required but nullable (null = unknown, the model has a band for it). (2) Loans outside the *training* range are scored but listed in `outside_training_range`, with a standing caution about the through-the-cycle level (1.4-2.6x too high in calm years). (3) The API takes `interest_rate` and `reference_rate` and computes `rate_spread` itself; the caller must supply a reliable reference. (4) No approve/refuse decision, no training, no storage or logging of loan data. (5) The model file is loaded and validated at start-up; a missing or damaged file stops the service from starting (tested). (6) The `training_ranges` field was added to the model file (metadata only: model id unchanged, `b3069001d62e`).

**Bug found by a test.** Sending the non-standard JSON value `Infinity` made the *error response itself* crash (FastAPI echoes the bad value back in its 422 answer, and infinity cannot be encoded), which would have been a server error (500) instead of a clean refusal. Fixed with a custom validation-error handler that reports field, problem and type but never echoes the value; the test `test_bad_values_rejected[dti-inf]` guards it.

**Verification.** API score equals the file scorer exactly on several loans (incl. missing values); golden loan (700, 44, 85, 85, spread 0.55, one borrower, MI 25, 360 months, purchase) gives 553.30 points and 9.17%, top reasons credit_score, cltv, dti; a live uvicorn run answered /health, /score and a 422 as expected. Full suite: 137 passed. Known remark: starlette warns that `httpx` in its test client is deprecated in favour of `httpx2` (tests only; to revisit).

## 2026-10-11: the pipeline (step 3.4, Dagster)

Code: `pipeline/` (`steps.py` plain functions, `checks.py` file checks, `freshness.py` skip rule, `definitions.py` the Dagster assets and checks, `run.py` one-command runner), `workspace.yaml`; tests: `tests/test_pipeline.py` (17 cases, made-up loans, no Freddie Mac data needed). Libraries pinned: dagster 1.13.26, dagster-webserver 1.13.26 (installing them downgraded the transitive `protobuf` 7.36.2 -> 6.33.6; `pip check` is clean and streamlit, shap and xgboost still import).

**Graph.** `freddie_zips` (external, downloaded by hand) -> `raw_parquet` -> `staging_dev` / `staging_fresh` -> `features_dev` / `features_fresh`; `features_dev` -> `scorecard_v2`. Each of the six built assets has a BLOCKING check (if it fails, what depends on it does not run): files present and not empty; staging data checks re-run on the written files (keys, ranges, leakage, label sanity); features checks; fresh checks; model file valid and the golden loan still scores 553.3 +/- 0.2 points. The pipeline only WRAPS the code that already existed: it adds order, skipping and checks, no new maths.

**Skip rule.** A step re-runs if an output is missing or any input (data file or the code file that defines the step) is newer than the oldest output; `PIPELINE_FULL=1` / `--full` forces everything. The rule can only err on the safe side (an extra rebuild). A missing input is an error, never a silent skip.

**Safeguards kept.** (1) The model asset depends on `features_dev` only: a test proves the fresh vintages are not among its ancestors. (2) Staging reports of the fresh vintages contain default counts (locked until the exam): the pipeline only ever shows structural counts (`loans`, `relief_refi`, `seasoned_or_modified`, `not_observable_24m`), tested. (3) The exam scripts (`final_exam`, `v2_exam`) are deliberately NOT in the pipeline.

**Verification on the real data.** Before/after fingerprints (row count + md5 of every row, ordered by loan): development features 229,419 rows `4eb557f1...`, fresh features 177,081 rows `e805ad65...`, model_id `b3069001d62e`. After an incremental run AND after a `--full` rebuild from the 9 zips (5 min 1 s, all 6 assets rebuilt, 6 checks passed) all three were IDENTICAL: the whole chain is reproducible from the raw files. A second run with nothing changed reuses all six steps (about 50 s, mostly the checks).

**Problems found.** (a) `staging.stage_year` has `raw_dir` as a default argument frozen at import time, so a test that redirected the path silently read the real 2016 file (it only wrote to the temp folder). The step now passes the path explicitly; a test would catch a regression (it expects the 60 made-up loans). (b) The features and fresh steps could "reuse" an old result when their staged folder was empty; they now raise. (c) On Windows the Dagster CLI (Click) expands a bare `*` into file names, so `--select '*'` fails; use `raw_parquet*`. (d) `workspace.yaml` needs `working_directory: .` or the module `pipeline` is not found. (e) Dagster starts one process per step by default: a no-op run took 255 s through the CLI; the in-process executor brings it to 63 s. (f) `dagster dev` answers on its port and shows the 7 assets with the right dependencies (checked by GraphQL).

**Local history.** Run history lives in `.dagster_home/` (git-ignored). Set `DAGSTER_HOME` to that folder before `dagster dev` or it is lost when the process stops (an empty `dagster.yaml` is not needed; Dagster only prints a notice).

## 2026-10-11: what the cloud is for (decision after steps 3.2 to 3.4)

**Question.** With the data staying on the owner's computer so far, what is AWS for? Judged first on engineering value and cost, then on story and CV value, always keeping the framing honest. The owner's reading of the data terms is that private cloud storage is allowed; the decision below does not depend on that point except for the S3 data lake.

**Decisions (ranked by value).**
1. **Honest-evaluation workflow** is the core of the story (already built: freeze, pre-registration, exam on fresh vintages, leakage guards, documented 1.4-2.6x over-prediction in calm years). Keep saying it.
2. **Scoring API on AWS Lambda** (container image, Function URL), deployed by GitHub Actions through **OIDC** (no stored keys), least-privilege IAM, a budget alert and a cap on concurrent executions (a budget alert only warns; the cap limits spend). Cold-start time is measured and reported, not hidden.
3. **Data in the owner's private S3** (Parquet, partitioned by vintage) so the platform reads from a cloud data lake. Stated as a design choice, not as forced by data size.
4. **Athena, scoped.** Earlier today the answer was "no" (about 24.7 million monthly performance rows run in seconds in DuckDB, so Athena is not needed; corrected on 2026-10-13 after counting: the figure first written here was 15 million, from memory). Changed to a scoped yes for story value, on one condition: it is never claimed to be necessary. Its honest value is the **parity test** (same SQL, identical numbers in DuckDB and Athena) and the monitoring summaries, with a per-query scan limit set on the workgroup.
5. **Scheduled retraining becomes ONE recorded run of the pipeline container on ECS Fargate**, then the resources are deleted. Labelled an infrastructure demonstration. Not "continuous retraining": the data never changes, so retraining would give the same model.
6. **Monitoring (Evidently) with simulated months** taken from past vintages and labelled as simulated; includes the recalibration experiment for the calm-year over-prediction.
7. **Credit-memo agent (Phase 4)**: read-only, recommendation computed by code, validator checks every number. Needs an LLM API budget decision from the owner when we get there.
8. **Dagster stays local.** No server running 24/7.
9. **Model file baked into the container image** (7 KB), not loaded from S3 at start-up: the image is the version, nothing can drift between code and model, `/health` shows the model id. S3 keeps an archive of each model version.

**Changed from the sheet v1.3.** The 5,000-applicant snapshot inside the API is dropped (the API takes the loan facts directly); scheduled retraining is reduced to one recorded demonstration run; Athena is scoped (parity + monitoring), not the main query engine. The sheet is now v1.4.

**What would hurt credibility (avoid).** Calling it continuous retraining; saying Athena was required for this data size; showing a high Gini without the freeze, the exam and the failure mode; presenting it as a production lending product.

**Draft CV lines (numbers stay TBD until measured; nothing invented).** (a) End-to-end mortgage credit-risk platform on Freddie Mac data (450,000 loans, 9 vintage samples): reproducible Dagster pipeline with blocking data checks, WoE scorecard vs XGBoost, Gini TBD, calibration TBD. (b) Pre-registered, frozen evaluation on 4 unseen vintages (177,081 loans): documented a 1.4-2.6x over-prediction in calm years and tested recalibration (result TBD). (c) Scoring API (FastAPI, Docker, AWS Lambda) with CI/CD through GitHub OIDC (no stored keys), strict input validation and a golden-loan regression test.

**Order from here.** 3.5 monitoring, 3.6 S3 + Athena parity + Lambda deployment + the single ECS run, Phase 4 memo agent, Phase 5 README, demo video, risk register. AWS Free plan clock: record the demo and results early.

## 2026-10-11: monitoring and the level-recalibration experiment (step 3.5)

Pre-registration committed first (`4098ffe`, `docs/monitoring_preregistration.md` + `config/monitoring.yaml`), code committed second (`13ad66f`), results third. Code: `credit/monitoring/` (`scoring.py` vectorized scorer proven equal to the file scorer, `psi.py`, `drift.py`, `simulate.py`, `recalibration.py`, `report.py`); tests: `tests/test_monitoring.py` (25) plus 5 monitoring-check tests in `tests/test_pipeline.py`. Results: `results/monitoring_report.json` and `.md`, chart `docs/monitoring.png`. `report.main()` refuses to run unless the pre-registration and the thresholds file are committed and unmodified, and writes that commit into the result. New Dagster asset `monitoring_report` (depends on features_dev, features_fresh, scorecard_v2) with a blocking check: the monitors' own self-test must still pass and the report must be about the current model.

**Part A, real drift and level (observed / predicted default rate).** 2008: 1.80 (under-predicted, the crisis); every other vintage is over-predicted: 2010 0.49, 2012 0.35, 2014 0.38, 2016 0.43, 2018 0.47 (all level ALERTS), 2019 0.77, 2022 0.71, 2023 0.71 (warnings). The out-of-sample ratios agree with the exam (1.4 to 2.6 times over-prediction). The through-the-cycle level is anchored by 2008. Gini per vintage 0.47 to 0.66 (lowest 2019 at 0.472, in-sample; out-of-sample 0.543 to 0.628). Counts are small for 2010 (151 defaults) and 2012 (73): the ratio carries about 8% and 12% sampling noise, which cannot change these conclusions. Score PSI alerts only for 2010 (0.264) and 2012 (0.454); the cause is the input mix (purpose CSI 0.311 in 2012, the refinance wave), not worse ranking (Gini 0.642). Lesson: a drift alarm is not a failure alarm; the level ratio and Gini say whether the model fails.

**Part B, simulated drills (all labelled SIMULATED).** Control clean (score PSI 0.003, level ratio 0.93): R-M1 true. All 7 expected alerts caught (S1, S3, S4, S5, S6, S7 by the per-input CSI; S9 by the level ratio): R-M2 true. Findings: (1) the score PSI alone caught NONE of S1 to S7 at alert level (maximum 0.122): the per-input CSI is what works, never monitor only the score; (2) S2 (credit score -10) and S8 (defaults x1.25, level ratio 1.16 with about 250 defaults in a 10,000-loan batch) were NOT detected: the monitors have a sensitivity floor, reported, not tuned away; (3) S1 and S3 also raised the level alert only because the simulation changes the inputs but not the outcomes; (4) S4 is detectable only because the real baseline of missing credit scores is 0.026%: with a 1% baseline the PSI of that shift would be 0.247, just under the alert line (a documented blind spot, tested).

**Part C, can history alone repair the level? Verdict: not as an automatic fix.** Arm A static mean error 0.653; arm B (last known vintage) 0.449 (-31%), arm C (pooled known vintages) 0.836 (worse). R-C1: B passes the mean (+31%) and the count (5 of 7 targets) but fails the guard: worst worsening +0.65 (2012, where the only known vintage is the 2008 crisis) and +0.33 (2019), limit 0.30. C fails all three. R-C2 true (Gini unchanged by a constant shift). Reading (an observation, not a new rule): last-vintage recalibration cut the error a lot in stable regimes (2014 0.97 to 0.26, 2016 0.85 to 0.20, 2018 0.75 to 0.21, 2022 0.34 to 0.09, 2023 0.35 to 0.09) and hurt at turning points (2012, 2019), which is exactly where a correction matters most. Even a pass would only be "recommended, not proven": the nine vintages are all used as targets, so there is no untouched holdout. A macro signal (unemployment, house prices) would be the next experiment; it needs outside data and a new pre-registration.

**Predictions: 11 of 13 hit.** Misses: A2 (I expected the largest score PSI in 2008, 2010 or 2023; it was 2012: I did not foresee the refinance wave), C2 (I expected arm C to improve 2018; it did not). Thresholds were not changed after seeing results.

**Problems found along the way.** (a) My first synthetic data had 1% missing scores and the S4 drill was missed in the test; measuring the real baseline (0.026%) showed the drill is detectable in reality and exposed the blind spot above (the test data now mirrors the real baseline, and the blind spot has its own test). (b) The model pipeline step watched every file in `config/`, so adding `monitoring.yaml` rebuilt the model for nothing; it now watches only `assumptions.yaml` and `reason_codes.yaml`. (c) Rebuilding the model rewrites `exported_on` in the model file (metadata only; the model id `b3069001d62e` is unchanged).

**What it means for the story.** The platform does not only score loans, it knows when it is wrong: it flags the calm-year level problem on its own, its alarms were tested with drills, two blind spots are documented, and a tempting fix (recalibrate from history) was tested honestly and rejected by a rule written beforehand.

## 2026-10-12: exploratory check, what if the 2008 vintage is left out of training?

Question from the owner: the model over-predicts in calm years because the 2008 crisis is in its training data, so why not skip 2008? Reasoning given first (2008 holds 2,219 of the 3,902 development defaults, about 57%; leaving it out lowers the training default rate from 1.70% to about 0.94%; it would blind the model to the one crisis it has seen; the exam years contain no crisis, so dropping it would be rewarded by the exam). Then tested, clearly labelled **exploratory, not pre-registered, no decision depends on it**: `scripts/exploratory_without_2008.py` refits the v2 scorecard (same method and settings) on the development rows without 2008 and compares both models on all nine vintages. Results: `results/exploratory_without_2008.json` and `.md`. Predictions were written in the script before running. Sanity check: refitting on all development rows reproduces the committed model id `b3069001d62e`. The committed model is untouched.

**Results.** Training default rate 1.70% with 2008, 0.94% without (as computed beforehand). Observed/predicted ratio, committed model vs refit without 2008: 2008 1.80 vs 4.03; 2010 0.49 vs 0.84; 2012 0.35 vs 0.51; 2014 0.38 vs 0.59; 2016 0.43 vs 0.68; 2018 0.47 vs 0.78; 2019 0.77 vs 1.26; 2022 0.71 vs 1.14; 2023 0.71 vs 1.19. Without 2008 the calm years are much closer to reality, the late years (2019, 2022, 2023) flip to mild UNDER-prediction, and the crisis is under-predicted four times (predicted 1.11% against 4.46% observed).

**The honest part.** By the plain average the refit looks better: mean level error over the nine vintages 0.652 to 0.439, and total miss in number of defaults 3,210 to 2,490, because eight of the nine vintages are calm. The average hides the cost of the crisis year (miss of 988 defaults rising to 1,668). Which model is "right" depends on the purpose: a point-in-time view for calm periods, or a through-the-cycle view that must survive a downturn (capital, stress testing, provisioning). The committed model keeps the through-the-cycle choice, stated in `/model-info`.

**Ranking.** Gini moves a little: out-of-sample calm vintages are slightly better without 2008 (2014 +0.028, 2016 +0.023, 2018 +0.006, 2022 +0.013, 2023 +0.004, 2012 +0.013, 2010 -0.011); on 2008 itself Gini falls from 0.659 to 0.615 (not a clean comparison: 2008 is in-sample for the committed model and out-of-sample for the refit). The two scores correlate at 0.924 (Spearman), so 2008 is not irrelevant to the ranking but does not dominate it either (consistent with the earlier leave-one-vintage-out result).

**Predictions: 4 of 5 hit.** E1 (2010 to 2018 closer to 1), E2 (2019, 2022, 2023 cross above 1), E3 (2008 ratio at least 2.5), E5 (average error falls, 2008 miss rises) hit. E4 missed: I predicted that ranking barely changes (every Gini difference under 0.02 and a Spearman above 0.95); the largest differences are 0.044 (2008) and 0.028 (2014) and the correlation is 0.924.

**Decision.** Keep the committed model (through-the-cycle). Record the evidence. Possible future design, not built: keep the ranking from this model and expose the LEVEL as a documented "climate" setting (calm, average, crisis) anchored on these measured ratios, driven later by a macro signal (unemployment, house prices), which needs outside data and a new pre-registration. Adding macro variables directly to the scorecard is risky with only nine sample years (about 36 quarters): the model could memorise eras, the same reason raw `int_rate` was removed.

## 2026-10-12: future path for the level problem (not built)

The ranking comes from the loan model; the LEVEL is a macro question, and the data holds only about 9 distinct economies (one per sample year; about 36 quarters, strongly correlated), so fitting macro variables directly into the scorecard risks memorising the eras (the same reason raw `int_rate` was removed). Ordered options for later, each needing its own pre-registration:
1. **Vasicek single-factor dial.** One shared economy factor z and an asset correlation rho map the through-the-cycle PD to a PD for a chosen economy: PD(z) = Phi((Phi^-1(PD) - sqrt(rho) z) / sqrt(1 - rho)). Basel fixes rho at 0.15 for residential mortgages (to verify against the current rule before relying on it). Back-of-envelope with our pooled 1.7%: about 0.3% in a good year (z=+1), 1.1% in an average year, 9.3% in a once-in-a-hundred-years crisis (z=-2.33): untested on our data, and estimating rho from nine yearly numbers would be unstable, so the regulatory value would be used and stated as an assumption.
2. **Current LTV** (original LTV divided by local house-price growth since origination): theory-driven (negative equity drives default) and it varies by state and quarter, which multiplies the number of distinct situations far beyond nine; needs a public house-price index and, for scoring a new loan, a price scenario.
3. A **mixed-effects model** with a vintage effect (shrinkage, honest range for an unknown year) and bank-style **satellite models** (portfolio default rate on unemployment and house prices) once longer histories (full Freddie Mac files since 1999) are available.
No equation creates information that the data does not contain: theory supplies the shape and the uncertainty, assumptions fill the gaps, and they must be written down.

## 2026-10-12: the API container (step 3.6a, local and CI only, nothing created in AWS)

Files: `Dockerfile`, `.dockerignore`, `requirements-service.txt`, `scripts/smoke_test_api.py`, `scripts/expected_image_files.txt`, `tests/test_container.py` (10 tests), three new steps in `.github/workflows/ci.yml` (build, content check, smoke test).

**Design.** Base image `python:3.13-slim-bookworm` (the same Python as CI). The AWS Lambda Web Adapter (v1.1.0, the latest release when checked on 2026-10-12, read from the official GitHub repository) is copied from the public AWS registry: it lets the ordinary web app run inside Lambda with no code change and does nothing elsewhere; readiness is checked on `/health`. `requirements-service.txt` holds 14 fully pinned libraries resolved INSIDE the base image (not on Windows): no pandas, no scikit-learn, no Dagster, so the image is small (222 MB with the Python base) and starts quickly. The four top-level versions must equal those of `requirements.txt` (tested). The image runs as a non-root user (uid 10001).

**What is inside, by construction.** `.dockerignore` is an ALLOW-LIST (`*` first, then six allowed paths), so data, results, tests, `.git` and secrets are never even sent to Docker. The image holds exactly 8 files (`credit/__init__.py`, `credit/serving/__init__.py`, `credit/serving/model_file.py`, `service/` (3 files), `models/scorecard_v2.json`, `requirements-service.txt`); CI compares the real list with `scripts/expected_image_files.txt` and a test derives the same list from the Dockerfile. A test also checks that the API code imports only the standard library and the four service libraries.

**Verification.** Built locally and run in Docker 29.3.1: the smoke test (health with the expected model id `b3069001d62e`; model-info limits; golden loan 553.3 points / 9.17%; reasons start with credit_score; unknown field, text instead of number, out-of-range value, `Infinity` and non-JSON all give 422; no decision field) passed against the running container. The smoke script itself is also proven in the unit tests against a live in-process server, including its failure paths (wrong model id, dead service).

**To remember for 3.6b/3.6c (to verify then).** (1) Recent `docker build` adds an "attestation manifest" (provenance) to the image; AWS Lambda does not accept that format, so the image pushed to ECR must be built with provenance disabled (`--provenance=false`). (2) Pulling the adapter from `public.ecr.aws` is anonymous and can in rare cases be rate limited in CI. (3) The adapter's behaviour inside Lambda (readiness, port) is documented but not yet tested by us: it will be measured in 3.6d (cold start and warm latency).

## 2026-10-12: AWS command line ready, and what the account limits mean (step 3.6b-1, nothing created in AWS)

The owner installed AWS CLI 2.37.12 (current-user MSI from awscli.amazonaws.com) and signed in with IAM Identity Center (user `ayman-admin`, role `AdministratorAccess`, profile `credit-admin`, region `eu-north-1`). Only read-only commands were run: `sts get-caller-identity` confirmed the assumed role, `lambda get-account-settings` showed 0 functions. The CLI offered to install "AWS skills and the AWS MCP server" for AI coding agents: declined (`n`), because it would give an AI agent a standing connection to the account, against the rule that the owner runs AWS commands and credentials never reach the assistant.

**Finding.** The Lambda concurrency quota of this account is **10** (`ConcurrentExecutions` 10, unreserved 10). Reserved concurrency can only reserve the account limit minus 100 (official Lambda documentation), so **it cannot be used here** and the planned spending cap through reserved concurrency is dropped. Protection instead: (1) the account quota itself caps the function at 10 simultaneous executions; (2) the Function URL uses `AWS_IAM`, so only signed requests from the owner's identity can invoke it; (3) the Free plan cannot generate charges (the account closes when the credits are used or after six months), and the two budget alerts email on spending; (4) small function memory and a short timeout, log retention of 14 days, an ECR lifecycle rule that keeps the last 3 images. A public URL stays a separate, deliberate decision.

**Plan changes from the sheet (decided 2026-10-12 after reading the official documentation).** OIDC and the deploy workflow move from 3.6b to 3.6c; 3.6b is split into four small steps (CLI and sign-in, ECR repository, image upload, Lambda function with a locked URL), each approved separately; scripts live in `infra/`, are run by the owner, and have a matching teardown. Lambda rejects multi-architecture images, so the image is built for a single architecture with provenance metadata disabled. For repositories created after 2026-07-15 GitHub writes owner and repository IDs into the OIDC `sub` claim (`repo:OWNER@OWNER-ID/REPO@REPO-ID:ref:refs/heads/BRANCH`): the real value will be read from a test workflow before the trust policy is written. Free plan: credits of USD 100 plus up to 100 more, ends after six months or when credits are used, the account closes and data is kept 90 days, with an upgrade to Paid possible inside that window; the account opened around 2026-10-09, so the end is around April 2027 (exact date to read in the Billing console).

## 2026-10-12: ECR repository created (step 3.6b-2), image push script ready (step 3.6b-3, not yet run)

**3.6b-2 done by the owner.** `infra/01_create_ecr.ps1` was run in PowerShell after a dry run: private repository `credit-scoring-api` in `eu-north-1`, immutable tags, AES256 encryption, tag `project=credit-risk-platform`, cleanup rule (untagged images deleted after 1 day, last 3 images kept). First AWS resource of the project; the account number appears in the repository address and is never committed (a test scans `infra/` for 12-digit numbers, key patterns and ARNs with an account id).

**Two PowerShell traps found and fixed BEFORE the first run (keep for the interview).** (1) Windows PowerShell 5.1 raises an exception for any text a native program writes to stderr when `$ErrorActionPreference` is `Stop`, even when it is hidden with `2>$null`: the "does the repository exist?" check would have crashed on exactly the expected first-run case. Tested with a stand-in program, fixed by relaxing the preference around each call and checking the exit code (and, in the push script, merging stderr into stdout inside `cmd.exe`, because Docker writes its progress to stderr). (2) A PowerShell function returns everything it prints: the first helper would have returned the command's JSON together with its exit code and reported a false failure. Both fixes are covered by static tests and by running the real helper functions against stand-ins.

**3.6b-3 script: `infra/02_push_image.ps1` (written and tested locally, not yet run against AWS).** Refuses to run with uncommitted changes (the tag is the git commit, short sha of 7 characters); skips when the tag is already stored (tags are immutable); builds with `--platform linux/amd64 --provenance=false --sbom=false`; smoke-tests the exact image it built before pushing; signs in with the temporary ECR password (never printed, variable removed, `docker logout` in a `finally`); pushes; asks ECR for the stored manifest and refuses anything but a single Docker v2 or OCI image manifest (never an index); prints digest and size.

**Verified locally (no AWS).** With the flags the build exports one manifest; without them Docker also exports an "attestation manifest" and a "manifest list", which is what Lambda rejects. The image is amd64/linux, about 54 MB of content (the 222 MB shown earlier was disk usage including the uncompressed Python base).

**Still open.** The exact end date of the Free plan (read it on the Billing home page); public versus private function URL (decide before 3.6d); whether the image `USER` instruction is accepted by Lambda (to measure in 3.6b-4: the Lambda documentation says no USER is needed because Lambda defines its own default user).

## 2026-10-12: image in ECR (step 3.6b-3 done), Lambda scripts ready (step 3.6b-4, not yet run)

**3.6b-3 done by the owner.** `infra/02_push_image.ps1` pushed the image tagged `ac13c6b` (the git commit): a single Docker v2 manifest (not an index), stored size 51.2 MB (about 10% of the free 500 MB), digest `sha256:e5bc43e5...`. The same digest was printed by the local test build made before the push: a digest is a fingerprint of the content, so what is stored in AWS is byte-for-byte the image tested locally. The owner reads the Free-plan end as April 2027 (exact day still to be read from the Billing page).

**3.6b-4 scripts (written and tested locally, nothing run against AWS).** `infra/03_create_lambda.ps1` creates, each piece skipped when it already exists: (1) an IAM execution role `credit-scoring-api-lambda` that only Lambda can assume (`infra/lambda_trust_policy.json`) with ONE inline policy allowing `logs:CreateLogStream` and `logs:PutLogEvents` on its own log group only (`infra/lambda_logs_policy.template.json`, rendered at run time with the account number so no account number is committed; the managed `AWSLambdaBasicExecutionRole` was not used because it allows log writes everywhere); (2) the log group created first with a 14-day retention (otherwise Lambda creates one that never expires); (3) the function from the newest image in ECR (or `-Tag`): 512 MB, 10 s timeout, x86_64, no resource policy that could open it to others; (4) a Function URL with auth type `AWS_IAM`. It prints the repository policy that Lambda adds by itself to pull the image (documented behaviour), the function settings, and runs the signed smoke test. `infra/99_teardown.ps1` was rewritten to delete in a safe order (function and URL, log group, role, ECR repository), each after typing its name; its dry run was tested.

**Signed requests.** A locked Function URL refuses unsigned calls, so `scripts/smoke_test_api.py` can sign every request (SigV4, service `lambda`) with `--aws-profile credit-admin`; botocore is imported only then, so without the option the script stays standard-library only. New dev-only pins in `requirements-dev.txt`: `boto3==1.43.103` and `botocore==1.43.103` (17 days old at pinning; the newest boto3 was 3 days old; the two must match); installing them only added libraries (`pip check` clean). Tests use AWS's documented example credentials assembled at run time and check the scope (`/eu-north-1/lambda/aws4_request`), the signed host header, that the signature changes with the body, and that requests stay unsigned by default.

**Checks done without AWS.** Syntax of the four scripts; the real helper functions run against stand-in programs; the teardown confirmation helper in dry-run mode (prints, deletes nothing); the five JMESPath `--query` expressions evaluated with the same library the AWS CLI uses on sample data; 26 static tests of the scripts and policies (no account number or key pattern in any file, the URL can never be created unlocked, no `add-permission`, the role's only action is two log actions on its own log group).

**To measure when it runs.** Whether the image `USER` instruction is accepted by Lambda (the documentation says Lambda defines its own default user and no USER is needed); cold-start and warm latency (3.6d); the repository policy Lambda adds on its own.

## 2026-10-13: the Lambda function exists and answers behind a locked URL (step 3.6b-4 run by the owner)

**Created by `infra/03_create_lambda.ps1` after a dry run (all in `eu-north-1`):** the execution role `credit-scoring-api-lambda` (trust: Lambda only; one inline policy with two log actions on its own log group), the log group `/aws/lambda/credit-scoring-api` with 14 days retention, the function from image tag `ac13c6b` (state Active, 512 MB, 10 s, x86_64, package type Image; the code SHA reported by Lambda equals the image digest pushed in 3.6b-3) and a Function URL with auth type `AWS_IAM`. Second AWS resources of the project after the ECR repository. The URL and the account number are not committed.

**Settled by the run.** (1) The image runs as the non-root user `USER 10001` inside Lambda: the function became Active and answered `/health` through the signed, locked URL, so the open question about the `USER` instruction is closed. (2) The adapter works as documented: no code change, readiness on `/health`.

**Observation: the repository policy Lambda adds by itself.** AWS created the statement `LambdaECRImageRetrievalPolicy` on the ECR repository: principal `lambda.amazonaws.com`, condition `aws:sourceArn` = any function of this account in this Region, actions `BatchGetImage`, `GetDownloadUrlForLayer` and also `SetRepositoryPolicy`, `DeleteRepositoryPolicy`, `GetRepositoryPolicy`. It is the documented automatic behaviour, within one account and one owner, but wider than the minimum (pulling needs only the first two, and for one named function). Possible hardening, not done: replace it by an explicit policy with the two pull actions only and the ARN of this function in the condition.

**The smoke test crashed on a slow network, not on the service.** The script printed a traceback `TimeoutError: _ssl.c:1011: The handshake operation timed out` in the loop of bad-input checks, which comes after the health, model-info, golden-loan and explain checks. A TLS handshake happens before the request is sent, so this was the connection from the owner's computer. The script was too fragile: one slow handshake gave a traceback instead of a verdict. Fixed: `call()` now retries network errors up to 3 times (2 s, then 4 s, signing again each time so the signature is fresh), never retries a real answer from the server (403, 422, 5xx come back at once), and reports persistent network trouble as status 0, which becomes a failed check, not an exception. Four new tests cover a flaky handshake that recovers, a link that stays down, a 403 that must not be retried, and re-signing on every attempt. `infra/03_create_lambda.ps1` now says clearly, when only the smoke test fails, that everything was created and prints the command to run the test alone.

**Still to measure (3.6d).** Cold-start and warm latency, memory used (from the Lambda log line), and the first real bill lines in the Billing console.

## 2026-10-13: packaging the first version for a career forum (README, CV kit, interview bank, demo kit, latency script)

**Why.** A forum the next day and a recruiter's first look: the repository's front page was still the v1 README (German Credit, SMOTE). Decision: lead with what is already strong and true (honest validation, reproducible pipeline, tested container, a locked API on AWS) and be exact about what is not done.

**Done.** (1) `README.md` rewritten for v2: results table with numbers read from `results/`, architecture diagram (Mermaid), what runs on AWS, honest limitations, how to run; the old README is kept as `docs/v1_project.md`. (2) `docs/cv_and_pitch.md`: CV bullets for a data/AI-engineering and an ML/data-science version, 30-second and 2-minute pitches, LinkedIn and GitHub text, a list of claims NOT to make. (3) `docs/guide/11_interview_project_qa.md`: 37 questions with honest answers, built from the real mistakes and numbers of the project, plus a drill. (4) `docs/demo_script.md`: a 2-minute recording script with a privacy checklist (no account number on screen) and a screenshot list. (5) `scripts/measure_latency.py` with 13 tests: measures the live function from the client side and reads Lambda's own REPORT log lines (cold start, duration, billed duration, memory); it only reads logs and sends about 60 signed requests; it has not been run yet, so every latency number in the documents is marked TBD.

**Claims deliberately NOT made** (a first look must survive a second look): automatic CI/CD to AWS (CI builds and tests; the deploy is by scripts run by hand), Evidently (own PSI/CSI code), production, real-time retraining, a public demo, any latency figure.

**A number corrected after measuring.** The performance table holds 24.7 million monthly rows across the nine vintages (450,000 origination rows), not "about 15 million" as first written from memory in the decision log and in the sheet v1.4. Both were corrected and the correction is visible in the log.

**State at the end of this step.** 240 tests, CI green. Open: run the latency script (needs the owner's AWS login), GitHub OIDC deployment, S3 and Athena parity, the memo agent, the owner's review of `config/assumptions.yaml` and `config/economics.yaml`.

## 2026-10-13: the live API measured (step 3.6d, run by the owner with `scripts/measure_latency.py`)

**Result (files `results/lambda_latency.json` and `.md`; no URL and no account number inside, a test checks it).** 71 invocations in the 4-hour log window, 2 of them cold starts. Server side, from Lambda's own REPORT lines: warm request **2.7 ms** median (p95 3.0 ms, max 3.3 ms, n=69); cold start Init Duration **1,188 and 1,315 ms**; the request itself on a cold start 2.8 and 3.4 ms; billed duration median 3 ms, maximum 1,319 ms (the cold start's init is billed for a container image: the maximum is the init plus the request); max memory used **78 MB of 512 MB** on every invocation; billed compute in the window 1.36 GB-seconds against a free tier of 400,000 GB-seconds a month. Client side, from the owner's laptop to Stockholm (30 signed `POST /score` after a warm-up): min 353 ms, **median 681 ms**, p95 1,505 ms, max 2,278 ms; `GET /health` median 366 ms; 0 non-200 answers out of 60.

**How to read it (and how not to).** The 3 ms and the 0.68 s are not in conflict: the first is the function's compute, the second adds the internet trip, a NEW TLS handshake on every call (the script uses `urllib`, which opens a connection per request) and the request signing. For cost and sizing the first matters, for a user the second does. Both are quoted, labelled. The cold-start figure rests on only 2 observations, so it is quoted as "about 1.2 to 1.3 s", not as a distribution. The window also contains the smoke-test calls, so "warm n=69" mixes them with the measurement calls. The data does not support any claim about throughput or behaviour under load: concurrency was 1 and the account quota is 10.

**Possible tuning, not done.** 78 MB used of 512 MB suggests a smaller memory size, but Lambda gives CPU in proportion to memory, so init time and request time could get worse; it would need its own measurement. The 1.2 s init is the price of starting Python, FastAPI and uvicorn inside a container; a lighter framework or SnapStart-style tricks are options for later, and nothing here shows it matters for this use.

**Guards added.** `tests/test_docs_match_measurements.py`: once `results/lambda_latency.json` exists, no placeholder may survive in the README, the CV kit or the question bank, the README must quote the measured median, memory, round trip, invocation count and cold-start range exactly, and the measurement files must not contain a URL or an account number. The first run of this guard found two explanatory sentences that still contained the word "TBD" and one false alarm (a 12-digit run inside a long decimal), both fixed.

**Documents updated with the measured numbers.** README (results table and the AWS section), `docs/cv_and_pitch.md` (CV bullet and pitch), `docs/guide/11_interview_project_qa.md` (cold-start and latency answers, and a new question 38: "your laptop sees 0.68 s but Lambda reports 3 ms: which is the latency?").

## 2026-10-16: S3 data lake + Athena, day 1 (scripts and tests written; NOTHING run against AWS yet)

**Decision.** Publish the Parquet tables to a private S3 bucket and let Athena read them, then prove the cloud gives the same answers as the local DuckDB. The owner chose to upload everything, not only the two small feature tables: `raw_orig` (9 files), `raw_perf` (9 files, 24,674,152 monthly rows locally), `features_dev`, `features_fresh`. Total about 0.3 GB, so storage and queries cost cents.

**What was written (local, tested, no AWS call).** `credit/cloud/lake.py` (thin cloud layer: upload with a checksum skip rule, CREATE EXTERNAL TABLE text built from each Parquet file's own schema, Athena runner, parity comparison), `scripts/lake_sync.py` (`upload`, `tables`, `parity`, `cap-demo`), `infra/04_create_lake.ps1` (bucket with all four public-access blocks, SSE-S3 encryption, versioning, HTTPS-only policy, 3 cleanup rules; Glue database `credit_lake`; Athena workgroup `credit-risk` with the setting enforced), `infra/lake_bucket_policy.template.json`, `infra/lake_lifecycle.json`, teardown extended (workgroup, database, bucket emptied of every version, each after typing its name), and an opt-in Dagster asset `data_lake` (only when `CREDIT_LAKE=1`; the default pipeline stays offline, a test forbids it from importing AWS libraries). 280 tests pass (245 before), ruff clean.

**Deviation from what the owner was told.** The scan limit per Athena query is **200 MB**, not the 1 GB first announced. Reason: the largest single table is about 250 MB, so 200 MB makes the cap observable (`scripts/lake_sync.py cap-demo` runs `SELECT *` on the big table and it must be cancelled), and none of the parity queries needs more than a few MB. The limit is a script parameter (`-ScanLimitMb`, minimum 10 MB as AWS requires).

**Checked in AWS documentation (not from memory).** The per-query limit cancels the query when exceeded and cannot be changed to another action; the minimum is 10 MB; cancelled and failed queries are still billed; the Athena page gives 5 USD per TB scanned in its examples but names no region (to confirm in the console for eu-north-1); Glue Data Catalog is free up to 1 million objects and 1 million requests a month.

**Checked without AWS.** Both scripts parse; the real script ran against recording stand-ins for the `aws` program, which showed the exact call order (public-access block before the policy, check-before-create) and the exact JSON sent (workgroup limit 209,715,200 bytes); the bucket-emptying loop was run against a stand-in returning two batches. The six parity queries were run on the real local data: 450,000 origination rows and loans, 24,674,152 monthly rows over 450,000 loans, fresh vintages 35,304 / 42,566 / 49,377 / 49,834 loans. Not yet verified: that AWS accepts every command exactly as written (the owner's dry run and first run will show it).

**Fresh vintages.** The v2 exam is finished, so uploading `features_fresh` (it contains exam labels) breaks nothing; the parity queries on it still read structure only (a test forbids label words in them).

**Honesty map until the run.** S3 and Athena are still NOT used by the platform. The README and CV keep saying so until `results/lake_parity.json` exists.

## 2026-10-16: the S3 lake exists and passes the parity test (run by the owner)

**Run.** `infra/04_create_lake.ps1` (dry run, then real) created the bucket, the Glue database `credit_lake` and the workgroup `credit-risk`; AWS read-backs confirmed the four public-access blocks `true`, versioning `Enabled`, encryption `AES256`, scan limit 209,715,200 bytes enforced. `scripts/lake_sync.py upload` sent 20 files (261.7 MB) and verified size and checksum of each; a second dry run showed `0 to upload, 20 unchanged` (the skip rule works). `tables` created the four tables; `parity` ran the six queries on DuckDB and Athena: **6 of 6 identical** (`results/lake_parity.json`, `.md`). Athena scanned 0.04, 0.66, 0.85, 1.57, 0.00 and 2.69 MB: about 6 MB in total, so the cost is a tiny fraction of a cent (about 5 USD per TB; the 10 MB per-query minimum, if it applies to S3 data, would still keep the whole test under a cent).

**Observations.** `raw_perf_rows` scanned 0.00 MB: Athena answers `count(*)` from the Parquet file footers without reading data columns, which shows what a columnar format buys. Distinct loans in the monthly table cost 2.69 MB because only the `loan_seq` column is read, out of 35. The CLI printed `TransitionDefaultMinimumObjectSize: all_storage_classes_128K` when the cleanup rules were applied: harmless information from AWS.

**The cap seen working.** `scripts/lake_sync.py cap-demo` ran `SELECT * ... ORDER BY` on the 250 MB monthly table; the workgroup answered `query CANCELLED: Bytes scanned limit was exceeded`. The setting was read back earlier (209,715,200 bytes, enforced); now the behaviour is observed too. AWS bills cancelled queries (documentation), at most about 200 MB scanned here. Left for the end of the block: teach-back questions.

**Claims now allowed (and their limits).** "Parquet tables in a private S3 lake queried with Athena, with a parity test and a per-query scan cap." Not allowed: that the API or the monitoring reads from the lake (they do not), or that deployment is automatic.

## 2026-10-16: GitHub-to-AWS deployment without stored keys (step 3.6c; files written and tested locally, NOT yet run against AWS or GitHub)

**Decision.** A push to `main` deploys the API to Lambda through OIDC: GitHub shows AWS a signed ID card for the run, AWS hands back a key that lasts about an hour. No AWS key exists in GitHub (no secret at all; the only setting is a non-secret variable holding the role address).

**Facts checked in documentation, not from memory.** GitHub: the job needs `id-token: write`; provider URL `https://token.actions.githubusercontent.com`, audience `sts.amazonaws.com`; the `sub` claim for a branch has the form `repo:OWNER/REPO:ref:refs/heads/BRANCH`. AWS: `--thumbprint-list` of `create-open-id-connect-provider` is optional (AWS verifies with its own trusted-CA library). AWS Lambda: **since October 2025 a new Function URL with `AWS_IAM` needs both `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`** for the caller (the second can be limited with `lambda:InvokedViaFunctionUrl`); creating or updating an image function needs `ecr:GetRepositoryPolicy`, `SetRepositoryPolicy`, `BatchGetImage`, `GetDownloadUrlForLayer`, and Lambda only adds the repository statement itself when it is missing. Latest `aws-actions/configure-aws-credentials` release read on its page: v6.3.0 (15 Sep 2026); commit hashes read with `git ls-remote`.

**What was written.** `infra/05_create_github_deploy.ps1` (trust entry, role, policies, then policy-simulator proof: 3 actions allowed, 7 denied, stops on any surprise), `infra/github_oidc_trust_policy.template.json` (`StringEquals`, exact repository, exact branch, no wildcard), `infra/github_deploy_policy.template.json` (ECR push on one repository, update and read one function, signed call of its locked URL), `.github/workflows/deploy.yml` (one job: ruff, pytest, build for one architecture without attestations, image content check, local container smoke test, **then** the temporary key, push with immutable tag reuse, update, wait, digest equality check, live signed smoke test; actions pinned to commit hashes; skipped until the variable exists; never cancelled half-way), teardown sections 8 and 9, and `scripts/smoke_test_api.py --aws-default-credentials` (signs with the environment credentials; the profile does not exist in CI).

**Choices to remember.** (1) `ecr:SetRepositoryPolicy` is deliberately NOT given to the role: Lambda already added its pull statement when the function was created, and the permission would let the role rewrite who may read the repository. If the first deploy fails with an ECR permission error on `update-function-code`, that is the first suspect, and the decision to add it (scoped to the one repository) is the owner's. (2) The test job is duplicated inside the deploy workflow instead of reusing `ci.yml` (a reusable workflow would share CI's concurrency group and the two runs would cancel each other); a test checks that the key commands are identical in both files. (3) No automatic rollback yet: a failed live smoke test turns the run red and prints the manual rollback commands (the last 3 images are kept in ECR). An automatic rollback would be a code path that has never been exercised.

**Checked without AWS or GitHub.** Both PowerShell scripts parse; script 05 run against recording stand-ins (exact calls, exact JSON, simulator logic); every shell block of the workflow passes `bash -n`; 20 new static tests, and a mutation check (wildcard in the trust rule, `StringLike`, an extra delete permission, an unpinned action, a `pull_request` trigger, `cancel-in-progress: true`) made the right tests fail. **Not verified until it runs:** that AWS accepts every command as written, that the `sub` casing matches what GitHub sends, and the exact format of `Code.ResolvedImageUri` (the digest check reads it).

**Still not true, so not claimed.** Automatic deployment. It becomes true only after the first green run of this workflow.

## 2026-10-16: the history was rewritten; the first deploy run stopped at the AWS login

**Commit trailer.** The owner noticed GitHub listed Claude as a contributor: every commit message carried a `Co-Authored-By: Claude` line, added without telling them. They chose to remove it everywhere. Messages only were rewritten with `git filter-branch` (67 commits, branches `main` and `v2-prep`, tag `v2.0-mvp`); the trees were compared with the filter-branch backup (`refs/original`) and are identical; then force-pushed. All commit hashes changed: image tags such as `ac13c6b` in ECR and in older entries of this log are now only names, no longer commits. New commits carry no such line. (A mistake caught on the way: `filter-branch --branches` also rewrote the backup branch created just before, so a comparison against it proved nothing; the comparison against `refs/original` is the valid one.)

**First run of the deploy workflow (Deploy #1, commit a9f4c9c).** Everything before the AWS login passed: ruff, 304 tests, image build, image content check, container smoke test. The step "Get a temporary AWS key (OIDC)" failed with `Could not assume role with OIDC: Not authorized to perform sts:AssumeRoleWithWebIdentity`. The role and its trust entry exist (created and simulator-checked on the same day), so the suspects are: the claim values GitHub actually sends (`sub`, including letter case) against the trust rule `repo:Aymannel04/credit-risk-platform:ref:refs/heads/main`; the value stored in the repository variable; the audience. Nothing was pushed to ECR or changed in Lambda (the later steps were skipped). Next: a failure-only step prints the non-secret claims of the ID card so the trust rule can be compared with facts. The runner is also pinned to `ubuntu-24.04` (GitHub announced `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19).

**CI #24** (branch `v2-prep`, old commit) failed at "Build the API container image" while the same commit passed on the tag (CI #25): not a code problem, to be re-run.

## 2026-10-16: why the first deploy login was refused, and the fix

**Diagnosis (from the failure-only diagnostic step of Deploy #2, commit cf94380).** GitHub's ID card for this run said `sub: repo:Aymannel04@207994149/credit-risk-platform@1410817428:ref:refs/heads/main`, `aud: sts.amazonaws.com`, `iss: https://token.actions.githubusercontent.com`. The role's trust rule expected `repo:Aymannel04/credit-risk-platform:ref:refs/heads/main`: AWS compares the text exactly, so it said no, and the action retried 12 times for a minute. The two numbers are the permanent ids of the owner and of the repository; read independently from GitHub's public API they match (owner 207994149, repository 1410817428). The GitHub documentation explains why: repositories created after 2026-07-15 use an "immutable" subject format with these ids (older ones keep the name-only format unless they opt in). The example I had followed from the documentation page for AWS used the old format; the page about the OIDC reference describes both. A lesson worth keeping: a trust rule must be written from the claim that is actually sent (printed by a diagnostic step), not from an example.

**Fix.** `infra/github_oidc_trust_policy.template.json` now uses `repo:__OWNER__@__OWNER_ID__/__REPO__@__REPO_ID__:ref:refs/heads/__BRANCH__`; `infra/05_create_github_deploy.ps1` has the parameters `-GithubOwnerId 207994149` and `-GithubRepoId 1410817428` (numbers only, validated) and re-applies the trust rule to the existing role (`update-assume-role-policy`; nothing else changes). This is also stricter than before: the rule is tied to the numbers, so if the repository name is ever deleted and re-created by someone else, their repository has other ids and cannot take the role. The workflow now retries the login 3 times instead of 12. Nothing was pushed to ECR and Lambda was untouched in both failed runs.
