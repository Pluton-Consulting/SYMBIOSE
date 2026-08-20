"""
Nano Banana — la génération d'images Gemini, pour ESSAYER avant de payer.

Higgsfield est le tirage final : beau, facturé, validé par un humain. Nano
Banana (les modèles image de Gemini, inclus dans la clé Google déjà en place
pour les embeddings et la vision) est le BANC D'ESSAI : on itère sur le brief
en quelques secondes, et seul le rendu retenu part chez Higgsfield.

L'API rend l'image DANS la réponse (base64), pas une adresse CDN : rien
n'expire, on dépose les octets tels quels.

Vérifié avec la clé réelle : le format d'appel est accepté (les refus étaient
des 429 de quota, pas des 400). Le quota image de Google AI Studio est
journalier et peut exiger la facturation activée : le 429 est donc traduit en
message d'exploitation, jamais en panne.
"""
from __future__ import annotations

import base64
import logging
from typing import Optional

import httpx

logger = logging.getLogger("symbiose.visuels.nano_banana")

BASE = "https://generativelanguage.googleapis.com/v1beta/models"
# Le premier modèle vient du réglage ; les suivants sont des replis connus de
# cette clé (relevés sur son catalogue réel). Un 404 passe au suivant : Google
# retire les anciens modèles aux nouveaux comptes sans préavis.
REPLIS = ("gemini-3.1-flash-image", "gemini-2.5-flash-image")

RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")
DELAI_S = 120.0


class NanoBananaIndisponible(RuntimeError):
    """Clé absente, quota épuisé ou refus de l'API. Jamais la clé dans le message."""


def _cle() -> str:
    from llm.cles import valeur
    cle = (valeur("google_api_key") or "").strip()
    if not cle:
        raise NanoBananaIndisponible(
            "La clé Google n'est pas configurée (Paramètres > Clés API) : "
            "impossible d'essayer un visuel Nano Banana.")
    return cle


def _modeles() -> list[str]:
    from config import settings
    prefere = (getattr(settings, "model_nano_banana", "") or "").strip()
    suite = [m for m in REPLIS if m != prefere]
    return ([prefere] if prefere else []) + suite


async def generer(prompt: str, *, ratio: Optional[str] = None) -> dict:
    """Génère une image et rend ses octets. Lève NanoBananaIndisponible sinon."""
    cle = _cle()
    corps: dict = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    r = (ratio or "").strip()
    if r in RATIOS:
        corps["generationConfig"]["imageConfig"] = {"aspectRatio": r}

    derniere = "aucun modèle essayé"
    async with httpx.AsyncClient(timeout=DELAI_S) as client:
        for modele in _modeles():
            try:
                rep = await client.post(f"{BASE}/{modele}:generateContent",
                                        params={"key": cle}, json=corps)
            except httpx.HTTPError as e:
                derniere = f"{modele} injoignable ({type(e).__name__})"
                continue
            if rep.status_code == 429:
                # Le quota est un état d'exploitation, pas une panne : le dire
                # permet de décider (attendre demain, ou activer la facturation).
                raise NanoBananaIndisponible(
                    "Le quota d'images de la clé Google est épuisé pour "
                    "aujourd'hui (ou la facturation n'est pas activée sur "
                    "Google AI Studio). Réessayez plus tard, ou utilisez "
                    "directement `generer_visuel` (Higgsfield).")
            if rep.status_code == 404:
                derniere = f"{modele} inconnu de cette clé"
                continue
            if rep.status_code in (401, 403):
                raise NanoBananaIndisponible(
                    "Google a refusé la clé (Paramètres > Clés API).")
            if rep.status_code >= 400:
                derniere = f"{modele} : HTTP {rep.status_code}"
                logger.info("Nano Banana %s : %s", modele, rep.text[:200])
                continue

            parts = (rep.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
            images = []
            for p in parts:
                donnee = p.get("inlineData") or p.get("inline_data") or {}
                if donnee.get("data"):
                    try:
                        images.append((base64.b64decode(donnee["data"]),
                                       donnee.get("mimeType") or donnee.get("mime_type") or "image/png"))
                    except Exception:  # noqa: BLE001 - un base64 illisible n'est pas une image
                        continue
            if images:
                logger.info("Nano Banana : %d image(s) via %s", len(images), modele)
                return {"termine": True, "modele": modele, "images": images}
            derniere = f"{modele} : réponse sans image"

    raise NanoBananaIndisponible(f"Aucun modèle image n'a répondu ({derniere}).")


async def disponible() -> bool:
    try:
        _cle()
        return True
    except NanoBananaIndisponible:
        return False
