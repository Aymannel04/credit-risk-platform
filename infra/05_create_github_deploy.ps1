<#
Step 3.6c (day 2): let GitHub Actions deploy to AWS WITHOUT any stored password (OIDC), through a role that can do almost nothing.

Run it yourself from the repository root, in PowerShell, after `aws sso login --profile credit-admin`:
    powershell -ExecutionPolicy Bypass -File infra\05_create_github_deploy.ps1 -DryRun     # reads from AWS and prints the plan, creates nothing
    powershell -ExecutionPolicy Bypass -File infra\05_create_github_deploy.ps1             # does it

What it creates (each piece is skipped if it exists; the two policies are re-applied each time, so running it twice is safe):
  1. the "trust entry" in your AWS account: AWS accepts the signed ID cards (OIDC tokens) that GitHub Actions issues, audience sts.amazonaws.com
  2. the role `credit-risk-github-deploy`. Its TRUST rule says: only a run of exactly this GitHub repository, on exactly its main branch, may
     take the role (no wildcard: with `repo:*` any repository on GitHub could). The temporary key it gets lasts at most 1 hour.
  3. its permissions (infra\github_deploy_policy.template.json): push images to the ONE ECR repository, update and read the ONE Lambda function,
     call that function's locked URL for the smoke test. Nothing else (no S3, no IAM, no billing, no other function, no delete).
Then it ASKS AWS (policy simulator) whether the role may do 3 things it needs and may NOT do 7 things it must never do, and stops if an answer is wrong.
Finally it prints the role address and the one command that stores it in GitHub as a (non-secret) variable.
Cost: none. Roles and trust entries are free.
Undo: infra\99_teardown.ps1 (removes the role, then the trust entry after you type its name)
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [string]$FunctionName = "credit-scoring-api",
    [string]$RoleName = "credit-risk-github-deploy",
    [string]$GithubRepo = "Aymannel04/credit-risk-platform",
    [string]$Branch = "main",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$script:ExitCode = 0
$ProviderHost = "token.actions.githubusercontent.com"
if ($GithubRepo -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw "GithubRepo must look like owner/name, with no wildcard." }
if ($Branch -notmatch '^[A-Za-z0-9_./-]+$') { throw "Branch must be one exact branch name, with no wildcard." }

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

# AWS reads JSON files given as file://path; they must be plain UTF-8 without the byte-order mark Windows likes to add.
function Write-TempJson([string]$Name, [string]$Text) {
    $file = Join-Path $env:TEMP $Name
    if ($file -match "\s") { throw "The temporary folder path contains a space ($file): set TEMP to a path without spaces." }
    [System.IO.File]::WriteAllText($file, $Text, (New-Object System.Text.UTF8Encoding($false)))
    return $file
}

Write-Host "Profile: $Profile   Region: $Region   Role: $RoleName   Trusted: repo:${GithubRepo}:ref:refs/heads/$Branch   DryRun: $DryRun"
$common = "--profile $Profile --region $Region"

$account = Get-Text "aws" @("sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -ne 0 -or $account -notmatch '^\d{12}$') { throw "Not signed in. Run: aws sso login --profile $Profile" }
$roleArn = "arn:aws:iam::${account}:role/${RoleName}"
$functionArn = "arn:aws:lambda:${Region}:${account}:function:${FunctionName}"
$repoArn = "arn:aws:ecr:${Region}:${account}:repository/${Repository}"

# 1. the trust entry for GitHub's ID cards (one per account; shared by every repository you may add later)
$provider = Get-Text "aws" @("iam", "list-open-id-connect-providers", "--query", "OpenIDConnectProviderList[?ends_with(Arn, '/$ProviderHost')].Arn", "--output", "text", "--profile", $Profile)
if ($script:ExitCode -eq 0 -and $provider -like "arn:aws:iam::*") {
    Write-Host "1. The trust entry for $ProviderHost exists." -ForegroundColor Yellow
} else {
    Write-Host "1. Creating the trust entry for $ProviderHost..."
    Do-Aws "iam create-open-id-connect-provider --url https://$ProviderHost --client-id-list sts.amazonaws.com --tags Key=project,Value=credit-risk-platform --profile $Profile" "create-open-id-connect-provider"
}

# 2. the role, with the exact-repository, exact-branch trust rule
$trustText = (Get-Content "infra\github_oidc_trust_policy.template.json" -Raw).Replace("__ACCOUNT__", $account).Replace("__GITHUB_REPO__", $GithubRepo).Replace("__BRANCH__", $Branch)
if ($trustText -match "__" -or $trustText -match '\*') { throw "The trust policy still has a placeholder or a wildcard: refusing to continue." }
$trustFile = Write-TempJson "credit-risk-github-trust.json" $trustText
try {
    $roleExists = Test-Aws @("iam", "get-role", "--role-name", $RoleName, "--profile", $Profile)
    if ($roleExists) {
        Write-Host "2. Role $RoleName exists. Re-applying its trust rule (safe to repeat)." -ForegroundColor Yellow
        Do-Aws "iam update-assume-role-policy --role-name $RoleName --policy-document file://$trustFile --profile $Profile" "update-assume-role-policy"
    } else {
        Write-Host "2. Creating the role $RoleName..."
        Do-Aws "iam create-role --role-name $RoleName --assume-role-policy-document file://$trustFile --description Deploy-from-GitHub-Actions-main-branch-only --max-session-duration 3600 --tags Key=project,Value=credit-risk-platform --profile $Profile" "create-role"
    }
} finally {
    Remove-Item $trustFile -ErrorAction SilentlyContinue
}

# 3. its permissions
$policyText = (Get-Content "infra\github_deploy_policy.template.json" -Raw).Replace("__REGION__", $Region).Replace("__ACCOUNT__", $account).Replace("__REPOSITORY__", $Repository).Replace("__FUNCTION__", $FunctionName)
if ($policyText -match "__") { throw "The permissions policy still has a placeholder: refusing to continue." }
$policyFile = Write-TempJson "credit-risk-github-permissions.json" $policyText
try {
    Write-Host "3. Attaching the permissions (one repository, one function, nothing else)..."
    Do-Aws "iam put-role-policy --role-name $RoleName --policy-name deploy-one-function --policy-document file://$policyFile --profile $Profile" "put-role-policy"
} finally {
    Remove-Item $policyFile -ErrorAction SilentlyContinue
}

if ($DryRun) {
    Write-Host "Dry run finished: nothing was created or changed." -ForegroundColor Yellow
    exit 0
}

# 4. ask AWS (policy simulator) what the role may and may not do; a wrong answer stops the script
Write-Host "4. Asking AWS what the role may do (the new role needs a few seconds to be known everywhere)..."
Start-Sleep -Seconds 10
$expectations = @(
    @("lambda:UpdateFunctionCode", $functionArn, "allowed"),
    @("ecr:PutImage", $repoArn, "allowed"),
    @("ecr:GetAuthorizationToken", "*", "allowed"),
    @("lambda:DeleteFunction", $functionArn, "denied"),
    @("lambda:UpdateFunctionConfiguration", $functionArn, "denied"),
    @("ecr:DeleteRepository", $repoArn, "denied"),
    @("ecr:PutImage", "arn:aws:ecr:${Region}:${account}:repository/some-other-repository", "denied"),
    @("iam:CreateUser", "*", "denied"),
    @("s3:GetObject", "arn:aws:s3:::credit-risk-lake-${account}/*", "denied"),
    @("s3:PutObject", "arn:aws:s3:::credit-risk-lake-${account}/*", "denied")
)
$bad = 0
foreach ($e in $expectations) {
    $decision = Get-Text "aws" @("iam", "simulate-principal-policy", "--policy-source-arn", $roleArn, "--action-names", $e[0], "--resource-arns", $e[1],
        "--query", "EvaluationResults[0].EvalDecision", "--output", "text", "--profile", $Profile)
    $answer = if ($decision -eq "allowed") { "allowed" } elseif ($decision) { "denied" } else { "no answer" }
    $ok = ($answer -eq $e[2])
    if (-not $ok) { $bad++ }
    $shown = $e[1] -replace $account, "<account>"
    Write-Host ("   {0,-38} on {1,-62} -> {2,-9} {3}" -f $e[0], $shown, $answer, $(if ($ok) { "ok" } else { "NOT AS EXPECTED (wanted $($e[2]))" })) -ForegroundColor $(if ($ok) { "Gray" } else { "Red" })
}
if ($bad -gt 0) { throw "$bad answer(s) from the policy simulator were not as expected: do NOT use this role until that is understood." }

Write-Host ""
Write-Host "Done. The role (its address contains your account number, do not commit it):" -ForegroundColor Green
Write-Host "  $roleArn"
Write-Host "Store it in GitHub as a repository VARIABLE (not a secret: it is only an address), from the repository root:"
Write-Host "  gh variable set AWS_DEPLOY_ROLE_ARN --repo $GithubRepo --body $roleArn" -ForegroundColor Cyan
Write-Host "or in the browser: the repository > Settings > Secrets and variables > Actions > Variables > New repository variable."
Write-Host "Until that variable exists, the deploy workflow stays skipped."
