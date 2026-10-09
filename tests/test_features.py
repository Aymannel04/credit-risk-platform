"""Features-layer tests on made-up loans: exclusions, splits, and leakage guards."""
import duckdb
import pandas as pd
import pytest

from credit.freddie import features as ft


def _stg(loans):
    """loans: list of dicts with loan_seq + overrides. Returns (stg_orig, stg_label) DataFrames."""
    orig, label = [], []
    for ln in loans:
        o = dict(
            loan_seq=ln["loan_seq"], vintage_year=int(ln["loan_seq"][1:3]) + 2000, vintage_quarter=1,
            first_payment_date=pd.Timestamp("2016-03-01"), credit_score=700, mi_pct=0, n_units=1, cltv=80,
            dti=30, orig_upb=200000.0, ltv=80, int_rate=3.75, orig_term=360, n_borrowers=2,
            first_time_homebuyer="N", occupancy="P", channel="R", ppm_flag="N", property_type="SF",
            purpose="P", state="CA", super_conforming="N",
            relief_refi=ln.get("relief_refi", False), is_seasoned_or_modified=ln.get("seasoned", False),
        )
        observable = ln.get("observable", True)
        label.append(dict(
            loan_seq=ln["loan_seq"], observable_24m=observable,
            default_24m=ln.get("default", 0) if observable else None,
            default_24m_all_late=ln.get("default", 0) if observable else None,
            default_24m_loss_only=0 if observable else None,
        ))
        orig.append(o)
    return pd.DataFrame(orig), pd.DataFrame(label)


def _build(loans):
    orig, label = _stg(loans)
    con = duckdb.connect()
    con.register("orig_df", orig)
    con.register("label_df", label)
    con.execute("CREATE TABLE stg_orig AS SELECT * FROM orig_df")
    con.execute("CREATE TABLE stg_label AS SELECT * FROM label_df")
    return con, ft.build(con)


def test_exclusions_are_applied_and_counted():
    loans = [
        {"loan_seq": "F08Q10000001"},
        {"loan_seq": "F08Q10000002", "relief_refi": True},
        {"loan_seq": "F08Q10000003", "seasoned": True},
        {"loan_seq": "F22Q10000004", "observable": False},
        {"loan_seq": "F22Q10000005"},
    ]
    con, report = _build(loans)
    kept = {r[0] for r in con.execute("SELECT loan_seq FROM features").fetchall()}
    assert kept == {"F08Q10000001", "F22Q10000005"}
    w = {r["vintage_year"]: r for r in report["waterfall"]}
    assert w[2008]["start"] == 3 and w[2008]["removed_relief_refi"] == 1
    assert w[2008]["removed_seasoned_or_modified"] == 1 and w[2008]["kept"] == 1
    assert w[2022]["removed_not_observable"] == 1 and w[2022]["kept"] == 1
    assert report["failed_checks"] == []


def test_splits_by_time():
    loans = [{"loan_seq": f"F{yy}Q1{i:07d}"} for yy in ("08", "09", "16", "19", "22") for i in range(30)]
    con, report = _build(loans)
    rows = con.execute("SELECT vintage_year, split FROM features").fetchall()
    for year, split in rows:
        if year <= 2018:
            assert split in {"train", "calibration", "validation", "test_in_time"}
        elif year == 2019:
            assert split == "test_oot_2019"
        else:
            assert split == "test_oot_2022"
    assert report["failed_checks"] == []


def test_split_shares_are_close_to_target_and_reproducible():
    loans = [{"loan_seq": f"F16Q1{i:07d}"} for i in range(20000)]
    con, _ = _build(loans)
    shares = dict(con.execute("SELECT split, count(*) * 1.0 / 20000 FROM features GROUP BY split").fetchall())
    for name, target in {"train": 0.60, "calibration": 0.10, "validation": 0.15, "test_in_time": 0.15}.items():
        assert shares[name] == pytest.approx(target, abs=0.015)
    first = con.execute("SELECT loan_seq, split FROM features ORDER BY loan_seq").fetchall()
    con2, _ = _build(loans)
    assert con2.execute("SELECT loan_seq, split FROM features ORDER BY loan_seq").fetchall() == first


def test_only_allowed_columns_and_no_leakage():
    con, _ = _build([{"loan_seq": "F16Q10000001"}])
    cols = {r[0] for r in con.execute("DESCRIBE features").fetchall()}
    assert cols == set(ft.META + ft.FEATURES + ft.LABELS + ["split"])
    for banned in ("zip3", "msa", "seller_name", "program_indicator", "delinq_status", "zero_balance_code", "actual_loss"):
        assert banned not in cols
    assert not set(ft.FEATURES) & set(ft.LABELS)
    assert "vintage_year" not in ft.FEATURES  # vintage is for splitting only


def test_check_catches_a_leaking_column():
    con, _ = _build([{"loan_seq": "F16Q10000001"}])
    con.execute("ALTER TABLE features ADD COLUMN delinq_status VARCHAR")
    assert any("unexpected columns" in f for f in ft.check(con))
