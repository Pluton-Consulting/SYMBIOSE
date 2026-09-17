"""
Banc « la rédaction dit sur quoi elle s'appuie » — 18/09.

Relevé de Noa : « à la place de "je rédige la réponse" il faudrait plus de détails ».
Une étape part vers l'écran à la FIN de son nœud : le libellé du nœud `rediger` reste donc
affiché pendant TOUTE la passe d'écriture qui suit — la plus longue du tour — et il ne
disait rien. Il dit désormais combien d'actions nourrissent la réponse, de quelles sortes,
combien ont échoué, et pourquoi on réécrit quand c'est une reprise. Des comptes et des
sortes, JAMAIS de contenu ni de nom technique.
"""
import importlib
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print("\n═══ LA RÉDACTION DIT SUR QUOI ELLE S'APPUIE —", BACKEND.parent)
J = importlib.import_module("agents.journal")
etat = {"tool_results": [{"skill": "lire_mails", "ok": True}, {"skill": "lire_mail", "ok": True},
                         {"skill": "drive_ouvrir", "ok": False}, {"skill": "chiffre_affaires", "ok": True}]}
d = J.detail_redaction(etat)
verifier("combien d'actions, de quelles sortes, et les échecs",
         "4 actions" in d and "mails ×2" in d and "fichiers" in d and "données" in d and "1 sans succès" in d, d)
verifier("ni nom de skill ni contenu, et le libellé tient sur une ligne",
         "lire_mails" not in d and "drive_" not in d and len(d) <= J.MAX_LIBELLE)
verifier("une seule action : singulier", "1 action (" in J.detail_redaction({"tool_results": [{"skill": "lire_mails"}]}))
verifier("sans action, elle le dit", "aucune action" in J.detail_redaction({}))
verifier("un état mal formé ne lève jamais", isinstance(J.detail_redaction({"tool_results": ["x", None]}), str)
         and isinstance(J.detail_redaction(None), str))
d2 = J.detail_redaction({**etat, "verification": {"statut": "a_corriger", "problemes": [{}, {}]}})
verifier("une reprise après relecture dit combien de points elle corrige", "2 points relevés à la relecture" in d2, d2)
verifier("une sortie sur une note se dit", "je fais le point" in J.detail_redaction({**etat, "note_sortie": "x"}))
verifier("`libelle` affiche la précision pour le nœud de rédaction, le libellé nu sinon",
         J.libelle("rediger", {"redaction_detail": d}) == d and J.libelle("rediger", {}) == "je rédige la réponse")
verifier("le relecteur n'est plus muet, parle au passé, et dit quand un point ne tient pas",
         J.libelle("verifier", {}).startswith("j'ai relu")
         and "je le reprends" in J.libelle("verifier", {"verification": {"statut": "a_corriger"}}))
agent1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("le nœud de rédaction pose la précision, et la clé d'état est déclarée",
         '"redaction_detail": detail_redaction(state)' in agent1
         and "redaction_detail:" in (BACKEND / "agents" / "state.py").read_text(encoding="utf-8"))

print(f"\n{'═' * 70}\n{'✗ ' + str(len(echecs)) + ' échec(s) : ' + ', '.join(echecs) if echecs else '✓ 0 échec'}\n")
sys.exit(1 if echecs else 0)
