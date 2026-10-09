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
