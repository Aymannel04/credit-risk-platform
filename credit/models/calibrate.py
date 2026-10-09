"""Calibrate the logistic regression and the XGBoost model; measure on validation only.

Writes results/calibration_validation.json and docs/calibration_validation.png.
Usage (from the repo root):  .venv/Scripts/python -m credit.models.calibrate
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from credit.models import metrics, xgboost_model  # noqa: E402
from credit.models.baseline_logreg import build_model  # noqa: E402
from credit.models.calibration import IsotonicCalibrator, PlattCalibrator  # noqa: E402
from credit.models.data import load, xy  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"


def raw_predictors():
    """name -> function(df) giving raw probabilities. Both models are trained on `train` only."""
    train = load("train")
    X_tr, y_tr = xy(train)
    logistic = build_model().fit(X_tr, y_tr)
    xgb = xgboost_model.fit(train)
    return {
        "logistic": lambda df: logistic.predict_proba(xy(df)[0])[:, 1],
        "xgboost": lambda df: xgb.predict_proba(xy(df)[0]),
    }


def main() -> dict:
    cal, valid = load("calibration"), load("validation").reset_index(drop=True)
    y_cal, y_va = xy(cal)[1].to_numpy(), xy(valid)[1].to_numpy()
    out = {"calibration_split": {"n": int(len(cal)), "defaults": int(y_cal.sum())}, "models": {}}
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6))

    for ax, (name, predict) in zip(axes, raw_predictors().items(), strict=True):
        p_cal, p_va = predict(cal), predict(valid)
        platt = PlattCalibrator().fit(p_cal, y_cal)
        iso = IsotonicCalibrator().fit(p_cal, y_cal)
        versions = {"raw": p_va, "platt": platt.predict(p_va), "isotonic": iso.predict(p_va)}

        res = {"platt_slope": platt.slope, "platt_offset": platt.offset, "validation": {}, "validation_by_vintage": {}}
        for label, p in versions.items():
            m = metrics.evaluate(y_va, p)
            m["ece"] = metrics.ece(y_va, p)
            res["validation"][label] = m
            for v, g in valid.groupby("vintage_year"):
                if g["default_24m"].sum() >= 20:
                    idx = g.index.to_numpy()
                    res["validation_by_vintage"].setdefault(int(v), {})[label] = {
                        "mean_predicted_pd": float(p[idx].mean()), "observed": float(y_va[idx].mean()),
                        "brier": metrics.brier(y_va[idx], p[idx]),
                    }
        out["models"][name] = res

        ax.plot([1e-4, 0.5], [1e-4, 0.5], "k--", lw=1, label="perfect")
        for label, p in versions.items():
            t = metrics.calibration_table(y_va, p, n_bins=10)
            t = t[t["observed"] > 0]
            ax.plot(t["predicted"], t["observed"], marker="o", label=f"{label}")
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{name}: validation reliability (10 risk groups)")
        ax.set_xlabel("predicted default rate")
        ax.set_ylabel("observed default rate")
        ax.grid(alpha=0.3, which="both")
        ax.legend()
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / "calibration_validation.png", dpi=130)

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "calibration_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"calibration split: {out['calibration_split']['n']:,} loans, {out['calibration_split']['defaults']} defaults")
    print(f"{'':22s}{'Brier':>10s}{'ECE':>9s}{'AUC':>8s}{'mean PD':>9s}{'real':>8s}")
    for name, res in out["models"].items():
        print(f"{name}  (Platt slope={res['platt_slope']:.3f}, offset={res['platt_offset']:.3f})")
        for label, m in res["validation"].items():
            print(f"  {label:20s}{m['brier']:10.5f}{m['ece']:9.5f}{m['auc']:8.3f}{m['mean_predicted_pd']:9.4f}{m['default_rate']:8.4f}")
        for v, d in res["validation_by_vintage"].items():
            print(f"  vintage {v}: observed {d['raw']['observed']:.4f} | predicted raw {d['raw']['mean_predicted_pd']:.4f}"
                  f" platt {d['platt']['mean_predicted_pd']:.4f} isotonic {d['isotonic']['mean_predicted_pd']:.4f}")
    return out


if __name__ == "__main__":
    np.random.seed(0)
    main()
