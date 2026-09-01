"""
Banc « chacun voit le Drive avec SON compte » — 01/09.

Noa : « là c'est l'entreprise Symbiose Paysage, donc le Google Symbiose
Paysage. Chacun a juste à se connecter avec son compte et ça autorise pour le
Drive […] mais que les accès soient restreints à la personne qui est connectée.
Sauf super admin, où c'est connecté avec Benjamin Durou, ça ne bouge pas. Mais
les autres, même celui de Benjamin Durou, devront se reconnecter. »

LE RISQUE DU CHANTIER, et ce que ce banc protège avant tout : `outils/drive.py`
gardait son client Drive dans un cache GLOBAL de trente minutes. Brancher
l'identité sans toucher au cache aurait servi, pendant une demi-heure, le Drive
de la PREMIÈRE personne à toutes les suivantes. Le contrôle « deux identités,
deux clients » est le cœur de ce fichier ; il est EXÉCUTÉ, pas lu.

Le banc n'ouvre ni base ni réseau : le constructeur de client est doublé.
"""
import ast
import asyncio
import importlib.util
import pathlib
import re
import sys
import types

BACKEND = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "backend")
FRONTEND = BACKEND.resolve().parent / "frontend"
echecs = []


def verifier(nom, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {nom}" + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


print(f"\n═══ LE DRIVE, AU NOM DE CHACUN — {BACKEND.resolve().parent}\n")

# ── 1. LE CACHE PAR IDENTITÉ, exécuté ────────────────────────────────────
# On charge les seules définitions du cache : le module complet importerait
# googleapiclient, absent de ce Mac.
espace = {"asyncio": asyncio, "Optional": type(None)}
arbre = ast.parse((BACKEND / "outils" / "drive.py").read_text(encoding="utf-8"))
voulu = {"_CLIENTS", "_POOLS", "_DUREE_CLIENT_S", "_MAX_CLIENTS", "_POOL_TAILLE",
         "_cle_client", "_evincer", "_service", "_services", "DriveRefuse"}
gardes = []
for n in arbre.body:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.name in voulu:
        gardes.append(n)
    elif isinstance(n, (ast.Assign, ast.AnnAssign)):
        cibles = n.targets if isinstance(n, ast.Assign) else [n.target]
        if any(isinstance(c, ast.Name) and c.id in voulu for c in cibles):
            gardes.append(n)
exec(compile(ast.Module(body=gardes, type_ignores=[]), "drive", "exec"), espace)
manquants = voulu - set(espace)
verifier("le cache par identité existe dans le module livré", not manquants, str(manquants))

# Le constructeur est doublé : un objet distinct par identité demandée.
construits = []


async def _faux_build(identite=None, ecriture=False):
    construits.append((identite, ecriture))
    return f"client({identite or 'service'}{'-w' if ecriture else ''})#{len(construits)}"


espace["_build_service_pour"] = _faux_build

verifier("la clé de cache distingue le compte de service d'une personne",
         espace["_cle_client"](None) == "service"
         and espace["_cle_client"]("u1") == "perso:u1"
         and espace["_cle_client"]("") == "service")


async def _scenario_isolation():
    a1 = await espace["_service"]("alice")
    b1 = await espace["_service"]("bob")
    a2 = await espace["_service"]("alice")     # doit ressortir du cache
    s1 = await espace["_service"]()            # compte de service
    return a1, b1, a2, s1


a1, b1, a2, s1 = asyncio.run(_scenario_isolation())
verifier("DEUX PERSONNES, DEUX CLIENTS — jamais le Drive de quelqu'un d'autre",
         a1 != b1, f"{a1} vs {b1}")
verifier("la même personne réutilise SON client (le cache sert encore)",
         a1 == a2 and len(construits) == 3)
verifier("sans identité, c'est le compte de service, explicitement",
         s1 != a1 and s1 != b1 and construits[-1][0] is None)


async def _scenario_peremption():
    espace["_CLIENTS"].clear()
    avant = len(construits)
    await espace["_service"]("carl")
    espace["_CLIENTS"]["perso:carl"]["expire"] = 0.0     # périmé
    await espace["_service"]("carl")
    return len(construits) - avant


verifier("un client périmé se reconstruit, jamais ne se sert froid",
         asyncio.run(_scenario_peremption()) == 2)


async def _scenario_plafond():
    espace["_CLIENTS"].clear()
    for i in range(espace["_MAX_CLIENTS"] + 5):
        await espace["_service"](f"u{i}")
    return len(espace["_CLIENTS"])


verifier("le nombre de clients gardés est plafonné (pas 40 connexions vivantes)",
         asyncio.run(_scenario_plafond()) <= espace["_MAX_CLIENTS"])


async def _scenario_vivier():
    espace["_POOLS"].clear()
    a = await espace["_services"](3, "alice")
    b = await espace["_services"](3, "bob")
    return a, b


va, vb = asyncio.run(_scenario_vivier())
verifier("LE VIVIER AUSSI est par identité (c'est lui que `lire_lot` utilise)",
         not (set(va) & set(vb)) and len(va) == 3)
verifier("les clients d'un même vivier restent DISTINCTS entre eux "
         "(httplib2 n'est pas sûr entre threads)", len(set(va)) == 3)

# ── 2. Le choix personnel / compte de service ────────────────────────────
drv = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
verifier("la connexion PERSONNELLE est essayée d'abord",
         re.search(r"if identite:.*?credentials_pour_utilisateur", drv, re.S))
def _avant(texte, x, y):
    """« x » apparaît-il avant « y » ? Faux si l'un des deux manque."""
    ix, iy = texte.find(x), texte.find(y)
    return ix >= 0 and iy >= 0 and ix < iy


verifier("sans compte relié, on REFUSE en disant où le relier — jamais un "
         "repli silencieux sur le Drive de quelqu'un d'autre",
         "Mon compte Google" in drv and "raise DriveRefuse(" in drv)
# TROIS VOIES, dans cet ordre. La délégation de domaine donne le MÊME résultat
# que le consentement individuel — chacun voit SON Drive — mais sans que
# personne ait à cliquer. Elle n'existe que si l'entreprise administre son
# domaine ; quand elle manque, ce n'est pas une panne, c'est l'autre voie qui
# reste, puis le refus.
verifier("voie 2 : la délégation de domaine emprunte l'identité de la personne",
         "_build_service_delegue" in drv
         # L'ORDRE DES APPELS, pas celui des imports : le bloc d'import cite
         # les deux constructeurs bien avant qu'ils servent.
         and _avant(drv, "credentials_pour_utilisateur(str(identite))",
                    "_build_service_delegue, courriel"))
verifier("son absence n'est pas une panne : on continue vers le refus",
         "Délégation de domaine indisponible" in drv)
verifier("le refus nomme LES DEUX chemins (relier son compte, ou déléguer)",
         "délégation de domaine" in drv.split("raise DriveRefuse")[1][:600])
verifier("l'adresse empruntée est lue DANS LA BASE, jamais reçue en paramètre",
         "_courriel_du_compte" in drv
         and "SELECT email FROM users WHERE id = $1::uuid" in drv)
_gd = (BACKEND / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
verifier("la délégation dit que son pouvoir est ENTIER (emprunter n'importe qui)",
         "CE POUVOIR EST ENTIER" in _gd and "with_subject(adresse)" in _gd)
verifier("le commentaire interdit d'« harmoniser » le chemin du compte de "
         "service (acces_docs en dépend)",
         "acces_docs" in drv and "NE PAS « harmoniser »" in drv)
verifier("aucun cache global ne subsiste",
         "_CLIENT[" not in drv and "_POOL[" not in drv)

gd = (BACKEND / "ingestion" / "connectors" / "google_drive.py").read_text(encoding="utf-8")
verifier("le constructeur personnel existe et rafraîchit le jeton SUR PLACE",
         "_build_service_perso" in gd
         and "credentials.refresh(Request())" in gd)
verifier("un consentement révoqué se dit dans les mots de la personne",
         "n'est plus relié à l'assistant" in gd)
verifier("les trois voies du compte de service sont intactes",
         "_build_service_ecriture" in gd and "_SCOPES_ECRITURE" in gd)

# ── 3. La règle de Noa : super_admin garde le compte de service ──────────
outils = (BACKEND / "skills" / "outils.py").read_text(encoding="utf-8")
espace2 = {}
exec(compile(ast.Module(body=[n for n in ast.parse(outils).body
                              if isinstance(n, ast.FunctionDef) and n.name == "_identite"],
                        type_ignores=[]), "outils", "exec"), espace2)
_identite = espace2["_identite"]


class _U:
    def __init__(self, role, ident):
        self.role, self.id = role, ident


verifier("un super-admin garde le compte de service (décision de Noa)",
         _identite(_U("super_admin", "abc")) == "")
verifier("la direction, elle, voit avec SON compte",
         _identite(_U("direction", "abc")) == "abc")
verifier("un collaborateur aussi", _identite(_U("collaborateur", "xyz")) == "xyz")
# Le corps de LA fonction, découpé par l'AST : un `split` textuel avalait la
# fonction suivante (qui, elle, lit bien `data` — c'est son rôle).
_n = next(n for n in ast.parse(outils).body
          if isinstance(n, ast.FunctionDef) and n.name == "_identite")
_corps_identite = ast.dump(_n)
verifier("l'identité vient de la SESSION (l'objet `user`), jamais du modèle",
         "'data'" not in _corps_identite
         and "'getattr'" in _corps_identite and "'user'" in _corps_identite)
verifier("les huit gestes Drive portent l'identité",
         outils.count("identite=_identite(user)") == 8)
verifier("les périmètres passent en NOMMÉ partout (un ajout ne décale plus rien)",
         "_drive(deposer, dossier, nom, contenu,\n                        perimetres="
         in outils)
verifier("le propriétaire du brouillon n'est PAS confondu avec l'identité Google",
         "_proprietaire(user)" in outils and "deux notions distinctes" in outils)
verifier("LES DEUX FILTRES SE COMPOSENT, et le docstring le dit",
         "LES DEUX FILTRES SE COMPOSENT" in outils)
verifier("joindre un fichier du Drive à un mail suit la MÊME identité",
         "identite=_identite(user)" in
         (BACKEND / "mail" / "attaches.py").read_text(encoding="utf-8"))

# ── 4. Le module de connexion ────────────────────────────────────────────
gp = (BACKEND / "mail" / "google_perso.py").read_text(encoding="utf-8")
verifier("le scope demandé est `drive` COMPLET (le dépôt écrit dans un dossier "
         "existant)", '"https://www.googleapis.com/auth/drive",' in gp)
verifier("aucun scope Gmail n'est réclamé : Symbiose est sur Microsoft 365",
         "gmail." not in gp)
verifier("le cache porte DEUX index — par boîte et par personne",
         "_PAR_USER" in gp and "_CACHE" in gp)
verifier("les deux index sont remplis en une passe, depuis la même requête",
         "SELECT user_id, email, refresh_token" in gp)
verifier("`credentials_pour_utilisateur` rend None si le client OAuth manque",
         re.search(r"def credentials_pour_utilisateur.*?not configurable\(\).*?return None",
                   gp, re.S))
verifier("le jeton ne sort JAMAIS vers l'écran",
         "JAMAIS le jeton" in gp)
verifier("la condition des 7 jours (app externe en test) reste documentée",
         "SEPT JOURS" in gp)

routes = (BACKEND / "routers" / "google_perso.py").read_text(encoding="utf-8")
verifier("les routes sont portées", "router" in routes and "retour" in routes)
mig = BACKEND / "database" / "migrations" / "031_connexions_google.sql"
verifier("migration 031 : la table des connexions",
         mig.exists() and "connexions_google" in mig.read_text(encoding="utf-8"))
conf = (BACKEND / "config.py").read_text(encoding="utf-8")
verifier("le client OAuth « application Web » est un réglage distinct du "
         "client « bureau » du compte de service",
         "google_oauth_client_id" in conf and "google_credentials_file" in conf)
main = (BACKEND / "main.py").read_text(encoding="utf-8")
verifier("la route est montée sur /api/google",
         'prefix="/api/google"' in main)
verifier("le cache est rempli AU DÉMARRAGE (sinon tout le monde retombe sur "
         "le compte de service après chaque redéploiement)",
         "rafraichir_google" in main)

# ── 5. L'écran ───────────────────────────────────────────────────────────
sc = (FRONTEND / "app" / "(app)" / "parametres" / "SettingsClient.tsx").read_text(encoding="utf-8")
verifier("l'onglet existe et n'a AUCUN rôle (chacun y relie son compte)",
         '{ key: "google", label: "Mon compte Google" },' in sc)
verifier("il est le premier, donc l'onglet par défaut d'un collaborateur",
         sc.index('key: "google"') < sc.index('key: "utilisateurs"')
         and 'subTabs[0]?.key ?? "google"' in sc)
verifier("le composant est monté", "<GoogleTab" in sc and "import GoogleTab" in sc)
page = (FRONTEND / "app" / "(app)" / "parametres" / "page.tsx").read_text(encoding="utf-8")
verifier("la page ne renvoie plus un collaborateur vers l'accueil",
         '["super_admin", "direction"].includes' not in page and "if (!user)" in page)
perms = (FRONTEND / "lib" / "permissions.ts").read_text(encoding="utf-8")
verifier("Paramètres est atteignable — navigation ET panneau de l'engrenage",
         perms.count('href: "/parametres"') == 2
         and "MANAGERS" not in re.sub(r"\s+", " ", perms).split('"/parametres"')[1][:60]
         and "MANAGERS" not in re.sub(r"\s+", " ", perms).split('"/parametres"')[2][:60])
tab = (FRONTEND / "components" / "settings" / "GoogleTab.tsx").read_text(encoding="utf-8")
verifier("l'écran parle du COMPTE, pas de la boîte (Symbiose n'a pas Gmail)",
         "Mon compte Google" in tab and "Ma boîte Google" not in tab)

print(f"\n{'═' * 70}\n{'✗ ' + str(len(echecs)) + ' échec(s) : ' + ', '.join(echecs) if echecs else '✓ 0 échec'}\n")
sys.exit(1 if echecs else 0)
