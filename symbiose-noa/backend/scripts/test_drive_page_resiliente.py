"""
Banc de la PAGE RÉSILIENTE du Drive (22/09).

Journaux de Symbiose, 18:23 : un seul « HttpError 500 » de Google au milieu du
balayage des 12 000 dossiers faisait mourir toute la construction du catalogue.

CE QUE CE BANC PROUVE (sans réseau, fonctions extraites par AST) :
  · une erreur passagère (500, 503, 429) se relit et la page arrive ;
  · un refus franc (403, 404) remonte au premier coup, sans attente ;
  · après trois essais, l'erreur passagère remonte (pas de boucle) ;
  · le balayage des dossiers et le comptage des fichiers passent par elle.
Tombe sur la version d'avant (fonction absente).

Usage : python backend/scripts/test_drive_page_resiliente.py [backend]
"""
import ast
import asyncio
import logging
import pathlib
import sys

racine = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend").resolve()
echecs = []


def verifier(nom, ok):
    print(("  ✓ " if ok else "  ✗ ") + nom)
    if not ok:
        echecs.append(nom)


src = (racine / "outils" / "drive.py").read_text(encoding="utf-8")
arbre = ast.parse(src)
noms = ("_ATTENTES_PAGE_S", "_erreur_passagere", "_page_resiliente")
morceaux = [n for n in arbre.body
            if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms)
            or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") in noms for t in n.targets))]
verifier("les trois morceaux existent dans outils/drive.py", len(morceaux) == 3)
if echecs:
    print(f"✗ {len(echecs)} échec(s)")
    sys.exit(1)

attentes = []


async def fausse_attente(s):
    attentes.append(s)

espace = {"asyncio": asyncio, "logger": logging.getLogger("banc")}
exec(compile(ast.Module(body=morceaux, type_ignores=[]), "drive", "exec"), espace)
espace["asyncio"] = type("A", (), {"to_thread": staticmethod(asyncio.to_thread), "sleep": staticmethod(fausse_attente)})
page = espace["_page_resiliente"]


class Refus(Exception):
    def __init__(self, statut):
        super().__init__(f"HttpError {statut}")
        self.resp = type("R", (), {"status": statut})()


def appel_qui_echoue(statuts):
    restants = list(statuts)

    def appel():
        if restants:
            raise Refus(restants.pop(0))
        return {"files": [1]}
    return appel


print("— erreur passagère : la page est relue")
attentes.clear()
verifier("500 puis 503 puis la page", asyncio.run(page(appel_qui_echoue([500, 503]))) == {"files": [1]})
verifier("deux attentes, 2 puis 6 s", attentes == [2.0, 6.0])

print("— refus franc : il remonte aussitôt")
attentes.clear()
try:
    asyncio.run(page(appel_qui_echoue([403])))
    verifier("le 403 remonte", False)
except Refus:
    verifier("le 403 remonte sans attendre", attentes == [])

print("— passagère sans fin : l'erreur remonte après trois essais")
attentes.clear()
try:
    asyncio.run(page(appel_qui_echoue([500, 500, 500, 500])))
    verifier("l'erreur remonte", False)
except Refus:
    verifier("trois essais, deux attentes, puis l'erreur", attentes == [2.0, 6.0])

print("— le balayage et le comptage l'utilisent")
bal = src[src.index("async def _balayer_dossiers"):src.index("# LE CATALOGUE DU DRIVE EST GARDÉ")]
cpt = src[src.index("async def _compter_fichiers"):]
cpt = cpt[:cpt.index("\nasync def ", 10)] if "\nasync def " in cpt[10:] else cpt
verifier("`_balayer_dossiers`", "await _page_resiliente(_appel)" in bal and "to_thread(_appel)" not in bal)
verifier("`_compter_fichiers`", "await _page_resiliente(_appel)" in cpt)

print()
if echecs:
    print(f"✗ {len(echecs)} échec(s)")
    sys.exit(1)
print("✓ 0 échec")
