"""Fit the scorecard on `train`, measure on `train` and `validation` (never the tests), save the tables.

Writes results/scorecard_validation.json, results/scorecard_table.csv, results/scorecard_iv.csv.
Usage (from the repo root):  .venv/Scripts/python -m credit.models.scorecard_report
"""
import json
from pathlib import Path

import pandas as pd

from credit.models import metrics
from credit.models.data import TARGET, load, xy
from credit.models.scorecard import Scorecard, load_config

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def main() -> dict:
    cfg = load_config()
    train, valid = load("train"), load("validation").reset_index(drop=True)
    X_tr, y_tr = xy(train)
    X_va, y_va = xy(valid)
    sc = Scorecard(cfg).fit(X_tr, y_tr)
    p_tr, p_va = sc.predict_proba(X_tr), sc.predict_proba(X_va)
    iv = pd.DataFrame({"feature": list(sc.bins_), "iv": [fb.iv for fb in sc.bins_.values()]}).sort_values("iv", ascending=False)
    iv["kept"] = iv["feature"].isin(sc.selected_)
    table = sc.points_table()

    result = {
        "model": "woe_scorecard",
        "assumptions": {"scorecard_scaling": cfg["scorecard_scaling"], "scorecard_binning": cfg["scorecard_binning"]},
        "features_kept": sc.selected_,
        "sign_violations": sc.sign_violations(),
        "train": metrics.evaluate(y_tr, p_tr),
        "validation": metrics.evaluate(y_va, p_va),
        "validation_by_vintage": {
            int(v): metrics.evaluate(g[TARGET].astype(int), p_va[g.index.to_numpy()])
            for v, g in valid.groupby("vintage_year") if g[TARGET].sum() >= 20
        },
        "score_range_validation": [float(sc.score(X_va).min()), float(sc.score(X_va).max())],
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "scorecard_validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    table.round(4).to_csv(RESULTS / "scorecard_table.csv", index=False)
    iv.round(4).to_csv(RESULTS / "scorecard_iv.csv", index=False)

    print("Information Value per feature (>= 0.02 kept):")
    print(iv.to_string(index=False))
    print("\nsign violations (a coefficient > 0 would be a red flag):", result["sign_violations"] or "none")
    print(f"validation score range: {result['score_range_validation'][0]:.0f} .. {result['score_range_validation'][1]:.0f} points")
    print(f"\n{'':28s}{'AUC':>7s}{'Gini':>7s}{'KS':>7s}{'Brier':>9s}{'mean PD':>9s}{'real':>8s}")
    for part in ("train", "validation"):
        m = result[part]
        print(f"scorecard {part:18s}{m['auc']:7.3f}{m['gini']:7.3f}{m['ks']:7.3f}{m['brier']:9.5f}{m['mean_predicted_pd']:9.4f}{m['default_rate']:8.4f}")
    for v, m in result["validation_by_vintage"].items():
        print(f"scorecard validation {v}      {m['auc']:7.3f}{m['gini']:7.3f}{m['ks']:7.3f}{m['brier']:9.5f}{m['mean_predicted_pd']:9.4f}{m['default_rate']:8.4f}")
    return result


if __name__ == "__main__":
    main()
