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

a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
verifier("le résultat d'un inventaire n'est pas recoupé après avoir été parcouru en entier",
         "action['skill']=='lire_mails' and isinstance(sortie,dict) and sortie.get('inventaire'):plafond=190000" in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
