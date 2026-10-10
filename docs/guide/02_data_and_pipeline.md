# 2. The data and the pipeline (Phases 0 and 1)

## 2.1 Phase 0: preparing the ground

What we did before any modelling, and why:

1. **A new repository** (`credit-risk-platform`) copied from your first project, with the old one left untouched.
   Reason: your first project (v1) stays as it was; v2 is the serious upgrade.
2. **An audit of v1.** We re-ran it and found real weaknesses: the numbers could not be reproduced (no fixed random seed,
   no pinned library versions), the "probability of default" shown was not a real probability (it came from a model
   trained on artificially balanced data), and there were no tests.
3. **Quick wins:** pinned library versions, fixed seeds, `.gitignore`, `ruff` (style checker), `pytest` (tests), removed
   generated files from git. Result: the same number every time (AUC 0.8020).
4. **A first experiment on the small German Credit data:** it showed that making defaults artificially frequent (SMOTE or
   class weights) pushes predicted risk up. (We later reproduced this on 100,000 real loans: see file 5.)
5. **The dataset decision.** We first wanted Home Credit, then read its rules: the data may be used *only for the
   competition* (which ended in 2018). **Rejected.** Freddie Mac allows research use and publishing results, but
   forbids passing the raw data on, so **the data never goes into git or into the public demo**.
6. **The cloud.** Google Cloud refused to create a billing account (error `OR_BACR2_59`); AWS worked. We secured the AWS
   account (MFA on the master login, a separate everyday user, budget alerts). Nothing is deployed yet.

## 2.2 The data: two tables for one loan

```
 ID CARD (origination)  -- 1 row per loan, written once
   loan_seq  score  amount  ltv  dti  rate  state  purpose ...
 F16Q10000006  686  125,000  65   41  3.75   CA      C
        |
        |  loan_seq = the link
        |
 DIARY (performance)    -- 1 row per month
   F16Q10000006  201603  125,000  on time   age 0
   F16Q10000006  201604  124,000  on time   age 1
   ...                                                  (28 rows for this loan)
   F16Q10000006  201806        0  on time   age 27  ended: code 01 = paid off
```

We used **five yearly samples** of 50,000 loans each (2008, 2012, 2016, 2019, 2022): 250,000 loans and 14 million
diary lines.

## 2.3 The layers (we followed the "medallion" idea under our own names)

| Layer | Folder / code | What it contains | Rule |
|---|---|---|---|
| **raw** (bronze) | `credit/freddie/load.py` | The files as received, only column names added, everything as text | Never fix anything here |
| **staging** (silver) | `credit/freddie/staging.py` | Typed (numbers, dates), `999`/`9999` become "missing", flags, the label `default_24m` | Checks stop the run if data is wrong |
| **features** (gold) | `credit/freddie/features.py` | One row per kept loan: only day-one features, the label, and a split name | Exclusions are counted |

Each layer reads only the one before it. If something looks wrong, you walk back one step at a time.

**Tools used and why**
- **Parquet**: a compact table file stored by columns. 1.6 GB of text became 146 MB, and it loads fast.
- **DuckDB**: a database that runs inside your computer and lets you write SQL on files. 14 million rows in seconds, free.
- **pytest**: runs our 72 tests. **ruff**: checks code style and common mistakes.
- **git + GitHub**: the history of everything (code and decisions), without the data.

## 2.4 The checks (the "guards")

A guard is a test **on the data itself**. If one fails, the run stops with a clear message. Examples: every loan appears
once; every diary line belongs to a known loan; interest rates between 0% and 20%; labels are only 0 or 1; **no column of
the ID card looks like the answer** (leakage test). We also wrote tests that deliberately break the data to prove the
guards really stop it. (A guard that has never failed in a test proves nothing.)

## 2.5 Leakage (the most important idea in this file)

**Leakage** = the model gets, by accident, information that would not exist at the moment of the decision.
Analogy: a student gets the answer sheet before the exam and scores 100%.

Examples in this project:
- Using the **diary** (payments) as input to predict default: forbidden. Only the ID card is used.
- Using the **vintage year** as a feature: it would learn "2008 = risky", useless for the future. Forbidden.
- Choosing settings by looking at the **test** data: that is "data snooping" (see file 3).

## 2.6 The exclusions (what we removed, and the counts)

| Vintage | Sample | Relief refi | Seasoned/modified | Too young | Kept |
|---|---|---|---|---|---|
| 2008 | 49,999 | 0 | 287 | 0 | 49,712 |
| 2012 | 50,000 | **17,399** | 55 | 0 | 32,546 |
| 2016 | 50,000 | 2,525 | 103 | 0 | 47,372 |
| 2019 | 50,000 | 30 | 89 | 0 | 49,881 |
| 2022 | 50,000 | 0 | 22 | 71 | 49,907 |

"Too young" = fewer than 24 months of history, so we cannot know the label yet.

## 2.7 The splits (who studies, who takes the exam)

```
 Loans from 2008, 2012, 2016        ----> TRAIN 60%        the model learns here
 (random shuffle by a fixed code)         CALIBRATION 10%  a small correction of the percentages is learned here
                                          VALIDATION 15%   the "mock exam": we compare models and choose settings
                                          TEST IN TIME 15% real exam 1 (same era)
 Loans from 2019                    ----> TEST 2019        real exam 2 (the future)
 Loans from 2022                    ----> TEST 2022        real exam 3 (the future)
```

The shuffle uses a **hash of the loan ID** (a fixed mathematical scramble), so the split is identical every time and
does not change when data is added. The exams stay locked in the code: loading them without an explicit permission
raises an error.

## 2.7b Where things are in the repository

```
credit/freddie/    layout, load, staging, features        (the data part)
credit/models/     data, metrics, scorecard, xgboost, calibration, ablation, final exam, reasons, explain, fairness
credit/economics/  lgd, cutoff, decision report            (the money part)
config/            assumptions.yaml, economics.yaml, reason_codes.yaml   (every assumption, labelled)
results/           small JSON/Markdown files with every number we quote
docs/              decision-log.md, model_card.md, charts, and this guide
tests/             72 tests, all on made-up data (no real data needed)
data/              (git-ignored) the Freddie Mac files and the Parquet layers
```
