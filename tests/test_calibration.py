"""Calibration tests on synthetic data where the true probabilities are known."""
import numpy as np
import pytest

from credit.models import metrics
from credit.models.calibration import IsotonicCalibrator, PlattCalibrator


def _distorted(n=40000, seed=0, power=0.6):
    """True risk p_true; the 'model' reports a distorted version (too high), like an overconfident model."""
    rng = np.random.default_rng(seed)
    p_true = np.clip(rng.beta(1.2, 40, n), 1e-4, 0.9)
    y = (rng.random(n) < p_true).astype(int)
    p_model = np.clip(p_true**power * 1.0, 1e-4, 0.95)  # raising to a power <1 inflates small risks
    return y, p_model


def test_platt_improves_honesty_and_keeps_the_ranking():
    y_cal, p_cal = _distorted(seed=0)
    y_val, p_val = _distorted(seed=1)
    platt = PlattCalibrator().fit(p_cal, y_cal)
    fixed = platt.predict(p_val)
    assert metrics.brier(y_val, fixed) < metrics.brier(y_val, p_val)
    assert metrics.ece(y_val, fixed) < metrics.ece(y_val, p_val)
    assert abs(fixed.mean() - y_val.mean()) < abs(p_val.mean() - y_val.mean())
    assert metrics.auc(y_val, fixed) == pytest.approx(metrics.auc(y_val, p_val), abs=1e-9)  # same order
    assert fixed.min() > 0 and fixed.max() < 1


def test_isotonic_is_monotone_and_in_range():
    y_cal, p_cal = _distorted(seed=2)
    iso = IsotonicCalibrator().fit(p_cal, y_cal)
    grid = np.linspace(0.001, 0.9, 200)
    out = iso.predict(grid)
    assert (np.diff(out) >= -1e-12).all()
    assert out.min() > 0 and out.max() < 1


def test_ece_is_zero_for_perfect_and_positive_for_biased():
    rng = np.random.default_rng(3)
    p = rng.random(50000) * 0.1
    y = (rng.random(50000) < p).astype(int)
    assert metrics.ece(y, p) < 0.003
    assert metrics.ece(y, np.clip(p * 3, 0, 1)) > 0.05
