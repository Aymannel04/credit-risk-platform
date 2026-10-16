"""Static checks on the AWS set-up scripts: no secrets, safe defaults, valid ECR cleanup rules. Nothing here talks to AWS."""
import json
import re
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1] / "infra"
SCRIPTS = sorted(INFRA.glob("*.ps1"))
ALL_FILES = [*SCRIPTS, *INFRA.glob("*.json"), *INFRA.glob("*.md")]


def test_there_are_scripts_to_check():
    assert {p.name for p in SCRIPTS} >= {"01_create_ecr.ps1", "02_push_image.ps1", "03_create_lambda.ps1", "04_create_lake.ps1", "99_teardown.ps1"}


@pytest.mark.parametrize("path", ALL_FILES, ids=lambda p: p.name)
def test_no_account_number_key_or_token_is_committed(path):
    text = path.read_text(encoding="utf-8")
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", text), "a 12-digit number looks like an AWS account id"
    assert not re.search(r"A(KIA|SIA|ROA)[A-Z0-9]{12,}", text), "an AWS access key id pattern"
    assert "aws_secret_access_key" not in text.lower()
    assert "arn:aws:iam::" not in text or "<" in text  # real ARNs carry an account id; placeholders must be written with <>


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_scripts_stop_on_error_and_have_a_dry_run_and_fixed_region_and_profile(path):
    text = path.read_text(encoding="utf-8")
    assert '$ErrorActionPreference = "Stop"' in text
    assert "[switch]$DryRun" in text
    assert '[string]$Region = "eu-north-1"' in text
    assert '[string]$Profile = "credit-admin"' in text


def test_ecr_script_creates_a_private_immutable_tagged_repository_with_cleanup():
    text = (INFRA / "01_create_ecr.ps1").read_text(encoding="utf-8")
    assert "IMMUTABLE" in text and "AES256" in text and "project,Value=credit-risk-platform" in text
    assert "put-lifecycle-policy" in text
    assert "--force" not in text, "the create script must never delete anything"


def test_teardown_asks_for_confirmation_before_every_delete_and_deletes_in_a_safe_order():
    text = (INFRA / "99_teardown.ps1").read_text(encoding="utf-8")
    # every real delete lives inside a script block handed to Remove-AfterConfirmation, which asks first and stops on a wrong answer
    helper = text[text.index("function Remove-AfterConfirmation"):text.index("function Test-Exists")]
    assert "Read-Host" in helper and "exit 1" in helper and helper.index("Read-Host") < helper.index("& $Delete")
    deletes = [m.start() for m in re.finditer(r'"(delete-function|delete-function-url-config|delete-log-group|delete-role|delete-repository)"', text)]
    assert len(deletes) == 5  # the lake deletes are checked in their own tests below
    for pos in deletes:
        before = text[:pos]
        assert before.rfind("Remove-AfterConfirmation ") > before.rfind(chr(10) + "}"), "a delete must sit inside a confirmed block"
    order = [text.index(f'"{c}"') for c in ("delete-function", "delete-log-group", "delete-role", "delete-repository")]
    assert order == sorted(order), "function first, then logs, then role, then the repository"


@pytest.mark.parametrize("path", [p for p in SCRIPTS if p.name in ("01_create_ecr.ps1", "99_teardown.ps1")], ids=lambda p: p.name)
def test_aws_scripts_handle_stderr_safely_on_windows_powershell(path):
    """Windows PowerShell 5.1 throws on any native stderr text when ErrorActionPreference is Stop (even with 2>$null): every aws call
    must go through the helper that relaxes it and checks the exit code, and the helper must return only the exit code."""
    text = path.read_text(encoding="utf-8")
    assert "function Invoke-Aws" in text and '$ErrorActionPreference = "Continue"' in text
    assert "return $LASTEXITCODE" in text
    assert "| Out-Host" in text or "| Out-Null" in text, "command output must not leak into the returned value"


def test_push_script_handles_stderr_safely_and_returns_only_text():
    text = (INFRA / "02_push_image.ps1").read_text(encoding="utf-8")
    assert "function Invoke-Cmd" in text and 'cmd /c "$Line 2>&1"' in text, "stderr is merged inside cmd.exe so PowerShell never sees it"
    assert "function Get-Text" in text and '$ErrorActionPreference = "Continue"' in text
    assert "$script:ExitCode = $LASTEXITCODE" in text


def test_push_script_builds_one_architecture_without_attestation_and_tests_before_pushing():
    text = (INFRA / "02_push_image.ps1").read_text(encoding="utf-8")
    assert "--platform linux/amd64" in text and "--provenance=false" in text and "--sbom=false" in text
    assert text.index("docker build") < text.index("smoke_test_api.py") < text.index("docker push"), "build, then test the exact image, then push"
    assert "docker logout" in text and "finally" in text, "sign out even when something fails"
    assert ":latest" not in text and "--force" not in text
    assert "rev-parse" in text and "--porcelain" in text
    assert text.index("--porcelain") < text.index("docker build"), "the dirty-tree check must come before building"


def test_push_script_refuses_an_index_manifest_and_never_prints_the_password():
    text = (INFRA / "02_push_image.ps1").read_text(encoding="utf-8")
    assert "application/vnd.docker.distribution.manifest.v2+json" in text and "application/vnd.oci.image.manifest.v1+json" in text
    assert "image.index" not in text.replace("not an index", "")
    assert "--password-stdin" in text and "Write-Host $password" not in text and "Remove-Variable password" in text


def test_lifecycle_policy_obeys_the_ecr_rules():
    policy = json.loads((INFRA / "ecr_lifecycle_policy.json").read_text(encoding="utf-8"))
    rules = policy["rules"]
    priorities = [r["rulePriority"] for r in rules]
    assert len(set(priorities)) == len(priorities), "priorities must be unique"
    any_rules = [r for r in rules if r["selection"]["tagStatus"] == "any"]
    assert len(any_rules) == 1
    assert any_rules[0]["rulePriority"] == max(priorities), "the 'any' rule must have the highest priority number (it runs last)"
    keep = any_rules[0]["selection"]
    assert keep["countType"] == "imageCountMoreThan" and keep["countNumber"] == 3
    assert all(r["action"] == {"type": "expire"} for r in rules)


# ---------- step 3.6b-4: the Lambda script and its policies ----------

LAMBDA = INFRA / "03_create_lambda.ps1"


def test_lambda_script_creates_a_locked_url_a_least_privilege_role_and_a_short_log_retention():
    text = LAMBDA.read_text(encoding="utf-8")
    assert "--auth-type AWS_IAM" in text
    assert "--auth-type NONE" not in text, "the function URL must stay locked"
    assert "put-retention-policy" in text and "$LogRetentionDays" in text
    assert "--package-type Image" in text and "--architectures x86_64" in text
    assert "AdministratorAccess" not in text and "AWSLambdaBasicExecutionRole" not in text and "*:*" not in text
    assert "add-permission" not in text, "no resource policy that could open the function to others"


def test_lambda_script_defaults_are_small_and_it_checks_before_creating():
    text = LAMBDA.read_text(encoding="utf-8")
    assert "[int]$MemoryMb = 512" in text and "[int]$TimeoutSeconds = 10" in text and "[int]$LogRetentionDays = 14" in text
    for check in ("get-role", "describe-log-groups", '"get-function"', "get-function-url-config"):
        assert check in text, check
    assert text.index('"get-function"') < text.index("lambda create-function "), "look before creating"
    assert "Test-Path" in text and "smoke_test_api.py" in text and "--aws-profile" in text


def test_lambda_script_handles_stderr_safely_and_returns_only_text():
    text = LAMBDA.read_text(encoding="utf-8")
    assert 'cmd /c "$Line 2>&1"' in text and "function Get-Text" in text and '$ErrorActionPreference = "Continue"' in text
    assert "$script:ExitCode = $LASTEXITCODE" in text


def test_trust_policy_lets_only_lambda_assume_the_role():
    policy = json.loads((INFRA / "lambda_trust_policy.json").read_text(encoding="utf-8"))
    (stmt,) = policy["Statement"]
    assert stmt["Effect"] == "Allow" and stmt["Action"] == "sts:AssumeRole"
    assert stmt["Principal"] == {"Service": "lambda.amazonaws.com"}


def test_logs_policy_allows_two_log_actions_on_its_own_log_group_only():
    template = (INFRA / "lambda_logs_policy.template.json").read_text(encoding="utf-8")
    policy = json.loads(template)
    (stmt,) = policy["Statement"]
    assert stmt["Effect"] == "Allow"
    assert sorted(stmt["Action"]) == ["logs:CreateLogStream", "logs:PutLogEvents"]
    assert stmt["Resource"] == "arn:aws:logs:__REGION__:__ACCOUNT__:log-group:/aws/lambda/__FUNCTION__:*"
    assert "*" not in stmt["Resource"].replace(":*", "", 1)
    rendered = template.replace("__REGION__", "eu-north-1").replace("__ACCOUNT__", "123456789012").replace("__FUNCTION__", "credit-scoring-api")
    assert json.loads(rendered)["Statement"][0]["Resource"].endswith("log-group:/aws/lambda/credit-scoring-api:*")


# ---------- day 1: the S3 lake script, its policies, and the teardown of the lake ----------

LAKE = INFRA / "04_create_lake.ps1"


def test_lake_script_makes_a_private_encrypted_versioned_https_only_bucket():
    text = LAKE.read_text(encoding="utf-8")
    for needle in ("BlockPublicAcls=true", "IgnorePublicAcls=true", "BlockPublicPolicy=true", "RestrictPublicBuckets=true",
                   "put-bucket-encryption", "AES256", "put-bucket-versioning", "put-bucket-policy", "put-bucket-lifecycle-configuration"):
        assert needle in text, needle
    assert "=false" not in text, "no protection may be switched off"
    assert "public-read" not in text and "--acl" not in text


def test_lake_script_never_deletes_and_sets_a_scan_limit_that_is_enforced():
    text = LAKE.read_text(encoding="utf-8")
    body = text[text.index("$ErrorActionPreference"):]
    assert not re.search(r"(delete-|rm |rb |--force)", body), "the create script must never delete anything"
    assert "[int]$ScanLimitMb = 200" in text and "BytesScannedCutoffPerQuery" in text and "EnforceWorkGroupConfiguration = $true" in text
    assert text.index("$ScanLimitMb -lt 10") < text.index("Write-Host \"Profile:"), "refuse a limit below Athena's 10 MB minimum before touching anything"


def test_lake_script_checks_before_creating_and_handles_stderr_safely():
    text = LAKE.read_text(encoding="utf-8")
    for check in ("head-bucket", "get-database", "get-work-group"):
        assert check in text, check
    assert text.index("head-bucket") < text.index("create-bucket")
    assert text.index("put-public-access-block") < text.index("put-bucket-policy"), "close the doors before anything else"
    assert 'cmd /c "$Line 2>&1"' in text and "function Get-Text" in text and '$ErrorActionPreference = "Continue"' in text
    assert "UTF8Encoding($false)" in text, "AWS rejects JSON files that start with a byte-order mark"


def test_bucket_policy_denies_everything_that_is_not_https_on_this_bucket_only():
    policy = json.loads((INFRA / "lake_bucket_policy.template.json").read_text(encoding="utf-8"))
    (stmt,) = policy["Statement"]
    assert stmt["Effect"] == "Deny" and stmt["Principal"] == "*" and stmt["Condition"] == {"Bool": {"aws:SecureTransport": "false"}}
    assert stmt["Resource"] == ["arn:aws:s3:::__BUCKET__", "arn:aws:s3:::__BUCKET__/*"]


def test_lifecycle_rules_clean_results_partial_uploads_and_old_versions():
    rules = {r["ID"]: r for r in json.loads((INFRA / "lake_lifecycle.json").read_text(encoding="utf-8"))["Rules"]}
    assert len(rules) == 3 and all(r["Status"] == "Enabled" and "Filter" in r for r in rules.values())
    assert rules["athena-results-expire-after-7-days"]["Filter"] == {"Prefix": "athena-results/"}
    assert rules["athena-results-expire-after-7-days"]["Expiration"] == {"Days": 7}
    assert rules["abandoned-partial-uploads-after-1-day"]["AbortIncompleteMultipartUpload"] == {"DaysAfterInitiation": 1}
    assert rules["overwritten-versions-expire-after-30-days"]["Filter"] == {"Prefix": "lake/"}, "never expire the CURRENT data files"
    assert "Expiration" not in rules["overwritten-versions-expire-after-30-days"]


def test_teardown_removes_the_lake_after_confirmation_and_the_bucket_last():
    text = (INFRA / "99_teardown.ps1").read_text(encoding="utf-8")
    for call in ("delete-work-group", "delete-database", "delete-bucket"):
        pos = text.index(f'"{call}"')
        before = text[:pos]
        assert before.rfind("Remove-AfterConfirmation ") > before.rfind(chr(10) + "}"), f"{call} must sit inside a confirmed block"
    order = [text.index(f'"{c}"') for c in ("delete-repository", "delete-work-group", "delete-database", "delete-bucket")]
    assert order == sorted(order), "workgroup, then database, then the bucket they point to"
    assert "list-object-versions" in text and "DeleteMarkers" in text, "a versioned bucket must be emptied of every version first"
    assert text.index("Remove-AllObjectVersions $bucket") < text.index('"delete-bucket"')
