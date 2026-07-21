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

---

## Architecture retenue

```
   Employés (client Tailscale connecté à TON Headscale)
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

## Étape 0 — Se connecter (compte OVH, pas de nouveau compte)

```bash
ssh ubuntu@IP_PUBLIQUE      # ou  ssh root@IP_PUBLIQUE  selon l'image OVH
```

Le compte `ubuntu` d'OVH a déjà `sudo`. Inutile d'en créer un autre.

---

## Étape 1 — Mettre à jour

```bash
sudo apt update && sudo apt upgrade -y
```

---

## Étape 2 — Pare-feu (UFW)

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp             # Headscale : challenge ACME (sur l'IP publique)
sudo ufw allow 443/tcp            # Headscale : coordination du VPN (sur l'IP publique)
sudo ufw allow in on tailscale0   # tout le trafic entrant DEPUIS le VPN (Caddy + app)
sudo ufw --force enable && sudo ufw status
```

---

## Étape 3 — Swap (2 Go)

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h
```

---

## Étape 4 — Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

**Déconnecte/reconnecte** (`exit` puis `ssh …`), puis vérifie :

```bash
docker --version && docker compose version
```

---

## Étape 5 — VPN Headscale

### 5.1 — 1er enregistrement DNS

| Type | Nom | Valeur |
|------|-----|--------|
| A | `vpn.symbiose-paysage.fr` | **IP_PUBLIQUE** du VPS |

### 5.2 — Installer Headscale

```bash
VER=0.23.0     # dernière version : github.com/juanfont/headscale/releases
wget -O headscale.deb "https://github.com/juanfont/headscale/releases/download/v${VER}/headscale_${VER}_linux_amd64.deb"
sudo apt install -y ./headscale.deb
```

### 5.3 — Configurer

```bash
sudo nano /etc/headscale/config.yaml
```

Renseigne (remplace `IP_PUBLIQUE` par l'IP réelle — Headscale doit écouter sur l'IP
**publique** pour laisser les ports du VPN libres à Caddy) :

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

### 5.4 — Utilisateur + clé de pré-authentification

```bash
sudo headscale users create symbiose
sudo headscale users list                          # note l'ID (souvent 1)
sudo headscale preauthkeys create --user 1 --reusable --expiration 24h
# → copie la clé "tskey-..." (VPS + employés)
```

### 5.5 — Connecter le VPS au VPN (obligatoire AVANT le déploiement)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
tailscale ip -4        # → VPN_IP du VPS, ex. 100.64.0.1
```

> Caddy va se lier à `VPN_IP:443` : cette IP doit **exister** (VPS connecté au VPN) avant
> l'étape 8, sinon Docker refusera de démarrer Caddy.

### 5.6 — 2ᵉ enregistrement DNS

| Type | Nom | Valeur |
|------|-----|--------|
| A | `assistant.symbiose-paysage.fr` | **VPN_IP** du VPS (ex. `100.64.0.1`) |

---

## Étape 6 — Token API OVH (pour le certificat HTTPS)

Caddy prouve à Let's Encrypt que tu contrôles le domaine en créant un enregistrement DNS
temporaire via l'API OVH. Il faut un token :

1. Va sur **https://api.ovh.com/createToken/** (connecte-toi avec le compte OVH du domaine).
2. **Rights** — ajoute ces 4 droits (remplace le domaine si besoin) :
   ```
   GET     /domain/zone/symbiose-paysage.fr/*
   POST    /domain/zone/symbiose-paysage.fr/*
   PUT     /domain/zone/symbiose-paysage.fr/*
   DELETE  /domain/zone/symbiose-paysage.fr/*
   ```
3. **Validity** : *Unlimited*.
4. **Create keys** → note **Application Key**, **Application Secret**, **Consumer Key**
   (ils vont dans `.env` à l'étape 8). L'endpoint est **`ovh-eu`**.

---

## Étape 7 — Cloner le projet

```bash
cd ~
git clone https://github.com/BenITNoaBenitez/SYMBIOSE.git      # login = pseudo, mot de passe = PAT
cd SYMBIOSE/symbiose-noa
```

---

## Étape 8 — Fichier `.env` de production

Secrets neufs (une fois) : `openssl rand -hex 32` ×4 (POSTGRES_PASSWORD, JWT_SECRET_KEY,
NEXTAUTH_SECRET, INGESTION_WEBHOOK_SECRET). Puis `nano .env` :

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

> **Piège n°1 :** `NEXT_PUBLIC_API_URL` est **gelée au build** du frontend → mets-la
> correcte **avant** `./deploy.sh`. La changer plus tard ⇒ rebuild.

---

## Étape 9 — Construire et démarrer

```bash
chmod +x deploy.sh
./deploy.sh
```

Le script : build (frontend avec la bonne URL **+ l'image Caddy personnalisée**, ~2-3 min la
1ʳᵉ fois) → démarrage → migrations SQL → **super_admin `FIRST_ADMIN_EMAIL`** → skills.
Caddy demande alors le certificat via l'API OVH (**~1-2 min** : création d'un TXT, propagation,
émission). Suis-le :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f caddy
# attends une ligne du type "certificate obtained successfully" pour assistant.symbiose-paysage.fr
```

---

## Étape 10 — Premier accès + connexion

1. Sur **ton PC** : installe le client Tailscale et connecte-le à ton Headscale :
   ```
   tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
   ```
2. Ouvre **`https://assistant.symbiose-paysage.fr`** → cadenas vert.
3. Entre `FIRST_ADMIN_EMAIL` → **« Recevoir le lien »**.
4. Lien magique par **email** (Resend) ; sinon `docker compose logs backend | grep "MAGIC LINK"`.
5. Clique → connecté en **super_admin**.

---

## Étape 11 — Accès des employés

1. Génère une clé : `sudo headscale preauthkeys create --user 1 --expiration 720h`.
2. L'employé installe le client Tailscale et lance
   `tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey <sa-clé>`.
3. Il ouvre `https://assistant.symbiose-paysage.fr`.
4. Toi (super_admin) : crée son compte applicatif dans **Paramètres → Utilisateurs**.

Hors VPN, `assistant.` pointe sur une IP privée : personne d'autre ne peut y accéder.

---

## Étape 12 — Maintenance

```bash
# Mise à jour :
cd ~/SYMBIOSE/symbiose-noa && git pull && ./deploy.sh

# Sauvegarde base (cron quotidien) :
docker compose exec -T postgres pg_dump -U noa_user symbiose_noa | gzip > ~/backup-$(date +%F).sql.gz

# Logs :
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

Le certificat HTTPS se **renouvelle tout seul** (Caddy). Redémarrages auto déjà configurés.

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
