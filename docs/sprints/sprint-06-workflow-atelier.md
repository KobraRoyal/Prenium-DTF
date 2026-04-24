# Sprint 06 — Workflow production + ordre de fabrication

> Ce sprint ouvre le domaine atelier sur une base minimale mais sécurisée, sans
> implémenter encore le scan code-barres, l’expédition Sendcloud ni le PDF
> avancé.

## Objectif
Livrer une base sécurisée pour :
- créer un workflow production minimal lié à `Order` ;
- centraliser les transitions de statuts dans un service dédié ;
- historiser chaque changement de statut ;
- exposer une consultation staff dédiée du workflow ;
- exposer une transition staff dédiée ;
- construire un ordre de fabrication simple exploitable côté staff ;
- journaliser les changements sensibles via audit.

## Périmètre
- app Django dédiée `production`
- modèle `ProductionJob` lié en `OneToOne` à `Order`
- modèle `ProductionJobTransition` pour l’historique
- machine à états minimale `queued` / `in_progress` / `ready_to_ship` / `blocked` / `completed`
- permissions staff dédiées `production.view_productionjob` et `production.transition_productionjob`
- route staff de consultation
- route staff de transition
- ordre de fabrication simple sérialisé dans la réponse staff
- audit minimal de lecture et de changement de statut
- préparation future du scan/barcode via champ `source` sur les transitions

## Hors périmètre
- scan code-barres
- Sendcloud
- paiement
- facturation
- PDF atelier avancé
- automatisation complexe

## Tâches
- [x] créer l’app `production` et la brancher au projet
- [x] ajouter `ProductionJob` et `ProductionJobTransition`
- [x] définir une machine à états minimale avec refus par défaut
- [x] centraliser les transitions dans `ProductionWorkflowService`
- [x] exposer un endpoint staff de consultation du workflow
- [x] exposer un endpoint staff de transition
- [x] produire un ordre de fabrication simple exploitable
- [x] ajouter les permissions staff dédiées
- [x] couvrir transitions valides / invalides, permissions et non-régression
- [x] mettre à jour décisions, risques et statut projet

## Hypothèses
- la commande reste le centre métier et le workflow atelier ne remplace pas `Order.status`
- le client n’a aucune route dédiée au domaine production dans ce sprint
- l’ordre de fabrication reste une projection JSON staff ; aucun PDF n’est généré ici
- `manufacturing_order_number` sert de repère atelier minimal sans figer encore le futur scan

## Implémentation livrée
- `ProductionJob` porte l’état atelier courant, les repères temporels, l’ordre de fabrication minimal et le dernier acteur de transition
- `ProductionJobTransition` historise chaque mutation avec `from_status`, `to_status`, `changed_by`, `reason` et `source`
- `ProductionWorkflowService` encapsule :
  - la création idempotente du job production pour une commande
  - la matrice de transitions autorisées
  - le refus par défaut des transitions inconnues ou interdites
  - l’audit des consultations, des transitions acceptées et des transitions rejetées
  - la construction d’un ordre de fabrication simple incluant commande, lignes, uploads, contrôle fichier et état de sync Drive
- les routes staff dédiées sont :
  - `GET /api/staff/production/orders/<order_public_id>/`
  - `POST /api/staff/production/orders/<order_public_id>/transition/`
- l’écriture commande initialise désormais le job production minimal via le service dédié, sans logique critique dans la vue
- aucune route client n’expose le workflow production ni les détails atelier internes

## Validations exécutées
- [x] `./.venv/bin/python -m ruff check backend/apps/orders/services/orders.py backend/apps/production backend/apps/accounts/permissions.py tests/production`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py makemigrations --check --dry-run`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py check`
- [x] `cd backend && DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/production -q`
- [x] `cd backend && DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/orders ../tests/customers ../tests/accounts ../tests/uploads ../tests/production -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] logs/audit ajoutés si nécessaire
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour
