"""
Banc « TOUS LES MAILS SIGNIFIE TOUS LES MAILS » — 17/09, 14:54, Symbiose (Outlook).
« Liste TOUS les mails des 7 derniers jours, aucune troncature » : 97 annoncés, 25 lus,
« la lecture a été interrompue ». Le modèle a rappelé SEPT fois `lire_mails depuis 7j,
exhaustif: true` sans jamais prendre la page suivante ; la garde du rejeu a coupé.
`exhaustif` ne changeait qu'une phrase d'aide, et le parcours complet de `check_mails`
suit un CURSEUR que seule la voie IMAP rendait — Outlook n'avait jamais de page 2.

Sans réseau : fonctions extraites du code livré, boîte doublée de 97 messages.
"""
import ast
import asyncio
import pathlib
import sys
from datetime import datetime
from typing import Optional

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


def fonctions(src, noms):
    return "\n\n".join(ast.get_source_segment(src, n) for n in ast.parse(src).body
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in noms)


print("\n═══ INVENTAIRE DES MAILS —", BACKEND.parent)
lect = (BACKEND / "mail" / "lecture.py").read_text(encoding="utf-8")
esp = {"Optional": Optional, "datetime": datetime, "MAX_COMPTE": 5000, "SELECT_OUTLOOK": "id,subject",
       "_kql_echapper": lambda x: x}
exec(fonctions(lect, {"_saut_outlook", "_params_outlook"}), esp)
saut, params = esp["_saut_outlook"], esp["_params_outlook"]
verifier("le curseur Outlook se lit (« saut:50 » → 50), tout le reste vaut 0",
         saut("saut:50") == 50 and saut(None) == 0 and saut("imap:1:22") == 0 and saut("saut:x") == 0 and saut("2026-09-15") == 0)
p = params(25, datetime(2026, 9, 10), None, None, 50)
verifier("la page suivante garde le filtre, l'ordre et le compte, et saute les messages déjà rendus",
         p.get("$skip") == 50 and "receivedDateTime ge" in p.get("$filter", "") and p.get("$orderby") == "receivedDateTime desc" and p.get("$count") == "true")
verifier("la première page n'envoie pas de `$skip`", "$skip" not in params(25, datetime(2026, 9, 10)))
verifier("une RECHERCHE ne saute jamais (Graph refuse `$skip` avec `$search`)", "$skip" not in params(25, None, "terrasse", None, 50))
verifier("la dernière fiche d'une page Outlook porte le curseur SEULEMENT s'il reste des messages",
         'if resultats and total is not None and saut + len(resultats) < int(total):' in lect
         and 'resultats[-1]["curseur_suivant"] = f"saut:{saut + len(resultats)}"' in lect)
verifier("`lire_boite` accepte le curseur de SA voie et refuse celui d'une autre (trouvé par la sonde réelle)",
         "nom == 'outlook' and _forme.startswith('saut:')" in lect and "nom == 'imap' and _forme.startswith('imap:')" in lect)
verifier("la voie IMAP garde sa propre règle (le total dit s'il y a une suite)",
         "_dernier.startswith('saut:') or (total and total>len(messages))" in lect)

# ── le skill, EXÉCUTÉ sur une boîte doublée de 97 messages ───────────────────
sk = (BACKEND / "mail" / "skills.py").read_text(encoding="utf-8")
BOITE = [{"ref": f"r{i:03d}", "objet": f"Message {i}", "de": "client@exemple.fr", "date": "2026-09-1%d" % (i % 7)} for i in range(97)]
appels = []


async def lire_boite(boite, dossier="recus", limite=10, depuis=None, recherche=None, avant=None,
                     apercu=None, curseur=None, exhaustif=False):
    debut = int(str(curseur)[5:]) if str(curseur or "").startswith("saut:") else 0
    appels.append((debut, limite, apercu))
    page = [dict(m) for m in BOITE[debut:debut + limite]]
    suite = f"saut:{debut + len(page)}" if debut + len(page) < len(BOITE) else None
    return {"boite": boite, "messages": page, "nombre": len(page), "total_periode": len(BOITE),
            "curseur_suivant": suite, "tronque": bool(suite), "compte": "…", "pour_continuer": "…"}


class _Erreur(Exception):
    pass


async def _acces(user, boite): return boite or "moi@exemple-paysage.fr"
async def _defaut(user): return "moi@exemple-paysage.fr"
async def _visibles(user): return []
async def _a_lire(data, user): return data.get("mailbox") or "moi@exemple-paysage.fr"

import types, logging
sys.modules["mail.lecture"] = types.SimpleNamespace(lire_boite=lire_boite)
sys.modules.setdefault("mail", types.ModuleType("mail"))
esp2 = {"_boite_a_lire": _a_lire, "verifier_acces": _acces, "boite_par_defaut": _defaut, "boites_visibles": _visibles,
        "MailSkillError": _Erreur, "logger": logging.getLogger("banc"), "MAX_INVENTAIRE_MAILS": 250, "APERCU_INVENTAIRE": 200}
exec(fonctions(sk, {"lire_mails"}), esp2)
lire_mails = esp2["lire_mails"]
user = types.SimpleNamespace(id="u", role="direction")

r = asyncio.run(lire_mails({"depuis": "7j", "exhaustif": True}, user))     # les arguments EXACTS de prod
verifier("les arguments EXACTS de prod rendent les 97 messages en UN geste", r["nombre"] == 97 and len(r["messages"]) == 97, str(r.get("nombre")))
verifier("aucun doublon, aucun trou, l'ordre est tenu", [m["ref"] for m in r["messages"]] == [m["ref"] for m in BOITE])
verifier("le résultat dit que c'est TOUT, et de ne pas rappeler le geste",
         r["tronque"] is False and r["curseur_suivant"] is None and "TOUS" in r["compte"] and "Ne rappelle pas" in (r.get("a_faire") or ""))
verifier("il se déclare inventaire (c'est ce qui lui ouvre le grand plafond de résultat)", r.get("inventaire") is True)
verifier("quatre pages ont été lues côté serveur, avec l'extrait court de l'inventaire",
         [a[0] for a in appels] == [0, 25, 50, 75] and all(a[2] == 200 for a in appels), str(appels))

appels.clear()
r2 = asyncio.run(lire_mails({"depuis": "7j"}, user))
verifier("SANS `exhaustif`, une seule page comme avant (rapide)", len(appels) == 1 and r2["nombre"] == 25 and not r2.get("inventaire"))
appels.clear()
asyncio.run(lire_mails({"recherche": "terrasse", "exhaustif": True}, user))
verifier("une RECHERCHE exhaustive garde son régime (pas de parcours par curseur)", len(appels) == 1)
BOITE.extend({"ref": f"x{i}", "objet": "x", "de": "a@b.fr", "date": "2026-09-10"} for i in range(400))
appels.clear()
r3 = asyncio.run(lire_mails({"depuis": "30j", "tous": True}, user))
verifier("le parcours est BORNÉ (250), et au-delà la suite est DITE, jamais tue",
         r3["nombre"] == 250 and r3["tronque"] is True and r3["curseur_suivant"] == "saut:250" and "curseur=saut:250" in (r3.get("pour_continuer") or ""))

# ── LE TABLEAU COMPLET ET L'EXCEL SE FABRIQUENT, ILS NE SE RECOPIENT PAS ─────
# 17/09 15:36 → 15:45 : 98 mails lus, VINGT lignes à l'écran, puis QUATRE dans l'Excel.
print("\n── le livrable de l'inventaire")
import json as _json, re as _re
del BOITE[97:]
produits = []


async def _appeler(prompt, tier="standard"):
    # Un modèle doublé : classe chaque ligne du lot, invente UNE catégorie hors liste.
    rangs = [int(x) for x in _re.findall(r"^(\d+)\. De :", prompt, _re.M)]
    return "Voici : " + _json.dumps([{"n": n, "resume": f"résumé {n}", "categorie": ("fournisseur" if n % 2 else "PUBLICITÉ")} for n in rangs])


async def _protege(t): return t, {}
class _Atelier:
    @staticmethod
    def ouvrir(entete, proprio): return "jeton123"
    @staticmethod
    def ajouter(jeton, elements, proprio): produits.append(elements); return len(elements)
    @staticmethod
    def terminer(jeton, proprio): return {"octets": 4242}
sys.modules["bureautique"] = types.ModuleType("bureautique")
sys.modules["bureautique.atelier"] = _Atelier
esp3 = {"re": _re, "logger": logging.getLogger("banc"), "_appeler": _appeler, "_protege": _protege,
        "_rehydrater": lambda v, c: v}
exec("\n".join(ast.get_source_segment(sk, n) for n in ast.parse(sk).body
               if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("CATEGORIES_MAILS", "LOT_CLASSEMENT"))
               or (isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name in ("_categories_voulues", "_lire_classement", "_classer_les_mails", "_jour_lisible", "_livrer_inventaire"))), esp3)
esp2.update(esp3)
r4 = asyncio.run(lire_mails({"depuis": "7j", "classer": True, "fichier": True}, user))
blocs = r4["bloc_ui"]
table = next(b for b in blocs if b["type"] == "table")
verifier("`classer` + `fichier` sans `exhaustif` : l'inventaire complet est fait quand même (97 lignes)", len(table["rows"]) == 97, str(len(table["rows"])))
verifier("le tableau porte date, expéditeur, objet, résumé, catégorie — pour CHAQUE mail",
         table["columns"] == ["Date", "Expéditeur", "Objet", "Résumé", "Catégorie"] and all(len(l) == 5 for l in table["rows"]))
verifier("une catégorie HORS liste n'est pas recopiée : la ligne reste « à classer », rien n'est inventé",
         {l[4] for l in table["rows"]} == {"fournisseur", "à classer"})
verifier("le bloc est GARANTI (le modèle n'a rien à recopier) et le fichier est au-dessus du tableau",
         r4["bloc_garanti"] is True and blocs[0]["type"] == "fichier" and blocs[0]["url"] == "/api/documents/jeton123")
verifier("l'Excel porte les 97 lignes et un second onglet « Par catégorie »",
         len(produits[-1]) == 2 and produits[-1][0]["type"] == "feuille" and len(produits[-1][0]["lignes"]) == 97
         and produits[-1][1]["nom"] == "Par catégorie")
verifier("la consigne interdit de recopier et demande ce qu'on veut EN PLUS (les priorités)",
         "ne recopie AUCUNE ligne" in r4["a_faire"] and "priorité" in r4["a_faire"] and "Ne rappelle pas" in r4["a_faire"])
esp3["_appeler"] = None   # un modèle en panne
async def _panne(prompt, tier="standard"): raise RuntimeError("cascade à terre")
esp2["_appeler"] = _panne
r5 = asyncio.run(lire_mails({"depuis": "7j", "classer": True}, user))
verifier("un modèle en panne ne fait pas tomber l'inventaire : 97 lignes « à classer », et c'est dit",
         len(r5["bloc_ui"][0]["rows"]) == 97 and r5["classes"] == 0 and {l[4] for l in r5["bloc_ui"][0]["rows"]} == {"à classer"})
lc = esp3["_lire_classement"]
verifier("la lecture du classement est tolérante et bornée (rang hors lot, JSON cassé, prose autour)",
         lc('blabla [{"n": 1, "resume": "x", "categorie": "Fournisseur"}, {"n": 9, "resume": "y", "categorie": "fournisseur"}] fin', 3, ["fournisseur"]) == {1: ("x", "fournisseur")}
         and lc("pas de json", 3, ["a"]) == {} and lc("[{", 3, ["a"]) == {})
verifier("`categories` en texte ou en liste, sinon celles de la maison",
         esp3["_categories_voulues"]("Devis, SAV ; Compta") == ["devis", "sav", "compta"] and esp3["_categories_voulues"](None)[0] == "demande de devis")
proto = (BACKEND / "skills" / "protocol.py").read_text(encoding="utf-8")
verifier("le catalogue annonce `classer`, `categories`, `fichier` et dit de NE PAS passer par produire_document",
         '"classer", "categories", "fichier"' in proto and "n'utilise PAS `produire_document`" in proto)

a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("le résultat d'un inventaire n'est pas recoupé après avoir été parcouru en entier",
         "action['skill']=='lire_mails' and isinstance(sortie,dict) and sortie.get('inventaire'):plafond=190000" in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
