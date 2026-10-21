"""Write databricks/expected_control_queries.json: what DuckDB answers to the control queries, on the local files.

    python scripts/make_databricks_expected.py

The Databricks notebook 03 runs the same questions on the PySpark tables and compares. The first control query of the S3 + Athena test
(`dev_split_counts`) groups by `split`, which comes from DuckDB's `hash()`; Spark has another hash function, so that question is replaced
here by one that does not depend on the split (`dev_totals`). The other five are the same as in credit/cloud/lake.py.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from credit.cloud.lake import PARITY_QUERIES, local_connection  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "databricks" / "expected_control_queries.json"

QUERIES = {
    "dev_totals": "SELECT count(*) AS loans, sum(default_24m) AS defaults FROM features_dev",
    **{name: sql for name, sql in PARITY_QUERIES if name != "dev_split_counts"},
}


def main() -> None:
    con = local_connection()
    out = {}
    for name, sql in QUERIES.items():
        rows = con.execute(sql).fetchall()
        out[name] = {"sql": sql, "rows": [[None if v is None else str(v) for v in r] for r in rows]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(out)} queries)")
    for name, v in out.items():
        print(" ", name, v["rows"][:2])


if __name__ == "__main__":
    main()
