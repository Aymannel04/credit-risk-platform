"""Load the features table and prepare it for models.

Safety rule: the test splits (the real exams) cannot be loaded by accident. `load` refuses them
unless `allow_test=True` is passed, which only the final evaluation step should do.
"""
from pathlib import Path

import duckdb
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from credit.freddie.features import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES

ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = ROOT / "data" / "interim" / "features" / "features.parquet"

DEVELOPMENT_SPLITS = ("train", "calibration", "validation")
TEST_SPLITS = ("test_in_time", "test_oot_2019", "test_oot_2022")
TARGET = "default_24m"


def load(splits, path: Path = FEATURES_PATH, allow_test: bool = False) -> pd.DataFrame:
    """Rows of the given split names. Test splits are refused unless allow_test=True."""
    splits = [splits] if isinstance(splits, str) else list(splits)
    unknown = set(splits) - set(DEVELOPMENT_SPLITS) - set(TEST_SPLITS)
    if unknown:
        raise ValueError(f"unknown split(s): {sorted(unknown)}")
    locked = set(splits) & set(TEST_SPLITS)
    if locked and not allow_test:
        raise PermissionError(
            f"{sorted(locked)} are test splits (the real exams): they are locked until the final evaluation"
        )
    names = ", ".join(f"'{s}'" for s in splits)
    return duckdb.sql(
        f"SELECT * FROM read_parquet('{path.as_posix()}') WHERE split IN ({names})"
    ).df()


def xy(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Model inputs (day-one features only) and the label."""
    return df[FEATURES].copy(), df[TARGET].astype(int)


def make_preprocessor() -> ColumnTransformer:
    """Missing numbers -> median + a 'was missing' flag, then scaled; categories -> one-hot columns.

    Categories seen fewer than 50 times in training are grouped together; unseen categories at
    prediction time do not crash (they fall in the grouped column).
    """
    numeric = Pipeline(
        [
            ("impute", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        [
            ("impute", SimpleImputer(strategy="constant", fill_value="missing")),
            ("onehot", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50)),
        ]
    )
    # sparse_threshold=0: ALWAYS output a dense table. XGBoost treats empty cells of a sparse table as
    # MISSING values (not zeros), so training and predicting on different formats gives different
    # models. One dense format everywhere removes that trap (found during the SMOTE ablation).
    return ColumnTransformer(
        [("num", numeric, NUMERIC_FEATURES), ("cat", categorical, CATEGORICAL_FEATURES)],
        sparse_threshold=0.0,
    )
