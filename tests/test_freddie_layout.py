"""Layout tests that need no Freddie Mac data, plus one that runs only if the sample is present."""
import zipfile
from pathlib import Path

import pytest

from credit.freddie import load
from credit.freddie.layout import ORIGINATION_COLUMNS, PERFORMANCE_COLUMNS

ZIP_2016 = Path(__file__).resolve().parents[1] / "data" / "raw" / "freddie" / "sample_2016.zip"


def test_column_names_unique_and_counted():
    assert len(ORIGINATION_COLUMNS) == len(set(ORIGINATION_COLUMNS)) == 31
    assert len(PERFORMANCE_COLUMNS) == len(set(PERFORMANCE_COLUMNS)) == 35


def test_loan_seq_is_the_join_key():
    assert ORIGINATION_COLUMNS[19] == "loan_seq"  # column 20 in the guide
    assert PERFORMANCE_COLUMNS[0] == "loan_seq"  # column 1 in the guide


def test_to_parquet_keeps_text_and_names(tmp_path):
    txt = tmp_path / "mini.txt"
    # one fake performance row: 35 fields, status '00' must stay text, comma inside a name is kept
    row = ["F16Q10000006", "201603", "125000.00", "00", "0", "240"] + [""] * 27 + ["A, B BANK", ""]
    assert len(row) == 35
    txt.write_text("|".join(row) + "\n", encoding="utf-8")
    out = tmp_path / "mini.parquet"
    n = load._to_parquet(txt, PERFORMANCE_COLUMNS, out)
    assert n == 1
    import duckdb

    r = duckdb.sql(f"SELECT delinq_status, servicer_name FROM read_parquet('{out.as_posix()}')").fetchone()
    assert r == ("00", "A, B BANK")


@pytest.mark.skipif(not ZIP_2016.exists(), reason="Freddie Mac sample not downloaded")
def test_real_2016_sample_has_expected_field_counts():
    with zipfile.ZipFile(ZIP_2016) as z:
        for name, expected in (("sample_orig_2016.txt", 31), ("sample_perf_2016.txt", 35)):
            with z.open(name) as f:
                first = f.readline().decode("utf-8").rstrip("\n").split("|")
            assert len(first) == expected
