"""
Banc « COMPOSER UN VISUEL : UNE PAGE HTML → UNE IMAGE PNG » (23/09, Symbiose).

Relevé chez Julien : « la photo avant à gauche, l'après à droite, et dessous
l'explication du projet » → « je n'ai pas d'outil capable de coller deux photos ».

CE QUE CE BANC PROUVE (module et skill LIVRÉS, rendu et résolution doublés) :
  * la page écrite par le modèle perd tout ce qui exécute ou appelle le réseau
    (script, iframe, onerror=, javascript:, adresses http, @import) et garde
    le reste (styles, texte, marques d'images) ;
  * la page finale a la taille exacte, une règle de sécurité sans script ni
    réseau, et les images y sont incorporées dans l'ordre ;
  * les formats nommés et les tailles hors bornes se disent ;
  * le geste pose les images, rend, range le PNG, garde la page, rend le bloc
    d'écran ; `depuis` rend la page pour la corriger ; une marque {{image3}}
    sans troisième image est refusée AVANT tout rendu ;
  * le geste est déclaré, rangé dans la famille visuels, et le serveur pose
    les deux dernières images quand aucune n'est nommée (contrat lu).
"""
import asyncio
import base64
import importlib.util
import io
import pathlib
import sys
import tempfile
import types

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend").resolve()
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print(f"\n═══ COMPOSER UN VISUEL — {BACKEND.parent}\n")
try:
    from PIL import Image
except ImportError:
    print("SKIP : Pillow absent de cet environnement")
    sys.exit(0)


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


sys.modules["config"] = types.SimpleNamespace(settings=types.SimpleNamespace(
    browser_enabled=True, browser_worker_url="http://navigateur:9000", browser_worker_secret="s"))
c = charger("visuels.composition", BACKEND / "visuels" / "composition.py")

print("— Le nettoyage de la page")
sale = ('<div style="color:red">Avant<script>alert(1)</script><img src="{{image1}}" onerror="x()">'
        '<iframe src="https://x.fr"></iframe><a href="javascript:alert(2)">l</a>'
        '<img src="https://traceur.fr/p.gif"><div style="background:url(http://x.fr/a.png)"></div>'
        '<style>@import url(https://f.fr/a.css); h1{color:#2f5d3a}</style><link rel="stylesheet" href="https://x"></div>')
propre = c.nettoyer(sale)
for mot in ("<script", "alert(1)", "onerror", "<iframe", "javascript:", "traceur.fr", "http://x.fr", "@import", "<link"):
    verifier(f"retiré : {mot}", mot not in propre, propre)
for mot in ('style="color:red"', "Avant", "{{image1}}", "h1{color:#2f5d3a}"):
    verifier(f"gardé : {mot}", mot in propre, propre)

print("\n— La taille")
verifier("défaut : paysage 1920 × 1080", c.taille() == (1920, 1080))
verifier("format « carré » : 1080 × 1080", c.taille("carré") == (1080, 1080))
verifier("A4 paysage : 1754 × 1240", c.taille("a4_paysage") == (1754, 1240))
verifier("pixels explicites", c.taille(None, 1200, 800) == (1200, 800))
verifier("une seule dimension : l'autre suit le format", c.taille("carre", 900, None) == (900, 900))
for mauvais in [("inconnu", None, None), (None, 5000, 800), (None, 50, 800), (None, 3900, 3900)]:
    try:
        c.taille(*mauvais)
        verifier(f"refusé : {mauvais}", False)
    except c.CompositionRefusee:
        verifier(f"refusé : {mauvais}", True)

print("\n— La page finale")


def png(couleur, l=64, h=48):
    b = io.BytesIO()
    Image.new("RGB", (l, h), couleur).save(b, format="PNG")
    return b.getvalue()


d1, d2 = c.donnee_image(png("green")), c.donnee_image(png("red", 3000, 1500))
verifier("une photo devient une donnée incorporée", d1.startswith("data:image/jpeg;base64,"))
grande = Image.open(io.BytesIO(base64.b64decode(d2.split(",", 1)[1])))
verifier("une photo de 3 000 px est réduite à 2 000", max(grande.size) == c.COTE_IMAGE_INCORPOREE, grande.size)
page = c.document(c.incorporer('<img src="{{image2}}"><img src="{{ image:1 }}">', [d1, d2]), 1200, 800)
verifier("les marques sont remplacées dans l'ordre", page.index(d2) < page.index(d1))
verifier("taille exacte posée", "width:1200px;height:800px" in page)
verifier("règle de sécurité : aucun script, aucun réseau", "default-src 'none'" in page and "img-src data:" in page)
try:
    c.incorporer("{{image3}}", [d1, d2])
    verifier("{{image3}} sans 3e image : refusé", False)
except c.CompositionRefusee:
    verifier("{{image3}} sans 3e image : refusé", True)
verifier("les marques se relèvent", c.marques("{{image2}} {{image1}} {{image2}}") == [2, 1])

print("\n— Le geste")
DOSSIER = pathlib.Path(tempfile.mkdtemp()) / "visuels"
DOSSIER.mkdir()
depot = types.ModuleType("visuels.depot")
DEPOTS = {}


def deposer_octets(o, mime="image/png", proprietaire=None):
    cle = f"cle{len(DEPOTS) + 1:021d}"
    DEPOTS[cle] = o
    return cle


depot.DOSSIER, depot.deposer_octets = DOSSIER, deposer_octets
depot.peut_lire = lambda cle, user: cle in DEPOTS
visuels_pkg = types.ModuleType("visuels")
visuels_pkg.composition, visuels_pkg.depot = c, depot
sys.modules["visuels"] = visuels_pkg
sys.modules["visuels.depot"] = depot
IMAGES = {"cleavant": png("green"), "cleapres": png("blue")}


class ImageRefusee(ValueError):
    pass


async def resoudre(ref, user, **k):
    if ref not in IMAGES:
        raise ImageRefusee("introuvable")
    return IMAGES[ref], "png", ref


imgs = types.ModuleType("bureautique.images")
imgs.ImageRefusee, imgs.resoudre = ImageRefusee, resoudre
sys.modules["bureautique"] = types.ModuleType("bureautique")
sys.modules["bureautique.images"] = imgs


class SkillError(Exception):
    pass


err = types.ModuleType("skills.erreurs")
err.SkillError = SkillError
sys.modules["skills"] = types.ModuleType("skills")
sys.modules["skills.erreurs"] = err
reg = types.ModuleType("skills.registre")
reg.Declaration = lambda **k: types.SimpleNamespace(**k)
sys.modules["skills.registre"] = reg
RENDUS = []


async def rendre(page, l, h):
    RENDUS.append((page, l, h))
    return png("white", l, h)


c.rendre = rendre
for nom in ("visuels.nano_banana", "visuels.heic"):
    sys.modules[nom] = types.ModuleType(nom)
try:
    sv = charger("skills_visuels", BACKEND / "skills" / "visuels.py")
except Exception as e:  # noqa: BLE001
    print(f"  ✗ chargement du module des visuels : {type(e).__name__} {e}")
    echecs.append("chargement")
    sv = types.SimpleNamespace()
user = types.SimpleNamespace(id="u1", role="direction")
HTML = ('<div style="display:flex"><img src="{{image1}}" style="width:50%"><img src="{{image2}}" '
        'style="width:50%"></div><p>Massif de graminées, bordure corten</p>')


async def scenario():
    r = await sv.composer_visuel({"html": HTML, "images": ["cleavant", "cleapres"], "format": "paysage",
                                  "titre": "Avant / après"}, user)
    verifier("rendu fait à 1920 × 1080", RENDUS and RENDUS[-1][1:] == (1920, 1080))
    verifier("les deux photos incorporées", RENDUS[-1][0].count("data:image/jpeg;base64,") == 2)
    verifier("bloc d'écran garanti, image principale = le rendu",
             r.get("bloc_garanti") and r["bloc_ui"]["principale"] == r["image"])
    verifier("la page est gardée à côté du rendu", (DOSSIER / f"{r['image']}.composition.json").exists())
    relue = await sv.composer_visuel({"depuis": r["image"]}, user)
    verifier("`depuis` sans html : la page et ses images reviennent",
             relue.get("html") == HTML and relue.get("images") == ["cleavant", "cleapres"])
    n = len(RENDUS)
    r2 = await sv.composer_visuel({"depuis": r["image"], "html": HTML.replace("corten", "acier corten")}, user)
    verifier("correction : mêmes images, même taille, nouveau rendu",
             len(RENDUS) == n + 1 and RENDUS[-1][1:] == (1920, 1080) and r2["image"] != r["image"])
    n = len(RENDUS)
    for donnees, attendu in (({"html": "{{image3}}", "images": ["cleavant"]}, "3e image"),
                             ({"html": "<p>x</p>", "images": ["inconnue"]}, "image introuvable"),
                             ({"images": ["cleavant"]}, "page absente"),
                             ({"html": "<p>x</p>", "format": "géant"}, "format inconnu")):
        try:
            await sv.composer_visuel(donnees, user)
            verifier(f"refus : {attendu}", False)
        except SkillError:
            verifier(f"refus : {attendu}", True)
    verifier("aucun rendu lancé pour une demande refusée", len(RENDUS) == n)

if hasattr(sv, "composer_visuel"):
    asyncio.run(scenario())
else:
    verifier("le geste composer_visuel existe", False)

print("\n— Contrats lus dans le source")
src = (BACKEND / "skills" / "visuels.py").read_text(encoding="utf-8")
verifier("déclaré, effet interne (gratuit, sans accord)",
         '"composer_visuel": Declaration(' in src and 'libelle="je compose l\'image"' in src)
verifier("rangé dans la famille visuels",
         '"composer_visuel"' in (BACKEND / "skills" / "familles.py").read_text(encoding="utf-8"))
a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("sans images nommées : les deux dernières du fil", 'args = {**args, "images": _images[-2:]}' in a1)
verifier("la consigne des images renvoie l'assemblage à composer_visuel", "est `composer_visuel`" in a1)
w = (BACKEND.parent / "browser-worker" / "rapide.py").read_text(encoding="utf-8")
corps_rendu = w.split("async def rendre_html", 1)[1].split("async def ouvrir", 1)[0]
verifier("conteneur : réseau coupé pour le rendu", "--host-resolver-rules=MAP * ~NOTFOUND" in corps_rendu)
verifier("conteneur : pas l'option qui empêche la capture", "scriptEnabled=false" not in corps_rendu)
verifier("conteneur : route /rendre",
         '@app.post("/rendre")' in (BACKEND.parent / "browser-worker" / "worker.py").read_text(encoding="utf-8"))

print(f"\n{'✅ tout passe' if not echecs else f'❌ {len(echecs)} échec(s)'}\n")
sys.exit(1 if echecs else 0)
