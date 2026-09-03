"""
Connecteur Google Drive (API v3, lecture seule) — voie API directe.

Alternative RECOMMANDÉE : Make.com (connecteur natif, OAuth géré par Make) qui POST
vers /api/ingestion/webhook — aucune app à créer. Voir SETUP_CONNECTEURS.md.

Voie directe (ce module) — prérequis :
  1. Projet Google Cloud + API Drive activée.
  2. Client OAuth « Desktop » → déposer le JSON dans settings.google_credentials_file.
  3. 1er consentement interactif (hors Docker) → génère settings.google_token_file (refresh token).
"""
import asyncio
import logging
import os
from typing import Optional

from config import settings
from ingestion.pipeline import ingest_document

logger = logging.getLogger("symbiose.ingestion.gdrive")

# ── Bornes de l'ingestion ────────────────────────────────────────────
# Elles ne servent pas à « aller vite » : elles servent à ce qu'une anomalie
# s'arrête au lieu de bloquer la synchronisation pour toujours. Toutes ont été
# choisies après l'incident du 13/08/2026, où un seul PDF a gelé le backend.
MAX_PROFONDEUR = 12          # Un classement métier — service / année / chantier /
                             # lot / pièces / photos — dépasse rarement 6 niveaux.
                             # Au-delà de 12, c'est une recopie ou une boucle.
MAX_DOSSIERS_PARCOURUS = 5000  # Une PME du paysage a des centaines de chantiers.
                             # Atteindre cette borne n'est pas « un gros Drive »,
                             # c'est une anomalie — d'où l'avertissement au journal.
MAX_PAGES_PDF = 300          # Au-delà, ce n'est plus un document de travail.
DELAI_PAR_DOCUMENT_S = 90    # Le PDF qui a tout bloqué tenait depuis 7 minutes.
MAX_DOCUMENTS_LENTS = 5      # Plusieurs threads pendus = problème de fond.
# CE QUE LES JOURNAUX DU 31/08 ONT MONTRÉ. 34 568 fichiers listés, 438 ingérés —
# hier 34 565 et 436 — et « 5 documents trop lents, arrêt » à chaque passage,
# sur les MÊMES cinq PDF d'architecte (coupes, façades, plan masse, carnets).
# La synchro s'arrêtait donc toujours au même endroit, tout ce qui venait
# après dans l'ordre du Drive n'était jamais lu, et l'écran disait
# « Terminée ». Trois réponses, ici :
#   * un fichier abandonné est MÉMORISÉ (id + modifiedTime) et sauté aux
#     passages suivants : l'arrêt anticipé ne se reproduit plus au même
#     endroit, la synchro PROGRESSE ;
#   * un PDF au-delà de MAX_OCTETS_PDF n'est pas téléchargé : un plan de
#     40 Mo n'a rien à dire au texte, et c'est lui qui tient 90 s ;
#   * un fichier dont modifiedTime n'a pas bougé depuis sa dernière ingestion
#     n'est pas re-téléchargé : chaque passage réinsérait les 438 mêmes
#     documents et remettait ~1 000 embeddings en file pour rien.
MAX_OCTETS_PDF = 25 * 1024 * 1024
MAX_LIGNES_TABLEUR = 2000     # un classeur Drive lu comme texte, borné
FICHIER_LENTS = "drive_lents.json"

_MIME_DOSSIER = "application/vnd.google-apps.folder"
_MIME_RACCOURCI = "application/vnd.google-apps.shortcut"

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# Le scope d'ÉCRITURE, demandé SEULEMENT par le client du dépôt
# (`_build_service_ecriture`) : l'ingestion et toutes les lectures gardent le
# scope minimal. `drive` complet, et non `drive.file` : ce dernier ne voit que
# ce que l'application a créé — impossible de déposer DANS un dossier existant
# de l'entreprise, ce qui est précisément le geste demandé.
_SCOPES_ECRITURE = ["https://www.googleapis.com/auth/drive"]
# Documents natifs Google → export vers un format texte lisible.
_EXPORTABLE = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _build_service(scopes=None):
    # `scopes` : lecture par défaut ; le client du dépôt passe l'écriture.
    scopes = scopes or _SCOPES
    import json
    import os
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # 1. COMPTE DE SERVICE, s'il est depose. Aucun consentement humain, aucun
    #    jeton a renouveler : l'application s'authentifie seule. C'est la seule
    #    voie tenable pour un Drive d'entreprise — l'alternative obligerait
    #    chaque personne a se connecter a Google, et le jeton obtenu
    #    n'appartiendrait qu'a elle.
    if os.path.exists(settings.google_service_account_file):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=scopes)
        sujet = (settings.google_admin_subject or "").strip()
        if sujet:
            # Delegation a l'echelle du domaine : on AGIT AU NOM de ce compte.
            # Ne sert qu'aux « Mon Drive » individuels ; pour un Drive PARTAGE,
            # ajouter le compte de service comme membre suffit, et c'est moins
            # de pouvoir accorde.
            creds = creds.with_subject(sujet)
        logger.info("Google Drive : compte de service%s",
                    f" (au nom de {sujet})" if sujet else " (Drive partages)")
        return build("drive", "v3", credentials=creds)

    # 2. JETON OAUTH DONNÉ PAR L'ENVIRONNEMENT. Déposer un fichier de secret sur
    #    un serveur suppose un accès au disque ET les bons droits : le dossier
    #    `secrets/` y appartient souvent à root — créé par Docker — et la copie
    #    échoue sur « Permission denied ». Le jeton se fournit donc aussi comme
    #    les autres identifiants, par variable d'environnement.
    #
    #    Il se suffit à lui-même : le JSON rendu par le consentement porte déjà
    #    `client_id`, `client_secret` et `refresh_token`. Le client OAuth n'a
    #    donc PAS à être copié à côté — un fichier de moins à protéger.
    brut = (settings.google_token_json or "").strip()
    if brut:
        try:
            infos = json.loads(brut)
        except ValueError as e:
            raise NotImplementedError(
                f"GOOGLE_TOKEN_JSON illisible ({e}). Attendu : le contenu exact "
                "de secrets/google_token.json, sur UNE seule ligne.") from e
        # Un jeton amputé de son `refresh_token` fonctionne… jusqu'à la première
        # expiration, quelques jours plus tard, et l'accès tombe sans rien dire.
        # On le refuse tout de suite, avec le moyen de s'en sortir.
        manquants = [c for c in ("client_id", "client_secret", "refresh_token")
                     if not infos.get(c)]
        if manquants:
            raise NotImplementedError(
                f"GOOGLE_TOKEN_JSON incomplet : {', '.join(manquants)} manque(nt). "
                "Relancez scripts/google_consentement.py et vérifiez qu'il "
                "affiche « refresh token présent : oui ».")
        creds = Credentials.from_authorized_user_info(infos, scopes)
        if not creds.valid:
            # Aucun repli interactif ici : sur un serveur, `run_local_server`
            # attendrait un navigateur qui n'existe pas et le tour resterait
            # pendu. On rafraîchit, ou on échoue en le disant.
            from google.auth.exceptions import RefreshError
            try:
                creds.refresh(Request())
            except RefreshError as e:
                # Jeton révoqué, client OAuth supprimé, ou consentement resté
                # « en test » — Google y fait expirer le refresh token au bout
                # de sept jours. L'erreur brute (« invalid_client ») s'affichait
                # telle quelle sur l'écran de synchronisation, sans dire quoi
                # faire. `NotImplementedError` la range en « non configuré »,
                # ce qu'elle est devenue.
                raise NotImplementedError(
                    f"Le jeton Google n'est plus valide ({e}). Relancez "
                    "scripts/google_consentement.py et recollez le résultat "
                    "dans GOOGLE_TOKEN_JSON. Si l'écran de consentement Google "
                    "est resté « en test », passez-le en « interne » ou « en "
                    "production » : sinon le jeton meurt tous les 7 jours."
                ) from e
        logger.info("Google Drive : jeton OAuth lu dans l'environnement")
        return build("drive", "v3", credentials=creds)

    # 3. Sinon, consentement OAuth d'un utilisateur par FICHIER (voie historique).
    if not os.path.exists(settings.google_credentials_file):
        raise NotImplementedError(
            "Google Drive non configuré. Deux voies : "
            "1. RECOMMANDÉ pour un Drive d'entreprise, déposer la clé d'un compte "
            f"de service dans {settings.google_service_account_file} : personne "
            "n'a alors à se connecter à Google. "
            f"2. Client OAuth dans {settings.google_credentials_file}, avec un "
            "consentement interactif (scripts/google_consentement.py), ou son "
            "résultat collé dans GOOGLE_TOKEN_JSON, sans aucun fichier à copier.")

    creds = None
    if os.path.exists(settings.google_token_file):
        creds = Credentials.from_authorized_user_file(settings.google_token_file, scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(settings.google_credentials_file, scopes)
            creds = flow.run_local_server(port=0)  # ⚠ interactif : à lancer une fois hors conteneur
        os.makedirs(os.path.dirname(settings.google_token_file) or ".", exist_ok=True)
        with open(settings.google_token_file, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _build_service_ecriture():
    """Le client Drive capable d'ÉCRIRE — construit à la demande, jamais gardé.

    Séparé du client de lecture pour que l'ingestion et les skills de
    consultation ne portent JAMAIS plus de droits qu'il ne leur en faut. Un
    jeton OAuth taillé en lecture seule (l'historique GOOGLE_TOKEN_JSON du
    serveur) ne peut pas monter en écriture tout seul : Google refuse le
    rafraîchissement, et l'erreur dit alors le geste qui manque — relancer
    scripts/google_consentement.py (dont les scopes portent l'écriture depuis
    le 30/08) et recoller le résultat.
    """
    from google.auth.exceptions import RefreshError
    try:
        return _build_service(_SCOPES_ECRITURE)
    except RefreshError as e:
        raise NotImplementedError(
            "Le jeton Google ne porte que la LECTURE : le dépôt sur le Drive "
            "exige un nouveau consentement. Relancez "
            "scripts/google_consentement.py puis recollez le résultat dans "
            "GOOGLE_TOKEN_JSON. (Avec un compte de service, donnez-lui le rôle "
            "« Gestionnaire de contenu » sur le Drive partagé.)") from e


def _download_text(service, f) -> Optional[str]:
    mime, name = f["mimeType"], f["name"]
    try:
        if mime in _EXPORTABLE:
            data = service.files().export(fileId=f["id"], mimeType=_EXPORTABLE[mime]).execute()
            return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)

        if mime == "application/pdf" or name.lower().endswith(".pdf"):
            import io
            import pdfplumber
            from googleapiclient.http import MediaIoBaseDownload
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, service.files().get_media(fileId=f["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
            buf.seek(0)
            with pdfplumber.open(buf) as pdf:
                # UNE BORNE EN PAGES, en plus du délai. Relevé en production :
                # un PDF a tenu 100 % d'un cœur pendant plus de sept minutes,
                # mémoire du processus passée de 743 Mio à 2 Gio, et
                # l'ingestion ne s'en est jamais remise. Un document de plus de
                # 300 pages n'est pas un document de travail : c'est un scan
                # d'archives ou un fichier malformé, et il ne rend presque
                # jamais de texte exploitable.
                pages = pdf.pages[:MAX_PAGES_PDF]
                texte = "\n\n".join((p.extract_text() or "") for p in pages)
                if len(pdf.pages) > MAX_PAGES_PDF:
                    logger.info("Drive : « %s » tronqué à %d pages sur %d",
                                name, MAX_PAGES_PDF, len(pdf.pages))
                return texte

        if mime.startswith("text/") or name.lower().endswith((".txt", ".md")):
            data = service.files().get_media(fileId=f["id"]).execute()
            return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
        # Word, Excel, CSV : `ingestion.parsers` sait les lire depuis longtemps
        # (le NAS de Duret s'en sert), ce connecteur ne le faisait pas — les
        # .docx du Drive n'étaient JAMAIS ingérés (31/08). Les images restent
        # hors champ : l'OCR d'un Drive de photos de chantiers, c'est des
        # heures pour rien.
        from ingestion.parsers import (EXT_IMAGE, FichierNonSupporte, analyser,
                                       famille, ligne_en_texte)
        if famille(name) is not None and not name.lower().endswith(EXT_IMAGE):
            data = service.files().get_media(fileId=f["id"]).execute()
            try:
                structure = analyser(name, data)
            except FichierNonSupporte as e:
                logger.info("Drive : « %s » ignoré (%s)", name, e)
                return None
            if structure.get("kind") == "tabulaire":
                lignes = (structure.get("rows") or [])[:MAX_LIGNES_TABLEUR]
                return "\n\n".join(ligne_en_texte(l) for l in lignes)
            return structure.get("text")
    except Exception as e:
        logger.warning("Drive : téléchargement de « %s » échoué : %s", name, e)
    return None  # images et formats inconnus


def _instant(valeur) -> Optional["datetime"]:
    """Un `modifiedTime` Drive (« 2026-08-31T07:22:10.123Z ») en datetime UTC."""
    from datetime import datetime, timezone
    if not valeur:
        return None
    try:
        d = datetime.fromisoformat(str(valeur).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _inchange(fichier: dict, derniere_ingestion) -> bool:
    """Le fichier n'a pas bougé depuis qu'on l'a ingéré : inutile de le relire.
    Fonction PURE (banc). Sans date connue d'un côté ou de l'autre, on relit :
    dans le doute, c'est la relecture qui est sans risque."""
    modifie = _instant(fichier.get("modifiedTime"))
    if modifie is None or derniere_ingestion is None:
        return False
    from datetime import timezone
    d = derniere_ingestion if derniere_ingestion.tzinfo else derniere_ingestion.replace(tzinfo=timezone.utc)
    return d >= modifie


def _trop_gros(fichier: dict) -> bool:
    """Un PDF au-delà de la borne : on ne le télécharge même pas."""
    est_pdf = (fichier.get("mimeType") == "application/pdf"
               or str(fichier.get("name", "")).lower().endswith(".pdf"))
    try:
        return est_pdf and int(fichier.get("size") or 0) > MAX_OCTETS_PDF
    except (TypeError, ValueError):
        return False


def _chemin_lents():
    """Les fichiers abandonnés vivent dans le volume des documents produits : il
    survit au redéploiement — c'est tout l'intérêt de s'en souvenir."""
    import os
    import pathlib
    return pathlib.Path(os.environ.get("DOCUMENTS_DIR", "/tmp/symbiose-documents")) / FICHIER_LENTS


def _lire_lents() -> dict:
    import json
    try:
        return dict(json.loads(_chemin_lents().read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return {}


def _ecrire_lents(lents: dict) -> None:
    import json
    try:
        chemin = _chemin_lents()
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(json.dumps(lents, ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError as e:  # noqa: BLE001 — une mémoire d'appoint ne casse pas une synchro
        logger.warning("Drive : mémoire des fichiers lents non écrite : %s", e)


async def _dates_ingerees() -> dict:
    """source_id → date de la dernière ingestion (les chunks sont réécrits à
    chaque ingestion, `created_at` la date donc). Illisible → tout sera relu."""
    try:
        from database.connection import get_db
        async with get_db() as conn:
            lignes = await conn.fetch(
                "SELECT source_id, MAX(created_at) AS d FROM documents "
                "WHERE source_type = 'drive' GROUP BY source_id")
        return {l["source_id"]: l["d"] for l in lignes}
    except Exception as e:  # noqa: BLE001
        logger.warning("Drive : dates d'ingestion illisibles (%s) — tout sera relu", e)
        return {}


def perimetres() -> list[tuple[Optional[str], str]]:
    """Les couples (dossier, niveau d'accès) à synchroniser.

    POURQUOI DÉCOUPER ICI, ET PAS PAR IDENTIFIANT. Segmenter avec un compte de
    service par service — un pour le commercial, un pour la direction — ne
    change RIEN à ce que voient les utilisateurs : tout finit dans la même base,
    et c'est le niveau d'accès du document qui décide qui le retrouve. Ça ne
    réduit que la portée d'une clé volée, au prix d'autant de secrets à créer, à
    déposer et à faire tourner — c'est-à-dire d'autant d'occasions de fuite.

    Le découpage qui compte pour l'équipe est celui-ci : un dossier, un niveau.
    Un seul identifiant suffit, et chaque document arrive avec les droits de son
    dossier d'origine.

    Format : « dossierA:commercial_plus, dossierB:direction_only ». Sans ce
    réglage, on retombe sur le dossier unique et son niveau.
    """
    from security.acces import NIVEAUX

    brut = (settings.google_drive_perimetres or "").strip()
    if not brut:
        niveau = (settings.google_drive_access_level or "all").strip()
        if niveau not in NIVEAUX:
            raise ValueError(f"GOOGLE_DRIVE_ACCESS_LEVEL « {niveau} » inconnu. "
                             f"Valeurs possibles : {', '.join(NIVEAUX)}.")
        return [(settings.google_drive_folder_id, niveau)]

    couples: list[tuple[Optional[str], str]] = []
    for morceau in brut.split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        dossier, _, niveau = morceau.partition(":")
        dossier, niveau = dossier.strip(), niveau.strip()
        # Un dossier vide prendrait TOUT le Drive au niveau indiqué : dans une
        # configuration qui déclare plusieurs périmètres, c'est forcément une
        # erreur de frappe, et elle exposerait tout au niveau le plus ouvert.
        if not dossier:
            raise ValueError(
                f"GOOGLE_DRIVE_PERIMETRES : périmètre « {morceau} » sans dossier. "
                "Attendu « identifiant_du_dossier:niveau ».")
        if niveau not in NIVEAUX:
            raise ValueError(
                f"GOOGLE_DRIVE_PERIMETRES : niveau « {niveau or '(vide)'} » inconnu "
                f"pour le dossier {dossier}. Valeurs possibles : {', '.join(NIVEAUX)}.")
        couples.append((dossier, niveau))
    return couples


async def _pages(service, q: str) -> list[dict]:
    """Toutes les entrées d'une requête Drive, pagination comprise.

    HORS BOUCLE D'ÉVÉNEMENTS. Le client Google est bloquant, et la descente
    multiplie les appels par le nombre de dossiers. Laissés dans la boucle, ils
    gèlent le backend pendant toute la synchronisation : c'est ce qui a rendu
    l'application inutilisable — bouton figé, onglets bloqués, réponses HTTP
    tronquées par nginx. Les appels restent SÉQUENTIELS, un `await` à la fois :
    le client Google n'est pas prévu pour être partagé entre threads.
    """
    entrees, token = [], None
    while True:
        def _appel(t=token):
            return service.files().list(
                q=q, spaces="drive",
                fields="nextPageToken, files(id,name,mimeType,modifiedTime,size)",
                pageToken=t,
                # `corpora` MANQUAIT, et c'est ce qui rendait un Drive partagé
                # invisible. Par défaut l'API cherche dans le corpus « user »,
                # c'est-à-dire le « Mon Drive » du compte : sans dossier précisé,
                # la synchronisation d'un Drive PARTAGÉ ne remontait rien, et le
                # tour se terminait sur « 0 fichier » sans la moindre erreur — le
                # pire des symptômes, celui qui ressemble à un Drive vide.
                #
                # `includeItemsFromAllDrives` et `supportsAllDrives` ne suffisent
                # pas : ils autorisent les résultats hors « Mon Drive », ils ne
                # décident pas où l'on cherche.
                corpora="allDrives",
                includeItemsFromAllDrives=True, supportsAllDrives=True,
                pageSize=1000,
            ).execute()

        resp = await asyncio.to_thread(_appel)
        entrees.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            return entrees


async def _lister(service, folder: Optional[str],
                  exclus: frozenset = frozenset()) -> tuple[list[dict], dict]:
    """Les fichiers d'un périmètre, SOUS-DOSSIERS COMPRIS.

    CE QUI ÉTAIT FAUX. « 'X' in parents » ne rend que les enfants DIRECTS de X.
    Un dossier de chantier ne livrait donc que ce qui traînait à sa racine.
    Mesuré sur un Drive d'essai : 4 documents sur 5 jamais vus, et le compte
    annoncé — 3 « fichiers » — incluait 2 sous-dossiers pris pour des fichiers.

    Pire, l'effet était INVERSÉ : laisser le dossier vide ramenait tout le Drive
    à toutes les profondeurs, le nommer pour RESTREINDRE faisait tomber à la
    profondeur 1. Le geste de sécurité coupait l'ingestion.

    `exclus` : les dossiers qui ont DÉJÀ leur propre périmètre. Sans cette
    coupe, un sous-dossier « direction » rangé sous le dossier commercial
    hériterait du niveau commercial parce qu'un parcours l'atteint le premier —
    et comme l'ingestion REMPLACE les chunks d'une même source, c'est l'ordre de
    `GOOGLE_DRIVE_PERIMETRES` qui déciderait de la confidentialité.
    """
    if not folder:
        # Sans dossier, l'API rend déjà tout le Drive à toutes les profondeurs :
        # rien à parcourir. On retire quand même dossiers et raccourcis, qui
        # étaient comptés comme des « fichiers » et gonflaient le bilan.
        entrees = await _pages(service, "trashed=false")
        return ([e for e in entrees
                 if e.get("mimeType") not in (_MIME_DOSSIER, _MIME_RACCOURCI)],
                {"dossiers_parcourus": 0, "complet": True, "ignorés": 0})

    fichiers: list[dict] = []
    vus: set[str] = set()
    file_attente = [(folder, 0)]
    ignores = 0

    while file_attente and len(vus) < MAX_DOSSIERS_PARCOURUS:
        courant, niveau = file_attente.pop(0)
        # ANTI-CYCLE. Un dossier rangé sous deux parents, ou un raccourci qui
        # renvoie vers un ancêtre, ferait tourner le parcours sans fin — et
        # comme la synchronisation tourne en tâche de fond, personne ne le voit.
        if courant in vus:
            continue
        vus.add(courant)
        try:
            entrees = await _pages(service, f"'{courant}' in parents and trashed=false")
        except Exception as e:  # noqa: BLE001
            # Un dossier refusé n'annule pas le reste du périmètre.
            logger.warning("Drive : dossier %s illisible : %s", courant, e)
            continue
        for e in entrees:
            mime = e.get("mimeType")
            if mime == _MIME_DOSSIER:
                if e["id"] in exclus:
                    # Il a son propre périmètre : il sera ingéré avec SON niveau.
                    ignores += 1
                elif niveau + 1 < MAX_PROFONDEUR:
                    file_attente.append((e["id"], niveau + 1))
                else:
                    ignores += 1
            elif mime != _MIME_RACCOURCI:
                fichiers.append(e)

    rapport = {"dossiers_parcourus": len(vus),
               "complet": not file_attente, "ignorés": ignores}
    if file_attente:
        # UNE TRONCATURE QUI NE SE VOIT PAS EST UN DRIVE QU'ON CROIT AVOIR LU.
        logger.warning("Drive : parcours arrêté à %d dossiers, %d restants",
                       MAX_DOSSIERS_PARCOURUS, len(file_attente))
    return fichiers, rapport


async def sync(folder_id: Optional[str] = None, avancer=None) -> dict:
    """Ingère chaque périmètre déclaré, avec le niveau d'accès de son dossier.

    Un dossier passé en argument l'emporte sur la configuration : c'est ce qui
    permet de tester un seul dossier avant d'ouvrir plus large.

    `avancer(traites, total, etape)` est appelé au fil de l'eau quand le routeur
    en fournit un. Optionnel, et c'est voulu : les autres connecteurs ne le
    connaissent pas et ne doivent pas être réécrits pour autant.
    """
    service = await asyncio.to_thread(_build_service)

    if folder_id:
        from security.acces import NIVEAUX
        niveau = (settings.google_drive_access_level or "all").strip()
        if niveau not in NIVEAUX:
            raise ValueError(f"GOOGLE_DRIVE_ACCESS_LEVEL « {niveau} » inconnu.")
        cibles = [(folder_id, niveau)]
    else:
        cibles = perimetres()

    # Les dossiers qui ont leur PROPRE périmètre ne doivent pas être avalés par
    # le parcours d'un autre : ils seront ingérés avec leur niveau à eux.
    declares = frozenset(d for d, _ in cibles if d)

    async def _prevenir(traites, total, etape):
        if avancer is None:
            return
        try:
            await avancer(traites, total, etape)
        except Exception as e:  # noqa: BLE001 - un compteur ne casse pas une ingestion
            logger.debug("Drive : avancement non enregistré : %s", e)

    total_vus = total_ingeres = total_lents = 0
    inchanges = lents_sautes = trop_gros = non_examines = 0
    connus = await _dates_ingerees()
    lents = _lire_lents()
    detail = []
    for dossier, niveau in cibles:
        await _prevenir(total_ingeres, None, f"je liste {dossier or 'le Drive'}")
        fichiers, rapport = await _lister(service, dossier,
                                          declares - {dossier} if dossier else frozenset())
        ingeres = 0
        for i, f in enumerate(fichiers):
            if _inchange(f, connus.get(f["id"])):
                inchanges += 1
                continue
            if lents.get(f["id"]) == (f.get("modifiedTime") or ""):
                lents_sautes += 1          # abandonné à un passage précédent, inchangé depuis
                continue
            if _trop_gros(f):
                trop_gros += 1
                logger.info("Drive : « %s » non téléchargé (%s octets, au-delà de %d)",
                            f.get("name"), f.get("size"), MAX_OCTETS_PDF)
                continue
            # UN DÉLAI PAR DOCUMENT. Un PDF a déjà tenu plus de sept minutes à
            # 100 % d'un cœur, et l'ingestion ne s'en est jamais remise : elle
            # est restée bloquée sur ce fichier jusqu'au redémarrage.
            #
            # RÉSERVE ASSUMÉE : `to_thread` ne se tue pas. Le thread continue
            # de tourner après l'expiration — on ne peut pas l'interrompre sans
            # passer par un processus séparé. Ce qu'on gagne, c'est que
            # l'ingestion AVANCE et que la boucle d'événements reste libre.
            # C'est pour ça qu'on compte les dépassements et qu'on s'arrête
            # au-delà de quelques-uns : plusieurs threads pendus, c'est un
            # problème de fond, pas un fichier tordu.
            try:
                text = await asyncio.wait_for(
                    asyncio.to_thread(_download_text, service, f),
                    timeout=DELAI_PAR_DOCUMENT_S)
            except (asyncio.TimeoutError, TimeoutError):
                total_lents += 1
                lents[f["id"]] = f.get("modifiedTime") or ""
                _ecrire_lents(lents)      # il ne sera plus retenté tant qu'il ne change pas
                logger.warning("Drive : « %s » abandonné après %d s (mémorisé)",
                               f.get("name"), DELAI_PAR_DOCUMENT_S)
                if total_lents >= MAX_DOCUMENTS_LENTS:
                    non_examines += len(fichiers) - i - 1
                    logger.error("Drive : %d documents trop lents, arrêt anticipé — %d fichier(s) "
                                 "non examiné(s), ils passeront au prochain lancement",
                                 total_lents, len(fichiers) - i - 1)
                    break
                continue
            if text and await ingest_document(
                    text=text, source_type="drive", source_id=f["id"],
                    source_filename=f["name"], access_level=niveau):
                ingeres += 1
            if i % 10 == 0:
                await _prevenir(total_ingeres + ingeres, None,
                                f"j'ingère {f.get('name', '')[:60]}")
        total_vus += len(fichiers)
        total_ingeres += ingeres
        detail.append({"dossier": dossier or "(tout)", "niveau_acces": niveau,
                       "fichiers": len(fichiers), "ingérés": ingeres,
                       "dossiers_parcourus": rapport["dossiers_parcourus"],
                       "parcours_complet": rapport["complet"]})
        logger.info("Drive : dossier %s — %d fichiers dans %d dossiers, %d ingérés "
                    "au niveau « %s »", dossier or "(tout)", len(fichiers),
                    rapport["dossiers_parcourus"], ingeres, niveau)

    # Le détail par périmètre remonte jusqu'à l'écran : c'est la seule façon de
    # vérifier qu'un dossier sensible est bien arrivé au niveau qu'on croit,
    # sans avoir à relire un fichier de configuration sur le serveur.
    sortie = {"fichiers": total_vus, "ingérés": total_ingeres, "périmètres": detail,
              "inchangés": inchanges, "lents_ignorés": lents_sautes, "trop_gros": trop_gros}
    if total_lents:
        sortie["abandonnés_trop_lents"] = total_lents
    if non_examines:
        # L'écran doit dire « partielle », pas « terminée » : c'est le routeur
        # qui lit ces deux clés (routers/ingestion.py).
        sortie["arret_anticipe"] = True
        sortie["non_examines"] = non_examines
    return sortie


def _build_service_perso(credentials, scopes=None):
    """Client Drive bâti sur le consentement d'UNE personne (01/09).

    Le jeton est rafraîchi ICI, dans le thread de l'appelant : sinon la première
    requête Drive échouerait au milieu d'un listage, et l'erreur remonterait
    comme « le Drive est vide » plutôt que « reconnectez votre compte Google » —
    c'est le mensonge qu'on paie deux fois (une fois à le lire, une fois à le
    chercher ailleurs).

    `scopes` n'est pas transmis à `Credentials` : les scopes d'un jeton OAuth
    sont ceux du CONSENTEMENT, pas ceux qu'on redemande à l'usage. Il n'est là
    que pour dire, dans le journal, à quoi le client était destiné.
    """
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    try:
        credentials.refresh(Request())
    except RefreshError as e:
        raise NotImplementedError(
            "Votre compte Google n'est plus relié à l'assistant (accès révoqué, "
            "ou consentement expiré). Reliez-le à nouveau depuis "
            "Paramètres > Mon compte Google.") from e
    logger.info("Client Drive personnel construit (%s)",
                "écriture" if scopes == _SCOPES_ECRITURE else "lecture")
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _build_service_delegue(courriel: str, scopes=None):
    """Client Drive AU NOM d'une personne du domaine, sans qu'elle clique.

    LA TROISIÈME VOIE, et de loin la plus confortable quand l'entreprise est
    sur un Google Workspace administré. Un compte de service à qui la console
    Admin a accordé la DÉLÉGATION À L'ÉCHELLE DU DOMAINE peut emprunter
    l'identité de n'importe quel compte du domaine : chacun voit alors SON
    Drive, avec SES droits, sans consentement individuel, sans client OAuth
    « Web », et sans le piège des refresh tokens révoqués à sept jours.

    `_build_service` le faisait déjà, mais vers UNE adresse fixe
    (`google_admin_subject`) : c'est cette adresse-là que tout le monde
    empruntait. Ici le sujet est la personne QUI DEMANDE.

    ⚠️ CE POUVOIR EST ENTIER : la délégation permet d'emprunter l'identité de
    n'importe qui dans le domaine. Le `courriel` doit donc TOUJOURS venir de la
    session (la table `users`, lue par l'identifiant de la session), jamais
    d'un paramètre écrit par le modèle — c'est la même règle que `_identite`
    dans `skills/outils.py`, et elle n'a pas d'exception.
    """
    from google.oauth2 import service_account

    scopes = scopes or _SCOPES
    adresse = (courriel or "").strip().lower()
    if not adresse:
        raise NotImplementedError("Aucune adresse à emprunter.")
    if not os.path.exists(settings.google_service_account_file):
        raise NotImplementedError(
            "Aucun compte de service déposé : la délégation de domaine n'est "
            "pas disponible sur ce serveur.")
    creds = service_account.Credentials.from_service_account_file(
        settings.google_service_account_file, scopes=scopes)
    logger.info("Google Drive : délégation de domaine au nom de %s", adresse)
    return build("drive", "v3", credentials=creds.with_subject(adresse),
                 cache_discovery=False)
