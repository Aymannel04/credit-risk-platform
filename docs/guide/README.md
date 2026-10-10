# The learning guide (start here)

This guide explains the whole project **from zero**. You do not need any finance or data-science background.
Every difficult word is explained the first time it appears, and there is a glossary at the end.
Everything here is true to what we really built: the numbers come from the result files, not from memory.

## The project in one minute

A bank gives home loans (mortgages). Some borrowers stop paying: that is called a **default**.
The bank would like to know, **before** giving a loan, *how likely is this borrower to default?*

We took real, public data from a US company called **Freddie Mac** (about 250,000 loans), and built a **scorecard**:
a points system, like a driving test, where a higher score means a safer borrower.
Then we tested it **honestly** (on years it had never seen), measured how much money it could save a bank,
explained its decisions, and checked it for unfair differences between groups.

The most important lesson of the project is not a number. It is this:

> **A model that looks great in testing can fail in the real future. The skill is to test it honestly,
> find out *why* it fails, and say so clearly.**

## How to read this guide

| # | File | What you learn | Read it when |
|---|---|---|---|
| 1 | [01_the_basics.md](01_the_basics.md) | What a mortgage, a default, PD, LGD, expected loss are | First |
| 2 | [02_data_and_pipeline.md](02_data_and_pipeline.md) | The data, the layers, the checks, the splits (Phases 0 and 1) | Second |
| 3 | [03_how_we_measure_models.md](03_how_we_measure_models.md) | **Gini, KS, Brier, calibration**, overfitting, the exam | Third (the most useful) |
| 4 | [04_the_scorecard.md](04_the_scorecard.md) | Bands, WoE, IV, points, and the other two models | Fourth |
| 5 | [05_experiments_story.md](05_experiments_story.md) | What we tried, what happened, what we learned | Fifth |
| 6 | [06_money_explainability_fairness.md](06_money_explainability_fairness.md) | Loss, cut-off, reasons, SHAP, fairness | Sixth |
| 7 | [07_interview_cheatsheet.md](07_interview_cheatsheet.md) | Questions and short answers, numbers to remember | Before any interview |
| 8 | [08_glossary.md](08_glossary.md) | Every term, A to Z | Any time |
| 9 | [09_model_v2.md](09_model_v2.md) | Finding our own flaws, pre-registration, the exam on fresh years | After file 5 |

Deeper, more technical records live next to this guide: `docs/decision-log.md` (every decision with its evidence)
and `docs/model_card.md` (one-page summary of the model and its limits).

## Where the project stands

```
Phase 0  Audit and preparation       DONE
Phase 1  Data platform               ~70%  (data, checks and CI done; pipeline tool and cloud copy still to do)
Phase 2  Modeling                    DONE  (models, exam, money, explanations, fairness, model card, model v2)
Phase 3  Serving and monitoring      to do (API, drift alarms, pipeline, deployment on AWS)
Phase 4  Credit-memo agent           to do
Phase 5  Final README, demo, interview preparation
```

## What comes next (the plan)

1. **Model v2: DONE.** We removed the features that only reflect the era and proved on four years nobody had looked at that
   the cleaner model ranks slightly better (+0.024 Gini). Both models still predict 1.4 to 2.6 times the real default rate:
   a macro adjustment and monitoring are the next step (see file 9).
2. **CI: DONE.** A robot on GitHub runs the style check and all tests on every push (green tick on the repository).
3. **Pipeline, API, monitoring, deployment on AWS.**
4. **The memo agent**, then the final README, a short demo video and the interview-preparation session.
