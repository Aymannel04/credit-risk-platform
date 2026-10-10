"""Money report for the scorecard: line chosen on validation, reported on the exams.

New, labelled analysis made AFTER the final exam (the exam numbers themselves are untouched and the frozen
exam script refuses to run again). Nothing here changes the model; test results do not choose anything.

Writes results/economics_report.json, results/economics_report.md, docs/economics_report.png.
Usage (from the repo root):  .venv/Scripts/python -m credit.economics.decision_report
"""
import json
from pathlib import Path

import duckdb
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from credit.economics import cutoff as co  # noqa: E402
from credit.models.data import load, xy  # noqa: E402
from credit.models.scorecard import Scorecard  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
DOCS = ROOT / "docs"
RAW = ROOT / "data" / "interim" / "raw"
EXAMS = ("test_in_time", "test_oot_2019", "test_oot_2022")


def real_loss_by_loan() -> dict:
    """Actual loss (data) per loan over its whole life, NULL counted as 0. Gains are kept (negative)."""
    con = duckdb.connect()
    parts = [f"SELECT loan_seq, TRY_CAST(actual_loss AS DOUBLE) AS actual_loss FROM read_parquet('{(RAW / f'perf_{y}.parquet').as_posix()}')"
             for y in (2008, 2012, 2016, 2019, 2022)]
    rows = con.execute("SELECT loan_seq, sum(coalesce(actual_loss, 0)) FROM (" + " UNION ALL ".join(parts) + ") GROUP BY 1").fetchall()
    return dict(rows)


def main() -> dict:
    cfg = co.load_config()
    m0, L0 = cfg["margin_24m"]["base"], cfg["loss_per_flagged_loan"]["base"]
    margins, losses = cfg["margin_24m"]["grid"], cfg["loss_per_flagged_loan"]["grid"]

    train = load("train")
    sc = Scorecard().fit(*xy(train))
    data = {"validation": load("validation").reset_index(drop=True)}
    for e in EXAMS:
        data[e] = load(e, allow_test=True).reset_index(drop=True)
    real_loss = real_loss_by_loan()

    pd_, y_, ead_ = {}, {}, {}
    for k, df in data.items():
        pd_[k], y_[k], ead_[k] = sc.predict_proba(xy(df)[0]), xy(df)[1].to_numpy(), df["orig_upb"].to_numpy(dtype=float)

    # 1. the line, chosen on validation only
    best = co.best_cutoff(pd_["validation"], y_["validation"], ead_["validation"], m0, L0)
    theory = co.theory_cutoff(m0, L0)
    curve = co.profit_curve(pd_["validation"], y_["validation"], ead_["validation"], m0, L0)

    out = {"assumptions": cfg, "scorecard": "WoE scorecard fitted on train (raw PD)",
           "chosen_on_validation": {"best_pd_threshold": best["threshold"], "approval_rate": best["approval_rate"],
                                    "theory_threshold_if_pd_were_honest": theory},
           "reports": {}, "el_by_band": {}, "sensitivity_validation": {}}

    # 2. reported on validation and the exams, for every loss scenario
    for k in ("validation", *EXAMS):
        y, ead, p = y_[k], ead_[k], pd_[k]
        loss_data = np.array([real_loss.get(s, 0.0) for s in data[k]["loan_seq"]])
        block = {"loans": int(len(y)), "defaults": int(y.sum()), "exposure": float(ead.sum()),
                 "realised_loss_from_data_pct_of_exposure": float(loss_data.sum() / ead.sum()),
                 "base_case": co.decision_report(p, y, ead, best["threshold"], m0, L0), "by_loss_scenario": {}}
        for L in losses:
            r = co.decision_report(p, y, ead, best["threshold"], m0, L)
            block["by_loss_scenario"][str(L)] = {
                "profit_pct_of_exposure_with_line": r["profit_with_line"] / r["total_exposure"],
                "profit_pct_of_exposure_approve_all": r["profit_approve_all"] / r["total_exposure"],
                "gain_pct_of_exposure": (r["profit_with_line"] - r["profit_approve_all"]) / r["total_exposure"]}
        out["reports"][k] = block
        out["el_by_band"][k] = co.el_by_band(p, y, ead, L0).round(6).to_dict(orient="records")

    # 3. sensitivity (validation): how the best line moves with margin and loss
    g = co.sensitivity_grid(pd_["validation"], y_["validation"], ead_["validation"], margins, losses)
    out["sensitivity_validation"] = g.round(6).to_dict(orient="records")

    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "economics_report.json").write_text(json.dumps(out, indent=2, default=float), encoding="utf-8")
    write_markdown(out, g)
    plot(curve, best, theory, g)
    return out


def pct(x, d=2):
    return "n/a" if x is None else f"{100 * x:.{d}f}%"


def write_markdown(out: dict, g) -> None:
    c, a = out["chosen_on_validation"], out["assumptions"]
    lines = ["# Money report (scorecard; line chosen on validation; assumptions in config/economics.yaml)", "",
             f"Base case: margin {pct(a['margin_24m']['base'], 1)}, loss per flagged loan {pct(a['loss_per_flagged_loan']['base'], 0)} (ASSUMPTIONS).",
             f"Line chosen on validation: approve if PD <= {c['best_pd_threshold']:.4f} (approval rate {pct(c['approval_rate'])}); "
             f"textbook line if the PD were honest: {c['theory_threshold_if_pd_were_honest']:.4f}.", "",
             "## Base case: what the line does", "",
             "| Group | Approval rate | Default rate approved vs all | Defaults refused | Good loans refused | Profit with line (% of exposure) | Approve all | Loss in the data (% of exposure) |",
             "|---|---|---|---|---|---|---|---|"]
    for k, b in out["reports"].items():
        r = b["base_case"]
        lines.append(f"| {k} | {pct(r['approval_rate'])} | {pct(r['default_rate_approved'])} vs {pct(r['default_rate_all'])} | "
                     f"{pct(r['defaults_refused_share'], 1)} | {pct(r['good_loans_refused_share'], 1)} | "
                     f"{pct(r['profit_with_line'] / r['total_exposure'])} | {pct(r['profit_approve_all'] / r['total_exposure'])} | "
                     f"{pct(b['realised_loss_from_data_pct_of_exposure'])} |")
    lines += ["", "## Gain of the line over 'approve everyone', by loss scenario (% of exposure; margin at base)", "",
              "| Group | " + " | ".join(f"loss {pct(float(L), 0)}" for L in out["reports"]["validation"]["by_loss_scenario"]) + " |",
              "|---|" + "---|" * len(out["reports"]["validation"]["by_loss_scenario"])]
    for k, b in out["reports"].items():
        lines.append(f"| {k} | " + " | ".join(pct(v["gain_pct_of_exposure"], 3) for v in b["by_loss_scenario"].values()) + " |")
    lines += ["", "## Sensitivity on validation: best line by margin and loss", "",
              "| margin | loss | textbook line | best realised line | approval rate | gain vs approve all (% of exposure) |", "|---|---|---|---|---|---|"]
    for r in g.to_dict(orient="records"):
        lines.append(f"| {pct(r['margin'], 1)} | {pct(r['loss'], 0)} | {r['theory_cutoff']:.3f} | {r['best_cutoff']:.4f} | {pct(r['approval_rate'])} | {pct(r['gain_pct_of_exposure'], 3)} |")
    lines += ["", "## Expected loss by risk band (base loss), validation", "",
              "| band | mean PD | default rate | predicted EL | EL at the observed defaults | ratio |", "|---|---|---|---|---|---|"]
    for r in out["el_by_band"]["validation"]:
        ratio = f"{r['el_ratio']:.2f}" if r["el_ratio"] == r["el_ratio"] else "n/a"
        lines.append(f"| {int(r['band'])} | {pct(r['mean_pd'])} | {pct(r['default_rate'])} | {r['predicted_el']:,.0f} | {r['observed_el']:,.0f} | {ratio} |")
    (RESULTS / "economics_report.md").write_text("\n".join(lines), encoding="utf-8")


def plot(curve, best, theory, g) -> None:
    fig, ax = plt.subplots(1, 2, figsize=(12.5, 4.6))
    ax[0].plot(curve["approval_rate"] * 100, curve["profit"] / 1e6, lw=2)
    ax[0].axvline(best["approval_rate"] * 100, color="green", ls="--", label=f"best line ({best['approval_rate']:.1%} approved)")
    ax[0].set_xlabel("share of loans approved (safest first), %")
    ax[0].set_ylabel("profit on validation (millions)")
    ax[0].set_title("Profit curve (base case)")
    ax[0].legend()
    ax[0].grid(alpha=0.3)
    pivot = g.pivot(index="margin", columns="loss", values="approval_rate") * 100
    im = ax[1].imshow(pivot.values, cmap="viridis", aspect="auto", vmin=pivot.values.min(), vmax=100)
    ax[1].set_xticks(range(len(pivot.columns)), [f"{c:.0%}" for c in pivot.columns])
    ax[1].set_yticks(range(len(pivot.index)), [f"{m:.1%}" for m in pivot.index])
    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            ax[1].text(j, i, f"{pivot.values[i, j]:.0f}%", ha="center", va="center", color="white", fontsize=9)
    ax[1].set_xlabel("loss per flagged loan")
    ax[1].set_ylabel("margin")
    ax[1].set_title("Share of loans approved at the best line")
    fig.colorbar(im, ax=ax[1])
    fig.tight_layout()
    DOCS.mkdir(exist_ok=True)
    fig.savefig(DOCS / "economics_report.png", dpi=130)


if __name__ == "__main__":
    main()
    print((RESULTS / "economics_report.md").read_text(encoding="utf-8"))
