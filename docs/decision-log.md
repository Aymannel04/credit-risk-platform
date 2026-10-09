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
