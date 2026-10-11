"""Score many loans at once from the model file (numpy). Must give EXACTLY what `credit.serving.model_file.score_loan` gives.

The API scores one loan with the stdlib scorer; monitoring scores hundreds of thousands, so it needs a vectorized version.
A test compares the two on random loans, including values on band edges, missing values and unseen categories.
"""
import numpy as np
import pandas as pd


def band_index(spec: dict, values: pd.Series) -> np.ndarray:
    """Band number of every value (same rules as the file scorer: edge values belong to the lower band)."""
    if spec["type"] == "numeric":
        x = pd.to_numeric(values, errors="coerce").to_numpy(dtype=float)
        idx = np.searchsorted(np.asarray(spec["edges"], dtype=float), x, side="left")
        return np.where(np.isnan(x), len(spec["edges"]) + 1, idx)
    cats = spec["categories"]
    lookup = {c: i for i, c in enumerate(cats)}
    out = np.empty(len(values), dtype=int)
    for i, v in enumerate(values.to_numpy(dtype=object)):
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            out[i] = len(cats) + 1
        else:
            out[i] = lookup.get(v, len(cats))
    return out


def score_frame(model: dict, df: pd.DataFrame) -> pd.DataFrame:
    """Add `score` and `pd` columns (and keep nothing else): points of each feature's band, summed."""
    total = np.zeros(len(df))
    for name in model["feature_order"]:
        spec = model["features"][name]
        total += np.asarray(spec["points"], dtype=float)[band_index(spec, df[name])]
    sc = model["scaling"]
    z = np.clip((total - sc["offset"]) / sc["factor"], -700, 700)
    return pd.DataFrame({"score": total, "pd": 1.0 / (1.0 + np.exp(z))}, index=df.index)
