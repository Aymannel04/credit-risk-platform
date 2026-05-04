# Credit Scoring & Risk Analysis 🏦

End-to-end ML project predicting credit default risk on the German Credit dataset, with proper class imbalance handling, business-framed evaluation, and SHAP-based explainability.

**🔗 Live Demo:** https://creditscoringproject.streamlit.app/

## Overview

A binary classification model that predicts whether a loan applicant is likely to default. The project covers the full pipeline:
**Data acquisition → Preprocessing (encoding, SMOTE, scaling) → Modeling (XGBoost) → Explainability (SHAP) → Deployment (Streamlit).**

This project emphasizes three aspects often missing from student work:
1. **Correct SMOTE application** (training set only, post-split — no data leakage)
2. **Business-framed evaluation** (false negatives = real money lost, not just a metric)
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
- **StandardScaler fitted on resampled training data**, applied to both train and test
- All artifacts (encoders, scaler) saved as `.pkl` for use in the Streamlit app

### 3. Modeling (`src/model.py`)
- **Algorithm:** XGBoost (`XGBClassifier`)
- **Hyperparameters:** `n_estimators=100`, `learning_rate=0.1`, `max_depth=5`
- **Evaluation:** Accuracy, classification report, AUC-ROC, full confusion matrix with business labels

### 4. Explainability & UI (`app/dashboard.py`)
- Streamlit dashboard for individual loan applications
- **SHAP waterfall plot** showing the contribution of each feature to a single client's decision
- Designed for non-technical users (bank officers, not data scientists)

## Results

### Headline Metrics

| Metric | Value |
|---|---|
| **AUC-ROC** | **0.8074** |
| Accuracy | 76.50% |

AUC is the appropriate primary metric here — accuracy is misleading on imbalanced data (a "predict good for everyone" model would score 70%).

### Per-Class Performance

| Class | Precision | Recall | F1-Score | Support |
|---|---|---|---|---|
| Good Client (0) | 0.82 | 0.85 | 0.84 | 140 |
| Bad Client (1)  | 0.62 | 0.57 | 0.59 | 60 |

### Business-Framed Confusion Matrix

| | Predicted Good | Predicted Bad |
|---|---|---|
| **Actual Good** | 119 ✅ True Negative | 21 ❌ False Positive (lost revenue) |
| **Actual Bad**  | 26 💀 False Negative (real loss) | 34 💰 True Positive (default avoided) |

**Key insight:** the model catches **57% of actual defaulters** (recall on class 1) at the default 0.5 threshold. Lowering the threshold would catch more defaulters at the cost of refusing more good clients — a trade-off that depends on the bank's actual loss ratio per error type.

## Limitations & Next Steps

**Known limitations:**
- Hyperparameters not tuned (default-ish values used)
- Decision threshold fixed at 0.5 — not optimized for business cost
- The Streamlit dashboard exposes only ~6 of the 20 features for input simplicity; the rest are hardcoded to mode/mean values, which limits real-world applicability
- No comparison against a baseline model (e.g., Logistic Regression) to quantify XGBoost's added value

**Planned next steps:**
- Hyperparameter tuning with Optuna (target: improve recall on defaulters)
- **Threshold optimization based on a cost matrix** (e.g., if FN cost = 5× FP cost, optimize accordingly)
- Cost-sensitive learning via `scale_pos_weight` as an alternative to SMOTE — and compare
- Add a proper Logistic Regression baseline for comparison
- Expand the Streamlit form to capture all 20 features for realistic deployment

## Project Structure

```
├── app/
│   └── dashboard.py            # Streamlit UI with SHAP explanations
├── data/
│   ├── raw/                    # German Credit dataset (UCI)
│   └── processed/              # Preprocessed train/test splits
├── models/
│   ├── credit_xgb_model.pkl    # Trained XGBoost classifier
│   ├── scaler.pkl              # StandardScaler artifact
│   └── encoders.pkl            # LabelEncoders for categorical features
├── src/
│   ├── load_data.py            # UCI data acquisition
│   ├── process.py              # Encoding, SMOTE, scaling
│   └── model.py                # XGBoost training & evaluation
└── requirements.txt
```

## How to Run

```bash
# Install dependencies
pip install -r requirements.txt

# 1. Download the dataset
python src/load_data.py

# 2. Preprocess (encode, split, SMOTE, scale)
python src/process.py

# 3. Train and evaluate the model
python src/model.py

# 4. Launch the dashboard
streamlit run app/dashboard.py
```

## Tech Stack

**Data:** Pandas · NumPy
**Preprocessing:** Scikit-learn (LabelEncoder, StandardScaler) · imbalanced-learn (SMOTE)
**Modeling:** XGBoost
**Explainability:** SHAP
**Deployment:** Streamlit · Joblib · Matplotlib
**Language:** Python 3

## What I Learned

- **Accuracy is misleading on imbalanced datasets** — a 76.5% accuracy looks decent but only barely beats the "always predict good" baseline of 70%. AUC and recall-on-positives are the metrics that matter.
- **SMOTE must be applied after the train-test split** — applying it before causes data leakage and inflated metrics that collapse in production.
- **Saving preprocessing artifacts is non-negotiable for deployment** — the Streamlit app needs the exact same encoders and scaler used at training time, otherwise predictions are nonsense.
- **Explainability isn't optional in banking** — regulators (Bâle III, GDPR) require model decisions to be interpretable. SHAP makes XGBoost auditable on a per-decision basis.
- **The default 0.5 threshold is rarely optimal** — in production, the threshold should be tuned to the actual cost ratio between false negatives and false positives.
