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
# 18/09 après-midi : c'est le ROUTEUR qui juge (« flexible pour toutes les demandes ») ; le motif ne sert que s'il s'est tu.
asyncio.run(ouvrir({"nom": "Devis symbiose paysage Parking.pdf", "_demande_utilisateur": STRICTE,
                    "_fichier_exact": "Devis symbiose paysage Parkin.pdf", "_routeur_a_repondu": True}, None))
verifier("le routeur a jugé : son nom exact part, en exact", recu["nom"] == "Devis symbiose paysage Parkin.pdf" and recu["exact"] is True)
asyncio.run(ouvrir({"nom": "Devis symbiose paysage Parking.pdf", "_demande_utilisateur": STRICTE,
                    "_fichier_exact": "", "_routeur_a_repondu": True}, None))
verifier("le routeur a jugé qu'aucun fichier n'est imposé : le motif ne s'en mêle PAS, même sur la demande stricte",
         recu["nom"] == "Devis symbiose paysage Parking.pdf" and recu["exact"] is False)
asyncio.run(ouvrir({"nom": "Devis symbiose paysage Parking.pdf", "_demande_utilisateur": STRICTE, "_routeur_a_repondu": False}, None))
verifier("routeur muet (voie rapide, panne) : le motif reprend la main", recu["nom"] == "Devis symbiose paysage Parkin.pdf")
a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
src_o = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
bloc_o = src_o[src_o.index('"drive_ouvrir": Declaration('):][:1600]
verifier("`drive_ouvrir` s'ouvre par `nom` OU par `chemin` : aucun des deux n'est refusé avant le skill (18/09)",
         'requis=[], optionnels=["nom", "chemin", "exact"]' in bloc_o)
try:
    asyncio.run(ouvrir({"_routeur_a_repondu": True}, None)); verifier("sans nom ni chemin : refus", False)
except RuntimeError:
    verifier("sans nom ni chemin, c'est le skill qui refuse, avec sa raison", True)
verifier("la boucle d'actions donne la demande ET l'avis du routeur à `drive_ouvrir`",
         'if action["skill"] == "drive_ouvrir":' in a1 and '"_fichier_exact": state.get("fichier_exact")' in a1
         and '"fichier_exact": "<nom écrit par la personne ou vide>"' in a1)

# 18/09 : un paramètre obligatoire absent ne refuse l'action AVANT le skill que si RIEN n'est donné.
proto = (BACKEND / "skills" / "protocol.py").read_text(encoding="utf-8")
verifier("le protocole ne refuse un paramètre obligatoire manquant que sur des arguments VIDES (les alias reviennent au skill)",
         'if manquants and any(str(v or "").strip() for v in args.values()):' in proto)

# 21/09 : « le PDF « symbiose_devisfinal » » — nommé SANS extension. Le routeur l'a cru imposé,
# le serveur a réimposé « symbiose_devisfinal » à chaque essai, et le tour est mort sur un rejeu.
meme = esp["_meme_nom"]
verifier("le même fichier, écrit sans son extension", meme("Symbiose_DevisFinal.pdf", "symbiose_devisfinal"))
verifier("… mais une extension DIFFÉRENTE n'est pas le même fichier", not meme("Symbiose_DevisFinal.pdf", "Symbiose_DevisFinal.jpg"))
verifier("… ni une lettre de moins (« Parkin » n'est pas « Parking »)", not meme("Parking.pdf", "Parkin.pdf"))
asyncio.run(ouvrir({"nom": "Symbiose_DevisFinal.pdf", "_demande_utilisateur": "",
                    "_fichier_exact": "symbiose_devisfinal", "_routeur_a_repondu": True}, None))
verifier("le modèle complète l'extension : son nom COMPLET part (plus de rejeu à l'identique)",
         recu["nom"] == "Symbiose_DevisFinal.pdf" and recu["exact"] is True, str(recu))

# L'ouverture exacte elle-même, exécutée contre un Drive doublé.
src_d = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
fn = next(n for n in ast.parse(src_d).body if isinstance(n, ast.AsyncFunctionDef) and n.name == "ouvrir")


class DriveRefuse(Exception):
    pass


FICHIERS = []


async def _resoudre_fichier(nom, perimetres, identite):
    return FICHIERS[0], None, FICHIERS[1:]


async def _deposer_pour(fichier, service, proprietaire, sortie):
    return sortie
ing = types.ModuleType("ingestion.connectors.google_drive"); ing._download_text = lambda s, f: "texte"
sys.modules.setdefault("ingestion", types.ModuleType("ingestion"))
sys.modules.setdefault("ingestion.connectors", types.ModuleType("ingestion.connectors"))
sys.modules["ingestion.connectors.google_drive"] = ing
import re as _re
_accents = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")
esp_d = {"_resoudre_fichier": _resoudre_fichier, "_deposer_pour": _deposer_pour, "DriveRefuse": DriveRefuse,
         "re": _re, "asyncio": asyncio, "Optional": __import__("typing").Optional,
         "_nu": lambda v: " ".join((v or "").translate(_accents).lower().split())}
exec(compile(ast.Module(body=[fn], type_ignores=[]), "drive.py", "exec",
             flags=__import__("__future__").annotations.compiler_flag), esp_d)
ouvrir_drive = esp_d["ouvrir"]
FICHIERS[:] = [{"id": "p", "name": "Symbiose_DevisFinal.pdf"}]
r = asyncio.run(ouvrir_drive("symbiose_devisfinal", exact=True))
verifier("écrit sans extension, UN seul fichier porte ce nom : il est ouvert", r.get("id") == "p", str(r))
FICHIERS[:] = [{"id": "j", "name": "Symbiose_DevisFinal.jpg"}, {"id": "p", "name": "Symbiose_DevisFinal.pdf"}]
try:
    asyncio.run(ouvrir_drive("symbiose_devisfinal", exact=True)); dit = False
except DriveRefuse as e:
    dit = "extension comprise" in str(e) and "Symbiose_DevisFinal.pdf" in str(e)
verifier("le PDF ET le JPG portent ce nom : rien n'est deviné, le nom complet est demandé", dit)
FICHIERS[:] = [{"id": "p", "name": "Symbiose_DevisFinal.pdf"}, {"id": "j", "name": "Symbiose_DevisFinal.jpg"}]
r = asyncio.run(ouvrir_drive("Symbiose_DevisFinal.pdf", exact=True))
verifier("… et avec le nom complet, le PDF s'ouvre", r.get("id") == "p", str(r))
FICHIERS[:] = [{"id": "k", "name": "Devis symbiose paysage Parking.pdf"}]
try:
    asyncio.run(ouvrir_drive("Devis symbiose paysage Parkin.pdf", exact=True)); refuse = False
except DriveRefuse:
    refuse = True
verifier("une vraie différence de nom reste refusée en exact (le cas du 18/09)", refuse)
verifier("le routeur sait que NOMMER un fichier ne suffit pas à l'imposer",
         "NOMMER un fichier ne suffit pas" in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
