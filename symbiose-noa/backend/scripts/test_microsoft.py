#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test AUTONOME de l'app Microsoft Entra / Graph (flux app-only).

But : vérifier, AVANT de toucher au projet, que ton app Entra fonctionne vraiment :
  1) lister les boîtes mail de l'entreprise   (permission User.Read.All)
  2) lire les derniers mails d'une boîte       (permission Mail.Read)

Caractéristiques :
  - AUCUNE dépendance (bibliothèque standard Python 3 uniquement — pas de pip).
  - Tu saisis Tenant ID / Client ID / Client secret À LA MAIN. Rien n'est enregistré.

Lancer :   python test_microsoft.py
"""
import json
import sys
import getpass
import urllib.request
import urllib.parse
import urllib.error

GRAPH = "https://graph.microsoft.com/v1.0"
DEFAULT_MAILBOX = "contact@symbiose-paysage.fr"


# ── Utilitaires ───────────────────────────────────────────────────────

def ask(label, default=""):
    suffix = " [%s]" % default if default else ""
    val = input("%s%s : " % (label, suffix)).strip()
    return val or default


def get_token(tenant, client_id, client_secret):
    """Flux client_credentials → jeton d'application Graph. (token, erreur_dict)."""
    url = "https://login.microsoftonline.com/%s/oauth2/v2.0/token" % urllib.parse.quote(tenant)
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r).get("access_token"), None
    except urllib.error.HTTPError as e:
        try:
            return None, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return None, {"error": "http_%s" % e.code}
    except urllib.error.URLError as e:
        return None, {"error": "reseau", "error_description": str(e.reason)}


def graph_get(token, path):
    """GET Graph → (status_http, corps_json)."""
    req = urllib.request.Request(GRAPH + path, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}
    except urllib.error.URLError as e:
        return 0, {"error": {"code": "reseau", "message": str(e.reason)}}


def graph_error_hint(status, body):
    """Message d'aide en français selon l'erreur Graph."""
    err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
    code = err.get("code", "")
    msg = err.get("message", "")
    if status == 403 or code == "Authorization_RequestDenied":
        hint = ("Permission d'application manquante OU consentement admin non accordé.\n"
                "     -> Entra > Autorisations d'API : ajoute Mail.Read et User.Read.All\n"
                "        (permissions d'APPLICATION), puis 'Accorder le consentement admin'.")
    elif status == 401:
        hint = "Jeton refusé (secret invalide/expiré ?). Recree un secret client."
    elif code in ("MailboxNotEnabledForRESTAPI", "ResourceNotFound") or status == 404:
        hint = ("Boite introuvable ou non-Exchange : verifie l'adresse exacte "
                "(doit etre une vraie boite avec licence Exchange).")
    else:
        hint = msg or "voir le detail ci-dessus."
    return "%s %s" % (code or status, ("- " + msg) if msg else ""), hint


# ── Programme ─────────────────────────────────────────────────────────

def main():
    print("=" * 62)
    print("  TEST APP MICROSOFT ENTRA / GRAPH  (app-only, autonome)")
    print("=" * 62)
    print("Saisis les valeurs de ton app Entra (rien n'est enregistre).\n")

    tenant = ask("Tenant ID (ID de l'annuaire)")
    client_id = ask("Client ID (ID d'application)")
    client_secret = getpass.getpass("Client secret (la VALEUR, saisie masquee) : ").strip()
    mailbox = ask("Boite a tester", DEFAULT_MAILBOX)

    if not (tenant and client_id and client_secret):
        print("\n[ERREUR] Tenant, Client ID et secret sont obligatoires.")
        return 1

    # 0) Jeton
    print("\n[1/3] Obtention du jeton d'application...")
    token, err = get_token(tenant, client_id, client_secret)
    if not token:
        print("  [ECHEC] Impossible d'obtenir un jeton.")
        if err:
            print("    error       : %s" % err.get("error"))
            desc = err.get("error_description", "")
            if desc:
                print("    description : %s" % desc.splitlines()[0])
            print("    Pistes : Tenant/Client ID incorrect, ou secret invalide/expire.")
        return 1
    print("  [OK] Jeton obtenu. L'authentification de l'app fonctionne.")

    ok_users = ok_mail = False

    # 1) Liste des boites de l'entreprise (User.Read.All)
    print("\n[2/3] Liste des boites de l'entreprise (permission User.Read.All)...")
    status, body = graph_get(
        token, "/users?" + urllib.parse.urlencode(
            {"$select": "displayName,mail,userPrincipalName", "$top": "25"},
            quote_via=urllib.parse.quote))
    if status == 200:
        users = body.get("value", [])
        boites = [(u.get("displayName") or "?", u.get("mail") or u.get("userPrincipalName") or "?")
                  for u in users]
        print("  [OK] %d compte(s) recupere(s) :" % len(boites))
        for name, addr in boites:
            print("       - %-32s %s" % (addr, name))
        if body.get("@odata.nextLink") or len(users) == 25:
            print("       (... liste tronquee a 25)")
        ok_users = True
    else:
        label, hint = graph_error_hint(status, body)
        print("  [ECHEC] %s" % label)
        print("     %s" % hint)

    # 2) Derniers mails de la boite cible (Mail.Read)
    print("\n[3/3] Derniers mails de %s (permission Mail.Read)..." % mailbox)
    path = "/users/%s/messages?%s" % (
        urllib.parse.quote(mailbox, safe="@."),
        urllib.parse.urlencode(
            {"$top": "5", "$select": "subject,from,receivedDateTime,bodyPreview",
             "$orderby": "receivedDateTime desc"},
            quote_via=urllib.parse.quote))
    status, body = graph_get(token, path)
    if status == 200:
        msgs = body.get("value", [])
        if not msgs:
            print("  [OK] Acces autorise, mais la boite ne contient aucun message.")
        else:
            print("  [OK] %d dernier(s) mail(s) :" % len(msgs))
            for m in msgs:
                sender = ((m.get("from") or {}).get("emailAddress") or {}).get("address", "?")
                print("       - [%s] %s"
                      % (m.get("receivedDateTime", "?")[:16], m.get("subject") or "(sans objet)"))
                print("         de %s | %s" % (sender, (m.get("bodyPreview") or "").strip()[:70]))
        ok_mail = True
    else:
        label, hint = graph_error_hint(status, body)
        print("  [ECHEC] %s" % label)
        print("     %s" % hint)

    # Bilan
    print("\n" + "=" * 62)
    print("  BILAN")
    print("    Authentification app .......... OK")
    print("    Liste des boites (User.Read.All) %s" % ("OK" if ok_users else "ECHEC"))
    print("    Lecture des mails (Mail.Read) .. %s" % ("OK" if ok_mail else "ECHEC"))
    print("=" * 62)
    if ok_users and ok_mail:
        print("Tout fonctionne : Microsoft est pret pour l'ingestion.")
    else:
        print("Corrige les permissions en ECHEC dans Entra (voir pistes ci-dessus),")
        print("puis relance ce script.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAnnule.")
        sys.exit(130)
