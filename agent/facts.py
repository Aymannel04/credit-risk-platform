"""The fact sheet: the ONLY information the writer may use, and the reference the inspector checks the memo against.

Built by plain code from the loan that was sent to the scoring API and the API's answer (`/explain`). The recommendation is computed
here (agent.policy.decide), never by the language model. Every number is stored twice: `numbers` (plain text with a decimal point, used
for checking) and `display` (how it must be written in the memo: with a decimal comma in French).
"""
from decimal import ROUND_HALF_UP, Decimal

from agent.policy import Policy, decide
from agent.template import render_data_section

LOAN_FIELDS = ("credit_score", "dti", "ltv", "cltv", "interest_rate", "reference_rate", "number_of_borrowers", "mi_pct", "term_months")
PERCENT_FIELDS = ("dti", "ltv", "cltv", "interest_rate", "reference_rate", "mi_pct")


def _trim(value: Decimal) -> str:
    """44.0 -> '44', 4.550 -> '4.55' (plain notation, never an exponent)."""
    text = format(value.normalize(), "f")
    return text


def _fixed(value: Decimal, decimals: int) -> str:
    return format(value.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP), "f")


def _show(text: str, language: str, percent: bool = False) -> str:
    out = text.replace(".", ",") if language == "fr" else text
    if percent:
        out += " %" if language == "fr" else "%"
    return out


def build_facts(loan: dict, answer: dict, policy: Policy, language: str | None = None) -> dict:
    lang = policy.language(language)
    numbers: dict[str, str] = {}
    display: dict[str, str] = {}

    def put(name: str, text: str, percent: bool = False) -> None:
        numbers[name] = text
        display[name] = _show(text, lang.code, percent)

    for field in LOAN_FIELDS:
        value = loan.get(field)
        if value is not None:
            put(field, _trim(Decimal(str(value))), percent=field in PERCENT_FIELDS)
    if loan.get("interest_rate") is not None and loan.get("reference_rate") is not None:
        put("rate_spread", _trim(Decimal(str(loan["interest_rate"])) - Decimal(str(loan["reference_rate"]))), percent=True)
    if loan.get("term_months") is not None:
        put("term_years", _trim((Decimal(str(loan["term_months"])) / 12).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))

    probability = Decimal(str(answer["probability_of_default"]))
    put("score", _fixed(Decimal(str(answer["score"])), 1))
    put("probability_of_default", _fixed(probability * 100, 2), percent=True)
    put("approve_below", _trim(Decimal(str(policy.approve_below)) * 100), percent=True)
    put("decline_above", _trim(Decimal(str(policy.decline_above)) * 100), percent=True)
    put("caution_low", policy.caution_low)
    put("caution_high", policy.caution_high)

    reasons = []
    for i, r in enumerate(answer.get("reasons", []), start=1):
        put(f"points_lost_{i}", _fixed(Decimal(str(r["points_lost"])), 1))
        reasons.append({"feature": r["feature"], "phrase": lang.reason_phrases.get(r["feature"], r["phrase"]), "points_lost": f"points_lost_{i}"})

    decision = decide(float(answer["probability_of_default"]), policy)
    return {
        "language": lang.code,
        "recommendation": decision,
        "recommendation_label": lang.labels[decision],
        "numbers": numbers,
        "display": display,
        "reasons": reasons,
        "outside_training_range": list(answer.get("outside_training_range", [])),
        "headings": list(lang.headings),
        "disclaimer": lang.disclaimer,
        "caution": lang.caution.format(low=display["caution_low"], high=display["caution_high"]),
        "outside_range_text": lang.outside_range.format(fields=", ".join(answer["outside_training_range"])) if answer.get("outside_training_range") else "",
        "unknown": lang.unknown,
        "data_section": render_data_section(lang.code, display, lang.unknown),
    }
