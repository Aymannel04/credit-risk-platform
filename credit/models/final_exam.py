"""THE FINAL EXAM: the three models face the test splits, once.

Refuses to run unless the freeze manifest exists, is committed, and nothing it fingerprints has changed.
Models are trained on `train` only. Raw probabilities (no calibration), as frozen.
Results: results/final_exam.json, results/final_exam.md, docs/final_exam.png.

Usage (from the repo root):  .venv/Scripts/python -m credit.models.final_exam
"""
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from credit.models import metrics, xgboost_model  # noqa: E402
from credit.models.baseline_logreg import build_model  # noqa: E402
from credit.models.data import FEATURES_PATH, TARGET, load, xy  # noqa: E402
from credit.models.freeze import MANIFEST, WATCHED_PATHS, git, sha256  # noqa: E402
from credit.models.scorecard import CONFIG_PATH, Scorecard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
EXAMS = ("test_in_time", "test_oot_2019", "test_oot_2022")


class NotFrozenError(Exception):
    """The exam must not run: the freeze is missing, uncommitted, or something changed after it."""


def check_frozen(manifest_path: Path = MANIFEST, features_path: Path = FEATURES_PATH, config_path: Path = CONFIG_PATH,
                 watched=tuple(WATCHED_PATHS), use_git: bool = True) -> dict:
    if not manifest_path.exists():
        raise NotFrozenError("results/frozen_before_exam.json is missing: run credit.models.freeze and commit it")
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if sha256(features_path) != m["features_sha256"]:
        raise NotFrozenError("the features file changed after the freeze")
    if sha256(config_path) != m["assumptions_sha256"]:
        raise NotFrozenError("config/assumptions.yaml changed after the freeze")
    if use_git:
        if git("status", "--porcelain", "--", *watched, str(manifest_path.relative_to(ROOT))):
            raise NotFrozenError("code, config or the manifest have uncommitted changes: commit or revert them first")
        changed = git("diff", "--name-only", m["frozen_at_commit"], "HEAD", "--", *watched)
        if changed:
            raise NotFrozenError(f"files changed since the freeze commit: {changed.splitlines()}")
        if not git("log", "--oneline", "-1", "--", str(manifest_path.relative_to(ROOT))):
            raise NotFrozenError("the manifest has not been committed")
    return m


def fit_models() -> dict:
    """All models fitted on the training split only. Returns name -> function(df) -> raw probabilities."""
    train = load("train")
    X_tr, y_tr = xy(train)
    scorecard = Scorecard().fit(X_tr, y_tr)
    logistic = build_model().fit(X_tr, y_tr)
    xgb = xgboost_model.fit(train)
    return {
        "scorecard": lambda df: scorecard.predict_proba(xy(df)[0]),
        "logistic_regression": lambda df: logistic.predict_proba(xy(df)[0])[:, 1],
        "xgboost": lambda df: xgb.predict_proba(xy(df)[0]),
    }


def bootstrap(y: np.ndarray, probs: dict, n_boot: int, seed: int) -> dict:
    """Paired bootstrap over loans: the same resampled loans are used for every model."""
    rng = np.random.default_rng(seed)
    n = len(y)
    out = {k: {"gini": [], "ks": [], "brier": [], "pred_over_obs": []} for k in probs}
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)
        yb = y[idx]
        if yb.sum() == 0:
            continue
        for k, p in probs.items():
            pb = p[idx]
            out[k]["gini"].append(metrics.gini(yb, pb))
            out[k]["ks"].append(metrics.ks(yb, pb))
            out[k]["brier"].append(metrics.brier(yb, pb))
            out[k]["pred_over_obs"].append(float(pb.mean() / yb.mean()))
    return {k: {m: np.asarray(v) for m, v in d.items()} for k, d in out.items()}


def ci(a: np.ndarray) -> list[float]:
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))]


def main() -> dict:
    manifest = check_frozen()
    rules = manifest["rules"]["confidence_intervals"]
    models = fit_models()
    result = {"frozen_at_commit": manifest["frozen_at_commit"], "exams": {}}
    for exam in EXAMS:
        df = load(exam, allow_test=True).reset_index(drop=True)  # the only place the tests are opened
        y = xy(df)[1].to_numpy()
        probs = {name: fn(df) for name, fn in models.items()}
        boot = bootstrap(y, probs, rules["resamples"], rules["seed"])
        block = {"n": int(len(y)), "defaults": int(y.sum()), "default_rate": float(y.mean()), "models": {}, "gini_differences": {}}
        for name, p in probs.items():
            m = metrics.evaluate(y, p)
            m["ece"] = metrics.ece(y, p)
            m["ci95"] = {k: ci(boot[name][k]) for k in ("gini", "ks", "brier", "pred_over_obs")}
            m["by_vintage"] = {
                int(v): {"n": int(len(g)), "defaults": int(g[TARGET].sum()),
                         "gini": metrics.gini(g[TARGET].astype(int), p[g.index.to_numpy()]) if g[TARGET].sum() >= 20 else None,
                         "mean_predicted_pd": float(p[g.index.to_numpy()].mean()), "observed": float(g[TARGET].mean())}
                for v, g in df.groupby("vintage_year")
            }
            block["models"][name] = m
        names = list(probs)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                d = boot[a]["gini"] - boot[b]["gini"]
                lo, hi = ci(d)
                block["gini_differences"][f"{a} minus {b}"] = {
                    "difference": block["models"][a]["gini"] - block["models"][b]["gini"], "ci95": [lo, hi],
                    "significant": bool(lo > 0 or hi < 0)}
        result["exams"][exam] = block

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "final_exam.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    write_markdown(result)
    plot(result)
    return result


def write_markdown(result: dict) -> None:
    lines = ["# Final exam (test splits, models trained on `train` only, raw probabilities)", "",
             f"Frozen at commit `{result['frozen_at_commit'][:10]}`. 95% intervals: paired bootstrap, 1000 resamples.", ""]
    for exam, b in result["exams"].items():
        lines += [f"## {exam}: {b['n']:,} loans, {b['defaults']} defaults ({b['default_rate']:.2%})", "",
                  "| Model | Gini (95% CI) | KS | Brier | mean predicted PD | predicted / observed (95% CI) |", "|---|---|---|---|---|---|"]
        for name, m in b["models"].items():
            g, r = m["ci95"]["gini"], m["ci95"]["pred_over_obs"]
            lines.append(f"| {name} | {m['gini']:.3f} ({g[0]:.3f} to {g[1]:.3f}) | {m['ks']:.3f} | {m['brier']:.5f} | "
                         f"{m['mean_predicted_pd']:.2%} | {m['mean_predicted_pd'] / m['default_rate']:.2f} ({r[0]:.2f} to {r[1]:.2f}) |")
        lines += ["", "Gini differences (95% CI; significant = interval excludes 0):", ""]
        for k, d in b["gini_differences"].items():
            lines.append(f"- {k}: {d['difference']:+.3f} ({d['ci95'][0]:+.3f} to {d['ci95'][1]:+.3f}) "
                         f"{'significant' if d['significant'] else 'not significant'}")
        lines.append("")
    (RESULTS / "final_exam.md").write_text("\n".join(lines), encoding="utf-8")


def plot(result: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6))
    names = list(next(iter(result["exams"].values()))["models"])
    x = np.arange(len(EXAMS))
    w = 0.25
    for j, name in enumerate(names):
        g = [result["exams"][e]["models"][name]["gini"] for e in EXAMS]
        lo = [result["exams"][e]["models"][name]["ci95"]["gini"][0] for e in EXAMS]
        hi = [result["exams"][e]["models"][name]["ci95"]["gini"][1] for e in EXAMS]
        axes[0].bar(x + (j - 1) * w, g, w, yerr=[np.array(g) - lo, np.array(hi) - g], capsize=3, label=name)
    axes[0].set_xticks(x, EXAMS)
    axes[0].set_ylabel("Gini (higher = better ranking)")
    axes[0].set_title("Ranking quality with 95% intervals")
    axes[0].legend()
    real = [result["exams"][e]["default_rate"] * 100 for e in EXAMS]
    axes[1].bar(x - 1.5 * w, real, w, color="black", label="real default rate")
    for j, name in enumerate(names):
        axes[1].bar(x + (j - 0.5) * w, [result["exams"][e]["models"][name]["mean_predicted_pd"] * 100 for e in EXAMS], w, label=name)
    axes[1].set_xticks(x, EXAMS)
    axes[1].set_ylabel("average default rate (%)")
    axes[1].set_title("Honesty of the level: predicted vs real")
    axes[1].legend()
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / "final_exam.png", dpi=130)


if __name__ == "__main__":
    main()
