#!/usr/bin/env bash
# =====================================================================
#  Déploiement / mise à jour de Symbiose sur le VPS.
#  À lancer depuis le dossier symbiose-noa/ APRÈS avoir rempli .env :
#      chmod +x deploy.sh
#      ./deploy.sh
#  Idempotent : relançable pour appliquer une mise à jour (git pull puis ./deploy.sh).
#  Détail des étapes : voir DEPLOY.md.
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERREUR : fichier .env manquant. Copie .env.example vers .env puis remplis-le." >&2
  exit 1
fi

# Lit quelques variables du .env SANS le sourcer : le .env (format Docker Compose) peut
# contenir des espaces / des caractères < > (ex. RESEND_FROM_EMAIL) qui casseraient `. .env`.
# On retire aussi un éventuel commentaire de fin de ligne et les espaces.
env_get() { sed -n "s/^[[:space:]]*$1=//p" .env | sed 's/[[:space:]]*#.*$//; s/[[:space:]]*$//'; }
POSTGRES_USER="$(env_get POSTGRES_USER)"
POSTGRES_DB="$(env_get POSTGRES_DB)"
FIRST_ADMIN_EMAIL="$(env_get FIRST_ADMIN_EMAIL)"
: "${POSTGRES_USER:?POSTGRES_USER manquant dans .env}"
: "${POSTGRES_DB:?POSTGRES_DB manquant dans .env}"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo "==> 1/5  Build des images + démarrage (détaché)…"
$COMPOSE up -d --build

echo "==> 2/5  Attente de Postgres (healthcheck)…"
cid="$($COMPOSE ps -q postgres)"
until [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null || echo starting)" = "healthy" ]; do
  printf '.'; sleep 3
done
echo " ok"

echo "==> 3/5  Application des migrations SQL (ordre numérique, _dev_seed exclu)…"
for f in backend/database/migrations/[0-9]*.sql; do
  name="$(basename "$f")"
  echo "    - $name"
  # ON_ERROR_STOP=0 : sur un redéploiement, les objets déjà créés génèrent une erreur
  # bénigne que l'on ignore (les migrations ne sont pas toutes idempotentes).
  $COMPOSE exec -T postgres psql -v ON_ERROR_STOP=0 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -f "/migrations/$name" >/dev/null 2>&1 || true
done

echo "==> 4/5  Administrateur + catalogue de skills…"
if [ -n "${FIRST_ADMIN_EMAIL:-}" ]; then
  $COMPOSE exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -q -c \
    "INSERT INTO users (email, name, role) VALUES ('${FIRST_ADMIN_EMAIL}', 'Administrateur', 'super_admin') ON CONFLICT (email) DO UPDATE SET role='super_admin', actif=true;" \
    && echo "    super_admin : ${FIRST_ADMIN_EMAIL}"
fi
$COMPOSE exec -T backend sh -c "PYTHONPATH=. python scripts/seed_skills_catalogue.py" \
  && echo "    catalogue de skills : ok" || echo "    (seed skills ignoré — relançable plus tard)"

echo "==> 5/5  État des services :"
$COMPOSE ps
echo
echo "Terminé. Suivre les logs :  $COMPOSE logs -f backend"
