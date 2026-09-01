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
# Ces gestes servent un tour de conversation, pas une ingestion — mais
# « parcours TOUT le Drive et fais-moi le schéma » est une demande légitime, et
# elle doit aboutir en UN appel. Les anciennes bornes (3 niveaux, 40 dossiers)
# la faisaient échouer : l'arbre revenait tronqué, le modèle relançait avec
# d'autres paramètres, et le budget d'actions du tour y passait sans réponse.
#
# Le balayage global rend ça possible SANS explosion réseau : une seule requête
# paginée ramène jusqu'à mille dossiers, structure comprise. La profondeur
# n'est donc plus une affaire de coût, seulement d'affichage.
MAX_PROFONDEUR = 20                # l'arbre COMPLET, plafonné contre les cycles
MAX_DOSSIERS_ARBRE = 3000          # au-delà, on l'écrit honnêtement
# 5 → 30 et 10 → 30 (01/09, règle de Noa : une recherche ne se bloque jamais en
# quantité). À 5 000 dossiers balayés, un Drive plus gros rendait des recherches
# et des arbres PARTIELS alors que chaque page ne coûte qu'une requête : trente
# requêtes couvrent 30 000 dossiers, la borne ne reste que contre l'infini.
MAX_PAGES_BALAYAGE = 30            # 30 × 1000 dossiers par balayage global
MAX_PAGES_FICHIERS = 30            # 30 × 1000 fichiers pour les comptes
MAX_SCHEMA_CARACTERES = 9000       # le schéma texte rendu au modèle
MAX_LOT = 5
# 200 → 1000 (01/09) : l'API accepte mille entrées par page — un aperçu qui
# disait « compte PARTIEL » sur un dossier de 300 fichiers se payait en
# crédibilité, pas en requêtes.
MAX_ENTREES = 1000         # par dossier listé, une page d'API pleine

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

# UN VIVIER DE CLIENTS, PARCE QUE `Resource` N'EST PAS SÛR ENTRE THREADS.
#
# `google-api-python-client` fait reposer chaque `Resource` sur un objet
# `httplib2.Http` unique et partagé. Deux téléchargements menés de front sur le
# MÊME client se marchent dessus sur cette connexion : la bibliothèque le
# documente, et le symptôme serait une réponse mélangée à une autre — donc un
# document dont le contenu vient d'un autre fichier. Pire qu'une lenteur.
#
# On paie donc quelques constructions supplémentaires, une fois, et chaque
# lecture menée en parallèle reçoit SON client. Le vivier a la même durée de
# vie que le client unique, et se reconstruit avec lui.
_POOL: dict = {"services": [], "expire": 0.0}
_POOL_TAILLE = 5


async def _services(n: int) -> list:
    """`n` clients Drive DISTINCTS, pour des lectures menées de front.

    Construits en parallèle : chaque construction fait un rafraîchissement OAuth
    synchrone, et les enchaîner rendrait la mise en place aussi lente que les
    lectures séquentielles qu'on cherche à supprimer.
    """
    import time
    n = max(1, min(n, _POOL_TAILLE))
    if time.monotonic() >= _POOL["expire"]:
        _POOL["services"] = []
    if len(_POOL["services"]) < n:
        from ingestion.connectors.google_drive import _build_service
        a_creer = n - len(_POOL["services"])
        _POOL["services"].extend(await asyncio.gather(
            *[asyncio.to_thread(_build_service) for _ in range(a_creer)]))
        _POOL["expire"] = time.monotonic() + _DUREE_CLIENT_S
    return _POOL["services"][:n]


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


async def _drives_nommes(service) -> list[dict]:
    """Les Drive partagés, AVEC leur nom — pas seulement leur identifiant.

    `_racines` ne gardait que les identifiants. Or les gens désignent un Drive
    partagé par son nom (« dans le Drive partagé Holding Symbiose Paysage »),
    et un Drive n'est PAS un dossier : aucune recherche `files().list` ne peut
    le retrouver, quel que soit le motif. Son nom n'existe que dans cette
    liste-ci ; le jeter rendait la formulation la plus naturelle impossible à
    résoudre.
    """
    def _appel():
        return service.drives().list(pageSize=100, fields="drives(id,name)").execute()
    try:
        return [d for d in (await asyncio.to_thread(_appel)).get("drives", [])
                if d.get("id")]
    except Exception as e:  # noqa: BLE001
        # Le compte n'a peut-être aucun Drive partagé, ou pas le droit de les
        # lister. Ce n'est pas une panne : on continue avec « Mon Drive ».
        logger.info("Drive : liste des Drive partagés indisponible (%s)", e)
        return []


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
    partages = await _drives_nommes(service)
    if partages:
        logger.info("Drive : %d Drive(s) partagé(s) trouvé(s)", len(partages))
    return ["root"] + [d["id"] for d in partages]


def _echappe(v: str) -> str:
    return v.replace("\\", "\\\\").replace("'", "\\'")


# LA CASCADE PRODUIT PARFOIS DU FRANÇAIS SANS ACCENT — c'est déjà documenté
# dans `agents/annonce.py`, et un Drive nommé « Symbiose Extérieur Concept »
# ne se retrouverait jamais si le modèle écrit « Exterieur ». On compare donc
# des noms dépouillés, des deux côtés.
_ACCENTS = str.maketrans("àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ",
                         "aaaeeeeiioouuucAAAEEEEIIOOUUUC")


def _nu(v: str) -> str:
    """Un nom réduit à ce qui compte pour le reconnaître."""
    return " ".join((v or "").translate(_ACCENTS).lower().split())


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


async def _dossiers_partages(service, nom: Optional[str] = None,
                             limite: int = 100) -> list[dict]:
    """Les dossiers « partagés avec moi », filtrés par nom si demandé.

    Ils n'ont aucun parent visible : aucune requête `in parents` ne les
    retourne, seul le corpus utilisateur avec `sharedWithMe` les connaît.
    """
    q = (f"sharedWithMe and mimeType = '{_MIME_DOSSIER}' and trashed = false"
         + (f" and name contains '{_echappe(nom)}'" if nom else ""))

    def _appel():
        return service.files().list(
            q=q, spaces="drive", fields="files(id,name)",
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

    # LE PREMIER SEGMENT PEUT ÊTRE UN DRIVE PARTAGÉ LUI-MÊME.
    #
    # Relevé en production : « dans le Drive partagé Holding Symbiose Paysage,
    # dossier Communication » → refus, avec en prime la liste ASSURANCES,
    # BANQUE, COMMUNICATION… c'est-à-dire le CONTENU de ce Drive. La résolution
    # y était donc bien arrivée, mais elle ne reconnaissait pas son nom : un
    # Drive n'est pas un dossier, aucune requête `files().list` ne le retourne,
    # et son nom ne vit que dans `drives().list`.
    #
    # On le reconnaît avant tout le reste, et « Mon Drive » avec lui. Le
    # segment consommé, la descente continue normalement dans ses dossiers.
    # Une racine NOMMÉE ferme la recherche globale : « dans tel Drive, dossier
    # Communication » désigne LE Communication de ce Drive, pas n'importe lequel.
    racine_nommee = False
    drives = await _drives_nommes(service)
    if segments and drives:
        cherche = _nu(segments[0])
        # Restreint aux Drive RÉELLEMENT ouverts à ce rôle : sans ce filtre, un
        # périmètre déclaré serait contourné en nommant le Drive entier.
        ouverts = [d for d in drives if d["id"] in racines]
        exact = [d for d in ouverts if _nu(d.get("name")) == cherche]
        partiel = [d for d in ouverts if cherche in _nu(d.get("name"))]
        choisi = exact or partiel
        # UN NOM AMBIGU NE SE TRANCHE PAS AU HASARD.
        #
        # Les Drive de l'entreprise s'appellent « Holding Symbiose Paysage »,
        # « Symbiose Extérieur Concept » et « Symbiose Paysage » : le mot
        # « Symbiose » les désigne tous les trois, et « Symbiose Paysage » est
        # contenu dans le premier. Prendre le premier venu, c'est-à-dire
        # l'ordre de l'API, enverrait silencieusement vers le Drive d'une autre
        # entité — et ces Drive porteront les droits d'accès. Un doute se dit
        # et se fait lever ; il ne se devine pas.
        if not exact and len(partiel) > 1:
            noms = ", ".join(sorted(d.get("name") or "" for d in partiel))
            raise DriveRefuse(
                f"« {segments[0]} » désigne plusieurs Drive partagés : {noms}. "
                "Reprends le nom COMPLET de celui que tu veux.")
        if choisi:
            parents = [choisi[0]["id"]]
            parcourus.append(choisi[0]["name"])
            segments = segments[1:]
            racine_nommee = True
            if not segments:
                return parents[0]

    if segments and segments[0].lower() in ("mon drive", "my drive") \
            and "root" in racines:
        parents = ["root"]
        parcourus.append("Mon Drive")
        segments = segments[1:]
        racine_nommee = True
        if not segments:
            return "root"

    # « PARTAGÉS AVEC MOI » : LE NOM QUE L'ARBORESCENCE AFFICHE DOIT MARCHER.
    #
    # Le schéma regroupe les dossiers sans parent sous une pseudo-racine
    # « Partagés avec moi (hors racines) » — mais elle n'existait que dans
    # l'AFFICHAGE. Relevé en production : le modèle recopie ce libellé tel
    # quel dans un chemin, et reçoit « aucun dossier de ce nom », avec en
    # prime une liste qui ne contient pas ce qu'il voit à l'écran. Un écran
    # qui enseigne des noms que la navigation refuse fabrique des impasses.
    #
    # Réservé au Drive entièrement ouvert (`partout`), comme la recherche
    # globale : ces dossiers vivent hors de tout périmètre déclaré.
    if segments and partout and not racine_nommee             and "partages avec moi" in _nu(segments[0]):
        parcourus.append("Partagés avec moi")
        segments = segments[1:]
        racine_nommee = True
        if not segments:
            raise DriveRefuse(
                "« Partagés avec moi » regroupe des dossiers sans parent : "
                "ajoute le nom du dossier voulu, par exemple "
                "« Partagés avec moi/NOM DU DOSSIER ».")
        nom = segments[0]
        trouves = await _dossiers_partages(service, nom)
        tous_p: list[dict] | None = None
        if not trouves:
            # Même précaution que plus bas : le filtre de l'API est sensible
            # aux accents, on rabat sur un listage où c'est nous qui comparons.
            tous_p = await _dossiers_partages(service)
            cible = _nu(nom)
            trouves = [d for d in tous_p if cible in _nu(d.get("name"))]
        if not trouves:
            if tous_p is None:
                tous_p = await _dossiers_partages(service)
            dispo = sorted({d["name"] for d in tous_p})[:25]
            raise DriveRefuse(
                f"Aucun dossier « {nom} » parmi les partagés avec moi."
                + (f" Dossiers présents : {', '.join(dispo)}." if dispo
                   else " Aucun dossier partagé visible.")
                + " Reprends le nom EXACT dans cette liste.")
        exact = [d for d in trouves if _nu(d["name"]) == _nu(nom)]
        retenu = exact or trouves
        if len({d["id"] for d in retenu}) > 1 and not exact:
            noms = ", ".join(sorted({d.get("name") or "" for d in retenu})[:10])
            raise DriveRefuse(
                f"« {nom} » désigne plusieurs dossiers partagés : {noms}. "
                "Reprends le nom COMPLET de celui que tu veux.")
        parents = [retenu[0]["id"]]
        parcourus.append(retenu[0]["name"])
        segments = segments[1:]
        if not segments:
            return parents[0]

    for rang, segment in enumerate(segments):
        trouves = await _dossiers_sous(service, parents, segment)
        tous: list[dict] | None = None
        if not trouves:
            # LE FILTRE DE L'API EST SENSIBLE AUX ACCENTS. « name contains
            # 'COMPTABILITE' » ne retourne pas « COMPTABILITÉ » : le tri se
            # fait chez Google, avant que notre comparaison dépouillée ait son
            # mot à dire. On rabat donc sur un listage complet du niveau, où
            # c'est nous qui comparons — le filtre serveur n'est qu'un
            # raccourci, jamais l'autorité.
            tous = await _dossiers_sous(service, parents)
            cible = _nu(segment)
            trouves = [d for d in tous if cible in _nu(d.get("name"))]
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
        if not trouves and rang == 0 and partout and not racine_nommee:
            trouves = await _dossiers_partout(service, segment)
        if not trouves:
            if tous is None:
                tous = await _dossiers_sous(service, parents)
            dispo = [d["name"] for d in tous]
            ou = "/".join(parcourus) if parcourus else "la racine du Drive"
            # LES DRIVE PARTAGÉS SE NOMMENT AUSSI. Le refus ne listait que des
            # DOSSIERS : quand le nom cherché était celui d'un Drive, la liste
            # proposée ne pouvait donc pas contenir la réponse, et le modèle
            # repartait en devinettes sur des noms voisins.
            autres = ""
            if not parcourus and drives:
                noms = sorted(d.get("name") or "" for d in drives if d["id"] in racines)
                if noms:
                    autres = (" Drive(s) partagé(s) disponibles, utilisables comme "
                              f"premier élément du chemin : {', '.join(noms[:15])}.")
            raise DriveRefuse(
                f"Aucun dossier « {segment} » dans {ou}. "
                + (f"Dossiers présents : {', '.join(sorted(dispo)[:25])}."
                   if dispo else "Ce niveau ne contient aucun sous-dossier.")
                + autres
                + " Reprends le nom EXACT dans l'une de ces listes.")
        # Une correspondance exacte (accents et casse mis de côté) l'emporte
        # sur un simple « contient » : « Communication » et « Communication
        # interne » sortent tous deux, et c'est le premier qu'on veut.
        exact = [d for d in trouves if _nu(d["name"]) == _nu(segment)]
        # MÊME RÈGLE QUE POUR LES DRIVE : un nom qui désigne plusieurs dossiers
        # frères ne se tranche pas au hasard. « COMPTABILITÉ » et
        # « COMPTABILITE 2026 » côte à côte enverraient vers l'un ou l'autre
        # selon l'ordre de l'API, sans que personne ne puisse le prévoir.
        if not exact and len(trouves) > 1:
            noms = ", ".join(sorted(d["name"] for d in trouves)[:15])
            ou = "/".join(parcourus) if parcourus else "la racine du Drive"
            raise DriveRefuse(
                f"« {segment} » désigne plusieurs dossiers dans {ou} : {noms}. "
                "Reprends le nom COMPLET de celui que tu veux.")
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


async def _balayer_dossiers(service) -> tuple[dict, bool]:
    """TOUS les dossiers du Drive (id → nom, parents), en quelques requêtes.

    C'est le collecteur qui rend « parcours tout le Drive » possible en UN
    appel : une requête paginée ramène MILLE dossiers avec leur structure,
    là où le parcours dossier-par-dossier payait un aller-retour réseau par
    dossier. Trois cents dossiers : une requête au lieu de trois cents.

    RÉSERVÉ AU DRIVE ENTIÈREMENT OUVERT. Avec des périmètres déclarés, un
    balayage global ramènerait les noms des dossiers interdits — et un dossier
    « Licenciement Untel » dit déjà l'essentiel. Le chemin cloisonné passe par
    `_enfants_par_lots`, qui ne sort jamais des racines autorisées.
    """
    dossiers: dict[str, dict] = {}
    jeton = None
    for _ in range(MAX_PAGES_BALAYAGE):
        def _appel(jeton=jeton):
            return service.files().list(
                q=f"mimeType = '{_MIME_DOSSIER}' and trashed = false",
                spaces="drive", corpora="allDrives",
                includeItemsFromAllDrives=True, supportsAllDrives=True,
                fields="nextPageToken, files(id,name,parents)",
                pageSize=1000, pageToken=jeton,
            ).execute()
        resp = await asyncio.to_thread(_appel)
        for f in resp.get("files", []):
            dossiers[f["id"]] = {"nom": f.get("name"),
                                 "parents": f.get("parents") or []}
        jeton = resp.get("nextPageToken")
        if not jeton:
            break
    return dossiers, bool(jeton)


async def _compter_fichiers(service) -> tuple[dict, bool]:
    """Nombre de fichiers et octets PAR dossier parent, en quelques requêtes.

    Même logique de balayage que les dossiers : on ne demande que `parents` et
    `size`, mille fichiers par page. Un Drive qui en contient davantage que le
    plafond rend des comptes PARTIELS — et le drapeau le dit, pour que le
    schéma ne présente jamais un compte tronqué comme un compte exact.
    """
    comptes: dict[str, list] = {}
    jeton = None
    for _ in range(MAX_PAGES_FICHIERS):
        def _appel(jeton=jeton):
            return service.files().list(
                q=f"mimeType != '{_MIME_DOSSIER}' and trashed = false",
                spaces="drive", corpora="allDrives",
                includeItemsFromAllDrives=True, supportsAllDrives=True,
                fields="nextPageToken, files(parents,size)",
                pageSize=1000, pageToken=jeton,
            ).execute()
        resp = await asyncio.to_thread(_appel)
        for f in resp.get("files", []):
            for p in (f.get("parents") or []):
                c = comptes.setdefault(p, [0, 0])
                c[0] += 1
                c[1] += int(f.get("size") or 0)
        jeton = resp.get("nextPageToken")
        if not jeton:
            break
    return comptes, bool(jeton)


async def _enfants_par_lots(service, parents: list[str]) -> dict:
    """Les enfants (dossiers ET fichiers) de tous ces parents, par paquets.

    Le chemin CLOISONNÉ de l'arborescence : chaque requête porte jusqu'à
    quinze parents en `or`, donc un niveau entier de l'arbre se lit en une
    poignée de requêtes — sans jamais interroger quoi que ce soit hors des
    dossiers passés en argument. `parents` sur chaque résultat dit à quel
    parent le rattacher.
    """
    resultat = {p: {"dossiers": [], "fichiers": 0, "octets": 0, "tronque": False}
                for p in parents}
    for i in range(0, len(parents), 15):
        paquet = parents[i:i + 15]
        ou = " or ".join(f"'{_echappe(p)}' in parents" for p in paquet)
        q = f"({ou}) and trashed = false"
        jeton = None
        for _ in range(3):
            def _appel(jeton=jeton):
                return service.files().list(
                    q=q, spaces="drive",
                    fields="nextPageToken, files(id,name,mimeType,parents,size)",
                    corpora="allDrives", includeItemsFromAllDrives=True,
                    supportsAllDrives=True, pageSize=1000, pageToken=jeton,
                ).execute()
            resp = await asyncio.to_thread(_appel)
            for f in resp.get("files", []):
                for p in (f.get("parents") or []):
                    if p not in resultat:
                        continue
                    if f.get("mimeType") == _MIME_DOSSIER:
                        resultat[p]["dossiers"].append(
                            {"id": f["id"], "nom": f.get("name")})
                    else:
                        resultat[p]["fichiers"] += 1
                        resultat[p]["octets"] += int(f.get("size") or 0)
            jeton = resp.get("nextPageToken")
            if not jeton:
                break
        if jeton:
            for p in paquet:
                resultat[p]["tronque"] = True
    return resultat


def _rendre_schema(racines: list[dict], profondeur_max: int) -> tuple[str, int]:
    """L'arbre en texte, prêt à afficher — et la profondeur réellement rendue.

    UN SCHÉMA, PAS UN JSON. Le résultat repart vers le modèle avec un plafond
    de caractères : un arbre en JSON verbeux se faisait couper au milieu, et le
    modèle relançait l'exploration « car le résultat précédent était tronqué »
    — c'est mot pour mot ce qu'il a répondu. Le texte indenté porte la même
    information pour un cinquième du poids, et se recopie tel quel dans une
    réponse.

    Si même le texte déborde, on RÉDUIT LA PROFONDEUR D'AFFICHAGE, jamais la
    vérité : les niveaux repliés sont comptés et annoncés, pas perdus.
    """
    def _ligne(n: dict) -> str:
        bouts = []
        if n.get("sous_dossiers_total"):
            bouts.append(f"{n['sous_dossiers_total']} dossiers")
        if n.get("fichiers"):
            bouts.append(f"{n['fichiers']} fichiers")
        if n.get("cycle"):
            bouts.append("déjà détaillé plus haut")
        if n.get("tronque"):
            bouts.append("liste partielle")
        return (n.get("nom") or "?") + (f"  ({', '.join(bouts)})" if bouts else "")

    def _rendre(noeuds: list[dict], prefixe: str, niveau: int,
                limite: int, lignes: list[str]) -> int:
        """Rend un niveau ; renvoie le nombre de dossiers REPLIÉS (non montrés)."""
        replies = 0
        for i, n in enumerate(noeuds):
            dernier = i == len(noeuds) - 1
            lignes.append(prefixe + ("└─ " if dernier else "├─ ") + _ligne(n))
            enfants = n.get("enfants") or []
            if not enfants:
                continue
            if niveau + 1 >= limite:
                replies += n.get("sous_dossiers_total") or len(enfants)
                continue
            suite = prefixe + ("   " if dernier else "│  ")
            replies += _rendre(enfants, suite, niveau + 1, limite, lignes)
        return replies

    for limite in range(profondeur_max, 0, -1):
        lignes: list[str] = []
        replies = 0
        for r in racines:
            lignes.append(_ligne(r))
            replies += _rendre(r.get("enfants") or [], "", 1, limite, lignes)
        schema = "\n".join(lignes)
        if len(schema) <= MAX_SCHEMA_CARACTERES or limite == 1:
            if replies:
                schema += (f"\n… détail limité à {limite} niveau(x) : "
                           f"{replies} sous-dossier(s) repliés, comptés ci-dessus.")
            return schema, limite
    return "", 0


def _assembler(racines: list[dict], catalogue: dict, comptes: dict) -> int:
    """Monte la forêt depuis le balayage global. Rend le nombre de dossiers.

    Anti-cycle GLOBAL : un dossier à plusieurs parents (héritage de l'ancien
    Drive) n'est détaillé qu'une fois ; les autres occurrences le nomment avec
    la marque « déjà détaillé plus haut ». Sans cela, deux dossiers qui se
    référencent feraient boucler l'assemblage.
    """
    enfants_de: dict[str, list[str]] = {}
    for did, d in catalogue.items():
        for p in d["parents"]:
            enfants_de.setdefault(p, []).append(did)

    vus: set[str] = set()
    total = 0

    def _noeud(did: str, nom: str, niveau: int) -> dict:
        nonlocal total
        total += 1
        n = {"nom": nom, "enfants": [],
             "fichiers": comptes.get(did, [0, 0])[0],
             "octets": comptes.get(did, [0, 0])[1]}
        if did in vus:
            n["cycle"] = True
            return n
        vus.add(did)
        if niveau >= MAX_PROFONDEUR or total > MAX_DOSSIERS_ARBRE:
            n["sous_dossiers_total"] = len(enfants_de.get(did, []))
            return n
        ids = sorted(enfants_de.get(did, []),
                     key=lambda x: (catalogue.get(x, {}).get("nom") or "").lower())
        n["enfants"] = [_noeud(x, catalogue.get(x, {}).get("nom") or "?", niveau + 1)
                        for x in ids]
        n["sous_dossiers_total"] = len(ids)
        return n

    for r in racines:
        base = _noeud(r["id"], r["nom"], 0)
        r.update(base)
    return total


async def arborescence(dossier: Optional[str] = None, profondeur: int = 0,
                       perimetres: Optional[list] = None) -> dict:
    """L'arbre — COMPLET si on ne précise rien — en UN appel.

    « Parcours tous les dossiers et sous-dossiers du Drive et fais-moi un
    schéma » doit aboutir ICI, en une action. L'ancienne version exigeait un
    dossier de départ, s'arrêtait à trois niveaux et quarante dossiers : le
    modèle relançait avec d'autres paramètres jusqu'à épuiser son budget
    d'actions, sans jamais rendre le schéma.

    Deux collecteurs, choisis selon le cloisonnement :
      - Drive entièrement ouvert : BALAYAGE GLOBAL, une requête par millier de
        dossiers, Drive partagés compris — la structure entière en quelques
        secondes.
      - périmètres déclarés : descente PAR NIVEAUX, quinze parents par
        requête, sans jamais interroger hors des racines autorisées.

    Le résultat porte `schema` : l'arbre en texte. La couche skill le
    transforme en bloc d'écran mécanique (`skills/affichage.py`).
    """
    import time as _t
    debut = _t.monotonic()
    perimetres = perimetres or []
    service = await _service()
    profondeur = min(int(profondeur), MAX_PROFONDEUR) if profondeur else MAX_PROFONDEUR
    profondeur = max(1, profondeur)

    if _tout_le_drive(perimetres):
        catalogue, dossiers_partiels = await _balayer_dossiers(service)
        comptes, fichiers_partiels = await _compter_fichiers(service)

        # Les racines : Mon Drive (id réel, pas l'alias) et chaque Drive partagé.
        def _racine_reelle():
            return service.files().get(fileId="root", fields="id").execute()
        try:
            mon_drive = (await asyncio.to_thread(_racine_reelle)).get("id")
        except Exception:  # noqa: BLE001 - compte de service sans « Mon Drive »
            mon_drive = None
        racines = [{"id": mon_drive, "nom": "Mon Drive"}] if mon_drive else []
        try:
            def _drives():
                return service.drives().list(
                    pageSize=100, fields="drives(id,name)").execute()
            for d in (await asyncio.to_thread(_drives)).get("drives", []):
                racines.append({"id": d["id"],
                                "nom": f"Drive partagé « {d.get('name')} »"})
        except Exception as e:  # noqa: BLE001
            logger.info("Drive : liste des Drive partagés indisponible (%s)", e)

        # Un dossier précis ? On réduit la forêt à SON sous-arbre.
        if dossier:
            vise = await _resoudre(service, dossier, [r["id"] for r in racines],
                                   partout=True)
            nom = catalogue.get(vise, {}).get("nom") or dossier
            racines = [{"id": vise, "nom": nom}]

        # Les dossiers « partagés avec moi » n'ont aucun parent visible : sans
        # cette racine de rattachement, ils disparaissaient du schéma alors
        # qu'ils sont bien là.
        if not dossier:
            ids_racines = {r["id"] for r in racines}
            orphelins = [did for did, d in catalogue.items()
                         if not any(p in catalogue or p in ids_racines
                                    for p in d["parents"])]
            if orphelins:
                pseudo = "__orphelins__"
                for did in orphelins:
                    catalogue[did]["parents"] = [pseudo]
                racines.append({"id": pseudo, "nom": "Partagés avec moi (hors racines)"})

        total = _assembler(racines, catalogue, comptes)
        schema, rendu = _rendre_schema(racines, profondeur)
        complet = not dossiers_partiels and total <= MAX_DOSSIERS_ARBRE
        total_fichiers = sum(c[0] for c in comptes.values())

        sortie = {
            "schema": schema,
            "dossiers_total": len(catalogue),
            "fichiers_total": total_fichiers,
            "profondeur_affichee": rendu,
            "complet": complet,
            "duree_s": round(_t.monotonic() - debut, 1),
        }
        if complet and not fichiers_partiels:
            sortie["note"] = (
                "ARBORESCENCE COMPLÈTE : tous les dossiers y sont, comptes "
                "exacts. Elle est déjà affichée à l'écran. Ne relance PAS "
                "l'exploration, il n'y a rien de plus à trouver.")
        else:
            morceaux = []
            if dossiers_partiels or total > MAX_DOSSIERS_ARBRE:
                morceaux.append(
                    f"le Drive dépasse {MAX_PAGES_BALAYAGE * 1000} dossiers, "
                    "l'arbre s'arrête là")
            if fichiers_partiels:
                morceaux.append(
                    f"plus de {MAX_PAGES_FICHIERS * 1000} fichiers : les comptes "
                    "de fichiers sont partiels")
            sortie["note"] = ("Arborescence rendue, mais " + " ; ".join(morceaux)
                              + ". Dis-le tel quel : ne présente pas ces "
                                "nombres comme exhaustifs.")
        return sortie

    # ── Périmètres déclarés : descente par niveaux, sans balayage global ──
    racines_ids = [d for d, _ in perimetres if d]
    if dossier:
        vise = await _resoudre(service, dossier, racines_ids, partout=False)
        _garde_perimetre(vise, perimetres)
        racines = [{"id": vise, "nom": dossier}]
    else:
        if not racines_ids:
            raise DriveRefuse(
                "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle. "
                "Un administrateur doit renseigner GOOGLE_DRIVE_PERIMETRES.")
        racines = [{"id": rid, "nom": rid} for rid in racines_ids]

    par_id = {r["id"]: r for r in racines}
    for r in racines:
        r.update({"enfants": [], "fichiers": 0, "octets": 0})
    niveau_courant = [r["id"] for r in racines]
    total = len(racines)
    partiel = False
    for niveau in range(profondeur):
        if not niveau_courant:
            break
        if total >= MAX_DOSSIERS_ARBRE:
            partiel = True
            break
        infos = await _enfants_par_lots(service, niveau_courant)
        prochain: list[str] = []
        for pid in niveau_courant:
            noeud = par_id[pid]
            info = infos.get(pid) or {}
            noeud["fichiers"] = info.get("fichiers", 0)
            noeud["octets"] = info.get("octets", 0)
            noeud["tronque"] = info.get("tronque", False)
            sous = sorted(info.get("dossiers") or [],
                          key=lambda d: (d.get("nom") or "").lower())
            noeud["sous_dossiers_total"] = len(sous)
            for sd in sous:
                enfant = {"nom": sd["nom"], "enfants": [], "fichiers": 0,
                          "octets": 0}
                noeud["enfants"].append(enfant)
                par_id[sd["id"]] = enfant
                prochain.append(sd["id"])
                total += 1
        niveau_courant = prochain
    if niveau_courant:
        partiel = True

    schema, rendu = _rendre_schema(racines, profondeur)
    sortie = {
        "schema": schema,
        "dossiers_total": total,
        "profondeur_affichee": rendu,
        "complet": not partiel,
        "duree_s": round(_t.monotonic() - debut, 1),
    }
    sortie["note"] = (
        "ARBORESCENCE COMPLÈTE du périmètre autorisé. Elle est déjà affichée "
        "à l'écran : ne relance pas l'exploration."
        if not partiel else
        f"Arbre partiel (plafond de {MAX_DOSSIERS_ARBRE} dossiers ou de "
        "profondeur atteint) : précise un sous-dossier pour le détail. Ne le "
        "présente pas comme exhaustif.")
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

    # LES CINQ FICHIERS SE LISENT DE FRONT, PLUS L'UN APRÈS L'AUTRE.
    #
    # Mesuré dans la trace du 17/08 : 59,5 secondes pour UN appel de ce geste.
    # Chaque fichier demande un téléchargement puis une extraction de texte, dix
    # secondes environ, et ils s'enchaînaient. Menés ensemble, l'appel dure le
    # temps du plus lent au lieu de leur somme.
    #
    # `return_exceptions` : un fichier illisible ne doit pas emporter les quatre
    # autres. Il rejoint la liste des ignorés, comme avant, et l'échec est
    # journalisé plutôt qu'avalé — c'est en le lisant qu'on saura si un format
    # résiste.
    cibles = candidats[:limite]
    lus, ignores = [], []
    if cibles:
        clients = await _services(len(cibles))
        textes = await asyncio.gather(*[
            asyncio.to_thread(_download_text, clients[i % len(clients)], f)
            for i, f in enumerate(cibles)
        ], return_exceptions=True)
        for f, r in zip(cibles, textes):
            if isinstance(r, BaseException):
                logger.warning("Drive : lecture de « %s » échouée : %s", f.get("name"), r)
                ignores.append(f.get("name"))
            elif r:
                lus.append({"nom": f.get("name"), "contenu": r[:6000]})
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


MAX_TROUVAILLES = 40               # dossiers ou fichiers rendus par recherche


async def chercher(motif: str, perimetres: Optional[list] = None,
                   page: int = 1) -> dict:
    """Dossiers ET fichiers dont le NOM porte le motif, à TOUTES les profondeurs.

    Demande de Noa du 01/09 : quand une information sur un client n'est pas en
    mémoire d'entreprise, l'assistant doit « instinctivement » chercher si un
    dossier ou un fichier du Drive PARLE de ce client — pas seulement au
    premier niveau, pas borné à quelques entrées : partout, en se fiant
    d'abord aux NOMS, puis en proposant d'aller plus loin.

    Deux voies, comme l'arborescence :
      - Drive entièrement ouvert : le CATALOGUE des dossiers (balayage global)
        est filtré CHEZ NOUS (`_nu`), donc insensible aux accents, et chaque
        trouvaille porte son CHEMIN reconstruit ; les fichiers passent par
        `name contains` (toutes profondeurs par construction — le Drive est
        plat, seuls les `parents` font l'arbre).
      - périmètres déclarés : descente par niveaux SANS sortir des racines
        (mêmes garanties que l'arborescence cloisonnée), puis les fichiers
        cherchés dans TOUS les dossiers descendus, par lots de quinze parents.

    Le filtre `name contains` de l'API est sensible aux accents (leçon de
    `_resoudre`) : pour les fichiers, on essaie le motif entier PUIS son mot
    le plus long — et quand rien ne sort, on le dit sans conclure à l'absence.
    """
    motif = (motif or "").strip()
    if not motif:
        raise DriveRefuse("Donne le nom à chercher (client, chantier, fichier).")
    perimetres = perimetres or []
    if not perimetres:
        raise DriveRefuse(
            "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle.")
    service = await _service()
    cible = _nu(motif)
    jetons = [t for t in cible.split() if len(t) >= 3]

    def _correspond(nom) -> bool:
        nu = _nu(nom or "")
        return bool(nu) and (cible in nu or (jetons and all(t in nu for t in jetons)))

    trouves: list[dict] = []
    partiel = False

    if _tout_le_drive(perimetres):
        catalogue, partiel = await _balayer_dossiers(service)
        drives = {d["id"]: d.get("name") for d in await _drives_nommes(service)}

        def _chemin(did: Optional[str]) -> str:
            morceaux: list[str] = []
            cour = did
            for _ in range(MAX_PROFONDEUR):
                if not cour:
                    break
                if cour in drives:
                    morceaux.append(str(drives[cour]))
                    break
                d = catalogue.get(cour)
                if not d:
                    break
                morceaux.append(str(d.get("nom") or ""))
                parents = d.get("parents") or []
                cour = parents[0] if parents else None
            return "/".join(reversed([m for m in morceaux if m]))

        for did, d in catalogue.items():
            if _correspond(d.get("nom")):
                trouves.append({"nom": d.get("nom"), "chemin": _chemin(did),
                                "dossier": True})

        # Les fichiers : motif entier d'abord ; s'il est composé et que rien ne
        # sort, son mot le plus long — « Davy SAINT LAURENT » ne matche aucun
        # nom de devis, « SAINT LAURENT » si.
        essais = [motif]
        if len(jetons) > 1:
            essais.append(max(jetons, key=len))
        vus: set[str] = set()
        for essai in essais:
            if any(not t["dossier"] for t in trouves):
                break

            def _appel(nom=essai):
                return service.files().list(
                    q=(f"mimeType != '{_MIME_DOSSIER}' and trashed = false "
                       f"and name contains '{_echappe(nom)}'"),
                    spaces="drive", corpora="allDrives",
                    includeItemsFromAllDrives=True, supportsAllDrives=True,
                    fields="files(id,name,parents,modifiedTime)",
                    pageSize=200,
                ).execute()
            try:
                for f in (await asyncio.to_thread(_appel)).get("files", []):
                    if f["id"] in vus:
                        continue
                    vus.add(f["id"])
                    parents = f.get("parents") or []
                    trouves.append({"nom": f.get("name"),
                                    "chemin": _chemin(parents[0] if parents else None),
                                    "dossier": False,
                                    "modifie_le": f.get("modifiedTime")})
            except Exception as e:  # noqa: BLE001
                logger.warning("Drive : recherche fichiers « %s » échouée : %s", essai, e)
    else:
        # ── Cloisonné : on descend, on ne sort JAMAIS des racines ─────────
        chemins: dict[str, str] = {}
        niveau = [d for d, _ in perimetres if d]
        total = 0
        for _ in range(MAX_PROFONDEUR):
            if not niveau or total > MAX_DOSSIERS_ARBRE:
                partiel = partiel or bool(niveau)
                break
            infos = await _enfants_par_lots(service, niveau)
            prochain: list[str] = []
            for pid in niveau:
                for sd in (infos.get(pid) or {}).get("dossiers", []):
                    chemin = (chemins.get(pid, "") + "/" + str(sd.get("nom") or "")).strip("/")
                    chemins[sd["id"]] = chemin
                    total += 1
                    if _correspond(sd.get("nom")):
                        trouves.append({"nom": sd.get("nom"), "chemin": chemin,
                                        "dossier": True})
                    prochain.append(sd["id"])
            niveau = prochain

        ids = ([d for d, _ in perimetres if d] + list(chemins))[:1000]
        for i in range(0, len(ids), 15):
            paquet = ids[i:i + 15]
            ou = " or ".join(f"'{_echappe(p)}' in parents" for p in paquet)

            def _appel(requete=(f"({ou}) and mimeType != '{_MIME_DOSSIER}' "
                                f"and trashed = false "
                                f"and name contains '{_echappe(motif)}'")):
                return service.files().list(
                    q=requete, spaces="drive", corpora="allDrives",
                    includeItemsFromAllDrives=True, supportsAllDrives=True,
                    fields="files(id,name,parents,modifiedTime)",
                    pageSize=MAX_TROUVAILLES,
                ).execute()
            try:
                for f in (await asyncio.to_thread(_appel)).get("files", []):
                    parents = f.get("parents") or []
                    trouves.append({"nom": f.get("name"),
                                    "chemin": chemins.get(parents[0] if parents else "", ""),
                                    "dossier": False,
                                    "modifie_le": f.get("modifiedTime")})
            except Exception as e:  # noqa: BLE001
                logger.warning("Drive : recherche cloisonnée « %s » échouée : %s", motif, e)

    # L'exact d'abord, puis le chemin court : le dossier « Davy SAINT LAURENT »
    # doit précéder « Anciens clients/2019/SAINT LAURENT ancien devis ».
    trouves.sort(key=lambda t: (0 if _nu(t.get("nom")) == cible else 1,
                                not t.get("dossier"),
                                len(t.get("chemin") or ""),
                                _nu(t.get("nom"))))
    # PAGINÉ, JAMAIS COUPÉ (01/09, règle de Noa : une recherche ne se bloque
    # pas en quantité) : la page demandée est rendue, le compte total est dit,
    # et la suite s'obtient en rappelant avec `page` suivante.
    nombre = len(trouves)
    page = max(1, int(page or 1))
    pages = max(1, -(-nombre // MAX_TROUVAILLES))
    debut = (page - 1) * MAX_TROUVAILLES
    sortie: dict = {"motif": motif, "nombre": nombre, "page": page,
                    "pages": pages,
                    "resultats": trouves[debut:debut + MAX_TROUVAILLES]}
    if page < pages:
        sortie["pour_continuer"] = (f"{nombre} correspondances au total : "
                                    f"rappelle avec page={page + 1} pour la suite.")
    if partiel:
        sortie["note"] = ((sortie.get("note") or "") + " Recherche PARTIELLE : "
                          "le Drive dépasse le plafond de balayage — une absence "
                          "n'est pas prouvée.").strip()
    if not nombre:
        sortie["note"] = ((sortie.get("note") or "") + " Aucun nom ne correspond. "
                          "Le filtre fichiers est sensible aux accents : un seul "
                          "mot du nom, ou une autre orthographe, peut suffire. "
                          "Une recherche vide ne prouve pas l'absence.").strip()
    return sortie


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


# ═══════════════════════════════════════════════════════════════════════════
#  LES PHOTOS D'UN CHANTIER, MONTRÉES DANS LE CHAT
# ═══════════════════════════════════════════════════════════════════════════
#
# « Trouve-moi trois chantiers similaires et MONTRE-MOI les photos. » On savait
# retrouver les chantiers (la recherche documentaire les décrit très bien), et
# on ne savait pas montrer une seule image : `rechercher_documents` rend du
# texte, `ouvrir` refuse les formats non textuels (« ce format ne se lit pas
# ici »), et aucun bloc d'écran n'affichait un fichier du Drive.
#
# Or tout était déjà là, à un maillon près. Le dépôt de visuels
# (`visuels/depot.py`) range n'importe quels octets sous une clé et les sert
# par `/api/visuels/{clé}` avec le jeton de session ; le bloc `visuel` sait
# afficher une planche d'images téléchargeables. Il manquait le geste qui va
# CHERCHER les photos et les dépose. C'est celui-ci.
#
# CE QU'IL NE FAIT PAS : sortir du périmètre autorisé (même résolution de
# dossier que partout ailleurs ici), ni ramener autre chose que des images, ni
# télécharger un fichier énorme. Une photo de chantier fait deux à cinq méga ;
# au-delà, c'est autre chose, et on ne la prend pas.

MAX_PHOTOS = 12
MAX_OCTETS_PHOTO = 12 * 1024 * 1024
_MIMES_IMAGE = ("image/jpeg", "image/png", "image/webp", "image/heic",
                "image/heif", "image/gif")


async def photos(dossier: Optional[str] = None, motif: Optional[str] = None,
                 limite: int = 6, perimetres: Optional[list] = None) -> dict:
    """Les photos d'un dossier du Drive, rangées au dépôt et prêtes à l'écran."""
    perimetres = perimetres or []
    if not perimetres:
        raise DriveRefuse(
            "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle.")
    limite = max(1, min(int(limite or 6), MAX_PHOTOS))

    service = await _service()
    conditions = ["trashed = false",
                  "(" + " or ".join(f"mimeType = '{m}'" for m in _MIMES_IMAGE) + ")"]
    if motif:
        conditions.append(f"name contains '{_echappe(motif)}'")

    # Le dossier demandé, résolu comme partout ailleurs (nom OU chemin), sinon
    # les périmètres autorisés. On ne cherche jamais hors de ces bornes.
    parents: list[str] = []
    if dossier:
        racines = await _racines(service)
        resolu = await _resoudre(service, dossier, racines, perimetres)
        if resolu:
            parents = [resolu] if isinstance(resolu, str) else list(resolu)
    if not parents and not _tout_le_drive(perimetres):
        parents = [d for d, _n in perimetres if d]

    requetes = ([f"'{p}' in parents and " + " and ".join(conditions) for p in parents]
                if parents else [" and ".join(conditions)])

    trouves: list[dict] = []
    for q in requetes:
        def _appel(requete=q):
            return service.files().list(
                q=requete, spaces="drive",
                fields="files(id,name,mimeType,size,modifiedTime)",
                corpora="allDrives", includeItemsFromAllDrives=True,
                supportsAllDrives=True,
                orderBy="modifiedTime desc", pageSize=limite * 2,
            ).execute()
        try:
            trouves.extend((await asyncio.to_thread(_appel)).get("files", []))
        except Exception as e:  # noqa: BLE001
            logger.warning("Drive : recherche de photos échouée : %s", e)

    if not trouves:
        ou = f"« {dossier} »" if dossier else "les dossiers ouverts"
        return {
            "photos": [], "nombre": 0,
            "message": (f"Aucune image dans {ou}"
                        + (f" dont le nom contienne « {motif} »" if motif else "")
                        + ". Ce n'est pas une preuve qu'il n'y en a pas : elles "
                          "peuvent être ailleurs, ou hors du périmètre autorisé."),
        }

    # Dédoublonnage par identifiant : un même fichier peut remonter de deux
    # périmètres qui se chevauchent.
    uniques, vus = [], set()
    for f in trouves:
        if f["id"] not in vus:
            vus.add(f["id"])
            uniques.append(f)

    from visuels.depot import deposer_octets
    images, trop_gros = [], 0
    for f in uniques:
        if len(images) >= limite:
            break
        try:
            if int(f.get("size") or 0) > MAX_OCTETS_PHOTO:
                trop_gros += 1
                continue
            octets = await asyncio.to_thread(
                lambda fid=f["id"]: service.files().get_media(fileId=fid).execute())
            cle = deposer_octets(octets, f.get("mimeType") or "image/jpeg")
            if cle:
                images.append({"cle": cle, "legende": f.get("name") or "photo",
                               "modifie_le": f.get("modifiedTime")})
        except Exception as e:  # noqa: BLE001 — une photo illisible n'arrête pas les autres
            logger.info("Drive : photo « %s » non récupérée : %s", f.get("name"), e)

    if not images:
        return {"photos": [], "nombre": 0,
                "message": ("Des images existent mais aucune n'a pu être "
                            "récupérée (format, taille ou droits).")}

    return {
        "photos": images,
        "nombre": len(images),
        "disponibles": len(uniques),
        "trop_volumineuses": trop_gros or None,
        "bloc_ui": {"type": "visuel",
                    "titre": (dossier or motif or "Photos du Drive")[:80],
                    "images": [{"cle": i["cle"], "legende": i["legende"]}
                               for i in images]},
    }


# ═══════════════════════════════════════════════════════════════════════════
#  LE DÉPÔT SUR LE DRIVE — l'assistant sait enfin REMETTRE un document
# ═══════════════════════════════════════════════════════════════════════════
#
# Le pendant du dépôt NAS du projet jumeau, demandé par Noa le 30/08 : un
# document produit par l'atelier doit pouvoir se ranger dans le classement de
# l'entreprise, pas seulement se télécharger depuis le chat. Le commentaire de
# `SATISFAIT_PAR` (agents/annonce.py) attendait ce geste depuis le portage.
#
# Deux principes, hérités du NAS parce qu'ils y ont été payés :
#   · on ne dépose QUE des documents produits ICI, et seulement ceux de la
#     personne — téléverser un chemin arbitraire ferait de ce skill un moyen
#     d'exfiltration ;
#   · JAMAIS d'écrasement : un nom déjà pris est un refus, pas un remplacement.
# Et un troisième, propre au Drive : l'ÉCRITURE a son propre client
# (`_build_service_ecriture`), la lecture garde son scope minimal.


def _nom_avec_extension(nom: Optional[str], entete: dict) -> str:
    """Le nom du fichier déposé PORTE toujours son vrai format.

    Copié du NAS, où la leçon a été payée : « appelle-le test 2 » a produit un
    .docx sans extension, parfaitement valide et inutilisable sous Windows.
    L'extension ne dépend pas de l'humeur du modèle — le code sait dans quel
    format le fichier a réellement été rendu, c'est lui qui la garantit. Une
    extension MENTEUSE est corrigée ; un point qui ne désigne aucun format
    connu (« note.v2 ») fait partie du nom et n'est pas touché.
    """
    from bureautique.modele import FORMATS
    format_reel = (entete.get("format") or "docx").lower()
    titre = (nom or "").strip() or f"{entete.get('titre', 'document')}"
    racine_nom, point, extension = titre.rpartition(".")
    if point and extension.lower() in FORMATS:
        if extension.lower() != format_reel:
            return f"{racine_nom}.{format_reel}"
        return titre
    return f"{titre}.{format_reel}"


async def deposer(dossier: str, nom: str, contenu: bytes,
                  perimetres: Optional[list] = None) -> dict:
    """Dépose un fichier dans un dossier du Drive. ÉCRITURE — n'écrase jamais.

    Le dossier se résout par NOM, comme partout ailleurs, et DANS le périmètre
    autorisé : déposer n'ouvre pas plus de portes que lire.
    """
    dossier = (dossier or "").strip()
    nom = (nom or "").strip()
    if not dossier or not nom:
        raise DriveRefuse("Il faut le dossier de destination et le nom du fichier.")
    if not contenu:
        raise DriveRefuse("Le fichier à déposer est vide : rien n'a été envoyé.")
    perimetres = perimetres or []
    if not perimetres:
        raise DriveRefuse(
            "Aucun dossier du Drive n'est ouvert à l'assistant pour ce rôle : "
            "le dépôt est impossible. Ce n'est pas un Drive vide : dis-le tel quel.")

    service = await _service()
    racines = ([d for d, _ in perimetres if d]
               or (await _racines(service) if _tout_le_drive(perimetres) else []))
    cible = await _resoudre(service, dossier, racines,
                            partout=_tout_le_drive(perimetres))
    _garde_perimetre(cible, perimetres)

    # JAMAIS d'écrasement. Le Drive accepte deux fichiers du même nom dans un
    # même dossier — c'est pire qu'un écrasement : deux « devis.docx » côte à
    # côte, personne ne sait lequel fait foi. Même règle que le NAS : refus.
    def _existe():
        return service.files().list(
            q=(f"'{cible}' in parents and trashed=false and name='{_echappe(nom)}'"),
            spaces="drive", fields="files(id)", corpora="allDrives",
            includeItemsFromAllDrives=True, supportsAllDrives=True, pageSize=1,
        ).execute()
    if (await asyncio.to_thread(_existe)).get("files"):
        raise DriveRefuse(
            f"Un fichier nommé « {nom} » existe déjà dans ce dossier : rien "
            "n'a été écrasé. Donne un autre nom pour déposer celui-ci.")

    import io
    import mimetypes
    mime = mimetypes.guess_type(nom)[0] or "application/octet-stream"
    from googleapiclient.http import MediaIoBaseUpload
    from ingestion.connectors.google_drive import _build_service_ecriture
    ecriture = await asyncio.to_thread(_build_service_ecriture)

    def _envoi():
        media = MediaIoBaseUpload(io.BytesIO(contenu), mimetype=mime)
        return ecriture.files().create(
            body={"name": nom, "parents": [cible]}, media_body=media,
            fields="id,name,webViewLink", supportsAllDrives=True,
        ).execute()
    try:
        cree = await asyncio.to_thread(_envoi)
    except Exception as e:  # noqa: BLE001 — l'API Google lève ses propres types
        texte = str(e)
        if "insufficient" in texte.lower() or "403" in texte:
            raise DriveRefuse(
                "Le Drive refuse l'ÉCRITURE : l'accès configuré est en lecture "
                "seule. Un administrateur doit rejouer le consentement Google "
                "(scripts/google_consentement.py) ou donner au compte de "
                "service le rôle « Gestionnaire de contenu » sur ce Drive.") from e
        raise DriveRefuse(f"Le dépôt a échoué : {texte[:200]}") from e

    logger.info("Drive : « %s » déposé dans %s (%d octets)", nom, cible, len(contenu))
    return {
        "depose": True,
        "nom": cree.get("name") or nom,
        "id": cree.get("id"),
        "dossier": dossier,
        "lien": cree.get("webViewLink"),
        "octets": len(contenu),
        "message_final": f"« {nom} » est déposé dans « {dossier} » sur le Drive.",
    }


async def deposer_document(document_id: str, dossier: str, proprietaire: str,
                           nom: Optional[str] = None,
                           perimetres: Optional[list] = None) -> dict:
    """Finalise un document en cours et le dépose sur le Drive, en un geste.

    Même architecture que le serveur de fichiers du projet jumeau, où la
    chaîne en deux gestes cassait : sans l'identifiant sous les yeux, le
    modèle en inventait un, l'ajout était refusé, et il rouvrait un document
    en boucle. `proprietaire` vient du skill, qui seul connaît l'utilisateur —
    un document n'appartient qu'à celui qui l'a ouvert, et composer deux
    gestes ne compose pas les droits.

    EFFET EXTERNE : le dépôt écrit dans le classement de l'entreprise, la
    validation humaine reste obligatoire.
    """
    from bureautique.atelier import terminer, chemin_fichier

    if not (proprietaire or "").strip():
        raise PermissionError(
            "Impossible de déposer un document sans compte identifié.")

    fiche = terminer(document_id, proprietaire)      # lève si inconnu ou vide
    chemin = chemin_fichier(document_id, proprietaire)
    if not chemin:
        raise FileNotFoundError("Le document a été finalisé mais son fichier est "
                                "introuvable. Recommence-le.")

    entete = fiche["entete"]
    final = _nom_avec_extension(nom, entete)
    with open(chemin, "rb") as f:
        contenu = f.read()

    # `deposer` LÈVE sur tout échec (collision, écriture refusée, périmètre) :
    # pas de compte rendu optimiste possible — la leçon du NAS est déjà dans
    # sa structure.
    depot = await deposer(dossier, final, contenu, perimetres)
    depot["message_final"] = (
        f"Document finalisé et déposé : « {final} » dans « {dossier} » sur le Drive.")
    return {"document_id": document_id, "titre": entete["titre"],
            "format": entete["format"], "octets": fiche["octets"],
            "elements": fiche["elements"], **depot,
            # Le début RÉEL du fichier déposé, pour l'aperçu dans le chat.
            "extrait": fiche.get("extrait") or "",
            "note": ("Document finalisé ET déposé sur le Drive. Montre-le "
                     "avec un bloc ```ui `doc_apercu` portant `titre`, "
                     "`format` et `extrait` (recopié TEL QUEL).")}
