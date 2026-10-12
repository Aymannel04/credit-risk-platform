"""EXPLORATORY (not pre-registered, no decision depends on it): what happens if the 2008 crisis vintage is left out of training?

Question asked by the owner: the model over-predicts in calm years because the 2008 crisis is in its training data; why not skip 2008?
Method: refit the v2 scorecard (same method, same settings) on the development vintages WITHOUT 2008, and compare it with the
committed model on all nine vintages (level and ranking). The committed model and every decision stay untouched.
Sanity check: refitting WITH all development rows must reproduce the committed model id.

Predictions written BEFORE running (2026-10-12):
  E1  the level ratio of 2010, 2012, 2014, 2016 and 2018 moves closer to 1 for all five (less over-prediction)
  E2  2019, 2022 and 2023 cross above 1: the new model UNDER-predicts them
  E3  the 2008 ratio rises to at least 2.5 (the crisis is under-predicted by 2.5 times or more; it is 1.80 now)
  E4  ranking barely changes: |Gini difference| below 0.02 on every vintage, Spearman correlation of the two scores above 0.95
  E5  the plain average of the nine level errors FALLS (calm years are 8 of 9), while the 2008 miss in number of defaults rises:
      the average hides the cost of being wrong in the crisis

Usage (from the repo root):  .venv/Scripts/python scripts/exploratory_without_2008.py
Writes results/exploratory_without_2008.json and .md.
"""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from credit.models import metrics  # noqa: E402
from credit.models.scorecard import Scorecard  # noqa: E402
from credit.models.v2_exam import TARGET, V2_CATEGORICAL, V2_NUMERIC, v2_config  # noqa: E402
from credit.monitoring import report  # noqa: E402
from credit.monitoring.scoring import score_frame  # noqa: E402
from credit.serving.export import export_model  # noqa: E402
from credit.serving.model_file import load_model  # noqa: E402

CALM_BEFORE_2019 = [2010, 2012, 2014, 2016, 2018]
LATE = [2019, 2022, 2023]


def fit(rows):
    cols = V2_NUMERIC + V2_CATEGORICAL
    sc = Scorecard(v2_config(), V2_NUMERIC, V2_CATEGORICAL).fit(rows[cols], rows[TARGET])
    return export_model(sc, {})


def per_vintage(model: dict, scored_frame) -> dict:
    out = {}
    for v, g in scored_frame.groupby("vintage"):
        y, p = g["y"].to_numpy(), g["pd"].to_numpy()
        out[int(v)] = {
            "loans": int(len(g)), "defaults": int(y.sum()), "predicted_defaults": float(p.sum()),
            "observed_rate": float(y.mean()), "predicted_rate": float(p.mean()),
            "ratio": float(y.mean() / p.mean()), "level_error": float(abs(np.log(p.mean() / y.mean()))),
            "default_count_miss": float(abs(p.sum() - y.sum())), "gini": float(metrics.gini(y, p)),
        }
    return out


def main() -> dict:
    cfg = report.load_config()
    committed = load_model(report.MODEL)
    frame = report.build_frame(committed, cfg)
    frame["default_24m"] = frame["y"]  # Scorecard.fit reads the target by name
    dev = frame[frame["in_sample"]]

    refit_all = fit(dev)
    sanity_ok = refit_all["model_id"] == committed["model_id"]
    no2008 = fit(dev[dev["vintage"] != 2008])

    sets = {}
    for name, model in (("committed_all_vintages", committed), ("without_2008", no2008)):
        sets[name] = frame.join(score_frame(model, frame))
    a, b = per_vintage(committed, sets["committed_all_vintages"]), per_vintage(no2008, sets["without_2008"])
    vints = sorted(a)

    train_rate = {"with_2008": float(dev["y"].mean()), "without_2008": float(dev[dev["vintage"] != 2008]["y"].mean())}
    spearman = float(sets["committed_all_vintages"]["score"].corr(sets["without_2008"]["score"], method="spearman"))
    mean_err = {k: float(np.mean([m[v]["level_error"] for v in vints])) for k, m in (("committed", a), ("without_2008", b))}
    miss_total = {k: float(sum(m[v]["default_count_miss"] for v in vints)) for k, m in (("committed", a), ("without_2008", b))}

    preds = [
        {"id": "E1", "text": "2010-2018 ratios move closer to 1", "hit": all(abs(np.log(b[v]["ratio"])) < abs(np.log(a[v]["ratio"])) for v in CALM_BEFORE_2019)},
        {"id": "E2", "text": "2019, 2022, 2023 cross above 1", "hit": all(b[v]["ratio"] > 1 for v in LATE)},
        {"id": "E3", "text": "2008 ratio rises to at least 2.5", "hit": b[2008]["ratio"] >= 2.5},
        {"id": "E4", "text": "|Gini difference| < 0.02 everywhere and Spearman > 0.95",
         "hit": all(abs(b[v]["gini"] - a[v]["gini"]) < 0.02 for v in vints) and spearman > 0.95},
        {"id": "E5", "text": "average level error falls while the 2008 default-count miss rises",
         "hit": mean_err["without_2008"] < mean_err["committed"] and b[2008]["default_count_miss"] > a[2008]["default_count_miss"]},
    ]
    result = {
        "exploratory": True, "sanity_refit_reproduces_committed_model": bool(sanity_ok), "committed_model_id": committed["model_id"],
        "training_default_rate": train_rate, "spearman_between_scores": spearman, "mean_level_error": mean_err,
        "total_default_count_miss": miss_total, "committed": {str(k): v for k, v in a.items()},
        "without_2008": {str(k): v for k, v in b.items()}, "predictions": preds,
    }
    out = ROOT / "results"
    (out / "exploratory_without_2008.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    (out / "exploratory_without_2008.md").write_text(to_markdown(result, a, b, vints), encoding="utf-8")
    print(to_markdown(result, a, b, vints))
    return result


def to_markdown(r: dict, a: dict, b: dict, vints: list) -> str:
    L = ["# Exploratory: the model refitted WITHOUT the 2008 vintage", "",
         "Exploratory, not pre-registered, no decision depends on it. The committed model is untouched. "
         f"Sanity check (refit on all development rows reproduces model `{r['committed_model_id']}`): **{r['sanity_refit_reproduces_committed_model']}**. "
         "Vintages 2008, 2012, 2016, 2019, 2022 are in-sample for the committed model; for the refit, 2008 is out-of-sample.", "",
         f"Training default rate: {r['training_default_rate']['with_2008']:.2%} with 2008, {r['training_default_rate']['without_2008']:.2%} without. "
         f"Spearman correlation between the two scores on all loans: {r['spearman_between_scores']:.3f}.", "",
         "| Vintage | Observed | Predicted (committed) | Ratio (committed) | Predicted (no 2008) | Ratio (no 2008) | Gini (committed) | Gini (no 2008) | Default-count miss (committed) | (no 2008) |",
         "|---|---|---|---|---|---|---|---|---|---|"]
    for v in vints:
        L.append(f"| {v} | {a[v]['observed_rate']:.2%} | {a[v]['predicted_rate']:.2%} | {a[v]['ratio']:.2f} | {b[v]['predicted_rate']:.2%} | {b[v]['ratio']:.2f} | "
                 f"{a[v]['gini']:.3f} | {b[v]['gini']:.3f} | {a[v]['default_count_miss']:,.0f} | {b[v]['default_count_miss']:,.0f} |")
    L += ["", f"Plain average of the nine level errors: committed {r['mean_level_error']['committed']:.3f}, without 2008 {r['mean_level_error']['without_2008']:.3f}. "
          f"Total default-count miss over the nine vintages: committed {r['total_default_count_miss']['committed']:,.0f}, without 2008 {r['total_default_count_miss']['without_2008']:,.0f}.",
          "", "## Predictions written before running", "", "| Id | Prediction | Result |", "|---|---|---|"]
    L += [f"| {p['id']} | {p['text']} | {'HIT' if p['hit'] else 'MISS'} |" for p in r["predictions"]]
    L += ["", f"{sum(p['hit'] for p in r['predictions'])} of {len(r['predictions'])} predictions hit.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
