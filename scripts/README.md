# Scripts

Après modification de templates Django ou de `backend/static_src/css/` en **Docker** : `docker compose restart web` (relance Gunicorn + `collectstatic` dans l’entrypoint) pour voir le HTML et le CSS à jour — le moteur de templates met en cache les gabarits dans les workers.

Scripts utilitaires :
- bootstrap local
- quality checks
- sauvegardes
- maintenance

Validation de l’orchestration Codex :

```bash
make agents-check
```

Ce contrôle sans dépendance applicative valide `.codex/config.toml`, les profils
`.codex/agents/*.toml`, leur matrice modèle/effort et les invariants de sécurité
obligatoires. Le target utilise Python 3.12 dans Docker ; pre-commit fournit son
fallback TOML isolé pour les postes encore sous Python 3.10.
