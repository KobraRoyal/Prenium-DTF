# Goose kit — prenium-dtf.com via IDS supply

Ce dossier fournit une base **prête à adapter** pour piloter le projet avec **Goose** :
- configuration recommandée,
- stratégie multi-agents,
- routage provider/modèle,
- recettes (`recipes/`) pour planifier, implémenter et stabiliser,
- prompts et checklists de recette,
- exemples `.goosehints` / `.gooseignore`.

## Structure
- `config/` : exemples de configuration Goose
- `docs/` : conventions d’usage, sessions, provider strategy
- `recipes/` : recettes Goose réutilisables
- `subagents/` : rôles et responsabilités des agents
- `prompts/` : prompts de démarrage
- `project-files/` : fichiers à recopier à la racine du repo de code

## Ordre de mise en place
1. Lire `docs/provider-strategy.md`
2. Adapter `config/config.acp.example.yaml`
3. Copier `project-files/.goosehints.example` en `.goosehints` dans le repo du projet
4. Copier `project-files/.gooseignore.example` en `.gooseignore`
5. Importer ou exécuter les recettes de `recipes/`
6. Démarrer avec `recipes/research-codebase/recipe.yaml`, puis `create-plan`, puis `implement-plan`

## Important
Les recettes et configs ici sont fournies comme **templates adaptés à ton projet**. Vérifie les noms d’extensions, chemins et modèles disponibles dans ton installation Goose avant usage réel.
