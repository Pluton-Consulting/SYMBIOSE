"""
Banc « une colonne se trouve à la clé près » — 18/09, recette pilotée.

« Combien de clients n'ont pas d'adresse mail ? » : `contient: {"Email": "@"}` rendait 0 — la colonne
s'appelle « E-mail ». « Quel est notre client le plus rentable ? » : « Marge brute (BR) » recopié à un
espace près → « aucune des 687 lignes n'est lisible comme un nombre ». Le nom d'une colonne se compare
sans casse, sans accents, sans espaces ni ponctuation, en Python ET dans la clause SQL.
"""
import ast
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print("\n═══ COLONNES TOLÉRANTES —", BACKEND.parent)
src = (BACKEND / "skills" / "donnees.py").read_text(encoding="utf-8")
voulus = {"_cle_comparaison", "_sans_s", "_clause_contient", "_valeur_de"}
esp = {}
exec(compile(ast.Module(body=[n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in voulus],
                        type_ignores=[]), "donnees.py", "exec"), esp)
cle, valeur_de, clause = esp["_cle_comparaison"], esp["_valeur_de"], esp["_clause_contient"]
verifier("« Marge brute (BR) » = « marge_brute_br » = « MARGE BRUTE BR »",
         cle("Marge brute (BR)") == cle("marge_brute_br") == cle("MARGE BRUTE BR"))
verifier("« Email » = « E-mail » = « e_mail » ; « fournisseurs » = « fournisseur » (le pluriel reste)",
         cle("Email") == cle("E-mail") == cle("e_mail") and cle("fournisseurs") == cle("Fournisseur"))
ligne = {"champs": {}, "data": {"Marge brute (BR)": "1 234,50", "E-mail": "a@b.fr", "Ville": "Salles"}}
verifier("`_valeur_de` lit la colonne recopiée à un espace ou un tiret près",
         valeur_de(ligne, "marge brute BR") == "1 234,50" and valeur_de(ligne, "Email") == "a@b.fr"
         and valeur_de(ligne, "ville") == "Salles" and valeur_de(ligne, "telephone") == "")
sql, params = clause({"Email": "@", "Ville": "Salles"}, 4)
verifier("la clause SQL cherche la clé normalisée dans TOUTES les clés de la ligne, trois paramètres par colonne",
         params == ["Email", "email", "%@%", "Ville", "ville", "%Salles%"] and "jsonb_each_text" in sql
         and "$4" in sql and "$5" in sql and "$6" in sql and "$7" in sql and "$9" in sql, str(params))
verifier("sans fragment : TRUE, aucun paramètre", clause({}, 4) == ("TRUE", []))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
