"""The JSON model file and the file-only scorer must reproduce the scikit-learn scorecard exactly."""
import ast
import copy
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from credit.freddie.features import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES
from credit.models import reasons as rs
from credit.models.scorecard import Scorecard, load_config
from credit.serving import export as ex
from credit.serving import model_file as mf

ROOT = Path(__file__).resolve().parents[1]
MODEL_JSON = ROOT / "models" / "scorecard_v2.json"


def _data(n=30000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({c: rng.normal(size=n) for c in NUMERIC_FEATURES})
    for c in CATEGORICAL_FEATURES:
        df[c] = rng.choice(["A", "B", "C"], size=n)
    logit = -3.5 + 1.0 * df[NUMERIC_FEATURES[0]] - 0.7 * df[NUMERIC_FEATURES[1]] + 0.6 * (df[CATEGORICAL_FEATURES[0]] == "A")
    y = pd.Series((rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int))
    df.loc[rng.random(n) < 0.04, NUMERIC_FEATURES[0]] = np.nan  # missing values
    df.loc[rng.random(n) < 0.03, CATEGORICAL_FEATURES[0]] = None
    return df, y


def _table():
    return {f: {"code": f"R{i:02d}", "phrase": f"fixed sentence about {f}"} for i, f in enumerate(FEATURES)}


@pytest.fixture(scope="module")
def fitted(tmp_path_factory):
    X, y = _data()
    sc = Scorecard(load_config()).fit(X, y)
    model = ex.export_model(sc, {"version": "test"}, _table())
    path = tmp_path_factory.mktemp("m") / "model.json"
    mf.save_model(model, path)
    return sc, mf.load_model(path), X


def _row(X, i):
    return {c: (None if pd.isna(v) else (float(v) if c in NUMERIC_FEATURES else str(v))) for c, v in X.iloc[i].items() if c in FEATURES}


def test_file_scorer_equals_the_scikit_learn_scorecard(fitted):
    sc, model, X = fitted
    cols = sc.selected_
    X2 = X.head(4000)
    expected_score, expected_pd = sc.score(X2), sc.predict_proba(X2)
    got = [mf.score_loan(model, {k: _row(X2, i)[k] for k in cols}) for i in range(len(X2))]
    assert np.allclose([g["score"] for g in got], expected_score, atol=1e-9)
    assert np.allclose([g["probability_of_default"] for g in got], expected_pd, atol=1e-12)


def test_unseen_category_and_missing_values_match_too(fitted):
    sc, model, X = fitted
    cols = sc.selected_
    X2 = X.head(50).copy()
    cat = [c for c in cols if c in CATEGORICAL_FEATURES][0]
    X2[cat] = "NEVER_SEEN"
    X2.loc[X2.index[:10], cols[0]] = np.nan
    got = [mf.score_loan(model, {k: _row(X2, i)[k] for k in cols}) for i in range(len(X2))]
    assert np.allclose([g["score"] for g in got], sc.score(X2), atol=1e-9)
    assert np.allclose([g["probability_of_default"] for g in got], sc.predict_proba(X2), atol=1e-12)


def test_value_exactly_on_a_band_edge_goes_to_the_lower_band(fitted):
    sc, model, X = fitted
    name = next(c for c in sc.selected_ if sc.bins_[c].kind == "numeric" and sc.bins_[c].edges)
    edge = sc.bins_[name].edges[0]
    base = {k: _row(X, 0)[k] for k in sc.selected_}
    X1 = X.head(1).copy()
    for v in (edge, np.nextafter(edge, 1e9), np.nextafter(edge, -1e9)):
        base[name], X1[name] = float(v), float(v)
        assert mf.score_loan(model, base)["score"] == pytest.approx(float(sc.score(X1)[0]), abs=1e-9)


def test_reasons_equal_the_scikit_learn_reasons(fitted):
    sc, model, X = fitted
    X2 = X.head(300)
    expected = rs.reasons(sc, X2, top_k=4, reason_table=_table())
    for i in range(len(X2)):
        loan = {k: _row(X2, i)[k] for k in sc.selected_}
        got = mf.explain_loan(model, mf.score_loan(model, loan), top_k=4)
        assert [(r["code"], round(r["points_lost"], 6)) for r in got] == [(r["code"], round(r["points_lost"], 6)) for r in expected[i]]


def test_loaded_file_validates_and_a_tampered_one_does_not(fitted):
    _, model, _ = fitted
    mf.validate_model(model)
    bad = copy.deepcopy(model)
    del bad["scaling"]
    with pytest.raises(mf.ModelFileError, match="missing key"):
        mf.validate_model(bad)
    bad = copy.deepcopy(model)
    bad["schema_version"] = 2
    with pytest.raises(mf.ModelFileError, match="schema_version"):
        mf.validate_model(bad)
    bad = copy.deepcopy(model)
    name = next(n for n in bad["feature_order"] if bad["features"][n]["type"] == "numeric" and len(bad["features"][n]["edges"]) >= 2)
    bad["features"][name]["edges"].reverse()
    with pytest.raises(mf.ModelFileError, match="increasing"):
        mf.validate_model(bad)
    bad = copy.deepcopy(model)
    bad["features"][bad["feature_order"][0]]["points"].pop()
    with pytest.raises(mf.ModelFileError):
        mf.validate_model(bad)
    bad = copy.deepcopy(model)
    bad["features"][bad["feature_order"][0]]["points"][0] = float("nan")
    with pytest.raises(mf.ModelFileError, match="finite"):
        mf.validate_model(bad)


def test_the_scorer_refuses_bad_inputs(fitted):
    sc, model, X = fitted
    loan = {k: _row(X, 3)[k] for k in sc.selected_}
    num = next(k for k in sc.selected_ if sc.bins_[k].kind == "numeric")
    cat = next(k for k in sc.selected_ if sc.bins_[k].kind == "categorical")
    with pytest.raises(ValueError, match="unknown fields"):
        mf.score_loan(model, {**loan, "surprise": 1})
    with pytest.raises(ValueError, match="missing fields"):
        mf.score_loan(model, {k: v for k, v in loan.items() if k != num})
    for bad in ("700", True, float("inf")):
        with pytest.raises(ValueError):
            mf.score_loan(model, {**loan, num: bad})
    with pytest.raises(ValueError):
        mf.score_loan(model, {**loan, cat: 5})


def test_hash_ignores_metadata_but_not_the_numbers(fitted):
    _, model, _ = fitted
    h = mf.canonical_hash(model)
    assert mf.canonical_hash({**model, "version": "other", "known_limits": ["x"]}) == h
    changed = copy.deepcopy(model)
    changed["features"][changed["feature_order"][0]]["points"][0] += 1
    assert mf.canonical_hash(changed) != h


def test_the_scorer_module_uses_the_standard_library_only():
    tree = ast.parse((ROOT / "credit" / "serving" / "model_file.py").read_text(encoding="utf-8"))
    imported = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    imported |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    assert imported <= {"bisect", "hashlib", "json", "math", "pathlib"}, imported


# ---- the committed model file (runs in CI too: the file is in the repository) -------------------------------------

def test_committed_model_file_is_valid_and_consistent():
    model = mf.load_model(MODEL_JSON)
    assert model["model"] == "woe_scorecard_v2" and model["known_limits"]
    assert model["model_id"] == mf.canonical_hash(model)[:12]
    assert "state" not in model["features"] and "channel" not in model["features"] and "super_conforming" not in model["features"]
    assert set(model["feature_order"]) == {"credit_score", "dti", "rate_spread", "ltv", "cltv", "several_borrowers", "mi_pct", "orig_term", "purpose"}


GOLDEN_LOAN = {"credit_score": 700, "dti": 44, "ltv": 85, "cltv": 85, "rate_spread": 0.55, "several_borrowers": 0.0,
               "mi_pct": 25, "orig_term": 360, "purpose": "P"}


def test_golden_loan_always_gets_the_same_score():
    """If this fails, the model file changed: that must be a deliberate, versioned decision."""
    model = mf.load_model(MODEL_JSON)
    out = mf.score_loan(model, GOLDEN_LOAN)
    assert out["score"] == pytest.approx(553.3, abs=0.2)
    assert out["probability_of_default"] == pytest.approx(0.0917, abs=0.0006)
    top = mf.explain_loan(model, out, top_k=3)
    assert [r["feature"] for r in top] == ["credit_score", "cltv", "dti"]


def test_score_orders_loans_sensibly():
    model = mf.load_model(MODEL_JSON)
    better = {**GOLDEN_LOAN, "credit_score": 800, "dti": 20}
    worse = {**GOLDEN_LOAN, "credit_score": 620, "dti": 55}
    s = [mf.score_loan(model, x) for x in (better, GOLDEN_LOAN, worse)]
    assert s[0]["score"] > s[1]["score"] > s[2]["score"]
    assert s[0]["probability_of_default"] < s[1]["probability_of_default"] < s[2]["probability_of_default"]
    assert all(0 < r["probability_of_default"] < 1 and math.isfinite(r["score"]) for r in s)


# ---- real data (skipped when the Freddie Mac files are absent, e.g. on GitHub) --------------------------------

def test_committed_file_reproduces_the_scikit_learn_model_on_real_loans():
    from credit.models.era_review import FEATURES_PATH, load_dev

    if not FEATURES_PATH.exists():
        pytest.skip("development features not available")
    from credit.models.v2_exam import TARGET, V2_CATEGORICAL, V2_NUMERIC, v2_config

    dev = load_dev()
    cols = V2_NUMERIC + V2_CATEGORICAL
    sc = Scorecard(v2_config(), V2_NUMERIC, V2_CATEGORICAL).fit(dev[cols], dev[TARGET])
    model = mf.load_model(MODEL_JSON)
    sample = dev.sample(20000, random_state=1).reset_index(drop=True)
    expected_score, expected_pd = sc.score(sample[cols]), sc.predict_proba(sample[cols])
    got = [mf.score_loan(model, {c: (None if pd.isna(sample.at[i, c]) else (float(sample.at[i, c]) if c in V2_NUMERIC else str(sample.at[i, c]))) for c in cols})
           for i in range(len(sample))]
    assert np.max(np.abs(np.array([g["score"] for g in got]) - expected_score)) < 1e-9
    assert np.max(np.abs(np.array([g["probability_of_default"] for g in got]) - expected_pd)) < 1e-12
