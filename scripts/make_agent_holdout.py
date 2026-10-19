"""Make the held-out loans of the memo agent: 20 made-up loans drawn with a fixed random seed.

    python scripts/make_agent_holdout.py            # rewrites agent/cases/holdout_cases.json (the same file every time)

The 15 loans of agent/cases/eval_cases.json were used while the instructions of the writer were being improved (a failure was read, the
instructions were corrected). These 20 were generated afterwards and are NOT looked at while tuning: they give the numbers that are reported.
Every value stays inside the ranges the API accepts; the loans are random, not chosen, so they include dull, odd and risky ones.
"""
import json
import random
from pathlib import Path

SEED = 20261019
COUNT = 20
OUT = Path(__file__).resolve().parents[1] / "agent" / "cases" / "holdout_cases.json"


SEED_2 = 31415926
OUT_2 = OUT.with_name("holdout2_cases.json")


def make_loans(seed: int = SEED, count: int = COUNT, prefix: str = "h") -> list[dict]:
    rng = random.Random(seed)
    cases = []
    for i in range(1, count + 1):
        ltv = float(rng.choice([40, 50, 60, 70, 75, 80, 85, 90, 95, 97]))
        reference = round(rng.uniform(3.2, 4.8), 1)
        loan = {
            "credit_score": rng.choice([None] + [rng.randrange(560, 830, 5) for _ in range(19)]),
            "dti": rng.choice([None] + [float(rng.randrange(10, 58, 2)) for _ in range(19)]),
            "ltv": ltv,
            "cltv": min(ltv + float(rng.choice([0, 0, 0, 5, 10])), 100.0),
            "interest_rate": round(reference + rng.choice([-0.3, -0.1, 0.0, 0.1, 0.2, 0.4, 0.8, 1.5, 2.5]), 2),
            "reference_rate": reference,
            "number_of_borrowers": rng.choice([1, 1, 1, 2, 2, 3]),
            "mi_pct": float(rng.choice([0, 0, 0, 12, 18, 25, 30])),
            "term_months": rng.choice([120, 180, 240, 300, 360, 360, 360, 480]),
            "purpose": rng.choice(["P", "P", "C", "N", "R"]),
        }
        cases.append({"id": f"{prefix}{i:02d}", "description": "random loan (fixed seed)", "loan": loan})
    return cases


if __name__ == "__main__":
    OUT.write_text(json.dumps(make_loans(), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    OUT_2.write_text(json.dumps(make_loans(SEED_2, COUNT, "g"), indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name} (seed {SEED}, ids h01..h20, already used for error analysis) and {OUT_2.name} (seed {SEED_2}, ids g01..g20, fresh)")
