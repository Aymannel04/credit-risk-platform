"""The Dagster pipeline: freddie_zips -> raw_parquet -> staging -> features -> (data_lake) and scorecard_v2.

    dagster dev                                   # opens the picture of the pipeline in the browser
    dagster asset materialize --select '*'        # runs everything, skipping what is already up to date
    PIPELINE_FULL=1 dagster asset materialize --select '*'      # forces a full rebuild
or, simpler:  python -m pipeline.run [--full]

Each asset has a BLOCKING check: if it fails, the assets that depend on it do not run.
"""
from dagster import (
    AssetCheckResult,
    AssetSpec,
    Definitions,
    MaterializeResult,
    MetadataValue,
    asset,
    asset_check,
    in_process_executor,
)

from credit.freddie import features as ft
from credit.freddie import fresh, load
from credit.serving import export
from pipeline import checks, steps

freddie_zips = AssetSpec(
    "freddie_zips", description="Freddie Mac sample zips downloaded by hand into data/raw/freddie/ (git-ignored, never redistributed).")


def _years_md(per_year: dict) -> dict:
    """Metadata for a per-year step: a one-line status plus the detail per year."""
    rebuilt = sorted(y for y, v in per_year.items() if v["status"] == "rebuilt")
    status = f"rebuilt {rebuilt}" if rebuilt else "reused"
    return {"status": status, "years": MetadataValue.json({str(y): v for y, v in per_year.items()})}


@asset(deps=[freddie_zips], group_name="raw", description="Zips converted to Parquet, every column kept as text (the data as received).")
def raw_parquet() -> MaterializeResult:
    return MaterializeResult(metadata=_years_md(steps.raw_step()))


@asset_check(asset=raw_parquet, blocking=True)
def raw_files_present_and_not_empty() -> AssetCheckResult:
    problems = checks.check_raw(load.OUT_DIR, steps.ALL_YEARS)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[raw_parquet], group_name="staging", description="Development vintages: typed tables, labels, data checks.")
def staging_dev() -> MaterializeResult:
    return MaterializeResult(metadata=_years_md(steps.staging_step(steps.DEV_YEARS, ft.STG_DIR)))


@asset_check(asset=staging_dev, blocking=True)
def staging_dev_data_checks() -> AssetCheckResult:
    problems = checks.check_staging(ft.STG_DIR, steps.DEV_YEARS)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[raw_parquet], group_name="staging",
       description="Fresh (exam) vintages, kept in a SEPARATE folder so they cannot enter the development table. Default counts are never shown.")
def staging_fresh() -> MaterializeResult:
    return MaterializeResult(metadata=_years_md(steps.staging_step(steps.FRESH_YEARS, fresh.STG_FRESH)))


@asset_check(asset=staging_fresh, blocking=True)
def staging_fresh_data_checks() -> AssetCheckResult:
    problems = checks.check_staging(fresh.STG_FRESH, steps.FRESH_YEARS)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[staging_dev], group_name="features", description="The table the models learn from: exclusions, rate spread, hash-based splits.")
def features_dev() -> MaterializeResult:
    r = steps.features_step()
    return MaterializeResult(metadata={"status": r["status"], "waterfall": MetadataValue.json(r["report"]["waterfall"])})


@asset_check(asset=features_dev, blocking=True)
def features_dev_checks() -> AssetCheckResult:
    problems = checks.check_features(ft.OUT_DIR / "features.parquet")
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[staging_fresh], group_name="features", description="Same table for the fresh vintages (structure only; labels locked until the exam).")
def features_fresh() -> MaterializeResult:
    r = steps.fresh_step()
    return MaterializeResult(metadata={"status": r["status"], "waterfall": MetadataValue.json(r["waterfall"])})


@asset_check(asset=features_fresh, blocking=True)
def features_fresh_checks() -> AssetCheckResult:
    problems = checks.check_fresh(fresh.FRESH_PATH)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[raw_parquet, features_dev, features_fresh], group_name="lake",
       description="The Parquet tables copied to the private S3 lake (only when CREDIT_LAKE=1; checksum-skipped when unchanged). Athena reads them there.")
def data_lake() -> MaterializeResult:
    return MaterializeResult(metadata=steps.lake_step())


@asset_check(asset=data_lake, blocking=True)
def data_lake_matches_local() -> AssetCheckResult:
    problems = checks.check_lake(steps.lake_enabled())
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[features_dev], group_name="model", description="The adopted v2 scorecard as a small JSON file (models/scorecard_v2.json).")
def scorecard_v2() -> MaterializeResult:
    r = steps.model_step()
    return MaterializeResult(metadata={"status": r["status"], "model_id": r["model_id"], "bytes": r["bytes"]})


@asset_check(asset=scorecard_v2, blocking=True)
def scorecard_v2_valid_and_golden_loan() -> AssetCheckResult:
    problems = checks.check_model(export.MODEL_PATH)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


@asset(deps=[features_dev, features_fresh, scorecard_v2], group_name="monitoring",
       description="Drift per vintage, observed vs predicted level, simulated shifts (fire drills) and the pre-registered recalibration experiment.")
def monitoring_report() -> MaterializeResult:
    r = steps.monitoring_step()
    return MaterializeResult(metadata={k: v for k, v in r.items()})


@asset_check(asset=monitoring_report, blocking=True)
def monitoring_self_test_passed() -> AssetCheckResult:
    problems = checks.check_monitoring(report_json_path(), export.MODEL_PATH)
    return AssetCheckResult(passed=not problems, metadata={"problems": MetadataValue.json(problems)})


def report_json_path():
    from credit.monitoring import report

    return report.RESULTS / "monitoring_report.json"


EXECUTABLE = [
    raw_parquet, staging_dev, staging_fresh, features_dev, features_fresh, data_lake, scorecard_v2, monitoring_report,
    raw_files_present_and_not_empty, staging_dev_data_checks, staging_fresh_data_checks,
    features_dev_checks, features_fresh_checks, data_lake_matches_local, scorecard_v2_valid_and_golden_loan, monitoring_self_test_passed,
]
# one process for all steps: they run one after the other anyway, and a new process per step is slow on Windows
defs = Definitions(assets=[freddie_zips, *EXECUTABLE], executor=in_process_executor)
