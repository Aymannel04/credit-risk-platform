# 9. Model v2: finding our own flaws and fixing them honestly

This chapter is "Act 3" of the story: *I built it, I found where it fails, I fixed it, and I proved the fix on data I had
never seen.* It is also the best interview material in the project, because it shows scientific method.

## 9.1 Why we needed v2

After the first final exam we noticed problems in our own model:
- two features (`super_conforming`, and the raw interest rate earlier) were mostly telling the model **which year it was**;
- `state` made some states (Florida) look unfairly risky in later years;
- `n_borrowers` changed its definition in 2018.

We could not "fix and re-run" the exam: that would be **data snooping**. So we ran a **new experiment** with **new data**.

## 9.2 The method, step by step (and the words you need)

**Step 1: fresh years.** We downloaded four new samples we had never looked at: **2010, 2014, 2018, 2023**.
Their answers (who defaulted) stayed **locked** in the code until the very end.

**Step 2: a feature review using only the old years.** For each feature we asked: *does it help inside one year, or does it
only tell me which year it is?* We compared the feature's usefulness (IV) **inside** each year with the usefulness a
randomly shuffled copy would get by luck (the **noise floor**). Result:
- `credit_score`, `dti`, `ltv`, `cltv`, `rate_spread`, `n_borrowers`: real inside every year.
- `mi_pct`, `purpose`: real, but **hidden** when years are mixed (the old rule had thrown `purpose` away).
- `super_conforming`: **nothing** inside any year (a pure year flag). `channel`: almost nothing (mostly era).
- `state`: **not** an era proxy (it has information inside each year). We still removed it for fairness reasons, because
  removing it cost nothing in ranking.

**Step 3: leave-one-year-out (a rotating exam).** Train on four old years, test on the fifth, five times. Removing the
flawed features cost at most 0.005 Gini (nothing). It also **killed one of my own hypotheses**: I had said the weak ranking in
2019/2022 was because the 2008 crisis dominated the training. But even when 2008's weight changed, the weakness stayed. A
hypothesis that is tested and rejected is progress.

**Step 4: pre-registration.** Before opening any fresh answer, I wrote in a file: the three models to compare, the features,
my **predictions with ranges**, and the **success rules**. I committed it to GitHub. Think of it as a sealed envelope: afterwards
nobody can claim "I always knew".

**Step 5: freeze.** The models, settings, the rules, and fingerprints (hashes) of the data and the pre-registration were
committed. The exam script **refuses to run** unless all that is intact (we tested that it refused before the freeze).

**Step 6: the exam, once.** Three models (the "arms"):
| Arm | What it is | What comparing it tells you |
|---|---|---|
| **v1** | the old model | the baseline |
| **v1b** | old features, retrained on all five old years | v1b vs v1 = effect of **more data** |
| **v2** | fixed features, same data as v1b | v2 vs v1b = effect of **fixing the features** |

## 9.3 The results (fresh years, nobody had looked at them)

| Fresh year | Defaults | Gini v1 | Gini v1b | Gini v2 | Predicted ÷ real (v2) |
|---|---|---|---|---|---|
| 2010 | 151 | 0.598 | 0.616 | **0.628** | 2.03 |
| 2014 | 206 | 0.580 | 0.586 | **0.599** | 2.64 |
| 2018 | 420 | 0.523 | 0.543 | **0.543** | 2.11 |
| 2023 | 662 | 0.570 | 0.585 | **0.595** | 1.41 |

- **v2 minus v1:** about **+0.024 Gini** on average (95% interval +0.013 to +0.035). Small, but real (the interval does not
  contain 0). About +0.014 of it comes from more data, about +0.009 from the better features.
- **Ranking is useful** on all four fresh years (Gini 0.52 to 0.63; right in about 76-81 pairs out of 100). The real future
  (2023) scores 0.57-0.60, which is better than the 2022 vintage in the first exam. So "the future is always worse" is **not** true.
- **The level is wrong everywhere:** the model predicts **1.4 to 2.6 times** the real default rate in every fresh year. The
  real default rates were 0.43%, 0.48%, 0.85% and 1.33%, while the training mix averages about 2%. This is the macro effect again:
  the model cannot see whether the economy is calm. It needs a **macro adjustment or a recalibration per period**, and it must
  be **monitored**. v2 does not fix it.

## 9.4 The verdict, by the rules written before

| Rule | Result |
|---|---|
| R1: v2 not worse than v1 by more than 0.03 Gini | **Yes** (and even better: the interval is above 0) |
| R2: v2 has smaller differences between groups in at least 4 of 6 variables | **Yes, but exactly 4: no margin** |
| **Verdict** | **v2 is adopted as the recommended model** |

## 9.5 What I predicted wrong (this is good, not bad)
- I said "superior" had under 25% chance. It happened.
- I predicted the 2010 level would be 0.5-1.6 times reality. It was about **2** times.
- The fairness result was **fragile**: first-time buyers got slightly worse, and removing `state` did **not** remove the
  geographic pattern, because other features correlate with geography.

## 9.6 A bug found while exporting v2
The points table showed **-38 points** for a category the model had never seen (for example an unusual loan purpose). A new,
unusual applicant would have been punished **just for being unusual**. Fix: a band never seen in training is **neutral**.
Impact on the exam: **1 loan out of 177,081**, so the results stand. I wrote a test and logged it.

## 9.7 What to say in an interview
"After my first exam I found two features that mostly identified the year. I did not touch the exam. I reviewed all features
using only old data, wrote my predictions and success rules in a committed file, froze everything, and tested three models
on four years nobody had looked at. The cleaner model ranks slightly better (+0.024 Gini), but both models over-predict
default rates by 1.4 to 2.6 times because they cannot see the economic cycle, so a macro adjustment and monitoring are the
next step. Some of my predictions were wrong, and I report them."

## 9.8 Words introduced here
**Pre-registration** (writing predictions and rules before the test), **arm** (one version being compared), **noise floor**
(what a random feature scores by chance), **leave-one-year-out** (rotating exam), **through-the-cycle** (average-economy
model), **non-inferior** (not worse than the other by more than an agreed margin).
