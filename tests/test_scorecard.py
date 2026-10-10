"""Scorecard tests on synthetic data with a known relationship."""
import numpy as np
import pandas as pd
import pytest

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit.models import metrics
from credit.models.scorecard import Scorecard, fit_bins, load_config


def _data(n=30000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    for c in CATEGORICAL_FEATURES:
        df[c] = rng.choice(["A", "B", "C"], size=n)
    # risk rises with feature 0, falls with feature 1; category A of the first categorical is riskier
    logit = -3.5 + 1.0 * df[NUMERIC_FEATURES[0]] - 0.7 * df[NUMERIC_FEATURES[1]] + 0.6 * (df[CATEGORICAL_FEATURES[0]] == "A")
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int))
    df.loc[rng.random(n) < 0.04, NUMERIC_FEATURES[0]] = np.nan  # some missing values
    return df, y


@pytest.fixture(scope="module")
def fitted():
    X, y = _data(seed=0)
    return Scorecard(load_config()).fit(X, y), X, y


def test_informative_features_have_high_iv_and_noise_is_dropped(fitted):
    sc, _, _ = fitted
    assert sc.bins_[NUMERIC_FEATURES[0]].iv > 0.1
    assert sc.bins_[NUMERIC_FEATURES[1]].iv > 0.05
    # pure noise: below the keep-threshold (which is set above the IV that noise reaches by chance)
    assert sc.bins_[NUMERIC_FEATURES[5]].iv < load_config()["scorecard_binning"]["min_iv"]
    assert NUMERIC_FEATURES[5] not in sc.selected_
    assert NUMERIC_FEATURES[0] in sc.selected_


def test_woe_signs_follow_the_risk(fitted):
    sc, _, _ = fitted
    t = sc.bins_[NUMERIC_FEATURES[0]].table
    t = t[t["band"] != "missing"]
    # feature 0 raises risk: the lowest band must be safer (higher WoE) than the highest band
    assert t["woe"].iloc[0] > t["woe"].iloc[-1]
    cat = sc.bins_[CATEGORICAL_FEATURES[0]].table.set_index("band")["woe"]
    assert cat["A"] < cat["B"] and cat["A"] < cat["C"]


def test_missing_values_and_unseen_categories_get_their_own_band(fitted):
    sc, X, _ = fitted
    fb = sc.bins_[NUMERIC_FEATURES[0]]
    assert fb.table["band"].iloc[-1] == "missing" and fb.table["n"].iloc[-1] > 0
    new = X.head(3).copy()
    new[CATEGORICAL_FEATURES[0]] = ["NEVER_SEEN", "A", None]
    p = sc.predict_proba(new)
    assert len(p) == 3 and ((p > 0) & (p < 1)).all()


def test_no_sign_violations_and_good_ranking(fitted):
    sc, _, _ = fitted
    assert sc.sign_violations() == []
    X2, y2 = _data(seed=1)
    assert metrics.auc(y2, sc.predict_proba(X2)) > 0.75


def test_points_follow_the_pdo_convention(fitted):
    sc, X, _ = fitted
    cfg = load_config()["scorecard_scaling"]
    pts = sc.score(X.head(2000))
    p = sc.predict_proba(X.head(2000))
    odds_good = (1 - p) / p
    # score = offset + factor * ln(odds): +20 points <=> odds double
    factor = cfg["points_to_double_odds"] / np.log(2)
    expected = cfg["base_score"] + factor * (np.log(odds_good) - np.log(cfg["base_odds"]))
    assert np.allclose(pts, expected, atol=1e-6)
    # a higher score always means a lower probability of default
    order = np.argsort(pts)
    assert (np.diff(p[order]) <= 1e-12).all()


def test_points_table_adds_up_to_the_score(fitted):
    sc, X, _ = fitted
    table = sc.points_table()
    row = X.iloc[[0]]
    total = 0.0
    for c in sc.selected_:
        fb = sc.bins_[c]
        band = fb.band_labels()[int(fb.assign(row[c])[0])]
        total += float(table[(table["feature"] == c) & (table["band"] == band)]["points"].iloc[0])
    assert total == pytest.approx(float(sc.score(row)[0]), abs=1e-6)


def test_bin_edges_respect_the_minimum_share():
    X, y = _data(n=20000, seed=3)
    cfg = load_config()
    bins = fit_bins(X, y, cfg)
    min_n = cfg["scorecard_binning"]["min_bin_share"] * len(X)
    t = bins[NUMERIC_FEATURES[0]].table
    assert (t[t["band"] != "missing"]["n"] >= min_n * 0.99).all()


def test_a_band_never_seen_in_training_is_neutral_not_terrible(fitted):
    card, X, _ = fitted
    cat = CATEGORICAL_FEATURES[0]
    assert card.bins_[cat].table.set_index("band").loc["other", "n"] == 0  # no rare category in this data
    assert card.bins_[cat].table.set_index("band").loc["other", "woe"] == 0.0
    new = X.head(1).copy()
    new[cat] = "NEVER_SEEN"
    known = X.head(1).copy()
    p_unseen, p_known = card.predict_proba(new)[0], card.predict_proba(known)[0]
    assert abs(p_unseen - p_known) < 0.2  # an unseen value moves the risk a little, it does not explode it
