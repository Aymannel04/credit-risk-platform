"""Smoke test for the running scoring API (standard library only, so it runs anywhere: a laptop, CI, after a deploy).

    python scripts/smoke_test_api.py --url http://127.0.0.1:8080 [--wait 60] [--expect-model-id b3069001d62e]

Checks: the service is alive and runs the expected model; the golden loan scores as agreed (553.3 points, 9.17%);
reasons are returned; bad input is refused cleanly (422, never a server error); the API never decides approve/refuse.
Exit code 0 = all good, 1 = something failed. It prints no loan data other than the made-up golden loan.
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


def call(base: str, method: str, path: str, body: bytes | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(base + path, data=body, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raw, status = r.read().decode("utf-8"), r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read().decode("utf-8", "replace"), e.code
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
    a = ap.parse_args()
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
