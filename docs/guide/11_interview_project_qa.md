# 11. Interview question bank for this project

How to use it: read a question, **answer out loud first**, then read the model answer. Every number is from a file in this repository. A number in brackets that says it is not measured yet means: do not quote it. An honest "I haven't done that yet, here is how I would" beats a bluff.

## A. The project

**1. Describe the project in two minutes.**
See the 2-minute pitch in `docs/cv_and_pitch.md`. Order: problem, build, honesty (frozen model, pre-registered rules, a flaw found), cloud, limits.

**2. Why this project? Why not a Kaggle model?**
Kaggle gives a clean table and one score. Real credit risk has a time axis, a delayed label (you wait 24 months to know), leakage traps and a model that must be explained. I wanted to show the whole chain and, above all, honest validation.

**3. What is the hardest thing you solved?**
Not the model: the validation discipline. Freezing the model, committing the rules before looking, locking the labels of the exam years in code (`load_fresh` refuses to return them without a flag), and publishing the misses.

**4. What was your biggest mistake?** (pick one; they are all true)
- A first SMOTE run showed 0.7% predicted risk when the real rate was 2%. The cause: XGBoost treats empty sparse cells as "missing", and I trained on dense data but predicted on sparse data. Fix: force dense output, plus a guard test.
- An unseen category got a WoE of about −38 points, punishing an applicant only for being unusual. Fix: an empty band is neutral (WoE 0), with a test.
- The IV threshold of 0.02 let pure-noise columns in (noise reached 0.03 to 0.04). I measured it and raised the threshold to 0.05.

## B. Data engineering

**5. Why raw / staging / features?** (medallion pattern)
Each layer has one job and reads only the previous one. Raw is "as received" (everything text), staging types and labels and runs data guards, features applies exclusions and splits. When something is wrong I know which layer to blame, and I can rebuild one layer.

**6. How did you define the target?**
`default_24m` = within 24 months of the first month, the loan is 90+ days delinquent (or REO) while **no borrower assistance plan is active**, or it ends in a credit-event zero-balance code (02, 03, 09, 15). Loans that are not observable for 24 months are excluded because their label is unknown. I compared three definitions and logged why I chose this one.

**7. What is data leakage? How did you prevent it?**
Information in the features that would not exist at decision time. Features come only from the origination file; a staging check fails if a label-like column appears; splits are hash-based and out-of-time; the four exam vintages are locked in code; I removed the raw interest rate (it mostly says "which year") in favour of the **rate spread** versus the same quarter and term.

**8. Why hash-based splits?**
Splitting by a hash of the loan id is reproducible and stable: adding data never reshuffles old loans between train and test. Random splits with a seed change when the data changes.

**9. Why DuckDB and Parquet?**
The data (450,000 loans and 24.7 million monthly performance rows, about 250 MB of raw Parquet) fits one machine: DuckDB queries Parquet in seconds, with SQL. Athena would be a choice for show at this size; I'd say so honestly.

**10. Dagster or Airflow?**
Airflow is task-centric ("run X then Y"); Dagster is asset-centric ("this table exists, built from that one"), which fits data products with checks and lineage. I used Dagster because the data products are the point. In a company already running Airflow I would use Airflow.

**11. How do you know the pipeline is reproducible?**
I fingerprinted the feature tables (row count plus a hash of every row) and the model id, rebuilt everything from the raw zips (5 minutes), and got identical fingerprints. A second run with nothing changed reuses every step.

**12. How does the skip rule work and why is it safe?**
A step re-runs if an output is missing or any input (data or the code that defines the step) is newer than the oldest output. It can only err towards an extra rebuild, never towards a stale result.

**13. What does "blocking check" mean?**
A check attached to a step; if it fails, the steps after it do not run, so nothing is built on bad data. The checks read the files on disk, so they also protect a reused result.

## C. ML / data science

**14. Why a scorecard and not just XGBoost?**
On the exam the two were statistically tied (the paired-bootstrap differences include 0), so I chose the model I can explain: points per band, reason codes in fixed sentences, a 7 KB model file that anyone can audit, a scorer that needs only the standard library.

**15. Explain WoE and IV.**
For a band of a variable, WoE = ln(share of good loans / share of bad loans): positive means safer than average. IV sums how well a variable separates good from bad over its bands. Bands come from a decision tree (at least 5% of loans each, at most 6 bands). Points: 600 points = 50:1 odds, +20 points doubles the odds (a convention, kept as an assumption in `config/assumptions.yaml`).

**16. What is Gini? What did you get?**
Gini = 2·AUC − 1: how well the model ranks risky above safe. On four unseen vintages: 0.628, 0.599, 0.543, 0.595 for the recommended v2 (95% bootstrap intervals in `results/v2_exam.md`). KS and Brier are reported too.

**17. Why not accuracy?**
Defaults are 1 to 2% of loans: predicting "nobody defaults" is 98% accurate and useless. Ranking (Gini/KS) and probability quality (Brier, calibration) are the right questions.

**18. Imbalance: SMOTE or class weights?**
Neither for the PD baseline. Both change the class balance the model learns from, so the probabilities are no longer probabilities (the German Credit experiment showed the predicted PD pushed above the true rate). I kept an unweighted model, ran the others as ablations, and calibrated every variant on a separate calibration split.

**19. What is calibration and how did you check it?**
Calibration means "when the model says 2%, about 2% default". I compared mean predicted PD with the observed rate (the predicted/observed ratio with a bootstrap interval), Brier score and reliability curves.

**20. What is "pre-registration" and why do it?**
Writing the hypotheses and success rules in a committed file before seeing the result. Afterwards nobody, including me, can move the goalposts. The exam scripts even refuse to run unless the freeze is committed and the fingerprints match. In the monitoring study 11 of 13 predictions hit and I published the 2 misses.

**21. Why do you say the model "over-predicts in calm years"? What is the cause?**
Out-of-sample, predicted/observed default rates were 2.03, 2.64, 2.11 and 1.41 for 2010, 2014, 2018, 2023. The model is through-the-cycle: it learned from a mix that contains 2008, so its average level is crisis-flavoured. The ranking is fine; only the level is off, and the level is one number.

**22. Why not delete 2008?** (a favourite trap)
I tested it. Calm years get much closer to reality, but the crisis is then predicted about 4 times too low (1.11% vs 4.46%). The plain average looks better because 8 of 9 years are calm, and that is exactly the trap: being wrong in a crisis costs far more. The right choice depends on the purpose (calm-weather pricing vs surviving a downturn).

**23. Could you fix the level properly?**
Not from history alone: re-centring on the last known year cut the average error by 31% but made turning points worse (+0.65), so my pre-written rule rejected it. The principled tools: a Vasicek single-factor "climate" dial (Basel uses rho = 0.15 for mortgages), a current-LTV variable using local house prices, or a mixed model with a year effect. With only about 9 distinct economies in the data, fitting macro variables directly would memorise the years.

**24. How did you check fairness?**
No sex, race or age exists in the data, so I could not test protected groups. I analysed slices that do exist (first-time buyer, occupancy, purpose, state...). The four-fifths rule was uninformative with 97 to 99% approval, so I added a refusal-rate ratio. It is an analysis, not a compliance claim, and it says so.

**25. How do you explain a decision to a customer?**
Reason codes: the features where the loan loses the most points versus the best band, mapped to fixed, human-written sentences (not generated text). One feature that dominated every explanation (`super_conforming`) was an era proxy, so it is marked "not reportable".

## D. Cloud, MLOps and security

**26. Why a container on Lambda?**
It scales to zero and costs nothing when idle, and a container is the same artifact on my laptop, in CI and in AWS. A 51 MB image with 14 small libraries keeps cold starts short. Alternatives (ECS, App Runner) keep an instance running. Measured on the live function: a warm request is **2.7 ms** of compute (median; p95 3.0 ms), memory used **78 MB of 512 MB**, 71 invocations observed.

**27. What is a cold start?**
When no prepared container is waiting, Lambda prepares one (the Init Duration in the log); later calls reuse it. Measured: **about 1.2 to 1.3 s** over the 2 cold starts I observed (a small sample, so I say "about"), against 2.7 ms for a warm request. I report both, never one blended number.

**28. How is it secured?**
The Function URL uses `AWS_IAM`: every request must be signed (SigV4), so a browser gets 403. The function's role can write its own logs and nothing else (least privilege). Images are tagged with the git commit and immutable, so a tag always means the same code. No access keys exist anywhere.

**29. Why immutable tags and digests?**
A tag is a human label; a digest is a fingerprint of the content. If tags could be overwritten, "v5" today and tomorrow could differ, and rollbacks and audits would be guesswork. The digest stored in AWS equals the one I tested locally.

**30. What does your CI do? Why test the container?**
Lint, 307 tests, then it builds the image, compares its exact file list to an expected list (no data, no tests inside) and smoke-tests it. The Python tests run in a full environment; the image has 14 libraries, so only a test of the image can catch a missing file or library.

**31. How do you monitor drift?**
PSI per variable band (CSI) and on the score, plus the observed/predicted level ratio. PSI = sum over bands of (share now − share before) · ln(share now / share before); under 0.10 stable, 0.25 or more a big change.

**32. How do you know your alarms work?**
I damaged batches on purpose (simulated, labelled so): 7 of 7 expected alerts fired and the clean control stayed quiet. Findings: the score PSI alone caught none of them; per-variable CSI did; two subtle shifts (−10 credit-score points, defaults ×1.25) were invisible, and I reported that instead of tuning it away.

**33. A PSI alert fired. Is the model broken?**
Not necessarily. In 2012 the score PSI was 0.454 because of the refinance wave (the mix of loans changed), yet the Gini was still 0.642. Drift says "look"; the level ratio and Gini say whether the model fails.

**38. Your laptop sees 0.68 s but Lambda reports 3 ms. Which is the latency?**
Both are true and they measure different things. The 3 ms is the function's own compute, read from Lambda's logs. The 0.68 s median (p95 1.5 s) is what my laptop sees: the internet trip to Stockholm, a fresh TLS handshake on every call (my script opens a new connection each time) and request signing. For a user the second number matters; for sizing and cost the first one does. I label which one I quote.

## E. Honest "weak spot" questions

**34. Is it production-ready?**
No, and the README says so. Missing: an automatic rollback (deployment is automatic, but if the live check fails the previous image is put back by hand), alerting, a public endpoint, a scheduler, partitions, model governance, real-time features.

**35. What would you do with one more month?**
(1) An automatic rollback when the live check fails, and a deploy that skips documentation-only pushes. (2) The lake read by the monitoring, not only tested for parity. (3) The Vasicek climate dial or a house-price variable for the level. (4) A read-only memo agent whose numbers are all checked by a validator.

**36. What did you not do that you would normally do?**
Hyper-parameter tuning (the question was validation, not squeezing a score), a macro model for the level, a public demo, Evidently.

**37. Tell me about a time a test saved you.**
Sending the JSON value `Infinity` to the API made FastAPI's own error reply crash (it echoed the bad value back), which would have been a 500. A test found it; the handler now reports field and problem without echoing the value. Also: a PowerShell quirk would have crashed my first AWS script on its expected first run; I tested the helper against a stand-in program before running anything.

## Drill (do this out loud)
1. Give the 30-second pitch without notes.
2. Explain "Why not delete 2008?" in 40 seconds.
3. Explain least privilege using your Lambda role.
4. Explain PSI to a non-technical person using the 50/50 → 90/10 example (PSI ≈ 0.88).
5. Say, calmly, what the project does **not** do.


**39. How does GitHub deploy to AWS without a stored password?**
OIDC. Each run gets a short-lived signed ID card from GitHub (who I am: this repository, this branch, this audience). AWS has a trust entry for GitHub's signer and a role whose rule says: accept only a card whose subject is exactly my repository and my main branch. If the card matches, AWS hands out a temporary key (about an hour). Nothing permanent exists in GitHub. The role can only push to one ECR repository and update one Lambda function, and I asked AWS's policy simulator to prove 3 allowed and 7 forbidden actions.

**40. Your first deploy was refused by AWS. What happened?**
The trust rule used the subject format from the documentation example (`repo:owner/name:ref:...`). GitHub writes the permanent numeric ids of the owner and the repository into the subject of repositories created after 2026-07-15 (`repo:owner@id/name@id:ref:...`), and AWS compares the text exactly, so it said no. I found it by adding a step that runs only on failure and prints the non-secret claims of the card, then changed the rule to the real format. It is also stricter: a deleted and re-created repository name has other ids and cannot take the role. The lesson: write a trust rule from the claim that is actually sent, not from an example.

**41. Why is the image built and tested before AWS is touched?**
So that an AWS key never exists while untested code runs: the job has no AWS access until lint, tests, the image build, the check of the image's exact file list and the container smoke test have passed. After the update, the job checks that the function runs exactly the digest that was pushed, then calls the live locked URL with signed requests.
