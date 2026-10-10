"""SHAP explanations for the XGBoost challenger, summed back to the original features."""
import numpy as np
import pandas as pd
import shap

from credit.freddie.features import FEATURES


def original_feature(column_name: str) -> str:
    """'num__credit_score' -> credit_score; 'num__missingindicator_dti' -> dti; 'cat__state_CA' -> state."""
    name = column_name.split("__", 1)[1]
    name = name.replace("missingindicator_", "")
    for f in sorted(FEATURES, key=len, reverse=True):
        if name == f or name.startswith(f + "_"):
            return f
    raise ValueError(f"cannot map {column_name} to a feature")


def shap_by_feature(bundle, X: pd.DataFrame) -> pd.DataFrame:
    """SHAP values (log-odds of default; positive = pushes the risk up), one column per original feature."""
    Xt = bundle.prep.transform(X)
    values = shap.TreeExplainer(bundle.model).shap_values(Xt)
    names = [original_feature(n) for n in bundle.prep.get_feature_names_out()]
    out = pd.DataFrame(values, columns=names).T.groupby(level=0).sum().T
    out.index = X.index
    return out


def topk_overlap(scorecard_reasons: list[list[dict]], shap_df: pd.DataFrame, k: int = 3) -> dict:
    """How often do the scorecard's top reasons and XGBoost's top risk-raising SHAP features agree?"""
    overlaps, top1 = [], []
    for i, rs in enumerate(scorecard_reasons):
        a = [r["feature"] for r in rs[:k]]
        if not a:
            continue
        b = list(shap_df.iloc[i].sort_values(ascending=False).index[:k])
        overlaps.append(len(set(a) & set(b)) / len(a))
        top1.append(a[0] in b)
    return {"loans": len(overlaps), "mean_overlap_top_k": float(np.mean(overlaps)), "top1_reason_in_shap_top_k": float(np.mean(top1))}
