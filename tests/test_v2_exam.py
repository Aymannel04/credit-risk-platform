"""v2 exam: the freeze guard must block, the bootstrap must be paired, the v2 feature list must exclude the flawed features."""
import json

import numpy as np
import pandas as pd
import pytest

from credit.models import v2_exam as ex


def _setup(tmp_path):
    files = {n: tmp_path / n for n in ("dev.parquet", "fresh.parquet", "assumptions.yaml", "prereg.md")}
    for n, p in files.items():
        p.write_bytes(f"{n} v1".encode())
    manifest = tmp_path / "frozen.json"
    manifest.write_text(json.dumps({
        "frozen_at_commit": "abc", "dev_features_sha256": ex.sha256(files["dev.parquet"]),
        "fresh_features_sha256": ex.sha256(files["fresh.parquet"]), "assumptions_sha256": ex.sha256(files["assumptions.yaml"]),
        "preregistration_sha256": ex.sha256(files["prereg.md"]), "bootstrap": {"resamples": 10, "seed": 1}}))
    return manifest, files


def _check(manifest, files):
    return ex.check_frozen(manifest, files["dev.parquet"], files["fresh.parquet"], files["assumptions.yaml"], files["prereg.md"], use_git=False)


def test_intact_freeze_passes(tmp_path):
    manifest, files = _setup(tmp_path)
    assert _check(manifest, files)["frozen_at_commit"] == "abc"


@pytest.mark.parametrize("name,fragment", [("dev.parquet", "development"), ("fresh.parquet", "fresh"),
                                           ("assumptions.yaml", "assumptions"), ("prereg.md", "pre-registration")])
def test_any_change_after_the_freeze_blocks_the_exam(tmp_path, name, fragment):
    manifest, files = _setup(tmp_path)
    files[name].write_bytes(b"someone changed this")
    with pytest.raises(ex.NotFrozenError, match=fragment):
        _check(manifest, files)


def test_missing_manifest_blocks_the_exam(tmp_path):
    manifest, files = _setup(tmp_path)
    manifest.unlink()
    with pytest.raises(ex.NotFrozenError, match="missing"):
        _check(manifest, files)


def test_v2_features_exclude_the_flawed_ones_and_keep_the_new_ones():
    v2 = set(ex.V2_NUMERIC + ex.V2_CATEGORICAL)
    for banned in ("state", "channel", "super_conforming", "int_rate", "n_borrowers", "vintage_year", "zip3", "seller_name"):
        assert banned not in v2
    assert {"credit_score", "dti", "rate_spread", "several_borrowers", "purpose"} <= v2
    assert ex.v2_config()["scorecard_binning"]["min_iv"] == 0.0  # selection was done by the within-vintage rule


def test_bootstrap_is_paired_and_reproducible():
    rng = np.random.default_rng(0)
    ys, probs = {}, {"a": {}, "b": {}}
    for v in (2010, 2014):
        p = rng.beta(1.2, 30, 3000)
        ys[v] = (rng.random(3000) < p).astype(int)
        probs["a"][v] = p
        probs["b"][v] = np.clip(p + rng.normal(0, 0.02, 3000), 1e-4, 0.99)
    b1 = ex.bootstrap(ys, probs, 50, seed=3)
    b2 = ex.bootstrap(ys, probs, 50, seed=3)
    assert np.array_equal(b1[2010]["a"]["gini"], b2[2010]["a"]["gini"])
    assert b1[2010]["a"]["gini"].shape == b1[2010]["b"]["gini"].shape == (50,)
    lo, hi = ex.ci(b1[2014]["a"]["gini"])
    assert lo < hi


def test_group_spread_flags_a_group_that_is_overpredicted():
    rng = np.random.default_rng(1)
    n = 20000
    df = pd.DataFrame({v: rng.choice(["A", "B"], n) for v in ex.SLICE_VARIABLES})
    p = np.clip(rng.beta(1.2, 20, n), 1e-4, 0.9)
    df["default_24m"] = (rng.random(n) < p).astype(int)
    honest = ex.group_spread(df, p)
    biased_p = p.copy()
    biased_p[(df["state"] == "A").to_numpy()] *= 2
    biased = ex.group_spread(df, np.clip(biased_p, 0, 0.99))
    assert biased["state"] > honest["state"] * 1.5
