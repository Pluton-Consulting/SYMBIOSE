"""
Génération d'embeddings — multi-fournisseurs (RAG).

Fournisseurs supportés (settings.embedding_provider) :
  - gemini : Google `gemini-embedding-001` via REST, `outputDimensionality=1536`
             (tier gratuit, aucune migration de schéma). RECOMMANDÉ sur petit VPS.
  - openai : `text-embedding-3-small` (1536).
  - ollama : modèle local (ex. bge-m3, 1024 dims → nécessite une migration du schéma).

DÉGRADATION PROPRE : si la clé/le service manque ou échoue, les fonctions
renvoient `None` (ou une liste de `None`) et loggent un warning — elles ne lèvent
JAMAIS. Sans embeddings, la recherche RAG retombe sur pg_trgm.

On ne logge jamais le contenu vectorisé, uniquement des métadonnées.
"""
import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger("symbiose.embeddings")

_warned_no_key = False


def _warn_once(msg: str) -> None:
    global _warned_no_key
    if not _warned_no_key:
        logger.warning(msg)
        _warned_no_key = True


# ── OpenAI ────────────────────────────────────────────────────────────────
_openai_client = None


def _openai():
    global _openai_client
    if _openai_client is not None:
        return _openai_client
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI
        _openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
        return _openai_client
    except Exception as e:
        logger.warning("Client OpenAI indisponible (%s)", type(e).__name__)
        return None


async def _embed_openai(texts: list[str]) -> list[Optional[list[float]]]:
    client = _openai()
    if client is None:
        _warn_once("OPENAI_API_KEY absente : embeddings openai désactivés (dégradation pg_trgm).")
        return [None] * len(texts)
    try:
        resp = await client.embeddings.create(model=settings.embedding_model, input=texts)
        return [d.embedding for d in resp.data]
    except Exception as e:
        logger.warning("Échec embeddings OpenAI (%s) — mode dégradé", type(e).__name__)
        return [None] * len(texts)


# ── Gemini (Google AI Studio, REST) ───────────────────────────────────────
async def _embed_gemini(texts: list[str]) -> list[Optional[list[float]]]:
    if not settings.google_api_key:
        _warn_once("GOOGLE_API_KEY absente : embeddings gemini désactivés (dégradation pg_trgm).")
        return [None] * len(texts)

    model = settings.gemini_embedding_model
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:batchEmbedContents?key={settings.google_api_key}")
    body = {
        "requests": [
            {
                "model": f"models/{model}",
                "content": {"parts": [{"text": t}]},
                "outputDimensionality": settings.embedding_dimensions,
            }
            for t in texts
        ]
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
        embeddings = data.get("embeddings", [])
        out: list[Optional[list[float]]] = []
        for e in embeddings:
            vals = e.get("values")
            out.append(vals if vals else None)
        # aligne la longueur en cas de réponse partielle
        while len(out) < len(texts):
            out.append(None)
        return out
    except Exception as e:
        logger.warning("Échec embeddings Gemini (%s) — mode dégradé", type(e).__name__)
        return [None] * len(texts)


# ── Ollama (local) ────────────────────────────────────────────────────────
async def _embed_ollama(texts: list[str]) -> list[Optional[list[float]]]:
    out: list[Optional[list[float]]] = []
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            for t in texts:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/embeddings",
                    json={"model": settings.ollama_embedding_model, "prompt": t},
                )
                r.raise_for_status()
                out.append(r.json().get("embedding") or None)
        return out
    except Exception as e:
        logger.warning("Échec embeddings Ollama (%s) — mode dégradé", type(e).__name__)
        return out + [None] * (len(texts) - len(out))


_PROVIDERS = {"gemini": _embed_gemini, "openai": _embed_openai, "ollama": _embed_ollama}


# ── API publique ──────────────────────────────────────────────────────────
async def embed_texts(texts: list[str]) -> list[Optional[list[float]]]:
    """
    Vectorise un lot de textes. Ordre de sortie = ordre d'entrée. Textes vides →
    None sans appel réseau. Ne lève jamais ; renvoie [None,…] si indisponible.
    """
    if not texts:
        return []
    cleaned = [(t or "").strip() for t in texts]
    to_embed = [(i, t) for i, t in enumerate(cleaned) if t]
    if not to_embed:
        return [None] * len(texts)

    provider = _PROVIDERS.get(settings.embedding_provider, _embed_gemini)
    vectors = await provider([t for _, t in to_embed])

    results: list[Optional[list[float]]] = [None] * len(texts)
    for (orig_idx, _), vec in zip(to_embed, vectors):
        results[orig_idx] = vec
    return results


async def embed_query(text: str) -> Optional[list[float]]:
    """Embedding d'une requête unique (None si indisponible / texte vide)."""
    text = (text or "").strip()
    if not text:
        return None
    return (await embed_texts([text]))[0]
