# 8. Glossary (A to Z)

**API**: a small web service other programs can call (for example: send a loan, get a score).
**AUC**: the share of (defaulter, non-defaulter) pairs where the model gives the defaulter the higher risk. 0.5 = coin flip.
**Band (bin)**: a range of values of a feature (credit score 716 to 742), used by the scorecard.
**Bootstrap**: redrawing the exam loans with replacement many times to see how much a score could vary by luck.
**Brier score**: average squared gap between the predicted probability and what happened (0 or 1). Smaller is better.
**Calibration**: the percentages mean what they say ("3%" is about 3 in 100).
**Censoring**: a loan too young to know yet whether it will default in 24 months; we exclude it.
**CI (continuous integration)**: a robot that runs the tests on every change pushed to GitHub.
**CLTV / LTV**: (combined) loan-to-value: the loan divided by the house value.
**Class weights**: make each default count more during training (distorts probabilities).
**Credit event**: the loan ends with a loss (short sale, charge-off, house taken and sold).
**Credit score (FICO)**: 300-850 number summarising past repayment behaviour. Higher is safer.
**Data snooping**: changing a model after seeing the test result, so the test no longer measures the future.
**Decision tree**: a flowchart of yes/no questions that ends in a prediction.
**Default**: a borrower stops paying seriously. Our definition B is explained in file 1.
**Delinquency**: being late on payments (30, 60, 90 days...).
**DTI**: debt-to-income: share of monthly income that goes to debt payments.
**DuckDB**: a free database that runs inside your computer and queries files with SQL.
**EAD**: exposure at default: the amount of money at risk (we use the original loan amount).
**ECE**: expected calibration error: average gap between predicted and observed default rate.
**Early stopping**: stop adding trees when a held-out slice stops improving (prevents memorising).
**Era proxy**: a feature that mostly tells you *which year it is*, not anything about the borrower.
**Expected loss**: PD x LGD x EAD.
**Feature**: one fact about a loan used as model input (credit score, DTI...).
**Forbearance**: a payment pause granted to a borrower (for example during COVID).
**Foreclosure / REO**: the bank takes the house after non-payment (REO = real estate owned by the bank).
**Freeze**: committing the models, settings and rules (with data fingerprints) before the final exam.
**Gini**: 2 x AUC - 1. 0 = coin flip, 1 = perfect.
**HARP / relief refinance**: a post-2008 government programme for borrowers who owed nearly as much as their house was worth.
**Hash**: a fixed mathematical scramble of a text; used to split data reproducibly.
**IAM / OIDC (AWS)**: who may do what in the cloud; a way for GitHub to get short-lived access without stored passwords.
**Isotonic regression**: a flexible, free-form calibration method (risky with few defaults).
**IV (Information Value)**: how useful a feature is for separating good and bad loans.
**KS**: the largest gap between the share of bad and good loans caught while walking down the risk-sorted list.
**Leakage**: the model gets information that would not exist at decision time.
**LGD**: loss given default: share of the money lost when a loan defaults.
**Logistic regression**: a weighted sum squeezed into a probability between 0 and 100%.
**Margin**: the profit a lender earns on a loan that is repaid (assumed 2% over 24 months).
**Medallion layers**: raw (bronze), staging (silver), features (gold).
**Model card**: a one-page honest summary of a model: use, data, performance, flaws.
**Origination**: the creation of a loan; the origination file is the loan's ID card.
**Overfitting**: memorising the training data instead of learning the rule; good on training, poor on new data.
**Parquet**: a compact, fast table file format stored by columns.
**PD**: probability of default.
**Performance file**: the loan's monthly diary.
**Platt scaling**: a 2-number correction that converts scores into better probabilities without changing the ranking.
**PR-AUC**: area under the precision-recall curve; more informative when positives are rare.
**PSI**: population stability index: how much the distribution of a variable or score shifted between two periods.
**Reason code**: a fixed sentence explaining why a loan lost points.
**Reliability table**: predicted vs observed default rate per risk group.
**SHAP**: splits one prediction into one contribution per feature (a way to explain black-box models).
**SMOTE**: creates artificial defaulters until defaults are 50% of the training data (distorts probabilities).
**Seasoned / modified loan**: an old loan, or one whose terms were changed; its clock does not start at origination.
**Sensitivity table**: how an answer changes when an assumption changes.
**Spread (interest-rate spread)**: a loan's rate minus the typical rate of the same quarter and term.
**Staging**: the cleaned, typed layer of the data.
**Through-the-cycle model**: predicts an average-economy level of risk; cannot see the current economic climate.
**Validation**: the mock exam used to choose models and settings (can be reused, unlike the test).
**Vintage**: the year (or quarter) a group of loans was created.
**WoE (Weight of Evidence)**: ln(share of good loans in a band / share of bad loans in a band).
**XGBoost**: many small decision trees built one after another, each correcting the previous ones.
