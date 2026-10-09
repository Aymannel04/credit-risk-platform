"""Tests for the metrics and the data guard (made-up data only)."""
import numpy as np
import pandas as pd
import pytest

from credit.freddie.features import CATEGORICAL_FEATURES, FEATURES, LABELS, META, NUMERIC_FEATURES
from credit.models import metrics
from credit.models.data import load, make_preprocessor, xy


def test_perfect_ranking():
    y = np.array([0, 0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.3, 0.8, 0.9])
    assert metrics.auc(y, p) == 1.0
    assert metrics.gini(y, p) == 1.0
    assert metrics.ks(y, p) == 1.0


def test_random_scores_are_a_coin_flip():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 20000)
    p = rng.random(20000)
    assert metrics.auc(y, p) == pytest.approx(0.5, abs=0.02)
    assert abs(metrics.gini(y, p)) < 0.04


def test_gini_is_two_auc_minus_one():
    rng = np.random.default_rng(1)
    y = rng.integers(0, 2, 500)
    p = np.clip(y * 0.3 + rng.random(500) * 0.7, 0, 1)
    assert metrics.gini(y, p) == pytest.approx(2 * metrics.auc(y, p) - 1)


def test_brier_rewards_honest_percentages():
    rng = np.random.default_rng(2)
    p_true = rng.random(50000) * 0.2
    y = (rng.random(50000) < p_true).astype(int)
    honest = metrics.brier(y, p_true)
    too_high = metrics.brier(y, np.clip(p_true * 2, 0, 1))
    assert honest < too_high


def test_calibration_table_shape():
    rng = np.random.default_rng(3)
    p = rng.random(1000)
    y = (rng.random(1000) < p).astype(int)
    t = metrics.calibration_table(y, p, n_bins=10)
    assert len(t) == 10 and t["loans"].sum() == 1000
    assert (t["predicted"].diff().dropna() > 0).all()  # bins ordered by risk


def _toy_features(path):
    rows = []
    for i, split in enumerate(["train", "validation", "test_in_time", "test_oot_2019"] * 5):
        r = {c: None for c in META + FEATURES + LABELS}
        r.update(loan_seq=f"F16Q1{i:07d}", vintage_year=2016, vintage_quarter=1, default_24m=i % 2,
                 default_24m_all_late=0, default_24m_loss_only=0, split=split)
        for c in NUMERIC_FEATURES:
            r[c] = float(i)
        for c in CATEGORICAL_FEATURES:
            r[c] = "A"
        rows.append(r)
    pd.DataFrame(rows).to_parquet(path)


def test_test_splits_are_locked(tmp_path):
    p = tmp_path / "f.parquet"
    _toy_features(p)
    assert set(load("train", path=p)["split"]) == {"train"}
    for locked in ("test_in_time", "test_oot_2019", "test_oot_2022"):
        with pytest.raises(PermissionError):
            load(locked, path=p)
    assert len(load("test_in_time", path=p, allow_test=True)) == 5
    with pytest.raises(ValueError):
        load("nonsense", path=p)


def test_xy_uses_only_feature_columns(tmp_path):
    p = tmp_path / "f.parquet"
    _toy_features(p)
    X, y = xy(load("train", path=p))
    assert list(X.columns) == FEATURES
    assert not set(X.columns) & set(LABELS + META)
    assert set(y) <= {0, 1}


def test_preprocessor_handles_missing_and_unseen_categories():
    train = pd.DataFrame({**{c: [1.0, 2.0, np.nan, 4.0] * 30 for c in NUMERIC_FEATURES},
                          **{c: ["A", "B", None, "A"] * 30 for c in CATEGORICAL_FEATURES}})
    prep = make_preprocessor().fit(train)
    new = train.head(3).copy()
    new[CATEGORICAL_FEATURES[0]] = ["NEW", "A", None]
    out = prep.transform(new)
    assert out.shape[0] == 3 and not np.isnan(np.asarray(out.todense() if hasattr(out, "todense") else out)).any()
