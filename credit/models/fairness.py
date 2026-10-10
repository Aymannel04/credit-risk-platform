"""Slice report: approval rate and honesty of the predicted risk, group by group.

Freddie Mac provides NO sex, race or age. Only the groups present in the file can be examined (first-time
buyer, state, occupancy, purpose, property type, channel). This is an analysis of differences, not a legal
fairness certification, and it cannot detect discrimination on protected characteristics.

Definitions per group (only groups with at least `min_loans` loans are reported):
  approval rate          share of loans with PD <= the line chosen on validation (results/economics_report.json)
  adverse impact ratio   approval rate of the group / highest approval rate among the groups of the same variable
                         (the "four-fifths rule of thumb" flags values below 0.80)
  predicted / observed   sum of PD over the group / number of real defaults (1.0 = honest). 95% interval from the
                         normal approximation of the default count, shown only with >= 30 defaults.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from credit.models.data import load, xy
from credit.models.scorecard import Scorecard

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"
SLICE_VARIABLES = ["first_time_homebuyer", "occupancy", "purpose", "property_type", "channel", "state"]
TOP_STATES = 10


def slice_table(df: pd.DataFrame, p, y, threshold: float, variable: str, min_loans: int = 500) -> pd.DataFrame:
    d = pd.DataFrame({"group": df[variable].fillna("missing").astype(str).to_numpy(), "p": np.asarray(p), "y": np.asarray(y)})
    if variable == "state":  # keep the largest states, group the rest
        top = d["group"].value_counts().index[:TOP_STATES]
        d["group"] = np.where(d["group"].isin(top), d["group"], "other states")
    d["approved"] = d["p"] <= threshold
    g = d.groupby("group").agg(loans=("y", "size"), defaults=("y", "sum"), expected=("p", "sum"),
                              approval_rate=("approved", "mean"), mean_pd=("p", "mean")).reset_index()
    g["default_rate"] = g["defaults"] / g["loans"]
    g = g[g["loans"] >= min_loans].copy()
    g["adverse_impact_ratio"] = g["approval_rate"] / g["approval_rate"].max()
    # With approval rates of 97-99% the four-fifths ratio can never fall below 0.8 and hides real differences,
    # so also compare REFUSAL rates: group refusal rate / lowest refusal rate among the groups of the variable.
    refusal = 1 - g["approval_rate"]
    # (the lowest rate is floored at 0.1% so that a group with almost no refusals does not make ratios explode)
    g["refusal_ratio_vs_lowest"] = refusal / max(float(refusal.min()), 0.001)
    g["pred_over_obs"] = g["expected"] / g["defaults"].replace(0, np.nan)
    se = 1.96 * np.sqrt(g["defaults"].clip(lower=1))
    enough = g["defaults"] >= 30
    g["ratio_low"] = np.where(enough, g["expected"] / (g["defaults"] + se), np.nan)
    g["ratio_high"] = np.where(enough, g["expected"] / (g["defaults"] - se).clip(lower=0.5), np.nan)
    g["variable"] = variable
    g["flag_approval"] = g["adverse_impact_ratio"] < 0.80
    g["flag_calibration"] = enough & ((g["ratio_low"] > 1) | (g["ratio_high"] < 1))
    return g.drop(columns=["expected"]).sort_values("loans", ascending=False)


def build_report(sc: Scorecard, sets: dict, threshold: float) -> dict:
    out = {}
    for name, df in sets.items():
        X, y = xy(df)
        p = sc.predict_proba(X)
        out[name] = pd.concat([slice_table(df, p, y, threshold, v) for v in SLICE_VARIABLES])
    return out


def to_markdown(tables: dict, threshold: float) -> str:
    lines = [f"# Fairness slices (scorecard; line = approve if PD <= {threshold:.4f})", "",
             "No sex, race or age exists in these data: this is an analysis of differences between the groups that do exist, "
             "NOT a legal fairness certification. Flags: approval = adverse impact ratio < 0.80; calibration = the 95% interval "
             "of predicted/observed excludes 1 (needs >= 30 defaults).", ""]
    for name, t in tables.items():
        lines += [f"## {name}", ""]
        for v, g in t.groupby("variable", sort=False):
            lines += [f"### {v}", "",
                      "| group | loans | defaults | default rate | mean PD | approval | refusal vs lowest | pred/obs (95%) | flags |",
                      "|---|---|---|---|---|---|---|---|---|"]
            for r in g.itertuples():
                if r.ratio_low == r.ratio_low:
                    ci = f"{r.pred_over_obs:.2f} ({r.ratio_low:.2f}-{r.ratio_high:.2f})"
                elif r.pred_over_obs == r.pred_over_obs:
                    ci = f"{r.pred_over_obs:.2f}"
                else:
                    ci = "n/a"
                flags = ", ".join(f for f, on in (("APPROVAL", r.flag_approval), ("CALIBRATION", r.flag_calibration)) if on)
                lines.append(f"| {r.group} | {r.loans:,} | {int(r.defaults)} | {r.default_rate:.2%} | {r.mean_pd:.2%} | "
                             f"{r.approval_rate:.1%} | {r.refusal_ratio_vs_lowest:.1f}x | {ci} | {flags} |")
            lines.append("")
    return "\n".join(lines)


def main() -> dict:
    sc = Scorecard().fit(*xy(load("train")))
    threshold = json.loads((RESULTS / "economics_report.json").read_text(encoding="utf-8"))["chosen_on_validation"]["best_pd_threshold"]
    sets = {
        "validation": load("validation").reset_index(drop=True),
        "later years (2019 + 2022 exams pooled; post-exam diagnostic)": pd.concat(
            [load("test_oot_2019", allow_test=True), load("test_oot_2022", allow_test=True)]).reset_index(drop=True),
    }
    tables = build_report(sc, sets, threshold)
    (RESULTS / "fairness_report.md").write_text(to_markdown(tables, threshold), encoding="utf-8")
    (RESULTS / "fairness_report.json").write_text(
        json.dumps({k: v.round(5).to_dict(orient="records") for k, v in tables.items()}, indent=2, default=float), encoding="utf-8")
    return tables


if __name__ == "__main__":
    t = main()
    cols = ["variable", "group", "loans", "defaults", "approval_rate", "adverse_impact_ratio", "pred_over_obs", "ratio_low", "ratio_high"]
    for name, g in t.items():
        print(f"== {name}: groups flagged for approval: {int(g['flag_approval'].sum())}, for calibration: {int(g['flag_calibration'].sum())}")
        print(g[g["flag_approval"] | g["flag_calibration"]][cols].round(3).to_string(index=False))
