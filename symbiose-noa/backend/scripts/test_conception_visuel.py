"""
Banc « LA CONCEPTION DU CLIENT EST VUE PAR LE MOTEUR » — 17/09, Symbiose.

Prompt « Montage fidèle à ma conception » : une photo de l'existant et une vue SketchUp. Le moteur
d'images ne recevait QUE la photo ; la vue 3D lui arrivait décrite en mots, et le montage était une
interprétation (déjà vécu : « ton photomontage est incorrect »). Ce banc exécute `modifier_visuel`
LIVRÉ contre un moteur doublé — aucun tirage, aucun appel payant :

  · avec `conception`, DEUX images partent au moteur, la conception en DERNIER, avec sa consigne ;
  · sans `conception`, rien ne change : une image, le préréglage d'avant ;
  · une conception introuvable ne bloque pas la retouche, et le résultat le DIT ;
  · la photo d'origine (repères tracés) et la conception cohabitent : trois images.
"""
import asyncio
import pathlib
import sys
import types

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


class Indispo(Exception):
    pass


APPELS = []
DEPOT = {"photo": (b"PHOTO", "image/jpeg"), "vue3d": (b"VUE3D", "image/png"), "rendu1": (b"RENDU", "image/png")}


async def generer(prompt, images_entree=None, qualite=None, **kw):
    APPELS.append({"prompt": prompt, "images": [o for o, _ in images_entree or []]})
    raise Indispo("moteur doublé : aucun tirage")


doublure("skills.erreurs", SkillError=SkillError)
doublure("skills.registre", Declaration=type("Declaration", (), {"__init__": lambda self, **kw: self.__dict__.update(kw)}))
doublure("visuels")
doublure("visuels.depot", lire=lambda cle: DEPOT.get(cle), origine_de=lambda cle: "photo" if cle == "rendu1" else None,
         noter_origine=lambda a, b: None, deposer_octets=lambda *a, **k: "x", peut_lire=lambda c, u: True)
doublure("visuels.nano_banana", generer=generer, NanoBananaIndisponible=Indispo)
print("\n═══ LA CONCEPTION VUE PAR LE MOTEUR —", BACKEND.parent)
from skills import visuels  # noqa: E402

u = types.SimpleNamespace(id="u1", role="direction")
r = asyncio.run(visuels.modifier_visuel({"image": "photo", "changements": "integrate every element of the design", "conception": "vue3d"}, u))
a = APPELS[-1]
verifier("avec `conception`, DEUX images partent au moteur, la conception en DERNIER",
         a["images"] == [b"PHOTO", b"VUE3D"], str(a["images"]))
verifier("la consigne dit quoi en prendre (les ouvrages) et quoi NE PAS en prendre (ciel, angle, style)",
         "DESIGN REFERENCE" in a["prompt"] and "never its sky" in a["prompt"] and "add NOTHING that is not in" in a["prompt"])
verifier("un moteur indisponible rend un refus propre, pas une exception", r.get("genere") is False)

asyncio.run(visuels.modifier_visuel({"image": "photo", "changements": "add a wooden deck"}, u))
verifier("sans `conception`, RIEN ne change : une image, pas de consigne de conception",
         APPELS[-1]["images"] == [b"PHOTO"] and "DESIGN REFERENCE" not in APPELS[-1]["prompt"])

asyncio.run(visuels.modifier_visuel({"image": "photo", "changements": "add a deck", "conception": "inconnue"}, u))
verifier("une conception INTROUVABLE ne bloque pas la retouche et n'ajoute pas de consigne fantôme",
         APPELS[-1]["images"] == [b"PHOTO"] and "DESIGN REFERENCE" not in APPELS[-1]["prompt"])

asyncio.run(visuels.modifier_visuel({"image": "rendu1", "changements": "lower the wall at the blue line", "conception": "vue3d"}, u))
verifier("photo d'origine (repères) ET conception cohabitent : trois images, la conception toujours dernière",
         APPELS[-1]["images"] == [b"RENDU", b"PHOTO", b"VUE3D"], str(APPELS[-1]["images"]))
asyncio.run(visuels.modifier_visuel({"image": "photo", "changements": "x y z", "conception": "photo"}, u))
verifier("donner la MÊME image comme conception ne l'envoie pas deux fois", APPELS[-1]["images"] == [b"PHOTO"])
d = visuels.SKILLS["modifier_visuel"]
verifier("le catalogue nomme `conception`, et le geste reste soumis à l'accord humain",
         "conception" in d.optionnels and d.effet == "externe" and "au lieu de la decrire en mots" in d.description)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
