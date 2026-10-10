"""One command, whole pipeline.   .venv/Scripts/python -m pipeline.run [--full]

Runs every asset in order, skipping steps whose outputs are up to date (unless --full), and prints one line per asset
and per check. Exit code 1 if anything failed.
"""
import os
import sys

from dagster import DagsterEventType, materialize

from pipeline.definitions import EXECUTABLE


def main(argv: list[str]) -> int:
    if "--full" in argv:
        os.environ["PIPELINE_FULL"] = "1"
    result = materialize(EXECUTABLE, raise_on_error=False)
    for ev in result.get_asset_materialization_events():
        meta = ev.event_specific_data.materialization.metadata
        status = meta["status"].value if "status" in meta else ""
        print(f"asset  {ev.asset_key.to_user_string():<16} done {status}")
    for ev in result.get_asset_check_evaluations():
        print(f"check  {ev.check_name:<40} {'PASSED' if ev.passed else 'FAILED'}")
    for ev in result.filter_events(lambda e: e.event_type == DagsterEventType.STEP_FAILURE):
        print(f"FAILED step {ev.step_key}: {ev.event_specific_data.error.message.strip().splitlines()[-1][:300]}")
    print("PIPELINE OK" if result.success else "PIPELINE FAILED")
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
