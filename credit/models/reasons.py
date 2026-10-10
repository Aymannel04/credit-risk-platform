"""Reason codes from the scorecard: the features where a loan loses the most points.

A scorecard is additive, so points lost per feature (best band of the feature minus the loan's band) is an
EXACT explanation of why the score is not higher. Sentences come only from config/reason_codes.yaml.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from credit.models.scorecard import Scorecard

ROOT = Path(__file__).resolve().parents[2]
REASON_PATH = ROOT / "config" / "reason_codes.yaml"


def load_reason_table(path: Path = REASON_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def points_per_feature(sc: Scorecard, X: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(points of each loan per selected feature, band label of each loan per feature)."""
    table = sc.points_table()
    pts, bands = {}, {}
    for c in sc.selected_:
        fb = sc.bins_[c]
        pts_by_band = table[table["feature"] == c]["points"].to_numpy()
        labels = np.array(fb.band_labels())
        idx = fb.assign(X[c])
        pts[c], bands[c] = pts_by_band[idx], labels[idx]
    return pd.DataFrame(pts, index=X.index), pd.DataFrame(bands, index=X.index)


def best_points(sc: Scorecard) -> dict:
    """Highest points a loan can get from each feature (only bands that really occur, with at least one loan)."""
    t = sc.points_table()
    t = t[t["loans"] > 0]
    return t.groupby("feature")["points"].max().to_dict()


def reasons(
    sc: Scorecard, X: pd.DataFrame, top_k: int = 4, reason_table: dict | None = None, min_points_lost: float = 5.0
) -> list[list[dict]]:
    """For each loan: up to top_k reasons, biggest points loss first (ties: the scorecard's feature order).

    Only losses of at least `min_points_lost` points are reasons (smaller ones are noise), and features marked
    `reportable: false` in the config are never shown."""
    reason_table = reason_table or load_reason_table()
    missing = [c for c in sc.selected_ if c not in reason_table]
    if missing:  # never skip or improvise: every feature the scorecard uses needs an approved sentence
        raise ValueError(f"no approved reason sentence for {missing}: add them to config/reason_codes.yaml")
    pts, bands = points_per_feature(sc, X)
    best = best_points(sc)
    lost = pd.DataFrame({c: best[c] - pts[c] for c in sc.selected_})
    out = []
    for i in range(len(X)):
        row = lost.iloc[i]
        reportable = [c for c in sc.selected_ if reason_table[c].get("reportable", True)]
        order = sorted(reportable, key=lambda c: (-row[c], sc.selected_.index(c)))
        loan_reasons = []
        for c in order[:top_k]:
            if row[c] < min_points_lost:
                break
            loan_reasons.append({"code": reason_table[c]["code"], "feature": c, "phrase": reason_table[c]["phrase"],
                                 "band": str(bands.iloc[i][c]), "points_lost": float(row[c])})
        out.append(loan_reasons)
    return out
