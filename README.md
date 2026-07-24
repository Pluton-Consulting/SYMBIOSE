# Symbiose — Assistant IA interne

Assistant IA interne de **Symbiose Paysage** (bureau d'études paysage). Multi-agents,
mémoire d'entreprise en RAG, **zéro donnée personnelle envoyée aux LLM externes**
(anonymisation avant appel), accès **privé via VPN auto-hébergé**.

## Ce que fait l'assistant
- Recherche dans la mémoire d'entreprise (devis, CCTP, plans, mails, factures…) via **RAG** (pgvector).
- Répond en français, cite ses sources, n'invente jamais de donnée (montant, date, référence).
- **Agent navigateur** (browser-use) : navigation web autonome, login sur apps, extraction → RAG,
  avec **validation humaine** obligatoire pour toute action modifiante.
- **RGPD *fail-closed*** : la requête et les documents sont masqués (NER spaCy) avant l'appel LLM,
  puis réhydratés dans la réponse ; si l'anonymiseur est indisponible, aucun appel externe n'est fait.
- **Isolation par profil** : RBAC par fonctionnalité + RLS Postgres (conversations/KPI propres à chaque utilisateur).

## Stack
| Couche | Techno |
|---|---|
| Backend | FastAPI · LangGraph / LangChain · cascade LLM (OpenRouter → Groq → Ollama) · tracing Langfuse |
| Frontend | Next.js 14 (App Router, standalone) · NextAuth v5 (lien magique) |
| Données | PostgreSQL + **pgvector** (RAG) · Row Level Security |
| Agent navigateur | `browser-worker` (browser-use) + file de validation humaine (HITL) |
| Infra | Docker Compose · nginx · **VPN Headscale auto-hébergé** (app en HTTP derrière le tunnel) |

## Structure du dépôt
```
.
├── symbiose-noa/                # le projet
│   ├── backend/                 # FastAPI · agents LangGraph · RAG · sécurité (RBAC/RLS/anonymisation)
│   ├── frontend/                # Next.js 14 + NextAuth
│   ├── browser-worker/          # agent navigateur (browser-use) + HITL
│   ├── nginx/                   # reverse proxy
│   ├── docker-compose*.yml      # base · prod · dev · langfuse
│   ├── deploy.sh                # déploiement (build + migrations suivies + super_admin + restart nginx)
│   ├── backup.sh                # sauvegarde base + .env (rétention 14 j)
│   ├── DEPLOY.md                # runbook VPS générique (VPN Headscale + HTTP)
│   ├── SETUP.md                 # mise en route détaillée
│   └── .env.example             # gabarit de configuration
└── symbiose_infra_prompt.md     # note d'architecture
```

## Démarrage rapide
```bash
cd symbiose-noa
cp .env.example .env          # renseigner les valeurs (secrets, clés API, URLs)
docker network create noa_network
docker compose up -d --build
```
- **Déploiement sur un VPS** (VPN + HTTP) : voir [`symbiose-noa/DEPLOY.md`](symbiose-noa/DEPLOY.md).
- **Mise en route détaillée** (OAuth, Langfuse, migrations, pgvector) : voir [`symbiose-noa/SETUP.md`](symbiose-noa/SETUP.md).

## Branches
- La branche **par défaut** du dépôt → production (le VPS suit cette branche).
- **`dev`** → développement (mises à jour testées avant passage en prod).

## Sécurité
- **Secrets hors dépôt** : `.env`, `prod.env`, `backend/secrets/` sont **gitignorés** — ne jamais committer de clé.
  Chaque déploiement dépose son propre `.env` sur le VPS (cf. `DEPLOY.md`).
- **Aucune PII vers les LLM externes** (anonymisation NER *fail-closed*).
- **Accès privé** : l'application n'est jamais exposée sur l'Internet public — servie en **HTTP derrière le VPN**
  (tunnel WireGuard chiffré via Headscale).

---
Développé par **Pluton Consulting** pour Symbiose Paysage.
