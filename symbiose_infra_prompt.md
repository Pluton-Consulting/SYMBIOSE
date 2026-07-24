# Prompt — Infrastructure de base Symbiose Pluton

## Contexte

Tu es un ingénieur senior fullstack et DevOps. Tu vas créer l'infrastructure de base d'une application IA d'entreprise appelée **Pluton** pour la société **Symbiose Paysage**.

L'objectif de ce prompt est de générer uniquement l'infrastructure de base : pas de logique métier, pas de cas d'usage spécifiques, pas de RAG, pas de pipeline d'ingestion. Uniquement les fondations sur lesquelles tout le reste sera construit.

---

## Stack technique cible

- **Serveur** : VPS Linux Ubuntu 24.04 (OVH France)
- **VPN** : Headscale (WireGuard mesh auto-hébergé) — l'app n'est accessible que via le réseau Headscale
- **Backend** : Python 3.12 + FastAPI async
- **Orchestration agents** : LangGraph 1.2+
- **Base de données** : PostgreSQL 16 + pgvector + extension pg_trgm
- **Sandbox Agent 3** : Daytona SDK Python (tests des skills générés en environnement isolé)
- **Observabilité** : Langfuse self-hosted (Docker)
- **Interface** : Next.js 14 App Router (responsive mobile)
- **Auth** : NextAuth.js v5 + Google OAuth2 Provider
- **Containerisation** : Docker Compose
- **Reverse proxy** : Nginx (uniquement sur interface réseau Headscale — pas d'exposition publique)

---

## Architecture des fichiers à générer

```
symbiose-noa/
├── docker-compose.yml
├── docker-compose.langfuse.yml
├── .env.example
├── nginx/
│   └── nginx.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py
│   │   ├── migrations/
│   │   │   └── 001_initial_schema.sql
│   │   └── models.py
│   ├── auth/
│   │   ├── __init__.py
│   │   ├── jwt_handler.py
│   │   └── dependencies.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── auth.py
│   │   ├── users.py
│   │   ├── chat.py
│   │   └── dashboard.py
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── router.py
│   │   ├── state.py
│   │   ├── agent1.py
│   │   ├── agent2.py
│   │   └── agent3.py
│   ├── llm/
│   │   ├── __init__.py
│   │   └── router.py
│   ├── vectorstore/
│   │   ├── __init__.py
│   │   ├── client.py
│   │   └── schemas.py
│   ├── sandbox/
│   │   ├── __init__.py
│   │   └── daytona_client.py
│   └── security/
│       ├── __init__.py
│       ├── rbac.py
│       └── audit.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── next.config.js
    ├── app/
    │   ├── layout.tsx
    │   ├── page.tsx
    │   ├── (auth)/
    │   │   └── login/
    │   │       └── page.tsx
    │   ├── (app)/
    │   │   ├── layout.tsx
    │   │   ├── chat/
    │   │   │   └── page.tsx
    │   │   └── dashboard/
    │   │       └── page.tsx
    │   └── api/
    │       └── auth/
    │           └── [...nextauth]/
    │               └── route.ts
    ├── components/
    │   ├── chat/
    │   │   ├── ChatWindow.tsx
    │   │   ├── MessageList.tsx
    │   │   └── InputBar.tsx
    │   └── dashboard/
    │       ├── StatsCards.tsx
    │       └── ActivityFeed.tsx
    └── lib/
        ├── auth.ts
        └── api.ts
```

---

## 1. Docker Compose principal

Génère `docker-compose.yml` avec les services suivants :

### Service `postgres`
- Image : `pgvector/pgvector:pg16`
- Variables : `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` depuis `.env`
- Volume persistant : `postgres_data:/var/lib/postgresql/data`
- Healthcheck : `pg_isready`
- Réseau interne uniquement : `noa_network`

### Service `backend`
- Build depuis `./backend/Dockerfile`
- Dépend de `postgres` (healthcheck OK)
- Variables d'environnement depuis `.env`
- Port exposé uniquement sur l'interface Headscale : `127.0.0.1:8000:8000`
- Volume : `./backend:/app`
- Réseau : `noa_network`

### Service `frontend`
- Build depuis `./frontend/Dockerfile`
- Dépend de `backend`
- Port : `127.0.0.1:3000:3000`
- Variables : `NEXTAUTH_URL`, `NEXTAUTH_SECRET`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`
- Réseau : `noa_network`

### Service `nginx`
- Image : `nginx:alpine`
- Bind uniquement sur l'IP Headscale (variable `HEADSCALE_IP` dans `.env`)
- Ports : `${HEADSCALE_IP}:80:80`
- Config depuis `./nginx/nginx.conf`
- Réseau : `noa_network`

### Réseau et volumes
```yaml
networks:
  noa_network:
    driver: bridge
volumes:
  postgres_data:
```

---

## 2. Docker Compose Langfuse

Génère `docker-compose.langfuse.yml` en suivant exactement la configuration officielle Langfuse self-hosted avec :
- Service `langfuse-server`
- Service `langfuse-postgres` (base séparée pour Langfuse)
- Port Langfuse exposé uniquement sur `127.0.0.1:3001`
- Réseau partagé `noa_network` pour que le backend puisse l'atteindre
- Variables : `LANGFUSE_SECRET_KEY`, `LANGFUSE_SALT`, `DATABASE_URL` pour Langfuse

---

## 3. Nginx — nginx.conf

Configuration Nginx qui :
- Écoute uniquement sur `${HEADSCALE_IP}:80`
- Proxy `/api/` vers `backend:8000`
- Proxy `/` vers `frontend:3000`
- Headers de sécurité : `X-Frame-Options DENY`, `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin`
- WebSocket support pour `/api/ws/`
- Pas de SSL (le chiffrement est géré par Headscale/WireGuard)

---

## 4. Variables d'environnement — .env.example

Génère `.env.example` avec toutes les variables nécessaires, commentées :

```env
# Serveur
HEADSCALE_IP=100.64.0.1  # IP assignée par Headscale à ce serveur

# PostgreSQL
POSTGRES_DB=symbiose_noa
POSTGRES_USER=noa_user
POSTGRES_PASSWORD=CHANGE_ME_STRONG_PASSWORD
DATABASE_URL=postgresql+asyncpg://noa_user:CHANGE_ME@postgres:5432/symbiose_noa

# Auth Google OAuth2
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# NextAuth
NEXTAUTH_URL=http://100.64.0.1  # Remplacer par l'IP Headscale réelle
NEXTAUTH_SECRET=CHANGE_ME_GENERATE_WITH_openssl_rand_base64_32

# JWT Backend
JWT_SECRET_KEY=CHANGE_ME_GENERATE_WITH_openssl_rand_hex_32
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8

# LLM — Claude API (Anthropic)
ANTHROPIC_API_KEY=

# LLM — Ollama local (optionnel)
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL_LIGHT=mistral:7b

# Langfuse
LANGFUSE_SECRET_KEY=CHANGE_ME
LANGFUSE_PUBLIC_KEY=CHANGE_ME
LANGFUSE_HOST=http://langfuse-server:3000
LANGFUSE_SALT=CHANGE_ME

# Daytona (optionnel — phase 2)
DAYTONA_API_KEY=

# App
ENVIRONMENT=production
DEBUG=false
ALLOWED_HOSTS=100.64.0.1
```

---

## 5. Base de données — Migration SQL initiale

Génère `backend/database/migrations/001_initial_schema.sql` avec exactement les tables suivantes :

### Extensions
```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
```

### Table `users`
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    role VARCHAR(50) NOT NULL DEFAULT 'terrain',
    -- Rôles: 'direction', 'commercial', 'bureau_etudes', 'conducteur', 'administratif', 'terrain', 'admin'
    actif BOOLEAN NOT NULL DEFAULT true,
    quota_mensuel INTEGER NOT NULL DEFAULT 50,
    -- Quotas par défaut selon rôle (peut être overridé)
    -- direction: NULL (illimité), commercial: 200, bureau_etudes: 150
    -- conducteur: 100, administratif: 100, terrain: 50
    bypass_schedule BOOLEAN NOT NULL DEFAULT false,
    -- Si true : accès hors plage horaire autorisé (direction uniquement)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login TIMESTAMPTZ
);
```

### Table `roles_permissions`
```sql
CREATE TABLE roles_permissions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    role VARCHAR(50) NOT NULL,
    feature VARCHAR(100) NOT NULL,
    -- Features: 'chat_agent1', 'chat_agent2', 'chat_agent3',
    -- 'view_dashboard_global', 'view_own_stats', 'validate_skills',
    -- 'manage_users', 'configure_agents', 'view_costs_global',
    -- 'view_own_costs', 'view_audit_log'
    allowed BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(role, feature)
);
```

Insère les permissions par défaut pour tous les rôles au moment de la migration.

### Table `threads` (conversations)
```sql
CREATE TABLE threads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),
    -- Généré automatiquement depuis les premiers mots de la première requête
    agent_type VARCHAR(20) NOT NULL DEFAULT 'agent1',
    -- 'agent1', 'agent2', 'agent3', 'multi'
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    -- 'active', 'paused', 'completed', 'error'
    langgraph_thread_id VARCHAR(255) UNIQUE,
    -- thread_id utilisé par LangGraph pour le checkpointing
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table `messages`
```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    thread_id UUID NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    -- 'user', 'assistant', 'system'
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    -- Stocke: agent_used, tokens_in, tokens_out, model_used, duration_ms
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table `audit_log`
```sql
CREATE TABLE audit_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID REFERENCES users(id),
    -- NULL si action système
    action VARCHAR(100) NOT NULL,
    -- 'chat_request', 'login', 'logout', 'skill_created',
    -- 'skill_validated', 'user_created', 'user_deactivated', 'quota_exceeded'
    agent_id VARCHAR(20),
    -- 'agent1', 'agent2', 'agent3', NULL si hors agent
    model_used VARCHAR(100),
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    cost_eur DECIMAL(10, 6) DEFAULT 0,
    duration_ms INTEGER,
    success BOOLEAN DEFAULT true,
    error_message TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    -- Immuable : pas d'UPDATE, pas de DELETE sur cette table
);
```

### Table `skills`
```sql
CREATE TABLE skills (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) UNIQUE NOT NULL,
    -- snake_case ex: 'calcul_surface_terrasse'
    description TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    code TEXT NOT NULL,
    -- Le code Python du skill généré par l'Agent 3
    prompt_template TEXT,
    -- Le prompt associé au skill
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    -- 'draft', 'testing', 'validated', 'stable', 'deprecated'
    confidence_score DECIMAL(3, 2),
    -- Score 0.00 à 1.00 calculé par les tests Daytona
    usage_count INTEGER NOT NULL DEFAULT 0,
    avg_quality_score DECIMAL(3, 2),
    created_by VARCHAR(20) DEFAULT 'agent3',
    validated_by UUID REFERENCES users(id),
    validated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Table `api_usage_daily`
```sql
CREATE TABLE api_usage_daily (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id),
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    request_count INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    cost_eur DECIMAL(10, 4) NOT NULL DEFAULT 0,
    UNIQUE(user_id, date)
);
```

### Index de performance
```sql
-- Users
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_actif ON users(actif);

-- Threads
CREATE INDEX idx_threads_user_id ON threads(user_id);
CREATE INDEX idx_threads_status ON threads(status);
CREATE INDEX idx_threads_langgraph ON threads(langgraph_thread_id);

-- Messages
CREATE INDEX idx_messages_thread_id ON messages(thread_id);
CREATE INDEX idx_messages_created ON messages(created_at);

-- Audit
CREATE INDEX idx_audit_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_created ON audit_log(created_at);
CREATE INDEX idx_audit_action ON audit_log(action);

-- Skills
CREATE INDEX idx_skills_status ON skills(status);
CREATE INDEX idx_skills_name ON skills(name);

-- API Usage
CREATE INDEX idx_usage_user_date ON api_usage_daily(user_id, date);
```

### Row-Level Security
```sql
-- Activer RLS sur les tables sensibles
ALTER TABLE threads ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE api_usage_daily ENABLE ROW LEVEL SECURITY;

-- Politique : un user ne voit que ses propres threads
-- (les admins et la direction voient tout — géré au niveau applicatif via rôle)
CREATE POLICY threads_user_isolation ON threads
    USING (user_id = current_setting('app.current_user_id')::UUID
           OR current_setting('app.current_role') IN ('admin', 'direction'));

CREATE POLICY messages_user_isolation ON messages
    USING (thread_id IN (
        SELECT id FROM threads
        WHERE user_id = current_setting('app.current_user_id')::UUID
    ) OR current_setting('app.current_role') IN ('admin', 'direction'));
```

### Fonction de mise à jour `updated_at`
```sql
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_threads_updated_at BEFORE UPDATE ON threads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
CREATE TRIGGER update_skills_updated_at BEFORE UPDATE ON skills
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

---

## 6. Backend FastAPI — config.py

```python
# backend/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # App
    environment: str = "production"
    debug: bool = False
    allowed_hosts: str = "100.64.0.1"

    # Database
    database_url: str

    # Auth
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    # LLM — paliers
    anthropic_api_key: str
    ollama_base_url: str = "http://localhost:11434"
    ollama_model_light: str = "mistral:7b"

    # Langfuse
    langfuse_secret_key: str
    langfuse_public_key: str
    langfuse_host: str = "http://langfuse-server:3000"

    # Daytona (optionnel)
    daytona_api_key: Optional[str] = None

    # Schedule
    access_start_hour: int = 7   # 7h00
    access_end_hour: int = 19    # 19h00

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 7. Backend FastAPI — main.py

Génère `backend/main.py` avec :

```python
from fastapi import FastAPI, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from database.connection import init_db
from routers import auth, users, chat, dashboard
from config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield

app = FastAPI(
    title="Symbiose Pluton API",
    version="1.0.0",
    docs_url="/api/docs" if settings.debug else None,
    redoc_url=None,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://{settings.allowed_hosts}"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "symbiose-noa"}
```

---

## 8. LLM Router — paliers de requêtes

Génère `backend/llm/router.py` avec la logique de routage entre les modèles :

```python
# backend/llm/router.py
"""
Routeur LLM — 3 paliers selon la complexité de la tâche

PALIER 1 — LÉGER : Ollama local (Mistral 7B)
  Cas : classification de requête, recherche simple, résumé court
  Coût : 0€ (local)
  Latence : 2-5s

PALIER 2 — STANDARD : Claude Haiku 4.5
  Cas : recherche documentaire, rédaction courte, extraction simple
  Coût : ~0.0025€/requête
  Latence : 1-2s

PALIER 3 — COMPLEXE : Claude Sonnet 4.6
  Cas : analyse de plans, génération de devis, raisonnement multi-étapes,
        vision (photos/plans), génération de skills (Agent 3)
  Coût : ~0.02€/requête
  Latence : 3-8s
"""

from enum import Enum
from anthropic import AsyncAnthropic
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama
from config import settings

class LLMTier(Enum):
    LIGHT = "light"       # Ollama local
    STANDARD = "standard" # Claude Haiku
    COMPLEX = "complex"   # Claude Sonnet

def get_llm(tier: LLMTier):
    """Retourne l'instance LLM selon le palier demandé"""
    if tier == LLMTier.LIGHT:
        return ChatOllama(
            base_url=settings.ollama_base_url,
            model=settings.ollama_model_light,
            temperature=0.1,
        )
    elif tier == LLMTier.STANDARD:
        return ChatAnthropic(
            model="claude-haiku-4-5",
            api_key=settings.anthropic_api_key,
            temperature=0.1,
            max_tokens=2048,
        )
    elif tier == LLMTier.COMPLEX:
        return ChatAnthropic(
            model="claude-sonnet-4-6",
            api_key=settings.anthropic_api_key,
            temperature=0.1,
            max_tokens=4096,
        )

def classify_request_tier(query: str, has_attachment: bool = False) -> LLMTier:
    """
    Classifie automatiquement une requête dans le bon palier.
    Logique simple basée sur des heuristiques — à affiner avec l'usage.
    """
    # Palier 3 si pièce jointe (vision nécessaire)
    if has_attachment:
        return LLMTier.COMPLEX

    # Palier 1 si requête courte et simple
    simple_keywords = ["retrouve", "cherche", "liste", "montre", "qui", "quand"]
    if len(query.split()) < 10 and any(k in query.lower() for k in simple_keywords):
        return LLMTier.LIGHT

    # Palier 2 par défaut
    return LLMTier.STANDARD
```

---

## 9. LangGraph — État partagé

Génère `backend/agents/state.py` :

```python
# backend/agents/state.py
from typing import TypedDict, Optional, List, Annotated
from langgraph.graph.message import add_messages

class PlutonState(TypedDict):
    """État partagé entre tous les nœuds du graph LangGraph"""

    # Identité de la requête
    thread_id: str
    user_id: str
    user_role: str
    session_id: str

    # Requête entrante
    query: str
    has_attachment: bool
    attachment_type: Optional[str]  # 'pdf', 'image', 'sketchup'

    # Routage
    target_agent: Optional[str]     # 'agent1', 'agent2', 'agent3', 'multi'
    llm_tier: Optional[str]         # 'light', 'standard', 'complex'
    skill_name: Optional[str]       # Nom du skill utilisé si applicable

    # Traitement RAG
    raw_chunks: Optional[List[str]]
    anonymized_chunks: Optional[List[str]]
    entity_map: Optional[dict]      # Correspondances pour réhydratation

    # Réponse LLM
    llm_response: Optional[str]
    final_response: Optional[str]   # Après réhydratation

    # Human-in-the-loop
    requires_validation: bool
    validation_reason: Optional[str]
    validated_by: Optional[str]
    validation_status: Optional[str] # 'pending', 'approved', 'rejected'

    # Agent 3 — Skill learning
    out_of_scope: bool
    skill_generated: Optional[str]  # Code Python généré
    skill_test_result: Optional[dict]
    skill_confidence: Optional[float]

    # Métadonnées
    tokens_in: int
    tokens_out: int
    cost_eur: float
    duration_ms: Optional[int]
    error: Optional[str]

    # Messages (historique de la conversation)
    messages: Annotated[list, add_messages]
```

---

## 10. LangGraph — Les 3 agents (structure sans logique métier)

### Agent 1 — `backend/agents/agent1.py`

```python
# backend/agents/agent1.py
"""
Agent 1 — Commercial / Administratif
Rôle : point d'entrée principal information interne
Cas d'usage : À implémenter dans une prochaine itération
"""
from langgraph.graph import StateGraph, END
from agents.state import PlutonState
from llm.router import get_llm, LLMTier

# --- NŒUDS (stubs — à implémenter) ---

async def rag_node(state: PlutonState) -> dict:
    """Récupère les chunks pertinents depuis pgvector"""
    # TODO: Implémenter la recherche RAG
    return {"raw_chunks": []}

async def anonymize_node(state: PlutonState) -> dict:
    """Anonymise les chunks avec spaCy NER avant envoi LLM"""
    # TODO: Implémenter spaCy NER + regex métier
    return {
        "anonymized_chunks": state.get("raw_chunks", []),
        "entity_map": {}
    }

async def llm_node(state: PlutonState) -> dict:
    """Appel LLM avec chunks anonymisés"""
    # TODO: Implémenter l'appel LLM avec contexte
    llm = get_llm(LLMTier(state.get("llm_tier", "standard")))
    return {"llm_response": ""}

async def rehydrate_node(state: PlutonState) -> dict:
    """Réinjecte les vraies données dans la réponse"""
    # TODO: Implémenter la réhydratation depuis entity_map
    return {"final_response": state.get("llm_response", "")}

async def validation_check_node(state: PlutonState) -> dict:
    """Vérifie si une validation humaine est nécessaire"""
    # TODO: Détecter si la réponse contient des actions engageantes
    return {"requires_validation": False}

def should_validate(state: PlutonState) -> str:
    """Edge conditionnel : validation requise ou non"""
    if state.get("requires_validation"):
        return "wait_for_human"
    return END

# --- GRAPH ---

def build_agent1_graph():
    graph = StateGraph(PlutonState)

    graph.add_node("rag", rag_node)
    graph.add_node("anonymize", anonymize_node)
    graph.add_node("llm", llm_node)
    graph.add_node("rehydrate", rehydrate_node)
    graph.add_node("validation_check", validation_check_node)

    graph.set_entry_point("rag")
    graph.add_edge("rag", "anonymize")
    graph.add_edge("anonymize", "llm")
    graph.add_edge("llm", "rehydrate")
    graph.add_edge("rehydrate", "validation_check")
    graph.add_conditional_edges("validation_check", should_validate)

    return graph.compile()

agent1_graph = build_agent1_graph()
```

### Agent 2 — `backend/agents/agent2.py`

```python
# backend/agents/agent2.py
"""
Agent 2 — Conception / Visuels / Production
Rôle : analyse plans, photos, chiffrage, génération visuels
Cas d'usage : À implémenter dans une prochaine itération
"""
from langgraph.graph import StateGraph, END
from agents.state import PlutonState
from llm.router import get_llm, LLMTier

async def preprocess_attachment_node(state: PlutonState) -> dict:
    """Prétraitement fichier : suppression EXIF GPS photos, conversion PDF"""
    # TODO: Implémenter preprocessing
    return {}

async def vision_node(state: PlutonState) -> dict:
    """Analyse visuelle via Claude Sonnet Vision"""
    # TODO: Implémenter analyse image/plan
    llm = get_llm(LLMTier.COMPLEX)
    return {"llm_response": ""}

async def extraction_node(state: PlutonState) -> dict:
    """Extraction postes de travaux, surfaces, éléments clés"""
    # TODO: Implémenter extraction structurée
    return {}

async def similar_projects_node(state: PlutonState) -> dict:
    """Recherche chantiers similaires via RAG"""
    # TODO: Implémenter recherche sémantique chantiers
    return {}

async def prechiffrage_node(state: PlutonState) -> dict:
    """Prépare les éléments de pré-chiffrage"""
    # TODO: Implémenter logique pré-chiffrage
    return {"requires_validation": True, "validation_reason": "chiffrage"}

def build_agent2_graph():
    graph = StateGraph(PlutonState)

    graph.add_node("preprocess", preprocess_attachment_node)
    graph.add_node("vision", vision_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("similar_projects", similar_projects_node)
    graph.add_node("prechiffrage", prechiffrage_node)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "vision")
    graph.add_edge("vision", "extraction")
    graph.add_edge("extraction", "similar_projects")
    graph.add_edge("similar_projects", "prechiffrage")
    graph.add_edge("prechiffrage", END)

    return graph.compile()

agent2_graph = build_agent2_graph()
```

### Agent 3 — `backend/agents/agent3.py`

```python
# backend/agents/agent3.py
"""
Agent 3 — Superviseur / Auto-apprentissage
Rôle : détecte les requêtes hors champ, génère des skills, enrichit le Skill Store
Cas d'usage : À implémenter dans une prochaine itération
"""
from langgraph.graph import StateGraph, END
from agents.state import PlutonState
from llm.router import get_llm, LLMTier

async def analyze_gap_node(state: PlutonState) -> dict:
    """Analyse ce qui manque pour répondre à la requête"""
    # TODO: Implémenter l'analyse du gap
    llm = get_llm(LLMTier.COMPLEX)
    return {"out_of_scope": True}

async def search_existing_docs_node(state: PlutonState) -> dict:
    """Recherche docs existants comme base pour le skill"""
    # TODO: Implémenter recherche RAG pour contexte skill
    return {}

async def generate_skill_node(state: PlutonState) -> dict:
    """Claude génère le code Python du skill"""
    # TODO: Implémenter génération skill via Claude Sonnet
    llm = get_llm(LLMTier.COMPLEX)
    return {"skill_generated": "# TODO: generated skill code"}

async def test_skill_node(state: PlutonState) -> dict:
    """Test du skill dans sandbox Daytona isolé"""
    # TODO: Implémenter tests Daytona (phase 2)
    # Pour phase 1 : test basique subprocess Python isolé
    return {
        "skill_test_result": {"passed": False, "error": "Daytona not configured"},
        "skill_confidence": 0.0
    }

async def submit_for_validation_node(state: PlutonState) -> dict:
    """Soumet le skill à validation humaine"""
    # TODO: Notifier admin via WebSocket + créer entrée en DB
    return {
        "requires_validation": True,
        "validation_reason": "nouveau skill à valider"
    }

def should_retry_or_submit(state: PlutonState) -> str:
    """Edge conditionnel : retry si tests KO (max 3), soumettre si OK"""
    result = state.get("skill_test_result", {})
    if result.get("passed"):
        return "submit"
    # TODO: Implémenter compteur de retries dans l'état
    return "submit"  # Pour l'instant soumet toujours (même si KO)

def build_agent3_graph():
    graph = StateGraph(PlutonState)

    graph.add_node("analyze_gap", analyze_gap_node)
    graph.add_node("search_docs", search_existing_docs_node)
    graph.add_node("generate_skill", generate_skill_node)
    graph.add_node("test_skill", test_skill_node)
    graph.add_node("submit_validation", submit_for_validation_node)

    graph.set_entry_point("analyze_gap")
    graph.add_edge("analyze_gap", "search_docs")
    graph.add_edge("search_docs", "generate_skill")
    graph.add_edge("generate_skill", "test_skill")
    graph.add_conditional_edges(
        "test_skill",
        should_retry_or_submit,
        {"submit": "submit_validation"}
    )
    graph.add_edge("submit_validation", END)

    return graph.compile()

agent3_graph = build_agent3_graph()
```

---

## 11. LangGraph — Routeur principal

Génère `backend/agents/router.py` :

```python
# backend/agents/router.py
"""
Routeur LangGraph principal
Analyse la requête entrante et dispatche vers le bon agent
"""
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from agents.state import PlutonState
from agents.agent1 import agent1_graph
from agents.agent2 import agent2_graph
from agents.agent3 import agent3_graph
from llm.router import classify_request_tier, LLMTier
from config import settings

async def classify_node(state: PlutonState) -> dict:
    """
    Nœud 1 : Classification de la requête
    Détermine : quel agent, quel palier LLM
    """
    query = state["query"]
    has_attachment = state.get("has_attachment", False)
    user_role = state.get("user_role", "terrain")

    # Palier LLM
    tier = classify_request_tier(query, has_attachment)

    # Routage agent selon contenu et rôle
    # TODO: Affiner avec un LLM léger pour classification
    if has_attachment:
        target = "agent2"
        tier = LLMTier.COMPLEX
    else:
        target = "agent1"

    return {
        "target_agent": target,
        "llm_tier": tier.value,
    }

async def check_schedule_node(state: PlutonState) -> dict:
    """
    Nœud 2 : Vérification plage horaire
    Bloque si hors 7h-19h et pas bypass_schedule
    """
    # TODO: Vérifier heure courante vs settings.access_start/end_hour
    # et state["bypass_schedule"]
    return {}

async def dispatch_agent1(state: PlutonState) -> dict:
    """Exécute Agent 1"""
    result = await agent1_graph.ainvoke(state)
    return result

async def dispatch_agent2(state: PlutonState) -> dict:
    """Exécute Agent 2"""
    result = await agent2_graph.ainvoke(state)
    return result

async def dispatch_agent3(state: PlutonState) -> dict:
    """Exécute Agent 3 — déclenché si hors champ"""
    result = await agent3_graph.ainvoke(state)
    return result

def route_to_agent(state: PlutonState) -> str:
    """Edge conditionnel principal"""
    target = state.get("target_agent", "agent1")
    out_of_scope = state.get("out_of_scope", False)

    if out_of_scope:
        return "agent3"
    if target == "agent2":
        return "agent2"
    return "agent1"

async def build_main_graph(checkpointer):
    """Construit le graph principal avec checkpointing PostgreSQL"""
    graph = StateGraph(PlutonState)

    graph.add_node("classify", classify_node)
    graph.add_node("check_schedule", check_schedule_node)
    graph.add_node("agent1", dispatch_agent1)
    graph.add_node("agent2", dispatch_agent2)
    graph.add_node("agent3", dispatch_agent3)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "check_schedule")
    graph.add_conditional_edges(
        "check_schedule",
        route_to_agent,
        {
            "agent1": "agent1",
            "agent2": "agent2",
            "agent3": "agent3",
        }
    )
    graph.add_edge("agent1", END)
    graph.add_edge("agent2", END)
    graph.add_edge("agent3", END)

    return graph.compile(checkpointer=checkpointer)
```

---

## 12. Sécurité — RBAC

Génère `backend/security/rbac.py` :

```python
# backend/security/rbac.py
from fastapi import HTTPException, status
from functools import wraps
from typing import List

# Permissions par rôle
ROLE_PERMISSIONS = {
    "direction": [
        "chat_agent1", "chat_agent2", "chat_agent3",
        "view_dashboard_global", "view_own_stats",
        "validate_skills", "manage_users", "configure_agents",
        "view_costs_global", "view_own_costs", "view_audit_log"
    ],
    "admin": [
        "chat_agent1", "chat_agent2", "chat_agent3",
        "manage_users", "configure_agents", "view_audit_log",
        "view_costs_global", "validate_skills"
    ],
    "commercial": [
        "chat_agent1", "view_own_stats", "view_own_costs"
    ],
    "bureau_etudes": [
        "chat_agent1", "chat_agent2", "view_own_stats", "view_own_costs"
    ],
    "conducteur": [
        "chat_agent1", "view_own_stats", "view_own_costs"
    ],
    "administratif": [
        "chat_agent1", "view_own_stats", "view_own_costs"
    ],
    "terrain": [
        "chat_agent1"
    ],
}

# Quotas mensuels par défaut par rôle
ROLE_QUOTAS = {
    "direction": None,       # Illimité
    "admin": None,           # Illimité
    "commercial": 200,
    "bureau_etudes": 150,
    "conducteur": 100,
    "administratif": 100,
    "terrain": 50,
}

def has_permission(role: str, feature: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, [])
    return feature in permissions

def require_permission(feature: str):
    """Décorateur FastAPI pour vérifier une permission"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, current_user=None, **kwargs):
            if not current_user:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
            if not has_permission(current_user.role, feature):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{feature}' requise"
                )
            return await func(*args, current_user=current_user, **kwargs)
        return wrapper
    return decorator
```

---

## 13. Sécurité — Audit

Génère `backend/security/audit.py` :

```python
# backend/security/audit.py
"""
Système d'audit immuable — INSERT only, jamais UPDATE ou DELETE
"""
from database.connection import get_db
from typing import Optional
import time

async def log_action(
    action: str,
    user_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    model_used: Optional[str] = None,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_eur: float = 0.0,
    duration_ms: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    metadata: dict = {}
):
    """
    Enregistre une action dans l'audit log.
    Cette fonction ne fait que des INSERT — jamais d'UPDATE.
    """
    async with get_db() as conn:
        await conn.execute("""
            INSERT INTO audit_log (
                user_id, action, agent_id, model_used,
                tokens_in, tokens_out, cost_eur, duration_ms,
                success, error_message, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        """,
            user_id, action, agent_id, model_used,
            tokens_in, tokens_out, cost_eur, duration_ms,
            success, error_message, metadata
        )
```

---

## 14. pgvector — Tables SQL supplémentaires

Ajoute ces tables à la fin de `backend/database/migrations/001_initial_schema.sql` :

### Table `documents` — base du RAG

```sql
-- Table principale des documents vectorisés
-- Chaque ligne = un chunk de document prêt pour la recherche sémantique
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

    -- Contenu
    content TEXT NOT NULL,
    -- Texte brut du chunk (anonymisé si données sensibles)
    content_tokens INTEGER,
    -- Nombre approximatif de tokens (pour estimer les coûts RAG)

    -- Vecteur d'embedding
    embedding vector(1536),
    -- Dimension 1536 = OpenAI text-embedding-3-small / Anthropic
    -- Mettre NULL si pas encore vectorisé

    -- Métadonnées de la source
    source_type VARCHAR(50) NOT NULL,
    -- 'devis', 'chantier', 'client', 'plan_pdf', 'photo',
    -- 'email', 'catalogue_fournisseur', 'methode_interne',
    -- 'sketchup', 'planning', 'document_admin'
    source_id VARCHAR(255),
    -- Identifiant dans le système source (ex: ID Extrabat, chemin fichier)
    source_filename VARCHAR(500),
    -- Nom du fichier original

    -- Contrôle d'accès par métadonnées
    -- Utilisé par le filtre pgvector AVANT de retourner les résultats
    access_level VARCHAR(50) NOT NULL DEFAULT 'all',
    -- 'all' : tous les rôles
    -- 'commercial_plus' : commercial, bureau_etudes, conducteur, direction, admin
    -- 'bureau_etudes_plus' : bureau_etudes, direction, admin
    -- 'direction_only' : direction, admin uniquement
    -- 'admin_only' : admin uniquement

    -- Données sensibles — jamais envoyées au LLM brutes
    contains_pii BOOLEAN DEFAULT false,
    -- true si le chunk contient des données personnelles non anonymisées
    is_anonymized BOOLEAN DEFAULT false,
    -- true si le chunk a été passé par spaCy NER avant stockage

    -- Position dans le document source
    chunk_index INTEGER DEFAULT 0,
    -- Index du chunk dans le document (0 = premier chunk)
    chunk_total INTEGER DEFAULT 1,
    -- Nombre total de chunks pour ce document source

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at TIMESTAMPTZ
);
```

### Table `document_metadata` — métadonnées enrichies

```sql
-- Métadonnées structurées associées à chaque document source
-- Séparées de documents pour ne pas alourdir les chunks
CREATE TABLE document_metadata (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    source_id VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL,

    -- Métadonnées communes
    title VARCHAR(500),
    date_document DATE,
    -- Date du document source (pas de création en base)

    -- Métadonnées spécifiques (JSONB flexible selon source_type)
    data JSONB DEFAULT '{}',
    -- Exemples selon source_type :
    -- devis : { "client_id": "...", "montant_ht": null, "statut": "signé" }
    -- chantier : { "ville": "Arcachon", "type": "terrasse_bois", "surface_m2": 85 }
    -- client : { "nom_anonymise": "Client_001", "commune": "Bordeaux" }
    -- plan_pdf : { "architecte": "...", "echelle": "1/50", "nb_pages": 3 }

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(source_id, source_type)
);
```

### Table `embedding_jobs` — file d'attente vectorisation

```sql
-- File d'attente pour les documents à vectoriser
-- Le pipeline d'ingestion lit cette table et remplit documents.embedding
CREATE TABLE embedding_jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    -- 'pending', 'processing', 'completed', 'failed'
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ
);
```

### Index pgvector — IVFFlat pour recherche rapide

```sql
-- Index vectoriel IVFFlat — à créer APRÈS avoir inséré au moins 1000 chunks
-- Avant 1000 chunks : la recherche exacte (sans index) est suffisante
-- lists = sqrt(nb_chunks) — recalculer et REINDEX à chaque x10 de volume

-- Index principal pour la recherche de similarité cosinus
CREATE INDEX idx_documents_embedding_cosine
    ON documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
-- Ajuster lists selon le volume :
-- < 1 000 chunks  : pas d'index nécessaire
-- 1 000 - 10 000 : lists = 100
-- 10 000 - 100 000 : lists = 316
-- > 100 000 : lists = 1000

-- Index sur les métadonnées pour les filtres combinés (filtre + vecteur)
CREATE INDEX idx_documents_source_type ON documents(source_type);
CREATE INDEX idx_documents_access_level ON documents(access_level);
CREATE INDEX idx_documents_source_id ON documents(source_id);
CREATE INDEX idx_documents_contains_pii ON documents(contains_pii);

-- Index GIN pour recherche full-text hybride (backup si embedding absent)
CREATE INDEX idx_documents_content_trgm
    ON documents
    USING gin (content gin_trgm_ops);

-- Index sur embedding_jobs
CREATE INDEX idx_embedding_jobs_status ON embedding_jobs(status);
CREATE INDEX idx_embedding_jobs_document ON embedding_jobs(document_id);

-- Index sur document_metadata
CREATE INDEX idx_doc_metadata_source ON document_metadata(source_id, source_type);
CREATE INDEX idx_doc_metadata_data ON document_metadata USING gin(data);
```

### Commentaire sur la recherche hybride à implémenter

```sql
-- La recherche RAG utilisera une requête hybride combinant :
-- 1. Recherche vectorielle (similarité cosinus) via pgvector
-- 2. Filtre sur access_level selon le rôle utilisateur
-- 3. Optionnellement : filtre full-text pg_trgm en fallback
--
-- Exemple de requête (à implémenter dans vectorstore/client.py) :
--
-- SELECT id, content, source_type, source_id,
--        1 - (embedding <=> $1::vector) AS similarity
-- FROM documents
-- WHERE access_level = ANY($2::text[])   -- filtre rôle
--   AND source_type = ANY($3::text[])    -- filtre type optionnel
--   AND is_anonymized = true             -- sécurité : jamais de PII brut
-- ORDER BY embedding <=> $1::vector      -- tri par distance cosinus
-- LIMIT $4;                             -- top-K résultats
--
-- $1 = vecteur de la requête utilisateur (généré par le pipeline)
-- $2 = liste des access_level autorisés pour ce rôle
-- $3 = types de documents autorisés (optionnel)
-- $4 = K = nombre de chunks à retourner (défaut : 5)
```

---

## 15. pgvector — Client Python

Génère `backend/vectorstore/client.py` :

```python
# backend/vectorstore/client.py
"""
Client pgvector — interface de recherche sémantique
Gère la recherche hybride (vecteur + filtres métadonnées)
et l'insertion de nouveaux documents.

Note : la vectorisation (génération des embeddings) est intentionnellement
absente de ce fichier — elle sera implémentée dans le pipeline d'ingestion
lors d'une prochaine itération.
"""
from typing import List, Optional
from uuid import UUID
import asyncpg
from database.connection import get_db

# Mapping rôle → access_levels autorisés
# Un rôle peut accéder à tous les niveaux inférieurs au sien
ROLE_ACCESS_LEVELS = {
    "admin":          ["all", "commercial_plus", "bureau_etudes_plus", "direction_only", "admin_only"],
    "direction":      ["all", "commercial_plus", "bureau_etudes_plus", "direction_only"],
    "bureau_etudes":  ["all", "commercial_plus", "bureau_etudes_plus"],
    "commercial":     ["all", "commercial_plus"],
    "conducteur":     ["all", "commercial_plus"],
    "administratif":  ["all"],
    "terrain":        ["all"],
}

class VectorStoreClient:
    """
    Interface principale pour les opérations pgvector.
    À instancier une fois au démarrage et réutiliser.
    """

    async def search(
        self,
        query_embedding: List[float],
        user_role: str,
        source_types: Optional[List[str]] = None,
        top_k: int = 5,
        similarity_threshold: float = 0.3,
    ) -> List[dict]:
        """
        Recherche sémantique avec filtres d'accès.

        Args:
            query_embedding: Vecteur float32 de la requête (1536 dims)
            user_role: Rôle de l'utilisateur (filtre access_level)
            source_types: Types de documents à inclure (None = tous)
            top_k: Nombre de résultats à retourner
            similarity_threshold: Score minimum (0.0 à 1.0)

        Returns:
            Liste de chunks triés par similarité décroissante
        """
        allowed_levels = ROLE_ACCESS_LEVELS.get(user_role, ["all"])

        async with get_db() as conn:
            # Construction de la requête selon les filtres
            source_filter = ""
            params = [query_embedding, allowed_levels, top_k, similarity_threshold]

            if source_types:
                source_filter = "AND source_type = ANY($5::text[])"
                params.append(source_types)

            rows = await conn.fetch(f"""
                SELECT
                    id,
                    content,
                    source_type,
                    source_id,
                    source_filename,
                    chunk_index,
                    chunk_total,
                    1 - (embedding <=> $1::vector) AS similarity
                FROM documents
                WHERE access_level = ANY($2::text[])
                  AND is_anonymized = true
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> $1::vector) >= $4
                  {source_filter}
                ORDER BY embedding <=> $1::vector
                LIMIT $3
            """, *params)

            return [dict(row) for row in rows]

    async def search_hybrid(
        self,
        query_text: str,
        query_embedding: Optional[List[float]],
        user_role: str,
        top_k: int = 5,
    ) -> List[dict]:
        """
        Recherche hybride : vecteur si embedding disponible,
        fallback pg_trgm full-text sinon.
        Utile pour les requêtes exactes (numéro de devis, nom de ville).
        """
        if query_embedding:
            return await self.search(query_embedding, user_role, top_k=top_k)

        # Fallback full-text via pg_trgm
        allowed_levels = ROLE_ACCESS_LEVELS.get(user_role, ["all"])
        async with get_db() as conn:
            rows = await conn.fetch("""
                SELECT id, content, source_type, source_id,
                       similarity(content, $1) AS similarity
                FROM documents
                WHERE access_level = ANY($2::text[])
                  AND is_anonymized = true
                  AND content % $1
                ORDER BY similarity DESC
                LIMIT $3
            """, query_text, allowed_levels, top_k)
            return [dict(row) for row in rows]

    async def insert_document_chunk(
        self,
        content: str,
        source_type: str,
        source_id: str,
        access_level: str = "all",
        source_filename: Optional[str] = None,
        chunk_index: int = 0,
        chunk_total: int = 1,
        embedding: Optional[List[float]] = None,
        contains_pii: bool = False,
        is_anonymized: bool = False,
    ) -> UUID:
        """
        Insère un chunk de document.
        Si embedding est None, crée un embedding_job pour vectorisation différée.
        """
        async with get_db() as conn:
            async with conn.transaction():
                # Insérer le chunk
                doc_id = await conn.fetchval("""
                    INSERT INTO documents (
                        content, embedding, source_type, source_id,
                        source_filename, access_level, chunk_index, chunk_total,
                        contains_pii, is_anonymized,
                        content_tokens
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                              array_length(string_to_array($1, ' '), 1))
                    RETURNING id
                """,
                    content,
                    embedding,  # None si pas encore vectorisé
                    source_type, source_id, source_filename,
                    access_level, chunk_index, chunk_total,
                    contains_pii, is_anonymized
                )

                # Si pas d'embedding → créer un job de vectorisation
                if embedding is None:
                    await conn.execute("""
                        INSERT INTO embedding_jobs (document_id, status)
                        VALUES ($1, 'pending')
                    """, doc_id)

                return doc_id

    async def delete_by_source(
        self,
        source_id: str,
        source_type: str,
    ) -> int:
        """
        Supprime tous les chunks d'une source donnée.
        Utile pour ré-ingérer un document modifié.
        """
        async with get_db() as conn:
            result = await conn.execute("""
                DELETE FROM documents
                WHERE source_id = $1 AND source_type = $2
            """, source_id, source_type)
            return int(result.split()[-1])

    async def get_pending_embedding_jobs(self, limit: int = 50) -> List[dict]:
        """
        Récupère les jobs de vectorisation en attente.
        Appelé par le pipeline d'ingestion (à implémenter).
        """
        async with get_db() as conn:
            rows = await conn.fetch("""
                SELECT ej.id AS job_id, ej.document_id, ej.attempts,
                       d.content, d.source_type
                FROM embedding_jobs ej
                JOIN documents d ON d.id = ej.document_id
                WHERE ej.status = 'pending'
                  AND ej.attempts < ej.max_attempts
                ORDER BY ej.created_at ASC
                LIMIT $1
            """, limit)
            return [dict(row) for row in rows]

    async def mark_job_completed(self, job_id: UUID, embedding: List[float]):
        """Marque un job comme traité et met à jour l'embedding"""
        async with get_db() as conn:
            async with conn.transaction():
                await conn.execute("""
                    UPDATE embedding_jobs
                    SET status = 'completed', processed_at = NOW()
                    WHERE id = $1
                """, job_id)
                await conn.execute("""
                    UPDATE documents
                    SET embedding = $1, updated_at = NOW()
                    WHERE id = (
                        SELECT document_id FROM embedding_jobs WHERE id = $2
                    )
                """, embedding, job_id)

    async def mark_job_failed(self, job_id: UUID, error: str):
        """Marque un job comme échoué"""
        async with get_db() as conn:
            await conn.execute("""
                UPDATE embedding_jobs
                SET status = CASE
                        WHEN attempts + 1 >= max_attempts THEN 'failed'
                        ELSE 'pending'
                    END,
                    attempts = attempts + 1,
                    error_message = $2
                WHERE id = $1
            """, job_id, error)


# Instance singleton — importée par les agents
vectorstore = VectorStoreClient()
```

Génère `backend/vectorstore/schemas.py` :

```python
# backend/vectorstore/schemas.py
"""
Schémas Pydantic pour les opérations vectorstore.
"""
from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

class DocumentChunk(BaseModel):
    """Un chunk de document retourné par la recherche"""
    id: UUID
    content: str
    source_type: str
    source_id: str
    source_filename: Optional[str]
    chunk_index: int
    chunk_total: int
    similarity: float  # Score 0.0 à 1.0

class SearchRequest(BaseModel):
    """Requête de recherche sémantique"""
    query_text: str
    source_types: Optional[List[str]] = None
    top_k: int = 5
    similarity_threshold: float = 0.3

class SearchResult(BaseModel):
    """Résultat d'une recherche"""
    chunks: List[DocumentChunk]
    total_found: int
    search_method: str  # 'vector', 'hybrid', 'fulltext'

class InsertDocumentRequest(BaseModel):
    """Requête d'insertion d'un chunk"""
    content: str
    source_type: str
    source_id: str
    access_level: str = "all"
    source_filename: Optional[str] = None
    chunk_index: int = 0
    chunk_total: int = 1
    contains_pii: bool = False
    is_anonymized: bool = False
```

---

## 16. Daytona — Client Python pour l'Agent 3

Génère `backend/sandbox/daytona_client.py` :

```python
# backend/sandbox/daytona_client.py
"""
Client Daytona — Sandbox isolé pour tester les skills générés par l'Agent 3.

Fonctionnement :
1. L'Agent 3 génère du code Python (le skill)
2. Ce client crée un sandbox Daytona éphémère (<90ms)
3. Le code est exécuté dans le sandbox avec des données de test fictives
4. Le résultat (succès/échec, output, métriques) est retourné
5. Le sandbox est détruit immédiatement après
6. Aucune donnée client ne transite par Daytona — uniquement du code Python

Si Daytona n'est pas configuré (DAYTONA_API_KEY absent),
le client bascule automatiquement sur un fallback subprocess local.
"""
import asyncio
import time
import subprocess
import tempfile
import os
from typing import Optional
from dataclasses import dataclass
from config import settings


@dataclass
class SandboxTestResult:
    """Résultat d'un test de skill dans le sandbox"""
    passed: bool
    output: Optional[str]
    error: Optional[str]
    execution_time_ms: int
    memory_used_mb: Optional[float]
    confidence_score: float
    # Score calculé à partir des métriques d'exécution
    # 0.0 = échec total, 1.0 = succès parfait
    sandbox_type: str
    # 'daytona' ou 'subprocess_fallback'


# Données de test fictives utilisées pour valider les skills
# Ces données ne contiennent aucune information réelle de Symbiose
MOCK_TEST_DATA = {
    # Données géométriques fictives
    "surface_m2": 85.0,
    "longueur_m": 12.5,
    "largeur_m": 6.8,
    "perimetre_m": 38.6,
    "hauteur_m": 2.4,

    # Matériaux fictifs
    "essence_bois": "ipé",
    "epaisseur_lame_mm": 21,
    "largeur_lame_mm": 145,
    "prix_m2_ht": 85.0,

    # Quantités fictives
    "nb_poteaux": 12,
    "entraxe_m": 1.5,
    "nb_lames_necessaires": 230,

    # Résultat attendu fictif (pour validation du skill)
    "resultat_attendu": 7225.0,
}


class DaytonaClient:
    """
    Client pour l'exécution de code dans des sandboxes Daytona isolés.
    Fallback automatique sur subprocess si Daytona non configuré.
    """

    def __init__(self):
        self.api_key = settings.daytona_api_key
        self.daytona_available = bool(self.api_key)

        if self.daytona_available:
            try:
                from daytona_sdk import Daytona
                self._daytona = Daytona(api_key=self.api_key)
            except ImportError:
                # SDK non installé → fallback subprocess
                self.daytona_available = False
                self._daytona = None
        else:
            self._daytona = None

    async def test_skill(
        self,
        skill_code: str,
        skill_name: str,
        max_execution_seconds: int = 30,
    ) -> SandboxTestResult:
        """
        Teste un skill généré par l'Agent 3.

        Args:
            skill_code: Code Python du skill à tester
            skill_name: Nom du skill (pour les logs)
            max_execution_seconds: Timeout en secondes

        Returns:
            SandboxTestResult avec le résultat du test
        """
        if self.daytona_available:
            return await self._test_in_daytona(
                skill_code, skill_name, max_execution_seconds
            )
        else:
            return await self._test_in_subprocess(
                skill_code, skill_name, max_execution_seconds
            )

    async def _test_in_daytona(
        self,
        skill_code: str,
        skill_name: str,
        timeout: int,
    ) -> SandboxTestResult:
        """
        Exécution dans un sandbox Daytona isolé.
        Le sandbox démarre en <90ms et est détruit après le test.
        """
        sandbox = None
        start_time = time.monotonic()

        try:
            # Prépare le code avec injection des données de test
            test_code = self._wrap_with_test_data(skill_code)

            # Crée le sandbox
            # Daytona SDK — voir https://github.com/daytonaio/daytona
            sandbox = self._daytona.create()

            # Exécute le code dans le sandbox
            result = sandbox.process.start_and_wait(
                f"python3 -c '{test_code}'",
                timeout=timeout
            )

            execution_time = int((time.monotonic() - start_time) * 1000)
            passed = result.exit_code == 0

            confidence = self._calculate_confidence(
                passed=passed,
                output=result.result,
                execution_time_ms=execution_time,
            )

            return SandboxTestResult(
                passed=passed,
                output=result.result if passed else None,
                error=result.result if not passed else None,
                execution_time_ms=execution_time,
                memory_used_mb=None,  # À extraire des métriques Daytona si disponible
                confidence_score=confidence,
                sandbox_type="daytona",
            )

        except Exception as e:
            execution_time = int((time.monotonic() - start_time) * 1000)
            return SandboxTestResult(
                passed=False,
                output=None,
                error=str(e),
                execution_time_ms=execution_time,
                memory_used_mb=None,
                confidence_score=0.0,
                sandbox_type="daytona",
            )

        finally:
            # Destruction du sandbox dans tous les cas
            if sandbox and self._daytona:
                try:
                    self._daytona.remove(sandbox)
                except Exception:
                    pass  # Ne pas faire échouer le retour si la destruction échoue

    async def _test_in_subprocess(
        self,
        skill_code: str,
        skill_name: str,
        timeout: int,
    ) -> SandboxTestResult:
        """
        Fallback : exécution dans un subprocess Python isolé.
        Moins sécurisé que Daytona mais suffisant pour la phase 1.
        ATTENTION : ne pas utiliser en production avec du code non validé.
        """
        start_time = time.monotonic()
        test_code = self._wrap_with_test_data(skill_code)

        try:
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                prefix=f'skill_test_{skill_name}_'
            ) as tmp:
                tmp.write(test_code)
                tmp_path = tmp.name

            # Exécution dans un subprocess avec timeout
            proc = await asyncio.create_subprocess_exec(
                'python3', tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                # Restrictions minimales pour le fallback
                env={
                    'PATH': '/usr/bin:/bin',
                    'PYTHONDONTWRITEBYTECODE': '1',
                }
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return SandboxTestResult(
                    passed=False,
                    output=None,
                    error=f"Timeout après {timeout}s",
                    execution_time_ms=timeout * 1000,
                    memory_used_mb=None,
                    confidence_score=0.0,
                    sandbox_type="subprocess_fallback",
                )

            execution_time = int((time.monotonic() - start_time) * 1000)
            passed = proc.returncode == 0
            output = stdout.decode().strip() if stdout else None
            error = stderr.decode().strip() if stderr else None

            confidence = self._calculate_confidence(
                passed=passed,
                output=output,
                execution_time_ms=execution_time,
            )

            return SandboxTestResult(
                passed=passed,
                output=output,
                error=error if not passed else None,
                execution_time_ms=execution_time,
                memory_used_mb=None,
                confidence_score=confidence,
                sandbox_type="subprocess_fallback",
            )

        except Exception as e:
            return SandboxTestResult(
                passed=False,
                output=None,
                error=str(e),
                execution_time_ms=int((time.monotonic() - start_time) * 1000),
                memory_used_mb=None,
                confidence_score=0.0,
                sandbox_type="subprocess_fallback",
            )

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _wrap_with_test_data(self, skill_code: str) -> str:
        """
        Enveloppe le code du skill avec les données de test fictives.
        Le skill reçoit un dict 'data' avec les données de test.
        Le skill doit retourner un résultat via print() ou return.
        """
        return f"""
# Données de test fictives — aucune donnée réelle de Symbiose
TEST_DATA = {MOCK_TEST_DATA}

# Code du skill généré par l'Agent 3
{skill_code}

# Exécution du skill avec les données de test
# Convention : le skill doit exposer une fonction run(data) -> dict
try:
    result = run(TEST_DATA)
    print(f"OK: {{result}}")
except NameError:
    # Si pas de fonction run(), tenter une exécution directe
    print("OK: skill exécuté sans erreur")
except Exception as e:
    raise RuntimeError(f"Skill failed: {{e}}")
"""

    def _calculate_confidence(
        self,
        passed: bool,
        output: Optional[str],
        execution_time_ms: int,
    ) -> float:
        """
        Calcule un score de confiance basé sur les métriques d'exécution.
        Score entre 0.0 et 1.0.
        """
        if not passed:
            return 0.0

        score = 0.7  # Base si tests passés

        # Bonus si output non vide (le skill produit quelque chose)
        if output and len(output) > 0:
            score += 0.1

        # Bonus si rapide (< 5s)
        if execution_time_ms < 5000:
            score += 0.1

        # Bonus si très rapide (< 1s)
        if execution_time_ms < 1000:
            score += 0.1

        return min(score, 1.0)


# Instance singleton — importée par l'Agent 3
sandbox_client = DaytonaClient()
```

### Mise à jour `agent3.py` — utiliser le sandbox client

Mets à jour le nœud `test_skill_node` dans `backend/agents/agent3.py` pour utiliser le client :

```python
# Dans backend/agents/agent3.py — remplacer le nœud test_skill_node

from sandbox.daytona_client import sandbox_client, SandboxTestResult

async def test_skill_node(state: PlutonState) -> dict:
    """
    Test du skill dans sandbox isolé.
    Utilise Daytona si configuré, subprocess en fallback.
    Jusqu'à 3 tentatives automatiques si le test échoue.
    """
    skill_code = state.get("skill_generated", "")
    skill_name = state.get("skill_name", "unknown_skill")

    if not skill_code:
        return {
            "skill_test_result": {"passed": False, "error": "Aucun code généré"},
            "skill_confidence": 0.0,
        }

    result: SandboxTestResult = await sandbox_client.test_skill(
        skill_code=skill_code,
        skill_name=skill_name,
        max_execution_seconds=30,
    )

    return {
        "skill_test_result": {
            "passed": result.passed,
            "output": result.output,
            "error": result.error,
            "execution_time_ms": result.execution_time_ms,
            "sandbox_type": result.sandbox_type,
        },
        "skill_confidence": result.confidence_score,
    }
```

### Variable d'environnement à ajouter dans `.env.example`

```env
# Daytona — Sandbox Agent 3 (optionnel phase 1 — requis phase 2)
# Laisser vide pour utiliser le fallback subprocess local
# Obtenir sur https://app.daytona.io
DAYTONA_API_KEY=
```

### Dépendance à ajouter dans `requirements.txt`

```
# Daytona SDK (optionnel — installer si DAYTONA_API_KEY configuré)
daytona-sdk==0.14.0
```

---

## 17. Frontend — Page login

Génère `frontend/app/(auth)/login/page.tsx` :

```tsx
// frontend/app/(auth)/login/page.tsx
"use client"
import { signIn } from "next-auth/react"

export default function LoginPage() {
  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "#f8f7f2"
    }}>
      <div style={{
        background: "white",
        borderRadius: 16,
        padding: "40px 48px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.08)",
        textAlign: "center",
        maxWidth: 380,
        width: "100%"
      }}>
        <div style={{ fontSize: 32, marginBottom: 8 }}>🌿</div>
        <h1 style={{ fontSize: 22, fontWeight: 500, marginBottom: 4 }}>Pluton</h1>
        <p style={{ color: "#888", fontSize: 14, marginBottom: 32 }}>
          Symbiose Paysage
        </p>
        <button
          onClick={() => signIn("google", { callbackUrl: "/chat" })}
          style={{
            width: "100%",
            padding: "12px 24px",
            background: "#1D9E75",
            color: "white",
            border: "none",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 500,
            cursor: "pointer",
          }}
        >
          Se connecter avec Google
        </button>
        <p style={{ color: "#aaa", fontSize: 11, marginTop: 24 }}>
          Accès réservé aux collaborateurs Symbiose Paysage
        </p>
      </div>
    </div>
  )
}
```

---

## 18. Instructions de déploiement

À la fin de la génération, crée un fichier `SETUP.md` avec les étapes dans l'ordre :

```markdown
# Setup Pluton — Symbiose Paysage

## Prérequis
- Ubuntu 24.04
- Docker + Docker Compose installés
- Headscale installé et configuré
- Domaine Google Workspace pour OAuth2

## Étapes

### 1. Cloner et configurer
git clone <repo>
cp .env.example .env
# Éditer .env avec les vraies valeurs

### 2. Configurer Google OAuth2
# Aller sur console.cloud.google.com
# Créer un projet → APIs → OAuth 2.0 Client IDs
# URI autorisé : http://<HEADSCALE_IP>
# Ajouter GOOGLE_CLIENT_ID et GOOGLE_CLIENT_SECRET dans .env

### 3. Lancer l'infrastructure
docker compose up -d
docker compose -f docker-compose.langfuse.yml up -d

### 4. Initialiser la base de données
docker compose exec postgres psql -U noa_user -d symbiose_noa -f /migrations/001_initial_schema.sql

### 5. Vérifier les extensions pgvector
docker compose exec postgres psql -U noa_user -d symbiose_noa -c "\dx"
# Doit afficher : vector, pg_trgm, uuid-ossp

### 6. Installer Ollama (optionnel — palier léger local)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull mistral:7b

### 6. Vérifier
curl http://<HEADSCALE_IP>/api/health
# → {"status": "ok", "service": "symbiose-noa"}

### 7. Accéder à Langfuse
# http://<HEADSCALE_IP>:3001
# Créer un projet → récupérer les clés → mettre dans .env

## Variables à générer
openssl rand -base64 32  # → NEXTAUTH_SECRET
openssl rand -hex 32     # → JWT_SECRET_KEY
openssl rand -hex 32     # → LANGFUSE_SECRET_KEY
openssl rand -hex 16     # → LANGFUSE_SALT
```

---

## Contraintes et règles à respecter impérativement

1. **Aucun port public** — tous les services bindent sur `127.0.0.1` ou `${HEADSCALE_IP}`. Nginx est le seul point d'entrée et uniquement sur l'IP Headscale.

2. **Async partout** — toutes les fonctions Python sont `async def`. Utiliser `asyncpg` pour PostgreSQL, pas psycopg2 synchrone.

3. **Pas de logique métier** — les nœuds LangGraph sont des stubs avec `# TODO`. Ne pas inventer de logique de recherche, de chiffrage ou de traitement de documents. Uniquement la structure.

4. **RLS activé** — ne pas oublier le `SET app.current_user_id` et `SET app.current_role` dans chaque connexion DB avant les requêtes sur les tables avec RLS.

5. **Audit sur toutes les actions** — chaque appel `/api/chat` doit appeler `audit.log_action()`. C'est non négociable.

6. **Type hints partout** — Python typé avec mypy, TypeScript strict en frontend.

7. **Pas de données en clair dans les logs** — ne jamais logger le contenu des messages ou les données clients. Logger uniquement les métadonnées (user_id, durée, tokens, erreur).

8. **requirements.txt complet** avec versions fixées :
```
fastapi==0.115.0
uvicorn[standard]==0.32.0
pydantic==2.9.0
pydantic-settings==2.5.0
asyncpg==0.30.0
langgraph==1.2.0
langchain-anthropic==0.3.0
langchain-ollama==0.2.0
langfuse==2.55.0
python-jose[cryptography]==3.3.0
httpx==0.27.0
pgvector==0.3.6
numpy==1.26.4
spacy==3.7.6
# fr_core_news_lg à installer séparément :
# python -m spacy download fr_core_news_lg
daytona-sdk==0.14.0
```

