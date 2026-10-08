"""Basic tests on the German Credit fixture (no download, no cloud)."""
from pathlib import Path

import pandas as pd
import pytest
from imblearn.over_sampling import SMOTE
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

FIXTURE = Path(__file__).parent / "fixtures" / "german_credit.csv"
SEED = 42


@pytest.fixture(scope="module")
def df() -> pd.DataFrame:
    return pd.read_csv(FIXTURE)


def test_shape_and_target(df):
    assert df.shape == (1000, 21)
    assert set(df["target"].unique()) == {0, 1}
    assert df["target"].mean() == pytest.approx(0.30, abs=0.001)


def test_target_not_in_features(df):
    X = df.drop(columns="target")
    assert "target" not in X.columns


def test_split_has_no_overlap_and_keeps_rate(df):
    X, y = df.drop(columns="target"), df["target"]
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    assert set(X_tr.index).isdisjoint(X_te.index)
    assert len(X_te) == 200
    assert y_te.mean() == pytest.approx(0.30, abs=0.001)
    assert y_tr.mean() == pytest.approx(0.30, abs=0.001)


def test_smote_touches_train_only(df):
    X = df.drop(columns="target").copy()
    y = df["target"]
    for col in X.select_dtypes(include=["object", "str"]).columns:
        X[col] = LabelEncoder().fit_transform(X[col])
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.2, random_state=SEED, stratify=y
    )
    _, y_res = SMOTE(random_state=SEED).fit_resample(X_tr, y_tr)
    assert (y_res == 1).sum() == (y_res == 0).sum() == 560
    assert len(y_te) == 200  # test set is unchanged


def test_encoder_round_trip(df):
    for col in ["checking_account_status", "purpose", "credit_history"]:
        enc = LabelEncoder().fit(df[col])
        back = enc.inverse_transform(enc.transform(df[col]))
        assert list(back) == list(df[col])


def test_no_missing_values(df):
    assert df.isna().sum().sum() == 0
