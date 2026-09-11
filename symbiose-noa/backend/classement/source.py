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
GESTE_LISTER = "drive_lister"
GESTE_CHERCHER = "drive_chercher"
# Le connecteur de synchronisation de ce stockage (clé de
# `routers.ingestion.CONNECTEURS`). La campagne « Enrichir les documents »
# le lance d'abord : elle ouvre chaque fichier de le Drive AVANT d'en tirer le
# savoir, au lieu de ne relire que ce qu'une synchronisation passée aurait
# laissé en mémoire (11/09).
CONNECTEUR = "google_drive"


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


async def lire_fichier(ref, user) -> dict:
    """{texte, methode} d'un fichier du Drive — lu PAR TYPE comme une pièce
    jointe (`mail/pieces.lire_sans_deposer`, 09/09) : PDF avec OCR si scanné,
    Word, Excel, Google Docs exportés, DXF, et les IMAGES décrites par la
    vision. L'extracteur de l'ingestion (`_download_text`) rendait None pour
    toute photo : les quatre photos et le plan du dossier Camp étaient « sans
    texte lisible », et l'inventaire ne disait rien du dossier. Le binaire
    vient de `_binaire` (exports natifs compris) ; un élément Google non
    téléchargeable lève une raison lisible, rendue telle quelle."""
    from mail.pieces import CONSIGNE_FICHIER, MAX_OCTETS_PIECE, lire_sans_deposer
    from outils import drive as d
    from skills.outils import _identite

    fichier = ref if isinstance(ref, dict) else {}
    nom = str(fichier.get("name") or "fichier")
    mime = str(fichier.get("mimeType") or "")
    taille = int(fichier.get("size") or 0)
    if taille > MAX_OCTETS_PIECE:
        return {"texte": "", "methode": f"trop lourd pour être lu ({taille // (1024 * 1024)} Mo)"}
    service = await d._service(_identite(user))
    brut, vrai_nom, mime = await d._binaire(fichier, service, nom, mime)
    return await lire_sans_deposer(vrai_nom, mime, brut, consigne_vision=CONSIGNE_FICHIER)
