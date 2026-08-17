"""
Skill natif : faire ENTRER les documents du Drive dans la mémoire d'entreprise.

POURQUOI IL EXISTE. Relevé en production : « enrichis au maximum la base de
connaissance, va sur le Drive et lis tous les documents ». L'assistant a
répondu qu'il ne pouvait pas, a proposé `lancer_enrichissement` (qui ne lit que
le courrier) et `retenir` (qui n'écrit pas dans la mémoire mais dans les
consignes de comportement). Il n'avait pas tort sur les gestes qu'il connaissait
— il n'en avait simplement aucun pour ce qu'on lui demandait.

Or la capacité était là depuis le début : `ingestion.connectors.google_drive.sync`
parcourt les périmètres, télécharge chaque fichier et appelle `ingest_document`.
Elle n'était atteignable que par une route HTTP, donc par un écran. Une demande
formulée en français n'avait aucun chemin.

CE QUI EST DÉLIBÉRÉMENT ABSENT : ce module ne réimplémente RIEN. Il appelle
`routers.ingestion.demarrer_sync`, qui porte la ligne `synchronisations`, l'index
unique qui interdit deux campagnes simultanées et la libération des synchros
pendues. Une seconde implémentation serait un second endroit où le verrou
anti-doublon peut manquer.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, status

logger = logging.getLogger("symbiose.ingestion.skills")

PERMISSION = "manage_system"
SOURCE = "google_drive"


async def lancer_ingestion_documents(data: dict, user) -> dict:
    """Démarre l'ingestion du Drive. Ne bloque pas : elle dure longtemps."""
    from security.rbac import has_permission
    from routers.ingestion import demarrer_sync

    role = getattr(user, "role", "")
    if not has_permission(role, PERMISSION):
        # Fail-closed, et le refus n'apprend rien de la configuration : sinon le
        # message deviendrait un moyen de cartographier les droits.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Faire entrer des documents dans la mémoire d'entreprise est "
                   "réservé à l'administration système.")

    # LE CONTRÔLE D'ACCÈS RESTE CELUI DU CONNECTEUR. On ne passe volontairement
    # aucun dossier depuis le modèle : `sync()` sans argument suit les périmètres
    # déclarés en configuration, chacun avec SON niveau d'accès. Laisser le
    # modèle désigner un dossier ouvrirait une ingestion hors périmètre, au
    # niveau le plus large — et ce serait une fuite silencieuse, puisque les
    # documents deviendraient ensuite consultables par la recherche.
    resultat = await demarrer_sync(SOURCE, user)

    return {
        **resultat,
        "message": ("Ingestion du Drive lancée en tâche de fond : chaque document "
                    "des dossiers déclarés est téléchargé, découpé et rangé dans la "
                    "mémoire d'entreprise avec le niveau d'accès de son dossier."),
        "a_savoir": ("Ce geste est le SEUL qui fasse entrer un document en mémoire. "
                     "Les actions `drive_*` ne font que lire pour le tour en cours : "
                     "elles n'enregistrent rien."),
        "duree": "Plusieurs minutes à plusieurs heures selon le volume du Drive.",
        "suivi": "Paramètres, Synchronisations — ou demande-moi où en est l'ingestion.",
    }


async def statut_ingestion_documents(data: dict, user) -> dict:
    """Avancement de l'ingestion du Drive. Lecture seule."""
    from security.rbac import has_permission
    from database.connection import get_db

    if not has_permission(getattr(user, "role", ""), PERMISSION):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Réservé à l'administration système.")

    # LU EN BASE, pas en mémoire : le dictionnaire `_SYNCS` du routeur meurt avec
    # le processus, et après un redémarrage il annoncerait « jamais lancée » sur
    # une campagne qui vient de tourner.
    async with get_db() as conn:
        ligne = await conn.fetchrow(
            "SELECT statut, etape, traites, total, erreur, lance_par_email, "
            "       demarre_a, termine_a "
            "  FROM synchronisations WHERE source = $1 "
            " ORDER BY demarre_a DESC LIMIT 1", SOURCE)

    if not ligne:
        return {"message": "Aucune ingestion du Drive n'a encore été lancée."}
    return {k: v for k, v in dict(ligne).items() if v is not None}
