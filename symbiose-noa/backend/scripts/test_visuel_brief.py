"""
Banc du brief visuel — la saison vient de la demande, la demande entre dans le brief.
Fonctions pures extraites du module livré (visuels.py importe le dépôt au chargement).
"""
import sys, ast, pathlib
BACKEND = sys.argv[1] if len(sys.argv) > 1 else "backend"
src = (pathlib.Path(BACKEND) / "skills" / "visuels.py").read_text(encoding="utf-8")
arbre = ast.parse(src); espace = {}
for n in arbre.body:
    if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("_SAISONS", "DEFAUTS", "GABARIT")) \
       or (isinstance(n, ast.FunctionDef) and n.name in ("_saison_deduite", "_brief_client")):
        exec(compile(ast.Module(body=[n], type_ignores=[]), "visuels", "exec"), espace)
sd, bc = espace["_saison_deduite"], espace["_brief_client"]
echecs = []
def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond: echecs.append(nom)
print(f"\n═══ BRIEF VISUEL — {BACKEND}\n")
verifier("« en plein hiver avec une légère neige » → hiver ET neige dans la saison",
         "winter" in sd("Un grand jardin", "petit bassin", "", "en plein hiver avec une légère neige") and "snow" in sd("", "", "", "légère neige"))
verifier("la neige dans la SCÈNE suffit (le modèle l'y avait mise)", "snow" in sd("large modern garden in winter with light snow", "", "", ""))
verifier("automne → autumn", "autumn" in sd("jardin en automne"))
verifier("rien de saisonnier → vide (le défaut reprend)", sd("jardin avec piscine", "terrasse bois") == "")
verifier("la demande brute entre dans le brief, en français, bornée",
         "CLIENT BRIEF" in bc("Un grand jardin sans arbre, neige légère") and bc("x" * 900).count("x") == 500)
verifier("sans demande, rien n'est ajouté", bc("") == "")
print(f"\n═══ {len(echecs)} échec(s)" + (f" : {', '.join(echecs)}" if echecs else " — tout passe"))
sys.exit(1 if echecs else 0)
