"""
LE DÉPÔT DES VISUELS GÉNÉRÉS — sur disque, parce qu'un tirage payé ne se perd pas.

Higgsfield rend des adresses d'images sur son CDN, signées et périssables.
Les donner telles quelles au chat, c'est montrer des images qui meurent au
bout de quelques heures — et un rendu FACTURÉ qui disparaît est un rendu payé
deux fois. Chaque image est donc téléchargée UNE fois par le backend, rangée
dans le volume des documents produits (le même qui garde les Word), et servie
par une route authentifiée. Elle survit aux redémarrages, comme le devis
qu'elle illustre.

La clé est un condensé de l'adresse d'origine : re-déposer la même image rend
la même clé, sans doublon sur le disque.
"""
from __future__ import annotations

import hashlib
import logging
import os
import pathlib

import httpx

logger = logging.getLogger("symbiose.visuels.depot")

DOSSIER = pathlib.Path(os.environ.get("DOCUMENTS_DIR", "/tmp/symbiose-documents")) / "visuels"

_MIMES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}
_EXT_PAR_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
MAX_OCTETS = 15 * 1024 * 1024


async def deposer_depuis_url(url: str) -> str | None:
    """Télécharge une image et rend sa clé. None si le téléchargement échoue —
    l'appelant garde alors l'adresse externe, on ne perd jamais le rendu."""
    if not url or not url.startswith("http"):
        return None
    cle = hashlib.sha256(url.split("?")[0].encode("utf-8")).hexdigest()[:24]
    existant = _chemin(cle)
    if existant:
        return cle
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            if len(r.content) > MAX_OCTETS:
                logger.warning("Visuel trop lourd (%d octets), garde en externe", len(r.content))
                return None
            mime = (r.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            ext = _EXT_PAR_MIME.get(mime, ".jpg")
        DOSSIER.mkdir(parents=True, exist_ok=True)
        (DOSSIER / f"{cle}{ext}").write_bytes(r.content)
        logger.info("Visuel déposé : %s (%d Ko)", cle, len(r.content) // 1024)
        return cle
    except Exception as e:  # noqa: BLE001 — un dépôt raté n'annule pas la génération
        logger.warning("Dépôt du visuel impossible (%s)", type(e).__name__)
        return None


def _chemin(cle: str) -> pathlib.Path | None:
    if not cle.isalnum():
        return None
    for ext in _MIMES:
        p = DOSSIER / f"{cle}{ext}"
        if p.exists():
            return p
    return None


def lire(cle: str) -> tuple[bytes, str] | None:
    """(octets, type MIME) d'un visuel déposé, ou None."""
    p = _chemin(cle)
    if not p:
        return None
    return p.read_bytes(), _MIMES.get(p.suffix, "image/jpeg")
