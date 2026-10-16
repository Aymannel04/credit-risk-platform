# CV lines, pitches and forum kit

Every number below comes from a result file in this repository (see the README table). A bracketed placeholder would mark a number that does not exist yet: do not quote it until it does. (The Lambda latency was measured on 2026-10-13: `results/lambda_latency.md`.)

## 1. The one-sentence headline

- **Data / AI engineering version:** *Credit-risk platform on AWS: reproducible Dagster pipeline, tested scoring API in a container on Lambda, drift monitors validated with simulated shifts.*
- **ML / data science version:** *Mortgage-default scorecard validated honestly: frozen model, pre-registered success rules, 4 unseen vintages (177k loans), flaws measured and published.*

## 2. CV bullets (pick 3 to 4; keep the verbs, trim the details to fit)

**Data / AI engineering**
1. Built a reproducible **Dagster** pipeline (raw → staging → features → model → monitoring) on Freddie Mac loan-level data (450k loans, 9 vintages) with blocking data-quality checks and hash-based splits; a full rebuild reproduces the same data and model (row fingerprint, model id).
2. Served the model through a strict **FastAPI** service (typed validation, no decision logic, no data stored) packaged as a 51 MB **Docker** image on **AWS Lambda** behind a signature-protected Function URL, with a least-privilege IAM role and scripted infrastructure (dry-run, idempotent, teardown).
3. **CI** with 307 automated tests that also builds the container, checks its exact contents and smoke-tests it; immutable, commit-tagged images.
4. Drift monitoring (**PSI/CSI**, level ratio) validated with simulated-shift drills: 7/7 expected alerts caught, 2 blind spots documented. Measured on the live Lambda: **2.7 ms** median warm request (p95 3.0 ms), **about 1.2 s** cold start, **78 MB** of 512 MB used.

**ML / data science**
1. Built a calibrated **WoE scorecard** (and logistic/XGBoost comparisons) for 24-month mortgage default on 450k Freddie Mac loans; reason codes in fixed sentences; the readable model is statistically indistinguishable from XGBoost.
2. Evaluated with a **frozen, pre-registered protocol** on 4 unseen vintages (177k loans): Gini 0.54 to 0.63 with paired-bootstrap intervals; v2 beat v1 by +0.024 Gini (95% CI +0.013 to +0.035).
3. Found and **documented a 1.4 to 2.6x calm-year over-prediction**; tested a recalibration fix and rejected it by a rule written beforehand; tested "drop 2008" and showed the average hides a 4x crisis under-prediction.
4. Slice-level fairness and calibration analysis and an expected-loss cut-off under **stated assumptions** (no protected attributes in the data; limits written down).

**One-line version for a crowded CV:** *Credit-risk platform (Freddie Mac, 450k loans): Dagster pipeline, calibrated WoE scorecard validated on 4 unseen vintages (Gini 0.54 to 0.63), FastAPI + Docker on AWS Lambda, PSI/CSI drift monitors with tested alarms.*

## 3. The 30-second pitch

"I built a credit-risk platform on real mortgage data. A Dagster pipeline turns 450,000 loans into a scorecard that predicts default, served by an API in a container on AWS. What I'm proudest of is the honesty: I froze the model and wrote the success rules *before* testing it on four years it had never seen, then published the flaw I found: it over-predicts defaults by one and a half to two and a half times in calm years. I tested a fix, and my own rule rejected it."

## 4. The 2-minute pitch (the order matters: problem, build, honesty, cloud, limits)

1. **Problem (15 s).** A bank wants the probability that a new mortgage goes seriously delinquent within two years, using only what is known at origination. I used Freddie Mac's public loan-level data: nine yearly samples, 450,000 loans.
2. **Build (30 s).** A Dagster pipeline: raw, staging, features, model, with checks that stop the chain if data is wrong. The model is a points-based scorecard (weight of evidence plus logistic regression), compared with XGBoost. Every decision is in a decision log, including my mistakes.
3. **Honesty (35 s).** I froze the model and committed the success rules first, then tested on four unseen vintages, 177,000 loans: Gini between 0.54 and 0.63. The scorecard and XGBoost were statistically tied, so I kept the readable one. The model over-predicts defaults in calm years, because the 2008 crisis anchors its level. I tested "recalibrate from history": it cut the average error by 31% but got worse at turning points, so my pre-written rule rejected it. I also showed that simply deleting 2008 makes calm years look better but under-predicts the crisis four times.
4. **Cloud (25 s).** The model is a 7 KB JSON file; the API is FastAPI in a 51 MB Docker image on Lambda, behind a signature-protected URL, with a role that can only write its own logs. CI runs 307 tests and smoke-tests the container. A warm request costs about 3 ms of compute; a cold start about 1.2 seconds, measured. Monitors for drift were tested with simulated shifts: 7 of 7 expected alerts caught, two subtle ones missed, reported.
5. **Limits (15 s).** It's a portfolio project, not a lending product: deployment is automatic but has no automatic rollback, and the next steps are a read-only memo agent and a macro-aware level.

## 5. LinkedIn "Projects" blurb (3 lines)

Credit Risk Platform: an honestly validated mortgage-default model on 450k Freddie Mac loans, served on AWS Lambda.
Dagster pipeline with blocking checks; WoE scorecard vs XGBoost; frozen, pre-registered evaluation on 4 unseen vintages (Gini 0.54 to 0.63); PSI/CSI monitors tested with simulated shifts.
Python · Dagster · DuckDB · scikit-learn · XGBoost · FastAPI · Docker · AWS Lambda/ECR/IAM · GitHub Actions. Code and decision log: github.com/Aymannel04/credit-risk-platform

## 6. GitHub "About" box

- Description (under 350 characters): *Credit-risk platform on real Freddie Mac mortgage data: Dagster pipeline, calibrated WoE scorecard validated on unseen years with pre-registered rules, FastAPI on AWS Lambda, drift monitors tested with simulated shifts.*
- Topics: `credit-risk` `machine-learning` `data-engineering` `mlops` `dagster` `fastapi` `docker` `aws-lambda` `scorecard` `model-validation` `duckdb` `python`

## 7. Forum kit (what to have on your phone)

1. The repository page (README top: the results table and the diagram) as a bookmark.
2. `docs/monitoring.png` saved as a picture: it shows the flaw and the failed fix in one image.
3. Three sentences you can say anywhere: the 30-second pitch above.
4. **Do not claim:** "CI/CD deploys to AWS" (deploy is scripted by hand), "Evidently" (own PSI code), "production" or "real-time retraining", a public demo, or a latency number without its context: quote the server-side 2.7 ms warm and about 1.2 s cold-start figures, and say that the 0.68 s round trip from your laptop is mostly network.
5. If asked something you do not know: "I haven't done that yet; here is how I would approach it" is a strong answer. The honest-limits section of the README is your safety net.

## 8. Good questions to ask a recruiter or engineer at the forum

- "How does your team validate a model before it goes live, and who can say no?"
- "What happens when an input feed drifts: who gets the alert and what is the first thing they check?"
- "Do your data engineers and data scientists share the pipeline, or hand work over?"
