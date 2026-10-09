"""XGBoost model: many small decision trees, each correcting the previous ones.

Unweighted on purpose (probabilities must match the real default rate). Early stopping watches a
slice of the TRAINING data (an inner holdout), never the validation split, so validation stays an
honest mock exam. The test splits stay locked.

Usage (from the repo root):  .venv/Scripts/python -m credit.models.xgboost_model
"""
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import xgboost
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from credit.models import metrics
from credit.models.data import TARGET, load, make_preprocessor, xy

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
SEED = 42

PARAMS = dict(
    n_estimators=600,  # upper limit; early stopping decides the real number
    learning_rate=0.05,  # small steps: each tree corrects only a little
    max_depth=3,  # shallow trees: harder to memorise the training data
    min_child_weight=5,  # a leaf needs enough loans behind it
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,  # penalty against extreme predictions
    eval_metric="logloss",
    early_stopping_rounds=40,
    random_state=SEED,
    n_jobs=4,
)


@dataclass
class Bundle:
    prep: object
    model: XGBClassifier
    best_iteration: int

    def predict_proba(self, X: pd.DataFrame):
        return self.model.predict_proba(self.prep.transform(X))[:, 1]


def fit(train: pd.DataFrame, params: dict | None = None) -> Bundle:
    """Fit on a training dataframe only. 15% of it is held out inside, for early stopping."""
    X, y = xy(train)
    X_in, X_hold, y_in, y_hold = train_test_split(X, y, test_size=0.15, stratify=y, random_state=SEED)
    prep = make_preprocessor().fit(X_in)  # preprocessing learns from the inner training part only
    model = XGBClassifier(**(params or PARAMS))
    model.fit(prep.transform(X_in), y_in, eval_set=[(prep.transform(X_hold), y_hold)], verbose=False)
    return Bundle(prep=prep, model=model, best_iteration=int(model.best_iteration))


def main() -> dict:
    train, valid = load("train"), load("validation").reset_index(drop=True)
    X_tr, y_tr = xy(train)
    X_va, y_va = xy(valid)
    bundle = fit(train)
    p_tr, p_va = bundle.predict_proba(X_tr), bundle.predict_proba(X_va)
    result = {
        "model": "xgboost_unweighted",
        "xgboost_version": xgboost.__version__,
        "seed": SEED,
        "params": {k: v for k, v in PARAMS.items()},
        "trees_used": bundle.best_iteration + 1,
        "train": metrics.evaluate(y_tr, p_tr),
        "validation": metrics.evaluate(y_va, p_va),
        "validation_by_vintage": {
            int(v): metrics.evaluate(g[TARGET].astype(int), p_va[g.index.to_numpy()])
            for v, g in valid.groupby("vintage_year")
            if g[TARGET].sum() >= 20
        },
        "note": "raw (uncalibrated) probabilities; test splits not used; pooled metrics are inflated by the era mix",
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "xgboost_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

    base_path = RESULTS / "baseline_validation.json"
    base = json.loads(base_path.read_text(encoding="utf-8")) if base_path.exists() else None
    print(f"XGBoost used {result['trees_used']} trees (early stopping on an inner holdout of the training data)")
    header = f"{'':32s}{'AUC':>7s}{'Gini':>7s}{'KS':>7s}{'PR-AUC':>8s}{'Brier':>9s}{'mean PD':>9s}{'real':>8s}"
    print(header)

    def row(label, m):
        print(f"{label:32s}{m['auc']:7.3f}{m['gini']:7.3f}{m['ks']:7.3f}{m['pr_auc']:8.3f}{m['brier']:9.5f}"
              f"{m['mean_predicted_pd']:9.4f}{m['default_rate']:8.4f}")

    if base:
        row("logistic   train", base["train"])
    row("xgboost    train", result["train"])
    if base:
        row("logistic   validation", base["validation"])
    row("xgboost    validation", result["validation"])
    for v, m in result["validation_by_vintage"].items():
        if base and str(v) in {str(k) for k in base["validation_by_vintage"]}:
            row(f"logistic   validation {v}", base["validation_by_vintage"][str(v)])
        row(f"xgboost    validation {v}", m)
    return result


if __name__ == "__main__":
    main()
