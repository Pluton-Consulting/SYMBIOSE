"""
Banc des photos d'iPhone (HEIC / HEIF) — converties dès qu'elles entrent (21/09).

Demande de Noa : « un outil de conversion HEIC vers PNG ou JPG, en automatique dès
qu'une image de ce format est mise en pièce jointe, et l'IA peut s'en servir si
besoin ». Éprouvé ici :
  · la détection par les OCTETS (la boîte « ftyp »), pas seulement par le nom ;
  · la conversion (JPEG ou PNG, redressée, sans métadonnées) ;
  · les trois entrées automatiques : pièces jointes du chat, dépôt d'une image
    (photos du Drive, pièces d'un mail), lecture d'une pièce de mail ;
  · le geste `convertir_image`, au catalogue, que l'assistant appelle au besoin.

Ce qui exige `pillow-heif` (installé par requirements.lock) ne s'exécute que là
où il est — l'image du backend ; ailleurs le banc le dit.

Usage : python backend/scripts/test_heic.py [backend]
"""
import ast
import asyncio
import base64
import importlib.util
import io
import logging
import os
import pathlib
import sys
import tempfile
import types

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend").resolve()
sys.path.insert(0, str(BACKEND))
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    spec.loader.exec_module(module)
    return module


def fonction_de(chemin, nom, espace):
    """Extrait UNE fonction d'un module lourd et l'exécute dans `espace`."""
    source = (BACKEND / chemin).read_text(encoding="utf-8")
    arbre = ast.parse(source)
    noeud = next(n for n in arbre.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nom)
    exec(compile(ast.Module(body=[noeud], type_ignores=[]), chemin, "exec"), espace)
    return espace[nom]


print(f"\n═══ LES PHOTOS D'IPHONE (HEIC) — {BACKEND.parent}\n")
heic = charger("visuels.heic", BACKEND / "visuels" / "heic.py")

# ── La détection ──────────────────────────────────────────────────────────────
entete_heic = b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic"
verifier("un HEIC se reconnaît à ses octets", heic.est_heic(entete_heic))
verifier("… même annoncé comme un fichier quelconque", heic.est_heic(entete_heic, "application/octet-stream", "photo.bin"))
verifier("… même renommé en .jpg", heic.est_heic(entete_heic, "image/jpeg", "IMG_1234.jpg"))
verifier("une image HEIF « mif1 » aussi", heic.est_heic(b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00"))
verifier("un AVIF n'est pas un HEIC", not heic.est_heic(b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00", "", "x.avif"))
verifier("un JPEG n'est pas un HEIC", not heic.est_heic(b"\xff\xd8\xff\xe0\x00\x10JFIF", "image/jpeg", "a.jpg"))
verifier("le nom converti garde la base", heic.nom_converti("IMG_1234.HEIC", "jpg") == "IMG_1234.jpg")

# ── Le branchement ────────────────────────────────────────────────────────────
racine = BACKEND.parent
verifier("pillow-heif est une dépendance déclarée ET verrouillée (avec empreintes)",
         "pillow-heif" in (BACKEND / "requirements.txt").read_text(encoding="utf-8")
         and "pillow-heif==" in (BACKEND / "requirements.lock").read_text(encoding="utf-8"))
verifier("le décodeur est activé au démarrage du serveur",
         "activer_heic()" in (BACKEND / "main.py").read_text(encoding="utf-8"))
chat = (BACKEND / "routers" / "chat.py").read_text(encoding="utf-8")
verifier("les pièces jointes du chat sont converties AVANT tout le reste, hors de la boucle",
         "await asyncio.to_thread(_convertir_heic, pieces)" in chat)
verifier("tout dépôt d'image convertit un HEIC (photos du Drive, pièces de mail)",
         "est_heic(octets, mime)" in (BACKEND / "visuels" / "depot.py").read_text(encoding="utf-8"))
verifier("une pièce de mail HEIC est convertie avant d'être lue",
         (BACKEND / "mail" / "pieces.py").read_text(encoding="utf-8").count("_sans_heic, nom") == 2)
visuels_src = (BACKEND / "skills" / "visuels.py").read_text(encoding="utf-8")
verifier("le geste `convertir_image` est au catalogue", '"convertir_image": Declaration(' in visuels_src)
verifier("… dans la famille des images (le routeur le propose)",
         '"convertir_image"' in (BACKEND / "skills" / "familles.py").read_text(encoding="utf-8"))
verifier("… et sans référence, c'est la DERNIÈRE image de la conversation",
         '("pivoter_image", "convertir_image")' in (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8"))
barre = (racine / "frontend" / "components" / "chat" / "InputBar.tsx").read_text(encoding="utf-8")
verifier("l'écran annonce « HEIC → JPG » sur la pièce en attente, sans vignette cassée",
         "HEIC → JPG" in barre and "onError" in barre)

# ── Exécuté, là où pillow-heif est installé ───────────────────────────────────
try:
    from PIL import Image
    import pillow_heif  # noqa: F401
except ImportError:
    Image = None
    print("  · pillow-heif absent ici : la conversion n'est pas exécutée (elle l'est dans l'image du backend)")

if Image is not None:
    heic.activer()
    photo = Image.new("RGB", (400, 300), (40, 140, 60))
    for x in range(150, 250):
        for y in range(100, 200):
            photo.putpixel((x, y), (220, 30, 30))
    tampon = io.BytesIO()
    photo.save(tampon, "HEIF", quality=90)
    vrai_heic = tampon.getvalue()
    verifier("un vrai fichier HEIC est reconnu à ses octets", heic.est_heic(vrai_heic, "", "sans-nom"))

    jpeg, mime, ext = heic.convertir(vrai_heic, "jpg")
    im = Image.open(io.BytesIO(jpeg))
    verifier("HEIC → JPEG : même taille, contenu gardé",
             mime == "image/jpeg" and ext == "jpg" and im.size == (400, 300)
             and im.convert("RGB").getpixel((200, 150))[0] > 180, f"{mime} {im.size}")
    png, mime_png, _ = heic.convertir(vrai_heic, "png")
    verifier("HEIC → PNG", mime_png == "image/png" and png[:8] == b"\x89PNG\r\n\x1a\n")
    try:
        heic.convertir(vrai_heic, "gif")
        refuse = False
    except ValueError as e:
        refuse = "jpg ou png" in str(e)
    verifier("un format de sortie inconnu est refusé en le disant", refuse)

    # Les pièces jointes du chat : la fonction EXÉCUTÉE telle qu'elle est livrée.
    espace = {"base64": base64, "logger": logging.getLogger("banc")}
    convertir_pieces = fonction_de("routers/chat.py", "_convertir_heic", espace)
    pieces = [{"nom": "IMG_4750.HEIC", "mime": "image/heic", "b64": base64.b64encode(vrai_heic).decode()},
              {"nom": "devis.pdf", "mime": "application/pdf", "b64": base64.b64encode(b"%PDF-1.4").decode()}]
    convertir_pieces(pieces)
    p = pieces[0]
    verifier("pièce jointe du chat : la photo HEIC devient « IMG_4750.jpg », en JPEG",
             p["nom"] == "IMG_4750.jpg" and p["mime"] == "image/jpeg"
             and base64.b64decode(p["b64"])[:3] == b"\xff\xd8\xff" and p.get("converti_de") == "IMG_4750.HEIC", str(p)[:120])
    verifier("… les autres pièces ne bougent pas", pieces[1]["nom"] == "devis.pdf")

    with tempfile.TemporaryDirectory() as dossier:
        os.environ["DOCUMENTS_DIR"] = dossier
        sys.modules.setdefault("stockage", types.ModuleType("stockage"))
        if "stockage.verrous" not in sys.modules:
            try:
                import stockage.verrous  # noqa: F401
            except Exception:  # noqa: BLE001
                import contextlib
                v = types.ModuleType("stockage.verrous")
                v.verrou_fichier = lambda *a, **k: contextlib.nullcontext()
                sys.modules["stockage.verrous"] = v
        depot = charger("visuels.depot", BACKEND / "visuels" / "depot.py")
        cle = depot.deposer_octets(vrai_heic, "image/heic")
        range_ = depot.lire(cle) if cle else None
        verifier("un HEIC déposé (photo du Drive, pièce de mail) est rangé en JPEG, affichable",
                 range_ is not None and range_[1] == "image/jpeg" and range_[0][:3] == b"\xff\xd8\xff", str(range_ and range_[1]))

        # Le geste de l'assistant, avec une résolution doublée (ses droits sont éprouvés ailleurs).
        images = types.ModuleType("bureautique.images")

        class ImageRefusee(Exception):
            pass

        async def resoudre(ref, user, place="", contexte="", remarques=None):
            if ref != "IMG_4750.HEIC":
                raise ImageRefusee("introuvable")
            return vrai_heic, "heic", "IMG_4750.HEIC"
        images.ImageRefusee, images.resoudre = ImageRefusee, resoudre
        sys.modules["bureautique"] = sys.modules.get("bureautique") or types.ModuleType("bureautique")
        sys.modules["bureautique.images"] = images
        erreurs = types.ModuleType("skills.erreurs")

        class SkillError(Exception):
            pass
        erreurs.SkillError = SkillError
        sys.modules["skills.erreurs"] = erreurs
        convertir_image = fonction_de("skills/visuels.py", "convertir_image", {})
        utilisateur = types.SimpleNamespace(id="u1")
        r = asyncio.run(convertir_image({"image": "IMG_4750.HEIC", "format": "png"}, utilisateur))
        verifier("`convertir_image` : le HEIC du Drive devient un PNG téléchargeable, affiché en carte",
                 r.get("convertie") and r["format"] == "png" and r["nom"] == "IMG_4750.png"
                 and r["bloc_ui"]["type"] == "visuel" and depot.lire(r["image"])[1] == "image/png", str(r)[:200])
        try:
            asyncio.run(convertir_image({"image": "inconnu.heic"}, utilisateur))
            dit = False
        except SkillError as e:
            dit = "n'a pas pu être convertie" in str(e)
        verifier("… une référence introuvable se dit, sans planter", dit)

print(f"\n{'═' * 70}\n{'✗ ' + str(len(echecs)) + ' échec(s) : ' + ', '.join(echecs) if echecs else '✓ 0 échec'}\n")
sys.exit(1 if echecs else 0)
