"""
Le planning d'interventions, CALCULÉ PAR LE SERVEUR.

POURQUOI (18/09, recette pilotée, prompt 20). « Construis le planning d'avril à juin : une ligne
par intervention, une feuille par mois, 7 h par jour au plus, UNE seule équipe, tournées par
secteur. » Le modèle a écrit le classeur à la main, en plusieurs versements : pas de feuille
« Mai », des onglets en double (« AVRIL 20271 », « Synthèse_2 »), et une réponse qui annonçait
ce que le fichier ne contenait pas. 136 clients sur trois mois font quatre cents lignes sous
contrainte de capacité : c'est un calcul, pas une rédaction.

CE QUE FAIT LE GESTE. Il reçoit les lignes d'un tableau (`"lignes": "@tableau"`, le classeur ouvert
ou joint), des RÈGLES (« piscine : tous les 14 jours, 1,5 h »), une période, une capacité par
jour. Il place chaque passage sur un jour ouvré, en regroupant les villes, sans jamais dépasser
la capacité ; ce qui ne rentre pas est DIT (à décaler), jamais tassé. Il rend le classeur (une
feuille par mois, synthèse, hypothèses, à décaler) et les chiffres de charge.

CE QU'IL NE FAIT PAS : inventer une fréquence. Les règles viennent de la demande ou d'une
hypothèse que le modèle ANNONCE ; elles sont recopiées telles quelles dans la feuille « Hypothèses ».
"""
from __future__ import annotations

import logging
import unicodedata
from datetime import date, timedelta

from skills.registre import Declaration

logger = logging.getLogger("pluton.skills.planning")

MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")
JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MAX_INTERVENTIONS = 6000
MAX_JOURS_PERIODE = 400


def _plat(texte) -> str:
    t = unicodedata.normalize("NFD", str(texte or "").lower())
    return " ".join("".join(c for c in t if unicodedata.category(c) != "Mn").split())


def _jour(valeur, fin: bool = False) -> date | None:
    """Une date écrite par quelqu'un. « juin 2027 » en fin de période = le 30 juin, pas le 1er."""
    import calendar
    from skills.lecture import lire_date
    if isinstance(valeur, date):
        return valeur
    lu, precision = lire_date(str(valeur or ""))
    if lu is None:
        return None
    if fin and precision == "mois":
        return lu.replace(day=calendar.monthrange(lu.year, lu.month)[1])
    if fin and precision == "annee":
        return lu.replace(month=12, day=31)
    return lu


def _colonne(lignes: list[dict], *mots: str) -> str | None:
    """La première colonne dont le nom porte un de ces mots."""
    for ligne in lignes[:5]:
        for nom in ligne:
            if any(m in _plat(nom) for m in mots):
                return nom
    return None


def _nom_du_client(ligne: dict, col_nom: str | None, col_prenom: str | None) -> str:
    nom = str(ligne.get(col_nom) or "").strip() if col_nom else ""
    prenom = str(ligne.get(col_prenom) or "").strip() if col_prenom else ""
    return " ".join(x for x in (nom, prenom) if x) or "[NOM À COMPLÉTER]"


def lire_les_regles(brutes) -> list[dict]:
    """[{si: {colonne, contient}, prestation, tous_les_jours, duree_h}] — une règle illisible LÈVE."""
    from skills.erreurs import SkillError
    if isinstance(brutes, dict):
        brutes = [brutes]
    regles = []
    for r in brutes or []:
        if not isinstance(r, dict):
            continue
        try:
            periode = int(float(str(r.get("tous_les_jours") or r.get("periode_jours") or 0).replace(",", ".")))
            duree = float(str(r.get("duree_h") or r.get("duree") or 0).replace(",", ".").rstrip("h ").strip() or 0)
        except ValueError:
            raise SkillError("Une règle porte une fréquence ou une durée illisible : `tous_les_jours` (entier) et "
                             "`duree_h` (heures, ex. 1.5).")
        if periode < 1 or duree <= 0:
            raise SkillError("Chaque règle demande `tous_les_jours` (≥ 1) et `duree_h` (> 0).")
        si = r.get("si") if isinstance(r.get("si"), dict) else {}
        regles.append({"colonne": str(si.get("colonne") or "").strip(), "contient": _plat(si.get("contient")),
                       "prestation": str(r.get("prestation") or "Intervention").strip()[:80],
                       "periode": periode, "duree": round(duree, 2)})
    if not regles:
        raise SkillError("Donne au moins une règle dans `regles` : {\"si\": {\"colonne\": …, \"contient\": …}, "
                         "\"prestation\": …, \"tous_les_jours\": 30, \"duree_h\": 2}. Si la fréquence n'est écrite "
                         "nulle part, DIS ton hypothèse à la personne : elle sera recopiée dans le classeur.")
    return regles


def planifier(lignes: list[dict], regles: list[dict], du: date, au: date, heures_par_jour: float = 7.0,
              jours_ouvres=(0, 1, 2, 3, 4)) -> dict:
    """PUR. Place chaque passage sur un jour ouvré de SA fenêtre, villes regroupées, capacité tenue."""
    # « Prénom » CONTIENT « nom » : la colonne du nom est celle qui ne parle pas de prénom.
    col_prenom = _colonne(lignes, "prenom")
    col_nom = next((c for ligne in lignes[:5] for c in ligne
                    if "nom" in _plat(c) and "prenom" not in _plat(c)), None)
    col_ville = _colonne(lignes, "ville", "commune")
    col_cp = _colonne(lignes, "code postal", "cp")
    jours = [du + timedelta(days=k) for k in range((au - du).days + 1)]
    ouvres = [j for j in jours if j.weekday() in jours_ouvres]
    reste = {j: float(heures_par_jour) for j in ouvres}
    villes_du_jour: dict[date, set] = {j: set() for j in ouvres}
    places, a_decaler, sans_regle = [], [], 0

    demandes = []            # (début de fenêtre, fin de fenêtre, client, ville, cp, règle)
    for ligne in lignes:
        if not isinstance(ligne, dict):
            continue
        siennes = [r for r in regles
                   if not r["contient"] or r["contient"] in _plat(ligne.get(r["colonne"]) if r["colonne"]
                                                                  else " ".join(str(v) for v in ligne.values()))]
        if not siennes:
            sans_regle += 1
            continue
        client = _nom_du_client(ligne, col_nom, col_prenom)
        ville = str(ligne.get(col_ville) or "").strip() if col_ville else ""
        cp = str(ligne.get(col_cp) or "").strip() if col_cp else ""
        for r in siennes:
            debut = du
            while debut <= au:
                fin = min(au, debut + timedelta(days=r["periode"] - 1))
                demandes.append((debut, fin, client, ville, cp, r))
                debut = debut + timedelta(days=r["periode"])
    if len(demandes) > MAX_INTERVENTIONS:
        from skills.erreurs import SkillError
        raise SkillError(f"{len(demandes)} passages à placer : au-delà de {MAX_INTERVENTIONS}. Réduis la période "
                         "ou le nombre de clients.")
    # Par fenêtre, puis par SECTEUR (code postal, ville) : le premier jour qui a la place reçoit
    # le passage ; comme les villes se suivent, elles se regroupent sur les mêmes journées.
    demandes.sort(key=lambda d: (d[0], d[1], _plat(d[4])[:2], _plat(d[3]), _plat(d[2])))
    for debut, fin, client, ville, cp, r in demandes:
        fenetre = [j for j in ouvres if debut <= j <= fin]
        candidats = [j for j in fenetre if reste[j] + 1e-9 >= r["duree"]]
        memes = [j for j in candidats if _plat(ville) and _plat(ville) in villes_du_jour[j]]
        choisi = (memes or candidats or [None])[0]
        if choisi is None:
            a_decaler.append({"client": client, "ville": ville, "prestation": r["prestation"],
                              "duree": r["duree"], "fenetre": (debut, fin)})
            continue
        reste[choisi] -= r["duree"]
        villes_du_jour[choisi].add(_plat(ville))
        places.append({"date": choisi, "client": client, "ville": ville, "prestation": r["prestation"],
                       "duree": r["duree"]})
    places.sort(key=lambda p: (p["date"], _plat(p["ville"]), _plat(p["client"])))

    par_mois: dict[tuple, dict] = {}
    for j in ouvres:
        par_mois.setdefault((j.year, j.month), {"heures": 0.0, "interventions": 0, "jours_ouvres": 0})["jours_ouvres"] += 1
    for p in places:
        m = par_mois[(p["date"].year, p["date"].month)]
        m["heures"] += p["duree"]
        m["interventions"] += 1
    for m in par_mois.values():
        m["heures"] = round(m["heures"], 2)
        m["jours_de_travail"] = round(m["heures"] / heures_par_jour, 1) if heures_par_jour else 0
        m["taux_occupation"] = round(100 * m["heures"] / (m["jours_ouvres"] * heures_par_jour), 1) if m["jours_ouvres"] else 0.0
    semaines: dict[tuple, int] = {}
    for d in a_decaler:
        iso = d["fenetre"][0].isocalendar()
        semaines[(iso[0], iso[1])] = semaines.get((iso[0], iso[1]), 0) + 1
    return {"interventions": places, "a_decaler": a_decaler, "par_mois": par_mois,
            "semaines_en_surcharge": sorted(semaines.items()), "clients_sans_regle": sans_regle,
            "jour_le_plus_charge": round(heures_par_jour - min(reste.values()), 2) if reste else 0.0,
            "colonnes_lues": {"nom": col_nom, "prenom": col_prenom, "ville": col_ville, "code_postal": col_cp}}


async def planifier_interventions(data: dict, user) -> dict:
    """Le planning d'une équipe sur une période : classeur par mois, charge, surcharges, clients à décaler."""
    import asyncio
    from skills.erreurs import SkillError

    lignes = data.get("lignes") or data.get("clients") or data.get("tableau")
    if not isinstance(lignes, list) or not lignes or not isinstance(lignes[0], dict):
        raise SkillError("Passe `\"lignes\": \"@tableau\"` après avoir OUVERT le classeur des clients "
                         "(`drive_ouvrir`) ou l'avoir reçu en pièce jointe : ce geste travaille sur ses lignes.")
    du, au = _jour(data.get("du")), _jour(data.get("au"), fin=True)
    if not du or not au or au < du:
        raise SkillError("Donne la période : `du` et `au` (jour/mois/année).")
    if (au - du).days > MAX_JOURS_PERIODE:
        raise SkillError(f"La période dépasse {MAX_JOURS_PERIODE} jours : découpe-la.")
    try:
        capacite = float(str(data.get("heures_par_jour") or 7).replace(",", "."))
    except ValueError:
        capacite = 7.0
    capacite = max(1.0, min(capacite, 12.0))
    regles = lire_les_regles(data.get("regles"))
    trop_longues = [r["prestation"] for r in regles if r["duree"] > capacite]
    if trop_longues:
        raise SkillError(f"Une intervention de « {trop_longues[0]} » dure plus que la journée de {capacite:g} h : "
                         "elle ne rentre dans aucun jour. Revois la durée ou la capacité.")
    r = planifier(lignes, regles, du, au, capacite)
    if not r["interventions"]:
        raise SkillError("Aucune intervention n'a pu être placée : aucune ligne du tableau ne correspond aux règles "
                         "(vérifie `si.colonne` et `si.contient`).")

    entetes = ["Date", "Jour", "Client", "Ville", "Prestation", "Durée prévue (h)", "Statut"]
    feuilles = []
    for (annee, mois) in sorted(r["par_mois"]):
        du_mois = [p for p in r["interventions"] if (p["date"].year, p["date"].month) == (annee, mois)]
        feuilles.append({"type": "feuille", "nom": f"{MOIS[mois - 1].capitalize()} {annee}", "entetes": entetes,
                         "lignes": [[p["date"].strftime("%d/%m/%Y"), JOURS[p["date"].weekday()], p["client"], p["ville"],
                                     p["prestation"], p["duree"], "prévu"] for p in du_mois]})
    synthese = [[f"{MOIS[m - 1].capitalize()} {a}", v["interventions"], v["heures"], v["jours_de_travail"],
                 v["jours_ouvres"], f"{v['taux_occupation']:g} %"] for (a, m), v in sorted(r["par_mois"].items())]
    feuilles.append({"type": "feuille", "nom": "Synthèse",
                     "entetes": ["Mois", "Interventions", "Heures", "Jours de travail", "Jours ouvrés", "Taux d'occupation"],
                     "lignes": synthese})
    feuilles.append({"type": "feuille", "nom": "À décaler",
                     "entetes": ["Client", "Ville", "Prestation", "Durée (h)", "Fenêtre sans place"],
                     "lignes": [[d["client"], d["ville"], d["prestation"], d["duree"],
                                 f"du {d['fenetre'][0].strftime('%d/%m')} au {d['fenetre'][1].strftime('%d/%m/%Y')}"]
                                for d in r["a_decaler"]] or [["(aucun : tout rentre)", "", "", "", ""]]})
    feuilles.append({"type": "feuille", "nom": "Hypothèses",
                     "entetes": ["Règle", "Valeur"],
                     "lignes": [["Équipe", "UNE seule équipe, jours ouvrés du lundi au vendredi"],
                                ["Capacité", f"{capacite:g} h d'intervention par jour au plus"]]
                               + [[f"{x['prestation']}" + (f" (si « {x['colonne']} » contient « {x['contient']} »)" if x["contient"] else ""),
                                   f"un passage tous les {x['periode']} jours, {x['duree']:g} h"] for x in regles]
                               + [["Origine des fréquences et des durées", "fixées dans la demande ou posées en hypothèse — "
                                   "le tableau des clients ne les porte pas"]]})

    from bureautique.atelier import ouvrir, ajouter, terminer
    proprio = str(getattr(user, "id", "") or "")
    titre = str(data.get("titre") or f"Planning du {du.strftime('%d/%m/%Y')} au {au.strftime('%d/%m/%Y')}").strip()[:120]

    def _produire():
        jeton = ouvrir({"titre": titre, "format": "xlsx"}, proprio)
        ajouter(jeton, feuilles, proprio)
        return jeton, terminer(jeton, proprio)
    try:
        jeton, fiche = await asyncio.to_thread(_produire)
    except Exception as e:  # noqa: BLE001
        logger.warning("Classeur du planning impossible : %s", e)
        raise SkillError("Le classeur du planning n'a pas pu être produit. Réessayez.")

    blocs = [{"type": "table", "titre": "Charge de l'équipe, mois par mois",
              "columns": ["Mois", "Interventions", "Heures", "Jours de travail", "Jours ouvrés", "Taux d'occupation"],
              "rows": synthese},
             {"type": "fichier", "url": f"/api/documents/{jeton}", "nom": f"{titre}.xlsx", "titre": titre,
              "format": "xlsx", "octets": fiche.get("octets")}]
    return {
        "trouve": True, "interventions_placees": len(r["interventions"]), "a_decaler": len(r["a_decaler"]),
        "clients_sans_regle": r["clients_sans_regle"] or None,
        "jour_le_plus_charge_h": r["jour_le_plus_charge"], "capacite_h": capacite,
        "semaines_en_surcharge": [f"semaine {s} de {a} : {n} passage(s) sans place" for (a, s), n in r["semaines_en_surcharge"]][:30],
        "exemples_a_decaler": [f"{d['client']} ({d['ville']}) — {d['prestation']}" for d in r["a_decaler"][:15]],
        "feuilles": [f["nom"] for f in feuilles], "colonnes_lues": r["colonnes_lues"],
        "bloc_garanti": True, "bloc_ui": blocs, "document_id": jeton,
        "message_final": (f"Planning établi : {len(r['interventions'])} interventions placées, "
                          f"{len(r['a_decaler'])} à décaler faute de place."),
        "a_faire": ("Le tableau de charge et le classeur s'affichent AUTOMATIQUEMENT : n'écris aucun bloc pour eux et "
                    "ne produis PAS d'autre document. Le classeur porte EXACTEMENT les feuilles de `feuilles` : ne "
                    "décris que celles-là. Donne la charge mensuelle et le taux d'occupation tels quels, les semaines "
                    "en surcharge, et des exemples de clients à décaler. RAPPELLE que les fréquences et les durées "
                    "sont des HYPOTHÈSES (feuille « Hypothèses ») si le tableau ne les portait pas. Aucune journée ne "
                    f"dépasse {capacite:g} h et il n'y a qu'une équipe : c'est garanti par le calcul."),
    }


SKILLS = {
    "planifier_interventions": Declaration(
        fonction=planifier_interventions,
        description=(
            "LE PLANNING D'UNE EQUIPE, CALCULE PAR LE SERVEUR : chaque passage place sur un jour ouvre, villes "
            "regroupees, jamais plus de N heures par jour, UNE equipe ; classeur Excel (une feuille par mois, "
            "Synthese, A decaler, Hypotheses), charge mensuelle et taux d'occupation. A utiliser pour tout "
            "« planning d'intervention / d'entretien / de tournees » : NE L'ECRIS JAMAIS a la main avec "
            "`produire_document`. D'abord OUVRE le classeur des clients (`drive_ouvrir`), puis : "
            "`lignes: \"@tableau\"`, `du`, `au`, `heures_par_jour` (7), `regles`: [{\"si\": {\"colonne\": "
            "\"Piscine ou jardin\", \"contient\": \"piscine\"}, \"prestation\": \"Entretien piscine\", "
            "\"tous_les_jours\": 14, \"duree_h\": 1.5}]. Si frequences ou durees ne sont ecrites nulle part, "
            "pose une hypothese et DIS-LA"),
        requis=["lignes", "du", "au", "regles"], optionnels=["heures_par_jour", "titre"],
        effet="ecriture_interne",
        libelle="je calcule le planning de l'équipe"),
}
