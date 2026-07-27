# Accès admin — Google Drive & Outlook (ingestion Symbiose)

Guide clic-par-clic pour donner à Symbiose l'accès au **Drive de l'entreprise** (Google)
et à la **messagerie Outlook** (Microsoft 365). Les étapes sont ce que **toi** tu fais dans
les consoles ; l'adaptation du code des connecteurs est côté dev.

> **Rappel :** aucun de ces accès ne marche avec un simple email + mot de passe. Il faut créer
> une app / un compte de service et accorder un accès. Colle exactement aux connecteurs du backend
> (`ingestion/connectors/google_drive.py`, `ingestion/connectors/outlook.py`).

## Vue d'ensemble

| Service | Ce que ça débloque | Droit admin | Méthode |
|---|---|---|---|
| **Google Drive — voie A** | Un **dossier / Drive partagé** précis | Aucun (juste partager) | Compte de service + **partage du dossier** |
| **Google Drive — voie B** | Le Drive de **chaque utilisateur** du Workspace | **Super admin** Workspace | Compte de service + **délégation domaine** |
| **Outlook / M365** | **Toutes les boîtes** du tenant | **Administrateur général** | App Entra + Graph `Mail.Read` + `User.Read.All` |

---

## 1. Google Drive

Choisis **UNE** des deux voies selon ce que tu veux lire.

### Voie A — un dossier / Drive partagé précis ✅ (simple, sans `admin.google.com`)

À privilégier si les documents de l'entreprise sont rangés à un endroit identifié.

1. **Créer le compte de service** — [console.cloud.google.com](https://console.cloud.google.com) →
   **IAM et admin › Comptes de service › Créer** → nom `symbiose-ingestion` →
   à l'étape « rôle », **ne mets aucun rôle** → **Terminé**.
   Note l'**email** du compte (`…@….iam.gserviceaccount.com`).
2. **Générer la clé JSON** — sur le compte → **Clés › Ajouter une clé › JSON** → dépose-la dans
   `backend/secrets/google_service_account.json` (gitignoré, ne jamais committer).
3. **Activer l'API** — **API et services › Bibliothèque** → activer **Google Drive API**.
4. **Partager le dossier avec le compte de service** — dans Google Drive, clic droit sur le
   **dossier** (ou le **Drive partagé**) à ingérer → **Partager** → colle l'**email du compte de
   service** → droit **Lecteur** → Envoyer. *(Exactement comme partager avec un collègue.)*
5. **`.env`** :
   ```dotenv
   GOOGLE_SERVICE_ACCOUNT_FILE=secrets/google_service_account.json
   GOOGLE_DRIVE_FOLDER_ID=<id du dossier / Drive partagé>
   ```
   *(l'ID est la fin de l'URL du dossier : `drive.google.com/drive/folders/`**`<ID>`**)*
6. **Déclencher** (rôle super_admin de l'app) : `POST /api/ingestion/sync/google_drive`.

> ✅ Aucun passage par `admin.google.com`, marche même sur un compte Google perso.

### Voie B — le Drive de TOUS les salariés (délégation à l'échelle du domaine)

Nécessite d'être **super administrateur** du Google Workspace.

1. **Créer le compte de service** (idem voie A, étapes 1-2) — note aussi son **ID client numérique**
   (onglet « Détails » du compte).
2. **Activer les API** — **Google Drive API** **et** **Admin SDK API** (l'Admin SDK sert à lister
   les utilisateurs du domaine).
3. **Autoriser la délégation dans la console Admin** ⭐ (l'étape qui exige le super admin) —
   [admin.google.com](https://admin.google.com) → **Sécurité › Accès et contrôle des données ›
   Commandes des API › Gérer la délégation au niveau du domaine › Ajouter** :
   - **ID client** = l'ID numérique du compte de service
   - **Champs d'application OAuth** (à coller tel quel) :
     ```
     https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly
     ```
   - → **Autoriser**
4. **`.env`** :
   ```dotenv
   GOOGLE_SERVICE_ACCOUNT_FILE=secrets/google_service_account.json
   GOOGLE_WORKSPACE_ADMIN=admin@symbiose-paysage.fr   # super-admin à impersoner pour lister les comptes
   GOOGLE_DRIVE_FOLDER_ID=                             # optionnel : limiter à un dossier
   ```
5. **Déclencher** : `POST /api/ingestion/sync/google_drive`.

> **Pourquoi `admin.google.com` ?** Donner à une app le droit de lire les fichiers de **tout le
> monde** ne peut être autorisé **que** par un super admin, dans la console Admin. La Cloud Console
> crée le compte de service mais ne peut pas lui donner ce pouvoir.

---

## 2. Outlook / Microsoft 365

Nécessite d'être **Administrateur général** du tenant (pour accorder le consentement admin).

1. **Inscrire l'application** — [entra.microsoft.com](https://entra.microsoft.com) →
   **Identité › Applications › Inscriptions d'applications › Nouvelle inscription** →
   nom `Symbiose Ingestion` → **Comptes dans cet annuaire uniquement** → **Inscrire**.
2. **Copier les identifiants** (page **Vue d'ensemble**) :
   - **ID d'application (client)** → `MS_CLIENT_ID`
   - **ID de l'annuaire (locataire)** → `MS_TENANT_ID`
3. **Créer un secret client** — **Certificats et secrets › Secrets client › Nouveau secret client**
   → description + expiration (ex. 24 mois) → **Ajouter**.
   - ⚠️ Copie **immédiatement** la colonne **Valeur** → `MS_CLIENT_SECRET`
     (**pas** l'« ID de secret » ; la Valeur disparaît dès que tu quittes la page).
4. **Ajouter les permissions** — **Autorisations d'API › Ajouter une autorisation ›
   Microsoft Graph › Autorisations d'application** → coche **`Mail.Read`** *et* **`User.Read.All`**
   → **Ajouter**.
   - `Mail.Read` (app-only) = lit **toutes les boîtes** ; `User.Read.All` = les **lister**.
5. **Accorder le consentement admin** — bouton **« Accorder un consentement d'administrateur pour
   Symbiose »** → **Oui** (statuts au vert). *(C'est ici que le rôle Global Admin est requis.)*
6. **`.env`** :
   ```dotenv
   MS_TENANT_ID=<ID de l'annuaire>
   MS_CLIENT_ID=<ID d'application>
   MS_CLIENT_SECRET=<la Valeur du secret>
   MS_MAILBOX=                    # vide = toutes les boîtes ; ou une adresse pour n'en lire qu'une
   ```
7. **Déclencher** : `POST /api/ingestion/sync/outlook`.

> ⚠️ Le secret expire (≤ 24 mois) → prévoir la rotation. Ne pas utiliser IMAP/mot de passe
> (basic auth désactivée) ni EWS (fin de vie ~oct. 2026).

### Tester Microsoft avant tout (script autonome)

Un script **sans dépendance** vérifie l'app Entra (jeton + liste des boîtes + derniers mails) :

```bash
python backend/scripts/test_microsoft.py
```
Il demande Tenant/Client/Secret à la main. Le `[1/3]` (jeton) valide déjà Tenant + Client + Secret,
même sans permissions. Les `[2/3]`/`[3/3]` valident `User.Read.All` / `Mail.Read`.

---

## Récapitulatif — où mettre quoi

```dotenv
# .env (ou CREDENTIALS.env, gitignoré)

# Google Drive
GOOGLE_SERVICE_ACCOUNT_FILE=secrets/google_service_account.json
GOOGLE_DRIVE_FOLDER_ID=            # voie A : l'ID du dossier partagé
GOOGLE_WORKSPACE_ADMIN=           # voie B uniquement (super-admin à impersoner)

# Outlook / Microsoft 365
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_MAILBOX=                       # vide = toutes les boîtes
```

| Fichier | Contenu |
|---|---|
| `backend/secrets/google_service_account.json` | clé JSON du compte de service (ne pas committer) |
| `.env` | les variables `GOOGLE_*` et `MS_*` ci-dessus |

## État du code (côté dev)

- `google_drive.py` : aujourd'hui en OAuth utilisateur → à basculer en **compte de service**
  (voie A : lecture simple ; voie B : + impersonation via Admin SDK).
- `outlook.py` : aujourd'hui **une** boîte (`MS_MAILBOX`) → à étendre au **balayage de toutes les
  boîtes** (liste `/users` puis messages de chacune).
- Les deux gardent un **mode de repli** → aucune régression.

## RGPD

Emails et documents contiennent des données personnelles : l'ingestion **anonymise par défaut**
(`anonymize=true`) et les résultats restent réservés aux **rôles direction**. Ne jamais logger le
contenu, seulement les métadonnées.
