"""The inspector: plain code that checks a memo against the fact sheet. No language model is involved here.

validate_memo() returns a list of problems; an empty list means the memo may be published. Every problem has a short code and a sentence
that is given back to the writer when it is asked to rewrite.

What it checks, and what it cannot check (honest limits):
- every number written in the memo must be a fact (rounded to the precision written) or an allowed constant. It cannot tell WHICH fact:
  a memo that swaps two different facts which are both on the sheet still passes the number check;
- numbers spelled out in words are caught only through the list `spelled_numbers` of the policy file (one, un and une are allowed);
- the language is checked through the fixed headings and the fixed disclaimer, not by detecting the language of the sentences.
"""
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from agent.policy import DATA_SECTION_INDEX, RECOMMENDATION_SECTION_INDEX, Policy

# A number: digits, maybe a decimal part, and a minus sign when it is a real sign (not preceded by a letter or digit, so "36-40" is two numbers).
# Both the hyphen and the typographic minus are read as a sign: a negative fact (an interest rate below its reference) must be copied with it.
NUMBER = re.compile(r"(?:(?<!\w)[-−])?\d+(?:[.,]\d+)?")
HEADING = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Problem:
    code: str
    message: str


def count_words(text: str) -> int:
    """The one way words are counted, here and in the instructions given to the writer."""
    return len(re.findall(r"\w+", text))


def _squash(text: str) -> str:
    """Single spaces, and no space before a percent sign, so '9,17 %' and '9,17%' are the same."""
    return re.sub(r"\s+%", "%", re.sub(r"\s+", " ", text)).strip()


def _plain(token: str) -> str:
    """The token as text Decimal can read: decimal point, ordinary minus."""
    return token.replace("−", "-").replace(",", ".")


def _decimals(token: str) -> int:
    return len(_plain(token).split(".")[1]) if "." in _plain(token) else 0


def _allowed_values(facts: dict, policy: Policy) -> list[Decimal]:
    return [Decimal(v) for v in facts["numbers"].values()] + [Decimal(c) for c in policy.allowed_constants]


def _is_fact(token: str, allowed: list[Decimal]) -> bool:
    value, d = Decimal(_plain(token)), _decimals(token)
    unit = Decimal(1).scaleb(-d)
    return any(a.quantize(unit, rounding=ROUND_HALF_UP) == value for a in allowed)


def _sign_hints(bad: list[str], allowed: list[Decimal]) -> str:
    """When a rejected number is a fact with the opposite sign (a loss written as -52,1 instead of 52,1), say exactly that."""
    hints = []
    for token in bad:
        plain = _plain(token)
        if plain.startswith("-") and _is_fact(token[1:], allowed):
            hints.append(f"{token[1:]} is on the sheet WITHOUT a minus sign: write {token[1:]}, not {token}")
        elif not plain.startswith("-") and _is_fact("-" + token, allowed):
            hints.append(f"the sheet has -{token} WITH a minus sign: write -{token}, not {token}")
    return (" Sign problems: " + "; ".join(hints) + ".") if hints else ""


# Which complaints are about the SAFETY of the memo (a wrong or invented number, a wrong or conflicting decision, a missing warning,
# a promise) and which are about its FORM (headings, length). The exam reports both: a memo rejected only for its form is not a wrong memo.
SAFETY_CODES = frozenset({"NUMBER_NOT_IN_FACTS", "SPELLED_NUMBER", "DECISION_MISSING", "DECISION_CONFLICT", "DISCLAIMER_MISSING", "CAUTION_MISSING",
                          "OUTSIDE_RANGE_MISSING", "RISK_MISSING", "FORBIDDEN_PHRASE", "DATA_SECTION_ALTERED"})
FORM_CODES = frozenset({"EMPTY", "SECTIONS", "TEXT_OUTSIDE_SECTIONS", "EMPTY_SECTION", "LENGTH"})


def _sections(memo: str, headings: list[str]) -> tuple[dict[str, str] | None, str]:
    """The memo split by its '## ' headings, or None if the headings are not exactly the expected ones, in order. Second value: text before the first heading."""
    found = list(HEADING.finditer(memo))
    before = memo[: found[0].start()] if found else memo
    if [m.group(1) for m in found] != headings:
        return None, before
    bodies = {}
    for i, m in enumerate(found):
        end = found[i + 1].start() if i + 1 < len(found) else len(memo)
        bodies[m.group(1)] = memo[m.end():end].strip()
    return bodies, before


def validate_memo(memo: str, facts: dict, policy: Policy) -> list[Problem]:
    problems: list[Problem] = []
    lang = policy.language(facts["language"])
    if not memo or not memo.strip():
        return [Problem("EMPTY", "The memo is empty.")]
    flat = _squash(memo)
    folded = flat.casefold()

    sections, before = _sections(memo, facts["headings"])
    if sections is None:
        data_title = facts["headings"][DATA_SECTION_INDEX]  # inserted by the system, so it is not the writer's to get right or wrong
        written = [m.group(1) for m in HEADING.finditer(memo) if m.group(1) != data_title]
        wanted = [h for h in facts["headings"] if h != data_title]
        missing = [h for h in wanted if h not in written]
        extra = [h for h in written if h not in facts["headings"]]
        details = (f" Missing: {', '.join(missing)}." if missing else "") + (f" Not allowed: {', '.join(extra)}." if extra else "")
        problems.append(Problem("SECTIONS", "Use exactly these five headings, in this order, each on its own line starting with '## ': "
                                + " | ".join(wanted) + f". You wrote: {' | '.join(written) or 'no heading'}." + details))
    else:
        if before.strip():
            problems.append(Problem("TEXT_OUTSIDE_SECTIONS", "Write nothing before the first heading."))
        for heading, body in sections.items():
            if not body:
                problems.append(Problem("EMPTY_SECTION", f"The section '{heading}' is empty."))
        data_heading = facts["headings"][DATA_SECTION_INDEX]
        if "data_section" in facts and _squash(sections[data_heading]) != _squash(facts["data_section"]):
            problems.append(Problem("DATA_SECTION_ALTERED", f"The section '{data_heading}' is written by the system: do not change it."))

    words = count_words(memo)
    if words > policy.max_words:
        cut = words - policy.max_words + 20
        problems.append(Problem("LENGTH", f"The memo has {words} words and the limit is {policy.max_words}: remove at least {cut} words of your own text "
                                          "(the system's 'Loan data' section and the fixed sentences cannot be shortened)."))
    elif words < policy.min_words:
        problems.append(Problem("LENGTH", f"The memo has {words} words; it needs at least {policy.min_words}."))

    allowed = _allowed_values(facts, policy)
    bad = sorted({t for t in NUMBER.findall(memo) if not _is_fact(t, allowed)})
    if bad:
        problems.append(Problem("NUMBER_NOT_IN_FACTS", "These numbers are not on the fact sheet: " + ", ".join(bad)
                                + ". Copy numbers exactly as written on the fact sheet and never compute a new one." + _sign_hints(bad, allowed)))

    spelled = [w for w in lang.spelled_numbers if re.search(rf"(?<!\w){re.escape(w)}(?!\w)", folded)]
    if spelled:
        problems.append(Problem("SPELLED_NUMBER", "Do not write quantities in words (" + ", ".join(spelled) + "): use the digits of the fact sheet."))

    label = facts["recommendation_label"].casefold()
    decision_text = (sections[facts["headings"][RECOMMENDATION_SECTION_INDEX]] if sections else memo)
    if label not in _squash(decision_text).casefold():
        problems.append(Problem("DECISION_MISSING", f"The recommendation section must state the recommendation exactly as: {facts['recommendation_label']}."))
    for other in (d for d in lang.labels if d != facts["recommendation"]):
        patterns = [re.escape(lang.labels[other].casefold()), *[s.casefold() for s in lang.decision_stems[other]]]
        hits = [m.group() for pattern in patterns if (m := re.search(rf"(?<!\w)(?:{pattern})(?!\w)", folded))]
        if hits:
            problems.append(Problem("DECISION_CONFLICT", f"The recommendation is {facts['recommendation_label']}: remove the words that belong to another decision ({', '.join(hits)})."))

    if _squash(facts["disclaimer"]).casefold() not in folded:
        problems.append(Problem("DISCLAIMER_MISSING", f"Include this sentence exactly: {facts['disclaimer']}"))
    if _squash(facts["caution"]).casefold() not in folded:
        problems.append(Problem("CAUTION_MISSING", f"Include this sentence exactly: {facts['caution']}"))
    if facts["outside_range_text"] and _squash(facts["outside_range_text"]).casefold() not in folded:
        problems.append(Problem("OUTSIDE_RANGE_MISSING", f"Include this sentence exactly: {facts['outside_range_text']}"))
    if _squash(facts["display"]["probability_of_default"]).casefold() not in folded:
        problems.append(Problem("RISK_MISSING", f"State the default probability exactly as written on the fact sheet: {facts['display']['probability_of_default']}."))

    banned = [w for w in lang.forbidden if re.search(rf"(?<!\w){re.escape(w.casefold())}(?!\w)", folded)]
    if banned:
        problems.append(Problem("FORBIDDEN_PHRASE", "Remove these forbidden words: " + ", ".join(banned) + ". The memo must never promise or guarantee anything."))
    return problems


def problems_to_text(problems: list[Problem]) -> str:
    return "\n".join(f"- [{p.code}] {p.message}" for p in problems)
