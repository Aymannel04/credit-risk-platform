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
