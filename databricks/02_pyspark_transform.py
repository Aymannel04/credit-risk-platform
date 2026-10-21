# Databricks notebook source
# MAGIC %md
# MAGIC # 02. The same cleaning and features, in PySpark
# MAGIC
# MAGIC The logic is the logic of `credit/freddie/staging.py`, `features.py` and `fresh.py` (written for DuckDB). Structure uses the DataFrame API
# MAGIC (`select`, `join`, `groupBy`, `filter`); one-column expressions use `F.expr` with the same SQL as the DuckDB version, so a reader can
# MAGIC compare them line by line.
# MAGIC
# MAGIC Two places cannot be identical, and that is the interesting part:
# MAGIC 1. **`split`**: DuckDB assigns it with its `hash()` function; Spark's hash is another function, so the split differs. Everything else must be identical.
# MAGIC 2. **Null handling and types**: Spark serverless runs in ANSI mode (a bad cast raises an error), so every cast is `try_cast` / `try_to_date`.

# COMMAND ----------

import time

from pyspark.sql import functions as F

CATALOG, SCHEMA = "workspace", "credit"
spark.sql(f"USE {CATALOG}.{SCHEMA}")

# The same constants as the Python pipeline and the dbt project (tests/test_dbt_project.py guards the dbt copy).
YEARS_MAIN = [2008, 2012, 2016, 2019, 2022]
YEARS_FRESH = [2010, 2014, 2018, 2023]
WINDOW_MONTHS = 24
DEV_MAX_VINTAGE = 2018
OOT_1 = (2019, 2021)
OOT_2_MIN = 2022
SPLIT_SEED = "split-v1"
SHORT_TERM_MONTHS = 180

TIMINGS = {}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Staging: typed tables (credit/freddie/staging.py)

# COMMAND ----------

def _int(col, na=None):
    """Text -> integer; empty and the 'not available' code become NULL."""
    e = f"nullif({col}, '')"
    if na is not None:
        e = f"nullif({e}, '{na}')"
    return F.expr(f"try_cast({e} as int)")


def _one_of(col, allowed):
    return F.when(F.col(col).isin(*allowed), F.col(col))


def _month(col):
    """'YYYYMM' text -> first day of that month."""
    return F.expr(f"try_to_date({col} || '01', 'yyyyMMdd')")


def stg_orig(raw):
    yy = F.expr("try_cast(substr(loan_seq, 2, 2) as int)")
    typed = raw.select(
        "loan_seq",
        (F.when(yy >= 90, F.lit(1900)).otherwise(F.lit(2000)) + yy).alias("vintage_year"),
        F.expr("try_cast(substr(loan_seq, 5, 1) as int)").alias("vintage_quarter"),
        F.when(_int("credit_score").between(300, 850), _int("credit_score")).alias("credit_score"),
        _month("first_payment_date").alias("first_payment_date"),
        _month("maturity_date").alias("maturity_date"),
        _one_of("first_time_homebuyer", ["Y", "N"]).alias("first_time_homebuyer"),
        F.expr("nullif(msa, '')").alias("msa"),
        _int("mi_pct", "999").alias("mi_pct"),
        _int("n_units", "99").alias("n_units"),
        _one_of("occupancy", ["P", "I", "S"]).alias("occupancy"),
        _int("cltv", "999").alias("cltv"),
        _int("dti", "999").alias("dti"),
        F.expr("try_cast(nullif(orig_upb, '') as double)").alias("orig_upb"),
        _int("ltv", "999").alias("ltv"),
        F.expr("try_cast(nullif(int_rate, '') as double)").alias("int_rate"),
        _one_of("channel", ["R", "B", "C", "T"]).alias("channel"),
        _one_of("ppm_flag", ["Y", "N"]).alias("ppm_flag"),
        F.expr("nullif(amort_type, '')").alias("amort_type"),
        F.expr("nullif(state, '')").alias("state"),
        _one_of("property_type", ["SF", "PU", "CO", "MH", "CP"]).alias("property_type"),
        F.expr("nullif(zip3, '')").alias("zip3"),
        _one_of("purpose", ["P", "C", "N", "R"]).alias("purpose"),
        _int("orig_term").alias("orig_term"),
        _int("n_borrowers", "99").alias("n_borrowers"),
        F.expr("nullif(seller_name, '')").alias("seller_name"),
        _one_of("super_conforming", ["Y", "N"]).alias("super_conforming"),
        F.expr("nullif(program_indicator, '')").alias("program_indicator"),
        F.coalesce(F.col("relief_refi") == "Y", F.lit(False)).alias("relief_refi"),
        _one_of("io_indicator", ["Y", "N"]).alias("io_indicator"),
    )
    months = (F.year("first_payment_date") * 12 + F.month("first_payment_date")) \
        - (F.col("vintage_year") * 12 + (F.col("vintage_quarter") - 1) * 3 + 1)
    return typed.withColumn("months_after_vintage", months).withColumn("is_seasoned_or_modified", months > 6)


def stg_label(perf):
    p = perf.select(
        "loan_seq",
        F.expr("try_cast(loan_age as int)").alias("age"),
        F.expr("coalesce(try_cast(delinq_status as int) >= 3 or delinq_status = 'RA', false)").alias("late90"),
        F.expr("coalesce(zero_balance_code in ('02', '03', '09', '15'), false)").alias("credit_event"),
        F.expr("coalesce(zero_balance_code is not null, false)").alias("ended"),
        F.expr("coalesce(borrower_assist_code is not null, false)").alias("assist"),
    )
    w = WINDOW_MONTHS
    per_loan = p.groupBy("loan_seq").agg(
        F.max("age").alias("max_age"),
        F.expr(f"coalesce(bool_or(ended and age <= {w}), false)").alias("ended_in_window"),
        F.expr(f"coalesce(bool_or((late90 or credit_event) and age <= {w}), false)").alias("def_a"),
        F.expr(f"coalesce(bool_or(((late90 and not assist) or credit_event) and age <= {w}), false)").alias("def_b"),
        F.expr(f"coalesce(bool_or(credit_event and age <= {w}), false)").alias("def_c"),
    )
    observable = (F.col("max_age") >= w) | F.col("ended_in_window")
    return per_loan.select(
        "loan_seq", "max_age",
        observable.alias("observable_24m"),
        F.when(observable, F.col("def_b").cast("int")).alias("default_24m"),
        F.when(observable, F.col("def_a").cast("int")).alias("default_24m_all_late"),
        F.when(observable, F.col("def_c").cast("int")).alias("default_24m_loss_only"),
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Features (credit/freddie/features.py and fresh.py)

# COMMAND ----------

META = ["loan_seq", "vintage_year", "vintage_quarter", "first_payment_date", "int_rate"]
NUMERIC = ["credit_score", "mi_pct", "n_units", "cltv", "dti", "orig_upb", "ltv", "rate_spread", "orig_term", "n_borrowers"]
CATEGORICAL = ["first_time_homebuyer", "occupancy", "channel", "ppm_flag", "property_type", "purpose", "state", "super_conforming"]
LABELS = ["default_24m", "default_24m_all_late", "default_24m_loss_only"]


def build_features(stg_o, stg_l, fresh=False):
    joined = stg_o.join(stg_l, "loan_seq")   # inner join on loan_seq, like JOIN ... USING (loan_seq)
    kept = (joined.filter(~F.col("relief_refi") & ~F.col("is_seasoned_or_modified") & F.col("observable_24m"))
            .withColumn("term_class", F.col("orig_term") > SHORT_TERM_MONTHS))
    # rate_spread = the loan's rate minus the median rate of the kept loans of the same vintage quarter and term class.
    # DuckDB does it with a window (quantile_cont ... OVER); here: groupBy + percentile (same linear interpolation) + a null-safe join.
    med = (kept.groupBy("vintage_year", "vintage_quarter", "term_class").agg(F.expr("percentile(int_rate, 0.5)").alias("median_rate"))
           .withColumnRenamed("vintage_year", "m_year").withColumnRenamed("vintage_quarter", "m_quarter").withColumnRenamed("term_class", "m_class"))
    cond = (kept["vintage_year"].eqNullSafe(med["m_year"]) & kept["vintage_quarter"].eqNullSafe(med["m_quarter"])
            & kept["term_class"].eqNullSafe(med["m_class"]))
    spread = kept.join(med, cond, "left").withColumn("rate_spread", F.col("int_rate") - F.col("median_rate"))
    vy = F.col("vintage_year")
    if fresh:
        nb = F.col("n_borrowers")
        spread = spread.withColumn("several_borrowers", F.when(nb.isNull(), F.lit(None).cast("double")).when(nb >= 2, F.lit(1.0)).otherwise(F.lit(0.0)))
        split = F.concat(F.lit("fresh_"), vy.cast("string"))
        cols = META + NUMERIC + CATEGORICAL + ["several_borrowers"] + LABELS
    else:
        h = F.pmod(F.hash(F.concat(F.col("loan_seq"), F.lit(SPLIT_SEED))), F.lit(100))   # NOT DuckDB's hash(): the split will differ
        split = (F.when(vy <= DEV_MAX_VINTAGE,
                        F.when(h < 60, "train").when(h < 70, "calibration").when(h < 85, "validation").otherwise("test_in_time"))
                 .when(vy.between(*OOT_1), "test_oot_2019").when(vy >= OOT_2_MIN, "test_oot_2022"))
        cols = META + NUMERIC + CATEGORICAL + LABELS
    return spread.select(*cols, split.alias("split"))

# COMMAND ----------

def timed(label, fn):
    t = time.perf_counter()
    out = fn()
    TIMINGS[label] = round(time.perf_counter() - t, 2)
    print(f"{label}: {TIMINGS[label]} s")
    return out


def stage_and_build(years, suffix, fresh):
    raw_o = spark.table("raw_orig").filter(F.col("source_year").isin(years))
    raw_p = spark.table("raw_perf").filter(F.col("source_year").isin(years))
    timed(f"stage{suffix}", lambda: (
        stg_orig(raw_o).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"stg_orig{suffix}"),
        stg_label(raw_p).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"stg_label{suffix}")))
    target = "features_fresh" if fresh else "features_dev"
    timed(f"features{suffix}", lambda: build_features(spark.table(f"stg_orig{suffix}"), spark.table(f"stg_label{suffix}"), fresh)
          .write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target))
    print(target, spark.table(target).count(), "rows")


t_all = time.perf_counter()
stage_and_build(YEARS_MAIN, "", fresh=False)
stage_and_build(YEARS_FRESH, "_fresh", fresh=True)
TIMINGS["total"] = round(time.perf_counter() - t_all, 2)
print("TOTAL", TIMINGS["total"], "s")
print(TIMINGS)
spark.createDataFrame([(k, float(v)) for k, v in TIMINGS.items()], ["step", "seconds"]).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable("timings")
