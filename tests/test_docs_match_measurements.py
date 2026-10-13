"""The documents must quote the measurements exactly, and no TBD may survive next to a real measurement."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LATENCY = ROOT / "results" / "lambda_latency.json"
DOCS = [ROOT / "README.md", ROOT / "docs" / "cv_and_pitch.md", ROOT / "docs" / "guide" / "11_interview_project_qa.md"]


@pytest.mark.skipif(not LATENCY.exists(), reason="the latency has not been measured yet")
@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_no_tbd_is_left_once_the_latency_is_measured(doc):
    text = doc.read_text(encoding="utf-8")
    assert "[TBD" not in text and "**TBD" not in text, f"{doc.name} still has a TBD although results/lambda_latency.json exists"


@pytest.mark.skipif(not LATENCY.exists(), reason="the latency has not been measured yet")
def test_the_readme_quotes_the_measured_numbers_exactly():
    r = json.loads(LATENCY.read_text(encoding="utf-8"))
    s = r["server_side"]
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    warm = f"{s['duration_ms_warm']['median']:.1f} ms"
    memory = f"{s['max_memory_used_mb']['max']:.0f} MB"
    round_trip = f"{r['client_side']['score']['median'] / 1000:.2f} s median"
    for needle in (warm, memory, round_trip, f"{s['invocations']} invocations"):
        assert needle in readme, needle
    low, high = s["init_duration_ms"]["min"] / 1000, s["init_duration_ms"]["max"] / 1000
    assert f"{low:.1f} to {high:.1f} s" in readme, "the cold-start range must match the measurement"


def test_measurement_files_never_contain_a_url_or_an_account_number():
    for name in ("lambda_latency.json", "lambda_latency.md"):
        path = ROOT / "results" / name
        if path.exists():
            text = path.read_text(encoding="utf-8")
            assert "lambda-url" not in text and "amazonaws.com" not in text
            import re
            assert not re.search(r"(?<![\d.])\d{12}(?![\d.])", text)
