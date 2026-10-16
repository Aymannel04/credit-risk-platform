"""Pipeline tests: the skip rule, the shape of the graph, and raw -> staging -> features on tiny made-up loans.

No Freddie Mac data is needed: the module paths are pointed at a temporary folder.
"""
import json
import os
import zipfile
from pathlib import Path

import duckdb
import pytest

from credit.freddie import features as ft
from credit.freddie import fresh, load, staging
from credit.freddie.layout import ORIGINATION_COLUMNS, PERFORMANCE_COLUMNS
from credit.serving.export import MODEL_PATH
from pipeline import checks, steps
from pipeline.definitions import defs
from pipeline.freshness import is_stale


def _touch(path: Path, when: float) -> Path:
    path.write_text("x", encoding="utf-8")
    os.utime(path, (when, when))
    return path


# ---------- the skip rule ----------

def test_missing_output_is_stale(tmp_path):
    src = _touch(tmp_path / "in", 100)
    assert is_stale([tmp_path / "out"], [src])
    assert is_stale([], [src])


def test_up_to_date_output_is_not_stale(tmp_path):
    src, out = _touch(tmp_path / "in", 100), _touch(tmp_path / "out", 200)
    assert not is_stale([out], [src])


def test_newer_input_makes_it_stale(tmp_path):
    src, out = _touch(tmp_path / "in", 300), _touch(tmp_path / "out", 200)
    assert is_stale([out], [src])


def test_one_old_output_among_several_is_enough(tmp_path):
    src = _touch(tmp_path / "in", 150)
    new, old = _touch(tmp_path / "new", 200), _touch(tmp_path / "old", 100)
    assert is_stale([new, old], [src])


def test_full_refresh_forces_rebuild(tmp_path, monkeypatch):
    src, out = _touch(tmp_path / "in", 100), _touch(tmp_path / "out", 200)
    monkeypatch.setenv("PIPELINE_FULL", "1")
    assert is_stale([out], [src])


def test_missing_input_is_an_error_not_a_silent_skip(tmp_path):
    out = _touch(tmp_path / "out", 200)
    with pytest.raises(FileNotFoundError):
        is_stale([out], [tmp_path / "nope"])


# ---------- the shape of the graph ----------

def test_graph_dependencies():
    g = defs.resolve_asset_graph()
    parents = {k.to_user_string(): sorted(p.to_user_string() for p in g.get(k).parent_keys) for k in g.get_all_asset_keys()}
    assert parents == {
        "freddie_zips": [], "raw_parquet": ["freddie_zips"], "staging_dev": ["raw_parquet"], "staging_fresh": ["raw_parquet"],
        "features_dev": ["staging_dev"], "features_fresh": ["staging_fresh"], "scorecard_v2": ["features_dev"],
        "data_lake": ["features_dev", "features_fresh", "raw_parquet"],
        "monitoring_report": ["features_dev", "features_fresh", "scorecard_v2"],
    }


def test_the_model_never_depends_on_the_fresh_vintages():
    g = defs.resolve_asset_graph()
    by_name = {k.to_user_string(): k for k in g.get_all_asset_keys()}
    ancestors, todo = set(), ["scorecard_v2"]
    while todo:
        for parent in g.get(by_name[todo.pop()]).parent_keys:
            if parent.to_user_string() not in ancestors:
                ancestors.add(parent.to_user_string())
                todo.append(parent.to_user_string())
    assert ancestors == {"features_dev", "staging_dev", "raw_parquet", "freddie_zips"}


def test_every_executable_asset_has_a_blocking_check():
    g = defs.resolve_asset_graph()
    checked = {ck.asset_key.to_user_string() for ck in g.asset_check_keys}
    assert checked == {"raw_parquet", "staging_dev", "staging_fresh", "features_dev", "features_fresh", "data_lake", "scorecard_v2", "monitoring_report"}
    for ck in g.asset_check_keys:
        assert g.get_check_spec(ck).blocking, ck


def test_pipeline_metadata_never_carries_default_counts():
    assert not any("default" in k for k in steps.STRUCTURAL_KEYS)
    assert not set(steps.DEV_YEARS) & set(steps.FRESH_YEARS)


# ---------- raw -> staging -> features on made-up loans ----------

def _loan_rows(n: int):
    orig_rows, perf_rows = [], []
    for i in range(1, n + 1):
        seq = f"F16Q1{i:07d}"
        o = dict.fromkeys(ORIGINATION_COLUMNS, "")
        o.update(
            credit_score=str(640 + i), first_payment_date="201603", first_time_homebuyer="N", maturity_date="204602",
            mi_pct="0", n_units="1", occupancy="P", cltv="80", dti="30", orig_upb="200000", ltv="80", int_rate=f"{3 + i % 5}.25",
            channel="R", ppm_flag="N", amort_type="FRM", state="CA", property_type="SF", zip3="900", loan_seq=seq,
            purpose="P", orig_term="360", n_borrowers="2", seller_name="OTHER", super_conforming="N", relief_refi="N",
            io_indicator="N",
        )
        orig_rows.append("|".join(o[c] for c in ORIGINATION_COLUMNS))
        for age in range(0, 31):
            p = dict.fromkeys(PERFORMANCE_COLUMNS, "")
            p.update(loan_seq=seq, report_period=f"2016{age % 12 + 1:02d}", loan_age=str(age), delinq_status="00")
            perf_rows.append("|".join(p[c] for c in PERFORMANCE_COLUMNS))
    return orig_rows, perf_rows


@pytest.fixture()
def lanes(tmp_path, monkeypatch):
    """Point every layer at a temporary folder and put one tiny zip (2016, 60 loans) in the raw folder."""
    raw_zips, raw_pq, stg, feats = (tmp_path / d for d in ("zips", "raw", "stg", "features"))
    raw_zips.mkdir()
    orig, perf = _loan_rows(60)
    with zipfile.ZipFile(raw_zips / "sample_2016.zip", "w") as z:
        z.writestr("sample_orig_2016.txt", "\n".join(orig) + "\n")
        z.writestr("sample_perf_2016.txt", "\n".join(perf) + "\n")
    monkeypatch.setattr(load, "RAW_DIR", raw_zips)
    monkeypatch.setattr(load, "OUT_DIR", raw_pq)
    monkeypatch.setattr(load, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(staging, "RAW_DIR", raw_pq)
    monkeypatch.setattr(ft, "STG_DIR", stg)
    monkeypatch.setattr(ft, "OUT_DIR", feats)
    monkeypatch.delenv("PIPELINE_FULL", raising=False)
    return {"zips": raw_zips, "raw": raw_pq, "stg": stg, "features": feats}


def test_chain_builds_then_reuses_then_rebuilds_when_input_changes(lanes):
    first = steps.raw_step([2016])
    assert first[2016]["status"] == "rebuilt" and first[2016]["orig_rows"] == 60 and first[2016]["perf_rows"] == 60 * 31
    assert steps.raw_step([2016])[2016]["status"] == "reused"

    st = steps.staging_step([2016], lanes["stg"])
    assert st[2016]["status"] == "rebuilt" and st[2016]["loans"] == 60
    assert "defaults_b" not in st[2016] and "default" not in " ".join(st[2016])
    assert steps.staging_step([2016], lanes["stg"])[2016]["status"] == "reused"

    f = steps.features_step()
    assert f["status"] == "rebuilt"
    assert steps.features_step()["status"] == "reused"
    assert checks.check_features(lanes["features"] / "features.parquet") == []
    assert checks.check_staging(lanes["stg"], [2016]) == []
    assert checks.check_raw(lanes["raw"], [2016]) == []

    # a newer zip invalidates the whole downstream chain, step by step
    zip_path = lanes["zips"] / "sample_2016.zip"
    later = zip_path.stat().st_mtime + 1000
    os.utime(zip_path, (later, later))
    assert steps.raw_step([2016])[2016]["status"] == "rebuilt"
    assert steps.staging_step([2016], lanes["stg"])[2016]["status"] == "rebuilt"
    assert steps.features_step()["status"] == "rebuilt"


def test_full_refresh_rebuilds_everything(lanes, monkeypatch):
    steps.raw_step([2016])
    monkeypatch.setenv("PIPELINE_FULL", "1")
    assert steps.raw_step([2016])[2016]["status"] == "rebuilt"


def test_a_failed_data_check_stops_the_step(lanes):
    steps.raw_step([2016])
    # break the data: duplicate a loan in the raw origination file -> primary key check must fail
    f = lanes["raw"] / "orig_2016.parquet"
    duckdb.sql(f"COPY (SELECT * FROM read_parquet('{f.as_posix()}') UNION ALL SELECT * FROM read_parquet('{f.as_posix()}') LIMIT 61) "
               f"TO '{(lanes['raw'] / 'x.parquet').as_posix()}' (FORMAT PARQUET)")
    (lanes["raw"] / "x.parquet").replace(f)
    with pytest.raises(staging.DataCheckError):
        steps.staging_step([2016], lanes["stg"])
    assert not (lanes["stg"] / "stg_orig_2016.parquet").exists()  # nothing half-written for the next step to pick up


def test_check_staging_catches_a_file_that_was_damaged_after_the_build(lanes):
    steps.raw_step([2016])
    steps.staging_step([2016], lanes["stg"])
    target = lanes["stg"] / "stg_orig_2016.parquet"
    duckdb.sql(f"COPY (SELECT * REPLACE (900.0 AS dti) FROM read_parquet('{target.as_posix()}')) "
               f"TO '{(lanes['stg'] / 'y.parquet').as_posix()}' (FORMAT PARQUET)")
    (lanes["stg"] / "y.parquet").replace(target)
    assert any("dti" in p for p in checks.check_staging(lanes["stg"], [2016]))


def test_check_features_reports_missing_file(tmp_path):
    assert checks.check_features(tmp_path / "nope.parquet") == ["missing nope.parquet"]
    assert checks.check_fresh(tmp_path / "nope.parquet") == ["missing nope.parquet"]


def test_fresh_step_wiring_uses_the_fresh_folder_only(lanes, monkeypatch):
    # the fresh layer reads fresh.STG_FRESH, never the development staging folder
    other = lanes["stg"].parent / "stg_fresh"
    monkeypatch.setattr(fresh, "STG_FRESH", other)
    monkeypatch.setattr(fresh, "OUT_DIR", lanes["stg"].parent / "features_fresh")
    monkeypatch.setattr(fresh, "FRESH_PATH", lanes["stg"].parent / "features_fresh" / "f.parquet")
    other.mkdir()
    with pytest.raises(FileNotFoundError):
        steps.fresh_step()  # no staged fresh files there: stops instead of reading the development files


# ---------- the model check ----------

def test_committed_model_passes_the_golden_loan_check():
    assert checks.check_model(MODEL_PATH) == []


def test_model_check_fails_when_a_point_changes(tmp_path):
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    model["features"]["credit_score"]["points"] = [p + 15 for p in model["features"]["credit_score"]["points"]]
    bad = tmp_path / "m.json"
    bad.write_text(json.dumps(model), encoding="utf-8")
    problems = checks.check_model(bad)
    assert problems and "golden" in problems[0]


def test_model_check_fails_on_a_broken_file(tmp_path):
    bad = tmp_path / "m.json"
    bad.write_text("{}", encoding="utf-8")
    assert checks.check_model(bad)[0].startswith("model file invalid")


# ---------- the monitoring check ----------

def _report_copy(tmp_path, **edits):
    from credit.monitoring import report

    data = json.loads((report.RESULTS / "monitoring_report.json").read_text(encoding="utf-8"))
    for dotted, value in edits.items():
        node = data
        *path, last = dotted.split(".")
        for key in path:
            node = node[key]
        node[last] = value
    out = tmp_path / "monitoring_report.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


def test_monitoring_check_passes_on_the_committed_report():
    from credit.monitoring import report

    assert checks.check_monitoring(report.RESULTS / "monitoring_report.json", MODEL_PATH) == []


def test_monitoring_check_fails_when_the_monitors_fail_their_self_test(tmp_path):
    assert any("false alarm" in p for p in checks.check_monitoring(_report_copy(tmp_path, **{"part_b.R_M1_control_clean": False}), MODEL_PATH))
    assert any("missed" in p for p in checks.check_monitoring(_report_copy(tmp_path, **{"part_b.R_M2_enough_alerts": False}), MODEL_PATH))
    assert any("Gini" in p for p in checks.check_monitoring(_report_copy(tmp_path, **{"part_c_verdict.R_C2_gini_unchanged": False}), MODEL_PATH))


def test_monitoring_check_fails_for_a_report_about_another_model(tmp_path):
    problems = checks.check_monitoring(_report_copy(tmp_path, model_id="deadbeef0000"), MODEL_PATH)
    assert any("not the current model" in p for p in problems)


def test_monitoring_check_reports_a_missing_file(tmp_path):
    assert checks.check_monitoring(tmp_path / "nope.json", MODEL_PATH) == ["missing nope.json"]


# ---------- the S3 lake step is opt-in and stays offline by default ----------

def test_lake_step_is_skipped_and_touches_no_cloud_code_unless_asked(monkeypatch):
    monkeypatch.delenv("CREDIT_LAKE", raising=False)
    monkeypatch.setattr("builtins.__import__", _forbid_boto3(__import__))
    r = steps.lake_step()
    assert r["status"].startswith("skipped") and r["files"] == 0
    assert checks.check_lake(False) == []


def test_lake_step_switch_reads_the_environment(monkeypatch):
    monkeypatch.setenv("CREDIT_LAKE", "1")
    assert steps.lake_enabled()
    monkeypatch.setenv("CREDIT_LAKE", "0")
    assert not steps.lake_enabled()


def _forbid_boto3(real_import):
    def guarded(name, *args, **kwargs):
        if name.split(".")[0] in ("boto3", "botocore"):
            raise AssertionError("the offline pipeline must not load AWS libraries")
        return real_import(name, *args, **kwargs)
    return guarded
