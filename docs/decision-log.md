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
