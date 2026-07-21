# Sprint 32 — Orchestration Codex des sous-agents

## Objectif

Installer une orchestration projet native pour choisir le modèle adapté à chaque
tâche, réduire la consommation de tokens et conserver les garde-fous de sécurité et
de non-régression IDS Hub.

## Hypothèses

- Les profils `.codex/agents/*.toml` sont la source exécutable de Codex.
- Les recettes `.goose/` restent compatibles et ne sont pas modifiées.
- Le budget de tokens est piloté par le routage, le périmètre et la concision, car le
  format TOML des agents ne fournit pas de plafond dur par mission.

## Livrables

- Configuration projet : `.codex/config.toml`.
- Six profils spécialisés Terra/Sol dans `.codex/agents/`.
- Politique de délégation, propriété d’écriture et revue sécurité.
- Validateur stdlib, tests contractuels, hook pre-commit et étape CI.
- Documentation architecture, suivi et commandes développeur.

## Sécurité et régression

Ce lot ne modifie ni modèle Django, ni migration, ni permission applicative, ni route
métier. Le validateur exige les invariants `Customer`, `public_id`, audit et tests
cross-tenant pour les rôles backend, architecture et sécurité.

## Checklist de fin

- [x] Routage Terra/Sol documenté
- [x] Concurrence limitée à trois sous-agents et une profondeur
- [x] Un seul propriétaire d’écriture par ensemble de fichiers
- [x] Revue sécurité indépendante obligatoire sur les surfaces sensibles
- [x] Contrats exécutables et test négatif ajoutés
- [x] Hook pre-commit et CI configurés
- [x] Validateur et tests ciblés passés
- [x] Ruff et formatage des nouveaux fichiers passés
- [x] Contrôles Django et migrations passés
- [x] Suite complète sans régression : 478 tests passés

Réserve hors lot : `ruff format --check .` signale dix fichiers applicatifs antérieurs
non formatés. Aucun de ces fichiers n’a été modifié dans ce sprint.
