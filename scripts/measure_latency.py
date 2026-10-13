"""Measure the LIVE scoring API honestly: speed seen from your computer, and what Lambda itself reports in its logs.

    python scripts/measure_latency.py --url https://<id>.lambda-url.eu-north-1.on.aws --aws-profile credit-admin [--calls 30]

Two kinds of numbers, never mixed:
  client side  how long each signed request takes from THIS computer (internet trip, TLS handshake and the API): depends on where
               you are, so it is labelled with that caveat
  server side  what Lambda writes in its own REPORT log lines: Duration, Billed Duration, Max Memory Used, and Init Duration on a
               cold start (a new container is prepared). These do not depend on your location.
Needs boto3 and botocore (dev-only libraries) to sign requests and to read the logs. It creates and changes nothing in AWS: it sends
about 2 x --calls signed requests and reads CloudWatch logs. Writes results/lambda_latency.json and .md (no URL, no account number).
"""
import argparse
import json
import math
import re
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import smoke_test_api as smoke  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
FUNCTION_NAME = "credit-scoring-api"
LOG_GROUP = f"/aws/lambda/{FUNCTION_NAME}"
_FIELD = re.compile(r"([A-Z][A-Za-z ]*?): ([0-9.]+) (ms|MB)")


def parse_report_line(message: str) -> dict | None:
    """Fields of a Lambda REPORT line (None for any other line). Cold starts are the lines that carry an Init Duration."""
    if not message.startswith("REPORT"):
        return None
    fields = {key.strip(): float(value) for key, value, _unit in _FIELD.findall(message)}
    if "Duration" not in fields:
        return None
    return {
        "duration_ms": fields["Duration"],
        "billed_ms": fields.get("Billed Duration"),
        "memory_size_mb": fields.get("Memory Size"),
        "max_memory_used_mb": fields.get("Max Memory Used"),
        "init_ms": fields.get("Init Duration"),
        "cold_start": "Init Duration" in fields,
    }


def percentile(values: list[float], q: float) -> float:
    """Nearest-rank percentile (q between 0 and 1): the smallest value with at least q of the data at or below it."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    return ordered[max(math.ceil(q * len(ordered)) - 1, 0)]


def describe(values: list[float]) -> dict | None:
    if not values:
        return None
    return {"n": len(values), "min": min(values), "median": statistics.median(values),
            "p95": percentile(values, 0.95), "max": max(values)}


def time_calls(call, n: int) -> dict:
    """`call()` returns an HTTP status. Returns the timing of n calls in milliseconds and how many did not answer 200."""
    times, errors = [], 0
    for _ in range(n):
        start = time.perf_counter()
        status = call()
        times.append((time.perf_counter() - start) * 1000)
        errors += status != 200
    return {"errors": errors, **describe(times)}


def summarize_server(reports: list[dict]) -> dict:
    warm = [r for r in reports if not r["cold_start"]]
    cold = [r for r in reports if r["cold_start"]]
    memory_size = next((r["memory_size_mb"] for r in reports if r["memory_size_mb"]), None)
    billed_gb_s = sum(r["billed_ms"] or 0 for r in reports) / 1000 * (memory_size or 0) / 1024
    return {
        "invocations": len(reports), "cold_starts": len(cold), "memory_size_mb": memory_size,
        "init_duration_ms": describe([r["init_ms"] for r in cold]),
        "duration_ms_warm": describe([r["duration_ms"] for r in warm]),
        "duration_ms_cold": describe([r["duration_ms"] for r in cold]),
        "billed_duration_ms": describe([r["billed_ms"] for r in reports if r["billed_ms"] is not None]),
        "max_memory_used_mb": describe([r["max_memory_used_mb"] for r in reports if r["max_memory_used_mb"] is not None]),
        "billed_gb_seconds_in_window": round(billed_gb_s, 4),
    }


def _fmt(d: dict | None, unit: str = "ms") -> str:
    if not d:
        return "no data"
    return f"n={d['n']}, min {d['min']:.1f}, median {d['median']:.1f}, p95 {d['p95']:.1f}, max {d['max']:.1f} {unit}"


def to_markdown(r: dict) -> str:
    c, s, f = r["client_side"], r["server_side"], r["function"]
    return "\n".join([
        "# Live API latency (measured, not estimated)", "",
        f"Measured {r['measured_at_utc']} against the Lambda function in `{r['region']}` ({f['memory_mb']} MB, {f['timeout_s']} s timeout, "
        f"{f['architecture']}, image tag `{f['image_tag']}`, model `{r['model_id']}`). Nothing here is a benchmark of AWS: it is one "
        "small function measured a few times.", "",
        "## Client side: from the owner's computer (includes the internet trip and the TLS handshake)", "",
        f"{c['note']}", "",
        f"- `POST /score`, {c['calls']} sequential signed calls after one warm-up: {_fmt(c['score'])}; non-200 answers: {c['score']['errors']}",
        f"- `GET /health`, {c['calls']} calls: {_fmt(c['health'])}; non-200 answers: {c['health']['errors']}", "",
        "## Server side: what Lambda reports in its own logs (independent of the client's location)", "",
        f"Window: the last {s['window_minutes']} minutes, {s['invocations']} invocations, of which {s['cold_starts']} cold starts.", "",
        f"- Cold start, init duration (a new container is prepared): {_fmt(s['init_duration_ms'])}",
        f"- Duration of the request itself, warm: {_fmt(s['duration_ms_warm'])}",
        f"- Duration of the request itself, on a cold start: {_fmt(s['duration_ms_cold'])}",
        f"- Billed duration: {_fmt(s['billed_duration_ms'])}",
        f"- Max memory used: {_fmt(s['max_memory_used_mb'], 'MB')} of {s['memory_size_mb']:.0f} MB configured",
        f"- Billed compute in this window: {s['billed_gb_seconds_in_window']} GB-seconds (the free tier is 400,000 GB-seconds a month)", "",
        "## How to read it", "",
        "A cold start happens once, when no prepared container is waiting (first call after a quiet period, or after a deploy): "
        "the user pays the init duration once. A warm call reuses a running container and only pays the request duration. "
        "Quoting one number hides this, so both are reported.", ""])


def fetch_report_lines(session, since_ms: int) -> list[dict]:
    logs = session.client("logs")
    reports, token = [], None
    while True:
        kwargs = {"logGroupName": LOG_GROUP, "filterPattern": "REPORT", "startTime": since_ms}
        if token:
            kwargs["nextToken"] = token
        page = logs.filter_log_events(**kwargs)
        reports += [p for e in page["events"] if (p := parse_report_line(e["message"]))]
        token = page.get("nextToken")
        if not token:
            return reports


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--aws-profile", required=True)
    ap.add_argument("--aws-region", default="eu-north-1")
    ap.add_argument("--calls", type=int, default=30)
    ap.add_argument("--log-minutes", type=int, default=240, help="how far back to read the Lambda REPORT lines")
    a = ap.parse_args()
    import boto3

    session = boto3.Session(profile_name=a.aws_profile, region_name=a.aws_region)
    smoke.SIGNER = smoke.signer_from_profile(a.aws_profile, a.aws_region)
    base = a.url.rstrip("/")
    body = json.dumps(smoke.GOLDEN).encode()

    status, health = smoke.call(base, "GET", "/health")
    if status != 200:
        print(f"FAIL: /health answered {status}: {health}")
        return 1
    print("warm-up done; timing the calls...")
    client = {
        "note": "Measured from the owner's computer; it depends on the distance to Stockholm and on the local network.",
        "calls": a.calls,
        "score": time_calls(lambda: smoke.call(base, "POST", "/score", body)[0], a.calls),
        "health": time_calls(lambda: smoke.call(base, "GET", "/health")[0], a.calls),
    }
    print("waiting 20 s for the logs to arrive...")
    time.sleep(20)
    reports = fetch_report_lines(session, int((time.time() - a.log_minutes * 60) * 1000))
    config = session.client("lambda").get_function(FunctionName=FUNCTION_NAME)
    cfg = config["Configuration"]
    result = {
        "measured_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M"), "region": a.aws_region, "model_id": health["model_id"],
        "function": {"memory_mb": cfg["MemorySize"], "timeout_s": cfg["Timeout"], "architecture": cfg["Architectures"][0],
                     "image_tag": config["Code"].get("ImageUri", "unknown").rsplit(":", 1)[-1]},
        "client_side": client,
        "server_side": {**summarize_server(reports), "window_minutes": a.log_minutes},
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "lambda_latency.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    md = to_markdown(result)
    (RESULTS / "lambda_latency.md").write_text(md, encoding="utf-8")
    print(md)
    return 1 if client["score"]["errors"] or client["health"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
