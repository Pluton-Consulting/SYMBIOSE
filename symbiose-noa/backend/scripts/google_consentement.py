#!/usr/bin/env python
"""
Consentement Google Drive — à lancer UNE FOIS, sur un poste avec navigateur.

POURQUOI PAS SUR LE VPS. Le premier consentement OAuth ouvre une page dans un
navigateur et attend le retour sur `localhost`. Un serveur sans écran ne peut ni
l'ouvrir ni le recevoir. On produit donc le jeton ici, puis on le dépose sur le
serveur : c'est un fichier, il se copie.

CE QU'IL PRODUIT. `secrets/google_token.json`, qui contient un REFRESH TOKEN.
C'est lui qui permet au serveur de se reconnecter seul, indéfiniment, sans
jamais redemander de mot de passe. Il vaut donc un accès en lecture à tout le
Drive : il se traite comme un mot de passe.

    python scripts/google_consentement.py

Prérequis : `secrets/google_credentials.json`, le client OAuth « Desktop »
téléchargé depuis Google Cloud Console.
"""
from __future__ import annotations

import json
import os
import sys

# Depuis le 30/08, le jeton porte l'ÉCRITURE : le dépôt sur le Drive
# (`drive_deposer`, `drive_deposer_document`) en a besoin, et le scope se fixe
# au CONSENTEMENT — un jeton taillé en lecture seule ne monte jamais tout seul.
# La lecture, elle, continue de construire ses clients avec le scope minimal
# (`_SCOPES` du connecteur) : seul le client du dépôt réclame celui-ci.
SCOPES = ["https://www.googleapis.com/auth/drive"]

CREDENTIALS = os.environ.get("GOOGLE_CREDENTIALS_FILE", "secrets/google_credentials.json")
TOKEN = os.environ.get("GOOGLE_TOKEN_FILE", "secrets/google_token.json")


def main() -> int:
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("Bibliothèques manquantes. Installez-les d'abord :\n"
              "    pip install google-auth-oauthlib google-api-python-client",
              file=sys.stderr)
        return 2

    if not os.path.exists(CREDENTIALS):
        print(f"Fichier introuvable : {CREDENTIALS}\n\n"
              "C'est le client OAuth « Desktop » à télécharger depuis Google Cloud\n"
              "Console (Identifiants > Créer > ID client OAuth > Application de\n"
              "bureau > télécharger le JSON).", file=sys.stderr)
        return 2

    print("Une page va s'ouvrir dans votre navigateur.")
    print("Connectez-vous avec le compte Google qui a accès aux dossiers à lire.\n")

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS, SCOPES)
    # `access_type=offline` demande le REFRESH TOKEN — c'est lui, et lui seul,
    # qui permet au serveur de se reconnecter sans personne devant l'écran.
    #
    # `prompt=consent` le REDEMANDE à chaque passage. Sans ça, Google ne le
    # délivre qu'au tout premier consentement : relancer ce script après un
    # échec rendait un jeton sans refresh token, et il fallait d'abord aller
    # retirer l'application dans son compte Google pour s'en sortir. Le piège
    # se referme des semaines plus tard, quand l'accès expire en silence.
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

    os.makedirs(os.path.dirname(TOKEN) or ".", exist_ok=True)
    with open(TOKEN, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    # Le jeton vaut un accès en lecture au Drive : on restreint le fichier au
    # propriétaire. Sans effet sur Windows, utile partout ailleurs.
    try:
        os.chmod(TOKEN, 0o600)
    except OSError:
        pass

    donnees = json.loads(creds.to_json())
    print(f"\nJeton écrit dans {TOKEN}")
    print("  refresh token présent :", "oui" if donnees.get("refresh_token") else "NON")

    if not donnees.get("refresh_token"):
        # Ne devrait plus arriver depuis `prompt=consent`. Le contrôle reste :
        # un jeton sans refresh token expire en silence quelques jours plus
        # tard, et le connecteur semblerait alors « avoir cessé de marcher ».
        print("\n⚠ SANS refresh token, le serveur perdra l'accès dès l'expiration.\n"
              "  Retirez l'accès de l'application sur https://myaccount.google.com/permissions\n"
              "  puis relancez ce script.")
        return 1

    print("\nÀ FAIRE ENSUITE — copier les DEUX fichiers sur le serveur :")
    print("    scp secrets/google_credentials.json secrets/google_token.json \\")
    print("        <utilisateur>@<serveur>:~/SYMBIOSE/symbiose-noa/backend/secrets/")
    print("\nPuis, dans Paramètres > Synchronisations, lancer « Google Drive ».")
    return 0


if __name__ == "__main__":
    sys.exit(main())
