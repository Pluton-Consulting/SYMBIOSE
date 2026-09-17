"""
LES ROUTINES — ce qu'on demande dix fois par semaine, en UN SEUL appel.

POURQUOI CE MODULE EXISTE. « Sors-moi la liste des clients » se répondait
jusqu'ici en enchaînant `interroger_donnees` trois fois : une fois sans
argument pour découvrir les jeux de données, une fois avec `source_type` pour
voir les colonnes, une fois avec un filtre pour obtenir les lignes. Trois
allers-retours, donc trois passages complets dans la cascade LLM — et chacun
paie les fournisseurs en panne avant d'atteindre celui qui répond. Sur la
session du 21/08, cela faisait une minute et demie pour une question dont la
réponse tient dans une requête SQL.

Le remède n'est pas un meilleur prompt : c'est de rendre le geste ATOMIQUE.
Une question fréquente mérite un skill qui la répond d'un coup, avec le bloc
d'écran déjà prêt. Moins d'appels au modèle, c'est moins de latence ET moins
d'occasions de se tromper.

LES ROUTINES :
  · `liste_clients`       — qui sont les clients, combien, avec quoi les joindre ;
  · `fiche_client`        — TOUT ce qu'on sait d'un client : devis, montants,
                            chiffre d'affaires, chantiers, contact — d'un seul
                            appel et à travers TOUS les jeux importés ;
  · `dossiers_en_attente` — ceux qui attendent une réponse depuis plus de N
                            jours, du plus ancien : le suivi, pas la recherche ;
  · `prix_observes`       — les prix que la maison PRATIQUE, lus ligne à ligne dans
                            ses devis et factures, et l'estimation qui en sort
                            (quantité × médian, fourchette, sources) ;
  · `check_mails`         — le point sur le courrier récent, prêt à être résumé.

ELLES NE SAVENT RIEN DU MÉTIER. Aucun nom de colonne n'est codé en dur : les
imports viennent de fichiers Excel ou CSV faits par le client, dont les
en-têtes varient (« Nom », « Client », « Raison sociale », « Société »…). Les
colonnes sont donc RECONNUES par famille de synonymes, et ce qui n'est pas
reconnu est rendu tel quel — mieux vaut afficher une colonne qu'on n'a pas su
nommer que de la perdre.
"""
from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger("pluton.skills.routines")

MAX_CLIENTS = 5000
# CE QUI ENTRE DANS LE BLOC D'ÉCRAN. Relevé le 22/08 : le bloc portait 300
# lignes, le modèle a dû le recopier, s'est arrêté vers la quarantième et a
# écrit « 300 affichés ». Un bloc que le modèle doit retaper doit tenir dans ce
# qu'il retape sans faute : soixante noms, et une pagination par initiale pour
# la suite. Le TOTAL, lui, reste exact et se dit.
MAX_AFFICHES = 60
MAX_LIGNES_PAR_JEU = 40


# ── Reconnaissance des colonnes, par familles de synonymes ──────────────────
#
# L'ordre compte : le premier synonyme trouvé gagne. « raison_sociale » avant
# « nom » parce qu'un fichier qui porte les deux met l'identité dans le premier
# et le nom du contact dans le second.
FAMILLES = {
    # « client » en DERNIER : c'est souvent un drapeau ou un identifiant, pas
    # un nom. « nom » avant lui, mais après la raison sociale (un fichier qui
    # porte les deux met l'identité dans la première et le contact dans le
    # second).
    "nom": ("raison_sociale", "raison sociale", "societe", "société",
            "nom_client", "customer", "entreprise", "nom", "name", "client"),
    # Le prénom à part : quand l'export le sépare du nom, « DUPONT » seul n'est
    # qu'un bout du client (relevé le 22/08 : « elle n'a donné que les noms »).
    "prenom": ("prenom", "prénom", "first_name", "firstname", "first name"),
    "email": ("email", "e-mail", "mail", "courriel", "adresse_mail"),
    "telephone": ("telephone", "téléphone", "tel", "portable", "mobile", "phone"),
    "ville": ("ville", "commune", "city", "localite"),
    "montant": ("montant_ttc", "total_ttc", "ttc", "montant_ht", "total_ht", "ht",
                "montant", "total", "prix", "amount", "chiffre_affaires", "ca"),
    "date": ("date", "date_devis", "date_facture", "date_signature", "created_at",
             "date_creation", "annee"),
    "statut": ("statut", "status", "etat", "état"),
    "reference": ("reference", "référence", "ref", "numero", "numéro", "num", "id"),
}


def _plat(texte) -> str:
    """Minuscules, sans accents, sans ponctuation : la forme qui se compare."""
    s = unicodedata.normalize("NFD", str(texte or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _colonne(donnees: dict, famille: str):
    """La colonne de cette famille présente dans l'enregistrement, ou None."""
    index = {_plat(k): k for k in donnees}
    for synonyme in FAMILLES.get(famille, ()):
        clef = index.get(_plat(synonyme))
        if clef is None:
            continue
        valeur = str(donnees[clef] or "").strip()
        if not valeur:
            continue
        # UN NOM CONTIENT DES LETTRES. Relevé le 22/08 : un export portait une
        # colonne « Client » valant « 1 » (un drapeau) à côté de « Nom » ; la
        # fiche s'est intitulée « 1 ». Une valeur sans lettre n'est pas une
        # identité, on passe au synonyme suivant.
        if famille == "nom" and not re.search(r"[a-zA-Z\u00C0-\u024F]", valeur):
            continue
        return clef
    return None


def _valeur(donnees: dict, famille: str) -> str:
    clef = _colonne(donnees, famille)
    return str(donnees[clef]).strip() if clef else ""


def _jsonb(valeur) -> dict:
    """Un JSONB tel qu'asyncpg le rend : une CHAÎNE, pas un dict.

    Relevé en production le 22/08, traces Langfuse : `liste_clients` rendait
    « dictionary update sequence element #0 has length 1; 2 is required » — le
    message de `dict()` nourri d'une chaîne. Aucun codec JSON n'est posé sur le
    pool (`database/connection.py`), donc `row["data"]` arrive en texte. Le
    banc ne l'avait pas vu parce que sa fausse base rendait des dicts : une
    doublure qui ment sur le TYPE teste un code qui n'existe pas. Elle rend
    désormais des chaînes, comme la vraie.
    """
    if not valeur:
        return {}
    if isinstance(valeur, dict):
        return valeur
    if isinstance(valeur, (bytes, bytearray)):
        valeur = valeur.decode("utf-8", "replace")
    if isinstance(valeur, str):
        import json
        try:
            d = json.loads(valeur)
            return d if isinstance(d, dict) else {}
        except ValueError:
            return {}
    try:
        return dict(valeur)
    except (TypeError, ValueError):
        return {}


def _nom_complet(d: dict) -> str:
    """Nom ET prénom quand l'export les sépare : « DUPONT Marie », pas « DUPONT »."""
    nom = _valeur(d, "nom")
    prenom = _valeur(d, "prenom")
    if prenom and _plat(prenom) not in _plat(nom):
        return f"{nom} {prenom}".strip()
    return nom


def _fusion(ligne) -> dict:
    """Les en-têtes d'origine ET le vocabulaire normalisé, dans un seul dict.

    La migration 020 conserve les deux à dessein : `data` porte les en-têtes du
    fichier tel qu'il a été exporté (« Raison sociale », « Montant HT »),
    `champs` la même ligne ramenée au vocabulaire du type (« nom »,
    « montant_ht »). Reconnaître une colonne a donc DEUX chances au lieu d'une
    — et l'export dont personne n'a normalisé les en-têtes reste lisible.

    `data` est appliqué en dernier : à valeur égale, l'orthographe d'origine
    l'emporte pour l'affichage, parce que c'est celle que le client reconnaît.
    """
    champs = _jsonb(ligne["champs"]) if "champs" in ligne.keys() else {}
    return {**champs, **_jsonb(ligne["data"])}


def _montant(texte) -> float:
    """« 12 450,50 € » → 12450.5. Rend 0.0 sur tout ce qui n'est pas un nombre.

    L'implémentation vit dans `skills/lecture.py`, avec la lecture des dates :
    elles avaient le même problème (du TEXTE écrit par un humain ou par un
    logiciel de gestion) et en avaient deux réponses différentes, dont une en
    SQL. Une seule règle, un seul endroit où la corriger.
    """
    from skills.lecture import lire_montant
    return lire_montant(texte)


def _euros(valeur: float) -> str:
    return f"{valeur:,.2f} €".replace(",", " ").replace(".", ",")


def _date_triable(texte) -> str:
    """« 12/03/2025 » → « 20250312 ». Chaîne vide si la date est illisible.

    POURQUOI TRIER. « Le dernier devis envoyé à X » est la première question
    que pose un dirigeant, et un export métier est trié par référence, jamais
    par date : la ligne la plus récente n'est pas la dernière du fichier. Sans
    ce tri, c'est le modèle qui doit comparer des dates écrites en toutes
    lettres pour désigner « la dernière » — exactement le calcul que le prompt
    lui interdit, et qu'il fait quand même.

    Ce qui est illisible se range en DERNIER, jamais en premier : une date
    qu'on ne sait pas lire ne doit pas se faire passer pour la plus récente.
    """
    from skills.lecture import cle_triable
    return cle_triable(texte)


async def _jeux(conn, niveaux: list) -> list:
    lignes = await conn.fetch(
        "SELECT DISTINCT source_type FROM document_metadata "
        "WHERE access_level = ANY($1::text[]) ORDER BY source_type", niveaux)
    return [l["source_type"] for l in lignes]


def _jeu_clients(existants: list):
    """Le jeu de données qui contient les clients, quel que soit son nom.

    On ne suppose pas « client » : un import peut s'appeler « clients »,
    « CLIENTS 2025 », « base_clients ». On cherche donc la racine dans le nom.
    """
    for candidat in existants:
        if "client" in _plat(candidat) or "customer" in _plat(candidat):
            return candidat
    return None


def _jeu_fournisseurs(existants: list):
    """Le jeu de données qui contient les fournisseurs, quel que soit son nom."""
    for candidat in existants:
        plat = _plat(candidat)
        if "fournisseur" in plat or "supplier" in plat or "vendor" in plat:
            return candidat
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  LISTE DES CLIENTS
# ═══════════════════════════════════════════════════════════════════════════
#
#  L'EXPORT DOIT SAVOIR RÉPONDRE À LA DEMANDE ENTIÈRE. Relevé le 23/08 :
#  « fais-moi un Excel avec une colonne pleine de tous les noms clients et une
#  colonne avec mon mail sur toutes les lignes ». Le skill ne savait produire
#  qu'un tableau figé (Client, Ville, Email, Téléphone) : le modèle a bien
#  fabriqué le fichier, a constaté qu'il ne portait pas la seconde colonne, et
#  s'est mis à DEMANDER l'adresse de son interlocuteur — deux tours de plus,
#  puis un troisième, sans jamais rien livrer. Une adresse que le serveur
#  connaît par la session, qui plus est.
#
#  Deux paramètres suffisent, et ils ne codent aucun métier :
#    · `colonnes` — celles qu'on garde (« juste les noms ») ;
#    · `ajouts`   — des colonnes CONSTANTES ({"E-mail": "@moi"}), où `@moi`
#      vaut l'adresse de la personne connectée. On ne la demande donc jamais.
_CLE_PAR_LIBELLE = {
    "client": "nom", "clients": "nom", "nom": "nom", "noms": "nom",
    "fournisseur": "nom", "fournisseurs": "nom",
    "raison_sociale": "nom", "societe": "nom",
    "ville": "ville", "villes": "ville", "commune": "ville",
    "email": "email", "e_mail": "email", "mail": "email", "mails": "email",
    "adresse_mail": "email", "courriel": "email",
    "telephone": "telephone", "tel": "telephone", "portable": "telephone",
}
# « @moi », « mon mail »… : l'adresse de celui qui parle, connue du serveur.
_C_EST_MOI = ("moi", "@moi", "mon_email", "mon_mail", "mon_adresse",
              "mon_adresse_mail", "mon_courriel", "utilisateur", "moi_meme")


def _colonnes_gardees(data: dict) -> list | None:
    """Les colonnes demandées, ramenées aux clés connues. `None` = toutes.

    Le nom reste TOUJOURS : une liste de clients sans les clients n'existe pas.
    """
    brut = data.get("colonnes")
    if isinstance(brut, str):
        brut = re.split(r"[,;/]| et ", brut)
    if not isinstance(brut, (list, tuple)) or not brut:
        return None
    gardees = ["nom"]
    for x in brut:
        cle = _CLE_PAR_LIBELLE.get(_plat(x))
        if cle and cle not in gardees:
            gardees.append(cle)
    return gardees


def _colonnes_ajoutees(data: dict, user) -> list:
    """Les colonnes constantes demandées en plus : `{"E-mail": "@moi"}`.

    Bornées à trois : au-delà, ce n'est plus une liste de clients enrichie,
    c'est un autre fichier — et il se fabrique avec l'atelier de documents.
    """
    import json as _j
    brut = data.get("ajouts") if data.get("ajouts") is not None else data.get("colonnes_fixes")
    if isinstance(brut, str):
        try:
            brut = _j.loads(brut)
        except ValueError:
            brut = None
    if not isinstance(brut, dict):
        return []
    moi = str(getattr(user, "email", "") or "").strip()
    sorties = []
    for libelle, valeur in list(brut.items())[:3]:
        titre = str(libelle or "").strip()[:40]
        if not titre:
            continue
        texte = str("" if valeur is None else valeur).strip()
        if _plat(texte) in _C_EST_MOI:
            texte = moi
        # Un jeton d'anonymisation resté orphelin (« [EMAIL_2] ») n'est pas une
        # valeur : dans un fichier remis à quelqu'un, il n'a rien à faire. Sur
        # une colonne de mail, la seule lecture honnête est l'adresse de la
        # session — celle que « mon mail » désignait ; ailleurs, la cellule
        # reste vide plutôt que d'écrire une balise technique.
        if re.fullmatch(r"\[[A-Z]+_\d+\]", texte):
            texte = moi if _CLE_PAR_LIBELLE.get(_plat(titre)) == "email" else ""
        sorties.append((titre, texte[:200]))
    return sorties


async def liste_clients(data: dict, user) -> dict:
    """Qui sont les clients, combien, et de quoi les joindre. UN appel."""
    return await _lister_annuaire(data, user, _jeu_clients, "client",
                                  "liste_clients", "fiche_client")


async def liste_fournisseurs(data: dict, user) -> dict:
    """Qui sont les fournisseurs, combien, et de quoi les joindre. UN appel.

    Relevé le 29/08 : « fais-moi un excel avec les noms fournisseurs » n'avait
    aucun geste — l'assistant proposait d'exporter la liste tout en disant ne
    pas y avoir accès. Un annuaire de fournisseurs se lit comme celui des
    clients : mêmes colonnes d'identité (raison sociale, société, nom), même
    export Excel. Une seule mécanique, deux jeux de données.
    """
    return await _lister_annuaire(data, user, _jeu_fournisseurs, "fournisseur",
                                  "liste_fournisseurs", None)


async def _lister_annuaire(data: dict, user, chercher_jeu, metier: str,
                           skill_nom: str, skill_fiche) -> dict:
    """Le corps commun des annuaires (clients, fournisseurs) : qui, combien,
    et de quoi les joindre — à l'écran ou en fichier Excel."""
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError

    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            existants = await _jeux(conn, niveaux)
            jeu = chercher_jeu(existants)
            if not jeu:
                # NE PAS RÉPONDRE « AUCUN ». Un jeu de données absent et un jeu
                # vide se ressemblent dans une réponse, et l'assistant a déjà
                # conclu « les données ne sont pas importées » alors qu'elles
                # l'étaient sous un autre nom.
                return {
                    "trouve": False,
                    "jeux_de_donnees": existants,
                    "message": (
                        f"Aucun jeu de données ne porte de nom de {metier}. Ce n'est PAS "
                        f"« il n'y a pas de {metier}s » : c'est que rien n'a été importé "
                        "sous ce nom. Jeux disponibles : "
                        + (", ".join(existants) if existants else "aucun") + "."),
                    "a_faire": ("Dis-le tel quel à l'utilisateur, propose d'importer le "
                                f"fichier des {metier}s depuis Paramètres > Import de "
                                "données, et n'invente AUCUN nom."),
                }

            total = await conn.fetchval(
                "SELECT COUNT(*) FROM document_metadata "
                "WHERE source_type = $1 AND access_level = ANY($2::text[])",
                jeu, niveaux)
            lignes = await conn.fetch(
                "SELECT data, champs FROM document_metadata "
                "WHERE source_type = $1 AND access_level = ANY($2::text[]) "
                "ORDER BY ligne NULLS LAST LIMIT $3",
                jeu, niveaux, MAX_CLIENTS)
    except Exception as e:  # noqa: BLE001
        logger.warning("Liste des %ss impossible : %s", metier, e)
        raise SkillError(f"La base des {metier}s est momentanément indisponible.")

    fiches = []
    for l in lignes:
        d = _fusion(l)
        nom = _nom_complet(d)
        if not nom:
            continue
        fiches.append({"nom": nom, "ville": _valeur(d, "ville"),
                       "email": _valeur(d, "email"), "telephone": _valeur(d, "telephone")})
    fiches.sort(key=lambda c: _plat(c["nom"]))

    # LA LISTE COMPLÈTE, C'EST UN FICHIER. Relevé le 22/08 : « il dit qu'il
    # affiche tout, il n'affiche jamais de grosse quantité ». Un bloc d'écran
    # n'est pas fait pour 478 lignes, et le modèle ne les recopiera jamais.
    # Quand on veut tout, on produit un Excel — rangé par l'atelier, servi par
    # la route des documents, affiché en aperçu dans le chat comme n'importe
    # quel fichier produit.
    veut_fichier = str(data.get("fichier") or data.get("format") or "").strip().lower() in (
        "1", "true", "oui", "vrai", "xlsx", "excel", "fichier", "csv", "complet", "tout")
    gardees = _colonnes_gardees(data)
    ajouts = _colonnes_ajoutees(data, user)
    if veut_fichier and fiches:
        return await _fichier_annuaire(fiches, jeu, total, user, gardees, ajouts, metier)

    # Pagination par initiale : « les clients en B », « la suite ».
    lettre = _plat(data.get("lettre") or "")[:1]
    if lettre:
        fiches = [c for c in fiches if _plat(c["nom"])[:1] == lettre]
    total_filtre = len(fiches)
    tronque_ecran = total_filtre > MAX_AFFICHES
    fiches = fiches[:MAX_AFFICHES]

    if not fiches:
        return {"trouve": False, "source_type": jeu, "nombre": 0,
                "message": (f"Le jeu « {jeu} » existe ({total} enregistrement(s)) mais "
                            f"aucun nom de {metier} n'a pu y être lu. Les colonnes ne "
                            "portent peut-être pas un nom reconnu."),
                "a_faire": "Propose d'appeler `interroger_donnees` pour voir les colonnes réelles."}

    identite = metier.capitalize()
    colonnes = [identite] + [t for t, c in (("Ville", "ville"), ("Email", "email"),
                                            ("Téléphone", "telephone"))
                             if any(x[c] for x in fiches)
                             and (gardees is None or c in gardees)]
    cles = {identite: "nom", "Ville": "ville", "Email": "email", "Téléphone": "telephone"}
    bloc = {"type": "table",
            "columns": colonnes + [t for t, _ in ajouts],
            "rows": [[c[cles[t]] for t in colonnes] + [v for _, v in ajouts]
                     for c in fiches]}

    n = len(fiches)
    if lettre:
        compte = (f"{total_filtre} {metier}{'s' if total_filtre > 1 else ''} dont le nom "
                  f"commence par « {lettre.upper()} » (sur {total} au total)"
                  + (f", les {n} premiers affichés." if tronque_ecran else ", tous affichés."))
    else:
        compte = (f"{total} {metier}{'s' if total > 1 else ''} en base"
                  + (f", les {n} premiers affichés par ordre alphabétique." if tronque_ecran
                     else ", tous affichés."))
    return {
        "trouve": True,
        "source_type": jeu,
        "nombre": total,
        "affiches": n,
        "lettre": lettre.upper() or None,
        "clients": fiches,
        "bloc_ui": bloc,
        "message_final": compte,
        "a_faire": ("Commence par cette phrase, mot pour mot : « " + compte + " ». "
                    "Puis AFFICHE la liste en insérant un bloc ```ui contenant EXACTEMENT "
                    "le contenu de `bloc_ui` — n'écris PAS les noms toi-même en texte, ne "
                    "dis pas un autre nombre que " + str(n) + " pour les affichés ni que "
                    + str(total) + " pour le total. "
                    + (f"Pour la suite, rappelle `{skill_nom}` avec `lettre` (une initiale). "
                       if tronque_ecran else "")
                    + (f"Pour le détail d'UN {metier}, c'est `{skill_fiche}`."
                       if skill_fiche else "")),
    }


async def _fichier_annuaire(fiches: list, jeu: str, total: int, user,
                            gardees: list | None, ajouts: list, metier: str) -> dict:
    """Toute la liste dans un .xlsx produit par l'atelier, avec son bloc `fichier`."""
    import asyncio
    from bureautique.atelier import ouvrir, ajouter, terminer
    proprio = str(getattr(user, "id", "") or "")
    ajouts = ajouts or []
    identite = metier.capitalize()
    colonnes = [(identite, "nom"), ("Ville", "ville"), ("Email", "email"), ("Téléphone", "telephone")]
    colonnes = [(t_, c) for t_, c in colonnes
                if c == "nom" or (any(x.get(c) for x in fiches)
                                  and (gardees is None or c in gardees))]
    entete = {"titre": f"Liste des {metier}s", "format": "xlsx"}
    elements = [{"type": "feuille", "nom": f"{identite}s",
                 "entetes": [t_ for t_, _ in colonnes] + [t_ for t_, _ in ajouts],
                 "lignes": [[c.get(cle, "") for _, cle in colonnes] + [v for _, v in ajouts]
                            for c in fiches]}]

    def _produire():
        jeton = ouvrir(entete, proprio)
        ajouter(jeton, elements, proprio)
        return jeton, terminer(jeton, proprio)

    try:
        jeton, fiche = await asyncio.to_thread(_produire)
    except Exception as e:  # noqa: BLE001
        logger.warning("Excel des %ss impossible : %s", metier, e)
        from skills.erreurs import SkillError
        raise SkillError(f"Le fichier des {metier}s n'a pas pu être produit. Réessayez, ou "
                         "demandez la liste à l'écran (par initiale).")

    # `titre` en plus du nom de fichier : c'est par lui que la réhydratation
    # reconnaît, au tour suivant, une vignette inventée qui parle de CE
    # fichier-là — et la remplace par le bloc réel (cf. `_designe_le_meme`).
    bloc = {"type": "fichier", "url": f"/api/documents/{jeton}", "nom": f"{metier}s.xlsx",
            "titre": entete["titre"], "format": "xlsx", "octets": fiche.get("octets")}
    entetes = [t_ for t_, _ in colonnes] + [t_ for t_, _ in ajouts]
    compte = (f"{total} {metier}{'s' if total > 1 else ''}, la liste complète est dans le fichier "
              f"Excel ci-dessous ({len(fiches)} lignes, colonnes : "
              + ", ".join(entetes) + ").")
    return {
        "trouve": True, "source_type": jeu, "nombre": total, "affiches": len(fiches),
        "fichier": bloc["url"], "bloc_ui": bloc, "message_final": compte,
        "a_faire": ("Dis : « " + compte + " », puis insère un bloc ```ui contenant EXACTEMENT "
                    "le contenu de `bloc_ui` (type `fichier`) : l'écran affiche l'aperçu du "
                    "tableau et le bouton de téléchargement. N'écris AUCUN nom toi-même. Le "
                    "lien vaut 24 h."),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  FICHE D'UN CLIENT
# ═══════════════════════════════════════════════════════════════════════════
def _champs_demandes(data: dict) -> list:
    """Les informations nommément demandées (« SIRET », « décennale »…).

    Le modèle les passe dans `champs` ; on accepte aussi une chaîne unique et
    les synonymes qu'il emploie spontanément. Sans elles, la fiche reste ce
    qu'elle a toujours été.
    """
    brut = data.get("champs") or data.get("informations") or data.get("champ") or []
    if isinstance(brut, str):
        brut = [m for m in re.split(r"[,;/]| et ", brut) if m.strip()]
    if not isinstance(brut, (list, tuple)):
        return []
    # Bornées : la fiche reste lisible, et une liste interminable de trous
    # n'apprend rien de plus qu'une liste courte.
    return [str(x).strip() for x in brut if str(x).strip()][:8]


async def fiche_client(data: dict, user) -> dict:
    """TOUT ce qu'on sait d'un client, à travers TOUS les jeux importés.

    Le point clé : on ne se limite pas au fichier des clients. Un client
    n'existe pas dans une table, il existe dans les devis, les factures, les
    chantiers — et c'est le recoupement qui répond à « combien il nous a
    rapporté ». Chercher dans un seul jeu rendrait une fiche vide et juste.
    """
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError

    demande = (data.get("nom") or data.get("client") or data.get("demande") or "").strip()
    if not demande:
        raise SkillError("Quel client ? Donne son nom dans `nom`.")

    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    cible = _plat(demande)

    try:
        async with get_db() as conn:
            existants = await _jeux(conn, niveaux)
            # Une seule lecture pour TOUS les jeux : la fiche croise les
            # sources, la faire en N requêtes multiplierait les allers-retours
            # pour un volume que Postgres filtre sans effort.
            lignes = await conn.fetch(
                "SELECT source_type, data, champs FROM document_metadata "
                "WHERE access_level = ANY($1::text[]) "
                "  AND (data::text ILIKE $2 OR champs::text ILIKE $2) "
                "LIMIT 2000",
                niveaux, f"%{demande}%")
    except Exception as e:  # noqa: BLE001
        logger.warning("Fiche client impossible : %s", e)
        raise SkillError("Les données clients sont momentanément indisponibles.")

    par_jeu: dict = {}
    identite: dict = {}
    for l in lignes:
        d = _fusion(l)
        # LE ILIKE RATISSE TROP LARGE, ET C'EST UN PIÈGE À CHIFFRES.
        # Relevé au banc : un chantier de la mairie portait « accès par la
        # parcelle de SCI Les Tilleuls » en commentaire, et se retrouvait
        # compté dans la fiche des Tilleuls. Un enregistrement n'appartient à
        # un client que si c'est SA COLONNE D'IDENTITÉ qui porte le nom —
        # « Client », « Raison sociale », « Société ». Le reste est du contexte.
        #
        # Quand aucune colonne d'identité n'existe (un fichier sans en-tête
        # reconnu), on retombe sur la correspondance large : mieux vaut une
        # ligne de trop, visible et vérifiable, qu'une fiche vide.
        colonne_identite = _colonne(d, "nom")
        if colonne_identite is not None:
            if cible not in _plat(d[colonne_identite]):
                continue
        elif not any(cible in _plat(v) for v in d.values()):
            continue
        par_jeu.setdefault(l["source_type"], []).append(d)
        if not identite and "client" in _plat(l["source_type"]):
            identite = d

    if not par_jeu:
        return {
            "trouve": False, "nom_demande": demande, "jeux_de_donnees": existants,
            "message": (f"Aucun enregistrement ne mentionne « {demande} » dans les "
                        f"{len(existants)} jeu(x) de données importés."),
            "a_faire": ("Dis-le sans détour et n'invente RIEN. AVANT de conclure, "
                        "cherche ce NOM dans le classement des fichiers (le geste "
                        "de recherche par nom : drive_chercher ou nas_chercher) — "
                        "les dossiers portent les noms des clients — et propose "
                        "`liste_clients` pour vérifier l'orthographe exacte."),
        }

    # ── Le recoupement : combien, pour combien, dans quel jeu ──────────────
    resume, total_general = [], 0.0
    detail_devis = []
    # Les jeux réellement additionnés : un chiffre qui circule sans sa source
    # finit par être cité en réunion sans que personne ne sache d'où il sort.
    sources_ca = []
    for jeu, enregistrements in sorted(par_jeu.items(), key=lambda x: -len(x[1])):
        somme = 0.0
        for d in enregistrements:
            colonne = _colonne(d, "montant")
            if colonne:
                somme += _montant(d[colonne])
        resume.append({"jeu": jeu, "enregistrements": len(enregistrements),
                       "montant_total": _euros(somme) if somme else ""})
        # Le chiffre d'affaires ne compte QUE les jeux de facturation : additionner
        # les devis ET les factures compterait deux fois la même affaire.
        if somme and any(mot in _plat(jeu) for mot in ("factur", "vente", "ca", "chiffre")):
            total_general += somme
            sources_ca.append(jeu)
        if any(mot in _plat(jeu) for mot in ("devis", "quote", "offre", "factur")):
            # DU PLUS RÉCENT AU PLUS ANCIEN, et le tri passe AVANT la coupe :
            # couper d'abord garderait les quarante premières lignes DU FICHIER,
            # et le dernier devis d'un gros client tomberait hors de la fiche.
            recents = sorted(enregistrements,
                             key=lambda d: _date_triable(_valeur(d, "date")),
                             reverse=True)
            for d in recents[:MAX_LIGNES_PAR_JEU]:
                detail_devis.append({
                    "jeu": jeu,
                    "reference": _valeur(d, "reference"),
                    "date": _valeur(d, "date"),
                    "statut": _valeur(d, "statut"),
                    "montant": _valeur(d, "montant"),
                })

    # Les jeux sont parcourus du plus fourni au moins fourni : sans ce dernier
    # tri, les factures d'un client pourraient précéder ses devis et « la
    # première ligne » ne serait plus « la plus récente ».
    detail_devis.sort(key=lambda d: _date_triable(d.get("date")), reverse=True)

    # Sans jeu de facturation identifié, le total le plus élevé fait foi —
    # et on DIT d'où il vient, pour qu'un chiffre ne circule jamais sans source.
    origine_ca = ", ".join(sources_ca)
    if not total_general and resume:
        meilleur = max(resume, key=lambda r: _montant(r["montant_total"]))
        total_general = _montant(meilleur["montant_total"])
        origine_ca = meilleur["jeu"]

    fiche = {"Client": _nom_complet(identite) or demande}
    for etiquette, famille in (("Ville", "ville"), ("Email", "email"), ("Téléphone", "telephone")):
        v = _valeur(identite, famille)
        if v:
            fiche[etiquette] = v

    # ── CE QU'ON A DEMANDÉ ET QU'ON N'A PAS ────────────────────────────────
    #
    # « Quel est le SIRET de X ? », « son assurance décennale ? » : la fiche ne
    # rendait que les colonnes qu'elle sait nommer, et le champ demandé
    # disparaissait sans laisser de trace. Le modèle voyait une fiche complète
    # et honnête — sur laquelle l'information manquante n'existait tout
    # simplement pas — et devait deviner qu'elle manquait.
    #
    # C'est le contraire de la règle du prompt système : « ne l'omets pas en
    # silence, ne la devine pas ». Une omission ne se voit pas ; un
    # [À COMPLÉTER] se voit. Et c'est aussi la question qui décide de la
    # confiance : un dirigeant qui voit l'assistant dire « je ne l'ai pas » le
    # croit ensuite quand il donne un chiffre.
    manquants = []
    for libelle in _champs_demandes(data):
        cible = _plat(libelle)
        valeur = ""
        for enregistrements in par_jeu.values():
            for d in enregistrements:
                for colonne, v in d.items():
                    if cible in _plat(colonne) and str(v or "").strip():
                        valeur = str(v).strip()
                        break
                if valeur:
                    break
            if valeur:
                break
        fiche[libelle.strip().capitalize()] = valeur or "[À COMPLÉTER]"
        if not valeur:
            manquants.append(libelle.strip())
    for r in resume:
        fiche[r["jeu"].capitalize()] = (f"{r['enregistrements']}"
                                        + (f" · {r['montant_total']}" if r["montant_total"] else ""))
    if total_general:
        fiche["Chiffre d'affaires"] = f"{_euros(total_general)} (source : {origine_ca})"

    return {
        "trouve": True,
        "client": fiche["Client"],
        "identite": identite,
        "champs_manquants": manquants or None,
        "par_jeu": resume,
        "devis": detail_devis,
        "chiffre_affaires": _euros(total_general) if total_general else None,
        "source_chiffre_affaires": origine_ca if total_general else None,
        "bloc_ui": {"type": "keyvalue",
                    "rows": [[k, v] for k, v in fiche.items()]},
        "message_final": (f"Voici ce que je sais de {fiche['Client']} : "
                          + ", ".join(f"{r['enregistrements']} {r['jeu']}" for r in resume)
                          + (f", pour un chiffre d'affaires de {_euros(total_general)}."
                             if total_general else ".")
                          + (f" En revanche, {' et '.join(manquants)} : cette information "
                             "ne figure dans aucun fichier importé."
                             if manquants else "")),
        "a_faire": (("Les champs marqués [À COMPLÉTER] ne figurent NULLE PART dans les "
                     "données de l'entreprise : recopie-les tels quels, dis-le en une "
                     "phrase, et ne va surtout pas chercher la valeur ailleurs : un "
                     "SIRET trouvé sur le web n'est pas une donnée de l'entreprise. "
                     if manquants else "")
                    + "AFFICHE la fiche : insère un bloc ```ui contenant EXACTEMENT le "
                    "contenu de `bloc_ui`. Si `devis` n'est pas vide, ajoute un second "
                    "bloc ```ui de type `table` (champs `columns` et `rows`) avec les "
                    "colonnes Référence, Date, Statut, Montant. `devis` est trié du PLUS "
                    "RÉCENT au plus ancien : pour « le dernier devis », c'est la PREMIÈRE "
                    "ligne, ne compare pas les dates toi-même. Cite les chiffres TELS "
                    "QUELS — ne les recalcule pas, ne les arrondis pas, et rappelle la "
                    "source du chiffre d'affaires."),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  POINT SUR LES MAILS
# ═══════════════════════════════════════════════════════════════════════════
async def check_mails(data: dict, user) -> dict:
    """Le point sur le courrier récent, prêt à être résumé en UN message.

    Ce skill ne résume pas lui-même : il RASSEMBLE. Faire écrire un résumé par
    message coûterait un appel LLM chacun — soit, sur vingt messages, vingt
    passages dans la cascade. Il rend donc la matière d'un seul coup, avec la
    consigne de tout traiter dans la même réponse.
    """
    from mail.skills import lire_mails
    from skills.erreurs import SkillError

    # Une période demandée ⇒ le détail va au maximum (voir lire_mails).
    _periode = data.get("depuis") or data.get("periode") or data.get("jours")
    try:
        limite = int(data.get("limite") or (25 if _periode else 15))
    except (TypeError, ValueError):
        limite = 25 if _periode else 15
    limite = max(1, min(limite, 25))

    # La période vient de l'utilisateur (« cette semaine » → jours=7). Sans
    # elle, les plus récents. Avec elle, le TOTAL de la période est exact même
    # si le détail reste borné — c'est la différence entre « 25 mails » et
    # « 84 mails cette semaine, voici les 25 derniers ».
    depuis = data.get("depuis") or data.get("periode") or data.get("jours")
    # L'EXTRAIT A UN BUDGET (31/08). Le point sur la semaine — analyser,
    # synthétiser, proposer des réponses — se fait sur le TEXTE des messages :
    # 160 caractères (le plancher de lire_mails à 25 messages) ne disent pas
    # s'il y a une question à laquelle répondre. Le relevé d'ici est plus
    # léger qu'une fiche de lire_mails (~180 caractères hors extrait), et le
    # résultat est « généreux » (12 000) : on demande la longueur qui remplit
    # ce budget — 240 pour 25 messages, 520 pour 15, 800 dès 10.
    apercu = max(450, min(800, (10500 - limite * 180) // limite))
    brut = await lire_mails({"mailbox": data.get("mailbox"),
                             "dossier": data.get("dossier") or "recus",
                             "limite": limite, "depuis": depuis,
                             # LA PAGE SUIVANTE (01/09) : « TOUS mes mails des
                             # 7 derniers jours » sur 63 messages n'était PAS
                             # couvrable — le détail est borné à 25 et ce skill
                             # ne transmettait même pas `avant`. Le point
                             # s'enchaîne désormais page par page.
                             "avant": data.get("avant") or data.get("avant_le"),
                             "curseur": data.get("curseur"),
                             "apercu": apercu}, user)

    messages = list(brut.get("messages") or brut.get("mails") or [])
    # La pagination IMAP est mécanique, pas une décision à redemander au LLM
    # à chaque lot. Les UID gardent les mails du même jour ; les contrôles de
    # droits de lire_mails sont rejoués pour chaque page.
    total_initial = brut.get('total_periode')
    suivant = brut.get('curseur_suivant')
    vus_curseurs = set()
    if _periode and not data.get('limite') and not data.get('avant') and not data.get('curseur'):
        while suivant and suivant not in vus_curseurs and len(messages)<250:
            vus_curseurs.add(suivant)
            page = await lire_mails({'mailbox':data.get('mailbox'),'dossier':data.get('dossier') or 'recus',
                'depuis':depuis,'limite':min(25,250-len(messages)),'curseur':suivant,'apercu':apercu},user)
            messages.extend(page.get('messages') or [])
            suivant=page.get('curseur_suivant')
        if vus_curseurs:
            uniques={m['ref']:m for m in messages if isinstance(m,dict) and m.get('ref')}
            messages=list(uniques.values())
            brut={**brut,'nombre':len(messages),'total_periode':total_initial,
                'tronque':bool(suivant or (total_initial is not None and len(messages)<total_initial)),
                'curseur_suivant':suivant,
                'compte':f'{total_initial} message(s) sur la période ; {len(messages)} aperçus consultés.',
                'plus_ancien':min((m.get('date_iso') for m in messages if m.get('date_iso')),default=None)}
    if not isinstance(messages, list):
        raise SkillError("La messagerie a répondu dans un format inattendu.")

    if not messages:
        return {"nombre": 0, "boite": brut.get("boite") or brut.get("mailbox"),
                "message_final": "Aucun message récent dans cette boîte.",
                "a_faire": "Dis-le simplement, sans meubler."}

    def _champ(m, *noms):
        for n in noms:
            v = m.get(n)
            if v:
                return str(v)
        return ""

    releve = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        objet = _champ(m, "objet", "subject", "sujet")
        releve.append({
            # La ref est ce qui permet d'OUVRIR le message (`lire_mail`) :
            # l'extrait ci-dessous n'en est qu'un début.
            "ref": _champ(m, "ref"),
            "de": _champ(m, "de", "from", "expediteur", "sender"),
            "objet": objet,
            "date": _champ(m, "date", "recu_le", "receivedAt", "received_at"),
            "extrait": _champ(m, "apercu", "extrait", "preview", "body", "corps")[:800],
            # « Re: » n'est pas un détail : une réponse dans un fil en cours est
            # ce qu'on veut voir en premier quand on fait le point.
            "reponse_dans_un_fil": bool(re.match(r"\s*(re|rép|rep)\s*:", objet, re.I)),
            # LA MESSAGERIE REND `lu`, PAS `non_lu` — et l'écart était invisible.
            # Le skill cherchait une clé qui n'existe nulle part dans
            # `mail/lecture.py` : le compteur de non-lus serait resté à zéro
            # pour toujours, sans erreur, sans trace. Relevé au banc.
            # `.get("lu", True)` : un message dont l'état est inconnu n'est PAS
            # annoncé comme non lu — on ne réveille pas sur une supposition.
            "non_lu": not bool(m.get("lu", True)),
            # Une pub n'appelle pas de réponse. Le dire ici évite au modèle de
            # proposer poliment de répondre à un catalogue d'automne.
            "automatique": bool(m.get("expediteur_automatique")),
            "interne": bool(m.get("expediteur_interne")),
        })

    fils = sum(1 for r in releve if r["reponse_dans_un_fil"])
    non_lus = sum(1 for r in releve if r["non_lu"])
    total = brut.get("total_periode")
    tronque = bool(brut.get("tronque"))
    compte = brut.get("compte") or f"{len(releve)} message(s)."
    plus_ancien = brut.get("plus_ancien")
    curseur = brut.get("curseur_suivant")

    return {
        "nombre": len(releve),
        "total_periode": total,
        "tronque": tronque,
        "compte": compte,
        "reponses_dans_un_fil": fils,
        "non_lus": non_lus,
        "boite": brut.get("boite") or brut.get("mailbox"),
        "plus_ancien": plus_ancien,
        "curseur_suivant": curseur,
        # LA PAGE SUIVANTE, MÉCANIQUE (01/09, règle « une recherche ne se
        # bloque jamais ») : quand la période compte plus de messages que le
        # détail, le point s'ENCHAÎNE — le modèle n'a rien à calculer.
        "pour_continuer": (
            f"Rappelle check_mails avec les MÊMES filtres et curseur={curseur}. Ne remplace pas ce curseur par une date, cela sauterait les messages du même jour."
            if curseur else
            f"Le détail couvre {len(releve)} message(s) sur {total} : rappelle "
            f"check_mails avec les MÊMES paramètres et avant={plus_ancien} pour "
            "les précédents, et enchaîne jusqu'à couvrir le total AVANT de rédiger."
            if plus_ancien and total and int(total) > len(releve) else None),
        "messages": releve,
        "message_final": (compte
                          + (f" Parmi les détaillés : {fils} réponse(s) à un fil en cours" if fils else "")
                          + (f", {non_lus} non lu(s)" if non_lus and fils else
                             f" Parmi les détaillés : {non_lus} non lu(s)" if non_lus else "")
                          + ("." if (fils or non_lus) else "")),
        "a_faire": (
            "Commence par le COMPTE, mot pour mot : « " + compte + " » — c'est le "
            "total qui répond à « combien », pas le nombre de messages détaillés. "
            # « Propose de cibler » a vécu (01/09) : « fais le point sur TOUS
            # mes mails » sur 63 messages rendait 25 et s'arrêtait là — TOUT
            # SIGNIFIE TOUT, la suite s'enchaîne, elle ne se propose pas.
            + ("Le détail ne couvre PAS toute la période : ENCHAÎNE — rappelle "
               "ce skill selon pour_continuer (curseur prioritaire, sinon avant) jusqu'à couvrir le "
               "compte, PUIS rédige UNE SEULE synthèse pour l'ensemble. Ne "
               "présente jamais les premiers messages comme le tout. "
               if tronque else "")
            + "Fais le point en UN SEUL message, sans rappeler ce skill. Pour chaque "
            "message : l'expéditeur, l'objet, et UNE phrase de résumé tirée de "
            "l'extrait — jamais de ta mémoire. Mets EN PREMIER ceux marqués "
            "`reponse_dans_un_fil` : ce sont des échanges en cours. "
            "N'en propose AUCUNE pour les messages marqués `automatique` : ce sont "
            "des envois de masse, y répondre n'a pas de sens. "
            "Quand des messages appellent visiblement une réponse (question posée, "
            "demande de devis, relance), rédige pour chacun une réponse courte (deux "
            "ou trois lignes) et rassemble-les TOUTES dans UN SEUL bloc ```ui "
            "reponses_mail (une entrée par message : ref, de, objet, synthese — une ou deux phrases sur ce que le mail REÇU demande, tirées de l'extrait —, reponse) — des "
            "cartes cochables avec envoi groupé. N’écris pas ces réponses en prose "
            "en plus du bloc, et n’envoie rien : chaque envoi repassera par "
            "`envoyer_email` et sa validation. "
            # 08/09, Noa : « ça propose des réponses uniquement à ceux qui
            # nécessitent des réponses, ça explique pourquoi certains ne
            # nécessitent pas de réponse ».
            "Pour chaque message SANS réponse proposée, dis en quelques mots POURQUOI "
            "(automatique, information, copie, remerciement, déjà traité…) : la personne "
            "doit voir que rien n'a été oublié. "
            "Si un extrait est vide, dis que le contenu n'a pas pu être lu au lieu "
            "d'inventer un résumé. Un `extrait` n'est que le DÉBUT du message : "
            "s'il ne suffit pas pour proposer une réponse juste, ouvre le message "
            "avec `lire_mail` et sa `ref` avant de répondre."),
    }


# ── Déclarations : tout ce que le système doit savoir, ICI ──────────────────
from skills.registre import Declaration


# ═══════════════════════════════════════════════════════════════════════════
#  LES DOSSIERS QUI ATTENDENT — le suivi actif
# ═══════════════════════════════════════════════════════════════════════════
#
# « Liste-moi tous les dossiers clients où on attend une réponse depuis plus de
# quinze jours. » C'est la question du suivi : elle ne demande pas de retrouver
# un document, elle demande de REGARDER LE TEMPS PASSER. Aucun geste ne savait
# la traiter, parce qu'il fallait croiser deux choses qu'on ne savait pas lire
# ensemble : un statut (le dossier attend-il quelque chose ?) et une ancienneté
# (depuis combien de temps ?).
#
# CE QUI REND CE GESTE POSSIBLE, c'est `skills/lecture.py` : les dates des
# fichiers importés sont du TEXTE, dans le format du logiciel d'origine, et
# rien ne les comparait à aujourd'hui.
#
# IL NE CODE AUCUN MÉTIER. Les statuts « en attente » sont reconnus par
# famille de synonymes, comme les colonnes le sont partout ailleurs ici, et la
# liste se surcharge (`statuts`) pour une maison qui écrirait autrement. Ce qui
# est CLOS, en revanche, ce sont les statuts qui mettent fin à l'attente :
# signé, refusé, payé. Un dossier signé n'attend plus rien, et le compter
# ferait passer un carnet de commandes pour une pile de relances.

# Ce qui attend. Comparé sur la forme aplatie, donc « En attente » et
# « EN_ATTENTE » se valent, et un préfixe suffit (« envoy » couvre « envoyé »,
# « envoye », « envoyée le 12/03 »).
STATUTS_EN_ATTENTE = ("envoy", "attente", "relanc", "en cours", "encours",
                      "transmis", "propos", "devis", "a_relancer", "a relancer",
                      "etude", "chiffrage", "pending", "sent")
# Ce qui n'attend plus. PRIORITAIRE sur la liste ci-dessus : un statut
# « devis signé » contient « devis », mais il est clos.
STATUTS_CLOS = ("sign", "accept", "valid", "gagn", "refus", "perdu", "annul",
                "abandon", "sold", "pay", "regl", "termin", "clotur", "facture",
                "won", "lost", "closed")

# Le seuil par défaut, quand personne ne le précise. Quinze jours est la
# formulation du brief client ; ce n'est pas une règle du métier, c'est un
# défaut raisonnable, et il est DIT dans la réponse pour qu'on puisse le
# contredire.
JOURS_PAR_DEFAUT = 15
MAX_DOSSIERS_AFFICHES = 40


def _statut_attend(valeur: str, personnalises=None) -> bool:
    """Ce dossier attend-il encore quelque chose ?

    Sans statut du tout, on répond OUI : un dossier dont on ignore l'état est
    précisément celui qu'il faut aller regarder. L'inverse — le taire — ferait
    disparaître de la liste les lignes les moins bien tenues, c'est-à-dire
    celles qui posent problème.
    """
    plat = _plat(valeur)
    # DES STATUTS EXPLICITES SONT UNE LISTE FERMÉE. Quand la personne nomme les
    # statuts qui l'intéressent, une ligne sans statut n'en fait partie
    # d'aucun : la retenir « par précaution » lui rendrait tout le fichier
    # alors qu'elle a demandé trois statuts. La précaution ci-dessous ne vaut
    # que pour la liste PAR DÉFAUT, où l'on ignore le vocabulaire de la maison.
    if personnalises:
        return bool(plat) and any(_plat(s) in plat for s in personnalises)
    if not plat:
        return True
    if any(mot in plat for mot in STATUTS_CLOS):
        return False
    return any(mot in plat for mot in STATUTS_EN_ATTENTE)


async def dossiers_en_attente(data: dict, user) -> dict:
    """Les dossiers sans réponse depuis plus de N jours, du plus ancien."""
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError
    from skills.lecture import age_en_jours

    seuil = data.get("jours", data.get("depuis_jours"))
    try:
        seuil = int(str(seuil).strip()) if str(seuil or "").strip() else JOURS_PAR_DEFAUT
    except ValueError:
        seuil = JOURS_PAR_DEFAUT
    seuil = max(0, min(seuil, 3650))
    demande_jeu = str(data.get("source_type") or data.get("jeu") or "").strip()
    statuts = data.get("statuts") or None
    if isinstance(statuts, str):
        statuts = [s.strip() for s in statuts.split(",") if s.strip()]

    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    try:
        async with get_db() as conn:
            existants = await _jeux(conn, niveaux)
            # Sans jeu précisé : tous ceux qui portent des affaires en cours.
            # On ne devine pas « devis » : un client peut appeler cela
            # « propositions », « offres » ou « affaires ».
            if demande_jeu:
                jeux = [j for j in existants if _plat(demande_jeu) in _plat(j)] \
                    or [demande_jeu]
            else:
                jeux = [j for j in existants
                        if any(m in _plat(j) for m in
                               ("devis", "offre", "proposition", "affaire", "quote",
                                "chantier", "dossier", "commande"))]
            if not jeux:
                return {
                    "trouve": False, "jeux_de_donnees": existants,
                    "message": ("Aucun jeu de données ne ressemble à des devis ou à des "
                                "affaires en cours. Jeux importés : "
                                + (", ".join(existants) or "aucun") + "."),
                    "a_faire": ("Dis-le sans détour, et demande DANS QUEL FICHIER se "
                                "trouvent les dossiers à suivre. N'invente aucune ligne."),
                }
            lignes = []
            for jeu in jeux:
                for l in await conn.fetch(
                        "SELECT data, champs FROM document_metadata "
                        "WHERE source_type = $1 AND access_level = ANY($2::text[]) "
                        "LIMIT $3",
                        jeu, niveaux, MAX_CLIENTS):
                    lignes.append((jeu, _fusion(l)))
    except Exception as e:  # noqa: BLE001
        logger.warning("Suivi des dossiers impossible : %s", e)
        raise SkillError("Les données des dossiers sont momentanément indisponibles.")

    en_attente, sans_date, clos = [], 0, 0
    for jeu, d in lignes:
        if not _statut_attend(_valeur(d, "statut"), statuts):
            clos += 1
            continue
        age = age_en_jours(_valeur(d, "date"))
        if age is None:
            sans_date += 1
            continue
        if age >= seuil:
            en_attente.append({
                "jeu": jeu,
                "client": _nom_complet(d) or _valeur(d, "nom"),
                "reference": _valeur(d, "reference"),
                "date": _valeur(d, "date"),
                "jours": age,
                "statut": _valeur(d, "statut"),
                "montant": _valeur(d, "montant"),
            })

    # DU PLUS ANCIEN AU PLUS RÉCENT : celui qui attend depuis le plus longtemps
    # est celui qu'il faut rappeler aujourd'hui. C'est l'ordre dans lequel on
    # décroche le téléphone, donc l'ordre dans lequel la liste doit sortir.
    en_attente.sort(key=lambda x: -x["jours"])
    total = len(en_attente)
    montres = en_attente[:MAX_DOSSIERS_AFFICHES]

    if not total:
        return {
            "trouve": True, "nombre": 0, "seuil_jours": seuil,
            "dossiers_examines": len(lignes), "dossiers_clos": clos,
            "sans_date_lisible": sans_date or None,
            "message_final": (f"Aucun dossier n'attend depuis plus de {seuil} jours "
                              f"(sur {len(lignes)} examinés, {clos} déjà clos)."
                              + (f" Attention : {sans_date} n'ont pas de date lisible."
                                 if sans_date else "")),
            "a_faire": "Dis-le en une phrase, avec le seuil employé. N'invente aucune ligne.",
        }

    return {
        "trouve": True, "nombre": total, "seuil_jours": seuil,
        "dossiers_examines": len(lignes), "dossiers_clos": clos,
        "sans_date_lisible": sans_date or None,
        "dossiers": montres,
        "bloc_ui": {
            "type": "table",
            "titre": f"Dossiers sans réponse depuis plus de {seuil} jours",
            "columns": ["Client", "Référence", "Date", "Attente", "Statut", "Montant"],
            "rows": [[d["client"] or "[À COMPLÉTER]", d["reference"], d["date"],
                      f"{d['jours']} j", d["statut"] or "[À COMPLÉTER]", d["montant"]]
                     for d in montres],
        },
        "message_final": (
            f"{total} dossier(s) attendent une réponse depuis plus de {seuil} jours"
            + (f", le plus ancien depuis {montres[0]['jours']} jours." if montres else ".")
            + (f" {sans_date} dossier(s) n'ont pas de date lisible et n'ont pas pu être "
               f"examinés." if sans_date else "")),
        "a_faire": (
            "AFFICHE la liste : insère un bloc ```ui contenant EXACTEMENT le contenu de "
            "`bloc_ui`. Elle est triée du plus ancien au plus récent, c'est l'ordre dans "
            "lequel il faut rappeler. Les âges sont EXACTS, cite-les tels quels. Ne "
            "propose PAS d'envoyer les relances toi-même sans qu'on te le demande."
            + (f" Signale les {sans_date} dossier(s) sans date lisible." if sans_date else "")),
    }



# ═══════════════════════════════════════════════════════════════════════════
#  LES PRIX DÉJÀ PRATIQUÉS — ce que la maison a devisé et facturé, et l'estimation qui en sort
# ═══════════════════════════════════════════════════════════════════════════
#
# « Prépare-moi une trame de pré-devis avec les postes et les quantités » : on
# rendait les postes et les surfaces, et pas un chiffre. C'était prudent et
# c'était insuffisant — un dirigeant qui demande un pré-devis attend des ordres
# de grandeur, et à défaut il ira les chercher ailleurs.
#
# LA SEULE SOURCE ACCEPTABLE EST L'HISTORIQUE DE LA MAISON. Pas un prix public,
# pas une moyenne du marché, pas une estimation du modèle : ce que CETTE
# entreprise a réellement facturé pour ce poste-là, avec le nombre
# d'observations, la fourchette et les affaires d'où cela sort. Un prix sans
# ces trois choses est une invention polie.
#
# CE GESTE OBSERVE, PUIS IL ESTIME — ET IL MONTRE D'OÙ (17/09). La première écriture
# s'interdisait tout chiffre unique : « n'en déduis jamais un prix ». Relevé de Noa après le
# pré-devis d'abattage resté vide : « j'aimerais qu'il analyse le contenu des factures, les
# articles, les prix, pour avoir des estimations des montants ». Deux choses manquaient :
#   * LES LIGNES. Les jeux importés ne portent que des TOTAUX par affaire ; le prix d'un
#     ouvrage vit dans les lignes des PDF (`prix.collecte` les lit en fond, migration 055).
#     C'est la source première ; les totaux d'affaires et le catalogue d'articles la complètent.
#   * LE DROIT D'ESTIMER. Quantité × prix unitaire MÉDIAN de la même unité, avec la fourchette
#     à côté et le nombre d'observations : c'est une estimation qui se vérifie, pas un prix
#     qui engage. Ce qui n'a pas deux observations reste « à chiffrer ».

MIN_OBSERVATIONS = 2
MAX_OBSERVATIONS_CITEES = 8
MAX_POSTES_PAR_APPEL = 12
MAX_LIGNES_CANDIDATES = 4000

# Les colonnes où un poste se décrit. On ne cherche PAS dans les montants, les
# dates ni les références : « 2024 » se retrouverait dans un numéro de devis, et
# le prix moyen d'un poste inexistant serait rendu avec le plus grand sérieux.
# « titre » : c'est la colonne où l'export des devis nomme l'affaire (« Abattage d'arbres »).
FAMILLES_DESCRIPTIVES = ("prestation", "description", "designation", "désignation",
                         "libelle", "libellé", "objet", "poste", "travaux", "titre",
                         "nature", "intitule", "intitulé", "chantier")
# « commentaire » a quitté la liste le 17/09 : un commentaire CITE un ouvrage (« voir abattage
# du voisin »), il ne décrit pas l'affaire — il faisait entrer le montant d'une autre affaire.


def _mediane(valeurs: list) -> float:
    ordonnees = sorted(valeurs)
    milieu = len(ordonnees) // 2
    if len(ordonnees) % 2:
        return ordonnees[milieu]
    return (ordonnees[milieu - 1] + ordonnees[milieu]) / 2


def _postes_demandes(data: dict) -> list[dict]:
    """Les postes à relever : `poste` seul, ou `postes` — des noms, ou des fiches
    {poste, quantite, unite} quand on veut l'estimation avec."""
    bruts = data.get("postes")
    if isinstance(bruts, str):
        bruts = [p for p in bruts.replace(";", ",").split(",")]
    if not isinstance(bruts, list) or not bruts:
        bruts = [{"poste": data.get("poste") or data.get("prestation") or data.get("recherche"),
                  "quantite": data.get("quantite"), "unite": data.get("unite")}]
    postes = []
    for b in bruts[:MAX_POSTES_PAR_APPEL]:
        if isinstance(b, dict):
            nom = b.get("poste") or b.get("designation") or b.get("nom") or b.get("prestation")
            quantite, unite = b.get("quantite") or b.get("qte"), b.get("unite")
        else:
            nom, quantite, unite = b, None, None
        nom = " ".join(str(nom or "").split())
        if len(nom) < 3:
            continue
        try:
            quantite = float(str(quantite).replace(",", ".").split()[0]) if quantite not in (None, "") else None
        except (ValueError, IndexError):
            quantite = None
        postes.append({"poste": nom, "quantite": quantite, "unite": str(unite or "").strip()})
    return postes


async def _lignes_du_poste(conn, racines: list, niveaux: list) -> list:
    """Les lignes chiffrées (devis et factures lus dans le classement) qui décrivent ce poste."""
    from prix.releve import correspond
    lignes = await conn.fetch(
        "SELECT l.designation, l.rubrique, l.unite, l.quantite, l.pu_ht, l.texte_plat, "
        "       p.nature, p.numero, p.date_piece, p.fichier_id "
        "FROM lignes_chiffrees l JOIN pieces_chiffrees p USING (fichier_id) "
        "WHERE p.etat = 'lue' AND p.access_level = ANY($1::text[]) "
        "  AND p.nature IN ('devis', 'facture', 'commande', 'situation') "
        "  AND l.texte_plat LIKE ALL($2::text[]) "
        f"LIMIT {MAX_LIGNES_CANDIDATES}",
        niveaux, [f"%{r}%" for r in racines])
    return [{"designation": l["designation"], "unite": l["unite"], "quantite": float(l["quantite"]),
             "pu_ht": float(l["pu_ht"]), "nature": l["nature"], "numero": l["numero"],
             "date": l["date_piece"], "fichier_id": l["fichier_id"]}
            for l in lignes if correspond(l["texte_plat"], racines)]


def _affaires_du_poste(lignes_jeux: list, racines: list, demande_jeu: str) -> dict | None:
    """Les TOTAUX d'affaires dont l'intitulé décrit ce poste (jeux importés)."""
    from prix.releve import correspond, plat
    from skills.lecture import lire_montant, est_un_nombre
    observations = []
    for l in lignes_jeux:
        jeu = l["source_type"]
        if demande_jeu and _plat(demande_jeu) not in _plat(jeu):
            continue
        # Les prix se lisent dans ce qui porte des montants d'affaires. Un
        # fichier de contacts qui mentionnerait « terrasse » n'a pas de prix.
        if not any(m in _plat(jeu) for m in
                   ("devis", "chantier", "factur", "offre", "vente", "commande",
                    "affaire", "proposition")):
            continue
        d = _fusion(l)
        # LE POSTE DOIT ÊTRE DANS UNE COLONNE QUI LE DÉCRIT. Le ILIKE ratisse
        # toute la ligne : sans ce contrôle, un commentaire « voir terrasse bois
        # du lot 3 » ferait entrer le montant d'un tout autre poste dans la
        # moyenne — le même piège que la fiche client, payé une fois déjà.
        colonne_trouvee = None
        for colonne, valeur in d.items():
            if any(f in _plat(colonne) for f in FAMILLES_DESCRIPTIVES) \
                    and correspond(plat(valeur), racines):
                colonne_trouvee = colonne
                break
        if not colonne_trouvee:
            continue
        brut = _valeur(d, "montant")
        if not est_un_nombre(brut):
            continue
        montant = lire_montant(brut)
        if montant <= 0:
            continue
        observations.append({"jeu": jeu, "montant": montant,
                             "designation": str(d[colonne_trouvee])[:120],
                             "reference": _valeur(d, "reference"), "date": _valeur(d, "date")})
    if len(observations) < MIN_OBSERVATIONS:
        return None
    montants = [o["montant"] for o in observations]
    observations.sort(key=lambda o: _date_triable(o["date"]), reverse=True)
    return {"observations": len(observations), "plus_bas": _euros(min(montants)),
            "median": _euros(_mediane(montants)), "plus_haut": _euros(max(montants)),
            "sources": sorted({o["jeu"] for o in observations}),
            "exemples": [{k: o[k] for k in ("designation", "montant", "reference", "date")}
                         for o in observations[:4]]}


def _articles_du_poste(lignes_jeux: list, racines: list) -> list:
    """Le TARIF de la maison : les articles du catalogue dont le libellé décrit ce poste et
    qui portent un prix (la moitié des prestations y sont à zéro : elles ne disent rien)."""
    from prix.releve import correspond, plat
    from skills.lecture import lire_montant, est_un_nombre
    articles = []
    for l in lignes_jeux:
        d = _fusion(l)
        libelle = next((v for c, v in d.items() if "libelle_de_l_article" in _plat(c)), None)
        if not libelle or not correspond(plat(libelle), racines):
            continue
        prix = next((v for c, v in d.items()
                     if _plat(c).startswith("prix_de_l_article") and _plat(c).endswith("ht")), None)
        if not est_un_nombre(prix) or lire_montant(prix) <= 0:
            continue
        unite = next((v for c, v in d.items() if _plat(c) == "unite"), "")
        articles.append({"article": str(libelle)[:120], "unite": str(unite or ""),
                         "prix_ht": _euros(lire_montant(prix))})
    return articles[:6]


async def prix_observes(data: dict, user) -> dict:
    """Ce que l'entreprise pratique pour un ou plusieurs postes, et l'estimation qui en sort."""
    from database.connection import get_db
    from security.acces import niveaux_visibles
    from skills.erreurs import SkillError
    from prix.releve import mots_cles, relever, estimer, unite_normale, euros

    postes = _postes_demandes(data)
    if not postes:
        raise SkillError(
            "Quel poste ? Donne-le dans `poste`, ou plusieurs dans `postes`, avec les mots du "
            "métier (« abattage d'arbre », « terrasse bois », « engazonnement »). Un mot trop "
            "court ramènerait n'importe quoi.")

    niveaux = sorted(niveaux_visibles(getattr(user, "role", "")))
    demande_jeu = str(data.get("source_type") or "").strip()
    releves, base = [], {}
    try:
        async with get_db() as conn:
            existants = await _jeux(conn, niveaux)
            try:
                from prix.collecte import bilan
                base = await bilan(conn, niveaux)
            except Exception:  # noqa: BLE001 — la base de prix peut ne pas exister (jumeau sans collecte)
                base = {}
            for p in postes:
                racines = mots_cles(p["poste"])
                if not racines:
                    releves.append({**p, "trouve": False})
                    continue
                elargi = None
                try:
                    lignes = await _lignes_du_poste(conn, racines, niveaux) if base else []
                    par_unite = relever(lignes)
                    # Trop peu avec tous les mots : on relâche sur le premier, celui qui nomme
                    # l'ouvrage (« abattage » dans « abattage d'arbres morts »), ET ON LE DIT.
                    if base and len(racines) > 1 and not any(r["suffisant"] for r in par_unite):
                        lignes = await _lignes_du_poste(conn, racines[:1], niveaux)
                        plus_large = relever(lignes)
                        if any(r["suffisant"] for r in plus_large):
                            par_unite, elargi = plus_large, racines[0]
                except Exception as e:  # noqa: BLE001
                    logger.warning("Lignes chiffrées illisibles : %s", str(e)[:160])
                    par_unite = []
                jeux = await conn.fetch(
                    "SELECT source_type, data, champs FROM document_metadata "
                    "WHERE access_level = ANY($1::text[]) "
                    "  AND (data::text ILIKE $2 OR champs::text ILIKE $2) LIMIT 2000",
                    niveaux, f"%{racines[0]}%")
                releves.append({**p, "racines": racines, "elargi_a": elargi,
                                "par_unite": par_unite,
                                "affaires": _affaires_du_poste(jeux, racines, demande_jeu),
                                "catalogue": _articles_du_poste(jeux, racines)})
    except SkillError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.warning("Relevé des prix impossible : %s", e)
        raise SkillError("Les données des affaires sont momentanément indisponibles.")

    lignes_tableau, lignes_estimation, fiches = [], [], []
    total = {"bas": 0.0, "median": 0.0, "haut": 0.0}
    chiffres, sans_prix = 0, []
    for r in releves:
        utiles = [u for u in r.get("par_unite") or [] if u["suffisant"]]
        voulue = unite_normale(r["unite"]) if r.get("unite") else None
        # L'unité demandée d'abord ; sinon la plus observée.
        utiles.sort(key=lambda u: (u["unite"] == voulue, u["observations"]), reverse=True)
        fiche = {"poste": r["poste"], "trouve": bool(utiles or r.get("affaires") or r.get("catalogue"))}
        if r.get("elargi_a"):
            fiche["recherche_elargie"] = (
                f"rien d'assez fourni avec tous les mots : relevé fait sur « {r['elargi_a']}… » seul")
        if utiles:
            fiche["prix_unitaires"] = [{
                "unite": u["unite"], "observations": u["observations"],
                "dont_factures": u["factures"], "dont_devis": u["devis"],
                "plus_bas": euros(u["plus_bas"]), "median": euros(u["median"]),
                "plus_haut": euros(u["plus_haut"]), "periode": u["periode_retenue"],
                "de": u["de"], "a": u["a"], "exemples": u["exemples"][:4]} for u in utiles[:3]]
            for u in utiles[:2]:
                lignes_tableau.append([r["poste"], u["unite"], str(u["observations"]),
                                       euros(u["plus_bas"]), euros(u["median"]), euros(u["plus_haut"]),
                                       u["periode_retenue"]])
        if r.get("affaires"):
            a = r["affaires"]
            fiche["affaires_entieres"] = a
            lignes_tableau.append([r["poste"], "affaire entière", str(a["observations"]),
                                   a["plus_bas"], a["median"], a["plus_haut"], "tout l'historique"])
        if r.get("catalogue"):
            fiche["catalogue_articles"] = r["catalogue"]
        if r.get("quantite"):
            e = estimer(utiles[0], r["quantite"]) if utiles and (not voulue or utiles[0]["unite"] == voulue) else None
            if e:
                fiche["estimation"] = {"quantite": e["quantite"], "unite": e["unite"],
                                       "bas": euros(e["bas"]), "median": euros(e["median"]),
                                       "haut": euros(e["haut"])}
                lignes_estimation.append([r["poste"], f"{e['quantite']:g} {e['unite']}",
                                          euros(utiles[0]["median"]), euros(e["bas"]),
                                          euros(e["median"]), euros(e["haut"])])
                for k in total:
                    total[k] += e[k]
                chiffres += 1
            else:
                fiche["estimation"] = None
                lignes_estimation.append([r["poste"], f"{r['quantite']:g} {r.get('unite') or ''}".strip(),
                                          "—", "à chiffrer", "à chiffrer", "à chiffrer"])
        if not fiche["trouve"]:
            sans_prix.append(r["poste"])
        fiches.append(fiche)

    trouve = any(f["trouve"] for f in fiches)
    blocs = []
    if lignes_tableau:
        blocs.append({"type": "table", "titre": "Prix déjà pratiqués par la maison (HT)",
                      "columns": ["Poste", "Unité", "Obs.", "Plus bas", "Médian", "Plus haut", "Période"],
                      "rows": lignes_tableau})
    if lignes_estimation:
        if chiffres > 1:
            lignes_estimation.append(["TOTAL des postes estimés", "", "", euros(total["bas"]),
                                      euros(total["median"]), euros(total["haut"])])
        blocs.append({"type": "table", "titre": "Estimation d'après les prix pratiqués (HT)",
                      "columns": ["Poste", "Quantité", "PU médian", "Bas", "Médian", "Haut"],
                      "rows": lignes_estimation})

    resultat = {
        "trouve": trouve, "postes": fiches, "base_de_prix": base or "absente",
        "jeux_de_donnees": existants if not trouve else None,
    }
    if sans_prix:
        resultat["sans_observation"] = sans_prix
    if not trouve:
        resultat["message"] = (
            "Aucun devis ni facture passé ne décrit " + ", ".join(f"« {p} »" for p in sans_prix)
            + " au moins deux fois : pas d'ordre de prix à en tirer.")
        resultat["a_faire"] = (
            "Dis-le franchement et n'avance AUCUN chiffre : ni prix de marché, ni ordre de "
            "grandeur « habituel ». Retente UNE fois avec un autre mot du métier (le nom de "
            "l'ouvrage seul : « abattage », « dessouchage », « élagage »), puis laisse la ligne "
            "« à chiffrer » dans le pré-devis."
            + (" La base de prix est encore en cours de lecture : dis-le, le relevé sera plus "
               "fourni plus tard." if (base or {}).get("reste_a_lire") else ""))
        return resultat

    resultat["bloc_ui"] = blocs if len(blocs) != 1 else blocs[0]
    resultat["bloc_garanti"] = True
    resultat["message_final"] = (
        f"Relevé des prix pratiqués pour {len([f for f in fiches if f['trouve']])} poste(s)"
        + (f" ; {len(sans_prix)} sans observation" if sans_prix else "") + ".")
    resultat["a_faire"] = (
        "Le ou les tableaux s'affichent AUTOMATIQUEMENT : ne les recopie pas. Ce sont les prix "
        "que la maison a DÉJÀ pratiqués, lus ligne à ligne dans ses devis et factures. "
        "POUR ESTIMER un poste : quantité × prix unitaire MÉDIAN de la MÊME unité, et donne la "
        "fourchette (plus bas – plus haut) à côté, avec le nombre d'observations. Rappelle ce "
        "geste avec `postes: [{poste, quantite, unite}]` pour que le calcul soit fait par le "
        "serveur plutôt que de tête. Un FORFAIT ne se transpose que si la désignation de "
        "l'exemple décrit un ouvrage comparable : lis les `exemples` avant de t'en servir. Ne "
        "mélange jamais deux unités. Un poste sans observation reste « à chiffrer » : aucun "
        "prix de marché, aucun prix du web, aucun chiffre de tête. Présente le tout comme une "
        "ESTIMATION à valider par la personne, jamais comme un prix ferme."
        + (" La base de prix est encore en cours de lecture : dis-le en une phrase."
           if (base or {}).get("reste_a_lire") else ""))
    return resultat


SKILLS = {
    "liste_clients": Declaration(
        fonction=liste_clients,
        description=(
            "LISTE les clients de l'entreprise en UN SEUL appel : le nombre exact, "
            "les noms, et le contact quand il est connu. C'est le skill a appeler "
            "pour « la liste des clients », « combien de clients », « qui sont nos "
            "clients » — PAS `interroger_donnees`, qui demanderait trois "
            "allers-retours pour la meme reponse, ni `rechercher_documents`, qui "
            "approxime. Le resultat donne un bloc ```ui a inserer TEL QUEL (60 noms "
            "au plus par appel, par ordre alphabetique ; `lettre` = une initiale pour "
            "la suite). Pour la liste COMPLETE, ou des qu'on demande « tous », « tout », "
            "« la liste entiere », un export, un Excel : passe `fichier: true` — le "
            "resultat est un fichier Excel avec apercu dans le chat, jamais une liste "
            "a recopier. Ne cherche JAMAIS sur le web pour cette question : les "
            "clients sont une donnee interne. "
            "LE FICHIER SE FACONNE ICI, en un seul appel : `colonnes` garde celles "
            "qu'on demande (`[\"Client\"]` pour « juste les noms ») et `ajouts` ajoute "
            "des colonnes CONSTANTES, repetees sur toutes les lignes "
            "(`{\"E-mail\": \"@moi\"}`). `@moi` vaut l'adresse de la personne connectee : "
            "elle est connue du serveur, ne la demande JAMAIS a l'utilisateur. "
            "N'enchaine pas d'autre action apres : le fichier est produit, montre-le"),
        requis=[], optionnels=["lettre", "fichier", "colonnes", "ajouts"],
        effet="lecture",
        libelle="je liste les clients"),
    "liste_fournisseurs": Declaration(
        fonction=liste_fournisseurs,
        description=(
            "LISTE les fournisseurs de l'entreprise en UN SEUL appel : le nombre "
            "exact, les noms, et le contact quand il est connu. C'est le skill a "
            "appeler pour « la liste des fournisseurs », « combien de fournisseurs », "
            "« qui sont nos fournisseurs » — PAS `interroger_donnees` ni "
            "`rechercher_documents`. Le resultat donne un bloc ```ui a inserer TEL "
            "QUEL (60 noms au plus par appel ; `lettre` = une initiale pour la "
            "suite). Pour la liste COMPLETE, ou des qu'on demande « tous », un "
            "export, un Excel : passe `fichier: true` — le resultat est un fichier "
            "Excel avec apercu dans le chat, jamais une liste a recopier. Ne "
            "cherche JAMAIS sur le web : les fournisseurs sont une donnee interne. "
            "LE FICHIER SE FACONNE ICI, en un seul appel : `colonnes` garde celles "
            "qu'on demande et `ajouts` ajoute des colonnes CONSTANTES "
            "(`{\"E-mail\": \"@moi\"}`). `@moi` vaut l'adresse de la personne "
            "connectee : elle est connue du serveur, ne la demande JAMAIS a "
            "l'utilisateur. N'enchaine pas d'autre action apres : le fichier est "
            "produit, montre-le"),
        requis=[], optionnels=["lettre", "fichier", "colonnes", "ajouts"],
        effet="lecture",
        libelle="je liste les fournisseurs"),
    "fiche_client": Declaration(
        fonction=fiche_client,
        description=(
            "TOUT ce que l'entreprise sait d'UN client, en UN SEUL appel et a "
            "travers TOUS les fichiers importes : devis (nombre, references, "
            "montants, statuts), factures, chantiers, chiffre d'affaires genere, "
            "coordonnees. C'est le skill a appeler des qu'une question porte sur un "
            "client nomme — « parle-moi de X », « combien de devis pour X », « quel "
            "chiffre d'affaires avec X ». `nom` : le nom du client. `champs` : la "
            "LISTE des informations precises qu'on te demande (« SIRET », « assurance "
            "decennale », « adresse ») — passe-la des qu'une question porte sur un "
            "renseignement nomme : ce qui manque revient marque [A COMPLETER] au lieu "
            "de disparaitre en silence. `devis` est trie du plus RECENT au plus ancien. "
            "Les chiffres rendus sont EXACTS : cite-les tels quels, ne les recalcule pas"),
        requis=["nom"], optionnels=["champs"],
        effet="lecture",
        libelle="je rassemble la fiche du client"),
    "dossiers_en_attente": Declaration(
        fonction=dossiers_en_attente,
        description=(
            "LES DOSSIERS QUI ATTENDENT UNE REPONSE depuis plus de N jours, du "
            "plus ancien au plus recent, avec l'anciennete EXACTE de chacun. "
            "C'est le geste du SUIVI : « les dossiers ou on attend une reponse "
            "depuis plus de 15 jours », « qui faut-il relancer », « les devis "
            "sans nouvelles ». `jours` : le seuil (15 par defaut, dis toujours "
            "lequel a servi). `source_type` : le fichier a examiner, sinon tous "
            "ceux qui portent des affaires en cours. `statuts` : les statuts qui "
            "comptent comme « en attente », si la maison a son propre "
            "vocabulaire. Le resultat donne un bloc ```ui a inserer TEL QUEL. "
            "N'envoie AUCUNE relance : ce geste ne fait que regarder"),
        requis=[], optionnels=["jours", "source_type", "statuts"],
        effet="lecture",
        libelle="je regarde les dossiers en attente"),
    "prix_observes": Declaration(
        fonction=prix_observes,
        description=(
            "LES PRIX QUE L'ENTREPRISE PRATIQUE, lus ligne a ligne dans ses devis et "
            "factures (designation, unite, prix unitaire HT), plus les totaux d'affaires "
            "et le catalogue d'articles. A appeler des qu'on demande un ordre de prix, "
            "une ESTIMATION, un pre-devis, un chiffrage, ou « combien on facture pour X ». "
            "`postes` : la liste des ouvrages, avec les mots du metier, et pour chacun "
            "`quantite` et `unite` si on les connait — ex. [{\"poste\": \"abattage "
            "arbre\", \"quantite\": 3, \"unite\": \"u\"}, {\"poste\": \"terrasse "
            "bois\", \"quantite\": 40, \"unite\": \"m2\"}] : le SERVEUR calcule alors "
            "l'estimation (bas, median, haut) et le total. `poste` seul marche aussi. UN "
            "SEUL appel pour tous les postes d'un pre-devis. Rends une ESTIMATION sourcee "
            "(fourchette + nombre d'observations), jamais un prix ferme ; un poste sans "
            "observation reste « a chiffrer ». Ne cherche JAMAIS un prix sur le web pour "
            "chiffrer une affaire : ce ne sont pas les prix de la maison"),
        requis=[], optionnels=["poste", "postes", "quantite", "unite", "source_type"],
        effet="lecture",
        libelle="je relève les prix déjà pratiqués"),
    "check_mails": Declaration(
        fonction=check_mails,
        description=(
            "FAIT LE POINT sur le courrier recent en UN SEUL appel : les derniers "
            "messages, lesquels sont des reponses a un fil en cours, lesquels sont "
            "non lus. A appeler pour « fais un check de mes mails », « quoi de neuf "
            "dans ma boite », « resume-moi mes mails ». Rends ensuite UN SEUL "
            "message : un resume par mail, et une PROPOSITION de reponse quand le "
            "message en appelle une. N'envoie rien — l'envoi passe par "
            "`redaction_email` et sa validation. `depuis` : OBLIGATOIRE des qu'une "
            "periode est nommee (« cette semaine » → \"7j\", « ce mois » → \"30j\", ou "
            "une date AAAA-MM-JJ) : le resultat donne alors le TOTAL EXACT de la "
            "periode en plus du detail des 25 plus recents — s'il y en a PLUS, "
            "ENCHAINE avec `avant` (rendu par pour_continuer) jusqu'a tout couvrir, "
            "PUIS redige UNE synthese. `limite` : 1 a 25 (defaut 15)"),
        requis=[], optionnels=["mailbox", "dossier", "limite", "depuis", "avant", "curseur"],
        effet="lecture",
        libelle="je fais le point sur les mails"),
}
