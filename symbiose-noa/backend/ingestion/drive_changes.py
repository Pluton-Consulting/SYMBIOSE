"""
LE DRIVE QUI CHANGE — suppressions, déplacements, accès retirés (16/09, S-27).

CE QUI ÉTAIT FAUX. La synchronisation comparait la DATE de modification de
chaque fichier à celle de notre dernière ingestion. C'est une bonne règle pour
repérer ce qui a été MODIFIÉ, et une mauvaise pour tout le reste :

  * un fichier SUPPRIMÉ (ou mis à la corbeille) ne change plus de date : il
    disparaît du listage, et rien ne le retirait de la mémoire. L'assistant
    continuait de citer un devis effacé six mois plus tôt ;
  * un fichier DÉPLACÉ hors d'un périmètre restait indexé au niveau d'accès de
    son ancien dossier ;
  * un ACCÈS RETIRÉ ne change aucune date : le contenu restait lisible chez
    nous pour des gens qui ne l'ouvraient plus sur le Drive.

Un inventaire complet règle tout cela — en parcourant des dizaines de milliers
de fichiers. Google tient pour nous un JOURNAL DES CHANGEMENTS
(`changes.list`) : avec un curseur, on ne lit que ce qui a bougé.

TROIS PRINCIPES, appris de ce que coûte un curseur mal tenu :
  * **le curseur ne s'écrit qu'APRÈS le traitement.** Écrit avant, une panne au
    milieu ferait sauter des changements pour toujours, et personne ne le
    saurait. Écrit après, une panne les fait simplement rejouer — le
    retraitement est sans effet de bord (on réingère ce qui est déjà là) ;
  * **un curseur périmé n'est pas une panne** : Google le dit (410), et l'on
    repart d'un inventaire contrôlé, en l'annonçant ;
  * **le journal des changements ne prouve pas les ACL.** Il dit ce qui a
    bougé, pas qui a le droit de le lire aujourd'hui. Un inventaire complet
    périodique reste nécessaire — ce module ne le remplace pas, il l'espace.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pathlib
import tempfile
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("symbiose.ingestion.drive_changes")

# Au-delà, on préfère un inventaire : un delta de cette taille signifie un
# rangement massif, et le rejouer fichier par fichier coûte plus que de relire.
MAX_CHANGEMENTS = 5000
# Combien d'ancêtres on remonte pour savoir de quel périmètre dépend un fichier.
MAX_REMONTEE = 12


def _chemin() -> pathlib.Path:
    base = os.environ.get("DOCUMENTS_DIR") or tempfile.gettempdir()
    return pathlib.Path(base) / "drive_curseur.json"


def lire_curseur() -> dict:
    """Le curseur enregistré : {token, pose_le, inventaire_le}. {} s'il n'y en a pas."""
    try:
        return json.loads(_chemin().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — pas de curseur : on le dira
        return {}


def ecrire_curseur(token: str, inventaire_le: Optional[str] = None) -> None:
    """Écriture ATOMIQUE : un curseur à moitié écrit est un curseur perdu."""
    fiche = lire_curseur()
    fiche["token"] = str(token)
    fiche["pose_le"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if inventaire_le:
        fiche["inventaire_le"] = inventaire_le
    chemin = _chemin()
    try:
        chemin.parent.mkdir(parents=True, exist_ok=True)
        provisoire = chemin.with_suffix(f".{os.getpid()}.tmp")
        provisoire.write_text(json.dumps(fiche, ensure_ascii=False), encoding="utf-8")
        os.replace(provisoire, chemin)
    except OSError as e:
        logger.warning("Curseur du Drive non enregistré : %s", e)


def oublier_curseur() -> None:
    try:
        _chemin().unlink()
    except OSError:
        pass


def _curseur_de_depart(service) -> Optional[str]:
    """Le jeton « à partir de maintenant », demandé à Google."""
    try:
        return service.changes().getStartPageToken().execute().get("startPageToken")
    except Exception as e:  # noqa: BLE001 — sans curseur, l'inventaire reste la voie
        logger.info("Curseur de départ du Drive indisponible : %s", e)
        return None


async def poser_depart(service) -> Optional[str]:
    """Le curseur du moment — à prendre AVANT un inventaire complet, pour ne
    pas perdre les changements qui arrivent PENDANT."""
    return await asyncio.to_thread(_curseur_de_depart, service)


def _perime(e: Exception) -> bool:
    """Google dit qu'un curseur est trop vieux par un 410 (Gone)."""
    texte = f"{getattr(getattr(e, 'resp', None), 'status', '')} {e}"
    return "410" in texte or "pageToken" in texte.lower() and "invalid" in texte.lower()


def _lire_changements(service, token: str) -> tuple:
    """(changements, nouveau_token, complet) — le journal depuis `token`."""
    changements, page = [], token
    nouveau = None
    while page:
        reponse = service.changes().list(
            pageToken=page,
            spaces="drive",
            includeRemoved=True,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
            pageSize=1000,
            fields=("nextPageToken,newStartPageToken,"
                    "changes(fileId,removed,time,"
                    "file(id,name,mimeType,modifiedTime,trashed,parents,size))"),
        ).execute()
        changements.extend(reponse.get("changes", []))
        if len(changements) >= MAX_CHANGEMENTS:
            return changements, None, False
        nouveau = reponse.get("newStartPageToken") or nouveau
        page = reponse.get("nextPageToken")
    return changements, nouveau, True


def _ancetres(service, fichier: dict, declares: dict) -> Optional[str]:
    """Le niveau d'accès du périmètre dont ce fichier dépend, ou None s'il est
    hors de tous les périmètres déclarés.

    On remonte les parents : Drive ne dit pas « ce fichier est dans tel
    périmètre », il dit « son parent est X ». Borné, parce qu'un cycle de
    raccourcis ferait tourner cette boucle sans fin.
    """
    vus = set()
    file_attente = list(fichier.get("parents") or [])
    for _ in range(MAX_REMONTEE):
        if not file_attente:
            break
        parent = file_attente.pop(0)
        if parent in vus:
            continue
        vus.add(parent)
        if parent in declares:
            return declares[parent]
        try:
            info = service.files().get(fileId=parent, fields="id,parents",
                                       supportsAllDrives=True).execute()
        except Exception:  # noqa: BLE001 — parent illisible : on s'arrête là
            continue
        file_attente.extend(info.get("parents") or [])
    return None


async def appliquer(service, declares: dict, niveau_par_defaut: str = "all") -> dict:
    """Applique le journal des changements. Rend un bilan lisible à l'écran.

    `declares` : {identifiant de dossier → niveau d'accès}. Un fichier qui n'en
    dépend d'aucun est RETIRÉ de la mémoire s'il y était : sorti du périmètre,
    il n'a plus à être lisible chez nous.
    """
    from ingestion.pipeline import ingest_document
    from vectorstore.client import vectorstore

    fiche = lire_curseur()
    token = fiche.get("token")
    if not token:
        return {"applique": False, "raison": "aucun curseur : un inventaire complet "
                                             "doit être joué une fois d'abord"}
    try:
        changements, nouveau, complet = await asyncio.to_thread(_lire_changements, service, token)
    except Exception as e:  # noqa: BLE001
        if _perime(e):
            oublier_curseur()
            return {"applique": False, "curseur_perime": True,
                    "raison": "le curseur du Drive est trop ancien : un inventaire "
                              "complet va le reposer"}
        raise
    if not complet:
        oublier_curseur()
        return {"applique": False, "trop_de_changements": len(changements),
                "raison": f"{len(changements)} changements en attente : un inventaire "
                          "complet est plus rapide que de les rejouer un par un"}

    retires, reingeres, ignores, illisibles = 0, 0, 0, 0
    for c in changements:
        fid = c.get("fileId")
        f = c.get("file") or {}
        if not fid:
            continue
        # SUPPRIMÉ, À LA CORBEILLE, OU HORS D'ATTEINTE : on retire. Un fichier
        # qu'on ne peut plus lire chez Google n'a pas à rester lisible chez nous.
        if c.get("removed") or f.get("trashed"):
            retires += await vectorstore.delete_by_source(fid, "drive") and 1 or 0
            continue
        if f.get("mimeType") == "application/vnd.google-apps.folder":
            continue
        niveau = await asyncio.to_thread(_ancetres, service, f, declares)
        if niveau is None:
            # DÉPLACÉ HORS PÉRIMÈTRE (ou accès retiré sur le dossier) : même
            # conclusion que la suppression, pour la même raison.
            if await vectorstore.delete_by_source(fid, "drive"):
                retires += 1
            else:
                ignores += 1
            continue
        try:
            from ingestion.connectors.google_drive import _download_text
            from ingestion.parsers import en_lecture
            texte = await en_lecture(_download_text, service, f, delai=60)
        except Exception as e:  # noqa: BLE001 — un fichier illisible n'arrête pas le lot
            logger.info("Changement Drive « %s » non lu : %s", f.get("name"), e)
            illisibles += 1
            continue
        if texte and await ingest_document(text=texte, source_type="drive", source_id=fid,
                                           source_filename=f.get("name") or fid,
                                           access_level=niveau or niveau_par_defaut):
            reingeres += 1
        else:
            ignores += 1

    # LE CURSEUR S'ÉCRIT EN DERNIER. Une panne plus haut fait rejouer le lot au
    # prochain passage : réingérer ce qui est déjà là ne coûte qu'un peu de
    # temps, alors qu'un changement sauté ne se rattrape jamais.
    if nouveau:
        ecrire_curseur(nouveau)
    return {"applique": True, "changements": len(changements), "retires": retires,
            "reingeres": reingeres, "ignores": ignores, "illisibles": illisibles,
            "curseur_pose_le": lire_curseur().get("pose_le")}
