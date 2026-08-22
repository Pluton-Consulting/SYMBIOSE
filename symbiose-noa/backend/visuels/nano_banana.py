"""
Nano Banana — LA génération d'images du projet. Un seul moteur, deux usages.

Higgsfield a été retiré (22/08/2026) : deux fournisseurs pour une même chose,
c'était deux jeux d'identifiants, deux formats de réponse, deux pannes
possibles, et un tirage final qu'on n'a jamais réussi à payer. Tout passe
désormais par l'API Google directe, avec la clé déjà en place pour les
embeddings et la vision.

TROIS GESTES, UN SEUL APPEL RÉSEAU DERRIÈRE :
  · l'ESSAI          — modèle rapide, replis autorisés, on itère ;
  · le TIRAGE FINAL  — Nano Banana Pro EXIGÉ, aucun repli : un rendu montré au
                       client ne doit pas sortir en douce d'un modèle moindre ;
  · la RETOUCHE      — une image d'entrée + ce qu'on veut changer.

LA RETOUCHE EST LE VRAI SUJET. Donner une photo de maison et demander « la même,
avec une terrasse en ipé à la place de la pelouse » n'est pas une génération :
c'est une ÉDITION. Le modèle reçoit l'image dans la requête (`inlineData`) et
non une description d'elle — c'est la seule façon de retrouver la MÊME maison.
Le préréglage de fidélité (`skills/visuels.py`) fait le reste du travail.

L'API rend l'image DANS la réponse (base64), pas une adresse CDN : rien
n'expire, on dépose les octets tels quels.

Le quota image de Google est journalier et exige la facturation activée sur LE
projet de la clé : le 429 est donc traduit en message d'exploitation, jamais en
panne — et il dit LEQUEL des deux cas c'est.
"""
from __future__ import annotations

import base64
import logging
import time
from typing import Iterable, Optional

import httpx

logger = logging.getLogger("symbiose.visuels.nano_banana")

BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Le modèle de tête vient du réglage `model_nano_banana`. Les replis sont des
# modèles connus de cette clé : un 404 passe au suivant, Google retirant les
# anciens modèles aux nouveaux comptes sans préavis.
PRO = "nano-banana-pro-preview"
REPLIS = ("gemini-3.1-flash-image", "gemini-2.5-flash-image")

RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")
# Conservées pour l'interface du skill : Google ne prend pas de hauteur en
# paramètre, mais la résolution demandée est reportée dans le brief, où elle
# oriente le rendu (« 4K », « ultra-detailed »).
RESOLUTIONS = ("720p", "1080p", "2k", "4k")
DELAI_S = 180.0

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
            "impossible de produire un visuel.")
    return cle


def _modeles(qualite: str) -> list[str]:
    """La liste des modèles à essayer, dans l'ordre.

    En qualité `finale`, la liste ne contient QUE Nano Banana Pro : mieux vaut
    un échec explicite qu'un tirage présenté au client comme le rendu final
    alors qu'il sort d'un modèle rapide. En qualité `essai`, les replis sont
    au contraire souhaitables — l'important est d'itérer.
    """
    from config import settings
    prefere = (getattr(settings, "model_nano_banana", "") or "").strip() or PRO
    if qualite == "finale":
        return [prefere] if prefere else [PRO]
    return [prefere] + [m for m in REPLIS if m != prefere]


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
                "(palier gratuit), où la génération d'images est quasi inaccessible. "
                "Recharger des crédits ailleurs n'y change rien : il faut "
                "activer la facturation sur LE projet de cette clé "
                "(console.cloud.google.com > Facturation), ou créer une clé "
                "dans un projet facturé et la coller dans Paramètres > Clés API.")
    return ("Le quota d'images de la clé Google est épuisé pour l'instant. "
            "Réessayez plus tard — le quota est journalier.")


async def generer(prompt: str, *,
                  ratio: Optional[str] = None,
                  images_entree: Optional[Iterable[tuple[bytes, str]]] = None,
                  qualite: str = "essai") -> dict:
    """Génère (ou RETOUCHE) une image et rend ses octets.

    `images_entree` : des couples (octets, mime) placés AVANT le texte dans la
    requête. L'ordre compte — l'API lit les parties dans l'ordre donné, et une
    consigne qui précède son image porte moins bien qu'une image suivie de sa
    consigne. Lève NanoBananaIndisponible en cas de refus.
    """
    cle = _cle()
    if time.monotonic() < _bloque_jusqua:
        # Refroidissement : même réponse, zéro appel réseau.
        raise NanoBananaIndisponible(_dernier_message or
                                     "Le quota d'images vient d'être refusé : réessayez dans quelques minutes.")

    parts: list[dict] = []
    n_entrees = 0
    for octets, mime in (images_entree or []):
        parts.append({"inlineData": {"mimeType": mime or "image/jpeg",
                                     "data": base64.b64encode(octets).decode()}})
        n_entrees += 1
    parts.append({"text": prompt})

    corps: dict = {
        "contents": [{"parts": parts}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    r = (ratio or "").strip()
    # SUR UNE RETOUCHE, ON N'IMPOSE PAS DE RATIO. Forcer un cadre recadre ou
    # étire la photo d'origine, et la « même maison » cesse d'être la même.
    if r in RATIOS and not n_entrees:
        corps["generationConfig"]["imageConfig"] = {"aspectRatio": r}

    derniere = "aucun modèle essayé"
    async with httpx.AsyncClient(timeout=DELAI_S) as client:
        for modele in _modeles(qualite):
            try:
                rep = await client.post(f"{BASE}/{modele}:generateContent",
                                        params={"key": cle}, json=corps)
            except httpx.HTTPError as e:
                derniere = f"{modele} injoignable ({type(e).__name__})"
                continue
            if rep.status_code == 429:
                # Le quota est un état d'exploitation, pas une panne — et le
                # DÉTAIL du refus dit lequel : des violations « FreeTier »
                # signifient que la clé vit sur un projet SANS facturation.
                # Le dire ainsi évite de « recharger des crédits » au mauvais
                # endroit — relevé en production, mot pour mot.
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

            contenu = (rep.json().get("candidates") or [{}])[0].get("content", {})
            images = []
            for p in contenu.get("parts", []):
                donnee = p.get("inlineData") or p.get("inline_data") or {}
                if donnee.get("data"):
                    try:
                        images.append((base64.b64decode(donnee["data"]),
                                       donnee.get("mimeType") or donnee.get("mime_type") or "image/png"))
                    except Exception:  # noqa: BLE001 - un base64 illisible n'est pas une image
                        continue
            if images:
                logger.info("Nano Banana : %d image(s) via %s (%d entrée(s), qualité %s)",
                            len(images), modele, n_entrees, qualite)
                return {"termine": True, "modele": modele, "images": images,
                        "retouche": bool(n_entrees)}
            derniere = f"{modele} : réponse sans image"

    if qualite == "finale":
        raise NanoBananaIndisponible(
            f"Le tirage final exige le meilleur moteur d'images, qui n'a pas répondu ({derniere}). "
            "Aucun repli n'est tenté à dessein : un rendu montré au client ne doit pas "
            "sortir d'un modèle plus faible sans que personne ne le sache. "
            "Réessayez, ou repassez par `tester_visuel` en attendant.")
    raise NanoBananaIndisponible(f"Aucun modèle image n'a répondu ({derniere}).")


async def disponible() -> bool:
    try:
        _cle()
        return True
    except NanoBananaIndisponible:
        return False
