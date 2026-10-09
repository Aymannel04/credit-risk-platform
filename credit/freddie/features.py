"""Features layer (gold): the table the models learn from.

One row per kept loan = day-one features (from the origination file only) + the label + a split name.

Steps (each counted, per vintage, in report.json):
  1. start from staging (typed tables)
  2. exclude relief refinance loans            (special government program, see decision log)
  3. exclude seasoned / modified loans         (their loan clock does not start at origination)
  4. exclude loans not observable for 24 months (label would be unknown)

Splits (assigned by hashing loan_seq, so they are reproducible and never change when data is added):
  development vintages (<= 2018; files 2008, 2012, 2016): train 60% | calibration 10% | validation 15% | test_in_time 15%
  later vintages (out of time): 2019-2021 -> test_oot_2019, 2022+ -> test_oot_2022
Out-of-time test sets are never used to choose or tune anything.

Usage (from the repo root):  .venv/Scripts/python -m credit.freddie.features
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
STG_DIR = ROOT / "data" / "interim" / "stg"
OUT_DIR = ROOT / "data" / "interim" / "features"

# Vintage ranges (by the year inside loan_seq). A few loans sit in a neighbouring year (e.g. one 2009 loan in the
# 2008 file), so ranges are used instead of exact years.
DEV_MAX_VINTAGE = 2018  # <= 2018: development pool (the files used are 2008, 2012, 2016)
OOT_1_RANGE = (2019, 2021)  # out-of-time test 1 (the file used is 2019)
OOT_2_MIN = 2022  # out-of-time test 2 (the file used is 2022)
SPLIT_SEED = "split-v1"

# Known on day one (origination file only). Changing these lists is a modelling decision: log it.
NUMERIC_FEATURES = [
    "credit_score", "mi_pct", "n_units", "cltv", "dti", "orig_upb", "ltv", "int_rate", "orig_term", "n_borrowers",
]
CATEGORICAL_FEATURES = [
    "first_time_homebuyer", "occupancy", "channel", "ppm_flag", "property_type", "purpose", "state", "super_conforming",
]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
# Kept for splitting, tracing and reporting; NEVER used as model inputs.
META = ["loan_seq", "vintage_year", "vintage_quarter", "first_payment_date"]
LABELS = ["default_24m", "default_24m_all_late", "default_24m_loss_only"]

# Deliberately not features (reason in docs/decision-log.md): zip3, msa, seller_name (geography/lender
# proxies), program_indicator (affordable-housing programme), vintage_year (does not transfer across time),
# amort_type / io_indicator / property_valuation_method (constant in this data), maturity_date (= term).


def _split_sql() -> str:
    h = f"hash(loan_seq || '{SPLIT_SEED}') % 100"
    return f"""
    CASE
      WHEN vintage_year <= {DEV_MAX_VINTAGE} THEN
        CASE
          WHEN {h} < 60 THEN 'train'
          WHEN {h} < 70 THEN 'calibration'
          WHEN {h} < 85 THEN 'validation'
          ELSE 'test_in_time'
        END
      WHEN vintage_year BETWEEN {OOT_1_RANGE[0]} AND {OOT_1_RANGE[1]} THEN 'test_oot_2019'
      WHEN vintage_year >= {OOT_2_MIN} THEN 'test_oot_2022'
    END"""


def build(con: duckdb.DuckDBPyConnection) -> dict:
    """Needs tables stg_orig and stg_label (all vintages). Creates table `features`; returns the report."""
    con.execute(
        """
        CREATE OR REPLACE TABLE joined AS
        SELECT o.*, l.observable_24m, l.default_24m, l.default_24m_all_late, l.default_24m_loss_only
        FROM stg_orig o JOIN stg_label l USING (loan_seq)
        """
    )
    waterfall = con.execute(
        """
        SELECT vintage_year,
          count(*)                                                                         AS start,
          count(*) FILTER (WHERE relief_refi)                                              AS removed_relief_refi,
          count(*) FILTER (WHERE NOT relief_refi AND is_seasoned_or_modified)              AS removed_seasoned_or_modified,
          count(*) FILTER (WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND NOT observable_24m)
                                                                                           AS removed_not_observable,
          count(*) FILTER (WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND observable_24m) AS kept
        FROM joined GROUP BY vintage_year ORDER BY vintage_year
        """
    ).df()

    cols = ", ".join(META + FEATURES + LABELS)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE features AS
        SELECT {cols}, {_split_sql()} AS split
        FROM joined
        WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND observable_24m
        """
    )
    splits = con.execute(
        """
        SELECT split, count(*) AS loans, sum(default_24m) AS defaults,
               round(100.0 * avg(default_24m), 2) AS default_rate_pct
        FROM features GROUP BY split ORDER BY split
        """
    ).df()
    return {
        "waterfall": waterfall.to_dict(orient="records"),
        "splits": splits.to_dict(orient="records"),
        "failed_checks": check(con),
    }


def check(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Checks on the features table. Empty list = all good."""

    def one(sql: str):
        return con.execute(sql).fetchone()[0]

    failures = []
    cols = [r[0] for r in con.execute("DESCRIBE features").fetchall()]
    allowed = set(META + FEATURES + LABELS + ["split"])
    if set(cols) != allowed:
        failures.append(f"unexpected columns in features: {sorted(set(cols) ^ allowed)}")
    if one("SELECT count(*) FROM features WHERE default_24m IS NULL OR split IS NULL"):
        failures.append("missing label or split")
    if one("SELECT count(*) - count(DISTINCT loan_seq) FROM features"):
        failures.append("duplicate loan_seq in features")
    if one(f"SELECT count(*) FROM features WHERE split LIKE 'test_oot%' AND vintage_year <= {DEV_MAX_VINTAGE}"):
        failures.append("development vintage found in an out-of-time test set")
    if one(f"SELECT count(*) FROM features WHERE split NOT LIKE 'test_oot%' AND vintage_year > {DEV_MAX_VINTAGE}"):
        failures.append("out-of-time vintage found in a training/validation split")
    leaking = [c for c in FEATURES if "default" in c or "delinq" in c or "zero_balance" in c or "loss" in c]
    if leaking:
        failures.append(f"leakage: label-like feature names {leaking}")
    return failures


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for kind in ("orig", "label"):
        files = sorted(STG_DIR.glob(f"stg_{kind}_*.parquet"))
        if not files:
            raise FileNotFoundError(f"no stg_{kind}_*.parquet in {STG_DIR}: run credit.freddie.staging first")
        listing = ", ".join(f"'{f.as_posix()}'" for f in files)
        con.execute(f"CREATE TABLE stg_{kind} AS SELECT * FROM read_parquet([{listing}], union_by_name=true)")
    report = build(con)
    if report["failed_checks"]:
        raise SystemExit("feature checks failed: " + "; ".join(report["failed_checks"]))
    con.execute(f"COPY features TO '{(OUT_DIR / 'features.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=int), encoding="utf-8")
    print("Exclusion waterfall (per vintage):")
    for r in report["waterfall"]:
        print("  ", r)
    print("Splits:")
    for r in report["splits"]:
        print("  ", r)
    print("checks = OK")


if __name__ == "__main__":
    main()
