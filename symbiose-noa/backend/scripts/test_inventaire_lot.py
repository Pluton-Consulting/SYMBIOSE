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
bloc = source[source.index('"drive_lister_lot": Declaration('):][:1200]
verifier("le catalogue annonce `detail` et `tri`", '"detail", "tri"' in bloc and "UNE LIGNE" in bloc)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
