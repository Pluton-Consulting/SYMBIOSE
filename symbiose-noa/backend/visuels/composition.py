"""
COMPOSER UN VISUEL : UNE PAGE HTML → UNE IMAGE PNG (23/09, Symbiose).

Relevé dans les échanges de Julien (23/09, 13:33 et 13:37) : « prends la photo
avant et la photo après, fais une seule image avec l'avant à gauche et l'après à
droite, et en dessous l'explication du projet, les matériaux et le nom des
plantes ». L'assistant a répondu qu'il n'avait « pas d'outil capable de coller
deux photos côte à côte » — et il avait raison : le moteur d'images RETOUCHE une
photo, il ne met pas en page. Demande de Noa : que l'IA écrive simplement une
page HTML à la taille voulue, y pose les images données, ajoute le texte et le
design, puis l'exporte en PNG.

CE QUE FAIT CE MODULE (sans modèle, sans coût) :
  * `nettoyer` retire de la page tout ce qui exécute ou appelle le réseau
    (scripts, cadres, gestionnaires d'événements, adresses extérieures) : la page
    est écrite par un modèle, elle ne doit rien pouvoir faire d'autre que
    s'afficher ;
  * `document` l'enveloppe à la taille exacte, avec une règle de sécurité
    (CSP) qui interdit tout script et toute ressource hors des images
    incorporées ;
  * les images désignées remplacent les marques `{{image1}}`, `{{image2}}`…
    sous forme de données incorporées (le conteneur qui rend la page n'a pas
    accès au dépôt, et ne doit rien télécharger) ;
  * `rendre` confie la page au conteneur navigateur (route `/rendre`), qui la
    photographie avec Chromium, réseau coupé.
"""
from __future__ import annotations

import base64
import io
import logging
import re

logger = logging.getLogger("symbiose.visuels.composition")

# Formats nommés : ce que la personne dit (« format carré pour Instagram », « une
# page A4 paysage ») plutôt que des pixels. A4 à 150 points par pouce.
FORMATS = {
    "paysage": (1920, 1080), "16:9": (1920, 1080),
    "carre": (1080, 1080), "carré": (1080, 1080), "instagram": (1080, 1080),
    "portrait": (1080, 1350), "story": (1080, 1920),
    "a4_paysage": (1754, 1240), "a4 paysage": (1754, 1240),
    "a4_portrait": (1240, 1754), "a4 portrait": (1240, 1754), "a4": (1240, 1754),
    "banniere": (1500, 500), "bannière": (1500, 500),
}
FORMAT_DEFAUT = "paysage"
COTE_MIN, COTE_MAX, PIXELS_MAX = 200, 4000, 12_000_000
IMAGES_MAX = 8
COTE_IMAGE_INCORPOREE = 2000          # une photo de 4 000 px n'apporte rien à une planche de 1 920
HTML_MAX = 60_000                     # le modèle écrit la page : au-delà, c'est une recopie

_MARQUE_IMAGE = re.compile(r"\{\{\s*image\s*:?\s*(\d+)\s*\}\}", re.I)


class CompositionRefusee(ValueError):
    """Demande impossible à rendre : la raison est pour la personne."""


def taille(format_: str | None = None, largeur=None, hauteur=None) -> tuple[int, int]:
    """(largeur, hauteur) en pixels : explicites s'ils sont donnés, sinon le format nommé."""
    if largeur or hauteur:
        try:
            l, h = int(float(largeur or 0)), int(float(hauteur or 0))
        except (TypeError, ValueError):
            raise CompositionRefusee("largeur et hauteur doivent être des nombres de pixels")
        if not l or not h:
            base = FORMATS.get(str(format_ or FORMAT_DEFAUT).strip().lower(), FORMATS[FORMAT_DEFAUT])
            l, h = l or round(h * base[0] / base[1]), h or round(l * base[1] / base[0])
    else:
        cle = str(format_ or FORMAT_DEFAUT).strip().lower()
        if cle not in FORMATS:
            raise CompositionRefusee(
                f"format « {format_} » inconnu : {', '.join(sorted({k for k in FORMATS if ' ' not in k}))}, "
                "ou largeur et hauteur en pixels")
        l, h = FORMATS[cle]
    if not (COTE_MIN <= l <= COTE_MAX and COTE_MIN <= h <= COTE_MAX) or l * h > PIXELS_MAX:
        raise CompositionRefusee(f"{l} × {h} px : chaque côté entre {COTE_MIN} et {COTE_MAX} px, "
                                 f"{PIXELS_MAX // 1_000_000} millions de pixels au plus")
    return l, h


_BALISES_INTERDITES = ("script", "iframe", "frame", "frameset", "object", "embed", "applet",
                       "form", "base", "link", "meta", "noscript", "template")


def nettoyer(html: str) -> str:
    """Retire ce qui exécute ou appelle le réseau. Fonction PURE, sans dépendance."""
    s = str(html or "")
    for balise in _BALISES_INTERDITES:
        s = re.sub(rf"<\s*{balise}\b[^>]*>.*?<\s*/\s*{balise}\s*>", "", s, flags=re.I | re.S)
        s = re.sub(rf"<\s*/?\s*{balise}\b[^>]*>", "", s, flags=re.I)
    # Gestionnaires d'événements (onload=, onerror=…), avec ou sans guillemets.
    s = re.sub(r"\son[a-z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", s, flags=re.I)
    s = re.sub(r"javascript\s*:", "", s, flags=re.I)
    # Adresses extérieures : attributs et url() de style. Seules les données
    # incorporées (data:) et les marques {{imageN}} restent.
    s = re.sub(r"(\s(?:src|href|srcset|poster|background|xlink:href)\s*=\s*)(\"|')\s*(?:https?:|//|file:|ftp:)[^\"']*\2",
               r"\1\2\2", s, flags=re.I)
    s = re.sub(r"url\(\s*(['\"]?)\s*(?:https?:|//|file:|ftp:)[^)]*\)", "url()", s, flags=re.I)
    s = re.sub(r"@import[^;]*;?", "", s, flags=re.I)
    return s


def marques(html: str) -> list[int]:
    """Les numéros d'images que la page utilise ({{image1}} → 1), dans l'ordre."""
    vus = []
    for m in _MARQUE_IMAGE.finditer(str(html or "")):
        n = int(m.group(1))
        if n not in vus:
            vus.append(n)
    return vus


def incorporer(html: str, images: list[str]) -> str:
    """Remplace {{imageN}} par la donnée incorporée de la N-ième image (1 = la première)."""
    def _remplacer(m):
        n = int(m.group(1))
        if 1 <= n <= len(images):
            return images[n - 1]
        raise CompositionRefusee(f"la page utilise {{{{image{n}}}}} mais seules "
                                 f"{len(images)} image(s) sont données")
    return _MARQUE_IMAGE.sub(_remplacer, str(html or ""))


def donnee_image(octets: bytes) -> str:
    """Une image → `data:` incorporable, réduite à COTE_IMAGE_INCORPOREE, redressée."""
    from PIL import Image, ImageOps
    img = Image.open(io.BytesIO(octets))
    img = ImageOps.exif_transpose(img)
    if max(img.size) > COTE_IMAGE_INCORPOREE:
        img.thumbnail((COTE_IMAGE_INCORPOREE, COTE_IMAGE_INCORPOREE))
    sortie = io.BytesIO()
    transparente = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    if transparente:
        img.save(sortie, format="PNG", optimize=True)
        mime = "image/png"
    else:
        img.convert("RGB").save(sortie, format="JPEG", quality=88, optimize=True)
        mime = "image/jpeg"
    return f"data:{mime};base64," + base64.b64encode(sortie.getvalue()).decode()


def document(corps: str, largeur: int, hauteur: int, fond: str = "#ffffff") -> str:
    """La page complète, à la taille EXACTE, sans script ni réseau possibles."""
    fond = fond if re.fullmatch(r"#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20}", str(fond or "")) else "#ffffff"
    return (
        "<!DOCTYPE html><html lang=\"fr\"><head><meta charset=\"utf-8\">"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
        "img-src data:; style-src 'unsafe-inline'; font-src data:\">"
        "<style>*{box-sizing:border-box}html,body{margin:0;padding:0}"
        f"body{{width:{largeur}px;height:{hauteur}px;overflow:hidden;background:{fond};"
        "font-family:'Liberation Sans','DejaVu Sans','Noto Sans',Arial,sans-serif;color:#1f2a1f;"
        "-webkit-font-smoothing:antialiased}img{display:block;max-width:100%}</style>"
        f"</head><body>{corps}</body></html>")


async def rendre(page: str, largeur: int, hauteur: int) -> bytes:
    """Le PNG de la page, rendu par le conteneur navigateur. Lève CompositionRefusee."""
    import httpx
    from config import settings
    if not getattr(settings, "browser_enabled", False):
        raise CompositionRefusee("le rendu des pages est désactivé sur ce serveur")
    url = settings.browser_worker_url.rstrip("/") + "/rendre"
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(url, json={"html": page, "largeur": largeur, "hauteur": hauteur},
                                  headers={"X-Navigateur-Secret": settings.browser_worker_secret})
    except httpx.HTTPError as e:
        logger.warning("Rendu de composition : conteneur injoignable (%s)", type(e).__name__)
        raise CompositionRefusee("le moteur de rendu ne répond pas") from e
    if r.status_code == 404:
        logger.warning("Rendu de composition : 404 — l'image du navigateur date d'avant /rendre, la reconstruire")
        raise CompositionRefusee("le moteur de rendu n'est pas à jour sur ce serveur")
    try:
        d = r.json()
    except Exception as e:  # noqa: BLE001
        raise CompositionRefusee(f"réponse illisible du moteur de rendu (HTTP {r.status_code})") from e
    if not d.get("ok"):
        raise CompositionRefusee(f"le rendu a échoué : {d.get('erreur') or 'raison inconnue'}")
    return base64.b64decode(d["png"])
