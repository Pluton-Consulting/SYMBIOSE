"""
Skills de la bibliothèque d'outils — la couche qui parle au modèle.

Chaque skill valide ses paramètres, appelle la fonction composée, et rend un
échec comme un ÉCHEC (`SkillError`). Les fonctions de `outils/` ne connaissent
ni l'utilisateur ni le protocole d'action : elles font le travail, c'est ici
qu'on branche l'identité et les droits.

Symbiose n'a pas de NAS : sa bibliothèque porte les documents et le mode
d'emploi. Les visuels gardent leurs deux actions séparées (voir
`outils/docs/visuels.md` : réunir un brief gratuit et une génération facturée
reviendrait à payer un tirage à chaque reformulation).
"""
from __future__ import annotations

import logging

logger = logging.getLogger("symbiose.skills.outils")


def _echec(message: str):
    from skills.executor import SkillError
    raise SkillError(message)


def _proprietaire(user) -> str:
    return str(getattr(user, "id", "") or "")


def _perimetres(user):
    """Les dossiers du Drive que CE rôle a le droit de voir.

    Composer n'ouvre aucun droit : le périmètre est recalculé à chaque appel,
    à partir du rôle réel, jamais passé par le modèle.
    """
    from outils.drive import perimetres_visibles
    return perimetres_visibles(getattr(user, "role", None))


async def _drive(fonction, *args, **kwargs):
    """Appelle un geste Drive et rend un échec comme un ÉCHEC.

    `DriveRefuse` porte des messages écrits POUR le modèle — « ce n'est pas un
    Drive vide, dis-le tel quel ». Les laisser passer en clair est le seul moyen
    qu'il ne transforme pas un refus de périmètre en « le Drive est vide ».
    """
    from outils.drive import DriveRefuse
    try:
        return await fonction(*args, **kwargs)
    except DriveRefuse as e:
        _echec(str(e))
    except Exception as e:  # noqa: BLE001
        _echec(str(getattr(e, "detail", None) or e))


# ── Google Drive ─────────────────────────────────────────────────────

async def drive_apercu(data: dict, user) -> dict:
    """Compte et classe le contenu d'un dossier du Drive, sans lister le détail."""
    from outils.drive import apercu
    return await _drive(apercu, (data.get("dossier") or "").strip() or None,
                        perimetres=_perimetres(user))


async def drive_arborescence(data: dict, user) -> dict:
    """L'arbre du Drive — complet si aucun dossier n'est précisé — en un appel."""
    from outils.drive import arborescence
    return await _drive(arborescence,
                        (data.get("dossier") or "").strip() or None,
                        data.get("profondeur") or 0,
                        perimetres=_perimetres(user))


async def drive_ouvrir(data: dict, user) -> dict:
    """Lit un fichier du Drive depuis son nom."""
    from outils.drive import ouvrir
    nom = (data.get("nom") or "").strip()
    if not nom:
        _echec("Donne le `nom` du fichier à ouvrir.")
    return await _drive(ouvrir, nom, perimetres=_perimetres(user))


async def drive_lire_lot(data: dict, user) -> dict:
    """Lit plusieurs fichiers du Drive correspondant à un motif."""
    from outils.drive import lire_lot
    motif = (data.get("motif") or "").strip()
    if not motif:
        _echec("Donne le `motif` des fichiers à lire (un morceau de leur nom).")
    return await _drive(lire_lot, motif,
                        (data.get("dossier") or "").strip() or None,
                        data.get("limite") or 5,
                        perimetres=_perimetres(user))


async def produire_document(data: dict, user) -> dict:
    """Crée, remplit et finalise un document en un seul appel."""
    from outils.documents import produire

    proprio = _proprietaire(user)
    if not proprio:
        _echec("Impossible de produire un document sans compte identifié.")
    titre = (data.get("titre") or "").strip()
    if not titre:
        _echec("Donne un `titre` au document.")

    blocs = data.get("blocs") or data.get("elements") or data.get("contenu")
    if isinstance(blocs, dict):
        blocs = [blocs]
    try:
        return await produire(
            titre=titre, blocs=blocs, proprietaire=proprio,
            format=(data.get("format") or "pdf").strip().lower(),
            entete=(data.get("entete") or "").strip(),
            pied=(data.get("pied") or "").strip(),
            numeroter=data.get("numeroter", True))
    except Exception as e:  # noqa: BLE001
        _echec(str(getattr(e, "detail", None) or e))


async def mode_emploi(data: dict, user) -> dict:
    """Le mode d'emploi complet d'un outil, à la demande.

    Ce texte n'est PAS injecté dans le prompt : c'est tout son intérêt. Les
    vocabulaires, limites et pannes connues pèsent des milliers de caractères
    qu'on ne peut pas faire porter à chaque tour.
    """
    from outils import mode_emploi as lire_doc, outils_disponibles
    nom = (data.get("outil") or "").strip()
    if not nom:
        return {"outils": [{"nom": n, "libelle": l} for n, l in outils_disponibles()],
                "note": "Précise `outil` pour obtenir son mode d'emploi."}
    return {"outil": nom, "mode_emploi": lire_doc(nom)}


# ── Déclarations : tout ce que le système doit savoir, ICI ───────────
from skills.registre import Declaration

SKILLS = {
    "drive_apercu": Declaration(
        fonction=drive_apercu,
        description=(
            # LE VOCABULAIRE MAISON vit dans la première entrée Drive : c'est au
            # moment de CHOISIR l'action que le modèle en a besoin. Personne ne
            # dit « Google Drive » en entier — on dit « le Drive », « le cloud »,
            # « le partage ».
            "COMPTE et resume un dossier du DRIVE : combien de dossiers, de "
            "fichiers, de quels types. LE DRIVE, LE CLOUD, GOOGLE et LE PARTAGE "
            "designent la meme chose. A utiliser des qu'on demande un NOMBRE ou "
            "« ce qu'il y a sur le Drive ». `dossier` accepte le NOM ou le "
            "CHEMIN, sans identifiant. Le nom d'un DRIVE PARTAGE est un debut "
            "de chemin valide (ex. « Holding Symbiose Paysage/Communication »)"),
        optionnels=["dossier"],
        effet="lecture",
        libelle="je regarde ce que contient le dossier"),
    "drive_arborescence": Declaration(
        fonction=drive_arborescence,
        description=("ARBRE COMPLET du Drive (Drives partages inclus) en UNE "
                     "action : sans `dossier`, TOUT y passe, avec les comptes. "
                     "Rend `schema` : recopie-le TEL QUEL dans un bloc ```. "
                     "`dossier` (NOM ou CHEMIN) limite a un sous-arbre"),
        optionnels=["dossier", "profondeur"],
        effet="lecture",
        libelle="je parcours les dossiers du Drive"),
    "drive_ouvrir": Declaration(
        fonction=drive_ouvrir,
        description=("OUVRE et lit un fichier du Drive depuis son NOM, sans en "
                     "connaitre l'identifiant. La voie normale pour lire un fichier"),
        requis=["nom"],
        effet="lecture",
        libelle="j'ouvre le fichier"),
    "drive_lire_lot": Declaration(
        fonction=drive_lire_lot,
        description=("LIT plusieurs fichiers du Drive correspondant a un motif "
                     "(5 maximum)"),
        requis=["motif"], optionnels=["dossier", "limite"],
        effet="lecture",
        libelle="je lis les fichiers"),
    "produire_document": Declaration(
        fonction=produire_document,
        description=(
            # Le detail de la mise en forme (valeurs de taille et de couleur)
            # vit dans `outils/docs/documents.md`, lisible via `mode_emploi` :
            # le catalogue est injecte a CHAQUE tour, y compris ceux qui ne
            # produisent aucun document. On y garde de quoi CHOISIR l'action,
            # pas de quoi la parametrer finement.
            # LE SEUIL EN PAGES, PAS EN BLOCS. « environ 30 blocs » ne parle
            # pas a une demande formulee « un docx de 10 pages » : le modele
            # appelait donc ce geste, obtenait 2 pages, et RECOMMENCAIT — sept
            # fois, six documents produits, aucun livre. Le geste est en UN
            # COUP : il finalise, donc rien ne se rallonge apres.
            # 395 caracteres : le catalogue est injecte a CHAQUE tour, le
            # plafond de 400 par description n'est pas negociable.
            "PRODUIT un document telechargeable (pdf, docx, xlsx) en UNE fois. "
            "`blocs` : {bloc:titre|paragraphe|liste|tableau|saut_page|feuille}. "
            "UNIQUEMENT si COURT : 2-3 pages, environ 30 blocs. AU-DELA "
            "(5 pages, 10 pages, rapport, guide) ce geste FINALISE et rien ne "
            "se rallonge apres : passe par `creer_document` + "
            "`ajouter_document` repetes + `terminer_document`. "
            "Mise en forme : `mode_emploi` documents"),
        requis=["titre", "blocs"],
        optionnels=["format", "entete", "pied", "numeroter"],
        effet="ecriture_interne",
        libelle="je produis le document"),
    "mode_emploi": Declaration(
        fonction=mode_emploi,
        description=("MODE D'EMPLOI complet d'un outil (drive, documents, visuels) : "
                     "conventions, limites, pannes connues. A lire quand aucune "
                     "action ne couvre le besoin"),
        optionnels=["outil"],
        effet="lecture",
        libelle="je relis le mode d'emploi de l'outil"),
}
