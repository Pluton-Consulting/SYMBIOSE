"""
Banc « UN CLIENT GOOGLE, UN FIL À LA FOIS » — 17/09, 11:07:30 UTC : le backend de
Symbiose est MORT (`free(): corrupted unsorted chunks`) et a redémarré seul, toutes
les conversations en cours perdues. Juste avant : six appels Drive de front sur le
même client et « [SSL] record layer failure ». Le listage en lot posé le matin
lançait huit listages sur LE client gardé ; httplib2 n'a qu'une connexion TLS, deux
fils qui y écrivent ensemble corrompent la mémoire d'OpenSSL.

CE QUE CE BANC PROUVE (sans réseau) : le garde EXÉCUTÉ sur un faux client qui
DÉTECTE deux fils entrés en même temps ; et le contrat du lot (un client par tâche).
"""
import ast
import logging
import pathlib
import sys
import threading
import time

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "outils" / "drive.py").read_text(encoding="utf-8")
garde_src = next(ast.get_source_segment(src, n) for n in ast.parse(src).body
                 if isinstance(n, ast.FunctionDef) and n.name == "_un_fil_a_la_fois")
esp = {"logger": logging.getLogger("banc")}
exec(garde_src, esp)
garde = esp["_un_fil_a_la_fois"]


class Http:
    """Une connexion qui SAIT quand deux fils y sont en même temps."""
    def __init__(self):
        self.dedans, self.collisions, self.appels = 0, 0, 0

    def request(self, uri, method="GET", **k):
        self.dedans += 1
        if self.dedans > 1:
            self.collisions += 1
        time.sleep(0.01)
        self.appels += 1
        self.dedans -= 1
        return ({"status": "200"}, b"{}")


class Service:
    def __init__(self):
        self._http = Http()


def marteler(service, fils=8, tours=6):
    def travail():
        for _ in range(tours):
            service._http.request("https://exemple", method="GET")
    ts = [threading.Thread(target=travail) for _ in range(fils)]
    [t.start() for t in ts]
    [t.join() for t in ts]


print("\n═══ UN CLIENT, UN FIL —", BACKEND.parent)
nu = Service(); marteler(nu)
verifier("SANS garde, huit fils se marchent dessus sur le même client (le défaut, reproduit)", nu._http.collisions > 0)
sur = garde(Service()); marteler(sur)
verifier("AVEC le garde, jamais deux fils en même temps sur le même client", sur._http.collisions == 0, str(sur._http.collisions))
verifier("…et aucun appel n'est perdu", sur._http.appels == 48)
verifier("le résultat de la requête traverse le garde intact", sur._http.request("x")[1] == b"{}")
v = sur._http._verrou_pluton
verifier("le garde est idempotent (un client déjà gardé n'est pas ré-enveloppé)", garde(sur)._http._verrou_pluton is v)
verifier("un client sans `_http` passe tel quel, sans lever", garde(object()) is not None)
a, b = garde(Service()), garde(Service())
verifier("deux clients DISTINCTS ne se bloquent pas l'un l'autre (le parallélisme reste possible)",
         a._http._verrou_pluton is not b._http._verrou_pluton)

verifier("le client gardé, le vivier et le client d'écriture passent TOUS par le garde",
         "service = _un_fil_a_la_fois(await _build_service_pour(identite))" in src
         and "_un_fil_a_la_fois(c) for c in await asyncio.gather(" in src
         and "_un_fil_a_la_fois(await _build_service_pour(identite, ecriture=True))" in src)
lot = src[src.index("async def lister_lot"):]
lot = lot[:lot.index("lots = await asyncio.gather")]
verifier("le lot prend ses clients dans le vivier : autant de tâches de front que de clients",
         "clients = await _services(min(MAX_LOT_CONCURRENCE, len(propres)), identite)" in lot
         and "client = await libres.get()" in lot)
verifier("chaque tâche impose SON client, et le rend quoi qu'il arrive",
         "_CLIENT_DE_LA_TACHE.set((cle_identite, client))" in lot
         and "finally:" in lot and "libres.put_nowait(client)" in lot and "_CLIENT_DE_LA_TACHE.reset(jeton)" in lot)
svc = src[src.index("async def _service(identite=None)"):]
svc = svc[:svc.index("\nasync def ", 10)]
verifier("`_service()` rend le client imposé — seulement pour la MÊME identité",
         "impose = _CLIENT_DE_LA_TACHE.get()" in svc and "impose[0] == _cle_client(identite)" in svc)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
