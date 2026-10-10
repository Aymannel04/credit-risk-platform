"""LGD computation checked on made-up loans with a hand-calculated answer."""
import duckdb
import pytest

from credit.economics.lgd import lgd_summary


def _con():
    con = duckdb.connect()
    con.execute("CREATE TABLE perf (loan_seq VARCHAR, zero_balance_code VARCHAR, actual_loss VARCHAR, zero_balance_removal_upb VARCHAR)")
    con.execute("CREATE TABLE loans (loan_seq VARCHAR, vintage_year INTEGER, orig_upb DOUBLE, default_24m INTEGER)")
    rows_loans = [
        ("A", 2016, 200000, 1),  # flagged, loss event with a 50,000 loss on a 100,000 balance
        ("B", 2016, 100000, 1),  # flagged, loss event with a GAIN of 10,000 on a 60,000 balance (negative loss)
        ("C", 2016, 300000, 1),  # flagged but recovered: no loss event at all
        ("D", 2016, 150000, 0),  # not flagged
        ("E", 2016, 100000, 1),  # flagged, loss event, amount unknown (NULL): excluded from the LGD, counted as 0 in the flag loss
    ]
    con.executemany("INSERT INTO loans VALUES (?, ?, ?, ?)", rows_loans)
    con.executemany("INSERT INTO perf VALUES (?, ?, ?, ?)", [
        ("A", "03", "50000", "100000"),
        ("B", "09", "-10000", "60000"),
        ("E", "02", None, "80000"),
        ("C", None, None, None),
        ("D", None, None, None),
    ])
    return con


def test_lgd_matches_the_hand_calculation():
    r = lgd_summary(_con())[0]
    assert r["flagged_defaults"] == 4  # A, B, C, E
    assert r["flagged_with_loss_event"] == 3  # A, B, E
    assert r["loss_event_loans"] == 3 and r["loss_event_with_amount"] == 2
    # loss events with an amount: (50,000 + -10,000) / (100,000 + 60,000) = 0.25
    assert r["lgd_loss_events"] == pytest.approx(0.25)
    # per flagged loan: total loss 40,000 (E counts as 0) / original amounts 200k+100k+300k+100k = 700k
    assert r["loss_per_flag"] == pytest.approx(40000 / 700000, abs=1e-4)
    assert r["share_no_loss_or_gain"] == pytest.approx(0.5)  # B had a gain
