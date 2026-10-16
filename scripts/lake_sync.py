"""Publish the Parquet tables to the S3 lake, describe them to Athena, and prove the cloud gives the same answers as the local DuckDB.

    aws sso login --profile credit-admin
    .venv/Scripts/python scripts/lake_sync.py upload --dry-run     # shows what would be sent, sends nothing
    .venv/Scripts/python scripts/lake_sync.py upload               # sends only files whose checksum changed
    .venv/Scripts/python scripts/lake_sync.py tables               # CREATE EXTERNAL TABLE for the 4 tables (free: DDL scans no data)
    .venv/Scripts/python scripts/lake_sync.py parity               # same SQL on DuckDB and Athena, writes results/lake_parity.*
    .venv/Scripts/python scripts/lake_sync.py cap-demo             # one query that the workgroup must CANCEL (shows the scan cap works)

The bucket (infra/04_create_lake.ps1) must exist first. Its name contains the account number: it is computed here, printed
nowhere that is saved, and never written to a result file. Exit code 0 = all good, 1 = a problem.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from credit.cloud import lake  # noqa: E402

RESULTS = ROOT / "results"
CAP_DEMO_SQL = "SELECT * FROM raw_perf ORDER BY current_upb"  # reads every column of 250 MB: more than the cap, so it must be cancelled


def _clients(profile: str):
    session = lake.make_session(profile)
    return session, session.client("s3"), session.client("athena")


def cmd_upload(args) -> int:
    session, s3, _ = _clients(args.profile)
    bucket = lake.bucket_name(session)
    items, unexpected = lake.plan_upload(s3, bucket)
    todo = [i for i in items if i.action == "upload"]
    for i in items:
        print(f"  {i.action:<7} {i.key:<48} {i.size / 1e6:9.2f} MB")
    print(f"{len(todo)} to upload ({sum(i.size for i in todo) / 1e6:.1f} MB), {len(items) - len(todo)} unchanged.")
    if unexpected:
        print(f"WARNING: {len(unexpected)} object(s) sit in a table folder but match no local file (Athena would read them): {unexpected}")
    if args.dry_run:
        print("Dry run: nothing was sent.")
        return 0
    sent = lake.upload(s3, bucket, items)
    problems = lake.verify_uploaded(s3, bucket, items)
    print(f"Sent {sent} file(s). Verification: " + ("every file is in S3 with the same size and checksum." if not problems else "PROBLEMS"))
    for p in problems:
        print("  -", p)
    return 1 if (problems or unexpected) else 0


def cmd_tables(args) -> int:
    if args.dry_run:  # offline: only prints the text that would be sent
        for t in lake.TABLES:
            print(lake.create_table_sql(t, "<bucket>"), end="\n\n")
        print("Dry run: nothing was sent to Athena.")
        return 0
    session, _, athena = _clients(args.profile)
    bucket = lake.bucket_name(session)
    print("Created (or already there):", ", ".join(lake.create_tables(athena, bucket)))
    return 0


def cmd_parity(args) -> int:
    session, s3, athena = _clients(args.profile)
    bucket = lake.bucket_name(session)
    items, _ = lake.plan_upload(s3, bucket)
    if any(i.action == "upload" for i in items):
        print("The lake is not up to date: run  scripts/lake_sync.py upload  first.")
        return 1
    results = lake.run_parity(athena, lake.local_connection())
    for r in results:
        print(f"  {'SAME' if r['passed'] else 'DIFFERENT':<9} {r['name']:<18} {r['athena_bytes_scanned'] / 1e6:8.2f} MB scanned  {r['differences']}")
    RESULTS.mkdir(exist_ok=True)
    payload = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), "files": len(items),
               "bytes": sum(i.size for i in items), "all_same": all(r["passed"] for r in results), "queries": results}
    (RESULTS / "lake_parity.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (RESULTS / "lake_parity.md").write_text(lake.parity_markdown(results, len(items), payload["bytes"]), encoding="utf-8")
    print("Wrote results/lake_parity.json and results/lake_parity.md")
    return 0 if payload["all_same"] else 1


def cmd_cap_demo(args) -> int:
    _, _, athena = _clients(args.profile)
    try:
        lake.run_query(athena, CAP_DEMO_SQL)
    except lake.LakeError as e:
        print(f"Cancelled as expected by the workgroup cap: {e}")
        return 0
    print("The query finished: the scan cap did NOT stop it. Check the workgroup settings (infra/04_create_lake.ps1).")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--profile", default=lake.PROFILE)
    sub = p.add_subparsers(dest="command", required=True)
    for name, fn in (("upload", cmd_upload), ("tables", cmd_tables), ("parity", cmd_parity), ("cap-demo", cmd_cap_demo)):
        s = sub.add_parser(name)
        s.add_argument("--dry-run", action="store_true")
        s.set_defaults(fn=fn)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
