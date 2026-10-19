"""The loop: ask the writer, inspect, give the complaints back, try again (at most `max_rewrites` times), then fall back to the memo written by code.

Guarantees (each one has a test):
- the returned memo ALWAYS passes the inspector: it is either a memo the inspector accepted or the backup memo written by code;
- a writer that fails (network, key, quota, nonsense) never makes the function raise: the result is the backup memo, with the reason recorded;
- the 'Loan data' section is always the one written by code, whatever the writer produced.
"""
import inspect
import re
from dataclasses import dataclass, field

from agent.policy import DATA_SECTION_INDEX, Policy
from agent.prompt import build_messages
from agent.template import render_template_memo
from agent.validator import Problem, validate_memo
from agent.writer import WriterError

BACKUP_FLAG = "LLM memo rejected"


class MemoError(RuntimeError):
    """A bug in the agent itself (the backup memo failed the inspector). Never raised because of the writer."""


@dataclass
class Attempt:
    number: int
    reply: str = ""
    memo: str = ""
    problems: list[Problem] = field(default_factory=list)
    error: str = ""


@dataclass
class MemoResult:
    memo: str
    status: str              # "accepted" (written by the model, inspected) or "backup" (written by code)
    writer: str
    attempts: list[Attempt]
    flag: str = ""           # BACKUP_FLAG when the backup memo was used

    @property
    def first_try(self) -> bool:
        return self.status == "accepted" and len(self.attempts) == 1


def _strip_fence(reply: str) -> str:
    """Models often wrap the whole answer in a markdown code fence, and reasoning models may print their thinking between <think> tags:
    both are formatting around the memo, not part of it."""
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL | re.IGNORECASE).lstrip()
    m = re.fullmatch(r"\s*```[a-zA-Z]*\n(.*?)\n?```\s*", reply, flags=re.DOTALL)
    return m.group(1) if m else reply


def _relayout(reply: str, titles: list[str]) -> str:
    """After a complaint a small model sometimes squeezes the whole memo onto one line ("## Résumé text ## Analyse ...") or puts a title and its
    text on the same line. Putting each KNOWN title back on its own line changes no word and no number, only the line breaks."""
    alt = "|".join(re.escape(t) for t in sorted(titles, key=len, reverse=True))
    inline = re.search(rf"\S[ \t]+##[ \t]+(?:{alt})\b", reply) or re.search(rf"(?m)^##[ \t]+(?:{alt})[ \t]+\S", reply)
    if not inline:
        return reply
    return re.sub(rf"[ \t]*##[ \t]+({alt})(?=[ \t\n]|$)[ \t]*", lambda m: f"\n\n## {m.group(1)}\n", reply).lstrip("\n")


def assemble(reply: str, facts: dict) -> str:
    """The writer's text with the 'Loan data' section replaced by (or inserted as) the one written by code. Anything else the writer
    wrote (extra text, extra or missing titles) is left alone so that the inspector sees it."""
    heading = facts["headings"][DATA_SECTION_INDEX]
    reply = _relayout(_strip_fence(reply), facts["headings"])
    found = list(re.finditer(r"(?m)^##\s+(.+?)\s*$", reply))
    code_section = f"## {heading}\n{facts['data_section']}\n\n"
    if not found:
        return reply if not reply.strip() else reply.rstrip() + "\n\n" + code_section
    preamble = reply[: found[0].start()]
    blocks = []
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(reply)
        blocks.append((m.group(1), reply[m.start():end].rstrip() + "\n\n"))
    out = []
    inserted = False
    for title, block in blocks:
        if title == heading:
            out.append(code_section)
            inserted = True
        else:
            out.append(block)
    if not inserted:
        out.insert(1 if blocks and blocks[0][0] == facts["headings"][0] else len(out), code_section)
    return (preamble + "".join(out)).rstrip() + "\n"


def _write(writer, messages: list[dict], temperature: float | None) -> str:
    """Ask the writer; after a rejection a different temperature is requested (the same question at temperature 0 gave the same memo again).
    Writers whose `write` does not take a temperature are simply called without it."""
    if temperature is not None and "temperature" in inspect.signature(writer.write).parameters:
        return writer.write(messages, temperature=temperature)
    return writer.write(messages)


def generate_memo(facts: dict, writer, policy: Policy) -> MemoResult:
    attempts: list[Attempt] = []
    previous_reply, previous_problems = None, None
    for n in range(1, policy.max_rewrites + 2):
        attempt = Attempt(number=n)
        attempts.append(attempt)
        try:
            attempt.reply = _write(writer, build_messages(facts, policy, previous_reply, previous_problems),
                                   policy.retry_temperature if n > 1 else None)
        except WriterError as e:
            attempt.error = str(e)
            break
        except Exception as e:  # a faulty writer must never break the agent
            attempt.error = f"unexpected error in the writer: {type(e).__name__}"
            break
        attempt.memo = assemble(attempt.reply, facts)
        attempt.problems = validate_memo(attempt.memo, facts, policy)
        if not attempt.problems:
            return MemoResult(memo=attempt.memo, status="accepted", writer=writer.name, attempts=attempts)
        previous_reply, previous_problems = attempt.reply, attempt.problems
    backup = render_template_memo(facts)
    leftovers = validate_memo(backup, facts, policy)
    if leftovers:
        raise MemoError("the backup memo failed the inspector: " + "; ".join(p.code for p in leftovers))
    return MemoResult(memo=backup, status="backup", writer=writer.name, attempts=attempts, flag=BACKUP_FLAG)
