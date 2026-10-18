"""The chef's decision and the rules of the memo agent, read from config/memo_policy.yaml.

The decision (approve / refer / decline) is computed here, by plain code, from the probability of default returned by the scoring API.
The language model never decides and never sees the two decision lines as something it could change.
"""
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "config" / "memo_policy.yaml"
DECISIONS = ("approve", "refer", "decline")
SECTIONS = 6
DATA_SECTION_INDEX = 1          # the 'Loan data' section: written by code, never by the model
RECOMMENDATION_SECTION_INDEX = 4


class PolicyError(ValueError):
    pass


@dataclass(frozen=True)
class Language:
    code: str
    headings: list[str]
    labels: dict[str, str]
    decision_stems: dict[str, list[str]]
    disclaimer: str
    caution: str
    outside_range: str
    unknown: str
    forbidden: list[str]
    spelled_numbers: list[str]
    reason_phrases: dict[str, str]


@dataclass(frozen=True)
class Policy:
    approve_below: float
    decline_above: float
    default_language: str
    max_rewrites: int
    min_words: int
    max_words: int
    allowed_constants: tuple[str, ...]
    caution_low: str
    caution_high: str
    languages: dict[str, Language]
    writers: dict[str, dict]

    def language(self, code: str | None = None) -> Language:
        code = code or self.default_language
        if code not in self.languages:
            raise PolicyError(f"unknown language '{code}' (known: {sorted(self.languages)})")
        return self.languages[code]


def load_policy(path: Path = POLICY_PATH) -> Policy:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    p, m = raw["policy"], raw["memo"]
    approve_below, decline_above = float(p["approve_below"]), float(p["decline_above"])
    if not 0 < approve_below <= decline_above < 1:
        raise PolicyError("the lines must satisfy 0 < approve_below <= decline_above < 1")
    languages = {}
    for code, spec in raw["languages"].items():
        if len(spec["headings"]) != SECTIONS or len(set(spec["headings"])) != SECTIONS:
            raise PolicyError(f"{code}: exactly {SECTIONS} different headings are required")
        if set(spec["labels"]) != set(DECISIONS) or set(spec["decision_stems"]) != set(DECISIONS):
            raise PolicyError(f"{code}: labels and decision_stems need the keys {DECISIONS}")
        languages[code] = Language(code=code, reason_phrases=spec.get("reason_phrases") or {}, **{
            k: spec[k] for k in ("headings", "labels", "decision_stems", "disclaimer", "caution", "outside_range", "unknown",
                                 "forbidden", "spelled_numbers")})
    if m["default_language"] not in languages:
        raise PolicyError("default_language is not a defined language")
    if m["min_words"] >= m["max_words"]:
        raise PolicyError("min_words must be below max_words")
    return Policy(approve_below=approve_below, decline_above=decline_above, default_language=m["default_language"],
                  max_rewrites=int(m["max_rewrites"]), min_words=int(m["min_words"]), max_words=int(m["max_words"]),
                  allowed_constants=tuple(str(x) for x in m["allowed_constants"]),
                  caution_low=str(m["caution_numbers"]["low"]), caution_high=str(m["caution_numbers"]["high"]), languages=languages,
                  writers=dict(raw.get("writers") or {}))


def decide(probability_of_default: float, policy: Policy) -> str:
    """approve under the first line, decline above the second, refer to a human in between (a value exactly on a line is referred)."""
    if not 0.0 <= probability_of_default <= 1.0:
        raise PolicyError(f"a probability must be between 0 and 1, got {probability_of_default}")
    if probability_of_default < policy.approve_below:
        return "approve"
    if probability_of_default > policy.decline_above:
        return "decline"
    return "refer"
