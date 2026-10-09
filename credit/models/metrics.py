"""Credit-risk metrics. y = 1 for default, p = predicted probability of default."""
import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score, roc_curve


def auc(y, p) -> float:
    """Chance that a random defaulter gets a higher risk than a random non-defaulter."""
    return float(roc_auc_score(y, p))


def gini(y, p) -> float:
    """Banker's version of AUC: 2 * AUC - 1 (0 = coin flip, 1 = perfect)."""
    return 2 * auc(y, p) - 1


def ks(y, p) -> float:
    """Largest gap between the share of defaulters and of non-defaulters caught at the same cut-off."""
    fpr, tpr, _ = roc_curve(y, p)
    return float(np.max(tpr - fpr))


def pr_auc(y, p) -> float:
    """Area under the precision-recall curve (more informative when defaults are rare)."""
    return float(average_precision_score(y, p))


def brier(y, p) -> float:
    """Mean squared error of the probabilities (smaller = more honest percentages)."""
    return float(brier_score_loss(y, p))


def evaluate(y, p) -> dict:
    y = np.asarray(y)
    p = np.asarray(p)
    return {
        "n": int(len(y)),
        "defaults": int(y.sum()),
        "default_rate": float(y.mean()),
        "mean_predicted_pd": float(p.mean()),
        "auc": auc(y, p),
        "gini": gini(y, p),
        "ks": ks(y, p),
        "pr_auc": pr_auc(y, p),
        "brier": brier(y, p),
    }


def calibration_table(y, p, n_bins: int = 10):
    """For equal-sized groups of loans sorted by predicted risk: average predicted vs observed default rate."""
    import pandas as pd

    df = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    df["bin"] = pd.qcut(df["p"].rank(method="first"), n_bins, labels=False)
    out = df.groupby("bin").agg(loans=("y", "size"), predicted=("p", "mean"), observed=("y", "mean")).reset_index()
    return out


def ece(y, p, n_bins: int = 10) -> float:
    """Expected calibration error: average gap between predicted and observed default rate,
    over equal-sized risk groups, weighted by group size (0 = perfectly honest percentages)."""
    t = calibration_table(y, p, n_bins=n_bins)
    return float((t["loans"] * (t["predicted"] - t["observed"]).abs()).sum() / t["loans"].sum())
