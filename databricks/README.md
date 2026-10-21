# Databricks: the same transformations in PySpark on Delta tables

Three notebooks redo the cleaning and the features of the pipeline with **PySpark on Delta tables** (Databricks Free Edition, serverless), and prove
the results are the same as the DuckDB pipeline's. They run on the owner's Databricks account; nothing here is run by CI. They have been run once, successfully (see Result).

| Notebook | What it does |
|---|---|
| `01_load_delta.py` | the 18 raw Parquet files become 2 Delta tables (`raw_orig`, `raw_perf`); checks 450,000 loans and 24,674,152 monthly rows; shows time travel and schema enforcement |
| `02_pyspark_transform.py` | staging and features in PySpark (main and fresh vintages), written as Delta tables, with a timer per step |
| `03_parity_and_timing.py` | tables compared with the DuckDB pipeline's (rows on one side only), 6 control queries compared with DuckDB's answers, the timing table |

## Set up (once, about 15 minutes; no credit card, nothing to pay)

1. Create an account on **Databricks Free Edition** (databricks.com, "Free Edition"). Never share the password or a token with anyone, including an assistant.
2. In **Catalog**, create the schema `credit` in your catalog (named `workspace` by default; if yours differs, change `CATALOG` at the top of each notebook).
3. In the schema `credit`, create two **volumes**: `raw` and `ref`.
4. Upload the files (drag and drop in the volume page). They stay private in your workspace.
   - volume `raw`: the 18 files of `data/interim/raw/` (`orig_*.parquet`, `perf_*.parquet`, about 245 MB)
   - volume `ref`: `data/interim/features/features.parquet`, `data/interim/features_fresh/features_fresh.parquet` and `databricks/expected_control_queries.json`
5. Import the three `.py` files (Workspace, Import, file). Databricks reads the `# COMMAND ----------` lines as cells.
6. Run `01`, then `02`, then `03` (serverless compute; the first cell attaches it).

## What to expect and what cannot be identical

- Counts, vintages, labels and every feature must be identical (the comparison ignores only the `split` column).
- **`split` differs:** it is `hash(loan_seq || seed) % 100`, and DuckDB's `hash()` is not Spark's `hash()`. Reproducible inside one engine, not portable between engines. The proportions must still be about 60 / 10 / 15 / 15.
- Spark serverless runs in **ANSI mode**: a bad cast raises an error instead of giving NULL, so every cast is `try_cast` / `try_to_date`.
- DuckDB's `quantile_cont(...) OVER (...)` became `groupBy` + `percentile` + a null-safe join.

## Result (2026-10-21, run by the owner)

Tables identical (0 rows on one side only, both sets), 6 of 6 control queries identical, `split` proportions 59.8 / 10.2 / 14.9 / 15.1. Spark 35.38 s (one run) against DuckDB 1.77 s (median of 3). Details and limits: `results/spark_parity.md`.

## Honest limits

- 450,000 loans fit on one laptop: DuckDB is expected to be faster (it was: 1.77 s, median of 3, `results/engine_timing_duckdb.json`). The two timings come from different machines and Spark includes writing Delta tables; it is a sanity check, not a benchmark.
- The notebooks cannot be run in the repository's tests (no Spark there). `tests/test_databricks_notebooks.py` checks they parse, that their constants equal the Python pipeline's and that they hold no secret.
