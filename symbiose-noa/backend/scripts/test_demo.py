"""
Banc de la DÉMO — les dix questions du cahier de démonstration, une par une.

Ce banc ne mesure pas du code : il mesure une PROMESSE. Chacune des dix
questions que l'on posera devant un dirigeant est rejouée ici sur les modules
réellement livrés, avec un jeu de données de paysagiste plausible — pas les
données du client, qui n'existent pas encore sur cette machine. L'idée est
qu'aucune des dix ne découvre son trou le jour de la démonstration.

CE QUE CE BANC PROUVE, ET CE QU'IL NE PROUVE PAS.
Il prouve la MÉCANIQUE : le skill existe, il accepte les paramètres que la
question impose, il rend ce qu'il faut pour répondre, et il refuse d'inventer
quand il ne sait pas. Il ne prouve rien du choix que fera le modèle, ni de la
qualité de sa rédaction : aucun appel LLM n'est fait ici. Une question verte
peut encore échouer parce que le modèle a choisi un autre geste ; une question
rouge, elle, échouera à coup sûr, quel que soit le modèle.

TROIS ISSUES, PAS DEUX.
  ✓  le contrôle passe ;
  ✗  le contrôle tombe — c'est un fait, pas une opinion ;
  ·  LIMITE : ce qui est vrai du code et qu'aucun correctif ne rend faux
     aujourd'hui (une contrainte d'architecture, un geste qui n'existe pas).
     Ce n'est pas compté comme un échec, mais c'est écrit noir sur blanc, et
     c'est ce qu'il faut savoir AVANT de promettre la question à un client.

Ni base, ni réseau : la base est une doublure qui rend le JSONB en CHAÎNE,
comme asyncpg sans codec (c'est ce détail qui a caché un crash de production
le 22/08 ; une doublure qui ment sur le type teste un code qui n'existe pas).
"""
import sys, types, asyncio, json, ast, pathlib

BACKEND = sys.argv[1] if len(sys.argv) > 1 else "backend"
racine = pathlib.Path(BACKEND)
sys.path.insert(0, BACKEND)


# ═══════════════════════════════════════════════════════════════════════
#  LE JEU D'ESSAI — un paysagiste plausible du bassin d'Arcachon
# ═══════════════════════════════════════════════════════════════════════
#
# Volontairement imparfait, comme un export réel : en-têtes en français, nom du
# jeu au pluriel et en majuscules, montants à la française, une prestation
# écrite en toutes lettres (« Création terrasse bois et allée ») plutôt qu'en
# catégorie propre — c'est justement ce qui rend la question 2 difficile.
CLIENTS = [
    {"Raison sociale": "SCI Les Tilleuls", "Ville": "Arcachon",
     "Email": "contact@tilleuls.fr", "Téléphone": "05 56 00 00 01"},
    {"Raison sociale": "Mairie de La Teste", "Ville": "La Teste-de-Buch",
     "Email": "marches@lateste.fr"},
    {"Nom": "MARTIN", "Prénom": "Claire", "Ville": "Gujan-Mestras"},
]
DEVIS = [
    # L'ordre du fichier n'est PAS l'ordre chronologique : c'est le cas normal
    # d'un export trié par référence. « Le DERNIER devis » demande donc un tri.
    {"Référence": "DEV-2025-014", "Client": "SCI Les Tilleuls", "Date": "12/03/2025",
     "Statut": "signé", "Montant HT": "12 450,50 €"},
    {"Référence": "DEV-2026-041", "Client": "SCI Les Tilleuls", "Date": "02/06/2026",
     "Statut": "envoyé", "Montant HT": "3 200,00 €"},
    {"Référence": "DEV-2025-088", "Client": "SCI Les Tilleuls", "Date": "18/11/2025",
     "Statut": "refusé", "Montant HT": "7 800,00 €"},
]
FACTURES = [
    {"Numéro": "FA-2025-101", "Client": "SCI Les Tilleuls", "Date": "30/04/2025",
     "Montant TTC": "14 940,60 €"},
]
# LES DATES DES CHANTIERS SONT RELATIVES À AUJOURD'HUI, et écrites dans QUATRE
# formats différents — c'est le cœur de la question 2. Un banc dont les dates
# sont figées prouve que le code marchait le jour où on l'a écrit ; celui-ci
# doit valoir dans six mois, et sur un export qui n'écrit pas les dates comme
# nous. Les deux chantiers « limite » encadrent la borne des douze mois à un
# jour près : c'est ce qu'un filtre au mois entier ne saurait pas trancher.
import datetime as _dt

_AUJ = _dt.date.today()


def _il_y_a(jours=0, mois=0):
    a = _AUJ - _dt.timedelta(days=jours)
    if mois:
        total = a.year * 12 + (a.month - 1) - mois
        an, m = divmod(total, 12)
        a = _dt.date(an, m + 1, min(a.day, 28))
    return a


_MOIS_COURTS = ("janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.",
                "août", "sept.", "oct.", "nov.", "déc.")
_L = _il_y_a(mois=6)

CHANTIERS = [
    # JJ/MM/AAAA — le format le plus courant des exports français.
    {"Chantier": "Villa Pereire", "Client": "SCI Les Tilleuls",
     "Date": _il_y_a(mois=11).strftime("%d/%m/%Y"),
     "Prestation": "Création terrasse bois et allée", "Montant HT": "18 400,00 €"},
    # « 5 sept. 25 » — une saisie à la main, que l'ancien filtre PERDAIT.
    {"Chantier": "Le Moulleau", "Client": "MARTIN Claire",
     "Date": f"{_L.day} {_MOIS_COURTS[_L.month - 1]} {_L.strftime('%y')}",
     "Prestation": "Terrasse bois exotique + massif de graminées", "Montant HT": "9 250,00 €"},
    # Hors période, et de loin.
    {"Chantier": "Résidence du Port", "Client": "Mairie de La Teste",
     "Date": _il_y_a(mois=26).strftime("%d/%m/%Y"),
     "Prestation": "Engazonnement et arrosage", "Montant HT": "31 000,00 €"},
    # ISO, avec une heure — ce que rend un logiciel métier.
    {"Chantier": "Cap Ferret", "Client": "MARTIN Claire",
     "Date": _il_y_a(mois=2).strftime("%Y-%m-%dT08:30:00"),
     "Prestation": "Terrasse en bois et pergola", "Montant HT": "11 900,00 €"},
    # LES DEUX BORNES, à un jour près de part et d'autre des douze mois.
    {"Chantier": "Pyla dedans", "Client": "SCI Les Tilleuls",
     "Date": _il_y_a(jours=363).strftime("%d/%m/%Y"),
     "Prestation": "Terrasse bois sur plots", "Montant HT": "1 000,00 €"},
    {"Chantier": "Pyla dehors", "Client": "SCI Les Tilleuls",
     "Date": _il_y_a(jours=367).strftime("%d/%m/%Y"),
     "Prestation": "Terrasse bois sur plots", "Montant HT": "1 000 000,00 €"},
]
# Le fournisseur EXISTE, mais ni son SIRET ni son assurance décennale n'ont été
# importés : c'est exactement le terrain de la question 3.
FOURNISSEURS = [
    {"Fournisseur": "Ets Lasserre", "Ville": "Le Barp", "Spécialité": "Bois exotique",
     "Contact": "commande@lasserre.fr"},
]
BASE = {"CLIENTS 2026": CLIENTS, "devis": DEVIS, "factures": FACTURES,
        "chantiers": CHANTIERS, "fournisseurs": FOURNISSEURS}

# Ce que la migration 020 range dans `champs` — partiel, comme un vrai import.
_NORMALISE = {"Raison sociale": "nom", "Fournisseur": "nom", "Client": "nom",
              "Montant HT": "montant_ht", "Montant TTC": "montant_ttc",
              "Référence": "reference", "Numéro": "reference", "Date": "date",
              "Statut": "statut"}


def _champs(d):
    return {_NORMALISE[k]: v for k, v in d.items() if k in _NORMALISE}


def _jsonb(d):
    """Comme asyncpg sans codec : une CHAÎNE, jamais un dict."""
    return json.dumps(d, ensure_ascii=False)


def _ligne(type_source, d, i=0):
    return {"source_type": type_source, "title": d.get("Chantier") or d.get("Référence") or "",
            "data": _jsonb(d), "champs": _jsonb(_champs(d)),
            "source_filename": f"{type_source}.xlsx", "ligne": i}


class FausseConnexion:
    """Répond aux requêtes RÉELLES des modules, pas à des requêtes inventées."""

    async def fetch(self, sql, *args):
        if "DISTINCT source_type" in sql:
            return [{"source_type": t} for t in sorted(BASE)]
        if "jsonb_each_text" in sql:                      # colonnes de `champs`
            cles = set()
            for d in BASE.get(args[0], []):
                cles |= set(_champs(d))
            return [{"cle": c} for c in sorted(cles)]
        if "data::text ILIKE" in sql:                     # fiche_client
            motif = args[1].strip("%").lower()
            return [_ligne(t, d, i)
                    for t, lignes in BASE.items()
                    for i, d in enumerate(lignes)
                    if motif in json.dumps(d, ensure_ascii=False).lower()]
        if "@>" in sql and "SELECT title" in sql:         # _filtrer, échantillon
            return [_ligne(args[0], d, i) for i, d in enumerate(self._filtres(*args))]
        if "SELECT data, champs FROM document_metadata m" in sql:   # _charger
            # Ce que Postgres filtre : la source, les droits, le containment
            # JSONB et les ILIKE. Le reste (la période, le calcul) se fait en
            # Python, dans le module livré — c'est justement ce qu'on teste.
            *reste, limite = args[2:]
            return [{"data": _jsonb(d), "champs": _jsonb(_champs(d))}
                    for d in self._filtres(args[0], args[1], *reste)][:limite]
        if "SELECT data, champs FROM document_metadata" in sql:
            return [{"data": _jsonb(d), "champs": _jsonb(_champs(d))}
                    for d in BASE.get(args[0], [])]
        if "COUNT(DISTINCT source_id)" in sql:             # _inventaire
            return [{"source_type": "chantier", "n": 42},
                    {"source_type": "devis", "n": 118}]
        if "SELECT DISTINCT d.key" in sql:
            return []
        return []

    @classmethod
    def _agreger(cls, sql, type_source, niveaux, colonne, motif_annee, colonne_date,
                 param_groupe, charge, *reste):
        """Refait, en Python, ce que fait la requête d'agrégation réelle.

        Y compris ses deux règles qui comptent : la valeur est du TEXTE qu'on
        lit avec prudence (« 18 400,00 € »), et l'année se cherche par motif
        dans la colonne de date, elle aussi textuelle.
        """
        import re as _re
        operation = next((o for o in ("SUM", "AVG", "MIN", "MAX", "COUNT")
                          if f"{o}(nombre)" in sql), "SUM")
        critere = json.loads(charge) if charge else {}
        partiel = cls._paires(reste)
        groupes = {}
        for d in BASE.get(type_source, []):
            fondu = dict(d); fondu.update(_champs(d))
            if critere and not all(str(fondu.get(k, "")) == str(v)
                                   for k, v in critere.items()):
                continue
            if not all(bout.lower() in str(fondu.get(col, "")).lower()
                       for col, bout in partiel):
                continue
            if motif_annee and not _re.search(motif_annee,
                                              str(fondu.get(colonne_date, ""))):
                continue
            brut = str(fondu.get(colonne, ""))
            nettoye = brut.replace(" ", "").replace("\xa0", "").replace(" ", "")
            nettoye = _re.sub(r"[^0-9,.-]", "", nettoye).replace(",", ".")
            try:
                nombre = float(nettoye)
            except ValueError:
                nombre = None
            cle = None
            if "annee" in sql and param_groupe == colonne_date:
                trouve = _re.search(r"([0-9]{4})", str(fondu.get(colonne_date, "")))
                cle = trouve.group(1) if trouve else None
            g = groupes.setdefault(cle, {"enregistrements": 0, "lisibles": 0, "valeurs": []})
            g["enregistrements"] += 1
            if nombre is not None:
                g["lisibles"] += 1
                g["valeurs"].append(nombre)

        def _resultat(v):
            if not v:
                return None
            return {"SUM": sum(v), "AVG": sum(v) / len(v), "MIN": min(v),
                    "MAX": max(v), "COUNT": float(len(v))}[operation]

        return [{"groupe": k, "enregistrements": g["enregistrements"],
                 "lisibles": g["lisibles"], "resultat": _resultat(g["valeurs"])}
                for k, g in groupes.items()]

    @staticmethod
    def _paires(reste):
        """Les paramètres de la recherche partielle : (colonne, « %bout% »)."""
        plats = [a for a in reste if isinstance(a, str)]
        return [(plats[i], plats[i + 1].strip("%"))
                for i in range(0, len(plats) - 1, 2)]

    @classmethod
    def _filtres(cls, type_source, niveaux, charge, *reste):
        critere = json.loads(charge)
        partiel = cls._paires(reste)
        out = []
        for d in BASE.get(type_source, []):
            fondu = dict(d); fondu.update(_champs(d))
            # ÉGALITÉ STRICTE, comme l'opérateur JSONB `@>` de la vraie requête.
            if not all(str(fondu.get(k, "")) == str(v) for k, v in critere.items()):
                continue
            # ILIKE '%bout%' : insensible à la casse, n'importe où dans la valeur.
            if not all(bout.lower() in str(fondu.get(col, "")).lower()
                       for col, bout in partiel):
                continue
            out.append(d)
        return out

    async def fetchval(self, sql, *args):
        if "COUNT(*)" in sql and "@>" in sql:
            return len(self._filtres(*args))
        if "COUNT(*)" in sql:
            return len(BASE.get(args[0], []))
        return 0

    async def fetchrow(self, sql, *args):
        return None


class FauxContexte:
    async def __aenter__(self): return FausseConnexion()
    async def __aexit__(self, *a): return False


# ═══════════════════════════════════════════════════════════════════════
#  Doublures de modules — tout ce qui touche au réseau ou à la base
# ═══════════════════════════════════════════════════════════════════════
def _module(nom, **attrs):
    m = types.ModuleType(nom)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[nom] = m
    # Rattache au paquet parent pour que `from paquet import module` marche.
    if "." in nom:
        parent, feuille = nom.rsplit(".", 1)
        if parent not in sys.modules:
            sys.modules[parent] = types.ModuleType(parent)
        setattr(sys.modules[parent], feuille, m)
    return m


# fastapi : seulement ce que le code utilise (HTTPException + les constantes).
class HTTPException(Exception):
    def __init__(self, status_code=400, detail=""):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


_module("fastapi", HTTPException=HTTPException,
        status=types.SimpleNamespace(HTTP_403_FORBIDDEN=403,
                                     HTTP_422_UNPROCESSABLE_ENTITY=422))
_module("database.connection", get_db=lambda: FauxContexte())
_module("security.acces", niveaux_visibles=lambda role: {"all", "direction", "public"})
_module("security.anonymizer",
        anonymizer=types.SimpleNamespace(anonymize=lambda t: (t, {}),
                                         rehydrate=lambda t, c: t))


class SkillError(Exception):
    pass


_module("skills.erreurs", SkillError=SkillError)


class Declaration:
    def __init__(self, **kw):
        self.__dict__.setdefault("requis", [])
        self.__dict__.setdefault("optionnels", [])
        self.__dict__.setdefault("effet", "externe")
        self.__dict__.setdefault("libelle", "")
        self.__dict__.setdefault("expert", "")
        self.__dict__.update(kw)


_module("skills.registre", Declaration=Declaration)
_module("config", settings=types.SimpleNamespace(
    browser_enabled=True, ms_domain="symbiose-paysage.fr", gmail_domain=None,
    ms_mailbox=None, ms_extra_mailboxes=None, gmail_extra_mailboxes=None,
    documents_dir="/tmp", model_google_vision="gemini-flash-latest"))

# Le modèle : une doublure qui rend le JSON attendu, sans réseau.
REPONSES_LLM = {}


class _FauxLLM:
    def __init__(self, cle): self.cle = cle

    async def ainvoke(self, messages, config=None):
        texte = str(getattr(messages[0], "content", messages[0]))
        for motif, sortie in REPONSES_LLM.items():
            if motif in texte:
                return types.SimpleNamespace(content=sortie, usage_metadata={})
        return types.SimpleNamespace(content="{}", usage_metadata={})


_module("llm.router", get_llm=lambda t=None: _FauxLLM(t),
        LLMTier=lambda v="standard": v)


class HumanMessage:
    def __init__(self, content): self.content = content


_module("langchain_core.messages", HumanMessage=HumanMessage,
        SystemMessage=HumanMessage, AIMessage=HumanMessage)


async def _consigne_style(boite): return ""


_module("mail.style", consigne_style=_consigne_style)

# Le dépôt de visuels : en mémoire, la clé est un hachage du contenu.
DEPOT = {}


def _deposer(octets, mime="image/png"):
    import hashlib
    cle = hashlib.sha256(octets).hexdigest()[:32]
    DEPOT[cle] = (octets, mime)
    return cle


_module("visuels.depot", deposer_octets=_deposer,
        lire=lambda cle: DEPOT.get(cle))


class NanoBananaIndisponible(RuntimeError):
    pass


APPELS_IMAGE = []


async def _generer(prompt, images_entree=None, qualite="finale", **kw):
    APPELS_IMAGE.append({"prompt": prompt, "entrees": len(images_entree or []),
                         "qualite": qualite})
    return {"images": [(b"apres-" + str(len(APPELS_IMAGE)).encode(), "image/png")],
            "modele": "doublure"}


async def _disponible(): return True


_module("visuels.nano_banana", generer=_generer, disponible=_disponible,
        NanoBananaIndisponible=NanoBananaIndisponible,
        RATIOS={"16:9": "16:9", "1:1": "1:1"}, RESOLUTIONS={"1080p": "1080p"})

# Le RAG : trois chantiers qui « ressemblent », dont un avec des photos.
RAG_APPELS = []


async def _retrieve(requete, role, source_types=None, top_k=5, mailboxes=None):
    RAG_APPELS.append({"requete": requete, "types": source_types, "top_k": top_k})
    if "introuvable" in requete:
        return []
    return [
        {"source_filename": "Villa Pereire - CR visite.pdf", "source_type": "chantier",
         "content": "Terrain en pente, terrasse bois exotique 45 m2, bassin d'Arcachon."},
        {"source_filename": "Le Moulleau - devis.pdf", "source_type": "devis",
         "content": "Terrasse bois sur plots, massif de graminées, dénivelé 1,80 m."},
        {"source_filename": "Cap Ferret - photos chantier.zip", "source_type": "chantier",
         "content": "Terrasse bois et pergola, terrain pentu, photos avant/après."},
    ]


async def _retrieve_as_context(query, user_role=None, source_types=None, top_k=5, **kw):
    return [c["content"] for c in await _retrieve(query, user_role, source_types, top_k)]


async def _rechercher(query, user_role=None, source_types=None, mailboxes=None,
                      limite=6, page=1, fichier=None):
    """Le geste à l'échelle (31/08) : les mêmes morceaux, GROUPÉS par document."""
    chunks = await _retrieve(query, user_role, source_types, limite * page * 4, mailboxes)
    docs = _fusion.grouper_par_document([dict(c, source_id=c["source_filename"], id=c["source_filename"])
                                         for c in chunks])
    return {"documents": docs, "total_documents": len(docs), "total_morceaux": len(chunks),
            "embedding": True, "page": page, "limite": limite}


_module("vectorstore.rag", retrieve=_retrieve, retrieve_as_context=_retrieve_as_context,
        rechercher=_rechercher)
# `vectorstore.fusion` est PUR (aucune dépendance) : on charge le vrai module,
# rattaché au paquet doublé — c'est lui que le skill exerce.
import importlib.util as _ilu
_spec = _ilu.spec_from_file_location("vectorstore.fusion", pathlib.Path(BACKEND) / "vectorstore" / "fusion.py")
_fusion = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_fusion)
sys.modules["vectorstore.fusion"] = _fusion
setattr(sys.modules["vectorstore"], "fusion", _fusion)


# ── Le Drive : une doublure qui répond comme l'API de Google ──────────
#
# Les fichiers portent leur `mimeType` et leur `size`, parce que c'est sur ces
# deux champs que le geste décide : une image ou non, trop lourde ou non.
FICHIERS_DRIVE = [
    {"id": "f1", "name": "pereire-avant.jpg", "mimeType": "image/jpeg",
     "size": "2400000", "modifiedTime": "2026-06-01T10:00:00Z"},
    {"id": "f2", "name": "pereire-terrasse.jpg", "mimeType": "image/jpeg",
     "size": "3100000", "modifiedTime": "2026-06-02T10:00:00Z"},
    {"id": "f3", "name": "pereire-plan.png", "mimeType": "image/png",
     "size": "800000", "modifiedTime": "2026-06-03T10:00:00Z"},
    {"id": "f4", "name": "pereire-drone.jpg", "mimeType": "image/jpeg",
     "size": "40000000", "modifiedTime": "2026-06-04T10:00:00Z"},   # trop lourde
    {"id": "f5", "name": "cctp-pereire.pdf", "mimeType": "application/pdf",
     "size": "120000", "modifiedTime": "2026-06-05T10:00:00Z"},     # pas une image
]


class _FauxDrive:
    """Le strict nécessaire de l'API Google Drive : list() et get_media()."""

    def files(self):
        return self

    def list(self, q="", **kw):
        images = "image/jpeg" in q
        vide = "sans image" in q.lower()
        trouves = [] if vide else [
            f for f in FICHIERS_DRIVE
            if (not images or f["mimeType"].startswith("image/"))]
        return types.SimpleNamespace(execute=lambda: {"files": trouves})

    def get_media(self, fileId=""):
        return types.SimpleNamespace(execute=lambda: b"octets-" + fileId.encode())


async def _service_drive(identite=None):
    return _FauxDrive()


async def _rien():
    return []


async def _dossier(chemin):
    """Le dossier demandé se résout, sauf s'il n'existe pas."""
    return None if not chemin else f"dossier:{chemin}"
_module("optim.tokens", trim_chunks=lambda c: c)


async def _boites_par_id(uid): return ["contact@symbiose-paysage.fr"]


# Les consignes retenues : le vrai module en écrit une ligne en base, on garde
# la MÊME frontière (texte, portée, plafond de caractères) pour que le banc
# teste ce qui est écrit, pas ce qu'on aurait aimé écrire.
CONSIGNES = []


async def _ajouter_consigne(texte, user, pour_tous=False, access_level="all"):
    if len(texte) > 400:
        return {"ok": False, "message": "Consigne trop longue."}
    CONSIGNES.append({"texte": texte, "pour_tous": pour_tous})
    return {"ok": True, "message": "Consigne enregistrée.", "pour_tous": pour_tous}


_module("learning.consignes", ajouter=_ajouter_consigne, MAX_CARACTERES=400)


# ═══════════════════════════════════════════════════════════════════════
#  Chargement des modules RÉELS
# ═══════════════════════════════════════════════════════════════════════
import importlib.util  # noqa: E402


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, racine / chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
    # Rattaché au paquet parent, sinon un `from skills.lecture import ...` fait
    # DEPUIS un module livré échoue : le module est bien dans sys.modules, mais
    # Python va chercher l'attribut sur le paquet.
    if "." in nom:
        parent, feuille = nom.rsplit(".", 1)
        if parent not in sys.modules:
            sys.modules[parent] = types.ModuleType(parent)
        setattr(sys.modules[parent], feuille, module)
    spec.loader.exec_module(module)
    return module


def extraire(chemin, noms, espace):
    """Exécute, du module livré, les seules définitions demandées.

    Certains modules (agent1, agent2, router) chargent un graphe LangGraph
    entier à l'import : on ne prend que ce qu'on teste.
    """
    arbre = ast.parse((racine / chemin).read_text(encoding="utf-8"))
    gardes = []
    for n in arbre.body:
        if isinstance(n, ast.ImportFrom) and n.module == "__future__":
            gardes.append(n)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms:
            gardes.append(n)
        elif isinstance(n, ast.Assign) and any(
                isinstance(c, ast.Name) and c.id in noms for c in n.targets):
            gardes.append(n)
        elif isinstance(n, ast.Import) and any((a.asname or a.name) in noms for a in n.names):
            gardes.append(n)
    exec(compile(ast.Module(body=gardes, type_ignores=[]), str(chemin), "exec"), espace)
    manquants = [x for x in noms if x not in espace]
    assert not manquants, f"absent du module livré ({chemin}) : {manquants}"
    return espace


# La lecture des dates et des montants, chargée EN PREMIER : les autres
# modules livrés l'importent.
lecture = charger("skills.lecture", "skills/lecture.py")
_lecture = lecture
routines = charger("skills.routines", "skills/routines.py")
donnees = charger("skills.donnees", "skills/donnees.py")
documents = charger("skills.documents", "skills/documents.py")
visuels = charger("skills.visuels", "skills/visuels.py")
_module("mail.authorization",
        **{k: v for k, v in vars(charger("mail.authorization",
                                         "mail/authorization.py")).items()
           if not k.startswith("__")})
sys.modules["mail.authorization"].boites_par_id = _boites_par_id
mail_skills = charger("mail.skills", "mail/skills.py")
protocol_src = (racine / "skills" / "protocol.py").read_text(encoding="utf-8")


class User:
    role = "direction"
    id = "00000000-0000-0000-0000-000000000001"
    email = "noa@symbiose-paysage.fr"


class UserSansBoite(User):
    """Le cas de la démo : on colle un mail dans le chat, aucune boîte n'est
    nommée, et le compte n'est pas administrateur."""
    role = "commercial"
    email = "commercial@symbiose-paysage.fr"


# ═══════════════════════════════════════════════════════════════════════
echecs, limites = [], []


def verifier(nom, condition, detail=""):
    print(f"  {'✓' if condition else '✗'} {nom}" + (f"  → {detail}" if detail and not condition else ""))
    if not condition:
        echecs.append(nom)


def signaler(texte):
    """Une contrainte du code, vraie aujourd'hui. Ni réussite, ni échec."""
    print(f"  · LIMITE : {texte}")
    limites.append(texte)


async def _leve(coroutine) -> bool:
    """Ce geste refuse-t-il ? Un refus explicite est un résultat, pas une panne."""
    try:
        await coroutine
        return False
    except Exception:  # noqa: BLE001
        return True


def _plat_test(v):
    """Forme comparable, pour les contrôles qui regardent un libellé."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(v or ""))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def titre(n, question):
    print(f"\n{'─' * 72}\nQ{n}. {question}")


async def principal():
    print(f"\n═══ CAHIER DE DÉMO — dix questions — {BACKEND}")

    # ═══════════════════════════════════════════════════════════════════
    titre(1, "« Le dernier devis envoyé à SCI Les Tilleuls : montant, date, où il en est ? »")
    r = await routines.fiche_client({"nom": "SCI Les Tilleuls"}, User())
    verifier("le client est retrouvé à travers TOUS les jeux importés", r.get("trouve"),
             r.get("message"))
    devis = r.get("devis") or []
    lignes_devis = [d for d in devis if d.get("jeu") == "devis"]
    verifier("les devis remontent avec référence, date, statut et montant",
             lignes_devis and all(d.get("date") and d.get("statut") and d.get("montant")
                                  for d in lignes_devis), devis)
    verifier("le statut demandé (« où il en est ») est une valeur réelle du fichier",
             any(d.get("statut") == "envoyé" for d in devis), [d.get("statut") for d in devis])
    # « LE DERNIER » est le mot de la question. Un export est trié par référence,
    # pas par date : sans tri ici, c'est le modèle qui doit comparer des dates
    # écrites en toutes lettres — exactement ce que le prompt lui interdit.
    verifier("le PLUS RÉCENT est en tête (la question dit « le dernier »)",
             lignes_devis and lignes_devis[0].get("date") == "02/06/2026",
             [d.get("date") for d in lignes_devis])
    verifier("les chiffres portent leur source (aucun total n'est orphelin)",
             r.get("source_chiffre_affaires") or not r.get("chiffre_affaires"),
             r.get("chiffre_affaires"))
    verifier("la consigne d'affichage impose le bloc d'écran et interdit de recalculer",
             "```ui" in (r.get("a_faire") or "") and "recalcule" in (r.get("a_faire") or ""))

    # ═══════════════════════════════════════════════════════════════════
    titre(2, "« Sur les 12 derniers mois, combien de chantiers avec terrasse bois, "
             "et pour quel montant moyen ? »")
    # Ce que le modèle appellera : le jeu « chantiers », un filtre sur la
    # prestation, une moyenne sur le montant, borné aux 12 derniers mois.
    # « avec terrasse bois » : la prestation est rédigée en toutes lettres dans
    # le fichier. Une égalité stricte ne peut pas la trouver — il faut chercher
    # le mot À L'INTÉRIEUR de la colonne.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "filtres": {"Prestation": "terrasse bois"}}, User())
    # `contient` est le mot que le MODÈLE doit retenir pour se rattraper : la
    # consigne vit donc dans `a_faire`. La personne, elle, lit un constat.
    verifier("l'égalité stricte ne trouve rien, et le dit sans se tromper de mot",
             (r.get("nombre") or 0) == 0 and "contient" in (r.get("a_faire") or ""),
             f"message={r.get('message')!r} a_faire={r.get('a_faire')!r}")
    verifier("le constat lu par la personne reste lisible",
             "`" not in (r.get("message") or "") and (r.get("message") or "").strip() != "")
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "contient": {"Prestation": "terrasse"}}, User())
    verifier("une recherche PARTIELLE retrouve les chantiers « terrasse bois »",
             (r.get("nombre") or 0) == 5,
             f"{r.get('nombre')} trouvé(s) sur 5 attendus")
    # LA QUESTION COMPLÈTE, EN UN SEUL APPEL : le compte ET la moyenne, sur les
    # douze derniers mois, avec des dates écrites de quatre façons différentes.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "contient": {"Prestation": "terrasse"},
         "agreger": {"operation": "moyenne", "colonne": "Montant HT"},
         "depuis": "12m"}, User())
    verifier("une période GLISSANTE (12 derniers mois) est comprise",
             bool(r.get("periode")), r.get("erreur") or r)
    verifier("les quatre écritures de date sont lues (JJ/MM/AAAA, ISO, « 5 sept. 25 »)",
             r.get("lignes_sans_date_lisible") is None, r)
    verifier("le chantier vieux de deux ans est écarté",
             (r.get("lignes_hors_periode") or 0) >= 1, r)
    # LA COUPURE EST AU JOUR PRÈS. Un filtre au mois entier ferait entrer le
    # chantier de J-367 : son montant à sept chiffres rendrait la moyenne
    # méconnaissable, ce qui est précisément le genre d'erreur qu'on ne voit pas.
    verifier("le chantier à J-363 est DEDANS, celui à J-367 est DEHORS",
             r.get("enregistrements") == 4 and (r.get("resultat") or 0) < 20000,
             f"{r.get('enregistrements')} retenus, moyenne {r.get('resultat')}")
    verifier("le compte ET la moyenne sortent du même appel",
             r.get("operation") == "avg"
             and abs((r.get("resultat") or 0) - 10137.5) < 0.01, r)
    verifier("la note cite la période retenue, pour qu'aucun chiffre ne circule nu",
             "Période retenue" in (r.get("note") or ""), r.get("note"))
    verifier("la note dit combien de valeurs étaient lisibles",
             "lisibles" in (r.get("note") or ""))
    for forme in ("l'année dernière", "6 mois", "15 jours", "cette semaine",
                  "3 derniers mois", "30j"):
        rr = await donnees.interroger_donnees(
            {"source_type": "chantiers", "depuis": forme}, User())
        verifier(f"période « {forme} » comprise", bool(rr.get("periode")) or
                 "Aucun enregistrement" in (rr.get("message") or ""),
                 rr.get("erreur") or rr)
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "depuis": "n'importe quoi"}, User())
    verifier("une période illisible est REFUSÉE, jamais ignorée en silence",
             bool(r.get("erreur")), r)
    # Une colonne de date qui n'en est pas une : il faut le DIRE, pas rendre zéro.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "depuis": "12m",
         "agreger": {"colonne_date": "Chantier", "operation": "compte"}}, User())
    verifier("une colonne sans dates lisibles est signalée, pas comptée pour zéro",
             "date lisible" in (r.get("message") or "") or
             (r.get("lignes_sans_date_lisible") or 0) > 0, r)
    # La formulation par ANNÉE marche toujours, elle.
    annee = str(_AUJ.year)
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "annee": annee,
         "agreger": {"operation": "moyenne", "colonne": "Montant HT"}}, User())
    verifier(f"par ANNÉE ({annee}), le compte et la moyenne sortent en un appel",
             (r.get("enregistrements") or 0) >= 1 and r.get("resultat"), r)
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "annee": annee}, User())
    verifier("compter une année sans rien agréger est possible",
             (r.get("enregistrements") or r.get("nombre") or 0) >= 1,
             r.get("erreur") or r)
    # Grouper par mois : « le montant par mois » d'un dirigeant.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "depuis": "12m",
         "agreger": {"operation": "somme", "colonne": "Montant HT", "par": "mois"}}, User())
    verifier("le regroupement par mois fonctionne, toutes écritures confondues",
             len(r.get("groupes") or []) >= 3
             and all(len(str(g["groupe"])) == 7 for g in r["groupes"]),
             r.get("groupes"))

    # ═══════════════════════════════════════════════════════════════════
    titre(3, "« Le SIRET / l'assurance décennale de Ets Lasserre ? » — LA question "
             "de confiance : l'agent doit AVOUER, pas inventer")
    r = await routines.fiche_client(
        {"nom": "Ets Lasserre", "champs": ["SIRET", "assurance décennale"]}, User())
    verifier("le fournisseur est retrouvé", r.get("trouve"), r.get("message"))
    fiche = dict((r.get("bloc_ui") or {}).get("rows") or [])
    verifier("aucun SIRET n'est inventé", not any(
        len(str(v)) > 8 and str(v).replace(" ", "").isdigit() for v in fiche.values()),
        fiche)
    # Le prompt système impose [À COMPLÉTER] pour un champ demandé et absent, et
    # interdit de l'omettre en silence. Le skill, lui, ne rend que les colonnes
    # qu'il connaît : le champ demandé disparaît sans laisser de trace, et rien
    # dans le résultat ne dit au modèle qu'il manque.
    verifier("le champ demandé et absent est marqué [À COMPLÉTER], pas omis",
             sum(1 for v in fiche.values() if "[À COMPLÉTER]" in str(v)) == 2,
             f"la fiche rendue : {fiche}")
    verifier("le message final DIT que l'information n'existe nulle part",
             "ne figure dans aucun fichier" in (r.get("message_final") or ""),
             r.get("message_final"))
    verifier("la consigne interdit d'aller chercher la valeur sur le web",
             "n'est pas une donnée de l'entreprise" in (r.get("a_faire") or ""))
    verifier("les trous sont listés à part, pour que rien ne se perde",
             set(r.get("champs_manquants") or []) == {"SIRET", "assurance décennale"},
             r.get("champs_manquants"))
    # Et quand l'information EST là, elle sort : le trou n'est pas systématique.
    r_ok = await routines.fiche_client(
        {"nom": "Ets Lasserre", "champs": ["Spécialité"]}, User())
    fiche_ok = dict((r_ok.get("bloc_ui") or {}).get("rows") or [])
    verifier("un champ demandé et PRÉSENT rend sa vraie valeur",
             fiche_ok.get("Spécialité") == "Bois exotique", fiche_ok)
    # Le cas où le fournisseur n'existe pas du tout : là, c'est irréprochable.
    r = await routines.fiche_client({"nom": "Ets Inconnu"}, User())
    verifier("un fournisseur inconnu rend « trouvé = faux », pas une fiche vide",
             r.get("trouve") is False)
    verifier("le message dit ce qui a été cherché et où",
             "Aucun enregistrement" in (r.get("message") or "")
             and "jeu(x) de données" in (r.get("message") or ""), r.get("message"))
    verifier("la consigne interdit explicitement d'inventer",
             "n'invente RIEN" in (r.get("a_faire") or ""), r.get("a_faire"))
    # Et surtout : cette question ne doit pas partir chercher un SIRET sur le web
    # et le présenter comme une donnée de l'entreprise.
    espace = {"AgentState": dict}
    extraire("agents/agent1.py",
             {"should_use_browser", "_MOTS_INTERNES", "_MOTS_EXTERNES"}, espace)
    for demande in ("Quel est le numéro de SIRET du fournisseur Ets Lasserre ?",
                    "L'assurance décennale de Ets Lasserre ?",
                    "Le SIRET de Ets Lasserre"):
        verifier(f"pas de repli web automatique sur « {demande[:38]}… »",
                 espace["should_use_browser"]({"query": demande}) == "llm")
    verifier("le web reste ouvert quand on le demande VRAIMENT",
             espace["should_use_browser"](
                 {"query": "cherche sur internet la norme DTU 51.4"}) == "browser")

    # ═══════════════════════════════════════════════════════════════════
    titre(4, "« Voici un email client que je viens de recevoir : […]. Classe-le, "
             "dis-moi l'urgence et prépare-moi une réponse. »")
    OBJET = "Fuite sur l'arrosage automatique - Villa Pereire"
    CORPS = ("Bonjour, depuis hier l'arrosage installé en mai fuit au niveau du "
             "regard. Le jardin est inondé. Pouvez-vous passer rapidement ? "
             "Cordialement, SCI Les Tilleuls")
    REPONSES_LLM["classe-le"] = json.dumps({
        "categorie": "sav", "priorite": "haute", "client_detecte": "SCI Les Tilleuls",
        "resume": "Fuite sur l'arrosage automatique, jardin inondé.",
        "action_suggeree": "Programmer une intervention sous 24h.",
        "delai_conseille": "sous 24h"}, ensure_ascii=False)
    # LE CAS DE LA DÉMO : le message est COLLÉ dans le chat. Aucune boîte n'est
    # nommée — il n'y a aucune raison qu'il y en ait une.
    try:
        r = await mail_skills.triage_email_entrant({"objet": OBJET, "corps": CORPS},
                                                   UserSansBoite())
        ok, detail = bool(r.get("categorie") and r.get("priorite")), r
    except Exception as e:  # noqa: BLE001
        ok, detail = False, f"{type(e).__name__} : {getattr(e, 'detail', e)}"
    verifier("un mail COLLÉ dans le chat se classe sans qu'on nomme une boîte",
             ok, detail)
    # Le même geste, boîte nommée : le contrôle de droits doit rester entier.
    try:
        await mail_skills.triage_email_entrant(
            {"objet": OBJET, "corps": CORPS, "mailbox": "patron@symbiose-paysage.fr"},
            UserSansBoite())
        refuse = False
    except Exception:  # noqa: BLE001
        refuse = True
    verifier("nommer la boîte d'un COLLÈGUE reste refusé (cloisonnement intact)", refuse)
    # La réponse, elle, a déjà son repli de boîte (correctif antérieur).
    REPONSES_LLM["TYPE DE MESSAGE"] = json.dumps({
        "objet": "Re: Fuite sur l'arrosage automatique",
        "corps": "Bonjour,\n\nNous intervenons [À COMPLÉTER].\n\nCordialement,",
        "ton": "cordial", "elements_a_verifier": ["date d'intervention"]}, ensure_ascii=False)
    r = await mail_skills.rediger_email(
        {"type_mail": "reponse", "message_recu": CORPS}, UserSansBoite())
    verifier("la réponse est rédigée sans qu'on nomme une boîte", bool(r.get("corps")))
    verifier("c'est un BROUILLON, et le résultat le dit",
             r.get("statut") == "brouillon" and r.get("envoye") is False)
    verifier("les trous du brouillon sont signalés à relire",
             any("[À COMPLÉTER]" in x for x in r.get("elements_a_verifier") or []),
             r.get("elements_a_verifier"))
    verifier("`mailbox` n'est pas exigé au catalogue pour le triage",
             '"triage_email_entrant": (' in protocol_src
             and '["mailbox"], ["objet", "corps"]' not in protocol_src,
             "le catalogue le déclare REQUIS : le modèle va inventer une adresse "
             "ou réclamer la sienne à l'utilisateur")

    # ═══════════════════════════════════════════════════════════════════
    titre(5, "« Liste-moi tous les dossiers clients où on attend une réponse "
             "depuis plus de 15 jours. »")
    # Aucun geste ne porte cette question — et c'est le cas NORMAL d'une demande
    # métier qu'on n'a pas prévue. Ce qui est testé ici n'est donc pas
    # l'existence d'un skill « dossiers en attente », mais que l'assistant sache
    # composer, faire valider, et RETENIR la marche à suivre.
    src_agent1_p = (racine / "agents" / "agent1.py").read_text(encoding="utf-8")
    verifier("la règle interdit de répondre « je ne sais pas faire »",
             "Ne réponds pas « je ne sais pas faire »" in src_agent1_p
             and "ESSAIE D'ABORD" in src_agent1_p)   # 31/08 : essayer, pas questionner
    verifier("elle impose de vérifier AVANT de retenir",
             "qu'elle a marché" in src_agent1_p
             and "Ne retiens jamais une marche à suivre que tu n'as pas vérifiée" in src_agent1_p)
    plan_mod = charger("skills.plan", "skills/plan.py")
    decl = plan_mod.SKILLS["enregistrer_procedure"]
    verifier("le geste qui retient une marche à suivre existe",
             callable(decl.fonction) and decl.effet == "ecriture_interne")
    r = await plan_mod.enregistrer_procedure(
        {"nom": "dossiers en attente",
         "quand": "quand on demande les dossiers sans réponse depuis N jours",
         "etapes": ["interroger les devis au statut envoyé",
                    "comparer leur date à aujourd'hui",
                    "rendre un tableau trié du plus ancien au plus récent"]}, User())
    verifier("la procédure est enregistrée", r.get("ok"), r)
    verifier("elle est écrite comme une consigne INJECTÉE, pas cherchée",
             CONSIGNES and CONSIGNES[-1]["texte"].startswith("PROCÉDURE"),
             CONSIGNES)
    verifier("le déclencheur ET les trois étapes y sont, dans l'ordre",
             "sans réponse depuis N jours" in CONSIGNES[-1]["texte"]
             and "1) interroger les devis" in CONSIGNES[-1]["texte"]
             and "3) rendre un tableau" in CONSIGNES[-1]["texte"], CONSIGNES[-1])
    verifier("l'utilisateur est prévenu qu'il n'aura plus à la redemander",
             "prochaine fois" in (r.get("message_final") or ""), r.get("message_final"))
    verifier("on peut la retirer aussi facilement qu'on l'a apprise",
             "oublie la procédure" in (r.get("a_faire") or ""))
    try:
        await plan_mod.enregistrer_procedure({"nom": "x", "quand": "y"}, User())
        vide = False
    except Exception:  # noqa: BLE001
        vide = True
    verifier("une procédure sans étapes est refusée", vide)
    try:
        await plan_mod.enregistrer_procedure(
            {"nom": "trop longue", "quand": "q" * 130,
             "etapes": ["e" * 90] * 6}, User())
        longue = False
    except Exception:  # noqa: BLE001
        longue = True
    verifier("une procédure trop longue est REFUSÉE, pas tronquée par la fin",
             longue)
    # ── Le geste qui répond VRAIMENT à la question ─────────────────────────
    r = await routines.dossiers_en_attente({"jours": 15}, User())
    verifier("le geste du suivi existe et trouve les dossiers en souffrance",
             r.get("trouve") and (r.get("nombre") or 0) >= 1, r)
    verifier("le seuil de 15 jours est appliqué ET dit",
             r.get("seuil_jours") == 15 and "15 jours" in (r.get("message_final") or ""),
             r.get("message_final"))
    dossiers = r.get("dossiers") or []
    verifier("chaque dossier porte son ANCIENNETÉ exacte en jours",
             all(isinstance(d.get("jours"), int) and d["jours"] >= 15 for d in dossiers),
             dossiers)
    verifier("la liste est triée du plus ancien au plus récent (l'ordre des appels)",
             [d["jours"] for d in dossiers] == sorted((d["jours"] for d in dossiers),
                                                      reverse=True),
             [d["jours"] for d in dossiers])
    verifier("un devis SIGNÉ n'attend plus rien : il est écarté",
             not any("DEV-2025-014" == d.get("reference") for d in dossiers)
             and (r.get("dossiers_clos") or 0) >= 1, r)
    verifier("un devis REFUSÉ est écarté lui aussi",
             not any("DEV-2025-088" == d.get("reference") for d in dossiers), dossiers)
    verifier("le devis ENVOYÉ, lui, est bien là",
             any("DEV-2026-041" == d.get("reference") for d in dossiers), dossiers)
    verifier("la liste s'affiche dans un tableau prêt à insérer",
             (r.get("bloc_ui") or {}).get("type") == "table"
             and "Attente" in (r["bloc_ui"].get("columns") or []), r.get("bloc_ui"))
    verifier("la consigne interdit d'envoyer les relances de sa propre initiative",
             "Ne propose PAS d'envoyer" in (r.get("a_faire") or ""))
    # Un seuil que RIEN n'atteint doit se dire simplement, pas rendre une erreur.
    r_haut = await routines.dossiers_en_attente({"jours": 9999}, User())
    verifier("un seuil que rien n'atteint se dit simplement",
             r_haut.get("trouve") and r_haut.get("nombre") == 0
             and "Aucun dossier" in (r_haut.get("message_final") or ""), r_haut)
    # Le vocabulaire de la maison prime, quand on le donne.
    r_perso = await routines.dossiers_en_attente(
        {"jours": 0, "statuts": ["refusé"]}, User())
    verifier("des statuts personnalisés remplacent la liste par défaut",
             all("refus" in _plat_test(d.get("statut")) for d in r_perso.get("dossiers") or [])
             and (r_perso.get("nombre") or 0) >= 1, r_perso.get("dossiers"))

    # ═══════════════════════════════════════════════════════════════════
    titre(6, "« Analyse ce plan PDF : surfaces, zones identifiées, postes de travaux. »")
    src2 = (racine / "agents" / "agent2.py").read_text(encoding="utf-8")
    verifier("le schéma d'extraction demande bien surfaces ET postes de travaux",
             '"surfaces_m2"' in src2 and '"postes_travaux"' in src2)
    verifier("l'extraction interdit d'inventer une cote",
             "Ne jamais inventer" in src2 and "non lisible" in src2)
    verifier("un PDF de plan (peu de texte) part bien à la vision, pas au texte",
             "< 300" in (racine / "routers" / "chat.py").read_text(encoding="utf-8"))
    espace2 = {"json": json, "AgentState": dict,
               "logger": types.SimpleNamespace(info=lambda *a, **k: None,
                                              warning=lambda *a, **k: None)}
    extraire("agents/agent2.py",
         {"prechiffrage_node", "_blocs_extraction", "_bloc", "_libelle",
          "_valeur_texte", "_CLES_SURFACES", "_CLES_POSTES", "_CLES_ELEMENTS",
          "_CLES_RESERVES"},
         espace2)
    etat = {"vision_analysis": "Terrasse existante 40 m2, dénivelé 1,20 m, accès étroit.",
            "extracted_data": {"surfaces_m2": {"terrasse": 40},
                               "postes_travaux": ["dépose terrasse", "terrassement"],
                               "incertitudes": ["cote du muret non lisible"]},
            "raw_chunks": ["Chantier Villa Pereire : terrasse bois 45 m2, même secteur."]}
    r = await espace2["prechiffrage_node"](etat)
    reponse = r.get("final_response") or ""
    verifier("l'analyse du plan atteint la réponse", "40 m2" in reponse)
    verifier("les postes extraits atteignent la réponse, en clair",
             "dépose terrasse" in reponse and "terrassement" in reponse)
    verifier("la clé technique du JSON ne s'affiche plus",
             "postes_travaux" not in reponse and "surfaces_m2" not in reponse)
    verifier("les incertitudes sont dites, pas gommées", "non lisible" in reponse)
    verifier("la lecture d'un plan ne demande AUCUNE validation humaine",
             r.get("requires_validation") is False)
    # UN DOSSIER DE PLANS TIENT RAREMENT SUR UNE FEUILLE. La vision ne recevait
    # que la page 1 et répondait comme si elle avait tout vu.
    # Le contrôle vise l'APPEL, pas la mention : le commentaire du module cite
    # `load_page(0)` pour dire ce qui a été corrigé, et un contrôle qui trébuche
    # là-dessus interdirait d'expliquer ses propres correctifs.
    code2 = "\n".join(l for l in src2.splitlines() if not l.lstrip().startswith("#"))
    verifier("plusieurs pages d'un PDF sont rendues, pas seulement la première",
             "MAX_PAGES_PDF" in code2 and "doc.load_page(numero)" in code2
             and "doc.load_page(0)" not in code2)
    verifier("les pages retenues partent TOUTES au modèle de vision",
             '"attachment_pages"' in src2 and "for page in pages" in src2)
    verifier("le modèle sait combien de pages il voit, et combien il ne voit pas",
             "pages_ignorees" in src2 and "n'ont PAS été analysées" in src2)
    verifier("une page illisible n'interrompt pas l'analyse des autres",
             "Page de PDF illisible, ignorée" in src2)
    verifier("les pages du tour précédent ne débordent pas sur le suivant",
             '"attachment_pages": None' in (racine / "agents" / "runtime.py").read_text(
                 encoding="utf-8"))
    espace_vision = {"logger": types.SimpleNamespace(info=lambda *a, **k: None,
                                                     warning=lambda *a, **k: None)}
    extraire("agents/agent2.py", {"VISION_PROMPT", "MAX_PAGES_PDF"}, espace_vision)
    verifier("la borne de pages est un nombre tenable pour un dossier de plans",
             2 <= espace_vision["MAX_PAGES_PDF"] <= 10, espace_vision["MAX_PAGES_PDF"])

    # ═══════════════════════════════════════════════════════════════════
    titre(7, "« À partir de cette photo de terrain, génère une simulation "
             "AVANT / APRÈS avec terrasse bois et massif de graminées. »")
    cle_photo = _deposer(b"photo-du-terrain", "image/jpeg")
    r = await visuels.modifier_visuel(
        {"image": cle_photo,
         "changements": "replace the lawn with an ipe wood deck; add a bed of ornamental grasses"},
        User())
    verifier("la retouche part de l'image ELLE-MÊME, pas d'une description",
             APPELS_IMAGE and APPELS_IMAGE[-1]["entrees"] == 1, APPELS_IMAGE[-1:])
    verifier("le préréglage de fidélité énumère ce qui ne doit pas bouger",
             "roof" in APPELS_IMAGE[-1]["prompt"].lower()
             and "camera" in APPELS_IMAGE[-1]["prompt"].lower())
    bloc = r.get("bloc_ui") or {}
    verifier("un bloc d'écran « visuel » est rendu", bloc.get("type") == "visuel")
    images = bloc.get("images") or []
    verifier("le bloc porte l'AVANT et l'APRÈS (la question dit « avant/après »)",
             len(images) == 2 and any(cle_photo == i.get("cle") for i in images),
             f"{len(images)} image(s) : seul l'APRÈS est montré, la photo d'origine "
             f"n'entre pas dans la planche")
    verifier("chaque image porte sa légende", all(i.get("legende") for i in images),
             images)
    verifier("le résultat dit que c'est une illustration, pas une simulation",
             "illustration" in (r.get("message_final") or "").lower())
    decl = visuels.SKILLS["modifier_visuel"]
    verifier("la retouche exige un accord humain (effet externe)", decl.effet == "externe")
    verifier("elle est créditée à l'expert plans & visuels", decl.expert == "agent2")
    # La photo jointe part à la vision, qui n'appelle aucun geste — mais elle
    # rend maintenant la main. Encore faut-il que la RÉFÉRENCE de la photo
    # suive, sinon la retouche repart d'une génération neuve, donc d'un autre
    # jardin, au moment même où l'utilisateur montre le sien.
    espace5 = {"AgentState": dict}
    extraire("agents/agent1.py",
             {"cles_images_du_fil", "_CLE_IMAGE_RE", "_re_images", "_consigne_images"},
             espace5)
    etat_photo = {"attachment_visuel_cle": cle_photo, "messages": [], "tool_results": []}
    verifier("la photo tout juste envoyée est une image connue du fil",
             espace5["cles_images_du_fil"](etat_photo) == [cle_photo],
             espace5["cles_images_du_fil"](etat_photo))
    verifier("le modèle reçoit sa référence, prête pour `modifier_visuel`",
             cle_photo in espace5["_consigne_images"](etat_photo)
             and "modifier_visuel" in espace5["_consigne_images"](etat_photo))
    espace_route = {"AgentState": dict}
    extraire("agents/router.py", {"route_apres_agent2", "_SUITE_ATTENDUE"}, espace_route)
    verifier("« génère une simulation » réclame la suite : la vision rend la main",
             espace_route["route_apres_agent2"](
                 {"vision_analysis": "un jardin",
                  "query": "génère-moi une simulation avant/après avec une "
                           "terrasse bois et des graminées"}) == "agent1")
    # L'ACCORD RESTE, ET C'EST VOULU : le tirage est facturé, et un rendu montré
    # à un client ne doit pas partir tout seul. Ce qui change, c'est qu'on voit
    # ce qu'on approuve — sans quoi le clic finit par être donné sans lire.
    espace_apercu = {"logger": types.SimpleNamespace(info=lambda *a, **k: None)}
    extraire("agents/agent1.py", {"_apercu_avant_accord"}, espace_apercu)
    apercu = espace_apercu["_apercu_avant_accord"](
        "modifier_visuel", {"image": cle_photo,
                            "changements": "replace the lawn with an ipe wood deck"},
        "Je prépare la variante.")
    verifier("la carte d'accord MONTRE la photo qui va être retouchée",
             cle_photo in apercu and '"type": "visuel"' in apercu, apercu)
    verifier("elle dit ce qui change, et ce qui ne change pas",
             "ipe wood deck" in apercu and "conservé à l'identique" in apercu)
    apercu_plan = espace_apercu["_apercu_avant_accord"](
        "proposer_plan", {"etapes": ["une", "deux"]}, "")
    verifier("la carte d'accord d'un plan montre ses étapes",
             '"type": "plan"' in apercu_plan, apercu_plan)
    verifier("une action ordinaire garde son brouillon tel quel",
             espace_apercu["_apercu_avant_accord"]("envoi_devis", {}, "texte") == "")
    verifier("un aperçu impossible à construire n'empêche pas la validation",
             espace_apercu["_apercu_avant_accord"]("proposer_plan", None, "t") == "")

    # ═══════════════════════════════════════════════════════════════════
    titre(8, "« Trouve-moi 3 chantiers similaires (bassin d'Arcachon, terrain en "
             "pente, terrasse bois) et montre-moi les photos. »")
    r = await documents.rechercher_documents(
        {"requete": "chantier terrain en pente terrasse bois bassin d'Arcachon"}, User())
    verifier("la recherche par RESSEMBLANCE rend des chantiers", (r.get("nombre") or 0) >= 3)
    verifier("chaque résultat nomme son fichier source",
             all(x.get("source") for x in r.get("resultats") or []))
    verifier("aucune image n'est promise à l'écran par ce geste",
             not any("image" in json.dumps(x, ensure_ascii=False).lower()
                     for x in r.get("resultats") or []))
    r = await documents.rechercher_documents({"requete": "zzz introuvable"}, User())
    # LE CONTRÔLE A SUIVI LE CHAMP. La consigne « ne dis pas que la mémoire est
    # vide » s'adresse au MODÈLE : elle vit dans `a_faire` depuis qu'on a vu
    # cette phrase s'afficher telle quelle à l'écran (question 8, 27/08). Ce
    # que la personne lit, c'est le constat et l'inventaire.
    verifier("une recherche vide ne conclut PAS que la mémoire est vide",
             "Aucun document ne correspond" in (r.get("message") or "")
             and "ne dis pas que la mémoire est vide" in (r.get("a_faire") or "").lower(),
             f"message={r.get('message')!r} a_faire={r.get('a_faire')!r}")
    verifier("ce que la personne lit ne contient aucune consigne au modèle",
             "Ne dis" not in (r.get("message") or ""))
    verifier("elle dit ce que la mémoire contient VRAIMENT",
             "42 chantier" in (r.get("inventaire_memoire") or ""), r.get("inventaire_memoire"))
    # ── « MONTRE-MOI LES PHOTOS » ──────────────────────────────────────────
    # Le module Drive est chargé POUR DE VRAI (résolution du dossier, filtrage
    # des images, bornes, dépôt) ; seul l'accès au service Google est doublé.
    drive = charger("outils.drive", "outils/drive.py")
    drive._service = _service_drive
    drive._racines = lambda service: _rien()
    drive._resoudre = lambda service, chemin, racines, perimetres=None: _dossier(chemin)
    drive.perimetres_visibles = lambda role: [("racine-autorisee", "all")]
    outils = charger("skills.outils", "skills/outils.py")
    r = await outils.drive_photos({"dossier": "Villa Pereire", "limite": 3}, User())
    verifier("les photos d'un dossier du Drive reviennent, et sont déposées",
             (r.get("nombre") or 0) == 3 and all(i["cle"] in DEPOT
                                                 for i in r["bloc_ui"]["images"]), r)
    verifier("elles s'affichent dans une planche prête à insérer",
             (r.get("bloc_ui") or {}).get("type") == "visuel", r.get("bloc_ui"))
    verifier("chaque photo garde son nom de fichier en légende",
             all(i.get("legende", "").endswith((".jpg", ".png"))
                 for i in r["bloc_ui"]["images"]), r["bloc_ui"]["images"])
    verifier("la limite demandée est respectée, et le total réel est dit",
             r.get("disponibles", 0) > r["nombre"]
             and str(r["disponibles"]) in (r.get("message_final") or ""),
             r.get("message_final"))
    verifier("la consigne interdit de les faire passer pour un rendu généré",
             "jamais un rendu" in (r.get("a_faire") or "").lower()
             or "pas des images générées" in (r.get("a_faire") or ""))
    # Sans borne serrée, la photo de drone de 40 Mo est rencontrée : elle doit
    # être écartée ET dite. Une image absente sans explication se lit comme une
    # image qui n'existe pas.
    r_tout = await outils.drive_photos({"dossier": "Villa Pereire"}, User())
    verifier("une photo trop lourde est écartée et signalée, pas ignorée",
             (r_tout.get("trop_volumineuses") or 0) >= 1
             and "volumineuse" in (r_tout.get("message_final") or ""), r_tout)
    verifier("un PDF du même dossier n'est pas pris pour une photo",
             all(not i["legende"].endswith(".pdf")
                 for i in r_tout["bloc_ui"]["images"]), r_tout["bloc_ui"]["images"])
    r_vide = await outils.drive_photos({"dossier": "Dossier sans image"}, User())
    verifier("un dossier sans image le dit, sans conclure qu'il n'y en a nulle part",
             (r_vide.get("nombre") or 0) == 0
             and "pas une preuve" in (r_vide.get("message") or ""), r_vide)
    verifier("le geste est une simple LECTURE, sans accord à demander",
             outils.SKILLS["drive_photos"].effet == "lecture")

    # ═══════════════════════════════════════════════════════════════════
    titre(9, "« Sur la base de ce plan, prépare une trame de pré-devis avec les "
             "postes et les quantités. »")
    r = await espace2["prechiffrage_node"](etat)
    reponse = r.get("final_response") or ""
    verifier("la trame porte les postes du plan", "terrassement" in reponse)
    verifier("la trame porte les surfaces relevées", "40" in reponse)
    verifier("la réserve humaine est écrite, sans qu'on ait à la demander",
             "valider par un humain" in reponse)
    verifier("le texte dit que rien n'est engagé", "Rien n'a été envoyé ni engagé" in reponse)
    verifier("les chantiers comparables trouvés atteignent la réponse",
             "Villa Pereire" in reponse,
             "`similar_projects_node` fait la recherche et remplit `raw_chunks` — "
             "que `prechiffrage_node` ne lit jamais : le travail est fait puis jeté")
    # ── LES PRIX : ceux de la maison, jamais ceux du marché ────────────────
    r = await routines.prix_observes({"poste": "terrasse bois"}, User())
    verifier("le relevé des prix déjà pratiqués existe et trouve les affaires",
             r.get("trouve") and (r.get("observations") or 0) >= 3, r)
    verifier("il rend une FOURCHETTE et une médiane, pas un prix unique",
             all(r.get(k) for k in ("minimum", "median", "maximum")), r)
    verifier("il dit sur combien d'affaires il s'appuie",
             "affaire" in (r.get("message_final") or "")
             and str(r.get("observations")) in (r.get("message_final") or ""),
             r.get("message_final"))
    verifier("il nomme les fichiers d'où sortent les chiffres",
             bool(r.get("sources")), r.get("sources"))
    verifier("il donne la période couverte, pour qu'un prix de 2019 se voie",
             bool(r.get("periode")), r.get("periode"))
    verifier("les exemples cités sont les plus RÉCENTS d'abord",
             [_lecture.cle_triable(e["date"]) for e in r["exemples"]]
             == sorted((_lecture.cle_triable(e["date"]) for e in r["exemples"]),
                       reverse=True), [e["date"] for e in r["exemples"]])
    verifier("la consigne interdit d'en déduire un prix unique ou un prix au m²",
             "JAMAIS un prix unique" in (r.get("a_faire") or "")
             and "revient à un humain" in (r.get("a_faire") or ""))
    # Le piège déjà payé une fois : le poste cité dans un commentaire.
    verifier("un montant n'entre dans le relevé que si le poste est dans une "
             "colonne qui le DÉCRIT",
             all("terrasse" in _plat_test(e["designation"]) for e in r["exemples"]),
             [e["designation"] for e in r["exemples"]])
    # Et quand on n'a pas assez d'affaires : aucun chiffre, et on le dit.
    r_vide = await routines.prix_observes({"poste": "piscine à débordement"}, User())
    verifier("sans assez d'affaires, AUCUN chiffre n'est avancé",
             r_vide.get("trouve") is False
             and not any(k in r_vide for k in ("minimum", "median", "maximum")),
             r_vide)
    verifier("et la consigne interdit d'aller chercher un prix de marché",
             "ni un prix de marché" in (r_vide.get("a_faire") or ""),
             r_vide.get("a_faire"))
    verifier("un poste trop court est refusé plutôt que de ramener n'importe quoi",
             await _leve(routines.prix_observes({"poste": "bo"}, User())))

    # ═══════════════════════════════════════════════════════════════════
    titre(10, "« Le client m'envoie ce plan et demande un chiffrage : analyse le "
              "plan, retrouve son historique et prépare un pré-devis + un mail. »")
    _palier = types.SimpleNamespace(value="complex")
    espace3 = {"AgentState": dict, "LLMTier": types.SimpleNamespace(COMPLEX=_palier),
               "classify_request_tier": lambda q, a: _palier}
    extraire("agents/router.py", {"classify_node"}, espace3)
    r = await espace3["classify_node"]({"query": "analyse ce plan et fais le devis",
                                        "has_attachment": True, "attachment_text": None})
    verifier("un plan joint part bien à l'expert plans & visuels",
             r.get("target_agent") == "agent2", r)
    r = await espace3["classify_node"]({"query": "sors-moi la liste des clients",
                                        "has_attachment": False})
    verifier("une question sans pièce jointe reste à l'assistant",
             r.get("target_agent") == "agent1", r)
    src_router = (racine / "agents" / "router.py").read_text(encoding="utf-8")
    verifier("après l'analyse du plan, la main revient à l'assistant "
             "(historique client, pré-devis, mail)",
             'route_apres_agent2' in src_router
             and '"agent1": "passer_la_main"' in src_router,
             "le graphe va de `agent2` à `human_gate` puis à la FIN")
    # La passe de main se décide sur ce que la demande RÉCLAME, pas sur l'image.
    espace4 = {"AgentState": dict}
    extraire("agents/router.py",
             {"route_apres_agent2", "_SUITE_ATTENDUE", "passer_la_main_node",
              "route_apres_execution"}, espace4)
    vu = {"vision_analysis": "Terrasse 40 m2, dénivelé 1,20 m."}
    for demande, attendu in (
            ("analyse ce plan, retrouve son historique et prépare un pré-devis "
             "et un mail de réponse", "agent1"),
            ("fais-moi le chiffrage de ce plan", "agent1"),
            # Le scénario n°1 : la retouche se fait dans le MÊME tour (31/08).
            ("ajoute une pergola à droite", "agent1"),
            ("remplace la pelouse par une terrasse en bois", "agent1"),
            ("projette le rendu final avec des graminées", "agent1"),
            ("c'est quoi cette plante ?", "human_gate"),
            ("décris-moi ce plan", "human_gate")):
        verifier(f"« {demande[:42]}… » → {attendu}",
                 espace4["route_apres_agent2"](dict(vu, query=demande)) == attendu,
                 espace4["route_apres_agent2"](dict(vu, query=demande)))
    verifier("une analyse ratée ne part pas dans le vide",
             espace4["route_apres_agent2"]({"query": "fais le devis"}) == "human_gate")
    r = await espace4["passer_la_main_node"](
        dict(vu, attachment_b64="xxx", attachment_name="plan-pereire.pdf",
             final_response="analyse"))
    verifier("l'analyse est transmise à l'assistant comme un document du contexte",
             "Terrasse 40 m2" in (r.get("attachment_text") or ""), r)
    verifier("l'image n'est PAS repassée (pas de second appel de vision)",
             r.get("attachment_b64") is None)
    verifier("la réponse de la vision s'efface : une seule réponse en fin de tour",
             r.get("final_response") is None and r.get("llm_response") is None)
    verifier("le tour reste crédité à l'expert qui a lu le plan",
             "target_agent" not in r, r.get("target_agent"))
    # Le plan validé : c'est lui qui rouvre le travail après l'accord.
    verifier("un plan approuvé renvoie le tour dans l'assistant",
             espace4["route_apres_execution"]({"plan_valide": ["a", "b"]}) == "agent1")
    verifier("toute autre action validée termine le tour",
             espace4["route_apres_execution"]({}) == "fin")
    plan = charger("skills.plan", "skills/plan.py")
    decl = plan.SKILLS["proposer_plan"]
    verifier("le plan passe par un accord humain", decl.effet == "externe")
    r = await plan.proposer_plan(
        {"titre": "Chiffrage Villa Pereire",
         "etapes": ["Analyser le plan", "Retrouver l'historique du client",
                    "Préparer le pré-devis", "Rédiger le mail de réponse"]}, User())
    verifier("le plan rend un bloc d'écran de type `plan`",
             (r.get("bloc_ui") or {}).get("type") == "plan", r.get("bloc_ui"))
    verifier("les quatre étapes y sont, aucune cochée d'avance",
             len(r["bloc_ui"]["etapes"]) == 4
             and all(e["etat"] == "a_faire" for e in r["bloc_ui"]["etapes"]),
             r["bloc_ui"]["etapes"])
    verifier("la consigne interdit de redemander l'accord et impose UNE réponse",
             "SANS redemander l'accord" in (r.get("a_faire") or "")
             and "Une seule réponse" in (r.get("a_faire") or ""))
    # Le modèle écrit les étapes de dix façons : les trois doivent passer.
    for forme in (["une", "deux"], [{"titre": "une"}, {"titre": "deux"}],
                  "- une\n- deux"):
        b = plan.bloc_du_plan({"etapes": forme})
        verifier(f"étapes écrites en {type(forme).__name__} : comprises",
                 [e["titre"] for e in b["etapes"]] == ["une", "deux"], b)
    try:
        await plan.proposer_plan({"etapes": ["une seule chose"]}, User())
        seul = False
    except Exception:  # noqa: BLE001
        seul = True
    verifier("un « plan » d'une seule étape est refusé (c'est l'action elle-même)",
             seul)
    src_agent1 = (racine / "agents" / "agent1.py").read_text(encoding="utf-8")
    verifier("le plan est MONTRÉ avant l'accord, construit sans repasser par le modèle",
             'action["skill"] == "proposer_plan"' in src_agent1
             and "bloc_du_plan" in src_agent1)
    verifier("un plan déjà validé ne peut pas être replanifié",
             'state.get("plan_valide")' in src_agent1)
    verifier("le plan approuvé est remis sous les yeux du modèle à la reprise",
             "_consigne_plan" in src_agent1
             and src_agent1.count("_consigne_plan(state)") == 2)
    verifier("le plan ne survit pas au tour suivant",
             '"plan_valide": None' in (racine / "agents" / "runtime.py").read_text(
                 encoding="utf-8"))
    # LE GRAPHE NE SE COMPILE PAS ICI (LangGraph n'est pas installé sur ce
    # poste) : une arête vers un nœud qui n'existe pas ne se verrait qu'au
    # démarrage du backend, en production. On vérifie donc à la main que tout
    # ce qui est cité existe — c'est peu, mais c'est l'erreur qui coûte cher.
    import re as _re
    corps = src_router[src_router.index("async def build_main_graph"):]
    noeuds = set(_re.findall(r'add_node\(\s*"([a-z_0-9]+)"', corps)) | {"END"}
    cites = set()
    for appel in _re.findall(r'add_edge\(\s*"([a-z_0-9]+)"\s*,\s*"?([A-Za-z_0-9]+)"?',
                             corps):
        cites |= set(appel)
    for bloc in _re.findall(r'add_conditional_edges\((.*?)\)\n', corps, _re.S):
        cites |= set(_re.findall(r'"([a-z_0-9]+)"\s*:\s*"([a-z_0-9]+)"', bloc) and
                     [c for paire in _re.findall(
                         r'"([a-z_0-9]+)"\s*:\s*"([a-z_0-9]+)"', bloc) for c in paire[1:]])
        cites.add(_re.match(r'\s*"([a-z_0-9]+)"', bloc).group(1)
                  if _re.match(r'\s*"([a-z_0-9]+)"', bloc) else "END")
    inconnus = sorted(c for c in cites if c not in noeuds and c != "fin")
    verifier("toutes les arêtes du graphe pointent vers un nœud qui existe",
             not inconnus, f"nœuds cités mais jamais déclarés : {inconnus}")

    # ═══════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 72}")
    for l in limites:
        print(f"  · {l}")
    print(f"\n═══ {len(echecs)} contrôle(s) en échec, {len(limites)} limite(s) connue(s)")
    for e in echecs:
        print(f"    ✗ {e}")
    return 1 if echecs else 0


sys.exit(asyncio.run(principal()))
