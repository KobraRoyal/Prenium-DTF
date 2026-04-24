#!/bin/sh
# Recompile Tailwind (app.css) puis recopie les statiques dans le volume Docker (nginx).
# À lancer depuis la racine du dépôt après modification CSS ou si /login/ semble « figé ».
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/backend"
npm run build:css
cd "$ROOT"
docker compose exec web sh -c 'cd /app/backend && python manage.py collectstatic --noinput'
echo "OK : app.css régénéré et collectstatic exécuté dans le service web."
