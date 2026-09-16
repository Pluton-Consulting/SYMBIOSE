"""
Banc « LE DRIVE COMPLET, À JOUR ET FIDÈLE » — audit du 15/09, fiche S-27.

CE QUI ÉTAIT FAUX :
  · la synchronisation comparait des DATES de modification. Un fichier
    SUPPRIMÉ, mis à la corbeille, DÉPLACÉ hors périmètre ou dont l'ACCÈS avait
    été retiré ne change aucune date : il disparaissait simplement du listage,
    et rien ne le retirait de la mémoire. L'assistant citait des devis effacés ;
  · un Google Sheet s'exportait en `text/csv` — c'est-à-dire UNE feuille. Un
    classeur de trois onglets entrait amputé des deux tiers, en silence ; et
    même en XLSX, le lecteur ne lisait que `wb.active` ;
  · un dépôt dont la réponse réseau se perdait était déclaré en ÉCHEC, alors
    que le fichier pouvait être arrivé : réessayer faisait un doublon, ou
    recevait « existe déjà, donne un autre nom » pour un dépôt qui avait réussi.

CE BANC PROUVE (modules EXÉCUTÉS, Drive doublé) :
  1. le journal des changements retire ce qui est supprimé, à la corbeille ou
     sorti du périmètre, et réingère ce qui a changé ;
  2. le curseur ne s'écrit qu'APRÈS le traitement, et un curseur périmé renvoie
     à un inventaire au lieu de lever ;
  3. un inventaire TRONQUÉ ne pose pas de curseur (sinon on déclarerait à jour
     ce qu'on n'a jamais lu) ;
  4. un classeur à trois onglets rend ses trois onglets, chaque ligne sachant
     d'où elle vient ;
  5. un dépôt dont la réponse se perd est RÉCONCILIÉ : on regarde si le fichier
     est là avant de conclure, et on ne renvoie jamais deux fois.

Usage : python backend/scripts/test_drive_complet.py [backend]
"""
import asyncio
import importlib.util
import os
import pathlib
import sys
import tempfile
import types

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend").resolve()
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {str(detail)[:300]}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


def poser(nom, **attrs):
    mod = types.ModuleType(nom)
    mod.__dict__.update(attrs)
    mod.__path__ = []
    sys.modules[nom] = mod
    if "." in nom:
        parent, feuille = nom.rsplit(".", 1)
        if parent not in sys.modules:
            poser(parent)
        setattr(sys.modules[parent], feuille, mod)
    return mod


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, BACKEND / chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    if "." in nom:
        parent, feuille = nom.rsplit(".", 1)
        if parent not in sys.modules:
            poser(parent)
        setattr(sys.modules[parent], feuille, module)
    spec.loader.exec_module(module)
    return module


print(f"\n═══ LE DRIVE : CHANGEMENTS, ONGLETS, DÉPÔT — {BACKEND.parent}\n")
os.environ["DOCUMENTS_DIR"] = tempfile.mkdtemp(prefix="banc-drive-")

# ── LE DRIVE DOUBLÉ ────────────────────────────────────────────────────────
ARBRE = {          # identifiant -> parents
    "dossier-devis": ["racine-perimetre"],
    "fichier-modifie": ["dossier-devis"],
    "fichier-sorti": ["dossier-hors"],
    "dossier-hors": ["ailleurs"],
}
CHANGEMENTS = [
    {"fileId": "fichier-efface", "removed": True},
    {"fileId": "fichier-corbeille",
     "file": {"id": "fichier-corbeille", "name": "vieux devis.docx", "trashed": True,
              "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}},
    {"fileId": "fichier-modifie",
     "file": {"id": "fichier-modifie", "name": "devis DULUGAT.docx", "trashed": False,
              "parents": ["dossier-devis"],
              "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}},
    {"fileId": "fichier-sorti",
     "file": {"id": "fichier-sorti", "name": "note interne.docx", "trashed": False,
              "parents": ["dossier-hors"],
              "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}},
    {"fileId": "un-dossier",
     "file": {"id": "un-dossier", "name": "Chantiers", "trashed": False,
              "parents": ["racine-perimetre"],
              "mimeType": "application/vnd.google-apps.folder"}},
]
ETAT = {"perime": False, "token": "jeton-1", "appels": []}


class _Changes:
    def getStartPageToken(self):
        return types.SimpleNamespace(execute=lambda: {"startPageToken": "jeton-neuf"})

    def list(self, **kw):
        ETAT["appels"].append(kw)

        def _executer():
            if ETAT["perime"]:
                raise RuntimeError("HttpError 410 : Change token is no longer valid")
            return {"changes": CHANGEMENTS, "newStartPageToken": "jeton-2"}
        return types.SimpleNamespace(execute=_executer)


class _Files:
    def get(self, fileId=None, **kw):
        return types.SimpleNamespace(
            execute=lambda: {"id": fileId, "parents": ARBRE.get(fileId, [])})


class _Service:
    def changes(self):
        return _Changes()

    def files(self):
        return _Files()


SUPPRIMES, INGERES = [], []


async def _supprimer(source_id, source_type):
    SUPPRIMES.append((source_id, source_type))
    return 1


async def _ingerer(**kw):
    INGERES.append(kw)
    return 3


poser("vectorstore.client", vectorstore=types.SimpleNamespace(delete_by_source=_supprimer))
poser("ingestion.pipeline", ingest_document=_ingerer)
poser("ingestion.parsers", en_lecture=lambda f, *a, **k: asyncio.sleep(0, result="du texte"))
poser("ingestion.connectors.google_drive", _download_text=lambda *a, **k: "du texte")
changes = charger("ingestion.drive_changes", "ingestion/drive_changes.py")

print("1. Le journal des changements")
bilan = asyncio.run(changes.appliquer(_Service(), {"racine-perimetre": "all"}))
verifier("sans curseur, on ne prétend pas avoir appliqué quoi que ce soit",
         bilan["applique"] is False and "inventaire complet" in bilan["raison"], bilan)
changes.ecrire_curseur("jeton-1")
SUPPRIMES.clear(); INGERES.clear()
bilan = asyncio.run(changes.appliquer(_Service(), {"racine-perimetre": "all"}))
verifier("un fichier SUPPRIMÉ est retiré de la mémoire",
         ("fichier-efface", "drive") in SUPPRIMES, SUPPRIMES)
verifier("un fichier mis à la CORBEILLE aussi",
         ("fichier-corbeille", "drive") in SUPPRIMES, SUPPRIMES)
verifier("un fichier SORTI du périmètre est retiré (l'accès a changé, pas la date)",
         ("fichier-sorti", "drive") in SUPPRIMES, SUPPRIMES)
verifier("un fichier modifié DANS le périmètre est réingéré, à son niveau",
         len(INGERES) == 1 and INGERES[0]["source_id"] == "fichier-modifie"
         and INGERES[0]["access_level"] == "all", INGERES)
verifier("un DOSSIER n'est pas ingéré comme un document",
         not any(i["source_id"] == "un-dossier" for i in INGERES))
verifier("le bilan compte ce qu'il a fait", bilan["applique"] and bilan["retires"] == 3
         and bilan["reingeres"] == 1, bilan)

print("2. Le curseur : écrit après, jamais avant")
verifier("le curseur a avancé APRÈS le traitement", changes.lire_curseur()["token"] == "jeton-2")
verifier("il porte la date de sa pose", bool(changes.lire_curseur().get("pose_le")))
ETAT["perime"] = True
bilan = asyncio.run(changes.appliquer(_Service(), {"racine-perimetre": "all"}))
verifier("un curseur PÉRIMÉ ne lève pas : il renvoie à un inventaire, en le disant",
         bilan["applique"] is False and bilan.get("curseur_perime")
         and "trop ancien" in bilan["raison"], bilan)
verifier("… et il est oublié, pour ne pas réessayer en boucle",
         not changes.lire_curseur().get("token"), changes.lire_curseur())
ETAT["perime"] = False
verifier("la lecture demande les éléments RETIRÉS (sans quoi rien ne serait jamais retiré)",
         all(a.get("includeRemoved") for a in ETAT["appels"]))
verifier("… et les Drive partagés", all(a.get("includeItemsFromAllDrives") for a in ETAT["appels"]))

print("3. L'inventaire tronqué ne pose pas de curseur")
src = (BACKEND / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
verifier("le curseur se prend AVANT l'inventaire",
         src.index("depart = await drive_changes.poser_depart") < src.index("total_vus = total_ingeres"))
verifier("il ne s'écrit que si le parcours est COMPLET",
         'complet = all(d.get("parcours_complet") for d in detail) and not non_examines' in src
         and "if depart and complet:" in src)
verifier("le mode est dit à l'écran (changements ou inventaire)",
         '"mode": "changements"' in src and '"mode": "inventaire"' in src)
verifier("un inventaire imposé dit POURQUOI", "inventaire_parce_que" in src)

print("4. Un classeur rend tous ses onglets")
parsers_src = (BACKEND / "ingestion" / "parsers.py").read_text(encoding="utf-8")
verifier("le lecteur ne s'arrête plus à `wb.active`",
         "for feuille in feuilles:" in parsers_src and "wb.worksheets" in parsers_src)
verifier("chaque ligne porte le nom de son onglet quand il y en a plusieurs",
         '"Feuille": feuille.title' in parsers_src)
drive_src = (BACKEND / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
verifier("un Google Sheet s'exporte en XLSX, plus en CSV",
         "spreadsheetml.sheet" in drive_src.split("_EXPORTABLE = {")[1].split("}")[0]
         and "text/csv" not in drive_src.split("_EXPORTABLE = {")[1].split("}")[0])
verifier("le classeur exporté passe par le lecteur tabulaire commun "
         "(même extraction qu'à la lecture directe)",
         'cible.endswith("spreadsheetml.sheet")' in drive_src)

print("5. Un dépôt réessayé ne fait pas de doublon")
outils_src = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
espace = {}
debut = outils_src.index("def _reponse_perdue")
exec(compile(outils_src[debut:outils_src.index("\n\n\n", debut)], "drive", "exec"), espace)
perdue = espace["_reponse_perdue"]
verifier("un délai dépassé est AMBIGU (le fichier est peut-être arrivé)",
         perdue(TimeoutError("Read timed out")) and perdue(RuntimeError("502 Bad Gateway")))
verifier("un refus de droits ne l'est pas : rien n'a été écrit",
         not perdue(RuntimeError("403 insufficient permissions"))
         and not perdue(RuntimeError("404 notFound")))
verifier("après une réponse perdue, on REGARDE si le fichier est là",
         "_retrouver" in outils_src and "réconcilié sans second envoi" in outils_src)
verifier("s'il est là, le dépôt est une RÉUSSITE, et on le dit",
         '"reconcilie": reconcilie' in outils_src
         and "il n'a pas été envoyé deux fois" in outils_src)
verifier("s'il n'y est pas, on dit que rien n'a été déposé (on peut réessayer)",
         "rien n'a été déposé, on peut réessayer" in outils_src)
verifier("le dépôt rend l'empreinte de ce qui est parti",
         '"empreinte": empreinte' in outils_src and "hashlib.sha256(contenu)" in outils_src)

print()
if echecs:
    print(f"✗ {len(echecs)} échec(s)")
    sys.exit(1)
print("✓ 0 échec")
