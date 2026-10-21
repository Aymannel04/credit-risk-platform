"""The dbt project (dbt/credit_dbt) is the same logic as the Python pipeline, written as dbt models with tests.

These tests need no data and no dbt: they check that the project is complete and that its constants cannot drift away from the Python code.
The real proof (the dbt tables are identical to the pipeline's Parquet files) is the `parity_*` tests, run by `dbt build` on the owner's machine.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from credit.freddie import features, staging

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt" / "credit_dbt"
MODELS = {"stg_orig", "stg_label", "stg_orig_fresh", "stg_label_fresh", "mart_loan_features", "mart_loan_features_fresh", "mart_default_rates"}


def _yaml(path: Path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_every_model_has_a_sql_file_and_a_description():
    described = {m["name"] for f in PROJECT.glob("models/*/schema.yml") for m in _yaml(f)["models"]}
    files = {p.stem for p in PROJECT.glob("models/*/*.sql")}
    assert files == MODELS == described


def test_every_model_has_at_least_one_test_or_parity_proof():
    tested = {m["name"] for f in PROJECT.glob("models/*/schema.yml") for m in _yaml(f)["models"]
              if any(c.get("data_tests") for c in m.get("columns", []))}
    assert MODELS - {"mart_default_rates"} <= tested  # the rates table is covered by range tests on its columns, checked just below
    rates = next(m for m in _yaml(PROJECT / "models/marts/schema.yml")["models"] if m["name"] == "mart_default_rates")
    assert all(c.get("data_tests") for c in rates["columns"])


def test_the_constants_equal_the_python_pipeline():
    v = _yaml(PROJECT / "dbt_project.yml")["vars"]
    assert v["window_months"] == staging.WINDOW_MONTHS
    assert v["dev_max_vintage"] == features.DEV_MAX_VINTAGE
    assert (v["oot_1_min"], v["oot_1_max"]) == features.OOT_1_RANGE
    assert v["oot_2_min"] == features.OOT_2_MIN
    assert v["split_seed"] == features.SPLIT_SEED
    assert v["short_term_months"] == features.SHORT_TERM_MONTHS
    assert len(v["years"]) + len(v["fresh_years"]) == 9 and not set(v["years"]) & set(v["fresh_years"])


def test_the_feature_columns_equal_the_python_lists_in_the_same_order():
    macro = (PROJECT / "macros" / "staging_helpers.sql").read_text(encoding="utf-8")
    block = re.search(r"macro feature_columns\(\) -%\}(.*?)\{%-", macro, re.S).group(1)
    assert [c.strip() for c in block.split(",")] == features.META + features.FEATURES + features.LABELS


def test_the_existing_data_is_never_inside_the_project_and_nothing_secret_is_in_it():
    sources = [p for p in PROJECT.rglob("*") if p.is_file() and not {"target", "logs", "dbt_packages"} & set(p.relative_to(PROJECT).parts)]
    assert {p.suffix for p in sources} <= {".sql", ".yml"}  # no data file, no key file (the build output in target/ is ignored by git)
    text = "\n".join(p.read_text(encoding="utf-8") for p in sources if p.suffix == ".yml")
    assert not re.search(r"(token|password|secret)\s*:|dapi[0-9a-f]{8}", text, re.I)  # a key written as `name: value`, or a Databricks token
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "dbt/credit_dbt/target/" in ignore


def test_the_parity_tests_exist_for_both_sets_of_vintages():
    tests = {p.stem for p in (PROJECT / "tests").glob("*.sql")}
    assert {"parity_features_vs_existing_pipeline", "parity_staging_vs_existing_pipeline", "parity_fresh_vs_existing_pipeline"} <= tests


@pytest.mark.skipif(shutil.which("dbt") is None and not (Path(sys.prefix) / "Scripts" / "dbt.exe").exists(), reason="dbt is not installed (it is optional)")
def test_dbt_can_parse_the_project():
    exe = shutil.which("dbt") or str(Path(sys.prefix) / "Scripts" / "dbt.exe")
    done = subprocess.run([exe, "parse", "--profiles-dir", "."], cwd=PROJECT, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout[-800:] + done.stderr[-800:]
