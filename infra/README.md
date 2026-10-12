# infra/: AWS set-up scripts (you run them, one step at a time)

Rules for everything in this folder:
- **You run the scripts, not the assistant.** Your AWS credentials stay in your terminal.
- Every script has a **`-DryRun`** switch that only prints what it would do. Read that first.
- Scripts are **safe to run twice**: they check what exists before creating anything.
- `99_teardown.ps1` deletes what the other scripts created. It asks you to type a name before deleting.
- **Never commit** account numbers, repository addresses, keys or tokens. Scripts read the account at run time.
- Everything is created in region `eu-north-1` (Stockholm) with the profile `credit-admin`, and tagged `project=credit-risk-platform`.

Before any script: sign in (the session lasts a few hours)

```powershell
aws sso login --profile credit-admin
```

Run a script from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File infra\01_create_ecr.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File infra\01_create_ecr.ps1
```

(`-ExecutionPolicy Bypass` applies to that single run only. Windows blocks `.ps1` files by default.)

| Script | Step | Creates |
|---|---|---|
| `01_create_ecr.ps1` | 3.6b-2 | A private container repository with immutable tags and a keep-last-3 rule |
| `02_push_image.ps1` | 3.6b-3 | Builds the image (one architecture), smoke-tests it, pushes it tagged with the git commit, and checks what was stored |
| `03_create_lambda.ps1` | 3.6b-4 | A least-privilege role (logs only), a log group (14 days), the Lambda function from the pushed image, and a LOCKED Function URL (AWS_IAM) |
| `99_teardown.ps1` | any | Deletes what the scripts above created, in a safe order, asking you to type each name |

More scripts are added here as steps are approved (the deploy workflow with OIDC, the S3 data lake).

Before `02_push_image.ps1`: Docker Desktop must be running and every change must be committed (the image tag is the git commit).
