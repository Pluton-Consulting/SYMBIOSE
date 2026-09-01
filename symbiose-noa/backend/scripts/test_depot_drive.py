"""
Banc du DÉPÔT sur le Drive — l'assistant range un document, il n'écrase rien.

Le dépôt (`drive_deposer`, `drive_deposer_document`) est né le 30/08 : le
pendant Symbiose du dépôt NAS du projet jumeau, dont il reprend les leçons
payées — jamais d'écrasement, jamais un chemin arbitraire, extension garantie
par le code. Ce banc vérifie sans réseau ni googleapiclient :

  · les REFUS mécaniques de `deposer` (aucun périmètre, nom déjà pris) ;
  · le geste composé `deposer_document` : finalisation, nom à l'extension
    vraie, compte rendu qui porte l'aperçu ;
  · les DÉCLARATIONS : effet `externe`, clôture satisfaite (SATISFAIT_PAR),
    scope d'écriture demandé au consentement, client d'écriture séparé.
"""
import ast
import asyncio
import pathlib
import sys
import types

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "backend"
racine = pathlib.Path(BACKEND)

echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


def extraire(chemin, noms, espace):
    """Exécute, du module livré, les seules définitions demandées."""
    arbre = ast.parse(pathlib.Path(chemin).read_text(encoding="utf-8"))
    gardes = []
    for n in arbre.body:
        if isinstance(n, ast.ImportFrom) and n.module == "__future__":
            gardes.append(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms:
            gardes.append(n)
        elif isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id in noms for c in n.targets):
            gardes.append(n)
    exec(compile(ast.Module(body=gardes, type_ignores=[]), str(chemin), "exec"), espace)
    manquants = [x for x in noms if x not in espace]
    assert not manquants, f"absent du module livré : {manquants}"
    return espace


print(f"\n═══ LE DÉPÔT SUR LE DRIVE — {BACKEND}\n")

# ── doublures : l'atelier et le modèle, sans monter le backend ─────────────
faux_modele = types.ModuleType("bureautique.modele")
faux_modele.FORMATS = ("docx", "pdf", "xlsx")
faux_atelier = types.ModuleType("bureautique.atelier")
FICHE = {"entete": {"titre": "Devis Dupont", "format": "docx"},
         "octets": 3160, "elements": 4, "extrait": "Devis n° 42 — Terrasse bois"}


def _terminer(jeton, proprietaire):
    _terminer.appels.append((jeton, proprietaire))
    return dict(FICHE)


_terminer.appels = []
faux_atelier.terminer = _terminer
faux_atelier.chemin_fichier = lambda jeton, proprio: str(
    racine / "scripts" / "test_depot_drive.py")   # un fichier qui existe vraiment
faux_paquet = types.ModuleType("bureautique")
sys.modules["bureautique"] = faux_paquet
sys.modules["bureautique.modele"] = faux_modele
sys.modules["bureautique.atelier"] = faux_atelier


class DriveRefuse(Exception):
    pass


class _Journal:
    def info(self, *a, **k):
        pass
    warning = info


class _Liste:
    def __init__(self, reponse):
        self._r = reponse

    def execute(self):
        return self._r


class _Files:
    def __init__(self, reponse):
        self._r = reponse

    def list(self, **kw):
        return _Liste(self._r)


class _Service:
    def __init__(self, reponse):
        self._files = _Files(reponse)

    def files(self):
        return self._files


def espace_drive(collision: bool):
    async def _service(identite=None):
# 01/09 : le client Drive est construit PAR IDENTITÉ (voir test_drive_personnel).
        return _Service({"files": [{"id": "deja-la"}] if collision else []})

    async def _racines(service):
        return ["RACINE"]

    async def _resoudre(service, chemin, racines, partout=False):
        return "ID-CIBLE"

    e = {"DriveRefuse": DriveRefuse, "logger": _Journal(), "asyncio": asyncio,
         "_service": _service, "_racines": _racines, "_resoudre": _resoudre,
         "_garde_perimetre": lambda dossier, perimetres: None,
         "_tout_le_drive": lambda perimetres: False,
         "_echappe": lambda v: v.replace("\\", "\\\\").replace("'", "\\'")}
    extraire(racine / "outils" / "drive.py",
             {"_nom_avec_extension", "deposer", "deposer_document"}, e)
    return e


def refuse(coro, attendu):
    try:
        asyncio.run(coro)
    except DriveRefuse as e:
        return attendu in str(e)
    except (PermissionError, FileNotFoundError) as e:
        return attendu in str(e)
    return False


# ── 1. l'extension appartient au code, pas à l'humeur du modèle ────────────
nom_ext = espace_drive(False)["_nom_avec_extension"]
verifier("« test 2 » reçoit l'extension du format réel",
         nom_ext("test 2", {"format": "docx"}) == "test 2.docx")
verifier("une extension MENTEUSE est corrigée",
         nom_ext("rapport.pdf", {"format": "docx"}) == "rapport.docx")
verifier("un point qui n'est pas une extension fait partie du nom",
         nom_ext("note.v2", {"format": "pdf"}) == "note.v2.pdf")
verifier("sans nom, le titre du document sert de nom",
         nom_ext(None, {"titre": "Devis Dupont", "format": "xlsx"}) == "Devis Dupont.xlsx")

# ── 2. les refus mécaniques de `deposer` ───────────────────────────────────
print()
deposer = espace_drive(False)["deposer"]
verifier("sans périmètre ouvert, le dépôt est refusé — et ce n'est pas « un Drive vide »",
         refuse(deposer("Devis 2026", "a.docx", b"x", []), "ouvert"))
verifier("sans dossier ou sans nom, refus",
         refuse(deposer("", "a.docx", b"x", [("ID", 0)]), "destination"))
verifier("un contenu vide ne part pas",
         refuse(deposer("Devis 2026", "a.docx", b"", [("ID", 0)]), "vide"))
deposer_collision = espace_drive(True)["deposer"]
verifier("un nom déjà pris est un REFUS, jamais un écrasement",
         refuse(deposer_collision("Devis 2026", "a.docx", b"x", [("ID", 0)]), "écrasé"))

# ── 3. le geste composé : finaliser ET déposer ─────────────────────────────
print()
e = espace_drive(False)
appels = []


async def _faux_depot(dossier, nom, contenu, perimetres=None):
    appels.append((dossier, nom, len(contenu)))
    return {"depose": True, "nom": nom, "dossier": dossier,
            "message_final": "posé."}

e["deposer"] = _faux_depot
r = asyncio.run(e["deposer_document"]("DOC-1", "Devis 2026", "noa-id",
                                      nom="devis dupont", perimetres=[("ID", 0)]))
verifier("le document est FINALISÉ avant le dépôt (terminer appelé, au bon propriétaire)",
         _terminer.appels == [("DOC-1", "noa-id")], str(_terminer.appels))
verifier("le nom déposé porte l'extension du format réel",
         appels and appels[0][1] == "devis dupont.docx", str(appels))
verifier("le compte rendu porte le titre, le format et l'extrait pour l'aperçu",
         r.get("titre") == "Devis Dupont" and r.get("format") == "docx"
         and "Terrasse bois" in r.get("extrait", ""), str(r))
verifier("la note dicte l'aperçu `doc_apercu` au modèle",
         "doc_apercu" in r.get("note", ""))
verifier("un propriétaire vide est refusé — un document appartient à quelqu'un",
         refuse(e["deposer_document"]("DOC-1", "Devis 2026", "  "), "compte identifié"))

# ── 4. déclarations, clôture, scopes ───────────────────────────────────────
print()
skills_src = (racine / "skills" / "outils.py").read_text(encoding="utf-8")
verifier("drive_deposer et drive_deposer_document sont déclarés à effet EXTERNE",
         skills_src.count('effet="externe"') >= 2
         and '"drive_deposer"' in skills_src and '"drive_deposer_document"' in skills_src)
verifier("le catalogue promet ce que le code tient : jamais d'écrasement",
         "N'ecrase jamais" in skills_src)

annonce_src = (racine / "agents" / "annonce.py").read_text(encoding="utf-8")
verifier("le geste composé SATISFAIT la clôture du document (leçon du jumeau)",
         '"drive_deposer_document"' in annonce_src.split("SATISFAIT_PAR")[1][:400])

consentement = (racine / "scripts" / "google_consentement.py").read_text(encoding="utf-8")
verifier("le consentement demande désormais l'écriture",
         '"https://www.googleapis.com/auth/drive"' in consentement)

connecteur = (racine / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
verifier("la lecture garde son scope minimal, l'écriture a son client séparé",
         'drive.readonly' in connecteur and "_SCOPES_ECRITURE" in connecteur
         and "_build_service_ecriture" in connecteur)
verifier("un jeton en lecture seule échoue en le DISANT",
         "ne porte que la LECTURE" in connecteur
         and "refuse l'ÉCRITURE" in (racine / "outils" / "drive.py").read_text(encoding="utf-8"))

print(f"\n═══ {len(echecs)} échec(s)" + (" — tout passe" if not echecs else f" : {echecs}"))
sys.exit(1 if echecs else 0)
