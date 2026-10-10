"""Fresh-vintage table: locked labels, same rules as the development table, consistency with it."""
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from credit.freddie import features as ft
from credit.freddie import fresh


def _stg(loans):
    orig, label = [], []
    for ln in loans:
        orig.append(dict(
            loan_seq=ln["loan_seq"], vintage_year=2000 + int(ln["loan_seq"][1:3]), vintage_quarter=1,
            first_payment_date=pd.Timestamp("2016-03-01"), credit_score=700, mi_pct=0, n_units=1, cltv=80, dti=30,
            orig_upb=200000.0, ltv=80, int_rate=ln.get("rate", 3.75), orig_term=360, n_borrowers=ln.get("nb", 2),
            first_time_homebuyer="N", occupancy="P", channel="R", ppm_flag="N", property_type="SF", purpose="P",
            state="CA", super_conforming="N", relief_refi=ln.get("relief", False), is_seasoned_or_modified=False))
        label.append(dict(loan_seq=ln["loan_seq"], observable_24m=True, default_24m=0, default_24m_all_late=0,
                          default_24m_loss_only=0))
    return pd.DataFrame(orig), pd.DataFrame(label)


def _con(loans):
    o, l_ = _stg(loans)
    con = duckdb.connect()
    con.register("o", o)
    con.register("l", l_)
    con.execute("CREATE TABLE stg_orig AS SELECT * FROM o")
    con.execute("CREATE TABLE stg_label AS SELECT * FROM l")
    return con


def test_labels_are_locked_without_permission(tmp_path):
    with pytest.raises(PermissionError):
        fresh.load_fresh(path=tmp_path / "x.parquet")


def test_fresh_table_has_spread_several_borrowers_and_exclusions():
    loans = [{"loan_seq": f"F10Q1{i:07d}", "rate": 4.0 + 0.1 * i, "nb": 1 if i % 2 else 3} for i in range(5)]
    loans.append({"loan_seq": "F10Q19999999", "relief": True})
    con = _con(loans)
    rep = fresh.build_fresh(con)
    assert fresh.check_fresh(con) == []
    assert rep["waterfall"][0]["removed_relief_refi"] == 1 and rep["waterfall"][0]["kept"] == 5
    t = con.execute("SELECT loan_seq, rate_spread, several_borrowers, split FROM fresh ORDER BY loan_seq").fetchall()
    assert [round(r[1], 3) for r in t] == [-0.2, -0.1, 0.0, 0.1, 0.2]  # rate minus the quarter's median (4.2)
    assert [r[2] for r in t] == [1.0, 0.0, 1.0, 0.0, 1.0]  # rows 0, 2, 4 have 3 borrowers
    assert all(r[3] == "fresh_2010" for r in t)


def test_fresh_columns_cover_what_the_v1_model_needs():
    con = _con([{"loan_seq": "F10Q10000001"}])
    fresh.build_fresh(con)
    cols = {r[0] for r in con.execute("DESCRIBE fresh").fetchall()}
    assert set(ft.FEATURES) <= cols and "several_borrowers" in cols


def test_same_rules_as_development_table_on_real_data():
    """Rebuilding the KNOWN vintages with the fresh builder must reproduce the development rate_spread exactly."""
    stg = Path(__file__).resolve().parents[1] / "data" / "interim" / "stg"
    dev = Path(__file__).resolve().parents[1] / "data" / "interim" / "features" / "features.parquet"
    if not (stg.exists() and dev.exists()):
        pytest.skip("data not available")
    con = duckdb.connect()
    for kind in ("orig", "label"):
        listing = ", ".join(f"'{f.as_posix()}'" for f in sorted(stg.glob(f"stg_{kind}_*.parquet")))
        con.execute(f"CREATE TABLE stg_{kind} AS SELECT * FROM read_parquet([{listing}], union_by_name=true)")
    fresh.build_fresh(con)
    got = con.execute(f"""
        SELECT count(*) AS n, max(abs(a.rate_spread - b.rate_spread)) AS max_diff
        FROM fresh a JOIN read_parquet('{dev.as_posix()}') b USING (loan_seq)""").fetchone()
    n_dev = con.execute(f"SELECT count(*) FROM read_parquet('{dev.as_posix()}')").fetchone()[0]
    assert got[0] == n_dev and got[1] < 1e-9
