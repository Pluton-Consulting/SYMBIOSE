"""
Niveau de confidentialité RÉEL d'un document du socle — côté Google Drive.

LA QUESTION POSÉE. La campagne documentaire (`enrichissement_docs.py`) doit
savoir, pour chaque fichier, QUI a le droit de le voir : une connaissance
tirée d'un fichier partagé avec toute l'entreprise peut être servie à tous,
une connaissance tirée d'un fichier que seule la direction ouvre ne doit
ressortir qu'à elle. La vérité vit dans les PARTAGES du Drive — les adresses
e-mail qui ont accès au fichier — pas dans un réglage global.

LA TRADUCTION. Les partages parlent en adresses ; l'application parle en
niveaux (`security/acces.py`). Le pont : l'annuaire des comptes de
l'application (adresse → rôle). Le niveau retenu est LE PLUS OUVERT dont
l'audience tient toute entière dans les rôles qui ont réellement accès au
fichier — direction et super_admin mis à part, puisqu'ils voient tout de
toute façon. Une adresse externe (client, partenaire) n'élargit RIEN : le
partage sortant d'un fichier ne dit pas qui, en interne, doit le voir.

LECTURE SEULE, ET FAIL-CLOSED. Un seul appel par fichier
(`permissions.list`, couvert par le scope de lecture existant), mis en cache.
Fichier disparu, partage illisible, aucun compte interne reconnu : on rend
`None` ou le plus restrictif — une erreur ne doit jamais OUVRIR un accès.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger("symbiose.learning.acces_docs")

# Un partage « toute l'organisation » ou « toute personne ayant le lien » :
# le fichier est public à l'échelle de la maison.
_TYPES_PUBLICS = ("domain", "anyone")

_CACHE: dict[str, str | None] = {}
_ANNUAIRE: dict = {"emails": None, "expire": 0.0}


def niveau_pour_roles(roles) -> str:
    """Le niveau LE PLUS OUVERT dont l'audience est couverte par ces rôles.

    Direction et super_admin sont hors du calcul : ils voient tous les
    niveaux, leur présence dans un partage ne dit rien de son ouverture.
    """
    from security.acces import ROLE_ACCESS_LEVELS

    # RÈGLE STRICTE, choisie contre la fuite : le niveau n'est accordé que si
    # TOUS ceux qu'il rend lecteurs ont réellement accès au fichier. Un fichier
    # partagé avec le seul commercial ne devient pas « commercial_plus » — ce
    # niveau ouvrirait aussi aux conducteurs et au bureau d'études, qui n'ont
    # pas le partage. La connaissance retombe alors en direction seule ; le
    # document lui-même reste trouvable par la recherche, à son propre niveau.
    toujours = {"super_admin", "direction"}
    presents = set(roles) - toujours
    for niveau in ("all", "commercial_plus", "bureau_etudes_plus"):
        audience = {r for r, vus in ROLE_ACCESS_LEVELS.items() if niveau in vus}
        if audience - toujours <= presents:
            return niveau
    return "direction_only"


def niveau_depuis_permissions(permissions, annuaire: dict) -> str | None:
    """Traduit une liste de partages Drive en niveau — ou avoue ne pas savoir.

    `annuaire` : adresse e-mail (minuscules) → rôle applicatif. Un GROUPE non
    résolu n'élargit pas l'accès (on ne sait pas qui est dedans) ; une adresse
    inconnue de l'annuaire non plus (externe).

    AUCUN COMPTE INTERNE RECONNU → `None`, PAS « direction seule ». La leçon
    est de production (30/08, premier lancement) : Drive ne montre la liste
    complète des partages qu'aux propriétaires et éditeurs — un compte de
    synchronisation simple LECTEUR ne voit que sa propre entrée. La première
    version classait alors « le plus restrictif », et les 430 documents sont
    TOUS partis en direction seule : sûr, et inutilisable. Ne rien reconnaître
    n'est pas une information sur le fichier, c'est une information sur notre
    POINT DE VUE : on rend la main, et le niveau stocké à l'ingestion (réglé
    par périmètre) fait foi. « Direction seule » ne se prononce que sur une
    identification POSITIVE — des comptes internes vus, et seulement eux.
    """
    roles = set()
    for p in permissions or []:
        if not isinstance(p, dict):
            continue
        if p.get("type") in _TYPES_PUBLICS:
            return "all"
        adresse = str(p.get("emailAddress") or "").strip().lower()
        if adresse and adresse in annuaire:
            roles.add(annuaire[adresse])
    if not roles:
        return None
    return niveau_pour_roles(roles)


async def _annuaire() -> dict:
    """Adresse → rôle des comptes ACTIFS de l'application, en cache 10 min."""
    if _ANNUAIRE["emails"] is not None and time.monotonic() < _ANNUAIRE["expire"]:
        return _ANNUAIRE["emails"]
    from database.connection import get_db
    async with get_db() as conn:
        lignes = await conn.fetch(
            "SELECT email, role FROM users WHERE actif = true")
    _ANNUAIRE["emails"] = {str(l["email"]).strip().lower(): str(l["role"] or "").strip()
                           for l in lignes if l["email"]}
    _ANNUAIRE["expire"] = time.monotonic() + 600
    return _ANNUAIRE["emails"]


async def niveau_reel(source_id: str, source_type: str) -> str | None:
    """Le niveau réel d'un fichier Drive, ou None si on ne sait pas dire.

    `None` rend la main à l'appelant, qui retombe sur le niveau stocké à
    l'ingestion : ne pas savoir n'est pas une information.
    """
    if source_type != "drive" or not source_id:
        return None
    if source_id in _CACHE:
        return _CACHE[source_id]

    try:
        from outils.drive import _service
        service = await _service()

        def _appel():
            return service.permissions().list(
                fileId=source_id,
                fields="permissions(type,emailAddress,role)",
                supportsAllDrives=True,
            ).execute()

        reponse = await asyncio.to_thread(_appel)
        niveau = niveau_depuis_permissions(reponse.get("permissions") or [],
                                           await _annuaire())
    except Exception as e:  # noqa: BLE001 — fichier disparu, droit refusé : on ne sait pas
        logger.info("Partages de %s illisibles : %s", source_id[:12], str(e)[:120])
        niveau = None
    _CACHE[source_id] = niveau
    return niveau
