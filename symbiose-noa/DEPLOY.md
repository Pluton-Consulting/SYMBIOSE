# Déployer Symbiose sur un VPS Ubuntu — VPN Headscale + domaine + HTTPS

Ce guide déploie **le projet Symbiose identique à celui du dépôt** sur un VPS Ubuntu :
- accès **privé via un VPN auto-hébergé (Headscale)** — l'app n'est **jamais** sur l'Internet public ;
- sous le nom de domaine **`symbiose.pluton-consulting.fr`** ;
- en **HTTPS valide** (certificat Let's Encrypt public, renouvelé automatiquement, **rien à
  installer sur les postes**), obtenu via le **challenge DNS-01 Gandi** (Caddy).

100 % gratuit, sans dépendance à un service tiers.

> **Domaine et DNS.** L'app = `symbiose.pluton-consulting.fr`, le serveur VPN = `vpn.pluton-consulting.fr`.
> Le DNS de `pluton-consulting.fr` est chez **Gandi** (nameservers `*.gandi.net`) → le certificat
> HTTPS passe par le module **`caddy-dns/gandi`** et un **token Gandi**. Le domaine racine
> (le site Pluton Consulting) n'est **pas** touché : on n'ajoute que 2 sous-domaines. Tout est
> paramétré dans `.env` — pour changer de domaine un jour, il suffit d'éditer `.env` (et le module
> Caddy si le nouveau domaine n'est pas chez Gandi).

> **Deux « admin » à ne pas confondre :**
> - l'**admin du serveur** = le compte Linux OVH (`ubuntu`/`root`) qui gère la machine ;
> - l'**admin de l'application** (`FIRST_ADMIN_EMAIL`) = ton login *dans* NOA (par email / lien magique).

> **Headscale ≠ Tailscale — à lire une fois :** **Headscale** est le *serveur* VPN que **tu
> héberges** sur le VPS. **`tailscale`** est le *logiciel client* (open-source, gratuit) installé
> sur le VPS et sur chaque poste ; l'option `--login-server https://vpn.…` le connecte à **TON**
> Headscale, **jamais** au cloud Tailscale.

---

## Architecture retenue

```
   Employés (client tailscale connecté à TON serveur Headscale)
            │   (tunnel WireGuard chiffré, privé)
            ▼
   https://symbiose.pluton-consulting.fr   → IP VPN du VPS (100.64.0.x)   ← domaine + HTTPS
            │
   Caddy  (écoute sur ${VPN_IP}:443)        ← certificat Let's Encrypt (DNS-01 Gandi), auto-renouvelé
            │  reverse_proxy
   nginx  (interne, 127.0.0.1:80)           ← routage déjà dans le projet
       ├── /            → frontend:3000
       ├── /api/        → backend:8000
       └── /api/ws/     → backend:8000  (WebSocket)
            │
   Réseau Docker : frontend · backend · browser-worker · postgres(pgvector)

   ── En parallèle, sur le même VPS ──
   https://vpn.pluton-consulting.fr → IP PUBLIQUE du VPS → serveur Headscale (coordination VPN)
```

Deux enregistrements DNS à créer chez Gandi (sur `pluton-consulting.fr`) :
- **`vpn`** → IP **publique** du VPS → serveur Headscale (seule chose publique ; son propre certif).
- **`symbiose`** → IP **VPN** (`100.64.0.x`, privée) → Caddy → l'app. Routable seulement sur le VPN.

Deux IP à garder sous la main : **`IP_PUBLIQUE`** (celle d'OVH) et **`VPN_IP`** (celle que
donne `tailscale ip -4`, ex. `100.64.0.1`).

---

## Ce dont tu as besoin

- Un **VPS Ubuntu 22.04/24.04** — recommandé **VPS-2 (4 vCPU / 8 Go)** minimum.
- L'**accès SSH** OVH (compte `ubuntu` ou `root`) + l'**IP publique**.
- La main sur le **DNS Gandi de `pluton-consulting.fr`** (2 enregistrements + un token API).
- Un **jeton GitHub (PAT)** pour cloner `BenITNoaBenitez/SYMBIOSE`.
- Les **clés API** (mêmes qu'en dev) : Groq, LongCat, Gemini, Resend.

---

## Étape 0 — Se connecter au VPS

*À quoi ça sert :* ouvrir un terminal **sur le VPS**. Toutes les commandes du guide se tapent
là. On utilise le compte fourni par OVH, pas un nouveau.

```bash
ssh ubuntu@IP_PUBLIQUE      # ou  ssh root@IP_PUBLIQUE  selon l'image OVH
```

Le compte `ubuntu` d'OVH a déjà `sudo` (les droits d'administration).

---

## Étape 1 — Mettre à jour le système

*À quoi ça sert :* installer les derniers correctifs de sécurité d'Ubuntu **avant** d'ajouter
quoi que ce soit — on part d'une base saine.

```bash
sudo apt update && sudo apt upgrade -y
```

---

## Étape 2 — Pare-feu (UFW)

*À quoi ça sert :* fermer tout ce qui n'est pas indispensable. On ne laisse ouvert au public
que le **SSH** et les ports du **serveur VPN**. L'application ne sera **jamais** joignable
publiquement : elle passe uniquement par le tunnel (interface `tailscale0`).

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp             # Headscale : challenge ACME (sur l'IP publique)
sudo ufw allow 443/tcp            # Headscale : coordination du VPN (sur l'IP publique)
sudo ufw allow in on tailscale0   # tout le trafic entrant DEPUIS le VPN (Caddy + app)
sudo ufw --force enable && sudo ufw status
```

---

## Étape 3 — Swap (2 Go)

*À quoi ça sert :* ajouter une mémoire de secours sur le disque. Sans elle, la **compilation**
(Next.js + Chromium) peut épuiser la RAM d'un petit VPS et faire planter des conteneurs.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

---

## Étape 4 — Installer Docker

*À quoi ça sert :* installer le moteur qui fait tourner toute l'application. Chaque brique
(base, backend, frontend, worker, Caddy…) est un **conteneur Docker** ; Docker Compose les
orchestre ensemble.

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

**Déconnecte/reconnecte** (`exit` puis `ssh …`) pour activer le groupe `docker`, puis vérifie :

```bash
docker --version && docker compose version
```

---

## Étape 5 — Monter le VPN (Headscale)

*À quoi ça sert :* créer le **réseau privé** par lequel — et seulement par lequel — on accédera
à l'application. **Headscale** est le serveur qui coordonne le VPN ; ensuite le VPS et chaque
poste s'y connectent avec le **client `tailscale`**. C'est cette étape qui rend l'app privée.

### 5.1 — 1er enregistrement DNS (Gandi)

*Pointer le nom du serveur VPN vers l'IP publique du VPS.*

| Type | Nom | Valeur |
|------|-----|--------|
| A | `vpn` | **IP_PUBLIQUE** du VPS |

### 5.2 — Installer le serveur Headscale

```bash
VER=0.23.0     # dernière version : github.com/juanfont/headscale/releases
wget -O headscale.deb "https://github.com/juanfont/headscale/releases/download/v${VER}/headscale_${VER}_linux_amd64.deb"
sudo apt install -y ./headscale.deb
```

### 5.3 — Configurer Headscale

*On part du fichier d'exemple **officiel de ta version** — le réécrire à la main est risqué
(les noms de champs changent entre versions, et un fichier mal collé casse tout : `Error loading
config … cannot unmarshal`). On ne modifie ensuite que 4 lignes. Headscale écoute sur l'IP
**publique** (pour laisser les ports du VPN libres à Caddy) et gère son propre certificat.*

```bash
headscale version
```

Récupère l'exemple correspondant (remplace `v0.23.0` par ta version) et ouvre-le :

```bash
sudo wget -O /etc/headscale/config.yaml https://raw.githubusercontent.com/juanfont/headscale/v0.23.0/config-example.yaml
sudo nano /etc/headscale/config.yaml
```

Dans nano, `Ctrl+W` cherche une ligne. Modifie **seulement** ces 4 réglages (retire le `#` en
tête des lignes `tls_letsencrypt_*` si elles sont commentées). `IP_PUBLIQUE` = `curl -4 ifconfig.me` :

```yaml
server_url: https://vpn.pluton-consulting.fr
listen_addr: IP_PUBLIQUE:443
tls_letsencrypt_hostname: vpn.pluton-consulting.fr
tls_letsencrypt_listen: IP_PUBLIQUE:80
```

Enregistre (`Ctrl+O`, `Entrée`, `Ctrl+X`), puis démarre :

```bash
sudo systemctl enable --now headscale
sudo systemctl status headscale --no-pager        # "active (running)"
```

> **Erreur « cannot unmarshal … » ?** Le YAML est invalide (indentation cassée, ou texte collé
> par erreur dans le fichier). Relance le `wget` ci-dessus pour repartir propre, puis ne touche
> qu'aux 4 lignes. Astuce : colle **une commande à la fois** — les collages multi-lignes se
> chevauchent souvent dans un terminal SSH.

### 5.4 — Créer un utilisateur + une clé d'inscription

*La clé « preauth » permet d'inscrire une machine sur le VPN sans manipulation manuelle.*

```bash
sudo headscale users create symbiose
sudo headscale users list                          # note l'ID (souvent 1)
sudo headscale preauthkeys create --user 1 --reusable --expiration 24h
# → copie la clé "tskey-..." (elle servira pour le VPS et les postes)
```

### 5.5 — Connecter le VPS lui-même au VPN

*Installer le **client** `tailscale` sur le VPS et l'inscrire sur ton Headscale. Indispensable :
l'app (Caddy) écoutera sur l'IP VPN du VPS, donc cette IP doit exister **avant** l'étape 9.*

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --login-server https://vpn.pluton-consulting.fr --authkey tskey-VOTRE_CLE
tailscale ip -4        # → VPN_IP du VPS, ex. 100.64.0.1
```

### 5.6 — 2ᵉ enregistrement DNS (Gandi)

*Pointer le nom de l'application vers l'IP **VPN** (privée) → joignable seulement sur le VPN.*

| Type | Nom | Valeur |
|------|-----|--------|
| A | `symbiose` | **VPN_IP** du VPS (ex. `100.64.0.1`) |

---

## Étape 6 — Créer le token API Gandi (pour le HTTPS)

*À quoi ça sert :* autoriser Caddy à créer un enregistrement DNS temporaire chez Gandi. C'est la
**preuve exigée par Let's Encrypt** (challenge DNS-01) pour délivrer un certificat HTTPS à un
service non public — impossible autrement pour une IP privée.

1. Connecte-toi sur **https://admin.gandi.net**.
2. Menu de ton **organisation** (celle qui possède `pluton-consulting.fr`) →
   **Jetons d'accès personnel** (*Personal Access Tokens*).
3. **Créer un jeton** ; coche la permission **« Gérer les configurations techniques du nom de
   domaine »** (*Manage domain name technical configurations*). Tu peux le restreindre au
   domaine `pluton-consulting.fr`.
4. Copie le jeton → il ira dans `GANDI_API_TOKEN` (`.env`, étape 8).

> Si ton build de Caddy attend l'ancienne **clé API LiveDNS** au lieu du jeton PAT
> (message d'auth Gandi), crée-la dans *Compte → Sécurité → Clé API* et mets-la dans la même
> variable `GANDI_API_TOKEN`.

---

## Étape 7 — Cloner le projet

*À quoi ça sert :* télécharger le code du projet depuis GitHub sur le VPS.

```bash
cd ~
git clone https://github.com/BenITNoaBenitez/SYMBIOSE.git      # login = pseudo, mot de passe = PAT
cd SYMBIOSE/symbiose-noa
```

---

## Étape 8 — Créer le fichier `.env` de production

*À quoi ça sert :* renseigner **tous les secrets et réglages** (mots de passe base, clés de
sécurité, clés API, domaine, token Gandi). C'est LE fichier de configuration de l'app — il
n'est volontairement **pas** sur GitHub, on le crée à la main sur le VPS.

Génère d'abord 4 secrets : `openssl rand -hex 32` (une fois par ligne, note-les).

```bash
nano .env
```

```ini
# ─── Base de données ─────────────────────────────────────────────
POSTGRES_DB=symbiose_noa
POSTGRES_USER=noa_user
POSTGRES_PASSWORD=⟨secret n°1⟩
DATABASE_URL=postgresql+asyncpg://noa_user:⟨secret n°1⟩@postgres:5432/symbiose_noa

# ─── Sécurité applicative ────────────────────────────────────────
JWT_SECRET_KEY=⟨secret n°2⟩
NEXTAUTH_SECRET=⟨secret n°3⟩
INGESTION_WEBHOOK_SECRET=⟨secret n°4⟩

# ─── URLs (⚠ HTTPS + le domaine, identiques toutes les 3) ────────
APP_URL=https://symbiose.pluton-consulting.fr
NEXTAUTH_URL=https://symbiose.pluton-consulting.fr
NEXT_PUBLIC_API_URL=https://symbiose.pluton-consulting.fr

# ─── Réseau ──────────────────────────────────────────────────────
HEADSCALE_IP=127.0.0.1          # nginx reste interne (Caddy est l'entrée HTTPS)
VPN_IP=100.64.0.1               # IP de `tailscale ip -4` : Caddy s'y lie (443)

# ─── HTTPS : Caddy + DNS-01 Gandi ────────────────────────────────
APP_HOSTNAME=symbiose.pluton-consulting.fr
ACME_EMAIL=admin@pluton-consulting.fr
GANDI_API_TOKEN=⟨jeton Gandi⟩

# ─── Clés API (mêmes qu'en dev) ──────────────────────────────────
GROQ_API_KEY=⟨…⟩
LONGCAT_API_KEY=⟨…⟩
LONGCAT_BASE_URL=https://api.longcat.chat/openai/v1
GOOGLE_API_KEY=⟨…⟩
RESEND_API_KEY=⟨…⟩
RESEND_FROM_EMAIL=noreply@pluton-consulting.fr   # doit être un domaine vérifié dans Resend

# ─── Agent navigateur ────────────────────────────────────────────
BROWSER_AGENT_ENABLED=true
BROWSER_LLM_MODEL=LongCat-2.0
BROWSER_ALLOWED_DOMAINS=www.myextrabat.com,manager.deytime.fr
BROWSER_READONLY=true
BROWSER_AGENT_MAX_STEPS=25
ANTHROPIC_API_KEY=placeholder

# ─── ADMIN DE L'APPLICATION (≠ compte Linux OVH) ─────────────────
FIRST_ADMIN_EMAIL=ton.email@pluton-consulting.fr
```

> **Piège n°1 :** `NEXT_PUBLIC_API_URL` est **gelée au build** du frontend → mets-la correcte
> **avant** `./deploy.sh`. La changer plus tard ⇒ rebuild (`./deploy.sh`).

---

## Étape 9 — Construire et démarrer

*À quoi ça sert :* fabriquer les images et lancer **toute la pile**. Le script applique en plus
la base (migrations), crée ton compte admin, charge les skills, et Caddy récupère le certificat HTTPS.

```bash
chmod +x deploy.sh
./deploy.sh
```

Détail : build (frontend avec la bonne URL **+ image Caddy personnalisée**, ~2-3 min la 1ʳᵉ fois)
→ démarrage → migrations SQL → **super_admin `FIRST_ADMIN_EMAIL`** → skills. Caddy demande alors
le certificat via l'API Gandi (**~1-2 min**). Suis-le :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy
# attends "certificate obtained successfully" pour symbiose.pluton-consulting.fr
```

---

## Étape 10 — Premier accès + connexion

*À quoi ça sert :* rejoindre le VPN depuis **ton PC** et ouvrir l'application pour la toute
première connexion administrateur.

1. Sur ton PC, installe le **client tailscale** et connecte-le à ton Headscale :
   ```
   tailscale up --login-server https://vpn.pluton-consulting.fr --authkey tskey-VOTRE_CLE
   ```
2. Ouvre **`https://symbiose.pluton-consulting.fr`** → cadenas vert.
3. Entre `FIRST_ADMIN_EMAIL` → **« Recevoir le lien »**.
4. Lien magique par **email** (Resend) ; sinon `docker compose logs backend | grep "MAGIC LINK"`.
5. Clique → connecté en **super_admin**.

---

## Étape 11 — Donner l'accès aux employés

*À quoi ça sert :* faire entrer les collaborateurs. Chacun rejoint le VPN, puis reçoit un
compte applicatif que tu crées.

1. Génère-lui une clé : `sudo headscale preauthkeys create --user 1 --expiration 720h`.
2. Il installe le **client tailscale** et lance
   `tailscale up --login-server https://vpn.pluton-consulting.fr --authkey <sa-clé>`.
3. Il ouvre `https://symbiose.pluton-consulting.fr`.
4. Toi (super_admin) : crée son compte dans **Paramètres → Utilisateurs**, avec le bon rôle.

Hors VPN, `symbiose.pluton-consulting.fr` pointe sur une IP privée : personne d'autre ne peut y accéder.

---

## Étape 12 — Maintenance

*À quoi ça sert :* les gestes courants ensuite — mettre à jour, sauvegarder, consulter les logs.

```bash
# Mise à jour du projet :
cd ~/SYMBIOSE/symbiose-noa && git pull && ./deploy.sh

# Sauvegarde de la base (à mettre en cron quotidien) :
docker compose exec -T postgres pg_dump -U noa_user symbiose_noa | gzip > ~/backup-$(date +%F).sql.gz

# Logs :
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

Le certificat HTTPS se **renouvelle tout seul** (Caddy). Redémarrages auto déjà configurés
(`restart: unless-stopped`).

---

## Checklist finale

- [ ] DNS Gandi : `vpn` → IP_PUBLIQUE ; `symbiose` → VPN_IP (`100.64.0.x`).
- [ ] `sudo systemctl status headscale` → **active** ; `https://vpn.pluton-consulting.fr` répond.
- [ ] `tailscale ip -4` (VPS) = la valeur de `VPN_IP` dans `.env`.
- [ ] `.env` : 3 URLs = `https://symbiose.pluton-consulting.fr` ; `HEADSCALE_IP=127.0.0.1` ; `GANDI_API_TOKEN` rempli.
- [ ] `docker compose … logs caddy` → **certificat obtenu**.
- [ ] `docker compose ps` → tous `running`/`healthy`.
- [ ] Depuis un poste **du VPN** : `https://symbiose.pluton-consulting.fr` en cadenas vert, connexion super_admin OK.

---

## Dépannage HTTPS

- **Caddy ne démarre pas, « cannot assign requested address »** → le VPS n'est pas connecté
  au VPN (l'IP `VPN_IP` n'existe pas). Refais l'étape 5.5, vérifie `tailscale ip -4`.
- **« error getting certificate / DNS problem »** → `GANDI_API_TOKEN` invalide ou sans la
  permission « configurations techniques du nom de domaine ».
- **La page ne charge pas** → vérifie que `symbiose` pointe bien sur `VPN_IP` (pas l'IP
  publique) et que tu es connecté au VPN.
