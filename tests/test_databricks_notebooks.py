"""The Databricks notebooks (databricks/*.py) cannot run here (no Spark), so these tests check what can be checked: they parse, they follow the
notebook format, their constants equal the Python pipeline's, and they hold no secret. The real proof is notebook 03 on the owner's account."""
import ast
import json
import re
from pathlib import Path

import pytest

from credit.freddie import features, staging

DIR = Path(__file__).resolve().parents[1] / "databricks"
NOTEBOOKS = sorted(DIR.glob("0*.py"))


def test_there_are_three_notebooks_in_order():
    assert [p.name for p in NOTEBOOKS] == ["01_load_delta.py", "02_pyspark_transform.py", "03_parity_and_timing.py"]


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.name)
def test_each_notebook_parses_and_has_the_databricks_format(path):
    text = path.read_text(encoding="utf-8")
    ast.parse(text)
    assert text.startswith("# Databricks notebook source\n")
    assert "# COMMAND ----------" in text


def _consts(path: Path) -> dict:
    out = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            try:
                out[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass
    return out


def test_the_constants_of_the_notebook_equal_the_python_pipeline():
    c = _consts(DIR / "02_pyspark_transform.py")
    assert c["WINDOW_MONTHS"] == staging.WINDOW_MONTHS
    assert c["DEV_MAX_VINTAGE"] == features.DEV_MAX_VINTAGE
    assert tuple(c["OOT_1"]) == features.OOT_1_RANGE
    assert c["OOT_2_MIN"] == features.OOT_2_MIN
    assert c["SPLIT_SEED"] == features.SPLIT_SEED
    assert c["SHORT_TERM_MONTHS"] == features.SHORT_TERM_MONTHS
    assert c["META"] == features.META and c["LABELS"] == features.LABELS
    assert c["NUMERIC"] + c["CATEGORICAL"] == features.FEATURES


def test_the_main_and_fresh_years_are_the_ones_of_the_pipeline_and_do_not_overlap():
    c = _consts(DIR / "02_pyspark_transform.py")
    assert c["YEARS_MAIN"] == [2008, 2012, 2016, 2019, 2022] and c["YEARS_FRESH"] == [2010, 2014, 2018, 2023]
    assert not set(c["YEARS_MAIN"]) & set(c["YEARS_FRESH"])


def test_expected_answers_cover_six_questions_and_none_uses_the_split():
    expected = json.loads((DIR / "expected_control_queries.json").read_text(encoding="utf-8"))
    assert list(expected) == ["dev_totals", "dev_vintage_sums", "fresh_structure", "raw_orig_loans", "raw_perf_rows", "raw_perf_loans"]
    assert not any("split" in v["sql"] for v in expected.values())  # DuckDB's hash() is not Spark's
    assert expected["raw_orig_loans"]["rows"] == [["450000", "450000"]]
    assert expected["raw_perf_rows"]["rows"] == [["24674152"]]
    for name in ("fresh_structure",):
        assert not re.search(r"default|label|observable", expected[name]["sql"])  # fresh labels never appear in a control query


def test_no_secret_in_the_notebooks():
    text = "\n".join(p.read_text(encoding="utf-8") for p in DIR.iterdir() if p.is_file())
    assert not re.search(r"dapi[0-9a-f]{8}|(token|password)\s*[=:]\s*[\"']\w", text, re.I)
