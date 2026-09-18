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


def _perimetres(user):
    """Les dossiers du Drive que CE rôle a le droit de voir.

    Composer n'ouvre aucun droit : le périmètre est recalculé à chaque appel,
    à partir du rôle réel, jamais passé par le modèle.
    """
    from outils.drive import perimetres_visibles
    return perimetres_visibles(getattr(user, "role", None))


def _identite(user) -> str:
    """Le compte Google au nom duquel agir sur le Drive.

    L'identifiant APPLICATIF de la session, jamais une valeur venue du modèle :
    le jeton Google d'une personne ne doit pouvoir être réclamé que par sa
    propre session. Composer deux gestes ne compose pas les droits — même règle
    que `_perimetres`.

    LE SUPER-ADMIN FAIT EXCEPTION, et c'est une décision de Noa (01/09) : « sauf
    super admin, où c'est connecté avec Benjamin Durou, ça ne bouge pas ». Le
    compte de service reste SA vue — c'est aussi celle dont vivent l'ingestion
    et l'enrichissement, qui classent les documents pour toute l'entreprise.
    Tous les autres, Benjamin compris en tant qu'utilisateur ordinaire, voient
    le Drive avec LEUR propre compte, et rien d'autre.

    LES DEUX FILTRES SE COMPOSENT : le jeton personnel borne par ce que Google
    laisse voir à cette personne, les périmètres bornent par ce que l'entreprise
    a déclaré pour ce rôle. Retirer l'un parce que l'autre existe rouvrirait
    tout ce qui n'a jamais été classé.
    """
    if str(getattr(user, "role", "") or "") == "super_admin":
        return ""
    return str(getattr(user, "id", "") or "")


# UNE RECHERCHE NE SE BLOQUE PAS EN TEMPS (règle du 01/09). Le délai posé le 17/09
# au matin — 45 s, contre un Google muet — était plus court que le travail NORMAL :
# « entretien » porte des centaines de fichiers à replacer dans 12 150 dossiers, la
# recherche a été déclarée en échec, le modèle l'a redemandée, et le tour s'est
# fermé sur « a échoué et redonnerait le même résultat ». Ce garde ne vise que le
# service qui ne répond PLUS : il se compte en minutes.
DELAI_RECHERCHE_DRIVE_S = 300


async def _drive(fonction, *args, **kwargs):
    """Appelle un geste Drive et rend un échec comme un ÉCHEC.

    `DriveRefuse` porte des messages écrits POUR le modèle — « ce n'est pas un
    Drive vide, dis-le tel quel ». Les laisser passer en clair est le seul moyen
    qu'il ne transforme pas un refus de périmètre en « le Drive est vide ».
    """
    from outils.drive import DriveRefuse
    try:
        return await fonction(*args, **kwargs)
    except DriveRefuse as e:
        _echec(str(e))
    except Exception as e:  # noqa: BLE001
        _echec(str(getattr(e, "detail", None) or e))


# ── Google Drive ─────────────────────────────────────────────────────

async def drive_apercu(data: dict, user) -> dict:
    """Compte et classe le contenu d'un dossier du Drive, sans lister le détail.

    Le résumé s'affiche en blocs MÉCANIQUES (fiche + noms des sous-dossiers) :
    relevé le 01/09, laissé au modèle, l'aperçu devenait une carte de document
    inventée aux lignes vides.
    """
    from outils.drive import apercu
    from skills.affichage import garantir_apercu
    dossier = (data.get("dossier") or "").strip()
    resultat = await _drive(apercu, dossier or None, perimetres=_perimetres(user),
                            identite=_identite(user))
    return garantir_apercu(resultat, f"« {dossier} »" if dossier else "le Drive")


async def drive_lister(data: dict, user) -> dict:
    """Le contenu d'un dossier du Drive, NOMMÉ : fichiers et sous-dossiers.

    Le pendant du `nas_lister` du jumeau (08/09 soir) : l'aperçu compte, ce
    geste nomme — et le tableau mécanique dit d'enchaîner l'ouverture quand
    c'est ce que la demande réclame.
    """
    from outils.drive import lister
    from skills.affichage import garantir_listage
    dossier = (data.get("dossier") or data.get("chemin") or data.get("nom") or "").strip()
    if not dossier:
        _echec("Donne le `dossier` (nom ou chemin) à lister.")
    resultat = await _drive(lister, dossier, perimetres=_perimetres(user),
                            identite=_identite(user), page=data.get("page") or 1,
                            tri=data.get("tri"))
    return garantir_listage(resultat, dossier, ouvreur="drive_ouvrir")



# Un inventaire détaillé à l'écran : au-delà, le tableau dit où il s'arrête.
MAX_LIGNES_INVENTAIRE_LOT = 2000


async def drive_lister_lot(data: dict, user) -> dict:
    """Liste plusieurs dossiers du Drive en parallèle, en une seule action."""
    from outils.drive import lister_lot
    dossiers = data.get("dossiers")
    if isinstance(dossiers, str):
        dossiers = [x.strip() for x in dossiers.replace("\n", ",").split(",") if x.strip()]
    elif not isinstance(dossiers, list):
        dossier = (data.get("dossier") or data.get("chemin") or "").strip()
        dossiers = [dossier] if dossier else []
    dossiers = [str(x).strip() for x in dossiers if str(x).strip()]
    if not dossiers:
        _echec("Donne la liste des dossiers à inspecter dans dossiers.")
    resultat = await _drive(
        lister_lot, dossiers,
        perimetres=_perimetres(user),
        identite=_identite(user),
        motif=(data.get("motif") or "").strip() or None,
    )
    lots = resultat.get("lots") or []
    rows = []
    for lot in lots:
        if not lot.get("ok"):
            rows.append([lot.get("dossier") or "?", "Erreur", "", lot.get("erreur") or ""])
            continue
        noms = [str(e.get("nom") or "?") for e in (lot.get("entrees") or [])]
        suffixe = " …" if lot.get("tronque") else ""
        rows.append([
            lot.get("dossier") or "?",
            int(lot.get("sous_dossiers") or 0),
            int(lot.get("fichiers") or 0),
            ", ".join(noms[:30]) + suffixe,
        ])
    resultat["bloc_ui"] = {
        "type": "table",
        "titre": "Inspection des dossiers du Drive",
        "columns": ["Dossier", "Sous-dossiers", "Fichiers", "Entrées"],
        "rows": rows,
    }
    # L'INVENTAIRE LIGNE À LIGNE (18/09, recette pilotée, prompt 10). « Liste tout le contenu :
    # nom exact, type, date, taille, sous-dossier d'appartenance, trié par date » : ce geste ne
    # rendait qu'une ligne PAR DOSSIER, avec ses trente premiers noms à la suite. `detail: true`
    # ajoute le tableau d'une ligne par élément — assemblé ici, le modèle n'a rien à recopier.
    veut_detail = str(data.get("detail") or data.get("inventaire") or "").strip().lower() in ("true", "1", "oui", "yes")
    if veut_detail:
        from skills.affichage import _jour, octets_lisibles
        elements = [(str(lot.get("dossier") or "?"), e) for lot in lots if lot.get("ok")
                    for e in (lot.get("entrees") or []) if isinstance(e, dict)]
        if str(data.get("tri") or "").strip().lower() in ("date", "recent", "récent", "modifie", "modifié"):
            elements.sort(key=lambda de: str(de[1].get("modifie_le") or ""), reverse=True)
        vus: dict = {}
        for _, e in elements:
            cle = " ".join(str(e.get("nom") or "").lower().split())
            vus[cle] = vus.get(cle, 0) + 1
        doublons = sorted({str(e.get("nom")) for _, e in elements
                           if vus.get(" ".join(str(e.get("nom") or "").lower().split()), 0) > 1})
        montres = elements[:MAX_LIGNES_INVENTAIRE_LOT]
        resultat["bloc_ui"] = [resultat["bloc_ui"], {
            "type": "table",
            "titre": f"Inventaire détaillé ({len(elements)} éléments)",
            "columns": ["Sous-dossier", "Nom", "Type", "Taille", "Modifié le"],
            "rows": [[d, str(e.get("nom") or ""), "Dossier" if e.get("dossier") else "Fichier",
                      "" if e.get("dossier") else octets_lisibles(e.get("octets") or 0),
                      _jour(e.get("modifie_le"))] for d, e in montres]}]
        resultat["elements_total"] = len(elements)
        resultat["doublons_de_nom"] = doublons[:40]
        if len(elements) > len(montres):
            resultat["inventaire_coupe_a"] = len(montres)
        # Le modèle n'a pas à relire mille lignes : les comptes et les doublons lui suffisent.
        for lot in lots:
            if len(lot.get("entrees") or []) > 12:
                lot["entrees"] = (lot.get("entrees") or [])[:12]
                lot["entrees_coupees_pour_le_modele"] = True
    resultat["bloc_garanti"] = True
    resultat["message_final"] = (
        f"{resultat.get('dossiers_inspectes', 0)} dossier(s) inspecté(s) sur "
        f"{resultat.get('dossiers_demandes', 0)}."
    )
    if resultat.get("dossiers_en_erreur"):
        resultat["message_final"] += (
            f" {resultat['dossiers_en_erreur']} dossier(s) n'ont pas pu être lus ; "
            "la raison est indiquée sur leur ligne."
        )
    resultat["a_faire"] = (
        "Le tableau est déjà affiché par le serveur. Ne recopie pas ses lignes. "
        "Dis exactement combien de dossiers ont été inspectés et distingue les "
        "dossiers en erreur ou dont le contenu dépassait la première page."
        + ((" L'inventaire DÉTAILLÉ (une ligne par élément : sous-dossier, nom, type, taille, date) "
            f"s'affiche aussi : annonce `elements_total` = {resultat.get('elements_total')} et cite "
            "`doublons_de_nom` tels quels (vide = aucun doublon exact).") if veut_detail else
           " Pour une ligne PAR ÉLÉMENT (inventaire : nom, type, taille, date, sous-dossier), "
           "rappelle ce geste avec `detail: true` (et `tri: \"date\"`).")
    )
    return resultat


async def drive_photos(data: dict, user) -> dict:
    """LES PHOTOS d'un dossier du Drive, rangées au dépôt et prêtes à l'écran.

    « Montre-moi les photos de ce chantier » ne trouvait aucun geste : la
    recherche documentaire rend du texte, et `drive_ouvrir` refuse les images.
    Elles sont ici déposées comme un visuel produit, donc affichables et
    téléchargeables dans le chat, sans qu'aucun lien ne sorte de l'application.
    """
    from outils.drive import photos
    resultat = await _drive(
        photos,
        (data.get("dossier") or data.get("chantier") or "").strip() or None,
        (data.get("motif") or data.get("nom") or "").strip() or None,
        data.get("limite") or 6,
        perimetres=_perimetres(user), identite=_identite(user))
    if resultat.get("bloc_ui"):
        resultat["message_final"] = (
            f"Voici {resultat['nombre']} photo(s)"
            + (f" sur {resultat['disponibles']} trouvée(s)"
               if resultat.get("disponibles", 0) > resultat["nombre"] else "")
            + ((" ; " + str(resultat["trop_volumineuses"])
                + " étaient trop volumineuse(s) pour être affichée(s)")
               if resultat.get("trop_volumineuses") else "") + ".")
        resultat["a_faire"] = (
            "AFFICHE les photos : insère un bloc ```ui contenant EXACTEMENT le "
            "contenu de `bloc_ui`. Ce sont de VRAIES photos du Drive, pas des "
            "images générées : ne les présente jamais comme un rendu ou une "
            "simulation. Ne colle aucune adresse d'image en texte.")
    return resultat


async def drive_arborescence(data: dict, user) -> dict:
    """L'arbre du Drive — complet si aucun dossier n'est précisé — en un appel.

    L'arbre s'affiche par un bloc MÉCANIQUE (`arbre`) : demander au modèle de
    recopier le `schema` produisait une carte de document inventée, sans rien
    dedans (relevé le 01/09).
    """
    from outils.drive import arborescence
    from skills.affichage import garantir_arborescence
    dossier = (data.get("dossier") or "").strip()
    resultat = await _drive(arborescence, dossier or None,
                            data.get("profondeur") or 0,
                            perimetres=_perimetres(user),
                            identite=_identite(user))
    return garantir_arborescence(
        resultat, f"du dossier « {dossier} »" if dossier else "du Drive")


async def drive_chercher(data: dict, user) -> dict:
    """Dossiers ET fichiers dont le NOM porte un motif, à toutes les profondeurs.

    Demande de Noa du 01/09 : une information sur un client absente de la
    mémoire d'entreprise doit déclencher, d'instinct, une recherche par NOM
    dans le classement du Drive — partout, pas au seul premier niveau — puis
    la proposition d'aller plus loin. Le pendant du `nas_chercher` du projet
    jumeau, même forme de résultat, même affichage mécanique.
    """
    from outils.drive import chercher
    from skills.affichage import garantir_recherche
    import asyncio
    motif = (data.get("motif") or data.get("nom") or data.get("client") or "").strip()
    if not motif:
        _echec("Donne le `motif` à chercher (nom de client, de chantier, de fichier).")
    try:
        resultat = await asyncio.wait_for(
            _drive(chercher, motif, perimetres=_perimetres(user),
                   identite=_identite(user),
                   page=data.get("page") or 1,
                   genre=data.get("type") or data.get("genre")),
            timeout=DELAI_RECHERCHE_DRIVE_S)
    except asyncio.TimeoutError:
        _echec(f"La recherche Drive a dépassé {DELAI_RECHERCHE_DRIVE_S // 60} minutes : Google ne "
               "répond pas. Aucun fichier n'a été modifié. Un motif plus précis (un nom "
               "entier, une année) rendra la main plus vite.")
    return garantir_recherche(resultat, motif, ouvreur="drive_ouvrir")


_STRICT = None


def nom_impose_par_la_demande(demande: str) -> str:
    """Le nom de fichier que la PERSONNE a écrit entre guillemets, quand elle interdit d'en ouvrir
    un autre (« interdiction d'ouvrir un document approchant », « exactement », « strictement »).

    POURQUOI (18/09, recette pilotée, prompt 11 rejoué avec une faute). Demandé : « Devis symbiose
    paysage Parkin.pdf », interdiction absolue d'un document approchant. Le modèle a cherché,
    trouvé « …Parking.pdf », et l'a ouvert sous SON nom corrigé : `exact: true` ne pouvait rien y
    voir, le nom passé était le bon. C'est le nom ÉCRIT PAR LA PERSONNE qui fait foi."""
    import re
    import unicodedata
    global _STRICT
    if _STRICT is None:
        _STRICT = re.compile(r"approchant|exactement|strictement|\bexact\b|et pas un autre|et aucun autre|"
                             r"ce fichier[- ]la et|nom exact|a la lettre", re.IGNORECASE)
    texte = str(demande or "")
    plat = "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")
    if not _STRICT.search(plat):
        return ""
    noms = re.findall(r"[«\"“]\s*([^«»\"“”\n]{3,160}?\.[A-Za-z0-9]{2,5})\s*[»\"”]", texte)
    return noms[0].strip() if len(noms) == 1 else ""


def _meme_nom(a: str, b: str) -> bool:
    import unicodedata

    def nu(x: str) -> str:
        x = unicodedata.normalize("NFD", str(x or "").split("/")[-1].strip().lower())
        return " ".join("".join(c for c in x if unicodedata.category(c) != "Mn").split())
    return nu(a) == nu(b)


async def drive_ouvrir(data: dict, user) -> dict:
    """Lit un fichier du Drive depuis son nom — ou le `chemin` rendu par un listage."""
    from outils.drive import ouvrir
    nom = (data.get("nom") or data.get("chemin") or data.get("fichier") or "").strip()
    # L'avis du ROUTEUR d'abord (18/09 : un jugement, pas un motif) ; le motif ne sert que s'il s'est tu.
    impose = (str(data.get("_fichier_exact") or "").strip() if data.get("_routeur_a_repondu")
              else nom_impose_par_la_demande(data.get("_demande_utilisateur") or ""))
    if impose:
        # Le nom écrit par la personne fait foi : s'il n'existe pas, l'ouverture échoue et
        # propose les noms proches — elle n'ouvre pas le voisin que le modèle a trouvé.
        if not _meme_nom(nom, impose):
            nom = impose
        data = {**data, "exact": True}
    # Un nom encodé à la façon d'une URL (r%C3%A9emploi) redevient lisible :
    # relevé sur le jumeau le 08/09, le modèle encode parfois les accents.
    if "%" in nom:
        import re as _re
        from urllib.parse import unquote
        if _re.search(r"%[0-9A-Fa-f]{2}", nom):
            nom = unquote(nom)
    if not nom:
        _echec("Donne le `nom` du fichier à ouvrir.")
    exact = str(data.get("exact") or "").strip().lower() in ("true", "1", "oui", "vrai")
    return await _drive(ouvrir, nom, perimetres=_perimetres(user),
                        identite=_identite(user), proprietaire=_proprietaire(user),
                        exact=exact)


async def drive_lire_lot(data: dict, user) -> dict:
    """Lit plusieurs fichiers du Drive correspondant à un motif."""
    from outils.drive import lire_lot
    motif = (data.get("motif") or "").strip()
    if not motif:
        _echec("Donne le `motif` des fichiers à lire (un morceau de leur nom).")
    return await _drive(lire_lot, motif,
                        (data.get("dossier") or "").strip() or None,
                        data.get("limite") or 5,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


async def drive_deposer(data: dict, user) -> dict:
    """Dépose sur le Drive un document produit par l'assistant. ÉCRITURE."""
    from outils.drive import deposer

    dossier = (data.get("dossier") or "").strip()
    jeton = (data.get("document_id") or "").strip()
    if not dossier or not jeton:
        _echec("Il faut le dossier du Drive et le `document_id` d'un document "
               "déjà terminé (`terminer_document`).")

    # On ne dépose QUE des documents produits ici, et seulement ceux de la
    # personne : téléverser un chemin arbitraire du serveur ferait de ce skill
    # un moyen d'exfiltrer des fichiers internes vers le Drive.
    from bureautique.atelier import chemin_fichier, fiche
    proprio = _proprietaire(user)
    chemin = chemin_fichier(jeton, proprio)
    if not chemin:
        _echec("Document inconnu, pas encore terminé, ou appartenant à "
               "quelqu'un d'autre. Reprends le `document_id` EXACT rendu par "
               "`terminer_document`.")

    f = fiche(jeton, proprio) or {}
    entete = f.get("entete") or {}
    nom = data.get("nom") or f"{entete.get('titre', 'document')}.{entete.get('format', 'docx')}"

    with open(chemin, "rb") as fichier:
        contenu = fichier.read()
    return await _drive(deposer, dossier, nom, contenu,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


async def drive_creer_dossier(data: dict, user) -> dict:
    """Crée un dossier sur le Drive, et y copie au besoin le contenu d'un dossier type. EFFET EXTERNE."""
    from outils.drive import creer_dossier

    parent = (data.get("parent") or data.get("dossier") or data.get("dans") or "").strip()
    nom = (data.get("nom") or data.get("nom_dossier") or "").strip()
    if not parent or not nom:
        _echec("Il faut `parent` (le dossier où créer) et `nom` (le nom EXACT du dossier à créer).")
    return await _drive(creer_dossier, parent, nom,
                        (data.get("modele") or data.get("dossier_type") or "").strip() or None,
                        perimetres=_perimetres(user), identite=_identite(user))


async def drive_deposer_document(data: dict, user) -> dict:
    """Finalise un document en cours et le dépose sur le Drive. EFFET EXTERNE."""
    from outils.drive import deposer_document

    doc = (data.get("document_id") or "").strip()
    dossier = (data.get("dossier") or "").strip()
    if not doc or not dossier:
        _echec("`document_id` et `dossier` sont requis.")
    # `proprietaire` (le propriétaire du BROUILLON) et `identite` (le compte
    # Google au nom duquel on écrit) sont deux notions distinctes : les
    # confondre exploserait au premier document repris par quelqu'un d'autre.
    return await _drive(deposer_document, doc, dossier, _proprietaire(user),
                        (data.get("nom") or "").strip() or None,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


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
            numeroter=data.get("numeroter", True),
            entete_image=str(data.get("entete_image") or data.get("logo_entete")
                             or data.get("logo") or "").strip(),
            pied_image=str(data.get("pied_image") or data.get("logo_pied") or "").strip(),
            user=user, fil=data.get("_fil"),
            style=data.get("style"), sous_titre=data.get("sous_titre"),
            image_couverture=data.get("image_couverture") or data.get("couverture"),
            page_de_garde=data.get("page_de_garde"), sommaire=data.get("sommaire"))
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
    "drive_apercu": Declaration(
        fonction=drive_apercu,
        description=(
            # LE VOCABULAIRE MAISON vit dans la première entrée Drive : c'est au
            # moment de CHOISIR l'action que le modèle en a besoin. Personne ne
            # dit « Google Drive » en entier — on dit « le Drive », « le cloud »,
            # « le partage ».
            "COMPTE et resume un dossier du DRIVE : combien de dossiers, de "
            "fichiers, de quels types. LE DRIVE, LE CLOUD, GOOGLE et LE PARTAGE "
            "designent la meme chose. Pour un NOMBRE ou « ce qu'il y a sur le "
            "Drive ». S'AFFICHE AUTOMATIQUEMENT : n'en fais jamais un document. "
            "Il COMPTE sans nommer les fichiers : pour leurs NOMS, `drive_lister`. "
            "`dossier` : NOM ou CHEMIN, sans identifiant"),
        optionnels=["dossier"],
        effet="lecture",
        libelle="je regarde ce que contient le dossier"),
    "drive_lister": Declaration(
        fonction=drive_lister,
        description=(
            "LISTE le contenu d'un dossier du DRIVE : sous-dossiers ET fichiers par "
            "NOM, avec taille et date — le tableau S'AFFICHE AUTOMATIQUEMENT. LE "
            "geste pour savoir QUELS fichiers un dossier contient, puis en ouvrir "
            "un (`drive_ouvrir` avec le `chemin` rendu). `dossier` : NOM ou "
            "CHEMIN ; `page` pour la suite ; `tri: \"date\"` : le plus recemment "
            "modifie d'abord. Les doublons de nom sont rendus dans `doublons_de_nom`"),
        # `dossier` OU `chemin` OU `nom` : le skill vérifie lui-même (18/09).
        requis=[], optionnels=["dossier", "chemin", "page", "tri"],
        effet="lecture",
        libelle="je liste le contenu du dossier"),
    "drive_lister_lot": Declaration(
        fonction=drive_lister_lot,
        description=(
            "LISTE PLUSIEURS DOSSIERS DU DRIVE EN UNE SEULE ACTION, EN PARALLELE. "
            "A utiliser pour « chacun », « tous les dossiers clients » ou toute "
            "demande portant sur au moins trois dossiers. Passe dossiers=[...], "
            "et motif pour ne garder que les noms correspondants. POUR UN INVENTAIRE (« liste tout "
            "le contenu : nom, type, date, taille, sous-dossier ») : `detail: true` rend UNE LIGNE "
            "PAR ELEMENT, `tri: \"date\"` du plus recent au plus ancien. Le tableau "
            "s'affiche automatiquement ; ne rappelle pas drive_lister dossier "
            "par dossier."),
        requis=["dossiers"], optionnels=["motif", "detail", "tri"],
        effet="lecture",
        libelle="j'inspecte les dossiers du Drive en parallèle"),
    "drive_photos": Declaration(
        fonction=drive_photos,
        description=(
            "MONTRE LES PHOTOS d'un dossier du DRIVE dans le chat : elles sont "
            "affichees en planche et telechargeables. A utiliser des qu'on "
            "demande de VOIR des images (« montre-moi les photos du chantier "
            "X », « les visuels de ce dossier »). `dossier` : le NOM ou le "
            "CHEMIN du dossier. `motif` : un bout de nom de fichier. `limite` : "
            "1 a 12 (6 par defaut). Ce sont de VRAIES photos, jamais un rendu "
            "genere : ne les presente pas comme une simulation"),
        optionnels=["dossier", "motif", "limite"],
        effet="lecture",
        libelle="je vais chercher les photos"),
    "drive_arborescence": Declaration(
        fonction=drive_arborescence,
        description=("ARBRE COMPLET du Drive (Drives partages inclus) en UNE "
                     "action : sans `dossier`, TOUT y passe, avec les comptes. "
                     "L'arbre S'AFFICHE AUTOMATIQUEMENT dans le chat : ne le "
                     "recopie pas, n'en fais jamais un document. "
                     "`dossier` (NOM ou CHEMIN) limite a un sous-arbre"),
        optionnels=["dossier", "profondeur"],
        effet="lecture",
        libelle="je parcours les dossiers du Drive"),
    "drive_chercher": Declaration(
        fonction=drive_chercher,
        description=(
            "CHERCHE dossiers ET fichiers par NOM sur TOUT le Drive, toutes "
            "profondeurs, avec leurs CHEMINS. D'INSTINCT quand un client, un "
            "chantier ou un fournisseur ne sort ni des fichiers importes ni des "
            "documents. S'affiche automatiquement, dossiers ET fichiers sur "
            "chaque page ; si la demande est d'OUVRIR, enchaine `drive_ouvrir` "
            "sur un FICHIER trouve. `motif` ; `page` ; `type` : « fichiers » "
            "ou « dossiers »"),
        requis=["motif"], optionnels=["page", "type"],
        effet="lecture",
        libelle="je cherche ce nom sur le Drive"),
    "drive_ouvrir": Declaration(
        fonction=drive_ouvrir,
        description=("OUVRE et lit un fichier du Drive depuis son NOM, sans en "
                     "connaitre l'identifiant, ou depuis le `chemin` rendu par "
                     "`drive_lister` (le plus sur). La voie normale pour lire un "
                     "fichier ; le fichier s'affiche avec son apercu. `exact: true` "
                     "quand on te donne un nom PRECIS et qu'on interdit d'en ouvrir un "
                     "autre : un nom approchant est alors REFUSE et les noms proches "
                     "te sont rendus. Un document long se lit en entier par "
                     "`lire_source_dossier`, page apres page : enchaine-les quand on "
                     "demande le contenu integral, ne resume pas a la place"),
        # `nom` OU `chemin` (18/09) : requis=["nom"] refusait AVANT le skill l'ouverture par le
        # chemin rendu par `drive_lister` — que le catalogue présente comme « le plus sûr ». Le
        # skill vérifie lui-même qu'il a l'un des deux (même piège que `mailbox` le 26/08).
        requis=[], optionnels=["nom", "chemin", "exact"],
        effet="lecture",
        libelle="j'ouvre le fichier"),
    "drive_lire_lot": Declaration(
        fonction=drive_lire_lot,
        description=("LIT plusieurs fichiers du Drive correspondant a un motif "
                     "(5 maximum)"),
        requis=["motif"], optionnels=["dossier", "limite"],
        effet="lecture",
        libelle="je lis les fichiers"),
    "drive_deposer": Declaration(
        fonction=drive_deposer,
        description=("DEPOSE sur le Drive un fichier deja produit, UNIQUEMENT "
                     "pour le RANGER dans le classement de l'entreprise. Un "
                     "document produit est DEJA telechargeable dans le chat : "
                     "ne depose JAMAIS pour « donner », « montrer » ou "
                     "« telecharger » un fichier. Ecrit sur le Drive : "
                     "validation humaine. N'ecrase jamais. Aucune suppression "
                     "ni renommage n'est possible : ne le promets pas"),
        requis=["dossier", "document_id"], optionnels=["nom"],
        # Écrire dans le classement de l'entreprise sort du périmètre de
        # l'application : effet EXTERNE, validation humaine obligatoire.
        effet="externe",
        libelle="je dépose le fichier sur le Drive"),
    "drive_creer_dossier": Declaration(
        fonction=drive_creer_dossier,
        description=("CREE un dossier sur le Drive, dans un dossier EXISTANT. `parent` : le "
                     "dossier ou le creer (nom ou chemin). `nom` : le nom EXACT du nouveau "
                     "dossier. `modele` (option) : le NOM d'un dossier type dont le CONTENU est "
                     "copie dans le nouveau dossier. AVANT d'appeler ce geste, LISTE le parent "
                     "(`drive_lister`) et ecris dans ta reponse deux dossiers voisins dont tu "
                     "reprends le nommage, casse comprise : c'est ce que la personne lira "
                     "au-dessus de la carte d'accord. Refuse si un dossier du meme nom existe "
                     "deja. Ecrit sur le Drive : validation humaine. Ne renomme, ne deplace et "
                     "ne supprime rien : ne le promets pas"),
        requis=["parent", "nom"], optionnels=["modele"],
        effet="externe",
        libelle="je crée le dossier sur le Drive"),
    "drive_deposer_document": Declaration(
        fonction=drive_deposer_document,
        description=("FINALISE un document en cours et le DEPOSE sur le Drive, "
                     "en un geste — UNIQUEMENT si on demande de le RANGER sur "
                     "le Drive. Pour donner ou telecharger un document dans le "
                     "chat, `terminer_document` suffit : le fichier y est deja. "
                     "`dossier` accepte le NOM (ex. « Devis 2026 »). Ecrit sur "
                     "le Drive : demande une validation humaine"),
        requis=["document_id", "dossier"], optionnels=["nom"],
        # Le depot ecrit dans le classement de l'entreprise : effet EXTERNE,
        # donc validation humaine — composer deux gestes ne compose pas les droits.
        effet="externe",
        libelle="je finalise et dépose le document"),
    "produire_document": Declaration(
        fonction=produire_document,
        description=(
            # Le detail de la mise en forme (valeurs de taille et de couleur)
            # vit dans `outils/docs/documents.md`, lisible via `mode_emploi` :
            # le catalogue est injecte a CHAQUE tour, y compris ceux qui ne
            # produisent aucun document. On y garde de quoi CHOISIR l'action,
            # pas de quoi la parametrer finement.
            # LE SEUIL EN PAGES, PAS EN BLOCS. « environ 30 blocs » ne parle
            # pas a une demande formulee « un docx de 10 pages » : le modele
            # appelait donc ce geste, obtenait 2 pages, et RECOMMENCAIT — sept
            # fois, six documents produits, aucun livre. Le geste est en UN
            # COUP : il finalise, donc rien ne se rallonge apres.
            # 395 caracteres : le catalogue est injecte a CHAQUE tour, le
            # plafond de 400 par description n'est pas negociable.
            "PRODUIT un document (pdf, docx, xlsx) en UNE fois. `style` : classique|moderne|"
            "epure|plaquette, CHOISI selon le document. `blocs` : titre|paragraphe|liste|"
            "tableau|image|colonnes (photo a cote du texte)|encadre|chiffres|citation|"
            "saut_page|feuille. `entete_image`/`pied_image`/`image_couverture` : logo, "
            "photo, ou PDF de la maison. couleur:'charte'. ~30 blocs max ; au-dela "
            "creer/ajouter/terminer_document. `mode_emploi` documents"),
        requis=["titre", "blocs"],
        optionnels=["format", "entete", "pied", "numeroter", "entete_image", "pied_image",
                    "page_de_garde", "sommaire", "style", "image_couverture", "sous_titre"],
        effet="ecriture_interne",
        libelle="je produis le document"),
    "mode_emploi": Declaration(
        fonction=mode_emploi,
        description=("MODE D'EMPLOI complet d'un outil (drive, documents, visuels) : "
                     "conventions, limites, pannes connues. A lire quand aucune "
                     "action ne couvre le besoin"),
        optionnels=["outil"],
        effet="lecture",
        libelle="je relis le mode d'emploi de l'outil"),
}
