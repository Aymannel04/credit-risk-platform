"""Cut-off and profit logic on made-up loans with known answers."""
import numpy as np
import pytest

from credit.economics import cutoff as co


def test_theory_cutoff_formula():
    assert co.theory_cutoff(0.02, 0.10) == pytest.approx(1 / 6)
    assert co.theory_cutoff(0.02, 0.01) == pytest.approx(2 / 3)  # small loss: approve almost everyone
    assert co.theory_cutoff(0.02, 0.20) < co.theory_cutoff(0.02, 0.10)  # bigger loss: stricter line


def test_realised_profit_by_hand():
    y = np.array([0, 0, 1, 0])
    ead = np.array([100.0, 200.0, 100.0, 100.0])
    approve = np.array([True, True, True, False])
    # approved: two good loans earn 2% of 300 = 6; the defaulter loses 10% of 100 = 10 -> 6 - 10 = -4
    assert co.realised_profit(y, ead, approve, margin=0.02, loss=0.10) == pytest.approx(-4.0)
    assert co.realised_profit(y, ead, np.zeros(4, bool), 0.02, 0.10) == 0.0  # refuse all


def test_break_even_pd_matches_the_formula():
    margin, loss = 0.02, 0.10
    t = co.theory_cutoff(margin, loss)
    for p in (t - 0.01, t + 0.01):
        expected = (1 - p) * margin - p * loss
        assert (expected > 0) == (p < t)


def test_perfect_model_refuses_exactly_the_defaulters():
    rng = np.random.default_rng(0)
    n = 5000
    y = (rng.random(n) < 0.05).astype(int)
    p = np.where(y == 1, 0.9, 0.01) + rng.random(n) * 0.001  # a model that knows the future
    ead = np.full(n, 100.0)
    best = co.best_cutoff(p, y, ead, margin=0.02, loss=0.10)
    rep = co.decision_report(p, y, ead, best["threshold"], 0.02, 0.10)
    assert rep["defaults_refused_share"] == pytest.approx(1.0, abs=0.01)
    assert rep["default_rate_approved"] < 0.01
    assert rep["profit_with_line"] > rep["profit_approve_all"]


def test_useless_model_gains_nothing_and_bigger_loss_means_stricter_line():
    rng = np.random.default_rng(1)
    n = 20000
    y = (rng.random(n) < 0.02).astype(int)
    p = rng.random(n) * 0.2  # no information
    ead = np.full(n, 100.0)
    g = co.sensitivity_grid(p, y, ead, margins=[0.02], losses=[0.01, 0.20])
    assert (g["gain_pct_of_exposure"] < 0.0005).all()  # almost nothing to gain from noise
    # with real signal the line gets stricter as the loss grows
    p2 = np.clip(0.02 + (y * 0.15) + rng.normal(0, 0.03, n), 0.001, 0.99)
    g2 = co.sensitivity_grid(p2, y, ead, margins=[0.02], losses=[0.01, 0.20]).set_index("loss")
    assert g2.loc[0.20, "approval_rate"] <= g2.loc[0.01, "approval_rate"]


def test_expected_loss_by_band_adds_up():
    rng = np.random.default_rng(2)
    n = 10000
    p = rng.beta(1.2, 40, n)
    y = (rng.random(n) < p).astype(int)
    ead = rng.uniform(50, 300, n)
    t = co.el_by_band(p, y, ead, loss=0.10)
    assert t["loans"].sum() == n
    assert t["predicted_el"].sum() == pytest.approx((p * 0.10 * ead).sum())
    assert t["observed_el"].sum() == pytest.approx((y * 0.10 * ead).sum())
    assert t["predicted_el"].sum() / t["observed_el"].sum() == pytest.approx(1.0, abs=0.15)  # honest PD: EL matches
