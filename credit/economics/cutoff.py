"""Approve/refuse line, profit and expected loss: the money side of the scorecard.

Rule of the game (per loan, exposure EAD = original loan amount):
  approve a loan that does NOT default -> earn  margin * EAD
  approve a loan that DOES default     -> lose  loss * EAD     (loss = loss per flagged loan)
  refuse a loan                        -> nothing happens
With a correct PD p, approving has expected profit EAD * ((1 - p) * margin - p * loss), which is positive
exactly when p < margin / (margin + loss): the classic cut-off.

The line is CHOSEN on validation (realised profit) and only REPORTED on the test splits.
All money assumptions come from config/economics.yaml.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "economics.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def theory_cutoff(margin: float, loss: float) -> float:
    """PD above which approving loses money in expectation (if the PD is honest)."""
    return margin / (margin + loss)


def realised_profit(y, ead, approve, margin: float, loss: float) -> float:
    """Profit actually made by approving the loans in `approve`, given what really happened (y = 1: default)."""
    y, ead, approve = np.asarray(y), np.asarray(ead, dtype=float), np.asarray(approve, dtype=bool)
    per_loan = np.where(y == 0, margin * ead, -loss * ead)
    return float(per_loan[approve].sum())


def profit_curve(p, y, ead, margin: float, loss: float, n_points: int = 101) -> pd.DataFrame:
    """Approve every loan with PD <= t, for thresholds t going from the safest half up to everyone."""
    p = np.asarray(p)
    thresholds = np.unique(np.quantile(p, np.linspace(0.5, 1.0, n_points)))
    rows = []
    for t in thresholds:
        approve = p <= t
        rows.append({"threshold": float(t), "approval_rate": float(approve.mean()),
                     "profit": realised_profit(y, ead, approve, margin, loss)})
    return pd.DataFrame(rows)


def best_cutoff(p, y, ead, margin: float, loss: float) -> dict:
    curve = profit_curve(p, y, ead, margin, loss)
    best = curve.loc[curve["profit"].idxmax()]
    return {"threshold": float(best["threshold"]), "approval_rate": float(best["approval_rate"]), "profit": float(best["profit"])}


def decision_report(p, y, ead, threshold: float, margin: float, loss: float) -> dict:
    """What the line does on a group of loans, next to the two trivial policies."""
    p, y, ead = np.asarray(p), np.asarray(y), np.asarray(ead, dtype=float)
    approve = p <= threshold
    n_def = int(y.sum())
    return {
        "approval_rate": float(approve.mean()),
        "default_rate_all": float(y.mean()),
        "default_rate_approved": float(y[approve].mean()) if approve.any() else None,
        "defaults_refused_share": float(y[~approve].sum() / n_def) if n_def else None,
        "good_loans_refused_share": float(((y == 0) & ~approve).sum() / max(1, (y == 0).sum())),
        "profit_with_line": realised_profit(y, ead, approve, margin, loss),
        "profit_approve_all": realised_profit(y, ead, np.ones(len(y), bool), margin, loss),
        "profit_refuse_all": 0.0,
        "total_exposure": float(ead.sum()),
    }


def el_by_band(p, y, ead, loss: float, n_bands: int = 10) -> pd.DataFrame:
    """Expected loss (sum of PD * loss * EAD) against the loss that follows the real defaults at the same loss rate."""
    df = pd.DataFrame({"p": np.asarray(p), "y": np.asarray(y), "ead": np.asarray(ead, dtype=float)})
    df["band"] = pd.qcut(df["p"].rank(method="first"), n_bands, labels=False) + 1
    df["pred_el"] = df["p"] * loss * df["ead"]
    df["real_el"] = df["y"] * loss * df["ead"]
    g = df.groupby("band").agg(loans=("y", "size"), mean_pd=("p", "mean"), default_rate=("y", "mean"),
                              exposure=("ead", "sum"), predicted_el=("pred_el", "sum"), observed_el=("real_el", "sum")).reset_index()
    g["el_ratio"] = g["predicted_el"] / g["observed_el"].replace(0, np.nan)
    return g


def sensitivity_grid(p, y, ead, margins, losses) -> pd.DataFrame:
    """For each (margin, loss): theory line, best realised line, approval rate and profit gain over 'approve all'."""
    rows = []
    for m in margins:
        for L in losses:
            best = best_cutoff(p, y, ead, m, L)
            base = realised_profit(y, ead, np.ones(len(y), bool), m, L)
            rows.append({"margin": m, "loss": L, "theory_cutoff": theory_cutoff(m, L), "best_cutoff": best["threshold"],
                         "approval_rate": best["approval_rate"], "profit_gain_vs_approve_all": best["profit"] - base,
                         "gain_pct_of_exposure": (best["profit"] - base) / float(np.sum(ead))})
    return pd.DataFrame(rows)
