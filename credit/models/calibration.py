"""Calibration: correct a model's percentages so that "3%" means about 3 defaults out of 100.

Both calibrators are fitted ONLY on the calibration split (loans the model never trained on) and
applied unchanged to validation and, later, to the tests.

  Platt scaling : learns 2 numbers (a slope and an offset) on the log-odds of the raw probability.
                  Keeps the ranking of loans exactly the same. Safe with few defaults.
  Isotonic      : learns a free-form staircase. Flexible, but can overfit when defaults are few
                  (the calibration split has only ~250 defaults) and creates ties in the ranking.
"""
import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-6


def _logit(p):
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


class PlattCalibrator:
    def fit(self, p_raw, y):
        # penalty=None: we want the plain 2-parameter fit, no extra shrinkage
        self.lr_ = LogisticRegression(penalty=None, max_iter=1000).fit(_logit(p_raw).reshape(-1, 1), y)
        return self

    @property
    def slope(self) -> float:
        return float(self.lr_.coef_[0][0])

    @property
    def offset(self) -> float:
        return float(self.lr_.intercept_[0])

    def predict(self, p_raw):
        return self.lr_.predict_proba(_logit(p_raw).reshape(-1, 1))[:, 1]


class IsotonicCalibrator:
    def fit(self, p_raw, y):
        self.iso_ = IsotonicRegression(out_of_bounds="clip", y_min=EPS, y_max=1 - EPS).fit(p_raw, y)
        return self

    def predict(self, p_raw):
        return self.iso_.predict(p_raw)
