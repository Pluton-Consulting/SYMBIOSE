"""
Banc « LA SIGNATURE S'APPREND DEPUIS LE MESSAGE QU'ON DÉSIGNE » — 17/09, 14:25,
fil 99746210 (Symbiose). L'assistant venait de trouver l'image de signature dans le
message envoyé « RE: projet allée et surface autour garage… ». « Enregistre cette
signature » → le modèle écrit {"skill":"apprendre_signature","args":{"boite":…,
"source":"RE: projet allée…"}}. `source` était inconnu du geste et IGNORÉ EN
SILENCE : la signature a été ré-apprise depuis le DERNIER envoi (« Envoyé à partir
de Outlook pour iOS »), et la réponse affirmait l'image enregistrée.

Sans réseau : les fonctions sont extraites du code livré, la boîte est doublée.
"""
import ast
import asyncio
import pathlib
import sys
import types

BACKEND = pathlib.Path(__file__).resolve().parents[1]
echecs = []


def verifier(nom, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + nom + (f"  → {detail}" if detail and not cond else ""))
    if not cond:
        echecs.append(nom)


src = (BACKEND / "mail" / "skills.py").read_text(encoding="utf-8")
arbre = ast.parse(src)
code = "\n\n".join(ast.get_source_segment(src, n) for n in arbre.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and n.name in ("_objet_designe", "_objet_nu", "_ref_du_message_envoye"))
ENVOYES = [
    {"ref": "aaaa", "objet": "Essence Belin Belin Super U"},                       # le dernier envoi (iPhone)
    {"ref": "bbbb", "objet": "RE: projet allée et surface autour garage pour parking voiture et surface arrière"},
    {"ref": "cccc", "objet": "TR: RE: projet allée et surface autour garage pour parking voiture et surface arrière"},
]
appels = []


async def lire_boite(boite, dossier="recus", limite=10, recherche=None, **k):
    appels.append((boite, dossier, recherche))
    return {"messages": ENVOYES}

sys.modules["mail.lecture"] = types.SimpleNamespace(lire_boite=lire_boite)
sys.modules.setdefault("mail", types.ModuleType("mail"))
esp = {"_CLES_OBJET_DESIGNE": ("objet", "source", "message", "sujet", "titre", "subject")}
exec(code, esp)
designe, nu, ref_de = esp["_objet_designe"], esp["_objet_nu"], esp["_ref_du_message_envoye"]

print("\n═══ SIGNATURE DÉSIGNÉE —", BACKEND.parent)
ARGS_PROD = {"boite": "benjamin.durou@exemple-paysage.fr",
             "source": "RE: projet allée et surface autour garage pour parking voiture et surface arrière"}
verifier("les arguments EXACTS de prod désignent bien un message (`source`)", designe(ARGS_PROD).startswith("RE: projet allée"))
verifier("`objet`, `sujet`, `message`, `titre` valent aussi ; guillemets retirés",
         designe({"objet": "« Devis Martin »"}) == "Devis Martin" and designe({"sujet": "x"}) == "x"
         and designe({"titre": "y"}) == "y" and designe({"message": "z"}) == "z")
verifier("sans désignation, rien (le parcours libre-service des derniers envois reste)", designe({"mailbox": "a@b.fr"}) == "" and designe({}) == "")
verifier("les préfixes RE: / TR: / Fwd: tombent, la casse et les espaces aussi",
         nu("RE: TR:  Projet   Allée") == "projet allée" and nu("Fwd: RE: x") == "x")
r = asyncio.run(ref_de("boite@exemple-paysage.fr", ARGS_PROD["source"]))
verifier("le message désigné est retrouvé dans les ENVOYÉS — pas le dernier envoi de l'iPhone", r == "bbbb", r)
verifier("la recherche part bien dans le dossier des envoyés", appels and appels[-1][1] == "envoyes" and "projet allée" in appels[-1][2])
verifier("un objet partiel retrouve le message", asyncio.run(ref_de("b", "projet allée et surface autour garage")) == "bbbb")
verifier("un objet inconnu ne rend RIEN (le geste échouera, il ne prendra pas un autre message)",
         asyncio.run(ref_de("b", "Commande de gravier Dupont")) == "")

skill = src[src.index("async def apprendre_signature"):]
skill = skill[:skill.index("\nasync def ", 10)]
verifier("désigné mais introuvable : ÉCHEC dit, avant tout apprentissage",
         skill.index("AUCUNE signature n'a été apprise ni modifiée") < skill.index("resultat = await apprendre(boite, user, ref=ref)"))
verifier("`boite` est accepté comme `mailbox` (la forme écrite par le modèle)", 'data.get("mailbox") or data.get("boite")' in skill)
proto = (BACKEND / "skills" / "protocol.py").read_text(encoding="utf-8")
verifier("le catalogue annonce `objet` et dit de DÉSIGNER le message qu'on vient de trouver",
         '["mailbox", "ref", "objet"]' in proto and "DESIGNE-LE" in proto)

# ── LA MENTION D'UN TÉLÉPHONE N'EST PAS UNE SIGNATURE ─────────────────────────
import re as _re
sig = (BACKEND / "mail" / "signature.py").read_text(encoding="utf-8")
m = ast.parse(sig)
code_sig = "\n".join(ast.get_source_segment(sig, n) for n in m.body
                     if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "_RE_MENTION_MOBILE")
                     or (isinstance(n, ast.FunctionDef) and n.name == "mention_de_telephone"))
e2 = {"re": _re}; exec(code_sig, e2); mobile = e2["mention_de_telephone"]
print("\n── la mention du téléphone")
verifier("« Envoyé à partir de Outlook pour iOS » (enregistrée comme signature le 17/09) est écartée",
         mobile("Envoyé à partir de Outlook pour iOS") and mobile("Envoyé de mon iPhone") and mobile("Sent from my iPhone")
         and mobile("Télécharger Outlook pour Android"))
verifier("une vraie signature ne l'est pas, même courte, même si la mention la précède",
         not mobile("Benjamin DUROU\nDirecteur\n06 73 33 72 80") and not mobile("Cordialement,\nBenjamin")
         and not mobile("Envoyé à partir de Outlook pour iOS\nBenjamin DUROU\nDirecteur\nSymbiose Paysage") and not mobile(""))
verifier("la mention est écartée AVANT d'entrer dans les candidates, et l'échec dit pourquoi",
         sig.index("if mention_de_telephone(en_texte(signature)):") < sig.index("entree = candidats.setdefault(")
         and "n'est pas une signature" in sig and "if not candidats and mobiles:" in sig)
verifier("l'échantillon des envois est assez profond pour dépasser une série d'envois de téléphone",
         int(_re.search(r"^MAX_ECHANTILLONS = (\d+)", sig, _re.M).group(1)) >= 20)

# ── LES PIÈCES D'UN MAIL OUVERT EN CHEMIN NE S'AFFICHENT PAS D'OFFICE ────────
a1 = (BACKEND / "agents" / "agent1.py").read_text(encoding="utf-8")
m1 = ast.parse(a1)
code_a1 = "\n".join(ast.get_source_segment(a1, n) for n in m1.body
                    if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in ("_SKILLS_PIECES_DE_MAIL", "_DEMANDE_DE_MAIL_RE"))
                    or (isinstance(n, ast.FunctionDef) and n.name == "_pieces_de_mail_hors_sujet"))
e3 = {"_re_livrables": _re}; exec(code_a1, e3); hs = e3["_pieces_de_mail_hors_sujet"]
print("\n── les pièces hors sujet")
verifier("le tour EXACT de 14:26 : « Enregistre l'image » + un `lire_mail` en chemin = hors sujet",
         hs({"skill": "lire_mail", "ok": True}, "Enregistre l’image") is True)
verifier("dès que la demande parle de mails ou de pièces jointes, elles s'affichent comme avant",
         not hs({"skill": "lire_mail"}, "ouvre le dernier mail avec ses pièces jointes")
         and not hs({"skill": "lire_piece_jointe"}, "lis la PJ du message de Martin")
         and not hs({"skill": "check_mails"}, "fais le point sur ma boîte"))
verifier("un livrable PRODUIT n'est jamais concerné (produire_document, modifier_visuel, drive_ouvrir…)",
         not hs({"skill": "produire_document"}, "Enregistre l’image") and not hs({"skill": "drive_ouvrir"}, "ouvre le devis"))
verifier("connu n'est pas affiché d'office : la pièce reste montrable, elle ne s'ajoute plus seule",
         "a_montrer = [b for b in produits if _reference_bloc(b) in _d_office]" in a1
         and "connus = produits + " in a1)

print("\n" + "═" * 70)
if echecs:
    print(f"✗ {len(echecs)} échec(s) : " + ", ".join(echecs))
    sys.exit(1)
print("✓ 0 échec\n")
