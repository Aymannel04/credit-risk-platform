"""The API client, the 15 evaluation loans, the evaluation runner, the command line, and the read-only promise. No network, no key, no model."""
import io
import json
import re
import urllib.error

import pytest

from agent import evaluate, run
from agent.api_client import ApiError, LiveScorer, OfflineScorer, check_answer
from agent.doubles import SEEDED_KINDS, good_reply
from agent.policy import ROOT, load_policy
from agent.writer import ScriptedWriter, WriterError

POLICY = load_policy()
CASES = evaluate.load_cases()


@pytest.fixture(scope="module")
def scorer():
    with OfflineScorer() as s:
        yield s


# ---------- the 15 evaluation loans ----------

def test_there_are_fifteen_distinct_loans_and_the_api_accepts_them_all(scorer):
    assert len(CASES) == 15 and len({c["id"] for c in CASES}) == 15
    for case in CASES:
        assert set(case["loan"]) == {"credit_score", "dti", "ltv", "cltv", "interest_rate", "reference_rate", "number_of_borrowers",
                                     "mi_pct", "term_months", "purpose"}, case["id"]
        scorer.explain(case["loan"])


def test_the_loans_cover_all_three_decisions_and_sit_next_to_the_lines(scorer):
    probability = {c["id"]: scorer.explain(c["loan"])["probability_of_default"] for c in CASES}
    decisions = {i: ("approve" if p < POLICY.approve_below else "decline" if p > POLICY.decline_above else "refer") for i, p in probability.items()}
    assert set(decisions.values()) == {"approve", "refer", "decline"}
    assert POLICY.approve_below < probability["05_just_above_first_line"] < POLICY.approve_below + 0.002
    assert POLICY.decline_above - 0.002 < probability["07_just_below_second_line"] < POLICY.decline_above
    assert POLICY.decline_above < probability["08_just_above_second_line"] < POLICY.decline_above + 0.002
    outside = scorer.explain(next(c for c in CASES if c["id"] == "12_outside_training_range")["loan"])
    assert outside["outside_training_range"], "one loan must be outside the training range"


def test_duplicate_case_ids_are_refused(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([{"id": "a", "loan": {}}, {"id": "a", "loan": {}}]), encoding="utf-8")
    with pytest.raises(ValueError):
        evaluate.load_cases(path)


# ---------- the evaluation runner ----------

def test_a_careful_pretend_writer_gets_every_loan_accepted_on_the_first_try(scorer):
    result = evaluate.evaluate_cases(CASES, scorer, lambda f: ScriptedWriter([good_reply(f)]), POLICY, "fr", "pretend")
    assert (result["cases"], result["accepted_first_try"], result["backup_memo"], result["writer_errors"]) == (15, 15, 0, 0)
    assert result["mean_tries"] == 1.0 and result["problem_codes"] == {}


def test_a_careful_pretend_writer_also_works_in_english(scorer):
    result = evaluate.evaluate_cases(CASES, scorer, lambda f: ScriptedWriter([good_reply(f)]), POLICY, "en", "pretend")
    assert result["accepted_first_try"] == 15


@pytest.mark.parametrize("language", ["fr", "en"])
def test_every_deliberate_mistake_is_rejected_on_every_loan(scorer, language):
    result = evaluate.evaluate_seeded(CASES, scorer, POLICY, language)
    assert result["runs"] == 15 * len(SEEDED_KINDS) == 150
    assert result["rejected"] == 150 and result["reached_the_reader"] == 0 and result["rejection_rate"] == 1.0
    assert all(r["tries"] == POLICY.max_rewrites + 1 for r in result["rows"])


def test_a_forgetful_writer_is_measured_not_hidden(scorer):
    """A writer that gets half of the loans wrong: the numbers must show it (rewrites, backups and the complaint codes)."""
    state = {"n": 0}

    def writer_for(facts):
        state["n"] += 1
        from agent.doubles import seeded_reply
        if state["n"] % 2:
            return ScriptedWriter([seeded_reply(facts, "promise"), good_reply(facts)])
        return ScriptedWriter([seeded_reply(facts, "wrong_number")] * 3)

    result = evaluate.evaluate_cases(CASES, scorer, writer_for, POLICY, "fr", "forgetful")
    assert result["accepted_after_rewrite"] == 8 and result["backup_memo"] == 7 and result["accepted_first_try"] == 0
    assert {"FORBIDDEN_PHRASE", "NUMBER_NOT_IN_FACTS"} <= set(result["problem_codes"])
    assert result["mean_tries"] == round((8 * 2 + 7 * 3) / 15, 2)


def test_results_are_saved_readable_and_free_of_secrets(scorer, tmp_path):
    seeded = evaluate.evaluate_seeded(CASES, scorer, POLICY, "fr")
    pretend = evaluate.evaluate_cases(CASES, scorer, lambda f: ScriptedWriter([good_reply(f)]), POLICY, "fr", "pretend")
    for label, result in (("seeded", seeded), ("pretend", pretend)):
        json_path, md_path = evaluate.save(result, label, POLICY, tmp_path)
        for path in (json_path, md_path):
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"(?<!\d)\d{12}(?!\d)", text) and "http" not in text and "NVIDIA_API_KEY" not in text and "arn:" not in text
        assert json.loads(json_path.read_text(encoding="utf-8"))["generated_utc"]
    assert "150 of 150" in (tmp_path / "agent_eval_seeded.md").read_text(encoding="utf-8")
    assert "| Accepted on the first try | 15 |" in (tmp_path / "agent_eval_pretend.md").read_text(encoding="utf-8")


def test_committed_results_files_match_what_the_code_produces(scorer):
    committed = ROOT / "results" / "agent_eval_seeded.json"
    if committed.exists():
        data = json.loads(committed.read_text(encoding="utf-8"))
        assert data["runs"] == 150 and data["rejected"] == 150 and data["reached_the_reader"] == 0


# ---------- the scoring API client ----------

def test_offline_scorer_refuses_a_bad_loan_without_echoing_it(scorer):
    with pytest.raises(ApiError) as info:
        scorer.explain({"credit_score": 700, "secret_extra_field": "do-not-echo-me"})
    assert "do-not-echo-me" not in str(info.value)


@pytest.mark.parametrize("answer", [None, {}, {"score": 1}, {"score": 1, "probability_of_default": 2, "reasons": [], "outside_training_range": []},
                                    {"score": 1, "probability_of_default": "0.1", "reasons": [], "outside_training_range": []}])
def test_a_strange_api_answer_is_refused(answer):
    with pytest.raises(ApiError):
        check_answer(answer)


class FakeResponse:
    def __init__(self, payload):
        self._bytes = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._bytes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


GOOD = {"score": 553.3, "probability_of_default": 0.0917, "reasons": [], "outside_training_range": []}


def live(outcomes, signs=None, **kw):
    outcomes = list(outcomes)
    seen = []

    def urlopen(request, timeout):
        seen.append(request)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(outcome)

    def sign(method, url, body, headers):
        if signs is not None:
            signs.append((method, url))
        return {**headers, "Authorization": "AWS4-HMAC-SHA256 stand-in"}

    return LiveScorer("https://abc123.lambda-url.example.on.aws", urlopen=urlopen, sign=sign, sleep=lambda s: None, **kw), seen


def test_the_live_scorer_signs_every_request_and_sends_only_the_loan():
    signs = []
    scorer, seen = live([urllib.error.URLError("blip"), GOOD], signs=signs)
    assert scorer.explain({"credit_score": 700})["score"] == 553.3
    assert len(signs) == 2, "the request is signed again on every try"
    assert all(s == ("POST", "https://abc123.lambda-url.example.on.aws/explain") for s in signs)
    assert seen[-1].get_header("Authorization") == "AWS4-HMAC-SHA256 stand-in" and json.loads(seen[-1].data) == {"credit_score": 700}


def test_the_live_scorer_reports_errors_without_leaking_the_address():
    for outcome, words in ((urllib.error.HTTPError("u", 403, "x", {}, io.BytesIO(b"")), "aws sso login"), (urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b"")), "500"),
                           (b"not json", "valid JSON"), ({"nope": 1}, "unexpected")):
        scorer, _ = live([outcome])
        with pytest.raises(ApiError, match=words) as info:
            scorer.explain({})
        assert "abc123" not in str(info.value)
    scorer, seen = live([urllib.error.URLError("down")] * 3)
    with pytest.raises(ApiError, match="network"):
        scorer.explain({})
    assert len(seen) == 3


def test_the_live_scorer_needs_https():
    with pytest.raises(ApiError):
        LiveScorer("http://abc.example.test", sign=lambda *a: {})


# ---------- the command line ----------

LOAN = {"credit_score": 720, "dti": 36.0, "ltv": 85.0, "cltv": 85.0, "interest_rate": 4.2, "reference_rate": 4.0, "number_of_borrowers": 1,
        "mi_pct": 25.0, "term_months": 360, "purpose": "P"}


@pytest.fixture
def loan_file(tmp_path):
    path = tmp_path / "loan.json"
    path.write_text(json.dumps(LOAN), encoding="utf-8")
    return path


def test_the_command_makes_the_memo_written_by_code_without_a_model(loan_file, tmp_path, capsys):
    out = tmp_path / "memo.md"
    assert run.main(["--loan", str(loan_file), "--lang", "fr", "--out", str(out)]) == 0
    printed = capsys.readouterr().out
    assert "À EXAMINER" in printed and "status: memo written by code" in printed
    assert out.read_text(encoding="utf-8").startswith("## Résumé")


def test_the_command_with_a_model_that_cannot_be_reached_ends_on_the_backup_memo(loan_file, monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert run.main(["--loan", str(loan_file), "--writer", "nvidia", "--model", "some-model"]) == 0
    printed = capsys.readouterr().out
    assert "BACKUP memo written by code" in printed and "NVIDIA_API_KEY is not set" in printed and "À EXAMINER" in printed


def test_the_command_with_a_good_pretend_model_is_accepted(loan_file, monkeypatch, capsys):
    monkeypatch.setattr(run, "make_writer", lambda *a, **k: _Replaying())
    assert run.main(["--loan", str(loan_file), "--writer", "nvidia", "--model", "m"]) == 0
    assert "accepted by the inspector on try 1" in capsys.readouterr().out


class _Replaying:
    name = "replaying"

    def write(self, messages):
        from agent.doubles import good_reply
        from agent.facts import build_facts
        # rebuild the facts the same way the command does, to answer like a careful model
        with OfflineScorer() as s:
            return good_reply(build_facts(LOAN, s.explain(LOAN), POLICY, "fr"))


@pytest.mark.parametrize("args", [["--writer", "nvidia"], ["--writer", "custom", "--model", "m"], ["--writer", "unknown", "--model", "m"]])
def test_the_command_refuses_a_missing_model_or_an_unknown_writer(loan_file, args, capsys):
    assert run.main(["--loan", str(loan_file), *args]) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_the_command_reports_a_missing_or_broken_loan_file(tmp_path, capsys):
    assert run.main(["--loan", str(tmp_path / "missing.json")]) == 1
    broken = tmp_path / "broken.json"
    broken.write_text("{nope", encoding="utf-8")
    assert run.main(["--loan", str(broken)]) == 1
    refused = tmp_path / "extra.json"
    refused.write_text(json.dumps({**LOAN, "extra": 1}), encoding="utf-8")
    assert run.main(["--loan", str(refused)]) == 1


def test_presets_come_from_the_policy_file_and_hold_no_key():
    writer = run.make_writer("nvidia", POLICY, "some-model")
    assert writer.base_url == "https://integrate.api.nvidia.com/v1" and writer.api_key_env == "NVIDIA_API_KEY"
    assert run.make_writer("backup", POLICY, None) is None
    with pytest.raises(WriterError):
        run.make_writer("custom", POLICY, "m")
    assert "nvapi" not in (ROOT / "config" / "memo_policy.yaml").read_text(encoding="utf-8")


# ---------- the read-only promise, checked in the code itself ----------

def test_the_agent_package_can_only_write_the_results_and_the_requested_memo_file():
    sources = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "agent").glob("*.py")}
    writers = {name for name, text in sources.items() if re.search(r"\.write_text\(|open\([^)]*[\"'][wax]", text)}
    assert writers == {"evaluate.py", "run.py"}, writers
    for name, text in sources.items():
        imported = set(re.findall(r"(?m)^\s*(?:import|from)\s+([A-Za-z_][\w]*)", text))
        assert not imported & {"subprocess", "shutil", "boto3", "requests", "pickle", "ftplib", "smtplib", "socket"}, (name, imported)
        for forbidden in ("os.system", "eval(", "exec(", "os.remove", "unlink(", "rmtree"):
            assert forbidden not in text, (name, forbidden)
    assert "import botocore" not in sources["api_client.py"].split("def _make_signer")[0], "AWS libraries are only imported when the live API is used"


def test_the_only_http_verb_to_the_scoring_api_is_post_to_explain():
    text = (ROOT / "agent" / "api_client.py").read_text(encoding="utf-8")
    assert re.findall(r'"/explain"|/explain"|/explain', text) and not re.search(r"method=\"(PUT|DELETE|PATCH)\"", text)
    assert "/score" not in text and "model-info" not in text
