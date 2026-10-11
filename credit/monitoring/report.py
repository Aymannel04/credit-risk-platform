"""Monitoring report: Part A (real drift per vintage), Part B (simulated shifts), Part C (recalibration experiment).

Refuses to run unless the pre-registration and the thresholds file are committed and unmodified (the same discipline as the
exam scripts), and records the commit in the result. Reads the fresh labels (the exam is already done) but never uses them to
choose anything.

Usage (from the repo root):  .venv/Scripts/python -m credit.monitoring.report
Writes results/monitoring_report.json, results/monitoring_report.md and docs/monitoring.png.
"""
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from credit.monitoring import recalibration
from credit.monitoring.drift import Profile
from credit.monitoring.scoring import score_frame
from credit.monitoring.simulate import run_simulation
from credit.serving.model_file import load_model

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "docs" / "monitoring_preregistration.md"
CONFIG = ROOT / "config" / "monitoring.yaml"
MODEL = ROOT / "models" / "scorecard_v2.json"
RESULTS = ROOT / "results"


def load_config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _git(args: list[str], root: Path) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
        return r.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def prereg_state(files: tuple[Path, ...] = (PREREG, CONFIG), root: Path = ROOT) -> dict:
    """For each file: the last commit that touched it and whether it has uncommitted changes."""
    out = {}
    for f in files:
        rel = str(f.relative_to(root)).replace("\\", "/")
        commit = _git(["log", "-1", "--format=%H", "--", rel], root)
        dirty = _git(["status", "--porcelain", "--", rel], root)
        out[rel] = {"commit": commit or None, "clean": dirty == ""}
    return out


def build_frame(model: dict, cfg: dict) -> pd.DataFrame:
    """One row per kept loan: the model inputs, y (default_24m), vintage (sample year) and in_sample."""
    from credit.freddie.fresh import load_fresh
    from credit.models.era_review import load_dev

    ref_years = np.array(cfg["reference_vintages"])
    dev = load_dev()
    vy = dev["vintage_year"].to_numpy()
    dev["vintage"] = ref_years[np.abs(vy[:, None] - ref_years[None, :]).argmin(axis=1)]
    fresh = load_fresh(allow_exam=True)  # the exam is done: labels are open; nothing is chosen from them
    fresh["vintage"] = fresh["split"].str.replace("fresh_", "", regex=False).astype(int)
    cols = list(model["feature_order"]) + ["default_24m", "vintage"]
    frame = pd.concat([dev[cols], fresh[cols]], ignore_index=True)
    frame["y"] = frame["default_24m"].astype(int)
    frame["in_sample"] = frame["vintage"].isin(cfg["reference_vintages"])
    return frame.drop(columns="default_24m")


def part_a(model: dict, frame: pd.DataFrame, cfg: dict) -> dict:
    scored = frame.join(score_frame(model, frame))
    profile = Profile(model, scored[scored["in_sample"]], cfg)
    out = {}
    for v in sorted(scored["vintage"].unique()):
        b = scored[scored["vintage"] == v]
        rep = profile.compare(b, b["y"].to_numpy())
        rep["in_sample"] = bool(b["in_sample"].iloc[0])
        rep["max_csi_feature"] = max(rep["csi"], key=rep["csi"].get)
        out[int(v)] = rep
    return out, scored


def predictions(a: dict, b: dict, c_rows: dict, c_verdict: dict) -> list[dict]:
    """Every pre-registered prediction, scored as hit or miss."""
    p = []

    def add(pid, text, hit):
        p.append({"id": pid, "prediction": text, "hit": bool(hit)})

    add("A1", "2014 and 2018 raise a level ALERT (ratio below 0.67)", a[2014]["level_flag"] == "alert" and a[2018]["level_flag"] == "alert")
    top = max(a, key=lambda v: a[v]["score_psi"])
    add("A2", f"largest score PSI is in 2008, 2010 or 2023 (found: {top})", top in (2008, 2010, 2023))
    add("A3", "Gini between 0.40 and 0.70 on every vintage", all(0.40 <= r["gini"] <= 0.70 for r in a.values()))
    d = b["drills"]
    add("B1", "control raises no warn and no alert", b["control_clean"])
    for s in ("S1", "S3", "S4", "S5", "S9"):
        add(f"B-{s}", f"{s} raises an alert", d[s]["alert"])
    add("B-S2", "S2 (subtle) raises at most a warning", not d["S2"]["alert"])
    best = c_verdict["C_pooled"]["improved_targets"]
    add("C1", "arm B (last vintage) is not recommended", not c_verdict["B_last"]["recommended"])
    add("C2", "arm C (pooled) improves 2018, 2019, 2022, 2023 and worsens 2012 and 2014",
        {2018, 2019, 2022, 2023} <= set(best) and not ({2012, 2014} & set(best)))
    add("C3", "arm C (pooled) is not recommended", not c_verdict["C_pooled"]["recommended"])
    return p


def to_markdown(r: dict) -> str:
    a, b, c, v = r["part_a"], r["part_b"], r["part_c"], r["part_c_verdict"]
    L = [f"# Monitoring report (model `{r['model_id']}`)", "",
         f"Pre-registration commit: `{r['preregistration']['docs/monitoring_preregistration.md']['commit']}` (committed before this run). "
         "Part B is SIMULATED. Part A on the five development vintages is in-sample (the model was fitted on them).", "",
         "## Part A: real drift and level per vintage", "",
         "| Vintage | Sample | Loans | Defaults | Predicted | Observed | Obs / pred | Level flag | Gini | Score PSI | Max CSI (input) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for y, x in a.items():
        L.append(f"| {y} | {'in' if x['in_sample'] else 'out'} | {x['n']:,} | {x['defaults']:,} | {x['level']['predicted']:.2%} | "
                 f"{x['level']['observed']:.2%} | {x['level']['ratio']:.2f} | {x['level_flag']} | {x['gini']:.3f} | "
                 f"{x['score_psi']:.3f} ({x['score_flag']}) | {max(x['csi'].values()):.3f} ({x['max_csi_feature']}) |")
    L += ["", "## Part B: simulated shifts (fire drills)", "",
          f"Batch {b['batch_size']:,} loans against a reference of {b['reference_size']:,}. "
          f"R-M1 (control clean): **{b['R_M1_control_clean']}**. R-M2 (at least 6 of 7 expected alerts): **{b['R_M2_enough_alerts']}** "
          f"(caught {b['caught']}, missed {b['missed']}).", "",
          "| Drill | Shift | Score PSI | Max CSI (input) | Level ratio | Alert monitors |", "|---|---|---|---|---|---|"]
    for sid, x in b["drills"].items():
        L.append(f"| {sid} | {x['spec']} | {x['score_psi']:.3f} | {x['max_csi']:.3f} ({x['max_csi_feature']}) | "
                 f"{x['level_ratio']:.2f} | {', '.join(x['alert_monitors']) or 'none'} |")
    L += ["", "## Part C: can history alone repair the level?", "",
          "Level error = |ln(predicted / observed)|; lower is better. delta = constant added on the log-odds scale.", "",
          "| Target | Known vintages | Observed | Error A static | Error B last | Error C pooled | delta B | delta C |", "|---|---|---|---|---|---|---|---|"]
    for t, x in c.items():
        L.append(f"| {t} | {x['known_vintages']} | {x['observed']:.2%} | {x['A_static']['level_error']:.3f} | {x['B_last']['level_error']:.3f} | "
                 f"{x['C_pooled']['level_error']:.3f} | {x['B_last']['delta']:+.2f} | {x['C_pooled']['delta']:+.2f} |")
    L += ["", f"Mean error: static {v['mean_error_static']:.3f}, B {v['B_last']['mean_error']:.3f}, C {v['C_pooled']['mean_error']:.3f}.",
          f"R-C2 (Gini unchanged): **{v['R_C2_gini_unchanged']}**.", ""]
    for arm in ("B_last", "C_pooled"):
        x = v[arm]
        L.append(f"- **{arm}**: mean improvement {x['mean_improvement']:+.1%} (need 20%: {x['mean_improvement_ok']}), improved "
                 f"{x['targets_improved']} of {len(v['targets'])} targets (need 5: {x['targets_improved_ok']}; {x['improved_targets']}), "
                 f"worst worsening {x['worst_worsening']:+.3f} (limit 0.30: {x['worst_worsening_ok']}) -> "
                 f"**{'recommended' if x['recommended'] else 'not recommended'}**.")
    L += ["", "## Pre-registered predictions: hit or miss", "", "| Id | Prediction | Result |", "|---|---|---|"]
    L += [f"| {p['id']} | {p['prediction']} | {'HIT' if p['hit'] else 'MISS'} |" for p in r["predictions"]]
    hits = sum(p["hit"] for p in r["predictions"])
    L += ["", f"{hits} of {len(r['predictions'])} predictions hit.", ""]
    return "\n".join(L)


def chart(a: dict, c: dict, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    years = list(a)
    ratios = [a[y]["level"]["ratio"] for y in years]
    ax[0].axhspan(0.80, 1.25, color="#2a9d8f", alpha=0.15, label="ok (0.80-1.25)")
    ax[0].axhspan(0.67, 0.80, color="#e9c46a", alpha=0.25)
    ax[0].axhspan(1.25, 1.50, color="#e9c46a", alpha=0.25, label="warn")
    colors = ["#264653" if a[y]["in_sample"] else "#e76f51" for y in years]
    ax[0].scatter([str(y) for y in years], ratios, c=colors, s=70, zorder=3)
    ax[0].axhline(1, color="grey", lw=0.8)
    ax[0].set_ylabel("observed / predicted default rate")
    ax[0].set_title("Level per vintage (dark: in-sample, orange: out-of-sample)")
    ax[0].legend(loc="upper right", fontsize=8)
    ts = list(c)
    x = np.arange(len(ts))
    for i, (arm, col) in enumerate((("A_static", "#999999"), ("B_last", "#e9c46a"), ("C_pooled", "#2a9d8f"))):
        ax[1].bar(x + (i - 1) * 0.27, [c[t][arm]["level_error"] for t in ts], 0.27, label=arm, color=col)
    ax[1].set_xticks(x, [str(t) for t in ts])
    ax[1].set_ylabel("level error |ln(predicted / observed)|")
    ax[1].set_title("Recalibration from history (lower is better)")
    ax[1].legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main(verbose: bool = True) -> dict:
    state = prereg_state()
    bad = [f for f, s in state.items() if s["commit"] is None or not s["clean"]]
    if bad:
        raise SystemExit(f"refusing to run: commit these files first (pre-registration discipline): {bad}")
    cfg = load_config()
    model = load_model(MODEL)
    frame = build_frame(model, cfg)
    a, scored = part_a(model, frame, cfg)

    dev = scored[scored["in_sample"]]
    b = run_simulation(model, dev[list(model["feature_order"])].reset_index(drop=True), dev["y"].to_numpy(), cfg)

    frames = {int(v): g[["pd", "y"]] for v, g in scored.groupby("vintage")}
    c_rows = recalibration.run(frames, cfg)
    c_verdict = recalibration.verdict(c_rows, cfg)

    result = {
        "model_id": model["model_id"], "preregistration": state,
        "config_sha256": hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
        "note": "Part B is SIMULATED. Part A on development vintages is in-sample.",
        "part_a": {str(k): v for k, v in a.items()}, "part_b": b,
        "part_c": {str(k): v for k, v in c_rows.items()}, "part_c_verdict": c_verdict,
    }
    result["predictions"] = predictions(a, b, c_rows, c_verdict)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "monitoring_report.json").write_text(json.dumps(result, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o)), encoding="utf-8")
    md_input = {**result, "part_a": a, "part_c": c_rows}
    (RESULTS / "monitoring_report.md").write_text(to_markdown(md_input), encoding="utf-8")
    chart(a, c_rows, ROOT / "docs" / "monitoring.png")
    if verbose:
        print(to_markdown(md_input))
    return result


if __name__ == "__main__":
    main()
