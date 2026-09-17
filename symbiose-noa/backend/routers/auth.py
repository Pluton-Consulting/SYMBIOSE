import logging
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from database.connection import get_db
from auth import appareil
from auth.jwt_handler import create_access_token, decode_access_token
from auth.dependencies import get_current_user
from database.models import User
from security.audit import log_action
from security import tentatives

logger = logging.getLogger("symbiose.auth")

_bearer = HTTPBearer()

router = APIRouter()

class ConnexionEmailRequest(BaseModel):
    email: str


class RefreshRequest(BaseModel):
    """Le jeton d'appareil posé lors de la dernière connexion."""
    refresh_token: str


class LogoutRequest(BaseModel):
    """`refresh_token` optionnel : sans lui, seul le JWT courant est révoqué et
    l'appareil resterait connecté au rechargement — ce serait un mensonge
    d'écran (« Fermer la session sur cet appareil »)."""
    refresh_token: str | None = None


@router.post("/connexion/email")
async def connexion_email(body: ConnexionEmailRequest, request: Request):
    """Entrée par adresse seule, demandée explicitement par le propriétaire.

    Ce mode temporaire ne prouve pas la possession de la boîte mail. Il garde
    les comptes, rôles et sessions existants ; il ne crée aucun utilisateur.
    Le futur code devra être vérifié ici avant toute émission de session.
    """
    origine = "email:" + tentatives.origine_de(
        request.headers.get("x-forwarded-for", ""), getattr(request.client, "host", ""))
    if tentatives.saturee(origine):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail="Connexion impossible. Réessayez plus tard.")
    email = str(body.email).strip().lower()
    async with get_db() as conn:
        comptes = await conn.fetch(
            "SELECT * FROM users WHERE lower(trim(email)) = $1 AND actif = true LIMIT 2", email)
    # Refuser une adresse ambiguë plutôt que choisir arbitrairement un rôle.
    if len(comptes) != 1:
        tentatives.noter_echec(origine)
        await log_action(action="login_attempt_unknown", success=False,
                         error_message="Compte absent, inactif ou ambigu")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Accès non autorisé")
    user = comptes[0]
    tentatives.oublier(origine)
    async with get_db() as conn:
        await conn.execute("UPDATE users SET last_login = $1 WHERE id = $2",
                           datetime.now(timezone.utc), user["id"])
    await log_action(action="login_email", user_id=str(user["id"]))
    access_token = create_access_token({"sub": str(user["id"]), "role": user["role"]})
    jeton_appareil = await appareil.creer(user["id"], request.headers.get("user-agent", ""))
    return {"id": str(user["id"]), "email": user["email"], "access_token": access_token,
            "token_type": "bearer", "role": user["role"], "refresh_token": jeton_appareil}


@router.post("/magic-link/request")
@router.post("/magic-link/verify")
@router.post("/magic-link/etat")
async def lien_magique_retire():
    raise HTTPException(status_code=status.HTTP_410_GONE,
                        detail="Saisissez votre adresse sur la page de connexion.")


@router.post("/refresh")
async def refresh_session(body: RefreshRequest):
    """Échange le jeton d'appareil contre un JWT frais — sans mail, sans clic.

    Appelée par le navigateur dès que le JWT approche de son terme. Un refus
    ne dit pas POURQUOI (session inconnue, révoquée, échue, compte désactivé) :
    à qui présente un jeton, on répond « reconnectez-vous », pas un diagnostic.
    """
    compte = await appareil.compte_de(body.refresh_token)
    if compte is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session close : reconnectez-vous.",
        )
    access_token = create_access_token({"sub": str(compte["user_id"]), "role": compte["role"]})
    return {"access_token": access_token, "token_type": "bearer", "role": compte["role"]}


@router.post("/appareils/fermer-jeton")
async def fermer_par_jeton(body: RefreshRequest):
    """Ferme la session de CET appareil sur présentation de son propre jeton.

    POURQUOI SANS JWT. C'est la route qu'appelle « Se déconnecter ». Or on se
    déconnecte souvent d'un onglet dont le JWT a déjà expiré : exiger un JWT
    valide laisserait alors l'appareil se reconnecter tout seul à la page
    suivante — le bouton mentirait. Le jeton d'appareil EST la preuve, et le
    pire qu'en fasse quelqu'un qui l'aurait volé est de nous déconnecter.
    """
    ferme = await appareil.revoquer(body.refresh_token)
    return {"ok": ferme}


@router.get("/appareils")
async def lister_appareils(current_user: User = Depends(get_current_user)):
    """Les appareils qui restent connectés à SON compte.

    La contrepartie d'une session qui ne périme pas : on ne peut l'accepter que
    si l'on voit ce qui est ouvert, et que l'on peut le fermer. `disponible:
    false` dit « je ne peux pas le savoir » (migration absente) — ce n'est pas
    « aucun appareil ».
    """
    appareils = await appareil.lister(current_user.id)
    if appareils is None:
        return {"disponible": False, "appareils": [], "migration_absente": appareil.MIGRATION}
    return {"disponible": True, "appareils": appareils}


@router.delete("/appareils/{session_id}")
async def fermer_appareil(session_id: UUID, current_user: User = Depends(get_current_user)):
    """Ferme UN appareil de son propre compte."""
    ferme = await appareil.revoquer_une(current_user.id, session_id)
    if ferme:
        await log_action(action="session_appareil_fermee", user_id=str(current_user.id))
    return {"ok": ferme}


@router.post("/appareils/tout-fermer")
async def fermer_tous_les_appareils(current_user: User = Depends(get_current_user)):
    """Ferme TOUS ses appareils — le geste d'un poste perdu ou d'un doute."""
    combien = await appareil.revoquer_tout(current_user.id)
    await log_action(action="sessions_appareil_toutes_fermees", user_id=str(current_user.id))
    return {"ok": True, "fermes": combien}


@router.post("/logout")
async def logout(
    body: LogoutRequest | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    current_user: User = Depends(get_current_user),
):
    """Révoque le JWT actuel — inscrit le jti en blacklist jusqu'à expiration —
    ET ferme la session durable de cet appareil (03/09).

    Les deux vont ensemble : révoquer le seul JWT laisserait l'appareil se
    reconnecter tout seul à la page suivante.
    """
    if body and body.refresh_token:
        await appareil.revoquer(body.refresh_token)
    try:
        payload = decode_access_token(credentials.credentials)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            async with get_db() as conn:
                await conn.execute(
                    """INSERT INTO revoked_tokens (jti, user_id, expires_at)
                       VALUES ($1, $2, to_timestamp($3))
                       ON CONFLICT DO NOTHING""",
                    UUID(jti), current_user.id, float(exp),
                )
    except Exception:
        pass  # Toujours renvoyer OK même si l'inscription blacklist échoue

    await log_action(action="logout", user_id=str(current_user.id))
    return {"ok": True}
