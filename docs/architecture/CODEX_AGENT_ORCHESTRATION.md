# Orchestration Codex des sous-agents

## Objectif

Cette politique réduit le coût en tokens sans diminuer les exigences de sécurité du
projet. La racine orchestre, conserve la vision d’ensemble et reste responsable de
l’intégration. Les sous-agents reçoivent uniquement des tâches bornées et
indépendantes.

Les fichiers exécutables de référence sont `.codex/config.toml` et
`.codex/agents/*.toml`. Les workflows `.goose/` restent indépendants et inchangés.
Les anciens profils `.agents/subagents/*.md` servent seulement de documentation
spécialisée UI et ne remplacent pas les agents Codex natifs.

## Matrice de routage

| Agent | Modèle / effort | Droits | Usage |
|---|---|---|---|
| `ids_explorer` | `gpt-5.6-terra` / low | lecture seule | Cartographie de fichiers, patterns, dépendances et tests ciblés |
| `ids_qa` | `gpt-5.6-terra` / medium | tests et diagnostic | Triage de logs, tests ciblés, analyse de régression |
| `ids_backend_worker` | `gpt-5.6-sol` / medium | écriture bornée | Une tranche Django, avec propriété exclusive de ses fichiers |
| `ids_ui_worker` | `gpt-5.6-sol` / medium | écriture bornée | Une tranche templates, HTMX, Alpine, CSS ou JavaScript |
| `ids_security_reviewer` | `gpt-5.6-sol` / high | lecture seule | Isolation tenant, RBAC, fichiers, webhooks, secrets et audit |
| `ids_domain_architect` | `gpt-5.6-sol` / high | lecture seule | Modèles, migrations, services, contraintes et transitions |

Une indisponibilité de modèle ne doit jamais provoquer une rétrogradation silencieuse
d’un rôle sensible vers Terra. La racine suspend la délégation concernée ou hérite
temporairement du modèle principal, puis documente le changement de matrice.

## Décision de délégation et budget

- Tâche triviale ou séquentielle : aucun sous-agent.
- Exploration, documentation, recherche de tests ou triage : un agent Terra.
- Feature bornée : au plus un agent de lecture et un agent écrivain Sol.
- Changement multi-tenant, permission, fichier, webhook, secret ou audit : relecture
  obligatoire par `ids_security_reviewer`.
- Modèle, migration, état métier ou frontière de service : avis de
  `ids_domain_architect` avant l’écriture risquée.
- Maximum projet : trois sous-agents actifs et une profondeur. Aucun agent ne crée
  une chaîne de délégation.

Codex ne fournit pas de plafond de tokens par profil TOML. Le budget est donc
contractuel : périmètre de fichiers explicite, aucune exploration du dépôt entier sans
motif, aucun log brut, aucun contexte répété et compte rendu concis. La racine ne
duplique pas une exploration déjà confiée à un agent.

## Contrat d’une mission

Chaque délégation précise :

1. le résultat attendu et le contexte minimum ;
2. les fichiers ou domaines autorisés ;
3. les invariants de sécurité applicables ;
4. si l’agent peut écrire, exécuter des tests ou doit rester en lecture seule ;
5. les critères de fin et le format du compte rendu.

Un seul agent peut écrire dans un même ensemble de fichiers. Les autres agents
inspectent ou valident. La racine résout les conflits, applique les changements
transverses, exécute les contrôles finaux et décide de la livraison.

## Garde-fous IDS Hub

- Le scope `Customer` et les permissions objet restent vérifiés côté serveur.
- Les ressources exposées utilisent `public_id`, jamais un identifiant incrémental.
- Les fichiers restent médiés par le backend ou par une URL signée contrôlée.
- Toute mutation sensible prévoit audit, tests de permissions et accès croisé.
- L’UI ne devient jamais la source d’autorité d’une règle métier ou permission.
- Un agent de revue ne valide pas sa propre implémentation.

## Validation

```bash
make agents-check
pytest -q tests/core/test_codex_agent_contracts.py
pre-commit run --all-files
```

Le validateur sans dépendance applicative est exécuté par pre-commit et CI. Il
verrouille le nombre de threads,
la profondeur, les modèles, l’effort, les droits de lecture seule et les invariants
des rôles sensibles.

Référence officielle : [Codex — Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents.md).
