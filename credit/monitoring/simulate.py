"""Simulated shifts: fire drills that test whether the monitors really raise an alarm. EVERYTHING here is simulated.

A shift damages a copy of a batch in a controlled way (scores of borrowers go down, a value goes missing, a never-seen
category appears, defaults become more frequent). We then record whether each monitor noticed. The settings are in
config/monitoring.yaml and were fixed before any result existed (docs/monitoring_preregistration.md).
"""
import numpy as np
import pandas as pd

from credit.monitoring.drift import Profile, alerts, warnings_or_worse
from credit.monitoring.scoring import score_frame

LIMITS = {"credit_score": (300, 850), "dti": (0, 65), "ltv": (1, 300), "cltv": (1, 300)}  # valid ranges of the data dictionary


def apply_shift(batch: pd.DataFrame, y: np.ndarray, spec: dict, rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    """Return a damaged copy of (batch, y). The input is never modified."""
    b, y = batch.copy(), y.copy()
    kind = spec["kind"]
    if kind in ("shift", "shift_many"):
        for f in [spec["feature"]] if kind == "shift" else spec["features"]:
            lo, hi = LIMITS.get(f, (-np.inf, np.inf))
            b[f] = (pd.to_numeric(b[f], errors="coerce") + spec["delta"]).clip(lo, hi)
    elif kind == "missing":
        hit = rng.random(len(b)) < spec["share"]
        b.loc[hit, spec["feature"]] = np.nan
    elif kind == "new_category":
        hit = rng.random(len(b)) < spec["share"]
        b[spec["feature"]] = b[spec["feature"]].astype(object)
        b.loc[hit, spec["feature"]] = spec["value"]
    elif kind == "default_rate":
        target = min(int(round(y.sum() * spec["factor"])), len(y))
        zeros = np.flatnonzero(y == 0)
        extra = max(target - int(y.sum()), 0)
        y[rng.choice(zeros, size=min(extra, len(zeros)), replace=False)] = 1
    else:
        raise ValueError(f"unknown shift kind: {kind}")
    return b, y


def run_simulation(model: dict, pool: pd.DataFrame, y: np.ndarray, cfg: dict) -> dict:
    """`pool`: model inputs of the development loans, `y`: their 0/1 outcomes. Returns one row per drill (control first)."""
    sim = cfg["simulation"]
    rng = np.random.default_rng(sim["seed"])
    batch_idx = np.sort(rng.choice(len(pool), size=sim["batch_size"], replace=False))
    is_batch = np.zeros(len(pool), dtype=bool)
    is_batch[batch_idx] = True
    ref = pool[~is_batch].copy()
    ref = ref.join(score_frame(model, ref))
    profile = Profile(model, ref, cfg)
    base_batch, base_y = pool[is_batch].copy(), y[is_batch]

    rows = {}
    for sid, spec in {"C0": None, **sim["shifts"]}.items():
        if spec is None:
            b, yy = base_batch.copy(), base_y.copy()
        else:
            b, yy = apply_shift(base_batch, base_y, spec, np.random.default_rng(sim["seed"] + 1))
        b = b.join(score_frame(model, b))
        rep = profile.compare(b, yy)
        rows[sid] = {
            "spec": spec or "none (control)", "simulated": True,
            "alert_monitors": alerts(rep), "warn_or_worse_monitors": warnings_or_worse(rep),
            "alert": bool(alerts(rep)), "warn_or_worse": bool(warnings_or_worse(rep)),
            "score_psi": rep["score_psi"], "max_csi": max(rep["csi"].values()),
            "max_csi_feature": max(rep["csi"], key=rep["csi"].get), "level_ratio": rep["level"]["ratio"],
        }
    expected = set(sim["expect_alert"])
    caught = sorted(s for s in expected if rows[s]["alert"])
    return {
        "batch_size": sim["batch_size"], "reference_size": int(len(ref)), "drills": rows,
        "control_clean": not rows["C0"]["warn_or_worse"],
        "expected_alerts": sorted(expected), "caught": caught, "missed": sorted(expected - set(caught)),
        "R_M1_control_clean": not rows["C0"]["warn_or_worse"],
        "R_M2_enough_alerts": len(caught) >= sim["min_alerts_expected"],
    }
