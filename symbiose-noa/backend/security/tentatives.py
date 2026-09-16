"""
LES ESSAIS RATÉS, COMPTÉS PAR ORIGINE (16/09, audit S-19).

Deux portes s'ouvrent sans mot de passe : la demande de lien de connexion et sa
vérification. Aucune des deux n'était bornée. Demander mille liens à mille
adresses coûte mille mails partis de notre domaine (et notre réputation
d'expéditeur avec) ; essayer des jetons au hasard ne coûtait rien non plus.

Trois principes, parce qu'une borne mal posée fait plus de mal que de bien :
  * c'est une borne d'ORIGINE, jamais de compte — bloquer une personne parce
    qu'un inconnu a tapé son adresse serait une façon commode de l'exclure ;
  * seuls les essais RATÉS comptent : entrer normalement, même souvent (un
    poste partagé par toute l'équipe, derrière la même adresse sortante), ne
    bloque personne ;
  * la fenêtre s'oublie seule et la mémoire est bornée : elle vit dans le
    processus, se perd au redémarrage, et ne remplace pas le VPN qui fait la
    porte — elle ralentit, elle ne protège pas à elle seule.

⚠️ LA RÉPONSE NE CHANGE PAS QUAND LA BORNE MORD. Dire « trop d'essais » à qui
tape une adresse inconnue lui apprendrait que les autres existent : la demande
de lien répond toujours la même chose, on cesse simplement d'envoyer.
"""
from __future__ import annotations

import time

ESSAIS_MAX = 30
FENETRE_S = 900
MAX_ORIGINES = 5000

_ESSAIS: dict[str, list[float]] = {}


def origine_de(entete_transmis: str = "", hote: str = "") -> str:
    """L'origine d'une demande : la première adresse de `X-Forwarded-For`
    (nginx la pose), sinon l'adresse de la connexion."""
    premiere = (entete_transmis or "").split(",")[0].strip()
    return premiere or (hote or "").strip() or "inconnue"


def _recents(origine: str, maintenant: float) -> list:
    recents = [t for t in _ESSAIS.get(origine, []) if maintenant - t < FENETRE_S]
    if recents:
        _ESSAIS[origine] = recents
    else:
        _ESSAIS.pop(origine, None)
    return recents


def saturee(origine: str, maintenant: float | None = None) -> bool:
    """Cette origine a-t-elle épuisé ses essais ratés ?"""
    return len(_recents(origine, maintenant or time.time())) >= ESSAIS_MAX


def noter_echec(origine: str, maintenant: float | None = None) -> int:
    """Compte un essai RATÉ et rend le nombre d'essais retenus."""
    maintenant = maintenant or time.time()
    recents = _recents(origine, maintenant)
    recents.append(maintenant)
    _ESSAIS[origine] = recents
    if len(_ESSAIS) > MAX_ORIGINES:      # une mémoire d'appoint ne grossit pas sans fin
        _ESSAIS.clear()
        _ESSAIS[origine] = recents
    return len(recents)


def oublier(origine: str) -> None:
    """Efface les essais d'une origine (une entrée réussie n'a rien à traîner)."""
    _ESSAIS.pop(origine, None)
