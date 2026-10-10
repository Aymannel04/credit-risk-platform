"""The scorecard as a small JSON file, and a scorer that needs nothing but this file.

STANDARD LIBRARY ONLY on purpose (no numpy, pandas, scikit-learn): the API loads this module, so it stays tiny and fast
to start (important on AWS Lambda), and anybody can read and audit the model.

How a score is computed (the whole model):
  for each feature: find the band the value falls in -> take the points of that band
  total score = sum of the points
  probability of default = 1 / (1 + e^((score - offset) / factor))      (offset and factor come from the scaling)
Numeric bands are (edge[i-1], edge[i]]: a value equal to an edge belongs to the lower band. Missing values and, for
categories, unseen values have their own bands. Reasons are the features where a loan loses the most points compared
with the best band of that feature (fixed sentences stored in the file).
"""
import bisect
import hashlib
import json
import math
from pathlib import Path

SCHEMA_VERSION = 1


class ModelFileError(ValueError):
    """The model file is malformed or has been tampered with."""


def canonical_hash(model: dict) -> str:
    """A stable fingerprint of what the model computes (scaling + features), independent of descriptive metadata."""
    core = {"scaling": model["scaling"], "feature_order": model["feature_order"], "features": model["features"]}
    return hashlib.sha256(json.dumps(core, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def validate_model(model: dict) -> dict:
    """Raise ModelFileError unless the structure is exactly what the scorer expects."""
    for key in ("schema_version", "model", "scaling", "feature_order", "features", "best_points", "reason_codes", "known_limits"):
        if key not in model:
            raise ModelFileError(f"missing key: {key}")
    if model["schema_version"] != SCHEMA_VERSION:
        raise ModelFileError(f"unsupported schema_version {model['schema_version']} (expected {SCHEMA_VERSION})")
    sc = model["scaling"]
    for key in ("base_score", "base_odds", "points_to_double_odds", "factor", "offset"):
        if not isinstance(sc.get(key), (int, float)) or not math.isfinite(sc[key]):
            raise ModelFileError(f"scaling.{key} must be a finite number")
    if sc["factor"] <= 0:
        raise ModelFileError("scaling.factor must be positive")
    if set(model["feature_order"]) != set(model["features"]) or len(set(model["feature_order"])) != len(model["feature_order"]):
        raise ModelFileError("feature_order and features disagree")
    for name, f in model["features"].items():
        pts = f.get("points")
        if not pts or not all(isinstance(p, (int, float)) and math.isfinite(p) for p in pts):
            raise ModelFileError(f"{name}: points must be finite numbers")
        if f.get("type") == "numeric":
            e = f.get("edges", [])
            if any(not math.isfinite(x) for x in e) or any(b <= a for a, b in zip(e, e[1:], strict=False)):
                raise ModelFileError(f"{name}: edges must be finite and strictly increasing")
            if len(pts) != len(e) + 2:  # bands + missing
                raise ModelFileError(f"{name}: expected {len(e) + 2} points")
        elif f.get("type") == "categorical":
            if len(pts) != len(f.get("categories", [])) + 2:  # categories + other + missing
                raise ModelFileError(f"{name}: expected {len(f.get('categories', [])) + 2} points")
        else:
            raise ModelFileError(f"{name}: unknown type {f.get('type')}")
        if len(f.get("labels", [])) != len(pts):
            raise ModelFileError(f"{name}: labels and points differ in length")
        if name not in model["best_points"] or name not in model["reason_codes"]:
            raise ModelFileError(f"{name}: missing best_points or reason_codes")
    return model


def load_model(path) -> dict:
    return validate_model(json.loads(Path(path).read_text(encoding="utf-8")))


def save_model(model: dict, path) -> None:
    validate_model(model)
    Path(path).write_text(json.dumps(model, indent=1, sort_keys=False) + "\n", encoding="utf-8")


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _band_index(spec: dict, name: str, value) -> int:
    """Index of the band (into spec['points'] and spec['labels']) for one value."""
    if spec["type"] == "numeric":
        if _is_missing(value):
            return len(spec["edges"]) + 1
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name}: expected a number, got {type(value).__name__}")
        if not math.isfinite(value):
            raise ValueError(f"{name}: value must be finite")
        return bisect.bisect_left(spec["edges"], value)  # value == edge -> lower band, like the training code
    cats = spec["categories"]
    if _is_missing(value):
        return len(cats) + 1
    if not isinstance(value, str):
        raise ValueError(f"{name}: expected a text category, got {type(value).__name__}")
    return cats.index(value) if value in cats else len(cats)  # unseen category -> the "other" band


def score_loan(model: dict, loan: dict) -> dict:
    """Score one loan from the model file alone. `loan` must contain exactly the model's features (None = missing)."""
    names = model["feature_order"]
    unknown = sorted(set(loan) - set(names))
    absent = [n for n in names if n not in loan]
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")
    if absent:
        raise ValueError(f"missing fields: {absent} (use null for an unknown value)")
    points, bands = {}, {}
    for name in names:
        spec = model["features"][name]
        i = _band_index(spec, name, loan[name])
        points[name], bands[name] = spec["points"][i], spec["labels"][i]
    score = sum(points.values())
    sc = model["scaling"]
    z = (score - sc["offset"]) / sc["factor"]
    pd_ = 1.0 / (1.0 + math.exp(z)) if z < 700 else 0.0  # exp overflows beyond ~709; the probability is 0 there
    return {"score": score, "probability_of_default": pd_, "points": points, "bands": bands}


def explain_loan(model: dict, scored: dict, top_k: int = 4, min_points_lost: float = 5.0) -> list:
    """Reasons: features where the loan loses the most points versus the best band. Only fixed sentences, only reportable ones."""
    names = model["feature_order"]
    lost = {n: model["best_points"][n] - scored["points"][n] for n in names if model["reason_codes"][n].get("reportable", True)}
    order = sorted(lost, key=lambda n: (-lost[n], names.index(n)))
    out = []
    for n in order[:top_k]:
        if lost[n] < min_points_lost:
            break
        rc = model["reason_codes"][n]
        out.append({"code": rc["code"], "feature": n, "phrase": rc["phrase"], "band": scored["bands"][n], "points_lost": lost[n]})
    return out
