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
import time
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

# APRES UN 429, ON SE TAIT DEUX MINUTES. Releve en production : le modele a
# rappele `tester_visuel` une quarantaine de fois dans le MEME tour en variant
# le brief, esperant que le quota revienne — il ne revient pas a cette
# echelle. Le refroidissement rend la meme reponse sans toucher l'API, et le
# message porte la consigne d'arreter.
_REFROIDISSEMENT_S = 120.0
_bloque_jusqua = 0.0
_dernier_message = ""


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


def _marquer_blocage(message: str) -> str:
    """Retient le refus deux minutes : les appels suivants rendent la même
    réponse sans toucher l'API."""
    global _bloque_jusqua, _dernier_message
    _bloque_jusqua = time.monotonic() + _REFROIDISSEMENT_S
    _dernier_message = message
    return message


def _diagnostic_429(rep) -> str:
    """Le 429 traduit en cause actionnable, à partir des violations de quota."""
    try:
        details = rep.json().get("error", {}).get("details", [])
    except Exception:  # noqa: BLE001
        details = []
    ids = " ".join(v.get("quotaId", "")
                   for d in details if "QuotaFailure" in str(d.get("@type", ""))
                   for v in d.get("violations", []))
    if "FreeTier" in ids:
        return ("La clé Google utilisée est sur un projet SANS facturation "
                "(palier gratuit), où Nano Banana Pro est quasi inaccessible. "
                "Recharger des crédits ailleurs n'y change rien : il faut "
                "activer la facturation sur LE projet de cette clé "
                "(console.cloud.google.com > Facturation), ou créer une clé "
                "dans un projet facturé et la coller dans Paramètres > Clés "
                "API. En attendant : `generer_visuel` (Higgsfield).")
    return ("Le quota d'images de la clé Google est épuisé. Réessayez plus "
            "tard, ou utilisez directement `generer_visuel` (Higgsfield).")


async def generer(prompt: str, *, ratio: Optional[str] = None) -> dict:
    """Génère une image et rend ses octets. Lève NanoBananaIndisponible sinon."""
    cle = _cle()
    if time.monotonic() < _bloque_jusqua:
        # Refroidissement : même réponse, zéro appel réseau.
        raise NanoBananaIndisponible(_dernier_message or
                                     "Le quota d'images vient d'être refusé : réessayez dans quelques minutes.")
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
                # Le quota est un état d'exploitation, pas une panne — et le
                # DÉTAIL du refus dit lequel : des violations « FreeTier »
                # signifient que la clé vit sur un projet SANS facturation,
                # où Nano Banana Pro est quasi inaccessible. Le dire ainsi
                # évite de « recharger des crédits » au mauvais endroit —
                # relevé en production, mot pour mot.
                raise NanoBananaIndisponible(_marquer_blocage(_diagnostic_429(rep)))
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
