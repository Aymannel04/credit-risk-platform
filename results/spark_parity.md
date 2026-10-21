# PySpark on Databricks (Delta) against the DuckDB pipeline

Run by the owner on 2026-10-21, Databricks Free Edition, serverless compute, notebooks `databricks/01` to `03`. Outputs read from the notebook screens.

| Check | Result |
|---|---|
| Raw load into Delta | 450,000 loans, 24,674,152 monthly rows (same as the local pipeline); an append of the wrong shape was refused (`AnalysisException`), the table kept 450,000 rows |
| Features table, main vintages | 229,419 rows in Spark and in DuckDB; **0 rows only in Spark, 0 only in DuckDB** (every column except `split`) |
| Features table, fresh vintages | 177,081 rows in both; **0 and 0** |
| Control queries (6, answers computed by DuckDB) | **6 of 6 identical** (`dev_totals`, `dev_vintage_sums`, `fresh_structure`, `raw_orig_loans`, `raw_perf_rows`, `raw_perf_loans`) |
| `split` | not comparable by design (DuckDB's `hash()` is not Spark's); proportions in Spark: train 59.8%, calibration 10.2%, validation 14.9%, test in time 15.1% (target 60 / 10 / 15 / 15) |

## Timing (450,000 loans in; staging and features, main and fresh vintages)

| Engine | Seconds | How |
|---|---|---|
| DuckDB 1.5.6, laptop with 32 logical cores, in memory | **1.77** | median of 3 runs (1.78, 1.77, 1.67), `scripts/time_duckdb_pipeline.py`, `results/engine_timing_duckdb.json` |
| PySpark, Databricks Free Edition serverless, writing Delta tables | **35.38** | one run (staging 12.61 + features 6.82 for the main vintages; 9.09 + 5.46 for the fresh ones) |

**How to read it.** At this size one machine wins by a factor of about 20. The comparison is a sanity check, not a benchmark: different machines, Spark includes writing Delta tables and a possible cold start, and Spark was run once. Spark is worth its cost when the data no longer fits on one machine or when many people share one cluster.
