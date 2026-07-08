# Connecteurs sources externes — guide d'activation

Ingestion des données Symbiose Paysage dans la base documentaire (RAG) depuis
**Google Drive**, **Outlook / Microsoft 365**, **Extrabat** et **Deytime**.

## Le point honnête à retenir

**Un simple email + mot de passe ne suffit pour AUCUN de ces services** en accès
programmatique. Les mots de passe présents dans `CREDENTIALS.env` servent à se
connecter à la main aux interfaces web, **pas** aux API. Il faut, selon le service,
soit passer par **Make.com** (qui gère l'authentification pour nous), soit créer une
**app OAuth**, soit **activer un accès API** auprès de l'éditeur.

Découverte des recherches : le domaine `symbiose-paysage.fr` est hébergé sur
**Microsoft 365** (l'email = Outlook ; Mailinblack n'est que le filtre anti-spam en
amont). Google Drive correspond à un **accès Google personnel** distinct.

## Architecture d'ingestion

```
Source ──► [ Make.com  OU  connecteur API direct ] ──► pipeline.ingest_document()
                                                              │
                                                    découpe + (anonymisation) + base RAG
```

Deux points d'entrée dans le backend :

| Point d'entrée | Usage | Sécurité |
|---|---|---|
| `POST /api/ingestion/webhook` | Reçoit un doc depuis un scénario **Make.com** | En-tête `X-Ingestion-Secret` |
| `POST /api/ingestion/sync/{source}` | Déclenche un **connecteur API direct** | super_admin (JWT) |
| `GET /api/ingestion/status` | Compteurs (docs par source, vectorisation) | permission `view_dashboard_global` |

`source` ∈ `google_drive`, `outlook`, `extrabat`, `deytime`.

---

## Recommandation par service

| Service | Voie la plus simple | Voie pérenne (API directe) |
|---|---|---|
| **Google Drive** | ✅ **Make.com** (connecteur natif, OAuth en 2 clics) | OAuth Google Cloud |
| **Outlook / M365** | ✅ **Make.com** (connecteur natif) | App Azure AD + Graph (consentement admin) |
| **Extrabat** | Exports **CSV/Excel** (immédiat) | API REST — activation par l'éditeur |
| **Deytime** | Export **Excel**, ou via **Extrabat** | Aucune API |

---

## 1. Le pont Make.com (recommandé pour Drive + Outlook)

Aucune app à créer côté Google/Microsoft : Make possède déjà ses apps OAuth.

1. Générer un secret et le mettre dans `.env` :
   `INGESTION_WEBHOOK_SECRET=<chaîne aléatoire longue>`
2. Dans Make (compte déjà connecté, org 8278432, plan Free) créer un scénario :
   - **Google Drive** → module *Watch Files in a Folder* (ou *Watch All Files*)
     → *Download a File* → module **HTTP → Make a request**.
   - **Outlook/M365** → module *Microsoft 365 Email → Watch Emails*
     (+ *Download an Attachment*) → module **HTTP → Make a request**.
3. Configurer le module HTTP :
   - URL : `https://<backend-public>/api/ingestion/webhook`
   - Méthode : `POST`, en-tête `X-Ingestion-Secret: <le secret>`
   - Body JSON :
     ```json
     {
       "source_type": "drive",          // ou "email", "devis", "chantier"...
       "source_id": "{{id du fichier/email}}",
       "filename": "{{nom / sujet}}",
       "text": "{{corps ou texte extrait}}",
       "content_base64": "{{données si binaire}}",
       "mime_type": "{{mimeType}}",
       "anonymize": true                 // conseillé pour les emails (RGPD)
     }
     ```
> Plan Free = 1000 opérations/mois, polling mini 15 min. OK pour démarrer, à
> upgrader (Core/Pro) pour la prod. Sécuriser le webhook (secret + allowlist IP Make).

---

## 2. Google Drive — voie API directe (alternative)

Prérequis : accès à [console.cloud.google.com](https://console.cloud.google.com).

1. Créer un projet, activer **Google Drive API**.
2. **OAuth consent screen** : type *Internal* si compte Workspace, sinon *External*.
3. **Credentials → Create OAuth client ID → Desktop app** → télécharger le JSON.
4. Le déposer dans `backend/secrets/google_credentials.json`.
5. **1er consentement** (interactif, une seule fois, hors Docker) : lancer un petit
   script appelant `ingestion.connectors.google_drive.sync()` → une fenêtre s'ouvre,
   on valide → un `secrets/google_token.json` (refresh token) est écrit.
6. Copier ce dossier `secrets/` dans le conteneur (monté en volume). Ensuite,
   `POST /api/ingestion/sync/google_drive` fonctionne sans interaction.

`.env` : `GOOGLE_DRIVE_FOLDER_ID=<id du dossier à ingérer>` (sinon tout le Drive).

> ⚠ Compte Google **personnel** (pas Workspace) : app en mode *Testing* → le refresh
> token expire au bout de 7 jours. Publier l'app (mode *Production*) pour un token
> durable. Sur ce point Make.com est nettement plus simple.

---

## 3. Outlook / Microsoft 365 — voie API directe (alternative)

Prérequis **bloquant** : être **Administrateur général** du tenant M365 (probable
si tu possèdes le domaine) pour accorder le consentement admin.

1. [entra.microsoft.com](https://entra.microsoft.com) → *Inscriptions d'applications*
   → *Nouvelle inscription*. Noter **Tenant ID** et **Client ID**.
2. *Certificats et secrets* → *Nouveau secret client* → copier la **valeur**.
3. *Autorisations d'API* → Microsoft Graph → **permissions d'application** :
   `Mail.Read` (+ `Files.Read.All` si OneDrive/SharePoint) → **Accorder le
   consentement administrateur**.
4. Restreindre l'accès à la seule boîte cible (RGPD) via Exchange Online PowerShell :
   `New-ApplicationAccessPolicy` sur `contact@symbiose-paysage.fr`.
5. `.env` :
   ```
   MS_TENANT_ID=...
   MS_CLIENT_ID=...
   MS_CLIENT_SECRET=...
   MS_MAILBOX=contact@symbiose-paysage.fr
   ```
6. `POST /api/ingestion/sync/outlook`.

> Le client secret expire (≤ 24 mois) → prévoir la rotation. Ne PAS partir sur
> IMAP/mot de passe (basic auth désactivée) ni EWS (fin de vie ~oct. 2026).

---

## 4. Extrabat

Pas de connecteur Make natif. Deux voies.

**Voie immédiate — exports CSV/Excel** (aucune dépendance à l'éditeur) :
depuis Extrabat, bulle **Exports** (clients, gestion commerciale, factures,
articles), télécharger le fichier puis :
```python
from ingestion.connectors.extrabat import import_export
await import_export("chemin/clients.xlsx", source_type="clients")
```

**Voie pérenne — API REST** (`https://api.extrabat.com/v1`) :
1. Dans Extrabat : *Paramètres > Magasin > Coordonnées et informations générales*
   → générer/récupérer l'**identifiant + mot de passe API** (≠ login email).
2. **Contacter le support Extrabat** (Angoulême, servicescompris.extrabat.com) pour
   **activer l'accès API** et obtenir la doc des endpoints (non publique). Confirmer
   au passage que **devis** et **chantiers/planning** sont accessibles.
3. `.env` : `EXTRABAT_API_LOGIN=...` et `EXTRABAT_API_PASSWORD=...`
4. `POST /api/ingestion/sync/extrabat` (⚠ endpoints du connecteur à ajuster selon
   la doc reçue — voir `_ENTITIES` dans `connectors/extrabat.py`).

---

## 5. Deytime

**Aucune API, aucun webhook, aucun connecteur Make.** Deux voies.

**Voie 1 — export Excel** « prépa paie » (backoffice manager, mensuel) :
```python
from ingestion.connectors.deytime import import_excel
await import_excel("chemin/deytime_prepa_paie.xlsx")
```
(les pointages sont classés `direction_only` + anonymisés — données RH sensibles.)

**Voie 2 — via Extrabat** : Deytime remonte automatiquement les temps dans Extrabat.
Si Extrabat est utilisé, récupérer plannings/pointages par l'**API Extrabat** (§4)
est la voie durable.

Contact éditeur (petit éditeur français) : **benjamin.durou@deytime.fr** — leur
demander s'il existe un export automatisé.

---

## Variables `.env` — récapitulatif

```dotenv
# Pont Make.com
INGESTION_WEBHOOK_SECRET=

# Google Drive (voie directe)
GOOGLE_DRIVE_FOLDER_ID=
# fichiers : secrets/google_credentials.json + secrets/google_token.json

# Outlook / Microsoft 365 (voie directe)
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_MAILBOX=contact@symbiose-paysage.fr

# Extrabat (voie API)
EXTRABAT_API_LOGIN=
EXTRABAT_API_PASSWORD=
```

## Dépendances

Les libs des connecteurs (`google-api-python-client`, `msal`, `pandas`, `openpyxl`,
`pdfplumber`) sont dans `requirements.txt` et **importées paresseusement** : le
backend démarre sans elles ; elles ne sont nécessaires qu'à l'exécution du
connecteur concerné. Reconstruire l'image après ajout pour activer une voie directe.

## RGPD

Emails, clients et pointages contiennent des données personnelles : l'ingestion
anonymise par défaut (`anonymize=true`) et les pointages Deytime sont restreints à
`direction_only`. Ne jamais logger le contenu, uniquement les métadonnées.
