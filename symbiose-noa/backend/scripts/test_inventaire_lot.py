"""
Banc « l'inventaire d'un lot de dossiers, une ligne par élément » — 18/09, recette pilotée, prompt 10.

« Liste tout le contenu de 1-ÉTUDES, sous-dossiers inclus : nom exact, type, date, taille,
sous-dossier d'appartenance, trié par date décroissante. » `drive_lister_lot` ne rendait qu'une
ligne PAR DOSSIER (ses trente premiers noms à la suite) : 317 éléments comptés, aucun détaillé.
`detail: true` ajoute le tableau ligne à ligne, assemblé par le serveur.
"""
import ast
import asyncio
import pathlib
import sys
import types

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print("\n═══ INVENTAIRE D'UN LOT —", BACKEND.parent)
source = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
arbre = ast.parse(source)
voulus = {"drive_lister_lot", "MAX_LIGNES_INVENTAIRE_LOT"}
corps = [n for n in arbre.body
         if (isinstance(n, ast.AsyncFunctionDef) and n.name in voulus)
         or (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id in voulus for c in n.targets))]


def lots():
    return {"dossiers_demandes": 2, "dossiers_inspectes": 2, "lots": [
        {"dossier": "1-ÉTUDES/A", "ok": True, "sous_dossiers": 1, "fichiers": 2, "entrees": [
            {"nom": "Plan.pdf", "dossier": False, "octets": 2048, "modifie_le": "2024-03-01T10:00:00Z"},
            {"nom": "Photos", "dossier": True, "modifie_le": "2026-01-05T10:00:00Z"},
            {"nom": "Devis.pdf", "dossier": False, "octets": 1024, "modifie_le": "2025-06-01T10:00:00Z"}]},
        {"dossier": "1-ÉTUDES/B", "ok": True, "sous_dossiers": 0, "fichiers": 15, "entrees": [
            {"nom": "devis.pdf" if i == 0 else f"f{i}.jpg", "dossier": False, "octets": 10, "modifie_le": f"2023-01-{i + 1:02d}T00:00:00Z"}
            for i in range(15)]},
        {"dossier": "1-ÉTUDES/C", "ok": False, "erreur": "accès refusé", "entrees": []}]}


faux = types.ModuleType("outils.drive"); faux.lister_lot = object()
sys.modules.setdefault("outils", types.ModuleType("outils")); sys.modules["outils.drive"] = faux


async def _drive(fonction, *a, **k):
    return lots()
esp = {"_drive": _drive, "_perimetres": lambda u: [], "_identite": lambda u: None,
       "_echec": lambda m: (_ for _ in ()).throw(RuntimeError(m))}
exec(compile(ast.Module(body=corps, type_ignores=[]), "outils.py", "exec"), esp)
geste = esp["drive_lister_lot"]

r0 = asyncio.run(geste({"dossiers": ["A", "B", "C"]}, None))
verifier("sans `detail`, rien ne change : UN tableau, une ligne par dossier",
         isinstance(r0["bloc_ui"], dict) and len(r0["bloc_ui"]["rows"]) == 3 and "detail: true" in r0["a_faire"])
r = asyncio.run(geste({"dossiers": ["A", "B", "C"], "detail": True, "tri": "date"}, None))
blocs = r["bloc_ui"]
verifier("avec `detail`, deux tableaux : la synthèse par dossier ET une ligne par élément",
         isinstance(blocs, list) and len(blocs) == 2 and len(blocs[1]["rows"]) == 18 and r["elements_total"] == 18, str(r.get("elements_total")))
verifier("chaque ligne porte le sous-dossier, le nom exact, le type, la taille et la date",
         blocs[1]["columns"] == ["Sous-dossier", "Nom", "Type", "Taille", "Modifié le"]
         and blocs[1]["rows"][0][:3] == ["1-ÉTUDES/A", "Photos", "Dossier"] and blocs[1]["rows"][0][4] == "05/01/2026", str(blocs[1]["rows"][0]))
dates = [l[4][6:] + l[4][3:5] + l[4][:2] for l in blocs[1]["rows"]]
verifier("`tri: date` range du plus récent au plus ancien, tous dossiers confondus", dates == sorted(dates, reverse=True))
verifier("les doublons de nom se lisent à la casse près, entre dossiers", r["doublons_de_nom"] == ["Devis.pdf", "devis.pdf"], str(r["doublons_de_nom"]))
verifier("le modèle ne relit pas mille lignes : les entrées lui sont abrégées, et c'est dit",
         len(r["lots"][1]["entrees"]) == 12 and r["lots"][1]["entrees_coupees_pour_le_modele"] is True)
verifier("un dossier en erreur garde sa ligne de synthèse et n'entre pas dans l'inventaire",
         blocs[0]["rows"][2][1] == "Erreur" and not any(l[0].endswith("/C") for l in blocs[1]["rows"]))
# 18/09 (D1, « lequel a été modifié le plus récemment ? ») : 178 entrées datées dépassaient le
# plafond, la coupe emportait la fin, le modèle répondait « classement partiel ».
verifier("chaque lot porte son compte exact et son entrée la plus récente, calculés par le serveur",
         r0["lots"][0]["entrees_total"] == 3 and r0["lots"][0]["le_plus_recent"] == {"nom": "Photos", "modifie_le": "05/01/2026", "type": "dossier"}
         and r0["lots"][1]["entrees_total"] == 15, str(r0["lots"][0].get("le_plus_recent")))
verifier("le plus récent de TOUS les lots est nommé avec son dossier",
         r0["le_plus_recent_de_tous"] == {"dossier": "1-ÉTUDES/A", "nom": "Photos", "modifie_le": "05/01/2026", "type": "dossier"}, str(r0.get("le_plus_recent_de_tous")))
rd = asyncio.run(geste({"dossiers": ["A", "B"], "tri": "date"}, None))
verifier("`tri: date` sans `detail` range les entrées de chaque lot, le premier EST le plus récent",
         [e["nom"] for e in rd["lots"][0]["entrees"]] == ["Photos", "Devis.pdf", "Plan.pdf"] and rd["lots"][1]["entrees"][0]["nom"] == "f14.jpg")
gros = lots(); gros["lots"][1]["entrees"] = [{"nom": f"g{i}", "dossier": True, "modifie_le": f"2026-02-{(i % 28) + 1:02d}T00:00:00Z"} for i in range(60)]
async def _gros(fonction, *a, **k):
    return gros
esp["_drive"] = _gros
rg = asyncio.run(geste({"dossiers": ["A", "B"]}, None))
verifier("sans inventaire, un lot de 60 entrées est abrégé à 40 pour le modèle, compte et plus récent intacts",
         len(rg["lots"][1]["entrees"]) == 40 and rg["lots"][1]["entrees_coupees_pour_le_modele"] is True
         and rg["lots"][1]["entrees_total"] == 60 and rg["lots"][1]["le_plus_recent"]["modifie_le"] == "28/02/2026"
         and "le_plus_recent" in rg["a_faire"])
esp["_drive"] = _drive
# 18/09 (D1) : le chemin que la carte du classement affiche (« Drive partagé « Symbiose Paysage »/…»)
# doit se résoudre — le modèle l'a recopié, trois listages perdus avant de deviner la forme attendue.
drive_src = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
arbre_d = ast.parse(drive_src)
voulus_d = {"_resoudre", "_nu", "_ACCENTS", "_est_identifiant"}
corps_d = [n for n in arbre_d.body
           if (isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name in voulus_d)
           or (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id in voulus_d for c in n.targets))]
class _Refus(Exception): ...
async def _drives(service):
    return [{"id": "dr1", "name": "Symbiose Paysage"}, {"id": "dr2", "name": "Holding Symbiose Paysage"}]
esp_d = {"DriveRefuse": _Refus, "_drives_nommes": _drives, "re": __import__("re"), "unicodedata": __import__("unicodedata"),
         "Optional": __import__("typing").Optional, "logger": __import__("logging").getLogger("banc")}
exec(compile(ast.Module(body=corps_d, type_ignores=[]), "drive.py", "exec"), esp_d)
verifier("« Drive partagé « Symbiose Paysage » » se résout comme le Drive lui-même (exact, pas la Holding)",
         asyncio.run(esp_d["_resoudre"](None, "Drive partagé « Symbiose Paysage »", ["dr1", "dr2"])) == "dr1")
verifier("le nom nu marche toujours", asyncio.run(esp_d["_resoudre"](None, "Symbiose Paysage", ["dr1", "dr2"])) == "dr1")
bloc = source[source.index('"drive_lister_lot": Declaration('):][:1200]
verifier("le catalogue annonce `detail` et `tri`", '"detail", "tri"' in bloc and "UNE LIGNE" in bloc)

# 18/09 : le tableau d'une RECHERCHE porte la date des fichiers, et le plus récent est nommé.
from skills.affichage import garantir_recherche  # noqa: E402
rr = garantir_recherche({"motif": "parking", "nombre": 2, "resultats": [
    {"nom": "Devis Transformation parking.pdf", "chemin": "A", "modifie_le": "2024-10-07T10:00:00Z"},
    {"nom": "Devis symbiose paysage Parking.pdf", "chemin": "B", "modifie_le": "2026-09-15T10:00:00Z"},
    {"nom": "Parkings", "chemin": "C", "dossier": True, "modifie_le": "2026-09-17T10:00:00Z"}]}, "parking")
verifier("une recherche du Drive montre « Modifié le » et nomme le FICHIER le plus récent (pas un dossier)",
         rr["bloc_ui"]["columns"][-1] == "Modifié le" and rr["bloc_ui"]["rows"][1][3] == "15/09/2026"
         and rr["fichier_le_plus_recent"]["nom"] == "Devis symbiose paysage Parking.pdf", str(rr.get("fichier_le_plus_recent")))
sans = garantir_recherche({"motif": "x", "nombre": 1, "resultats": [{"nom": "a.pdf", "chemin": "A"}]}, "x")
verifier("sans date rendue (NAS), le tableau garde ses trois colonnes", sans["bloc_ui"]["columns"] == ["Nom", "Type", "Emplacement"])

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
