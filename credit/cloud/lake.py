"""The S3 data lake and Athena: the thin cloud layer of the project.

Local first: every table below already exists as a Parquet file on disk (built and checked by the Dagster pipeline). This module
only (1) copies those files to a private S3 bucket, skipping files that did not change, (2) describes them to Athena
(a CREATE EXTERNAL TABLE built from the Parquet schema itself, so the two can never drift apart) and (3) proves the cloud gives the
same answers as the local DuckDB, by running the same SQL in both and comparing the results.

Nothing here creates AWS resources: the bucket, the Glue database and the Athena workgroup come from infra/04_create_lake.ps1,
which the owner runs. The bucket name contains the account number, so it is computed at run time and never written to a file.

The fresh (exam) vintages are uploaded as files, but the parity queries on them never touch a label column.
"""
import hashlib
import time
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

REGION = "eu-north-1"
PROFILE = "credit-admin"
DATABASE = "credit_lake"
WORKGROUP = "credit-risk"
BUCKET_PREFIX = "credit-risk-lake-"
ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data" / "interim"
QUERY_TIMEOUT_SECONDS = 180


class LakeError(RuntimeError):
    pass


@dataclass(frozen=True)
class LakeTable:
    """One Athena table = one folder (prefix) in S3 holding Parquet files that all share the same columns."""

    name: str
    prefix: str  # folder inside the bucket, ends with "/"
    folder: str  # folder under data/interim/
    pattern: str  # which files in it


TABLES = (
    LakeTable("raw_orig", "lake/raw_orig/", "raw", "orig_*.parquet"),
    LakeTable("raw_perf", "lake/raw_perf/", "raw", "perf_*.parquet"),
    LakeTable("features_dev", "lake/features_dev/", "features", "features.parquet"),
    LakeTable("features_fresh", "lake/features_fresh/", "features_fresh", "features_fresh.parquet"),
)


def local_files(table: LakeTable, interim: Path = INTERIM) -> list[Path]:
    return sorted((interim / table.folder).glob(table.pattern))


def make_session(profile: str = PROFILE):
    import boto3

    return boto3.Session(profile_name=profile, region_name=REGION)


def bucket_name(session) -> str:
    """credit-risk-lake-<account number>. Bucket names are global, the account number makes ours unique. Never written to a file."""
    account = session.client("sts").get_caller_identity()["Account"]
    return f"{BUCKET_PREFIX}{account}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


# ---------- upload ----------

@dataclass(frozen=True)
class UploadItem:
    path: Path
    key: str
    sha256: str
    action: str  # "upload" or "skip"
    size: int


def _remote_sha(s3, bucket: str, key: str) -> str | None:
    """The sha256 we stored in the object's metadata when we uploaded it (None if the object does not exist or has none)."""
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except s3.exceptions.ClientError as e:
        if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
            return None
        raise
    return head.get("Metadata", {}).get("sha256")


def plan_upload(s3, bucket: str, tables=TABLES, interim: Path = INTERIM) -> tuple[list[UploadItem], list[str]]:
    """What would be uploaded. Also returns S3 keys that sit in a table folder but match no local file (they would be read by Athena)."""
    items, unexpected = [], []
    for t in tables:
        files = local_files(t, interim)
        if not files:
            raise LakeError(f"no local file for table {t.name} in {interim / t.folder} (run the pipeline first)")
        wanted = set()
        for f in files:
            key = t.prefix + f.name
            wanted.add(key)
            sha = sha256_file(f)
            action = "skip" if _remote_sha(s3, bucket, key) == sha else "upload"
            items.append(UploadItem(f, key, sha, action, f.stat().st_size))
        listed = s3.list_objects_v2(Bucket=bucket, Prefix=t.prefix)
        unexpected += [o["Key"] for o in listed.get("Contents", []) if o["Key"] not in wanted]
    return items, unexpected


def upload(s3, bucket: str, items: list[UploadItem]) -> int:
    """Upload the items marked "upload"; returns how many were sent. The sha256 goes into the object's metadata (the skip rule)."""
    sent = 0
    for it in items:
        if it.action != "upload":
            continue
        s3.upload_file(str(it.path), bucket, it.key, ExtraArgs={"Metadata": {"sha256": it.sha256}, "ServerSideEncryption": "AES256"})
        sent += 1
    return sent


def verify_uploaded(s3, bucket: str, items: list[UploadItem]) -> list[str]:
    """Problems (empty = all good): every local file is in S3 with the same size and the same sha256."""
    problems = []
    for it in items:
        try:
            head = s3.head_object(Bucket=bucket, Key=it.key)
        except s3.exceptions.ClientError:
            problems.append(f"{it.key}: missing in S3")
            continue
        if head["ContentLength"] != it.size:
            problems.append(f"{it.key}: size {head['ContentLength']} in S3, {it.size} locally")
        if head.get("Metadata", {}).get("sha256") != it.sha256:
            problems.append(f"{it.key}: checksum differs from the local file")
    return problems


# ---------- tables ----------

_TYPE_MAP = {"VARCHAR": "string", "INTEGER": "int", "BIGINT": "bigint", "SMALLINT": "smallint", "TINYINT": "tinyint",
             "DOUBLE": "double", "FLOAT": "float", "DATE": "date", "BOOLEAN": "boolean", "TIMESTAMP": "timestamp"}


def athena_type(duck_type: str) -> str:
    t = duck_type.upper()
    if t.startswith("DECIMAL"):
        return t.lower()
    if t in _TYPE_MAP:
        return _TYPE_MAP[t]
    raise LakeError(f"no Athena type known for the DuckDB type {duck_type}")


def create_table_sql(table: LakeTable, bucket: str, interim: Path = INTERIM) -> str:
    """CREATE EXTERNAL TABLE from the Parquet schema of the first local file (all files of a table share it)."""
    first = local_files(table, interim)[0]
    cols = duckdb.sql(f"DESCRIBE SELECT * FROM read_parquet('{first.as_posix()}')").fetchall()
    body = ",\n  ".join(f"`{name}` {athena_type(duck_type)}" for name, duck_type, *_ in cols)
    return (f"CREATE EXTERNAL TABLE IF NOT EXISTS {DATABASE}.{table.name} (\n  {body}\n)\n"
            f"STORED AS PARQUET\nLOCATION 's3://{bucket}/{table.prefix}'\nTBLPROPERTIES ('parquet.compression'='ZSTD')")


# ---------- Athena ----------

@dataclass
class QueryResult:
    rows: list[tuple]
    bytes_scanned: int
    engine_ms: int


def run_query(athena, sql: str, database: str = DATABASE, workgroup: str = WORKGROUP, timeout: int = QUERY_TIMEOUT_SECONDS) -> QueryResult:
    """Run one query in the workgroup (its scan cap and result location apply) and wait. Raises LakeError with AWS's reason on failure."""
    qid = athena.start_query_execution(QueryString=sql, QueryExecutionContext={"Database": database}, WorkGroup=workgroup)["QueryExecutionId"]
    start = time.monotonic()
    while True:
        q = athena.get_query_execution(QueryExecutionId=qid)["QueryExecution"]
        state = q["Status"]["State"]
        if state == "SUCCEEDED":
            break
        if state in ("FAILED", "CANCELLED"):
            raise LakeError(f"query {state}: {q['Status'].get('StateChangeReason', 'no reason given')}")
        if time.monotonic() - start > timeout:
            athena.stop_query_execution(QueryExecutionId=qid)
            raise LakeError(f"query still running after {timeout} s, stopped")
        time.sleep(1)
    rows = []
    for page in athena.get_paginator("get_query_results").paginate(QueryExecutionId=qid):
        for r in page["ResultSet"]["Rows"]:
            rows.append(tuple(c.get("VarCharValue") for c in r["Data"]))
    stats = q.get("Statistics", {})
    has_header = rows and not sql.lstrip().upper().startswith(("CREATE", "DROP", "ALTER"))  # a SELECT's first row is the column names
    return QueryResult(rows[1:] if has_header else [], int(stats.get("DataScannedInBytes", 0)), int(stats.get("EngineExecutionTimeInMillis", 0)))


def create_tables(athena, bucket: str, tables=TABLES, interim: Path = INTERIM) -> list[str]:
    done = []
    for t in tables:
        run_query(athena, create_table_sql(t, bucket, interim))
        done.append(t.name)
    return done


# ---------- parity: the same SQL in DuckDB (local files) and Athena (S3) ----------

# No label column of the fresh vintages appears in the fresh queries (a test enforces it): structure only.
PARITY_QUERIES = (
    ("dev_split_counts",
     "SELECT split, count(*) AS loans, sum(default_24m) AS defaults FROM features_dev GROUP BY split ORDER BY split"),
    ("dev_vintage_sums",
     "SELECT vintage_year, count(*) AS loans, sum(credit_score) AS sum_score, sum(dti) AS sum_dti, sum(orig_term) AS sum_term, "
     "round(avg(rate_spread), 6) AS avg_spread FROM features_dev GROUP BY vintage_year ORDER BY vintage_year"),
    ("fresh_structure",
     "SELECT vintage_year, count(*) AS loans, count(DISTINCT loan_seq) AS distinct_loans, sum(credit_score) AS sum_score, "
     "min(first_payment_date) AS first_payment_min FROM features_fresh GROUP BY vintage_year ORDER BY vintage_year"),
    ("raw_orig_loans", "SELECT count(*) AS n_rows, count(DISTINCT loan_seq) AS loans FROM raw_orig"),
    ("raw_perf_rows", "SELECT count(*) AS monthly_rows FROM raw_perf"),
    ("raw_perf_loans", "SELECT count(DISTINCT loan_seq) AS loans FROM raw_perf"),
)
FRESH_LABEL_WORDS = ("default", "label", "observable")


def local_connection(tables=TABLES, interim: Path = INTERIM) -> duckdb.DuckDBPyConnection:
    """DuckDB with one view per lake table, named like the Athena tables, over the local Parquet files."""
    con = duckdb.connect()
    for t in tables:
        paths = ", ".join(f"'{p.as_posix()}'" for p in local_files(t, interim))
        con.execute(f"CREATE VIEW {t.name} AS SELECT * FROM read_parquet([{paths}])")
    return con


def _same(local, remote: str | None, rel: float = 1e-9, abs_tol: float = 1e-6) -> bool:
    if local is None:
        return remote is None
    if remote is None:
        return False
    if isinstance(local, (int, float, Decimal)) and not isinstance(local, bool):
        try:
            a, b = float(local), float(remote)
        except ValueError:
            return False
        return abs(a - b) <= max(abs_tol, rel * max(abs(a), abs(b)))
    if isinstance(local, (date, datetime)):
        return str(local)[:10] == str(remote)[:10]
    return str(local) == str(remote)


def compare_rows(local_rows: list[tuple], remote_rows: list[tuple]) -> list[str]:
    """Differences between the local and the Athena answer (empty list = identical, floats within a tiny tolerance)."""
    if len(local_rows) != len(remote_rows):
        return [f"{len(local_rows)} rows locally, {len(remote_rows)} in Athena"]
    diffs = []
    for i, (lr, rr) in enumerate(zip(local_rows, remote_rows, strict=True)):
        if len(lr) != len(rr):
            diffs.append(f"row {i}: {len(lr)} columns locally, {len(rr)} in Athena")
            continue
        for j, (a, b) in enumerate(zip(lr, rr, strict=True)):
            if not _same(a, b):
                diffs.append(f"row {i}, column {j}: local {a!r}, Athena {b!r}")
    return diffs


def run_parity(athena, con: duckdb.DuckDBPyConnection, queries=PARITY_QUERIES) -> list[dict]:
    results = []
    for name, sql in queries:
        local_rows = con.execute(sql).fetchall()
        remote = run_query(athena, sql)
        diffs = compare_rows(local_rows, remote.rows)
        results.append({"name": name, "sql": sql, "passed": not diffs, "differences": diffs[:5], "rows": len(local_rows),
                        "first_row_local": [str(v) for v in local_rows[0]] if local_rows else [],
                        "athena_bytes_scanned": remote.bytes_scanned, "athena_engine_ms": remote.engine_ms})
    return results


def parity_markdown(results: list[dict], uploaded_files: int, uploaded_bytes: int) -> str:
    lines = ["# Data lake parity: the same SQL on local DuckDB and on Athena over S3", "",
             f"{sum(r['passed'] for r in results)} of {len(results)} queries gave the same answer in both. "
             f"Lake: {uploaded_files} Parquet files, {uploaded_bytes / 1e6:.1f} MB in total.", "",
             "| Query | Same answer | Rows | Athena scanned | Athena engine time |", "|---|---|---|---|---|"]
    for r in results:
        lines.append(f"| `{r['name']}` | {'yes' if r['passed'] else 'NO'} | {r['rows']} | {r['athena_bytes_scanned'] / 1e6:.2f} MB | {r['athena_engine_ms']} ms |")
    lines += ["", "Bytes scanned is what Athena bills (about 5 USD per TB, to confirm for the region in the console). "
              "Floats are compared with a tolerance of 1e-9 (relative) / 1e-6 (absolute); counts and sums must be identical.", ""]
    for r in results:
        if not r["passed"]:
            lines.append(f"- `{r['name']}` differences: {r['differences']}")
    return "\n".join(lines) + "\n"
