"""Population Stability Index (PSI): how different is the distribution now from the reference?

Cut a variable in bands. For each band compare the share of loans now with the share in the reference:
    PSI = sum over bands of (share_now - share_ref) * ln(share_now / share_ref)
0 means identical. Each share is raised to a small floor so that an empty band does not give ln(0).
The same formula is called CSI (characteristic stability index) when applied to an input of the model, and PSI when
applied to the score. Common reading: below 0.10 stable, 0.10 to 0.25 look, 0.25 or more a big change (practice, not law).
"""
import numpy as np


def shares(counts: np.ndarray) -> np.ndarray:
    counts = np.asarray(counts, dtype=float)
    total = counts.sum()
    if total <= 0:
        raise ValueError("no observations")
    return counts / total


def psi(ref_counts, cur_counts, floor: float = 0.0001) -> float:
    ref = np.maximum(shares(ref_counts), floor)
    cur = np.maximum(shares(cur_counts), floor)
    return float(np.sum((cur - ref) * np.log(cur / ref)))


def flag(value: float, warn: float, alert: float) -> str:
    """'alert' if value >= alert, 'warn' if value >= warn, else 'ok'."""
    return "alert" if value >= alert else "warn" if value >= warn else "ok"


def counts_by_key(keys: np.ndarray, universe: np.ndarray) -> np.ndarray:
    """How many observations fall in each key of `universe` (a sorted array of all keys seen anywhere)."""
    pos = np.searchsorted(universe, keys)
    return np.bincount(pos, minlength=len(universe))
