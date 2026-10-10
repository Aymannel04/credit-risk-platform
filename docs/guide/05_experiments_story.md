# 5. The story: what we tried, what happened, what we learned

Each entry: **what we expected, what happened, what it taught us.** The full evidence is in `docs/decision-log.md`.

---

### Story 1: v1's "probability" was not a probability (German Credit, Phase 0)
- **Expected:** a clean model with a 0.81 AUC.
- **Found:** v1 trained on artificially balanced data (SMOTE) but displayed the output as a probability of default. We
  re-ran it: AUC 0.8020 (not 0.8074), because nothing was fixed (no seeds, no pinned versions).
- **Lesson:** a result you cannot reproduce is not a result. Fix seeds and versions first.

### Story 2: the first dataset was not allowed
- **Expected:** use Home Credit (famous, multi-table).
- **Found:** its rules limit the data to "the competition" (ended 2018). Freddie Mac allows research use but no
  redistribution.
- **Lesson:** read the terms **before** building. Raw data never goes to GitHub.

### Story 3: defining "default" is a decision, not a fact
- **Found:** Freddie Mac has no "default" column. 90+ days late looked natural, but in the 2019 vintage that gave 4.6%
  "defaults", most of them COVID payment pauses (only 1.3% without them).
- **Lesson:** a label is a modelling choice. We chose definition B, wrote it down, and kept the other definitions (A: all
  90+ days late; C: loss events only) as comparisons.

### Story 4: the first model looked too good (the "era mix")
- **Expected:** a decent baseline.
- **Found:** Gini **0.83** on validation, higher than real scorecards usually are. Inside a single year it was lower
  (0.74 and 0.58).
- **Why:** in 2008 loans had **both** high interest rates (6%) and many defaults; in 2012-2016 low rates and few defaults.
  The model was partly **recognising the year** from the interest rate.
- **Fix (later):** replace the raw rate by the **rate spread** (rate minus that quarter's typical rate). Mixed-year Gini
  fell to 0.78 (the free points were gone); the Gini **inside each year barely moved**, proof that the real skill stayed.
- **Lesson:** when a metric looks too good, find out *why* before celebrating.

### Story 5: the complex model did not win
- **Found:** XGBoost and logistic regression tied (validation AUC 0.913 each). The effects here are simple and go in one
  direction (higher score = safer), so complexity finds little extra.
- **Lesson:** use the simplest model that is as good. Complexity must earn its place.

### Story 6: calibration did nothing, because the model was already honest
- **Found:** Platt scaling learned slope 1.00 and offset about 0: "the model was already right". The flexible method
  (isotonic) was worse and even predicted 0.0001% risk for the safest loans while 0.15% really defaulted.
- **Lesson:** a correction must **prove itself on validation**. Flexible methods overfit when there are few defaults
  (our calibration group had only 248).

### Story 7: the popular "fixes" for rare defaults ruin the percentages (the headline result)
Same XGBoost, only the treatment of the 2% imbalance changes (real default rate on validation: 2.04%):

| Training | Average predicted risk | Brier (lower = better) | Ranking (AUC) |
|---|---|---|---|
| **Normal (unweighted)** | **2.03%** | **0.0176** | 0.894 |
| Class weights (defaults count 49x) | 27.3% | 0.1313 | 0.892 |
| SMOTE (artificial defaults, 50/50) | 17.6% | 0.0652 | 0.879 |

- Class weights damage only the **level**; Platt scaling repairs it (offset -3.85, which matches the maths: -ln(76,441/1,566) = -3.89).
- SMOTE damages the **level and the ranking**; calibration cannot give the ranking back.
- **Lesson:** if you need a real probability, do not "balance" the data.

### Story 8: a bug that contradicted the theory
- **Found:** my first SMOTE run predicted 0.7% (too low), but theory says balancing should push it **up**.
- **Cause:** XGBoost reads empty cells of a *sparse* table as **missing values**, not zeros. I trained on a dense table and
  predicted on a sparse one, so the same model gave different answers (16.7%, 0.7%, 13.3%).
- **Fix:** always use one dense format, with a test that guards it. Earlier results were re-run and unchanged.
- **Lesson:** when a result contradicts the theory, suspect your own code first.

### Story 9: the final exam (run once)
Rules: freeze everything in a committed file; the exam script refuses to run otherwise; write predictions in advance.

| Exam | Gini | Predicted vs real default rate |
|---|---|---|
| In time (2008/12/16) | 0.735-0.749 | 1.97% vs 1.93% (ratio 1.02, honest) |
| Future 2019 | 0.446-0.463 | 1.75% vs 1.26% (ratio 1.38) |
| Future 2022 | 0.523-0.529 | 2.08% vs 1.39% (ratio 1.50) |

- **My predictions:** in-time 0.75-0.80 (got 0.74-0.75, edge), future "a bit lower" (it was a **big** drop), ratio 1.4-1.6
  (right), no clear winner (right).
- **Why it drops (hypotheses, not proven):** 76% of the training defaults come from the 2008 crisis, so the model learned
  crisis patterns; defaults in calm years come from life events a loan application cannot see; the model cannot see the
  economy ("through-the-cycle" model).
- **Lesson:** a model is only as good as the world it is tested in. Report the bad numbers too.

### Story 10: we found flaws in our own model after the exam
- `super_conforming` only exists for loans after Oct 2008, so it mostly separates crisis loans from later ones.
- `state` captured the 2008 housing-bust map (Florida, Arizona, Michigan...), so Florida is over-predicted by 2.2x later.
- **What we did:** did **not** touch the exam numbers; hid the faulty feature from the reasons; wrote it in the model card;
  planned **model v2** to be tested on **fresh years**.
- **Lesson:** an IV screen cannot see an era proxy. For every feature ask: *does this exist and mean the same thing in
  every era?*

### Story 11: honesty about our own mistakes
We wrote a wrong count in our notes (4,225 defaults instead of 2,925). We caught it by re-checking and corrected the log,
saying so. A project that records its corrections is more believable than one that pretends to be perfect.
