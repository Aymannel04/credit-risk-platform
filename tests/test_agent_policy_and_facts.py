"""The chef: the two decision lines, the policy file, and the fact sheet built from the real API's answers."""
import pytest
import yaml

from agent.facts import build_facts
from agent.policy import POLICY_PATH, ROOT, PolicyError, decide, load_policy
from service.main import CAUTION
from tests.agent_cases import EXPECTED_DECISION, LOANS, explain_all

POLICY = load_policy()


@pytest.fixture(scope="module")
def answers():
    return explain_all()


# ---------- the decision ----------

@pytest.mark.parametrize("probability, expected", [
    (0.0, "approve"), (0.0199, "approve"), (0.02, "refer"), (0.0201, "refer"), (0.05, "refer"), (0.0501, "decline"), (1.0, "decline")])
def test_decision_lines(probability, expected):
    assert decide(probability, POLICY) == expected, "a value exactly on a line goes to the human"


@pytest.mark.parametrize("bad", [-0.01, 1.01, 5])
def test_a_probability_outside_0_1_is_refused(bad):
    with pytest.raises(PolicyError):
        decide(bad, POLICY)


def test_the_decision_is_monotone():
    order = {"approve": 0, "refer": 1, "decline": 2}
    values = [decide(i / 1000, POLICY) for i in range(0, 1001)]
    assert [order[v] for v in values] == sorted(order[v] for v in values), "riskier never gets a kinder decision"


# ---------- the policy file ----------

def test_policy_file_is_loaded_and_the_lines_are_the_documented_assumption():
    assert (POLICY.approve_below, POLICY.decline_above) == (0.02, 0.05)
    assert POLICY.default_language == "fr" and set(POLICY.languages) == {"fr", "en"}
    assert "ASSUMPTION" in POLICY_PATH.read_text(encoding="utf-8"), "the lines must stay labelled as an assumption"


def _write(tmp_path, mutate):
    raw = yaml.safe_load(POLICY_PATH.read_text(encoding="utf-8"))
    mutate(raw)
    path = tmp_path / "policy.yaml"
    path.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return path


@pytest.mark.parametrize("mutate", [
    lambda r: r["policy"].update(approve_below=0.06),
    lambda r: r["policy"].update(approve_below=0),
    lambda r: r["policy"].update(decline_above=1),
    lambda r: r["languages"]["fr"]["headings"].pop(),
    lambda r: r["languages"]["fr"]["headings"].__setitem__(1, r["languages"]["fr"]["headings"][0]),
    lambda r: r["languages"]["en"]["labels"].pop("refer"),
    lambda r: r["memo"].update(default_language="de"),
    lambda r: r["memo"].update(min_words=300),
])
def test_a_broken_policy_file_is_refused(tmp_path, mutate):
    with pytest.raises(PolicyError):
        load_policy(_write(tmp_path, mutate))


def test_unknown_language_is_refused():
    with pytest.raises(PolicyError):
        POLICY.language("de")


def test_the_caution_numbers_in_the_policy_are_the_ones_the_api_states():
    assert POLICY.caution_low in CAUTION and POLICY.caution_high in CAUTION


def test_every_reportable_reason_has_a_french_sentence_without_digits():
    reasons = yaml.safe_load((ROOT / "config" / "reason_codes.yaml").read_text(encoding="utf-8"))
    reportable = {k for k, v in reasons.items() if v.get("reportable", True)}
    french = POLICY.language("fr").reason_phrases
    assert reportable <= set(french), reportable - set(french)
    assert not any(ch.isdigit() for text in french.values() for ch in text)


def _matches(lang, decision, text):
    import re

    patterns = [re.escape(lang.labels[decision].casefold()), *[s.casefold() for s in lang.decision_stems[decision]]]
    return [p for p in patterns if re.search(rf"(?<!\w)(?:{p})(?!\w)", text.casefold())]


def test_the_words_of_one_decision_never_match_the_words_of_another():
    for lang in POLICY.languages.values():
        for a in lang.labels:
            assert _matches(lang, a, lang.labels[a]), (lang.code, a, "a decision must recognise its own label")
            for b in lang.labels:
                if a != b:
                    assert not _matches(lang, a, lang.labels[b]), (lang.code, a, b)
        for heading in lang.headings:
            assert not any(_matches(lang, d, heading) for d in lang.labels), (lang.code, heading)
        assert not any(_matches(lang, d, "Reference rate / taux de référence") for d in lang.labels), "'reference' is not 'refer'"


# ---------- the fact sheet ----------

def test_the_decision_of_every_example_loan_comes_from_the_api_probability(answers):
    for name, answer in answers.items():
        facts = build_facts(LOANS[name], answer, POLICY, "fr")
        assert facts["recommendation"] == EXPECTED_DECISION[name] == decide(answer["probability_of_default"], POLICY), name
        assert facts["recommendation_label"] == POLICY.language("fr").labels[facts["recommendation"]]


def test_golden_loan_numbers_in_both_languages(answers):
    fr = build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "fr")
    en = build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "en")
    assert fr["numbers"] == en["numbers"], "the plain numbers do not depend on the language"
    assert fr["numbers"]["score"] == "553.3" and fr["numbers"]["probability_of_default"] == "9.17"
    assert fr["numbers"]["dti"] == "44" and fr["numbers"]["interest_rate"] == "4.55" and fr["numbers"]["rate_spread"] == "0.55"
    assert fr["numbers"]["term_years"] == "30" and fr["numbers"]["approve_below"] == "2" and fr["numbers"]["decline_above"] == "5"
    assert fr["display"]["probability_of_default"] == "9,17 %" and en["display"]["probability_of_default"] == "9.17%"
    assert fr["display"]["interest_rate"] == "4,55 %" and en["display"]["score"] == "553.3" and fr["display"]["score"] == "553,3"


def test_unknown_inputs_are_left_out_not_invented(answers):
    facts = build_facts(LOANS["unknown_fields"], answers["unknown_fields"], POLICY, "fr")
    assert not {"credit_score", "dti", "mi_pct"} & set(facts["numbers"])
    assert facts["unknown"] == "inconnu"


def test_reasons_use_the_french_sentences_and_number_each_loss(answers):
    facts = build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "fr")
    assert [r["feature"] for r in facts["reasons"]] == ["credit_score", "cltv", "dti", "several_borrowers"]
    assert all(r["phrase"] == POLICY.language("fr").reason_phrases[r["feature"]] for r in facts["reasons"])
    assert [r["points_lost"] for r in facts["reasons"]] == ["points_lost_1", "points_lost_2", "points_lost_3", "points_lost_4"]
    en = build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "en")
    assert en["reasons"][0]["phrase"] == answers["golden_decline"]["reasons"][0]["phrase"], "English keeps the API's own sentence"


def test_outside_training_range_sentence(answers):
    outside = build_facts(LOANS["outside_range"], answers["outside_range"], POLICY, "fr")
    assert outside["outside_training_range"] == ["credit_score"] and "credit_score" in outside["outside_range_text"]
    assert build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "fr")["outside_range_text"] == ""


def test_the_fact_sheet_never_carries_the_model_id_or_the_requests_raw_text(answers):
    facts = build_facts(LOANS["golden_decline"], answers["golden_decline"], POLICY, "fr")
    text = str(facts)
    assert answers["golden_decline"]["model_id"] not in text and "purpose" not in facts["numbers"]
