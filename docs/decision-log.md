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
