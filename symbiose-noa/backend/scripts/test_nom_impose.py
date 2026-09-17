"""
Banc « le nom écrit par la personne fait foi » — 18/09, recette pilotée, prompt 11 avec une faute.

Demandé : « Devis symbiose paysage Parkin.pdf », « interdiction absolue d'ouvrir un document
approchant ». Le modèle a cherché, trouvé « …Parking.pdf » et l'a ouvert sous ce nom corrigé :
`exact: true` n'y voyait rien. `drive_ouvrir` reçoit la demande et impose le nom ÉCRIT.
"""
import ast
import asyncio
import pathlib
import sys
import types

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print("\n═══ LE NOM ÉCRIT FAIT FOI —", BACKEND.parent)
source = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
voulus = {"nom_impose_par_la_demande", "_meme_nom", "drive_ouvrir", "_STRICT"}
corps = [n for n in ast.parse(source).body
         if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in voulus)
         or (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id in voulus for c in n.targets))]
recu = {}


async def _drive(fonction, nom, **k):
    recu.update(nom=nom, **k)
    return {"ok": True}
faux = types.ModuleType("outils.drive"); faux.ouvrir = object()
sys.modules.setdefault("outils", types.ModuleType("outils")); sys.modules["outils.drive"] = faux
esp = {"_drive": _drive, "_perimetres": lambda u: [], "_identite": lambda u: None, "_proprietaire": lambda u: "u",
       "_echec": lambda m: (_ for _ in ()).throw(RuntimeError(m))}
exec(compile(ast.Module(body=corps, type_ignores=[]), "outils.py", "exec"), esp)
impose, ouvrir = esp["nom_impose_par_la_demande"], esp["drive_ouvrir"]

STRICTE = ("Document visé : « Devis symbiose paysage Parkin.pdf », sur le Drive.\nOuvre-le.\n"
           "Interdiction absolue d'ouvrir un document approchant.")
verifier("un nom entre guillemets + une interdiction d'approchant = un nom imposé",
         impose(STRICTE) == "Devis symbiose paysage Parkin.pdf")
verifier("sans interdiction, rien n'est imposé (« ouvre « Devis.pdf » » garde la tolérance d'avant)",
         impose("ouvre « Devis.pdf »") == "" and impose("ouvre exactement le devis du parking") == "")
verifier("deux noms cités : on n'en impose aucun plutôt que d'en choisir un",
         impose('Compare exactement « A.pdf » et « B.pdf »') == "")
asyncio.run(ouvrir({"nom": "Devis symbiose paysage Parking.pdf", "_demande_utilisateur": STRICTE}, None))
verifier("le modèle passe le nom VOISIN qu'il a trouvé : c'est le nom écrit qui part, en exact",
         recu["nom"] == "Devis symbiose paysage Parkin.pdf" and recu["exact"] is True, str(recu))
bonne = STRICTE.replace("Parkin.pdf", "Parking.pdf")
asyncio.run(ouvrir({"chemin": "1-ÉTUDES/FAROU/Devis/Devis symbiose paysage Parking.pdf", "_demande_utilisateur": bonne}, None))
verifier("le bon nom passé par son CHEMIN garde son chemin (le bon dossier), en exact",
         recu["nom"].startswith("1-ÉTUDES/FAROU") and recu["exact"] is True, str(recu))
asyncio.run(ouvrir({"nom": "Devis.pdf", "_demande_utilisateur": "ouvre un devis au hasard"}, None))
verifier("une demande ordinaire ne change rien", recu["nom"] == "Devis.pdf" and recu["exact"] is False)
a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("la boucle d'actions donne la demande à `drive_ouvrir`",
         'if action["skill"] == "drive_ouvrir":' in a1 and '"_demande_utilisateur": state.get("query")' in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
