"""WoE scorecard: bands per feature -> Weight of Evidence -> logistic regression -> points.

Terms:
  band (bin)   a range of a number (credit score 720-759) or a category (state = CA)
  WoE          ln( share of non-defaults in the band / share of defaults in the band ).
               > 0 safer than average, < 0 riskier, 0 average
  IV           Information Value of a feature = sum over bands of (good share - bad share) * WoE
  points       the log-odds of the logistic regression, rescaled with the PDO convention
               (config/assumptions.yaml: base score, base odds, points to double the odds)
Everything is learned on `train`. Missing values get their own band.
"""
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "assumptions.yaml"
SMOOTH = 0.5  # added to bad/good counts so that an empty cell never gives an infinite WoE


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


@dataclass
class FeatureBins:
    name: str
    kind: str  # "numeric" or "categorical"
    edges: list = field(default_factory=list)  # numeric: sorted cut points; band i = (edge[i-1], edge[i]]
    categories: list = field(default_factory=list)  # categorical: kept categories
    table: pd.DataFrame | None = None  # band, n, defaults, woe, iv_part
    iv: float = 0.0

    def band_labels(self) -> list[str]:
        if self.kind == "numeric":
            e = self.edges
            labels = [f"<= {e[0]:g}" if e else "all"]
            labels += [f"({e[i - 1]:g}, {e[i]:g}]" for i in range(1, len(e))]
            if e:
                labels.append(f"> {e[-1]:g}")
            return labels + ["missing"]
        return [*[str(c) for c in self.categories], "other", "missing"]

    def assign(self, s: pd.Series) -> np.ndarray:
        """Band index for each value (last index = missing; categorical: second to last = other)."""
        if self.kind == "numeric":
            values = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
            idx = np.searchsorted(np.asarray(self.edges), values, side="left")
            return np.where(np.isnan(values), len(self.edges) + 1, idx)
        mapping = {c: i for i, c in enumerate(self.categories)}
        n = len(self.categories)
        return np.array([n + 1 if pd.isna(v) else mapping.get(v, n) for v in s])


def _woe_table(bands: np.ndarray, y: np.ndarray, n_bands: int, labels: list[str]) -> tuple[pd.DataFrame, float]:
    total_bad, total_good = y.sum(), (1 - y).sum()
    rows = []
    for b in range(n_bands):
        m = bands == b
        bad, good = y[m].sum(), (1 - y[m]).sum()
        if m.sum() == 0:  # a band the training data never saw (unseen category, missing never observed): neutral, not "terrible"
            rows.append({"band": labels[b], "n": 0, "defaults": 0, "default_rate": np.nan, "woe": 0.0, "iv_part": 0.0})
            continue
        woe = np.log(((good + SMOOTH) / (total_good + SMOOTH * n_bands)) / ((bad + SMOOTH) / (total_bad + SMOOTH * n_bands)))
        iv_part = ((good + SMOOTH) / (total_good + SMOOTH * n_bands) - (bad + SMOOTH) / (total_bad + SMOOTH * n_bands)) * woe
        rows.append({"band": labels[b], "n": int(m.sum()), "defaults": int(bad),
                     "default_rate": float(bad / m.sum()) if m.sum() else np.nan, "woe": float(woe), "iv_part": float(iv_part)})
    t = pd.DataFrame(rows)
    return t, float(t["iv_part"].sum())


def fit_bins(
    X: pd.DataFrame, y: pd.Series, cfg: dict, numeric: list | None = None, categorical: list | None = None
) -> dict[str, FeatureBins]:
    numeric = NUMERIC_FEATURES if numeric is None else numeric
    categorical = CATEGORICAL_FEATURES if categorical is None else categorical
    b = cfg["scorecard_binning"]
    n = len(X)
    y_arr = np.asarray(y)
    out = {}
    for col in numeric:
        v = pd.to_numeric(X[col], errors="coerce")
        known = v.notna().to_numpy()
        edges = []
        if known.sum() > 0 and v[known].nunique() > 1:
            tree = DecisionTreeClassifier(
                max_leaf_nodes=b["max_bins_per_numeric"], min_samples_leaf=max(30, int(b["min_bin_share"] * n)), random_state=42
            ).fit(v[known].to_numpy().reshape(-1, 1), y_arr[known])
            edges = sorted(float(t) for t in tree.tree_.threshold if t != -2)
        fb = FeatureBins(col, "numeric", edges=edges)
        bands = fb.assign(X[col])
        fb.table, fb.iv = _woe_table(bands, y_arr, len(edges) + 2, fb.band_labels())
        out[col] = fb
    for col in categorical:
        counts = X[col].value_counts()
        kept = [c for c, k in counts.items() if k >= b["min_category_share"] * n]
        fb = FeatureBins(col, "categorical", categories=sorted(kept, key=str))
        bands = fb.assign(X[col])
        fb.table, fb.iv = _woe_table(bands, y_arr, len(kept) + 2, fb.band_labels())
        out[col] = fb
    return out


class Scorecard:
    """Fit on a training dataframe (features + y). Use predict_proba / score on new loans."""

    def __init__(self, cfg: dict | None = None, numeric: list | None = None, categorical: list | None = None):
        self.cfg = cfg or load_config()
        self.numeric, self.categorical = numeric, categorical  # None = the default feature lists

    def fit(self, X: pd.DataFrame, y: pd.Series) -> "Scorecard":
        self.bins_ = fit_bins(X, y, self.cfg, self.numeric, self.categorical)
        min_iv = self.cfg["scorecard_binning"]["min_iv"]
        self.selected_ = [c for c, fb in self.bins_.items() if fb.iv >= min_iv]
        self.lr_ = LogisticRegression(max_iter=2000, C=1.0).fit(self.woe(X), np.asarray(y))
        return self

    def woe(self, X: pd.DataFrame) -> np.ndarray:
        cols = []
        for c in self.selected_:
            fb = self.bins_[c]
            woe_by_band = fb.table["woe"].to_numpy()
            cols.append(woe_by_band[fb.assign(X[c])])
        return np.column_stack(cols)

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        return self.lr_.predict_proba(self.woe(X))[:, 1]

    # ---- points -------------------------------------------------------------------------------
    def _scaling(self) -> tuple[float, float]:
        s = self.cfg["scorecard_scaling"]
        factor = s["points_to_double_odds"] / np.log(2)
        offset = s["base_score"] - factor * np.log(s["base_odds"])
        return float(factor), float(offset)

    def points_table(self) -> pd.DataFrame:
        """One row per (feature, band) with its points. Total score = sum of the points of a loan's bands."""
        factor, offset = self._scaling()
        coef, b0, k = self.lr_.coef_[0], float(self.lr_.intercept_[0]), len(self.selected_)
        rows = []
        for j, c in enumerate(self.selected_):
            fb = self.bins_[c]
            for _, r in fb.table.iterrows():
                pts = -factor * coef[j] * r["woe"] + (offset - factor * b0) / k
                rows.append({"feature": c, "band": r["band"], "loans": r["n"], "defaults": r["defaults"],
                             "default_rate": r["default_rate"], "woe": r["woe"], "points": pts})
        return pd.DataFrame(rows)

    def score(self, X: pd.DataFrame) -> np.ndarray:
        """Total points per loan (higher = safer), computed from the points table logic."""
        factor, offset = self._scaling()
        coef, b0 = self.lr_.coef_[0], float(self.lr_.intercept_[0])
        eta = b0 + self.woe(X) @ coef  # log-odds of default
        return offset + factor * (-eta)

    def sign_violations(self) -> list[str]:
        """Each coefficient must be negative: a higher WoE (safer band) must never raise the risk."""
        return [c for c, w in zip(self.selected_, self.lr_.coef_[0], strict=True) if w > 0]
