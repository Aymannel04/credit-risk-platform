# Credit Scoring & Risk Analysis 🏦

> **This repository is the v2 work in progress** (credit-risk platform on GCP, see `docs/technical-sheet.md` and `docs/decision-log.md`).
> The original, frozen v1 project is at https://github.com/Aymannel04/credit_scoring_project. This repo keeps v1's code as a starting point and fixes its weaknesses first (Phase 0). Numbers below were re-measured on pinned library versions.

End-to-end ML project predicting credit default risk on the German Credit dataset, with SMOTE-based class imbalance handling, a business-labelled confusion matrix, and SHAP-based explainability.

**🔗 Live Demo (v1, unchanged):** https://creditscoringproject.streamlit.app/

## Overview

A binary classification model that predicts whether a loan applicant is likely to default. The project covers the full pipeline:
**Data acquisition → Preprocessing (encoding, SMOTE, scaling) → Modeling (XGBoost) → Explainability (SHAP) → Deployment (Streamlit).**

This project emphasizes three aspects often missing from student work:
1. **Correct SMOTE application** (training set only, post-split — no data leakage)
2. **Business-labelled evaluation** (false negatives = real money lost). The labels are business-style, but the threshold is still 0.5 and no cost values are used yet; a cost-based threshold is planned in v2
3. **Per-prediction explainability** (SHAP waterfall plots showing why each decision was made)

## Problem Statement

Banks face an asymmetric cost structure when scoring credit applicants:
- **False negative** (predicting "good" for a bad payer) → direct financial loss from default
- **False positive** (predicting "bad" for a good payer) → opportunity cost from refused revenue

A model optimized purely for accuracy ignores this asymmetry. This project frames evaluation around the confusion matrix and AUC — metrics that reflect the actual business problem.

## Dataset

- **Source:** German Credit Data, UCI Machine Learning Repository
- **Volume:** 1,000 clients
- **Class distribution:** 70% good payers / 30% defaulters (imbalanced)
- **Features:** 20 attributes including age, credit amount, duration, checking account status, credit history, loan purpose, employment length, housing, and more

## Pipeline

### 1. Data Acquisition (`src/load_data.py`)
- Downloads raw data from the UCI repository
- Maps the original target encoding (1 = good, 2 = bad) to standard ML convention (0 = good, 1 = bad)
- Saves to `data/raw/german_credit.csv`

### 2. Preprocessing (`src/process.py`)
- **Label encoding** of categorical features (with encoders saved for inference)
- **Train/test split first** (80/20, stratified to preserve class distribution)
- **SMOTE applied to training set only** — preventing data leakage that would inflate metrics
- **StandardScaler fitted on resampled training data**, applied to both train and test (not needed for tree models; kept from v1)
- All artifacts (encoders, scaler) saved as `.pkl` for use in the Streamlit app

### 3. Modeling (`src/model.py`)
- **Algorithm:** XGBoost (`XGBClassifier`)
- **Hyperparameters:** `n_estimators=100`, `learning_rate=0.1`, `max_depth=5`, `random_state=42` (seed added in v2 prep, so runs repeat exactly)
- **Evaluation:** Accuracy, classification report, AUC-ROC, full confusion matrix with business labels

### 4. Explainability & UI (`app/dashboard.py`)
- Streamlit dashboard for individual loan applications
- **SHAP waterfall plot** showing the contribution of each feature to a single client's decision
- Designed for non-technical users (bank officers, not data scientists)

## Results

### Headline Metrics

Re-measured on pinned libraries (see `requirements.txt`) with a fixed seed; raw output in `docs/baseline_run.txt`. The test set is only 200 rows (60 defaulters), so a few points of difference are within noise.

| Metric | Value |
|---|---|
| **AUC-ROC** | **0.8020** |
| Accuracy | 74.00% |

The original v1 README reported AUC 0.8074 and accuracy 76.50%; that run could not be reproduced exactly (libraries were unpinned and XGBoost had no seed). AUC is the more appropriate primary metric: accuracy is misleading on imbalanced data (a "predict good for everyone" model would score 70%).

### Per-Class Performance

| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| Good Client (0) | 0.80 | 0.84 | 0.82 | 140 |
| Bad Client (1)  | 0.57 | 0.52 | 0.54 | 60 |

### Confusion Matrix (labelled in business terms)

| | Predicted Good | Predicted Bad |
|---|---|---|
| **Actual Good** | 117 ✅ True Negative | 23 ❌ False Positive (lost revenue) |
| **Actual Bad**  | 29 💀 False Negative (real loss) | 31 💰 True Positive (default avoided) |

**Key insight:** at the default 0.5 threshold the model catches **52% of actual defaulters** (recall on class 1). Lowering the threshold would catch more defaulters at the cost of refusing more good clients; the right trade-off depends on the real loss ratio per error type, which is not modelled yet.

### A weakness found in v1: the displayed probability is not a calibrated PD

v1 trains on a SMOTE-balanced (50/50) set but shows the model output as a "probability of default" while the real default rate is 30%. A calibration check on the German Credit data (`experiments/calibration_experiment.py`, out-of-fold predictions on all 1,000 rows, 3 seeds; output in `docs/calibration_experiment.txt`):

| Variant | Brier (raw) | Brier (calibrated) | Mean predicted PD (raw) |
|---|---|---|---|
| unweighted | 0.168 | 0.161 | 0.287 |
| class weights | 0.177 | 0.161 | 0.356 |
| SMOTE | 0.176 | 0.162 | 0.338 |

True default rate: 0.300. Lower Brier is better. Calibration (Platt scaling, fitted with cross-validation) improves all three variants, and class weights and SMOTE push the average predicted PD above the true rate. The effect is modest on this small dataset, and the calibrated variants differ by less than the noise. Reliability curves: `docs/calibration_experiment.png`. v2 uses an unweighted model as the PD baseline and always calibrates.

## Limitations & Next Steps

**Known limitations:**
- Hyperparameters not tuned (default-ish values used)
- Decision threshold fixed at 0.5 — not optimized for business cost
- The Streamlit dashboard exposes only ~6 of the 20 features for input simplicity; the rest are hardcoded to mode/mean values, which limits real-world applicability
- No comparison against a baseline model (e.g., Logistic Regression) to quantify XGBoost's added value

**Planned next steps:**
- Hyperparameter tuning with Optuna (target: improve recall on defaulters)
- **Threshold optimization based on a cost matrix** (e.g., if FN cost = 5× FP cost, optimize accordingly)
- Cost-sensitive learning via `scale_pos_weight` as an alternative to SMOTE (a first comparison, including calibration, is in the section above)
- Add a proper Logistic Regression baseline for comparison
- Expand the Streamlit form to capture all 20 features for realistic deployment

## Project Structure

```
├── app/
│   └── dashboard.py            # Streamlit UI with SHAP explanations
├── data/
│   ├── raw/                    # German Credit dataset (UCI)
│   └── processed/              # Generated by src/process.py (not in git)
├── models/                     # Generated by the scripts (not in git):
│   │                           #   credit_xgb_model.pkl, scaler.pkl, encoders.pkl
├── experiments/
│   └── calibration_experiment.py  # SMOTE vs class weights vs unweighted, raw and calibrated
├── tests/                      # pytest tests on the German Credit fixture
├── docs/                       # technical sheet, decision log, baseline run, experiment outputs
├── src/
│   ├── load_data.py            # UCI data acquisition
│   ├── process.py              # Encoding, SMOTE, scaling
│   └── model.py                # XGBoost training & evaluation
└── requirements.txt
```

## How to Run

```bash
# Create an isolated environment and install pinned dependencies
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows; use .venv/bin/python on Linux/macOS

# 1. Download the dataset
python src/load_data.py

# 2. Preprocess (encode, split, SMOTE, scale)
python src/process.py

# 3. Train and evaluate the model
python src/model.py

# 4. Launch the dashboard (needs steps 2 and 3 first: models are not stored in git)
streamlit run app/dashboard.py

# Quality checks
ruff check .
pytest -q
```

## Tech Stack

**Data:** Pandas · NumPy
**Preprocessing:** Scikit-learn (LabelEncoder, StandardScaler) · imbalanced-learn (SMOTE)
**Modeling:** XGBoost
**Explainability:** SHAP
**Deployment:** Streamlit · Joblib · Matplotlib
**Language:** Python 3

## What I Learned

- **Accuracy is misleading on imbalanced datasets** — a 74% accuracy looks decent but only barely beats the "always predict good" baseline of 70%. AUC and recall-on-positives are the metrics that matter.
- **SMOTE must be applied after the train-test split** — applying it before causes data leakage and inflated metrics that collapse in production.
- **Saving preprocessing artifacts is non-negotiable for deployment** — the Streamlit app needs the exact same encoders and scaler used at training time, otherwise predictions are nonsense.
- **Explainability is expected in credit decisioning** and supports auditability and trust. SHAP makes XGBoost explainable on a per-decision basis (it explains the model, not causality).
- **The default 0.5 threshold is rarely optimal** — in production, the threshold should be tuned to the actual cost ratio between false negatives and false positives.
