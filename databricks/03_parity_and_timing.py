# Databricks notebook source
# MAGIC %md
# MAGIC # 03. Does Spark give the same answers as DuckDB? And how long does each take?
# MAGIC
# MAGIC Three checks, like the S3 + Athena test of the project:
# MAGIC 1. **The features tables** made by PySpark against the ones the DuckDB pipeline wrote (rows on one side only = a difference).
# MAGIC 2. **Six control queries** (five are the questions of `credit/cloud/lake.py`, one replaces the split question) whose DuckDB answers are in `expected_control_queries.json`.
# MAGIC 3. **A timing table**, with its limits written next to it.
# MAGIC
# MAGIC Upload to the volume `ref` first: `features.parquet`, `features_fresh.parquet` (from `data/interim/features*/`) and `expected_control_queries.json` (from `databricks/`).

# COMMAND ----------

import json

from pyspark.sql import functions as F

CATALOG, SCHEMA = "workspace", "credit"
REF = f"/Volumes/{CATALOG}/{SCHEMA}/ref"
spark.sql(f"USE {CATALOG}.{SCHEMA}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. The tables (every column except `split`, see below)

# COMMAND ----------

def norm(df, cols):
    """Every column as text, doubles rounded to 6 decimals: the two engines may differ in the last bits of a float, never in a meaning."""
    types = dict(df.dtypes)
    return df.select(*[(F.round(F.col(c), 6) if types[c] in ("double", "float") else F.col(c)).cast("string").alias(c) for c in cols])


def compare(mine_table, ref_file):
    mine, ref = spark.table(mine_table), spark.read.parquet(f"{REF}/{ref_file}")
    cols = [c for c in ref.columns if c != "split"]
    a, b = norm(mine, cols), norm(ref, cols)
    only_mine, only_ref = a.exceptAll(b).count(), b.exceptAll(a).count()
    print(f"{mine_table}: spark {mine.count()} rows, duckdb {ref.count()} rows | only in spark: {only_mine} | only in duckdb: {only_ref}")
    return only_mine == 0 and only_ref == 0


ok_dev = compare("features_dev", "features.parquet")
ok_fresh = compare("features_fresh", "features_fresh.parquet")
print("TABLES IDENTICAL (except split):", ok_dev and ok_fresh)

# COMMAND ----------

# MAGIC %md
# MAGIC ### The split, and why it is the one difference
# MAGIC DuckDB's `hash()` and Spark's `hash()` are two different functions, so the same loan can land in another split. The split is a hash of the loan id
# MAGIC and a fixed seed: reproducible **inside one engine**, not portable **between engines**. The proportions must still be about 60 / 10 / 15 / 15.

# COMMAND ----------

display(spark.sql("""
  SELECT split, count(*) AS loans, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
  FROM features_dev WHERE vintage_year <= 2018 GROUP BY split ORDER BY split"""))

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. The control queries

# COMMAND ----------

expected = json.loads(open(f"{REF}/expected_control_queries.json", encoding="utf-8").read())


def same(a, b):
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) <= 1e-6 + 1e-9 * abs(float(b))
    except (TypeError, ValueError):
        return False


all_ok = True
for name, spec in expected.items():
    got = [[None if v is None else str(v) for v in r] for r in spark.sql(spec["sql"]).collect()]
    ok = len(got) == len(spec["rows"]) and all(len(g) == len(e) and all(same(x, y) for x, y in zip(g, e, strict=True)) for g, e in zip(got, spec["rows"], strict=True))
    all_ok &= ok
    print(("PASS " if ok else "FAIL ") + name, "" if ok else f"\n  spark:  {got[:3]}\n  duckdb: {spec['rows'][:3]}")
print("ALL CONTROL QUERIES IDENTICAL:", all_ok)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Timing
# MAGIC Fill `DUCKDB` from `results/engine_timing_duckdb.json` (median of 3 runs, measured by `scripts/time_duckdb_pipeline.py`). Spark: the numbers of notebook 02
# MAGIC (the last run of notebook 02, kept in the table `timings`). **Read this with care:** the machines differ (a 32-thread laptop against a free serverless service),
# MAGIC Spark includes writing Delta tables while DuckDB measured in memory, and 450,000 loans is small. It is a sanity check, not a benchmark.

# COMMAND ----------

DUCKDB = {"stage_main": 0.67, "features_main": 0.3, "stage_fresh": 0.51, "features_fresh": 0.25, "total": 1.77}   # seconds, median of 3
spark_last = {r["step"]: r["seconds"] for r in spark.table("timings").collect()}   # notebook 02 rewrites this table at every run
rows = [("DuckDB (laptop, in memory)", 450000, DUCKDB["total"]), ("PySpark (Databricks Free, serverless, Delta)", 450000, spark_last.get("total"))]
display(spark.createDataFrame(rows, ["engine", "input_loans", "seconds"]))
print("At this size one machine wins. Spark pays off when the data no longer fits on one machine, or when many people share one cluster.")
