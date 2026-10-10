"""Era review tests: an era proxy must be exposed, a genuinely informative feature must be kept."""
import numpy as np
import pandas as pd

from credit.freddie.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from credit.models import era_review as er


def _eras(seed=0, n_per=15000):
    """Three eras with very different default levels.
    NUMERIC_FEATURES[0]  genuine: raises risk inside every era
    NUMERIC_FEATURES[1]  era proxy: its value is just the era (high in the crisis era), no information inside an era
    CATEGORICAL_FEATURES[0] level 'Y' exists only in the calm eras
    everything else: noise
    """
    rng = np.random.default_rng(seed)
    frames = []
    for year, base, proxy_level in ((2008, -2.6, 6.0), (2012, -4.6, 3.5), (2016, -4.2, 3.8)):
        df = pd.DataFrame({c: rng.normal(size=n_per) for c in NUMERIC_FEATURES})
        for c in CATEGORICAL_FEATURES:
            df[c] = rng.choice(["A", "B", "C"], size=n_per)
        df[NUMERIC_FEATURES[1]] = proxy_level + rng.normal(0, 0.05, n_per)
        logit = base + 1.0 * df[NUMERIC_FEATURES[0]]
        df["default_24m"] = (rng.random(n_per) < 1 / (1 + np.exp(-logit))).astype(int)
        df["vintage_year"] = year
        df[CATEGORICAL_FEATURES[1]] = np.where(year == 2008, "N", rng.choice(["N", "Y"], size=n_per, p=[0.9, 0.1]))
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_era_proxy_is_exposed_and_genuine_feature_is_kept():
    rep = er.feature_report(_eras()).set_index("feature")
    genuine, proxy = NUMERIC_FEATURES[0], NUMERIC_FEATURES[1]
    assert rep.loc[genuine, "keep_ratio"] > 0.5  # the information is real inside each era
    assert rep.loc[proxy, "pooled_iv"] > 0.3  # it looks very informative when eras are pooled...
    assert rep.loc[proxy, "keep_ratio"] < 0.2  # ...but almost nothing is left inside an era


def test_vanishing_category_level_is_flagged():
    df = _eras()
    rep = er.feature_report(df).set_index("feature")
    assert "Y" in rep.loc[CATEGORICAL_FEATURES[1], "levels_vanishing"]
    assert rep.loc[CATEGORICAL_FEATURES[0], "levels_vanishing"] == []


def test_direction_flip_is_detected():
    df = _eras()
    col = NUMERIC_FEATURES[2]
    flip = df["vintage_year"] == 2012
    rng = np.random.default_rng(1)
    # in 2012 the feature acts the opposite way
    df.loc[flip, col] = -df.loc[flip, NUMERIC_FEATURES[0]] + rng.normal(0, 0.1, flip.sum())
    df.loc[~flip, col] = df.loc[~flip, NUMERIC_FEATURES[0]] + rng.normal(0, 0.1, (~flip).sum())
    rep = er.feature_report(df).set_index("feature")
    assert bool(rep.loc[col, "direction_flips"])
    assert not bool(rep.loc[NUMERIC_FEATURES[0], "direction_flips"])


def test_lovo_runs_for_each_held_out_vintage():
    df = _eras(n_per=8000)
    out = er.lovo(df, NUMERIC_FEATURES, CATEGORICAL_FEATURES)
    assert set(out) == {2008, 2012, 2016}
    assert all(v["gini"] > 0.2 for v in out.values())
