"""
Banc de la synchro Drive — « elle avance, elle lit Word et Excel, et elle dit quand elle s'arrête ».

POURQUOI. Table `synchronisations` du VPS, 31/08 : 34 568 fichiers listés, 438
ingérés, `abandonnés_trop_lents: 5` — la veille 34 565 / 436 / 5. Le journal :
les mêmes cinq PDF d'architecte abandonnés à 90 s, puis « 5 documents trop
lents, arrêt ». La synchro s'arrêtait donc TOUJOURS au même endroit, tout ce qui
venait après n'était jamais lu, et l'écran affichait « Terminée » avec
`parcours_complet: true`. En plus, le connecteur ne lisait ni .docx ni .xlsx
(« à ajouter ici »), et re-téléchargeait les 438 mêmes fichiers à chaque
passage — d'où ~1 000 embeddings remis en file pour rien.

CE QUE CE BANC PROUVE, sans Drive ni base : les fonctions PURES extraites du
connecteur (`_inchange`, `_trop_gros`, `_instant`, mémoire des fichiers lents
dans un dossier temporaire) font ce qu'elles disent ; et, sur le source livré,
que le listage demande `modifiedTime` et `size`, que les parseurs communs sont
branchés, que l'arrêt anticipé est DIT (`arret_anticipe`, `non_examines`), que le
routeur le traduit en statut « partielle » et que l'écran sait l'afficher.

Propre à Symbiose (le connecteur Drive l'est) ; le routeur et l'écran sont du socle.
"""
import os
import pathlib
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from typing import Optional

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend")
FRONTEND = BACKEND.parent / "frontend"
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
debut = src.index("def _instant(")
fin = src.index("async def _dates_ingerees(")


class _Journal:
    def warning(self, *a, **k): pass
    info = warning


espace = {"Optional": Optional, "logger": _Journal(),
          "MAX_OCTETS_PDF": 25 * 1024 * 1024, "FICHIER_LENTS": "drive_lents.json"}
exec(src[debut:fin], espace)  # noqa: S102 — code du dépôt
_inchange, _trop_gros, _instant = espace["_inchange"], espace["_trop_gros"], espace["_instant"]
_lire_lents, _ecrire_lents = espace["_lire_lents"], espace["_ecrire_lents"]

print(f"\n═══ SYNCHRO DRIVE INCRÉMENTALE — {BACKEND.parent}\n")

print("1. Un fichier inchangé depuis son ingestion n'est pas relu")
modif = "2026-08-20T10:00:00.000Z"
apres = datetime(2026, 8, 31, 7, 22, tzinfo=timezone.utc)
avant = datetime(2026, 8, 1, tzinfo=timezone.utc)
verifier("modifiedTime Drive lu en datetime UTC", _instant(modif) == datetime(2026, 8, 20, 10, tzinfo=timezone.utc))
verifier("ingéré APRÈS la modification → inchangé, sauté", _inchange({"modifiedTime": modif}, apres) is True)
verifier("ingéré AVANT la modification → à relire", _inchange({"modifiedTime": modif}, avant) is False)
verifier("jamais ingéré → à lire", _inchange({"modifiedTime": modif}, None) is False)
verifier("sans modifiedTime → à lire (le doute se lève en relisant)", _inchange({}, apres) is False)
verifier("une date naïve côté base est comprise en UTC",
         _inchange({"modifiedTime": modif}, apres.replace(tzinfo=None)) is True)

print("\n2. Un PDF trop gros n'est pas téléchargé")
verifier("PDF de 40 Mo → sauté", _trop_gros({"mimeType": "application/pdf", "size": str(40 * 1024 * 1024)}) is True)
verifier("PDF de 3 Mo → lu", _trop_gros({"mimeType": "application/pdf", "size": "3000000"}) is False)
verifier("un .docx de 40 Mo n'est pas concerné (ce sont les PDF vectoriels qui tiennent 90 s)",
         _trop_gros({"mimeType": "application/x", "name": "x.docx", "size": str(40 * 1024 * 1024)}) is False)
verifier("taille absente ou illisible → lu", _trop_gros({"mimeType": "application/pdf"}) is False
         and _trop_gros({"mimeType": "application/pdf", "size": "n/a"}) is False)

print("\n3. Les fichiers lents sont mémorisés d'un passage à l'autre")
with tempfile.TemporaryDirectory() as d:
    ancien = os.environ.get("DOCUMENTS_DIR")
    os.environ["DOCUMENTS_DIR"] = d
    try:
        verifier("sans mémoire : dictionnaire vide, pas d'exception", _lire_lents() == {})
        _ecrire_lents({"id-coupes": modif})
        verifier("écrit puis relu", _lire_lents() == {"id-coupes": modif})
        verifier("dans le volume des documents (survit au redéploiement)",
                 (pathlib.Path(d) / "drive_lents.json").exists())
    finally:
        if ancien is None:
            del os.environ["DOCUMENTS_DIR"]
        else:
            os.environ["DOCUMENTS_DIR"] = ancien

print("\n4. Le connecteur : listage, parseurs, arrêt anticipé dit")
verifier("le listage demande modifiedTime et size", "files(id,name,mimeType,modifiedTime,size)" in src)
verifier("Word/Excel/CSV passent par ingestion.parsers", "from ingestion.parsers import" in src and "analyser(name, data)" in src)
verifier("les images restent hors champ (pas d'OCR d'un Drive de photos)", "endswith(EXT_IMAGE)" in src)
verifier("un fichier abandonné est mémorisé au moment du timeout", "lents[f[\"id\"]] = f.get(\"modifiedTime\")" in src)
verifier("un fichier mémorisé et inchangé est sauté", 'lents.get(f["id"]) == (f.get("modifiedTime") or "")' in src)
verifier("l'arrêt anticipé est écrit dans le résultat", '"arret_anticipe"' in src and '"non_examines"' in src)
verifier("le nombre de fichiers non examinés est calculé", "non_examines += len(fichiers) - i - 1" in src)
verifier("les comptes inchangés / lents ignorés / trop gros sortent dans le bilan",
         '"inchangés": inchanges' in src and '"lents_ignorés"' in src and '"trop_gros"' in src)

print("\n5. Le routeur et l'écran disent « partielle »")
routeur = (BACKEND / "routers" / "ingestion.py").read_text(encoding="utf-8")
verifier("routeur : arret_anticipe → statut partielle", 'statut = "partielle" if anticipe else "terminee"' in routeur)
verifier("routeur : la raison est écrite (erreur) et lue par l'écran", "relancer pour continuer" in routeur)
ecran = (FRONTEND / "components" / "settings" / "SyncTab.tsx").read_text(encoding="utf-8")
verifier("écran : étiquette « Partielle »", 'partielle: { texte: "Partielle"' in ecran)
verifier("écran : la raison s'affiche pour une synchro partielle", 'e.etat === "partielle") return e.erreur' in ecran)
verifier("écran : chargement visible et nouvelles tentatives (les cartes qui « ne s'affichent pas »)",
         "Chargement des connecteurs" in ecran and "tentatives.current < 3" in ecran)

print(f"\n═══ {len(echecs)} échec(s)" + (f" : {', '.join(echecs)}" if echecs else " — tout passe"))
sys.exit(1 if echecs else 0)
