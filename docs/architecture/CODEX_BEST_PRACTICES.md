# Codex — meilleures pratiques appliquées au projet

## Principes
- Utiliser un fichier `AGENTS.md` pour charger les règles du projet automatiquement.
- Demander un plan avant d’implémenter les tâches complexes.
- Préférer des instructions réutilisables plutôt que de réécrire les mêmes contraintes à chaque prompt.
- Découper le travail en sprints courts avec objectifs, fichiers ciblés, tests et critères d’acceptation.
- Utiliser des agents spécialisés pour l’architecture, la sécurité, le backend, le front et les tests.
- Utiliser des skills dédiés pour les tâches répétitives : permissions, revues sécurité, migrations, intégrations externes, tests.

## Traduction concrète pour ce projet
- `AGENTS.md` au root du repo
- dossier `skills/` pour les workflows récurrents
- dossier `prompts/` pour les prompts standardisés
- dossier `sprints/` pour lot par lot
- mise à jour systématique des plans et sous-plans après chaque lot
