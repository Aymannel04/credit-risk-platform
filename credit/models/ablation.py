"""Ablation: how does handling the 2% imbalance change the probabilities, raw and calibrated?

Same XGBoost, same settings, same number of trees for every variant (no early stopping), so the ONLY
difference is the treatment of the imbalance:
  unweighted     : the data as it is (the baseline of this project)
  class_weights  : each defaulter counts about 49x more during training
  smote          : synthetic defaulters are added until defaults are 50% of the training data
Fitted on `train`; calibrators fitted on `calibration`; measured on `validation`. Tests stay locked.

Usage (from the repo root):  .venv/Scripts/python -m credit.models.ablation
"""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from imblearn.over_sampling import SMOTE  # noqa: E402
from xgboost import XGBClassifier  # noqa: E402

from credit.models import metrics  # noqa: E402
from credit.models.calibration import IsotonicCalibrator, PlattCalibrator  # noqa: E402
from credit.models.data import load, make_preprocessor, xy  # noqa: E402
from credit.models.xgboost_model import PARAMS, SEED, Bundle  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
N_TREES = 219  # trees used by the early-stopped unweighted model (results/xgboost_validation.json)
VARIANTS = ("unweighted", "class_weights", "smote")


def fit_variant(train, kind: str, n_trees: int = N_TREES) -> Bundle:
    X, y = xy(train)
    prep = make_preprocessor().fit(X)
    Xt = prep.transform(X)
    params = {k: v for k, v in PARAMS.items() if k != "early_stopping_rounds"}
    params["n_estimators"] = n_trees
    if kind == "class_weights":
        params["scale_pos_weight"] = float((y == 0).sum() / (y == 1).sum())
    elif kind == "smote":
        Xt, y = SMOTE(random_state=SEED).fit_resample(Xt, y)  # Xt is dense (see make_preprocessor)
    elif kind != "unweighted":
        raise ValueError(kind)
    model = XGBClassifier(**params).fit(Xt, y)
    return Bundle(prep=prep, model=model, best_iteration=n_trees - 1)


def main() -> dict:
    train, cal = load("train"), load("calibration")
    valid = load("validation").reset_index(drop=True)
    y_cal, y_va = xy(cal)[1].to_numpy(), xy(valid)[1].to_numpy()
    out = {"n_trees": N_TREES, "variants": {}}
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)

    for ax, kind in zip(axes, VARIANTS, strict=True):
        bundle = fit_variant(train, kind)
        p_cal, p_va = bundle.predict_proba(xy(cal)[0]), bundle.predict_proba(xy(valid)[0])
        platt = PlattCalibrator().fit(p_cal, y_cal)
        iso = IsotonicCalibrator().fit(p_cal, y_cal)
        versions = {"raw": p_va, "platt": platt.predict(p_va), "isotonic": iso.predict(p_va)}
        res = {"platt_slope": platt.slope, "platt_offset": platt.offset, "validation": {}, "by_vintage": {}}
        for label, p in versions.items():
            m = metrics.evaluate(y_va, p)
            m["ece"] = metrics.ece(y_va, p)
            res["validation"][label] = m
            for v, g in valid.groupby("vintage_year"):
                if g["default_24m"].sum() >= 20:
                    idx = g.index.to_numpy()
                    res["by_vintage"].setdefault(int(v), {})[label] = {
                        "mean_predicted_pd": float(p[idx].mean()), "observed": float(y_va[idx].mean())}
        out["variants"][kind] = res

        ax.plot([1e-3, 1], [1e-3, 1], "k--", lw=1, label="perfect")
        for label, p in versions.items():
            t = metrics.calibration_table(y_va, p, n_bins=10)
            t = t[t["observed"] > 0]
            ax.plot(t["predicted"], t["observed"], marker="o", label=label)
        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_title(f"{kind}: validation reliability")
        ax.set_xlabel("predicted default rate")
        ax.grid(alpha=0.3, which="both")
        ax.legend()
    axes[0].set_ylabel("observed default rate")
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / "ablation_validation.png", dpi=130)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "ablation_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{'variant / version':26s}{'Brier':>10s}{'ECE':>9s}{'AUC':>8s}{'mean PD':>9s}{'real':>8s}")
    for kind, res in out["variants"].items():
        print(f"{kind}  (Platt slope={res['platt_slope']:.3f}, offset={res['platt_offset']:.3f})")
        for label, m in res["validation"].items():
            print(f"  {label:24s}{m['brier']:10.5f}{m['ece']:9.5f}{m['auc']:8.3f}{m['mean_predicted_pd']:9.4f}{m['default_rate']:8.4f}")
    return out


if __name__ == "__main__":
    main()
