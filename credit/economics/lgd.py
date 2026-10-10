"""LGD (loss given default) measured from the real loss data of the Freddie Mac samples.

Two numbers, because our default flag (definition B) also catches loans that later recovered:
  lgd_loss_events : among loans that really ended with a loss event (zero balance code 02, 03, 09, 15) and
                    whose Actual Loss is populated: sum(actual_loss) / sum(unpaid balance at that moment)
  loss_per_flag   : among ALL loans flagged default_24m = 1: sum(actual_loss over the whole life) /
                    sum(original loan amount). This is the multiplier that matches our PD (PD counts every
                    flagged loan) and the exposure we use (original amount).
Actual Loss is NULL for loans disposed in the last 3 months before the data cutoff and for loans with a defect.
Negative losses (a gain on the sale) are kept: dropping them would overstate the loss.

Usage (from the repo root):  .venv/Scripts/python -m credit.economics.lgd
"""
import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "interim" / "raw"
STG = ROOT / "data" / "interim" / "stg"
RESULTS = ROOT / "results"
CREDIT_EVENT_CODES = ("02", "03", "09", "15")


def lgd_summary(con: duckdb.DuckDBPyConnection) -> list[dict]:
    """Needs tables: perf (raw performance, text columns) and loans (loan_seq, vintage_year, orig_upb, default_24m)."""
    codes = ", ".join(f"'{c}'" for c in CREDIT_EVENT_CODES)
    q = f"""
    WITH ends AS (  -- one row per loan that ended with a credit event: its final record
      SELECT loan_seq,
             TRY_CAST(actual_loss AS DOUBLE)              AS actual_loss,
             TRY_CAST(zero_balance_removal_upb AS DOUBLE) AS upb_at_end
      FROM perf WHERE zero_balance_code IN ({codes})
    ),
    j AS (
      SELECT l.vintage_year, l.loan_seq, l.orig_upb, l.default_24m, e.loan_seq IS NOT NULL AS loss_event,
             e.actual_loss, e.upb_at_end
      FROM loans l LEFT JOIN ends e USING (loan_seq)
    )
    SELECT
      vintage_year,
      count(*) FILTER (WHERE default_24m = 1)                                                AS flagged_defaults,
      count(*) FILTER (WHERE default_24m = 1 AND loss_event)                                  AS flagged_with_loss_event,
      count(*) FILTER (WHERE loss_event)                                                      AS loss_event_loans,
      count(*) FILTER (WHERE loss_event AND actual_loss IS NOT NULL)                          AS loss_event_with_amount,
      round(sum(actual_loss) FILTER (WHERE loss_event AND actual_loss IS NOT NULL)
            / nullif(sum(upb_at_end) FILTER (WHERE loss_event AND actual_loss IS NOT NULL), 0), 4) AS lgd_loss_events,
      round(quantile_cont(actual_loss / nullif(upb_at_end, 0), 0.5)
            FILTER (WHERE loss_event AND actual_loss IS NOT NULL), 4)                         AS median_loss_share,
      round(avg((actual_loss <= 0)::INT) FILTER (WHERE loss_event AND actual_loss IS NOT NULL), 4) AS share_no_loss_or_gain,
      round(sum(coalesce(actual_loss, 0)) FILTER (WHERE default_24m = 1)
            / nullif(sum(orig_upb) FILTER (WHERE default_24m = 1), 0), 4)                     AS loss_per_flag
    FROM j GROUP BY vintage_year ORDER BY vintage_year
    """
    return con.execute(q).df().to_dict(orient="records")


def main() -> list[dict]:
    con = duckdb.connect()
    parts = []
    for y in (2008, 2012, 2016, 2019, 2022):
        parts.append(f"SELECT loan_seq, zero_balance_code, actual_loss, zero_balance_removal_upb "
                     f"FROM read_parquet('{(RAW / f'perf_{y}.parquet').as_posix()}')")
    con.execute("CREATE TABLE perf AS " + " UNION ALL ".join(parts))
    con.execute(f"""
        CREATE TABLE loans AS
        SELECT o.loan_seq, o.vintage_year, o.orig_upb, l.default_24m
        FROM read_parquet('{(STG / 'stg_orig_*.parquet').as_posix()}') o
        JOIN read_parquet('{(STG / 'stg_label_*.parquet').as_posix()}') l USING (loan_seq)
        WHERE NOT o.relief_refi AND NOT o.is_seasoned_or_modified AND l.observable_24m
    """)
    rows = lgd_summary(con)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "lgd_estimate.json").write_text(json.dumps(rows, indent=2, default=float), encoding="utf-8")
    return rows


if __name__ == "__main__":
    import pandas as pd

    pd.set_option("display.width", 220)
    print(pd.DataFrame(main()).to_string(index=False))
