# Sprint 07 — Code-barres + scan atelier

> Ce sprint formalise la couche scan atelier sur la base du workflow production
> livrée au Sprint 06, sans ouvrir de surface client ni ajouter d’interface
> complexe.

## Objectif
Livrer une base sécurisée pour :
- attribuer un identifiant scannable unique à chaque `ProductionJob` ;
- résoudre rapidement un scan vers le bon job de production ;
- autoriser une transition atelier rapide déclenchée par scan ;
- journaliser les scans et leurs résultats ;
- exposer une surface staff simple, exploitable au poste atelier.

## Périmètre
- identifiant scan unique sur `ProductionJob`
- génération automatique de cet identifiant à la création du job
- endpoint staff de résolution de scan
- endpoint staff de transition via scan
- log minimal des scans et des résolutions
- permissions staff dédiées et refus par défaut
- payload JSON simple pour poste atelier
- compatibilité stricte avec `ProductionWorkflowService`

## Hors périmètre
- matériel scanner réel
- interface front riche ou temps réel
- PDF avancé
- Sendcloud
- paiement et facturation
- refonte du workflow production

## Tâches
- [x] ajouter l’identifiant scannable unique sur `ProductionJob`
- [x] générer automatiquement cet identifiant à la création
- [x] créer le service de résolution de scan staff-only
- [x] créer le service de transition via scan en réutilisant le workflow central
- [x] ajouter un log minimal des scans et des tentatives refusées
- [x] exposer un payload atelier simple et sûr
- [x] ajouter les permissions staff dédiées nécessaires
- [x] couvrir scan valide / invalide, staff autorisé / refusé, transition autorisée / refusée
- [x] vérifier la non-régression sur workflow production, commandes et uploads
- [x] mettre à jour décisions, risques et statut projet

## Hypothèses
- le scan identifie un `ProductionJob` ou son ordre sans jamais ouvrir d’accès client
- la résolution et la transition passent par le backend, jamais directement par les vues
- la logique critique reste centralisée dans le service de workflow existant
- l’identifiant scannable doit rester non prédictible et non exposant
- une surface JSON staff suffit pour le poste atelier ; aucune UI complexe n’est requise

## Implémentation livrée
- `ProductionJob` reçoit désormais un `scan_identifier` opaque et unique, auto-généré à la création et exposé dans le payload staff comme valeur de scan, barcode Code 128 logique et QR logique.
- `ProductionJobScanLog` historise les scans de résolution et de transition, y compris les scans inconnus et les transitions rejetées.
- `ProductionScanService` centralise :
  - la normalisation et la résolution du scan ;
  - la journalisation minimale des scans ;
  - l’audit des scans acceptés et refusés ;
  - la transition via scan en réutilisant strictement `ProductionWorkflowService`.
- les routes staff dédiées sont :
  - `POST /api/staff/production/scans/resolve/`
  - `POST /api/staff/production/scans/transition/`
- les permissions staff dédiées au scan sont :
  - `production.scan_productionjob`
  - `production.scan_transition_productionjob`
- aucune route client n’expose le scan, et aucune transition par scan ne contourne la matrice centrale de workflow.

## Validations attendues
- [x] identifiant scan généré automatiquement et unique
- [x] scan valide résout le bon `ProductionJob`
- [x] scan invalide est refusé
- [x] client refusé sur les routes scan
- [x] staff non autorisé refusé
- [x] scan + transition valide OK
- [x] scan + transition invalide refusée
- [x] log de scan créé
- [x] non-régression workflow production / orders / uploads / audit

## Validations exécutées
- [x] `./.venv/bin/python -m ruff check backend/apps/accounts/permissions.py backend/apps/production tests/production`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py makemigrations --check --dry-run`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py check`
- [x] `cd backend && DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/production -q`
- [x] `cd backend && DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/orders ../tests/uploads ../tests/accounts ../tests/customers ../tests/production -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] logs / audit ajoutés si nécessaire
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour
