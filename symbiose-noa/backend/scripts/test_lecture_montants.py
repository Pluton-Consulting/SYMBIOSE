"""
Banc « un montant se lit, deux montants collés ne font pas un milliard » — 18/09, recette pilotée.

Prompt 13 (dossier client consolidé) : la fiche d'un client annonçait « 14 360 181 369 014,46 € ».
Un export range TTC et HT dans la MÊME cellule ; privée de ses espaces, l'écriture portait plusieurs
points, tous pris pour des séparateurs de milliers. Ce banc fige les lectures d'AVANT (rien ne doit
bouger pour une écriture bien formée) et la nouvelle règle (le premier montant d'une cellule double).
"""
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
from skills.lecture import lire_montant  # noqa: E402

echecs = []
print("\n═══ LECTURE DES MONTANTS —", BACKEND.parent)
INCHANGES = {"12 450,50 €": 12450.5, "1.234,56": 1234.56, "1,234.56": 1234.56, "7.000": 7000.0,
             "1.234.567": 1234567.0, "33 593,47 €": 33593.47, "4312.5": 4312.5, "-120,00": -120.0,
             "1 896 390,38": 1896390.38, "15": 15.0, "abc": 0.0, "1,234,567.89": 1234567.89, "0,5": 0.5,
             "2 425 640,31 €": 2425640.31, "": 0.0}
DOUBLES = {"14 360,18 13 054,71": 14360.18, "14360.1813054.71": 14360.18, "14 360,18\n13 054,71": 14360.18,
           "1 242,00 1 490,40": 1242.0}
for libelle, cas in (("une écriture bien formée se lit comme avant", INCHANGES),
                     ("deux montants dans une cellule : le PREMIER, jamais leur collage", DOUBLES)):
    for v, attendu in cas.items():
        r = lire_montant(v)
        ok = abs(r - attendu) < 1e-6
        print(f"  {'✓' if ok else '✗'} {libelle} : {v!r} → {r}")
        if not ok:
            echecs.append(f"{v!r} → {r} (attendu {attendu})")
verifie = all(lire_montant(v) < 1e9 for v in DOUBLES)
print(f"  {'✓' if verifie else '✗'} aucune cellule double ne dépasse le milliard")
if not verifie:
    echecs.append("milliard")

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + " ; ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
