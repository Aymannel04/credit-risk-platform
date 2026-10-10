"""The pipeline steps as plain functions (no Dagster inside): easy to test, and Dagster only calls them in order.

Every step wraps code that already existed and was verified; the pipeline adds ORDER, SKIP-IF-UP-TO-DATE and CHECKS,
never new maths. Module paths are read at call time (not copied) so tests can point them at a temporary folder.

The staging report of a fresh vintage also contains default counts, which are locked until the exam: this module only
ever returns the structural counts (loans, exclusions, observability).
"""
import json
from pathlib import Path

from credit.freddie import features as ft
from credit.freddie import fresh, layout, load, staging
from credit.serving import export, model_file
from pipeline.freshness import is_stale

DEV_YEARS = [2008, 2012, 2016, 2019, 2022]  # development vintages (train / calibration / validation / test)
FRESH_YEARS = [2010, 2014, 2018, 2023]  # the v2 exam vintages: built structurally, labels stay locked
ALL_YEARS = sorted(DEV_YEARS + FRESH_YEARS)
STRUCTURAL_KEYS = ("loans", "relief_refi", "seasoned_or_modified", "not_observable_24m")  # never the default counts


def _code(*modules) -> list[Path]:
    return [Path(m.__file__) for m in modules]


def raw_step(years: list[int] = ALL_YEARS) -> dict:
    """zip -> raw Parquet (all text). One year is rebuilt only if its Parquet files are missing or older than the zip or the code."""
    out = {}
    for y in years:
        outputs = [load.OUT_DIR / f"orig_{y}.parquet", load.OUT_DIR / f"perf_{y}.parquet"]
        inputs = [load.RAW_DIR / f"sample_{y}.zip", *_code(load, layout)]
        if is_stale(outputs, inputs):
            counts = load.load_year(y)
            out[y] = {"status": "rebuilt", "orig_rows": counts["orig"], "perf_rows": counts["perf"]}
        else:
            out[y] = {"status": "reused"}
    return out


def staging_step(years: list[int], out_dir: Path) -> dict:
    """raw Parquet -> typed tables + labels + data checks (a failed check raises DataCheckError and stops the chain)."""
    out = {}
    for y in years:
        outputs = [out_dir / f"stg_orig_{y}.parquet", out_dir / f"stg_label_{y}.parquet", out_dir / f"report_{y}.json"]
        inputs = [staging.RAW_DIR / f"orig_{y}.parquet", staging.RAW_DIR / f"perf_{y}.parquet", *_code(staging)]
        status = "rebuilt"
        if is_stale(outputs, inputs):
            staging.stage_year(y, raw_dir=staging.RAW_DIR, out_dir=out_dir)  # raw_dir passed explicitly: its default is frozen at import time
        else:
            status = "reused"
        report = json.loads((out_dir / f"report_{y}.json").read_text(encoding="utf-8"))
        out[y] = {"status": status, **{k: report[k] for k in STRUCTURAL_KEYS}}
    return out


def features_step() -> dict:
    """staged development vintages -> the features table (exclusions, splits, rate spread, feature checks)."""
    target = ft.OUT_DIR / "features.parquet"
    stg_files = sorted(ft.STG_DIR.glob("stg_*_*.parquet"))
    if not stg_files:
        raise FileNotFoundError(f"no staged files in {ft.STG_DIR}")
    if is_stale([target, ft.OUT_DIR / "report.json"], [*stg_files, *_code(ft)]):
        _run_main(ft.main)
        status = "rebuilt"
    else:
        status = "reused"
    return {"status": status, "report": json.loads((ft.OUT_DIR / "report.json").read_text(encoding="utf-8"))}


def fresh_step() -> dict:
    """staged fresh vintages -> the fresh features table (structure only; labels stay locked)."""
    stg_files = sorted(fresh.STG_FRESH.glob("stg_*_*.parquet"))
    if not stg_files:
        raise FileNotFoundError(f"no staged fresh files in {fresh.STG_FRESH}")
    if is_stale([fresh.FRESH_PATH, fresh.OUT_DIR / "report.json"], [*stg_files, *_code(fresh, ft)]):
        _run_main(fresh.main)
        status = "rebuilt"
    else:
        status = "reused"
    return {"status": status, "waterfall": json.loads((fresh.OUT_DIR / "report.json").read_text(encoding="utf-8"))["waterfall"]}


def model_step() -> dict:
    """development features -> the JSON scorecard v2 (fit on all development rows, as in the adopted model)."""
    from credit.models import era_review, reasons, scorecard, v2_exam

    root = export.ROOT
    inputs = [ft.OUT_DIR / "features.parquet", *_code(export, model_file, scorecard, v2_exam, reasons, era_review),
              *sorted((root / "config").glob("*.yaml"))]
    if is_stale([export.MODEL_PATH], inputs):
        export.main()
        status = "rebuilt"
    else:
        status = "reused"
    model = model_file.load_model(export.MODEL_PATH)
    return {"status": status, "model_id": model["model_id"], "bytes": export.MODEL_PATH.stat().st_size}


def _run_main(fn) -> None:
    """The layer scripts end with SystemExit when their own checks fail; turn that into a normal error for the orchestrator."""
    try:
        fn()
    except SystemExit as e:
        raise RuntimeError(f"{fn.__module__}: {e}") from e
