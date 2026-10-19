"""Static checks of the GitHub -> AWS deployment (OIDC): the workflow, the trust rule, the permissions, the script. Nothing here talks to AWS."""
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
INFRA = ROOT / "infra"
WORKFLOWS = ROOT / ".github" / "workflows"
DEPLOY = WORKFLOWS / "deploy.yml"
SCRIPT = INFRA / "05_create_github_deploy.ps1"


@pytest.fixture(scope="module")
def wf():
    return yaml.safe_load(DEPLOY.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def steps(wf):
    return wf["jobs"]["deploy"]["steps"]


def _index(steps, fragment):
    hits = [i for i, s in enumerate(steps) if fragment in s.get("name", "")]
    assert len(hits) == 1, f"expected one step named like '{fragment}', found {len(hits)}"
    return hits[0]


# ---------- the workflow ----------

def test_deploys_only_on_a_push_to_main_or_by_hand_never_from_a_pull_request(wf):
    triggers = wf.get("on", wf.get(True))  # YAML 1.1 reads the key `on` as True
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"branches": ["main"]}
    assert "pull_request" not in DEPLOY.read_text(encoding="utf-8")


def test_permissions_are_the_least_possible(wf):
    assert wf["permissions"] == {"contents": "read"}
    assert wf["jobs"]["deploy"]["permissions"] == {"contents": "read", "id-token": "write"}


def test_no_password_or_secret_is_used_anywhere():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "secrets." not in text
    for forbidden in ("aws-access-key-id", "aws-secret-access-key", "AWS_SECRET_ACCESS_KEY", "AWS_ACCESS_KEY_ID", "session-token:"):
        assert forbidden.lower() not in text.lower(), forbidden
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", text), "no account number in the workflow"
    assert "vars.AWS_DEPLOY_ROLE_ARN" in text


def test_every_action_is_pinned_to_an_exact_commit():
    uses = re.findall(r"uses:\s*(\S+)", DEPLOY.read_text(encoding="utf-8"))
    assert uses, "the workflow uses actions"
    for ref in uses:
        assert re.fullmatch(r"[\w./-]+@[0-9a-f]{40}", ref), f"{ref} is not pinned to a full commit hash"


def test_the_job_is_skipped_until_the_role_variable_exists_and_never_cancelled_half_way(wf):
    assert "vars.AWS_DEPLOY_ROLE_ARN" in wf["jobs"]["deploy"]["if"]
    assert wf["concurrency"]["cancel-in-progress"] is False


def test_everything_is_tested_before_aws_is_touched(steps):
    order = [_index(steps, n) for n in ("Style and common mistakes", "Tests (pytest)", "Build the API container image",
                                        "Check what is inside the image", "Smoke-test the running container",
                                        "Get a temporary AWS key", "Push the image to ECR", "Point the Lambda function",
                                        "Smoke-test the LIVE")]
    assert order == sorted(order), "tests, build, local container checks, THEN the key, push, update, live smoke test"
    credentials = steps[_index(steps, "Get a temporary AWS key")]
    assert credentials["uses"].startswith("aws-actions/configure-aws-credentials@")
    assert credentials["with"]["role-to-assume"] == "${{ vars.AWS_DEPLOY_ROLE_ARN }}"


def test_the_image_is_built_the_way_lambda_accepts_it_and_tagged_with_the_commit():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "--platform linux/amd64" in text and "--provenance=false" in text and "--sbom=false" in text
    assert "git rev-parse --short=7 HEAD" in text, "same tag rule as infra/02_push_image.ps1"
    assert ":latest" not in text and "--force" not in text
    assert "imageManifestMediaType" in text, "a multi-image index must be refused, as in the push script"


def test_the_function_must_run_exactly_the_pushed_image_and_the_live_url_is_tested_signed():
    text = DEPLOY.read_text(encoding="utf-8")
    assert "Code.ResolvedImageUri" in text and "$DIGEST" in text
    assert "aws lambda wait function-updated" in text
    assert "--aws-default-credentials" in text and "get-function-url-config" in text
    assert "::add-mask::$URL" in text and "::add-mask::$ACCOUNT" in text, "the URL and the account number must be hidden in the logs"


def test_the_deploy_runs_the_same_checks_as_ci():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    deploy = DEPLOY.read_text(encoding="utf-8")
    for command in ("ruff check .", "pytest -q", "diff scripts/expected_image_files.txt /tmp/image_files.txt",
                    "python scripts/smoke_test_api.py --url http://127.0.0.1:8080 --wait 60"):
        assert command in ci and command in deploy, command


# ---------- the trust rule: who may take the role ----------

def _render(path: Path, **values) -> str:
    text = path.read_text(encoding="utf-8")
    for key, value in values.items():
        text = text.replace(f"__{key}__", value)
    return text


def test_only_one_repository_on_one_branch_may_take_the_role():
    template = json.loads((INFRA / "github_oidc_trust_policy.template.json").read_text(encoding="utf-8"))
    (stmt,) = template["Statement"]
    assert stmt["Effect"] == "Allow" and stmt["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert stmt["Principal"] == {"Federated": "arn:aws:iam::__ACCOUNT__:oidc-provider/token.actions.githubusercontent.com"}
    assert set(stmt["Condition"]) == {"StringEquals"}, "StringLike would allow wildcards"
    conditions = stmt["Condition"]["StringEquals"]
    assert conditions["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    # GitHub writes the permanent numeric ids of the owner and the repository into the subject of repositories created after 2026-07-15
    # (found in the first real run: repo:Aymannel04@207994149/credit-risk-platform@1410817428:ref:refs/heads/main)
    assert conditions["token.actions.githubusercontent.com:sub"] == "repo:__OWNER__@__OWNER_ID__/__REPO__@__REPO_ID__:ref:refs/heads/__BRANCH__"
    rendered = json.loads(_render(INFRA / "github_oidc_trust_policy.template.json", ACCOUNT="111122223333", OWNER="Aymannel04",
                                  OWNER_ID="207994149", REPO="credit-risk-platform", REPO_ID="1410817428", BRANCH="main"))
    sub = rendered["Statement"][0]["Condition"]["StringEquals"]["token.actions.githubusercontent.com:sub"]
    assert sub == "repo:Aymannel04@207994149/credit-risk-platform@1410817428:ref:refs/heads/main" and "*" not in sub


def test_the_script_refuses_wildcards_and_leftover_placeholders_before_creating_anything():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "-notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$'" in text and "-notmatch '^[A-Za-z0-9_./-]+$'" in text
    assert "-match '\\*'" in text and '-match "__"' in text
    assert "GithubOwnerId -notmatch '^\\d+$'" in text and "GithubRepoId -notmatch '^\\d+$'" in text, "the numeric ids must be plain numbers"
    assert text.index("GithubRepo must look like") < text.index("create-open-id-connect-provider")
    assert text.index('-match "__"') < text.index("iam create-role")


def test_the_repository_in_the_script_default_is_the_real_one():
    remote = (ROOT / ".git" / "config").read_text(encoding="utf-8") if (ROOT / ".git" / "config").exists() else ""
    script = SCRIPT.read_text(encoding="utf-8")
    default = re.search(r'\[string\]\$GithubRepo = "([^"]+)"', script).group(1)
    assert default == "Aymannel04/credit-risk-platform"
    assert re.search(r'\[string\]\$GithubOwnerId = "\d+"', script) and re.search(r'\[string\]\$GithubRepoId = "\d+"', script)
    if "github.com" in remote:
        assert default in remote or "Aymannel04/credit-risk-platform" in remote


# ---------- what the role may do ----------

EXPECTED_ACTIONS = {
    "ecr:GetAuthorizationToken",
    "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
    "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:GetRepositoryPolicy", "ecr:DescribeImages",
    "lambda:UpdateFunctionCode", "lambda:GetFunction", "lambda:GetFunctionConfiguration", "lambda:GetFunctionUrlConfig",
    "lambda:InvokeFunctionUrl", "lambda:InvokeFunction",
}


def _statements():
    policy = json.loads((INFRA / "github_deploy_policy.template.json").read_text(encoding="utf-8"))
    return policy["Statement"]


def _actions(stmt):
    return [stmt["Action"]] if isinstance(stmt["Action"], str) else stmt["Action"]


def test_the_role_can_do_exactly_these_actions_and_nothing_else():
    allowed = {a for s in _statements() for a in _actions(s)}
    assert allowed == EXPECTED_ACTIONS
    assert all(s["Effect"] == "Allow" for s in _statements())
    assert not any("*" in a for s in _statements() for a in _actions(s)), "no wildcard action"
    assert not any(a.split(":")[0] in ("iam", "s3", "sts", "athena", "glue", "ce", "budgets", "organizations") for a in allowed)


def test_everything_is_limited_to_one_repository_and_one_function():
    for s in _statements():
        resource = s["Resource"]
        if "ecr:GetAuthorizationToken" in _actions(s):
            assert resource == "*", "AWS cannot scope this one action to a repository"
        else:
            assert resource.startswith(("arn:aws:ecr:__REGION__:__ACCOUNT__:repository/__REPOSITORY__",
                                        "arn:aws:lambda:__REGION__:__ACCOUNT__:function:__FUNCTION__")) and "*" not in resource
    destructive = {a for s in _statements() for a in _actions(s) if re.search(r"Delete|Remove|Put(?!Image)|Create|Set|Update(?!FunctionCode)", a)}
    assert destructive == set(), destructive


def test_calling_the_url_is_allowed_only_for_iam_protected_urls_and_only_through_the_url():
    by_action = {a: s for s in _statements() for a in _actions(s)}
    assert by_action["lambda:InvokeFunctionUrl"]["Condition"] == {"StringEquals": {"lambda:FunctionUrlAuthType": "AWS_IAM"}}
    assert by_action["lambda:InvokeFunction"]["Condition"] == {"Bool": {"lambda:InvokedViaFunctionUrl": "true"}}


def test_the_script_asks_aws_what_the_role_can_and_cannot_do_and_stops_on_a_surprise():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "simulate-principal-policy" in text and "NOT AS EXPECTED" in text and "throw" in text[text.index("NOT AS EXPECTED"):]
    denied = re.findall(r'@\("([a-z0-9]+:[A-Za-z]+)",[^)]*"denied"\)', text)
    assert {"lambda:DeleteFunction", "lambda:UpdateFunctionConfiguration", "ecr:DeleteRepository", "iam:CreateUser", "s3:GetObject", "s3:PutObject"} <= set(denied)
    allowed = re.findall(r'@\("([a-z0-9]+:[A-Za-z]+)",[^)]*"allowed"\)', text)
    assert {"lambda:UpdateFunctionCode", "ecr:PutImage", "ecr:GetAuthorizationToken"} <= set(allowed)


def test_the_script_creates_but_never_deletes_and_is_safe_to_repeat():
    text = SCRIPT.read_text(encoding="utf-8")
    body = text[text.index("$ErrorActionPreference"):]
    assert not re.search(r"\b(delete-|remove-|--force)", body.lower().replace("remove-item", "").replace("remove-variable", ""))
    for check in ("list-open-id-connect-providers", "get-role"):
        assert check in text
    assert text.index("list-open-id-connect-providers") < text.index("iam create-open-id-connect-provider")
    assert "update-assume-role-policy" in text and "put-role-policy" in text
    assert "[switch]$DryRun" in text and '[string]$Region = "eu-north-1"' in text and '[string]$Profile = "credit-admin"' in text
    assert 'cmd /c "$Line 2>&1"' in text and "UTF8Encoding($false)" in text


def test_teardown_removes_the_deploy_role_then_the_shared_trust_entry_after_confirmation():
    text = (INFRA / "99_teardown.ps1").read_text(encoding="utf-8")
    for call in ('"delete-role-policy", "--role-name", $DeployRoleName', '"delete-open-id-connect-provider"'):
        assert call in text, call
    pos = text.index('"delete-open-id-connect-provider"')
    assert text[:pos].rfind("Remove-AfterConfirmation ") > text[:pos].rfind(chr(10) + "}")
    assert text.index('"delete-role", "--role-name", $DeployRoleName') < pos, "the role first, then the trust entry it relies on"


# ---------- the smoke test can sign with the temporary key from the environment ----------

def _load_smoke():
    spec = importlib.util.spec_from_file_location("smoke_test_api", ROOT / "scripts" / "smoke_test_api.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_smoke_test_signs_with_the_credentials_found_in_the_environment(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIA" + "IOSFODNN7EXAMPLE")  # AWS documentation example values, not real
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "wJalrXUtnFEMI/K7MDENG/bPx" + "RfiCYEXAMPLEKEY")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "example-session-token")
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    sign = _load_smoke().signer_from_profile(None, "eu-north-1")
    headers = {k.lower(): v for k, v in sign("GET", "https://abc.lambda-url.eu-north-1.on.aws/health", None, {}).items()}
    assert "/eu-north-1/lambda/aws4_request" in headers["authorization"] and headers["x-amz-security-token"] == "example-session-token"


def test_smoke_test_stops_clearly_when_there_are_no_credentials(monkeypatch, tmp_path):
    for var in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "none"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    with pytest.raises(SystemExit, match="no AWS credentials found in the environment"):
        _load_smoke().signer_from_profile(None, "eu-north-1")


# ---------- the first real run failed at the login: a diagnostic that cannot leak the token, and a pinned runner ----------

def test_failed_login_diagnostic_runs_only_on_that_failure_and_never_prints_the_token(steps):
    step = steps[_index(steps, "Diagnose a failed OIDC login")]
    assert step["if"] == "failure() && steps.aws_login.outcome == 'failure'"
    assert steps[_index(steps, "Get a temporary AWS key")]["id"] == "aws_login"
    run = step["run"]
    assert 'echo "$TOKEN"' not in run and "echo $TOKEN" not in run and "print(sys.argv" not in run
    assert "claims.get(key)" in run and '"sub"' in run
    assert _index(steps, "Get a temporary AWS key") < _index(steps, "Diagnose a failed OIDC login") < _index(steps, "Push the image to ECR")


def test_the_runner_image_is_pinned(wf):
    assert wf["jobs"]["deploy"]["runs-on"] == "ubuntu-24.04"


def test_ci_uses_the_same_pinned_runner_as_the_deploy():
    ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in ci and "ubuntu-latest" not in ci.replace("'ubuntu-latest'", "")


def test_a_refused_login_fails_fast(steps):
    assert steps[_index(steps, "Get a temporary AWS key")]["with"]["retry-max-attempts"] == 3


def test_both_image_builds_retry_when_a_public_registry_answers_429():
    """The first CI failures were `429 Too Many Requests` from public.ecr.aws (anonymous downloads from shared GitHub machines)."""
    for name in ("ci.yml", "deploy.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        build = text[text.index("for attempt in 1 2 3 4"):]
        assert "docker build" in build.split("done")[0] and "sleep $((attempt * 30))" in build and "exit 1" in build, name
