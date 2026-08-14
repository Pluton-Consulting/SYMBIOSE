"""
Outil « Google Drive » — les gestes composés du Drive de l'entreprise.

POURQUOI CET OUTIL EXISTE. L'assistant répondait « je n'ai pas accès à Google
Drive » alors que le Drive est synchronisé chez lui : il n'avait simplement
aucune ACTION pour aller y regarder. « Va sur le Drive et compte les dossiers »
n'avait donc pas de réponse possible — ni vraie, ni fausse, juste absente.

CE QUE LA MÉMOIRE NE REMPLACE PAS. L'ingestion range le CONTENU des documents
dans la mémoire d'entreprise : on peut y chercher une phrase, pas y compter des
dossiers ni savoir ce qu'un client a déposé hier. Compter, parcourir, ouvrir un
fichier par son nom sont des questions sur la STRUCTURE, et la structure n'est
pas ingérée. D'où ces quatre gestes.

CHAQUE FONCTION RÉUNIT UNE CHAÎNE COMPLÈTE. Mesuré sur Duret, où la même
bibliothèque existe pour le serveur de fichiers : 57 % du temps d'une demande
part en allers-retours avec le modèle, 14 % seulement dans les outils. Compter
les dossiers demandait un listage, puis un comptage par le modèle — qui se
trompe d'autant plus que la liste est longue. Ici le compte est fait par le
code, en un appel.

LE PÉRIMÈTRE EST CELUI DE LA CONFIGURATION, PAS TOUT LE DRIVE. `perimetres()`
associe un niveau d'accès à chaque dossier déclaré ; ces fonctions ne voient que
les dossiers dont le niveau est visible par le rôle qui demande. Un dossier RH
en `direction_only` n'existe pas pour un commercial — ni son contenu, ni son
nom, ni son existence.
"""
from __future__ import annotations

import asyncio
import logging
import posixpath
from typing import Optional

logger = logging.getLogger("symbiose.outils.drive")

# ── Bornes ───────────────────────────────────────────────────────────
# Les mêmes esprits que pour le NAS de Duret : ces gestes servent un tour de
# conversation, pas une ingestion. Le modèle n'exploite pas quarante dossiers,
# et chaque niveau supplémentaire coûte un appel réseau que l'utilisateur attend.
MAX_PROFONDEUR = 3
MAX_DOSSIERS_PARCOURUS = 40
MAX_LOT = 5
MAX_ENTREES = 200          # par dossier listé, comme l'API le pagine

_MIME_DOSSIER = "application/vnd.google-apps.folder"
_MIME_RACCOURCI = "application/vnd.google-apps.shortcut"


class DriveRefuse(Exception):
    """Le Drive refuse, ou rien n'est ouvert à l'assistant. PAS un Drive vide."""


def perimetres_visibles(role: Optional[str]) -> list[tuple[Optional[str], str]]:
    """Les (dossier, niveau) que ce rôle a le droit de voir.

    LE FILTRE EST ICI, PAS À L'AFFICHAGE. Rendre l'arborescence complète puis
    masquer les branches interdites laisserait fuiter les NOMS — et un dossier
    « Licenciement Untel » dit déjà l'essentiel sans qu'on l'ouvre.
    """
    from ingestion.connectors.google_drive import perimetres
    from security.acces import niveaux_visibles

    autorises = set(niveaux_visibles(role))
    return [(d, n) for d, n in perimetres() if n in autorises]


# LE CLIENT EST GARDÉ, et ce n'est pas une micro-optimisation. Le construire
# coûte DEUX allers-retours avec Google : un éventuel rafraîchissement du jeton
# OAuth, puis le téléchargement du document de description de l'API Drive. Une
# à deux secondes, payées à CHAQUE action — l'assistant paraissait « beaucoup
# trop lent » pour cette seule raison, avant même d'avoir lu quoi que ce soit.
#
# Durée de vie courte : un jeton d'accès Google vaut une heure, on se reconstruit
# bien avant pour ne jamais servir un client périmé.
_CLIENT: dict = {"service": None, "expire": 0.0}
_DUREE_CLIENT_S = 1800


async def _service():
    """Le client Drive, construit HORS de la boucle d'événements, et gardé.

    `_build_service` fait un rafraîchissement OAuth synchrone : laissé dans la
    boucle, il gèle tout le backend le temps de l'aller-retour avec Google.
    """
    import time
    if _CLIENT["service"] is not None and time.monotonic() < _CLIENT["expire"]:
        return _CLIENT["service"]
    from ingestion.connectors.google_drive import _build_service
    service = await asyncio.to_thread(_build_service)
    _CLIENT.update({"service": service, "expire": time.monotonic() + _DUREE_CLIENT_S})
    return service


async def _racines(service) -> list[str]:
    """Les dossiers de tête à explorer quand tout le Drive est ouvert.

    « root » NE DÉSIGNE QUE « MON DRIVE ». Un Drive PARTAGÉ — celui d'une
    entreprise, justement — a sa propre racine, dont l'identifiant est celui du
    Drive lui-même. Partir de « root » sur une organisation qui travaille en
    Drive partagé rend un dossier personnel vide, et l'assistant conclut que le
    Drive est vide. C'est le même piège que `corpora` côté ingestion : les
    réglages « autorisent » les Drive partagés sans jamais décider d'y chercher.

    On rend donc « root » ET la racine de chaque Drive partagé accessible.
    """
    racines = ["root"]
    try:
        def _appel():
            return service.drives().list(pageSize=100, fields="drives(id,name)").execute()
        partages = (await asyncio.to_thread(_appel)).get("drives", [])
        racines += [d["id"] for d in partages if d.get("id")]
        if partages:
            logger.info("Drive : %d Drive(s) partagé(s) trouvé(s)", len(partages))
    except Exception as e:  # noqa: BLE001
        # Le compte n'a peut-être aucun Drive partagé, ou pas le droit de les
        # lister. Ce n'est pas une panne : on continue avec « Mon Drive ».
        logger.info("Drive : liste des Drive partagés indisponible (%s)", e)
    return racines


def _echappe(v: str) -> str:
    return v.replace("\\", "\\\\").replace("'", "\\'")


def _est_identifiant(v: str) -> bool:
    """Un identifiant Drive, ou un nom écrit par un humain ?

    Les identifiants font une trentaine de caractères sans espace ni barre
    oblique ; un nom de dossier d'entreprise en a presque toujours.
    """
    return len(v) >= 20 and " " not in v and "/" not in v


async def _dossiers_sous(service, parents: list[str], nom: Optional[str] = None,
                         limite: int = 100) -> list[dict]:
    """Les sous-dossiers d'un ou plusieurs parents, filtrés par nom si demandé."""
    ou = " or ".join(f"'{_echappe(p)}' in parents" for p in parents)
    q = (f"({ou}) and mimeType = '{_MIME_DOSSIER}' and trashed = false"
         + (f" and name contains '{_echappe(nom)}'" if nom else ""))

    def _appel():
        return service.files().list(
            q=q, spaces="drive", fields="files(id,name)",
            corpora="allDrives", includeItemsFromAllDrives=True,
            supportsAllDrives=True, pageSize=limite,
        ).execute()

    return (await asyncio.to_thread(_appel)).get("files", [])


async def _dossiers_partout(service, nom: str, limite: int = 20) -> list[dict]:
    """Les dossiers portant ce nom, à n'importe quelle profondeur du Drive."""
    def _appel():
        return service.files().list(
            q=(f"mimeType = '{_MIME_DOSSIER}' and trashed = false "
               f"and name contains '{_echappe(nom)}'"),
            spaces="drive", fields="files(id,name)",
            corpora="allDrives", includeItemsFromAllDrives=True,
            supportsAllDrives=True, pageSize=limite,
        ).execute()

    return (await asyncio.to_thread(_appel)).get("files", [])


async def _resoudre(service, chemin: str, racines: list[str],
                    partout: bool = False) -> str:
    """Un NOM ou un CHEMIN de dossier vers son identifiant Drive.

    POURQUOI C'EST INDISPENSABLE. Ces outils n'acceptaient qu'un IDENTIFIANT.
    Personne n'en connaît par cœur, et le modèle encore moins : à « dans le
    Drive partagé, dossier communication, il y a combien de dossiers ? », il
    passait le NOM en guise d'identifiant, recevait un 404, essayait un autre
    nom, puis un autre — jusqu'à épuiser son budget d'actions sans jamais rien
    répondre. Le geste le plus naturel était le seul impossible.

    QUAND ÇA ÉCHOUE, ON DIT CE QUI EXISTE. Un « dossier introuvable » sec
    relance le modèle dans des devinettes coûteuses. Lui rendre les noms
    présents à ce niveau lui permet de se corriger en UN coup — c'est la
    différence entre une erreur et une piste.
    """
    valeur = (chemin or "").strip().strip("/")
    if not valeur:
        raise DriveRefuse("Donne le nom ou le chemin du dossier.")
    # UN IDENTIFIANT DE PÉRIMÈTRE FAIT AUTORITÉ. Il vient de la configuration,
    # pas du modèle : le chercher par nom serait absurde, et l'heuristique de
    # forme ci-dessous se tromperait sur un identifiant court.
    if valeur in racines:
        return valeur
    if _est_identifiant(valeur):
        return valeur

    parents = list(racines)
    parcourus: list[str] = []
    segments = [s.strip() for s in valeur.split("/") if s.strip()]
    for rang, segment in enumerate(segments):
        trouves = await _dossiers_sous(service, parents, segment)
        # LE PREMIER SEGMENT SE CHERCHE PARTOUT — mais SEULEMENT si tout le
        # Drive est déjà ouvert. « le dossier communication » ne veut pas dire
        # « à la racine » : les gens nomment le dossier qu'ils ont en tête sans
        # savoir où il est rangé, et ne chercher qu'au premier niveau faisait
        # échouer la formulation la plus naturelle.
        #
        # DÈS QUE DES PÉRIMÈTRES SONT DÉCLARÉS, on ne sort pas : une recherche
        # globale trouverait un dossier hors périmètre, et le refus qui suivrait
        # confirmerait son EXISTENCE. Pour un dossier nommé « Licenciement
        # Untel », l'existence est déjà l'information.
        #
        # Les segments SUIVANTS restent contraints à leur parent : c'est tout
        # le sens d'un chemin.
        if not trouves and rang == 0 and partout:
            trouves = await _dossiers_partout(service, segment)
        if not trouves:
            dispo = [d["name"] for d in await _dossiers_sous(service, parents)]
            ou = "/".join(parcourus) if parcourus else "la racine du Drive"
            raise DriveRefuse(
                f"Aucun dossier « {segment} » dans {ou}. "
                + (f"Dossiers présents : {', '.join(sorted(dispo)[:25])}."
                   if dispo else "Ce niveau ne contient aucun sous-dossier.")
                + " Reprends le nom EXACT dans cette liste.")
        # Une correspondance exacte (à la casse près) l'emporte sur un simple
        # « contient » : « Communication » et « Communication interne » sortent
        # tous deux, et c'est le premier qu'on veut.
        exact = [d for d in trouves if d["name"].lower() == segment.lower()]
        choisi = (exact or trouves)[0]
        parcourus.append(choisi["name"])
        parents = [choisi["id"]]
    return parents[0]


def _tout_le_drive(perimetres: list) -> bool:
    """Le périmètre couvre-t-il le Drive ENTIER ?

    Sans `GOOGLE_DRIVE_PERIMETRES` ni `GOOGLE_DRIVE_FOLDER_ID`, `perimetres()`
    rend `[(None, 'all')]` — ce qui signifie « tout le Drive à ce niveau », pas
    « aucun dossier ». Je l'avais lu comme une absence, et l'aperçu refusait :
    l'assistant redemandait alors la même action, en boucle, jusqu'au garde-fou
    anti-répétition. C'est ce qui donnait « redemandée à l'identique sans que la
    demande avance ».
    """
    return any(d is None for d, _ in perimetres)


async def _lister(service, dossier: str, limite: int = MAX_ENTREES) -> dict:
    """Les entrées DIRECTES d'un dossier, bornées, avec le total réel."""
    def _appel():
        return service.files().list(
            q=f"'{dossier}' in parents and trashed=false",
            spaces="drive",
            fields="nextPageToken, files(id,name,mimeType,size,modifiedTime)",
            corpora="allDrives", includeItemsFromAllDrives=True,
            supportsAllDrives=True, pageSize=min(limite, 1000),
        ).execute()

    resp = await asyncio.to_thread(_appel)
    entrees = resp.get("files", [])
    return {
        "entrees": entrees[:limite],
        # UNE PAGE SUIVANTE VEUT DIRE QU'ON N'A PAS TOUT. C'est la seule
        # information qui permette de ne pas annoncer un compte partiel comme
        # un compte exact — le mensonge que le modèle répète ensuite.
        "tronque": bool(resp.get("nextPageToken")) or len(entrees) > limite,
    }


def _classer(entrees: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sépare dossiers et fichiers. Les raccourcis comptent pour des fichiers."""
    dossiers = [e for e in entrees if e.get("mimeType") == _MIME_DOSSIER]
    fichiers = [e for e in entrees if e.get("mimeType") != _MIME_DOSSIER]
    return dossiers, fichiers


async def apercu(dossier: Optional[str] = None,
                 perimetres: Optional[list] = None) -> dict:
    """Ce que contient un dossier, compté et classé — sans lister le détail.

    Répond en UN appel à « combien de dossiers sur le Drive », « qu'est-ce
    qu'il y a là-dedans », « c'est gros ? ».
    """
    perimetres = perimetres or []
    if not dossier:
        # AUCUN DOSSIER OUVERT N'EST PAS UN DRIVE VIDE. Répondre « 0 dossier »
        # se lit comme « le Drive est vide », et le modèle le répète tel quel.
        if not perimetres:
            raise DriveRefuse(
                "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle. "
                "Un administrateur doit renseigner GOOGLE_DRIVE_PERIMETRES. Ce "
                "n'est PAS un Drive vide : dis-le tel quel.")
        cibles = [d for d, _ in perimetres if d]
        if not cibles and _tout_le_drive(perimetres):
            cibles = await _racines(await _service())
        if not cibles:
            raise DriveRefuse(
                "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle.")
    else:
        # Le dossier arrive presque toujours sous forme de NOM ou de CHEMIN :
        # c'est ce qu'un humain dit, et donc ce que le modèle répète.
        service = await _service()
        racines = ([d for d, _ in perimetres if d]
                   or (await _racines(service) if _tout_le_drive(perimetres) else []))
        dossier = await _resoudre(service, dossier, racines,
                                partout=_tout_le_drive(perimetres))
        _garde_perimetre(dossier, perimetres)
        cibles = [dossier]

    service = await _service()
    resume, illisibles = [], []
    for d in cibles:
        try:
            brut = await _lister(service, d)
        except Exception as e:  # noqa: BLE001
            # Un dossier illisible n'efface pas les autres.
            illisibles.append({"dossier": d, "raison": str(e)[:120]})
            continue
        dossiers, fichiers = _classer(brut["entrees"])
        octets = sum(int(f.get("size") or 0) for f in fichiers)
        # Les extensions les plus présentes disent la NATURE d'un dossier
        # (plans, devis, photos) mieux qu'une liste de noms tronquée.
        types: dict[str, int] = {}
        for f in fichiers:
            ext = posixpath.splitext(f.get("name") or "")[1].lower().lstrip(".")
            types[ext or "sans extension"] = types.get(ext or "sans extension", 0) + 1
        resume.append({
            "dossier": d,
            "dossiers": len(dossiers),
            "fichiers": len(fichiers),
            "octets_total": octets,
            "types_de_fichiers": dict(sorted(types.items(), key=lambda kv: -kv[1])[:8]),
            "noms_des_dossiers": [x.get("name") for x in dossiers][:40],
            "tronque": brut["tronque"],
        })

    tronques = [r for r in resume if r["tronque"]]
    sortie = {
        "total_dossiers": sum(r["dossiers"] for r in resume),
        "total_fichiers": sum(r["fichiers"] for r in resume),
        "detail": resume,
    }
    if tronques:
        sortie["note"] = (
            "Compte PARTIEL : au moins un dossier contient plus d'entrées que "
            f"les {MAX_ENTREES} lues. Ne présente pas ces nombres comme exacts.")
    if illisibles:
        sortie["illisibles"] = illisibles
    return sortie


async def arborescence(dossier: str, profondeur: int = 2,
                       perimetres: Optional[list] = None) -> dict:
    """L'arbre d'un dossier sur plusieurs niveaux, en UN appel.

    Descendre de trois niveaux demandait trois listages, donc trois
    allers-retours de modèle. Bornée en profondeur ET en nombre de dossiers :
    un Drive d'entreprise peut en contenir des milliers.
    """
    perimetres = perimetres or []
    service = await _service()
    racines = ([d for d, _ in perimetres if d]
               or (await _racines(service) if _tout_le_drive(perimetres) else []))
    dossier = await _resoudre(service, dossier, racines,
                                partout=_tout_le_drive(perimetres))
    _garde_perimetre(dossier, perimetres)
    profondeur = max(1, min(int(profondeur or 2), MAX_PROFONDEUR))
    vus = 0
    racine: dict = {"dossier": dossier, "enfants": []}
    file_attente = [(dossier, racine, 0)]
    inexplores = 0

    while file_attente and vus < MAX_DOSSIERS_PARCOURUS:
        courant, noeud, niveau = file_attente.pop(0)
        vus += 1
        try:
            brut = await _lister(service, courant)
        except Exception as e:  # noqa: BLE001
            noeud["illisible"] = str(e)[:120]
            continue
        sous_dossiers, fichiers = _classer(brut["entrees"])
        noeud["fichiers"] = len(fichiers)
        noeud["tronque"] = brut["tronque"]
        for sd in sous_dossiers:
            enfant = {"dossier": sd["id"], "nom": sd.get("name"), "enfants": []}
            noeud["enfants"].append(enfant)
            if niveau + 1 < profondeur:
                file_attente.append((sd["id"], enfant, niveau + 1))
            else:
                # UN DOSSIER NON EXPLORÉ N'EST PAS UN DOSSIER VIDE. Sans cette
                # marque, l'arbre présentait des branches vides que le modèle
                # rapportait comme telles à l'utilisateur.
                enfant["explore"] = False
                inexplores += 1

    sortie = {"arbre": racine, "dossiers_parcourus": vus,
              "profondeur": profondeur}
    if file_attente:
        sortie["note"] = (
            f"Parcours ARRÊTÉ à {MAX_DOSSIERS_PARCOURUS} dossiers : l'arbre est "
            "incomplet. Ne le présente pas comme exhaustif.")
    elif inexplores:
        sortie["note"] = (
            f"{inexplores} dossier(s) atteints à la profondeur maximale n'ont "
            "pas été ouverts : leur contenu est inconnu, pas vide.")
    return sortie


async def ouvrir(nom: str, perimetres: Optional[list] = None) -> dict:
    """Lit un fichier depuis son NOM, sans en connaître l'identifiant.

    La voie normale pour lire un fichier : personne ne connaît par cœur un
    identifiant Drive, et un modèle qui n'en a pas sous les yeux l'INVENTE.
    """
    nom = (nom or "").strip()
    if not nom:
        raise DriveRefuse("Donne le nom du fichier à ouvrir.")
    perimetres = perimetres or []
    if not perimetres:
        raise DriveRefuse(
            "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle.")

    service = await _service()
    echappe = nom.replace("\\", "\\\\").replace("'", "\\'")
    trouves = []

    if _tout_le_drive(perimetres):
        # TOUT LE DRIVE EST OUVERT : on cherche PARTOUT, à toutes les
        # profondeurs. Se limiter aux enfants directs de la racine ne trouvait
        # presque rien — les fichiers d'une entreprise vivent dans des
        # sous-dossiers, jamais à la racine. C'est ce qui faisait échouer
        # « ouvre tel fichier » alors que le fichier existait bien.
        def _partout():
            return service.files().list(
                q=f"trashed=false and name contains '{echappe}'",
                spaces="drive", fields="files(id,name,mimeType,size,modifiedTime)",
                corpora="allDrives", includeItemsFromAllDrives=True,
                supportsAllDrives=True, pageSize=10,
            ).execute()
        try:
            trouves = (await asyncio.to_thread(_partout)).get("files", [])
        except Exception as e:  # noqa: BLE001
            logger.warning("Drive : recherche de « %s » échouée : %s", nom, e)
    else:
        # Périmètres déclarés : on cherche DEDANS, jamais ailleurs — sinon un
        # nom bien choisi ramènerait un document hors périmètre.
        for d, _niveau in perimetres:
            if not d:
                continue
            def _appel(dossier=d):
                return service.files().list(
                    q=(f"'{dossier}' in parents and trashed=false "
                       f"and name contains '{echappe}'"),
                    spaces="drive", fields="files(id,name,mimeType,size,modifiedTime)",
                    corpora="allDrives", includeItemsFromAllDrives=True,
                    supportsAllDrives=True, pageSize=10,
                ).execute()
            try:
                trouves.extend((await asyncio.to_thread(_appel)).get("files", []))
            except Exception as e:  # noqa: BLE001
                logger.warning("Drive : recherche de « %s » dans %s échouée : %s",
                               nom, d, e)

    trouves = [f for f in trouves if f.get("mimeType") != _MIME_DOSSIER]
    if not trouves:
        raise DriveRefuse(
            f"Aucun fichier nommé « {nom} » dans les dossiers ouverts. "
            "Ce n'est pas une preuve qu'il n'existe pas : il peut être ailleurs "
            "sur le Drive, ou hors du périmètre autorisé.")

    fichier = trouves[0]
    from ingestion.connectors.google_drive import _download_text
    texte = await asyncio.to_thread(_download_text, service, fichier)
    if texte is None:
        return {"nom": fichier.get("name"), "id": fichier["id"],
                "type": fichier.get("mimeType"),
                "note": ("Ce format ne se lit pas ici (image, docx, tableur "
                         "propriétaire). Le fichier existe, son contenu n'a pas "
                         "pu être extrait.")}
    return {
        "nom": fichier.get("name"), "id": fichier["id"],
        "modifie_le": fichier.get("modifiedTime"),
        "contenu": texte[:20000],
        "tronque": len(texte) > 20000,
        "autres_correspondances": [f.get("name") for f in trouves[1:5]] or None,
    }


async def lire_lot(motif: str, dossier: Optional[str] = None,
                   limite: int = MAX_LOT,
                   perimetres: Optional[list] = None) -> dict:
    """Lit plusieurs fichiers correspondant à un motif, en UN appel."""
    motif = (motif or "").strip()
    if not motif:
        raise DriveRefuse("Donne le motif des fichiers à lire.")
    perimetres = perimetres or []
    limite = max(1, min(int(limite or MAX_LOT), MAX_LOT))
    partout = _tout_le_drive(perimetres) and not dossier
    service = await _service()
    if dossier:
        racines = ([d for d, _ in perimetres if d]
                   or (await _racines(service) if _tout_le_drive(perimetres) else []))
        dossier = await _resoudre(service, dossier, racines,
                                partout=_tout_le_drive(perimetres))
        _garde_perimetre(dossier, perimetres)
        cibles = [(dossier, None)]
    else:
        cibles = [(d, n) for d, n in perimetres if d]
    if not cibles and not partout:
        raise DriveRefuse(
            "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle.")

    echappe = motif.replace("\\", "\\\\").replace("'", "\\'")
    candidats = []
    # Même raison que pour `ouvrir` : tout le Drive ouvert veut dire à toutes
    # les profondeurs, pas seulement à la racine.
    requetes = ([f"trashed=false and name contains '{echappe}'"] if partout
                else [f"'{d}' in parents and trashed=false "
                      f"and name contains '{echappe}'" for d, _ in cibles])
    for q in requetes:
        def _appel(requete=q):
            return service.files().list(
                q=requete, spaces="drive", fields="files(id,name,mimeType)",
                corpora="allDrives", includeItemsFromAllDrives=True,
                supportsAllDrives=True, pageSize=limite * 2,
            ).execute()
        try:
            candidats.extend((await asyncio.to_thread(_appel)).get("files", []))
        except Exception as e:  # noqa: BLE001
            logger.warning("Drive : lot « %s » échoué : %s", motif, e)

    candidats = [f for f in candidats if f.get("mimeType") != _MIME_DOSSIER]
    from ingestion.connectors.google_drive import _download_text
    lus, ignores = [], []
    for f in candidats[:limite]:
        texte = await asyncio.to_thread(_download_text, service, f)
        if texte:
            lus.append({"nom": f.get("name"), "contenu": texte[:6000]})
        else:
            ignores.append(f.get("name"))
    return {
        "motif": motif, "lus": lus, "nombre_lu": len(lus),
        "illisibles": ignores or None,
        # LE NOMBRE DE CANDIDATS COMPTE : « j'ai lu 5 fichiers » sur 40 qui
        # correspondent n'est pas une réponse à « lis les factures de juillet ».
        "correspondances_totales": len(candidats),
        "note": (f"{len(candidats)} fichiers correspondent, {limite} lus au "
                 f"maximum par appel." if len(candidats) > limite else None),
    }


def _garde_perimetre(dossier: str, perimetres: list) -> None:
    """Un dossier demandé doit appartenir à un périmètre autorisé.

    SANS CE CONTRÔLE, il suffirait de connaître un identifiant Drive pour lire
    hors de son périmètre — et les identifiants circulent dans les URL que les
    gens se partagent.

    Quand le périmètre couvre tout le Drive, il n'y a rien à cloisonner : tout
    est déjà autorisé, et refuser serait absurde.
    """
    if _tout_le_drive(perimetres):
        return
    autorises = {d for d, _ in perimetres if d}
    if dossier not in autorises:
        raise DriveRefuse(
            "Ce dossier n'est pas dans le périmètre ouvert à l'assistant pour "
            "ce rôle. Demande à un administrateur de l'ajouter s'il doit l'être.")
