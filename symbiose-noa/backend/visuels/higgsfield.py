"""
Client Higgsfield — génération de visuels paysagers (§6 du cahier des charges).

CONTRAT, relevé sur la documentation de l'éditeur et non deviné :
  * base            https://platform.higgsfield.ai
  * authentification  en-tête `Authorization: Key <clé>:<secret>` — DEUX valeurs,
                    pas une ; une clé seule ne suffit pas.
  * soumission      POST /higgsfield-ai/soul/standard
                    {"prompt": ..., "aspect_ratio": ..., "resolution": ...}
                    -> rend un `request_id` et un statut `queued`
  * suivi           GET /requests/{request_id}/status
                    queued -> in_progress -> completed, puis `images[].url`

CE QUI N'EST PAS FAIT, ET POURQUOI. La transformation d'une PHOTO existante
(simulation avant/après, variantes sur un terrain réel) n'est pas implémentée :
la documentation publique ne décrit pas le paramètre d'image d'entrée. Coder
contre une API supposée produirait un échec silencieux au premier appel réel,
facturé. Le client est structuré pour l'accueillir dès que le champ est confirmé
auprès de l'éditeur.

COÛT. Chaque appel est facturé à l'usage. C'est pourquoi le skill qui s'appuie
sur ce client est déclaré à effet EXTERNE : il passe par la validation humaine
avant de partir, comme toute action engageante. Le §9 le demande explicitement,
et une génération lancée par erreur ne se rembourse pas.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger("symbiose.visuels.higgsfield")

BASE = "https://platform.higgsfield.ai"
CHEMIN_GENERATION = "/higgsfield-ai/soul/standard"

# Formats proposés. Bornés à dessein : un format libre laisserait passer des
# valeurs que l'API refuse, et l'erreur reviendrait après facturation.
RATIOS = ("16:9", "9:16", "1:1", "4:3", "3:4")
RESOLUTIONS = ("720p", "1080p")

DELAI_APPEL_S = 30.0
# Une génération prend de quelques secondes à quelques minutes. On borne pour
# ne pas retenir une requête indéfiniment si l'éditeur ne répond plus.
ATTENTE_MAX_S = 300
PAUSE_SUIVI_S = 3.0


class HiggsfieldIndisponible(RuntimeError):
    """Panne, clé absente ou refus de l'éditeur. Jamais la clé dans le message."""


def _entetes() -> dict[str, str]:
    """En-tête d'authentification. Lève si les DEUX valeurs ne sont pas là."""
    from llm.cles import valeur

    cle = (valeur("higgsfield_api_key") or "").strip()
    secret = (valeur("higgsfield_api_secret") or "").strip()
    if not cle or not secret:
        manquant = "clé" if not cle else "secret"
        raise HiggsfieldIndisponible(
            f"Higgsfield n'est pas configuré : {manquant} d'API absent. "
            "Renseignez les deux valeurs dans Paramètres > Clés API.")
    return {"Authorization": f"Key {cle}:{secret}",
            "Content-Type": "application/json"}


def _brider(valeur_demandee: Optional[str], permises: tuple, defaut: str) -> str:
    v = (valeur_demandee or "").strip()
    return v if v in permises else defaut


async def generer(prompt: str, *, ratio: Optional[str] = None,
                  resolution: Optional[str] = None) -> dict:
    """Lance une génération et attend l'image. Rend l'URL et le coût connu.

    Ne journalise ni la clé ni le secret. Le prompt est journalisé tronqué :
    il décrit un aménagement, pas une personne, mais rien ne garantit qu'un
    nom de client ne s'y glisse pas.
    """
    import httpx

    texte = (prompt or "").strip()
    if not texte:
        raise HiggsfieldIndisponible("Aucune description fournie pour le visuel.")

    corps = {
        "prompt": texte,
        "aspect_ratio": _brider(ratio, RATIOS, "16:9"),
        "resolution": _brider(resolution, RESOLUTIONS, "720p"),
    }

    entetes = _entetes()
    logger.info("Higgsfield : génération demandée (%s, %s, %d caractères)",
                corps["aspect_ratio"], corps["resolution"], len(texte))

    async with httpx.AsyncClient(timeout=DELAI_APPEL_S) as client:
        try:
            depart = await client.post(BASE + CHEMIN_GENERATION,
                                       json=corps, headers=entetes)
        except httpx.HTTPError as e:
            raise HiggsfieldIndisponible(f"Higgsfield injoignable : {e}") from e

        if depart.status_code in (401, 403):
            raise HiggsfieldIndisponible(
                "Higgsfield a refusé les identifiants. Vérifiez la clé ET le "
                "secret dans Paramètres > Clés API.")
        if depart.status_code >= 400:
            raise HiggsfieldIndisponible(
                f"Higgsfield a refusé la demande ({depart.status_code}). "
                f"{depart.text[:200]}")

        demande = depart.json()
        identifiant = demande.get("request_id") or demande.get("id")
        if not identifiant:
            raise HiggsfieldIndisponible(
                "Higgsfield n'a pas rendu d'identifiant de demande.")

        # SUIVI. La génération est déjà lancée et donc déjà facturée : au-delà
        # du délai, on rend l'identifiant plutôt que de laisser croire à un
        # échec — l'image existera, elle sera simplement à récupérer plus tard.
        limite = asyncio.get_event_loop().time() + ATTENTE_MAX_S
        etat = str(demande.get("status") or "queued")
        while asyncio.get_event_loop().time() < limite:
            if etat == "completed":
                break
            if etat in ("failed", "canceled", "cancelled"):
                raise HiggsfieldIndisponible(
                    f"La génération s'est arrêtée (statut « {etat} »).")
            await asyncio.sleep(PAUSE_SUIVI_S)
            try:
                suivi = await client.get(f"{BASE}/requests/{identifiant}/status",
                                         headers=entetes)
                if suivi.status_code >= 400:
                    continue
                demande = suivi.json()
                etat = str(demande.get("status") or etat)
            except httpx.HTTPError:
                continue        # un accroc réseau ne doit pas annuler l'attente

        if etat != "completed":
            return {"termine": False, "request_id": identifiant, "statut": etat,
                    "message": ("La génération est lancée mais pas encore terminée "
                                f"(statut « {etat} »). Elle sera facturée : ne la "
                                "relance pas, récupère-la avec cet identifiant.")}

        images = [i.get("url") for i in (demande.get("images") or []) if i.get("url")]
        if not images:
            raise HiggsfieldIndisponible(
                "Higgsfield annonce la génération terminée mais ne rend aucune image.")

        logger.info("Higgsfield : %d image(s) rendue(s) pour %s", len(images), identifiant)
        return {"termine": True, "request_id": identifiant, "images": images,
                "format": corps["aspect_ratio"], "resolution": corps["resolution"]}


async def disponible() -> bool:
    """Les deux identifiants sont-ils renseignés ? N'appelle pas l'éditeur."""
    try:
        _entetes()
        return True
    except HiggsfieldIndisponible:
        return False
