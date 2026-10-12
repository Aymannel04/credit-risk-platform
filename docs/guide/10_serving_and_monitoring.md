# 10. From model to service: the model file, the API, the pipeline and the monitors

Phase 3 turns a notebook-style project into something that behaves like a real system. Four pieces, one picture:

> Think of a restaurant. The **model file** is the recipe card. The **API** is the waiter. The **pipeline** is the kitchen
> routine that prepares everything in the right order. The **monitors** are the dashboard that tells you when the food
> is no longer what customers expect.

## 1. The model file (a price list)
The scorecard is not a mystery: it is a table of points. To score a loan, find the band of each fact (credit score,
debt-to-income, ...), take its points, add them up (higher is safer), then a formula turns the total into a probability of
default. We save this table as one small file (`models/scorecard_v2.json`, 7 KB). Anyone can open and read it, and scoring
needs only simple addition: no machine-learning library, no training data. It also carries its own **known limits**.
A *golden loan* (one loan whose score we know, 553.3 points = 9.17%) is a test that fails if the model ever changes by accident.

## 2. The API (the waiter)
An **API** is a program that waits for questions and answers them. Ours (`service/`) has four doors: `/health` (alive?),
`/model-info` (what model, which limits), `/score` (points and probability), `/explain` (plus the main reasons, in fixed
sentences). It is **strict**: an unknown field, a text where a number is expected or a credit score of 900 is refused, so
garbage never reaches the model. It never approves or refuses a loan, stores nothing, and refuses to start if the model file
is damaged. Later (step 3.6) it will run on AWS Lambda inside a container, deployed automatically by GitHub without any stored password.

## 3. The pipeline (the kitchen routine)
`zips -> raw -> staging -> features -> model -> monitoring report`. **Dagster** knows this order, runs it with one command
(`python -m pipeline.run`), skips steps whose results are already up to date, and has **blocking checks**: if a check fails,
the next steps do not run. We proved it is reproducible: a full rebuild from the raw zips gave identical data and the identical model.
The exam years live in a separate branch with no arrow into the model, so they cannot leak.

## 4. The monitors (the dashboard)
Three things can go wrong with a model that is already running:

| Problem | Plain words | How we watch |
|---|---|---|
| Data drift | The loans coming in look different from the training loans | **PSI** (score) and **CSI** (each input) |
| Performance drift | The model ranks borrowers worse | Gini per period |
| Level drift | The model predicts 9% but reality is 4% | Observed / predicted default rate |

**PSI** cuts a variable into bands and compares the share of loans in each band, now versus training. Zero means identical.
Rule of thumb: under 0.10 stable, 0.10 to 0.25 look closer, 0.25 or more a big change.

### What we found (real numbers, from `results/monitoring_report.md`)
- **The level problem is real and the monitor sees it.** Only the 2008 crisis year is under-predicted (observed/predicted 1.80). Every other year is over-predicted (ratio 0.35 to 0.77): the model's level is anchored by 2008.
- **A drift alarm is not a failure alarm.** In 2012 the score PSI was 0.454 (alert) because of the refinance wave, yet the model still ranked well (Gini 0.642).
- **Fire drills.** We damaged batches on purpose (SIMULATED) to test the alarms. All 7 expected alerts fired and the clean control stayed quiet. But the score PSI alone caught none of them: the per-input CSI did. Two subtle drills (credit score -10, defaults x1.25) were NOT detected: every alarm has a sensitivity floor.
- **Can history repair the level?** We wrote the rule before looking. Shifting the level using the last known year cut the error by 31% on average and by a lot in stable years, but made it worse at turning points (2012, 2019), exactly when you need it. Verdict: not an automatic fix. A macro signal would be the next experiment.
- **11 of 13 predictions hit.** The two misses are in the decision log. Being able to say "I predicted X, I was wrong" is the point.

## Why not just delete the 2008 year? (tested, exploratory)
It is the obvious question, so we tested it: refit the model without 2008 and compare. Plain words:
- **Calm years get much closer to reality** (for example 2018: the model was 2.1 times too scared, now 1.3 times too relaxed in the later years).
- **The crisis becomes invisible**: for 2008 the new model predicts 1.11% of loans defaulting, reality was 4.46%, four times more.
- **The plain average looks better without 2008**, because eight of the nine years are calm. That is the trap: an average hides how much more expensive it is to be wrong in a crisis.
- The right choice depends on the purpose: a calm-weather view, or a model that must survive a downturn. We kept the second one and wrote it in the model's limits.
- Fixing the level properly needs the state of the economy (unemployment, house prices). That is not in our data and is a bigger piece of future work, with a trap: with only 9 sample years a model can memorise the eras instead of learning a rule.

## Questions to test yourself
1. Why does a model file with only band edges and points need no machine-learning library?
2. Why is a PSI alert not the same as "the model is broken"? Give the 2012 example.
3. Why did we write the success rule for the recalibration before running it?
4. Why can monitoring only the score PSI be dangerous?
