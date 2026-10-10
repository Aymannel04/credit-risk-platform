"""The final exam must refuse to run unless the freeze is intact."""
import json

import numpy as np
import pytest

from credit.models import final_exam as fe
from credit.models.freeze import sha256


def _setup(tmp_path):
    features, config = tmp_path / "features.parquet", tmp_path / "assumptions.yaml"
    features.write_bytes(b"features v1")
    config.write_bytes(b"config v1")
    manifest = tmp_path / "frozen.json"
    manifest.write_text(json.dumps({
        "frozen_at_commit": "abc", "features_sha256": sha256(features), "assumptions_sha256": sha256(config),
        "rules": {"confidence_intervals": {"resamples": 10, "seed": 1}},
    }))
    return manifest, features, config


def test_intact_freeze_passes(tmp_path):
    manifest, features, config = _setup(tmp_path)
    assert fe.check_frozen(manifest, features, config, use_git=False)["frozen_at_commit"] == "abc"


def test_missing_manifest_blocks_the_exam(tmp_path):
    _, features, config = _setup(tmp_path)
    with pytest.raises(fe.NotFrozenError, match="missing"):
        fe.check_frozen(tmp_path / "nope.json", features, config, use_git=False)


def test_changed_features_block_the_exam(tmp_path):
    manifest, features, config = _setup(tmp_path)
    features.write_bytes(b"features v2 (someone tuned the data)")
    with pytest.raises(fe.NotFrozenError, match="features"):
        fe.check_frozen(manifest, features, config, use_git=False)


def test_changed_config_blocks_the_exam(tmp_path):
    manifest, features, config = _setup(tmp_path)
    config.write_bytes(b"config v2")
    with pytest.raises(fe.NotFrozenError, match="assumptions"):
        fe.check_frozen(manifest, features, config, use_git=False)


def test_bootstrap_is_paired_reproducible_and_brackets_the_truth():
    rng = np.random.default_rng(0)
    n = 4000
    p_true = rng.beta(1.2, 30, n)
    y = (rng.random(n) < p_true).astype(int)
    probs = {"a": p_true, "b": np.clip(p_true + rng.normal(0, 0.02, n), 1e-4, 0.99)}
    r1 = fe.bootstrap(y, probs, n_boot=200, seed=5)
    r2 = fe.bootstrap(y, probs, n_boot=200, seed=5)
    assert np.array_equal(r1["a"]["gini"], r2["a"]["gini"])  # same seed, same intervals
    lo, hi = fe.ci(r1["a"]["gini"])
    assert lo < hi
    from credit.models import metrics
    assert lo <= metrics.gini(y, probs["a"]) <= hi
    assert r1["a"]["gini"].shape == r1["b"]["gini"].shape  # paired: same resamples for every model
