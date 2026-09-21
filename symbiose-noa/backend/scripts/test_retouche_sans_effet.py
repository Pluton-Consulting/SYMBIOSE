"""
Banc de la retouche sans effet — un rendu identique ne se présente plus comme fait.

POURQUOI. 21/09, « fais le couloir en gravier plus large » demandé trois fois : trois
tirages facturés, trois images identiques à la précédente (0,0 % de la surface
changée, mesuré), et trois réponses « l'espace a été agrandi ». Le rédacteur écrit
d'après le résultat du geste, qui disait « image produite » ; personne ne regardait
l'image. `modifier_visuel` mesure désormais ce qui a changé et, sous 0,5 %, le dit
EN TÊTE du résultat.

La mesure est EXÉCUTÉE sur des images fabriquées (Pillow, présent dans l'image du
backend ; sans lui, cette partie est sautée et le banc le dit). Les calibrages
viennent des vrais rendus du 21/09 : 0,0 % pour les trois demandes du couloir,
1,8 % pour une porte repeinte, 4,1 % pour un sol refait, 13,6 % pour un muret ajouté.

Usage : python backend/scripts/test_retouche_sans_effet.py [backend]
"""
import importlib.util
import io
import pathlib
import sys

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend")
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print(f"\n═══ RETOUCHE SANS EFFET — {BACKEND.parent}\n")
source = (BACKEND / "skills" / "visuels.py").read_text(encoding="utf-8")

# ── 1. La consigne du moteur ─────────────────────────────────────────────────
debut = source.index("PRESET_FIDELITE = (")
preset = source[debut:source.index(")\n", debut)]
verifier("déplacer / élargir un élément est une modification demandée, pas une violation",
         "MOVES, SETS BACK, WIDENS" in preset and "protects only what is NOT listed" in preset)
verifier("un trait dessiné est une instruction, effacé du rendu",
         "Hand-drawn marks" in preset and "remove them completely from the result" in preset)

# ── 2. La mesure, exécutée ───────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    print("  · Pillow absent ici : la mesure n'est pas exécutée (elle l'est dans l'image du backend)")

if Image is not None:
    sys.path.insert(0, str(BACKEND))
    spec = importlib.util.spec_from_file_location("visuels_banc", BACKEND / "skills" / "visuels.py")
    visuels = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(visuels)

    def jpeg(img, qualite=92):
        tampon = io.BytesIO()
        img.save(tampon, "JPEG", quality=qualite)
        return tampon.getvalue()

    # Une scène avec du détail : un dégradé et quelques formes.
    scene = Image.new("RGB", (1195, 896), (120, 150, 110))
    d = ImageDraw.Draw(scene)
    for i in range(0, 1195, 40):
        d.line([(i, 0), (i, 896)], fill=(110 + i % 60, 140, 100), width=3)
    d.rectangle([700, 420, 1130, 690], fill=(60, 60, 65))            # une porte de garage
    d.polygon([(200, 700), (640, 500), (640, 540), (200, 860)], fill=(170, 130, 80))  # un muret

    avant = jpeg(scene)
    verifier("la même image ré-encodée (bruit du moteur) : rien n'a changé",
             visuels.part_changee(avant, jpeg(scene, 70)) < visuels.PART_INCHANGEE,
             str(visuels.part_changee(avant, jpeg(scene, 70))))

    porte = scene.copy()
    ImageDraw.Draw(porte).rectangle([700, 420, 1130, 690], fill=(200, 30, 30))
    part_porte = visuels.part_changee(avant, jpeg(porte))
    verifier("une porte repeinte se voit (au-dessus du seuil)", part_porte > visuels.PART_INCHANGEE, str(part_porte))

    deplace = scene.copy()
    dd = ImageDraw.Draw(deplace)
    dd.polygon([(200, 700), (640, 500), (640, 540), (200, 860)], fill=(150, 150, 140))   # gravier
    dd.polygon([(120, 640), (600, 470), (600, 505), (120, 790)], fill=(170, 130, 80))    # muret reculé
    part_deplace = visuels.part_changee(avant, jpeg(deplace))
    verifier("un muret déplacé se voit", part_deplace > visuels.PART_INCHANGEE, str(part_deplace))

    petite = jpeg(scene.resize((640, 480)))
    verifier("deux tailles différentes se comparent (photo d'origine 640 × 480 contre rendu)",
             visuels.part_changee(petite, avant) is not None)
    verifier("des octets illisibles : pas de mesure, jamais d'exception",
             visuels.part_changee(b"pas une image", avant) is None)

# ── 3. Le résultat le dit, en tête ───────────────────────────────────────────
fin = source[source.index("async def modifier_visuel("):source.index("_SENS_DE_ROTATION")]
verifier("la mesure compare la SOURCE au rendu", "part_changee(octets, rendu[0])" in fin)
verifier("sous le seuil, le constat est posé EN TÊTE (le rédacteur ne lit que le début)",
         'sortie = {"modification_appliquee": False, "constat": constat, **sortie}' in fin)
verifier("le compte rendu mécanique ne dit plus « avec les changements demandés »",
         'sortie["message_final"] = constat' in fin)
verifier("la consigne propose l'annotation au crayon et interdit de relancer la même retouche",
         "Annoter" in fin and "Ne relance pas la même retouche" in fin)
routeur = (BACKEND / "agents" / "router.py").read_text(encoding="utf-8")
verifier("le rédacteur après accord reçoit bien `constat` (il n'est pas écarté)",
         '"constat"' not in routeur[routeur.index("async def _reponse_apres_action("):routeur.index("async def _reponse_apres_echec(")])

print(f"\n{'═' * 70}\n{'✗ ' + str(len(echecs)) + ' échec(s) : ' + ', '.join(echecs) if echecs else '✓ 0 échec'}\n")
sys.exit(1 if echecs else 0)
