"""Opening result of v2: does the way we handle imbalance distort the probabilities?

Compares three XGBoost variants on German Credit, each raw and calibrated (Platt scaling,
fitted with 5-fold cross-validation inside each training fold):
  - unweighted      : natural 30% default rate
  - class weights   : scale_pos_weight = n_good / n_bad
  - SMOTE           : synthetic defaulters until 50/50 (inside the pipeline, train folds only)
Predictions are out-of-fold over all 1,000 rows, repeated with 3 seeds.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from imblearn.pipeline import Pipeline
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parent.parent
SEEDS = [42, 43, 44]


def load() -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(ROOT / "tests" / "fixtures" / "german_credit.csv")
    X, y = df.drop(columns="target").copy(), df["target"]
    for col in X.select_dtypes(include=["object", "str"]).columns:
        X[col] = LabelEncoder().fit_transform(X[col])
    return X, y


def xgb(seed: int, scale_pos_weight: float = 1.0) -> XGBClassifier:
    return XGBClassifier(
        n_estimators=100, learning_rate=0.1, max_depth=5, eval_metric="logloss",
        random_state=seed, scale_pos_weight=scale_pos_weight,
    )


def variants(seed: int, y: pd.Series) -> dict:
    spw = (y == 0).sum() / (y == 1).sum()
    return {
        "unweighted": xgb(seed),
        "class weights": xgb(seed, spw),
        "SMOTE": Pipeline([("smote", SMOTE(random_state=seed)), ("xgb", xgb(seed))]),
    }


def main() -> None:
    X, y = load()
    rows, curves = [], {}
    for seed in SEEDS:
        cv = StratifiedKFold(5, shuffle=True, random_state=seed)
        for name, model in variants(seed, y).items():
            for kind in ("raw", "calibrated"):
                est = model
                if kind == "calibrated":
                    est = CalibratedClassifierCV(model, method="sigmoid", cv=5)
                p = cross_val_predict(est, X, y, cv=cv, method="predict_proba")[:, 1]
                rows.append({
                    "variant": name, "kind": kind, "seed": seed,
                    "brier": brier_score_loss(y, p), "auc": roc_auc_score(y, p),
                    "mean_pd": p.mean(),
                })
                if seed == SEEDS[0]:
                    curves[(name, kind)] = p

    res = pd.DataFrame(rows)
    summ = res.groupby(["variant", "kind"]).agg(
        brier=("brier", "mean"), brier_sd=("brier", "std"),
        auc=("auc", "mean"), mean_pd=("mean_pd", "mean"),
    ).round(4)
    print(f"Observed default rate: {y.mean():.3f}  (Brier of constant 0.30 forecast: "
          f"{brier_score_loss(y, np.full(len(y), y.mean())):.4f})")
    print(summ.to_string())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=True)
    for ax, kind in zip(axes, ("raw", "calibrated"), strict=True):
        ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfect")
        for name in ("unweighted", "class weights", "SMOTE"):
            frac, mean_p = calibration_curve(y, curves[(name, kind)], n_bins=8, strategy="quantile")
            ax.plot(mean_p, frac, marker="o", label=name)
        ax.set_title(f"Reliability curve ({kind})")
        ax.set_xlabel("predicted probability of default")
        ax.grid(alpha=0.3)
    axes[0].set_ylabel("observed default rate")
    axes[0].legend()
    fig.tight_layout()
    out = ROOT / "docs" / "calibration_experiment.png"
    fig.savefig(out, dpi=130)
    print(f"Saved {out.name}")


if __name__ == "__main__":
    main()
