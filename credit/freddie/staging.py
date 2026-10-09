"""Staging (silver layer): typed tables, special values turned into NULL, labels, data checks.

Reads the raw Parquet files made by credit.freddie.load (all columns as text) and writes, per year:
  stg_orig_<year>.parquet   one row per loan, typed, with flags (relief refinance, seasoned/modified)
  stg_label_<year>.parquet  one row per loan: was it observed 24 months, and did it default?
  report_<year>.json        counts and check results

Nothing is filtered out here: excluded loans are only FLAGGED. The exclusion rules are applied in
the features layer, and counted there. This keeps staging a faithful, typed copy of the raw data.

Default label (decision log, 2026-10-09): within 24 months of the loan's first month,
  A: 90+ days late (status >= 3 or 'RA') OR credit-event zero balance code (02, 03, 09, 15)
  B: like A, but lateness only counts when no borrower assistance plan is active  <-- default_24m
  C: credit-event zero balance code only
Usage (from the repo root):  .venv/Scripts/python -m credit.freddie.staging 2008 2012 2016 2019 2022
"""
import json
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "interim" / "raw"
STG_DIR = ROOT / "data" / "interim" / "stg"
WINDOW_MONTHS = 24


class DataCheckError(Exception):
    """Raised when a data check fails: the pipeline must stop."""


def _int(col: str, na: str | None = None) -> str:
    """Text -> integer; empty and the 'not available' code become NULL."""
    expr = f"NULLIF({col}, '')"
    if na is not None:
        expr = f"NULLIF({expr}, '{na}')"
    return f"TRY_CAST({expr} AS INTEGER)"


def _one_of(col: str, allowed: tuple[str, ...]) -> str:
    items = ", ".join(f"'{a}'" for a in allowed)
    return f"CASE WHEN {col} IN ({items}) THEN {col} END"


def _month(col: str) -> str:
    """'YYYYMM' text -> first day of that month."""
    return f"CAST(TRY_STRPTIME({col} || '01', '%Y%m%d') AS DATE)"


def stg_orig_sql(raw_path: Path) -> str:
    return f"""
    WITH typed AS (
      SELECT
        loan_seq,
        CASE WHEN TRY_CAST(substr(loan_seq, 2, 2) AS INTEGER) >= 90 THEN 1900 ELSE 2000 END
          + TRY_CAST(substr(loan_seq, 2, 2) AS INTEGER)                 AS vintage_year,
        TRY_CAST(substr(loan_seq, 5, 1) AS INTEGER)                      AS vintage_quarter,
        CASE WHEN {_int('credit_score')} BETWEEN 300 AND 850
             THEN {_int('credit_score')} END                             AS credit_score,
        {_month('first_payment_date')}                                   AS first_payment_date,
        {_month('maturity_date')}                                        AS maturity_date,
        {_one_of('first_time_homebuyer', ('Y', 'N'))}                    AS first_time_homebuyer,
        NULLIF(msa, '')                                                  AS msa,
        {_int('mi_pct', '999')}                                          AS mi_pct,
        {_int('n_units', '99')}                                          AS n_units,
        {_one_of('occupancy', ('P', 'I', 'S'))}                          AS occupancy,
        {_int('cltv', '999')}                                            AS cltv,
        {_int('dti', '999')}                                             AS dti,
        TRY_CAST(NULLIF(orig_upb, '') AS DOUBLE)                         AS orig_upb,
        {_int('ltv', '999')}                                             AS ltv,
        TRY_CAST(NULLIF(int_rate, '') AS DOUBLE)                         AS int_rate,
        {_one_of('channel', ('R', 'B', 'C', 'T'))}                       AS channel,
        {_one_of('ppm_flag', ('Y', 'N'))}                                AS ppm_flag,
        NULLIF(amort_type, '')                                           AS amort_type,
        NULLIF(state, '')                                                AS state,
        {_one_of('property_type', ('SF', 'PU', 'CO', 'MH', 'CP'))}       AS property_type,
        NULLIF(zip3, '')                                                 AS zip3,
        {_one_of('purpose', ('P', 'C', 'N', 'R'))}                       AS purpose,
        {_int('orig_term')}                                              AS orig_term,
        {_int('n_borrowers', '99')}                                      AS n_borrowers,
        NULLIF(seller_name, '')                                          AS seller_name,
        {_one_of('super_conforming', ('Y', 'N'))}                        AS super_conforming,
        NULLIF(program_indicator, '')                                    AS program_indicator,
        COALESCE(relief_refi = 'Y', FALSE)                               AS relief_refi,
        {_one_of('io_indicator', ('Y', 'N'))}                            AS io_indicator
      FROM read_parquet('{raw_path.as_posix()}')
    )
    SELECT *,
      (date_part('year', first_payment_date) * 12 + date_part('month', first_payment_date))
        - (vintage_year * 12 + (vintage_quarter - 1) * 3 + 1)            AS months_after_vintage,
      ((date_part('year', first_payment_date) * 12 + date_part('month', first_payment_date))
        - (vintage_year * 12 + (vintage_quarter - 1) * 3 + 1)) > 6       AS is_seasoned_or_modified
    FROM typed
    """


def stg_label_sql(raw_path: Path) -> str:
    return f"""
    WITH p AS (
      SELECT
        loan_seq,
        TRY_CAST(loan_age AS INTEGER)                                          AS age,
        COALESCE(TRY_CAST(delinq_status AS INTEGER) >= 3 OR delinq_status = 'RA', FALSE) AS late90,
        COALESCE(zero_balance_code IN ('02', '03', '09', '15'), FALSE)         AS credit_event,
        COALESCE(zero_balance_code IS NOT NULL, FALSE)                         AS ended,
        COALESCE(borrower_assist_code IS NOT NULL, FALSE)                      AS assist
      FROM read_parquet('{raw_path.as_posix()}')
    ),
    per_loan AS (
      SELECT
        loan_seq,
        max(age)                                                              AS max_age,
        COALESCE(bool_or(ended AND age <= {WINDOW_MONTHS}), FALSE)            AS ended_in_window,
        COALESCE(bool_or((late90 OR credit_event) AND age <= {WINDOW_MONTHS}), FALSE) AS def_a,
        COALESCE(bool_or(((late90 AND NOT assist) OR credit_event)
                         AND age <= {WINDOW_MONTHS}), FALSE)                  AS def_b,
        COALESCE(bool_or(credit_event AND age <= {WINDOW_MONTHS}), FALSE)     AS def_c
      FROM p GROUP BY loan_seq
    )
    SELECT
      loan_seq, max_age,
      (max_age >= {WINDOW_MONTHS} OR ended_in_window)                         AS observable_24m,
      CASE WHEN (max_age >= {WINDOW_MONTHS} OR ended_in_window) THEN def_b::INTEGER END AS default_24m,
      CASE WHEN (max_age >= {WINDOW_MONTHS} OR ended_in_window) THEN def_a::INTEGER END AS default_24m_all_late,
      CASE WHEN (max_age >= {WINDOW_MONTHS} OR ended_in_window) THEN def_c::INTEGER END AS default_24m_loss_only
    FROM per_loan
    """


def run_checks(
    con: duckdb.DuckDBPyConnection, max_missing_score: float = 0.01, max_default_rate: float = 0.20
) -> list[str]:
    """Return a list of failed checks (empty list = all good). Tables stg_orig and stg_label exist.

    The two limits are sanity limits for real-size data; tests on tiny data relax them."""

    def one(sql: str):
        return con.execute(sql).fetchone()[0]

    failures = []
    n = one("SELECT count(*) FROM stg_orig")
    if n == 0:
        failures.append("stg_orig is empty")
    if one("SELECT count(DISTINCT loan_seq) FROM stg_orig") != n:
        failures.append("loan_seq is not unique in stg_orig (primary key broken)")
    if one("SELECT count(*) FROM stg_label") != one("SELECT count(DISTINCT loan_seq) FROM stg_label"):
        failures.append("loan_seq is not unique in stg_label")
    orphans = one("SELECT count(*) FROM stg_label l LEFT JOIN stg_orig o USING (loan_seq) WHERE o.loan_seq IS NULL")
    if orphans:
        failures.append(f"{orphans} loans in the performance file have no origination row (foreign key broken)")
    if one("SELECT count(*) FROM stg_orig WHERE vintage_year IS NULL OR vintage_quarter IS NULL"):
        failures.append("some loan_seq values do not follow the PYYQnXXXXXXX pattern")
    if one("SELECT count(*) FROM stg_orig WHERE orig_upb IS NULL OR orig_upb <= 0"):
        failures.append("orig_upb must be positive and present")
    if one("SELECT count(*) FROM stg_orig WHERE int_rate IS NULL OR int_rate < 0 OR int_rate > 20"):
        failures.append("int_rate outside 0-20%")
    if one("SELECT count(*) FROM stg_orig WHERE orig_term IS NULL OR orig_term < 60 OR orig_term > 480"):
        failures.append("orig_term outside 60-480 months")
    if one("SELECT count(*) FROM stg_orig WHERE dti IS NOT NULL AND (dti < 0 OR dti > 65)"):
        failures.append("dti outside 0-65")
    if one("SELECT count(*) FROM stg_orig WHERE credit_score < 300 OR credit_score > 850"):
        failures.append("credit_score outside 300-850 (should have become NULL)")
    if n and one("SELECT avg((credit_score IS NULL)::INTEGER) FROM stg_orig") > max_missing_score:
        failures.append(f"more than {max_missing_score:.0%} of credit scores are missing")
    if one("SELECT count(*) FROM stg_label WHERE observable_24m AND default_24m IS NULL"):
        failures.append("an observable loan has no label")
    if one("SELECT count(*) FROM stg_label WHERE default_24m NOT IN (0, 1)"):
        failures.append("default_24m has values other than 0 or 1")
    rate = one("SELECT avg(default_24m) FROM stg_label WHERE observable_24m")
    if rate is not None and not (0 <= rate <= max_default_rate):
        failures.append(f"default rate {rate:.3f} outside the sane range 0-{max_default_rate:.0%}")
    # leakage test: no feature column of the origination table may look like a label
    cols = [r[0] for r in con.execute("DESCRIBE stg_orig").fetchall()]
    leaking = [c for c in cols if "default" in c or "delinq" in c or c.startswith("zero_balance")]
    if leaking:
        failures.append(f"leakage: label-like columns in stg_orig: {leaking}")
    return failures


def stage_year(
    year: int,
    raw_dir: Path = RAW_DIR,
    out_dir: Path = STG_DIR,
    max_missing_score: float = 0.01,
    max_default_rate: float = 0.20,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"CREATE TABLE stg_orig AS {stg_orig_sql(raw_dir / f'orig_{year}.parquet')}")
    con.execute(f"CREATE TABLE stg_label AS {stg_label_sql(raw_dir / f'perf_{year}.parquet')}")

    failures = run_checks(con, max_missing_score, max_default_rate)
    report = {
        "year": year,
        "loans": con.execute("SELECT count(*) FROM stg_orig").fetchone()[0],
        "relief_refi": con.execute("SELECT count(*) FROM stg_orig WHERE relief_refi").fetchone()[0],
        "seasoned_or_modified": con.execute("SELECT count(*) FROM stg_orig WHERE is_seasoned_or_modified").fetchone()[0],
        "not_observable_24m": con.execute("SELECT count(*) FROM stg_label WHERE NOT observable_24m").fetchone()[0],
        "defaults_b": con.execute("SELECT coalesce(sum(default_24m), 0) FROM stg_label").fetchone()[0],
        "defaults_a_all_late": con.execute("SELECT coalesce(sum(default_24m_all_late), 0) FROM stg_label").fetchone()[0],
        "defaults_c_loss_only": con.execute("SELECT coalesce(sum(default_24m_loss_only), 0) FROM stg_label").fetchone()[0],
        "failed_checks": failures,
    }
    if failures:
        raise DataCheckError(f"{year}: " + "; ".join(failures))
    con.execute(f"COPY stg_orig TO '{(out_dir / f'stg_orig_{year}.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    con.execute(f"COPY stg_label TO '{(out_dir / f'stg_label_{year}.parquet').as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    (out_dir / f"report_{year}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    con.close()
    return report


if __name__ == "__main__":
    years = [int(a) for a in sys.argv[1:]] or [2008, 2012, 2016, 2019, 2022]
    for y in years:
        r = stage_year(y)
        print(
            f"{y}: loans={r['loans']:,} relief_refi={r['relief_refi']:,} seasoned_or_modified={r['seasoned_or_modified']:,} "
            f"not_observable={r['not_observable_24m']:,} defaults(B)={r['defaults_b']:,} "
            f"(A={r['defaults_a_all_late']:,}, C={r['defaults_c_loss_only']:,}) checks=OK"
        )
