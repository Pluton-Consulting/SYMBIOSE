"""
Agent 2 — Conception / Visuels / Production
Rôle : analyse plans, photos, chiffrage, génération visuels
Toujours sur palier LLM COMPLEX (Claude Sonnet Vision)
Pipeline : preprocess → vision → extraction → [browser?] → similar_projects → prechiffrage
Cas d'usage : À implémenter dans une prochaine itération
"""
from langgraph.graph import StateGraph, END
from agents.state import AgentState
from llm.router import get_llm, LLMTier


# ── Nœuds ────────────────────────────────────────────────────────────

async def preprocess_attachment_node(state: AgentState) -> dict:
    """Prétraitement fichier : suppression EXIF/GPS photos, conversion PDF→images"""
    # TODO: Implémenter avec Pillow (EXIF) et pdf2image (PDF)
    return {}


async def vision_node(state: AgentState, config=None) -> dict:
    """Analyse visuelle via Vision (palier COMPLEX). Tracing Langfuse propagé via config."""
    # TODO (cas d'usage) : encoder l'image en base64 + message multimodal, puis
    #   response = await llm.ainvoke(messages, config=config)  # tracé dans le même arbre
    llm = get_llm(LLMTier.COMPLEX)
    return {"llm_response": "", "model_used": None}


async def extraction_node(state: AgentState) -> dict:
    """Extraction structurée : postes de travaux, surfaces, éléments clés"""
    # TODO: Implémenter extraction JSON structurée via function calling
    return {}


async def browser_node(state: AgentState) -> dict:
    """
    Enrichit le pré-chiffrage avec des prix matériaux actuels (DuckDuckGo via Daytona).
    Intercalé entre extraction et similar_projects.
    """
    from browser.tools import web_search

    query = state.get("query", "")
    result = await web_search(
        query=query,
        user_id=state.get("user_id", ""),
        agent_id="agent2",
        max_results=3,
    )

    existing = list(state.get("raw_chunks") or [])
    if result["success"]:
        existing.append(
            "[SOURCE WEB — prix / données externes, à mentionner et à valider]\n"
            + result["content"]
        )

    return {
        "raw_chunks": existing,
        "browser_used": True,
        "browser_sources": result.get("sources", []),
        "browser_content": result.get("content"),
        "browser_was_filtered": result.get("was_filtered", False),
    }


async def similar_projects_node(state: AgentState) -> dict:
    """Recherche chantiers similaires via RAG vectoriel (source_type='chantier')."""
    from vectorstore.rag import retrieve_as_context

    contexts = await retrieve_as_context(
        query=state.get("query", ""),
        user_role=state.get("user_role", "bureau_etudes"),
        source_types=["chantier", "devis"],
        top_k=5,
    )
    existing = list(state.get("raw_chunks") or [])
    existing.extend(contexts)
    return {"raw_chunks": existing}


async def prechiffrage_node(state: AgentState) -> dict:
    """Prépare les éléments de pré-chiffrage — toujours validé par un humain"""
    # TODO: Implémenter logique pré-chiffrage métier Symbiose
    return {"requires_validation": True, "validation_reason": "chiffrage"}


# ── Edges conditionnels ───────────────────────────────────────────────

def should_use_browser(state: AgentState) -> str:
    """
    Le browser est le DERNIER RECOURS pour l'Agent 2.
    Il ne se déclenche que si le RAG n'a retourné aucun chunk.
    Les données internes (chantiers similaires, prix historiques) sont toujours prioritaires.
    """
    from config import settings

    if state.get("browser_used"):
        return "similar_projects"
    if not settings.browser_enabled:
        return "similar_projects"

    no_internal = len(state.get("raw_chunks") or []) == 0
    return "browser" if no_internal else "similar_projects"


# ── Graph ─────────────────────────────────────────────────────────────

def build_agent2_graph():
    graph = StateGraph(AgentState)

    graph.add_node("preprocess", preprocess_attachment_node)
    graph.add_node("vision", vision_node)
    graph.add_node("extraction", extraction_node)
    graph.add_node("browser", browser_node)
    graph.add_node("similar_projects", similar_projects_node)
    graph.add_node("prechiffrage", prechiffrage_node)

    graph.set_entry_point("preprocess")
    graph.add_edge("preprocess", "vision")
    graph.add_edge("vision", "extraction")
    graph.add_conditional_edges(
        "extraction",
        should_use_browser,
        {"browser": "browser", "similar_projects": "similar_projects"},
    )
    graph.add_edge("browser", "similar_projects")
    graph.add_edge("similar_projects", "prechiffrage")
    graph.add_edge("prechiffrage", END)

    return graph.compile()


agent2_graph = build_agent2_graph()
