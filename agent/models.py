"""List the models a writer service offers, so that the model name is taken from the service and never guessed.

    python -m agent.models --writer nvidia                    # all model names
    python -m agent.models --writer nvidia --contains instruct   # only the names containing a word

Needs the key in the environment variable of the preset (NVIDIA_API_KEY). The key is only sent in the request header and never printed.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable

from agent.policy import PolicyError, load_policy
from agent.writer import OpenAICompatibleWriter, WriterError


def list_models(base_url: str, api_key_env: str, urlopen: Callable = urllib.request.urlopen, timeout: float = 30.0) -> list[str]:
    if not base_url.startswith("https://"):
        raise WriterError("the base URL must use https")
    key = os.environ.get(api_key_env, "")
    if not key:
        raise WriterError(f"the environment variable {api_key_env} is not set")
    request = urllib.request.Request(f"{base_url.rstrip('/')}/models", method="GET",
                                     headers={"Accept": "application/json", "Authorization": f"Bearer {key}"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return sorted({m["id"] for m in payload["data"] if isinstance(m.get("id"), str)})
    except urllib.error.HTTPError as e:
        reason = {401: "the API key was refused", 403: "the API key is not allowed to do this", 404: "address not found"}.get(e.code, "the service returned an error")
        raise WriterError(f"HTTP {e.code}: {reason}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise WriterError("could not reach the service (network or timeout)") from None
    except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError, AttributeError):
        raise WriterError("the service answered something that is not a list of models") from None


def probe_models(base_url: str, api_key_env: str, names: list[str], urlopen: Callable = urllib.request.urlopen,
                 sleep: Callable = time.sleep, pause: float = 1.6, on_result: Callable | None = None) -> list[tuple[str, bool, str]]:
    """Ask every model one tiny question and report (name, answered, short note). The pause keeps us under the free rate limit.
    `on_result` is called with each result as soon as it is known, so a person can watch the progress."""
    results = []
    for i, name in enumerate(names):
        if i:
            sleep(pause)
        writer = OpenAICompatibleWriter(base_url, name, api_key_env, max_tokens=8, retries=0, timeout=45.0, urlopen=urlopen, sleep=sleep)
        try:
            reply = writer.write([{"role": "user", "content": "Reply with the single word OK."}])
            results.append((name, True, " ".join(reply.split())[:30]))
        except WriterError as e:
            results.append((name, False, str(e)[:160]))
        if on_result:
            on_result(results[-1])
    return results


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--writer", default="nvidia", help="a preset of config/memo_policy.yaml, or custom")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--contains", default=None, help="only names containing this text (not case sensitive)")
    ap.add_argument("--probe", action="store_true", help="send each shown model one tiny question and report which ones really answer")
    a = ap.parse_args(argv)
    try:
        policy = load_policy()
        if a.writer == "custom":
            if not (a.base_url and a.key_env):
                raise WriterError("--writer custom needs --base-url and --key-env")
            base_url, key_env = a.base_url, a.key_env
        elif a.writer in policy.writers:
            base_url, key_env = policy.writers[a.writer]["base_url"], policy.writers[a.writer]["api_key_env"]
        else:
            raise WriterError(f"unknown writer '{a.writer}' (known: custom, {', '.join(sorted(policy.writers))})")
        names = list_models(base_url, key_env)
    except (WriterError, PolicyError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    shown = [n for n in names if not a.contains or a.contains.casefold() in n.casefold()]
    if not a.probe:
        print("\n".join(shown))
        print(f"{len(shown)} model(s) shown, {len(names)} offered in total.")
        return 0
    print(f"Asking {len(shown)} model(s) one tiny question each. Each result appears as soon as it is known (a slow model can take up to 45 s).", flush=True)

    def show(result):
        name, answered, note = result
        print(f"{'ANSWERS' if answered else 'no     '}  {name}  {'' if answered else '-> ' + note}", flush=True)

    outcomes = probe_models(base_url, key_env, shown, on_result=show)
    print(f"{sum(o[1] for o in outcomes)} of {len(outcomes)} models answered.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
