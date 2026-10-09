"""Staging tests on tiny made-up loans (no Freddie Mac data needed).

Each fake loan triggers exactly one rule:
  L_NORMAL    never late, still running at month 30            -> observable, default 0
  L_LATE      90+ days late at month 10, no assistance plan    -> default 1 (A and B)
  L_FORB      90+ days late at month 10 DURING forbearance     -> default 0 in B, 1 in A
  L_LOSS      ends with zero balance code 03 at month 20       -> default 1 (A, B and C)
  L_PAIDOFF   paid off (01) at month 12                        -> observable, default 0
  L_YOUNG     only 10 months of history, still running         -> NOT observable, label NULL
  L_RELIEF    relief refinance loan                            -> flagged
  L_SEASONED  first payment 3 years after its vintage          -> flagged
  L_999       dti 999, credit score 9999, 99 units             -> become NULL
"""
import duckdb
import pandas as pd
import pytest

from credit.freddie import staging
from credit.freddie.layout import ORIGINATION_COLUMNS, PERFORMANCE_COLUMNS


def _orig(loan_seq, **over):
    row = dict.fromkeys(ORIGINATION_COLUMNS)
    row.update(
        credit_score="700", first_payment_date="201603", first_time_homebuyer="N",
        maturity_date="204602", mi_pct="0", n_units="1", occupancy="P", cltv="80", dti="30",
        orig_upb="200000", ltv="80", int_rate="3.75", channel="R", ppm_flag="N", amort_type="FRM",
        state="CA", property_type="SF", zip3="900", loan_seq=loan_seq, purpose="P", orig_term="360",
        n_borrowers="2", seller_name="OTHER", super_conforming="N", relief_refi="N", io_indicator="N",
    )
    row.update(over)
    return row


def _perf(loan_seq, ages, status=None, assist=None, end_code=None):
    """One row per month. status/assist: dict age -> value. end_code: (age, code)."""
    rows = []
    for a in ages:
        r = dict.fromkeys(PERFORMANCE_COLUMNS)
        r.update(loan_seq=loan_seq, report_period="2016%02d" % (a % 12 + 1), loan_age=str(a), delinq_status="00")
        if status and a in status:
            r["delinq_status"] = status[a]
        if assist and a in assist:
            r["borrower_assist_code"] = assist[a]
        if end_code and a == end_code[0]:
            r["zero_balance_code"] = end_code[1]
        rows.append(r)
    return rows


def _write(path, rows, columns):
    con = duckdb.connect()
    cols = ", ".join(f'"{c}" VARCHAR' for c in columns)
    con.execute(f"CREATE TABLE t ({cols})")
    for r in rows:
        con.execute(f"INSERT INTO t VALUES ({', '.join(['?'] * len(columns))})", [r[c] for c in columns])
    con.execute(f"COPY t TO '{path.as_posix()}' (FORMAT PARQUET)")
    con.close()


@pytest.fixture()
def staged(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "stg"
    raw.mkdir()
    orig = [
        _orig("F16Q10000001"), _orig("F16Q10000002"), _orig("F16Q10000003"), _orig("F16Q10000004"),
        _orig("F16Q10000005"), _orig("F16Q10000006"),
        _orig("F16Q10000007", relief_refi="Y", pre_relief_loan_seq="F14Q10000099", dti="999"),
        _orig("F16Q10000008", first_payment_date="201903"),
        _orig("F16Q10000009", dti="999", credit_score="9999", n_units="99"),
    ]
    perf = (
        _perf("F16Q10000001", range(0, 31))
        + _perf("F16Q10000002", range(0, 31), status={10: "03"})
        + _perf("F16Q10000003", range(0, 31), status={10: "03"}, assist={10: "F"})
        + _perf("F16Q10000004", range(0, 21), end_code=(20, "03"))
        + _perf("F16Q10000005", range(0, 13), end_code=(12, "01"))
        + _perf("F16Q10000006", range(0, 10))
        + _perf("F16Q10000007", range(0, 31))
        + _perf("F16Q10000008", range(0, 31))
        + _perf("F16Q10000009", range(0, 31))
    )
    _write(raw / "orig_2016.parquet", orig, ORIGINATION_COLUMNS)
    _write(raw / "perf_2016.parquet", perf, PERFORMANCE_COLUMNS)
    # toy data: relax the real-data sanity limits (11% missing score, 25% defaults are expected here)
    report = staging.stage_year(2016, raw_dir=raw, out_dir=out, max_missing_score=1.0, max_default_rate=1.0)
    con = duckdb.connect()
    labels = {
        r[0]: r[1:]
        for r in con.execute(
            f"SELECT loan_seq, observable_24m, default_24m, default_24m_all_late, default_24m_loss_only "
            f"FROM read_parquet('{(out / 'stg_label_2016.parquet').as_posix()}')"
        ).fetchall()
    }
    orig_df = con.execute(f"SELECT * FROM read_parquet('{(out / 'stg_orig_2016.parquet').as_posix()}')").df().set_index("loan_seq")
    return report, labels, orig_df


def test_labels(staged):
    _, labels, _ = staged
    assert labels["F16Q10000001"] == (True, 0, 0, 0)
    assert labels["F16Q10000002"] == (True, 1, 1, 0)  # late, no assistance: default in B and A
    assert labels["F16Q10000003"] == (True, 0, 1, 0)  # late during forbearance: A yes, B no
    assert labels["F16Q10000004"] == (True, 1, 1, 1)  # loss event
    assert labels["F16Q10000005"] == (True, 0, 0, 0)  # paid off early: observed, not a default
    assert labels["F16Q10000006"] == (False, None, None, None)  # too young: no label


def test_flags(staged):
    report, _, o = staged
    assert bool(o.loc["F16Q10000007", "relief_refi"]) is True
    assert bool(o.loc["F16Q10000001", "relief_refi"]) is False
    assert bool(o.loc["F16Q10000008", "is_seasoned_or_modified"]) is True
    assert bool(o.loc["F16Q10000001", "is_seasoned_or_modified"]) is False
    assert report["relief_refi"] == 1 and report["seasoned_or_modified"] == 1
    assert report["not_observable_24m"] == 1


def test_special_values_become_null(staged):
    _, _, o = staged
    row = o.loc["F16Q10000009"]
    assert pd.isna(row["dti"])  # 999 -> NULL
    assert pd.isna(row["credit_score"])  # 9999 -> NULL
    assert pd.isna(row["n_units"])  # 99 -> NULL
    assert o.loc["F16Q10000001", "credit_score"] == 700


def test_vintage_and_types(staged):
    _, _, o = staged
    assert o.loc["F16Q10000001", "vintage_year"] == 2016
    assert o.loc["F16Q10000001", "vintage_quarter"] == 1
    assert o.loc["F16Q10000001", "months_after_vintage"] == 2  # first payment 2016-03, quarter starts 2016-01


def test_check_fails_on_duplicate_loan(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "orig_2016.parquet", [_orig("F16Q10000001"), _orig("F16Q10000001")], ORIGINATION_COLUMNS)
    _write(raw / "perf_2016.parquet", _perf("F16Q10000001", range(0, 31)), PERFORMANCE_COLUMNS)
    with pytest.raises(staging.DataCheckError, match="not unique"):
        staging.stage_year(2016, raw_dir=raw, out_dir=tmp_path / "stg")


def test_check_fails_on_orphan_performance_rows(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "orig_2016.parquet", [_orig("F16Q10000001")], ORIGINATION_COLUMNS)
    perf = _perf("F16Q10000001", range(0, 31)) + _perf("F16Q10000099", range(0, 31))
    _write(raw / "perf_2016.parquet", perf, PERFORMANCE_COLUMNS)
    with pytest.raises(staging.DataCheckError, match="no origination row"):
        staging.stage_year(2016, raw_dir=raw, out_dir=tmp_path / "stg")


def test_check_fails_on_absurd_interest_rate(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    _write(raw / "orig_2016.parquet", [_orig("F16Q10000001", int_rate="55")], ORIGINATION_COLUMNS)
    _write(raw / "perf_2016.parquet", _perf("F16Q10000001", range(0, 31)), PERFORMANCE_COLUMNS)
    with pytest.raises(staging.DataCheckError, match="int_rate"):
        staging.stage_year(2016, raw_dir=raw, out_dir=tmp_path / "stg")
