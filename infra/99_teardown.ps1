<#
Undo: delete what the infra scripts created. Run it yourself, only when you want everything gone.
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File infra\99_teardown.ps1

It asks you to type the repository name before deleting anything (a deleted repository and its images cannot be recovered).
Sections for later steps (Lambda function, roles, logs) are added here when those steps are built; every section skips what does not exist.
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [switch]$DryRun
)
$ErrorActionPreference = "Stop"

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

# --- ECR repository (step 3.6b-2) ---
$exitCode = Invoke-Aws @("ecr", "describe-repositories", "--repository-names", $Repository, "--profile", $Profile, "--region", $Region) -Quiet
if ($exitCode -ne 0) {
    Write-Host "ECR repository '$Repository': not found, nothing to delete."
} else {
    Write-Host "ECR repository '$Repository' exists and would be deleted WITH all its images." -ForegroundColor Yellow
    if ($DryRun) {
        Write-Host "  > aws ecr delete-repository --repository-name $Repository --force --profile $Profile --region $Region" -ForegroundColor Cyan
    } else {
        $answer = Read-Host "Type the repository name ($Repository) to confirm"
        if ($answer -ne $Repository) { Write-Host "Not confirmed. Nothing deleted."; exit 1 }
        $code = Invoke-Aws @("ecr", "delete-repository", "--repository-name", $Repository, "--force", "--profile", $Profile, "--region", $Region)
        if ($code -ne 0) { throw "delete failed (exit code $code)" }
        Write-Host "Deleted the ECR repository." -ForegroundColor Green
    }
}
