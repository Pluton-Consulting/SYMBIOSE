# Déployer Symbiose sur un VPS Ubuntu — VPN Headscale + nom de domaine

Ce guide déploie **le projet Symbiose identique à celui du dépôt** sur un VPS Ubuntu,
accessible via un **VPN privé auto-hébergé (Headscale)** sous un **nom de domaine**.
L'application n'est **jamais exposée sur l'Internet public** — seuls les appareils
connectés au VPN (toi + les employés) y accèdent. C'est le bon choix pour des
**données client sensibles**, et c'est **100 % gratuit / sans dépendance** à un tiers.

> **Deux « admin » à ne pas confondre** (voir §1 et §7) :
> - l'**admin du serveur** = le compte Linux fourni par OVH (`ubuntu`/`root`) qui gère la machine ;
> - l'**admin de l'application** = ton login *dans* NOA (par email/lien magique). Ce sont deux couches différentes.

---

## Architecture retenue

```
   Employés (client Tailscale connecté à TON Headscale)
            │   (tunnel WireGuard chiffré, privé — jamais l'Internet public)
            ▼
   assistant.symbiose-paysage.fr   → IP VPN du VPS (100.64.0.x)   ← ton nom de domaine
            │
   nginx  (écoute sur HEADSCALE_IP = l'IP VPN du VPS, port 80)     ← reverse proxy déjà dans le projet
       ├── /            → frontend:3000  (Next.js)
       ├── /api/        → backend:8000   (FastAPI)
       └── /api/ws/     → backend:8000   (WebSocket du chat)
            │
   Réseau Docker interne : frontend · backend · browser-worker · postgres(pgvector)

   ── En parallèle, sur le même VPS ──
   vpn.symbiose-paysage.fr → IP PUBLIQUE du VPS → serveur Headscale (coordination du VPN)
```

Deux sous-domaines de `symbiose-paysage.fr` :
- **`vpn.`** → IP **publique** → le serveur Headscale (seule chose publique ; c'est juste
  la coordination du VPN, durcie par conception, avec son propre certificat Let's Encrypt).
- **`assistant.`** → IP **VPN** (`100.64.0.x`, privée) → l'application. Résolue partout mais
  **routable seulement depuis le VPN**. Le trafic est chiffré par WireGuard.

---

## Ce dont tu as besoin

- Un **VPS Ubuntu 22.04/24.04** — recommandé **VPS-2 (4 vCPU / 8 Go)** minimum.
- L'**IP publique** du VPS + l'**accès SSH** fourni par OVH (compte `ubuntu` ou `root`).
- La main sur le **DNS de `symbiose-paysage.fr`** (pour créer 2 enregistrements A).
- Un **jeton GitHub (PAT)** pour cloner le dépôt privé `BenITNoaBenitez/SYMBIOSE`.
- Les **clés API** (les mêmes qu'en dev) : Groq, LongCat, Gemini (`GOOGLE_API_KEY`), Resend.

---

## Étape 0 — Se connecter au VPS (compte OVH, pas de nouveau compte)

Utilise **le compte que OVH t'a donné** — inutile d'en créer un autre :

```bash
ssh ubuntu@TON_IP_VPS      # ou  ssh root@TON_IP_VPS  selon l'image OVH
```

Le compte `ubuntu` d'OVH a déjà les droits `sudo`. (Si tu es en `root`, les commandes
`sudo` ci-dessous fonctionnent aussi telles quelles.)

---

## Étape 1 — Mettre à jour

```bash
sudo apt update && sudo apt upgrade -y
```

> **Durcissement SSH (optionnel, plus tard).** Tu peux ajouter une clé SSH et désactiver
> le mot de passe (`/etc/ssh/sshd_config` → `PasswordAuthentication no`) une fois à l'aise.
> Ne le fais pas maintenant si tu risques de te verrouiller dehors.

---

## Étape 2 — Pare-feu (UFW)

On ouvre le **SSH** + les ports **80/443** (nécessaires au serveur Headscale et à son
certificat). L'application, elle, n'est jamais ouverte au public : elle vit sur l'interface
VPN `tailscale0`.

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp          # Headscale (ACME Let's Encrypt)
sudo ufw allow 443/tcp         # Headscale (coordination du VPN)
sudo ufw allow in on tailscale0   # tout le trafic entrant DEPUIS le VPN (l'app)
sudo ufw --force enable
sudo ufw status
```

---

## Étape 3 — Swap (2 Go)

Évite qu'un build (Next.js + Chromium) ne tue des conteneurs par manque de RAM.

```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                        # doit montrer 2,0Gi de Swap
```

---

## Étape 4 — Installer Docker

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER    # lancer docker sans sudo
```

**Déconnecte-toi / reconnecte-toi** (`exit` puis `ssh ubuntu@IP`) pour activer le groupe, puis :

```bash
docker --version && docker compose version
```

---

## Étape 5 — Installer et configurer Headscale (le serveur VPN)

### 5.1 — Enregistrements DNS (chez ton registrar `symbiose-paysage.fr`)

Crée d'abord :

| Type | Nom | Valeur |
|------|-----|--------|
| A | `vpn.symbiose-paysage.fr` | **IP publique** du VPS |

(le 2ᵉ enregistrement `assistant.` viendra à l'étape 5.5, une fois l'IP VPN connue.)

### 5.2 — Installer Headscale

```bash
VER=0.23.0     # vérifie la dernière version sur github.com/juanfont/headscale/releases
wget -O headscale.deb "https://github.com/juanfont/headscale/releases/download/v${VER}/headscale_${VER}_linux_amd64.deb"
sudo apt install -y ./headscale.deb
```

### 5.3 — Configurer

```bash
sudo nano /etc/headscale/config.yaml
```

Renseigne au minimum (adapte selon ta version — les clés existent déjà dans le fichier) :

```yaml
server_url: https://vpn.symbiose-paysage.fr
listen_addr: 0.0.0.0:443

# Certificat HTTPS automatique du serveur Headscale (public) :
tls_letsencrypt_hostname: vpn.symbiose-paysage.fr
tls_letsencrypt_challenge_type: HTTP-01
tls_letsencrypt_listen: ":80"

prefixes:
  v4: 100.64.0.0/10

dns:                          # (section « dns_config » sur les versions < 0.23)
  magic_dns: true
  base_domain: symbiose.internal
```

Démarre :

```bash
sudo systemctl enable --now headscale
sudo systemctl status headscale --no-pager     # doit être "active (running)"
```

### 5.4 — Créer un utilisateur + une clé de pré-authentification

```bash
sudo headscale users create symbiose
sudo headscale users list                       # note l'ID (souvent 1)
sudo headscale preauthkeys create --user 1 --reusable --expiration 24h
# → copie la clé affichée (tskey-...) pour l'étape suivante et pour les employés
```

### 5.5 — Connecter le VPS lui-même au VPN

L'application (nginx) doit écouter sur l'IP VPN du VPS → le VPS doit être membre du VPN.
On installe le **client** Tailscale (le logiciel client est open-source ; il se connecte à
TON Headscale, pas au service Tailscale) :

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
tailscale ip -4        # → l'IP VPN du VPS, ex. 100.64.0.1  → c'est HEADSCALE_IP
```

Ajoute maintenant le 2ᵉ enregistrement DNS :

| Type | Nom | Valeur |
|------|-----|--------|
| A | `assistant.symbiose-paysage.fr` | **IP VPN** du VPS (ex. `100.64.0.1`) |

---

## Étape 6 — Cloner le projet (dépôt privé)

```bash
cd ~
git clone https://github.com/BenITNoaBenitez/SYMBIOSE.git
# Utilisateur : ton pseudo GitHub · Mot de passe : COLLE TON JETON PAT
cd SYMBIOSE/symbiose-noa          # ← le docker-compose est dans ce sous-dossier
```

---

## Étape 7 — Créer le fichier `.env` de production

Génère des secrets neufs (une seule fois, note-les) :

```bash
openssl rand -hex 32     # → POSTGRES_PASSWORD
openssl rand -hex 32     # → JWT_SECRET_KEY
openssl rand -hex 32     # → NEXTAUTH_SECRET
openssl rand -hex 32     # → INGESTION_WEBHOOK_SECRET
```

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

# ─── URLs (⚠ = ton nom de domaine assistant., identiques toutes les 3) ─
# HTTP suffit : le trafic passe déjà chiffré dans le tunnel WireGuard du VPN.
APP_URL=http://assistant.symbiose-paysage.fr
NEXTAUTH_URL=http://assistant.symbiose-paysage.fr
NEXT_PUBLIC_API_URL=http://assistant.symbiose-paysage.fr

# nginx écoute sur l'IP VPN du VPS (celle de `tailscale ip -4`).
HEADSCALE_IP=100.64.0.1

# ─── Clés API (les mêmes qu'en dev — même client) ────────────────
GROQ_API_KEY=⟨ta clé Groq⟩
LONGCAT_API_KEY=⟨ta clé LongCat⟩
LONGCAT_BASE_URL=https://api.longcat.chat/openai/v1
GOOGLE_API_KEY=⟨ta clé Gemini⟩
RESEND_API_KEY=⟨ta clé Resend⟩
RESEND_FROM_EMAIL=noreply@symbiose-paysage.fr

# ─── Agent navigateur ────────────────────────────────────────────
BROWSER_AGENT_ENABLED=true
BROWSER_LLM_MODEL=LongCat-2.0
BROWSER_ALLOWED_DOMAINS=www.myextrabat.com,manager.deytime.fr
BROWSER_READONLY=true
BROWSER_AGENT_MAX_STEPS=25
ANTHROPIC_API_KEY=placeholder

# ─── ADMIN DE L'APPLICATION (≠ compte Linux OVH) ─────────────────
# Ton login DANS l'assistant NOA. Crée le 1er super_admin (obligatoire pour
# ouvrir l'appli web). Utilisé uniquement par deploy.sh.
FIRST_ADMIN_EMAIL=ton.email@symbiose-paysage.fr
```

`Ctrl+O`, `Entrée`, `Ctrl+X`.

> **Piège n°1 :** `NEXT_PUBLIC_API_URL` est **gelée au build** du frontend. Elle doit être
> correcte **avant** `./deploy.sh`. Changer d'URL plus tard ⇒ rebuild (`./deploy.sh`).

---

## Étape 8 — Construire et démarrer

```bash
chmod +x deploy.sh
./deploy.sh
```

Le script : build (avec la bonne URL) → démarrage → migrations SQL → **création du
super_admin `FIRST_ADMIN_EMAIL`** → catalogue de skills. Le modèle spaCy (anonymisation
RGPD) est **déjà dans l'image backend**. À la fin, `docker compose ps` = tout `running`.

<details>
<summary>Rappel — l'admin appli créé ici n'est PAS un compte Linux</summary>

`deploy.sh` insère une ligne dans la table `users` de la base :
`INSERT INTO users (email,name,role) VALUES ('ton.email@…','Administrateur','super_admin')`.
C'est ton identité **dans NOA** (connexion par lien magique), sans aucun rapport avec le
compte `ubuntu`/`root` du serveur.
</details>

---

## Étape 9 — Premier accès + première connexion

1. Sur **ton PC**, installe le client Tailscale ([tailscale.com/download](https://tailscale.com/download))
   et connecte-le à **ton Headscale** :
   ```
   tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey tskey-VOTRE_CLE
   ```
2. Ouvre `http://assistant.symbiose-paysage.fr`.
3. Entre l'email `FIRST_ADMIN_EMAIL` → **« Recevoir le lien »**.
4. Le lien magique arrive par **email** (Resend configuré) ; sinon lis-le dans les logs :
   `docker compose logs backend | grep "MAGIC LINK"`.
5. Clique → connecté en **super_admin**.

---

## Étape 10 — Donner l'accès aux employés

Pour chaque employé :

1. Génère-lui une clé : `sudo headscale preauthkeys create --user 1 --expiration 720h`.
2. Il installe le client Tailscale et lance
   `tailscale up --login-server https://vpn.symbiose-paysage.fr --authkey <sa-clé>`.
3. Il ouvre `http://assistant.symbiose-paysage.fr`.
4. Toi (super_admin) tu crées son compte applicatif dans **Paramètres → Utilisateurs**,
   avec le bon rôle. Il se connecte ensuite par lien magique.

Hors du VPN, personne ne peut atteindre l'application (le nom `assistant.` pointe sur une IP privée).

---

## Étape 11 — Maintenance

```bash
# Mettre à jour le projet :
cd ~/SYMBIOSE/symbiose-noa && git pull && ./deploy.sh

# Sauvegarde base (à mettre en cron quotidien) :
docker compose exec -T postgres pg_dump -U noa_user symbiose_noa | gzip > ~/backup-$(date +%F).sql.gz

# Logs :
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

Redémarrages automatiques déjà configurés (`restart: unless-stopped`).

---

## Checklist finale

- [ ] `sudo systemctl status headscale` → **active (running)**.
- [ ] `tailscale status` (sur le VPS) → connecté à `vpn.symbiose-paysage.fr`.
- [ ] DNS : `vpn.` → IP publique ; `assistant.` → IP VPN (`100.64.0.x`).
- [ ] `.env` : les 3 URLs = `http://assistant.symbiose-paysage.fr` ; `HEADSCALE_IP` = l'IP `tailscale ip -4`.
- [ ] `docker compose ps` → tous `running`/`healthy`.
- [ ] Connexion super_admin réussie depuis un poste **du VPN**.

---

## Annexe — Le cadenas HTTPS sur l'application (optionnel)

Le VPN chiffre déjà tout ; le HTTPS applicatif est un « plus » (padlock, cookies « secure »).
Si tu le veux sur `assistant.symbiose-paysage.fr` :

- Installe **Caddy** sur le VPS et fais-lui obtenir un certificat par **challenge DNS-01**
  (Headscale ne fournit pas de certif pour l'app car son IP est privée → HTTP-01 impossible).
  Caddy réclame l'**API DNS de ton registrar** (ex. module `caddy-dns/ovh`).
- Caddy écoute sur l'IP VPN en 443 et fait `reverse_proxy` vers nginx (`127.0.0.1:80`).
- Passe alors les 3 URLs du `.env` en `https://…` et **rebuild** (`./deploy.sh`).

Tant que ce n'est pas en place, **HTTP sur le VPN reste sûr** (tunnel WireGuard chiffré).
