# 7. Interview cheat-sheet

Short answers in plain words. Practise saying them out loud. Where an answer has a number, the source is in `results/`.

## The 30-second pitch
"I built a credit-risk scorecard on 250,000 real US mortgages from Freddie Mac. I predicted default within 24 months using
only information known when the loan is made, and I tested it honestly on years the model had never seen. In the same era
it ranks well (Gini 0.74); on later years it drops to about 0.5 and over-predicts risk by about 40%. I diagnosed why,
documented the flaws I found in my own model, and I built a v2 without them, with my predictions and success rules written and committed in advance. On four years nobody
had looked at, v2 ranks slightly better (+0.024 Gini), but both models over-predict default rates by 1.4 to 2.6 times because
they cannot see the economic cycle."

## Numbers to remember
| What | Number |
|---|---|
| Loans used / defaults (training) | 250,000 sampled; 78,007 train loans, 1,566 defaults |
| Default rate | about 2% (training mix); 1.26% in 2019, 1.39% in 2022 |
| Gini in time / 2019 / 2022 | 0.735 / 0.446 / 0.523 (scorecard) |
| Predicted / real default rate, later years | 1.38 (2019) and 1.50 (2022) |
| Models | scorecard, logistic, XGBoost: statistically tied |
| Share of training defaults from the 2008 crisis | 76% |
| Class weights / SMOTE: predicted average risk vs real 2.04% | 27.3% / 17.6% |
| Best cut-off (base case) | approve if PD <= 14.7% (97.5% approved) |
| Money gain of that cut-off over "approve all" | about +0.02% of the amount lent |
| Loss per flagged loan (measured) | 20% (2008), 4% (2012), 1% (2016) |
| Tests | 91 passing |
| v2 exam (fresh 2010/2014/2018/2023): Gini v2 | 0.628 / 0.599 / 0.543 / 0.595 |
| v2 minus v1, mean Gini difference (95%) | +0.024 (+0.013 to +0.035) |
| Predicted / real default rate on fresh years | 1.4 to 2.6 (the macro effect) |

## Questions about the data and the target
**Q. How did you define default?** "Within 24 months, 90+ days late while no payment-relief plan is active, or the loan
ends in a loss event. The dataset has no ready-made default column, so this is my decision, documented with the
alternatives. Without the relief rule, the 2019 loans looked as risky as the 2008 crisis because of COVID payment pauses."

**Q. What is leakage and how did you avoid it?** "Using information that would not exist at decision time. I only use the
origination facts as inputs; the monthly diary only builds the label. I have a test that fails if a label-like column
appears in the features. Also the test years are never used to choose anything."

**Q. Why split by time?** "A bank predicts the future. Mixing years makes the test too easy. My mixed-year score looked
like Gini 0.83; the real future years gave 0.45-0.52."

**Q. Why did you drop 35% of the 2012 sample?** "They were relief-refinance (HARP) loans, a special government programme
with different rules and missing data. I excluded them and logged the counts. I state it in the model card."

## Questions about the models
**Q. What is Gini?** "Pick one loan that defaulted and one that did not. Gini says how often the model ranks the
defaulter as riskier, rescaled so 0 is a coin flip and 1 is perfect: Gini = 2 x AUC - 1. A Gini of 0.5 means right in
75 of 100 pairs."

**Q. What is the difference between ranking and calibration?** "Ranking: are risky loans above safe ones. Calibration: is
'3%' really 3 in 100. A bank multiplies the probability by money, so both matter."

**Q. How does a scorecard work?** "Cut each feature into bands, compute for each band the Weight of Evidence (how much
safer or riskier than average), fit a logistic regression on those values, and rescale to points where 600 is 50:1 odds and
+20 points doubles the odds. Total points = sum of band points, so every decision is explainable."

**Q. Why a scorecard if XGBoost is as good?** "In the final exam they were statistically tied, and the scorecard is
readable, auditable and gives exact reason codes."

**Q. Why not SMOTE or class weights?** "They teach the model that defaults are common, so the predicted probabilities are
inflated: 27% and 17.6% average predicted risk against a real 2%. Calibration repairs the level for class weights, but
SMOTE also damages the ranking. If you need a real probability, train on the data as it is."

**Q. What overfitting protections did you use?** "Separate train, calibration, validation and test groups; shallow trees
with early stopping on an inner slice of training data; the test untouched until a committed freeze; error bars by bootstrap."

## Questions about the results
**Q. Why does it drop to Gini 0.5 in the future?** "I first suspected that the 2008 crisis dominated the training
(76% of its defaults). I tested it with a leave-one-year-out experiment and the weakness stayed, so I rejected that
hypothesis. On four fresh years the ranking is 0.52-0.63, so it is not a general law; defaults in calm years are probably
harder to predict from day-one data."

**Q. Why does it over-predict by 40%?** "It is a through-the-cycle model: it cannot see the economic climate. On average
it predicts the pooled-era level, while calm years have fewer defaults. A bank would add a macro overlay or recalibrate
per period; I would monitor predicted versus observed by period and by group."

**Q. Why didn't you improve the model until the exam was better?** "That is data snooping: the exam would then measure my
tuning, not the model. Any improvement is a new, labelled experiment evaluated on new data."

**Q. What would you do next?** "Fix the level, not the ranking: a macro overlay or per-period recalibration (the models over-predict
by 1.4 to 2.6 times), then monitoring of predicted vs observed by period and group, then a new experiment on new data."

## Questions about mistakes and honesty (these impress people)
**Q. Tell me about a bug you found.** "My first SMOTE run predicted 0.7% risk, which contradicted theory (balancing should
push it up). The cause: XGBoost treats empty cells of a sparse table as missing, and I trained on a dense table but
predicted on a sparse one. I made the preprocessing always dense and added a test."

**Q. A flaw you found in your own model?** "After the exam I saw that 'super conforming' is mostly an era flag, and 'state'
captured the 2008 housing-bust map, so Florida was over-predicted 2.2 times. I did not alter the exam. I hid the feature from
the reasons, documented it, and planned a v2 tested on fresh data."

**Q. An assumption you checked?** "The textbook rule keeps features with Information Value above 0.02. I tested it on pure
noise columns: they reached 0.03-0.04, so I raised my threshold to 0.05."

## Questions about money and fairness
**Q. How do you choose the cut-off?** "Approve if the risk is below margin / (margin + loss). Margin and loss are
assumptions, so I show a sensitivity table. The best line was chosen on validation and only reported on the tests."

**Q. Does the scorecard make money?** "Only a little for prime mortgages: refusing risky loans added about 0.02% of the
amounts lent in the base case. The score is more valuable for pricing and for setting aside money."

**Q. Is the model fair?** "I cannot test protected characteristics: the dataset has no sex, race or age. I measured
differences between groups that exist: later years it over-predicts first-time buyers, broker loans and Florida more than
others. This is a report of differences, not a legal certification."

**Q. How do you explain a decision to a customer?** "Reason codes: the features where the loan lost the most points, with
fixed, human-written sentences. No language model writes them."

## Questions about engineering
**Q. How do you keep results reproducible?** "Pinned libraries, fixed seeds, hash-based splits, a frozen manifest with
fingerprints of the data and config, tests on made-up data, and a decision log with the evidence of each choice."

**Q. How do you protect the data?** "The Freddie Mac terms forbid redistribution, so data is git-ignored and the public
repo only has code, config and aggregate results."

**Q. What is still missing?** "A pipeline orchestrator, an API, drift monitoring, deployment on AWS, and a memo agent.
Planned, with the tests and guards written first."
