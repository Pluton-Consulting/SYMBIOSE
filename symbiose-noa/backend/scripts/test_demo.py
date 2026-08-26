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
CHANTIERS = [
    {"Chantier": "Villa Pereire", "Client": "SCI Les Tilleuls", "Date": "05/09/2025",
     "Prestation": "Création terrasse bois et allée", "Montant HT": "18 400,00 €"},
    {"Chantier": "Le Moulleau", "Client": "MARTIN Claire", "Date": "14/02/2026",
     "Prestation": "Terrasse bois exotique + massif de graminées", "Montant HT": "9 250,00 €"},
    {"Chantier": "Résidence du Port", "Client": "Mairie de La Teste", "Date": "20/06/2024",
     "Prestation": "Engazonnement et arrosage", "Montant HT": "31 000,00 €"},
    {"Chantier": "Cap Ferret", "Client": "MARTIN Claire", "Date": "03/07/2026",
     "Prestation": "Terrasse en bois et pergola", "Montant HT": "11 900,00 €"},
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
        if "WITH base AS" in sql:                         # _agreger
            return self._agreger(sql, *args)
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


_module("vectorstore.rag", retrieve=_retrieve, retrieve_as_context=_retrieve_as_context)
_module("optim.tokens", trim_chunks=lambda c: c)


async def _boites_par_id(uid): return ["contact@symbiose-paysage.fr"]


# ═══════════════════════════════════════════════════════════════════════
#  Chargement des modules RÉELS
# ═══════════════════════════════════════════════════════════════════════
import importlib.util  # noqa: E402


def charger(nom, chemin):
    spec = importlib.util.spec_from_file_location(nom, racine / chemin)
    module = importlib.util.module_from_spec(spec)
    sys.modules[nom] = module
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
    verifier("l'égalité stricte ne trouve rien, et le dit sans se tromper de mot",
             (r.get("nombre") or 0) == 0 and "contient" in (r.get("message") or ""),
             r.get("message"))
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "contient": {"Prestation": "terrasse"}}, User())
    verifier("une recherche PARTIELLE retrouve les chantiers « terrasse bois »",
             (r.get("nombre") or 0) == 3,
             f"{r.get('nombre')} trouvé(s) sur 3 attendus")
    # La question complète, en UN appel : le compte ET la moyenne, sur 12 mois.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "contient": {"Prestation": "terrasse"},
         "agreger": {"operation": "moyenne", "colonne": "Montant HT"},
         "depuis": "12m"}, User())
    verifier("une période GLISSANTE (12 derniers mois) est comprise",
             bool(r.get("periode")), r.get("erreur") or r)
    verifier("le chantier plus vieux que la période est écarté",
             r.get("enregistrements") == 3, r)
    verifier("le compte ET la moyenne sortent du même appel",
             r.get("operation") == "avg" and round(r.get("resultat") or 0) == 13183, r)
    verifier("la note cite la période retenue, pour qu'aucun chiffre ne circule nu",
             "Période retenue" in (r.get("note") or ""), r.get("note"))
    verifier("la note dit combien de valeurs étaient lisibles",
             "lisibles" in (r.get("note") or ""))
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "depuis": "l'année dernière"}, User())
    verifier("une période écrite en toutes lettres est comprise aussi",
             bool(r.get("periode")), r.get("erreur") or r)
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "depuis": "n'importe quoi"}, User())
    verifier("une période illisible est REFUSÉE, jamais ignorée en silence",
             bool(r.get("erreur")), r)
    # La formulation de repli : par ANNÉE. Un seul appel rend le compte ET la
    # moyenne — c'est exactement ce que la question demande, à la période près.
    r = await donnees.interroger_donnees(
        {"source_type": "chantiers", "annee": "2026",
         "agreger": {"operation": "moyenne", "colonne": "Montant HT"}}, User())
    verifier("par ANNÉE, le compte et la moyenne sortent en un seul appel",
             r.get("enregistrements") == 2 and round(r.get("resultat") or 0) == 10575,
             r)
    # Et si le modèle veut seulement COMPTER l'année, sans rien moyenner :
    r = await donnees.interroger_donnees({"source_type": "chantiers", "annee": "2026"}, User())
    verifier("compter une année sans rien agréger est possible",
             (r.get("enregistrements") or r.get("nombre") or 0) == 2,
             r.get("erreur") or r)
    signaler("une période glissante se compte en MOIS ENTIERS (« 12 derniers mois » "
             "au 26/08 part du 1er août de l'an dernier) et ne retient que les dates "
             "écrites AAAA-MM-JJ ou JJ/MM/AAAA. Un export qui daterait autrement "
             "(« 5 sept. 25 ») sort de la période : interroger alors par `annee`.")

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
    catalogue = protocol_src + "".join(
        str(getattr(d, "description", "")) for d in
        list(getattr(routines, "SKILLS", {}).values())
        + list(getattr(visuels, "SKILLS", {}).values()))
    verifier("un geste sait rendre les dossiers SANS RÉPONSE depuis N jours",
             any(m in catalogue.lower() for m in
                 ("sans reponse depuis", "sans réponse depuis", "en attente depuis",
                  "relances a faire", "relances à faire")),
             "aucun geste du catalogue ne croise un statut et une ancienneté ; "
             "`relance_devis` est un TYPE DE MAIL, pas un suivi")
    # Ce que l'on peut faire aujourd'hui, à défaut : compter par statut.
    r = await donnees.interroger_donnees(
        {"source_type": "devis", "filtres": {"Statut": "envoyé"}}, User())
    verifier("à défaut, compter les devis « envoyé » fonctionne",
             (r.get("nombre") or 0) == 1, r.get("nombre"))
    signaler("« depuis plus de 15 jours » n'est calculable par aucun geste : les "
             "dates sont du TEXTE dans les fichiers importés, et rien ne les "
             "compare à aujourd'hui. La question rendra, au mieux, la liste des "
             "devis en attente SANS le filtre d'ancienneté.")

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
               "logger": types.SimpleNamespace(info=lambda *a, **k: None)}
    extraire("agents/agent2.py", {"prechiffrage_node"}, espace2)
    etat = {"vision_analysis": "Terrasse existante 40 m2, dénivelé 1,20 m, accès étroit.",
            "extracted_data": {"surfaces_m2": {"terrasse": 40},
                               "postes_travaux": ["dépose terrasse", "terrassement"],
                               "incertitudes": ["cote du muret non lisible"]},
            "raw_chunks": ["Chantier Villa Pereire : terrasse bois 45 m2, même secteur."]}
    r = await espace2["prechiffrage_node"](etat)
    reponse = r.get("final_response") or ""
    verifier("l'analyse du plan atteint la réponse", "40 m2" in reponse)
    verifier("les postes extraits atteignent la réponse", "postes_travaux" in reponse)
    verifier("les incertitudes sont dites, pas gommées", "non lisible" in reponse)
    verifier("la lecture d'un plan ne demande AUCUNE validation humaine",
             r.get("requires_validation") is False)
    signaler("un PDF de plusieurs pages n'est lu QUE sur sa première page "
             "(`load_page(0)` dans agent2) : pour un dossier de plans, joindre "
             "les pages une par une.")

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
    signaler("une photo jointe part TOUJOURS à l'agent vision, qui n'appelle aucun "
             "geste : la simulation demande DEUX messages — joindre la photo, puis "
             "« ajoute une terrasse bois et des graminées ». En un seul message, "
             "la réponse est une analyse et une proposition, pas une image.")

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
    verifier("une recherche vide ne conclut PAS que la mémoire est vide",
             "Aucun document ne correspond à CETTE recherche" in (r.get("message") or "")
             and "Ne dis donc PAS qu'elle est vide" in (r.get("message") or ""),
             r.get("message"))
    verifier("elle dit ce que la mémoire contient VRAIMENT",
             "42 chantier" in (r.get("inventaire_memoire") or ""), r.get("inventaire_memoire"))
    signaler("« montre-moi les photos » ne peut pas être tenue : `rechercher_documents` "
             "rend du TEXTE. Les photos d'un chantier ne s'affichent que par le Drive "
             "(`drive_apercu` / `drive_ouvrir`), et aucun bloc d'écran ne montre une "
             "image du Drive dans le chat.")

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
    signaler("aucun PRIX n'est proposé : la trame liste des postes et des surfaces. "
             "Le chiffrage reste à faire à la main (ce que la question demande, "
             "mais un dirigeant peut attendre des montants).")

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
    verifier("après l'analyse du plan, la main peut revenir à l'assistant "
             "(historique client, pré-devis, mail)",
             'add_edge("agent2", "agent1")' in src_router
             or '"agent2", route_apres_agent2' in src_router,
             "le graphe va de `agent2` à `human_gate` puis à la FIN : l'expert "
             "vision n'appelle aucun geste et ne rend jamais la main")
    signaler("LA question de démonstration ne tient pas en UN message : le plan "
             "joint est analysé par l'expert vision, qui ne sait ni lire la fiche "
             "du client, ni produire un document, ni rédiger un mail. Il faut la "
             "jouer en trois temps : (1) joindre le plan, (2) « fais la fiche de "
             "ce client », (3) « prépare le mail de réponse ».")

    # ═══════════════════════════════════════════════════════════════════
    print(f"\n{'═' * 72}")
    for l in limites:
        print(f"  · {l}")
    print(f"\n═══ {len(echecs)} contrôle(s) en échec, {len(limites)} limite(s) connue(s)")
    for e in echecs:
        print(f"    ✗ {e}")
    return 1 if echecs else 0


sys.exit(asyncio.run(principal()))
