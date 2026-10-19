"""The writer plug-in, the instructions, and the loop (try, inspect, rewrite, backup). No network, no key, no language model."""
import io
import json
import urllib.error

import pytest

from agent.doubles import SEEDED_KINDS, good_reply, seeded_reply
from agent.facts import build_facts
from agent.memo import BACKUP_FLAG, MemoError, assemble, generate_memo
from agent.policy import load_policy
from agent.prompt import build_messages, build_system, writer_view
from agent.template import render_template_memo
from agent.validator import validate_memo
from agent.writer import OpenAICompatibleWriter, ScriptedWriter, WriterError
from tests.agent_cases import LOANS, explain_all

POLICY = load_policy()
KEY_VALUE = "test-key-" + "0123456789abcdef"  # a made-up value, only ever put in the environment of the test


@pytest.fixture(scope="module")
def sheets():
    answers = explain_all()
    return {(name, lang): build_facts(LOANS[name], answers[name], POLICY, lang) for name in LOANS for lang in ("fr", "en")}


# ---------- the pretend writers are sound ----------

def test_the_good_pretend_writer_passes_the_inspector_on_every_loan(sheets):
    for key, facts in sheets.items():
        memo = assemble(good_reply(facts), facts)
        assert validate_memo(memo, facts, POLICY) == [], key


def test_every_seeded_mistake_is_really_a_mistake_for_the_inspector(sheets):
    for key, facts in sheets.items():
        for kind in SEEDED_KINDS:
            if kind == "other_language" and key[1] == "en":
                pass
            memo = assemble(seeded_reply(facts, kind), facts)
            assert validate_memo(memo, facts, POLICY), (key, kind, "the inspector accepted a damaged memo")


def test_unknown_seeded_kind_is_refused(sheets):
    with pytest.raises(ValueError):
        seeded_reply(sheets[("golden_decline", "fr")], "nonsense")


# ---------- the scripted writer ----------

def test_scripted_writer_returns_replies_in_order_and_records_the_calls():
    w = ScriptedWriter(["a", lambda messages: f"{len(messages)} messages", "c"])
    assert [w.write([{"role": "user", "content": "x"}]) for _ in range(3)] == ["a", "1 messages", "c"]
    assert len(w.calls) == 3
    with pytest.raises(WriterError):
        w.write([])


# ---------- the real writer, with a fake network ----------

class FakeResponse:
    def __init__(self, payload):
        self._bytes = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code):
    return urllib.error.HTTPError("https://example.test/v1/chat/completions", code, "x", {}, io.BytesIO(b"{}"))


class FakeNetwork:
    """Plays a list of outcomes: a payload, or an exception to raise."""

    def __init__(self, outcomes):
        self.outcomes, self.requests, self.sleeps = list(outcomes), [], []

    def urlopen(self, request, timeout):
        self.requests.append((request, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    def sleep(self, seconds):
        self.sleeps.append(seconds)


def ok(text="hello"):
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def make_writer(net, **kw):
    return OpenAICompatibleWriter("https://example.test/v1/", "some-model", "FAKE_LLM_KEY", urlopen=net.urlopen, sleep=net.sleep, **kw)


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY_VALUE)


def test_a_successful_call_sends_the_right_request(with_key):
    net = FakeNetwork([ok("the memo")])
    writer = make_writer(net, temperature=0.1)
    assert writer.write([{"role": "user", "content": "hi"}]) == "the memo"
    (request, timeout), = net.requests
    assert request.full_url == "https://example.test/v1/chat/completions" and request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {KEY_VALUE}" and timeout == 60.0
    body = json.loads(request.data)
    assert body["model"] == "some-model" and body["messages"] == [{"role": "user", "content": "hi"}] and body["temperature"] == 0.1
    assert writer.name == "some-model"


def test_the_key_is_read_from_the_environment_only_when_calling(monkeypatch):
    net = FakeNetwork([ok()])
    writer = make_writer(net)
    monkeypatch.delenv("FAKE_LLM_KEY", raising=False)
    with pytest.raises(WriterError, match="FAKE_LLM_KEY"):
        writer.write([])
    assert net.requests == [], "no request may leave without a key"


def test_busy_service_is_retried_with_waiting_then_succeeds(with_key):
    net = FakeNetwork([http_error(429), http_error(503), ok("finally")])
    assert make_writer(net).write([]) == "finally"
    assert len(net.requests) == 3 and net.sleeps == [2, 4]


def test_a_service_that_stays_busy_fails_cleanly(with_key):
    net = FakeNetwork([http_error(429)] * 3)
    with pytest.raises(WriterError, match="HTTP 429"):
        make_writer(net).write([])
    assert len(net.requests) == 3


@pytest.mark.parametrize("code, words", [(401, "refused"), (403, "not allowed"), (404, "not found")])
def test_authentication_and_address_errors_are_not_retried(with_key, code, words):
    net = FakeNetwork([http_error(code), ok()])
    with pytest.raises(WriterError, match=words):
        make_writer(net).write([])
    assert len(net.requests) == 1


def test_network_trouble_is_retried_then_reported(with_key):
    net = FakeNetwork([urllib.error.URLError("down"), TimeoutError(), ConnectionError()])
    with pytest.raises(WriterError, match="network"):
        make_writer(net).write([])
    assert len(net.requests) == 3


@pytest.mark.parametrize("payload", [b"not json", b"\xff\xfe", {"choices": []}, {"choices": [{"message": {}}]}, {"nope": 1},
                                     {"choices": [{"message": {"content": "   "}}]}, {"choices": [{"message": {"content": 5}}]}])
def test_malformed_answers_are_reported_as_writer_errors(with_key, payload):
    net = FakeNetwork([payload])
    with pytest.raises(WriterError):
        make_writer(net).write([])


def test_the_key_never_appears_in_any_error_message(with_key):
    for outcome in (http_error(401), http_error(500), urllib.error.URLError("x"), b"nonsense", {"choices": []}):
        net = FakeNetwork([outcome] * 3)
        with pytest.raises(WriterError) as info:
            make_writer(net).write([])
        assert KEY_VALUE not in str(info.value) and KEY_VALUE not in repr(info.value)


@pytest.mark.parametrize("url, allowed", [("https://integrate.example.test/v1", True), ("http://localhost:11434/v1", True),
                                          ("http://127.0.0.1:11434/v1", True), ("http://example.test/v1", False), ("ftp://x/v1", False)])
def test_plain_http_is_only_allowed_on_this_computer(url, allowed):
    if allowed:
        OpenAICompatibleWriter(url, "m", "K")
    else:
        with pytest.raises(WriterError):
            OpenAICompatibleWriter(url, "m", "K")


# ---------- the instructions ----------

def test_the_instructions_carry_the_rules_and_only_what_the_writer_may_use(sheets):
    facts = sheets[("middle_refer", "fr")]
    system = build_system(facts, POLICY)
    for needle in (facts["recommendation_label"], "Résumé", "Analyse du risque", "Raisons principales", "Recommandation", "Limites",
                   facts["disclaimer"], facts["caution"], facts["display"]["probability_of_default"], "garanti", "French"):
        assert needle in system, needle
    assert "Do NOT write a section called \"Données du dossier\"" in system
    view = json.dumps(writer_view(facts), ensure_ascii=False)
    assert "0.0334" not in view and "0,0334" not in view, "the raw probability must not be given to the writer"
    assert facts["display"]["probability_of_default"] in view and "approve" not in view and "decline" not in view
    messages = build_messages(facts, POLICY)
    assert [m["role"] for m in messages] == ["system", "user"]


def test_the_instructions_name_the_outside_range_sentence_only_when_there_is_one(sheets):
    assert sheets[("outside_range", "fr")]["outside_range_text"] in build_system(sheets[("outside_range", "fr")], POLICY)
    assert "plage d'entraînement" not in build_system(sheets[("golden_decline", "fr")], POLICY)


def test_after_a_rejection_the_writer_gets_its_own_text_and_the_complaints(sheets):
    facts = sheets[("golden_decline", "en")]
    bad = seeded_reply(facts, "wrong_number")
    problems = validate_memo(assemble(bad, facts), facts, POLICY)
    messages = build_messages(facts, POLICY, bad, problems)
    assert [m["role"] for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[2]["content"] == bad and "NUMBER_NOT_IN_FACTS" in messages[3]["content"] and "77.7" in messages[3]["content"]


# ---------- assembling ----------

def test_the_loan_data_section_is_always_the_one_written_by_code(sheets):
    facts = sheets[("golden_decline", "en")]
    reply = good_reply(facts)
    assert facts["data_section"] in assemble(reply, facts)
    forged = reply.replace("## Risk analysis", "## Loan data\n- Credit score: 85\n- Loan to value: 700%\n\n## Risk analysis")
    memo = assemble(forged, facts)
    assert facts["data_section"] in memo and "700%" not in memo and memo.count("## Loan data") == 1
    assert validate_memo(memo, facts, POLICY) == []


def test_assembling_keeps_what_the_inspector_must_see(sheets):
    facts = sheets[("golden_decline", "fr")]
    assert assemble("Voici :\n" + good_reply(facts), facts).startswith("Voici :")
    assert "TEXT_OUTSIDE_SECTIONS" in {p.code for p in validate_memo(assemble("Voici :\n" + good_reply(facts), facts), facts, POLICY)}
    assert assemble("", facts) == ""
    assert "## Données du dossier" in assemble("just text, no headings", facts)


def test_a_code_fence_around_the_whole_answer_is_ignored(sheets):
    facts = sheets[("prime_approve", "fr")]
    for fenced in ("```markdown\n" + good_reply(facts) + "```", "```\n" + good_reply(facts) + "\n```\n"):
        assert validate_memo(assemble(fenced, facts), facts, POLICY) == []


# ---------- the loop ----------

def test_a_good_first_try_is_accepted(sheets):
    facts = sheets[("middle_refer", "fr")]
    writer = ScriptedWriter([good_reply(facts)], name="pretend")
    result = generate_memo(facts, writer, POLICY)
    assert result.status == "accepted" and result.first_try and result.flag == "" and result.writer == "pretend"
    assert validate_memo(result.memo, facts, POLICY) == [] and len(writer.calls) == 1


def test_a_rejected_memo_is_rewritten_with_the_complaints(sheets):
    facts = sheets[("golden_decline", "en")]
    writer = ScriptedWriter([seeded_reply(facts, "promise"), good_reply(facts)])
    result = generate_memo(facts, writer, POLICY)
    assert result.status == "accepted" and not result.first_try and len(result.attempts) == 2
    assert result.attempts[0].problems and result.attempts[1].problems == []
    second_call = writer.calls[1]
    assert second_call[-2]["role"] == "assistant" and "FORBIDDEN_PHRASE" in second_call[-1]["content"]


def test_after_three_failures_the_backup_memo_written_by_code_is_used(sheets):
    facts = sheets[("golden_decline", "fr")]
    writer = ScriptedWriter([seeded_reply(facts, "wrong_number")] * 3)
    result = generate_memo(facts, writer, POLICY)
    assert result.status == "backup" and result.flag == BACKUP_FLAG and len(result.attempts) == POLICY.max_rewrites + 1
    assert result.memo == render_template_memo(facts) and validate_memo(result.memo, facts, POLICY) == []
    assert len(writer.calls) == 3, "the writer is never asked a fourth time"


@pytest.mark.parametrize("failure", [WriterError("could not reach the service"), RuntimeError("boom"), KeyError("x")])
def test_a_failing_writer_never_breaks_the_agent(sheets, failure):
    facts = sheets[("prime_approve", "en")]

    class Broken:
        name = "broken"

        def write(self, messages):
            raise failure

    result = generate_memo(facts, Broken(), POLICY)
    assert result.status == "backup" and result.flag == BACKUP_FLAG and result.attempts[0].error
    assert validate_memo(result.memo, facts, POLICY) == []


def test_a_writer_that_fails_after_a_rejection_still_ends_with_the_backup(sheets):
    facts = sheets[("prime_approve", "en")]
    result = generate_memo(facts, ScriptedWriter([seeded_reply(facts, "wrong_number")]), POLICY)  # the second call raises: no reply left
    assert result.status == "backup" and len(result.attempts) == 2 and result.attempts[1].error


def test_a_backup_that_fails_the_inspector_is_reported_as_a_bug_not_published(sheets, monkeypatch):
    facts = sheets[("prime_approve", "en")]
    monkeypatch.setattr("agent.memo.render_template_memo", lambda f: "garbage")
    with pytest.raises(MemoError):
        generate_memo(facts, ScriptedWriter([]), POLICY)


def test_the_number_of_tries_follows_the_policy(sheets):
    facts = sheets[("prime_approve", "en")]
    from dataclasses import replace

    for rewrites in (0, 1, 4):
        policy = replace(POLICY, max_rewrites=rewrites)
        writer = ScriptedWriter([seeded_reply(facts, "promise")] * 10)
        result = generate_memo(facts, writer, policy)
        assert len(writer.calls) == rewrites + 1 and result.status == "backup"


# ---------- the seeded-error test at the level of the whole loop ----------

def test_no_seeded_mistake_ever_reaches_the_reader(sheets):
    """10 kinds of mistake x 6 loans x 2 languages, forced on all three tries: the loop must end on the backup memo every time, and
    nothing it returns may contain the mistake."""
    runs = rejected = 0
    for key, facts in sheets.items():
        for kind in SEEDED_KINDS:
            writer = ScriptedWriter([seeded_reply(facts, kind)] * 3, name=f"seeded-{kind}")
            result = generate_memo(facts, writer, POLICY)
            runs += 1
            rejected += result.status == "backup"
            assert result.status == "backup", (key, kind)
            assert validate_memo(result.memo, facts, POLICY) == [], (key, kind)
            assert "777" not in result.memo and "77,7" not in result.memo and "77.7" not in result.memo
    assert runs == len(SEEDED_KINDS) * 12 == rejected


def test_the_thinking_of_a_reasoning_model_is_ignored_not_inspected(sheets):
    facts = sheets[("prime_approve", "fr")]
    thinking = "<think>Let me count: the risk is maybe 12 percent, deux lignes, I should promise... garanti</think>\n"
    assert validate_memo(assemble(thinking + good_reply(facts), facts), facts, POLICY) == []
    fenced = "<THINK>\nmore thinking 999\n</THINK>\n```markdown\n" + good_reply(facts) + "```"
    assert validate_memo(assemble(fenced, facts), facts, POLICY) == []
    # thinking is dropped, but a reply that is ONLY thinking is still an empty memo that gets rejected
    assert validate_memo(assemble("<think>nothing else</think>", facts), facts, POLICY)


def test_the_real_writer_is_built_with_generous_room_and_time_by_default():
    from agent import run

    writer = run.make_writer("nvidia", POLICY, "some-model")
    assert writer.max_tokens == 2500 and writer.timeout == 150.0
    writer = run.make_writer("custom", POLICY, "m", "https://x.test/v1", "K", max_tokens=100, timeout=5)
    assert writer.max_tokens == 100 and writer.timeout == 5


def test_an_empty_answer_says_why(with_key):
    thinking_only = {"choices": [{"finish_reason": "length", "message": {"content": None, "reasoning_content": "I am thinking about the memo..."}}]}
    net = FakeNetwork([thinking_only])
    with pytest.raises(WriterError) as info:
        make_writer(net).write([])
    assert "finish_reason: length" in str(info.value) and "only produced thinking" in str(info.value) and "--max-tokens" in str(info.value)
    blank = {"choices": [{"finish_reason": "stop", "message": {"content": "  "}}]}
    with pytest.raises(WriterError) as info:
        make_writer(FakeNetwork([blank])).write([])
    assert "empty text (finish_reason: stop)" in str(info.value) and "thinking" not in str(info.value)


def test_the_attempts_view_shows_what_the_model_wrote_and_what_the_inspector_said(sheets):
    from agent.run import show_attempts

    facts = sheets[("golden_decline", "en")]
    result = generate_memo(facts, ScriptedWriter([seeded_reply(facts, "invented_number"), good_reply(facts)]), POLICY)
    view = show_attempts(result)
    assert "=== try 1 (written by the model)" in view and "=== try 2" in view and "About 777 comparable files." in view
    assert "inspector: [NUMBER_NOT_IN_FACTS]" in view
    long = generate_memo(facts, ScriptedWriter(["x" * 5000] * 3), POLICY)
    assert "more characters]" in show_attempts(long, limit=100)
    broken = generate_memo(facts, ScriptedWriter([]), POLICY)
    assert "the writer failed: the scripted writer has no reply left" in show_attempts(broken)


# ---------- the writer is told the REAL length budget, and the complaints say exactly what to fix ----------

def _skeleton(facts, filler_words):
    """A memo made only of what the budget accounts for (titles, the system's section, the sentences to copy, the decision word, the risk)
    plus `filler_words` words of the writer's own."""
    h = facts["headings"]
    limits = " ".join([facts["disclaimer"], facts["caution"], *([facts["outside_range_text"]] if facts["outside_range_text"] else [])])
    own = "mot " * filler_words
    return "\n".join([f"## {h[0]}", facts["display"]["probability_of_default"] + " " + own, f"## {h[1]}", facts["data_section"], f"## {h[2]}", "x",
                      f"## {h[3]}", "- x", f"## {h[4]}", facts["recommendation_label"], f"## {h[5]}", limits]) + "\n"


def test_the_word_budget_in_the_instructions_agrees_with_the_inspector(sheets):
    from agent.prompt import word_budget
    from agent.validator import count_words

    for key, facts in sheets.items():
        budget = word_budget(facts, POLICY)
        system = build_system(facts, POLICY)
        assert 20 <= budget < POLICY.max_words and f"at most {budget} words of your own" in system and f"under {POLICY.max_words} words" in system, key
        full = _skeleton(facts, budget)
        assert count_words(full) <= POLICY.max_words, (key, count_words(full))   # the whole budget used: still inside the limit
        assert "LENGTH" not in {p.code for p in validate_memo(full, facts, POLICY)}, key
        beyond = _skeleton(facts, budget + 15 + 2)                                # beyond the budget AND the safety margin: over the limit
        assert count_words(beyond) > POLICY.max_words and "LENGTH" in {p.code for p in validate_memo(beyond, facts, POLICY)}, key


def test_the_length_complaint_says_how_much_to_cut(sheets):
    facts = sheets[("golden_decline", "fr")]
    from agent.validator import count_words

    memo = render_template_memo(facts)
    long = memo + "\n" + "mot " * (POLICY.max_words - count_words(memo) + 4)
    (problem,) = [p for p in validate_memo(long, facts, POLICY) if p.code == "LENGTH"]
    assert f"limit is {POLICY.max_words}" in problem.message and "remove at least 24 words" in problem.message
    short = "".join(f"## {h}\nx\n" for h in facts["headings"])
    assert any("needs at least" in p.message for p in validate_memo(short, facts, POLICY) if p.code == "LENGTH")


def test_the_headings_complaint_lists_what_was_written_and_what_is_missing(sheets):
    facts = sheets[("golden_decline", "fr")]
    memo = assemble(good_reply(facts).replace("## Limites", "## Notes"), facts)
    (problem,) = [p for p in validate_memo(memo, facts, POLICY) if p.code == "SECTIONS"]
    assert "You wrote: Résumé | Analyse du risque | Raisons principales | Recommandation | Notes" in problem.message
    assert "Missing: Limites" in problem.message and "Not allowed: Notes" in problem.message
    assert "Données du dossier" not in problem.message.split("You wrote:")[1], "the system's own section is never blamed on the writer"


# ---------- the lessons of the first held-out loans: layout repair, sign hints, rewrites that differ, safety versus form ----------

def test_a_memo_squeezed_onto_one_line_is_put_back_in_shape_without_changing_a_word(sheets):
    facts = sheets[("golden_decline", "fr")]
    good = good_reply(facts)
    one_line = " ".join(good.split())          # the whole memo as one paragraph, as the small model did after a complaint
    assert "\n" not in one_line and validate_memo(assemble(one_line, facts), facts, POLICY) == []
    same_line = good.replace("## Résumé\n", "## Résumé ").replace("## Raisons principales\n", "## Raisons principales ")
    assert validate_memo(assemble(same_line, facts), facts, POLICY) == []
    from agent.validator import count_words

    assert count_words(assemble(one_line, facts)) == count_words(assemble(good, facts)), "only line breaks changed"


def test_layout_repair_leaves_good_memos_alone_and_never_hides_extra_text(sheets):
    facts = sheets[("golden_decline", "en")]
    good = good_reply(facts)
    assert assemble(good, facts) == assemble(assemble(good, facts), facts), "assembling twice gives the same memo"
    with_preamble = "Sure! Here is the memo: " + " ".join(good.split())
    problems = {p.code for p in validate_memo(assemble(with_preamble, facts), facts, POLICY)}
    assert "TEXT_OUTSIDE_SECTIONS" in problems, "text before the first title is still refused"
    unknown_title = good.replace("## Limits", "## Notes")
    assert "SECTIONS" in {p.code for p in validate_memo(assemble(unknown_title, facts), facts, POLICY)}, "a title that is not one of ours is refused"
    longer_title = good.replace("## Limits", "## Limits and more notes")
    assert validate_memo(assemble(longer_title, facts), facts, POLICY) == [], "a known title followed by words becomes the title plus a sentence"


def test_the_sign_complaint_says_exactly_what_to_write(sheets):
    facts = sheets[("golden_decline", "fr")]
    bad = good_reply(facts).replace("(35,6 points perdus)", "(-35,6 points perdus)") if "(35,6 points perdus)" in good_reply(facts) else None
    first_loss = facts["display"]["points_lost_1"]
    bad = good_reply(facts).replace(f"{first_loss} points perdus", f"-{first_loss} points perdus")
    assert bad != good_reply(facts)
    (problem,) = [p for p in validate_memo(assemble(bad, facts), facts, POLICY) if p.code == "NUMBER_NOT_IN_FACTS"]
    assert f"-{first_loss}" in problem.message and f"write {first_loss}, not -{first_loss}" in problem.message


def test_every_complaint_code_is_classified_as_safety_or_form():
    import re as _re
    from pathlib import Path

    from agent.validator import FORM_CODES, SAFETY_CODES

    source = (Path(__file__).resolve().parents[1] / "agent" / "validator.py").read_text(encoding="utf-8")
    emitted = set(_re.findall(r'Problem\("([A-Z_]+)"', source))
    assert emitted == SAFETY_CODES | FORM_CODES and not SAFETY_CODES & FORM_CODES, emitted ^ (SAFETY_CODES | FORM_CODES)


def test_a_rewrite_asks_for_a_different_temperature_but_the_first_try_does_not(sheets):
    facts = sheets[("prime_approve", "en")]
    writer = ScriptedWriter([seeded_reply(facts, "promise"), seeded_reply(facts, "promise"), good_reply(facts)])
    generate_memo(facts, writer, POLICY)
    assert writer.temperatures == [None, POLICY.retry_temperature, POLICY.retry_temperature] and POLICY.retry_temperature == 0.4


def test_the_real_writer_uses_the_temperature_it_is_given(with_key):
    net = FakeNetwork([ok("one"), ok("two")])
    writer = make_writer(net, temperature=0.0)
    writer.write([])
    writer.write([], temperature=0.4)
    assert [json.loads(r.data)["temperature"] for r, _ in net.requests] == [0.0, 0.4]


def test_a_writer_that_cannot_take_a_temperature_still_works(sheets):
    facts = sheets[("prime_approve", "en")]

    class Plain:
        name = "plain"

        def __init__(self, replies):
            self.replies = list(replies)

        def write(self, messages):
            return self.replies.pop(0)

    result = generate_memo(facts, Plain([seeded_reply(facts, "promise"), good_reply(facts)]), POLICY)
    assert result.status == "accepted" and len(result.attempts) == 2
