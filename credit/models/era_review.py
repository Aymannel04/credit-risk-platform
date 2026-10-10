"""Era-stability review of the features (development vintages only; the fresh vintages are never read here).

Question for every feature: does it carry information INSIDE each era, or does it mostly tell which era it is?
  pooled IV                 information value on all vintages together (includes the difference between eras)
  within-vintage IV excess  information value computed inside one vintage, minus the IV that a randomly shuffled
                            copy of the same feature reaches by chance (the "noise floor" for that vintage's size)
  keep ratio                median within-vintage excess / pooled IV. Near 1: the information is real in every era.
                            Near 0: the pooled IV was mostly an era effect (an era proxy).
  direction flips           numeric features: the sign of the single-feature ranking differs between vintages
  level changes             categorical features: a level that is common in one vintage and (almost) absent in another
Then a leave-one-vintage-out (LOVO) test of candidate feature sets: train on four vintages, test on the fifth.

Usage (from the repo root):  .venv/Scripts/python -m credit.models.era_review
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit.models import metrics
from credit.models.scorecard import Scorecard, _woe_table, fit_bins, load_config

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
FEATURES_PATH = ROOT / "data" / "interim" / "features" / "features.parquet"
TARGET = "default_24m"
N_SHUFFLES = 5
SEED = 7


def _within_iv(fb, values: pd.Series, y: np.ndarray) -> float:
    bands = fb.assign(values)
    return _woe_table(bands, y, len(fb.table), list(fb.table["band"]))[1]


def within_vintage_iv(df: pd.DataFrame, bins: dict) -> pd.DataFrame:
    """IV per feature and vintage, the noise floor, and the excess. Bands are the pooled ones (fixed)."""
    rng = np.random.default_rng(SEED)
    rows = []
    for v, g in df.groupby("vintage_year"):
        if g[TARGET].sum() < 30:
            continue
        y = g[TARGET].to_numpy()
        for col, fb in bins.items():
            iv = _within_iv(fb, g[col], y)
            noise = np.mean([_within_iv(fb, pd.Series(rng.permutation(g[col].to_numpy())), y) for _ in range(N_SHUFFLES)])
            rows.append({"feature": col, "vintage": int(v), "defaults": int(y.sum()), "iv": iv, "noise_floor": float(noise),
                         "excess": iv - float(noise)})
    return pd.DataFrame(rows)


def direction_by_vintage(df: pd.DataFrame, numeric: list) -> pd.DataFrame:
    """Signed single-feature Gini per vintage (positive: higher value, higher default risk)."""
    rows = []
    for v, g in df.groupby("vintage_year"):
        if g[TARGET].sum() < 30:
            continue
        for col in numeric:
            x = pd.to_numeric(g[col], errors="coerce")
            x = x.fillna(x.median())
            if x.nunique() < 2:
                continue
            rows.append({"feature": col, "vintage": int(v), "signed_gini": 2 * roc_auc_score(g[TARGET], x) - 1})
    return pd.DataFrame(rows)


def level_shares(df: pd.DataFrame, categorical: list) -> dict:
    """Share of each level of each categorical feature, per vintage; flags a level that (almost) vanishes in some vintage."""
    flags = {}
    for col in categorical:
        t = pd.crosstab(df[col].fillna("missing"), df["vintage_year"], normalize="columns")
        common = t[(t.max(axis=1) >= 0.02)]
        bad = [lvl for lvl, row in common.iterrows() if row.min() < 0.002 or row.max() / max(row.min(), 1e-6) >= 8]
        flags[col] = bad
    return flags


def feature_report(df: pd.DataFrame, cfg: dict | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    numeric = [c for c in NUMERIC_FEATURES if c in df.columns]
    categorical = [c for c in CATEGORICAL_FEATURES if c in df.columns]
    bins = fit_bins(df, df[TARGET], cfg, numeric, categorical)
    wv = within_vintage_iv(df, bins)
    dirs = direction_by_vintage(df, numeric)
    levels = level_shares(df, categorical)
    out = []
    for col, fb in bins.items():
        w = wv[wv.feature == col]
        d = dirs[dirs.feature == col]["signed_gini"] if col in numeric else pd.Series(dtype=float)
        flips = bool((d > 0.02).any() and (d < -0.02).any())
        out.append({"feature": col, "pooled_iv": fb.iv, "median_excess_iv": float(w["excess"].median()),
                    "min_excess_iv": float(w["excess"].min()), "keep_ratio": float(w["excess"].median() / fb.iv) if fb.iv > 0 else np.nan,
                    "direction_flips": flips, "levels_vanishing": levels.get(col, [])})
    return pd.DataFrame(out).sort_values("pooled_iv", ascending=False)


def lovo(df: pd.DataFrame, numeric: list, categorical: list, cfg: dict | None = None) -> dict:
    """Leave one vintage out: fit on the other vintages, measure on the held-out one."""
    cfg = cfg or load_config()
    res = {}
    for v in sorted(df["vintage_year"].unique()):
        held = df[df["vintage_year"] == v]
        if held[TARGET].sum() < 30:
            continue
        train = df[df["vintage_year"] != v]
        sc = Scorecard(cfg, numeric, categorical).fit(train[numeric + categorical], train[TARGET])
        p = sc.predict_proba(held[numeric + categorical])
        y = held[TARGET].to_numpy()
        res[int(v)] = {"gini": metrics.gini(y, p), "pred_over_obs": float(p.mean() / y.mean()), "defaults": int(y.sum())}
    return res


def candidate_sets() -> dict:
    base_num = [c for c in NUMERIC_FEATURES if c != "n_borrowers"]
    base_cat = list(CATEGORICAL_FEATURES)
    no_two = [c for c in base_cat if c not in ("state", "super_conforming")]
    return {
        "A v1 features (all)": (NUMERIC_FEATURES, base_cat),
        "B minus state": (NUMERIC_FEATURES, [c for c in base_cat if c != "state"]),
        "C minus super_conforming": (NUMERIC_FEATURES, [c for c in base_cat if c != "super_conforming"]),
        "D minus both": (NUMERIC_FEATURES, no_two),
        "E D + several_borrowers instead of n_borrowers": (base_num + ["several_borrowers"], no_two),
        "H E minus channel": (base_num + ["several_borrowers"], [c for c in no_two if c != "channel"]),
        "F within-era features (no state/channel/super_conf.)": (
            ["credit_score", "dti", "rate_spread", "ltv", "cltv", "several_borrowers", "mi_pct", "orig_term"], ["purpose"]),
        "G core only": (["credit_score", "dti", "rate_spread", "ltv", "cltv", "several_borrowers"], []),
    }


def load_dev() -> pd.DataFrame:
    import duckdb

    df = duckdb.sql(f"SELECT * FROM read_parquet('{FEATURES_PATH.as_posix()}')").df()
    df["several_borrowers"] = (pd.to_numeric(df["n_borrowers"], errors="coerce") >= 2).astype(float).where(df["n_borrowers"].notna())
    return df


def main() -> dict:
    df = load_dev()
    rep = feature_report(df)
    cand = {name: lovo(df, list(n), list(c)) for name, (n, c) in candidate_sets().items()}
    out = {"vintages": sorted(int(v) for v in df["vintage_year"].unique()), "feature_report": rep.round(4).to_dict(orient="records"),
           "lovo": cand}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "v2_feature_review.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = main()
    pd.set_option("display.width", 250)
    print(pd.DataFrame(o["feature_report"]).to_string(index=False))
    print("\nLeave-one-vintage-out (Gini / predicted-over-observed on the held-out vintage):")
    vint = sorted({v for r in o["lovo"].values() for v in r})
    print(f"{'candidate set':50s}" + "".join(f"{v:>16d}" for v in vint) + f"{'mean Gini':>11s}")
    for name, r in o["lovo"].items():
        cells = "".join(f"  {r[v]['gini']:.3f} / {r[v]['pred_over_obs']:.2f}" if v in r else f"{'-':>16s}" for v in vint)
        print(f"{name:50s}{cells}{np.mean([r[v]['gini'] for v in r]):11.3f}")
