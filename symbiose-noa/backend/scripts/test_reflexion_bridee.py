"""
Banc « LA RÉFLEXION EST BRIDÉE, MODÈLE PAR MODÈLE » — trace du 17/09, fil d13ff0ac.

Mesuré dans Langfuse sur ce tour : deepseek-v4-pro rendait 2 000 à 13 770 jetons de
sortie pour écrire un bloc d'action de cent caractères, 10 à 60 s l'appel, et quatre
« délai dépassé — candidat suivant » en vingt minutes (120 s perdues à chaque fois).
La table vient des mesures du 17/09 sur Ollama Cloud (projet jumeau) : la mauvaise
valeur est PIRE que rien, donc on ne vérifie ici que ce qui a été mesuré.
"""
import ast
import pathlib
import sys
import types
from typing import Optional

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "llm" / "router.py").read_text(encoding="utf-8")
f = next(ast.get_source_segment(src, n) for n in ast.parse(src).body
         if isinstance(n, ast.FunctionDef) and n.name == "reflexion_mesuree")
reglages = types.SimpleNamespace(ollama_cloud_reflexion="mesuree")
esp = {"Optional": Optional, "settings": reglages}
exec(f, esp)
r = esp["reflexion_mesuree"]

print("\n═══ RÉFLEXION BRIDÉE —", BACKEND.parent)
verifier("deepseek-v4-pro au palier COMPLEX : « low » (le réglage de prod du modèle puissant)",
         r("ollama_cloud", "deepseek-v4-pro", "complex") == "low")
verifier("deepseek-v4-pro ailleurs, et deepseek-v4-flash partout : « none »",
         r("ollama_cloud", "deepseek-v4-pro", "standard") == "none"
         and r("ollama_cloud", "deepseek-v4-flash", "complex") == "none"
         and r("ollama_cloud", "deepseek-v4-flash:0731", "light") == "none")
verifier("glm-5.3 et kimi-k3 : « low » (« none » fait penser glm en clair)",
         r("ollama_cloud", "glm-5.3-flash", "standard") == "low" and r("ollama_cloud", "kimi-k3", "complex") == "low")
verifier("vision : deepseek et glm « low » ; qwen3.5 n'a pas été mesuré, rien n'est envoyé",
         r("ollama_cloud", "deepseek-v4.1-flash", usage="vision") == "low"
         and r("ollama_cloud", "glm-5.3-flash", usage="vision") == "low"
         and r("ollama_cloud", "qwen3.5:397b", usage="vision") is None)
verifier("un modèle non mesuré, ou un autre fournisseur : rien n'est envoyé",
         r("ollama_cloud", "gpt-oss:120b") is None and r("openrouter", "deepseek/deepseek-v4-pro", "complex") is None
         and r("google", "gemini-flash-latest") is None and r("ollama_cloud", None) is None)
reglages.ollama_cloud_reflexion = "libre"
verifier("`OLLAMA_CLOUD_REFLEXION=libre` rend la main aux modèles", r("ollama_cloud", "deepseek-v4-pro", "complex") is None)

appel = src[src.index("class ResilientLLM"):]
verifier("la bride part avec CHAQUE appel du palier, pas seulement l'extraction documentaire",
         "effort = reflexion_mesuree(provider, model, self.tier.value)" in appel
         and 'options.setdefault("reasoning_effort", effort)' in appel)
verifier("« low » pense encore : son budget de sortie est relevé pour que la réponse tienne",
         "_BUDGET_REFLEXION_BASSE" in appel and "_BUDGET_REFLEXION_BASSE = 12000" in src)
verifier("la relance après une réponse VIDE coupe la réflexion au lieu de la doubler",
         'options["reasoning_effort"] = "none"' in appel)
verifier("la vision est bridée elle aussi",
         'reflexion_mesuree(provider, model, usage="vision")' in src and "llm_vision.bind(reasoning_effort=effort" in src)
verifier("le réglage existe dans config.py, à « mesuree » par défaut",
         'ollama_cloud_reflexion: str = "mesuree"' in (BACKEND / "config.py").read_text(encoding="utf-8"))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
