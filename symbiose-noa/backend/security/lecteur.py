"""
POUR QUI CE GESTE S'EXÉCUTE — le rôle et l'identité de la personne.

POURQUOI UN CONTEXTE ET PAS UN PARAMÈTRE (16/09, audit S-03). Ce qui est déposé
pendant un geste — une photo du chat, une pièce jointe d'un mail, un visuel, une
image tirée d'un Word — appartient à QUELQU'UN. Or les octets traversent une
dizaine de fonctions avant d'atteindre le dépôt (prétraitement, vision,
résolution d'une pièce, insertion dans un document), et aucune ne connaît
l'appelant. Ajouter un paramètre `user` à chacune aurait laissé la première
oubliée déposer un fichier sans propriétaire — donc lisible par un identifiant
deviné.

L'identité est donc posée UNE fois, au goulot par lequel passent tous les skills
(`skills/executor.execute_skill`) et à la préparation des pièces jointes, puis
relue au dépôt (`visuels/depot.noter_proprietaire`). `asyncio.gather` et
`to_thread` copient le contexte : les pièces préparées de front voient la même
personne.

SANS LECTEUR = LE SYSTÈME. Les synchronisations, la carte du classement et les
campagnes d'enrichissement doivent TOUT voir pour tout ranger ; elles ne passent
pas par l'exécuteur de skills, donc n'ont pas de lecteur. Ce qu'elles déposent
n'appartient à personne en particulier — et les routes protégées le disent.

⚠️ Le Drive, lui, se lit avec le compte Google DE LA PERSONNE (règle du 01/09) :
ce module ne remplace pas ce cloisonnement, il porte l'identité là où les octets
sont rangés chez nous.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

_ROLE: ContextVar[Optional[str]] = ContextVar("role_lecteur", default=None)
_ID: ContextVar[Optional[str]] = ContextVar("id_lecteur", default=None)


def role_lecteur() -> Optional[str]:
    """Le rôle de la personne pour qui l'on agit, ou None (le système)."""
    return _ROLE.get()


def id_lecteur() -> Optional[str]:
    """L'identifiant de la personne pour qui l'on agit, ou None (le système)."""
    return _ID.get()


@contextmanager
def en_systeme():
    """Le temps d'un traitement commun (carte du classement, synchronisation),
    AUCUN lecteur.

    Une tâche lancée depuis un geste hérite du contexte de ce geste : ce qu'elle
    dépose porterait alors le nom de la personne qui a déclenché le geste, alors
    que le résultat est servi à tout le monde.
    """
    jeton, jeton_id = _ROLE.set(None), _ID.set(None)
    try:
        yield
    finally:
        _ROLE.reset(jeton)
        _ID.reset(jeton_id)


@contextmanager
def au_nom_de(user):
    """Le temps d'un geste, ce qui est déposé appartient à `user`.

    Un utilisateur sans rôle lisible obtient une chaîne vide, pas None : il
    reste une PERSONNE (droits les plus faibles), jamais le système.
    """
    jeton = _ROLE.set(str(getattr(user, "role", "") or ""))
    jeton_id = _ID.set(str(getattr(user, "id", "") or "") or None)
    try:
        yield
    finally:
        _ROLE.reset(jeton)
        _ID.reset(jeton_id)
