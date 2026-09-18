"""
LE CHIFFRE D'AFFAIRES, CALCULÉ PAR LE SERVEUR — depuis les factures lues dans le classement.

Pourquoi ce geste existe (17/09) : « en reprenant toutes les factures, quel chiffre d'affaires
avons-nous fait entre le 01/09/2025 et le 31/08/2026 ? » n'avait aucune réponse fiable. Le jeu
« facture » importé n'a ni date ni numéro ; le modèle partait ouvrir plus de mille PDF un à un,
s'arrêtait, et rendait un chiffre sans méthode. Depuis que `prix.collecte` lit chaque facture
(numéro, date, total HT, client), la somme est un calcul — et un calcul ne se confie pas à un
modèle.

CE QU'UN CONTRÔLEUR DE GESTION EXIGERAIT, ET QUE LE GESTE REND :
  * UNE FACTURE NE COMPTE QU'UNE FOIS. Le même PDF vit en deux ou trois exemplaires dans le
    classement (2 207 fichiers pour 1 065 numéros) : on dédoublonne par NUMÉRO, en gardant
    l'exemplaire le mieux lu.
  * UN DEVIS N'EST JAMAIS DU CHIFFRE D'AFFAIRES. Seules les pièces « facture » entrent ; un
    avoir vient en MOINS.
  * CE QUI N'A PAS PU ÊTRE LU EST DIT. Une facture sans total lisible, ou sans date, est listée
    à part, jamais comptée pour zéro en silence.
  * LE CA D'UN CLIENT EST LA SOMME DE TOUTES SES FACTURES. Les variantes d'écriture d'un même
    client se regroupent par son CODE client quand il est écrit, et la fusion est déclarée.
  * LA SOMME DES CLIENTS ÉGALE LE TOTAL, par construction — et le geste le vérifie quand même.

Lecture seule. Ne touche ni au classement ni à la messagerie.
"""
from __future__ import annotations

import logging
import re
from datetime import date

from skills.registre import Declaration

logger = logging.getLogger(__name__)

MAX_CLIENTS_A_L_ECRAN = 10
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")
_CIVILITES = re.compile(r"^(m\.?\s+et\s+mme|mr?\.?\s+et\s+mme|mme\s+et\s+m\.?|m\.|mr\.?|mme|mlle|monsieur|madame|"
                        r"st[ée]|soci[ée]t[ée]|sas|sarl|sci|eurl|sa)\s+", re.IGNORECASE)


def _euros(v: float) -> str:
    entier, _, cents = f"{v:,.2f}".partition(".")
    return f"{entier.replace(',', ' ')},{cents} €"


def _cle_client(nom: str, code: str) -> str:
    """Ce qui fait qu'un client est LE MÊME : son code, sinon son nom sans civilité ni casse."""
    if code:
        return "code:" + code.upper()
    from prix.releve import plat
    return "nom:" + plat(_CIVILITES.sub("", (nom or "").strip()))


def _periode(data: dict) -> tuple[date, date]:
    """(du, au) inclus. `annee`, ou `du` / `au` ; sans rien, les douze derniers mois pleins."""
    from skills.erreurs import SkillError
    from skills.lecture import lire_date
    annee = str(data.get("annee") or "").strip()
    if annee.isdigit() and len(annee) == 4:
        return date(int(annee), 1, 1), date(int(annee), 12, 31)
    du, _ = lire_date(str(data.get("du") or data.get("debut") or data.get("depuis") or ""))
    au, _ = lire_date(str(data.get("au") or data.get("fin") or data.get("jusqu_au") or ""))
    if bool(data.get("du") or data.get("debut") or data.get("depuis")) and not du:
        raise SkillError("La date de début n'est pas lisible : écris-la jour/mois/année (01/09/2025).")
    if bool(data.get("au") or data.get("fin") or data.get("jusqu_au")) and not au:
        raise SkillError("La date de fin n'est pas lisible : écris-la jour/mois/année (31/08/2026).")
    au = au or date.today()
    if not du:
        du = date(au.year - 1, au.month, 1)
    if du > au:
        raise SkillError("La période est à l'envers : la date de début est après la date de fin.")
    return du, au


def retenir_une_piece_par_numero(pieces: list[dict]) -> tuple[list[dict], int]:
    """Un exemplaire par numéro de facture : celui dont la somme des lignes retrouve le total,
    sinon celui qui a un total, sinon le dernier lu. Rend (pièces gardées, exemplaires écartés)."""
    meilleures: dict[str, dict] = {}
    for p in pieces:
        cle = p.get("numero") or f"fichier:{p.get('fichier_id')}"
        rang = (p.get("controle") == "juste", p.get("total_ht") is not None, str(p.get("lu_le") or ""))
        if cle not in meilleures or rang > meilleures[cle]["_rang"]:
            meilleures[cle] = {**p, "_rang": rang}
    return [{k: v for k, v in p.items() if k != "_rang"} for p in meilleures.values()], len(pieces) - len(meilleures)


def calculer(pieces: list[dict], du: date, au: date, facture_min: float = 0.0) -> dict:
    """Le calcul, PUR : dédoublonne, borne à la période, somme par mois et par client.
    `facture_min` (18/09) : « sans compter les factures de moins de 500 € » — écartées AVANT le calcul,
    et comptées à part ; sans lui, le modèle partait sur le jeu importé, qui n'est pas la même base."""
    uniques, doublons = retenir_une_piece_par_numero(pieces)
    sans_date = [p for p in uniques if not isinstance(p.get("date_piece"), date)]
    dans = [p for p in uniques if isinstance(p.get("date_piece"), date) and du <= p["date_piece"] <= au]
    illisibles = [p for p in dans if p.get("total_ht") is None]
    retenues = [p for p in dans if p.get("total_ht") is not None]
    sous_le_seuil = 0
    if facture_min and facture_min > 0:
        avant = len(retenues)
        retenues = [p for p in retenues if p.get("nature") == "avoir" or abs(float(p["total_ht"])) >= facture_min]
        sous_le_seuil = avant - len(retenues)
    for p in retenues:
        p["montant"] = -abs(float(p["total_ht"])) if p.get("nature") == "avoir" else float(p["total_ht"])
    total = round(sum(p["montant"] for p in retenues), 2)

    mensuel: dict[tuple, list] = {}
    for p in retenues:
        cle = (p["date_piece"].year, p["date_piece"].month)
        mensuel.setdefault(cle, [0, 0.0])
        mensuel[cle][0] += 1
        mensuel[cle][1] += p["montant"]

    clients: dict[str, dict] = {}
    for p in retenues:
        cle = _cle_client(p.get("client") or "", p.get("code_client") or "")
        if cle == "nom:":
            cle = "inconnu"
        c = clients.setdefault(cle, {"noms": {}, "factures": 0, "total": 0.0})
        nom = " ".join((p.get("client") or "").split()) or "(client non lu sur la facture)"
        c["noms"][nom] = c["noms"].get(nom, 0) + 1
        c["factures"] += 1
        c["total"] += p["montant"]
    classement = []
    for c in clients.values():
        noms = sorted(c["noms"].items(), key=lambda x: -x[1])
        classement.append({"client": noms[0][0], "variantes": [n for n, _ in noms[1:]],
                           "factures": c["factures"], "total": round(c["total"], 2),
                           "panier_moyen": round(c["total"] / c["factures"], 2),
                           "part": round(100 * c["total"] / total, 1) if total else 0.0})
    classement.sort(key=lambda c: -c["total"])
    return {"total": total, "retenues": retenues, "doublons": doublons, "illisibles": illisibles,
            "sans_date": sans_date, "mensuel": sorted(mensuel.items()), "clients": classement,
            "avoirs": sum(1 for p in retenues if p.get("nature") == "avoir"),
            "factures_sous_le_seuil": sous_le_seuil,
            "somme_clients": round(sum(c["total"] for c in classement), 2)}


async def chiffre_affaires(data: dict, user) -> dict:
    """Le chiffre d'affaires HT d'une période, par mois et par client, depuis les factures lues."""
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError

    du, au = _periode(data)
    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            lignes = await conn.fetch(
                "SELECT fichier_id, fichier_nom, nature, numero, date_piece, total_ht, controle, "
                "       client, code_client, methode, lu_le "
                "FROM pieces_chiffrees WHERE etat = 'lue' AND nature IN ('facture', 'avoir') "
                "  AND access_level = ANY($1::text[])", niveaux)
            from prix.lignes import VERSION
            reste = await conn.fetchval(
                "SELECT count(*) FROM pieces_chiffrees WHERE methode IS NULL OR methode NOT LIKE $1",
                f"%/{VERSION}")
    except Exception as e:  # noqa: BLE001
        logger.warning("Chiffre d'affaires impossible : %s", str(e)[:160])
        raise SkillError("La base des factures n'est pas disponible : elle se constitue en tâche de "
                         "fond à partir des PDF du classement. Réessayez plus tard.")
    if not lignes:
        raise SkillError("Aucune facture n'a encore été lue dans le classement : le chiffre d'affaires "
                         "ne peut pas être calculé. N'avance aucun montant.")

    from skills.lecture import lire_montant
    facture_min = lire_montant(data.get("facture_min") or data.get("montant_min") or data.get("minimum") or 0)
    r = calculer([dict(l) for l in lignes], du, au, facture_min)
    periode = f"du {du.strftime('%d/%m/%Y')} au {au.strftime('%d/%m/%Y')}"
    sans_client = sum(c["factures"] for c in r["clients"] if c["client"].startswith("(client non lu"))
    fusions = [{"client": c["client"], "regroupe_aussi": c["variantes"]} for c in r["clients"] if c["variantes"]]
    tableau_mois = [[f"{MOIS[m - 1]} {a}", str(n), _euros(t)] for (a, m), (n, t) in r["mensuel"]]
    # LES FACTURES DONT LE CLIENT N'A PAS ÉTÉ LU NE SONT PAS « UN CLIENT ». Premier essai réel : le
    # lot sortait en tête du classement avec 76 % du chiffre. Il compte dans le TOTAL, il se déclare
    # à part, et le classement ne porte que des clients nommés.
    nommes = [c for c in r["clients"] if not c["client"].startswith("(client non lu")]
    non_lus = [c for c in r["clients"] if c["client"].startswith("(client non lu")]
    tete = nommes[:MAX_CLIENTS_A_L_ECRAN]
    tableau_clients = [[c["client"], str(c["factures"]), _euros(c["total"]), _euros(c["panier_moyen"]),
                        f"{c['part']:.1f} %".replace(".", ",")] for c in tete]
    blocs = [{"type": "table", "titre": f"Chiffre d'affaires HT {periode} : {_euros(r['total'])}",
              "columns": ["Mois", "Factures", "Total HT"], "rows": tableau_mois},
             {"type": "table", "titre": f"Les {len(tete)} premiers clients sur {len(nommes)}",
              "columns": ["Client", "Factures", "Total HT", "Panier moyen", "Part"], "rows": tableau_clients}]
    queue = nommes[-MAX_CLIENTS_A_L_ECRAN:] if len(nommes) > 2 * MAX_CLIENTS_A_L_ECRAN else []
    if queue and str(data.get("classement") or "").lower() in ("true", "1", "oui", "complet"):
        blocs.append({"type": "table", "titre": f"Les {len(queue)} derniers clients",
                      "columns": ["Client", "Factures", "Total HT", "Panier moyen", "Part"],
                      "rows": [[c["client"], str(c["factures"]), _euros(c["total"]), _euros(c["panier_moyen"]),
                                f"{c['part']:.1f} %".replace(".", ",")] for c in queue]})

    resultat = {
        "periode": periode, "chiffre_affaires_ht": _euros(r["total"]),
        "factures_retenues": len(r["retenues"]), "dont_avoirs_en_moins": r["avoirs"],
        "exemplaires_en_double_ecartes": r["doublons"],
        "factures_ecartees_sous_le_seuil": ({"seuil_ht": _euros(facture_min), "nombre": r["factures_sous_le_seuil"]}
                                            if facture_min else None),
        "factures_sans_total_lisible": [{"numero": p.get("numero"), "fichier": p.get("fichier_nom"),
                                         "date": p["date_piece"].isoformat()} for p in r["illisibles"][:40]],
        "factures_sans_date_lisible": len(r["sans_date"]),
        "clients": len(nommes), "factures_sans_client_lu": sans_client,
        "montant_sans_client_lu": _euros(sum(c["total"] for c in non_lus)) if non_lus else None,
        "trois_premiers": [{"client": c["client"], "total": _euros(c["total"]), "part": c["part"]}
                           for c in nommes[:3]],
        "noms_regroupes": fusions[:30],
        "controle": ("la somme des clients égale le total" if abs(r["somme_clients"] - r["total"]) < 0.01
                     else f"ÉCART : clients {_euros(r['somme_clients'])} / total {_euros(r['total'])}"),
        "methode": ("factures de vente lues dans les PDF du classement, montants HT, date de facture, une "
                    "facture comptée une fois par numéro, avoirs en moins, devis exclus"),
        "bloc_ui": blocs, "bloc_garanti": True,
    }
    if reste:
        resultat["base_en_cours_de_lecture"] = (
            f"{reste} pièce(s) du classement n'ont pas encore été relues avec le client : le chiffre "
            "peut monter, et des clients apparaître, d'ici la fin de la lecture.")

    if str(data.get("fichier") or "").lower() in ("true", "1", "oui"):
        import asyncio
        from bureautique.atelier import ajouter, ouvrir, terminer
        proprio = str(getattr(user, "id", "") or "")
        entete = {"titre": f"Chiffre d'affaires {periode.replace('/', '-')}", "format": "xlsx"}
        elements = [
            {"type": "feuille", "nom": "Factures retenues",
             "entetes": ["Numéro", "Date", "Client", "Montant HT", "Nature", "Fichier"],
             "lignes": [[p.get("numero") or "", p["date_piece"].strftime("%d/%m/%Y"), p.get("client") or "",
                         round(p["montant"], 2), p.get("nature") or "", p.get("fichier_nom") or ""]
                        for p in sorted(r["retenues"], key=lambda p: p["date_piece"])]},
            {"type": "feuille", "nom": "Par mois", "entetes": ["Mois", "Factures", "Total HT"],
             "lignes": [[f"{MOIS[m - 1]} {a}", n, round(t, 2)] for (a, m), (n, t) in r["mensuel"]]},
            {"type": "feuille", "nom": "Par client",
             "entetes": ["Client", "Factures", "Total HT", "Panier moyen", "Part %", "Autres écritures regroupées"],
             "lignes": [[c["client"], c["factures"], c["total"], c["panier_moyen"], c["part"],
                         " ; ".join(c["variantes"])] for c in r["clients"]]},
            {"type": "feuille", "nom": "Non comptées", "entetes": ["Numéro", "Date", "Fichier", "Motif"],
             "lignes": [[p.get("numero") or "", p["date_piece"].strftime("%d/%m/%Y"), p.get("fichier_nom") or "",
                         "total HT illisible"] for p in r["illisibles"]]
                       + [[p.get("numero") or "", "", p.get("fichier_nom") or "", "date illisible"]
                          for p in r["sans_date"]]}]

        def _produire():
            jeton = ouvrir(entete, proprio)
            ajouter(jeton, elements, proprio)
            return jeton, terminer(jeton, proprio)
        try:
            jeton, fiche = await asyncio.to_thread(_produire)
            blocs.append({"type": "fichier", "url": f"/api/documents/{jeton}", "nom": "chiffre-affaires.xlsx",
                          "titre": entete["titre"], "format": "xlsx", "octets": fiche.get("octets")})
            resultat["fichier"] = f"/api/documents/{jeton}"
        except Exception as e:  # noqa: BLE001
            logger.warning("Excel du chiffre d'affaires impossible : %s", str(e)[:160])
            resultat["fichier_non_produit"] = "le classeur n'a pas pu être produit ; les chiffres ci-dessus restent justes"

    resultat["message_final"] = (
        f"Chiffre d'affaires HT {periode} : {_euros(r['total'])}, sur {len(r['retenues'])} facture(s) "
        f"et {len(nommes)} client(s) nommé(s)."
        + (f" {sans_client} facture(s) n'ont pas encore leur client." if sans_client else ""))
    resultat["a_faire"] = (
        "Les tableaux s'affichent AUTOMATIQUEMENT : ne les recopie pas. Donne le total et la MÉTHODE en "
        "une phrase, la part des trois premiers clients, puis DÉCLARE ce que le contrôle exige : le nombre "
        "de factures retenues, les exemplaires en double écartés, les factures sans total ou sans date "
        "lisible (nomme-les si elles sont peu nombreuses), les noms regroupés. Tous les montants se "
        "recopient de ce résultat : n'additionne rien toi-même, n'extrapole aucun mois incomplet. "
        "Si `base_en_cours_de_lecture` est présent, dis-le : le chiffre n'est pas encore définitif.")
    return resultat


def classer_articles(lignes: list[dict], combien: int = 10, par: str = "frequence") -> list[dict]:
    """Les ouvrages et articles qui reviennent le plus, PUR. Une même ligne d'une même pièce
    (copies du PDF) ne compte qu'une fois ; deux écritures proches se regroupent par leur tête."""
    from prix.releve import plat, sans_doublons, tete
    groupes: dict[str, dict] = {}
    for l in sans_doublons(lignes):
        # La clé : les trois premiers mots qui portent du sens. « Tonte du gazon et ramassage » et
        # « Tonte du gazon et ramassage des déchets » sont le même ouvrage.
        from prix.releve import _MOTS_CREUX
        cle = " ".join([m for m in tete(l.get("designation")).split()
                        if len(m) >= 4 and m not in _MOTS_CREUX][:3])
        if len(cle) < 4:
            continue
        g = groupes.setdefault(cle, {"libelles": {}, "pieces": set(), "quantite": 0.0, "montant": 0.0, "unites": {}})
        lib = " ".join(str(l.get("designation") or "").split())[:90]
        g["libelles"][lib] = g["libelles"].get(lib, 0) + 1
        g["pieces"].add(l.get("numero") or l.get("fichier_id"))
        g["quantite"] += float(l.get("quantite") or 0)
        g["montant"] += float(l.get("montant_ht") or 0)
        u = plat(l.get("unite")) or "—"
        g["unites"][u] = g["unites"].get(u, 0) + 1
    rendus = [{"article": max(g["libelles"].items(), key=lambda x: x[1])[0], "pieces": len(g["pieces"]),
               "quantite": round(g["quantite"], 2), "unite": max(g["unites"].items(), key=lambda x: x[1])[0],
               "montant_ht": round(g["montant"], 2)} for g in groupes.values()]
    cle_tri = (lambda r: -r["montant_ht"]) if str(par).lower().startswith("montant") else (lambda r: (-r["pieces"], -r["montant_ht"]))
    return sorted(rendus, key=cle_tri)[:max(1, min(int(combien or 10), 50))]


async def articles_frequents(data: dict, user) -> dict:
    """Les articles et ouvrages les plus facturés (ou devisés) sur une période."""
    from datetime import timedelta
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError
    try:
        mois = max(1, min(int(str(data.get("mois") or 24)), 120))
    except ValueError:
        mois = 24
    nature = "devis" if "devis" in str(data.get("nature") or "").lower() else "facture"
    contient = " ".join(str(data.get("contient") or "").split())
    depuis = date.today() - timedelta(days=round(30.44 * mois))
    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            lignes = await conn.fetch(
                "SELECT l.designation, l.unite, l.quantite, l.pu_ht, l.montant_ht, p.numero, p.fichier_id "
                "FROM lignes_chiffrees l JOIN pieces_chiffrees p USING (fichier_id) "
                "WHERE p.etat = 'lue' AND p.nature = $1 AND p.date_piece >= $2 "
                "  AND p.access_level = ANY($3::text[]) LIMIT 60000", nature, depuis, niveaux)
    except Exception as e:  # noqa: BLE001
        logger.warning("Classement des articles impossible : %s", str(e)[:160])
        raise SkillError("La base des lignes de factures n'est pas disponible pour l'instant.")
    lignes = [dict(l) for l in lignes]
    if contient:
        from prix.releve import correspond, mots_cles, plat
        racines = mots_cles(contient)
        lignes = [l for l in lignes if correspond(plat(l["designation"]), racines)]
    classement = classer_articles(lignes, data.get("combien") or 10, data.get("par") or "frequence")
    if not classement:
        return {"trouve": False, "message": f"Aucune ligne de {nature} lue sur les {mois} derniers mois"
                                            + (f" ne parle de « {contient} »." if contient else "."),
                "a_faire": "Dis-le tel quel, sans rien avancer."}
    # LE TOTAL DE TOUTES LES LIGNES RETENUES, pas des dix premières (18/09, question « combien avons-nous
    # devisé et facturé en terrasses bois ») : appelé une fois en `nature: devis` et une fois en
    # `facture` avec le même `contient`, ce geste donne les deux montants à comparer.
    total_lignes = round(sum(float(l.get("montant_ht") or 0) for l in lignes), 2)
    pieces_distinctes = len({l.get("numero") or l.get("fichier_id") for l in lignes})
    return {"trouve": True, "nature": nature, "periode": f"les {mois} derniers mois", "lignes_analysees": len(lignes),
            "total_ht_de_toutes_les_lignes": _euros(total_lignes), "pieces_concernees": pieces_distinctes,
            "classement": classement, "bloc_garanti": True,
            "bloc_ui": {"type": "table", "titre": f"Les {len(classement)} articles les plus {'devisés' if nature == 'devis' else 'facturés'} — {mois} derniers mois",
                        "columns": ["Article ou ouvrage", "Pièces", "Quantité", "Unité", "Montant HT"],
                        "rows": [[c["article"], str(c["pieces"]), f"{c['quantite']:g}", c["unite"], _euros(c["montant_ht"])]
                                 for c in classement]},
            "message_final": f"Classement établi sur {len(lignes)} ligne(s) de {nature}.",
            "a_faire": ("Le tableau s'affiche AUTOMATIQUEMENT : ne le recopie pas. Ce sont des lignes de VENTE lues dans "
                        "les factures de la maison, pas des achats chez les fournisseurs : dis-le si la demande parlait "
                        "d'achats. Deux écritures proches d'un même ouvrage sont regroupées ; les montants se recopient tels quels. "
                        "`total_ht_de_toutes_les_lignes` porte sur TOUTES les lignes retenues (pas seulement le classement) : "
                        "pour comparer DEVISÉ et FACTURÉ d'un ouvrage, appelle ce geste deux fois avec le même `contient` "
                        "(`nature: \"devis\"` puis `\"facture\"`) — et dis qu'un devis et sa facture ne sont pas reliés un à "
                        "un : le rapport des deux montants est un ordre de grandeur, pas un taux de transformation exact.")}


MIN_PASSAGES_FIABLES = 3
_UNITES_D_HEURE = ("h", "heure", "heures", "hr", "hrs")


def frequences_par_client(lignes: list[dict]) -> list[dict]:
    """PUR. Des lignes de factures (client, code_client, numero, date_piece, unite, quantite, montant_ht)
    → par client : le nombre de PASSAGES (une facture datée = un passage), la première et la dernière
    date, l'intervalle moyen entre deux passages, les heures par passage quand l'unité est l'heure.
    Moins de trois passages : la fréquence est calculée mais marquée NON FIABLE."""
    par_client: dict[str, dict] = {}
    for l in lignes:
        if not isinstance(l.get("date_piece"), date):
            continue
        cle = _cle_client(l.get("client") or "", l.get("code_client") or "")
        c = par_client.setdefault(cle, {"client": l.get("client") or "(client non lu sur la pièce)", "passages": {}})
        passage = c["passages"].setdefault(l.get("numero") or f"fichier:{l.get('fichier_id')}",
                                           {"date": l["date_piece"], "heures": 0.0, "montant": 0.0})
        if str(l.get("unite") or "").strip().lower().rstrip(".") in _UNITES_D_HEURE:
            passage["heures"] += float(l.get("quantite") or 0)
        passage["montant"] += float(l.get("montant_ht") or 0)
    sortie = []
    for c in par_client.values():
        passages = sorted(c["passages"].values(), key=lambda x: x["date"])
        n = len(passages)
        jours = (passages[-1]["date"] - passages[0]["date"]).days
        heures = [x["heures"] for x in passages if x["heures"] > 0]
        sortie.append({"client": c["client"], "passages": n,
                       "premier": passages[0]["date"], "dernier": passages[-1]["date"],
                       "intervalle_moyen_jours": round(jours / (n - 1)) if n > 1 else None,
                       "passages_par_an": round(365.25 * (n - 1) / jours, 1) if n > 1 and jours > 0 else None,
                       "heures_par_passage": round(sum(heures) / len(heures), 2) if heures else None,
                       "montant_ht": round(sum(x["montant"] for x in passages), 2),
                       "donnee_incomplete": n < MIN_PASSAGES_FIABLES})
    sortie.sort(key=lambda x: (-(x["passages_par_an"] or 0), -x["passages"]))
    return sortie


async def frequence_des_passages(data: dict, user) -> dict:
    """Pour chaque client, combien de fois on lui a facturé une prestation (« entretien »), à quel
    rythme et pour combien d'heures — lu dans les factures DATÉES du classement (18/09, prompt 18).

    Le jeu importé « facture » porte les lignes `mainentretien` SANS date : la fréquence y est
    incalculable, et l'assistant l'a dit. Les mêmes lignes existent, datées, dans les PDF lus."""
    from datetime import timedelta
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError
    from prix.releve import correspond, mots_cles, plat
    try:
        mois = max(1, min(int(str(data.get("mois") or 12)), 120))
    except ValueError:
        mois = 12
    contient = " ".join(str(data.get("contient") or data.get("prestation") or "entretien").split())
    depuis = date.today() - timedelta(days=round(30.44 * mois))
    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            lignes = await conn.fetch(
                "SELECT l.designation, l.rubrique, l.unite, l.quantite, l.montant_ht, p.numero, p.fichier_id, "
                "       p.date_piece, p.client, p.code_client, p.titre "
                "FROM lignes_chiffrees l JOIN pieces_chiffrees p USING (fichier_id) "
                "WHERE p.etat = 'lue' AND p.nature = 'facture' AND p.date_piece >= $1 "
                "  AND p.access_level = ANY($2::text[]) LIMIT 60000", depuis, niveaux)
    except Exception as e:  # noqa: BLE001
        logger.warning("Fréquence des passages impossible : %s", str(e)[:160])
        raise SkillError("La base des lignes de factures n'est pas disponible pour l'instant.")
    racines = mots_cles(contient)
    gardees = [dict(l) for l in lignes
               if correspond(plat(f"{l['rubrique']} {l['designation']} {l['titre'] or ''}"), racines)]
    clients = frequences_par_client(gardees)
    if not clients:
        return {"trouve": False,
                "message": f"Aucune ligne de facture datée des {mois} derniers mois ne parle de « {contient} ».",
                "a_faire": "Dis-le tel quel, sans avancer aucune fréquence."}
    sans_client = [c for c in clients if c["client"].startswith("(client non lu")]
    nommes = [c for c in clients if not c["client"].startswith("(client non lu")]

    def _rangee(c: dict) -> list:
        return [c["client"], c["passages"], c["premier"].strftime("%d/%m/%Y"), c["dernier"].strftime("%d/%m/%Y"),
                f"{c['intervalle_moyen_jours']} j" if c["intervalle_moyen_jours"] is not None else "",
                f"{c['passages_par_an']:g}" if c["passages_par_an"] is not None else "",
                f"{c['heures_par_passage']:g} h" if c["heures_par_passage"] is not None else "",
                _euros(c["montant_ht"]), "OUI (moins de 3 passages)" if c["donnee_incomplete"] else ""]
    colonnes = ["Client", "Passages facturés", "Premier", "Dernier", "Intervalle moyen", "Passages / an",
                "Heures / passage", "Montant HT", "Donnée incomplète"]
    blocs = [{"type": "table", "titre": f"Fréquence des passages « {contient} » — {mois} derniers mois ({len(nommes)} clients)",
              "columns": colonnes, "rows": [_rangee(c) for c in nommes[:300]]}]
    veut_fichier = str(data.get("fichier") or "").strip().lower() in ("true", "1", "oui", "yes", "xlsx", "excel")
    if veut_fichier:
        import asyncio
        from bureautique.atelier import ouvrir, ajouter, terminer
        proprio = str(getattr(user, "id", "") or "")
        titre_f = f"Fréquence des passages — {contient}"

        def _produire():
            jeton = ouvrir({"titre": titre_f, "format": "xlsx"}, proprio)
            ajouter(jeton, [{"type": "feuille", "nom": "Fréquences", "entetes": colonnes,
                             "lignes": [_rangee(c) for c in nommes]}], proprio)
            return jeton, terminer(jeton, proprio)
        try:
            jeton, fiche = await asyncio.to_thread(_produire)
            blocs.append({"type": "fichier", "url": f"/api/documents/{jeton}", "nom": "frequence-passages.xlsx",
                          "titre": titre_f, "format": "xlsx", "octets": fiche.get("octets")})
        except Exception as e:  # noqa: BLE001 — le tableau reste à l'écran
            logger.warning("Excel des fréquences impossible : %s", e)
    return {
        "trouve": True, "prestation": contient, "periode": f"les {mois} derniers mois",
        "clients": len(nommes), "fiables": sum(1 for c in nommes if not c["donnee_incomplete"]),
        "lignes_retenues": len(gardees),
        "passages_sans_client_lu": sum(c["passages"] for c in sans_client) or None,
        "bloc_garanti": True, "bloc_ui": blocs if len(blocs) > 1 else blocs[0],
        "message_final": (f"{len(nommes)} client(s) facturés pour « {contient} » sur les {mois} derniers mois, "
                          f"dont {sum(1 for c in nommes if not c['donnee_incomplete'])} avec au moins "
                          f"{MIN_PASSAGES_FIABLES} passages."),
        "a_faire": ("Le tableau s'affiche AUTOMATIQUEMENT : ne le recopie pas. UN PASSAGE = UNE FACTURE DATÉE qui "
                    "porte la prestation : c'est une fréquence de FACTURATION ; si la maison facture plusieurs "
                    "passages sur une même facture, la fréquence réelle est plus haute — dis-le. « Donnée "
                    "incomplète » = moins de trois passages : fréquence non fiable. La fréquence CONTRACTUELLE "
                    "n'est écrite dans aucune donnée : ne conclus à aucun écart avec un contrat sans l'avoir lu."),
    }


def resumer_les_pieces(pieces: list[dict]) -> dict:
    """PUR : une pièce par numéro, du plus récent au plus ancien, et les totaux par nature."""
    uniques, doublons = retenir_une_piece_par_numero(pieces)
    uniques.sort(key=lambda p: str(p.get("date_piece") or ""), reverse=True)

    def somme(nature: str) -> float:
        return round(sum(float(p["total_ht"]) for p in uniques
                         if p.get("nature") == nature and p.get("total_ht") is not None), 2)
    facture = round(somme("facture") - somme("avoir"), 2)
    return {"pieces": uniques, "copies_ecartees": doublons,
            "devis": sum(1 for p in uniques if p.get("nature") == "devis"),
            "factures": sum(1 for p in uniques if p.get("nature") == "facture"),
            "avoirs": sum(1 for p in uniques if p.get("nature") == "avoir"),
            "total_devise": somme("devis"), "total_facture": facture,
            "sans_total": [p.get("numero") or p.get("fichier_nom") for p in uniques if p.get("total_ht") is None]}


async def pieces_du_client(data: dict, user) -> dict:
    """Les devis et factures d'UN client, lus dans les PDF du classement (18/09, prompt 13).

    « Consolide son dossier : devis, factures, total facturé » ne trouvait que les jeux importés :
    un devis, une facture — alors que le classement porte onze factures et trois devis à son nom."""
    import unicodedata
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError

    nom = str(data.get("client") or data.get("nom") or "").strip()
    if len(nom) < 2:
        raise SkillError("Donne le `client` (son nom de famille suffit).")
    plat = "".join(c for c in unicodedata.normalize("NFD", nom.lower()) if unicodedata.category(c) != "Mn")
    mots = [m for m in plat.replace("-", " ").split() if len(m) >= 3 and m not in ("mme", "mlle", "mrs", "madame", "monsieur", "les", "des")]
    if not mots:
        raise SkillError("Ce nom est trop court pour chercher sans confondre : donne le nom de famille.")
    # Le mot le PLUS LONG du nom suffit à trouver (un prénom manque souvent sur la pièce) ; les
    # autres mots ne servent qu'à dire si la pièce les porte aussi.
    pivot = max(mots, key=len)
    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            lignes = await conn.fetch(
                "SELECT fichier_id, fichier_nom, nature, numero, date_piece, titre, total_ht, controle, "
                "       client, code_client, lu_le "
                "FROM pieces_chiffrees WHERE etat = 'lue' AND access_level = ANY($1::text[]) "
                # Sans accents des DEUX côtés : « LÉVÊQUE » sur la pièce, « leveque » dans la demande.
                "  AND (translate(lower(coalesce(client, '')), 'àâäéèêëîïôöùûüç', 'aaaeeeeiioouuuc') LIKE $2 "
                "    OR translate(lower(fichier_nom), 'àâäéèêëîïôöùûüç', 'aaaeeeeiioouuuc') LIKE $2) "
                "LIMIT 600", niveaux, f"%{pivot}%")
    except Exception as e:  # noqa: BLE001
        logger.warning("Pièces du client impossibles : %s", str(e)[:160])
        raise SkillError("La base des pièces lues dans le classement n'est pas disponible. Réessayez plus tard.")
    # LE MOT LE PLUS LONG TROUVE, LES AUTRES DÉPARTAGENT (18/09, E3) : « VRD AQUITAIN » rendait les
    # trente pièces de « CRCAM Aquitaine » sous le titre « VRD AQUITAIN (30) ». Quand des pièces
    # portent TOUS les mots du nom, elles seules comptent ; sinon on garde les pièces du pivot mais
    # on DIT que la correspondance est partielle, et le modèle doit vérifier les noms lus.
    def _plat(texte: str) -> str:
        return "".join(c for c in unicodedata.normalize("NFD", str(texte or "").lower())
                       if unicodedata.category(c) != "Mn")
    entieres = [l for l in lignes
                if all(m in _plat(f"{l['client']} {l['fichier_nom']}") for m in mots)]
    correspondance = "tous les mots du nom"
    if entieres:
        lignes = entieres
    elif len(mots) > 1:
        correspondance = f"partielle : seul « {pivot} » est retrouvé sur ces pièces"
    r = resumer_les_pieces([dict(l) for l in lignes])
    if not r["pieces"]:
        return {"trouve": False, "client": nom,
                "message_final": f"Aucun devis ni facture au nom de « {nom} » parmi les pièces lues dans le classement.",
                "a_faire": ("Dis-le tel quel. Ce n'est PAS la preuve qu'il n'en existe pas : la base ne porte que "
                            "les PDF déjà lus, et le nom du client n'est pas lu sur toutes. Cherche aussi son "
                            "dossier par `drive_chercher`.")}
    rangees = [[p.get("nature") or "", p.get("numero") or "", p["date_piece"].strftime("%d/%m/%Y") if p.get("date_piece") else "",
                (p.get("titre") or "")[:70], _euros(float(p["total_ht"])) if p.get("total_ht") is not None else "non lu",
                p.get("client") or "(client non lu sur la pièce)", p.get("fichier_nom") or ""] for p in r["pieces"][:200]]
    homonymes = sorted({str(p.get("client")) for p in r["pieces"] if p.get("client")})
    return {
        "trouve": True, "client": nom, "devis": r["devis"], "factures": r["factures"], "avoirs": r["avoirs"],
        "total_devise_ht": _euros(r["total_devise"]), "total_facture_ht": _euros(r["total_facture"]),
        "copies_ecartees": r["copies_ecartees"], "pieces_sans_total": r["sans_total"][:20] or None,
        "noms_lus_sur_les_pieces": homonymes[:12],
        "correspondance": correspondance,
        "bloc_garanti": True,
        "bloc_ui": {"type": "table",
                    "titre": (f"Devis et factures lus dans le classement — {nom} ({len(r['pieces'])})"
                              if entieres or len(mots) < 2 else
                              f"Pièces du classement portant « {pivot} » ({len(r['pieces'])}) — aucune au nom « {nom} » en entier"),
                    "columns": ["Nature", "Numéro", "Date", "Titre", "Total HT", "Client lu", "Fichier"], "rows": rangees},
        "message_final": (f"{r['devis']} devis et {r['factures']} facture(s) au nom de « {nom} » dans le classement : "
                          f"{_euros(r['total_facture'])} HT facturés"
                          + (f" (avoirs déduits : {r['avoirs']})" if r["avoirs"] else "")
                          + f", {_euros(r['total_devise'])} HT devisés."),
        "a_faire": ("Le tableau s'affiche AUTOMATIQUEMENT : ne le recopie pas. Les totaux sont calculés par le "
                    "serveur (une pièce par numéro, avoirs déduits) : cite-les tels quels, avec le NOM DU FICHIER "
                    "comme source. `noms_lus_sur_les_pieces` : si plusieurs clients différents portent ce nom, "
                    "DIS-LE et ne les additionne pas. « Réglée ou non » n'est écrit sur aucune pièce : ne "
                    "l'affirme jamais. Un devis n'est pas du chiffre d'affaires."
                    + ("" if entieres or len(mots) < 2 else
                       f" ⚠ CORRESPONDANCE PARTIELLE : aucune pièce ne porte « {nom} » en entier, seul "
                       f"« {pivot} » est retrouvé — compare `noms_lus_sur_les_pieces` au client demandé ; "
                       "si ce sont d'autres clients, dis qu'AUCUNE pièce n'est à son nom et n'attribue rien.")),
    }


SKILLS = {
    "articles_frequents": Declaration(
        fonction=articles_frequents,
        description=(
            "LES ARTICLES ET OUVRAGES QUI REVIENNENT LE PLUS dans les factures (ou les devis) de la maison : "
            "nombre de pieces, quantite, montant HT. Pour « le top 10 de ce qu'on vend le plus », « quels "
            "ouvrages on facture le plus souvent ». `mois` (24 par defaut), `combien` (10), `par` : "
            "\"frequence\" ou \"montant\", `nature` : \"facture\" ou \"devis\", `contient` : un mot pour ne "
            "garder qu'une famille (« piscine », « plantation »). Rend aussi le TOTAL HT de toutes les lignes retenues : "
            "pour « combien a-t-on devise / facture en terrasses bois », appelle-le en `devis` puis en `facture` avec le "
            "meme `contient`. Ce sont des VENTES, pas des achats fournisseurs"),
        requis=[], optionnels=["mois", "combien", "par", "nature", "contient"],
        effet="lecture",
        libelle="je classe les articles les plus facturés"),
    "frequence_des_passages": Declaration(
        fonction=frequence_des_passages,
        description=(
            "LA FREQUENCE DES PASSAGES PAR CLIENT pour une prestation (« entretien » par defaut), calculee par le "
            "serveur sur les factures DATEES lues dans le classement : passages factures, premiere et derniere "
            "date, intervalle moyen, passages par an, heures par passage, montant ; moins de 3 passages = donnee "
            "incomplete. Pour « la frequence d'entretien de chaque client », « combien de passages par an ». "
            "`contient` : la prestation, `mois` (12), `fichier: true` pour l'Excel. N'utilise PAS "
            "`interroger_donnees` pour cela : le fichier importe n'a pas les dates"),
        requis=[], optionnels=["contient", "mois", "fichier"],
        effet="lecture",
        libelle="je calcule la fréquence des passages par client"),
    "pieces_du_client": Declaration(
        fonction=pieces_du_client,
        description=(
            "LES DEVIS ET FACTURES D'UN CLIENT, lus dans les PDF du classement : nature, numero, date, titre, "
            "total HT, fichier — plus le TOTAL FACTURE et le total devise, calcules par le serveur (une piece "
            "par numero, avoirs deduits). A appeler pour « le dossier de tel client », « ses devis et ses "
            "factures », « combien lui a-t-on facture », EN PLUS de `fiche_client` (qui ne lit que les "
            "fichiers importes). `client` : son nom de famille"),
        requis=["client"], optionnels=[],
        effet="lecture",
        libelle="je rassemble les devis et factures du client"),
    "chiffre_affaires": Declaration(
        fonction=chiffre_affaires,
        description=(
            "LE CHIFFRE D'AFFAIRES HT d'une periode, CALCULE PAR LE SERVEUR a partir des factures de "
            "vente lues dans les PDF du classement : total, detail MOIS PAR MOIS, classement des CLIENTS "
            "(nombre de factures, total, panier moyen, part), noms regroupes, et la liste de ce qui n'a "
            "pas pu etre compte. A appeler pour « quel CA entre telle et telle date », « CA 2025 », "
            "« nos meilleurs clients », « portefeuille client ». `du` / `au` (jour/mois/annee) ou `annee` ; "
            "`classement: true` ajoute les dix derniers clients ; `fichier: true` produit l'Excel des "
            "factures retenues ; `facture_min` : ecarte les factures sous un montant HT (« sans compter les "
            "factures de moins de 500 € »). Un devis n'est jamais du chiffre d'affaires. N'OUVRE PAS les "
            "factures une a une pour les additionner : ce geste l'a deja fait, et il dedoublonne. C'EST LUI "
            "qui fait foi pour un CA ou un classement de clients, PAS `interroger_donnees` sur le jeu importe "
            "« facture » (un etat des affaires, sans date lisible sur la plupart des lignes)"),
        requis=[], optionnels=["du", "au", "annee", "classement", "fichier", "facture_min"],
        effet="lecture",
        libelle="je calcule le chiffre d'affaires"),
}
