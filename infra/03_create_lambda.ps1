<#
Step 3.6b-4: create the Lambda function (from the image already in ECR) with a LOCKED Function URL.

Run it yourself from the repository root, in PowerShell, after `aws sso login --profile credit-admin`:
    powershell -ExecutionPolicy Bypass -File infra\03_create_lambda.ps1 -DryRun     # reads from AWS and prints the plan, creates nothing
    powershell -ExecutionPolicy Bypass -File infra\03_create_lambda.ps1             # does it

What it creates (each piece is skipped if it already exists, so running it twice is safe):
  1. an execution role `credit-scoring-api-lambda`: Lambda may assume it, and it may do ONE thing: write logs into its own log group
  2. the log group /aws/lambda/credit-scoring-api, kept 14 days (otherwise Lambda creates one that never expires)
  3. the function, from the newest image in the ECR repository (or -Tag): 512 MB memory, 10 s timeout, x86_64, no public access
  4. a Function URL with auth type AWS_IAM: every request must be signed with AWS credentials, strangers get 403
Then it prints the URL and the repository policy Lambda added by itself to be allowed to pull the image, and smoke-tests the URL
with signed requests (use -SkipSmokeTest to skip).
Cost: an idle function costs nothing; the free tier is 1M requests and 400,000 GB-seconds a month (AWS Lambda pricing page).
Undo: infra\99_teardown.ps1
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [string]$FunctionName = "credit-scoring-api",
    [string]$RoleName = "credit-scoring-api-lambda",
    [string]$Tag = "",
    [int]$MemoryMb = 512,
    [int]$TimeoutSeconds = 10,
    [int]$LogRetentionDays = 14,
    [switch]$DryRun,
    [switch]$SkipSmokeTest
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$script:ExitCode = 0

# Windows PowerShell 5.1 turns ANY text a program writes to stderr into an exception when $ErrorActionPreference is "Stop".
# So: Invoke-Cmd merges stderr into stdout INSIDE cmd.exe, Get-Text relaxes the preference around the call.
# Both keep the exit code in $script:ExitCode and return nothing else (a PowerShell function returns everything it prints).
function Invoke-Cmd([string]$Line) {
    Write-Host "  > $Line" -ForegroundColor Cyan
    & cmd /c "$Line 2>&1" | Out-Host
    $script:ExitCode = $LASTEXITCODE
}

function Get-Text([string]$Exe, [string[]]$Arguments) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & $Exe @Arguments 2>$null
        $script:ExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    return (($out | Out-String).Trim())
}

function Test-Aws([string[]]$AwsArgs) {
    $null = Get-Text "aws" $AwsArgs
    return ($script:ExitCode -eq 0)
}

function Assert-Ok([string]$What) {
    if ($script:ExitCode -ne 0) { throw "$What failed (exit code $($script:ExitCode))" }
}

function Do-Aws([string]$AwsLine, [string]$What) {
    if ($DryRun) { Write-Host "  (dry run) would run: aws $AwsLine" -ForegroundColor Yellow; return }
    Invoke-Cmd "aws $AwsLine"
    Assert-Ok $What
}

Write-Host "Profile: $Profile   Region: $Region   Function: $FunctionName   DryRun: $DryRun"
$common = "--profile $Profile --region $Region"

# who am I?
$account = Get-Text "aws" @("sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -ne 0 -or $account -notmatch '^\d{12}$') { throw "Not signed in. Run: aws sso login --profile $Profile" }
$roleArn = "arn:aws:iam::${account}:role/${RoleName}"

# which image? the newest pushed one unless -Tag is given; it must exist
if (-not $Tag) {
    $Tag = Get-Text "aws" @("ecr", "describe-images", "--repository-name", $Repository,
        "--query", "sort_by(imageDetails,&imagePushedAt)[-1].imageTags[0]", "--output", "text", "--profile", $Profile, "--region", $Region)
    if ($script:ExitCode -ne 0 -or -not $Tag -or $Tag -eq "None") { throw "No image found in the repository '$Repository'. Run infra\02_push_image.ps1 first." }
}
if (-not (Test-Aws @("ecr", "describe-images", "--repository-name", $Repository, "--image-ids", "imageTag=$Tag", "--profile", $Profile, "--region", $Region))) {
    throw "The image tag '$Tag' is not in the repository '$Repository'."
}
$imageUri = "${account}.dkr.ecr.${Region}.amazonaws.com/${Repository}:${Tag}"
Write-Host "Image: tag $Tag"

# 1. execution role: Lambda may assume it; it may only write logs into its own log group
$roleExists = Test-Aws @("iam", "get-role", "--role-name", $RoleName, "--profile", $Profile)
if ($roleExists) {
    Write-Host "1. Role $RoleName exists." -ForegroundColor Yellow
} else {
    Write-Host "1. Creating the role $RoleName..."
    Do-Aws "iam create-role --role-name $RoleName --assume-role-policy-document file://infra/lambda_trust_policy.json --tags Key=project,Value=credit-risk-platform --profile $Profile" "create-role"
}
$policyText = (Get-Content "infra\lambda_logs_policy.template.json" -Raw).Replace("__REGION__", $Region).Replace("__ACCOUNT__", $account).Replace("__FUNCTION__", $FunctionName)
$policyFile = Join-Path $env:TEMP "credit-scoring-api-logs-policy.json"
if ($policyFile -match "\s") { throw "The temporary folder path contains a space ($policyFile): set TEMP to a path without spaces." }
try {
    Set-Content -Path $policyFile -Value $policyText -Encoding ascii
    Write-Host "   Attaching the logs-only policy to the role (safe to repeat)..."
    Do-Aws "iam put-role-policy --role-name $RoleName --policy-name logs-own-log-group-only --policy-document file://$policyFile --profile $Profile" "put-role-policy"
} finally {
    Remove-Item $policyFile -ErrorAction SilentlyContinue
}

# 2. log group with a retention
$logGroup = "/aws/lambda/$FunctionName"
$found = Get-Text "aws" @("logs", "describe-log-groups", "--log-group-name-prefix", $logGroup,
    "--query", "length(logGroups[?logGroupName=='$logGroup'])", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($found -eq "1") {
    Write-Host "2. Log group $logGroup exists." -ForegroundColor Yellow
} else {
    Write-Host "2. Creating the log group $logGroup..."
    Do-Aws "logs create-log-group --log-group-name $logGroup --tags project=credit-risk-platform $common" "create-log-group"
}
Do-Aws "logs put-retention-policy --log-group-name $logGroup --retention-in-days $LogRetentionDays $common" "put-retention-policy"

# 3. the function
if (Test-Aws @("lambda", "get-function", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)) {
    Write-Host "3. Function $FunctionName exists (updating its code is done by the deploy workflow, step 3.6c)." -ForegroundColor Yellow
} else {
    Write-Host "3. Creating the function..."
    if (-not $roleExists -and -not $DryRun) { Write-Host "   (the new role needs a few seconds to become usable: waiting 10 s)"; Start-Sleep -Seconds 10 }
    $create = "lambda create-function --function-name $FunctionName --package-type Image --code ImageUri=$imageUri --role $roleArn --memory-size $MemoryMb --timeout $TimeoutSeconds --architectures x86_64 --tags project=credit-risk-platform $common"
    if ($DryRun) {
        Write-Host "  (dry run) would run: aws $create" -ForegroundColor Yellow
    } else {
        $attempt = 0
        while ($true) {
            $attempt++
            Invoke-Cmd "aws $create"
            if ($script:ExitCode -eq 0) { break }
            if ($attempt -ge 5) { throw "create-function failed $attempt times (exit code $($script:ExitCode))" }
            Write-Host "   not ready yet (often the new role is still spreading inside AWS): waiting 10 s, attempt $attempt of 5" -ForegroundColor Yellow
            Start-Sleep -Seconds 10
        }
        Write-Host "   waiting until the function is active (AWS prepares the image, usually a few seconds)..."
        Do-Aws "lambda wait function-active-v2 --function-name $FunctionName $common" "wait function-active-v2"
    }
}

# 4. the locked URL
if (Test-Aws @("lambda", "get-function-url-config", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)) {
    Write-Host "4. The Function URL exists." -ForegroundColor Yellow
} else {
    Write-Host "4. Creating the Function URL with auth type AWS_IAM (locked)..."
    Do-Aws "lambda create-function-url-config --function-name $FunctionName --auth-type AWS_IAM $common" "create-function-url-config"
}

if ($DryRun) { Write-Host "Dry run finished: nothing was created." -ForegroundColor Yellow; exit 0 }

$url = Get-Text "aws" @("lambda", "get-function-url-config", "--function-name", $FunctionName, "--query", "FunctionUrl", "--output", "text", "--profile", $Profile, "--region", $Region)
Assert-Ok "reading the Function URL"
Write-Host ""
Write-Host "Function settings:" -ForegroundColor Green
Invoke-Cmd "aws lambda get-function-configuration --function-name $FunctionName --query {state:State,memory:MemorySize,timeout:Timeout,architecture:Architectures[0],package:PackageType} $common"
Write-Host "Repository policy that Lambda added by itself to pull the image (documented behaviour):" -ForegroundColor Green
$policy = Get-Text "aws" @("ecr", "get-repository-policy", "--repository-name", $Repository, "--query", "policyText", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -eq 0) { Write-Host $policy } else { Write-Host "  (no repository policy: Lambda reads the image through its own permissions)" }
Write-Host "Function URL (locked, contains no secret but do not commit it): $url" -ForegroundColor Green

if (-not $SkipSmokeTest) {
    Write-Host ""
    Write-Host "Smoke-testing the locked URL with signed requests (the first call is slow: a cold start)..."
    $python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
    Invoke-Cmd "$python scripts\smoke_test_api.py --url $url --aws-profile $Profile --aws-region $Region --wait 90"
    Assert-Ok "the smoke test against the Lambda URL"
}
