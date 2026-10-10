"""Fairness slice tests on synthetic groups with known behaviour."""
import numpy as np
import pandas as pd

from credit.models.fairness import slice_table


def _df(n=20000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({"state": rng.choice(["AA", "BB", "CC"], size=n), "first_time_homebuyer": rng.choice(["Y", "N"], size=n)})
    p = np.clip(rng.beta(1.2, 30, n), 1e-4, 0.9)
    y = (rng.random(n) < p).astype(int)
    return df, p, y


def test_honest_model_gets_no_flags():
    df, p, y = _df()
    t = slice_table(df, p, y, threshold=0.3, variable="first_time_homebuyer")
    assert not t["flag_calibration"].any()
    assert (t["adverse_impact_ratio"] > 0.95).all()


def test_overpredicted_group_is_flagged_for_calibration():
    df, p, y = _df(seed=1)
    p = p.copy()
    p[(df["first_time_homebuyer"] == "Y").to_numpy()] *= 2.0  # the model doubles the risk of one group only
    t = slice_table(df, np.clip(p, 0, 0.99), y, threshold=0.3, variable="first_time_homebuyer").set_index("group")
    assert bool(t.loc["Y", "flag_calibration"]) and not bool(t.loc["N", "flag_calibration"])
    assert t.loc["Y", "pred_over_obs"] > 1.5


def test_strict_line_for_one_group_is_flagged_for_approval():
    df, p, y = _df(seed=2)
    p = p.copy()
    p[(df["state"] == "AA").to_numpy()] = 0.5  # every loan of one group is above the line
    t = slice_table(df, p, y, threshold=0.3, variable="state").set_index("group")
    assert bool(t.loc["AA", "flag_approval"]) and t.loc["AA", "adverse_impact_ratio"] < 0.1


def test_small_groups_are_not_reported_and_states_are_grouped():
    rng = np.random.default_rng(3)
    n = 3000
    df = pd.DataFrame({"state": rng.choice([f"S{i:02d}" for i in range(30)], size=n)})
    p, y = rng.random(n) * 0.05, (rng.random(n) < 0.02).astype(int)
    t = slice_table(df, p, y, threshold=0.3, variable="state", min_loans=500)
    assert len(t) <= 11  # top 10 states + "other states"
    assert (t["loans"] >= 500).all()


def test_refusal_ratio_exposes_what_the_four_fifths_rule_hides():
    df, p, y = _df(seed=4)
    p = p.copy()
    mask = (df["state"] == "AA").to_numpy()
    rng = np.random.default_rng(5)
    p[mask] = np.where(rng.random(mask.sum()) < 0.04, 0.5, p[mask])  # 4% of group AA refused, ~0% elsewhere
    t = slice_table(df, p, y, threshold=0.3, variable="state").set_index("group")
    assert t.loc["AA", "adverse_impact_ratio"] > 0.9  # the classic rule sees nothing (approval ~96% vs ~100%)
    assert not bool(t.loc["AA", "flag_approval"])
    assert t.loc["AA", "refusal_ratio_vs_lowest"] > 5  # but this group is refused many times more often
