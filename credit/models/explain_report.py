"""Reason codes for the scorecard, SHAP for XGBoost, and how well they agree (validation sample only).

Writes results/explain_report.json.  Usage:  .venv/Scripts/python -m credit.models.explain_report
"""
import json
from pathlib import Path

import numpy as np

from credit.models import explain, reasons, xgboost_model
from credit.models.data import load, xy
from credit.models.scorecard import Scorecard

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def main() -> dict:
    train = load("train")
    sc = Scorecard().fit(*xy(train))
    xgb = xgboost_model.fit(train)
    valid = load("validation").reset_index(drop=True)
    sample = valid.sample(2000, random_state=42).reset_index(drop=True)
    Xs = xy(sample)[0]

    rs_ = reasons.reasons(sc, Xs, top_k=4)
    shap_df = explain.shap_by_feature(xgb, Xs)
    shap_report = shap_df.drop(columns=["super_conforming"])  # compare like with like: that feature is not reportable
    agree = {k: explain.topk_overlap(rs_, shap_report, k) for k in (1, 3)}

    # global view: scorecard = information value, XGBoost = mean absolute SHAP
    iv = {c: fb.iv for c, fb in sc.bins_.items() if c in sc.selected_}
    mean_abs = shap_df.abs().mean().sort_values(ascending=False)
    # the 20 riskiest and 20 safest loans of the sample, with their reasons
    p = sc.predict_proba(Xs)
    order = np.argsort(-p)
    examples = []
    for i in list(order[:3]) + list(order[-2:]):
        examples.append({"scorecard_pd": float(p[i]), "score_points": float(sc.score(Xs.iloc[[i]])[0]),
                         "actual_default": int(sample.loc[i, "default_24m"]),
                         "reasons": [f"{r['code']} {r['phrase']} [{r['band']}] -{r['points_lost']:.0f} pts" for r in rs_[i]]})
    most_common = {}
    for loan in rs_:
        for r in loan[:1]:
            most_common[r["feature"]] = most_common.get(r["feature"], 0) + 1
    out = {"sample": len(Xs), "agreement_top_k": agree,
           "features_by_iv": dict(sorted(iv.items(), key=lambda kv: -kv[1])),
           "features_by_mean_abs_shap": mean_abs.round(4).to_dict(),
           "first_reason_counts": dict(sorted(most_common.items(), key=lambda kv: -kv[1])),
           "examples": examples}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "explain_report.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


if __name__ == "__main__":
    o = main()
    print("agreement scorecard reasons vs XGBoost SHAP:", {k: {kk: round(vv, 3) for kk, vv in v.items()} for k, v in o["agreement_top_k"].items()})
    print("\nfeatures by scorecard IV:      ", [f"{k} {v:.2f}" for k, v in o["features_by_iv"].items()])
    print("features by mean |SHAP| (xgb): ", [f"{k} {v:.2f}" for k, v in o["features_by_mean_abs_shap"].items()][:11])
    print("\nmost common FIRST reason in the sample:", o["first_reason_counts"])
    for e in o["examples"]:
        print(f"\nPD {e['scorecard_pd']:.2%} | score {e['score_points']:.0f} | defaulted: {e['actual_default']}")
        for r in e["reasons"]:
            print("   -", r)
