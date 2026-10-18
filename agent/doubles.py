"""Pretend writers for tests and offline runs. They are NOT language models and prove nothing about a real model: they exist so that the loop,
the inspector and the backup memo can be tested without a network, a key or any cost.

- good_reply(facts): what a careful model would write (five sections, in its own wording, every rule respected).
- seeded_reply(facts, kind): the same memo with ONE deliberate mistake of a known kind. The inspector must reject all of them.
"""
import re

SEEDED_KINDS = ("wrong_number", "invented_number", "wrong_decision", "promise", "number_in_words", "missing_disclaimer",
                "wrong_heading", "text_before_heading", "missing_risk", "other_language")

_WORDS = {
    "fr": {
        "summary": "Pour ce dossier, le modèle estime le risque de défaut à {pd} sur 24 mois. La recommandation est {label}.",
        "risk": "Le score du modèle est de {score} points. Les lignes de la politique illustrative sont {line1} et {line2}.",
        "reason": "{phrase} ({points} points perdus).",
        "recommendation": "{label}",
        "promise": "Ce prêt est garanti.", "words": "Environ trois dossiers comparables.", "invented": "Environ 777 dossiers comparables.",
    },
    "en": {
        "summary": "For this file, the model estimates the default risk at {pd} over 24 months. The recommendation is {label}.",
        "risk": "The model score is {score} points. The lines of the illustrative policy are {line1} and {line2}.",
        "reason": "{phrase} ({points} points lost).",
        "recommendation": "{label}",
        "promise": "This loan is guaranteed.", "words": "About three comparable files.", "invented": "About 777 comparable files.",
    },
}


def good_reply(facts: dict) -> str:
    """Five sections (the 'Loan data' section is added by the system), as a careful model would write them."""
    lang, d, h = facts["language"], facts["display"], facts["headings"]
    w = _WORDS[lang]
    reasons = "\n".join(f"- {w['reason'].format(phrase=r['phrase'], points=d[r['points_lost']])}" for r in facts["reasons"]) or "- -"
    limits = " ".join([facts["disclaimer"], facts["caution"], *([facts["outside_range_text"]] if facts["outside_range_text"] else [])])
    return "\n".join([
        f"## {h[0]}", w["summary"].format(pd=d["probability_of_default"], label=facts["recommendation_label"]), "",
        f"## {h[2]}", w["risk"].format(score=d["score"], line1=d["approve_below"], line2=d["decline_above"]), "",
        f"## {h[3]}", reasons, "",
        f"## {h[4]}", w["recommendation"].format(label=facts["recommendation_label"]), "",
        f"## {h[5]}", limits, ""])


def seeded_reply(facts: dict, kind: str) -> str:
    """good_reply with one deliberate mistake."""
    lang, d, h = facts["language"], facts["display"], facts["headings"]
    text, w = good_reply(facts), _WORDS[facts["language"]]
    other_labels = [x for x in ("approve", "refer", "decline") if x != facts["recommendation"]]
    if kind == "wrong_number":
        return text.replace(d["probability_of_default"], "77,7 %" if lang == "fr" else "77.7%")
    if kind == "invented_number":
        return text + "\n" + w["invented"] + "\n"
    if kind == "wrong_decision":
        from agent.policy import load_policy
        wrong = load_policy().language(lang).labels[other_labels[0]]
        return text.replace(facts["recommendation_label"], wrong)
    if kind == "promise":
        return text + "\n" + w["promise"] + "\n"
    if kind == "number_in_words":
        return text + "\n" + w["words"] + "\n"
    if kind == "missing_disclaimer":
        return text.replace(facts["disclaimer"], "")
    if kind == "wrong_heading":
        return text.replace(f"## {h[5]}", "## Notes")
    if kind == "text_before_heading":
        return ("Voici le mémo demandé :\n" if lang == "fr" else "Here is the memo you asked for:\n") + text
    if kind == "missing_risk":
        return text.replace(d["probability_of_default"], "un risque modéré" if lang == "fr" else "a moderate risk")
    if kind == "other_language":
        other = "en" if lang == "fr" else "fr"
        return re.sub(r"(?m)^## .*$", lambda m: f"## {_other_heading(other, m.group())}", text)
    raise ValueError(f"unknown kind of seeded mistake: {kind}")


def _other_heading(language: str, heading_line: str) -> str:
    from agent.policy import load_policy
    own = {h: i for lang in load_policy().languages.values() for i, h in enumerate(lang.headings)}
    index = own.get(heading_line[3:], 0)
    return load_policy().language(language).headings[index]
