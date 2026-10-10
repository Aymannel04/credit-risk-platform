"""Features table for the FRESH vintages (the v2 exam). Same exclusions and same rate spread as the development table.

The labels of these vintages are LOCKED: `load_fresh` refuses to return them unless `allow_exam=True`, which only
the v2 exam script passes (after the freeze). Building the table prints structural counts only, never labels.

Usage (from the repo root):  .venv/Scripts/python -m credit.freddie.fresh
"""
import json
from pathlib import Path

import duckdb
import pandas as pd

from credit.freddie.features import FEATURES, LABELS, META, SHORT_TERM_MONTHS

ROOT = Path(__file__).resolve().parents[2]
STG_FRESH = ROOT / "data" / "interim" / "stg_fresh"
OUT_DIR = ROOT / "data" / "interim" / "features_fresh"
FRESH_PATH = OUT_DIR / "features_fresh.parquet"
EXTRA = ["several_borrowers"]  # a v2 input: "more than one borrower?" (the n_borrowers definition changed in 2018Q2)


def build_fresh(con: duckdb.DuckDBPyConnection) -> dict:
    """Needs tables stg_orig and stg_label (fresh vintages only). Creates table `fresh`; returns structural counts."""
    con.execute(
        """
        CREATE OR REPLACE TABLE joined AS
        SELECT o.*, l.observable_24m, l.default_24m, l.default_24m_all_late, l.default_24m_loss_only
        FROM stg_orig o JOIN stg_label l USING (loan_seq)
        """
    )
    waterfall = con.execute(
        """
        SELECT vintage_year, count(*) AS start,
          count(*) FILTER (WHERE relief_refi) AS removed_relief_refi,
          count(*) FILTER (WHERE NOT relief_refi AND is_seasoned_or_modified) AS removed_seasoned_or_modified,
          count(*) FILTER (WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND NOT observable_24m) AS removed_not_observable,
          count(*) FILTER (WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND observable_24m) AS kept
        FROM joined GROUP BY vintage_year ORDER BY vintage_year
        """
    ).df()
    cols = ", ".join(META + FEATURES + EXTRA + LABELS)
    con.execute(
        f"""
        CREATE OR REPLACE TABLE fresh AS
        WITH kept AS (
          SELECT * FROM joined WHERE NOT relief_refi AND NOT is_seasoned_or_modified AND observable_24m
        ), spread AS (
          SELECT *, int_rate - quantile_cont(int_rate, 0.5)
                 OVER (PARTITION BY vintage_year, vintage_quarter, (orig_term > {SHORT_TERM_MONTHS})) AS rate_spread,
                 CASE WHEN n_borrowers IS NULL THEN NULL WHEN n_borrowers >= 2 THEN 1.0 ELSE 0.0 END AS several_borrowers
          FROM kept
        )
        SELECT {cols}, 'fresh_' || CAST(vintage_year AS VARCHAR) AS split FROM spread
        """
    )
    return {"waterfall": waterfall.to_dict(orient="records")}


def check_fresh(con: duckdb.DuckDBPyConnection) -> list[str]:
    failures = []
    one = lambda q: con.execute(q).fetchone()[0]  # noqa: E731
    cols = {r[0] for r in con.execute("DESCRIBE fresh").fetchall()}
    if cols != set(META + FEATURES + EXTRA + LABELS + ["split"]):
        failures.append("unexpected columns in the fresh table")
    if one("SELECT count(*) - count(DISTINCT loan_seq) FROM fresh"):
        failures.append("duplicate loan_seq")
    if one("SELECT count(*) FROM fresh WHERE default_24m IS NULL"):
        failures.append("missing label on a kept loan")
    return failures


def load_fresh(vintages=None, path: Path = FRESH_PATH, allow_exam: bool = False) -> pd.DataFrame:
    if not allow_exam:
        raise PermissionError("the fresh vintages are the v2 exam: their rows (and labels) are locked until the freeze")
    where = ""
    if vintages is not None:
        names = ", ".join(f"'fresh_{int(v)}'" for v in vintages)
        where = f" WHERE split IN ({names})"
    return duckdb.sql(f"SELECT * FROM read_parquet('{path.as_posix()}'){where}").df()


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for kind in ("orig", "label"):
        files = sorted(STG_FRESH.glob(f"stg_{kind}_*.parquet"))
        if not files:
            raise FileNotFoundError(f"no staged fresh {kind} files in {STG_FRESH}")
        listing = ", ".join(f"'{f.as_posix()}'" for f in files)
        con.execute(f"CREATE TABLE stg_{kind} AS SELECT * FROM read_parquet([{listing}], union_by_name=true)")
    report = build_fresh(con)
    failures = check_fresh(con)
    if failures:
        raise SystemExit("fresh checks failed: " + "; ".join(failures))
    con.execute(f"COPY fresh TO '{FRESH_PATH.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    (OUT_DIR / "report.json").write_text(json.dumps(report, indent=2, default=int), encoding="utf-8")
    print("fresh features built (structure only; labels stay locked):")
    for r in report["waterfall"]:
        print("  ", r)


if __name__ == "__main__":
    main()
