"""The model-listing command, with a fake network."""
import io
import json
import urllib.error

import pytest

from agent import models
from agent.writer import WriterError

KEY = "test-key-" + "fedcba9876543210"


class Response:
    def __init__(self, payload):
        self._b = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False


def opener(outcome, seen=None):
    def urlopen(request, timeout):
        if seen is not None:
            seen.append(request)
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)
    return urlopen


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY)


def test_the_names_come_back_sorted_and_unique(key):
    seen = []
    names = models.list_models("https://x.test/v1/", "FAKE_LLM_KEY", opener({"data": [{"id": "b/model"}, {"id": "a/model"}, {"id": "b/model"}, {"object": "x"}]}, seen))
    assert names == ["a/model", "b/model"]
    request = seen[0]
    assert request.full_url == "https://x.test/v1/models" and request.get_method() == "GET" and request.get_header("Authorization") == f"Bearer {KEY}"


def test_no_key_means_no_request(monkeypatch):
    monkeypatch.delenv("FAKE_LLM_KEY", raising=False)
    seen = []
    with pytest.raises(WriterError, match="FAKE_LLM_KEY"):
        models.list_models("https://x.test/v1", "FAKE_LLM_KEY", opener({"data": []}, seen))
    assert seen == []


@pytest.mark.parametrize("outcome, words", [(urllib.error.HTTPError("u", 401, "x", {}, io.BytesIO(b"")), "refused"),
                                            (urllib.error.HTTPError("u", 500, "x", {}, io.BytesIO(b"")), "error"),
                                            (urllib.error.URLError("down"), "network"), (b"nope", "not a list"), ({"nope": 1}, "not a list"),
                                            ({"data": 5}, "not a list")])
def test_failures_are_clear_and_never_contain_the_key(key, outcome, words):
    with pytest.raises(WriterError, match=words) as info:
        models.list_models("https://x.test/v1", "FAKE_LLM_KEY", opener(outcome))
    assert KEY not in str(info.value)


def test_http_is_refused():
    with pytest.raises(WriterError):
        models.list_models("http://x.test/v1", "FAKE_LLM_KEY")


def test_the_command_filters_and_counts(key, monkeypatch, capsys):
    monkeypatch.setattr(models, "list_models", lambda base, env: ["meta/llama-instruct", "x/embedder", "y/Instruct-2"])
    assert models.main(["--writer", "nvidia", "--contains", "instruct"]) == 0
    out = capsys.readouterr().out
    assert "meta/llama-instruct" in out and "y/Instruct-2" in out and "embedder" not in out and "2 model(s) shown, 3 offered" in out


def test_the_command_reports_problems_without_the_key(monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    assert models.main(["--writer", "nvidia"]) == 1
    err = capsys.readouterr().err
    assert "NVIDIA_API_KEY is not set" in err
    assert models.main(["--writer", "nonsense"]) == 1
    assert models.main(["--writer", "custom"]) == 1


# ---------- the probe, and the safe explanation of service errors ----------

from agent.writer import OpenAICompatibleWriter, service_detail  # noqa: E402


def err(code, body):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")))


def test_service_detail_hides_the_key_and_long_identifiers_and_shortens():
    body = {"detail": f"Function 'a1b2c3d4-e5f6-7890-abcd-ef1234567890': Not found for account '0123456789abcdef0123'. key {KEY} nvapi-ABCDEFGH12345"}
    text = service_detail(err(404, body), KEY)
    assert KEY not in text and "nvapi" not in text and "a1b2c3d4" not in text and "0123456789abcdef" not in text
    assert "<id>" in text and "Not found for account" in text
    assert len(service_detail(err(404, {"detail": "x " * 500}), KEY)) <= 140


@pytest.mark.parametrize("body, expected", [({"message": "plain message"}, "plain message"), ({"title": "A title"}, "A title"),
                                            ({"error": {"message": "nested"}}, "nested"), ({"error": "text error"}, "text error"),
                                            (b"not json", ""), ({"detail": 5}, ""), ([1, 2], ""), ({}, "")])
def test_service_detail_reads_the_common_shapes_and_never_crashes(body, expected):
    assert service_detail(err(400, body), KEY) == expected


def test_the_writer_error_carries_the_clean_explanation_but_never_the_key(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY)

    def urlopen(request, timeout):
        raise err(404, {"detail": f"Function 'a1b2c3d4-e5f6-7890-abcd-ef1234567890': Not found for account. {KEY}"})

    writer = OpenAICompatibleWriter("https://x.test/v1", "m", "FAKE_LLM_KEY", urlopen=urlopen, sleep=lambda s: None)
    with pytest.raises(WriterError) as info:
        writer.write([])
    message = str(info.value)
    assert "HTTP 404" in message and "service says: Function '<id>': Not found for account" in message
    assert KEY not in message and "a1b2c3d4" not in message


def test_the_probe_reports_which_models_answer_and_pauses_between_calls(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY)
    outcomes = {"good/model": {"choices": [{"message": {"content": "OK"}}]}, "gone/model": err(404, {"detail": "Not found for account"}),
                "busy/model": err(500, {"title": "oops"})}
    asked, sleeps = [], []

    def urlopen(request, timeout):
        body = json.loads(request.data)
        asked.append((body["model"], body["max_tokens"]))
        outcome = outcomes[body["model"]]
        if isinstance(outcome, Exception):
            raise outcome
        return Response(outcome)

    result = models.probe_models("https://x.test/v1", "FAKE_LLM_KEY", ["good/model", "gone/model", "busy/model"], urlopen=urlopen,
                                 sleep=sleeps.append, pause=1.6)
    assert [(n, ok) for n, ok, _ in result] == [("good/model", True), ("gone/model", False), ("busy/model", False)]
    assert "Not found for account" in result[1][2] and KEY not in str(result)
    assert asked == [("good/model", 8), ("gone/model", 8), ("busy/model", 8)], "one tiny call each, no retries"
    assert sleeps == [1.6, 1.6]


def test_the_probe_command_prints_a_clear_table(monkeypatch, capsys):
    monkeypatch.setattr(models, "list_models", lambda base, env: ["a/instruct", "b/instruct", "c/other"])
    def fake_probe(base, env, names, on_result=None, **options):
        results = [(n, n.startswith("a"), "OK" if n.startswith("a") else "HTTP 404: gone") for n in names]
        for r in results:
            on_result(r)
        return results

    monkeypatch.setattr(models, "probe_models", fake_probe)
    assert models.main(["--writer", "nvidia", "--contains", "instruct", "--probe"]) == 0
    out = capsys.readouterr().out
    assert "ANSWERS  a/instruct" in out and "no       b/instruct  -> HTTP 404: gone" in out and "1 of 2 models answered." in out
    assert "c/other" not in out


def test_each_probe_result_is_reported_before_the_next_model_is_asked(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY)
    events = []

    def urlopen(request, timeout):
        events.append(("asked", json.loads(request.data)["model"]))
        return Response({"choices": [{"message": {"content": "OK"}}]})

    models.probe_models("https://x.test/v1", "FAKE_LLM_KEY", ["m1", "m2", "m3"], urlopen=urlopen, sleep=lambda s: None,
                        on_result=lambda r: events.append(("shown", r[0])))
    assert events == [("asked", "m1"), ("shown", "m1"), ("asked", "m2"), ("shown", "m2"), ("asked", "m3"), ("shown", "m3")]


def test_service_detail_also_hides_opaque_account_ids_that_are_not_hexadecimal():
    body = {"detail": "Function 'a1b2c3d4-e5f6-7890-abcd-ef1234567890': Not found for account 'AbCdEfGhIjKlMnOp_qRsT-uVwXyZ0123'"}
    text = service_detail(err(404, body), KEY)
    assert text == "Function '<id>': Not found for account '<id>'"
    assert "AbCdEf" not in text


def test_the_probe_can_be_given_room_and_time_for_slow_reasoning_models(monkeypatch):
    monkeypatch.setenv("FAKE_LLM_KEY", KEY)
    asked, timeouts = [], []

    def urlopen(request, timeout):
        asked.append(json.loads(request.data)["max_tokens"])
        timeouts.append(timeout)
        return Response({"choices": [{"message": {"content": "OK"}}]})

    models.probe_models("https://x.test/v1", "FAKE_LLM_KEY", ["m"], urlopen=urlopen, sleep=lambda s: None, max_tokens=400, timeout=120)
    assert asked == [400] and timeouts == [120]


def test_the_command_can_probe_exact_names_and_refuses_unknown_ones(monkeypatch, capsys):
    monkeypatch.setattr(models, "list_models", lambda base, env: ["a/one", "b/two", "c/three"])
    seen = []

    def fake_probe(base, env, names, on_result=None, **options):
        seen.append((list(names), options))
        results = [(n, True, "OK") for n in names]
        for r in results:
            on_result(r)
        return results

    monkeypatch.setattr(models, "probe_models", fake_probe)
    assert models.main(["--writer", "nvidia", "--probe", "--names", "b/two, c/three", "--max-tokens", "400", "--timeout", "120"]) == 0
    assert seen == [(["b/two", "c/three"], {"max_tokens": 400, "timeout": 120.0})]
    assert models.main(["--writer", "nvidia", "--probe", "--names", "b/two,nope/missing"]) == 1
    assert "nope/missing" in capsys.readouterr().err
