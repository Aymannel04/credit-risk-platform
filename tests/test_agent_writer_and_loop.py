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
