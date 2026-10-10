"""Export a fitted scorecard to the JSON model file (training side: uses scikit-learn code, the API does not).

Usage (from the repo root):  .venv/Scripts/python -m credit.serving.export
Writes models/scorecard_v2.json (aggregate numbers only: edges, categories and points; no loan data).
"""
import hashlib
import json
from datetime import date
from pathlib import Path

from credit.models.reasons import best_points, load_reason_table
from credit.models.scorecard import Scorecard
from credit.serving.model_file import SCHEMA_VERSION, canonical_hash, save_model

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = ROOT / "models" / "scorecard_v2.json"

KNOWN_LIMITS = [
    "Through-the-cycle model: it cannot see the economic climate. On four fresh vintages (2010, 2014, 2018, 2023) the "
    "predicted default rate was 1.4 to 2.6 times the real one. Use a macro overlay or per-period recalibration before "
    "using the level in money terms.",
    "Probability of a flagged serious delinquency within 24 months (definition B), not a probability of loss.",
    "Trained on prime fixed-rate US mortgages (Freddie Mac samples); relief-refinance and seasoned/modified loans excluded.",
    "rate_spread = loan rate minus the typical rate of the same quarter and term: the caller must compute it with a reliable reference rate.",
    "No protected characteristic exists in the data, so fairness toward them could not be tested.",
    "Portfolio project, not a lending product.",
]


def export_model(sc: Scorecard, meta: dict, reason_table: dict | None = None) -> dict:
    reason_table = reason_table or load_reason_table()
    missing = [f for f in sc.selected_ if f not in reason_table]
    if missing:
        raise ValueError(f"no approved reason sentence for {missing}: add them to config/reason_codes.yaml")
    factor, offset = sc._scaling()
    table = sc.points_table()
    features = {}
    for name in sc.selected_:
        fb = sc.bins_[name]
        pts = [float(p) for p in table[table["feature"] == name]["points"]]
        spec = {"type": fb.kind, "labels": [str(b) for b in fb.band_labels()], "points": pts}
        if fb.kind == "numeric":
            spec["edges"] = [float(e) for e in fb.edges]
        else:
            spec["categories"] = [str(c) for c in fb.categories]
        features[name] = spec
    s = sc.cfg["scorecard_scaling"]
    model = {
        "schema_version": SCHEMA_VERSION,
        "model": "woe_scorecard_v2",
        "scaling": {"base_score": s["base_score"], "base_odds": s["base_odds"], "points_to_double_odds": s["points_to_double_odds"],
                    "factor": float(factor), "offset": float(offset)},
        "feature_order": list(sc.selected_),
        "features": features,
        "best_points": {k: float(v) for k, v in best_points(sc).items()},
        "reason_codes": {n: {"code": reason_table[n]["code"], "phrase": reason_table[n]["phrase"],
                             "reportable": bool(reason_table[n].get("reportable", True))} for n in sc.selected_},
        "known_limits": KNOWN_LIMITS,
    }
    model["model_id"] = canonical_hash(model)[:12]
    model.update(meta)
    return model


def main() -> None:
    from credit.models.era_review import FEATURES_PATH, load_dev
    from credit.models.v2_exam import TARGET, V2_CATEGORICAL, V2_NUMERIC, v2_config

    dev = load_dev()
    cols = V2_NUMERIC + V2_CATEGORICAL
    sc = Scorecard(v2_config(), V2_NUMERIC, V2_CATEGORICAL).fit(dev[cols], dev[TARGET])
    meta = {
        "version": "2026-10-11",
        "exported_on": date.today().isoformat(),
        "trained_on": "all kept loans of the 2008, 2012, 2016, 2019 and 2022 Freddie Mac samples (aggregate bands only are stored)",
        "training_data_sha256": hashlib.sha256(FEATURES_PATH.read_bytes()).hexdigest(),
        "adopted_by": "pre-registered exam on fresh vintages 2010/2014/2018/2023 (docs/v2_preregistration.md, results/v2_exam.md)",
    }
    model = export_model(sc, meta)
    MODEL_PATH.parent.mkdir(exist_ok=True)
    save_model(model, MODEL_PATH)
    print(f"wrote {MODEL_PATH.relative_to(ROOT)} ({MODEL_PATH.stat().st_size:,} bytes), model_id {model['model_id']}")
    print(json.dumps({k: model[k] for k in ("model", "version", "model_id")}))


if __name__ == "__main__":
    main()
