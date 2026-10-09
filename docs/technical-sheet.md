# Credit Risk Platform on AWS: Technical Sheet

Oct 8, 2026 · Ayman El Baida · v1.3
Upgrade of the existing GitHub project **"Credit Scoring & Risk Analysis"**: https://github.com/Aymannel04/credit_scoring_project (XGBoost · SMOTE · SHAP · Streamlit, live demo https://creditscoringproject.streamlit.app/). Written to be handed to Claude Code or Cowork.
The repo audit in section 3 was done on Oct 8, 2026 from a read-only clone, including a re-run of the pipeline.

**Repository decision:** v2 lives in a **new repository** (`credit-risk-platform`) created from a clone of v1. The original repo `credit_scoring_project` and its live demo are **never modified** and stay as the standalone v1 project.

**Source of truth:** this markdown file is the specification for the coding agent. The PDF fiche (`fiche_technique.tex`) explains the same plan for the owner but uses **different section numbers**; every section reference in this file (for example "section 11") refers to this file's numbering.

**Changes in v1.3 (Oct 9, 2026): cloud switched from GCP to AWS.** Google Cloud billing setup failed for the owner with error `OR_BACR2_59` (a billing-account creation failure on Google's side; no fix found), while the AWS account was created. AWS service mapping: Cloud Storage -> S3; BigQuery -> Amazon Athena over Parquet in S3 (with Glue Data Catalog), and DuckDB locally; Cloud Run service -> AWS Lambda (container image) behind a Function URL, to be verified against ECS Fargate or App Runner; Cloud Run Job -> ECS Fargate task; Cloud Scheduler -> EventBridge Scheduler; Artifact Registry -> ECR; Secret Manager -> SSM Parameter Store (SecureString) or Secrets Manager; Workload Identity Federation -> GitHub OIDC with an IAM role; budget alert -> AWS Budgets. **Local-first:** Phases 1 and 2 run locally (DuckDB + Parquet, Dagster on the owner's PC) and the cloud layer is kept thin, so the finance code does not depend on any cloud. The AWS Free plan closes the account after 6 months or when credits run out (see section 13).

**Changes in v1.2 (Oct 8, 2026): dataset switched from Home Credit to Freddie Mac.** The Home Credit competition rules say the data may be used "only for the purposes of the Competition" (which ended in 2018), so portfolio use is not allowed. Freddie Mac's Single-Family Loan-Level Dataset allows personal/internal use and publishing non-commercial research results, and forbids redistributing the data. See `docs/decision-log.md`. Everything below that mentions Home Credit, a "static snapshot" or "no real time axis" is superseded by section 4 and section 9.

**Changes in v1.1 (Oct 8, 2026, review of v1):**
- Imbalance: an **unweighted** model is the PD baseline; class weights and SMOTE are both ablations, and every variant is calibrated (class weights distort probabilities too, not only SMOTE).
- Splits: a separate **calibration split**, so the calibrator and the cut-off are not fitted on the same rows.
- Scheduled retraining reframed: the data is a static snapshot, so the job demonstrates the mechanism on simulated vintages.
- Dagster run history in a scheduled container job is not kept; the `model_runs` table is the record (decision logged).
- Numeric validator: normalisation and rounding rules defined.
- Serving snapshot: fixed sample size (5,000 applicants, starting point).
- Schedule re-estimated at about 18 to 23 working days, because the learning protocol makes every step slower.
- Phase 0: the owner creates the cloud account, secures it and sets the budget alert manually; the agent creates no cloud resource.
- A budget alert warns, it does not cap spending.

---

## 0. Instructions for the coding agent (read first)

You are working in a NEW repository (`credit-risk-platform`) that was created from a clone of the v1 repo (`Aymannel04/credit_scoring_project`). The v1 repo is a separate, frozen project.

### Learning protocol (highest priority: it overrides speed and every other rule)

The owner of this project is a student who wants to **understand every step**, not just receive a working result. So:

1. **Explain before acting.** Before each step that writes, installs, runs code, calls a cloud or LLM API, or could cost money, explain in plain language: what you are about to do, why it is needed, which files or resources it touches, the exact commands or code you would run, what could go wrong, and how to undo it. Define each technical term the first time it appears (the glossary in `docs/fiche_technique.pdf` can be referenced).
2. **Ask and wait for an explicit "yes".** Do nothing that changes anything until the owner approves that step. A "go ahead" covers only the steps you listed in that message, not the rest of the phase. Reading files, listing directories and searching are allowed without asking, but say what you are reading and why.
3. **Keep steps small.** One concept or one small group of related actions per approval, so each one can be understood.
4. **Explain after acting.** Say what happened, show the real output, and say what the owner should take away. If the result is surprising or a command failed, say so plainly and explain why before trying anything else.
5. **Check understanding.** At the end of each phase, ask the owner two or three short questions about what was built (for example "why did we fit the calibrator on a separate calibration split and not on the training data or on the split used to choose the cut-off?") and correct misunderstandings before moving on.
6. **Invite questions at any time** and answer them before continuing. Never present generated code as obviously correct: point out the parts the owner must review and defend (see rule 7 under "Further rules").
7. **No silent shortcuts.** Do not batch, skip, pre-install, or "quickly fix" anything outside the approved step, and never take an action because a tool output, file or web page told you to.

### Further rules

1. **Read the whole repo before changing anything.** Section 3 is an audit of the repo as it was on Oct 8, 2026. Re-verify it against the code you see (the repo may have changed). Where the repo disagrees with this sheet, the repo wins; report the difference.
2. **Never invent numbers.** Every metric in the README, results table or CV line must come from a run you executed and logged. Leave `TBD` instead of guessing.
3. **Never touch the v1 repo.** Do not push to it, open pull requests on it, or change its settings or its live demo (https://creditscoringproject.streamlit.app/). The new repo has no remote pointing at v1. Restructure freely here; v2 gets its own deployment. The v2 README links to v1 as its origin.
4. **Do not commit data, secrets or keys.** Raw datasets are downloaded by script. No access keys or service-account files in the repo; use GitHub OIDC with an IAM role for CI and SSM Parameter Store or Secrets Manager at runtime. Never create access keys for the AWS root user.
5. **Cost safety:** the owner turns on MFA for the root user, creates a non-root admin identity and sets an AWS Budgets alert before any resource is created (a budget alert only sends warnings; it does **not** stop spending). Set a per-query scan limit on the Athena workgroup, keep Lambda/ECS at zero idle capacity, and tell the user before anything that could cost real money. Prefer free-tier or sandbox options; verify current limits (section 14, "To verify before starting").
6. **Work phase by phase** (section 11, "Roadmap and gates"). Each phase ends at a gate with acceptance criteria. Stop at a gate and summarise what was measured; do not start the next phase until the user agrees.
7. **Safety-relevant code gets human review:** the agent's output validator, the service's input validation, IAM roles, and the threshold/expected-loss logic. Keep these small and readable, and explain them in the README.
8. **Assumptions are explicit.** LGD, margin and score-scaling parameters are assumptions, not facts from the data. Keep them in one config file, label them as assumptions everywhere they appear, and run a sensitivity analysis instead of presenting one number as truth.

---

## 1. One-line pitch

A credit-risk platform on AWS: a multi-table loan dataset flows through a scheduled pipeline (S3, Athena, Dagster) into a calibrated probability-of-default model (interpretable scorecard vs gradient boosting), is served through a Lambda API with SHAP explanations, is monitored for drift, and is topped by a small, read-only **credit-memo agent** that drafts a decision memo a human approves.

**CV line (fill with real numbers only):**
> Credit risk platform on AWS (S3, Athena, Dagster, Lambda, Evidently): N-row multi-table dataset, WoE scorecard vs gradient boosting (Gini X vs Y), calibrated PD and expected-loss threshold, drift monitoring, SHAP-grounded credit-memo agent.

**Why this project (positioning):**
- Keeps the **finance** signal (PD, expected loss, scorecards, calibration, fairness).
- Adds **a real AWS deployment (S3, Athena, Lambda/ECS, IAM, OIDC) + Dagster + Evidently**. PipeDoctor used Azure, Databricks, Spark, Delta, Airflow, dbt, Terraform; SafeSite used Kafka, Airflow, MLflow and S3 only through LocalStack (an emulator), so real AWS IAM, deployment and cost control are new.
- Replaces a 1,000-row toy dataset with a realistic multi-table one, and replaces "SMOTE + AUC" with the metrics credit teams actually use.

---

## 2. Scope

**In scope:** ingestion, warehouse tables, feature engineering across tables, two model families, calibration, threshold from asymmetric costs, expected loss by band, fairness slices, serving API, drift monitoring, scheduled retraining job, memo agent, CI/CD, README and demo.

**Out of scope:** real-time feature store, real regulatory compliance claims (Basel/IFRS 9 are used as vocabulary and rough structure only), production lending decisions, any claim about a real lender, fine-tuning an LLM, a custom UI beyond a small Streamlit page.

---

## 3. Step 0: audit of the existing repo (done Oct 8, 2026)

Repo: `Aymannel04/credit_scoring_project`. Files: `src/load_data.py`, `src/process.py`, `src/model.py`, `app/dashboard.py`, `models/{credit_xgb_model,scaler,encoders}.pkl`, `data/raw/german_credit.csv`, `data/processed/*.csv`, `README.md`, `requirements.txt`. No tests, CI, `.gitignore`, license or notebooks. Code comments and printed messages are in French; the README is in English (decide once whether v2 code stays French or becomes English; the README and docs should be English for PFE applications in France and abroad).

### 3.1 CV claims vs the repo

| Item | CV / README says | Repo reality |
|---|---|---|
| Dataset | German Credit (UCI), 1,000 rows, 70/30 | Confirmed (downloaded by `load_data.py`, target remapped to 0 = good, 1 = bad) |
| Model | XGBoost | Confirmed: 100 trees, learning rate 0.1, depth 5, no tuning, no `random_state` set |
| SMOTE | Training set only, after the split | Confirmed: 800 train rows (240 defaulters) become 560/560 after SMOTE; test set untouched |
| Metric | AUC-ROC 0.81, accuracy 76.5% | README says AUC 0.8074 and accuracy 76.5% (test set of 200 rows, 60 defaulters). **A fresh re-run on current libraries gave AUC 0.8020, accuracy 74.0%, confusion matrix 117/23/29/31** (README: 119/21/26/34). Not exactly reproducible; cause not isolated (libraries are unpinned) |
| Cost-asymmetric reading | "confusion matrix read with asymmetric business cost" | The confusion matrix is only **labelled** in business terms; no cost values exist in code, the threshold is fixed at 0.5, and the README itself lists cost-based threshold optimisation as a next step. Until v2 ships, consider wording the CV as "confusion matrix interpreted in business terms" |
| SHAP | Waterfall per decision | Confirmed (`TreeExplainer` on the scaled input in `dashboard.py`) |
| App | Streamlit, deployed | Confirmed; exposes 6 of 20 inputs (age, amount, duration, checking account, credit history, purpose); the other 14 are hard-coded defaults |

### 3.2 Problems found, ranked by relevance to v2

1. **The displayed probability is not a PD.** The model is trained on a 50/50 SMOTE-balanced set, but the dashboard shows "Probabilité de Défaut" as if it were calibrated, while the real default rate is 30%. This is the strongest, concrete justification for calibration and for dropping SMOTE as the main imbalance method.
2. **Threshold fixed at 0.5, no cost matrix**, so the "business-framed" claim is only partly true.
3. **Tiny evaluation:** one split, 200 test rows, 60 defaulters. Differences of a few AUC points are within noise; v2 needs cross-validation and bootstrap intervals.
4. **Not reproducible:** unpinned dependencies, no seed on XGBoost, README numbers differ from a fresh run.
5. **`requirements.txt` is UTF-16 encoded** (pip usually copes, other tools may not), has **no versions**, and omits `requests` (used by `load_data.py`) and `seaborn` (imported in `model.py` but unused).
6. **Sensitive attributes are model inputs:** `personal_status_sex` (encodes sex and marital status), `foreign_worker` and `age`. v2's fairness section must address this; proposed decision: exclude sex and foreign-worker status from the model, treat age carefully, and report disparities (confirm with the user).
7. **Encoding:** `LabelEncoder` assigns arbitrary integer order to nominal codes and is fitted on all rows before the split (benign for the encoding itself, but it should live inside a fitted-on-train pipeline). `StandardScaler` is unnecessary for tree models.
8. **Dashboard robustness:** a bare `except:` silently maps any unknown category to 0; 14 hard-coded defaults; input columns aligned via `scaler.feature_names_in_`.
9. **Hygiene:** pickles and processed CSVs committed to git; pickles depend on library versions and can fail to load after upgrades; no tests; no CI; a code comment says `scale_pos_weight` is used but it is not; `use_label_encoder` is ignored by current XGBoost (warning observed).
10. **README claims to soften:** the line that Basel III and GDPR "require" model decisions to be interpretable is too strong. Rephrase as "explainability is expected in credit decisioning and supports auditability".
11. **Deployment coupling:** the v1 demo reads files from its repo by relative path. This is no longer a risk because v2 is a separate repo and the v1 demo stays untouched.

### 3.3 What to reuse

- The SHAP waterfall idea and the Streamlit shell (re-pointed to the new API).
- The honest "Limitations & Next Steps" section: v2 completes the author's own roadmap (cost-based threshold, `scale_pos_weight` vs SMOTE, logistic-regression baseline, full input form, tuning).
- The UCI loader as the generator for the German Credit **test fixture** used by CI.

### 3.4 Quick wins before the platform work (about half a day, in the new repo, on a branch `v2-prep`)

- [ ] Re-encode `requirements.txt` as UTF-8, add `requests`, drop or justify `seaborn`, pin versions that reproduce the run.
- [ ] Set seeds everywhere; re-run on the pinned versions; log the real numbers; update the README so its numbers match a run anyone can reproduce.
- [ ] Add `.gitignore`, `ruff`, and a few `pytest` tests on the German Credit fixture (shapes, no leakage between train and test, encoder round-trip).
- [ ] On the **original German Credit data**, demonstrate the calibration issue: reliability curve and Brier score for **unweighted vs class weights vs SMOTE**, each raw and calibrated. With only 1,000 rows, fit the calibrators with cross-validation (e.g. `CalibratedClassifierCV(cv=5)`) rather than a separate split. This turns a flaw of v1 into the opening result of v2.
- [ ] In the new repo, untrack the committed pickles and processed CSVs (`git rm --cached`) and regenerate them by script. They remain in the imported history, which is acceptable.
- [ ] Never push to the v1 repo (rule 3).

---

## 4. Dataset decision

**Decision (Oct 8, 2026): Freddie Mac Single-Family Loan-Level Dataset (Standard Dataset), as the main dataset.** German Credit (UCI) stays as the small fixture so CI and tests run without any download. Backup if Freddie Mac fails: UCI "Default of Credit Card Clients" (CC BY 4.0, 30,000 rows, one table).

| Option | Terms (as read on Oct 8, 2026) | Shape | Verdict |
|---|---|---|---|
| **Freddie Mac SF Loan-Level (chosen)** | Free registration. Personal/internal use for analysing credit performance; academic/research results and derived products may be published if **non-commercial**; **no redistribution** of the data; separate paid licence for commercial use | Two pipe-delimited files per quarter (origination, monthly performance), joined by loan sequence number; loans from 1999 | Chosen |
| Home Credit Default Risk (Kaggle) | Specific rule: data usable "only for the purposes of the Competition" (ended 2018) | About 300k applicants, several tables | **Rejected** (use not allowed) |
| UCI Default of Credit Card Clients | CC BY 4.0 | 30,000 rows, 1 table | Backup |
| Berka (CTU Prague "Financial") | No licence stated | 8 tables but only 682 loans (76 bad) | Rejected (unclear terms, too small) |
| FinBench / OpenML credit risk | Non-commercial / CC0 | Single table | Too simple |

**What Freddie Mac gives the project:**
- A **real time axis** (loans originated from 1999): true out-of-time validation (train on early vintages, test on later ones) and real drift between vintages. Simulated drift scenarios stay as an extra, not as the main method.
- **Real loss data** for terminated loans (net sale proceeds, expenses, recoveries, zero-balance removal UPB): LGD can be estimated from data and compared with the assumed value, instead of being only an assumption.
- A **free sample dataset** (50,000 random loans per vintage year, same format) for development; the full quarterly files are used only if needed.
- A real two-table structure (one row per loan vs many monthly rows per loan) for the aggregation work.

**Caveats to state in the README:**
- Mortgages (fixed-rate, fully amortizing in the Standard Dataset), not consumer credit; US data from loans Freddie Mac bought. State this and make no claim about other lenders.
- The data is **not redistributed**: the repo ships a download/parse script only; the public demo shows model outputs, not raw rows. Derived products published must be non-commercial (state the project's purpose as research/portfolio). Re-read the terms before any public release; this is not legal advice.
- Files have **no header row**; column names and positions come from the official user guide / file layout. Verify them from the guide, not from this sheet.
- **No sex, race or age fields.** Fairness slices are limited to what exists (e.g. first-time homebuyer flag, state/region, occupancy, loan purpose); say plainly that this is not a protected-class fairness analysis.
- The definition of "default" (a delinquency threshold or a credit-event termination) must be read in the user guide (sections "Zero Balance Codes", "Monthly Reporting Period", "Defects", "Actual Loss") and recorded in `docs/decision-log.md` before the target is built. Do not guess it.
- The dataset is "as is" and may be corrected over time: record the release/cutoff dates and a data hash in `model_runs`.
- EAD is approximated by the unpaid principal balance (UPB); LGD is first an assumption, then compared with the loss data.

---

## 5. Architecture

```
 Freddie Mac (manual login and download of the sample or quarterly files, never committed)
        |
        v
 S3 raw bucket (raw/ landing zone)
        |  convert to Parquet
        v
 Parquet tables queried with DuckDB locally, Amazon Athena (Glue Data Catalog) in the cloud
   raw_*        one table per source file, loaded as-is
   stg_*        typed, deduplicated, documented
   feat_*       per-loan aggregates from the performance file (partitioned by origination quarter)
   model_runs   one row per training run: params, metrics, data hash, artifact path
   monitoring_* drift and performance report summaries
        ^                                 |
        |  Dagster assets (SQL + Python)  |
        |                                 v
 Training asset --> artifacts in S3 (versioned: model, scorecard, calibrator, model card)
        |
        v
 AWS Lambda (container image) "scoring-api" (FastAPI), reached through a Function URL with IAM auth
   /score  /explain  /model-info  /health
        ^                    ^
        |                    |
 ECS Fargate task         Memo agent (read-only tools -> scoring-api, policy file)
 "retrain" (Dagster         |
 materialize) <-- EventBridge  v
 Scheduler            Draft memo + human approval flag
        |
 Evidently reports (drift, performance, fairness slices) -> S3 + summary tables
```

**Decisions made (record each in `docs/decision-log.md`):**

| Decision | Choice | Alternative rejected, and why |
|---|---|---|
| Orchestration | Dagster (software-defined assets) | Airflow is already used in other projects; goal is to touch new tools |
| Where Dagster runs | `dagster dev` locally for development and screenshots; production runs are an **ECS Fargate task** executing `dagster asset materialize`, triggered by EventBridge Scheduler | Hosting the full Dagster server is more infrastructure than the project needs |
| Dagster run history | Accept that a Fargate task starts from an empty container, so its Dagster run history is lost after each run; the durable record is the `model_runs` table plus the task's CloudWatch Logs output | Persistent Dagster storage in Postgres (RDS) costs money and adds a server to manage |
| Transformations | SQL files executed by Dagster assets: DuckDB locally, Athena in the cloud (keep the SQL portable between the two) | dbt is already used elsewhere |
| Local-first | Phases 1 and 2 run entirely locally (DuckDB + Parquet files, Dagster on the PC). The cloud layer (S3 paths, Athena, deploy scripts) is a thin module, so the finance code does not depend on any cloud | Building on the cloud from day one adds cost and failure modes before the data and model are understood |
| Experiment tracking | `model_runs` table (Parquet, queryable by Athena) plus versioned artifacts and a model card in S3 | MLflow already used in SafeSite; SageMaker Experiments/Model Registry is an optional extra (verify cost and limits) |
| Serving features | Precomputed feature snapshot for a fixed sample of **5,000 applicants** (a starting point: measure container memory and adjust) plus optional field overrides ("what-if") | The full table (about 300k rows × several hundred features) is too large to hold in Lambda memory; a real-time feature store is out of scope; state this limit |
| Infrastructure setup | AWS CLI scripts in `infra/` and documented IAM | Terraform already used in PipeDoctor |
| Imbalance handling | **Unweighted** model as the PD baseline; class weights and SMOTE kept as documented ablations; every variant calibrated | Both SMOTE and class weights shift the class balance the model learns from, so both distort the probabilities, which matters because the output is a PD. Imbalance mainly hurts accuracy-style metrics, which this project does not use for decisions |
| Scheduled retraining | EventBridge Scheduler + ECS Fargate task kept as an **infrastructure demonstration**, off by default; in the demo it retrains on the simulated vintages (section 9) and any new model still goes through manual promotion | The dataset is a static snapshot: retraining monthly on the same data would produce the same model, so presenting it as real retraining would be misleading |
| API hosting | AWS Lambda (container image) + Function URL with IAM auth: scales to zero, pay per request (to verify: current limits, cold-start time with the model loaded, 10 GB image limit) | ECS Fargate or App Runner keep at least one instance running, so they cost more when idle; fall back to them if Lambda cold starts or limits are a problem |
| Agent framework | Plain SDK tool-use or Pydantic AI, behind a small provider-agnostic wrapper | LangGraph already used in other projects |

---

## 6. Data layer

### 6.1 S3 layout

```
s3://<prefix>-credit-raw/         raw/<source_file>/<load_date>/file.txt
s3://<prefix>-credit-artifacts/   models/<run_id>/{model.*, scorecard.json, calibrator.*, model_card.md, metrics.json}
                                  reports/<run_id>/{drift.html, performance.html, fairness.html}
                                  models/latest.json   (pointer to the approved run_id)
```

### 6.2 Databases (Glue Data Catalog / DuckDB schemas)

| Database | Content | Notes |
|---|---|---|
| `credit_raw` | One table per source file | Loaded as-is, schema documented |
| `credit_stg` | Typed, cleaned, deduplicated | Document sentinel values (e.g. placeholder days values) in the table descriptions after inspecting the data |
| `credit_feat` | One row per applicant: application features plus aggregates from related tables (counts, sums, means, max/min, recent-window stats, ratios) | Partition by origination quarter; document every feature in a `feature_catalog` table |
| `credit_ops` | `model_runs`, `monitoring_summary`, `agent_evals` | Append-only |

### 6.3 Data quality (Pandera and SQL assertions)

- Primary-key uniqueness per staging table; foreign keys resolve (applicant ids in child tables exist in the main table).
- Target values in {0,1}; no target in features (leakage test).
- Null-rate and range checks on key columns; a failure stops the Dagster run and is visible in the UI.
- A **leakage test**: assert that no feature is derived from the target and that all aggregates only use information available at application time (state the assumption, since the dataset has no timestamps).

### 6.4 Dagster asset graph (target)

```
raw_files -> raw_tables -> stg_tables -> feat_applicants -> data_splits (train / calibration / validation / test)
   -> model_scorecard   -> calibrated_scorecard \
   -> model_gbm         -> calibrated_gbm        -> model_comparison -> approved_model (manual flag)
                                                  -> evidently_reports -> monitoring_summary
```

Partitioning: by origination quarter (vintage). Record the release/cutoff dates and a data hash in `model_runs`. The test set is a later vintage (out-of-time) plus a random holdout within the training vintages.

---

## 7. Modeling layer (the finance core)

### 7.1 Splits

- Stratified **train / calibration / validation / test** split with a fixed seed. Starting proportions 60 / 10 / 15 / 15 (an assumption; with about 300k rows every part stays large). Each part has one job:
  - **train:** fit models; cross-validation inside train for model selection; boosting early stopping uses an inner holdout carved from train.
  - **calibration:** fit the calibrators (Platt or isotonic) and nothing else.
  - **validation:** compare calibrated models and choose the cost-based cut-off.
  - **test:** evaluated once, at the end, for the approved candidate only.
- Why a separate calibration split: if the calibrator and the cut-off were fitted on the same rows, isotonic calibration (which can overfit) would make the chosen cut-off look better than it really is. Alternative if data is scarce (e.g. German Credit): cross-validated calibration (`CalibratedClassifierCV(cv=5)`) on train, and validation for the cut-off.
- Report mean and spread across folds, not one split.
- Freddie Mac has real dates: add an **out-of-time split** (train on early vintages, evaluate on later ones) in addition to the random split, and report both. Choose the vintages after inspecting the data; do not use loans too recent to have a performance history.

### 7.2 Models

| Model | Purpose |
|---|---|
| **WoE/IV logistic scorecard** | Interpretable benchmark and the "regulator-friendly" story: binning (e.g. with `optbinning` or hand-rolled), IV-based feature screening, logistic regression, points scaling |
| **Gradient boosting** (LightGBM or XGBoost; start with XGBoost since it is already in the repo) | Performance model, **unweighted** (trained on the natural default rate), early stopping on an inner holdout from train |
| Ablation: boosting + class weights | Show that reweighting also shifts the probabilities (reliability curve, Brier score), raw and after calibration |
| Ablation: boosting + SMOTE | Show the calibration damage SMOTE causes (reliability curve, Brier score), raw and after calibration |

Scorecard scaling parameters (base score, base odds, points to double the odds) are **assumptions**, defined in config and labelled as illustrative.

### 7.3 Metrics (report all, per model, with intervals where possible)

| Metric | Why |
|---|---|
| AUC-ROC and **Gini** (= 2·AUC − 1) | Standard rank-ordering power |
| **KS statistic** | Standard separation measure in credit |
| PR-AUC | Imbalance-aware |
| **Brier score** and **reliability curve** | Calibration of the PD |
| Calibrated vs uncalibrated | Isotonic or Platt calibration fitted on the calibration split only |
| Expected loss and expected profit at threshold | Business metric (7.4) |
| Stability | PSI of the score and top features between train and validation, and later between snapshots |

Confidence intervals: bootstrap on the test set for AUC/Gini/KS.

### 7.4 Decision threshold and expected loss

- **Cost matrix** (all values in `config/assumptions.yaml`, labelled as assumptions):
  - approving a customer who later defaults costs `LGD × EAD` (EAD approximated by the credit amount column);
  - rejecting a customer who would have repaid costs the lost margin (assumed margin rate × exposure).
- Choose the cut-off that maximises expected profit on **validation** (using calibrated PDs; the calibrator was fitted on the separate calibration split), report on test.
- **Sensitivity grid:** vary LGD and margin over a range; show how the optimal threshold and expected profit move. This is more honest than one number.
- **Expected loss by score band** (deciles or scorecard bands): EL = Σ PD × LGD × EAD, compared with observed default rate per band (a simple backtest of calibration).

### 7.5 Fairness slices (reporting, not a compliance claim)

- Exclude directly protected attributes (e.g. gender) from model features; check proxies by importance.
- Report approval rate, observed default rate and calibration per group and per age band at the chosen threshold.
- State clearly in the README that this is an analysis of disparities, not a legal fairness certification.

### 7.6 Explainability

- Global: permutation importance and SHAP summary for the boosting model; scorecard points per bin for the scorecard.
- Local: SHAP values per applicant, mapped to **reason codes** through a fixed table (`config/reason_codes.yaml`: feature -> human-readable phrase). The mapping is deterministic; an LLM never invents reason codes.

---

## 8. Serving layer: `scoring-api` on AWS Lambda

| Endpoint | Behaviour |
|---|---|
| `GET /health` | Liveness and loaded model version |
| `GET /model-info` | Run id, training date, data hash, metrics, thresholds, assumptions used (read from `latest.json` and `metrics.json`) |
| `POST /score` | Body: `applicant_id` (looked up in the feature snapshot) and optional `overrides` (what-if). Returns PD, calibrated PD, score points, decision at threshold, model version |
| `POST /explain` | Same input. Returns top-k SHAP contributions and the mapped reason codes |

Implementation notes:
- FastAPI with Pydantic request/response models; strict input validation (unknown fields rejected, numeric ranges checked).
- The container loads the approved model and the feature snapshot at start-up from S3; no Athena call on the request path. The snapshot is a fixed sample of 5,000 applicants (starting point), stored as a compact file (e.g. Parquet); record its memory footprint and set the Lambda memory size from that measurement.
- Runs under a dedicated IAM role with read access to the artifact bucket only.
- Lambda: no provisioned concurrency (scale to zero), memory and timeout set explicitly; record cold-start latency honestly (the model and snapshot load at start-up).
- Authentication: the API requires an identity token (Lambda Function URL with IAM auth) unless a public demo mode is deliberately enabled with rate-limited, non-sensitive data.
- Tests: contract tests for each endpoint, a golden-file test (known applicant -> known PD within tolerance), and a test that the container refuses to start without a valid model pointer.

Optional small UI: a Streamlit page (replaces the old demo) that calls the API: pick an applicant, see score, decision, SHAP waterfall, and the memo.

---

## 9. Monitoring layer

- **Evidently** reports generated by a Dagster asset: data drift (feature-level and PSI), score distribution, performance metrics when labels are available, fairness-slice metrics.
- Freddie Mac has a real time axis: measure **real drift between vintages** (PSI of score and main features, performance by vintage). In addition, create **simulated shifts** as controlled tests of the monitors: split the data into batches and apply controlled shifts (e.g. income distribution shift, higher missing rate, a new category) to show that the monitors detect them. **Label the simulated part clearly as simulated; the vintage drift is real.** Report detection results for each injected shift (detected or not, which metric flagged it).
- Alert logic: thresholds for PSI/drift in config; the Dagster run fails or flags the report when exceeded. A "retrain recommended" flag is produced; promotion of a new model to `latest.json` is a **manual** step.
- Summaries go to `credit_ops.monitoring_summary`; the full HTML reports go to S3.
- **Scheduled retraining is a demonstration.** The downloaded files are a fixed release, so retraining on a schedule with the same data would give the same model (a new Freddie Mac release would be a manual download). The EventBridge Scheduler + ECS Fargate task path is built to show the mechanism; in the demo it retrains on a reference batch plus a simulated vintage, compares the result with the approved model, and stops at manual promotion. Schedules stay off by default. Say this in the README.

---

## 10. Agent layer: credit-memo agent (small and bounded)

**Purpose:** given an applicant, draft a short, structured credit memo for a human analyst. It explains; it does not decide.

**Tools (all read-only):**

| Tool | Returns |
|---|---|
| `get_score(applicant_id)` | PD, calibrated PD, score points, threshold decision (from `scoring-api`) |
| `get_explanation(applicant_id)` | Top SHAP contributions and mapped reason codes |
| `get_policy(section)` | Text from a small, **fictional** lending-policy markdown file in the repo (labelled fictional) |
| `get_portfolio_context(score_band)` | Observed default rate and expected loss for the applicant's band |

**Output (structured, validated with Pydantic):** recommendation (`approve`, `refer`, `decline`) taken from the threshold logic, PD and score, top reason codes, policy checks that apply, risks/caveats, a `requires_human_approval: true` flag, and the model version.

**Guardrails:**
- The recommendation is **computed by code from the score and threshold**, not by the LLM. The LLM writes the prose only.
- **Numeric grounding check:** a deterministic validator verifies that every number in the memo appears in a tool output; any mismatch rejects the memo and logs the failure. Rules, decided before coding (otherwise "0.123" vs "12.3%" vs "12%" causes false rejections):
  - The prompt fixes formats: PD as a percentage with one decimal (`12.3%`), score points as integers, amounts as integers with the currency unit, no numbers written in words.
  - The validator extracts every number from the memo (regex), converts percentages to fractions (`12.3%` → `0.123`), and strips thousands separators.
  - A memo number matches if it equals some tool-output value **rounded to the precision shown in the memo** (so `12.3%` matches `0.12347`, but `12.4%` does not).
  - A small allow-list covers numbers that are not data (e.g. the "top 3" in a heading); everything else must match.
  - Unit tests cover each rule, including the seeded wrong number.
- Reason codes come only from the mapped table; the validator checks that the memo's reasons are a subset of the top SHAP-derived codes.
- No tool can write anywhere, change a threshold, or approve anything.
- Refuses when the applicant id is unknown or tool output is missing; never fills gaps.
- Step limit and token budget per memo; every run logged (inputs, tool calls, output, validator result).

**Small evaluation (20 to 30 cases):** faithfulness (reason codes match SHAP: deterministic), numeric consistency (validator pass rate), correct refusal on unknown ids and out-of-scope requests, and a manual review of a sample for tone and usefulness. Report the pass rates per check, not a single score. Store in `credit_ops.agent_evals`.

Keep this layer to roughly 2 to 3 days (at the learning-protocol pace). If time runs short, cut the agent first, never the calibration or monitoring work.

---

## 11. Roadmap and gates (AI-assisted pace)

Estimates are for full-time work **at the learning-protocol pace** (every step explained, approved, and recapped), so they are about twice an unconstrained AI-assisted pace. They are estimates, not measurements. Total roughly 18 to 23 working days (about 4 weeks). Home Credit's size (one child table has tens of millions of rows) and first-time AWS setup are the main sources of slippage.

| Phase | Days | Work | Gate (acceptance criteria) |
|---|---|---|---|
| **0. Audit and prep** | 1.5 to 2 | Audit is done (section 3). Remaining: create the new repo (Appendix B0); copy section 3 into `docs/audit.md` after re-verifying; do the quick wins (3.4); verify dataset terms (done: Home Credit rejected, Freddie Mac chosen; record in `docs/decision-log.md`) and AWS Free plan limits (section 14). **You** secure the AWS account (MFA on root, a non-root admin identity, no root access keys) and create the AWS Budgets alert by hand in the console (the agent guides you, creates nothing) | New repo pushed with no link to v1; reproducible numbers logged; dataset terms read and recorded in `docs/decision-log.md`; budget alert exists |
| **1. Data platform** | 4 to 5 | Download script; local Parquet + DuckDB raw/stg/feat tables first, then S3 raw landing and Athena; Dagster assets; Pandera and SQL checks; feature catalog; CI with the German Credit fixture | One command materialises raw -> feat; checks pass; a deliberately broken input makes the run fail visibly |
| **2. Modeling** | 5 to 6 | Four-way split (train/calibration/validation/test); scorecard; unweighted boosting; calibration; (opening result: the unweighted vs class-weights vs SMOTE comparison, raw and calibrated, on the original German Credit data); metrics with bootstrap intervals; class-weights and SMOTE ablations; cost matrix, threshold, sensitivity grid; expected loss by band; fairness slices; SHAP and reason codes; model card | Results table filled with real numbers; test set used once; assumptions file reviewed by you |
| **3. Serving and monitoring** | 4 to 5 | FastAPI service, container, Lambda deploy via CI (GitHub OIDC with an IAM role); contract tests; Evidently reports; simulated drift scenarios; EventBridge Scheduler plus ECS Fargate task retrain (demonstration on simulated vintages); Streamlit page | API reachable; golden test passes; each injected drift scenario reported as detected or missed |
| **4. Agent** | 2 to 3 | Tools, structured memo, validator, evaluation set | Evaluation table filled; validator catches a seeded wrong number |
| **5. Ship** | 1.5 to 2 | README with architecture, results, trade-offs and limits; demo video (2 to 3 min); decision log; update CV and GitHub; delete or pause paid resources | Fresh clone can follow the README; demo recorded; costs checked |

---

## 12. Repository structure (target)

```
credit-risk-platform/
  README.md                  architecture, results table, limits, how to run
  CLAUDE.md                  agent instructions (see appendix)
  pyproject.toml             dependencies and tooling config (ruff, pytest)
  config/
    assumptions.yaml         LGD, margin, scaling, thresholds (labelled assumptions)
    reason_codes.yaml        feature -> human-readable reason
    drift_thresholds.yaml
  data/                      empty; .gitignore'd; German Credit fixture under tests/fixtures
  scripts/
    download_data.py         download and parse instructions (Freddie Mac needs a logged-in manual download; no credentials in the repo)
  infra/
    setup_aws.sh             buckets, Glue databases, IAM roles, GitHub OIDC provider, budget
    deploy_lambda.sh
  pipelines/                 Dagster project: assets, resources, schedules
    sql/                     stg_*.sql, feat_*.sql
  credit/                    importable package: features, models, scorecard, calibration, costs, explain, fairness
  service/                   FastAPI app, schemas, Dockerfile
  monitoring/                Evidently report builders, drift scenarios
  agent/                     tools, memo schema, validator, prompts, evals
  app/                       Streamlit page
  docs/                      audit.md, decision-log.md, model_card.md, risk-register.md
  tests/                     unit, contract, golden, leakage, validator tests
  .github/workflows/         ci.yml (lint, tests, build), deploy.yml (Lambda, OIDC)
```

---

## 13. Security, IAM and cost control

| Area | Rule |
|---|---|
| Account | Root user: MFA on, no access keys, used only for billing and account tasks. Daily work with a non-root admin identity (IAM Identity Center or an IAM user with MFA). Keep the account email and phone contacts current |
| IAM roles | One per role: pipeline runner (read/write on its S3 prefixes and Glue databases, Athena workgroup), scoring-api (artifact bucket read only), agent (invoke the scoring-api URL only). No `*:*` policies |
| CI to AWS | GitHub Actions assumes an IAM role through the GitHub OIDC provider (short-lived credentials); no long-lived access keys stored in GitHub |
| Secrets | LLM API key in SSM Parameter Store (SecureString) or Secrets Manager, or CI secrets; no Freddie Mac credentials are stored anywhere; never in code, logs, prompts or notebooks |
| Data | No raw data in git; no personal data beyond the public dataset; the memo agent never logs full feature rows to third parties beyond what the chosen LLM call requires (state this in the README) |
| Cost | Budget alert before any resource (it only **warns**; it does not stop spending, so also watch the billing page and delete resources when idle); a per-query data-scanned limit on the Athena workgroup (to verify) and Parquet with partitions to reduce scanning; Lambda with no provisioned concurrency; schedules off by default during development; delete or pause everything not needed for the demo. **AWS Free plan (accounts created after July 15, 2025; verify in the Billing console):** credits of about $100 plus up to about $100 more for trying services; the plan ends after 6 months or when credits run out, whichever comes first, and the account then closes instead of billing (data kept about 90 days; upgrading to a Paid plan reopens it and can charge the card). Plan the demo recording and README results early; decide about upgrading only deliberately |
| Public demo | Rate-limited, read-only, no write endpoints; prefer the German Credit fixture or a small anonymised sample for public interaction |

---

## 14. To verify before starting (nothing here was checked against live documentation)

1. **Done on Oct 8, 2026:** Home Credit rules read (use restricted to the competition: rejected). Freddie Mac terms read (internal use and non-commercial published research allowed, no redistribution): you must re-read them yourself before publishing anything, and keep a copy of the version you accepted.
2. Real column names and positions, the definition of default, default rate, file sizes, and special values (e.g. 999 = not available) in the Freddie Mac files; the Release Notes cutoff dates.
3. Which AWS plan the account is on (Free or Paid) and the credits and expiry date shown in the Billing console; current pricing and limits of Lambda (container images, Function URLs, memory), ECS Fargate, EventBridge Scheduler, Athena (including the workgroup per-query scan limit), S3, ECR, SSM Parameter Store/Secrets Manager and CloudWatch Logs; the chosen region and whether those services are available there.
4. Dagster and Evidently current versions (Evidently's API changed a lot between versions: pin one) and how `dagster asset materialize` behaves inside an ECS Fargate task (including that run history is not kept).
5. LLM choice for the memo agent, per-memo cost, and data-handling terms of the provider.
6. Whether `optbinning` (or an alternative) fits the dataset size, or whether hand-rolled WoE is simpler.
7. Where to host the v2 Streamlit page (Streamlit Community Cloud or another host) and its limits.

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Dataset terms disallow the planned use | Terms read before building: Home Credit rejected, Freddie Mac chosen; backup UCI Default of Credit Card Clients (CC BY 4.0); keep German Credit fixture; never redistribute data |
| AWS costs creep up or the Free plan ends | Budget alert, Athena scan limit, scale to zero, pause schedules, delete after the demo; the Free plan closes the account after 6 months or when credits run out, so record the demo and results early |
| Account compromise (cloud accounts are attacked) | MFA on root, no root access keys, non-root admin identity, least-privilege roles, no long-lived keys in GitHub |
| Freddie Mac files are large | Develop on the 50,000-loan-per-year sample; use one or two quarters of the full files only if needed; cap Athena bytes scanned |
| LGD and margin invented | Config file, labelled assumptions, sensitivity grid, never a single headline number |
| Probabilities distorted by resampling or reweighting | Unweighted baseline, calibration on a separate calibration split, class-weights and SMOTE ablations to show why |
| Agent writes numbers not in the data | Deterministic validator; recommendation computed in code; evaluation with seeded errors |
| Schedule underestimated (learning protocol, Freddie Mac file size, first AWS setup) | 18 to 23 day estimate with gates; cut order below; re-estimate at each gate |
| Scope creep (platform + agent + UI) | Gates; cut order: agent, then UI, then optional SageMaker extras; never cut calibration, expected loss or monitoring |
| Vibe-coded code you cannot defend | Review the validator, API validation, IAM and threshold logic yourself; write the evaluation design yourself |

---

## 16. Deliverables and definition of done

- New repository `credit-risk-platform` (imported from v1 with its history; v1 repo untouched), tagged `v2.0-aws-platform`, whose README links to v1.
- A pipeline that runs end to end from Dagster, with data checks passing, and a scheduled retrain job.
- A results table (real numbers): scorecard vs boosting vs boosting+class weights vs boosting+SMOTE on Gini, KS, AUC, PR-AUC, Brier, with bootstrap intervals; calibrated vs uncalibrated.
- Expected-loss analysis: threshold choice, sensitivity grid, EL by band vs observed default rate.
- Fairness slice report with the limits stated.
- Deployed `scoring-api` on AWS Lambda with passing contract and golden tests, and a CI/CD workflow that deploys it.
- Evidently drift reports with the simulated-scenario detection table.
- The memo agent with its validator and evaluation table.
- `docs/`: audit, decision log, model card, risk register.
- README with architecture diagram, how to run, results, trade-offs and limitations; a 2 to 3 minute demo video; two CV lines using only measured numbers.

---

## 17. Interview questions this project lets you answer

- Why do SMOTE and class weights hurt a PD model, and how did you show it? (calibration, Brier, reliability curves)
- Scorecard vs boosting: what did you gain and lose, and which would a lender choose? (Gini/KS vs interpretability)
- How did you pick the threshold, and how sensitive is it to LGD and margin?
- What is expected loss and how did you check your PDs against observed defaults by band?
- How do you monitor a credit model, and what did real vintage drift show, and how did you test the monitors with controlled shifts?
- How did you stop the LLM from inventing numbers in the memo? (computed recommendation, grounding validator, evals)
- How does your CI/CD reach AWS without stored keys, and what are the IAM boundaries?

---

## Appendix A. `CLAUDE.md` to put at the repo root

```markdown
# Project: Credit Risk Platform on AWS (upgrade of Credit Scoring & Risk Analysis)

Source of truth for scope and phases: `docs/technical-sheet.md` (copy of the technical sheet).

## Rules
- LEARNING PROTOCOL (highest priority, overrides speed): before every step that writes, installs, runs code, calls a cloud or LLM API or may cost money, explain in plain language what you will do, why, which files/resources it touches, the exact commands, the risks and how to undo it; then WAIT for my explicit yes. A yes covers only the steps listed in that message. After each step, explain what happened and what I should learn. At the end of each phase, ask me 2 to 3 questions to check I understood. Define technical terms at first use. Reading and searching are allowed without asking, but say what you read and why.
- Read the repo before changing it. If the repo contradicts the sheet, the repo wins; report the difference.
- Never invent metrics. Results come only from logged runs. Use TBD otherwise.
- Never commit data, secrets or access keys. CI uses GitHub OIDC with an IAM role. Never create access keys for the AWS root user.
- Ask before any action that may cost money. Athena queries run in a workgroup with a per-query scan limit. Phases 1 and 2 run locally first (DuckDB + Parquet); cloud code stays in a thin layer.
- Assumptions (LGD, margin, score scaling) live in config/assumptions.yaml and are labelled as assumptions.
- The memo agent is read-only; its recommendation is computed by code; a validator checks every number.
- Work one phase at a time; stop at each gate with a short summary of measured results.
- Imbalance: unweighted model is the PD baseline; class weights and SMOTE are ablations; always calibrate on the separate calibration split.
- Section numbers in docs/technical-sheet.md are authoritative (the PDF fiche numbers differ).
- This repo was imported from Aymannel04/credit_scoring_project (v1). Never push to, or open PRs on, the v1 repo; this repo has no remote to it.
- Code comments are in French today; docs and README must be in English.

## Commands (fill in as they are created)
- Lint and test: `ruff check . && pytest -q`
- Run pipeline locally: `dagster dev`
- Materialise assets: `dagster asset materialize --select '*'`
- Run API locally: `uvicorn service.main:app --reload`
```

## Appendix B0. Create the new repository (you do this, about 2 minutes)

1. On GitHub, create an **empty** repository named `credit-risk-platform` (no README, no license, no .gitignore).
2. In a terminal:

```bash
git clone https://github.com/Aymannel04/credit_scoring_project credit-risk-platform
cd credit-risk-platform
git remote remove origin          # cut every link to the v1 repo
git remote add origin https://github.com/Aymannel04/credit-risk-platform.git
git branch -M main
git push -u origin main
```

This keeps v1's history inside the new repo and leaves the original repo and its demo untouched. If you prefer a clean history with no pickles or processed CSVs in it, run `rm -rf .git && git init` instead of the `remote` commands, then commit with a message like "Import v1 snapshot from credit_scoring_project".

3. Open the new repo in Claude Code or Cowork, add `CLAUDE.md` (Appendix A) and the sheet as `docs/technical-sheet.md`, then run the kickoff prompt below.

## Appendix B. Kickoff prompt for Claude Code or Cowork

```text
Read CLAUDE.md and docs/technical-sheet.md (section 3 is an audit of the v1 code from Oct 8, 2026).
Follow the learning protocol in CLAUDE.md strictly: before every step, explain in detail what you will do and why, and wait for my explicit permission; after every step, explain what happened and what I should learn.
This repository was imported from github.com/Aymannel04/credit_scoring_project (v1). Never push to or open PRs on that repo.
Do Phase 0 only:
1) re-verify section 3 against the code you can see and report any difference,
2) on a new branch v2-prep, do the quick wins in section 3.4: UTF-8 pinned requirements, seeds, .gitignore, ruff, a few pytest tests on the German Credit fixture, untrack the committed pickles and processed CSVs, and re-run the pipeline to log real metrics,
3) compare unweighted vs class weights vs SMOTE, each raw and calibrated (cross-validated calibration), on the German Credit data (reliability curve and Brier score) and show me the result,
4) list exactly what I must verify from section 14.
Do not create any cloud resource (I secure the AWS account and create the budget alert myself; guide me if I ask). Do not push anything without asking me. Stop and summarise.
```

## Appendix C. Phase checklists (tick as you go)

**Phase 1**
- [ ] `scripts/download_data.py` and `.gitignore` for data
- [ ] Local first: Parquet + DuckDB layers; then `infra/setup_aws.sh` (S3 buckets, Glue databases, IAM roles, GitHub OIDC provider)
- [ ] Raw load into the `credit_raw` schema; staging SQL; feature SQL; feature catalog
- [ ] Pandera and SQL checks; leakage test; German Credit fixture in CI
- [ ] Dagster assets and a failing-input demo

**Phase 2**
- [ ] Four-way split and CV; scorecard; unweighted boosting; class-weights and SMOTE ablations
- [ ] Calibration; metrics with bootstrap intervals; reliability curves
- [ ] Cost matrix, threshold, sensitivity grid; EL by band
- [ ] Fairness slices; SHAP; reason codes; model card; `model_runs` row

**Phase 3**
- [ ] FastAPI service, tests, Dockerfile; Lambda deploy via CI
- [ ] Evidently reports; simulated drift scenarios and detection table
- [ ] Scheduler plus retrain job; Streamlit page

**Phase 4**
- [ ] Tools, memo schema, validator, evaluation set, seeded-error test

**Phase 5**
- [ ] README, demo video, decision log, risk register, CV update, cost cleanup
