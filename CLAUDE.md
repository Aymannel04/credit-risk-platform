# Project: Credit Risk Platform on GCP (upgrade of Credit Scoring & Risk Analysis)

Source of truth for scope and phases: `docs/technical-sheet.md` (copy of the technical sheet).

## Rules
- LEARNING PROTOCOL (highest priority, overrides speed): before every step that writes, installs, runs code, calls a cloud or LLM API or may cost money, explain in plain language what you will do, why, which files/resources it touches, the exact commands, the risks and how to undo it; then WAIT for my explicit yes. A yes covers only the steps listed in that message. After each step, explain what happened and what I should learn. At the end of each phase, ask me 2 to 3 questions to check I understood. Define technical terms at first use. Reading and searching are allowed without asking, but say what you read and why.
- Read the repo before changing it. If the repo contradicts the sheet, the repo wins; report the difference.
- Never invent metrics. Results come only from logged runs. Use TBD otherwise.
- Never commit data, secrets or service-account keys. CI uses Workload Identity Federation.
- Ask before any action that may cost money. Every BigQuery job sets maximum_bytes_billed.
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
