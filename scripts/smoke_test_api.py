"""Smoke test for the running scoring API (standard library only, so it runs anywhere: a laptop, CI, after a deploy).

    python scripts/smoke_test_api.py --url http://127.0.0.1:8080 [--wait 60] [--expect-model-id b3069001d62e]
    python scripts/smoke_test_api.py --url https://<id>.lambda-url.eu-north-1.on.aws --aws-profile credit-admin   # a locked (AWS_IAM) Lambda URL

Checks: the service is alive and runs the expected model; the golden loan scores as agreed (553.3 points, 9.17%);
reasons are returned; bad input is refused cleanly (422, never a server error); the API never decides approve/refuse.
Exit code 0 = all good, 1 = something failed. It prints no loan data other than the made-up golden loan.
Locked URLs (Lambda Function URL with AWS_IAM) refuse unsigned requests: with --aws-profile every request is signed (SigV4, service
"lambda") using your SSO session. That is the only part that needs botocore (a dev-only library); without the option the script
uses the standard library only.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

GOLDEN = {
    "credit_score": 700, "dti": 44.0, "ltv": 85.0, "cltv": 85.0, "interest_rate": 4.55, "reference_rate": 4.0,
    "number_of_borrowers": 1, "mi_pct": 25.0, "term_months": 360, "purpose": "P",
}
GOLDEN_SCORE, GOLDEN_SCORE_TOLERANCE = 553.3, 0.2
GOLDEN_PD, GOLDEN_PD_TOLERANCE = 0.09165, 5e-4
MODEL_FILE = Path(__file__).resolve().parents[1] / "models" / "scorecard_v2.json"
SIGNER = None  # set by main() when --aws-profile is given: a function (method, url, body, headers) -> signed headers


def make_signer(credentials, region: str, service: str = "lambda"):
    """Build a SigV4 signer from botocore credentials (frozen: they do not refresh while the script runs)."""
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    def sign(method: str, url: str, body: bytes | None, headers: dict) -> dict:
        request = AWSRequest(method=method, url=url, data=body, headers=dict(headers))
        SigV4Auth(credentials, service, region).add_auth(request)
        return dict(request.headers)

    return sign


def signer_from_profile(profile: str, region: str):
    import botocore.session

    credentials = botocore.session.Session(profile=profile).get_credentials()
    if credentials is None:
        raise SystemExit(f"no credentials for the profile '{profile}': run  aws sso login --profile {profile}")
    return make_signer(credentials.get_frozen_credentials(), region)


TRANSIENT = (urllib.error.URLError, TimeoutError, ConnectionError, OSError)  # network trouble, not an answer from the server


def call(base: str, method: str, path: str, body: bytes | None = None, attempts: int = 3) -> tuple[int, dict | str]:
    """One request. Network trouble (a slow TLS handshake, a dropped connection) is retried, then reported as status 0.
    Any real answer from the server, even an error such as 403 or 422, is returned at once and never retried.
    Every attempt is signed again, so the signature is always fresh."""
    for attempt in range(1, attempts + 1):
        headers = {"content-type": "application/json"}
        if SIGNER is not None:
            headers = SIGNER(method, base + path, body, headers)
        req = urllib.request.Request(base + path, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw, status = r.read().decode("utf-8"), r.status
            break
        except urllib.error.HTTPError as e:  # must come first: HTTPError is a kind of URLError
            raw, status = e.read().decode("utf-8", "replace"), e.code
            break
        except TRANSIENT as e:
            if attempt == attempts:
                return 0, f"network error after {attempts} attempts: {e}"
            time.sleep(2.0 * attempt)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


def wait_until_alive(base: str, seconds: float) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if call(base, "GET", "/health")[0] == 200:
                return True
        except (urllib.error.URLError, OSError, ConnectionError):
            pass
        time.sleep(1.0)
    return False


def run_checks(base: str, expect_model_id: str | None = None) -> list[str]:
    """Returns the list of failures (empty = all good)."""
    fails = []

    def expect(ok: bool, what: str):
        if not ok:
            fails.append(what)

    status, health = call(base, "GET", "/health")
    expect(status == 200 and isinstance(health, dict) and health.get("status") == "ok", f"/health answered {status}")
    if expect_model_id is None and MODEL_FILE.exists():
        expect_model_id = json.loads(MODEL_FILE.read_text(encoding="utf-8"))["model_id"]
    if isinstance(health, dict) and expect_model_id:
        expect(health.get("model_id") == expect_model_id, f"model id is {health.get('model_id')}, expected {expect_model_id}")

    status, info = call(base, "GET", "/model-info")
    expect(status == 200 and isinstance(info, dict) and bool(info.get("known_limits")), "/model-info must list the known limits")
    expect(isinstance(info, dict) and info.get("scaling", {}).get("base_score") == 600, "/model-info scaling.base_score must be 600")

    status, score = call(base, "POST", "/score", json.dumps(GOLDEN).encode())
    ok = status == 200 and isinstance(score, dict)
    expect(ok, f"/score on the golden loan answered {status}")
    if ok:
        expect(abs(score["score"] - GOLDEN_SCORE) <= GOLDEN_SCORE_TOLERANCE, f"golden score {score['score']:.2f}, expected {GOLDEN_SCORE}")
        expect(abs(score["probability_of_default"] - GOLDEN_PD) <= GOLDEN_PD_TOLERANCE, f"golden PD {score['probability_of_default']:.5f}")
        expect(not {"approved", "decision"} & set(score), "the API must never return a decision")

    status, exp = call(base, "POST", "/explain", json.dumps(GOLDEN).encode())
    expect(status == 200 and isinstance(exp, dict) and exp.get("reasons", [{}])[0].get("feature") == "credit_score",
           "/explain must give credit_score as the first reason of the golden loan")

    bad = {
        "unknown field": json.dumps({**GOLDEN, "income": 90000}).encode(),
        "number sent as text": json.dumps({**GOLDEN, "credit_score": "700"}).encode(),
        "value out of range": json.dumps({**GOLDEN, "credit_score": 900}).encode(),
        "Infinity": json.dumps({**GOLDEN, "dti": 0}).encode().replace(b'"dti": 0', b'"dti": Infinity'),
        "not json": b"hello",
    }
    for name, body in bad.items():
        status, _ = call(base, "POST", "/score", body)
        expect(status == 422, f"bad input ({name}) must give 422, got {status}")
    return fails


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8080")
    ap.add_argument("--wait", type=float, default=0, help="seconds to wait for the service to come alive")
    ap.add_argument("--expect-model-id", default=None)
    ap.add_argument("--aws-profile", default=None, help="sign every request (SigV4) with this AWS profile, for a locked Function URL")
    ap.add_argument("--aws-region", default="eu-north-1")
    a = ap.parse_args()
    global SIGNER
    if a.aws_profile:
        SIGNER = signer_from_profile(a.aws_profile, a.aws_region)
    base = a.url.rstrip("/")
    if a.wait and not wait_until_alive(base, a.wait):
        print(f"FAIL: the service at {base} did not answer /health within {a.wait:.0f} s")
        return 1
    fails = run_checks(base, a.expect_model_id)
    for f in fails:
        print("FAIL:", f)
    print("SMOKE TEST OK" if not fails else f"SMOKE TEST FAILED ({len(fails)} problem(s))")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
