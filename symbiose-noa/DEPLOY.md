# Déployer Symbiose sur un VPS Ubuntu — VPN privé + nom de domaine

Ce guide déploie **le projet Symbiose identique à celui du dépôt** sur un VPS Ubuntu,
accessible via un **VPN privé** (Tailscale) sous un **nom de domaine en HTTPS**.
Objectif : l'application n'est **jamais exposée sur l'Internet public** — seuls les
appareils du VPN (toi + les employés) y accèdent. C'est le bon choix pour des
**données client sensibles**.

> Tu peux tout faire à la main en suivant les étapes, ou utiliser le script
> `./deploy.sh` (étape 8) qui automatise build + base de données + skills.

---

## Architecture retenue

```
   Employés (Tailscale installé)
            │   (réseau chiffré, privé — jamais l'Internet public)
            ▼
   https://symbiose-vps.<ton-tailnet>.ts.net      ← ton "nom de domaine" + HTTPS auto
            │   (tailscale serve : termine le TLS)
            ▼
   nginx  (écoute sur 127.0.0.1:80)               ← reverse proxy déjà dans le projet
       ├── /            → frontend:3000  (Next.js)
       ├── /api/        → backend:8000   (FastAPI)
       └── /api/ws/     → backend:8000   (WebSocket du chat)
            │
   Réseau Docker interne (noa_network) :
   frontend · backend · browser-worker · postgres(pgvector)
```

Rien n'est publié sur Internet : le pare-feu n'ouvre que le SSH, nginx n'écoute que
sur `127.0.0.1`, et c'est **Tailscale** qui distribue l'accès (chiffré) + un vrai nom
de domaine `.ts.net` avec un certificat HTTPS valide, automatiquement.

---

## Ce dont tu as besoin

- Un **VPS Ubuntu 22.04 ou 24.04** — recommandé **VPS-2 (4 vCPU / 8 Go RAM)** minimum.
- L'**IP publique** du VPS + un accès **SSH** (root ou un mot de passe root).
- Un compte **Tailscale** gratuit — [tailscale.com](https://tailscale.com) (connexion via Google/GitHub/Microsoft).
- Un **jeton d'accès GitHub (PAT)** pour cloner le dépôt privé `BenITNoaBenitez/SYMBIOSE`.
- Les **clés API** (les mêmes qu'en dev, même client) : Groq, LongCat, Gemini (`GOOGLE_API_KEY`), Resend.

Chaque commande ci-dessous se tape **dans le terminal du VPS** (via SSH), sauf mention contraire.

---

## Étape 0 — Se connecter au VPS en SSH

Depuis ton PC (PowerShell ou un terminal) :

```bash
ssh root@TON_IP_VPS
```

La première fois, tape `yes` pour accepter l'empreinte. Entre le mot de passe root
(fourni par l'hébergeur). Tu es maintenant **sur le VPS**.

---

## Étape 1 — Mettre à jour + créer un utilisateur non-root

Travailler en root en permanence est risqué. On crée un utilisateur avec `sudo`.

```bash
apt update && apt upgrade -y
adduser noa                 # choisis un mot de passe, laisse le reste vide (Entrée)
usermod -aG sudo noa        # lui donne les droits d'administration
```

**Garde ta session root ouverte**, et dans un **2ᵉ terminal** teste la connexion :

```bash
ssh noa@TON_IP_VPS          # ça doit marcher avant de continuer
```

À partir de maintenant, on travaille avec `noa` (on préfixe les commandes admin par `sudo`).

### Durcir le SSH (recommandé)

```bash
sudo nano /etc/ssh/sshd_config
```

Mets ces deux lignes (décommente-les / modifie-les) :

```
PermitRootLogin no
PasswordAuthentication no      # ⚠ seulement si tu as configuré une clé SSH — sinon laisse "yes"
```

> **Débutant ?** Laisse `PasswordAuthentication yes` pour l'instant (tu te connectes par
> mot de passe). Passe à `no` plus tard, une fois une clé SSH en place. Ne te verrouille pas dehors.

```bash
sudo systemctl restart ssh
```

---

## Étape 2 — Pare-feu (UFW)

On n'ouvre **que le SSH**. L'application restera privée (accessible seulement par le VPN).

```bash
sudo ufw allow OpenSSH
sudo ufw --force enable
sudo ufw status
```

Les ports `80`, `3000`, `8000` **ne sont pas ouverts** au public : c'est voulu.
nginx n'écoutera que sur `127.0.0.1`, et Tailscale achemine le trafic sur son propre
réseau chiffré (interface `tailscale0`), sans passer par ces règles.

---

## Étape 3 — Swap (2 Go)

Une petite mémoire d'échange évite que le build (Next.js + Chromium) ne tue des conteneurs
par manque de RAM.

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
free -h                       # tu dois voir 2,0Gi de Swap
```

---

## Étape 4 — Installer Docker + Docker Compose

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker noa          # pouvoir lancer docker sans sudo
```

**Déconnecte-toi puis reconnecte-toi** (`exit` puis `ssh noa@IP`) pour que le groupe
`docker` prenne effet. Vérifie :

```bash
docker --version
docker compose version               # le plugin "compose" est inclus par get.docker.com
```

---

## Étape 5 — Installer Tailscale (le VPN + le nom de domaine)

C'est ce qui donne à la fois l'accès privé, le nom de domaine et le HTTPS.

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Une URL s'affiche → **ouvre-la dans ton navigateur** et connecte-toi : le VPS rejoint
ton réseau Tailscale (« tailnet »). Récupère son nom et son IP privée :

```bash
tailscale status               # montre le nom, ex. symbiose-vps
tailscale ip -4                # montre l'IP privée, ex. 100.101.102.103
```

### Activer le HTTPS + le nom de domaine (MagicDNS)

Dans la **console d'admin Tailscale** ([login.tailscale.com/admin/dns](https://login.tailscale.com/admin/dns)) :

1. Active **MagicDNS**.
2. Active **HTTPS Certificates**.

Ton nom de domaine privé sera de la forme :

```
symbiose-vps.<ton-tailnet>.ts.net
```

(le préfixe = le nom de la machine ; le suffixe `.ts.net` t'est attribué). C'est **ce nom**
qu'on met dans le `.env` à l'étape 7. Le certificat HTTPS est fourni automatiquement.

> **Tu veux TON propre domaine** (`symbiose.tonentreprise.fr`) ? C'est possible aussi —
> voir l'**Annexe A**. Le nom `.ts.net` suffit et fonctionne immédiatement ; commence par lui.

---

## Étape 6 — Cloner le projet (dépôt privé)

```bash
cd ~
git clone https://github.com/BenITNoaBenitez/SYMBIOSE.git
# Utilisateur : ton pseudo GitHub
# Mot de passe : COLLE TON JETON PAT (pas ton mot de passe GitHub)
cd SYMBIOSE/symbiose-noa          # ← le docker-compose est dans ce sous-dossier
ls                                # tu dois voir docker-compose.yml, deploy.sh, backend/, frontend/...
```

> Le fichier `.env` **n'est pas** dans le dépôt (il contient les secrets) : on le crée à l'étape 7.

---

## Étape 7 — Créer le fichier `.env` de production

Génère d'abord des secrets neufs (à faire tourner **une fois**, note les valeurs) :

```bash
openssl rand -hex 32     # → POSTGRES_PASSWORD
openssl rand -hex 32     # → JWT_SECRET_KEY
openssl rand -hex 32     # → NEXTAUTH_SECRET
openssl rand -hex 32     # → INGESTION_WEBHOOK_SECRET
```

Crée le fichier :

```bash
nano .env
```

Colle ce modèle et **remplace** les valeurs `⟨…⟩` (surtout le nom de domaine `.ts.net`) :

```ini
# ─── Base de données ─────────────────────────────────────────────
POSTGRES_DB=symbiose_noa
POSTGRES_USER=noa_user
POSTGRES_PASSWORD=⟨secret openssl n°1⟩
DATABASE_URL=postgresql+asyncpg://noa_user:⟨secret n°1⟩@postgres:5432/symbiose_noa

# ─── Sécurité applicative ────────────────────────────────────────
JWT_SECRET_KEY=⟨secret openssl n°2⟩
NEXTAUTH_SECRET=⟨secret openssl n°3⟩
INGESTION_WEBHOOK_SECRET=⟨secret openssl n°4⟩

# ─── URLs publiques (⚠ = ton nom de domaine Tailscale, en HTTPS) ─
# Ces 3 valeurs DOIVENT être identiques et pointer sur le nom .ts.net.
APP_URL=https://symbiose-vps.⟨ton-tailnet⟩.ts.net
NEXTAUTH_URL=https://symbiose-vps.⟨ton-tailnet⟩.ts.net
NEXT_PUBLIC_API_URL=https://symbiose-vps.⟨ton-tailnet⟩.ts.net

# nginx écoute sur la boucle locale ; c'est Tailscale serve qui expose en HTTPS.
HEADSCALE_IP=127.0.0.1

# ─── Clés API (les mêmes qu'en dev — même client) ────────────────
GROQ_API_KEY=⟨ta clé Groq⟩
LONGCAT_API_KEY=⟨ta clé LongCat⟩
LONGCAT_BASE_URL=https://api.longcat.chat/openai/v1
GOOGLE_API_KEY=⟨ta clé Gemini (base vectorielle)⟩
RESEND_API_KEY=⟨ta clé Resend⟩
RESEND_FROM_EMAIL=noreply@⟨ton-domaine-verifie⟩

# ─── Agent navigateur ────────────────────────────────────────────
BROWSER_AGENT_ENABLED=true
BROWSER_LLM_MODEL=LongCat-2.0
BROWSER_ALLOWED_DOMAINS=www.myextrabat.com,manager.deytime.fr
BROWSER_READONLY=true
BROWSER_AGENT_MAX_STEPS=25

# ─── (optionnel) Langfuse, Anthropic… ────────────────────────────
ANTHROPIC_API_KEY=placeholder

# ─── Utilisé UNIQUEMENT par deploy.sh pour créer ton compte admin ─
FIRST_ADMIN_EMAIL=ton.email@symbiose-paysage.fr
```

Enregistre : `Ctrl+O`, `Entrée`, puis `Ctrl+X`.

> **Le piège n°1 du déploiement** : `NEXT_PUBLIC_API_URL` est **gelée au moment du build**
> du frontend. Le `Dockerfile` et `docker-compose.prod.yml` ont été préparés pour l'injecter
> automatiquement au build — il suffit qu'elle soit correcte dans `.env` **avant** de builder.
> Si tu changes le domaine plus tard, il faut **rebuilder** le frontend (`./deploy.sh`).

---

## Étape 8 — Construire et démarrer (script automatique)

Le script fait tout : build des images (avec la bonne URL), démarrage, migrations SQL,
création de ton compte admin, catalogue de skills.

```bash
chmod +x deploy.sh
./deploy.sh
```

À la fin, `docker compose ps` doit montrer tous les services en `running`/`healthy`.
Le modèle spaCy français (anonymisation RGPD) est **déjà inclus** dans l'image backend :
aucun téléchargement manuel.

<details>
<summary>Équivalent 100 % manuel (si tu préfères comprendre chaque commande)</summary>

```bash
CO="docker compose -f docker-compose.yml -f docker-compose.prod.yml"
$CO up -d --build
# attends ~15 s que postgres soit prêt
for f in backend/database/migrations/[0-9]*.sql; do
  $CO exec -T postgres psql -U noa_user -d symbiose_noa -f "/migrations/$(basename "$f")"
done
$CO exec -T postgres psql -U noa_user -d symbiose_noa -c \
  "INSERT INTO users (email,name,role) VALUES ('ton.email@symbiose-paysage.fr','Administrateur','super_admin') \
   ON CONFLICT (email) DO UPDATE SET role='super_admin', actif=true;"
$CO exec -T backend sh -c "PYTHONPATH=. python scripts/seed_skills_catalogue.py"
```
</details>

---

## Étape 9 — Exposer l'application en HTTPS via Tailscale

nginx écoute sur `127.0.0.1:80`. On demande à Tailscale de le publier en HTTPS
sous le nom de domaine :

```bash
sudo tailscale serve --bg 80
sudo tailscale serve status
```

`serve status` doit afficher `https://symbiose-vps.<tailnet>.ts.net → http://127.0.0.1:80`.

> Selon la version de Tailscale, la syntaxe peut être
> `sudo tailscale serve --bg --https=443 http://127.0.0.1:80`.
> En cas de doute : `tailscale serve --help`. L'objectif est toujours :
> **HTTPS public (dans le VPN) → 127.0.0.1:80 (nginx)**.

---

## Étape 10 — Premier accès + première connexion

1. Sur **ton PC**, installe Tailscale ([tailscale.com/download](https://tailscale.com/download))
   et connecte-toi au **même compte** → ton PC rejoint le tailnet.
2. Ouvre `https://symbiose-vps.<ton-tailnet>.ts.net` — le cadenas HTTPS doit être vert.
3. Entre l'email `FIRST_ADMIN_EMAIL` (celui du `.env`) → **« Recevoir le lien »**.
4. Le lien magique arrive :
   - par **email** si Resend est configuré et le domaine d'envoi vérifié ;
   - sinon lis-le dans les logs : `docker compose logs backend | grep "MAGIC LINK"`.
5. Clique le lien → tu es connecté en **super_admin**.

---

## Étape 11 — Donner l'accès aux employés

Pour chaque employé :

1. Il installe **Tailscale** sur son poste et se connecte à **ton tailnet** (invitation
   depuis la console admin Tailscale → *Users* → *Invite*).
2. Il ouvre `https://symbiose-vps.<ton-tailnet>.ts.net`.
3. Toi (super_admin) tu crées son compte dans l'onglet **Paramètres → Utilisateurs**,
   avec le bon rôle. Il se connecte ensuite par lien magique.

Personne hors du tailnet ne peut atteindre l'application.

---

## Étape 12 — Maintenance

**Mettre à jour** (récupérer une nouvelle version du projet) :

```bash
cd ~/SYMBIOSE/symbiose-noa
git pull
./deploy.sh                    # rebuild + redémarre + rejoue les migrations
```

**Sauvegarder la base** (à mettre dans un `cron` quotidien) :

```bash
docker compose exec -T postgres pg_dump -U noa_user symbiose_noa | gzip > ~/backup-$(date +%F).sql.gz
```

**Voir les logs** :

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f backend
```

**Redémarrages automatiques** : déjà configurés (`restart: unless-stopped`) — les services
repartent tout seuls après un reboot du VPS.

---

## Checklist finale

- [ ] `ufw status` → seul **OpenSSH** est autorisé.
- [ ] `tailscale status` → le VPS est **connecté** au tailnet.
- [ ] `.env` : les 3 URLs (`APP_URL`, `NEXTAUTH_URL`, `NEXT_PUBLIC_API_URL`) = le nom `.ts.net` en **https**, identiques.
- [ ] `HEADSCALE_IP=127.0.0.1` dans `.env`.
- [ ] `docker compose ps` → tous les services `running`/`healthy`.
- [ ] `tailscale serve status` → HTTPS → `127.0.0.1:80`.
- [ ] Connexion réussie en super_admin depuis un poste **du VPN**.

---

## Annexe A — Utiliser ton propre nom de domaine

Deux options si tu veux `symbiose.tonentreprise.fr` plutôt que le nom `.ts.net` :

- **Simple** — dans la console Tailscale, garde l'accès VPN et crée un enregistrement DNS
  `CNAME symbiose.tonentreprise.fr → symbiose-vps.<tailnet>.ts.net`. L'accès reste privé
  (il faut être sur le VPN pour résoudre l'IP).
- **Avec ton propre certificat** — remplace `tailscale serve` par **Caddy** en frontal
  (`symbiose.tonentreprise.fr { reverse_proxy 127.0.0.1:80 }`) et obtiens le certificat via
  un **challenge DNS-01** (nécessite l'API DNS de ton hébergeur de domaine). Mets alors les
  3 URLs du `.env` sur `https://symbiose.tonentreprise.fr` et **rebuild** (`./deploy.sh`).

## Annexe B — VPN 100 % auto-hébergé (Headscale)

Si tu ne veux **aucune dépendance** au service Tailscale, tu peux héberger ton propre
serveur de coordination **Headscale** (d'où le nom de la variable `HEADSCALE_IP`). C'est
plus de travail (gestion des clés, du DNS et des certificats à ta charge, pas de `.ts.net`
ni de certificat automatique). Recommandé seulement si la contrainte « rien chez un tiers »
est ferme ; sinon Tailscale gratuit couvre parfaitement une PME.
