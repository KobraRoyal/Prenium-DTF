# Scripts

Après modification de templates Django ou de `backend/static_src/css/` en **Docker** : `docker compose restart web` (relance Gunicorn + `collectstatic` dans l’entrypoint) pour voir le HTML et le CSS à jour — le moteur de templates met en cache les gabarits dans les workers.

Scripts utilitaires :
- bootstrap local
- quality checks
- sauvegardes
- maintenance
