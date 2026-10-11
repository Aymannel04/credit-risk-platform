"""Can history alone repair the level? (pre-registered in docs/monitoring_preregistration.md, Part C)

For a target vintage V we only use outcomes that were already known when V started (vintage Y is known if Y <= V - lag).
A constant is added on the log-odds scale so that the mean predicted PD of the reference loans equals their observed
default rate; the same constant is applied to V. Adding a constant keeps the ranking, so Gini cannot change.
Arms: A static (nothing), B last (reference = the most recent known vintage), C pooled (all known vintages pooled).
"""
import numpy as np

from credit.models import metrics

ARMS = ("A_static", "B_last", "C_pooled")


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    return np.log(p / (1 - p))


def shift_probabilities(p: np.ndarray, delta: float) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-(_logit(p) + delta)))


def solve_shift(p: np.ndarray, target_rate: float, tol: float = 1e-12) -> float:
    """The constant delta such that mean(shift_probabilities(p, delta)) == target_rate (bisection; the mean rises with delta)."""
    if not 0 < target_rate < 1:
        raise ValueError("target_rate must be strictly between 0 and 1")
    lo, hi = -30.0, 30.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if shift_probabilities(p, mid).mean() < target_rate:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def known_vintages(target: int, vintages: list[int], lag: int) -> list[int]:
    return sorted(v for v in vintages if v <= target - lag)


def level_error(p: np.ndarray, y: np.ndarray) -> float:
    """|ln(mean predicted PD / observed default rate)|: 0 is a perfect level."""
    return float(abs(np.log(np.mean(p) / np.mean(y))))


def run(frames: dict, cfg: dict) -> dict:
    """`frames`: vintage -> DataFrame with columns `pd` (predicted PD) and `y` (0/1). Returns one row per target vintage."""
    lag = cfg["recalibration"]["label_lag_years"]
    vintages = sorted(frames)
    rows = {}
    for v in vintages:
        known = known_vintages(v, vintages, lag)
        if not known:
            continue
        p, y = frames[v]["pd"].to_numpy(), frames[v]["y"].to_numpy()
        last = frames[known[-1]]
        pool_p = np.concatenate([frames[k]["pd"].to_numpy() for k in known])
        pool_y = np.concatenate([frames[k]["y"].to_numpy() for k in known])
        deltas = {
            "A_static": 0.0,
            "B_last": solve_shift(last["pd"].to_numpy(), float(last["y"].mean())),
            "C_pooled": solve_shift(pool_p, float(pool_y.mean())),
        }
        row = {"known_vintages": known, "observed": float(y.mean()), "n": int(len(y))}
        base_gini = metrics.gini(y, p)
        for arm, d in deltas.items():
            q = shift_probabilities(p, d) if d else p
            row[arm] = {
                "delta": d, "mean_predicted": float(q.mean()), "level_error": level_error(q, y),
                "ratio_observed_over_predicted": float(y.mean() / q.mean()), "brier": float(metrics.brier(y, q)),
                "gini": float(metrics.gini(y, q)), "gini_unchanged": bool(abs(metrics.gini(y, q) - base_gini) < 1e-9),
            }
        rows[v] = row
    return rows


def verdict(rows: dict, cfg: dict) -> dict:
    """R-C1 for arms B and C against the static arm A, exactly as pre-registered."""
    c = cfg["recalibration"]
    targets = sorted(rows)
    base = np.array([rows[t]["A_static"]["level_error"] for t in targets])
    out = {"targets": targets, "mean_error_static": float(base.mean())}
    for arm in ("B_last", "C_pooled"):
        e = np.array([rows[t][arm]["level_error"] for t in targets])
        improvement = 1 - e.mean() / base.mean()
        improved = int(np.sum(e < base))
        worst = float(np.max(e - base))
        checks = {
            "mean_improvement": float(improvement), "mean_improvement_ok": bool(improvement >= c["min_mean_improvement"]),
            "targets_improved": improved, "targets_improved_ok": improved >= c["min_targets_improved"],
            "worst_worsening": worst, "worst_worsening_ok": worst <= c["max_single_worsening"],
        }
        out[arm] = {**checks, "mean_error": float(e.mean()),
                    "recommended": all(checks[k] for k in ("mean_improvement_ok", "targets_improved_ok", "worst_worsening_ok")),
                    "improved_targets": [t for t, a, b in zip(targets, e, base, strict=True) if a < b]}
    out["R_C2_gini_unchanged"] = all(rows[t][a]["gini_unchanged"] for t in targets for a in ARMS)
    return out
