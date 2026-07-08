"""
Agent 1 — Commercial / Administratif
Pipeline : RAG pgvector → anonymisation NER → [browser?] → LLM → réhydratation → validation check
Zéro PII vers l'API LLM : la requête ET les documents sont masqués avant l'appel,
puis les vraies valeurs sont réinjectées dans la réponse (entity_map).
"""
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from llm.router import get_llm, LLMTier

SYSTEM_PROMPT = """Tu es Symbiose, assistant IA interne de Symbiose Paysage, cabinet d'architecture paysagère et d'aménagements extérieurs.
Tu aides les équipes (commerciaux, bureau d'études, conducteurs de travaux, administratif, terrain) dans leur travail quotidien.
Tu as accès aux documents internes : devis, chantiers, catalogues fournisseurs, méthodes internes, plannings.
Réponds toujours en français. Sois précis, professionnel et concis.
Certaines valeurs peuvent apparaître masquées sous forme de balises [PER_1], [MONTANT_2], etc. — conserve ces balises telles quelles dans ta réponse, elles seront réinjectées automatiquement.
Si tu n'as pas l'information demandée dans les documents fournis, dis-le clairement — n'invente jamais un montant, un nom ou une date."""


# ── Nœuds ────────────────────────────────────────────────────────────

async def rag_node(state: AgentState) -> dict:
    """Récupère les chunks pertinents depuis pgvector (filtrés par rôle)."""
    from vectorstore.rag import retrieve_as_context

    contexts = await retrieve_as_context(
        query=state.get("query", ""),
        user_role=state.get("user_role", "terrain"),
        top_k=5,
    )
    return {"raw_chunks": contexts}


async def anonymize_node(state: AgentState) -> dict:
    """Masque la requête ET les chunks avant tout envoi LLM (entity_map partagé)."""
    from security.anonymizer import anonymizer

    query = state.get("query", "")
    chunks = list(state.get("raw_chunks") or [])
    masked, entity_map = anonymizer.anonymize_chunks([query] + chunks)

    return {
        "anonymized_query": masked[0] if masked else query,
        "anonymized_chunks": masked[1:] if len(masked) > 1 else [],
        "entity_map": entity_map,
    }


async def browser_node(state: AgentState) -> dict:
    """Recherche web via DuckDuckGo dans sandbox Daytona — dernier recours si RAG vide."""
    from browser.tools import web_search
    result = await web_search(
        query=state.get("query", ""),
        user_id=state.get("user_id", ""),
        agent_id="agent1",
        max_results=3,
    )
    existing = list(state.get("raw_chunks") or [])
    if result["success"]:
        existing.append(
            "[SOURCE WEB — information externe, à mentionner et valider]\n" + result["content"]
        )
    return {
        "raw_chunks": existing,
        "browser_used": True,
        "browser_sources": result.get("sources", []),
        "browser_content": result.get("content"),
        "browser_was_filtered": result.get("was_filtered", False),
    }


async def llm_node(state: AgentState, config=None) -> dict:
    """Appel LLM (résilient) sur requête/contexte masqués. Le tracing Langfuse est
    propagé depuis le tour complet via `config` (arbre de trace unique)."""
    # Fail-closed RGPD : si l'anonymiseur NER est HS, on NE contacte PAS de LLM
    # externe (noms/adresses/organisations partiraient en clair). On refuse.
    from security.anonymizer import anonymizer
    from config import settings as _settings
    if _settings.block_external_llm_without_ner and not anonymizer.spacy_available:
        return {
            "llm_response": ("Service momentanément indisponible : la protection des données "
                             "(anonymisation) n'est pas opérationnelle, la requête n'a pas été "
                             "envoyée à un modèle externe. Contactez l'administrateur."),
            "model_used": None,
            "error": "ner_unavailable",
        }

    llm = get_llm(LLMTier(state.get("llm_tier", "standard")))

    chunks = state.get("anonymized_chunks")
    if chunks is None:
        chunks = state.get("raw_chunks") or []
    context_text = "\n\n---\n\n".join(str(c) for c in chunks) if chunks else ""

    query = state.get("anonymized_query") or state.get("query", "")
    human_content = f"Question : {query}"
    if context_text:
        human_content = f"Documents internes disponibles :\n{context_text}\n\n{human_content}"

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=human_content)]
    response = await llm.ainvoke(messages, config=config)

    usage = getattr(response, "usage_metadata", None) or {}
    return {
        "llm_response": response.content,
        "tokens_in": usage.get("input_tokens", 0),
        "tokens_out": usage.get("output_tokens", 0),
        "model_used": llm.last_model_used,
    }


async def rehydrate_node(state: AgentState) -> dict:
    """Réinjecte les vraies entités dans la réponse via entity_map."""
    from security.anonymizer import anonymizer

    text = state.get("llm_response", "") or ""
    entity_map = state.get("entity_map") or {}
    return {"final_response": anonymizer.rehydrate(text, entity_map)}


async def validation_check_node(state: AgentState) -> dict:
    """Détecte si la réponse nécessite une validation humaine (devis, envoi client...)."""
    # TODO (cas d'usage métier) : heuristique sur le contenu de final_response.
    return {"requires_validation": False}


# ── Edges conditionnels ───────────────────────────────────────────────

def should_use_browser(state: AgentState) -> str:
    from config import settings
    if state.get("browser_used"):
        return "llm"
    if not settings.browser_enabled:
        return "llm"
    return "browser" if not (state.get("raw_chunks") or []) else "llm"


def should_validate(state: AgentState) -> str:
    return "wait_for_human" if state.get("requires_validation") else END


# ── Graph ─────────────────────────────────────────────────────────────

def build_agent1_graph():
    graph = StateGraph(AgentState)
    graph.add_node("rag", rag_node)
    graph.add_node("anonymize", anonymize_node)
    graph.add_node("browser", browser_node)
    graph.add_node("llm", llm_node)
    graph.add_node("rehydrate", rehydrate_node)
    graph.add_node("validation_check", validation_check_node)

    graph.set_entry_point("rag")
    graph.add_edge("rag", "anonymize")
    graph.add_conditional_edges("anonymize", should_use_browser, {"browser": "browser", "llm": "llm"})
    graph.add_edge("browser", "llm")
    graph.add_edge("llm", "rehydrate")
    graph.add_edge("rehydrate", "validation_check")
    graph.add_conditional_edges("validation_check", should_validate)

    return graph.compile()


agent1_graph = build_agent1_graph()
