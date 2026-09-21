"""
LES PHOTOS D'IPHONE (HEIC / HEIF), CONVERTIES DÈS QU'ELLES ENTRENT (21/09).

Un iPhone enregistre ses photos en HEIC. Ni Pillow seul, ni Chrome, ni Word ne
savent les ouvrir : une photo de chantier jointe telle quelle n'arrivait pas à la
vision, ne s'affichait pas dans le chat et ne pouvait pas entrer dans un document.
Demande de Noa : « un outil de conversion HEIC vers PNG ou JPG, en automatique dès
qu'une image de ce format est mise en pièce jointe, et l'IA peut s'en servir si
besoin ».

Trois usages, un seul module :
  · `activer()` enregistre le décodeur HEIF dans Pillow, pour tout le processus
    (appelé au démarrage) : toute lecture d'image du backend sait alors l'ouvrir ;
  · les pièces jointes du chat, et tout dépôt d'image (photos du Drive, pièces
    d'un mail), passent en JPEG avant d'aller plus loin (`est_heic`, `convertir`) ;
  · le geste `convertir_image` s'en sert quand l'assistant a besoin d'un JPG ou
    d'un PNG (skills/visuels.py).

Un HEIC se reconnaît à ses OCTETS (la boîte « ftyp » et sa marque), pas seulement
à son nom : un navigateur annonce parfois `application/octet-stream`, et une photo
renommée en « .jpg » reste un HEIC.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger("symbiose.visuels.heic")

# Les marques de la boîte « ftyp » d'un fichier HEIF (images fixes et séquences).
_MARQUES = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
_MIMES = ("image/heic", "image/heif", "image/heic-sequence", "image/heif-sequence")
FORMATS = {"jpg": ("JPEG", "image/jpeg", "jpg"), "jpeg": ("JPEG", "image/jpeg", "jpg"),
           "png": ("PNG", "image/png", "png")}

_actif: bool | None = None


def activer() -> bool:
    """Enregistre le décodeur HEIF dans Pillow (une fois par processus). Faux s'il manque."""
    global _actif
    if _actif is None:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
            _actif = True
        except Exception as e:  # noqa: BLE001 — sans lui, un HEIC est refusé en le disant
            logger.warning("Décodage HEIC indisponible (pillow-heif absent) : %s", e)
            _actif = False
    return _actif


def est_heic(octets: bytes | None, mime: str | None = "", nom: str | None = "") -> bool:
    """Ces octets sont-ils une image HEIC / HEIF ? Les octets d'abord, le type et le nom ensuite."""
    tete = bytes((octets or b"")[:12])
    if len(tete) >= 12 and tete[4:8] == b"ftyp":
        return tete[8:12] in _MARQUES
    return (str(mime or "").split(";")[0].strip().lower() in _MIMES
            or str(nom or "").lower().endswith((".heic", ".heif")))


def nom_converti(nom: str | None, extension: str) -> str:
    """« IMG_1234.HEIC » → « IMG_1234.jpg »."""
    nom = str(nom or "image").strip() or "image"
    base = nom.rsplit(".", 1)[0] if "." in nom else nom
    return f"{base}.{extension}"


def convertir(octets: bytes, format: str = "jpg", qualite: int = 92) -> tuple[bytes, str, str]:
    """(octets, mime, extension) : l'image en JPEG ou en PNG, redressée, sans métadonnées.

    Lève `ValueError` avec une phrase lisible : format inconnu, décodeur HEIC absent,
    fichier qui n'est pas une image.
    """
    cible = FORMATS.get(str(format or "jpg").strip().lower().lstrip("."))
    if not cible:
        raise ValueError(f"format « {format} » inconnu : jpg ou png")
    activer()
    from PIL import Image, ImageOps
    try:
        img = Image.open(io.BytesIO(octets))
        img.load()
    except Exception as e:  # noqa: BLE001
        if est_heic(octets) and not _actif:
            raise ValueError("cette photo est au format HEIC (iPhone) et le décodeur HEIC "
                             "n'est pas installé sur le serveur") from e
        raise ValueError("le fichier n'est pas une image lisible") from e
    # Le sens de la prise de vue : une photo de téléphone en portrait reste debout.
    img = ImageOps.exif_transpose(img)
    sortie = io.BytesIO()
    if cible[0] == "JPEG":
        # Pas d'EXIF recopié : la position GPS d'une photo de chantier ne voyage pas.
        img.convert("RGB").save(sortie, "JPEG", quality=int(qualite), optimize=True)
    else:
        img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").save(sortie, "PNG", optimize=True)
    return sortie.getvalue(), cible[1], cible[2]
