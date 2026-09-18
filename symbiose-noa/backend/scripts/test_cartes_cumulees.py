"""
Banc « un brouillon par mail = une carte par mail » — 18/09, recette pilotée, prompt 7.

Dix `redaction_email` dans un tour rendaient dix blocs de cartes ; la règle « un publipostage
refait remplace le précédent » (03/09) n'en gardait qu'UN : neuf réponses finissaient en prose,
sans bouton. `_fondre_les_cartes` cumule les petites rédactions et garde la règle du 03/09 pour
les publipostages.
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


print("\n═══ UNE CARTE PAR BROUILLON —", BACKEND.parent)
arbre = ast.parse((BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8"))
voulus = {"_fondre_les_cartes", "MAX_CARTES_D_UNE_REDACTION"}
corps = [n for n in arbre.body
         if (isinstance(n, ast.FunctionDef) and n.name in voulus)
         or (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id in voulus for c in n.targets))]
esp = {}
exec(compile(ast.Module(body=corps, type_ignores=[]), "agent1.py", "exec"), esp)
fondre = esp["_fondre_les_cartes"]


def bloc(*cartes):
    return {"type": "reponses_mail", "titre": "Brouillon — modifiable", "boite": "b@x.fr", "reponses": list(cartes)}


dix = [bloc({"ref": f"r{i}", "de": f"c{i}@x.fr", "objet": f"Re: {i}", "reponse": f"texte {i}"}) for i in range(10)]
f = fondre(dix)
verifier("dix rédactions distinctes donnent UN bloc de dix cartes, dans l'ordre",
         len(f["reponses"]) == 10 and [c["ref"] for c in f["reponses"]] == [f"r{i}" for i in range(10)], str(len(f["reponses"])))
verifier("le titre dit le nombre, la boîte reste", "10" in f["titre"] and f["boite"] == "b@x.fr")
r = fondre([bloc({"ref": "r1", "objet": "Re: A", "reponse": "v1"}), bloc({"ref": "r2", "objet": "Re: B", "reponse": "x"}),
            bloc({"ref": "r1", "objet": "Re: A", "reponse": "v2 retouchée"})])
verifier("une carte refaite pour le même message remplace la sienne, à sa place",
         [c["reponse"] for c in r["reponses"]] == ["v2 retouchée", "x"], str(r["reponses"]))
r2 = fondre([bloc({"de": "A@x.fr", "objet": "Re:  Devis", "reponse": "v1"}), bloc({"de": "a@x.fr", "objet": "re: devis", "reponse": "v2"})])
verifier("sans référence, même destinataire et même objet = la même carte (une retouche ne double rien)",
         r2["reponses"] == [{"de": "a@x.fr", "objet": "re: devis", "reponse": "v2"}] and r2["titre"] == "Brouillon — modifiable")
gros1 = bloc(*[{"de": f"c{i}@x.fr", "objet": "Vœux", "reponse": "v1"} for i in range(95)])
gros2 = bloc(*[{"de": f"c{i}@x.fr", "objet": "Voeux !", "reponse": "v2"} for i in range(95)])
verifier("un publipostage refait REMPLACE le précédent (règle du 03/09 intacte) : 95 cartes, pas 190",
         fondre([gros1, gros2]) is gros2)
verifier("une rédaction après un publipostage : la rédaction prime, le publipostage ne s'y mêle pas",
         len(fondre([gros1, dix[0], dix[1]])["reponses"]) == 2)
verifier("deux cartes sans aucune identité ne s'écrasent pas",
         len(fondre([bloc({"reponse": "a"}), bloc({"reponse": "b"})])["reponses"]) == 2)
src = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("`_blocs_garantis` passe par la fusion", "[_fondre_les_cartes(du_genre)]" in src)

# La recopie APPROCHANTE d'un brouillon (quelques mots changés) s'efface aussi ; la présentation reste.
voulus2 = {"_sans_recopie_du_brouillon", "_aplati_texte"}
esp2 = {}
exec(compile(ast.Module(body=[n for n in arbre.body if isinstance(n, ast.FunctionDef) and n.name in voulus2], type_ignores=[]), "agent1.py", "exec"), esp2)
carte = ("Bonjour Monsieur Farou,\n\nMerci pour les photos et les plans, c'est très clair. Je prépare un chiffrage pour "
         "l'aménagement de l'allée et des surfaces autour du garage et je reviens vers vous rapidement. Souhaitez-vous "
         "qu'on se donne un rendez-vous sur place pour valider les détails ?\n\nCordialement,")
prose = ("Voici les neuf réponses, une carte par mail.\n\n8. Réponse à Patrick Farou, 15/09 (vouvoiement)\n\nBonjour Monsieur Farou,\n\n"
         "Merci pour les photos et les plans, c'est très clair. Je prépare un chiffrage pour l'aménagement de l'allée et des "
         "surfaces autour du garage et reviens vers vous très rapidement. Souhaitez-vous qu'on se voie sur place pour valider "
         "les détails ?\n\nCordialement, Benjamin Durou\n\nListe à part des mails non traités : Pantxika Sola.")
r = esp2["_sans_recopie_du_brouillon"](prose, [carte])
verifier("la recopie APPROCHANTE d'un brouillon (mots changés) s'efface ; la présentation et la liste à part restent",
         "Merci pour les photos" not in r and "Réponse à Patrick Farou" in r and "Liste à part" in r and "Voici les neuf" in r, r)
autre = "Bonjour Monsieur Farou,\n\nJe vous confirme que le chantier de la piscine est reporté au mois de mai, comme convenu avec Julien."
verifier("une phrase qui n'est PAS le brouillon reste (moins de 85 % de mots communs)",
         "chantier de la piscine" in esp2["_sans_recopie_du_brouillon"](autre, [carte]))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
