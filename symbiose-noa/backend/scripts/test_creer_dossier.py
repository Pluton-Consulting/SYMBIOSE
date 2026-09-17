"""
Banc « CRÉER UN DOSSIER SUR LE DRIVE » — 17/09, Symbiose.

Demandé trois fois en prod (« crée-moi un dossier étude avec le fichier type 33-MODELE »,
« nouveau dossier ») : aucun geste ne savait créer un dossier ni copier le dossier type.
⚠️ Le jeton Google de prod ne porte que `drive.readonly` au 17/09 : ce geste n'a JAMAIS
écrit sur le vrai Drive. Ce banc exécute `creer_dossier` LIVRÉ contre un Drive doublé :

  · le dossier se crée DANS le parent résolu, jamais ailleurs ;
  · un dossier du même nom (casse et accents près) fait REFUSER, rien n'est créé ;
  · le contenu du dossier type est copié, sous-dossiers compris, et la copie est BORNÉE ;
  · un Drive en lecture seule rend un refus qui dit quoi faire ;
  · le geste est `externe` (accord humain) et rangé dans une famille.
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


print("\n═══ CRÉER UN DOSSIER SUR LE DRIVE —", BACKEND.parent)
source = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
arbre = ast.parse(source)
voulus = {"creer_dossier", "voisins", "_nu", "_ACCENTS", "MAX_COPIES_DOSSIER_TYPE", "MAX_PROFONDEUR_COPIE", "_MIME_DOSSIER"}
corps = [n for n in arbre.body
         if (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in voulus)
         or (isinstance(n, ast.Assign) and any(isinstance(c, ast.Name) and c.id in voulus for c in n.targets))
         or (isinstance(n, ast.ImportFrom) and n.module == "__future__")]

DOSSIER = "application/vnd.google-apps.folder"


class Drive:
    """Un Drive en mémoire : {id: {name, mimeType, parents}}."""
    def __init__(self, lecture_seule=False):
        self.f = {"ETUDES": {"name": "1-ÉTUDES", "mimeType": DOSSIER, "parents": ["RACINE"]},
                  "D1": {"name": "33 ARCACHON - DUPONT", "mimeType": DOSSIER, "parents": ["ETUDES"]},
                  "D2": {"name": "33 LA TESTE - MARTIN", "mimeType": DOSSIER, "parents": ["ETUDES"]},
                  "MOD": {"name": "33 MODELE - Dossier type", "mimeType": DOSSIER, "parents": ["ETUDES"]},
                  "M1": {"name": "Devis type.docx", "mimeType": "x/docx", "parents": ["MOD"]},
                  "M2": {"name": "Photos", "mimeType": DOSSIER, "parents": ["MOD"]},
                  "M3": {"name": "lisez-moi.txt", "mimeType": "text/plain", "parents": ["M2"]}}
        self.n, self.lecture_seule, self.ecritures = 0, lecture_seule, []

    def files(self):
        return self

    def list(self, q="", **kw):
        parent = q.split("'")[1]
        seulement_dossiers = "mimeType='" + DOSSIER in q.replace(" ", "")
        res = [{"id": i, **v} for i, v in self.f.items() if parent in v["parents"]
               and (not seulement_dossiers or v["mimeType"] == DOSSIER)]
        return _Rep({"files": res})

    def create(self, body=None, **kw):
        if self.lecture_seule:
            return _Rep(None, erreur="<HttpError 403 insufficientPermissions>")
        self.n += 1
        i = f"N{self.n}"
        self.f[i] = {"name": body["name"], "mimeType": body["mimeType"], "parents": body["parents"]}
        self.ecritures.append(("dossier", body["name"], body["parents"][0]))
        return _Rep({"id": i, "name": body["name"], "webViewLink": "https://drive/" + i})

    def copy(self, fileId=None, body=None, **kw):
        self.n += 1
        i = f"N{self.n}"
        self.f[i] = {"name": body["name"], "mimeType": self.f[fileId]["mimeType"], "parents": body["parents"]}
        self.ecritures.append(("copie", body["name"], body["parents"][0]))
        return _Rep({"id": i})


class _Rep:
    def __init__(self, valeur, erreur=None):
        self.valeur, self.erreur = valeur, erreur

    def execute(self):
        if self.erreur:
            raise RuntimeError(self.erreur)
        return self.valeur


class DriveRefuse(Exception):
    pass


def monter(drive):
    async def _resoudre(service, chemin, racines, partout=False):
        nom = chemin.strip("/").split("/")[-1].lower()
        for i, v in drive.f.items():
            if v["mimeType"] == DOSSIER and (v["name"].lower() == nom or nom in v["name"].lower()):
                return i
        raise DriveRefuse(f"Dossier « {chemin} » introuvable.")

    async def _service(identite=None): return drive
    async def _racines(service): return ["RACINE"]
    async def _build(identite=None, ecriture=False): return drive
    import logging
    import unicodedata
    espace = {"asyncio": asyncio, "Optional": __import__("typing").Optional, "DriveRefuse": DriveRefuse,
              "_service": _service, "_racines": _racines, "_resoudre": _resoudre,
              "_build_service_pour": _build, "_un_fil_a_la_fois": lambda s: s,
              "_tout_le_drive": lambda p: True, "_garde_perimetre": lambda cible, p: None,
              "logger": logging.getLogger("banc"), "unicodedata": unicodedata, "re": __import__("re")}
    exec(compile(ast.Module(body=corps, type_ignores=[]), "drive.py", "exec"), espace)
    return espace


P = [(None, "all")]
d = Drive(); e = monter(d)
r = asyncio.run(e["creer_dossier"]("1-ÉTUDES", "33 SAINT-MEDARD-EN-JALLES - LAQUET", "33 MODELE - Dossier type", perimetres=P))
verifier("le dossier est créé DANS le parent résolu, et nulle part ailleurs",
         r["cree"] and d.ecritures[0] == ("dossier", "33 SAINT-MEDARD-EN-JALLES - LAQUET", "ETUDES"), str(d.ecritures[:1]))
verifier("le contenu du dossier type est copié, sous-dossier et son fichier compris",
         r["copies"] == ["Devis type.docx", "Photos/", "Photos/lisez-moi.txt"] and not r["non_copies"], str(r["copies"]))
verifier("le dossier TYPE lui-même n'est ni déplacé ni modifié",
         d.f["MOD"]["parents"] == ["ETUDES"] and d.f["M1"]["parents"] == ["MOD"])
verifier("le compte rendu donne le nom exact, le chemin et ce qui a été repris",
         "33 SAINT-MEDARD-EN-JALLES - LAQUET" in r["message_final"] and r["chemin"].endswith("/33 SAINT-MEDARD-EN-JALLES - LAQUET"))

d2 = Drive(); e2 = monter(d2)
try:
    asyncio.run(e2["creer_dossier"]("1-ÉTUDES", "33 arcachon - dupont", perimetres=P))
    verifier("un dossier du même nom (casse près) fait REFUSER", False)
except DriveRefuse as x:
    verifier("un dossier du même nom (casse près) fait REFUSER, rien n'est créé",
             "existe déjà" in str(x) and not d2.ecritures, str(x))
for mauvais in ("", "a/b"):
    try:
        asyncio.run(e2["creer_dossier"]("1-ÉTUDES", mauvais, perimetres=P))
        verifier(f"nom refusé : « {mauvais} »", False)
    except DriveRefuse:
        verifier(f"un nom vide ou avec une barre oblique est refusé (« {mauvais} »)", not d2.ecritures)
try:
    asyncio.run(e2["creer_dossier"]("1-ÉTUDES", "X", perimetres=[]))
    verifier("sans périmètre, rien", False)
except DriveRefuse:
    verifier("sans périmètre ouvert à ce rôle, rien n'est créé", not d2.ecritures)

d3 = Drive(lecture_seule=True); e3 = monter(d3)
try:
    asyncio.run(e3["creer_dossier"]("1-ÉTUDES", "33 PESSAC - DURAND", perimetres=P))
    verifier("Drive en lecture seule : refus explicite", False)
except DriveRefuse as x:
    verifier("Drive en LECTURE SEULE : le refus dit quoi faire (consentement à rejouer)",
             "lecture seule" in str(x) and "google_consentement" in str(x), str(x))

d4 = Drive(); e4 = monter(d4)
for k in range(200):
    d4.f[f"G{k}"] = {"name": f"fichier {k}.pdf", "mimeType": "x/pdf", "parents": ["MOD"]}
r4 = asyncio.run(e4["creer_dossier"]("1-ÉTUDES", "33 BIGANOS - GROS", "33 MODELE - Dossier type", perimetres=P))
verifier("la copie est BORNÉE, et ce qui n'a pas été copié est DIT",
         len(r4["copies"]) == e4["MAX_COPIES_DOSSIER_TYPE"] and len(r4["non_copies"]) > 0
         and "n'ont pas pu être copiés" in r4["message_final"], f"{len(r4['copies'])} / {len(r4['non_copies'])}")
v = asyncio.run(e["voisins"]("1-ÉTUDES", perimetres=P, combien=2))
verifier("`voisins` rend des dossiers existants : le nommage de la maison se lit sur eux", len(v) >= 2 and all(isinstance(x, str) for x in v))

outils = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
bloc = outils[outils.index('"drive_creer_dossier": Declaration('):][:1400]
verifier("le geste est EXTERNE : accord humain obligatoire", 'effet="externe"' in bloc and 'requis=["parent", "nom"]' in bloc)
verifier("le catalogue demande de montrer deux dossiers voisins AVANT, et ne promet ni renommage ni suppression",
         "deux dossiers voisins" in bloc and "ne supprime rien" in bloc)
verifier("le geste est rangé dans une famille",
         '"drive_creer_dossier"' in (BACKEND / "skills" / "familles.py").read_text(encoding="utf-8"))

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
