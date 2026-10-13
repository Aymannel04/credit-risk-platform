"""The latency script: the log-line parser, the percentile maths, the summaries and the report (no AWS needed)."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    sys.path.insert(0, str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location("measure_latency", ROOT / "scripts" / "measure_latency.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load()
WARM = "REPORT RequestId: 8f1a3c2e-0000-4a5b-9c1d-123456789abc\tDuration: 3.21 ms\tBilled Duration: 4 ms\tMemory Size: 512 MB\tMax Memory Used: 71 MB\t"
COLD = ("REPORT RequestId: 8f1a3c2e-0000-4a5b-9c1d-123456789abd\tDuration: 18.40 ms\tBilled Duration: 419 ms\tMemory Size: 512 MB\t"
        "Max Memory Used: 78 MB\tInit Duration: 400.12 ms\t")


def test_parse_a_warm_report_line():
    r = M.parse_report_line(WARM)
    assert r == {"duration_ms": 3.21, "billed_ms": 4.0, "memory_size_mb": 512.0, "max_memory_used_mb": 71.0, "init_ms": None, "cold_start": False}


def test_parse_a_cold_report_line_and_do_not_confuse_the_three_durations():
    r = M.parse_report_line(COLD)
    assert r["cold_start"] and r["init_ms"] == 400.12
    assert r["duration_ms"] == 18.40 and r["billed_ms"] == 419.0, "Duration, Billed Duration and Init Duration are three different numbers"


@pytest.mark.parametrize("line", ["START RequestId: abc Version: $LATEST", "END RequestId: abc", "INFO:     127.0.0.1 - GET /health", "", "REPORT without numbers"])
def test_other_lines_are_ignored(line):
    assert M.parse_report_line(line) is None


def test_percentile_is_nearest_rank():
    values = list(range(1, 21))  # 1..20
    assert M.percentile(values, 0.95) == 19 and M.percentile(values, 0.5) == 10 and M.percentile(values, 1.0) == 20
    assert M.percentile([7.0], 0.95) == 7.0
    assert M.percentile([3, 1, 2], 0.5) == 2, "input order must not matter"
    with pytest.raises(ValueError):
        M.percentile([], 0.5)


def test_describe_has_the_five_numbers_and_handles_no_data():
    d = M.describe([4.0, 1.0, 3.0, 2.0])
    assert d == {"n": 4, "min": 1.0, "median": 2.5, "p95": 4.0, "max": 4.0}
    assert M.describe([]) is None


def test_time_calls_counts_errors_and_times_every_call():
    statuses = iter([200, 200, 500, 200])
    out = M.time_calls(lambda: next(statuses), 4)
    assert out["n"] == 4 and out["errors"] == 1 and out["min"] >= 0


def test_server_summary_separates_cold_from_warm_and_counts_billed_compute():
    reports = [M.parse_report_line(WARM)] * 9 + [M.parse_report_line(COLD)]
    s = M.summarize_server(reports)
    assert s["invocations"] == 10 and s["cold_starts"] == 1 and s["memory_size_mb"] == 512
    assert s["init_duration_ms"]["median"] == 400.12
    assert s["duration_ms_warm"]["n"] == 9 and s["duration_ms_cold"]["n"] == 1
    assert s["max_memory_used_mb"]["max"] == 78.0
    assert s["billed_gb_seconds_in_window"] == pytest.approx((9 * 4 + 419) / 1000 * 0.5, abs=1e-4)


def test_server_summary_with_no_cold_start_has_no_init_numbers():
    s = M.summarize_server([M.parse_report_line(WARM)] * 3)
    assert s["cold_starts"] == 0 and s["init_duration_ms"] is None and s["duration_ms_cold"] is None


def test_markdown_states_what_is_measured_and_where():
    reports = [M.parse_report_line(WARM)] * 4 + [M.parse_report_line(COLD)]
    stats = {"errors": 0, **M.describe([50.0, 60.0, 70.0])}
    result = {
        "measured_at_utc": "2026-10-13 18:00", "region": "eu-north-1", "model_id": "b3069001d62e",
        "function": {"memory_mb": 512, "timeout_s": 10, "architecture": "x86_64", "image_tag": "ac13c6b"},
        "client_side": {"note": "Measured from the owner's computer.", "calls": 3, "score": stats, "health": stats},
        "server_side": {**M.summarize_server(reports), "window_minutes": 240},
    }
    md = M.to_markdown(result)
    for needle in ("not estimated", "Client side", "Server side", "cold start", "image tag `ac13c6b`", "init duration", "400.1"):
        assert needle in md, needle
    assert "http" not in md and "lambda-url" not in md, "the report must never contain the function URL"
