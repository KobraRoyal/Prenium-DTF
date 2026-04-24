# prenium-dtf.com via IDS supply

Base de travail du projet **SaaS e-commerce premium DTF** développé avec une approche **Codex / vibe coding**.

Ce repo sert à la fois de :
- socle documentaire,
- cadre de gouvernance Codex,
- base d’architecture,
- suivi d’avancement par sprints,
- point d’entrée du futur code applicatif.

## Structure du repo

- `AGENTS.md`  
  Règles globales du projet pour Codex : architecture, sécurité, DRY, SRP, tests, définition de terminé.

- `.agents/skills/`  
  Skills réutilisables pour Codex : planning de feature, review permissions, accès fichiers sécurisé, Google Drive, Sendcloud, workflow, tests, UI.

- `docs/master-plan/`  
  Plan directeur du projet et roadmap globale.

- `docs/sprints/`  
  Découpage par sprints avec objectifs, tâches, tests et critères de validation.

- `docs/security/`  
  Baseline sécurité, stratégie de tests, matrice de tests.

- `docs/architecture/`  
  Structure projet, domaines métier, ADR, stratégie subagents, bonnes pratiques Codex.

- `docs/product-design/`  
  Guides UX/UI front-office et backoffice.

- `docs/prompts/`  
  Templates de prompts pour feature, review sécurité et lancement de sprint.

- `docs/tracking/`  
  Suivi projet, risques, décisions.

- `backend/`  
  Futur backend Django.

- `frontend/`  
  Futur front-office / backoffice moderne.

- `infra/`  
  Docker, reverse proxy, déploiement, configuration infra.

- `scripts/`  
  Scripts utilitaires projet.

- `tests/`  
  Organisation des tests unitaires, intégration, e2e et sécurité.

## Ordre de lecture recommandé

1. `AGENTS.md`
2. `docs/master-plan/PLAN_DEVELOPPEMENT_SAAS_DTF_V1.md`
3. `docs/master-plan/ROADMAP_EXECUTION.md`
4. `docs/sprints/SPRINTS_INDEX.md`
5. `docs/security/SECURITY_BASELINE.md`

## Mode de travail recommandé

1. Lire les règles dans `AGENTS.md`
2. Choisir le sprint actif dans `docs/sprints/`
3. Préparer le plan d’implémentation
4. Développer lot par lot
5. Ajouter les tests en même temps
6. Mettre à jour la documentation du sprint et le tracking projet

## Exigences non négociables

- isolation stricte des données client
- permissions objet par objet
- accès fichiers sécurisé
- logique métier centralisée
- architecture DRY et SRP
- tests à chaque niveau
- documentation maintenue à jour

## Statut

Repo initial de cadrage et de pilotage, prêt à accueillir :
- le socle Docker,
- le backend Django,
- le front moderne,
- les intégrations Google Drive et Sendcloud,
- le workflow de production DTF.    