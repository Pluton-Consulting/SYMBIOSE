# Déployer Symbiose sur un VPS Ubuntu — VPN Headscale + domaine + HTTPS

Ce guide déploie **le projet Symbiose identique à celui du dépôt** sur un VPS Ubuntu :
- accès **privé via un VPN auto-hébergé (Headscale)** — l'app n'est **jamais** sur l'Internet public ;
- sous un **nom de domaine** (`assistant.symbiose-paysage.fr`) ;
- en **HTTPS valide** (certificat Let's Encrypt public, renouvelé automatiquement, **rien à
  installer sur les postes**), obtenu via le **challenge DNS-01 OVH** (Caddy).

100 % gratuit, sans dépendance à un service tiers.

> **Le nom de domaine se configure quand tu veux (même plus tard).** Rien n'est figé dans le
> code : tout se règle dans `.env` (étape 8). Ici `symbiose-paysage.fr` / `assistant.symbiose-paysage.fr`
> ne sont qu'un **exemple** — remplace-les partout par ton vrai domaine. ⚠ Le **seul** point qui
> dépend du domaine est son **hébergeur DNS** (pour le certificat HTTPS DNS-01). Ce guide suppose
> **OVH** ; si ton domaine est chez Cloudflare / Gandi / autre, une **ligne** du `caddy/Dockerfile`
> (le module) et le bloc `tls` du `Caddyfile` sont à adapter — dis-le-moi et je te les donne.

> **Deux « admin » à ne pas confondre :**
> - l'**admin du serveur** = le compte Linux OVH (`ubuntu`/`root`) qui gère la machine ;
> - l'**admin de l'application** (`FIRST_ADMIN_EMAIL`) = ton login *dans* NOA (par email / lien magique).

> **Headscale ≠ Tailscale — à lire une fois :** dans ce guide, **Headscale** est le *serveur* VPN
> que **tu héberges** sur le VPS. **`tailscale`** est le *logiciel client* (open-source, gratuit)
> installé sur le VPS et sur chaque poste ; l'option `--login-server https://vpn.…` le connecte
> à **TON** Headscale, **jamais** au cloud Tailscale. Voir un « tailscale » = c'est toujours le
> client qui parle à ton propre serveur.

---

## Architecture retenue

```
   Employés (client tailscale connecté à TON serveur Headscale)
            │   (tunnel WireGuard chiffré, privé)
            ▼
   https://assistant.symbiose-paysage.fr   → IP VPN du VPS (100.64.0.x)   ← domaine + HTTPS
            │
   Caddy  (écoute sur ${VPN_IP}:443)        ← certificat Let's Encrypt (DNS-01 OVH), auto-renouvelé
            │  reverse_proxy
   nginx  (interne, 127.0.0.1:80)           ← routage déjà dans le projet
       ├── /            → frontend:3000
       ├── /api/        → backend:8000
       └── /api/ws/     → backend:8000  (WebSocket)
            │
   Réseau Docker : frontend · backend · browser-worker · postgres(pgvector)

   ── En parallèle, sur le même VPS ──
   https://vpn.symbiose-paysage.fr → IP PUBLIQUE du VPS → serveur Headscale (coordination VPN)
```

Deux enregistrements DNS de `symbiose-paysage.fr` :
- **`vpn.`** → IP **publique** → serveur Headscale (seule chose publique ; son propre certif).
- **`assistant.`** → IP **VPN** (`100.64.0.x`, privée) → Caddy → l'app. Routable seulement sur le VPN.

Deux IP à garder sous la main : **`IP_PUBLIQUE`** (celle d'OVH) et **`VPN_IP`** (celle que
donne `tailscale ip -4`, ex. `100.64.0.1`).

---

## Ce dont tu as besoin

- Un **VPS Ubuntu 22.04/24.04** — recommandé **VPS-2 (4 vCPU / 8 Go)** minimum.
- L'**accès SSH** OVH (compte `ubuntu` ou `root`) + l'**IP publique**.
- La main sur le **DNS OVH de `symbiose-paysage.fr`** (2 enregistrements A + un token API).
- Un **jeton GitHub (PAT)** pour cloner `BenITNoaBenitez/SYMBIOSE`.
- Les **clés API** (mêmes qu'en dev) : Groq, LongCat, Gemini, Resend.

---

## Étape 0 — Se connecter au VPS

*À quoi ça sert :* ouvrir un terminal **sur le VPS**. Toutes les commandes du guide se tapent
là, à travers cette connexion SSH. On utilise le compte fourni par OVH, pas un nouveau.

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
que le **SSH** et les ports du **serveur VPN**. L'application, elle, ne sera **jamais** joignable
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
(base de données, backend, frontend, worker, Caddy…) est un **conteneur Docker** ; Docker
Compose les orchestre ensemble.

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

### 5.1 — 1er enregistrement DNS

*Pointer le nom du serveur VPN vers l'IP publique du VPS.*

| Type | Nom | Valeur |
|------|-----|--------|
| A | `vpn.symbiose-paysage.fr` | **IP_PUBLIQUE** du VPS |

### 5.2 — Installer le serveur Headscale

```bash
VER=0.23.0     # dernière version : github.com/juanfont/headscale/releases
wget -O headscale.deb "https://github.com/juanfont/headscale/releases/download/v${VER}/headscale_${VER}_linux_amd64.deb"
sudo apt install -y ./headscale.deb
```

### 5.3 — Configurer Headscale

*On dit à Headscale son URL publique, et on le fait écouter sur l'IP **publique** (pour laisser
les ports du VPN libres à Caddy). Il gère aussi son propre certificat Let's Encrypt.*

```bash
sudo nano /etc/headscale/config.yaml
```

```yaml
server_url: https://vpn.symbiose-paysage.fr
listen_addr: IP_PUBLIQUE:443

tls_letsencrypt_hostname: vpn.symbiose-paysage.fr
tls_letsencrypt_challenge_type: HTTP-01
tls_letsencrypt_listen: IP_PUBLIQUE:80

prefixes:
  v4: 100.64.0.0/10

dns:                          # (« dns_config » sur les versions < 0.23)
  magic_dns: true
  base_domain: symbiose.internal
```

```bash
sudo systemctl enable --now headscale
sudo systemctl status headscale --no-pager        # "active (running)"
```

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
sudo tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
tailscale ip -4        # → VPN_IP du VPS, ex. 100.64.0.1
```

### 5.6 — 2ᵉ enregistrement DNS

*Pointer le nom de l'application vers l'IP **VPN** (privée) → joignable seulement sur le VPN.*

| Type | Nom | Valeur |
|------|-----|--------|
| A | `assistant.symbiose-paysage.fr` | **VPN_IP** du VPS (ex. `100.64.0.1`) |

---

## Étape 6 — Créer le token API OVH (pour le HTTPS)

*À quoi ça sert :* autoriser Caddy à créer un enregistrement DNS temporaire chez OVH. C'est la
**preuve exigée par Let's Encrypt** (challenge DNS-01) pour délivrer un certificat HTTPS à un
service qui n'est pas public — impossible autrement pour une IP privée.

1. Va sur **https://api.ovh.com/createToken/** (connecte-toi avec le compte OVH du domaine).
2. **Rights** — ajoute ces 4 droits :
   ```
   GET     /domain/zone/symbiose-paysage.fr/*
   POST    /domain/zone/symbiose-paysage.fr/*
   PUT     /domain/zone/symbiose-paysage.fr/*
   DELETE  /domain/zone/symbiose-paysage.fr/*
   ```
3. **Validity** : *Unlimited*.
4. **Create keys** → note **Application Key**, **Application Secret**, **Consumer Key**
   (ils vont dans `.env`, étape 8). L'endpoint est **`ovh-eu`**.

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
sécurité, clés API, domaine, token OVH). C'est LE fichier de configuration de l'app — il n'est
volontairement **pas** sur GitHub, on le crée à la main sur le VPS.

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

# ─── URLs (⚠ HTTPS + ton domaine, identiques toutes les 3) ───────
APP_URL=https://assistant.symbiose-paysage.fr
NEXTAUTH_URL=https://assistant.symbiose-paysage.fr
NEXT_PUBLIC_API_URL=https://assistant.symbiose-paysage.fr

# ─── Réseau ──────────────────────────────────────────────────────
HEADSCALE_IP=127.0.0.1          # nginx reste interne (Caddy est l'entrée HTTPS)
VPN_IP=100.64.0.1               # IP de `tailscale ip -4` : Caddy s'y lie (443)

# ─── HTTPS : Caddy + DNS-01 OVH ──────────────────────────────────
APP_HOSTNAME=assistant.symbiose-paysage.fr
ACME_EMAIL=admin@symbiose-paysage.fr
OVH_ENDPOINT=ovh-eu
OVH_APPLICATION_KEY=⟨Application Key OVH⟩
OVH_APPLICATION_SECRET=⟨Application Secret OVH⟩
OVH_CONSUMER_KEY=⟨Consumer Key OVH⟩

# ─── Clés API (mêmes qu'en dev) ──────────────────────────────────
GROQ_API_KEY=⟨…⟩
LONGCAT_API_KEY=⟨…⟩
LONGCAT_BASE_URL=https://api.longcat.chat/openai/v1
GOOGLE_API_KEY=⟨…⟩
RESEND_API_KEY=⟨…⟩
RESEND_FROM_EMAIL=noreply@symbiose-paysage.fr

# ─── Agent navigateur ────────────────────────────────────────────
BROWSER_AGENT_ENABLED=true
BROWSER_LLM_MODEL=LongCat-2.0
BROWSER_ALLOWED_DOMAINS=www.myextrabat.com,manager.deytime.fr
BROWSER_READONLY=true
BROWSER_AGENT_MAX_STEPS=25
ANTHROPIC_API_KEY=placeholder

# ─── ADMIN DE L'APPLICATION (≠ compte Linux OVH) ─────────────────
FIRST_ADMIN_EMAIL=ton.email@symbiose-paysage.fr
```

> **Piège n°1 :** `NEXT_PUBLIC_API_URL` est **gelée au build** du frontend → mets-la correcte
> **avant** `./deploy.sh`. La changer plus tard ⇒ rebuild (`./deploy.sh`).

---

## Étape 9 — Construire et démarrer

*À quoi ça sert :* fabriquer les images et lancer **toute la pile**. Le script applique en plus
la base de données (migrations), crée ton compte admin, charge les skills, et Caddy récupère
le certificat HTTPS.

```bash
chmod +x deploy.sh
./deploy.sh
```

Détail : build (frontend avec la bonne URL **+ image Caddy personnalisée**, ~2-3 min la 1ʳᵉ fois)
→ démarrage → migrations SQL → **super_admin `FIRST_ADMIN_EMAIL`** → skills. Caddy demande alors
le certificat via l'API OVH (**~1-2 min**). Suis-le :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy
# attends "certificate obtained successfully" pour assistant.symbiose-paysage.fr
```

---

## Étape 10 — Premier accès + connexion

*À quoi ça sert :* rejoindre le VPN depuis **ton PC** et ouvrir l'application pour la toute
première connexion administrateur.

1. Sur ton PC, installe le **client tailscale** et connecte-le à ton Headscale :
   ```
   tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
   ```
2. Ouvre **`https://assistant.symbiose-paysage.fr`** → cadenas vert.
3. Entre `FIRST_ADMIN_EMAIL` → **« Recevoir le lien »**.
4. Lien magique par **email** (Resend) ; sinon `docker compose logs backend | grep "MAGIC LINK"`.
5. Clique → connecté en **super_admin**.

---

## Étape 11 — Donner l'accès aux employés

*À quoi ça sert :* faire entrer les collaborateurs. Chacun rejoint le VPN, puis reçoit un
compte applicatif que tu crées.

1. Génère-lui une clé : `sudo headscale preauthkeys create --user 1 --expiration 720h`.
2. Il installe le **client tailscale** et lance
   `tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey <sa-clé>`.
3. Il ouvre `https://assistant.symbiose-paysage.fr`.
4. Toi (super_admin) : crée son compte dans **Paramètres → Utilisateurs**, avec le bon rôle.

Hors VPN, `assistant.` pointe sur une IP privée : personne d'autre ne peut y accéder.

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

- [ ] DNS : `vpn.` → IP_PUBLIQUE ; `assistant.` → VPN_IP (`100.64.0.x`).
- [ ] `sudo systemctl status headscale` → **active** ; `https://vpn.symbiose-paysage.fr` répond.
- [ ] `tailscale ip -4` (VPS) = la valeur de `VPN_IP` dans `.env`.
- [ ] `.env` : 3 URLs = `https://assistant.symbiose-paysage.fr` ; `HEADSCALE_IP=127.0.0.1` ; token OVH rempli.
- [ ] `docker compose … logs caddy` → **certificat obtenu**.
- [ ] `docker compose ps` → tous `running`/`healthy`.
- [ ] Depuis un poste **du VPN** : `https://assistant.symbiose-paysage.fr` en cadenas vert, connexion super_admin OK.

---

## Dépannage HTTPS

- **Caddy ne démarre pas, « cannot assign requested address »** → le VPS n'est pas connecté
  au VPN (l'IP `VPN_IP` n'existe pas). Refais l'étape 5.5, vérifie `tailscale ip -4`.
- **« error getting certificate / DNS problem »** → token OVH incomplet (les 4 droits
  `GET/POST/PUT/DELETE` sur `/domain/zone/symbiose-paysage.fr/*`) ou mauvais `OVH_ENDPOINT`.
- **La page ne charge pas** → vérifie que `assistant.` pointe bien sur `VPN_IP` (pas l'IP
  publique) et que tu es connecté au VPN.
