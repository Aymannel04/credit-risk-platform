"""Checks that read the FILES a step produced (so they also protect a reused, not rebuilt, result).

Each function returns a list of problems; an empty list means the check passed. They never print or return label
counts of the fresh vintages (those stay locked until the exam).
"""
from pathlib import Path

import duckdb

from credit.freddie import features as ft
from credit.freddie import fresh, staging
from credit.serving.model_file import load_model, score_loan

GOLDEN_LOAN = {
    "credit_score": 700.0, "dti": 44.0, "rate_spread": 0.55, "ltv": 85.0, "cltv": 85.0, "several_borrowers": 0.0,
    "mi_pct": 25.0, "orig_term": 360.0, "purpose": "P",
}
GOLDEN_SCORE, GOLDEN_TOLERANCE = 553.3, 0.2  # a deliberate model change must update these (and the decision log)


def check_raw(raw_dir: Path, years: list[int]) -> list[str]:
    problems = []
    for y in years:
        for kind in ("orig", "perf"):
            f = raw_dir / f"{kind}_{y}.parquet"
            if not f.exists():
                problems.append(f"missing {f.name}")
            elif duckdb.sql(f"SELECT count(*) FROM read_parquet('{f.as_posix()}')").fetchone()[0] == 0:
                problems.append(f"{f.name} is empty")
    return problems


def check_staging(stg_dir: Path, years: list[int]) -> list[str]:
    """Re-run the staging data checks (keys, ranges, leakage, label sanity) on the written files, year by year."""
    problems = []
    for y in years:
        orig, label = stg_dir / f"stg_orig_{y}.parquet", stg_dir / f"stg_label_{y}.parquet"
        if not (orig.exists() and label.exists()):
            problems.append(f"{y}: staged files missing")
            continue
        con = duckdb.connect()
        con.execute(f"CREATE TABLE stg_orig AS SELECT * FROM read_parquet('{orig.as_posix()}')")
        con.execute(f"CREATE TABLE stg_label AS SELECT * FROM read_parquet('{label.as_posix()}')")
        problems += [f"{y}: {p}" for p in staging.run_checks(con)]
        con.close()
    return problems


def check_features(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing {path.name}"]
    con = duckdb.connect()
    con.execute(f"CREATE TABLE features AS SELECT * FROM read_parquet('{path.as_posix()}')")
    return ft.check(con)


def check_fresh(path: Path) -> list[str]:
    if not path.exists():
        return [f"missing {path.name}"]
    con = duckdb.connect()
    con.execute(f"CREATE TABLE fresh AS SELECT * FROM read_parquet('{path.as_posix()}')")
    return fresh.check_fresh(con)


def check_model(path: Path) -> list[str]:
    """The model file must be valid and still score the golden loan as agreed."""
    try:
        model = load_model(path)
    except Exception as e:  # noqa: BLE001 - any failure to load is a failed check, reported with its message
        return [f"model file invalid: {e}"]
    out = score_loan(model, GOLDEN_LOAN)
    if abs(out["score"] - GOLDEN_SCORE) > GOLDEN_TOLERANCE:
        return [f"golden loan scores {out['score']:.2f}, expected {GOLDEN_SCORE} +/- {GOLDEN_TOLERANCE}: the model changed"]
    return []
