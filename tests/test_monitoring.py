"""Monitoring tests on made-up loans: PSI maths, vectorized scorer == file scorer, the monitors, the drills, recalibration."""
import math
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from credit.models import metrics
from credit.monitoring import recalibration as rc
from credit.monitoring import report
from credit.monitoring.drift import Profile, alerts, level, level_flag, warnings_or_worse
from credit.monitoring.psi import counts_by_key, flag, psi
from credit.monitoring.scoring import band_index, score_frame
from credit.monitoring.simulate import apply_shift, run_simulation
from credit.serving.model_file import _band_index, load_model, score_loan

MODEL = load_model(report.MODEL)
CFG = report.load_config()
FEATURES = MODEL["feature_order"]


def make_loans(n: int, seed: int = 0, score_shift: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    ltv = rng.normal(75, 15, n).clip(5, 100)
    df = pd.DataFrame({
        "credit_score": rng.normal(740 - score_shift, 50, n).clip(500, 850).round(),
        "dti": rng.normal(35, 10, n).clip(1, 65).round(),
        "rate_spread": rng.normal(0, 0.5, n).clip(-3.6, 3.6),
        "ltv": ltv, "cltv": (ltv + np.abs(rng.normal(0, 3, n))).clip(5, 113),
        "several_borrowers": rng.integers(0, 2, n).astype(float),
        "mi_pct": np.where(ltv > 80, rng.integers(6, 35, n), 0).astype(float),
        "orig_term": rng.choice([180.0, 240.0, 360.0], n, p=[0.15, 0.15, 0.7]),
        "purpose": rng.choice(["P", "C", "N"], n, p=[0.5, 0.2, 0.3]),
    })
    df.loc[rng.random(n) < 0.0003, "credit_score"] = np.nan  # the real data has 0.026% missing credit scores
    return df


def with_outcomes(df: pd.DataFrame, seed: int = 1, level_factor: float = 1.0) -> pd.DataFrame:
    out = df.join(score_frame(MODEL, df))
    out["y"] = (np.random.default_rng(seed).random(len(df)) < np.clip(out["pd"] * level_factor, 0, 1)).astype(int)
    return out


# ---------- PSI ----------

def test_psi_zero_for_identical_distributions():
    assert psi([10, 20, 70], [1, 2, 7]) == pytest.approx(0.0, abs=1e-12)


def test_psi_known_value_and_symmetry():
    expected = 0.4 * math.log(1.8) - 0.4 * math.log(0.2)  # shares (0.5, 0.5) -> (0.9, 0.1)
    assert psi([50, 50], [90, 10]) == pytest.approx(expected)
    assert psi([90, 10], [50, 50]) == pytest.approx(expected)


def test_psi_empty_band_stays_finite():
    assert math.isfinite(psi([50, 50, 0], [40, 40, 20]))
    assert math.isfinite(psi([50, 50, 10], [50, 50, 0]))


def test_known_blind_spot_missing_values_are_only_detectable_when_the_baseline_is_low():
    # S4 (10% of values become missing): with a 1% baseline the PSI stays just under the alert line, with the real 0.03% it is far above.
    assert psi([0.01, 0.99], [0.109, 0.891]) < 0.25
    assert psi([0.0003, 0.9997], [0.1003, 0.8997]) > 0.25


def test_flag_levels():
    assert flag(0.05, 0.10, 0.25) == "ok" and flag(0.10, 0.10, 0.25) == "warn" and flag(0.25, 0.10, 0.25) == "alert"


def test_counts_by_key():
    assert counts_by_key(np.array([1, 1, 3]), np.array([1, 2, 3])).tolist() == [2, 0, 1]


# ---------- the vectorized scorer is the file scorer ----------

def test_band_index_equals_file_scorer_including_edges_missing_and_unseen():
    rng = np.random.default_rng(3)
    for name in FEATURES:
        spec = MODEL["features"][name]
        if spec["type"] == "numeric":
            values = list(rng.uniform(-5, 900, 300)) + list(spec["edges"]) + [np.nan, None, 0.0]
            series = pd.Series(values, dtype=float)
        else:
            values = ["P", "C", "N", "R", "Z", None, np.nan] * 20
            series = pd.Series(values, dtype=object)
        got = band_index(spec, series)
        want = [_band_index(spec, name, None if (v is None or (isinstance(v, float) and np.isnan(v))) else v) for v in values]
        assert got.tolist() == want, name


def test_score_frame_equals_score_loan():
    df = make_loans(300, seed=5)
    scored = score_frame(MODEL, df)
    for i in range(len(df)):
        loan = {k: (None if pd.isna(v) else v) for k, v in df.iloc[i].items()}
        direct = score_loan(MODEL, loan)
        assert scored["score"].iloc[i] == pytest.approx(direct["score"], abs=1e-9)
        assert scored["pd"].iloc[i] == pytest.approx(direct["probability_of_default"], abs=1e-12)


# ---------- level flags ----------

def test_level_flag_thresholds():
    assert level_flag(1.0, CFG) == "ok"
    assert level_flag(0.75, CFG) == "warn" and level_flag(1.4, CFG) == "warn"
    assert level_flag(0.60, CFG) == "alert" and level_flag(1.6, CFG) == "alert"
    assert level_flag(float("nan"), CFG) == "alert"


def test_level_ratio_below_one_means_over_prediction():
    lv = level(np.array([0, 0, 0, 1]), np.array([0.5, 0.5, 0.5, 0.5]))
    assert lv["ratio"] == pytest.approx(0.5)


# ---------- the monitors and the drills ----------

@pytest.fixture(scope="module")
def pool():
    df = make_loans(40_000, seed=11)
    scored = with_outcomes(df, seed=12)
    return df, scored["y"].to_numpy()


def test_clean_batch_raises_no_warning(pool):
    df, y = pool
    ref = with_outcomes(df.iloc[:30_000], seed=2)
    batch = with_outcomes(df.iloc[30_000:], seed=3)
    rep = Profile(MODEL, ref, CFG).compare(batch, batch["y"].to_numpy())
    assert not warnings_or_worse(rep), rep["csi_flags"]


def test_a_score_drop_is_detected(pool):
    df, _ = pool
    ref = with_outcomes(df.iloc[:30_000])
    worse = make_loans(10_000, seed=21, score_shift=40)
    rep = Profile(MODEL, ref, CFG).compare(worse.join(score_frame(MODEL, worse)))
    assert alerts(rep)


def test_apply_shift_never_modifies_its_input_and_respects_limits(pool):
    df, y = pool
    batch, yb = df.iloc[:2000].copy(), y[:2000].copy()
    before, before_y = batch.copy(), yb.copy()
    b, _ = apply_shift(batch, yb, {"kind": "shift", "feature": "credit_score", "delta": -300}, np.random.default_rng(0))
    assert b["credit_score"].dropna().min() >= 300
    pd.testing.assert_frame_equal(batch, before)
    assert (yb == before_y).all()


def test_each_shift_kind_does_what_it_says(pool):
    df, y = pool
    batch, yb = df.iloc[:5000].copy(), y[:5000].copy()
    rng = np.random.default_rng(0)
    b, _ = apply_shift(batch, yb, {"kind": "missing", "feature": "credit_score", "share": 0.10}, rng)
    assert b["credit_score"].isna().mean() == pytest.approx(0.10 + batch["credit_score"].isna().mean(), abs=0.02)
    b, _ = apply_shift(batch, yb, {"kind": "new_category", "feature": "purpose", "value": "X", "share": 0.2}, rng)
    assert (b["purpose"] == "X").mean() == pytest.approx(0.2, abs=0.03)
    b, y2 = apply_shift(batch, yb, {"kind": "default_rate", "factor": 2.0}, rng)
    assert y2.sum() == min(2 * yb.sum(), len(yb)) and (y2 >= yb).all()
    b, _ = apply_shift(batch, yb, {"kind": "shift_many", "features": ["ltv", "cltv"], "delta": 10}, rng)
    assert (b["ltv"] >= batch["ltv"]).all() and (b["cltv"] >= batch["cltv"]).all()
    with pytest.raises(ValueError):
        apply_shift(batch, yb, {"kind": "nonsense"}, rng)


def test_simulation_control_clean_and_expected_alerts_caught(pool):
    df, y = pool
    cfg = {**CFG, "simulation": {**CFG["simulation"], "batch_size": 8000}}
    out = run_simulation(MODEL, df, y, cfg)
    assert out["R_M1_control_clean"], out["drills"]["C0"]
    assert set(out["caught"]) >= {"S1", "S3", "S4", "S5", "S9"}, out["missed"]
    assert all(d["simulated"] for d in out["drills"].values())
    again = run_simulation(MODEL, df, y, cfg)
    assert again["drills"]["S1"]["score_psi"] == out["drills"]["S1"]["score_psi"]  # same seed, same result


# ---------- recalibration ----------

def test_solve_shift_hits_the_target_and_keeps_the_ranking():
    p = np.random.default_rng(0).beta(1, 30, 5000)
    for target in (0.005, 0.02, 0.2):
        d = rc.solve_shift(p, target)
        assert rc.shift_probabilities(p, d).mean() == pytest.approx(target, abs=1e-9)
    y = (np.random.default_rng(1).random(5000) < p).astype(int)
    assert metrics.gini(y, rc.shift_probabilities(p, -1.3)) == pytest.approx(metrics.gini(y, p), abs=1e-9)
    with pytest.raises(ValueError):
        rc.solve_shift(p, 0.0)


def test_zero_shift_changes_nothing():
    p = np.array([0.01, 0.2, 0.9])
    assert rc.shift_probabilities(p, 0.0) == pytest.approx(p)


def test_known_vintages_rule_matches_the_preregistration():
    vint = [2008, 2010, 2012, 2014, 2016, 2018, 2019, 2022, 2023]
    assert rc.known_vintages(2010, vint, 3) == []
    assert rc.known_vintages(2012, vint, 3) == [2008]
    assert rc.known_vintages(2014, vint, 3) == [2008, 2010]
    assert rc.known_vintages(2019, vint, 3) == [2008, 2010, 2012, 2014, 2016]
    assert rc.known_vintages(2023, vint, 3) == [2008, 2010, 2012, 2014, 2016, 2018, 2019]
    assert [v for v in vint if rc.known_vintages(v, vint, 3)] == [2012, 2014, 2016, 2018, 2019, 2022, 2023]


def _frames(vintages, factor_by_vintage, n=6000):
    out = {}
    for i, v in enumerate(vintages):
        df = make_loans(n, seed=100 + i)
        s = with_outcomes(df, seed=200 + i, level_factor=factor_by_vintage[v])
        out[v] = s[["pd", "y"]]
    return out


def test_recalibration_helps_when_the_level_gap_is_stable_and_gini_never_changes():
    vint = [2008, 2010, 2012, 2014, 2016, 2018, 2019, 2022, 2023]
    rows = rc.run(_frames(vint, dict.fromkeys(vint, 0.5)), CFG)  # reality is always half of the prediction
    v = rc.verdict(rows, CFG)
    assert sorted(rows) == [2012, 2014, 2016, 2018, 2019, 2022, 2023]
    assert v["R_C2_gini_unchanged"]
    assert v["C_pooled"]["recommended"] and v["B_last"]["recommended"]


def test_recalibration_is_not_recommended_when_the_level_gap_flips_every_vintage():
    vint = [2008, 2010, 2012, 2014, 2016, 2018, 2019, 2022, 2023]
    factors = {v: (3.0 if i % 2 == 0 else 0.3) for i, v in enumerate(vint)}  # alternating crisis / calm
    v = rc.verdict(rc.run(_frames(vint, factors), CFG), CFG)
    assert not v["B_last"]["recommended"]


def test_verdict_applies_the_three_rules():
    base = {"gini_unchanged": True}
    rows = {t: {"A_static": {"level_error": 0.5, **base}, "B_last": {"level_error": 0.45, **base}, "C_pooled": {"level_error": 0.2, **base}}
            for t in range(7)}
    v = rc.verdict(rows, CFG)
    assert not v["B_last"]["recommended"] and not v["B_last"]["mean_improvement_ok"]  # 10% < 20%
    assert v["C_pooled"]["recommended"]
    rows[0]["C_pooled"]["level_error"] = 0.9  # one target gets much worse (+0.4 > 0.30)
    assert not rc.verdict(rows, CFG)["C_pooled"]["recommended"]


# ---------- the report ----------

def test_report_end_to_end_on_made_up_vintages():
    vint = [2008, 2010, 2012, 2014, 2016, 2018, 2019, 2022, 2023]
    ref_years = CFG["reference_vintages"]
    frame = pd.concat([
        make_loans(4000, seed=300 + i).assign(vintage=v) for i, v in enumerate(vint)], ignore_index=True)
    frame["y"] = with_outcomes(frame[FEATURES], seed=9)["y"].to_numpy()
    frame["in_sample"] = frame["vintage"].isin(ref_years)
    a, scored = report.part_a(MODEL, frame, CFG)
    assert sorted(a) == vint and a[2008]["in_sample"] and not a[2010]["in_sample"]
    cfg = {**CFG, "simulation": {**CFG["simulation"], "batch_size": 3000}}
    dev = scored[scored["in_sample"]]
    b = run_simulation(MODEL, dev[FEATURES].reset_index(drop=True), dev["y"].to_numpy(), cfg)
    c = rc.run({int(v): g[["pd", "y"]] for v, g in scored.groupby("vintage")}, CFG)
    verdict = rc.verdict(c, CFG)
    preds = report.predictions(a, b, c, verdict)
    assert {p["id"] for p in preds} >= {"A1", "A2", "A3", "B1", "C1", "C2", "C3"}
    md = report.to_markdown({"model_id": "x", "preregistration": {"docs/monitoring_preregistration.md": {"commit": "abc"}},
                             "part_a": a, "part_b": b, "part_c": c, "part_c_verdict": verdict, "predictions": preds})
    assert "Part A" in md and "SIMULATED" in md and "predictions hit" in md


# ---------- the pre-registration guard ----------

def test_preregistration_files_are_committed_in_this_repo():
    state = report.prereg_state()
    assert all(s["commit"] for s in state.values()), state


@pytest.mark.skipif(shutil.which("git") is None, reason="git not available")
def test_prereg_state_detects_uncommitted_changes(tmp_path):
    def git(*a):
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    f = tmp_path / "prereg.md"
    f.write_text("v1", encoding="utf-8")
    assert report.prereg_state((f,), tmp_path)[f.name] == {"commit": None, "clean": False}  # never committed
    git("add", "."), git("commit", "-q", "-m", "x")
    s = report.prereg_state((f,), tmp_path)[f.name]
    assert s["commit"] and s["clean"]
    f.write_text("v2", encoding="utf-8")  # edited after the commit
    assert not report.prereg_state((f,), tmp_path)[f.name]["clean"]
