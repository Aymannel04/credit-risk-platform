"""The S3 lake layer, tested without AWS: fake S3 and Athena objects, tiny Parquet files made on the spot."""
import re
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest
from botocore.exceptions import ClientError

from credit.cloud import lake

REPO = Path(__file__).resolve().parents[1]


# ---------- fakes ----------

class FakeS3:
    """Just enough of the S3 client: head_object, list_objects_v2, upload_file."""

    def __init__(self):
        self.objects = {}  # key -> {"size": int, "metadata": dict}
        self.uploads = []
        self.exceptions = SimpleNamespace(ClientError=ClientError)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject")
        o = self.objects[Key]
        return {"ContentLength": o["size"], "Metadata": o["metadata"]}

    def list_objects_v2(self, Bucket, Prefix):
        keys = [k for k in self.objects if k.startswith(Prefix)]
        return {"Contents": [{"Key": k} for k in keys]} if keys else {}

    def upload_file(self, filename, bucket, key, ExtraArgs=None):
        self.uploads.append((key, ExtraArgs))
        self.objects[key] = {"size": Path(filename).stat().st_size, "metadata": (ExtraArgs or {}).get("Metadata", {})}


class FakeAthena:
    """Runs the SQL in its own DuckDB over the given views (standing in for 'the cloud') and answers like Athena: everything as text."""

    def __init__(self, con, tamper=None, states=("SUCCEEDED",), reason="boom"):
        self.con, self.tamper, self.states, self.reason = con, tamper, list(states), reason
        self.queries, self.last = [], None

    def start_query_execution(self, QueryString, QueryExecutionContext, WorkGroup):
        self.queries.append((QueryString, QueryExecutionContext, WorkGroup))
        self.last = QueryString
        return {"QueryExecutionId": "q1"}

    def get_query_execution(self, QueryExecutionId):
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        status = {"State": state}
        if state in ("FAILED", "CANCELLED"):
            status["StateChangeReason"] = self.reason
        return {"QueryExecution": {"Status": status, "Statistics": {"DataScannedInBytes": 1234, "EngineExecutionTimeInMillis": 56}}}

    def stop_query_execution(self, QueryExecutionId):
        self.stopped = True

    def get_paginator(self, name):
        assert name == "get_query_results"
        outer = self

        class P:
            def paginate(self, QueryExecutionId):
                cur = outer.con.execute(outer.last)
                header = {"Data": [{"VarCharValue": d[0]} for d in cur.description]}
                rows = [{"Data": [{} if v is None else {"VarCharValue": str(v)} for v in r]} for r in cur.fetchall()]
                if outer.tamper:
                    rows = outer.tamper(rows)
                return [{"ResultSet": {"Rows": [header, *rows]}}]

        return P()


@pytest.fixture
def interim(tmp_path):
    """A tiny copy of the four lake tables, with the columns the parity queries use."""
    d = tmp_path / "interim"
    for sub in ("raw", "features", "features_fresh"):
        (d / sub).mkdir(parents=True)

    def write(path, select):
        duckdb.sql(f"COPY ({select}) TO '{path.as_posix()}' (FORMAT PARQUET)")

    write(d / "features" / "features.parquet",
          "SELECT 'L' || i AS loan_seq, 2012 + (i % 2) AS vintage_year, CAST(650 + i AS INTEGER) AS credit_score, CAST(30 + i AS INTEGER) AS dti, "
          "CAST(360 AS INTEGER) AS orig_term, CASE WHEN i = 3 THEN NULL ELSE 0.1 * i END AS rate_spread, CAST(i % 2 AS INTEGER) AS default_24m, "
          "CASE WHEN i < 6 THEN 'train' ELSE 'test' END AS split FROM range(10) t(i)")
    write(d / "features_fresh" / "features_fresh.parquet",
          "SELECT 'F' || i AS loan_seq, 2010 + 4 * (i % 2) AS vintage_year, CAST(700 + i AS INTEGER) AS credit_score, DATE '2010-03-01' + CAST(i AS INTEGER) AS first_payment_date, "
          "CAST(1 AS INTEGER) AS default_24m, CAST(2.0 AS DECIMAL(2,1)) AS several_borrowers FROM range(6) t(i)")
    for y in (2012, 2016):
        write(d / "raw" / f"orig_{y}.parquet", f"SELECT 'L{y}_' || i AS loan_seq, 'x' AS credit_score FROM range(4) t(i)")
        write(d / "raw" / f"perf_{y}.parquet", f"SELECT 'L{y}_' || (i % 4) AS loan_seq, 'x' AS delinq_status FROM range(12) t(i)")
    return d


# ---------- names and layout ----------

def test_bucket_name_is_prefix_plus_account_and_never_a_constant():
    session = SimpleNamespace(client=lambda name: SimpleNamespace(get_caller_identity=lambda: {"Account": "999999999999"}))
    assert lake.bucket_name(session) == "credit-risk-lake-999999999999"
    assert not re.search(r"\d{12}", Path(lake.__file__).read_text(encoding="utf-8")), "no account number in the source"


def test_tables_have_distinct_folders_inside_lake_prefix():
    prefixes = [t.prefix for t in lake.TABLES]
    assert len(set(prefixes)) == len(prefixes) and all(p.startswith("lake/") and p.endswith("/") for p in prefixes)
    assert {t.name for t in lake.TABLES} == {"raw_orig", "raw_perf", "features_dev", "features_fresh"}


def test_local_files_finds_the_right_files(interim):
    names = {t.name: [p.name for p in lake.local_files(t, interim)] for t in lake.TABLES}
    assert names["raw_orig"] == ["orig_2012.parquet", "orig_2016.parquet"]
    assert names["raw_perf"] == ["perf_2012.parquet", "perf_2016.parquet"]
    assert names["features_dev"] == ["features.parquet"] and names["features_fresh"] == ["features_fresh.parquet"]


# ---------- upload ----------

def test_plan_upload_sends_new_and_changed_files_and_skips_unchanged_ones(interim):
    s3 = FakeS3()
    items, unexpected = lake.plan_upload(s3, "b", interim=interim)
    assert {i.action for i in items} == {"upload"} and not unexpected
    assert len(items) == 6
    lake.upload(s3, "b", items)
    items2, _ = lake.plan_upload(s3, "b", interim=interim)
    assert {i.action for i in items2} == {"skip"}, "second run must send nothing"
    # change one local file: only that one is sent again
    f = interim / "features" / "features.parquet"
    duckdb.sql(f"COPY (SELECT * FROM read_parquet('{f.as_posix()}') WHERE split = 'train') TO '{(interim / 'tmp.parquet').as_posix()}' (FORMAT PARQUET)")
    (interim / "tmp.parquet").replace(f)
    items3, _ = lake.plan_upload(s3, "b", interim=interim)
    assert {i.key for i in items3 if i.action == "upload"} == {"lake/features_dev/features.parquet"}


def test_upload_sets_checksum_metadata_and_encryption(interim):
    s3 = FakeS3()
    items, _ = lake.plan_upload(s3, "b", interim=interim)
    assert lake.upload(s3, "b", items) == 6
    for key, extra in s3.uploads:
        assert extra["ServerSideEncryption"] == "AES256" and re.fullmatch(r"[0-9a-f]{64}", extra["Metadata"]["sha256"]), key


def test_unexpected_remote_files_are_reported(interim):
    s3 = FakeS3()
    s3.objects["lake/raw_perf/perf_1999.parquet"] = {"size": 1, "metadata": {}}
    _, unexpected = lake.plan_upload(s3, "b", interim=interim)
    assert unexpected == ["lake/raw_perf/perf_1999.parquet"]


def test_missing_local_table_is_an_error_not_a_silent_skip(tmp_path):
    with pytest.raises(lake.LakeError, match="run the pipeline"):
        lake.plan_upload(FakeS3(), "b", interim=tmp_path)


def test_verify_uploaded_catches_missing_size_and_checksum_problems(interim):
    s3 = FakeS3()
    items, _ = lake.plan_upload(s3, "b", interim=interim)
    assert "missing in S3" in lake.verify_uploaded(s3, "b", items)[0]
    lake.upload(s3, "b", items)
    assert lake.verify_uploaded(s3, "b", items) == []
    key = items[0].key
    s3.objects[key]["size"] += 1
    s3.objects[items[1].key]["metadata"] = {"sha256": "0" * 64}
    problems = lake.verify_uploaded(s3, "b", items)
    assert any("size" in p and key in p for p in problems) and any("checksum" in p for p in problems)


# ---------- tables (Athena DDL) ----------

def test_athena_types():
    assert [lake.athena_type(t) for t in ("VARCHAR", "INTEGER", "DOUBLE", "DATE", "DECIMAL(2,1)")] == ["string", "int", "double", "date", "decimal(2,1)"]
    with pytest.raises(lake.LakeError):
        lake.athena_type("STRUCT(a INTEGER)")


def test_create_table_sql_follows_the_parquet_schema(interim):
    sql = lake.create_table_sql(next(t for t in lake.TABLES if t.name == "features_fresh"), "mybucket", interim)
    assert sql.startswith("CREATE EXTERNAL TABLE IF NOT EXISTS credit_lake.features_fresh")
    assert "`first_payment_date` date" in sql and "`several_borrowers` decimal(2,1)" in sql and "`loan_seq` string" in sql
    assert "STORED AS PARQUET" in sql and "LOCATION 's3://mybucket/lake/features_fresh/'" in sql and "ZSTD" in sql


@pytest.mark.skipif(not (lake.INTERIM / "features" / "features.parquet").exists(), reason="needs the local pipeline output")
def test_real_tables_all_map_to_athena_types():
    for t in lake.TABLES:
        sql = lake.create_table_sql(t, "b")
        assert sql.count("`") % 2 == 0 and "LOCATION" in sql


# ---------- running queries ----------

def test_run_query_drops_the_header_and_reports_scan_size():
    con = duckdb.connect()
    r = lake.run_query(FakeAthena(con), "SELECT 1 AS a, 'x' AS b")
    assert r.rows == [("1", "x")] and r.bytes_scanned == 1234 and r.engine_ms == 56


def test_run_query_uses_the_capped_workgroup_and_database():
    athena = FakeAthena(duckdb.connect())
    lake.run_query(athena, "SELECT 1")
    _, context, workgroup = athena.queries[0]
    assert workgroup == "credit-risk" and context == {"Database": "credit_lake"}


def test_a_cancelled_query_raises_with_the_reason():
    athena = FakeAthena(duckdb.connect(), states=("RUNNING", "CANCELLED"), reason="Query exhausted resources: scanned more than the limit")
    with pytest.raises(lake.LakeError, match="CANCELLED.*limit"):
        lake.run_query(athena, "SELECT 1", timeout=5)


def test_a_query_that_never_finishes_is_stopped(monkeypatch):
    athena = FakeAthena(duckdb.connect(), states=("RUNNING",))
    clock = iter(range(0, 1000, 100))
    monkeypatch.setattr(lake.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(lake.time, "sleep", lambda s: None)
    with pytest.raises(lake.LakeError, match="stopped"):
        lake.run_query(athena, "SELECT 1", timeout=150)
    assert athena.stopped


def test_create_tables_issues_one_ddl_per_table(interim):
    class DDLAthena(FakeAthena):
        def get_paginator(self, name):
            class P:
                def paginate(self, QueryExecutionId):
                    return [{"ResultSet": {"Rows": []}}]
            return P()

    athena = DDLAthena(duckdb.connect())
    assert lake.create_tables(athena, "b", interim=interim) == ["raw_orig", "raw_perf", "features_dev", "features_fresh"]
    assert all(q[0].startswith("CREATE EXTERNAL TABLE") for q in athena.queries) and len(athena.queries) == 4


# ---------- comparing answers ----------

def test_compare_rows_accepts_text_numbers_dates_and_tiny_float_noise():
    import datetime
    import decimal

    local = [(1, 2.5, "a", datetime.date(2010, 3, 1), None, decimal.Decimal("2.0"))]
    assert lake.compare_rows(local, [("1", "2.5000000001", "a", "2010-03-01", None, "2.0")]) == []


def test_compare_rows_finds_every_kind_of_difference():
    assert lake.compare_rows([(1,)], [("2",)])
    assert lake.compare_rows([(1,)], [(None,)])
    assert lake.compare_rows([(None,)], [("1",)])
    assert lake.compare_rows([("a",)], [("b",)])
    assert lake.compare_rows([(1,), (2,)], [("1",)])
    assert lake.compare_rows([(1, 2)], [("1",)])
    assert lake.compare_rows([(1.0,)], [("not a number",)])
    assert lake.compare_rows([(1000000,)], [("1000001",)]), "counts must be exactly equal, not 'close'"


# ---------- parity ----------

def test_parity_queries_use_known_tables_and_never_a_label_of_the_fresh_vintages():
    tables = {t.name for t in lake.TABLES}
    for name, sql in lake.PARITY_QUERIES:
        used = set(re.findall(r"\bFROM (\w+)", sql))
        assert used <= tables, name
        if "features_fresh" in used:
            assert not any(w in sql.lower() for w in lake.FRESH_LABEL_WORDS), f"{name} touches a locked label"
    assert len({n for n, _ in lake.PARITY_QUERIES}) == len(lake.PARITY_QUERIES)


def test_parity_passes_when_cloud_and_local_agree(interim):
    con = lake.local_connection(interim=interim)
    results = lake.run_parity(FakeAthena(lake.local_connection(interim=interim)), con)
    assert len(results) == len(lake.PARITY_QUERIES) and all(r["passed"] for r in results), [r for r in results if not r["passed"]]
    assert all(r["athena_bytes_scanned"] == 1234 for r in results)


def test_parity_fails_when_a_single_number_differs(interim):
    def tamper(rows):
        rows[0]["Data"][-1] = {"VarCharValue": "999999"}  # change the last column of the first row of every answer
        return rows

    con = lake.local_connection(interim=interim)
    results = lake.run_parity(FakeAthena(lake.local_connection(interim=interim), tamper=tamper), con)
    assert not any(r["passed"] for r in results)
    assert all(r["differences"] for r in results)


def test_parity_markdown_states_the_verdict_and_holds_no_account_number(interim):
    results = lake.run_parity(FakeAthena(lake.local_connection(interim=interim)), lake.local_connection(interim=interim))
    md = lake.parity_markdown(results, 6, 123456)
    assert f"{len(results)} of {len(results)} queries gave the same answer" in md and "0.1 MB in total" in md
    assert not re.search(r"(?<!\d)\d{12}(?!\d)", md)


def test_a_committed_parity_report_has_no_account_number_or_bucket_name():
    for name in ("lake_parity.json", "lake_parity.md"):
        f = REPO / "results" / name
        if f.exists():
            text = f.read_text(encoding="utf-8")
            assert not re.search(r"(?<!\d)\d{12}(?!\d)", text) and "credit-risk-lake-" not in text and "s3://" not in text
