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
| `04_create_lake.ps1` | 3.7 | A private S3 bucket (no public access, encrypted, versioned, HTTPS only, cleanup rules), a Glue database, and an Athena workgroup that cancels any query scanning more than 200 MB |
| `05_create_github_deploy.ps1` | 3.6c | The trust entry for GitHub's ID cards (OIDC) and the role `credit-risk-github-deploy`: only this repository, only its main branch, only push-to-one-ECR-repository and update-one-Lambda-function. Asks AWS's policy simulator to prove what it can and cannot do |
| `99_teardown.ps1` | any | Deletes what the scripts above created, in a safe order (the S3 bucket is emptied of every version first), asking you to type each name |

After `04_create_lake.ps1`, the data goes up with `python scripts/lake_sync.py upload`, then `tables`, then `parity` (see the header of that script).
More scripts are added here as steps are approved (the deploy workflow with OIDC).

Before `02_push_image.ps1`: Docker Desktop must be running and every change must be committed (the image tag is the git commit).

## Deploying from GitHub (no stored password)

After `05_create_github_deploy.ps1`, store the role address as a GitHub **variable** (an address, not a secret):

```powershell
gh variable set AWS_DEPLOY_ROLE_ARN --repo Aymannel04/credit-risk-platform --body <the arn printed by the script>
```

Until that variable exists, `.github/workflows/deploy.yml` is skipped. After it exists, every push to `main` runs the tests and container checks with no AWS access,
then gets a temporary key (about an hour), pushes the image tagged with the git commit, updates the Lambda function, checks that the function runs exactly the pushed
image digest, and smoke-tests the live locked URL with signed requests.

Going back after a bad deploy (the last 3 images are kept in ECR): list the tags, then point the function at an older one, from your computer:

```powershell
aws ecr describe-images --repository-name credit-scoring-api --query "sort_by(imageDetails,&imagePushedAt)[].imageTags" --profile credit-admin --region eu-north-1
aws lambda update-function-code --function-name credit-scoring-api --image-uri <registry>/credit-scoring-api:<older tag> --profile credit-admin --region eu-north-1
```
