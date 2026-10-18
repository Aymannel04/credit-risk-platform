"""A memo written by plain code from the fact sheet: the backup when the language model fails the inspector.

It is also the reference of what a correct memo looks like: a test requires that it always passes the inspector, in both languages.
"""

_SENTENCES = {
    "fr": {
        "approve": "Le risque estimé est inférieur à la première ligne de la politique.",
        "refer": "Le risque estimé se situe entre la première et la seconde ligne de la politique : un analyste doit examiner le dossier.",
        "decline": "Le risque estimé dépasse la seconde ligne de la politique.",
    },
    "en": {
        "approve": "The estimated risk is below the first line of the policy.",
        "refer": "The estimated risk lies between the first and the second line of the policy: a human analyst should review the file.",
        "decline": "The estimated risk is above the second line of the policy.",
    },
}

_TEXT = {
    "fr": {
        "summary": "Le modèle estime un risque de défaut de {pd} sur 24 mois. Recommandation : {label}.",
        "rows": [("credit_score", "Score de crédit"), ("dti", "Dettes / revenu"), ("ltv", "Prêt / valeur du bien"),
                 ("cltv", "Emprunt total / valeur du bien"), ("interest_rate", "Taux du prêt"), ("reference_rate", "Taux de référence"),
                 ("rate_spread", "Écart de taux"), ("number_of_borrowers", "Nombre d'emprunteurs"), ("mi_pct", "Assurance du prêt"),
                 ("term_months", "Durée en mois"), ("term_years", "Durée en années")],
        "risk": "Score du modèle : {score} points. Probabilité de défaut estimée : {pd}. Lignes de la politique illustrative : {line1} et {line2}.",
        "lost": "{phrase} ({points} points perdus).",
        "no_reasons": "Aucune raison détaillée n'est disponible.",
    },
    "en": {
        "summary": "The model estimates a default risk of {pd} over 24 months. Recommendation: {label}.",
        "rows": [("credit_score", "Credit score"), ("dti", "Debt to income"), ("ltv", "Loan to value"), ("cltv", "Total borrowing to value"),
                 ("interest_rate", "Loan rate"), ("reference_rate", "Reference rate"), ("rate_spread", "Rate spread"),
                 ("number_of_borrowers", "Number of borrowers"), ("mi_pct", "Loan insurance"), ("term_months", "Term in months"),
                 ("term_years", "Term in years")],
        "risk": "Model score: {score} points. Estimated default probability: {pd}. Lines of the illustrative policy: {line1} and {line2}.",
        "lost": "{phrase} ({points} points lost).",
        "no_reasons": "No detailed reason is available.",
    },
}


def render_data_section(language: str, display: dict, unknown: str) -> str:
    """The body of the 'Loan data' section. Written by plain code, never by the language model, and checked word for word by the inspector."""
    shown = lambda name: display.get(name, unknown)  # noqa: E731
    sep = " :" if language == "fr" else ":"
    return "\n".join(f"- {label}{sep} {shown(name)}" for name, label in _TEXT[language]["rows"])


def render_template_memo(facts: dict) -> str:
    lang = facts["language"]
    t, d = _TEXT[lang], facts["display"]
    reasons = [f"- {t['lost'].format(phrase=r['phrase'], points=d[r['points_lost']])}" for r in facts["reasons"]] or [f"- {t['no_reasons']}"]
    limits = [facts["disclaimer"], facts["caution"], *([facts["outside_range_text"]] if facts["outside_range_text"] else [])]
    h = facts["headings"]
    parts = [
        f"## {h[0]}", t["summary"].format(pd=d["probability_of_default"], label=facts["recommendation_label"]), "",
        f"## {h[1]}", facts["data_section"], "",
        f"## {h[2]}", t["risk"].format(score=d["score"], pd=d["probability_of_default"], line1=d["approve_below"], line2=d["decline_above"]), "",
        f"## {h[3]}", *reasons, "",
        f"## {h[4]}", f"**{facts['recommendation_label']}**. {_SENTENCES[lang][facts['recommendation']]}", "",
        f"## {h[5]}", " ".join(limits),
    ]
    return "\n".join(parts) + "\n"
