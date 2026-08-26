"""
Skill natif : produire un visuel paysager (§6) — le SAVOIR-FAIRE complet.

UN SEUL MOTEUR DEPUIS LE 22/08/2026 : Nano Banana (API Google directe).
Higgsfield a été retiré — deux fournisseurs pour une même chose, c'était deux
jeux d'identifiants, deux formats de réponse, deux pannes possibles, et un
tirage final qu'on n'a jamais réussi à payer.

QUATRE GESTES.

  0. LES QUESTIONS. Un beau rendu ne sort pas d'une phrase vague. Quand il
     manque l'essentiel, `preparer_visuel` rend les questions COURTES à poser
     — style, éléments, ambiance, point de vue — et le modèle les pose en un
     seul message avant d'aller plus loin. Quatre questions de dix secondes
     économisent trois tirages ratés.

  1. `preparer_visuel` — n'appelle RIEN. Il assemble le GABARIT photoréaliste
     à partir des réponses : la description varie, le métier de l'image —
     lumière, optique, matière, échelle — est écrit une fois et ne se négocie
     pas. Gratuit, donc rejouable autant de fois qu'il faut.

  2. `tester_visuel` — l'ESSAI. Modèle rapide, replis autorisés : on itère,
     on montre, on ajuste. Effet lecture.

  3. `generer_visuel` — le TIRAGE FINAL. Nano Banana Pro EXIGÉ, sans repli, et
     le brief reçoit en plus les consignes de finition. Effet externe : un
     rendu qu'on montrera au client passe par un accord humain.

  4. `modifier_visuel` — LA RETOUCHE, et c'est le geste qui manquait. On donne
     une PHOTO EXISTANTE (celle du terrain, ou un rendu déjà produit) et la
     liste de ce qu'on veut changer : le modèle reçoit l'image elle-même dans
     la requête, pas une description d'elle. C'est la seule façon de retrouver
     LA MÊME maison. Le PRÉRÉGLAGE DE FIDÉLITÉ (plus bas) fait le reste : tout
     ce qui n'est pas explicitement demandé doit rester identique.

CE QUE ÇA NE FAIT TOUJOURS PAS : une image reste une ILLUSTRATION d'intention.
Même en partant d'une photo du terrain, ce n'est ni un plan, ni une simulation
d'exécution — et le texte rendu au chat le dit à chaque fois.

LE GABARIT EST EN ANGLAIS, LES RÉPONSES AUSSI. Les modèles d'image comprennent
nettement mieux l'anglais ; le catalogue demande au modèle de conversation de
traduire les éléments en anglais simple au moment de remplir. L'utilisateur,
lui, parle français : c'est le modèle qui fait le pont.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("symbiose.skills.visuels")

MAX_BRIEF = 1600
# Ce que l'utilisateur demande de changer, plafonné SEUL : les consignes fixes
# qui l'entourent ne sont jamais rognées (voir PRESET_FIDELITE).
MAX_CHANGEMENTS = 700

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

# ── LE PRÉRÉGLAGE DE FIDÉLITÉ — pour RETOUCHER une photo existante ──────────
#
# Le piège d'une retouche par IA, c'est qu'elle REFAIT l'image au lieu de la
# modifier : même sujet, mais une autre maison, un autre angle, une autre
# lumière. Le client ne reconnaît plus son terrain, et le rendu ne prouve plus
# rien. Tout ce préréglage sert donc à UNE chose : nommer explicitement, une
# par une, les choses qui NE DOIVENT PAS bouger.
#
# Pourquoi les énumérer plutôt qu'écrire « garde tout le reste identique » :
# une consigne générale se dilue, une liste tient. Géométrie du bâti, ligne de
# toiture, position des ouvertures, matériaux et teintes de façade, bâtiments
# voisins, ligne d'horizon, position et focale de la caméra, heure, direction
# et dureté des ombres, météo — chacune a été vue dériver au moins une fois.
#
# L'ordre importe aussi : l'identité D'ABORD, les changements ENSUITE, la
# qualité en dernier. Ce qui vient en tête d'une consigne pèse plus lourd, et
# ce qu'on veut ici c'est la même maison avant d'être une belle image.
PRESET_FIDELITE = (
    "Photorealistic architectural edit of the SUPPLIED photograph. "

    "ABSOLUTE PRIORITY — PRESERVE THE IDENTITY OF THE SOURCE IMAGE: keep the exact same "
    "building, the same architectural geometry and proportions, the same roofline and roof "
    "material, the same position, size and shape of every window, door and shutter, the same "
    "facade materials, textures and colours, the same neighbouring buildings and boundaries, "
    "the same terrain relief and horizon line, the same existing trees unless listed below. "
    "Keep the exact same camera position, focal length, perspective and vanishing points, the "
    "same framing and crop, the same time of day, the same light direction, the same shadow "
    "length and softness, the same weather and sky. "

    "CHANGE ONLY WHAT IS LISTED HERE: {changements}. "

    "Everything not listed must remain faithful to the source photograph, pixel for pixel where "
    "possible. Do not re-imagine the scene, do not re-frame it, do not re-light it, do not "
    "restyle the building, do not tidy up or remove clutter, do not add people, vehicles, "
    "furniture, signage or decorative elements that were not requested. "

    "INTEGRATION: the new elements must be physically plausible in this exact scene — correct "
    "ground contact, correct scale against the building and any visible door or window, cast "
    "shadows consistent with the existing light direction and length, coherent reflections, "
    "materials that age and weather like the real thing, planting that suits a temperate French "
    "climate and the season visible in the photograph. "

    "QUALITY: professional landscape architecture photography, ultra realistic, sharp focus, "
    "natural white balance, high dynamic range, photorealistic textures on every material, "
    "magazine quality. "

    "FORBIDDEN: text, watermark, logo, borders, collage, before/after split, oversaturated "
    "colours, cartoon or CGI look, fantasy elements"
)

# Ce qui s'ajoute au brief du TIRAGE FINAL seulement. L'essai n'en a pas
# besoin : on y règle la composition, pas la finition.
FINITION = (
    ". Final client-facing render: maximum detail, {resolution} level of detail, immaculate "
    "material rendering, refined composition, perfectly natural light, no artefacts, no "
    "duplicated or malformed elements, no distorted straight lines on architecture"
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


# LA SAISON SE DÉDUIT DE CE QU'ON DIT. Relevé le 22/08 : « en plein hiver avec
# une légère neige » — et l'image est sortie sans neige. Le modèle avait mis
# l'hiver dans la scène mais pas dans `saison`, et le gabarit a rempli le trou
# avec son défaut : « early summer ». Deux saisons dans un même brief, la plus
# affirmative gagne. On lit donc TOUS les champs ET la demande brute : le mot
# qui dit la saison est quelque part, il suffit de le prendre.
_SAISONS = (
    (("neige", "snow", "enneig", "snowy", "hiver", "winter", "hivernal", "gel", "frost"),
     "deep winter, light snow covering the ground, plants and surfaces, cold clear light"),
    (("automne", "autumn", "fall foliage", "feuilles mortes"),
     "autumn, warm foliage, fallen leaves"),
    (("printemps", "spring", "floraison", "blossom"),
     "spring, fresh green growth and first blossoms"),
    (("été", "ete", "summer", "canicule", "plein soleil"),
     "high summer, lush planting"),
)


def _saison_deduite(*textes) -> str:
    corpus = " ".join(str(x or "") for x in textes).lower()
    for mots, saison in _SAISONS:
        if any(m in corpus for m in mots):
            return saison
    return ""


def _brief_client(demande: str) -> str:
    """La demande du client, telle quelle, en fin de brief : l'autorité.

    Le modèle de conversation traduit et redécoupe la demande en champs, et il
    en perd en route (la neige, la couleur des poteaux). Les modèles d'image
    lisent le français : on leur donne AUSSI les mots du client, en leur disant
    que c'est ce qui fait foi. Borné : c'est un rappel, pas un second gabarit.
    """
    d = " ".join(str(demande or "").split())[:500]
    return f" CLIENT BRIEF (authoritative, in the client's own words, French): \"{d}\"." if d else ""


def _champ(data: dict, *noms: str) -> str:
    for n in noms:
        v = (data.get(n) or "").strip()
        if v:
            return v
    return ""


async def preparer_visuel(data: dict, user) -> dict:
    """Assemble le gabarit, ou rend les questions à poser. Gratuit."""
    from visuels.nano_banana import RATIOS, RESOLUTIONS, disponible

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

    demande_brute = _champ(data, "demande", "description", "requete")
    saison = _champ(data, "saison") or _saison_deduite(
        scene, elements, _champ(data, "ambiance", "lumiere"), demande_brute) or DEFAUTS["saison"]
    ambiance = _champ(data, "ambiance", "lumiere")
    # Une ambiance « heure dorée » par défaut sous la neige fait une image
    # d'été enneigée : quand la saison est l'hiver et que personne n'a demandé
    # de lumière, on prend une lumière d'hiver.
    if not ambiance:
        ambiance = ("soft overcast winter light, cool tones" if "winter" in saison
                    else DEFAUTS["ambiance"])
    valeurs = {
        "scene": scene,
        "elements": elements,
        "vegetation": _champ(data, "vegetation") or DEFAUTS["vegetation"],
        "materiaux": _champ(data, "materiaux", "materials") or DEFAUTS["materiaux"],
        "style": _champ(data, "style") or DEFAUTS["style"],
        "ambiance": ambiance,
        "saison": saison,
        "point_de_vue": _champ(data, "point_de_vue", "vue") or DEFAUTS["point_de_vue"],
    }
    brief = (GABARIT.format(**valeurs) + _brief_client(demande_brute))[:MAX_BRIEF + 600]

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
                 "`tester_visuel` : montre l'essai, ajuste le brief s'il le "
                 "faut, et ne lance `generer_visuel` (tirage final, validé) "
                 "que pour le rendu retenu. Si l'utilisateur veut partir "
                 "d'une PHOTO existante plutôt que d'une description, ce "
                 "n'est pas ce skill : c'est `modifier_visuel`."),
    }


def _rendu(resultat: dict, titre: str, *, essai: bool, avant: str = "") -> dict:
    """Dépose les images et fabrique le bloc ```ui. Commun aux trois gestes.

    Le dépôt local n'est pas une commodité : l'image ne vit QUE dans la
    réponse de l'API, en base64. Si on ne la range pas ici, elle n'existe plus
    après le tour — et une retouche ultérieure n'aurait plus de source.
    """
    import json as _json
    from visuels.depot import deposer_octets

    cles = [c for octets, mime in resultat["images"]
            if (c := deposer_octets(octets, mime))]
    if not cles:
        return {"genere": False,
                "message": "L'image a été rendue mais son dépôt a échoué : réessayez."}

    # L'AVANT ET L'APRÈS, DANS LA MÊME PLANCHE.
    #
    # Une retouche ne se juge pas seule : « voilà ce que ça donnerait » n'a de
    # sens qu'à côté de la photo d'origine, et c'est mot pour mot ce qu'un
    # client demande (« une simulation avant/après »). Les deux images sont
    # déjà au dépôt — la source y a été rangée en arrivant — donc le montrer ne
    # coûte ni un appel, ni un octet de plus : seulement de le dire ici.
    #
    # Les légendes ne sont posées QUE dans ce cas : sur un essai ou un tirage
    # simple, une légende « Après » ne voudrait rien dire.
    if avant and avant not in cles:
        images = ([{"cle": avant, "legende": "Avant (photo d'origine)"}]
                  + [{"cle": c, "legende": "Après (projet)"} for c in cles])
    else:
        images = [{"cle": c} for c in cles]
    bloc = {"type": "visuel",
            "titre": (titre or ("Essai de visuel" if essai else "Visuel d'aménagement"))[:80],
            "images": images}
    # LE NOM DU MODÈLE NE SORT PAS. Il était rendu ici, donc visible du modèle
    # de conversation, qui l'a recopié dans ses textes (« via nano-banana-pro… »).
    # C'est un détail d'infrastructure : il va dans le journal, pas à l'écran.
    logger.info("Visuel rendu par %s (%s)", resultat.get("modele"), "essai" if essai else "final")
    return {
        "genere": True,
        "essai": essai,
        "cles": cles,
        # La clé est DITE au modèle pour qu'il puisse la repasser à
        # `modifier_visuel` : « celle-là, mais avec un olivier » est la
        # demande suivante une fois sur deux, et sans la clé elle repartirait
        # d'une génération neuve — donc d'un autre jardin.
        # En minuscules et sans mot-titre : « Référence de cette image » s'est
        # fait masquer en « [LOC_21] de cette image » par l'anonymiseur (relevé
        # dans les traces) — la clé, elle, est passée. On écrit court et plat.
        "a_savoir": ("cle_image=" + ", ".join(cles) + " — pour la retoucher (changer un "
                     "detail en gardant tout le reste identique), appelle `modifier_visuel` "
                     "avec `image` = cette cle, jamais une nouvelle generation."),
        "bloc_ui": bloc,
        "a_faire": ("AFFICHE le rendu : insère dans ta réponse un bloc ```ui contenant "
                    "EXACTEMENT ceci : " + _json.dumps(bloc, ensure_ascii=False)
                    + " — l'écran montre les images. Ne colle pas d'adresse d'image en texte."),
    }


def _avec_metier(brief: str) -> str:
    """Réapplique le métier de l'image si le brief a été réécrit à la main sans
    lui : mieux vaut un doublon de consigne qu'un rendu de jeu vidéo."""
    if "photorealistic textures" in brief:
        return brief[:MAX_BRIEF]
    return (brief + ". Ultra realistic professional landscape photograph, "
            "photorealistic textures, golden hour light, believable human "
            "scale, magazine quality, no text, no watermark, no logo, "
            "no people in the foreground")[:MAX_BRIEF]


async def generer_visuel(data: dict, user) -> dict:
    """TIRAGE FINAL — Nano Banana Pro exigé. Effet externe : accord humain."""
    from visuels.nano_banana import generer, NanoBananaIndisponible, RESOLUTIONS

    brief = (data.get("brief") or data.get("demande") or "").strip()
    if not brief:
        from skills.erreurs import SkillError
        raise SkillError("Aucun brief fourni. Prépare-le d'abord avec "
                         "`preparer_visuel`, c'est gratuit.")

    resolution = (data.get("resolution") or "4k").strip().lower()
    if resolution not in RESOLUTIONS:
        resolution = "4k"
    # `_avec_metier` plafonne déjà le brief ; la finition s'ajoute APRÈS, pour
    # ne pas être la première chose que la troncature emporte.
    brief = _avec_metier(brief) + FINITION.format(resolution=resolution)

    try:
        resultat = await generer(brief, ratio=data.get("format"), qualite="finale")
    except NanoBananaIndisponible as e:
        logger.info("Tirage final impossible : %s", e)
        return {"genere": False, "message": str(e),
                "a_savoir": ("Explique la situation et ARRÊTE-TOI : ne relance pas ce "
                             "skill dans ce tour. Ce refus ne vaut QUE pour ce tour — "
                             "si l'utilisateur redemande plus tard, réessaie.")}

    sortie = _rendu(resultat, data.get("titre") or "Visuel d'aménagement", essai=False)
    if not sortie.get("genere"):
        return sortie
    sortie["note"] = ("Visuel d'ILLUSTRATION, produit à partir d'une description — ni un "
                      "plan, ni une simulation du terrain réel : présente-le comme une "
                      "intention d'aménagement.")
    # Le chemin POST-VALIDATION est mécanique : aucun modèle n'y repasse pour
    # lire `a_faire`. `message_final` et `bloc_ui` sont le contrat que
    # `execute_action_node` restitue tel quel — c'est ce qui fait que le rendu
    # S'AFFICHE aussi quand la génération a attendu un accord.
    n = len(sortie["cles"])
    sortie["message_final"] = (
        f"Voici le rendu final ({n} image{'s' if n > 1 else ''}) — une illustration "
        "d'intention d'aménagement, pas une simulation du terrain réel.")
    return sortie


async def modifier_visuel(data: dict, user) -> dict:
    """RETOUCHE une image existante : la même scène, quelques détails changés.

    La différence avec une génération n'est pas de degré : ici le modèle reçoit
    l'IMAGE ELLE-MÊME, pas une description d'elle. C'est ce qui fait qu'on
    retrouve la même maison au lieu d'une maison qui lui ressemble.
    """
    from skills.erreurs import SkillError
    from visuels.depot import lire
    from visuels.nano_banana import generer, NanoBananaIndisponible

    reference = (data.get("image") or data.get("reference") or data.get("cle") or "").strip()
    if not reference:
        raise SkillError(
            "Aucune image de départ. `modifier_visuel` retouche une image qui "
            "EXISTE : donne la référence d'une photo envoyée par l'utilisateur "
            "ou d'un visuel déjà produit (elle est rappelée dans le résultat du "
            "geste précédent). Pour créer une image à partir de rien, c'est "
            "`preparer_visuel` puis `tester_visuel`.")

    source = lire(reference)
    if not source:
        raise SkillError(
            f"L'image « {reference[:16]} » est introuvable dans le dépôt. Demande à "
            "l'utilisateur de renvoyer la photo, ou repars du dernier visuel produit.")

    changements = data.get("changements") or data.get("modifications") or data.get("demande")
    if isinstance(changements, (list, tuple)):
        changements = "; ".join(str(c).strip() for c in changements if str(c).strip())
    changements = (changements or "").strip()
    if not changements:
        raise SkillError(
            "Il manque ce qu'il faut changer. Demande-le à l'utilisateur, puis "
            "rappelle `modifier_visuel` avec `changements` EN ANGLAIS simple "
            "(ex. « replace the lawn with an ipe wood deck; add a low stone wall "
            "along the left boundary »).")

    prompt = PRESET_FIDELITE.format(changements=changements[:MAX_CHANGEMENTS])
    octets, mime = source

    try:
        resultat = await generer(prompt, images_entree=[(octets, mime)],
                                 qualite=(data.get("qualite") or "finale"))
    except NanoBananaIndisponible as e:
        logger.info("Retouche impossible : %s", e)
        return {"genere": False, "message": str(e),
                "a_savoir": ("Explique la situation et ARRÊTE-TOI : ne relance pas ce "
                             "skill dans ce tour. Ce refus ne vaut QUE pour ce tour.")}

    sortie = _rendu(resultat, data.get("titre") or "Avant / après",
                    essai=False, avant=reference)
    if not sortie.get("genere"):
        return sortie
    sortie["source"] = reference
    sortie["changements"] = changements
    sortie["note"] = ("Retouche de l'image fournie : seuls les points demandés ont été "
                      "modifiés, le reste de la scène est conservé. Cela reste une "
                      "ILLUSTRATION d'intention — ni un plan, ni une garantie de rendu "
                      "après travaux.")
    sortie["message_final"] = (
        "Voici l'avant / après : la même scène, avec " + changements[:160] +
        ". C'est une illustration d'intention, pas une simulation du chantier réel — "
        "dites-moi ce qu'on ajuste.")
    return sortie


async def tester_visuel(data: dict, user) -> dict:
    """ESSAI rapide : modèle rapide, replis autorisés, on itère librement."""
    from visuels.nano_banana import generer, NanoBananaIndisponible

    brief = (data.get("brief") or data.get("demande") or "").strip()
    if not brief:
        from skills.erreurs import SkillError
        raise SkillError("Aucun brief fourni. Prépare-le d'abord avec "
                         "`preparer_visuel`, c'est gratuit.")

    try:
        resultat = await generer(_avec_metier(brief), ratio=data.get("format"),
                                 qualite="essai")
    except NanoBananaIndisponible as e:
        logger.info("Essai de visuel impossible : %s", e)
        return {"genere": False, "message": str(e),
                # La consigne d'ARRÊT, pour le modèle : sans elle, il a rappelé
                # ce skill quarante fois dans un même tour en variant le brief.
                "a_savoir": ("NE RAPPELLE PLUS `tester_visuel` dans CE tour-ci : le "
                             "quota ne reviendra pas dans la minute, et changer "
                             "le brief n'y change rien. Explique la situation à "
                             "l'utilisateur avec le message ci-dessus et "
                             "ARRÊTE-TOI là. Ce refus ne vaut QUE pour ce tour : "
                             "si l'utilisateur redemande plus tard, réessaie — "
                             "la facturation peut avoir été activée entre-temps.")}

    sortie = _rendu(resultat, data.get("titre") or "Essai de visuel", essai=True)
    if not sortie.get("genere"):
        return sortie
    sortie["note"] = ("ESSAI rapide, pour régler le brief. Le tirage final, plus "
                      "abouti, se fait avec `generer_visuel`.")
    sortie["message_final"] = ("Voici l'essai de visuel — dites-moi ce qu'on ajuste, "
                               "ou si on lance le tirage final.")
    return sortie


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
            "point_de_vue, format (16:9, 1:1...), resolution (720p, 1080p). "
            "TOUJOURS passer `demande` = la phrase exacte de l'utilisateur (en "
            "francais) : elle entre dans le brief comme reference, rien de ce "
            "qu'il a dit ne doit se perdre (neige, couleur, saison). Le gabarit "
            "photo (lumiere, optique, realisme) est ajoute tout seul"),
        requis=[], optionnels=["scene", "elements", "vegetation", "materiaux",
                               "style", "ambiance", "saison", "point_de_vue",
                               "format", "resolution", "demande"],
        # `demande` : TOUJOURS y recopier la phrase de l'utilisateur telle
        # quelle (en français) — elle entre dans le brief comme référence.
        effet="lecture",
        # Les visuels s'exécutent dans le graphe d'agent1 (agent2 n'appelle
        # aucun skill), mais c'est un travail de CONCEPTION : le tableau de
        # bord et l'historique doivent le porter à l'« Expert plans & visuels ».
        expert="agent2",
        libelle="je prépare le brief du visuel"),
    "tester_visuel": Declaration(
        fonction=tester_visuel,
        description=(
            "ESSAIE le visuel en quelques secondes a partir du brief de "
            "`preparer_visuel`. C'est le BANC D'ESSAI : itere ici "
            "autant qu'il faut, montre chaque essai, ajuste le brief avec "
            "l'utilisateur, et ne passe a `generer_visuel` (tirage final, "
            "valide) que pour le rendu retenu. Le resultat donne un "
            "bloc ```ui a inserer TEL QUEL pour AFFICHER l'essai. Un echec "
            "de quota d'un tour PRECEDENT ne vaut plus rien : quand "
            "l'utilisateur redemande un essai, APPELLE ce skill au lieu de "
            "repondre de memoire — c'est lui qui sait si le quota est revenu, "
            "pas l'historique de la conversation"),
        requis=["brief"], optionnels=["format", "titre"],
        # L'essai s'itere librement ; seul le tirage final passe par un accord.
        effet="lecture",
        expert="agent2",
        libelle="j'essaie le visuel"),
    "modifier_visuel": Declaration(
        fonction=modifier_visuel,
        description=(
            "RETOUCHE une image QUI EXISTE DEJA en gardant tout le reste "
            "IDENTIQUE : meme maison, meme angle, meme lumiere, seuls les "
            "points demandes changent. C'est LE skill a appeler quand "
            "l'utilisateur a envoye une photo, ou qu'un visuel vient d'etre "
            "produit, et demande d'y changer quelque chose — surtout PAS une "
            "nouvelle generation, qui rendrait une AUTRE maison. `image` : la "
            "reference rappelee par le geste precedent ou par l'analyse de la "
            "photo jointe. `changements` : ce qu'il faut changer, EN ANGLAIS "
            "simple, liste courte separee par des points-virgules (ex. "
            "« replace the lawn with an ipe wood deck; add three olive trees "
            "on the right »). Ne demande QUE ce que l'utilisateur a demande : "
            "tout le reste doit rester tel quel. Le resultat donne un bloc "
            "```ui a inserer TEL QUEL pour AFFICHER la variante"),
        requis=["image", "changements"], optionnels=["titre", "qualite"],
        # Un rendu qu'on montrera au client : meme porte que le tirage final.
        effet="externe",
        expert="agent2",
        libelle="je retouche l'image"),
    "generer_visuel": Declaration(
        fonction=generer_visuel,
        description=(
            "GENERE le TIRAGE FINAL du visuel a partir du brief de "
            "`preparer_visuel` : le meilleur moteur exige, sans repli, avec les "
            "consignes de finition. Validation humaine obligatoire : jamais de "
            "ta propre initiative, jamais pour iterer — c'est le role de "
            "`tester_visuel`. Pour retoucher une image EXISTANTE, ce n'est pas "
            "ce skill mais `modifier_visuel`. Le resultat donne un bloc ```ui a "
            "inserer TEL QUEL pour AFFICHER le rendu dans le chat. `titre` : "
            "nom court du projet pour la legende"),
        requis=["brief"], optionnels=["format", "resolution", "titre"],
        # Le rendu montre au client : effet externe, validation humaine.
        effet="externe",
        expert="agent2",
        libelle="je génère le visuel"),
}
