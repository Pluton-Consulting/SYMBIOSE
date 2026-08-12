"""
Skills de la bibliothèque d'outils — la couche qui parle au modèle.

Chaque skill valide ses paramètres, appelle la fonction composée, et rend un
échec comme un ÉCHEC (`SkillError`). Les fonctions de `outils/` ne connaissent
ni l'utilisateur ni le protocole d'action : elles font le travail, c'est ici
qu'on branche l'identité et les droits.

Symbiose n'a pas de NAS : sa bibliothèque porte les documents et le mode
d'emploi. Les visuels gardent leurs deux actions séparées (voir
`outils/docs/visuels.md` : réunir un brief gratuit et une génération facturée
reviendrait à payer un tirage à chaque reformulation).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("symbiose.skills.outils")


def _echec(message: str):
    from skills.executor import SkillError
    raise SkillError(message)


def _proprietaire(user) -> str:
    return str(getattr(user, "id", "") or "")


async def produire_document(data: dict, user) -> dict:
    """Crée, remplit et finalise un document en un seul appel."""
    from outils.documents import produire

    proprio = _proprietaire(user)
    if not proprio:
        _echec("Impossible de produire un document sans compte identifié.")
    titre = (data.get("titre") or "").strip()
    if not titre:
        _echec("Donne un `titre` au document.")

    blocs = data.get("blocs") or data.get("elements") or data.get("contenu")
    if isinstance(blocs, dict):
        blocs = [blocs]
    try:
        return await produire(
            titre=titre, blocs=blocs, proprietaire=proprio,
            format=(data.get("format") or "pdf").strip().lower(),
            entete=(data.get("entete") or "").strip(),
            pied=(data.get("pied") or "").strip(),
            numeroter=data.get("numeroter", True))
    except Exception as e:  # noqa: BLE001
        _echec(str(getattr(e, "detail", None) or e))


async def mode_emploi(data: dict, user) -> dict:
    """Le mode d'emploi complet d'un outil, à la demande.

    Ce texte n'est PAS injecté dans le prompt : c'est tout son intérêt. Les
    vocabulaires, limites et pannes connues pèsent des milliers de caractères
    qu'on ne peut pas faire porter à chaque tour.
    """
    from outils import mode_emploi as lire_doc, outils_disponibles
    nom = (data.get("outil") or "").strip()
    if not nom:
        return {"outils": [{"nom": n, "libelle": l} for n, l in outils_disponibles()],
                "note": "Précise `outil` pour obtenir son mode d'emploi."}
    return {"outil": nom, "mode_emploi": lire_doc(nom)}


# ── Déclarations : tout ce que le système doit savoir, ICI ───────────
from skills.registre import Declaration

SKILLS = {
    "produire_document": Declaration(
        fonction=produire_document,
        description=(
            "PRODUIT un document telechargeable (pdf, docx, xlsx) en UNE fois "
            "et rend le lien. `blocs` : liste de {bloc:titre|paragraphe|liste|"
            "tableau|saut_page|feuille}. Un paragraphe accepte gras, italique, "
            "centre (booleens), taille (petit|normal|grand|tres_grand) et "
            "couleur (rouge|vert|bleu|orange|gris|noir). LA voie normale pour "
            "un document"),
        requis=["titre", "blocs"],
        optionnels=["format", "entete", "pied", "numeroter"],
        effet="ecriture_interne",
        libelle="je produis le document"),
    "mode_emploi": Declaration(
        fonction=mode_emploi,
        description=("MODE D'EMPLOI complet d'un outil (documents, visuels) : "
                     "conventions, limites, pannes connues. A lire quand aucune "
                     "action ne couvre le besoin"),
        optionnels=["outil"],
        effet="lecture",
        libelle="je relis le mode d'emploi de l'outil"),
}
