"""XGBoost wrapper tests on synthetic data with a known signal."""
import numpy as np
import pandas as pd

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit.models import metrics
from credit.models.xgboost_model import PARAMS, fit


def _synthetic(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    for c in CATEGORICAL_FEATURES:
        df[c] = rng.choice(["A", "B", "C"], size=n)
    logit = -3.0 + 1.5 * df[NUMERIC_FEATURES[0]] + 0.8 * (df[CATEGORICAL_FEATURES[0]] == "A")
    df["default_24m"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    df.loc[rng.random(n) < 0.05, NUMERIC_FEATURES[1]] = np.nan  # some missing values
    return df


def test_fit_learns_a_known_signal_and_outputs_probabilities():
    train, test = _synthetic(seed=0), _synthetic(seed=1)
    bundle = fit(train, params={**PARAMS, "n_estimators": 150, "early_stopping_rounds": 20})
    p = bundle.predict_proba(test.drop(columns="default_24m"))
    assert p.min() >= 0 and p.max() <= 1
    assert metrics.auc(test["default_24m"], p) > 0.75
    # unweighted: the average predicted risk stays close to the real default rate
    assert abs(p.mean() - test["default_24m"].mean()) < 0.02


def test_early_stopping_uses_fewer_trees_than_the_limit():
    train = _synthetic(seed=2)
    bundle = fit(train, params={**PARAMS, "n_estimators": 2000, "learning_rate": 0.2, "early_stopping_rounds": 10})
    assert bundle.best_iteration < 1999


def test_unseen_category_and_missing_values_do_not_crash():
    train = _synthetic(seed=3)
    bundle = fit(train, params={**PARAMS, "n_estimators": 50, "early_stopping_rounds": 10})
    new = _synthetic(n=20, seed=4).drop(columns="default_24m")
    new.loc[0, CATEGORICAL_FEATURES[0]] = "NEVER_SEEN"
    new.loc[1, NUMERIC_FEATURES[0]] = np.nan
    assert len(bundle.predict_proba(new)) == 20
