<#
Step 3.6b-2: create the private ECR repository (the warehouse for the API container image).

Run it yourself from the repository root, in PowerShell, after `aws sso login --profile credit-admin`:
    powershell -ExecutionPolicy Bypass -File infra\01_create_ecr.ps1 -DryRun     # only prints what it would do
    powershell -ExecutionPolicy Bypass -File infra\01_create_ecr.ps1             # does it

(-ExecutionPolicy Bypass applies to this one run only: Windows blocks .ps1 files by default.)

What it does:
  1. checks whether the repository already exists; if yes it stops and changes nothing (safe to run twice)
  2. creates a PRIVATE repository: immutable tags (a tag can never be overwritten), default AWS encryption, tagged project=credit-risk-platform
  3. adds a cleanup rule (infra\ecr_lifecycle_policy.json): untagged images deleted after 1 day, only the last 3 images kept
Cost: an empty repository costs nothing; stored images cost about 0.10 USD per GB-month (first 500 MB free for a year, per the AWS pricing page).
Undo: infra\99_teardown.ps1
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$policyFile = Join-Path $PSScriptRoot "ecr_lifecycle_policy.json"

# Windows PowerShell 5.1 turns ANY text a program writes to stderr into an exception when $ErrorActionPreference is "Stop",
# even if the text is hidden with 2>$null. So around every aws call we switch to "Continue" and check the exit code ourselves.
function Invoke-Aws([string[]]$AwsArgs, [switch]$Quiet) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) { & aws @AwsArgs 2>$null | Out-Null } else { & aws @AwsArgs | Out-Host }  # Out-Host: a function returns everything it prints, and we want to return only the exit code
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
}

function Show-AndRun([string[]]$AwsArgs) {
    Write-Host ("  > aws " + ($AwsArgs -join " ")) -ForegroundColor Cyan
    if (-not $DryRun) {
        $code = Invoke-Aws $AwsArgs
        if ($code -ne 0) { throw "the command failed (exit code $code)" }
    }
}

Write-Host "Profile: $Profile   Region: $Region   Repository: $Repository   DryRun: $DryRun"

# 1. does it exist already?  (stderr is hidden: 'not found' is the normal answer the first time)
$exitCode = Invoke-Aws @("ecr", "describe-repositories", "--repository-names", $Repository, "--profile", $Profile, "--region", $Region) -Quiet
if ($exitCode -eq 0) {
    Write-Host "The repository '$Repository' already exists. Nothing to do." -ForegroundColor Yellow
    exit 0
}

# 2. create it
Write-Host "Creating the private repository..."
Show-AndRun @("ecr", "create-repository",
    "--repository-name", $Repository,
    "--image-tag-mutability", "IMMUTABLE",
    "--encryption-configuration", "encryptionType=AES256",
    "--tags", "Key=project,Value=credit-risk-platform",
    "--profile", $Profile, "--region", $Region)

# 3. cleanup rule
Write-Host "Adding the cleanup rule (keep the last 3 images)..."
Show-AndRun @("ecr", "put-lifecycle-policy",
    "--repository-name", $Repository,
    "--lifecycle-policy-text", "file://$policyFile",
    "--profile", $Profile, "--region", $Region)

if (-not $DryRun) {
    $uri = & aws ecr describe-repositories --repository-names $Repository --profile $Profile --region $Region --query "repositories[0].repositoryUri" --output text
    if ($LASTEXITCODE -ne 0) { throw "could not read the repository address (exit code $LASTEXITCODE)" }
    Write-Host "Done. Repository address (contains your account number, do not commit it): $uri" -ForegroundColor Green
} else {
    Write-Host "Dry run finished: nothing was created." -ForegroundColor Yellow
}
