# 3. How we measure a model (Gini, KS, Brier, calibration, overfitting)

A model gives each loan a number. We need two different questions answered:

1. **Ranking:** does it put the risky loans *above* the safe ones? (Gini, AUC, KS)
2. **Honesty of the percentage:** when it says "3%", do about 3 in 100 really default? (calibration, Brier)

A model can be good at 1 and bad at 2. Both matter for a bank.

---

## 3.1 Gini and AUC: the pairs game

**Play this game.** Take **one loan that defaulted** and **one that did not**, at random. Ask the model: "which one is
riskier?" If it points to the one that really defaulted, it wins this round. Repeat for **every possible pair**.

> **AUC = the share of pairs the model gets right.**
> 50% = a coin flip (useless). 100% = perfect.

### A tiny example you can do by hand

Eight loans. The model gives each a **risk score** (higher = riskier). Three really defaulted (**bad**), five did not (**good**).

```
 bad  loans' scores :  0.9   0.6   0.3
 good loans' scores :  0.8   0.5   0.4   0.2   0.1
```
There are 3 x 5 = **15 pairs** (one bad, one good). In each pair the model is right if the bad loan has the higher score.

- bad 0.9 beats all five goods (0.8, 0.5, 0.4, 0.2, 0.1)  -> **5** wins
- bad 0.6 beats 0.5, 0.4, 0.2, 0.1 (but not 0.8)            -> **4** wins
- bad 0.3 beats 0.2 and 0.1 only                            -> **2** wins

Total **11 wins out of 15** -> **AUC = 11/15 = 0.733**.

### Gini = a rescaled AUC

Banks prefer a scale where **0 = useless** and **1 = perfect**. So they use

> **Gini = 2 x AUC - 1**

For the example: 2 x 0.733 - 1 = **0.467**.

| AUC | Gini | Meaning |
|---|---|---|
| 0.50 | 0.00 | coin flip |
| 0.75 | 0.50 | the model is right in 75 of 100 pairs |
| 0.87 | 0.74 | right in 87 of 100 pairs |
| 1.00 | 1.00 | perfect (suspicious in real life) |

### Our real numbers, translated

| Exam | Gini | AUC (= right in how many of 100 pairs?) |
|---|---|---|
| In time (same era) | 0.735 | 86.8 |
| Future: 2019 | 0.446 | 72.3 |
| Future: 2022 | 0.523 | 76.2 |

So in the future years the scorecard still picks the right loan in about **72-76 pairs out of 100**, versus 87 when
the era matches. Useful, but clearly weaker.

**What Gini does NOT tell you:** whether the *percentages* are right. A model can rank perfectly and say "50%" for every
loan that is really 2%.

---

## 3.2 KS: the biggest gap

Sort the loans from riskiest to safest. Walk down the list. At each step, look at two percentages:
the share of **all bad** loans you have already caught, and the share of **all good** loans you have already caught
(wrongly). **KS = the largest gap between the two.**

In the tiny example, cut at "score >= 0.6": you catch 2 of 3 bad (67%) and 1 of 5 good (20%). Gap = 47%. That is the
maximum, so **KS = 0.467**. A bigger KS means a cleaner separation of the two groups. (It happens to equal the Gini in
this small example; in general they differ.)

## 3.3 Calibration: is "3%" really 3%?

Think of a **weather forecaster**. Each day she says "30% chance of rain". Look at the 100 days with that forecast:

- it rained on about 30 of them -> she is **calibrated** (her percentages mean what they say),
- it rained on 55 -> she is too optimistic; on 10 -> too pessimistic.

For a bank this is crucial, because the percentage is **multiplied by money** (expected loss = PD x LGD x EAD).
A wrong 20% gives a wrong amount to set aside, even if the ranking is perfect.

**How we check it:** sort loans by predicted risk, cut into 10 equal groups, and compare the average prediction with the
real default rate in each group. In our validation data, the riskiest group was predicted at **12.4%** and really
defaulted **12.75%**. Almost perfect. This is the **reliability table** (or chart: predicted on one axis, real on the other,
the diagonal is perfect).

### Brier score

The average of (prediction - what happened)^2, where "what happened" is 1 for default and 0 for no default. **Smaller is
better.** Tiny example: predictions 0.9, 0.1, 0.2, 0.8 and outcomes 1, 0, 0, 1 give
(0.1^2 + 0.1^2 + 0.2^2 + 0.2^2) / 4 = **0.025**.

Because defaults are rare, Brier values look tiny (ours are about 0.017). To judge them, compare with the "lazy" forecast
that says the true average for everyone: p x (1 - p) = 0.0189 for 1.93% defaults. In time our models beat it
(0.0173-0.0175); in the future years they were slightly *worse* than the lazy forecast, because the level was too high.

### ECE

The "expected calibration error": the average gap between predicted and real default rate over the 10 groups.
0 would be perfect.

### Platt scaling (the correction)

A small 2-number curve (a slope and an offset) learned on the **calibration** group that converts raw scores into
better percentages. It never changes the ranking. We found it brought **no gain** for our honest models (slope about 1,
offset about 0): they were already calibrated. It only mattered for the distorted models (file 5).

---

## 3.4 Overfitting and the exam

**Overfitting** = a student who memorises last year's exam questions instead of understanding the course. He scores 100%
on the questions he has seen and badly on new ones. A model can do the same with its training data.

Defence: **never judge a model on the data it learned from.**

| Group | Role | Analogy |
|---|---|---|
| Train | the model learns | the textbook |
| Calibration | tune the percentages | a teacher checking "are you as sure as you claim?" |
| Validation | choose between models and settings | the **mock exam** (can be used again and again) |
| Test | the final score | the **real exam** (used once) |

**Why a separate real exam?** You repeat the mock exam many times to decide things, so you slowly adapt to it. The
real exam stays untouched, so its score is honest. Changing the model *after* seeing the real exam to improve its
score is **data snooping**: the exam then measures how much you tuned, not how good you are.

### Why we split by TIME

A bank always predicts the **future**. If we shuffled all years together, the test loans would come from the same
economy as the training loans, which is much easier. Proof from our own results: on a validation set mixing all years the first model scored Gini **0.83** (it was
partly recognising the year from the raw interest rate; after we fixed that it is **0.78**); the real future years
gave **0.45-0.52**.

### The freeze (how we protected the exam)

Before running the final exam we wrote the models, settings and rules into a file, plus **fingerprints (hashes)** of the
data and config, and committed it. The exam script **refuses to run** if the file is missing or if anything changed
afterwards. We also wrote our **predictions in advance**, then reported where we were wrong.

### Error bars (bootstrap)

A score from 375 or 630 defaults has luck in it. The **bootstrap** redraws the exam loans with replacement 1,000 times
and recomputes the score each time; the middle 95% of results is the **95% interval**. If two models' intervals overlap
heavily (or the interval of their *difference* contains 0), we cannot say one is better. That is why we say the three
models are **statistically tied**.

---

## 3.5 Quick summary

| Metric | Question it answers | Good looks like |
|---|---|---|
| Gini / AUC | Does it rank risky above safe? | Gini higher is better |
| KS | How cleanly do bad and good separate? | higher |
| Brier | How close are the percentages to what happened? | lower |
| Calibration table / ECE | Is "3%" really 3%? | predicted = observed |
| 95% interval | How much of this score is luck? | narrow |
