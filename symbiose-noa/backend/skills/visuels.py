"""
Skill natif : produire un visuel paysager (§6) — le SAVOIR-FAIRE complet.

TROIS TEMPS, ET C'EST VOLONTAIRE.

  0. LES QUESTIONS. Un beau rendu ne sort pas d'une phrase vague. Quand il
     manque l'essentiel, `preparer_visuel` rend les questions COURTES à poser
     — style, éléments, ambiance, point de vue — et le modèle les pose en un
     seul message avant d'aller plus loin. Quatre questions de dix secondes
     économisent trois tirages ratés.

  1. `preparer_visuel` — n'appelle RIEN. Il assemble le GABARIT photoréaliste
     (voir plus bas) à partir des réponses : la description varie, le métier
     de l'image — lumière, optique, matière, échelle — est écrit une fois et
     ne se négocie pas. Gratuit, donc rejouable autant de fois qu'il faut.

  2. `generer_visuel` — appelle Higgsfield, et cet appel est FACTURÉ. Effet
     EXTERNE : validation humaine avant de partir (§9). Après génération, les
     images sont TÉLÉCHARGÉES dans le dépôt local (les adresses du CDN
     expirent, un tirage payé ne se perd pas) et le résultat donne le bloc
     ```ui prêt à insérer : le rendu S'AFFICHE dans le chat, il ne se raconte
     pas.

LE GABARIT EST EN ANGLAIS, LES RÉPONSES AUSSI. Les modèles d'image comprennent
nettement mieux l'anglais ; le catalogue demande au modèle de conversation de
traduire les éléments en anglais simple au moment de remplir. L'utilisateur,
lui, parle français : c'est le modèle qui fait le pont.

CE QUE ÇA NE FAIT PAS. Partir d'une PHOTO du terrain (simulation avant/après
sur l'existant) n'est pas disponible : la documentation publique de l'éditeur
ne décrit pas d'image d'entrée. Le dire, plutôt que faire passer une
illustration pour une simulation du chantier réel.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("symbiose.skills.visuels")

MAX_BRIEF = 1600

# ── LE GABARIT PHOTORÉALISTE ────────────────────────────────────────────────
#
# Tout ce qui fait qu'une image de jardin a l'air d'une PHOTO et non d'un
# rendu de jeu vidéo est ICI, une fois pour toutes : l'optique (grand angle
# modéré, diaphragme de paysage), la lumière (heure dorée par défaut — c'est
# elle qui vend un aménagement), la matière (matériaux physiquement crédibles,
# ombres douces), l'échelle humaine, la cohérence botanique d'un climat
# tempéré français, et les interdits (texte, logo, personnages au premier
# plan, sursaturation). Le modèle ne remplit QUE la description ; il ne
# réinvente jamais le métier de l'image.
GABARIT = (
    "Award-winning professional landscape architecture photograph, ultra realistic. "
    "SCENE: {scene}. "
    "GARDEN FEATURES: {elements}. "
    "PLANTING: {vegetation}. "
    "MATERIALS: {materiaux}. "
    "STYLE: {style} garden design, coherent and lived-in, believable for a real French property. "
    "LIGHT & MOOD: {ambiance}, soft realistic shadows, gentle atmospheric depth. "
    "SEASON: {saison}, temperate French climate, botanically coherent species only. "
    "CAMERA: {point_de_vue}, full-frame camera, 28mm lens at f/8, eye-level unless stated, "
    "sharp focus front to back, natural white balance, high dynamic range, "
    "subtle film-like color grading, photorealistic textures on every material, "
    "physically accurate reflections on water and glass, believable human scale throughout. "
    "Magazine quality, no text, no watermark, no logo, no people in the foreground, "
    "no oversaturated colors, no fantasy elements"
)

# Les valeurs par défaut de chaque trou : un gabarit qui exige tout n'est
# jamais rempli. Ce qui est demandé à l'utilisateur : la scène et les
# éléments. Le reste a un défaut de métier, remplaçable.
DEFAUTS = {
    "vegetation": ("layered planting with ornamental grasses, clipped evergreen shrubs "
                   "and two feature trees"),
    "materiaux": "natural wood, local stone and gravel",
    "style": "contemporary",
    "ambiance": "golden hour late afternoon sunlight",
    "saison": "early summer",
    "point_de_vue": "wide view from the terrace across the whole garden",
}

# ── LES QUESTIONS COURTES ───────────────────────────────────────────────────
# Une par trou important, formulées comme on parle à un client — dix secondes
# chacune. Le modèle les pose en UN message (avec des suggestions cliquables),
# jamais en interrogatoire.
QUESTIONS = {
    "scene": "Quel est le lieu à représenter ? (ex. jardin arrière de 200 m² d'une maison en pierre, entrée de villa, cour de restaurant…)",
    "elements": "Quels aménagements doit-on voir ? (terrasse bois, piscine, massifs, pergola, allée, muret, éclairage…)",
    "style": "Quel style ? (contemporain, méditerranéen, champêtre, japonisant, exotique…)",
    "ambiance": "Quelle ambiance ? (fin d'après-midi doré, matin brumeux, midi d'été, tombée de la nuit avec éclairages…)",
    "point_de_vue": "Vu d'où ? (depuis la terrasse, vue d'ensemble, allée vers la maison, vue plongeante légère…)",
}


def _champ(data: dict, *noms: str) -> str:
    for n in noms:
        v = (data.get(n) or "").strip()
        if v:
            return v
    return ""


async def preparer_visuel(data: dict, user) -> dict:
    """Assemble le gabarit, ou rend les questions à poser. Gratuit."""
    from visuels.higgsfield import RATIOS, RESOLUTIONS, disponible

    scene = _champ(data, "scene", "demande", "description")
    elements = _champ(data, "elements", "amenagements")

    # Ce qui manque d'ESSENTIEL se demande ; le reste a un défaut de métier.
    manquants = []
    if not scene:
        manquants.append("scene")
    if not elements:
        manquants.append("elements")
    if manquants:
        # On joint les questions de confort UNE seule fois, pour que tout se
        # règle en un aller-retour au lieu de trois.
        a_poser = [QUESTIONS[m] for m in manquants]
        for confort in ("style", "ambiance", "point_de_vue"):
            if not _champ(data, confort):
                a_poser.append(QUESTIONS[confort])
        return {
            "pret": False,
            "questions_a_poser": a_poser[:4],
            "note": ("Il manque l'essentiel pour un beau rendu. Pose ces questions "
                     "à l'utilisateur en UN SEUL message court, avec des "
                     "`quick_replies` pour les réponses probables, puis rappelle "
                     "`preparer_visuel` avec les champs remplis EN ANGLAIS simple "
                     "(scene, elements, style, ambiance, point_de_vue…). "
                     "Ne génère RIEN d'ici là."),
        }

    valeurs = {
        "scene": scene,
        "elements": elements,
        "vegetation": _champ(data, "vegetation") or DEFAUTS["vegetation"],
        "materiaux": _champ(data, "materiaux", "materials") or DEFAUTS["materiaux"],
        "style": _champ(data, "style") or DEFAUTS["style"],
        "ambiance": _champ(data, "ambiance", "lumiere") or DEFAUTS["ambiance"],
        "saison": _champ(data, "saison") or DEFAUTS["saison"],
        "point_de_vue": _champ(data, "point_de_vue", "vue") or DEFAUTS["point_de_vue"],
    }
    brief = GABARIT.format(**valeurs)[:MAX_BRIEF]

    ratio = (data.get("format") or "16:9").strip()
    resolution = (data.get("resolution") or "1080p").strip()

    return {
        "pret": True,
        "brief": brief,
        "champs": valeurs,
        "format": ratio if ratio in RATIOS else "16:9",
        "resolution": resolution if resolution in RESOLUTIONS else "1080p",
        "service_configure": await disponible(),
        "note": ("Ce brief n'a RIEN généré et n'a rien coûté. Résume à "
                 "l'utilisateur EN FRANÇAIS ce que l'image montrera (pas le "
                 "brief anglais brut), puis ESSAIE d'abord avec "
                 "`tester_visuel` (rapide, inclus) : montre l'essai, ajuste "
                 "le brief s'il le faut, et ne lance `generer_visuel` "
                 "(Higgsfield, facturé, validé) que pour le tirage final "
                 "retenu."),
    }


async def generer_visuel(data: dict, user) -> dict:
    """Génère le visuel. FACTURÉ — passe par la validation (effet externe)."""
    from visuels.higgsfield import generer, HiggsfieldIndisponible

    brief = (data.get("brief") or data.get("demande") or "").strip()
    if not brief:
        from skills.erreurs import SkillError
        raise SkillError("Aucun brief fourni. Prépare-le d'abord avec "
                         "`preparer_visuel`, c'est gratuit.")

    # Le métier de l'image est réappliqué si le brief a été réécrit à la main
    # sans lui : mieux vaut un doublon de consigne qu'un rendu de jeu vidéo.
    if "photorealistic textures" not in brief:
        brief = (brief + ". Ultra realistic professional landscape photograph, "
                 "photorealistic textures, golden hour light, believable human "
                 "scale, magazine quality, no text, no watermark, no logo, "
                 "no people in the foreground")[:MAX_BRIEF]

    try:
        resultat = await generer(brief[:MAX_BRIEF],
                                 ratio=data.get("format"),
                                 resolution=data.get("resolution"))
    except HiggsfieldIndisponible as e:
        logger.info("Génération de visuel impossible : %s", e)
        return {"genere": False, "message": str(e)}

    if not resultat.get("termine"):
        return {"genere": False, **resultat}

    # LES IMAGES SONT RAPATRIÉES : les adresses du CDN expirent, le dépôt non.
    from visuels.depot import deposer_depuis_url
    images = []
    for url in resultat["images"]:
        cle = await deposer_depuis_url(url)
        images.append({"cle": cle, "url_externe": None if cle else url})

    cles = [i["cle"] for i in images if i["cle"]]
    import json as _json
    bloc = _json.dumps({"type": "visuel",
                        "titre": (data.get("titre") or "Visuel d'aménagement")[:80],
                        "images": [{"cle": c} for c in cles]}, ensure_ascii=False)

    sortie = {
        "genere": True,
        "images": images,
        "request_id": resultat["request_id"],
        "format": resultat["format"],
        "note": ("Visuel d'ILLUSTRATION, produit à partir d'une description — ni un "
                 "plan, ni une simulation du terrain réel : présente-le comme une "
                 "intention d'aménagement."),
    }
    if cles:
        sortie["a_faire"] = ("AFFICHE le rendu : insère dans ta réponse un bloc "
                             "```ui contenant EXACTEMENT ceci : " + bloc +
                             " — l'écran montre les images. Ne colle pas d'adresse "
                             "d'image en texte.")
        # Le chemin POST-VALIDATION est mécanique : aucun modèle n'y repasse
        # pour lire `a_faire`. Ces deux champs sont le contrat que
        # `execute_action_node` restitue tel quel — c'est ce qui fait que le
        # rendu S'AFFICHE aussi quand la génération a attendu un accord.
        sortie["message_final"] = (
            f"Voici le rendu ({len(cles)} image{'s' if len(cles) > 1 else ''}) — "
            "une illustration d'intention d'aménagement, pas une simulation du "
            "terrain réel.")
        sortie["bloc_ui"] = _json.loads(bloc)
    else:
        sortie["a_faire"] = ("Le dépôt local a échoué : donne les adresses "
                             "`url_externe` telles quelles, en prévenant qu'elles "
                             "expirent sous quelques heures.")
        liens = "\n".join(f"- {i['url_externe']}" for i in images if i.get("url_externe"))
        sortie["message_final"] = (
            "Le visuel est généré, mais son dépôt local a échoué. Voici les "
            "adresses directes (elles expirent sous quelques heures) :\n" + liens)
    return sortie


async def tester_visuel(data: dict, user) -> dict:
    """ESSAIE le visuel via Nano Banana (Gemini image). Rapide, inclus dans la
    clé Google — c'est le banc d'essai : on itère ici, et seul le rendu retenu
    part chez Higgsfield pour le tirage final."""
    from visuels.nano_banana import generer, NanoBananaIndisponible

    brief = (data.get("brief") or data.get("demande") or "").strip()
    if not brief:
        from skills.erreurs import SkillError
        raise SkillError("Aucun brief fourni. Prépare-le d'abord avec "
                         "`preparer_visuel`, c'est gratuit.")
    if "photorealistic textures" not in brief:
        brief = (brief + ". Ultra realistic professional landscape photograph, "
                 "photorealistic textures, golden hour light, believable human "
                 "scale, magazine quality, no text, no watermark, no logo, "
                 "no people in the foreground")[:MAX_BRIEF]

    try:
        resultat = await generer(brief[:MAX_BRIEF], ratio=data.get("format"))
    except NanoBananaIndisponible as e:
        logger.info("Essai de visuel impossible : %s", e)
        return {"genere": False, "message": str(e)}

    from visuels.depot import deposer_octets
    cles = [c for octets, mime in resultat["images"]
            if (c := deposer_octets(octets, mime))]
    if not cles:
        return {"genere": False,
                "message": "L'image a été rendue mais son dépôt a échoué : réessayez."}

    import json as _json
    bloc = {"type": "visuel",
            "titre": (data.get("titre") or "Essai de visuel")[:80],
            "images": [{"cle": c} for c in cles]}
    return {
        "genere": True,
        "essai": True,
        "modele": resultat["modele"],
        "note": ("ESSAI rapide (Nano Banana), pour régler le brief. Le tirage "
                 "final, plus abouti, se fait avec `generer_visuel` (Higgsfield, "
                 "facturé, validé)."),
        "a_faire": ("AFFICHE l'essai : insère dans ta réponse un bloc ```ui "
                    "contenant EXACTEMENT ceci : " + _json.dumps(bloc, ensure_ascii=False)
                    + " — puis propose d'ajuster le brief ou de lancer le tirage "
                    "final Higgsfield."),
        "message_final": "Voici l'essai de visuel — dites-moi ce qu'on ajuste, "
                         "ou si on lance le tirage final.",
        "bloc_ui": bloc,
    }


# ── Déclarations : tout ce que le système doit savoir, ICI ───────────
from skills.registre import Declaration

SKILLS = {
    "preparer_visuel": Declaration(
        fonction=preparer_visuel,
        description=(
            "PREPARE un visuel paysager photorealiste (rendu d'amenagement) sans "
            "rien generer : gratuit, rejouable. TOUJOURS l'appeler AVANT "
            "`generer_visuel`. S'il rend `questions_a_poser`, pose-les en UN "
            "message court avec des quick_replies, puis rappelle-le. Champs (EN "
            "ANGLAIS simple) : scene (lieu), elements (amenagements a voir), et "
            "en option vegetation, materiaux, style, ambiance, saison, "
            "point_de_vue, format (16:9, 1:1...), resolution (720p, 1080p). Le "
            "gabarit photo (lumiere, optique, realisme) est ajoute tout seul"),
        requis=[], optionnels=["scene", "elements", "vegetation", "materiaux",
                               "style", "ambiance", "saison", "point_de_vue",
                               "format", "resolution", "demande"],
        effet="lecture",
        libelle="je prépare le brief du visuel"),
    "tester_visuel": Declaration(
        fonction=tester_visuel,
        description=(
            "ESSAIE le visuel en quelques secondes via Nano Banana (Gemini "
            "image, inclus dans la cle Google, quota journalier) a partir du "
            "brief de `preparer_visuel`. C'est le BANC D'ESSAI : itere ici "
            "autant qu'il faut, montre chaque essai, ajuste le brief avec "
            "l'utilisateur, et ne passe a `generer_visuel` (Higgsfield, "
            "facture) que pour le tirage final retenu. Le resultat donne un "
            "bloc ```ui a inserer TEL QUEL pour AFFICHER l'essai"),
        requis=["brief"], optionnels=["format", "titre"],
        # Inclus dans la cle deja en place, pas de facture a l'acte : l'essai
        # s'itere librement, seul le tirage final passe par la validation.
        effet="lecture",
        libelle="j'essaie le visuel (Nano Banana)"),
    "generer_visuel": Declaration(
        fonction=generer_visuel,
        description=(
            "GENERE le TIRAGE FINAL du visuel via Higgsfield a partir du brief "
            "de `preparer_visuel`. FACTURE, validation humaine obligatoire : "
            "jamais de ta propre initiative, jamais pour iterer — c'est le "
            "role de `tester_visuel`. Le resultat donne un bloc ```ui a "
            "inserer TEL QUEL pour AFFICHER le rendu dans le chat. `titre` : "
            "nom court du projet pour la legende"),
        requis=["brief"], optionnels=["format", "resolution", "titre"],
        # FACTURE et hors du systeme : effet externe, validation humaine.
        effet="externe",
        libelle="je génère le visuel"),
}
