"""Make one credit memo from the command line.

    python -m agent.run --loan loan.json                                  # no language model: the memo written by code
    python -m agent.run --loan loan.json --writer nvidia --model <name>   # a language model writes, the inspector checks
    python -m agent.run --loan loan.json --live-url <url> --profile credit-admin   # score with the real Lambda API (signed)

The scoring is read-only. The key of the writer is read from an environment variable and never printed. The memo is printed in UTF-8.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from agent.api_client import ApiError, LiveScorer, OfflineScorer
from agent.facts import build_facts
from agent.memo import MemoResult, generate_memo
from agent.policy import Policy, PolicyError, load_policy
from agent.template import render_template_memo
from agent.writer import OpenAICompatibleWriter, WriterError


def run_one(loan: dict, language: str | None, writer, scorer, policy: Policy) -> tuple[dict, MemoResult]:
    facts = build_facts(loan, scorer.explain(loan), policy, language)
    return facts, generate_memo(facts, writer, policy)


def make_writer(kind: str, policy: Policy, model: str | None, base_url: str | None = None, key_env: str | None = None,
                max_tokens: int = 2500, timeout: float = 150.0, temperature: float = 0.0):
    """`max_tokens` is the room for the whole answer: 'reasoning' models spend part of it thinking, so it is generous."""
    if kind == "backup":
        return None
    if not model:
        raise WriterError("choose the model with --model (take its name from the list of the service, never guess it)")
    if kind == "custom":
        if not (base_url and key_env):
            raise WriterError("--writer custom needs --base-url and --key-env")
        return OpenAICompatibleWriter(base_url, model, key_env, max_tokens=max_tokens, timeout=timeout, temperature=temperature)
    if kind not in policy.writers:
        raise WriterError(f"unknown writer '{kind}' (known: backup, custom, {', '.join(sorted(policy.writers))})")
    preset = policy.writers[kind]
    return OpenAICompatibleWriter(preset["base_url"], model, preset["api_key_env"], max_tokens=max_tokens, timeout=timeout, temperature=temperature)


def describe(result: MemoResult) -> str:
    if result.status == "accepted":
        return f"status: accepted by the inspector on try {len(result.attempts)} (writer: {result.writer})"
    reasons = "; ".join(f"try {a.number}: " + (a.error or ", ".join(sorted({p.code for p in a.problems}))) for a in result.attempts)
    return f"status: BACKUP memo written by code ({result.flag}). {reasons}" if reasons else f"status: backup memo written by code ({result.flag})"


def show_attempts(result: MemoResult, limit: int = 3500) -> str:
    """What the model wrote on each try (cut after `limit` characters) and what the inspector said about it."""
    lines = []
    for a in result.attempts:
        lines.append(f"=== try {a.number} " + ("(the writer failed: " + a.error + ")" if a.error else "(written by the model)"))
        if a.reply:
            lines.append(a.reply if len(a.reply) <= limit else a.reply[:limit] + f"\n[... {len(a.reply) - limit} more characters]")
        for p in a.problems:
            lines.append(f"  inspector: [{p.code}] {p.message[:160]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--loan", required=True, help="a JSON file with the 10 fields of the API (/explain)")
    ap.add_argument("--lang", choices=("fr", "en"), default=None, help="memo language (default: the policy file's)")
    ap.add_argument("--writer", default="backup", help="backup (no model), nvidia (preset of the policy file) or custom")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--key-env", default=None, help="name of the environment variable that holds the key")
    ap.add_argument("--max-tokens", type=int, default=2500, help="room for the model's answer (reasoning models also think inside it)")
    ap.add_argument("--timeout", type=float, default=150.0, help="seconds to wait for the model")
    ap.add_argument("--temperature", type=float, default=0.0, help="0 = as repeatable as the service allows")
    ap.add_argument("--live-url", default=os.environ.get("CREDIT_API_URL"), help="use the real Lambda API (or set CREDIT_API_URL)")
    ap.add_argument("--profile", default="credit-admin")
    ap.add_argument("--out", default=None, help="also write the memo to this file")
    ap.add_argument("--show-attempts", action="store_true", help="print what the model wrote on each try, with the inspector's complaints")
    a = ap.parse_args(argv)
    result = None
    try:
        policy = load_policy()
        loan = json.loads(Path(a.loan).read_text(encoding="utf-8"))
        writer = make_writer(a.writer, policy, a.model, a.base_url, a.key_env, a.max_tokens, a.timeout, a.temperature)
        with (LiveScorer(a.live_url, profile=a.profile) if a.live_url else OfflineScorer()) as scorer:
            if writer is None:
                facts = build_facts(loan, scorer.explain(loan), policy, a.lang)
                memo, status = render_template_memo(facts), "status: memo written by code (no language model requested)"
            else:
                facts, result = run_one(loan, a.lang, writer, scorer, policy)
                memo, status = result.memo, describe(result)
    except (ApiError, WriterError, PolicyError, OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(memo)
    print(status)
    if a.show_attempts and result is not None:
        print(show_attempts(result))
    if a.out:
        Path(a.out).write_text(memo, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
