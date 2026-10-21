# Databricks notebook source
# MAGIC %md
# MAGIC # 01. Load the raw Freddie Mac files into Delta tables
# MAGIC
# MAGIC **What:** the raw Parquet files (everything as text, exactly as received) become two Delta tables, `raw_orig` and `raw_perf`.
# MAGIC **Why Delta:** a Delta table is Parquet files plus a transaction log. The log gives ACID writes (a write is all or nothing), schema enforcement
# MAGIC (a wrong shape is refused) and time travel (read an older version of the table).
# MAGIC
# MAGIC Run after uploading the 18 files `orig_*.parquet` and `perf_*.parquet` to the volume `raw` (see databricks/README.md).

# COMMAND ----------

import time

from pyspark.sql import functions as F

CATALOG = "workspace"      # change if your catalog has another name (Catalog explorer, left menu)
SCHEMA = "credit"
RAW = f"/Volumes/{CATALOG}/{SCHEMA}/raw"
YEARS_MAIN = [2008, 2012, 2016, 2019, 2022]
YEARS_FRESH = [2010, 2014, 2018, 2023]
ALL_YEARS = sorted(YEARS_MAIN + YEARS_FRESH)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"USE {CATALOG}.{SCHEMA}")

# COMMAND ----------

# One Delta table per kind of file. `source_year` remembers which file a row came from: a few loans sit in a neighbouring vintage
# year (one 2009 loan in the 2008 file), so the split between "main" and "fresh" vintages must follow the FILE, not loan_seq.
t0 = time.perf_counter()
for kind in ("orig", "perf"):
    parts = [spark.read.parquet(f"{RAW}/{kind}_{y}.parquet").withColumn("source_year", F.lit(y)) for y in ALL_YEARS]
    df = parts[0]
    for p in parts[1:]:
        df = df.unionByName(p)
    df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"raw_{kind}")
print(f"loaded in {time.perf_counter() - t0:.1f} s")

# COMMAND ----------

# The numbers the local pipeline reports (README, decision log): 450,000 loans, 24,674,152 monthly rows.
n_orig = spark.table("raw_orig").count()
n_loans = spark.table("raw_orig").select("loan_seq").distinct().count()
n_perf = spark.table("raw_perf").count()
print("raw_orig rows:", n_orig, "| distinct loans:", n_loans, "| raw_perf rows:", n_perf)
assert (n_orig, n_loans, n_perf) == (450_000, 450_000, 24_674_152), "the counts differ from the local pipeline: find out why before going on"
print("OK: same counts as the local pipeline")

# COMMAND ----------

# MAGIC %md
# MAGIC ## What Delta gives you (three small demonstrations, good to explain in an interview)

# COMMAND ----------

# 1. Time travel: every write is a numbered version, and an old version can be read.
display(spark.sql("DESCRIBE HISTORY raw_orig").select("version", "timestamp", "operation").limit(5))
print("rows at version 0:", spark.sql("SELECT count(*) FROM raw_orig VERSION AS OF 0").first()[0])

# COMMAND ----------

# 2. Schema enforcement: appending rows of the wrong shape is refused instead of silently corrupting the table.
try:
    spark.createDataFrame([("x", 1)], ["loan_seq", "not_a_column"]).write.format("delta").mode("append").saveAsTable("raw_orig")
    print("UNEXPECTED: the append was accepted")
except Exception as e:  # noqa: BLE001
    print("refused, as expected:", type(e).__name__)
print("rows still:", spark.table("raw_orig").count())
