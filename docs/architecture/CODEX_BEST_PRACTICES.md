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

## Navigation économe avec Graphify

Graphify est installé au niveau utilisateur pour être disponible dans les tâches
Codex actuelles et futures. La règle globale n'interroge Graphify que lorsqu'un
projet possède déjà `graphify-out/graph.json`; elle ne déclenche jamais seule une
indexation sémantique payante.

Dans IDS Hub, le graphe initial est construit en mode code uniquement : extraction
AST locale, communautés sans nommage LLM et visualisation HTML désactivée. Le
fichier `.graphifyignore` exclut notamment les secrets, dépendances, bibliothèques
vendorielles, caches, sorties UI et médias.

Baseline mesurée le 2026-08-11 : 4 897 nœuds, 11 424 relations et une réduction
moyenne estimée à 12,8× par rapport à la lecture naïve du corpus. Ce chiffre est un
benchmark Graphify indicatif et doit être réévalué lorsque le dépôt évolue.

Commandes courantes :

```bash
graphify query "show the permission flow" --budget 1000
graphify path "Customer" "Order"
graphify explain "AssetService"
graphify update .
graphify benchmark graphify-out/graph.json
```

Pour reconstruire sans consommer de tokens de modèle :

```bash
graphify extract . --code-only --no-cluster --max-workers 4 --out .
graphify cluster-only . --no-label --no-viz
```

Le graphe sert uniquement à orienter la lecture. Pour l'isolation multi-tenant, les
permissions, les fichiers, les secrets et l'audit, Codex doit toujours relire le
code et les tests faisant autorité. Le graphe global inter-projets n'est pas activé,
afin d'éviter tout mélange implicite de contextes entre clients ou dépôts.
