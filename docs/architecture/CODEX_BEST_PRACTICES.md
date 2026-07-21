# Codex — meilleures pratiques appliquées au projet

## Principes
- Utiliser un fichier `AGENTS.md` pour charger les règles du projet automatiquement.
- Demander un plan avant d’implémenter les tâches complexes.
- Préférer des instructions réutilisables plutôt que de réécrire les mêmes contraintes à chaque prompt.
- Découper le travail en sprints courts avec objectifs, fichiers ciblés, tests et critères d’acceptation.
- Utiliser des agents spécialisés pour l’architecture, la sécurité, le backend, le front et les tests.
- Utiliser des skills dédiés pour les tâches répétitives : permissions, revues sécurité, migrations, intégrations externes, tests.
- Router les tâches de lecture et de triage vers Terra, et réserver Sol aux écritures ou décisions à risque.
- Ne pas déléguer une tâche triviale et ne jamais faire écrire deux agents dans les mêmes fichiers.
- Valider les contrats avec `make agents-check` avant livraison.

## Traduction concrète pour ce projet
- `AGENTS.md` au root du repo
- dossier `skills/` pour les workflows récurrents
- dossier `prompts/` pour les prompts standardisés
- dossier `sprints/` pour lot par lot
- mise à jour systématique des plans et sous-plans après chaque lot
- configuration native `.codex/` et politique dans `docs/architecture/CODEX_AGENT_ORCHESTRATION.md`
