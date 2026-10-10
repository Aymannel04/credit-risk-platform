"""Freeze everything that defines the final exam BEFORE the exam is run.

Writes results/frozen_before_exam.json: the models and settings, the rules (which calibration, how the
confidence intervals are drawn), and fingerprints (SHA-256) of the features file and the config. The
exam script refuses to run unless this file is committed and nothing it describes has changed since.

Usage (from the repo root):  .venv/Scripts/python -m credit.models.freeze
"""
import hashlib
import json
import subprocess
from pathlib import Path

from credit.models.data import FEATURES_PATH
from credit.models.scorecard import CONFIG_PATH
from credit.models.xgboost_model import PARAMS

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "results" / "frozen_before_exam.json"

# Code that defines the models and the data: it must be unchanged between the freeze commit and the exam.
WATCHED_PATHS = ["credit", "config"]

EXAM_RULES = {
    "models": ["scorecard", "logistic_regression", "xgboost"],
    "trained_on": "split == 'train' only (calibration and validation rows are NOT used for the final fit)",
    "calibration": "none: raw probabilities. Reason (validation, 2026-10-09): Platt slope 1.00 and no Brier gain "
                   "for the unweighted models; a calibrator must earn its place on validation.",
    "exams": ["test_in_time", "test_oot_2019", "test_oot_2022"],
    "metrics": ["gini", "auc", "ks", "pr_auc", "brier", "ece", "mean_predicted_pd", "default_rate"],
    "confidence_intervals": {"method": "bootstrap over loans, paired across models", "resamples": 1000,
                             "seed": 20261010, "interval": "2.5% - 97.5%"},
    "after_the_exam": "no model, feature, setting or rule may be changed to improve these results; any later "
                      "change is a new, labelled experiment and these numbers stay in the record",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def build_manifest() -> dict:
    return {
        "frozen_at_commit": git("rev-parse", "HEAD"),
        "features_sha256": sha256(FEATURES_PATH),
        "assumptions_sha256": sha256(CONFIG_PATH),
        "xgboost_params": {k: v for k, v in PARAMS.items()},
        "rules": EXAM_RULES,
    }


if __name__ == "__main__":
    m = build_manifest()
    MANIFEST.write_text(json.dumps(m, indent=2), encoding="utf-8")
    print(f"frozen at commit {m['frozen_at_commit'][:10]}; features {m['features_sha256'][:12]}...; "
          f"config {m['assumptions_sha256'][:12]}...")
    print(f"wrote {MANIFEST.relative_to(ROOT)}: now COMMIT it, then run credit.models.final_exam")
