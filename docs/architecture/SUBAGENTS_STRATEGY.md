# Stratégie des agents spécialisés

La politique canonique et les règles de routage sont décrites dans
[`CODEX_AGENT_ORCHESTRATION.md`](CODEX_AGENT_ORCHESTRATION.md). Les profils Codex
exécutables vivent dans `.codex/agents/` :

- `ids_explorer` : reconnaissance rapide en lecture seule ;
- `ids_qa` : tests, logs et triage de régression ;
- `ids_backend_worker` : implémentation Django bornée ;
- `ids_ui_worker` : templates, HTMX, Alpine et CSS bornés ;
- `ids_security_reviewer` : revue indépendante des surfaces sensibles ;
- `ids_domain_architect` : revue des modèles, migrations et frontières métier.

Les profils historiques `.agents/subagents/landing-conversion-agent.md` et
`.agents/subagents/pixel-perfect-ui-agent.md` restent des guides UI spécialisés.
Les recettes `.goose/` forment un autre runtime et ne sont pas pilotées par la
configuration Codex.

Règles essentielles : un seul écrivain par groupe de fichiers, revue sécurité
indépendante pour toute feature sensible, et intégration finale par l’agent racine.
