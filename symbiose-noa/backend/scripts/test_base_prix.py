"""
Banc « LA BASE DE PRIX » — 17/09, Symbiose.

Relevé de Noa après un pré-devis d'abattage resté sans un chiffre : « j'aimerais qu'il
analyse le contenu des factures, les articles, les prix, pour avoir des estimations ».
Constaté en base : les jeux importés ne portent que des TOTAUX par affaire ; le détail vit
dans ~2 000 PDF du classement, dont quatre devis sur cinq sont des images (OCR).

CE QUE CE BANC ENFERME :
  1. LE LECTEUR DE LIGNES (`prix.lignes`) — des mots positionnés, et une ligne n'entre que
     si quantité × PU = montant (et montant × TVA = TTC). Le nom et l'adresse du client,
     posés au-dessus du tableau, n'entrent nulle part ; un acompte n'est pas un prix ; une
     pièce qui n'est pas de la maison (facture de fournisseur) ne rend rien ; un chiffre
     mal reconnu par l'OCR écarte la ligne au lieu d'entrer faux.
  2. LE RELEVÉ (`prix.releve`) — par unité, le récent d'abord, une pièce comptée une fois.
  3. `prix_observes` EXÉCUTÉ contre une base doublée : l'estimation est calculée par le
     serveur, un poste sans observation reste « à chiffrer », et l'intitulé « Titre » des
     devis importés est enfin lu (11 devis « abattage » étaient invisibles).

Sans base, sans réseau, sans modèle, sans PyMuPDF ni tesseract.
"""
import asyncio
import json
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


from prix import lignes as L      # noqa: E402
from prix import releve as R      # noqa: E402

print("\n═══ LA BASE DE PRIX —", BACKEND.parent)


def M(x0, y, texte, largeur=None, gras=False):
    return L.Mot(x0, x0 + (largeur or 5 * len(texte)), y, 9, texte, gras)


def rangee(y, *morceaux):
    return [M(x, y, t) for x, t in morceaux]


# ── 1. LE LECTEUR DE LIGNES ─────────────────────────────────────────────────
print("\n── le lecteur de lignes")
PAGE = (
    rangee(120, (330, "M."), (350, "DURAND"), (390, "Paul")) +                 # le client, AU-DESSUS du tableau
    rangee(134, (330, "12"), (345, "allée"), (375, "des"), (395, "Pins")) +
    rangee(200, (400, "Date"), (425, ":"), (432, "16/09/2026")) +
    rangee(257, (236, "Devis"), (262, "N°"), (275, "DV0001458")) +
    rangee(274, (236, "Abattage"), (280, "et"), (292, "évacuation")) +
    rangee(320, (39, "N°"), (149, "Description"), (296, "Unité"), (336, "Qté"), (377, "PU"),
           (390, "HT"), (421, "Montant"), (455, "HT"), (479, "TVA")) +
    [M(62, 334, "ABATTAGE", gras=True)] +
    rangee(348, (52, "1"), (62, "Abattage"), (105, "d'un"), (128, "pin"), (146, "de"), (160, "15"),
           (174, "m"), (291, "Unite"), (343, "3.00"), (391, "450.00"), (441, "1 350.00"),
           (479, "20.00"), (538, "1 620.00")) +
    rangee(361, (62, "y"), (70, "compris"), (108, "démontage"), (158, "par"), (176, "tronçons")) +
    rangee(388, (52, "2"), (62, "Evacuation"), (115, "des"), (133, "déchets"), (291, "m3"),
           (343, "12.00"), (391, "35.50"), (446, "426.00"), (479, "20.00"), (538, "511.20")) +
    # Une ligne dont le calcul NE TOMBE PAS juste (chiffre mal lu) : elle n'entre pas.
    rangee(420, (52, "3"), (62, "Dessouchage"), (291, "Unite"), (343, "3.00"), (391, "180.00"),
           (446, "640.00"), (479, "20.00"), (538, "768.00")) +
    rangee(450, (52, "4"), (62, "Acompte"), (100, "à"), (108, "la"), (120, "commande"), (291, "Unite"),
           (343, "1.00"), (391, "500.00"), (446, "500.00"), (479, "20.00"), (538, "600.00")) +
    rangee(636, (40, "Mode"), (65, "de"), (78, "règlement"), (125, ":"), (132, "Chèque"),
           (400, "Total"), (428, "HT"), (442, ":"), (450, "1 776.00 €"))
)
piece = L.lire_pages([PAGE])
lues = piece["lignes"]
verifier("la pièce est reconnue : devis, son numéro, sa date, son intitulé",
         piece["nature"] == "devis" and piece["numero"] == "DV0001458"
         and piece["date"] == date(2026, 9, 16) and piece["titre"].startswith("Abattage"), str(piece)[:200])
verifier("deux lignes entrent — celles dont quantité × PU = montant ET montant × TVA = TTC",
         [l["pu_ht"] for l in lues] == [450.0, 35.5], str([l["designation"] for l in lues]))
verifier("la désignation reprend sa suite (la rangée serrée dessous), sans le numéro d'ordre",
         lues[0]["designation"] == "Abattage d'un pin de 15 m y compris démontage par tronçons", lues[0]["designation"])
verifier("unité, quantité et montant sont ceux de la ligne (« 1 350.00 » lu 1350)",
         lues[0]["unite"] == "Unite" and lues[0]["quantite"] == 3.0 and lues[0]["montant_ht"] == 1350.0)
verifier("la rubrique en gras titre les lignes qui suivent", lues[0]["rubrique"] == "ABATTAGE")
verifier("LE NOM ET L'ADRESSE DU CLIENT n'entrent dans aucune désignation ni rubrique",
         not any("DURAND" in (l["designation"] + l["rubrique"]) or "Pins" in (l["designation"] + l["rubrique"]) for l in lues))
verifier("une ligne dont le calcul ne tombe pas juste est ÉCARTÉE, pas corrigée",
         not any("Dessouchage" in l["designation"] for l in lues))
verifier("un acompte n'est pas un prix", not any("Acompte" in l["designation"] for l in lues))
verifier("le Total HT est lu au milieu de sa rangée, et sert de contrôle (1 350 + 426 = 1 776)",
         piece["total_ht"] == 1776.0 and abs(sum(l["montant_ht"] for l in lues) - piece["total_ht"]) < 0.01)

# À l'OCR : les milliers arrivent en deux mots, et il n'y a pas de gras.
OCR = (rangee(100, (200, "Devis"), (230, "N°"), (245, "DV0000912")) +
       rangee(140, (39, "N°"), (149, "Description"), (296, "Unité"), (336, "Qté"), (377, "PU"), (421, "Montant")) +
       [M(52, 170, "1"), M(62, 170, "Terrasse"), M(105, 170, "pin"), M(291, 170, "m2"), M(343, 170, "50.00"),
        M(391, 170, "182.30"), L.Mot(440, 445, 170, 9, "9"), L.Mot(448, 478, 170, 9, "115.00"),
        M(490, 170, "20.00"), L.Mot(530, 540, 170, 9, "10"), L.Mot(543, 573, 170, 9, "938.00")])
p2 = L.lire_pages([OCR])
verifier("à l'OCR, « 9 » « 115.00 » se recollent en 9 115,00 et la ligne tombe juste",
         p2 and len(p2["lignes"]) == 1 and p2["lignes"][0]["montant_ht"] == 9115.0, str(p2)[:160])
verifier("une quantité et un prix voisins ne se recollent PAS (l'écart est celui d'une colonne)",
         p2["lignes"][0]["quantite"] == 50.0 and p2["lignes"][0]["pu_ht"] == 182.3)

# Les autres gabarits de la maison, relevés sur les vraies factures le 17/09 (une sur deux ne
# rendait AUCUNE ligne) : l'unité entre la quantité et le prix, la remise, la TVA au milieu.
def une(*morceaux):
    x = L._ligne_chiffree(rangee(100, *morceaux))
    return x and (x["quantite"], x["pu_ht"], x["montant_ht"], x.get("unite"), [m.texte for m in x["avant"]])
verifier("facture : « Qté · Unités · PU HT · Montant » — l'unité sépare la quantité du prix",
         une((60, "Bouteille"), (110, "CO2"), (300, "2.00"), (330, "Unité"), (380, "49.17"), (430, "98.33"),
             (480, "20.00"), (530, "118.00")) == (2.0, 49.17, 98.33, "Unité", ["Bouteille", "CO2"]))
verifier("avec une remise, le prix retenu est le NET payé (montant ÷ quantité)",
         une((60, "Banc"), (291, "Unité"), (343, "1.00"), (380, "1 649.50"), (430, "5.00"), (460, "1 567.03"),
             (500, "20.00"), (540, "1 880.43"))[:3] == (1.0, 1567.03, 1567.03))
verifier("second gabarit : « QTE · UNITÉ · TVA · P.U. HT · TOTAL HT », la TVA au milieu",
         une((60, "Tonte"), (300, "12"), (320, "h"), (340, "20,00 %"), (400, "45,00 €"), (470, "540,00 €"))[:3]
         == (12.0, 45.0, 540.0))
verifier("une rangée de numéros (téléphone, IBAN, code postal) ne fait jamais une ligne",
         une((60, "Tél"), (90, ":"), (100, "05"), (115, "40"), (130, "80"), (145, "95"), (160, "19")) is None
         and une((60, "IBAN"), (100, "3000"), (130, "4007"), (160, "5700"), (190, "0100")) is None)
collecte_src = (BACKEND / "prix" / "collecte.py").read_text(encoding="utf-8")
verifier("quand le lecteur apprend un gabarit, les pièces lues par une version plus ancienne sont rouvertes",
         isinstance(L.VERSION, int) and 'WHERE methode LIKE $1' in collecte_src and 'f"%/{VERSION}"' in collecte_src)

FOURNISSEUR = (rangee(60, (40, "FACTURE"), (90, "ND1406018")) +
               rangee(200, (62, "Gravier"), (110, "6/10"), (291, "T"), (343, "10.00"), (391, "42.00"),
                      (446, "420.00"), (479, "20.00"), (538, "504.00")))
verifier("une facture de FOURNISSEUR (pas de « Facture N° » de la maison) ne rend rien — un prix "
         "d'achat ne doit pas entrer dans les prix de vente", L.lire_pages([FOURNISSEUR]) is None)
verifier("un nombre s'écrit de plusieurs façons, une mesure n'est pas un nombre",
         L.nombre("27 788,00") == 27788.0 and L.nombre("2 910.00") == 2910.0
         and L.nombre("-126.60") == -126.6 and L.nombre("7.40 m") is None and L.nombre("16/18") is None)
source = (BACKEND / "prix" / "lignes.py").read_text(encoding="utf-8")
verifier("l'OCR passe par la porte commune du serveur (deux tesseract au plus)",
         "parsers._OCR_PORTE.acquire" in source and "_OCR_PORTE.release()" in source)

# ── 2. LE RELEVÉ ────────────────────────────────────────────────────────────
print("\n── le relevé par unité")
verifier("les racines d'un poste : le pluriel et les mots creux tombent",
         R.mots_cles("Fourniture et pose d'une terrasse bois") == ["terra", "boi"]
         and R.mots_cles("abattage d'arbres") == ["abatt", "arbre"])
verifier("une racine se compare en DÉBUT de mot : « terra » ne trouve pas « parterre »",
         R.correspond(R.plat("Abattage et dessouchage de 3 arbres"), ["abatt", "arbre"])
         and not R.correspond(R.plat("parterre fleuri"), ["terra"]))
AUJ = date(2026, 9, 17)
OBS = [
    {"designation": "Terrasse pin", "unite": "m2", "quantite": 50, "pu_ht": 182.30, "numero": "DV1", "nature": "devis", "date": date(2026, 3, 1)},
    {"designation": "Terrasse pin", "unite": "m2", "quantite": 50, "pu_ht": 182.30, "numero": "DV1", "nature": "devis", "date": date(2026, 3, 1)},  # la copie signée
    {"designation": "Terrasse ipé", "unite": "m²", "quantite": 30, "pu_ht": 240.0, "numero": "FA7", "nature": "facture", "date": date(2025, 11, 2)},
    {"designation": "Terrasse composite", "unite": "M2", "quantite": 20, "pu_ht": 150.0, "numero": "DV9", "nature": "devis", "date": date(2025, 6, 9)},
    {"designation": "Terrasse pin 2021", "unite": "m2", "quantite": 20, "pu_ht": 95.0, "numero": "DV0", "nature": "devis", "date": date(2021, 5, 1)},
    {"designation": "Terrasse sur mesure", "unite": "Forfait", "quantite": 1, "pu_ht": 9000.0, "numero": "DV4", "nature": "devis", "date": date(2026, 1, 5)},
]
rel = R.relever(OBS, AUJ)
m2 = next(r for r in rel if r["unite"] == "m²")
verifier("les unités ne se mélangent pas : m² d'un côté, forfait de l'autre",
         {r["unite"] for r in rel} == {"m²", "forfait"})
verifier("« m2 », « m² » et « M2 » sont la même unité", m2["observations_tout_historique"] == 4)
verifier("la copie d'un même devis ne compte qu'une fois", m2["observations_tout_historique"] == 4)
verifier("le récent prime : avec trois observations sur 24 mois, le prix de 2021 sort du relevé",
         m2["observations"] == 3 and m2["plus_bas"] == 150.0 and m2["periode_retenue"].startswith("les 24"))
verifier("médiane, et part des factures", m2["median"] == 182.3 and m2["factures"] == 1 and m2["devis"] == 2)
verifier("une seule observation ne fait pas un ordre de prix",
         next(r for r in rel if r["unite"] == "forfait")["suffisant"] is False)
e = R.estimer(m2, 40)
verifier("l'estimation : quantité × (plus bas, médian, plus haut)",
         e == {"quantite": 40, "unite": "m²", "bas": 6000.0, "median": 7292.0, "haut": 9600.0}, str(e))
verifier("pas d'estimation sur un relevé trop maigre", R.estimer({"suffisant": False}, 3) is None)
longue = ("Fourniture et installation complète d'un système d'arrosage automatique avec programmateur, "
          "électrovannes et tuyères, à réaliser avant engazonnement de la parcelle")
verifier("L'OUVRAGE SE NOMME EN TÊTE : un arrosage qui cite « engazonnement » en fin de phrase n'est pas un engazonnement",
         not R.correspond(R.tete(longue), R.mots_cles("engazonnement"))
         and R.correspond(R.tete(longue), R.mots_cles("arrosage automatique"))
         and R.correspond(R.tete("Semis", "ENGAZONNEMENT"), R.mots_cles("engazonnement")))
quatre = R.relever([{"designation": f"Terrasse {k}", "unite": "m2", "quantite": 10, "pu_ht": pu, "numero": f"D{k}",
                     "date": date(2026, 1, k + 1)} for k, pu in enumerate((10.31, 150.0, 160.0, 267.23))], AUJ)[0]
e4 = R.estimer(quatre, 40)
verifier("dès quatre observations, l'estimation prend la fourchette COURANTE : une réparation à 10 € le m² "
         "reste dans le relevé (plus bas) mais ne fait pas le bas de l'estimation",
         quatre["plus_bas"] == 10.31 and e4["bas"] > 40 * 100 and e4["haut"] < 40 * 267.23, str(e4))

# ── 3. prix_observes, EXÉCUTÉ ───────────────────────────────────────────────
print("\n── prix_observes contre une base doublée")
LIGNES_BASE = [
    ("Abattage d'un pin de 15 m y compris démontage", "ABATTAGE", "Unite", 3, 450.0, "devis", "DV0001458", date(2026, 9, 16), "f1"),
    ("Abattage d'un chêne", "", "Unite", 1, 620.0, "facture", "FA0000911", date(2026, 2, 3), "f2"),
    ("Abattage de 2 arbres morts", "", "Unite", 2, 380.0, "facture", "FA0000700", date(2025, 10, 12), "f3"),
    ("Abattage d'un pin de 15 m y compris démontage", "ABATTAGE", "Unite", 3, 450.0, "devis", "DV0001458", date(2026, 9, 16), "f1bis"),
    ("Evacuation des déchets verts", "", "m3", 12, 35.5, "devis", "DV0001458", date(2026, 9, 16), "f1"),
    ("Evacuation déchets", "", "m3", 8, 40.0, "facture", "FA0000911", date(2026, 2, 3), "f2"),
]
JEUX = {"devis": [{"Code": "DV0001200", "Titre": "Abattage d'arbres", "Total HT": "2 346,56", "Date": "02/05/2026"},
                  {"Code": "DV0001321", "Titre": "Abattage arbres et dessouchage", "Total HT": "4 100,00", "Date": "11/07/2026"},
                  {"Code": "DV0000999", "Titre": "Entretien annuel", "Total HT": "900,00", "Date": "01/01/2026",
                   "Commentaire interne": "voir abattage arbres du voisin"}],
        "fournisseur": [{"Libellé de l'article": "Terrasse composite", "Unité": "m2", "Prix de l'article HT": "85.0"},
                        {"Libellé de l'article": "Abattage d'arbres", "Unité": "Unite", "Prix de l'article HT": "0.0"}]}
REQUETES = []


class Conn:
    async def fetch(self, sql, *args):
        REQUETES.append(sql)
        if "DISTINCT source_type" in sql:
            return [{"source_type": t} for t in sorted(JEUX)]
        if "FROM lignes_chiffrees" in sql:
            motifs = [a.strip("%") for a in args[1]]
            return [{"designation": d, "rubrique": r, "unite": u, "quantite": q, "pu_ht": pu,
                     "texte_plat": R.plat(f"{r} {d}"), "nature": n, "numero": num, "date_piece": dt, "fichier_id": f}
                    for d, r, u, q, pu, n, num, dt, f in LIGNES_BASE
                    if all(m in R.plat(f"{r} {d}") for m in motifs)]
        if "data::text ILIKE" in sql:
            motif = args[1].strip("%").lower()
            return [{"source_type": t, "data": json.dumps(d, ensure_ascii=False), "champs": "{}"}
                    for t, ls in JEUX.items() for d in ls
                    if motif in R.plat(json.dumps(d, ensure_ascii=False))]
        return []

    async def fetchrow(self, sql, *args):
        return {"pieces": 3, "lignes": 6, "derniere_piece": date(2026, 9, 16), "derniere_lecture": None}

    async def fetchval(self, sql, *args):
        return 0


class Ctx:
    async def __aenter__(self): return Conn()
    async def __aexit__(self, *a): return False


def doublure(nom, **attributs):
    m = types.ModuleType(nom)
    m.__dict__.update(attributs)
    sys.modules[nom] = m
    return m


class SkillError(Exception):
    pass


doublure("database"); doublure("database.connection", get_db=lambda: Ctx())
doublure("security"); doublure("security.acces", niveaux_visibles=lambda role: {"all"})
doublure("skills.erreurs", SkillError=SkillError)
doublure("skills.registre", Declaration=type("Declaration", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)}))
doublure("bureautique"); doublure("bureautique.atelier")
from skills import routines  # noqa: E402

utilisateur = types.SimpleNamespace(role="direction", email="x@exemple-paysage.fr")
res = asyncio.run(routines.prix_observes({"postes": [
    {"poste": "abattage d'arbre", "quantite": 4, "unite": "u"},
    {"poste": "évacuation déchets", "quantite": 10, "unite": "m3"},
    {"poste": "pose de gazon synthétique", "quantite": 80, "unite": "m2"}]}, utilisateur))
fiches = {f["poste"]: f for f in res["postes"]}
abatt = fiches["abattage d'arbre"]
verifier("le relevé vient des LIGNES des devis et factures, par unité",
         abatt["prix_unitaires"][0]["unite"] == "unité" and abatt["prix_unitaires"][0]["observations"] == 3,
         str(abatt.get("prix_unitaires"))[:200])
verifier("la copie du devis (même numéro, autre fichier) ne double pas l'observation",
         abatt["prix_unitaires"][0]["dont_devis"] == 1 and abatt["prix_unitaires"][0]["dont_factures"] == 2)
verifier("L'ESTIMATION EST CALCULÉE PAR LE SERVEUR : 4 × (380 – 450 – 620)",
         abatt["estimation"] == {"quantite": 4.0, "unite": "unité", "bas": "1 520,00 €",
                                 "median": "1 800,00 €", "haut": "2 480,00 €"}, str(abatt.get("estimation")))
verifier("les TOTAUX d'affaires complètent : l'intitulé « Titre » des devis importés est enfin lu",
         abatt["affaires_entieres"]["observations"] == 2 and abatt["affaires_entieres"]["plus_bas"].startswith("2 346,56"),
         str(abatt.get("affaires_entieres"))[:160])
verifier("un commentaire qui cite le poste ne fait pas entrer le montant d'une autre affaire",
         not any("900" in str(x["montant"]) for x in abatt["affaires_entieres"]["exemples"]))
verifier("un article du catalogue à 0 € ne dit rien : il n'est pas cité", "catalogue_articles" not in abatt)
verifier("un poste SANS observation reste « à chiffrer » : aucun chiffre",
         fiches["pose de gazon synthétique"]["trouve"] is False
         and fiches["pose de gazon synthétique"].get("estimation") is None
         and res["sans_observation"] == ["pose de gazon synthétique"])
blocs = res["bloc_ui"]
estimation = next(b for b in blocs if b["titre"].startswith("Estimation"))
verifier("deux tableaux garantis : les prix pratiqués, et l'estimation avec son TOTAL",
         res["bloc_garanti"] is True and len(blocs) == 2 and estimation["rows"][-1][0].startswith("TOTAL")
         and estimation["rows"][-1][4] == "2 177,50 €", str(estimation["rows"][-1]))
verifier("le poste sans prix figure dans l'estimation, « à chiffrer »",
         any(r[0] == "pose de gazon synthétique" and r[3] == "à chiffrer" for r in estimation["rows"]))
verifier("la consigne : médian × quantité, fourchette, jamais un prix ferme, jamais le web",
         all(m in res["a_faire"] for m in ("MÉDIAN", "fourchette", "ESTIMATION", "à chiffrer")))

seul = asyncio.run(routines.prix_observes({"poste": "terrasse composite"}, utilisateur))
verifier("`poste` seul marche toujours ; le catalogue d'articles donne son tarif quand il en a un",
         seul["postes"][0].get("catalogue_articles") == [{"article": "Terrasse composite", "unite": "m2", "prix_ht": "85,00 €"}],
         str(seul["postes"][0])[:200])
rien = asyncio.run(routines.prix_observes({"poste": "piscine miroir"}, utilisateur))
verifier("rien nulle part : pas de tableau, et la consigne interdit tout chiffre",
         rien["trouve"] is False and "bloc_ui" not in rien and "AUCUN chiffre" in rien["a_faire"])
try:
    asyncio.run(routines.prix_observes({}, utilisateur))
    verifier("sans poste : une erreur qui dit quoi donner", False)
except SkillError as exc:
    verifier("sans poste : une erreur qui dit quoi donner", "postes" in str(exc))
decl = routines.SKILLS["prix_observes"]
verifier("le catalogue n'EXIGE plus `poste` (une liste `postes` était refusée avant d'atteindre le geste)",
         decl.requis == [] and {"poste", "postes"} <= set(decl.optionnels) and decl.effet == "lecture")

# ── 4. LA COLLECTE ──────────────────────────────────────────────────────────
print("\n── la collecte")
collecte = (BACKEND / "prix" / "collecte.py").read_text(encoding="utf-8")
verifier("lecture seule sur le classement : ni création, ni mise à jour, ni suppression",
         "files().get_media" in collecte and "files().list" in collecte
         and not any(f"files().{m}(" in collecte for m in ("create", "update", "delete", "copy", "emptyTrash")))
verifier("la collecte a SON client Drive (ni le client gardé du chat, ni le vivier)",
         "_un_fil_a_la_fois(await drive._build_service_pour(None))" in collecte)
verifier("une pièce déjà lue et inchangée n'est pas rouverte — écartée ou non",
         "f[\"id\"] not in deja" in collecte and "pas_de_la_maison" in collecte)
verifier("les lignes héritent du niveau d'accès du jeu « devis »", "_niveau_des_prix" in collecte)
principal = (BACKEND / "main.py").read_text(encoding="utf-8")
verifier("la collecte part en tâche de fond, seulement là où le classement est un Drive",
         "from prix.collecte import demarrer_collecte" in principal
         and principal.index("from outils import drive as _drive_present") < principal.index("demarrer_collecte())"))
migration = (BACKEND / "database" / "migrations" / "055_lignes_chiffrees.sql").read_text(encoding="utf-8")
verifier("la migration est additive et idempotente",
         migration.count("IF NOT EXISTS") >= 5 and "DROP" not in migration.upper().replace("ON DELETE", ""))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
