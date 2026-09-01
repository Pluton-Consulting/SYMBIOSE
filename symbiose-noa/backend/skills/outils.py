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


def _identite(user) -> str:
    """Le compte Google au nom duquel agir sur le Drive.

    L'identifiant APPLICATIF de la session, jamais une valeur venue du modèle :
    le jeton Google d'une personne ne doit pouvoir être réclamé que par sa
    propre session. Composer deux gestes ne compose pas les droits — même règle
    que `_perimetres`.

    LE SUPER-ADMIN FAIT EXCEPTION, et c'est une décision de Noa (01/09) : « sauf
    super admin, où c'est connecté avec Benjamin Durou, ça ne bouge pas ». Le
    compte de service reste SA vue — c'est aussi celle dont vivent l'ingestion
    et l'enrichissement, qui classent les documents pour toute l'entreprise.
    Tous les autres, Benjamin compris en tant qu'utilisateur ordinaire, voient
    le Drive avec LEUR propre compte, et rien d'autre.

    LES DEUX FILTRES SE COMPOSENT : le jeton personnel borne par ce que Google
    laisse voir à cette personne, les périmètres bornent par ce que l'entreprise
    a déclaré pour ce rôle. Retirer l'un parce que l'autre existe rouvrirait
    tout ce qui n'a jamais été classé.
    """
    if str(getattr(user, "role", "") or "") == "super_admin":
        return ""
    return str(getattr(user, "id", "") or "")


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
    """Compte et classe le contenu d'un dossier du Drive, sans lister le détail.

    Le résumé s'affiche en blocs MÉCANIQUES (fiche + noms des sous-dossiers) :
    relevé le 01/09, laissé au modèle, l'aperçu devenait une carte de document
    inventée aux lignes vides.
    """
    from outils.drive import apercu
    from skills.affichage import garantir_apercu
    dossier = (data.get("dossier") or "").strip()
    resultat = await _drive(apercu, dossier or None, perimetres=_perimetres(user),
                            identite=_identite(user))
    return garantir_apercu(resultat, f"« {dossier} »" if dossier else "le Drive")


async def drive_photos(data: dict, user) -> dict:
    """LES PHOTOS d'un dossier du Drive, rangées au dépôt et prêtes à l'écran.

    « Montre-moi les photos de ce chantier » ne trouvait aucun geste : la
    recherche documentaire rend du texte, et `drive_ouvrir` refuse les images.
    Elles sont ici déposées comme un visuel produit, donc affichables et
    téléchargeables dans le chat, sans qu'aucun lien ne sorte de l'application.
    """
    from outils.drive import photos
    resultat = await _drive(
        photos,
        (data.get("dossier") or data.get("chantier") or "").strip() or None,
        (data.get("motif") or data.get("nom") or "").strip() or None,
        data.get("limite") or 6,
        perimetres=_perimetres(user), identite=_identite(user))
    if resultat.get("bloc_ui"):
        resultat["message_final"] = (
            f"Voici {resultat['nombre']} photo(s)"
            + (f" sur {resultat['disponibles']} trouvée(s)"
               if resultat.get("disponibles", 0) > resultat["nombre"] else "")
            + ((" ; " + str(resultat["trop_volumineuses"])
                + " étaient trop volumineuse(s) pour être affichée(s)")
               if resultat.get("trop_volumineuses") else "") + ".")
        resultat["a_faire"] = (
            "AFFICHE les photos : insère un bloc ```ui contenant EXACTEMENT le "
            "contenu de `bloc_ui`. Ce sont de VRAIES photos du Drive, pas des "
            "images générées : ne les présente jamais comme un rendu ou une "
            "simulation. Ne colle aucune adresse d'image en texte.")
    return resultat


async def drive_arborescence(data: dict, user) -> dict:
    """L'arbre du Drive — complet si aucun dossier n'est précisé — en un appel.

    L'arbre s'affiche par un bloc MÉCANIQUE (`arbre`) : demander au modèle de
    recopier le `schema` produisait une carte de document inventée, sans rien
    dedans (relevé le 01/09).
    """
    from outils.drive import arborescence
    from skills.affichage import garantir_arborescence
    dossier = (data.get("dossier") or "").strip()
    resultat = await _drive(arborescence, dossier or None,
                            data.get("profondeur") or 0,
                            perimetres=_perimetres(user),
                            identite=_identite(user))
    return garantir_arborescence(
        resultat, f"du dossier « {dossier} »" if dossier else "du Drive")


async def drive_chercher(data: dict, user) -> dict:
    """Dossiers ET fichiers dont le NOM porte un motif, à toutes les profondeurs.

    Demande de Noa du 01/09 : une information sur un client absente de la
    mémoire d'entreprise doit déclencher, d'instinct, une recherche par NOM
    dans le classement du Drive — partout, pas au seul premier niveau — puis
    la proposition d'aller plus loin. Le pendant du `nas_chercher` du projet
    jumeau, même forme de résultat, même affichage mécanique.
    """
    from outils.drive import chercher
    from skills.affichage import garantir_recherche
    motif = (data.get("motif") or data.get("nom") or data.get("client") or "").strip()
    if not motif:
        _echec("Donne le `motif` à chercher (nom de client, de chantier, de fichier).")
    resultat = await _drive(chercher, motif, perimetres=_perimetres(user),
                            identite=_identite(user),
                            page=data.get("page") or 1)
    return garantir_recherche(resultat, motif)


async def drive_ouvrir(data: dict, user) -> dict:
    """Lit un fichier du Drive depuis son nom."""
    from outils.drive import ouvrir
    nom = (data.get("nom") or "").strip()
    if not nom:
        _echec("Donne le `nom` du fichier à ouvrir.")
    return await _drive(ouvrir, nom, perimetres=_perimetres(user),
                        identite=_identite(user))


async def drive_lire_lot(data: dict, user) -> dict:
    """Lit plusieurs fichiers du Drive correspondant à un motif."""
    from outils.drive import lire_lot
    motif = (data.get("motif") or "").strip()
    if not motif:
        _echec("Donne le `motif` des fichiers à lire (un morceau de leur nom).")
    return await _drive(lire_lot, motif,
                        (data.get("dossier") or "").strip() or None,
                        data.get("limite") or 5,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


async def drive_deposer(data: dict, user) -> dict:
    """Dépose sur le Drive un document produit par l'assistant. ÉCRITURE."""
    from outils.drive import deposer

    dossier = (data.get("dossier") or "").strip()
    jeton = (data.get("document_id") or "").strip()
    if not dossier or not jeton:
        _echec("Il faut le dossier du Drive et le `document_id` d'un document "
               "déjà terminé (`terminer_document`).")

    # On ne dépose QUE des documents produits ici, et seulement ceux de la
    # personne : téléverser un chemin arbitraire du serveur ferait de ce skill
    # un moyen d'exfiltrer des fichiers internes vers le Drive.
    from bureautique.atelier import chemin_fichier, fiche
    proprio = _proprietaire(user)
    chemin = chemin_fichier(jeton, proprio)
    if not chemin:
        _echec("Document inconnu, pas encore terminé, ou appartenant à "
               "quelqu'un d'autre. Reprends le `document_id` EXACT rendu par "
               "`terminer_document`.")

    f = fiche(jeton, proprio) or {}
    entete = f.get("entete") or {}
    nom = data.get("nom") or f"{entete.get('titre', 'document')}.{entete.get('format', 'docx')}"

    with open(chemin, "rb") as fichier:
        contenu = fichier.read()
    return await _drive(deposer, dossier, nom, contenu,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


async def drive_deposer_document(data: dict, user) -> dict:
    """Finalise un document en cours et le dépose sur le Drive. EFFET EXTERNE."""
    from outils.drive import deposer_document

    doc = (data.get("document_id") or "").strip()
    dossier = (data.get("dossier") or "").strip()
    if not doc or not dossier:
        _echec("`document_id` et `dossier` sont requis.")
    # `proprietaire` (le propriétaire du BROUILLON) et `identite` (le compte
    # Google au nom duquel on écrit) sont deux notions distinctes : les
    # confondre exploserait au premier document repris par quelqu'un d'autre.
    return await _drive(deposer_document, doc, dossier, _proprietaire(user),
                        (data.get("nom") or "").strip() or None,
                        perimetres=_perimetres(user),
                        identite=_identite(user))


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
            "« ce qu'il y a sur le Drive ». Le resume S'AFFICHE AUTOMATIQUEMENT "
            "dans le chat : n'en fais jamais un document. `dossier` accepte le "
            "NOM ou le CHEMIN, sans identifiant ; le nom d'un DRIVE PARTAGE est "
            "un debut de chemin valide"),
        optionnels=["dossier"],
        effet="lecture",
        libelle="je regarde ce que contient le dossier"),
    "drive_photos": Declaration(
        fonction=drive_photos,
        description=(
            "MONTRE LES PHOTOS d'un dossier du DRIVE dans le chat : elles sont "
            "affichees en planche et telechargeables. A utiliser des qu'on "
            "demande de VOIR des images (« montre-moi les photos du chantier "
            "X », « les visuels de ce dossier »). `dossier` : le NOM ou le "
            "CHEMIN du dossier. `motif` : un bout de nom de fichier. `limite` : "
            "1 a 12 (6 par defaut). Ce sont de VRAIES photos, jamais un rendu "
            "genere : ne les presente pas comme une simulation"),
        optionnels=["dossier", "motif", "limite"],
        effet="lecture",
        libelle="je vais chercher les photos"),
    "drive_arborescence": Declaration(
        fonction=drive_arborescence,
        description=("ARBRE COMPLET du Drive (Drives partages inclus) en UNE "
                     "action : sans `dossier`, TOUT y passe, avec les comptes. "
                     "L'arbre S'AFFICHE AUTOMATIQUEMENT dans le chat : ne le "
                     "recopie pas, n'en fais jamais un document. "
                     "`dossier` (NOM ou CHEMIN) limite a un sous-arbre"),
        optionnels=["dossier", "profondeur"],
        effet="lecture",
        libelle="je parcours les dossiers du Drive"),
    "drive_chercher": Declaration(
        fonction=drive_chercher,
        description=(
            "CHERCHE dossiers ET fichiers par NOM sur TOUT le Drive, a toutes "
            "les profondeurs, et rend leurs CHEMINS. A utiliser D'INSTINCT "
            "quand une information sur un client, un chantier ou un "
            "fournisseur ne sort ni des fichiers importes ni des documents : "
            "le classement porte les noms des clients. Le resultat s'affiche "
            "automatiquement ; propose ensuite d'ouvrir ou d'explorer ce qui "
            "est trouve. `motif` : le nom cherche ; `page` pour la suite"),
        requis=["motif"], optionnels=["page"],
        effet="lecture",
        libelle="je cherche ce nom sur le Drive"),
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
    "drive_deposer": Declaration(
        fonction=drive_deposer,
        description=("DEPOSE sur le Drive un fichier deja produit, UNIQUEMENT "
                     "pour le RANGER dans le classement de l'entreprise. Un "
                     "document produit est DEJA telechargeable dans le chat : "
                     "ne depose JAMAIS pour « donner », « montrer » ou "
                     "« telecharger » un fichier. Ecrit sur le Drive : "
                     "validation humaine. N'ecrase jamais. Aucune suppression "
                     "ni renommage n'est possible : ne le promets pas"),
        requis=["dossier", "document_id"], optionnels=["nom"],
        # Écrire dans le classement de l'entreprise sort du périmètre de
        # l'application : effet EXTERNE, validation humaine obligatoire.
        effet="externe",
        libelle="je dépose le fichier sur le Drive"),
    "drive_deposer_document": Declaration(
        fonction=drive_deposer_document,
        description=("FINALISE un document en cours et le DEPOSE sur le Drive, "
                     "en un geste — UNIQUEMENT si on demande de le RANGER sur "
                     "le Drive. Pour donner ou telecharger un document dans le "
                     "chat, `terminer_document` suffit : le fichier y est deja. "
                     "`dossier` accepte le NOM (ex. « Devis 2026 »). Ecrit sur "
                     "le Drive : demande une validation humaine"),
        requis=["document_id", "dossier"], optionnels=["nom"],
        # Le depot ecrit dans le classement de l'entreprise : effet EXTERNE,
        # donc validation humaine — composer deux gestes ne compose pas les droits.
        effet="externe",
        libelle="je finalise et dépose le document"),
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
