"""Evaluate the agent on the 15 test loans and write the results (JSON and a readable report) under results/.

    python -m agent.evaluate --writer pretend                       # a pretend careful writer: the loop works end to end (no model)
    python -m agent.evaluate --writer seeded                        # a pretend writer that ALWAYS makes one deliberate mistake: all must be rejected
    python -m agent.evaluate --writer nvidia --model <name>         # a real model (needs the key in the environment)

Every number in the results comes from the run that wrote them. The results contain no key, no address and no account number.
"""
import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agent.api_client import ApiError, LiveScorer, OfflineScorer
from agent.doubles import SEEDED_KINDS, good_reply, seeded_reply
from agent.facts import build_facts
from agent.memo import generate_memo
from agent.policy import ROOT, Policy, PolicyError, load_policy
from agent.run import make_writer
from agent.writer import ScriptedWriter, WriterError

CASES_PATH = ROOT / "agent" / "cases" / "eval_cases.json"
EVIDENCE_CHARS = 2500   # how much of what the model wrote is kept in the results, for the loans that needed a rewrite or fell back
RESULTS = ROOT / "results"


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    cases = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate case ids")
    return cases


def evaluate_cases(cases: list[dict], scorer, writer_for, policy: Policy, language: str, writer_name: str, progress=None) -> dict:
    """`writer_for(facts)` gives the writer to use for one case (a shared real model, or a pretend one built from the facts)."""
    rows = []
    for index, case in enumerate(cases, start=1):
        facts = build_facts(case["loan"], scorer.explain(case["loan"]), policy, language)
        started = time.monotonic()
        result = generate_memo(facts, writer_for(facts), policy)
        seconds = round(time.monotonic() - started, 1)
        rows.append({
            "case": case["id"], "decision": facts["recommendation"], "status": result.status, "tries": len(result.attempts),
            "first_try": result.first_try, "seconds": seconds, "problems_by_try": [sorted({p.code for p in a.problems}) for a in result.attempts],
            "writer_errors": [a.error for a in result.attempts if a.error], "memo": result.memo})
        if result.status == "backup" or len(result.attempts) > 1:  # the evidence for the loans that did not pass at once
            rows[-1]["evidence"] = [{"try": a.number, "complaints": [f"[{p.code}] {p.message[:200]}" for p in a.problems],
                                     "what_the_model_wrote": a.reply[:EVIDENCE_CHARS]} for a in result.attempts]
        if progress:
            progress(index, len(cases), rows[-1])
    codes = Counter(c for r in rows for tries in r["problems_by_try"] for c in tries)
    n = len(rows)
    return {
        "writer": writer_name, "language": language, "scorer": scorer.name, "cases": n,
        "accepted_first_try": sum(r["first_try"] for r in rows),
        "accepted_after_rewrite": sum(r["status"] == "accepted" and not r["first_try"] for r in rows),
        "backup_memo": sum(r["status"] == "backup" for r in rows),
        "writer_errors": sum(bool(r["writer_errors"]) for r in rows),
        "mean_tries": round(sum(r["tries"] for r in rows) / n, 2) if n else 0,
        "mean_seconds_per_loan": round(sum(r["seconds"] for r in rows) / n, 1) if n else 0,
        "slowest_loan_seconds": max((r["seconds"] for r in rows), default=0),
        "decisions": dict(Counter(r["decision"] for r in rows)),
        "problem_codes": dict(sorted(codes.items())), "rows": rows}


def evaluate_seeded(cases: list[dict], scorer, policy: Policy, language: str) -> dict:
    """Every case x every kind of deliberate mistake, forced on all tries. The loop must end on the backup memo every time."""
    rows = []
    for case in cases:
        facts = build_facts(case["loan"], scorer.explain(case["loan"]), policy, language)
        for kind in SEEDED_KINDS:
            writer = ScriptedWriter([seeded_reply(facts, kind)] * (policy.max_rewrites + 1), name=f"seeded-{kind}")
            result = generate_memo(facts, writer, policy)
            rows.append({"case": case["id"], "kind": kind, "status": result.status, "tries": len(result.attempts)})
    rejected = sum(r["status"] == "backup" for r in rows)
    return {"writer": "seeded mistakes (pretend writer)", "language": language, "scorer": scorer.name, "cases": len(cases),
            "kinds": list(SEEDED_KINDS), "runs": len(rows), "rejected": rejected, "reached_the_reader": len(rows) - rejected,
            "rejection_rate": round(rejected / len(rows), 4) if rows else 0, "rows": rows}


def render_report(result: dict, policy: Policy) -> str:
    settings = result.get("settings")
    head = [f"# Memo agent evaluation: {result['writer']}", "",
            f"Language: {result['language']}. Scoring: {result['scorer']}. Decision lines: {policy.approve_below:.0%} and {policy.decline_above:.0%} "
            f"(assumption). Generated {result['generated_utc']}." + (f" Writer settings: {settings}." if settings else ""), ""]
    if "rejection_rate" in result:
        head += [f"**{result['rejected']} of {result['runs']} deliberately damaged memos were rejected; {result['reached_the_reader']} reached the reader.** "
                 f"({result['cases']} loans x {len(result['kinds'])} kinds of mistake, forced on every try.)", "",
                 "Kinds: " + ", ".join(f"`{k}`" for k in result["kinds"]) + ".", ""]
        return "\n".join(head) + "\n"
    head += ["| Measure | Value |", "|---|---|", f"| Loans | {result['cases']} |",
             f"| Accepted on the first try | {result['accepted_first_try']} |", f"| Accepted after a rewrite | {result['accepted_after_rewrite']} |",
             f"| Backup memo (written by code) | {result['backup_memo']} |", f"| Loans where the writer itself failed | {result['writer_errors']} |",
             f"| Mean number of tries | {result['mean_tries']} |", f"| Decisions | {result['decisions']} |",
             f"| Seconds per loan (mean, slowest) | {result.get('mean_seconds_per_loan', 'not recorded')}, {result.get('slowest_loan_seconds', 'not recorded')} |",
             f"| Complaints raised by the inspector | {result['problem_codes'] or 'none'} |", "",
             "| Case | Decision | Result | Tries | Seconds | Complaints per try |", "|---|---|---|---|---|---|"]
    for r in result["rows"]:
        head.append(f"| `{r['case']}` | {r['decision']} | {r['status']} | {r['tries']} | {r.get('seconds', '')} | {r['problems_by_try'] or ''} |")
    evidence = [r for r in result["rows"] if r.get("evidence")]
    if evidence:
        head += ["", "## Evidence for the loans that did not pass at once", "",
                 "What the inspector complained about on each try. The text the model wrote is kept in the JSON file.", ""]
        for r in evidence:
            head.append(f"### `{r['case']}` ({r['decision']}, {r['status']})")
            for e in r["evidence"]:
                head.append(f"- try {e['try']}: " + ("; ".join(e["complaints"]) or "accepted"))
            head.append("")
    return "\n".join(head) + "\n"


def save(result: dict, label: str, policy: Policy, out_dir: Path = RESULTS) -> tuple[Path, Path]:
    out_dir.mkdir(exist_ok=True)
    result = {"generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M"), **result}
    (out_dir / f"agent_eval_{label}.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / f"agent_eval_{label}.md").write_text(render_report(result, policy), encoding="utf-8")
    return out_dir / f"agent_eval_{label}.json", out_dir / f"agent_eval_{label}.md"


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--writer", required=True, help="pretend, seeded, nvidia or custom")
    ap.add_argument("--model", default=None)
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--key-env", default=None)
    ap.add_argument("--max-tokens", type=int, default=2500, help="room for the model's answer (reasoning models also think inside it)")
    ap.add_argument("--timeout", type=float, default=150.0, help="seconds to wait for the model")
    ap.add_argument("--temperature", type=float, default=0.0, help="0 = as repeatable as the service allows")
    ap.add_argument("--cases", default=None, help="only these case ids, separated by commas (default: all of the file)")
    ap.add_argument("--cases-file", default=str(CASES_PATH), help="the file of loans: agent/cases/eval_cases.json (15, used while tuning) "
                                                                  "or agent/cases/holdout_cases.json (20, never looked at while tuning)")
    ap.add_argument("--lang", choices=("fr", "en"), default="fr")
    ap.add_argument("--live-url", default=os.environ.get("CREDIT_API_URL"))
    ap.add_argument("--profile", default="credit-admin")
    ap.add_argument("--label", default=None, help="name of the result files (default: the writer)")
    a = ap.parse_args(argv)
    try:
        policy, cases = load_policy(), load_cases(Path(a.cases_file))
        if a.cases:
            wanted = [c.strip() for c in a.cases.split(",") if c.strip()]
            unknown = sorted(set(wanted) - {c["id"] for c in cases})
            if unknown:
                raise ValueError("unknown case id(s): " + ", ".join(unknown))
            cases = [c for c in cases if c["id"] in wanted]
        with (LiveScorer(a.live_url, profile=a.profile) if a.live_url else OfflineScorer()) as scorer:
            if a.writer == "seeded":
                result = evaluate_seeded(cases, scorer, policy, a.lang)
            elif a.writer == "pretend":
                result = evaluate_cases(cases, scorer, lambda f: ScriptedWriter([good_reply(f)], name="pretend careful writer"), policy, a.lang,
                                        "pretend careful writer (not a language model)")
            else:
                writer = make_writer(a.writer, policy, a.model, a.base_url, a.key_env, a.max_tokens, a.timeout, a.temperature)
                def show(i, n, row):
                    note = row["writer_errors"][0][:90] if row["writer_errors"] else ", ".join(c for t in row["problems_by_try"] for c in t)
                    print(f"[{i}/{n}] {row['case']}: {row['decision']}, {row['status']} after {row['tries']} try(ies), {row['seconds']} s" + (f" ({note})" if note else ""), flush=True)

                print(f"Running {len(cases)} loans with {a.model}. Each line appears when a loan is finished (a few seconds each).", flush=True)
                result = evaluate_cases(cases, scorer, lambda f: writer, policy, a.lang, f"{a.writer}: {a.model}", progress=show)
                result["settings"] = {"temperature": a.temperature, "max_tokens": a.max_tokens, "timeout_s": a.timeout}
    except (ApiError, WriterError, PolicyError, OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    label = a.label or (a.writer if a.writer in ("pretend", "seeded") else f"{a.writer}_{a.lang}")
    json_path, md_path = save(result, label, policy)
    print(render_report({"generated_utc": "now", **result}, policy))
    shown = lambda p: p.relative_to(ROOT) if ROOT in p.parents else p  # noqa: E731
    print(f"Wrote {shown(json_path)} and {shown(md_path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
