"""
Connecteur Google Drive (API v3, lecture seule) — voie API directe.

Alternative RECOMMANDÉE : Make.com (connecteur natif, OAuth géré par Make) qui POST
vers /api/ingestion/webhook — aucune app à créer. Voir SETUP_CONNECTEURS.md.

Voie directe (ce module) — prérequis :
  1. Projet Google Cloud + API Drive activée.
  2. Client OAuth « Desktop » → déposer le JSON dans settings.google_credentials_file.
  3. 1er consentement interactif (hors Docker) → génère settings.google_token_file (refresh token).
"""
import logging
from typing import Optional

from config import settings
from ingestion.pipeline import ingest_document

logger = logging.getLogger("symbiose.ingestion.gdrive")

_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
# Documents natifs Google → export vers un format texte lisible.
_EXPORTABLE = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


def _build_service():
    import os
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    # 1. COMPTE DE SERVICE, s'il est depose. Aucun consentement humain, aucun
    #    jeton a renouveler : l'application s'authentifie seule. C'est la seule
    #    voie tenable pour un Drive d'entreprise — l'alternative obligerait
    #    chaque personne a se connecter a Google, et le jeton obtenu
    #    n'appartiendrait qu'a elle.
    if os.path.exists(settings.google_service_account_file):
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(
            settings.google_service_account_file, scopes=_SCOPES)
        sujet = (settings.google_admin_subject or "").strip()
        if sujet:
            # Delegation a l'echelle du domaine : on AGIT AU NOM de ce compte.
            # Ne sert qu'aux « Mon Drive » individuels ; pour un Drive PARTAGE,
            # ajouter le compte de service comme membre suffit, et c'est moins
            # de pouvoir accorde.
            creds = creds.with_subject(sujet)
        logger.info("Google Drive : compte de service%s",
                    f" (au nom de {sujet})" if sujet else " (Drive partages)")
        return build("drive", "v3", credentials=creds)

    # 2. Sinon, consentement OAuth d'un utilisateur (voie historique).
    if not os.path.exists(settings.google_credentials_file):
        raise NotImplementedError(
            "Google Drive non configuré. Deux voies : "
            "1. RECOMMANDÉ pour un Drive d'entreprise — déposer la clé d'un compte "
            f"de service dans {settings.google_service_account_file} : personne "
            "n'a alors à se connecter à Google. "
            f"2. Client OAuth dans {settings.google_credentials_file}, avec un "
            "consentement interactif (scripts/google_consentement.py).")

    creds = None
    if os.path.exists(settings.google_token_file):
        creds = Credentials.from_authorized_user_file(settings.google_token_file, _SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(settings.google_credentials_file, _SCOPES)
            creds = flow.run_local_server(port=0)  # ⚠ interactif : à lancer une fois hors conteneur
        os.makedirs(os.path.dirname(settings.google_token_file) or ".", exist_ok=True)
        with open(settings.google_token_file, "w") as f:
            f.write(creds.to_json())
    return build("drive", "v3", credentials=creds)


def _download_text(service, f) -> Optional[str]:
    mime, name = f["mimeType"], f["name"]
    try:
        if mime in _EXPORTABLE:
            data = service.files().export(fileId=f["id"], mimeType=_EXPORTABLE[mime]).execute()
            return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)

        if mime == "application/pdf" or name.lower().endswith(".pdf"):
            import io
            import pdfplumber
            from googleapiclient.http import MediaIoBaseDownload
            buf = io.BytesIO()
            dl = MediaIoBaseDownload(buf, service.files().get_media(fileId=f["id"]))
            done = False
            while not done:
                _, done = dl.next_chunk()
            buf.seek(0)
            with pdfplumber.open(buf) as pdf:
                return "\n\n".join((p.extract_text() or "") for p in pdf.pages)

        if mime.startswith("text/") or name.lower().endswith((".txt", ".md", ".csv")):
            data = service.files().get_media(fileId=f["id"]).execute()
            return data.decode("utf-8", "replace") if isinstance(data, bytes) else str(data)
    except Exception as e:
        logger.warning("Drive : téléchargement de « %s » échoué : %s", name, e)
    return None  # docx, images… : gérés via Make ou à ajouter ici


async def sync(folder_id: Optional[str] = None) -> dict:
    """Parcourt un dossier Drive (récursif via l'API) et ingère les fichiers texte/PDF/Docs."""
    service = _build_service()
    folder = folder_id or settings.google_drive_folder_id
    q = f"'{folder}' in parents and trashed=false" if folder else "trashed=false"

    files, token = [], None
    while True:
        resp = service.files().list(
            q=q, spaces="drive", fields="nextPageToken, files(id,name,mimeType)",
            pageToken=token,
            # `corpora` MANQUAIT, et c'est ce qui rendait un Drive partagé
            # invisible. Par défaut l'API cherche dans le corpus « user »,
            # c'est-à-dire le « Mon Drive » du compte : sans dossier précisé,
            # la synchronisation d'un Drive PARTAGÉ ne remontait rien, et le
            # tour se terminait sur « 0 fichier » sans la moindre erreur — le
            # pire des symptômes, celui qui ressemble à un Drive vide.
            #
            # `includeItemsFromAllDrives` et `supportsAllDrives` ne suffisent
            # pas : ils autorisent les résultats hors « Mon Drive », ils ne
            # décident pas où l'on cherche.
            corpora="allDrives",
            includeItemsFromAllDrives=True, supportsAllDrives=True, pageSize=100,
        ).execute()
        files.extend(resp.get("files", []))
        token = resp.get("nextPageToken")
        if not token:
            break

    ingested = 0
    for f in files:
        text = _download_text(service, f)
        if text and await ingest_document(text=text, source_type="drive",
                                          source_id=f["id"], source_filename=f["name"]):
            ingested += 1
    return {"fichiers": len(files), "ingérés": ingested}
