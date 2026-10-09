"""Ablation tests on synthetic data with a ~3% default rate."""
import numpy as np
import pandas as pd
import pytest

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit.models import metrics
from credit.models.ablation import fit_variant
from credit.models.calibration import PlattCalibrator


def _synthetic(n=8000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    for c in CATEGORICAL_FEATURES:
        df[c] = rng.choice(["A", "B", "C"], size=n)
    logit = -4.2 + 1.2 * df[NUMERIC_FEATURES[0]]
    df["default_24m"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


@pytest.fixture(scope="module")
def data():
    return _synthetic(seed=0), _synthetic(seed=1), _synthetic(seed=2)


def test_resampling_and_weights_inflate_probabilities_and_platt_repairs_them(data):
    train, cal, test = data
    real = test["default_24m"].mean()
    X_te, y_te = test.drop(columns="default_24m"), test["default_24m"].to_numpy()
    mean_pd, brier_raw, brier_fixed = {}, {}, {}
    for kind in ("unweighted", "class_weights", "smote"):
        b = fit_variant(train, kind, n_trees=60)
        p_te = b.predict_proba(X_te)
        platt = PlattCalibrator().fit(b.predict_proba(cal.drop(columns="default_24m")), cal["default_24m"])
        mean_pd[kind] = p_te.mean()
        brier_raw[kind] = metrics.brier(y_te, p_te)
        brier_fixed[kind] = metrics.brier(y_te, platt.predict(p_te))
    assert abs(mean_pd["unweighted"] - real) < 0.015  # honest on average
    assert mean_pd["class_weights"] > 3 * real  # inflated
    assert mean_pd["smote"] > 3 * real  # inflated
    for kind in ("class_weights", "smote"):
        assert brier_fixed[kind] < brier_raw[kind]  # calibration repairs the damage


def test_unknown_variant_is_rejected(data):
    with pytest.raises(ValueError):
        fit_variant(data[0], "magic", n_trees=5)
