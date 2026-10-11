"""The monitors: score PSI, one CSI per input (on the model's own bands) and the observed/predicted level ratio.

A `Profile` is the fixed reference (the development vintages). `Profile.compare(batch)` returns every monitor value for a
batch of loans together with its flag (ok / warn / alert), using the thresholds of config/monitoring.yaml.
"""
import numpy as np
import pandas as pd

from credit.models import metrics
from credit.monitoring.psi import counts_by_key, flag, psi
from credit.monitoring.scoring import band_index


def level(y: np.ndarray, p: np.ndarray) -> dict:
    """Observed default rate, mean predicted PD and their ratio (observed / predicted: below 1 means over-prediction)."""
    obs, pred = float(np.mean(y)), float(np.mean(p))
    return {"observed": obs, "predicted": pred, "ratio": obs / pred if pred > 0 else float("nan")}


def level_flag(ratio: float, cfg: dict) -> str:
    lo_a, hi_a = cfg["level_ratio"]["alert_outside"]
    lo_w, hi_w = cfg["level_ratio"]["warn_outside"]
    if not np.isfinite(ratio) or ratio < lo_a or ratio > hi_a:
        return "alert"
    return "warn" if ratio < lo_w or ratio > hi_w else "ok"


def _score_keys(score: np.ndarray, width: float) -> np.ndarray:
    return np.floor(np.asarray(score, dtype=float) / width).astype(int)


class Profile:
    """Reference distribution of the score and of every input's bands."""

    def __init__(self, model: dict, scored_ref: pd.DataFrame, cfg: dict):
        self.model, self.cfg = model, cfg
        self.width = cfg["psi"]["score_band_points"]
        self.ref_score_keys = _score_keys(scored_ref["score"].to_numpy(), self.width)
        self.ref_bands = {}
        for name in model["feature_order"]:
            spec = model["features"][name]
            self.ref_bands[name] = np.bincount(band_index(spec, scored_ref[name]), minlength=len(spec["points"]))

    def compare(self, batch: pd.DataFrame, y: np.ndarray | None = None) -> dict:
        """`batch` has the model inputs plus `score` and `pd`; `y` (0/1 outcomes) is optional."""
        c = self.cfg["psi"]
        keys = _score_keys(batch["score"].to_numpy(), self.width)
        universe = np.union1d(self.ref_score_keys, keys)
        score_psi = psi(counts_by_key(self.ref_score_keys, universe), counts_by_key(keys, universe), c["share_floor"])
        csi = {}
        for name in self.model["feature_order"]:
            spec = self.model["features"][name]
            cur = np.bincount(band_index(spec, batch[name]), minlength=len(spec["points"]))
            csi[name] = psi(self.ref_bands[name], cur, c["share_floor"])
        out = {
            "n": int(len(batch)),
            "score_psi": score_psi, "score_flag": flag(score_psi, c["warn"], c["alert"]),
            "csi": csi, "csi_flags": {k: flag(v, c["warn"], c["alert"]) for k, v in csi.items()},
        }
        if y is not None:
            lv = level(y, batch["pd"].to_numpy())
            out.update(level=lv, level_flag=level_flag(lv["ratio"], self.cfg), defaults=int(np.sum(y)),
                       gini=float(metrics.gini(y, batch["pd"].to_numpy())) if 0 < np.sum(y) < len(y) else float("nan"))
        return out


def alerts(report: dict) -> list[str]:
    """Names of the monitors at 'alert'."""
    out = ["score_psi"] if report["score_flag"] == "alert" else []
    out += [f"csi:{k}" for k, f in report["csi_flags"].items() if f == "alert"]
    if report.get("level_flag") == "alert":
        out.append("level_ratio")
    return out


def warnings_or_worse(report: dict) -> list[str]:
    """Names of the monitors at 'warn' or 'alert'."""
    out = ["score_psi"] if report["score_flag"] != "ok" else []
    out += [f"csi:{k}" for k, f in report["csi_flags"].items() if f != "ok"]
    if report.get("level_flag", "ok") != "ok":
        out.append("level_ratio")
    return out
