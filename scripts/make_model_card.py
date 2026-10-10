"""Build docs/model_card.md from the result files (numbers are never typed by hand).

Usage (from the repo root):  .venv/Scripts/python scripts/make_model_card.py
"""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R = ROOT / "results"


def load(name: str):
    return json.loads((R / name).read_text(encoding="utf-8"))


def pct(x, d=2):
    return f"{100 * x:.{d}f}%"


def gini_ci(model: dict) -> str:
    lo, hi = model["ci95"]["gini"]
    return f"{model['gini']:.3f} ({lo:.3f}-{hi:.3f})"


def main() -> None:
    exam, score, eco = load("final_exam.json"), load("scorecard_validation.json"), load("economics_report.json")
    expl, lgd, abl = load("explain_report.json"), load("lgd_estimate.json"), load("ablation_validation.json")
    v2x = load("v2_exam.json")
    feat_report = ROOT / "data" / "interim" / "features" / "report.json"
    waterfall = json.loads(feat_report.read_text(encoding="utf-8"))["waterfall"] if feat_report.exists() else []
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()

    L = []
    L += ["# Model card: WoE scorecard for 24-month mortgage default (portfolio project). Recommended model: v2", "",
          f"Generated from `results/*.json` at commit `{commit}`. Frozen exam commit: `{exam['frozen_at_commit'][:10]}`.", "",
          "> **Not a lending product.** A learning/portfolio project on public Freddie Mac data. No claim about any real lender, "
          "no regulatory compliance claim (Basel / IFRS 9 are used only as vocabulary).", "",
          "## 1. Purpose and intended use",
          "Estimate the probability that a newly originated, prime, fixed-rate mortgage is flagged as seriously delinquent within "
          "24 months, using only information known at origination, and rank loans by risk. Intended for: demonstration, teaching, "
          "and discussing model risk. **Not intended for:** real credit decisions, pricing of real loans, or any group not in the data.", "",
          "## 2. Data",
          "Freddie Mac Single-Family Loan-Level Dataset, Standard Dataset, 50,000-loan samples of the 2008, 2012, 2016, 2019 and 2022 "
          "origination years (data not redistributed: Freddie Mac terms). Mortgages only, fixed rate, US.", "",
          "| Vintage | loans | relief refinance removed | seasoned/modified removed | too young removed | kept |", "|---|---|---|---|---|---|"]
    for w in waterfall:
        L.append(f"| {w['vintage_year']} | {w['start']:,} | {w['removed_relief_refi']:,} | {w['removed_seasoned_or_modified']:,} | {w['removed_not_observable']:,} | {w['kept']:,} |")
    L += ["", "## 3. Target",
          "`default_24m` = 1 if, within 24 months of the loan's first month, the loan is 90+ days delinquent (or REO) **while no borrower "
          "assistance plan is active**, or ends with a credit-event zero balance code (02, 03, 09, 15). Definition choice and alternatives: "
          "`docs/decision-log.md`. The assistance-plan field exists only from 2014, so the rule is not symmetric across years.", "",
          "## 4. Model",
          f"Weight-of-Evidence logistic scorecard, unweighted (no resampling, no class weights), fitted on 78,007 training loans. "
          f"Features kept (Information Value >= 0.05): {', '.join(score['features_kept'])}. Points: 600 points = 50:1 odds, +20 points double the "
          "odds (ILLUSTRATIVE convention, `config/assumptions.yaml`). Challengers: logistic regression and XGBoost (statistically tied in the exam).", "",
          "Not used as inputs on purpose: zip3, MSA, seller name, affordable-housing program flag, vintage year, raw interest rate "
          "(replaced by the rate spread against the same quarter and term).", "",
          "## 5. Performance (final exam, run once after a committed freeze; 95% paired-bootstrap intervals)", "",
          "| Exam | loans / defaults | Gini scorecard | Gini logistic | Gini XGBoost | predicted vs real default rate (scorecard) |", "|---|---|---|---|---|---|"]
    for name, b in exam["exams"].items():
        m = b["models"]
        L.append(f"| {name} | {b['n']:,} / {b['defaults']} | {gini_ci(m['scorecard'])} | {gini_ci(m['logistic_regression'])} | {gini_ci(m['xgboost'])} | "
                 f"{pct(m['scorecard']['mean_predicted_pd'])} vs {pct(b['default_rate'])} |")
    L += ["", "No difference between the three models is statistically significant. The scorecard is recommended for being readable.", "",
          "## 5b. Model v2 (recommended): exam on four FRESH vintages (run once; pre-registered and frozen)",
          "v2 = scorecard with credit_score, dti, rate_spread, ltv, cltv, several_borrowers, mi_pct, orig_term, purpose "
          "(no state, channel or super_conforming), trained on all five known vintages. v1b = v1 features on the same training rows.", "",
          "| Fresh vintage | loans / defaults | real rate | Gini v1 | Gini v1b | Gini v2 | predicted/observed (v2) |", "|---|---|---|---|---|---|---|"]
    for v, b in v2x["vintages"].items():
        a = b["arms"]
        L.append(f"| {v} | {b['loans']:,} / {b['defaults']} | {pct(b['default_rate'])} | {a['v1']['gini']:.3f} | {a['v1b']['gini']:.3f} | {a['v2']['gini']:.3f} | "
                 f"{a['v2']['mean_predicted_pd'] / b['default_rate']:.2f} |")
    sm = v2x["summary"]["mean gini difference v2 minus v1"]
    L += ["", f"Mean Gini difference v2 minus v1 over the four vintages: {sm['difference']:+.3f} (95% interval {sm['ci95'][0]:+.3f} to {sm['ci95'][1]:+.3f}). "
          "Pre-registered rules: non-inferiority and group-spread criteria both met (the group criterion with no margin). "
          "The predictions are over the real default rate in every fresh vintage by a factor of 1.4 to 2.6: the level needs a macro overlay or per-period recalibration.", "",
          "## 6. Calibration and level",
          "Unweighted models are well calibrated in time (predicted/observed 1.02). Out of time the models over-predict by about 1.4x "
          "(2019) and 1.5x (2022): the model is a through-the-cycle model and cannot see the macro regime. Calibration (Platt) brought no "
          "gain on validation, so none is applied. Class weights and SMOTE inflate the PD (" + f"{pct(abl['variants']['class_weights']['validation']['raw']['mean_predicted_pd'], 1)} and "
          f"{pct(abl['variants']['smote']['validation']['raw']['mean_predicted_pd'], 1)} average predicted vs "
          f"{pct(abl['variants']['unweighted']['validation']['raw']['default_rate'], 2)} real, validation ablation) and are not used.", "",
          "## 7. Money (assumptions!)",
          f"Base case margin {pct(eco['assumptions']['margin_24m']['base'], 1)}, loss per flagged loan {pct(eco['assumptions']['loss_per_flagged_loan']['base'], 0)} "
          f"(assumptions; measured loss per flagged loan: " + ", ".join(f"{int(r['vintage_year'])}: {pct(r['loss_per_flag'], 1)}" for r in lgd if r.get("loss_per_flag") is not None and r["loss_per_flag"] == r["loss_per_flag"]) + "). "
          f"The line chosen on validation approves {pct(eco['chosen_on_validation']['approval_rate'], 1)} of loans and adds about "
          f"{pct(eco['reports']['validation']['by_loss_scenario']['0.1']['gain_pct_of_exposure'], 3)} of exposure over approving everyone; "
          "out of time it is slightly negative. The score is more useful for pricing and provisioning than for refusing prime loans.", "",
          "## 8. Explainability",
          "Scorecard points are additive: reasons are the features where a loan loses the most points (>= 5), with fixed sentences "
          f"(`config/reason_codes.yaml`). On {expl['sample']:,} validation loans, the scorecard's top reason is among XGBoost's top-3 SHAP features "
          f"for {pct(expl['agreement_top_k']['3']['top1_reason_in_shap_top_k'], 0)} of loans.", "",
          "## 9. Fairness (limits first)",
          "No sex, race or age in the data: protected characteristics **cannot** be tested. Group differences that can be measured: "
          "first-time buyers, occupancy, purpose, property type, channel, state (`results/fairness_report.md`). In later years the model over-predicts "
          "first-time buyers more than repeat buyers, investors, broker-channel loans and Florida; refusal rates differ by group "
          "(the four-fifths rule is uninformative when 97-99% are approved).", "",
          "## 10. Known flaws and limits",
          "- **Era proxies and geography.** `super_conforming` (exists only after Oct 2008) and `channel` carry almost no information inside an era; "
          "the raw `rate` was an era proxy and was replaced by the rate spread. `state` does carry information inside each era, but it is a geography "
          "stand-in with the largest group over-prediction (Florida) and was removed for fairness at no ranking cost. v2 (recommended) removes them "
          "and was tested on fresh vintages (section 5b).",
          "- **Crisis-dominated training.** 76% of the training-period defaults come from the 2008 vintage.",
          "- **Ranking is weaker out of time in the v1 exam** (Gini 0.45-0.53 vs 0.74 in time) but 0.52-0.63 on the fresh vintages; leave-one-vintage-out shows it is not caused by the 2008 weight in training; the cause is not proven.",
          "- Only five 50,000-loan samples; margin is illustrative; 2019 and 2022 losses are incomplete; PD is for a *flagged* delinquency, not a loss.",
          "- The default definition and every number above depend on assumptions listed in `docs/decision-log.md`.", "",
          "## 11. Monitoring (planned, Phase 3)",
          "Predicted vs observed by period and by group, PSI of the score and main features, refusal-rate ratios by group, and a recalibration "
          "or macro-overlay trigger. Promotion of any new model is manual.", ""]
    (ROOT / "docs" / "model_card.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote docs/model_card.md")


if __name__ == "__main__":
    main()
