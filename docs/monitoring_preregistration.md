# Monitoring and level recalibration: pre-registration (written and committed BEFORE any monitoring result exists)

Date: 2026-10-11. After this file is committed it is not edited; corrections are appended at the bottom with a date.
Model under test: `models/scorecard_v2.json` (model_id `b3069001d62e`), scored with the file-only scorer. Thresholds and
simulation settings: `config/monitoring.yaml` (assumptions, committed in the same commit).

## What I already know (so nobody can say I hid it)
- The v2 exam (`results/v2_exam.json`) already reported predicted/observed default-rate ratios on the four fresh
  vintages: the model over-predicts by 1.4 to 2.6 times in calm years.
- The exam labels are now open (the exam was run), so monitoring may read the fresh labels. They are NOT used to choose or
  tune anything: all thresholds below are fixed here, from general practice, not from these data.
- I have NOT computed: the per-vintage level ratios of the five development vintages, any PSI, any simulated-shift
  detection result, and any recalibrated result.
- The model was fitted on all rows of the five development vintages, so on those vintages its predictions are in-sample
  (the scorecard is low-capacity, but numbers there are reported as in-sample). The four fresh vintages are out-of-sample.

## Part A: real drift between vintages
- Vintages (sample years): 2008, 2010, 2012, 2014, 2016, 2018, 2019, 2022, 2023. Development rows are assigned to the nearest
  development sample year (a few loans sit in a neighbouring year).
- **Reference** = the five development vintages pooled. **Score PSI** = Population Stability Index of the score in bands of
  20 points. **CSI** (characteristic stability index, the same formula per input) uses the model's own bands (the edges stored
  in the model file, plus the missing band, plus "other" for categories). PSI = sum over bands of (share_now - share_ref) x
  ln(share_now / share_ref), with each share floored at 0.0001.
- Levels: warn at PSI >= 0.10, alert at PSI >= 0.25 (general practice, not fitted to these data).
- Per vintage also: Gini, mean predicted PD, observed default rate, ratio observed/predicted. Warn if the ratio is outside
  [0.80, 1.25], alert if outside [0.67, 1.50].
- No pass/fail rule for Part A: it is a description. Predictions: (A1) the calm vintages 2014 and 2018 raise a level
  ALERT (ratio below 0.67); (A2) the largest score PSI among the nine vintages is in 2008, 2010 or 2023 (the three
  most unusual economic settings); (A3) Gini stays between 0.40 and 0.70 on every vintage.

## Part B: simulated shifts (fire drills for the monitors; labelled SIMULATED everywhere)
Batch = 10,000 loans drawn at random (seed 20261012) from the development pool; reference = the rest of the pool. One
control and nine shifts, each applied to the batch only:

| Id | Shift | Should be detected at ALERT? |
|---|---|---|
| C0 | none (control) | must raise NO warn and NO alert |
| S1 | credit_score - 30 (floor 300) | yes |
| S2 | credit_score - 10 | subtle: either outcome accepted, reported |
| S3 | dti + 10 (cap 65) | yes |
| S4 | credit_score missing for 10% of loans | yes |
| S5 | purpose = "X" (never seen) for 20% of loans | yes |
| S6 | ltv + 10 and cltv + 10 | yes |
| S7 | rate_spread + 0.5 | yes |
| S8 | observed defaults x 1.25 (random 0 to 1 flips) | subtle: either outcome accepted, reported |
| S9 | observed defaults x 2.0 | yes |

- **R-M1:** the control raises no warn and no alert on any monitor (score PSI, every CSI, level ratio).
- **R-M2:** at least 6 of the 7 "yes" shifts raise an alert (shifts S1 to S7 are caught by PSI or CSI, S9 by the level ratio).
- If R-M1 or R-M2 fails, that is reported as a weakness of the monitors. Thresholds are NOT adjusted after seeing
  these results; a change would be a new, dated decision tested on new random batches.
- Predictions: C0 clean; S1, S3, S4, S5, S9 alert; S2 warn at most; S6, S7 uncertain.

## Part C: can history alone repair the level? (recalibration experiment)
Hypothesis: shifting the model's level using only outcomes that were already known when a vintage started reduces the
level error.
- **Known when vintage V starts:** vintages Y with Y <= V - 3 (24 months of history, plus margin so that all loans of Y
  have finished their window). Targets are the vintages with at least one known vintage: **2012, 2014, 2016, 2018, 2019,
  2022, 2023** (7 targets; 2010 has none).
- **Shift:** a constant added on the log-odds scale, found by bisection so that the mean predicted PD of the reference
  loans equals their observed default rate. It keeps the ranking, so Gini cannot change.
- **Arms:** A static (no shift); B last (reference = the most recent known vintage); C pooled (reference = all known
  vintages, loans pooled).
- **Level error** of a target: e = |ln(mean predicted PD / observed default rate)|.
- **R-C1:** an arm is "recommended" only if (1) the mean e over the 7 targets falls by at least 20% relative to A,
  (2) e is lower than A on at least 5 of the 7 targets, and (3) no single target gets worse by more than 0.30 in e.
  Otherwise the arm is "not recommended".
- **R-C2:** for every arm the Gini is identical to A's (to 1e-12). If not, it is a bug.
- Predictions (about 70% confidence): arm B fails R-C1 (a crisis-year shift pushes later calm years the wrong way);
  arm C helps the later targets (2018, 2019, 2022, 2023) but hurts 2012 and 2014 because the pool is then dominated by
  2008; arm C may pass on the mean but is expected to fail R-C1 (3). If no arm passes, the conclusion is: history alone
  cannot repair the level, an outside macro signal (unemployment, house prices) would be needed, and this stays a
  documented limit.
- Even a pass is "recommended, not proven": all nine vintages are used up as targets, so there is no untouched holdout.

## What is delivered
`credit/monitoring/` (psi, drift, simulate, recalibration, report), `config/monitoring.yaml`, tests on made-up data,
`results/monitoring_report.json` and `.md` plus charts, a Dagster asset `monitoring_report`, and a decision-log entry
that states each prediction as hit or missed.
