"""
Skill natif : produire un visuel paysager (§6).

DEUX TEMPS, ET C'EST VOLONTAIRE.

  1. `preparer_visuel` — n'appelle RIEN. Il construit le brief : reformule la
     demande dans le vocabulaire d'un rendu paysager, propose format et
     résolution, et rend le tout pour relecture. Gratuit, donc rejouable autant
     de fois qu'il faut pour tomber juste.

  2. `generer_visuel` — appelle Higgsfield, et cet appel est FACTURÉ. Il est
     déclaré à effet EXTERNE : il passe par la validation humaine avant de
     partir, comme toute action engageante. Le §9 l'exige, et une génération
     lancée par erreur ne se rembourse pas.

Séparer les deux évite le travers habituel : itérer sur la formulation en
payant chaque essai. On règle le brief gratuitement, on ne paie que le tirage.

CE QUE ÇA NE FAIT PAS. Partir d'une PHOTO du terrain (simulation avant/après,
variantes sur l'existant) n'est pas disponible : la documentation publique de
l'éditeur ne décrit pas le paramètre d'image d'entrée. Le dire plutôt que de
produire un visuel générique en le faisant passer pour une simulation du
chantier réel — c'est précisément le genre de confusion qui se retourne devant
un client.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("symbiose.skills.visuels")

# Consigne de rendu. Le modèle génératif ne connaît pas le métier : sans ces
# repères il produit une image de synthèse quelconque, jolie et inutilisable en
# rendez-vous client.
CADRE_PAYSAGER = (
    "rendu photoréaliste d'aménagement paysager extérieur, lumière naturelle de "
    "fin d'après-midi, végétation d'espèces tempérées cohérentes entre elles, "
    "échelle humaine crédible, matériaux lisibles (bois, pierre, gravier, béton "
    "désactivé), pas de texte, pas de logo, pas de personnage au premier plan"
)

MAX_BRIEF = 1200


async def preparer_visuel(data: dict, user) -> dict:
    """Construit le brief de génération. N'appelle rien, ne coûte rien."""
    from visuels.higgsfield import RATIOS, RESOLUTIONS, disponible

    demande = (data.get("demande") or data.get("description") or "").strip()
    if not demande:
        # Un paramètre manquant est un ÉCHEC de l'appel. Rendu comme un
        # dictionnaire ordinaire, il passait pour un brief réussi.
        from skills.erreurs import SkillError
        raise SkillError("Décris l'aménagement à représenter (lieu, ouvrages, "
                         "matériaux, ambiance) pour que je prépare le brief.")

    contraintes = (data.get("contraintes") or "").strip()
    ratio = (data.get("format") or "16:9").strip()
    resolution = (data.get("resolution") or "720p").strip()

    brief = ", ".join(x for x in (demande, contraintes, CADRE_PAYSAGER) if x)[:MAX_BRIEF]

    return {
        "brief": brief,
        "format": ratio if ratio in RATIOS else "16:9",
        "resolution": resolution if resolution in RESOLUTIONS else "720p",
        "formats_possibles": list(RATIOS),
        "resolutions_possibles": list(RESOLUTIONS),
        "service_configure": await disponible(),
        "note": ("Ce brief n'a RIEN généré et n'a rien coûté. Montre-le, laisse-le "
                 "corriger, puis appelle `generer_visuel` avec ce brief exact. "
                 "La génération, elle, est facturée et demandera une validation."),
    }


async def generer_visuel(data: dict, user) -> dict:
    """Génère le visuel. FACTURÉ — passe par la validation (effet externe)."""
    from visuels.higgsfield import generer, HiggsfieldIndisponible

    brief = (data.get("brief") or data.get("demande") or "").strip()
    if not brief:
        from skills.erreurs import SkillError
        raise SkillError("Aucun brief fourni. Prépare-le d'abord avec "
                         "`preparer_visuel`, c'est gratuit.")

    # Le cadre métier est réappliqué : rien ne garantit que le brief validé soit
    # celui qu'a produit `preparer_visuel` (il a pu être réécrit à la main).
    if CADRE_PAYSAGER[:40] not in brief:
        brief = f"{brief}, {CADRE_PAYSAGER}"

    try:
        resultat = await generer(brief[:MAX_BRIEF],
                                 ratio=data.get("format"),
                                 resolution=data.get("resolution"))
    except HiggsfieldIndisponible as e:
        logger.info("Génération de visuel impossible : %s", e)
        return {"genere": False, "message": str(e)}

    if not resultat.get("termine"):
        return {"genere": False, **resultat}

    return {
        "genere": True,
        "images": resultat["images"],
        "request_id": resultat["request_id"],
        "format": resultat["format"],
        "note": ("Visuel d'ILLUSTRATION, produit à partir d'une description. Ce "
                 "n'est ni un plan, ni une simulation du terrain réel, ni un "
                 "engagement sur ce qui sera réalisé : présente-le comme une "
                 "intention d'aménagement. Donne les liens tels quels."),
    }


# ── Déclarations : tout ce que le système doit savoir, ICI ───────────
# Les deux actions restent volontairement SÉPARÉES : le brief est gratuit et
# rejouable, la génération est facturée et validée. Les réunir reviendrait à
# payer un tirage à chaque reformulation (cf. outils/docs/visuels.md).
from skills.registre import Declaration

SKILLS = {
    "preparer_visuel": Declaration(
        fonction=preparer_visuel,
        description=(
            "PREPARE le brief d'un visuel paysager (rendu d'amenagement) sans "
            "rien generer : gratuit, rejouable autant de fois qu'il faut. "
            "TOUJOURS passer par lui avant `generer_visuel`. demande : ce "
            "qu'il faut representer ; contraintes : materiaux, style, saison ; "
            "format : 16:9, 1:1..."),
        requis=["demande"], optionnels=["contraintes", "format", "resolution"],
        effet="lecture",
        libelle="je prépare le brief du visuel"),
    "generer_visuel": Declaration(
        fonction=generer_visuel,
        description=(
            "GENERE reellement le visuel a partir d'un brief valide. "
            "ATTENTION : cet appel est FACTURE et demande une validation "
            "humaine. Ne l'appelle jamais de ta propre initiative ni pour "
            "iterer sur la formulation - c'est le role de `preparer_visuel`. "
            "Le resultat est une illustration, pas une simulation du terrain "
            "reel"),
        requis=["brief"], optionnels=["format", "resolution"],
        # FACTURE et hors du systeme : effet externe, validation humaine.
        effet="externe",
        libelle="je génère le visuel"),
}
