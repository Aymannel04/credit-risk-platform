<#
Undo: delete what the infra scripts created. Run it yourself, only when you want things gone.
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1 -DryRun     # shows what exists and what would be deleted
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1

Order (so nothing is left pointing at something deleted): 1. the Lambda function and its URL  2. its log group  3. its role  4. the ECR repository
5. the Athena workgroup  6. the Glue database (the table descriptions, not the data)  7. the S3 data lake bucket, emptied first (every version of every file)
8. the GitHub deploy role  9. the trust entry for GitHub (shared by every repository of the account: only delete it if nothing else uses it).
Each part skips what does not exist, and asks you to TYPE the name before deleting (deleted images, logs and files cannot be recovered).
The lake can be rebuilt from the local pipeline: scripts\lake_sync.py upload.
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [string]$FunctionName = "credit-scoring-api",
    [string]$RoleName = "credit-scoring-api-lambda",
    [string]$Database = "credit_lake",
    [string]$Workgroup = "credit-risk",
    [string]$DeployRoleName = "credit-risk-github-deploy",
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

# --- 5. Athena workgroup (day 1, S3 + Athena) ---
if (Test-Exists @("athena", "get-work-group", "--work-group", $Workgroup, "--profile", $Profile, "--region", $Region)) {
    Remove-AfterConfirmation $Workgroup "Athena workgroup '$Workgroup' (with its saved query history)" {
        $code = Invoke-Aws @("athena", "delete-work-group", "--work-group", $Workgroup, "--recursive-delete-option", "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-work-group failed (exit code $code)" }
    } "aws athena delete-work-group --work-group $Workgroup --recursive-delete-option"
} else {
    Write-Host "Athena workgroup '$Workgroup': not found."
}

# --- 6. Glue database (deleting it also deletes the table descriptions inside; the data files are not touched) ---
if (Test-Exists @("glue", "get-database", "--name", $Database, "--profile", $Profile, "--region", $Region)) {
    Remove-AfterConfirmation $Database "Glue database '$Database' and the table descriptions inside it" {
        $code = Invoke-Aws @("glue", "delete-database", "--name", $Database, "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-database failed (exit code $code)" }
    } "aws glue delete-database --name $Database"
} else {
    Write-Host "Glue database '$Database': not found."
}

# --- 7. the S3 bucket: a bucket with versioning must be emptied of every version and delete marker before it can be deleted ---
$account = Get-Text @("sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -ne 0 -or $account -notmatch '^\d{12}$') {
    Write-Host "Not signed in, so the S3 bucket was not checked. Run: aws sso login --profile $Profile" -ForegroundColor Yellow
    exit 1
}
$bucket = "credit-risk-lake-$account"

function Remove-AllObjectVersions([string]$BucketName) {
    # 'Versions' are the files (current and overwritten), 'DeleteMarkers' are the traces left by deletions. Up to 500 at a time.
    foreach ($kind in @("Versions", "DeleteMarkers")) {
        while ($true) {
            $json = Get-Text @("s3api", "list-object-versions", "--bucket", $BucketName, "--max-items", "500",
                "--query", "{Objects: $kind[].{Key: Key, VersionId: VersionId}}", "--output", "json", "--profile", $Profile, "--region", $Region)
            if ($script:ExitCode -ne 0) { throw "list-object-versions failed (exit code $($script:ExitCode))" }
            if (-not $json -or $json -match '"Objects":\s*null') { break }
            $file = Join-Path $env:TEMP "credit-risk-lake-delete.json"
            if ($file -match "\s") { throw "The temporary folder path contains a space ($file): set TEMP to a path without spaces." }
            [System.IO.File]::WriteAllText($file, $json, (New-Object System.Text.UTF8Encoding($false)))
            try {
                $code = Invoke-Aws @("s3api", "delete-objects", "--bucket", $BucketName, "--delete", "file://$file", "--profile", $Profile, "--region", $Region)
            } finally { Remove-Item $file -ErrorAction SilentlyContinue }
            if ($code -ne 0) { throw "delete-objects failed (exit code $code)" }
        }
    }
}

if (Test-Exists @("s3api", "head-bucket", "--bucket", $bucket, "--profile", $Profile, "--region", $Region)) {
    Remove-AfterConfirmation $bucket "S3 bucket '$bucket' WITH every file and every version inside" {
        Remove-AllObjectVersions $bucket
        $code = Invoke-Aws @("s3api", "delete-bucket", "--bucket", $bucket, "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete-bucket failed (exit code $code)" }
    } "aws s3api list-object-versions + delete-objects (all versions), then aws s3api delete-bucket --bucket $bucket"
} else {
    Write-Host "S3 bucket '$bucket': not found."
}

# --- 8. the role GitHub Actions uses to deploy (day 2, OIDC) ---
if (Test-Exists @("iam", "get-role", "--role-name", $DeployRoleName, "--profile", $Profile)) {
    Remove-AfterConfirmation $DeployRoleName "IAM role '$DeployRoleName' (GitHub can no longer deploy)" {
        $code = Invoke-Aws @("iam", "delete-role-policy", "--role-name", $DeployRoleName, "--policy-name", "deploy-one-function", "--profile", $Profile) -Quiet
        $code = Invoke-Aws @("iam", "delete-role", "--role-name", $DeployRoleName, "--profile", $Profile)
        if ($code -ne 0) { throw "delete-role failed (exit code $code)" }
    } "aws iam delete-role-policy / delete-role --role-name $DeployRoleName"
} else {
    Write-Host "IAM role '$DeployRoleName': not found."
}

# --- 9. the trust entry for GitHub's ID cards: it belongs to the whole account, so check nothing else uses it ---
$providerHost = "token.actions.githubusercontent.com"
$providerArn = "arn:aws:iam::${account}:oidc-provider/$providerHost"
if (Test-Exists @("iam", "get-open-id-connect-provider", "--open-id-connect-provider-arn", $providerArn, "--profile", $Profile)) {
    Remove-AfterConfirmation $providerHost "the trust entry for GitHub ($providerHost). Other roles of the account that use it would stop working" {
        $code = Invoke-Aws @("iam", "delete-open-id-connect-provider", "--open-id-connect-provider-arn", $providerArn, "--profile", $Profile)
        if ($code -ne 0) { throw "delete-open-id-connect-provider failed (exit code $code)" }
    } "aws iam delete-open-id-connect-provider --open-id-connect-provider-arn arn:aws:iam::<account>:oidc-provider/$providerHost"
} else {
    Write-Host "Trust entry for GitHub: not found."
}
