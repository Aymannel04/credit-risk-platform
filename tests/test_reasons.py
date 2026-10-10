"""Reason codes and SHAP mapping tests."""
import numpy as np
import pandas as pd
import pytest

from credit.freddie.features import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from credit.models import reasons as rs
from credit.models.explain import original_feature
from credit.models.scorecard import Scorecard, load_config


def _data(n=30000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    for c in CATEGORICAL_FEATURES:
        df[c] = rng.choice(["A", "B", "C"], size=n)
    logit = -3.5 + 1.0 * df[NUMERIC_FEATURES[0]] - 0.7 * df[NUMERIC_FEATURES[1]] + 0.6 * (df[CATEGORICAL_FEATURES[0]] == "A")
    return df, pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int))


@pytest.fixture(scope="module")
def sc():
    X, y = _data()
    return Scorecard(load_config()).fit(X, y), X


def test_every_feature_has_a_fixed_sentence_and_a_unique_code():
    table = rs.load_reason_table()
    assert set(table) <= set(FEATURES) | {"several_borrowers"}  # v2 adds one input
    codes = [v["code"] for v in table.values()]
    assert len(codes) == len(set(codes))
    assert all(len(v["phrase"]) > 10 for v in table.values())


def test_points_lost_plus_points_kept_equals_the_best_total(sc):
    card, X = sc
    pts, _ = rs.points_per_feature(card, X.head(500))
    best = rs.best_points(card)
    lost = sum(best[c] - pts[c] for c in card.selected_)
    best_total = sum(best.values())
    # the score of a loan = (sum of its points) and the best possible score = best_total: the gap IS the points lost
    assert np.allclose(pts.sum(axis=1) + lost, best_total)


def _full_table():
    return {f: {"code": f"R{i:02d}", "phrase": f"fixed sentence about {f}"} for i, f in enumerate(FEATURES)}


def test_reasons_are_sorted_deterministic_and_use_only_fixed_text():
    X, y = _data()
    card = Scorecard(load_config()).fit(X, y)
    table = _full_table()
    out1 = rs.reasons(card, X.head(300), top_k=3, reason_table=table)
    out2 = rs.reasons(card, X.head(300), top_k=3, reason_table=table)
    assert out1 == out2
    allowed = {v["phrase"] for v in table.values()}
    for loan in out1:
        assert len(loan) <= 3
        assert [r["points_lost"] for r in loan] == sorted((r["points_lost"] for r in loan), reverse=True)
        assert all(r["phrase"] in allowed and r["points_lost"] > 0 for r in loan)


def test_a_safe_loan_gets_fewer_or_smaller_reasons_than_a_risky_one(sc):
    card, X = sc
    p = card.predict_proba(X)
    safe, risky = X.iloc[[int(np.argmin(p))]], X.iloc[[int(np.argmax(p))]]
    s = sum(r["points_lost"] for r in rs.reasons(card, safe, top_k=10, reason_table=_full_table())[0])
    r_ = sum(r["points_lost"] for r in rs.reasons(card, risky, top_k=10, reason_table=_full_table())[0])
    assert s < r_


def test_original_feature_mapping():
    assert original_feature("num__credit_score") == "credit_score"
    assert original_feature("num__missingindicator_dti") == "dti"
    assert original_feature("cat__state_CA") == "state"
    assert original_feature("cat__first_time_homebuyer_Y") == "first_time_homebuyer"
    assert original_feature("cat__super_conforming_infrequent_sklearn") == "super_conforming"
    with pytest.raises(ValueError):
        original_feature("num__nonsense")


def test_a_feature_without_an_approved_sentence_is_an_error(sc):
    card, X = sc
    table = _full_table()
    del table[card.selected_[0]]
    with pytest.raises(ValueError, match="no approved reason sentence"):
        rs.reasons(card, X.head(3), reason_table=table)


def test_non_reportable_features_and_tiny_losses_are_never_shown(sc):
    card, X = sc
    table = _full_table()
    worst = card.selected_[0]
    table[worst]["reportable"] = False
    out = rs.reasons(card, X.head(300), top_k=10, reason_table=table, min_points_lost=5.0)
    for loan in out:
        assert all(r["feature"] != worst for r in loan)
        assert all(r["points_lost"] >= 5.0 for r in loan)
