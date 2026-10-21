# Demo kit: a 3-minute screen recording and the screenshots

Goal: someone who has never heard of the project understands in two minutes what it does, sees it work, and hears the honest part. You record; this file is the script.

## Before you record (5 minutes)

**Privacy: keep these off the screen.** Your AWS account number (it appears in the `get-caller-identity` output, in ECR addresses and in the SSO login page), the SSO start URL, and any tab showing the AWS console account menu.
1. Close every terminal and browser tab you do not need. Open a **fresh** PowerShell in the project folder and run `cls`.
2. Sign in once, **before** recording, so no login page appears: `aws sso login --profile credit-admin`.
3. Store the function URL in a variable **before** recording, and never print it:
   ```powershell
   $url = aws lambda get-function-url-config --function-name credit-scoring-api --query FunctionUrl --output text --profile credit-admin --region eu-north-1
   ```
4. Increase the terminal font (Ctrl and mouse wheel). Use light or dark mode, but the same everywhere.
5. Recorder: Windows Game Bar (`Win + G`, then record) or OBS. 1080p, microphone on, 3 to 3.5 minutes. One take is fine; small stumbles are human.

## The script (about 3 minutes)

| Time | On screen | Say (in your own words) |
|---|---|---|
| 0:00 to 0:15 | The GitHub README, top of the page: title, results table | "This is a credit-risk platform on real Freddie Mac mortgage data: 450,000 loans. A pipeline turns them into a scorecard that predicts default, and an API serves it on AWS. The idea of the project is to try to catch myself being wrong." |
| 0:15 to 0:35 | The architecture diagram on the README | "Data goes through raw, staging and features, with checks that stop the chain if something is wrong. The model is a points-based scorecard, a 7 KB file. The API runs in a Docker container on AWS Lambda." |
| 0:35 to 1:05 | `docs/monitoring.png` (open it, zoom on the left panel) | "I froze the model and wrote the success rules before testing on four years it had never seen. Gini between 0.54 and 0.63. But look at this: in calm years the model predicts one and a half to two and a half times too many defaults. I found it, measured it, and tested a fix. My own pre-written rule rejected the fix, because it got worse at turning points." |
| 1:05 to 1:35 | Terminal: the smoke test against the live Lambda (command below) | "This is the live API on AWS. The URL is locked: only signed requests work. The test scores a sample loan, asks for reasons, and checks that bad input is refused cleanly. It says SMOKE TEST OK." |
| 1:35 to 1:50 | Browser: paste the URL, show **403 Forbidden**, then the GitHub Actions page with a green run | "An anonymous visitor gets 403. CI runs 505 tests, builds the container and smoke-tests it on every push." |
| 1:50 to 2:35 | Terminal: the memo agent (commands below), then the first lines of `results/agent_eval_seeded.md` | "On top of the API there is a read-only agent that writes a credit memo. Code asks the API and decides approve, refer or decline. The AI only writes the words. An inspector, plain code, checks every number, the decision and the warnings, and sends the memo back if something is wrong. If it still fails, code writes the memo itself. I damaged memos on purpose 150 times, in 10 ways: all 150 were rejected. On 20 loans it had never seen, a small free model wrote 18 good memos on the first try. A call takes about 20 seconds because the free service is shared." |
| 2:35 to 2:55 | The README "Honest limitations" section | "It's a portfolio project, not a lending product. Deployment is automatic but without an automatic rollback. The agent runs from a command line, was measured on one small free model in French on made-up loans, and is not deployed." |

**The commands for the agent shot** (do the key step BEFORE recording, off screen; the key is never printed):

```powershell
$env:NVIDIA_API_KEY = "<your key>"      # before recording only; clear the screen with cls afterwards
```

1. The memo written by the AI and checked by the inspector (about 20 s, speed it up when editing; add `--lang en` for English, but English was not measured):

```powershell
.venv\Scripts\python.exe -m agent.run --loan agent\cases\example_loan.json --writer nvidia --model meta/llama-3.2-11b-vision-instruct --show-attempts
```

Point at the last lines: `status: accepted by the inspector on try 1` (or the complaints, if it needed a rewrite or fell back to the code memo; both are honest and worth explaining).

2. The proof that the inspector works (no run, no waiting):

```powershell
Get-Content resultsgent_eval_seeded.md -TotalCount 6
```

Point at: 150 of 150 deliberately damaged memos rejected, 0 reached the reader.

**The commands for the terminal shot** (variable `$url` already set):

```powershell
.venv\Scripts\python.exe scripts\smoke_test_api.py --url $url --aws-profile credit-admin --wait 90
```

For the optional "tests" shot (about 35 seconds, fast-forward it if you edit):

```powershell
.venv\Scripts\python.exe -m pytest -q
```

For the optional "pipeline" shot (about a minute; every step says `reused`, then `PIPELINE OK`):

```powershell
.venv\Scripts\python.exe -m pipeline.run
```

## Screenshots to take (for the forum and the README)

| # | Screenshot | Where | Why |
|---|---|---|---|
| 1 | README: results table | GitHub | the numbers at a glance |
| 2 | README: the architecture diagram | GitHub (Mermaid renders there) | the whole system in one picture |
| 3 | `docs/monitoring.png` | repo | the flaw and the rejected fix in one image |
| 4 | The Dagster graph | `dagster dev`, open http://127.0.0.1:3000 | pipeline with its groups |
| 5 | `SMOKE TEST OK` against the live URL | terminal, crop to hide the account | proof it runs on AWS |
| 6 | The browser showing 403 on the URL | browser | proof it is locked |
| 7 | A green GitHub Actions run | GitHub, Actions tab | CI evidence |

Start Dagster for screenshot 4:

```powershell
$env:DAGSTER_HOME = "$PWD\.dagster_home"
.venv\Scripts\python.exe -m dagster dev
```

(Stop it with `Ctrl+C` afterwards.)

## If something fails while you are on stage

- **No internet or SSO expired:** show the README, the monitoring picture and the recorded video. Say: "the live part is recorded here".
- **Smoke test slow:** it retries network trouble up to three times by itself; the first call after a quiet period is a cold start and is slower. That is normal, and it is a good thing to explain.
- **Anything you do not know:** "I haven't done that yet; here is how I would approach it."
