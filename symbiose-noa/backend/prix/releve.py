"""
DES LIGNES CHIFFRÉES À UN ORDRE DE PRIX — fonctions pures, sans base ni réseau.

Une estimation n'est pas un prix : c'est ce que la maison a DÉJÀ pratiqué pour un ouvrage
comparable, rendu avec de quoi le vérifier (combien d'observations, sur quelle période,
quelle fourchette, quelles pièces). Trois règles tiennent ce module :

  1. ON NE MÉLANGE PAS LES UNITÉS. 182 € le m² et 9 000 € le forfait ne font pas une
     moyenne. Chaque unité a son relevé ; c'est l'appelant qui choisit celle qui sert.
  2. LE RÉCENT PRIME. Un prix de 2022 n'est pas un prix de 2026. Si les vingt-quatre
     derniers mois portent assez d'observations, le relevé s'y tient et le dit.
  3. UNE PIÈCE NE COMPTE QU'UNE FOIS. Le même devis vit en trois exemplaires dans le
     classement (l'original, l'envoi, le scan signé) : sans dédoublonnage, un seul devis
     ferait une « tendance ».
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta
from typing import Optional

MIN_OBSERVATIONS = 2
MOIS_RECENTS = 24
MIN_RECENTES = 3
MAX_EXEMPLES = 5
MAX_POSTES = 12

# Mots qui ne distinguent aucun ouvrage : ils sont dans une désignation sur deux.
_MOTS_CREUX = {"fourniture", "fournitures", "pose", "mise", "place", "oeuvre", "realisation",
               "travaux", "prestation", "prestations", "compris", "comprend", "avec", "pour",
               "dans", "sans", "sous", "selon", "type", "environ", "divers", "ensemble",
               "prix", "devis", "estimation", "cout", "tarif", "unitaire",
               "une", "des", "les", "aux", "par", "sur", "est", "son", "ses", "mes", "nos"}

_UNITES = {"m2": "m²", "m²": "m²", "m 2": "m²", "ml": "ml", "m": "ml", "m3": "m³", "m³": "m³",
           "u": "unité", "un": "unité", "unite": "unité", "unites": "unité", "pce": "unité",
           "piece": "unité", "pieces": "unité", "forfait": "forfait", "ft": "forfait",
           "fft": "forfait", "ens": "forfait", "ens.": "forfait", "ensemble": "forfait",
           "h": "heure", "heure": "heure", "heures": "heure", "j": "jour", "jour": "jour",
           "jours": "jour", "kg": "kg", "kgs": "kg", "t": "tonne", "tonne": "tonne",
           "tonnes": "tonne", "l": "litre", "litre": "litre", "litres": "litre"}


def plat(texte) -> str:
    """Sans accents, sans casse, sans ponctuation : la forme sous laquelle on cherche."""
    t = unicodedata.normalize("NFKD", str(texte or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9/]+", " ", t).split())


def unite_normale(unite) -> str:
    u = plat(unite)
    return _UNITES.get(u, u or "sans unité")


def serre(mot: str) -> str:
    """Les lettres doublées ramenées à une : « abatage » (écrit tel quel dans un devis du 20/07)
    et « abattage » sont le même ouvrage, « terasse » et « terrasse » aussi."""
    return re.sub(r"(.)\1+", r"\1", mot)


def mots_cles(poste: str) -> list[str]:
    """Les racines qui portent le sens d'un poste : « abattage d'arbres » → abatt, arbre.

    Une racine de cinq lettres rapproche « abattage », « abattre », « abattu » sans
    dictionnaire ; un mot de quatre lettres (« haie », « spa ») se garde entier."""
    racines: list[str] = []
    for mot in plat(poste).split():
        if len(mot) < 3 or mot in _MOTS_CREUX or mot.isdigit():
            continue
        # « arbres » et « arbre », « pins » et « pin » : le pluriel ne fait pas un autre mot.
        # La racine se compare en DÉBUT de mot, donc « boi » retrouve toujours « bois ».
        if len(mot) >= 4 and mot.endswith("s"):
            mot = mot[:-1]
        racine = serre(mot)[:5]
        if racine not in racines:
            racines.append(racine)
    return racines[:5]


def correspond(texte_plat: str, racines: list[str]) -> bool:
    """Toutes les racines sont dans le texte, chacune en DÉBUT de mot (« terra » ne doit pas
    trouver « parterre »)."""
    mots = [serre(m) for m in texte_plat.split()]
    return bool(racines) and all(any(m.startswith(r) for m in mots) for r in racines)


def mediane(valeurs: list[float]) -> float:
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2


# L'OUVRAGE SE NOMME EN TÊTE DE LIGNE. Une désignation fait jusqu'à quatre cents caractères et
# cite en passant tout ce qui l'entoure : « installation d'un arrosage automatique … avant
# engazonnement » n'est pas un engazonnement. Premier essai réel (17/09) : « engazonnement »
# rendait le prix d'un arrosage, « évacuation » celui d'un terrassement de piscine.
TETE_DE_DESIGNATION = 90


def tete(designation, rubrique="") -> str:
    """Ce qui NOMME la ligne : sa rubrique et le début de sa désignation, à plat."""
    d = " ".join(str(designation or "").split())
    coupe = d[:TETE_DE_DESIGNATION]
    if len(d) > TETE_DE_DESIGNATION and " " in coupe:
        coupe = coupe.rsplit(" ", 1)[0]          # jamais au milieu d'un mot
    return plat(f"{rubrique or ''} {coupe}")


def quartiles(valeurs: list[float]) -> tuple[float, float]:
    """(Q1, Q3) par interpolation : la fourchette COURANTE, celle que les extrêmes ne tirent pas."""
    v = sorted(valeurs)
    def a(q: float) -> float:
        pos = (len(v) - 1) * q
        bas = int(pos)
        haut = min(bas + 1, len(v) - 1)
        return v[bas] + (v[haut] - v[bas]) * (pos - bas)
    return a(0.25), a(0.75)


def sans_doublons(lignes: list[dict]) -> list[dict]:
    """Une même ligne d'une même pièce ne compte qu'une fois, quel que soit le nombre de
    copies du PDF. Sans numéro de pièce, c'est le fichier qui fait l'identité."""
    vues = set()
    gardees = []
    for l in lignes:
        cle = (l.get("numero") or l.get("fichier_id"), plat(l.get("designation"))[:120],
               round(float(l.get("pu_ht") or 0), 2), round(float(l.get("quantite") or 0), 3))
        if cle in vues:
            continue
        vues.add(cle)
        gardees.append(l)
    return gardees


def euros(valeur: float) -> str:
    entier, _, cents = f"{valeur:,.2f}".partition(".")
    return f"{entier.replace(',', ' ')},{cents} €"


def relever(lignes: list[dict], aujourd_hui: Optional[date] = None) -> list[dict]:
    """Un relevé PAR UNITÉ, le plus fourni d'abord. Chaque ligne d'entrée porte au moins
    `designation`, `unite`, `quantite`, `pu_ht`, et si possible `date`, `numero`, `nature`."""
    aujourd_hui = aujourd_hui or date.today()
    seuil = aujourd_hui - timedelta(days=30 * MOIS_RECENTS)
    par_unite: dict[str, list[dict]] = {}
    for l in sans_doublons(lignes):
        if float(l.get("pu_ht") or 0) <= 0:
            continue
        par_unite.setdefault(unite_normale(l.get("unite")), []).append(l)

    releves = []
    for unite, groupe in par_unite.items():
        recentes = [l for l in groupe if isinstance(l.get("date"), date) and l["date"] >= seuil]
        retenues, periode = groupe, "tout l'historique"
        if len(recentes) >= MIN_RECENTES:
            retenues, periode = recentes, f"les {MOIS_RECENTS} derniers mois"
        prix = [float(l["pu_ht"]) for l in retenues]
        dates = [l["date"] for l in retenues if isinstance(l.get("date"), date)]
        retenues = sorted(retenues, key=lambda l: l.get("date") or date.min, reverse=True)
        releves.append({
            "unite": unite,
            "observations": len(retenues),
            "observations_tout_historique": len(groupe),
            "periode_retenue": periode,
            "de": min(dates).isoformat() if dates else None,
            "a": max(dates).isoformat() if dates else None,
            "suffisant": len(retenues) >= MIN_OBSERVATIONS,
            "plus_bas": round(min(prix), 2), "median": round(mediane(prix), 2),
            "plus_haut": round(max(prix), 2),
            # La fourchette qui sert à ESTIMER : les quartiles dès quatre observations. Une
            # « réparation de terrasse » à 10 € le m² est une observation vraie, mais elle ne
            # doit pas faire le bas d'une estimation de terrasse neuve.
            "courant_bas": round(quartiles(prix)[0] if len(prix) >= 4 else min(prix), 2),
            "courant_haut": round(quartiles(prix)[1] if len(prix) >= 4 else max(prix), 2),
            "factures": sum(1 for l in retenues if l.get("nature") == "facture"),
            "devis": sum(1 for l in retenues if l.get("nature") == "devis"),
            "exemples": [{
                "designation": str(l.get("designation") or "")[:160],
                "quantite": float(l.get("quantite") or 0), "pu_ht": round(float(l["pu_ht"]), 2),
                "piece": " ".join(x for x in (l.get("nature"), l.get("numero")) if x),
                "date": l["date"].isoformat() if isinstance(l.get("date"), date) else None,
            } for l in retenues[:MAX_EXEMPLES]],
        })
    releves.sort(key=lambda r: (r["suffisant"], r["observations"]), reverse=True)
    return releves


def estimer(releve: dict, quantite: float) -> Optional[dict]:
    """Quantité × prix pratiqué : bas, médian, haut. None si le relevé est trop maigre."""
    if not releve or not releve.get("suffisant") or quantite <= 0:
        return None
    return {"quantite": quantite, "unite": releve["unite"],
            "bas": round(quantite * releve.get("courant_bas", releve["plus_bas"]), 2),
            "median": round(quantite * releve["median"], 2),
            "haut": round(quantite * releve.get("courant_haut", releve["plus_haut"]), 2)}
