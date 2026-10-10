"""API tests: contract, rejection of bad input, golden loan, equivalence with the file scorer, start-up refusal."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from credit.serving.model_file import ModelFileError, load_model, score_loan
from service.main import DEFAULT_MODEL_PATH, create_app, to_model_input
from service.schemas import LoanRequest

GOLDEN = {
    "credit_score": 700, "dti": 44.0, "ltv": 85.0, "cltv": 85.0, "interest_rate": 4.55, "reference_rate": 4.00,
    "number_of_borrowers": 1, "mi_pct": 25.0, "term_months": 360, "purpose": "P",
}


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model_id"] == load_model(DEFAULT_MODEL_PATH)["model_id"]


def test_model_info_shows_limits_and_ranges(client):
    body = client.get("/model-info").json()
    assert body["known_limits"], "limits must be visible"
    assert set(body["training_ranges"]) >= {"credit_score", "dti", "ltv"}
    assert body["scaling"]["base_score"] == 600
    assert "purpose" in body["features"]


def test_golden_loan_score(client):
    r = client.post("/score", json=GOLDEN)
    assert r.status_code == 200
    body = r.json()
    assert body["score"] == pytest.approx(553.304, abs=0.01)
    assert body["probability_of_default"] == pytest.approx(0.09165, abs=1e-4)
    assert body["outside_training_range"] == []
    assert "decision" not in body and "approved" not in body  # the API never decides


def test_explain_golden_reasons(client):
    body = client.post("/explain", json=GOLDEN).json()
    assert [r["feature"] for r in body["reasons"][:3]] == ["credit_score", "cltv", "dti"]
    assert all(r["points_lost"] >= 5 for r in body["reasons"])
    assert body["score"] == pytest.approx(sum(body["points"].values()))


def test_explain_top_k(client):
    assert len(client.post("/explain?top_k=1", json=GOLDEN).json()["reasons"]) == 1
    assert client.post("/explain?top_k=0", json=GOLDEN).status_code == 422
    assert client.post("/explain?top_k=99", json=GOLDEN).status_code == 422


def test_equivalence_with_file_scorer(client):
    model = load_model(DEFAULT_MODEL_PATH)
    for score_in, dti, ltv, rate in [(620, 50.0, 97.0, 6.5), (780, 20.0, 60.0, 3.0), (None, None, 80.0, 4.0)]:
        loan = {**GOLDEN, "credit_score": score_in, "dti": dti, "ltv": ltv, "cltv": ltv, "interest_rate": rate}
        api = client.post("/score", json=loan).json()
        direct = score_loan(model, to_model_input(LoanRequest(**loan)))
        assert api["score"] == direct["score"]
        assert api["probability_of_default"] == direct["probability_of_default"]


def test_unknown_field_rejected(client):
    assert client.post("/score", json={**GOLDEN, "income": 90000}).status_code == 422


def test_missing_field_rejected(client):
    loan = dict(GOLDEN)
    del loan["dti"]
    assert client.post("/score", json=loan).status_code == 422


@pytest.mark.parametrize("field,value", [
    ("credit_score", 900), ("credit_score", 200), ("credit_score", "700"), ("credit_score", 700.5),
    ("dti", -1.0), ("dti", 90.0), ("dti", "high"), ("ltv", 0.0), ("ltv", 1000.0),
    ("interest_rate", 25.0), ("interest_rate", -1.0), ("number_of_borrowers", 0),
    ("term_months", 12), ("term_months", 1200), ("purpose", "X"), ("purpose", 1), ("mi_pct", 80.0),
    ("dti", True), ("dti", float("inf")),
])
def test_bad_values_rejected(client, field, value):
    # json= refuses inf/nan on some versions, so send raw text
    payload = json.dumps({**GOLDEN, field: value}, allow_nan=True)
    r = client.post("/score", content=payload, headers={"content-type": "application/json"})
    assert r.status_code == 422, (field, value, r.text)


def test_not_json_rejected(client):
    r = client.post("/score", content="not json", headers={"content-type": "application/json"})
    assert r.status_code == 422


def test_nulls_use_missing_band(client):
    loan = {k: None for k in GOLDEN}
    r = client.post("/score", json=loan)
    assert r.status_code == 200
    assert 0 < r.json()["probability_of_default"] < 1


def test_borrower_flag_and_spread_derivation():
    one = to_model_input(LoanRequest(**GOLDEN))
    two = to_model_input(LoanRequest(**{**GOLDEN, "number_of_borrowers": 2}))
    assert one["several_borrowers"] == 0.0 and two["several_borrowers"] == 1.0
    assert one["rate_spread"] == pytest.approx(0.55)
    assert to_model_input(LoanRequest(**{**GOLDEN, "reference_rate": None}))["rate_spread"] is None


def test_outside_training_range_flagged(client):
    body = client.post("/score", json={**GOLDEN, "credit_score": 450, "term_months": 600}).json()
    assert set(body["outside_training_range"]) == {"credit_score", "orig_term"}


def test_openapi_documents_endpoints(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert set(paths) == {"/health", "/model-info", "/score", "/explain"}


def test_startup_refuses_missing_model(tmp_path):
    with pytest.raises(FileNotFoundError), TestClient(create_app(tmp_path / "nope.json")):
        pass


def test_startup_refuses_damaged_model(tmp_path):
    bad = tmp_path / "bad.json"
    model = json.loads(Path(DEFAULT_MODEL_PATH).read_text(encoding="utf-8"))
    del model["scaling"]
    bad.write_text(json.dumps(model), encoding="utf-8")
    with pytest.raises(ModelFileError), TestClient(create_app(bad)):
        pass
