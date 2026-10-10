# 6. Money, explanations and fairness

## 6.1 Turning a probability into a decision (the cut-off)

The bank has two choices per loan: **approve** or **refuse**. The money rules (all in `config/economics.yaml`, all
**assumptions** except where stated):

- Approve a loan that is repaid: earn a **margin** (assumed 2% of the loan over 24 months).
- Approve a loan that defaults: lose part of the money (assumed **10%** of the loan; measured values range from 0.4% in
  calm years to 20% in the 2008 crisis).
- Refuse: nothing happens.

For a loan with risk p, approving is worth it when

> **(1 - p) x margin  >  p x loss**   which means   **p  <  margin / (margin + loss)**

Example: margin 2%, loss 10% -> approve if p < 0.02 / 0.12 = **16.7%**. If the loss is only 1%, the line moves to 67%
(approve almost everyone). If the loss is 20% (a crisis), it moves to 9%.

**Our result, honestly:** on validation the best line approved **97.5%** of loans, but the profit gain over "approve
everyone" was tiny (+0.02% of the amounts lent). Why: only about 2% of loans are flagged, and the margin on the other 98%
pays for them; the scorecard is good at finding the riskiest 10% (12.75% default rate vs 2% on average), but refusing them
only pays when losses are large or margins thin. In calm future years the line even lost a little (-0.01%), because the
model over-predicted risk.

**What it means:** for good-quality mortgages the score is more valuable for **pricing** (charge risky borrowers more) and
**provisioning** (how much money to set aside) than for saying no. The interest-rate spread feature is exactly the lender
doing that already.

The **sensitivity table** (`results/economics_report.md`) shows the best line for every combination of margin (0.5-3%)
and loss (1-20%). With margin 0.5% and loss 20%, the best line refuses 28% of loans and gains 0.25%, ten times the base case.
Because margin and loss are assumptions, **the table is the real answer, not one number.**

## 6.2 Expected loss by risk group

Sort loans into 10 equal groups by predicted risk. For each group: predicted loss = sum of (PD x loss x amount) against
the loss that follows the real defaults at the same loss rate. In the middle groups they match (ratio 1.02-1.04); in the
safest groups the model slightly over-predicts (tiny amounts); in the riskiest it slightly under-predicts (0.75-0.88).

## 6.3 Reason codes (why was this loan scored low?)

Covered in file 4. The rules: sentences written by humans in a config file; a reason needs at least 5 points lost; a
feature without an approved sentence raises an **error** (never skipped or improvised); the era-proxy feature
(`super_conforming`) is marked **not reportable**.

## 6.4 Fairness: what we can and cannot say

**Cannot:** Freddie Mac has **no sex, race or age**, so discrimination on protected characteristics **cannot be tested**
here. This is **not** a legal fairness certification.

**Can:** compare the groups that exist: first-time buyers, occupancy, purpose, property type, channel, state. For each:
- **approval rate** at the chosen line, and the **refusal-rate ratio** versus the group refused least. (The famous
  "four-fifths rule" compares approval rates, but when 97-99% of everybody is approved it can never fall below 0.8, so it
  hides differences. The refusal ratio shows them.)
- **predicted / observed** defaults: 1.0 means the model is honest for that group; above 1 means the model
  over-estimates the risk of that group.

**What we found (later years, 2019 + 2022 pooled):** the model over-predicts everyone by about 1.4x, but some groups more:

| Group | Predicted / observed |
|---|---|
| Repeat buyers | 1.35 |
| **First-time buyers** | **1.69** |
| Cash-out refinance | 1.12 |
| **Purchase loans** | **1.72** |
| Retail channel | 1.27 |
| **Broker channel** | **2.04** |
| **Florida** | **2.18** (4.5% of its loans refused; Ohio 0.1%) |

**Why Florida:** the model learned "Florida = risky" from 2008 (the housing bust hit Florida, Arizona, Michigan hard).
That pattern did not repeat, so Florida is penalised unfairly in later years. Geography also tends to stand in for
other characteristics, so the `state` feature is a candidate to **remove** in model v2.

**First-time buyers:** not a model input, yet the errors fall more heavily on them (they are often younger or with less
wealth). Worth watching in monitoring.

## 6.5 What a bank would do about all this

- **Macro overlay / recalibration per period:** adjust the level for the economic climate.
- **Monitor predicted vs observed by period and by group** (Phase 3).
- **Review features for era or geography stand-ins** (model v2).
