<#
Undo: delete what the infra scripts created. Run it yourself, only when you want things gone.
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1 -DryRun     # shows what exists and what would be deleted
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1

Order (so nothing is left pointing at something deleted): 1. the Lambda function and its URL  2. its log group  3. its role  4. the ECR repository.
Each part skips what does not exist, and asks you to TYPE the name before deleting (deleted images and logs cannot be recovered).
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [string]$FunctionName = "credit-scoring-api",
    [string]$RoleName = "credit-scoring-api-lambda",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
$script:ExitCode = 0

Write-Host "Profile: $Profile   Region: $Region   DryRun: $DryRun"

# Windows PowerShell 5.1 turns ANY text a program writes to stderr into an exception when $ErrorActionPreference is "Stop",
# even if hidden with 2>$null: around each aws call we switch to "Continue" and check the exit code ourselves.
function Invoke-Aws([string[]]$AwsArgs, [switch]$Quiet) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        if ($Quiet) { & aws @AwsArgs 2>$null | Out-Null } else { & aws @AwsArgs | Out-Null }
        return $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
}

function Get-Text([string[]]$AwsArgs) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $out = & aws @AwsArgs 2>$null
        $script:ExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    return (($out | Out-String).Trim())
}

function Remove-AfterConfirmation([string]$Name, [string]$What, [scriptblock]$Delete, [string]$ShownCommand) {
    Write-Host "$What exists and would be deleted." -ForegroundColor Yellow
    if ($DryRun) {
        Write-Host "  > $ShownCommand" -ForegroundColor Cyan
        return
    }
    $answer = Read-Host "Type the name ($Name) to confirm"
    if ($answer -ne $Name) { Write-Host "Not confirmed. Nothing more deleted."; exit 1 }
    & $Delete
    Write-Host "Deleted: $What" -ForegroundColor Green
}

function Test-Exists([string[]]$AwsArgs) {
    return ((Invoke-Aws $AwsArgs -Quiet) -eq 0)
}

# --- 1. Lambda function and its URL (step 3.6b-4) ---
if (Test-Exists @("lambda", "get-function", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)) {
    Remove-AfterConfirmation $FunctionName "Lambda function '$FunctionName' and its URL" {
        if (Test-Exists @("lambda", "get-function-url-config", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)) {
            $code = Invoke-Aws @("lambda", "delete-function-url-config", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)
            if ($code -ne 0) { throw "delete-function-url-config failed (exit code $code)" }
        }
        $code = Invoke-Aws @("lambda", "delete-function", "--function-name", $FunctionName, "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-function failed (exit code $code)" }
    } "aws lambda delete-function-url-config / delete-function --function-name $FunctionName"
} else {
    Write-Host "Lambda function '$FunctionName': not found."
}

# --- 2. its log group ---
$logGroup = "/aws/lambda/$FunctionName"
$found = Get-Text @("logs", "describe-log-groups", "--log-group-name-prefix", $logGroup, "--query", "length(logGroups[?logGroupName=='$logGroup'])", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($found -eq "1") {
    Remove-AfterConfirmation $logGroup "log group '$logGroup'" {
        $code = Invoke-Aws @("logs", "delete-log-group", "--log-group-name", $logGroup, "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-log-group failed (exit code $code)" }
    } "aws logs delete-log-group --log-group-name $logGroup"
} else {
    Write-Host "Log group '$logGroup': not found."
}

# --- 3. its role ---
if (Test-Exists @("iam", "get-role", "--role-name", $RoleName, "--profile", $Profile)) {
    Remove-AfterConfirmation $RoleName "IAM role '$RoleName' (with its logs-only policy)" {
        $code = Invoke-Aws @("iam", "delete-role-policy", "--role-name", $RoleName, "--policy-name", "logs-own-log-group-only", "--profile", $Profile) -Quiet
        $code = Invoke-Aws @("iam", "delete-role", "--role-name", $RoleName, "--profile", $Profile)
        if ($code -ne 0) { throw "delete-role failed (exit code $code)" }
    } "aws iam delete-role-policy / delete-role --role-name $RoleName"
} else {
    Write-Host "IAM role '$RoleName': not found."
}

# --- 4. ECR repository (step 3.6b-2) ---
if (Test-Exists @("ecr", "describe-repositories", "--repository-names", $Repository, "--profile", $Profile, "--region", $Region)) {
    Remove-AfterConfirmation $Repository "ECR repository '$Repository' WITH all its images" {
        $code = Invoke-Aws @("ecr", "delete-repository", "--repository-name", $Repository, "--force", "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-repository failed (exit code $code)" }
    } "aws ecr delete-repository --repository-name $Repository --force"
} else {
    Write-Host "ECR repository '$Repository': not found."
}
