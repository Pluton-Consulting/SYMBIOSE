"""
Banc « le planning d'une équipe se CALCULE » — 18/09, recette pilotée, prompt 20.

Écrit à la main par le modèle, le classeur n'avait pas de feuille « Mai », des onglets en double,
et la réponse décrivait un fichier qui n'existait pas. `skills/planning.planifier` (PUR) place
chaque passage sous contrainte ; ce banc l'EXÉCUTE.
"""
import pathlib
import sys
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print("\n═══ PLANNING D'UNE ÉQUIPE —", BACKEND.parent)
from skills import planning as P  # noqa: E402

VILLES = ["Arcachon", "La Teste", "Gujan-Mestras", "Pessac", "Lacanau"]
clients = [{"Piscine ou jardin": "PISCINE" if i % 3 == 0 else "JARDIN", "Nom": f"CLIENT{i:03d}", "Prénom": "A",
            "Ville": VILLES[i % 5], "Code postal": "33120"} for i in range(60)]
regles = P.lire_les_regles([
    {"si": {"colonne": "Piscine ou jardin", "contient": "piscine"}, "prestation": "Entretien piscine", "tous_les_jours": 14, "duree_h": 1.5},
    {"si": {"colonne": "Piscine ou jardin", "contient": "jardin"}, "prestation": "Entretien jardin", "tous_les_jours": 30, "duree_h": "3,5"}])
r = P.planifier(clients, regles, date(2027, 4, 1), date(2027, 6, 30), 7.0)
iv = r["interventions"]
par_jour = {}
for p in iv:
    par_jour[p["date"]] = par_jour.get(p["date"], 0) + p["duree"]
verifier("AUCUNE journée ne dépasse la capacité, et aucune intervention ne tombe un week-end",
         max(par_jour.values()) <= 7.0 + 1e-9 and all(p["date"].weekday() < 5 for p in iv), str(max(par_jour.values())))
verifier("toute la période est couverte : avril, mai ET juin ont leurs interventions",
         sorted(r["par_mois"]) == [(2027, 4), (2027, 5), (2027, 6)] and all(v["interventions"] > 0 for v in r["par_mois"].values()))
attendus = 20 * 7 + 40 * 4           # piscines : 91 jours / 14 → 7 fenêtres ; jardins : 91 / 30 → 4 fenêtres
verifier("chaque passage demandé est soit PLACÉ, soit DIT « à décaler » : rien ne disparaît",
         len(iv) + len(r["a_decaler"]) == attendus, f"{len(iv)} + {len(r['a_decaler'])} ≠ {attendus}")
verifier("un client de piscine passe bien tous les 14 jours (une fois par fenêtre, jamais deux)",
         sum(1 for p in iv if p["client"] == "CLIENT000 A") + sum(1 for d in r["a_decaler"] if d["client"] == "CLIENT000 A") == 7)
jours_d_une_ville = {}
for p in iv:
    jours_d_une_ville.setdefault(p["date"], set()).add(p["ville"])
verifier("les tournées se regroupent par secteur : la plupart des journées ne visitent qu'une ou deux villes",
         sum(1 for v in jours_d_une_ville.values() if len(v) <= 2) >= 0.7 * len(jours_d_une_ville))
verifier("la charge se chiffre : heures, jours de travail et taux d'occupation par mois",
         all(0 < v["taux_occupation"] <= 100 and v["jours_de_travail"] == round(v["heures"] / 7, 1) for v in r["par_mois"].values()))
serre = P.planifier(clients, regles, date(2027, 4, 1), date(2027, 4, 30), 2.0)
verifier("une capacité trop faible ne TASSE rien : le surplus part en « à décaler », semaines nommées",
         len(serre["a_decaler"]) > 0 and serre["semaines_en_surcharge"] and max(
             sum(p["duree"] for p in serre["interventions"] if p["date"] == j) for j in {p["date"] for p in serre["interventions"]}) <= 2.0)
verifier("une ligne qu'aucune règle ne vise est COMPTÉE, pas planifiée au hasard",
         P.planifier(clients + [{"Piscine ou jardin": "SPA", "Nom": "X"}], regles, date(2027, 4, 1), date(2027, 4, 30))["clients_sans_regle"] == 1)
for mauvaise in ([], [{"prestation": "x"}], [{"tous_les_jours": "souvent", "duree_h": 1}]):
    try:
        P.lire_les_regles(mauvaise)
        verifier(f"règle refusée : {mauvaise}", False)
    except Exception:
        verifier(f"une règle sans fréquence ni durée lisibles est REFUSÉE ({str(mauvaise)[:30]})", True)
verifier("« juin 2027 » en fin de période vaut le 30 juin", P._jour("juin 2027", fin=True) == date(2027, 6, 30)
         and P._jour("01/04/2027") == date(2027, 4, 1))
verifier("le geste est déclaré (écriture interne) et rangé dans une famille",
         P.SKILLS["planifier_interventions"].effet == "ecriture_interne"
         and '"planifier_interventions"' in (BACKEND / "skills" / "familles.py").read_text(encoding="utf-8"))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
