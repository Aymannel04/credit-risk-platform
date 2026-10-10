"""Fit the adopted v2 scorecard on all rows of the five known vintages and export its points table (aggregates only).

Run AFTER the v2 exam (the exam fixed the features and settings; nothing here changes them).
Usage (from the repo root):  .venv/Scripts/python scripts/export_v2_scorecard.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from credit.models.era_review import load_dev  # noqa: E402
from credit.models.scorecard import Scorecard  # noqa: E402
from credit.models.v2_exam import TARGET, V2_CATEGORICAL, V2_NUMERIC, v2_config  # noqa: E402

dev = load_dev()
sc = Scorecard(v2_config(), V2_NUMERIC, V2_CATEGORICAL).fit(dev[V2_NUMERIC + V2_CATEGORICAL], dev[TARGET])
table = sc.points_table()
iv = pd.DataFrame({"feature": list(sc.bins_), "iv_pooled": [fb.iv for fb in sc.bins_.values()]}).sort_values("iv_pooled", ascending=False)
table.round(4).to_csv(ROOT / "results" / "scorecard_v2_table.csv", index=False)
iv.round(4).to_csv(ROOT / "results" / "scorecard_v2_iv.csv", index=False)
print("sign violations:", sc.sign_violations() or "none")
print("score range on the development rows:", round(float(sc.score(dev[V2_NUMERIC + V2_CATEGORICAL]).min())), "..", round(float(sc.score(dev[V2_NUMERIC + V2_CATEGORICAL]).max())))
for f in ("credit_score", "dti", "purpose", "several_borrowers"):
    print(f"\n{f}")
    print(table[table.feature == f][["band", "loans", "default_rate", "points"]].round(3).to_string(index=False))
