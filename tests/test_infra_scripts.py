"""Static checks on the AWS set-up scripts: no secrets, safe defaults, valid ECR cleanup rules. Nothing here talks to AWS."""
import json
import re
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1] / "infra"
SCRIPTS = sorted(INFRA.glob("*.ps1"))
ALL_FILES = [*SCRIPTS, *INFRA.glob("*.json"), *INFRA.glob("*.md")]


def test_there_are_scripts_to_check():
    assert {p.name for p in SCRIPTS} >= {"01_create_ecr.ps1", "99_teardown.ps1"}


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


def test_teardown_asks_for_confirmation_before_deleting():
    text = (INFRA / "99_teardown.ps1").read_text(encoding="utf-8")
    assert "Read-Host" in text and "delete-repository" in text
    real_delete = text.index('Invoke-Aws @("ecr", "delete-repository"')
    assert text.index("Read-Host") < real_delete, "confirmation must come before the real delete"
    assert "exit 1" in text[text.index("Read-Host"):real_delete], "a wrong answer must stop the script before deleting"


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda p: p.name)
def test_scripts_handle_stderr_safely_on_windows_powershell(path):
    """Windows PowerShell 5.1 throws on any native stderr text when ErrorActionPreference is Stop (even with 2>$null): every aws call
    must go through the helper that relaxes it and checks the exit code, and the helper must return only the exit code."""
    text = path.read_text(encoding="utf-8")
    assert "function Invoke-Aws" in text and '$ErrorActionPreference = "Continue"' in text
    assert "return $LASTEXITCODE" in text
    assert "| Out-Host" in text or "| Out-Null" in text, "command output must not leak into the returned value"


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
