"""Time the DuckDB version of "raw Parquet -> features tables" (staging and features, main and fresh vintages), 3 runs, and write the median.

    python scripts/time_duckdb_pipeline.py          # writes results/engine_timing_duckdb.json

It uses the real functions of the pipeline (credit/freddie/staging.py, features.py, fresh.py) in memory, with no data written, so it measures the
transformations and not the disk. The PySpark notebooks of databricks/ measure the same steps; the two numbers are a sanity comparison, not a
benchmark: the machines are different (a laptop and a free serverless service).
"""
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from credit.freddie import features, fresh, staging  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "interim" / "raw"
MAIN_YEARS = (2008, 2012, 2016, 2019, 2022)
FRESH_YEARS = (2010, 2014, 2018, 2023)
RUNS = 3
OUT = ROOT / "results" / "engine_timing_duckdb.json"


def _stage(con: duckdb.DuckDBPyConnection, years: tuple[int, ...]) -> None:
    for kind, fn, prefix in (("orig", staging.stg_orig_sql, "orig"), ("label", staging.stg_label_sql, "perf")):
        parts = " UNION ALL BY NAME ".join(f"SELECT * FROM ({fn(RAW / f'{prefix}_{y}.parquet')})" for y in years)
        con.execute(f"CREATE OR REPLACE TABLE stg_{kind} AS {parts}")


def one_run() -> dict:
    con = duckdb.connect()
    t = time.perf_counter()
    _stage(con, MAIN_YEARS)
    t_stage_main = time.perf_counter() - t
    t = time.perf_counter()
    rows_main = features.build(con) and con.execute("SELECT count(*) FROM features").fetchone()[0]
    t_feat_main = time.perf_counter() - t
    t = time.perf_counter()
    _stage(con, FRESH_YEARS)
    t_stage_fresh = time.perf_counter() - t
    t = time.perf_counter()
    fresh.build_fresh(con)
    rows_fresh = con.execute("SELECT count(*) FROM fresh").fetchone()[0]
    t_feat_fresh = time.perf_counter() - t
    con.close()
    return {"stage_main": t_stage_main, "features_main": t_feat_main, "stage_fresh": t_stage_fresh, "features_fresh": t_feat_fresh,
            "total": t_stage_main + t_feat_main + t_stage_fresh + t_feat_fresh, "rows_main": rows_main, "rows_fresh": rows_fresh}


def main() -> None:
    runs = [one_run() for _ in range(RUNS)]
    median = {k: round(statistics.median(r[k] for r in runs), 2) for k in runs[0] if k.startswith(("stage", "features", "total"))}
    result = {"engine": "DuckDB " + duckdb.__version__, "machine": f"{platform.processor() or platform.machine()}, {os.cpu_count()} logical cores",
              "runs": RUNS, "median_seconds": median, "all_totals": [round(r["total"], 2) for r in runs],
              "rows_features_main": runs[0]["rows_main"], "rows_features_fresh": runs[0]["rows_fresh"], "input_rows": 450000}
    OUT.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
