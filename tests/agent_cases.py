"""Made-up loans for the memo-agent tests, scored by the REAL scoring API (in process, no network). Not a test file itself."""
from fastapi.testclient import TestClient

from service.main import create_app

BASE = dict(credit_score=700, dti=44.0, ltv=85.0, cltv=85.0, interest_rate=4.55, reference_rate=4.0, number_of_borrowers=1,
            mi_pct=25.0, term_months=360, purpose="P")

LOANS = {
    "golden_decline": BASE,
    "prime_approve": dict(BASE, credit_score=800, dti=20.0, ltv=60.0, cltv=60.0, interest_rate=3.0, reference_rate=3.0,
                          number_of_borrowers=2, mi_pct=0.0, purpose="N"),
    "middle_refer": dict(BASE, credit_score=720, dti=36.0, interest_rate=4.2),
    "weak_decline": dict(BASE, credit_score=620, dti=50.0, ltv=95.0, cltv=97.0, interest_rate=6.2, mi_pct=30.0),
    "outside_range": dict(BASE, credit_score=300, dti=65.0),
    "unknown_fields": dict(BASE, credit_score=None, dti=None, mi_pct=None),
}
EXPECTED_DECISION = {"golden_decline": "decline", "prime_approve": "approve", "middle_refer": "refer", "weak_decline": "decline",
                     "outside_range": "decline", "unknown_fields": "decline"}


def explain_all() -> dict[str, dict]:
    with TestClient(create_app()) as client:
        out = {}
        for name, loan in LOANS.items():
            response = client.post("/explain", json=loan)
            assert response.status_code == 200, (name, response.text)
            out[name] = response.json()
        return out
