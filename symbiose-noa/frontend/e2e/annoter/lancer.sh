#!/bin/bash
# Banc de l'annotateur d'images (21/09), joué dans un VRAI navigateur, sans backend.
#
# Les vrais composants (VisuelPaysager, PiecesJointes, InputBar, Annoter) sont
# assemblés par esbuild dans deux pages d'essai, puis pilotés par playwright-core :
# crayon, cinq couleurs, trait, annulation, export JPEG à la résolution de l'image,
# arrivée dans la barre de saisie, remplacement de la pièce en attente, envoi du
# message avec l'image, téléphone sans débordement, aucun onglet ouvert par erreur.
#
#   bash frontend/e2e/annoter/lancer.sh        (depuis la racine du dépôt)
#   CHROME=/chemin/vers/chrome bash …           (autre navigateur)
#
# Rien n'est installé dans le projet : esbuild et playwright-core viennent de npx,
# dans un dossier temporaire.
set -euo pipefail
ICI="$(cd "$(dirname "$0")" && pwd)"
FRONT="$(cd "$ICI/../.." && pwd)"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
( cd "$T" && npm init -y >/dev/null && npm i --silent esbuild playwright-core@1.57 >/dev/null )
for p in planche saisie; do
  NODE_PATH="$FRONT/node_modules" "$T/node_modules/.bin/esbuild" "$ICI/$p.tsx" --bundle --outfile="$T/$p.js" \
    --jsx=automatic --alias:@="$FRONT" --loader:.css=empty --log-level=warning \
    --define:process.env.NODE_ENV='"production"' --define:process.env.NEXT_PUBLIC_API_URL='""'
  printf '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"></head><body><div id="app"></div><script src="%s.js"></script></body></html>' "$p" > "$T/$p.html"
done
cp "$ICI"/banc-*.mjs "$T/"
cd "$T"
node banc-planche.mjs "$T"
node banc-saisie.mjs "$T"
