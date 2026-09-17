"""
Banc « LE CHIFFRE D'AFFAIRES ET LES CORRECTIFS DU 17/09 » — Symbiose.

Rapport d'anticipation du 17/09 (20 prompts, 113 demandes réelles) : quatre échecs certains, dont
« chiffre d'affaires sur une période » et « portefeuille client ». Aucun geste ne sommait les
factures ; le modèle ouvrait les PDF un à un. Ce banc exécute le code LIVRÉ, sans base ni réseau :

  1. `chiffres.calculer` : une facture par NUMÉRO (les copies ne comptent pas), un avoir en moins,
     un devis jamais, ce qui est illisible DÉCLARÉ, les écritures d'un même client regroupées,
     la somme des clients égale au total ;
  2. `chiffre_affaires` exécuté contre une base doublée ;
  3. le client lu sur la pièce (`prix.lignes.client_de_la_piece`) ;
  4. les petits correctifs : « A définir » attend, le listage dit la date et les doublons, la
     période des prix se règle, déposer dix brouillons n'est pas de l'acharnement.
"""
import asyncio
import pathlib
import sys
import types
from datetime import date

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


def doublure(nom, **attributs):
    m = types.ModuleType(nom)
    m.__dict__.update(attributs)
    sys.modules[nom] = m
    return m


class SkillError(Exception):
    pass


print("\n═══ LE CHIFFRE D'AFFAIRES —", BACKEND.parent)
PIECES = [
    dict(fichier_id="a", fichier_nom="FA0001.pdf", nature="facture", numero="FA0001", date_piece=date(2025, 9, 12), total_ht=1000.0, controle="juste", client="M. DUPONT Jean", code_client="90DUPON", lu_le="1"),
    dict(fichier_id="a2", fichier_nom="FA0001 (1).pdf", nature="facture", numero="FA0001", date_piece=date(2025, 9, 12), total_ht=1000.0, controle="ecart", client="M. DUPONT Jean", code_client="90DUPON", lu_le="2"),
    dict(fichier_id="b", fichier_nom="FA0002.pdf", nature="facture", numero="FA0002", date_piece=date(2025, 10, 3), total_ht=2500.5, controle="juste", client="DUPONT JEAN", code_client="90DUPON", lu_le="1"),
    dict(fichier_id="c", fichier_nom="FA0003.pdf", nature="facture", numero="FA0003", date_piece=date(2026, 1, 20), total_ht=400.0, controle="juste", client="Sté LE BOIS", code_client="", lu_le="1"),
    dict(fichier_id="d", fichier_nom="AV0001.pdf", nature="avoir", numero="AV0001", date_piece=date(2026, 1, 25), total_ht=100.0, controle="juste", client="Société Le Bois", code_client="", lu_le="1"),
    dict(fichier_id="e", fichier_nom="FA0004.pdf", nature="facture", numero="FA0004", date_piece=date(2026, 2, 2), total_ht=None, controle=None, client="Mme MARTIN", code_client="90MARTI", lu_le="1"),
    dict(fichier_id="f", fichier_nom="FA0005.pdf", nature="facture", numero="FA0005", date_piece=None, total_ht=900.0, controle="juste", client="Mme MARTIN", code_client="90MARTI", lu_le="1"),
    dict(fichier_id="g", fichier_nom="FA0006.pdf", nature="facture", numero="FA0006", date_piece=date(2024, 5, 1), total_ht=7777.0, controle="juste", client="M. VIEUX", code_client="", lu_le="1"),
]
doublure("skills.registre", Declaration=type("Declaration", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)}))
doublure("skills.erreurs", SkillError=SkillError)
from skills import chiffres  # noqa: E402

r = chiffres.calculer([dict(p) for p in PIECES], date(2025, 9, 1), date(2026, 8, 31))
verifier("une facture par NUMÉRO : la copie du même PDF ne compte pas deux fois", r["doublons"] == 1 and len(r["retenues"]) == 4)
verifier("l'exemplaire gardé est celui dont la somme des lignes retrouve le total",
         next(p for p in r["retenues"] if p["numero"] == "FA0001")["fichier_id"] == "a")
verifier("le total : 1 000 + 2 500,50 + 400 − 100 (l'avoir vient EN MOINS)", r["total"] == 3800.5 and r["avoirs"] == 1, str(r["total"]))
verifier("hors période, la facture de 2024 n'entre pas", not any(p["numero"] == "FA0006" for p in r["retenues"]))
verifier("une facture sans total lisible est DÉCLARÉE, pas comptée pour zéro",
         [p["numero"] for p in r["illisibles"]] == ["FA0004"])
verifier("une facture sans date lisible est déclarée à part", [p["numero"] for p in r["sans_date"]] == ["FA0005"])
verifier("le détail mensuel", [(k, n, round(t, 2)) for k, (n, t) in r["mensuel"]]
         == [((2025, 9), 1, 1000.0), ((2025, 10), 1, 2500.5), ((2026, 1), 2, 300.0)], str(r["mensuel"]))
dupont = r["clients"][0]
verifier("le CA d'un client est la somme de TOUTES ses factures ; ses écritures se regroupent par code",
         dupont["factures"] == 2 and dupont["total"] == 3500.5 and dupont["variantes"] == ["DUPONT JEAN"] or dupont["variantes"] == ["M. DUPONT Jean"],
         str(dupont))
bois = next(c for c in r["clients"] if "BOIS" in c["client"].upper())
verifier("sans code, « Sté Le Bois » et « Société Le Bois » sont le même client", bois["factures"] == 2 and bois["total"] == 300.0, str(bois))
verifier("la somme des clients égale le total", r["somme_clients"] == r["total"])
verifier("panier moyen et part", dupont["panier_moyen"] == 1750.25 and dupont["part"] == 92.1, str(dupont))


class Conn:
    async def fetch(self, sql, *a):
        assert "nature IN ('facture', 'avoir')" in sql and "etat = 'lue'" in sql
        return [dict(p, methode="texte/4") for p in PIECES]

    async def fetchval(self, sql, *a):
        return 12


class Ctx:
    async def __aenter__(self): return Conn()
    async def __aexit__(self, *a): return False


doublure("database"); doublure("database.connection", get_db=lambda: Ctx())
doublure("security"); doublure("security.acces", niveaux_visibles=lambda role: {"all"})
u = types.SimpleNamespace(role="direction", id="u1")
res = asyncio.run(chiffres.chiffre_affaires({"du": "01/09/2025", "au": "31/08/2026", "classement": True}, u))
verifier("le geste rend le total, la méthode et le contrôle",
         res["chiffre_affaires_ht"] == "3 800,50 €" and "devis exclus" in res["methode"]
         and res["controle"] == "la somme des clients égale le total", str(res.get("controle")))
verifier("les tableaux (mois, clients) sont GARANTIS à l'écran",
         res["bloc_garanti"] and [b["columns"][0] for b in res["bloc_ui"][:2]] == ["Mois", "Client"])
verifier("ce qui n'a pas pu être compté est rendu nommément",
         res["factures_sans_total_lisible"][0]["numero"] == "FA0004" and res["factures_sans_date_lisible"] == 1
         and res["exemplaires_en_double_ecartes"] == 1)
verifier("une base encore en cours de lecture est DITE", "12 pièce(s)" in res.get("base_en_cours_de_lecture", ""))
verifier("la consigne interdit d'additionner soi-même et d'extrapoler un mois incomplet",
         "n'additionne rien toi-même" in res["a_faire"] and "n'extrapole aucun mois" in res["a_faire"])
an = asyncio.run(chiffres.chiffre_affaires({"annee": "2024"}, u))
verifier("`annee` borne l'année civile", an["chiffre_affaires_ht"] == "7 777,00 €")
for mauvais in ({"du": "bientôt"}, {"du": "01/09/2026", "au": "01/01/2026"}):
    try:
        asyncio.run(chiffres.chiffre_affaires(mauvais, u))
        verifier(f"période refusée : {mauvais}", False)
    except SkillError:
        verifier(f"une période illisible ou à l'envers est REFUSÉE, jamais élargie en silence ({list(mauvais.values())[0]})", True)
d = chiffres.SKILLS["chiffre_affaires"]
verifier("geste de LECTURE, sans paramètre obligatoire, rangé dans une famille",
         d.effet == "lecture" and d.requis == [] and '"chiffre_affaires"' in (BACKEND / "skills" / "familles.py").read_text(encoding="utf-8"))

print("\n── les articles les plus facturés")
LA = [{"designation": "Tonte du gazon et ramassage", "unite": "Forfait", "quantite": 1, "pu_ht": 80, "montant_ht": 80, "numero": "F1"},
      {"designation": "Tonte du gazon et ramassage des déchets", "unite": "Forfait", "quantite": 1, "pu_ht": 90, "montant_ht": 90, "numero": "F2"},
      {"designation": "Tonte du gazon et ramassage", "unite": "Forfait", "quantite": 1, "pu_ht": 80, "montant_ht": 80, "numero": "F1"},
      {"designation": "Abri de piscine mi-haut", "unite": "Forfait", "quantite": 1, "pu_ht": 27000, "montant_ht": 27000, "numero": "F3"}]
cl = chiffres.classer_articles(LA)
verifier("deux écritures du même ouvrage se regroupent, la copie du PDF ne compte pas",
         cl[0]["article"].startswith("Tonte du gazon") and cl[0]["pieces"] == 2 and cl[0]["montant_ht"] == 170.0, str(cl[:1]))
verifier("`par: montant` classe par montant", chiffres.classer_articles(LA, par="montant")[0]["article"].startswith("Abri"))
verifier("geste de lecture, qui dit que ce sont des VENTES et pas des achats",
         chiffres.SKILLS["articles_frequents"].effet == "lecture" and "pas des achats" in chiffres.SKILLS["articles_frequents"].description)

print("\n── le client lu sur la pièce")
from prix import lignes as L  # noqa: E402
verifier("« Code client » et « Adresse Chantier : » donnent le client et son code",
         L.client_de_la_piece(["Code client : 90DUPON Adresse Chantier : M. et Mme DUPONT Jean"]) == ("M. et Mme DUPONT Jean", "90DUPON"))
verifier("« Adresse de livraison » aussi ; à l'OCR l'étiquette voisine est coupée",
         L.client_de_la_piece(["Email : a@b.fr Adresse de livraison : Sté LE BOIS"]) == ("Sté LE BOIS", "")
         and L.client_de_la_piece(["Code client :90PRO Adresse Chantier : PROMO URBA Email"]) == ("PROMO URBA", "90PRO"))
verifier("rien d'écrit : rien de deviné", L.client_de_la_piece(["Devis N° DV1", "Total"]) == ("", ""))
collecte = (BACKEND / "prix" / "collecte.py").read_text(encoding="utf-8")
verifier("la collecte range client, code et dossier, et la migration les ajoute sans rien casser",
         "client=$15, code_client=$16, dossier_id=$17" in collecte
         and "ADD COLUMN IF NOT EXISTS code_client" in (BACKEND / "database" / "migrations" / "056_client_des_pieces.sql").read_text(encoding="utf-8"))

print("\n── les petits correctifs")
doublure("bureautique"); doublure("bureautique.atelier")
from skills import routines  # noqa: E402
verifier("« A définir » est un devis qui ATTEND (691 devis étaient invisibles)",
         routines._statut_attend("A définir") and routines._statut_attend("En cours") and routines._statut_attend(""))
verifier("« Transformé », « Devis Archivé », « Perdu » n'attendent plus",
         not routines._statut_attend("Transformé") and not routines._statut_attend("Devis Archivé")
         and not routines._statut_attend("Perdu") and not routines._statut_attend("Partiellement transformé"))
src_r = (BACKEND / "skills" / "routines.py").read_text(encoding="utf-8")
verifier("les devis en attente ont un PLAFOND d'ancienneté et leur montant total, calculé par le serveur",
         '"age_max_jours"' in src_r and "montant_total_en_attente" in src_r and "trop_anciens += 1" in src_r)
from skills import affichage  # noqa: E402
res_l = affichage.garantir_listage({"chemin": "1-ÉTUDES", "entrees": [
    {"nom": "Devis.pdf", "dossier": False, "octets": 2048, "modifie_le": "2026-09-16T08:12:03.000Z"},
    {"nom": "devis.pdf", "dossier": False, "octets": 1024, "modifie_le": "2026-08-01T08:00:00.000Z"},
    {"nom": "Photos", "dossier": True, "modifie_le": "2026-07-01T08:00:00.000Z"}]}, "1-ÉTUDES", ouvreur="drive_ouvrir")
verifier("le listage dit la DATE de modification quand le stockage la donne",
         res_l["bloc_ui"]["columns"] == ["Nom", "Type", "Taille", "Modifié le"] and res_l["bloc_ui"]["rows"][0][3] == "16/09/2026")
verifier("les doublons de nom sont comptés par le serveur", res_l.get("doublons_de_nom") == ["Devis.pdf", "devis.pdf"])
sans_date = affichage.garantir_listage({"chemin": "X", "entrees": [{"nom": "a.pdf", "dossier": False, "octets": 1}]}, "X")
verifier("sans date (le NAS du jumeau), le tableau garde ses trois colonnes d'avant",
         sans_date["bloc_ui"]["columns"] == ["Nom", "Type", "Taille"] and "doublons_de_nom" not in sans_date)
from prix import releve as R  # noqa: E402
obs = [{"designation": f"Terrasse {k}", "unite": "m2", "quantite": 1, "pu_ht": pu, "numero": f"D{k}", "date": d}
       for k, (pu, d) in enumerate(((100.0, date(2026, 6, 1)), (120.0, date(2026, 3, 1)), (300.0, date(2025, 2, 1)), (90.0, date(2025, 1, 5))))]
douze = R.relever(obs, date(2026, 9, 17), mois=12)[0]
verifier("`mois: 12` est STRICT : ce qui a plus d'un an ne compte pas",
         douze["observations"] == 2 and douze["plus_haut"] == 120.0 and douze["periode_retenue"] == "les 12 derniers mois")
verifier("sans `mois`, le défaut d'avant est inchangé (24 mois si c'est assez fourni)",
         R.relever(obs, date(2026, 9, 17))[0]["observations"] == 4)
a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("déposer dix brouillons d'affilée n'est pas un geste qui s'acharne",
         'SKILLS_SANS_PLAFOND = frozenset({"ajouter_document", "deposer_brouillon", "enregistrer_relance"})' in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
