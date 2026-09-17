"""
Banc « LE CATALOGUE DU DRIVE NE MEURT PAS AVEC SON APPELANT » — 17/09, fil d13ff0ac.

Deux défauts du chemin À FROID de `outils/drive.py::_catalogue`, et le délai du geste :
  · la construction (≈ 60 s pour 12 150 dossiers) était attendue directement : un
    appelant annulé l'emportait, tout était à refaire au geste suivant ;
  · un second appelant, pendant ce temps, voyait `en_cours` et recevait un
    catalogue VIDE — une recherche qui ne trouve aucun dossier, sans le dire ;
  · `drive_chercher` abandonnait à 45 s, moins que le travail normal d'un motif large.

Sans réseau : les fonctions sont extraites du code livré, le balayage est doublé.
"""
import ast
import asyncio
import pathlib
import re
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
arbre = ast.parse(src)
voulues = {"_copie_catalogue", "_construire_catalogue", "_catalogue"}
code = "\n\n".join(ast.get_source_segment(src, n) for n in arbre.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in voulues)

balayages = []


async def _balayer_dossiers(service):
    balayages.append(1)
    await asyncio.sleep(0.3)
    return {"d1": {"name": "ESPACES VERTS", "parents": []}}, False


async def _compter_fichiers(service):
    return {"d1": 3}, False


class _Log:
    def info(self, *a, **k): pass


esp = {"asyncio": asyncio, "_CATALOGUES": {}, "_CONSTRUCTIONS": {}, "CATALOGUE_DRIVE_DUREE_S": 3600,
       "_balayer_dossiers": _balayer_dossiers, "_compter_fichiers": _compter_fichiers,
       "_cle_client": lambda i: "service" if i is None else str(i), "logger": _Log()}
exec(code, esp)
catalogue = esp["_catalogue"]

print("\n═══ CATALOGUE PARTAGÉ —", BACKEND.parent)


async def scenario():
    # 1. Un appelant annulé (le délai du geste) n'emporte pas la construction.
    try:
        await asyncio.wait_for(catalogue(object()), timeout=0.05)
        annule = False
    except asyncio.TimeoutError:
        annule = True
    verifier("l'appelant trop pressé est bien annulé", annule)
    # 2. Un second appelant, PENDANT la construction, attend le vrai catalogue.
    dossiers, *_ = await catalogue(object())
    verifier("le second appelant reçoit le catalogue PLEIN, pas un catalogue vide", "d1" in dossiers, str(dossiers))
    verifier("le balayage n'a tourné qu'UNE fois (la construction a survécu à l'annulation)", len(balayages) == 1, str(len(balayages)))
    # 3. Ensuite, le cache sert sans rebalayer.
    await catalogue(object())
    verifier("le troisième appel sort du cache", len(balayages) == 1)
    # 4. Une autre identité a SON catalogue.
    await catalogue(object(), identite="autre@exemple-paysage.fr")
    verifier("une autre identité ne reçoit jamais le Drive de la première", len(balayages) == 2
             and set(esp["_CATALOGUES"]) == {"service", "autre@exemple-paysage.fr"})
    # 5. Les appelants modifient leur copie, jamais le catalogue gardé.
    d, *_ = await catalogue(object()); d["d1"]["parents"].append("x") if False else d.pop("d1")
    d2, *_ = await catalogue(object())
    verifier("le catalogue gardé reste intact quand un appelant modifie sa copie", "d1" in d2)

asyncio.run(scenario())

outils = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
m = re.search(r"^DELAI_RECHERCHE_DRIVE_S = (\d+)", outils, re.M)
verifier("le délai de `drive_chercher` se compte en minutes (une recherche ne se bloque pas en temps)",
         m is not None and int(m.group(1)) >= 180 and "timeout=DELAI_RECHERCHE_DRIVE_S" in outils and "timeout=45" not in outils)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
