"""
Banc « UNE RECHERCHE DRIVE NE FAIT PAS L'INVENTAIRE DU DRIVE » — 17/09, 18:07, Symbiose.
`drive_chercher("Symbiose Paysage charte")` : le motif entier ne donne rien, le repli prenait
« le mot le plus long » — « Symbiose », le nom de l'entreprise, présent dans des milliers de
fichiers — puis le chemin de CHACUN était reconstruit par un appel Google par dossier parent.
Plus de quatre minutes, puis l'échec. Et la correction qui a déclenché cette recherche était
partie au modèle rapide sans réflexion, par la voie rapide du routeur.

Sans réseau : fonctions extraites du code livré, service Google doublé (il COMPTE ses appels).
"""
import ast
import asyncio
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
arbre = ast.parse(src)


def extrait(noms):
    return "\n\n".join(ast.get_source_segment(src, n) for n in arbre.body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms)


print("\n═══ RECHERCHE DRIVE RAPIDE —", BACKEND.parent)
esp = {"re": __import__("re"), "unicodedata": __import__("unicodedata"), "asyncio": asyncio, "MAX_PROFONDEUR": 12,
       "MAX_APPELS_CHEMINS": 150, "_CATALOGUES": {}, "Optional": __import__("typing").Optional}
esp["_ACCENTS"] = str.maketrans("àâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ", "aaaeeeeiioouuucAAAEEEEIIOOUUUC")
exec(extrait({"_nu", "_mots_de_repli", "_chemins_cibles"}), esp)
repli = esp["_mots_de_repli"]
nu = esp["_nu"]

jetons = [t for t in nu("Symbiose Paysage charte").split() if len(t) >= 3]
verifier("le motif EXACT de prod : le repli est « charte », jamais le nom de l'entreprise",
         repli(jetons, ["Symbiose Paysage"]) == ["charte"], str(repli(jetons, ["Symbiose Paysage"])))
verifier("plusieurs mots utiles : du plus long au plus court, trois au plus",
         repli(["devis", "terrasse", "martin", "bois", "symbiose"], ["Symbiose Paysage"]) == ["terrasse", "martin", "devis"])
verifier("un seul mot, ou que des mots omniprésents : AUCUN repli (mieux vaut « rien » en deux secondes)",
         repli(["charte"], ["Symbiose Paysage"]) == [] and repli(["symbiose", "paysage"], ["Symbiose Paysage"]) == [])
verifier("sans nom de Drive connu, le repli reste possible", repli(["devis", "martin"], []) == ["martin", "devis"])


class _Service:
    appels = 0

    def files(self):
        return self

    def get(self, fileId=None, **k):
        self._id = fileId
        return self

    def execute(self):
        _Service.appels += 1
        return {"id": self._id, "name": f"api-{self._id}", "parents": []}


# Un catalogue gardé : racine > Études > Client, comme en prod.
esp["_CATALOGUES"]["service"] = {"construit_le": 123.0, "dossiers": {
    "D1": {"nom": "SYMBIOSE PAYSAGE", "parents": ["DRIVE"]},
    "D2": {"nom": "1-ÉTUDES", "parents": ["D1"]},
    "D3": {"nom": "33 CENAC - Esprit Bastide", "parents": ["D2"]}}}
elements = [{"id": f"F{i}", "nom": f"fichier {i}.pdf", "parents": ["D3"], "dossier": False} for i in range(400)]
elements.append({"id": "D3", "nom": "33 CENAC - Esprit Bastide", "parents": ["D2"], "dossier": True})
asyncio.run(esp["_chemins_cibles"](_Service(), elements, {"DRIVE": "Symbiose Paysage"}))
verifier("400 fichiers trouvés : ZÉRO appel Google pour leurs chemins (tout vient du catalogue gardé)",
         _Service.appels == 0, f"{_Service.appels} appels")
verifier("le chemin est complet et exact, Drive partagé compris",
         elements[0]["chemin"] == "Symbiose Paysage/SYMBIOSE PAYSAGE/1-ÉTUDES/33 CENAC - Esprit Bastide", elements[0]["chemin"])
verifier("un DOSSIER trouvé porte son propre nom en fin de chemin", elements[-1]["chemin"].endswith("1-ÉTUDES/33 CENAC - Esprit Bastide"))
hors = [{"id": f"X{i}", "nom": "x", "parents": [f"INCONNU{i}"], "dossier": False} for i in range(400)]
_Service.appels = 0
asyncio.run(esp["_chemins_cibles"](_Service(), hors, {}))
verifier("hors catalogue, l'API est BORNÉE : jamais plus de 150 appels, le reste garde un chemin partiel",
         _Service.appels <= 150 and all("chemin" in e for e in hors), f"{_Service.appels} appels")
esp["_CATALOGUES"].clear()
_Service.appels = 0
asyncio.run(esp["_chemins_cibles"](_Service(), [{"id": "F", "nom": "f", "parents": ["P"], "dossier": False}], {}))
verifier("sans catalogue (démarrage à froid), l'ancien chemin par l'API fonctionne toujours", _Service.appels == 1)

cherche = src[src.index("async def chercher("):]
verifier("`chercher` essaie le motif entier puis les mots UTILES", "essais = [motif] + _mots_de_repli(jetons, list(drives.values()))" in cherche
         and "max(jetons, key=len)" not in cherche)

a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
voie = a1[a1.index("if question_meta(str(state.get(\"query\")"):][:1200]
verifier("la voie rapide évite l'appel d'orientation, pas la réflexion : une suite courte part au palier qui raisonne",
         '"llm_tier": "complex"' in voie and '"llm_tier": "standard"' not in voie)
verifier("« oui », « non », « ok » dans une conversation sont des ordres d'agir ; « merci », « bonjour » restent au modèle rapide",
         '"complex" if suite_a_agir else "standard"' in a1 and "_nu in _ACCORDS and bool(state.get(\"messages\"))" in a1
         and '"merci"' not in a1[a1.index("_ACCORDS = {"):a1.index("_ACCORDS = {") + 160])

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
