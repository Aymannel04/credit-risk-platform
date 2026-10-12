<#
Step 3.6b-3: build the API container image for ONE architecture, test it, and push it to the ECR repository.

Run it yourself from the repository root, in PowerShell, with Docker Desktop running and after `aws sso login --profile credit-admin`:
    powershell -ExecutionPolicy Bypass -File infra\02_push_image.ps1 -DryRun     # reads from AWS and prints the plan, builds and pushes nothing
    powershell -ExecutionPolicy Bypass -File infra\02_push_image.ps1             # does it

What it does, in order:
  1. refuses to run if the code has uncommitted changes (the image tag is the git commit, so the tag must truthfully name the code inside)
  2. skips everything if that tag is already in the repository (safe to run twice; tags are immutable)
  3. builds for linux/amd64 only, with provenance and SBOM metadata off: Lambda rejects multi-architecture images and the extra attestation manifest
  4. smoke-tests the exact image it just built (health, golden loan, clean refusals)
  5. signs in to the repository with a temporary 12-hour password from your SSO session (never printed, never written to a file)
  6. pushes the image, then asks AWS what was stored and refuses a multi-image index; prints digest and size
  7. signs out of the repository again
Cost: the image is stored compressed (tens of MB); the repository gives 500 MB free for a year (AWS ECR pricing page).
Undo: infra\99_teardown.ps1 deletes the repository with its images.
#>
param(
    [string]$Profile = "credit-admin",
    [string]$Region = "eu-north-1",
    [string]$Repository = "credit-scoring-api",
    [switch]$DryRun,
    [switch]$SkipSmokeTest
)
$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path (Join-Path $PSScriptRoot ".."))
$script:ExitCode = 0

# Windows PowerShell 5.1 turns ANY text a program writes to stderr into an exception when $ErrorActionPreference is "Stop".
# Docker and git write progress and warnings to stderr, so: (a) Invoke-Cmd merges stderr into stdout INSIDE cmd.exe, and
# (b) Get-Text relaxes the preference around the call. Both keep the exit code in $script:ExitCode and return nothing else.
function Invoke-Cmd([string]$Line, [switch]$Quiet) {
    Write-Host "  > $Line" -ForegroundColor Cyan
    if ($Quiet) { & cmd /c "$Line 2>&1" | Out-Null } else { & cmd /c "$Line 2>&1" | Out-Host }
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

function Assert-Ok([string]$What) {
    if ($script:ExitCode -ne 0) { throw "$What failed (exit code $($script:ExitCode))" }
}

Write-Host "Profile: $Profile   Region: $Region   Repository: $Repository   DryRun: $DryRun"

# 1. the tag must name the code: no uncommitted changes allowed
$dirty = Get-Text "git" @("status", "--porcelain")
Assert-Ok "git status"
if ($dirty) { throw "There are uncommitted changes. Commit them first: the image tag is the git commit.`n$dirty" }
$tag = Get-Text "git" @("rev-parse", "--short=7", "HEAD")
Assert-Ok "git rev-parse"

# who am I, and where is the repository?
$account = Get-Text "aws" @("sts", "get-caller-identity", "--query", "Account", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -ne 0 -or $account -notmatch '^\d{12}$') { throw "Not signed in. Run: aws sso login --profile $Profile" }
$registry = "$account.dkr.ecr.$Region.amazonaws.com"
$image = "${registry}/${Repository}:${tag}"
Write-Host "Image tag (git commit): $tag"

# 2. already there?
$digest = Get-Text "aws" @("ecr", "describe-images", "--repository-name", $Repository, "--image-ids", "imageTag=$tag",
    "--query", "imageDetails[0].imageDigest", "--output", "text", "--profile", $Profile, "--region", $Region)
if ($script:ExitCode -eq 0 -and $digest -match '^sha256:') {
    Write-Host "The tag $tag is already in the repository (digest $digest). Nothing to do." -ForegroundColor Yellow
    exit 0
}

if ($DryRun) {
    Write-Host "Dry run: this is what would happen (nothing is built or pushed):" -ForegroundColor Yellow
    Write-Host "  > docker build --platform linux/amd64 --provenance=false --sbom=false --tag <image> ."
    if (-not $SkipSmokeTest) { Write-Host "  > docker run -d -p 8099:8080 <image>   then   python scripts\smoke_test_api.py --url http://127.0.0.1:8099 --wait 60" }
    Write-Host "  > aws ecr get-login-password | docker login --username AWS --password-stdin <registry>"
    Write-Host "  > docker push <image>"
    Write-Host "  > aws ecr batch-get-image ... (the stored manifest must be a single image, not an index)"
    Write-Host "  > docker logout <registry>"
    exit 0
}

# 3. build for one architecture, without the extra metadata Lambda rejects
Write-Host "Building..."
Invoke-Cmd "docker build --platform linux/amd64 --provenance=false --sbom=false --tag $image ."
Assert-Ok "docker build"

# 4. smoke-test the exact image we are about to ship
if (-not $SkipSmokeTest) {
    Write-Host "Smoke-testing the built image..."
    $python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
    Invoke-Cmd "docker rm -f api-push-check" -Quiet
    try {
        Invoke-Cmd "docker run -d --name api-push-check -p 8099:8080 $image" -Quiet
        Assert-Ok "docker run"
        Invoke-Cmd "$python scripts\smoke_test_api.py --url http://127.0.0.1:8099 --wait 60"
        Assert-Ok "the smoke test"
    } finally {
        Invoke-Cmd "docker rm -f api-push-check" -Quiet
    }
}

# 5-7. sign in, push, verify, sign out
try {
    Write-Host "Signing in to the repository..."
    $password = Get-Text "aws" @("ecr", "get-login-password", "--profile", $Profile, "--region", $Region)
    if ($script:ExitCode -ne 0 -or -not $password) { throw "could not get a temporary repository password" }
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $password | & docker login --username AWS --password-stdin $registry 2>$null | Out-Host
        $script:ExitCode = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    Remove-Variable password
    Assert-Ok "docker login"

    Write-Host "Pushing..."
    Invoke-Cmd "docker push $image"
    Assert-Ok "docker push"

    $mediaType = Get-Text "aws" @("ecr", "batch-get-image", "--repository-name", $Repository, "--image-ids", "imageTag=$tag",
        "--query", "images[0].imageManifestMediaType", "--output", "text", "--profile", $Profile, "--region", $Region)
    Assert-Ok "reading the stored manifest"
    $allowed = @("application/vnd.docker.distribution.manifest.v2+json", "application/vnd.oci.image.manifest.v1+json")
    if ($allowed -notcontains $mediaType) { throw "The stored manifest is '$mediaType': Lambda needs a single image, not an index. Do not use this tag." }

    $details = Get-Text "aws" @("ecr", "describe-images", "--repository-name", $Repository, "--image-ids", "imageTag=$tag",
        "--query", "imageDetails[0].[imageDigest,imageSizeInBytes]", "--output", "text", "--profile", $Profile, "--region", $Region)
    Assert-Ok "describe-images"
    $parts = $details -split "\s+"
    $megabytes = [math]::Round([double]$parts[1] / 1MB, 1)
    Write-Host "Done. Tag $tag, single image ($mediaType), digest $($parts[0]), stored size $megabytes MB." -ForegroundColor Green
} finally {
    Invoke-Cmd "docker logout $registry" -Quiet
}
