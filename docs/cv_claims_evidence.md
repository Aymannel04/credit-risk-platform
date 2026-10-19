# CV claims and where each one is proven

The final CV (`AymanElBaida_CV_FINAL_FR.pdf`, English twin `AymanElBaida_Resume_FINAL_EN.pdf`) says only what this table proves. If an interviewer asks "show me", open the file in the right-hand column. Numbers marked "measured" come from a result file written by a run, never typed by hand.

| CV sentence (Credit Risk Platform) | Proof in this repository | Status |
|---|---|---|
| Reproducible Dagster pipeline on 450,000 public mortgage loans (Freddie Mac) | `pipeline/definitions.py`, `pipeline/steps.py`, README "Data" row; tests `tests/test_pipeline.py` | built, tested |
| Blocking data-quality checks | `pipeline/checks.py`; every asset has a blocking check (`test_every_executable_asset_has_a_blocking_check`) | built, tested |
| S3 data lake queryable with Athena, identical results to DuckDB on 6 control queries | `credit/cloud/lake.py`, `scripts/lake_sync.py`, `infra/04_create_lake.ps1`; measured: `results/lake_parity.md` (6 of 6 identical, 20 files, 261.7 MB) | built, measured |
| Interpretable scorecard (WoE) compared with XGBoost, validated on unseen vintages with a protocol frozen in advance | `docs/v2_preregistration.md` (written before the exam), `results/frozen_v2_before_exam.json`, exam: `results/v2_exam.md` | built, measured |
| Gini 0.54 to 0.63 | `results/v2_exam.json`: v2 Gini 0.628 (2010), 0.599 (2014), 0.543 (2018), 0.595 (2023) | measured |
| Drift alerts tested on simulated scenarios | `credit/monitoring/`, `results/monitoring_report.md` (simulated shifts: 7 of 7 expected alerts, 2 subtle shifts missed and reported) | built, measured |
| Containerized FastAPI API on AWS Lambda, signature-protected access | `service/`, `Dockerfile`, `infra/03_create_lambda.ps1` (Function URL with `AWS_IAM`), `results/lambda_latency.md` (warm 2.7 ms, cold start about 1.2 s) | live, measured |
| Automatic deployment with GitHub Actions through OIDC, no stored AWS key | `.github/workflows/deploy.yml`, `infra/05_create_github_deploy.ps1`, `docs/decision-log.md` entries of 2026-10-16 (Deploy runs #3 to #5 green) | live, measured |
| Read-only LLM agent that drafts credit memos | `agent/` (read-only is checked by a test that scans the code: `test_the_agent_package_can_only_write_the_results_and_the_requested_memo_file`) | built, tested |
| The decision is computed by code | `agent/policy.py` (`decide`), the writer never receives the decision lines | built, tested |
| A validator checks every number | `agent/validator.py` (ten checks), `tests/test_agent_validator.py` (every number of every correct memo is changed, one at a time, in both languages: every change must be caught, and the test fails if fewer than 250 numbers were attacked) | built, tested |
| 150 injected errors out of 150 rejected | `results/agent_eval_seeded.md`: 15 loans x 10 kinds of mistake, forced on every try; 0 reached the reader | measured (pretend writers, not a language model) |
| An unverified memo is never published | `agent/memo.py`: the result is either an accepted memo or the memo written by code; the backup is itself inspected (`MemoError` if it ever failed); `test_no_seeded_mistake_ever_reaches_the_reader` | built, tested |

## What the CV deliberately does NOT say
- No pass rate of a language model. The real-model exams exist (`results/agent_eval_*llama*`) and are honest, but they are still being finished; the tuning loans scored better than the held-out loans, and a number must be quoted from the final held-out exam only.
- No "production", no automatic rollback, no public demo, no claim that the API reads from the lake or that monitoring runs live.
- Tools tied only to the removed PipeDoctor project (Databricks, PySpark, Delta Lake, Unity Catalog, Terraform) are not listed.

## What is yours and not checked here
The ESI, HCP, ADII, SAIDA hackathon, SafeSite AI, leadership and distinction lines are your own history. I kept them as you wrote them in your previous versions and did not verify them.
