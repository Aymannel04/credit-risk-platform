"""Baseline model: plain logistic regression, no resampling and no class weights.

Trained on `train`, measured on `train` and `validation` only (the mock exam). The test splits stay
locked. Writes results/baseline_validation.json (numbers only, no loan data).

Usage (from the repo root):  .venv/Scripts/python -m credit.models.baseline_logreg
"""
import json
from pathlib import Path

import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from credit.models import metrics
from credit.models.data import TARGET, load, make_preprocessor, xy

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
SEED = 42


def build_model() -> Pipeline:
    return Pipeline(
        [
            ("prep", make_preprocessor()),
            # unweighted on purpose: the output must be a probability that matches the real default rate
            ("clf", LogisticRegression(max_iter=1000, C=1.0, random_state=SEED)),
        ]
    )


def main() -> dict:
    train, valid = load("train"), load("validation").reset_index(drop=True)
    X_tr, y_tr = xy(train)
    X_va, y_va = xy(valid)
    model = build_model().fit(X_tr, y_tr)
    p_va = model.predict_proba(X_va)[:, 1]
    result = {
        "model": "logistic_regression_unweighted",
        "sklearn_version": sklearn.__version__,
        "seed": SEED,
        "train": metrics.evaluate(y_tr, model.predict_proba(X_tr)[:, 1]),
        "validation": metrics.evaluate(y_va, p_va),
        # The pooled number mixes eras (2008 has both high rates and high defaults), so it flatters the model.
        # The honest ranking quality is the one INSIDE each vintage (only vintages with >= 20 defaults).
        "validation_by_vintage": {
            int(v): metrics.evaluate(g[TARGET].astype(int), p_va[g.index.to_numpy()])
            for v, g in valid.reset_index(drop=True).groupby("vintage_year")
            if g[TARGET].sum() >= 20
        },
        "note": "raw (uncalibrated) probabilities; test splits not used; pooled metrics are inflated by the era mix",
    }
    print("by vintage (validation):")
    for v, r_ in result["validation_by_vintage"].items():
        print(f"  {v}: n={r_['n']:,} defaults={r_['defaults']:,} AUC={r_['auc']:.3f} Gini={r_['gini']:.3f} KS={r_['ks']:.3f}")
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "baseline_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for part in ("train", "validation"):
        r = result[part]
        print(
            f"{part:11s} n={r['n']:,} defaults={r['defaults']:,} | AUC={r['auc']:.3f} Gini={r['gini']:.3f} "
            f"KS={r['ks']:.3f} PR-AUC={r['pr_auc']:.3f} Brier={r['brier']:.5f} | "
            f"mean predicted PD={r['mean_predicted_pd']:.4f} vs real {r['default_rate']:.4f}"
        )
    return result


if __name__ == "__main__":
    main()
