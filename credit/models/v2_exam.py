"""Model v2 exam: three scorecard arms face FRESH vintages, once, after a committed freeze.

Arms
  v1   the frozen v1 scorecard (trained on the v1 training split, v1 features)
  v1b  v1 features, retrained on ALL rows of the five known vintages (isolates the effect of the training data)
  v2   fixed features (no state / channel / super_conforming, several_borrowers instead of n_borrowers, purpose added),
       same training rows as v1b (isolates the effect of the feature changes)
Fresh vintages: 2010, 2014, 2018, 2023 (labels locked until `run`). Rules and predictions: docs/v2_preregistration.md.

Usage (from the repo root):
  .venv/Scripts/python -m credit.models.v2_exam freeze   -> writes results/frozen_v2_before_exam.json (then COMMIT it)
  .venv/Scripts/python -m credit.models.v2_exam run      -> refuses unless the freeze is intact and committed
"""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES  # noqa: E402
from credit.freddie.fresh import FRESH_PATH, load_fresh  # noqa: E402
from credit.models import metrics  # noqa: E402
from credit.models.era_review import FEATURES_PATH, load_dev  # noqa: E402
from credit.models.fairness import slice_table  # noqa: E402
from credit.models.final_exam import fit_models  # noqa: E402
from credit.models.scorecard import CONFIG_PATH, Scorecard, load_config  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
MANIFEST = RESULTS / "frozen_v2_before_exam.json"
PREREG = DOCS / "v2_preregistration.md"
WATCHED = ["credit", "config", "docs/v2_preregistration.md"]
FRESH_VINTAGES = (2010, 2014, 2018, 2023)
TARGET = "default_24m"
ARMS = ("v1", "v1b", "v2")
BOOT = {"resamples": 1000, "seed": 20261011}
NON_INFERIORITY_MARGIN = 0.03

V2_NUMERIC = ["credit_score", "dti", "rate_spread", "ltv", "cltv", "several_borrowers", "mi_pct", "orig_term"]
V2_CATEGORICAL = ["purpose"]
SLICE_VARIABLES = ["first_time_homebuyer", "occupancy", "purpose", "property_type", "channel", "state"]


class NotFrozenError(Exception):
    pass


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def v2_config() -> dict:
    cfg = copy.deepcopy(load_config())
    cfg["scorecard_binning"]["min_iv"] = 0.0  # features were selected by the within-vintage rule, not the pooled IV
    return cfg


def build_manifest() -> dict:
    return {
        "frozen_at_commit": git("rev-parse", "HEAD"),
        "dev_features_sha256": sha256(FEATURES_PATH),
        "fresh_features_sha256": sha256(FRESH_PATH),
        "assumptions_sha256": sha256(CONFIG_PATH),
        "preregistration_sha256": sha256(PREREG),
        "arms": {"v1": "frozen v1 scorecard (train split, v1 features)",
                 "v1b": "v1 features retrained on all rows of the 5 known vintages",
                 "v2": {"numeric": V2_NUMERIC, "categorical": V2_CATEGORICAL, "min_iv": 0.0, "training": "same rows as v1b"}},
        "fresh_vintages": list(FRESH_VINTAGES),
        "bootstrap": BOOT,
        "non_inferiority_margin_gini": NON_INFERIORITY_MARGIN,
    }


def check_frozen(manifest_path: Path = MANIFEST, dev_path: Path = FEATURES_PATH, fresh_path: Path = FRESH_PATH,
                 config_path: Path = CONFIG_PATH, prereg_path: Path = PREREG, use_git: bool = True) -> dict:
    if not manifest_path.exists():
        raise NotFrozenError("results/frozen_v2_before_exam.json is missing: run 'freeze' and commit it")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    for key, path, what in (("dev_features_sha256", dev_path, "development features"), ("fresh_features_sha256", fresh_path, "fresh features"),
                            ("assumptions_sha256", config_path, "config/assumptions.yaml"),
                            ("preregistration_sha256", prereg_path, "the pre-registration")):
        if sha256(path) != m[key]:
            raise NotFrozenError(f"{what} changed after the freeze")
    if use_git:
        rel = str(manifest_path.relative_to(ROOT))
        if git("status", "--porcelain", "--", *WATCHED, rel):
            raise NotFrozenError("code, config, pre-registration or manifest have uncommitted changes")
        changed = git("diff", "--name-only", m["frozen_at_commit"], "HEAD", "--", *WATCHED)
        if changed:
            raise NotFrozenError(f"files changed since the freeze commit: {changed.splitlines()}")
        if not git("log", "--oneline", "-1", "--", rel):
            raise NotFrozenError("the manifest has not been committed")
    return m


def fit_arms() -> dict:
    """name -> function(df) -> probabilities. v1b and v2 train on every row of the five known vintages."""
    dev = load_dev()
    cfg = load_config()
    v1 = fit_models()["scorecard"]
    v1b_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    v1b = Scorecard(cfg).fit(dev[v1b_cols], dev[TARGET])
    v2 = Scorecard(v2_config(), V2_NUMERIC, V2_CATEGORICAL).fit(dev[V2_NUMERIC + V2_CATEGORICAL], dev[TARGET])
    return {"v1": v1, "v1b": lambda df: v1b.predict_proba(df[v1b_cols]),
            "v2": lambda df: v2.predict_proba(df[V2_NUMERIC + V2_CATEGORICAL])}, v2


def bootstrap(ys: dict, probs: dict, n_boot: int, seed: int) -> dict:
    """Paired bootstrap: per vintage, the same resampled loans for every arm. Returns arrays of shape (n_boot,)."""
    rng = np.random.default_rng(seed)
    out = {v: {a: {"gini": [], "brier": [], "ratio": []} for a in probs} for v in ys}
    for _ in range(n_boot):
        for v, y in ys.items():
            idx = rng.integers(0, len(y), len(y))
            yb = y[idx]
            if yb.sum() == 0:
                for a in probs:
                    for k in out[v][a]:
                        out[v][a][k].append(np.nan)
                continue
            for a, p in probs.items():
                pb = p[v][idx]
                out[v][a]["gini"].append(metrics.gini(yb, pb))
                out[v][a]["brier"].append(metrics.brier(yb, pb))
                out[v][a]["ratio"].append(float(pb.mean() / yb.mean()))
    return {v: {a: {k: np.asarray(x) for k, x in d.items()} for a, d in arms.items()} for v, arms in out.items()}


def ci(a) -> list:
    a = np.asarray(a)
    a = a[~np.isnan(a)]
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def group_spread(df: pd.DataFrame, p: np.ndarray) -> dict:
    """Largest / smallest predicted-over-observed ratio among groups with >= 30 defaults, per slice variable."""
    out = {}
    for var in SLICE_VARIABLES:
        t = slice_table(df, p, df[TARGET].to_numpy(), threshold=1.0, variable=var, min_loans=500)
        t = t[t["defaults"] >= 30]
        out[var] = float(t["pred_over_obs"].max() / t["pred_over_obs"].min()) if len(t) >= 2 else None
    return out


def run() -> dict:
    manifest = check_frozen()
    predict, _v2 = fit_arms()
    data = {v: load_fresh([v], allow_exam=True).reset_index(drop=True) for v in FRESH_VINTAGES}  # the only place they are opened
    ys = {v: d[TARGET].to_numpy() for v, d in data.items()}
    probs = {a: {v: np.asarray(predict[a](d)) for v, d in data.items()} for a in ARMS}
    boot = bootstrap(ys, probs, manifest["bootstrap"]["resamples"], manifest["bootstrap"]["seed"])

    res = {"frozen_at_commit": manifest["frozen_at_commit"], "vintages": {}, "summary": {}}
    for v, d in data.items():
        block = {"loans": int(len(d)), "defaults": int(ys[v].sum()), "default_rate": float(ys[v].mean()), "arms": {}, "differences": {}}
        for a in ARMS:
            m = metrics.evaluate(ys[v], probs[a][v])
            m["ece"] = metrics.ece(ys[v], probs[a][v])
            m["ci95"] = {k: ci(boot[v][a][k]) for k in ("gini", "brier", "ratio")}
            block["arms"][a] = m
        for a, b in (("v2", "v1"), ("v2", "v1b"), ("v1b", "v1")):
            dg = boot[v][a]["gini"] - boot[v][b]["gini"]
            lo, hi = ci(dg)
            block["differences"][f"{a} minus {b}"] = {"gini": block["arms"][a]["gini"] - block["arms"][b]["gini"], "ci95": [lo, hi]}
        res["vintages"][v] = block

    # primary criterion: mean over the four vintages of the Gini difference, paired bootstrap
    for a, b in (("v2", "v1"), ("v2", "v1b"), ("v1b", "v1")):
        mean_d = np.nanmean([boot[v][a]["gini"] - boot[v][b]["gini"] for v in FRESH_VINTAGES], axis=0)
        point = float(np.mean([res["vintages"][v]["arms"][a]["gini"] - res["vintages"][v]["arms"][b]["gini"] for v in FRESH_VINTAGES]))
        lo, hi = ci(mean_d)
        res["summary"][f"mean gini difference {a} minus {b}"] = {"difference": point, "ci95": [lo, hi],
                                                                "non_inferior_margin_0.03": bool(lo > -NON_INFERIORITY_MARGIN),
                                                                "superior": bool(lo > 0)}
    pooled = pd.concat(data.values(), ignore_index=True)
    spreads = {a: group_spread(pooled, np.concatenate([probs[a][v] for v in FRESH_VINTAGES])) for a in ARMS}
    res["group_calibration_spread_(max/min of predicted/observed among groups with >=30 defaults)"] = spreads
    better = [var for var in SLICE_VARIABLES if spreads["v2"][var] is not None and spreads["v1"][var] is not None and spreads["v2"][var] < spreads["v1"][var]]
    res["summary"]["slice variables where v2 has the smaller spread than v1"] = {"count": len(better), "variables": better, "needed": 4}

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "v2_exam.json").write_text(json.dumps(res, indent=2, default=float), encoding="utf-8")
    write_markdown(res)
    plot(res)
    return res


def write_markdown(res: dict) -> None:
    L = ["# Model v2 exam (fresh vintages, run once after the freeze)", "", f"Frozen at commit `{res['frozen_at_commit'][:10]}`. 95% paired-bootstrap intervals, 1000 resamples.", "",
         "| Vintage | loans / defaults | arm | Gini (95% CI) | KS | Brier | predicted vs real | ratio (95% CI) |", "|---|---|---|---|---|---|---|---|"]
    for v, b in res["vintages"].items():
        for a, m in b["arms"].items():
            g, r = m["ci95"]["gini"], m["ci95"]["ratio"]
            L.append(f"| {v} | {b['loans']:,} / {b['defaults']} | {a} | {m['gini']:.3f} ({g[0]:.3f}-{g[1]:.3f}) | {m['ks']:.3f} | {m['brier']:.5f} | "
                     f"{m['mean_predicted_pd']:.2%} vs {b['default_rate']:.2%} | {m['mean_predicted_pd'] / b['default_rate']:.2f} ({r[0]:.2f}-{r[1]:.2f}) |")
    L += ["", "## Gini differences per vintage (95% CI)", ""]
    for v, b in res["vintages"].items():
        L.append(f"- {v}: " + "; ".join(f"{k} {d['gini']:+.3f} ({d['ci95'][0]:+.3f} to {d['ci95'][1]:+.3f})" for k, d in b["differences"].items()))
    L += ["", "## Pre-registered criteria", ""]
    for k, d in res["summary"].items():
        L.append(f"- {k}: {d}")
    L += ["", "## Group calibration spread", ""]
    for a, s in res["group_calibration_spread_(max/min of predicted/observed among groups with >=30 defaults)"].items():
        L.append(f"- {a}: " + ", ".join(f"{k} {v:.2f}" if v is not None else f"{k} n/a" for k, v in s.items()))
    (RESULTS / "v2_exam.md").write_text("\n".join(L), encoding="utf-8")


def plot(res: dict) -> None:
    vs = list(res["vintages"])
    x, w = np.arange(len(vs)), 0.25
    fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
    for j, a in enumerate(ARMS):
        g = np.array([res["vintages"][v]["arms"][a]["gini"] for v in vs])
        lo = np.array([res["vintages"][v]["arms"][a]["ci95"]["gini"][0] for v in vs])
        hi = np.array([res["vintages"][v]["arms"][a]["ci95"]["gini"][1] for v in vs])
        ax[0].bar(x + (j - 1) * w, g, w, yerr=[g - lo, hi - g], capsize=3, label=a)
        ax[1].bar(x + (j - 1) * w, [res["vintages"][v]["arms"][a]["mean_predicted_pd"] / res["vintages"][v]["default_rate"] for v in vs], w, label=a)
    ax[0].set_xticks(x, [str(v) for v in vs])
    ax[0].set_ylabel("Gini")
    ax[0].set_title("Ranking on fresh vintages (95% intervals)")
    ax[0].legend()
    ax[1].axhline(1.0, color="black", lw=1)
    ax[1].set_xticks(x, [str(v) for v in vs])
    ax[1].set_ylabel("predicted / observed default rate")
    ax[1].set_title("Level of the predictions (1.0 = honest)")
    ax[1].legend()
    fig.tight_layout()
    fig.savefig(DOCS / "v2_exam.png", dpi=130)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "freeze":
        m = build_manifest()
        MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
        print(f"frozen at commit {m['frozen_at_commit'][:10]}; now COMMIT results/frozen_v2_before_exam.json, then run")
    elif cmd == "run":
        run()
        print((RESULTS / "v2_exam.md").read_text(encoding="utf-8"))
    else:
        print("usage: python -m credit.models.v2_exam freeze | run")
