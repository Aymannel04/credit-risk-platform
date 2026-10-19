"""The writer: the one place where a language model is called. Everything else in the agent is plain code.

A writer takes chat messages (system, user, ...) and returns text. Two kinds:
- ScriptedWriter: returns texts chosen in advance (tests, demos, the seeded-error test). No network.
- OpenAICompatibleWriter: calls any service that speaks the OpenAI "chat completions" format with an API key from an environment
  variable (NVIDIA Build, Mistral, a local Ollama...). Standard library only. The key is read at call time, sent only in the
  Authorization header, and never written to a file, a log or an error message.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable


class WriterError(RuntimeError):
    """The writer could not produce text (network, key, quota, malformed answer). Never contains the API key."""


def service_detail(error: urllib.error.HTTPError, key: str, limit: int = 140) -> str:
    """The explanation the service gives with an error, made safe to show and to save: the key removed, long identifiers hidden, one line,
    shortened. Returns '' when there is nothing readable."""
    try:
        payload = json.loads(error.read().decode("utf-8", errors="replace"))
    except Exception:
        return ""
    candidates = [payload.get("detail"), payload.get("message"), payload.get("title"), (payload.get("error") or {}).get("message")
                  if isinstance(payload.get("error"), dict) else payload.get("error")] if isinstance(payload, dict) else []
    text = next((c for c in candidates if isinstance(c, str) and c.strip()), "")
    if key:
        text = text.replace(key, "***")
    text = re.sub(r"[0-9a-fA-F][0-9a-fA-F-]{15,}", "<id>", text)          # uuids, account ids, hashes
    text = re.sub(r"nvapi-[A-Za-z0-9_\-]+", "***", text)
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]", " ", text)).strip()
    return text[:limit]


class ScriptedWriter:
    def __init__(self, replies: list, name: str = "scripted"):
        """Each reply is a text, or a function (messages) -> text. They are used in order; asking for more raises WriterError."""
        self.name = name
        self._replies = list(replies)
        self.calls: list[list[dict]] = []

    def write(self, messages: list[dict]) -> str:
        self.calls.append(messages)
        if not self._replies:
            raise WriterError("the scripted writer has no reply left")
        reply = self._replies.pop(0)
        return reply(messages) if callable(reply) else reply


class OpenAICompatibleWriter:
    def __init__(self, base_url: str, model: str, api_key_env: str, temperature: float = 0.2, max_tokens: int = 900,
                 timeout: float = 60.0, retries: int = 2, urlopen: Callable = urllib.request.urlopen, sleep: Callable = time.sleep):
        if not base_url.startswith("https://") and not base_url.startswith("http://localhost") and not base_url.startswith("http://127.0.0.1"):
            raise WriterError("the base URL must use https (http is only allowed for a model running on this computer)")
        self.name = model
        self.base_url, self.model, self.api_key_env = base_url.rstrip("/"), model, api_key_env
        self.temperature, self.max_tokens, self.timeout, self.retries = temperature, max_tokens, timeout, retries
        self._urlopen, self._sleep = urlopen, sleep

    def write(self, messages: list[dict]) -> str:
        key = os.environ.get(self.api_key_env, "")
        if not key:
            raise WriterError(f"the environment variable {self.api_key_env} is not set")
        body = json.dumps({"model": self.model, "messages": messages, "temperature": self.temperature, "max_tokens": self.max_tokens}).encode("utf-8")
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, method="POST", headers={
                "Content-Type": "application/json", "Accept": "application/json", "Authorization": f"Bearer {key}"})
            try:
                with self._urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return self._text(payload)
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    self._sleep(2 ** attempt * 2)
                    continue
                reason = {401: "the API key was refused", 403: "the API key is not allowed to do this", 404: "model or address not found",
                          429: "rate limit reached"}.get(e.code, "the service returned an error")
                detail = service_detail(e, key)
                raise WriterError(f"HTTP {e.code}: {reason}" + (f" (service says: {detail})" if detail else "")) from None
            except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
                if attempt < self.retries:
                    self._sleep(2 ** attempt * 2)
                    continue
                raise WriterError("could not reach the service (network or timeout)") from None
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise WriterError("the service answered something that is not valid JSON") from None
        raise WriterError("no answer after the retries")

    @staticmethod
    def _text(payload: dict) -> str:
        try:
            text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise WriterError("the answer does not have the expected shape (choices[0].message.content)") from None
        if not isinstance(text, str) or not text.strip():
            raise WriterError("the service returned an empty text")
        return text
