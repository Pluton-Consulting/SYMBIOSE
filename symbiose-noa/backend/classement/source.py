"""
La SOURCE de la carte du classement chez ce client : le Google Drive.

Module propre au client (déclaré dans la dérive) : le socle `classement.carte`
ne sait pas d'où viennent les entrées. Ici, elles viennent du CATALOGUE du
Drive gardé par `outils.drive` (balayage global : tous les dossiers en
quelques requêtes, comptes de fichiers et types par dossier), relevé avec le
compte de service — le seul qui voit tout le classement.

Le niveau d'accès d'un morceau suit les PÉRIMÈTRES déclarés
(`GOOGLE_DRIVE_PERIMETRES`, « dossier:niveau ») : un dossier réservé à la
direction ne remonte pas dans la recherche d'un collaborateur. Sans périmètre
nommé, c'est le niveau unique du Drive.
"""
from __future__ import annotations

import asyncio
import logging
import unicodedata

logger = logging.getLogger("symbiose.classement")

NOM_STOCKAGE = "Drive de l'entreprise"
GESTE_LISTER = "drive_apercu"
GESTE_CHERCHER = "drive_chercher"


def _nu(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte or "")
                   if unicodedata.category(c) != "Mn").lower().strip()


async def entrees_du_classement() -> tuple[list, bool]:
    """Toutes les entrées (dossiers avec leurs comptes) et si le relevé est complet."""
    from outils import drive as d

    service = await d._service(None)
    catalogue, partiel, comptes, fichiers_partiels = await d._catalogue(service, None)
    drives = {x["id"]: x.get("name") for x in await d._drives_nommes(service)}

    def _racine_reelle():
        return service.files().get(fileId="root", fields="id").execute()
    try:
        mon_drive = (await asyncio.to_thread(_racine_reelle)).get("id")
    except Exception:  # noqa: BLE001 — compte de service sans « Mon Drive »
        mon_drive = None

    memo: dict = {}

    def _chemin(did: str) -> str:
        if did in memo:
            return memo[did]
        morceaux: list[str] = []
        cour, vus = did, set()
        while cour and cour not in vus:
            vus.add(cour)
            if cour == mon_drive:
                morceaux.append("Mon Drive")
                break
            if cour in drives:
                morceaux.append(f"Drive partagé « {drives[cour]} »")
                break
            info = catalogue.get(cour)
            if not info:
                morceaux.append("Partagés avec moi")
                break
            morceaux.append(str(info.get("nom") or "?"))
            parents = info.get("parents") or []
            cour = parents[0] if parents else None
        memo[did] = "/".join(reversed(morceaux))
        return memo[did]

    entrees = []
    for did in catalogue:
        c = comptes.get(did) or [0, 0, {}]
        entrees.append({"chemin": _chemin(did), "dossier": True,
                        "fichiers": int(c[0] or 0), "octets": int(c[1] or 0),
                        "types": dict(c[2]) if len(c) > 2 and isinstance(c[2], dict) else {}})
    return entrees, not (partiel or fichiers_partiels)


def niveau_de(chemin: str) -> str:
    """Le niveau d'accès du morceau qui décrit ce dossier."""
    try:
        from ingestion.connectors.google_drive import perimetres
        couples = perimetres()
    except Exception:  # noqa: BLE001 — réglage illisible : le plus restrictif
        return "admin_only"
    segments = [_nu(s) for s in (chemin or "").split("/")]
    nommes = [(d, n) for d, n in couples if d]
    if not nommes:
        return (couples[0][1] if couples else "all") or "all"
    for dossier, niveau in nommes:
        if _nu(dossier) in segments:
            return niveau
    # Hors de tout périmètre nommé : ce dossier n'est ouvert à personne par le
    # chat, sa description ne l'est donc pas non plus.
    return "admin_only"

# ── L'inventaire (08/09) : lister un dossier, lire un fichier, avec le compte
# de la PERSONNE (chacun voit le Drive avec son compte, règle du 01/09) et
# ses périmètres. Rien n'est déposé : le texte seul revient.

async def fichiers_du_dossier(dossier: str, user) -> tuple[str, list]:
    """(chemin affiché, fichiers directs du dossier) — chaque fichier porte `ref`
    (ce qu'il faut à `lire_fichier`), `nom`, `octets`, `type`."""
    from outils import drive as d
    from skills.outils import _identite, _perimetres

    identite = _identite(user)
    perimetres = _perimetres(user)
    service = await d._service(identite)
    racines = await d._racines(service)
    vise = await d._resoudre(service, dossier, racines, partout=d._tout_le_drive(perimetres))
    if not d._tout_le_drive(perimetres):
        d._garde_perimetre(vise, perimetres)
    brut = await d._lister(service, vise)
    _, fichiers = d._classer(brut.get("entrees") or [])
    return dossier, [{"nom": f.get("name") or "?", "ref": f, "octets": int(f.get("size") or 0),
                      "type": str(f.get("mimeType") or "")} for f in fichiers]


async def lire_fichier(ref, user) -> str:
    """Le texte d'un fichier (PDF, Word, Excel, Google Docs…), ou une chaîne vide."""
    from outils import drive as d
    from skills.outils import _identite

    service = await d._service(_identite(user))
    texte = await asyncio.to_thread(d._download_text, service, ref)
    return str(texte or "")
