<#
Step 3.7 (day 1): create the S3 data lake (a private bucket), the Glue database and the Athena workgroup with a scan limit.

Run it yourself from the repository root, in PowerShell, after `aws sso login --profile credit-admin`:
    powershell -ExecutionPolicy Bypass -File infra\04_create_lake.ps1 -DryRun     # reads from AWS and prints the plan, creates nothing
    powershell -ExecutionPolicy Bypass -File infra\04_create_lake.ps1             # does it

What it creates or sets (every part checks first and every setting can be re-applied, so running it twice is safe):
  1. a PRIVATE bucket `credit-risk-lake-<account number>` in eu-north-1: all four "block public access" switches on, encryption at rest (SSE-S3),
     versioning on, a policy that refuses any connection that is not HTTPS, tag project=credit-risk-platform
  2. cleanup rules (infra\lake_lifecycle.json): Athena result files expire after 7 days, abandoned partial uploads after 1 day,
     overwritten versions after 30 days
  3. a Glue database `credit_lake` (the address book: it will list the tables, it stores no data)
  4. an Athena workgroup `credit-risk`: results go to the bucket under athena-results/, the setting is ENFORCED (a query cannot choose
     another place), and every query is CANCELLED if it would scan more than -ScanLimitMb (default 200 MB)
The data itself is sent afterwards by  scripts\lake_sync.py upload  (then  tables  and  parity).
Cost: an empty bucket, a database and a workgroup cost nothing. Storage is about 0.02 to 0.03 USD per GB-month (S3 pricing page, to confirm
for eu-north-1), our files are about 0.3 GB. Athena is billed per data scanned (about 5 USD per TB, Athena pricing page) and the workgroup limit caps the damage of one bad query.
Undo: infra\99_teardown.ps1 (it empties the bucket, all versions included, after you type its name)
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Database = "credit_lake",
    [string]$Workgroup = "credit-risk",
    [int]$ScanLimitMb = 200,
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$script:ExitCode = 0
if ($ScanLimitMb -lt 10) { throw "Athena's minimum scan limit is 10 MB." }

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

Write-Host "Profile: $Profile   Region: $Region   DryRun: $DryRun"
$common = "--profile $Profile --region $Region"

# who am I?  (the bucket name needs the account number; it is computed here and never written to a file)
$account = Get-Text "aws" @("sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -ne 0 -or $account -notmatch '^\d{12}$') { throw "Not signed in. Run: aws sso login --profile $Profile" }
$bucket = "credit-risk-lake-$account"

# 1. the bucket
if (Test-Aws @("s3api", "head-bucket", "--bucket", $bucket, "--profile", $Profile, "--region", $Region)) {
    Write-Host "1. The bucket exists. Re-applying its protections (safe to repeat)." -ForegroundColor Yellow
} else {
    Write-Host "1. Creating the private bucket..."
    Do-Aws "s3api create-bucket --bucket $bucket --create-bucket-configuration LocationConstraint=$Region $common" "create-bucket"
}
Do-Aws "s3api put-public-access-block --bucket $bucket --public-access-block-configuration BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true $common" "put-public-access-block"
Do-Aws "s3api put-bucket-encryption --bucket $bucket --server-side-encryption-configuration ""Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256}}]"" $common" "put-bucket-encryption"
Do-Aws "s3api put-bucket-versioning --bucket $bucket --versioning-configuration Status=Enabled $common" "put-bucket-versioning"
Do-Aws "s3api put-bucket-tagging --bucket $bucket --tagging ""TagSet=[{Key=project,Value=credit-risk-platform}]"" $common" "put-bucket-tagging"

$policyText = (Get-Content "infra\lake_bucket_policy.template.json" -Raw).Replace("__BUCKET__", $bucket)
$policyFile = Write-TempJson "credit-risk-lake-policy.json" $policyText
try {
    Do-Aws "s3api put-bucket-policy --bucket $bucket --policy file://$policyFile $common" "put-bucket-policy"
} finally {
    Remove-Item $policyFile -ErrorAction SilentlyContinue
}

# 2. cleanup rules
Write-Host "2. Cleanup rules..."
Do-Aws "s3api put-bucket-lifecycle-configuration --bucket $bucket --lifecycle-configuration file://infra/lake_lifecycle.json $common" "put-bucket-lifecycle-configuration"

# 3. the Glue database (the address book for Athena)
$dbExists = Test-Aws @("glue", "get-database", "--name", $Database, "--profile", $Profile, "--region", $Region)
if ($dbExists) {
    Write-Host "3. Glue database $Database exists." -ForegroundColor Yellow
} else {
    Write-Host "3. Creating the Glue database $Database..."
    Do-Aws "glue create-database --database-input Name=$Database,Description=Tables-of-the-credit-risk-platform-lake --tags project=credit-risk-platform $common" "create-database"
}

# 4. the Athena workgroup: results in our bucket (enforced) and a cap on the data one query may scan
$cutoff = [long]$ScanLimitMb * 1024 * 1024
$result = @{ OutputLocation = "s3://$bucket/athena-results/"; EncryptionConfiguration = @{ EncryptionOption = "SSE_S3" } }
if (Test-Aws @("athena", "get-work-group", "--work-group", $Workgroup, "--profile", $Profile, "--region", $Region)) {
    Write-Host "4. Athena workgroup $Workgroup exists. Re-applying its settings (limit $ScanLimitMb MB per query)." -ForegroundColor Yellow
    $updates = @{ EnforceWorkGroupConfiguration = $true; PublishCloudWatchMetricsEnabled = $true; BytesScannedCutoffPerQuery = $cutoff; ResultConfigurationUpdates = $result }
    $file = Write-TempJson "credit-risk-workgroup-update.json" ($updates | ConvertTo-Json -Depth 5 -Compress)
    try { Do-Aws "athena update-work-group --work-group $Workgroup --configuration-updates file://$file $common" "update-work-group" } finally { Remove-Item $file -ErrorAction SilentlyContinue }
} else {
    Write-Host "4. Creating the Athena workgroup $Workgroup (limit $ScanLimitMb MB per query)..."
    $config = @{ EnforceWorkGroupConfiguration = $true; PublishCloudWatchMetricsEnabled = $true; BytesScannedCutoffPerQuery = $cutoff; ResultConfiguration = $result }
    $file = Write-TempJson "credit-risk-workgroup.json" ($config | ConvertTo-Json -Depth 5 -Compress)
    try { Do-Aws "athena create-work-group --name $Workgroup --configuration file://$file --description Credit-risk-platform-queries-with-a-scan-limit --tags Key=project,Value=credit-risk-platform $common" "create-work-group" } finally { Remove-Item $file -ErrorAction SilentlyContinue }
}

# what is really there now (read back, so you see the truth and not only our intention)
if (-not $DryRun) {
    Write-Host "Read back from AWS:" -ForegroundColor Green
    foreach ($check in @(
        @("s3api", "get-public-access-block", "--bucket", $bucket, "--query", "PublicAccessBlockConfiguration", "--output", "json"),
        @("s3api", "get-bucket-versioning", "--bucket", $bucket, "--query", "Status", "--output", "text"),
        @("s3api", "get-bucket-encryption", "--bucket", $bucket, "--query", "ServerSideEncryptionConfiguration.Rules[0].ApplyServerSideEncryptionByDefault.SSEAlgorithm", "--output", "text"),
        @("athena", "get-work-group", "--work-group", $Workgroup, "--query", "WorkGroup.Configuration.[BytesScannedCutoffPerQuery,EnforceWorkGroupConfiguration]", "--output", "json")
    )) {
        $text = Get-Text "aws" ($check + @("--profile", $Profile, "--region", $Region))
        Write-Host ("  " + $check[0] + " " + $check[1] + ": " + ($text -replace "\s+", " "))
    }
    Write-Host "Done. Next:  .venv\Scripts\python scripts\lake_sync.py upload --dry-run" -ForegroundColor Green
} else {
    Write-Host "Dry run finished: nothing was created or changed." -ForegroundColor Yellow
}
