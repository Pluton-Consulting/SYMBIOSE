"""
LA COLLECTE DES PRIX — relire en fond les devis et factures du classement, ligne à ligne.

Ce que fait ce module : il recense les PDF du classement dont le nom parle de devis ou de
facture, ouvre ceux qu'il n'a jamais lus (ou qui ont changé), en tire les lignes chiffrées
(`prix.lignes`, du code, vérifié par le calcul) et les range dans `lignes_chiffrees`
(migration 055). `prix_observes` n'a plus qu'à chercher dans cette table.

POURQUOI EN FOND, ET UNE PIÈCE À LA FOIS. La première passe ouvre deux mille PDF, dont
quatre devis sur cinq à l'OCR : deux à trois heures. Rien de cela ne doit se voir dans le
chat. Donc : un seul téléchargement à la fois (le client Drive de la tâche lui est propre),
l'OCR derrière la porte commune du serveur (`ingestion.parsers`), une pause entre deux
pièces, et une reprise là où l'on s'était arrêté — une pièce déjà lue et inchangée ne se
rouvre jamais, qu'elle ait donné des lignes ou non (une facture de fournisseur écartée une
fois n'est pas retéléchargée chaque nuit).

LECTURE SEULE sur le classement. Rien n'y est écrit, déplacé ni renommé.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("prix.collecte")

ATTENTE_DEMARRAGE_S = 180          # laisser le backend servir avant de charger la machine
CYCLE_S = 24 * 3600                # une relecture par jour suffit : les devis ne naissent pas à la minute
PAUSE_ENTRE_PIECES_S = 0.2
MAX_OCTETS = 15 * 1024 * 1024      # un devis pèse moins d'un Mo ; au-delà, c'est un dossier de plans
MAX_PAGES_RECENSEMENT = 60         # × 200 fichiers par page
DELAI_LECTURE_S = 240              # une pièce qui dépasse est notée illisible, pas retentée en boucle
# Ce que le nom du fichier doit dire pour qu'on l'ouvre. Large exprès : c'est le CONTENU
# (« Devis N° … », puis le calcul des lignes) qui décide, pas le nom.
MOTS_DU_NOM = ("devis", "facture", "DV0", "FA0")

_ETAT: dict = {"phase": "au repos", "recenses": 0, "a_lire": 0, "lus": 0, "lignes": 0,
               "ecartes": 0, "erreurs": 0, "debut": None, "fin": None, "dernier": ""}
_VERROU = asyncio.Lock()


def etat() -> dict:
    """Où en est la collecte — pour l'écran, les journaux et le résultat de `prix_observes`."""
    return dict(_ETAT)


async def _recenser(service) -> dict[str, dict]:
    """Tous les PDF candidats du classement, par identifiant."""
    trouves: dict[str, dict] = {}
    for mot in MOTS_DU_NOM:
        jeton = None
        for _ in range(MAX_PAGES_RECENSEMENT):
            def appel(jeton=jeton, mot=mot):
                args = dict(
                    q=f"name contains '{mot}' and mimeType='application/pdf' and trashed=false",
                    spaces="drive", corpora="allDrives", includeItemsFromAllDrives=True,
                    supportsAllDrives=True, pageSize=200,
                    fields="nextPageToken,files(id,name,size,modifiedTime)")
                if jeton:
                    args["pageToken"] = jeton
                return service.files().list(**args).execute()
            reponse = await asyncio.wait_for(asyncio.to_thread(appel), timeout=60)
            for f in reponse.get("files") or []:
                trouves.setdefault(f["id"], f)
            jeton = reponse.get("nextPageToken")
            if not jeton:
                break
    return trouves


def _instant(texte: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(texte).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001 — une date illisible vaut « inconnue »
        return None


async def _niveau_des_prix(conn) -> str:
    """Les lignes héritent du niveau d'accès du jeu « devis » importé : qui voit les totaux
    des devis voit leurs lignes, ni plus ni moins. Sans ce jeu, le plus fermé."""
    niveau = await conn.fetchval(
        "SELECT access_level FROM document_metadata WHERE source_type ILIKE '%devis%' "
        "GROUP BY 1 ORDER BY count(*) DESC LIMIT 1")
    return niveau or "direction_only"


async def _ecrire(conn, fichier: dict, etat_piece: str, niveau: str, piece: Optional[dict]) -> int:
    lignes = (piece or {}).get("lignes") or []
    somme = round(sum(float(l["montant_ht"]) for l in lignes), 2)
    total = (piece or {}).get("total_ht")
    controle = "sans_total" if total is None else ("juste" if abs(somme - total) <= 1 else "ecart")
    from prix.releve import plat
    from prix.lignes import VERSION
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO pieces_chiffrees(fichier_id, fichier_nom, modifie_le, etat, nature, numero, "
            "date_piece, titre, total_ht, somme_lignes, controle, methode, lignes, access_level, lu_le) "
            "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14, now()) "
            "ON CONFLICT (fichier_id) DO UPDATE SET fichier_nom=$2, modifie_le=$3, etat=$4, nature=$5, "
            "numero=$6, date_piece=$7, titre=$8, total_ht=$9, somme_lignes=$10, controle=$11, "
            "methode=$12, lignes=$13, access_level=$14, lu_le=now()",
            fichier["id"], str(fichier.get("name") or "")[:300], _instant(fichier.get("modifiedTime")),
            etat_piece, (piece or {}).get("nature"), (piece or {}).get("numero"),
            (piece or {}).get("date"), ((piece or {}).get("titre") or "")[:200] or None,
            total, somme if lignes else None, controle if piece else None,
            f"{(piece or {}).get('methode') or '-'}/{VERSION}", len(lignes), niveau)
        await conn.execute("DELETE FROM lignes_chiffrees WHERE fichier_id=$1", fichier["id"])
        if lignes:
            await conn.executemany(
                "INSERT INTO lignes_chiffrees(fichier_id, rang, designation, rubrique, texte_plat, "
                "unite, quantite, pu_ht, montant_ht, tva) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                [(fichier["id"], k, l["designation"], l.get("rubrique") or "",
                  plat(f"{l.get('rubrique') or ''} {l['designation']}")[:600], l.get("unite") or "",
                  l["quantite"], l["pu_ht"], l["montant_ht"], l.get("tva"))
                 for k, l in enumerate(lignes, 1)])
    return len(lignes)


async def collecter(limite: Optional[int] = None) -> dict:
    """UNE passe : recenser, puis lire ce qui est neuf. Rend le bilan. Ne lève pas."""
    if _VERROU.locked():
        return {**etat(), "deja_en_cours": True}
    async with _VERROU:
        from database.connection import get_db
        from outils import drive
        from prix.lignes import lire_piece
        _ETAT.update(phase="recensement", recenses=0, a_lire=0, lus=0, lignes=0, ecartes=0,
                     erreurs=0, debut=datetime.now(timezone.utc).isoformat(), fin=None, dernier="")
        depart = time.monotonic()
        try:
            # Un client construit POUR cette tâche, hors du client gardé et du vivier : une passe
            # de trois heures ne doit ni faire attendre le chat derrière son verrou, ni partager
            # une connexion (deux fils sur un même client Google tuaient le backend, 17/09).
            service = drive._un_fil_a_la_fois(await drive._build_service_pour(None))
            candidats = await _recenser(service)
            async with get_db() as conn:
                niveau = await _niveau_des_prix(conn)
                # Une pièce lue par une version PLUS ANCIENNE du lecteur compte pour non lue : un
                # gabarit appris après coup doit profiter aux pièces déjà passées.
                from prix.lignes import VERSION
                deja = {r["fichier_id"]: r["modifie_le"] for r in await conn.fetch(
                    "SELECT fichier_id, modifie_le FROM pieces_chiffrees WHERE methode LIKE $1",
                    f"%/{VERSION}")}
            a_lire = [f for f in candidats.values()
                      if f["id"] not in deja or (_instant(f.get("modifiedTime")) or 0) != (deja[f["id"]] or 0)]
            # Les plus récentes d'abord : ce sont elles qui portent les prix d'aujourd'hui, et
            # une passe interrompue aura lu l'utile.
            a_lire.sort(key=lambda f: f.get("modifiedTime") or "", reverse=True)
            if limite:
                a_lire = a_lire[:limite]
            _ETAT.update(phase="lecture", recenses=len(candidats), a_lire=len(a_lire))
            logger.info("Prix : %d PDF recensés, %d à lire", len(candidats), len(a_lire))

            for fichier in a_lire:
                _ETAT["dernier"] = str(fichier.get("name") or "")[:80]
                piece, etat_piece = None, "lue"
                try:
                    if int(fichier.get("size") or 0) > MAX_OCTETS:
                        etat_piece = "trop_lourde"
                    else:
                        octets = await asyncio.wait_for(asyncio.to_thread(
                            lambda f=fichier: service.files().get_media(fileId=f["id"]).execute()),
                            timeout=120)
                        piece = await asyncio.wait_for(asyncio.to_thread(lire_piece, octets),
                                                       timeout=DELAI_LECTURE_S)
                        if piece is None:
                            etat_piece = "pas_de_la_maison"
                except Exception as e:  # noqa: BLE001 — une pièce illisible n'arrête pas la passe
                    etat_piece = "illisible"
                    _ETAT["erreurs"] += 1
                    logger.info("Prix : « %s » illisible (%s)", _ETAT["dernier"], str(e)[:120])
                try:
                    async with get_db() as conn:
                        n = await _ecrire(conn, fichier, etat_piece, niveau, piece)
                    _ETAT["lignes"] += n
                    _ETAT["lus" if etat_piece == "lue" else "ecartes"] += 1
                except Exception as e:  # noqa: BLE001
                    _ETAT["erreurs"] += 1
                    logger.warning("Prix : écriture impossible pour « %s » (%s)", _ETAT["dernier"], str(e)[:160])
                await asyncio.sleep(PAUSE_ENTRE_PIECES_S)
            _ETAT["phase"] = "terminée"
        except Exception as e:  # noqa: BLE001
            _ETAT["phase"] = f"interrompue : {str(e)[:160]}"
            logger.warning("Prix : passe interrompue (%s)", str(e)[:200])
        _ETAT["fin"] = datetime.now(timezone.utc).isoformat()
        logger.info("Prix : passe %s en %.0f s — %d pièce(s) lue(s), %d ligne(s), %d écartée(s), %d erreur(s)",
                    _ETAT["phase"], time.monotonic() - depart, _ETAT["lus"], _ETAT["lignes"],
                    _ETAT["ecartes"], _ETAT["erreurs"])
        return etat()


async def demarrer_collecte() -> None:
    """Tâche de fond : une passe peu après le démarrage, puis une par jour. Ne lève jamais."""
    await asyncio.sleep(ATTENTE_DEMARRAGE_S)
    while True:
        try:
            await collecter()
        except Exception as e:  # noqa: BLE001
            logger.warning("Prix : cycle en échec (%s)", str(e)[:160])
        await asyncio.sleep(CYCLE_S)


async def bilan(conn, niveaux: list) -> dict:
    """Ce que la base de prix contient, pour ce que ce rôle peut voir."""
    r = await conn.fetchrow(
        "SELECT count(*) FILTER (WHERE etat='lue' AND lignes > 0) AS pieces, "
        "       coalesce(sum(lignes) FILTER (WHERE etat='lue'), 0) AS lignes, "
        "       max(date_piece) AS derniere_piece, max(lu_le) AS derniere_lecture "
        "FROM pieces_chiffrees WHERE access_level = ANY($1::text[])", niveaux)
    return {"pieces": int(r["pieces"] or 0), "lignes": int(r["lignes"] or 0),
            "derniere_piece": r["derniere_piece"].isoformat() if r["derniere_piece"] else None,
            "collecte": etat()["phase"], "reste_a_lire": max(0, etat()["a_lire"] - etat()["lus"] - etat()["ecartes"])}
