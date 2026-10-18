"""The instructions given to the writer (the language model), built from the fact sheet.

The model receives only what it is allowed to use: the numbers as they must be written (`display`), the reasons, the decision that was
already taken, and the sentences it must copy. It never receives the raw API answer, the model id or anything it could compute with.
"""
import json

from agent.policy import DATA_SECTION_INDEX, Policy
from agent.validator import Problem, problems_to_text

LANGUAGE_NAMES = {"fr": "French", "en": "English"}

SYSTEM = """You write a short credit memo for a human credit analyst. A program has ALREADY scored the loan and ALREADY decided the recommendation. You only WRITE the text.

Write the memo in {language}, in markdown. Write exactly these five sections, in this order, each starting on its own line with "## " and the exact title: {titles}. Do NOT write a section called "{data_title}": the system adds it by itself. Write nothing before the first title.

Hard rules. A program checks every one of them and throws away any memo that breaks one:
1. Use only numbers that appear in the fact sheet, copied exactly as written there (same digits, same decimal sign, same percent sign). Never compute, round, convert or invent a number. Use "- " bullets, never numbered lists.
2. Never write a number in words (for example never "two", "deux", "percent", "pour cent"): use the digits of the fact sheet.
3. The recommendation is already decided: {label}. Write it exactly like that in the section "{recommendation_title}". Never use words that belong to another decision.
4. Never promise or guarantee anything. Do not use these words: {forbidden}.
5. In the first section, state the default probability exactly as written: {risk}.
6. In the last section ("{limits_title}"), copy these sentences word for word, each one complete: {fixed_sentences}
7. In the section "{reasons_title}", explain the reasons in your own words, one bullet each, and copy the points lost exactly.
8. Keep your five sections between 90 and 160 words in total. Be factual and neutral."""


def build_system(facts: dict, policy: Policy) -> str:
    lang = policy.language(facts["language"])
    headings = facts["headings"]
    writer_titles = [h for i, h in enumerate(headings) if i != DATA_SECTION_INDEX]
    fixed = [facts["disclaimer"], facts["caution"], *([facts["outside_range_text"]] if facts["outside_range_text"] else [])]
    return SYSTEM.format(
        language=LANGUAGE_NAMES[facts["language"]], titles=" | ".join(writer_titles), data_title=headings[DATA_SECTION_INDEX],
        label=facts["recommendation_label"], recommendation_title=headings[4], forbidden=", ".join(lang.forbidden),
        risk=facts["display"]["probability_of_default"], limits_title=headings[5], reasons_title=headings[3],
        fixed_sentences=" ".join(f'"{s}"' for s in fixed))


def writer_view(facts: dict) -> dict:
    """The part of the fact sheet the writer may see (everything as it must be written)."""
    d = facts["display"]
    return {
        "recommendation_to_write": facts["recommendation_label"],
        "default_probability": d["probability_of_default"],
        "model_score_points": d["score"],
        "policy_lines": {"first_line": d["approve_below"], "second_line": d["decline_above"]},
        "reasons": [{"reason": r["phrase"], "points_lost": d[r["points_lost"]]} for r in facts["reasons"]],
        "numbers_you_may_mention": {k: v for k, v in d.items() if k not in ("approve_below", "decline_above", "caution_low", "caution_high")},
    }


def build_messages(facts: dict, policy: Policy, previous_reply: str | None = None, problems: list[Problem] | None = None) -> list[dict]:
    """First try: system + fact sheet. After a rejection: the same, then the writer's own rejected text and the inspector's complaints."""
    messages = [
        {"role": "system", "content": build_system(facts, policy)},
        {"role": "user", "content": "Fact sheet:\n" + json.dumps(writer_view(facts), ensure_ascii=False, indent=1) + "\n\nWrite the memo now."},
    ]
    if previous_reply is not None and problems:
        messages += [
            {"role": "assistant", "content": previous_reply},
            {"role": "user", "content": "The inspector rejected your memo for these reasons:\n" + problems_to_text(problems)
             + "\n\nWrite the whole memo again and fix every point."},
        ]
    return messages
