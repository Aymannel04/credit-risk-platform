"""The inspector and its cheat tests. A correct memo (the backup memo written by code) is damaged in every way we can think of; the
inspector must reject each damaged memo, and must accept the correct ones. Nothing here needs a network or a language model."""
import re
from decimal import Decimal

import pytest

from agent.facts import build_facts
from agent.policy import load_policy
from agent.template import render_template_memo
from agent.validator import NUMBER, _allowed_values, _is_fact, problems_to_text, validate_memo
from tests.agent_cases import LOANS, explain_all

POLICY = load_policy()
LANGUAGES = ("fr", "en")


@pytest.fixture(scope="module")
def sheets():
    answers = explain_all()
    return {(name, lang): build_facts(LOANS[name], answers[name], POLICY, lang) for name in LOANS for lang in LANGUAGES}


def codes(memo, facts):
    return {p.code for p in validate_memo(memo, facts, POLICY)}


# ---------- the correct memo passes ----------

def test_the_backup_memo_always_passes_the_inspector(sheets):
    for key, facts in sheets.items():
        memo = render_template_memo(facts)
        assert validate_memo(memo, facts, POLICY) == [], (key, problems_to_text(validate_memo(memo, facts, POLICY)))


def test_the_backup_memos_have_a_sensible_length_and_the_right_decision(sheets):
    for key, facts in sheets.items():
        memo = render_template_memo(facts)
        assert 60 <= len(re.findall(r"\w+", memo)) <= 260, key
        assert facts["recommendation_label"] in memo


# ---------- the cheat test: every wrong number is caught ----------

def _wrong_token(token: str, allowed: list[Decimal]) -> str:
    """The smallest change to the last written digit that is NOT a fact of the sheet."""
    sep = "," if "," in token else "."
    d = len(token.replace(",", ".").split(".")[1]) if re.search(r"[.,]", token) else 0
    unit = Decimal(1).scaleb(-d)
    candidate = Decimal(token.replace(",", ".")) + unit
    while _is_fact(f"{candidate:.{d}f}", allowed):
        candidate += unit
    return f"{candidate:.{d}f}".replace(".", sep)


def test_every_single_wrong_number_is_caught(sheets):
    checked = 0
    for key, facts in sheets.items():
        memo = render_template_memo(facts)
        allowed = _allowed_values(facts, POLICY)
        for m in list(NUMBER.finditer(memo)):
            damaged = memo[: m.start()] + _wrong_token(m.group(), allowed) + memo[m.end():]
            assert "NUMBER_NOT_IN_FACTS" in codes(damaged, facts), (key, m.group(), memo[max(0, m.start() - 30): m.end() + 10])
            checked += 1
    assert checked > 250, f"only {checked} numbers were attacked: the test would be too weak"


def test_a_number_that_is_not_on_the_sheet_is_caught_wherever_it_is_added(sheets):
    facts = sheets[("golden_decline", "fr")]
    memo = render_template_memo(facts)
    for extra in ("Le taux de défaut réel est de 12,5 %.", "Environ 777 emprunteurs similaires.", "Version v7 du modèle.", "Soit 0.0917."):
        assert "NUMBER_NOT_IN_FACTS" in codes(memo + "\n" + extra, facts), extra


def test_rounding_rule_accepts_a_coarser_number_but_never_a_different_one():
    allowed = [Decimal("9.17"), Decimal("553.3")]
    assert all(_is_fact(t, allowed) for t in ("9.17", "9,17", "9.2", "9", "553.3", "553", "9.170"))
    assert not any(_is_fact(t, allowed) for t in ("9.1", "9.18", "10", "8", "553.4", "554", "0.0917"))


# ---------- the decision word ----------

def test_a_different_decision_word_is_caught(sheets):
    for (name, lang), facts in sheets.items():
        memo = render_template_memo(facts)
        for other, label in POLICY.language(lang).labels.items():
            if other == facts["recommendation"]:
                continue
            damaged = memo.replace(facts["recommendation_label"], label)
            found = codes(damaged, facts)
            assert {"DECISION_MISSING", "DECISION_CONFLICT"} <= found, (name, lang, other, found)


def test_a_missing_decision_is_caught(sheets):
    facts = sheets[("middle_refer", "fr")]
    memo = render_template_memo(facts).replace("À EXAMINER", "")
    assert "DECISION_MISSING" in codes(memo, facts)


# ---------- structure ----------

def _split(memo):
    parts = re.split(r"(?m)^(?=## )", memo)
    return [p for p in parts if p.strip()]


def test_a_missing_reordered_extra_or_renamed_section_is_caught(sheets):
    for key, facts in sheets.items():
        memo = render_template_memo(facts)
        parts = _split(memo)
        assert len(parts) == 6
        for i in range(6):
            assert "SECTIONS" in codes("".join(parts[:i] + parts[i + 1:]), facts), (key, "removed", i)
        swapped = parts[:]
        swapped[1], swapped[2] = swapped[2], swapped[1]
        assert "SECTIONS" in codes("".join(swapped), facts)
        assert "SECTIONS" in codes(memo + "\n## Extra\nbla", facts)
        assert "SECTIONS" in codes(memo.replace(facts["headings"][0], "Intro", 1), facts)


def test_text_before_the_first_heading_and_empty_sections_are_caught(sheets):
    facts = sheets[("golden_decline", "en")]
    memo = render_template_memo(facts)
    assert "TEXT_OUTSIDE_SECTIONS" in codes("Sure! Here is the memo.\n" + memo, facts)
    parts = _split(memo)
    emptied = "".join(parts[:3] + [parts[3].split("\n")[0] + "\n\n"] + parts[4:])
    assert "EMPTY_SECTION" in codes(emptied, facts)


# ---------- sentences that must be there ----------

def test_missing_mandatory_sentences_are_caught(sheets):
    for key, facts in sheets.items():
        memo = render_template_memo(facts)
        assert "DISCLAIMER_MISSING" in codes(memo.replace(facts["disclaimer"], ""), facts), key
        assert "CAUTION_MISSING" in codes(memo.replace(facts["caution"], ""), facts), key
        assert "RISK_MISSING" in codes(memo.replace(facts["display"]["probability_of_default"], "un risque"), facts), key
        if facts["outside_range_text"]:
            assert "OUTSIDE_RANGE_MISSING" in codes(memo.replace(facts["outside_range_text"], ""), facts), key


def test_the_percent_sign_spacing_does_not_matter(sheets):
    facts = sheets[("golden_decline", "fr")]
    memo = render_template_memo(facts).replace("9,17 %", "9,17%")
    assert validate_memo(memo, facts, POLICY) == []


# ---------- forbidden claims, numbers in words, length, language ----------

def test_promises_and_numbers_in_words_are_caught(sheets):
    fr, en = sheets[("prime_approve", "fr")], sheets[("prime_approve", "en")]
    base_fr, base_en = render_template_memo(fr), render_template_memo(en)
    for word in ("garanti", "sans risque", "jamais", "certainement"):
        assert "FORBIDDEN_PHRASE" in codes(base_fr + f"\nCe prêt est {word}.", fr), word
    for word in ("guaranteed", "risk-free", "never", "definitely"):
        assert "FORBIDDEN_PHRASE" in codes(base_en + f"\nThis loan is {word}.", en), word
    for word in ("dix-sept", "pour cent", "trois", "cent", "mille"):
        assert "SPELLED_NUMBER" in codes(base_fr + f"\nEnviron {word} dossiers.", fr), word
    for word in ("seventeen" if False else "twenty", "percent", "three", "hundred"):
        assert "SPELLED_NUMBER" in codes(base_en + f"\nAbout {word} files.", en), word


def test_too_long_and_too_short_memos_are_caught(sheets):
    facts = sheets[("golden_decline", "fr")]
    memo = render_template_memo(facts)
    assert "LENGTH" in codes(memo + "\n" + "mot " * 300, facts)
    short = "".join(f"## {h}\nx\n" for h in facts["headings"])
    assert "LENGTH" in codes(short, facts)


def test_a_memo_in_the_other_language_is_caught(sheets):
    fr, en = sheets[("golden_decline", "fr")], sheets[("golden_decline", "en")]
    assert {"SECTIONS", "DISCLAIMER_MISSING"} <= codes(render_template_memo(en), fr)
    assert {"SECTIONS", "DISCLAIMER_MISSING"} <= codes(render_template_memo(fr), en)


# ---------- robustness and honesty ----------

@pytest.mark.parametrize("junk", ["", "   ", "\n\n", "9", "##", "## ##", "# # #", "é" * 5000, "9,9,9,9", "0.0.0", "%%%", "\x00\x01", "1" * 400,
                                  "## Résumé\n" * 6])
def test_garbage_never_crashes_the_inspector_and_is_never_accepted(sheets, junk):
    facts = sheets[("golden_decline", "fr")]
    result = validate_memo(junk, facts, POLICY)
    assert isinstance(result, list) and result, "garbage must be rejected"


def test_the_data_section_cannot_be_changed_even_by_swapping_two_facts(sheets):
    """The 'Loan data' section is written by code and compared word for word: swapping the credit score (700) with the loan-to-value (85)
    there is caught, although both numbers are on the sheet."""
    facts = sheets[("golden_decline", "en")]
    memo = render_template_memo(facts)
    swapped = memo.replace("- Credit score: 700", "- Credit score: 85").replace("- Loan to value: 85%", "- Loan to value: 700%")
    assert swapped != memo
    assert "DATA_SECTION_ALTERED" in codes(swapped, facts)
    assert "NUMBER_NOT_IN_FACTS" not in codes(swapped, facts), "each swapped number IS on the sheet: only the word-for-word comparison catches it"


def test_known_limit_swapping_two_facts_in_the_free_text_is_not_caught(sheets):
    """Documented limit: outside the protected data section the inspector checks that a number is ON the sheet, not WHICH fact it belongs
    to. Swapping the two policy lines (2 and 5) in the risk analysis gives two numbers that are both facts, so it passes."""
    facts = sheets[("golden_decline", "en")]
    memo = render_template_memo(facts)
    swapped = memo.replace("policy: 2% and 5%", "policy: 5% and 2%")
    assert swapped != memo
    assert validate_memo(swapped, facts, POLICY) == []


# ---------- negative numbers (found by the held-out loans: an interest rate below its reference gives a negative gap) ----------

def _negative_gap_facts():
    from tests.agent_cases import BASE

    loan = dict(BASE, interest_rate=3.4, reference_rate=3.7)
    answer = explain_all()["golden_decline"]
    return build_facts(loan, answer, POLICY, "fr")


def test_a_negative_fact_is_copied_with_its_sign_and_the_backup_memo_passes():
    facts = _negative_gap_facts()
    assert facts["numbers"]["rate_spread"] == "-0.3" and facts["display"]["rate_spread"] == "-0,3 %"
    memo = render_template_memo(facts)
    assert "-0,3 %" in memo and validate_memo(memo, facts, POLICY) == []


def test_a_lost_or_flipped_sign_is_caught_and_the_typographic_minus_is_accepted():
    facts = _negative_gap_facts()
    memo = render_template_memo(facts)
    assert "NUMBER_NOT_IN_FACTS" in codes(memo + "\nL'écart de taux est de 0,3 %.", facts), "0,3 is not -0,3"
    assert "NUMBER_NOT_IN_FACTS" not in codes(memo + "\nL'écart de taux est de -0,3 %.", facts)
    assert "NUMBER_NOT_IN_FACTS" not in codes(memo + "\nL'écart de taux est de " + chr(0x2212) + "0,3 %.", facts)
    assert "NUMBER_NOT_IN_FACTS" in codes(memo + "\nUn écart de +0,3 % ou -3,4 %.", facts)


def test_a_hyphen_between_numbers_is_not_a_minus_sign():
    from agent.validator import NUMBER

    assert NUMBER.findall("ratio 36-40 et x-0,3 puis -5 et (-0,3)") == ["36", "40", "0,3", "-5", "-0,3"]
