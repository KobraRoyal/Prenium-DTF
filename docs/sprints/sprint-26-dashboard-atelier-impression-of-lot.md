# Sprint 26 - Dashboard Atelier et impression des OF en lot

## Objectif

Tour de contrôle Atelier : émettre les PDF OF des commandes soumises, puis contrôler et produire dans le pilotage.

## Parcours livré

- quatre KPI : OF non imprimés, à contrôler, corrections client, lien pilotage ;
- **pas de bandeau « Prochain geste »** sur la tour de contrôle (supprimé du template + masqué en CSS v55 sur `.atelier-dashboard`) ;
- file limitée aux commandes soumises dont le PDF OF n'a pas encore été émis ;
- impression groupée possible même si les visuels sont encore à contrôler ;
- après émission PDF, la commande disparaît de la tour de contrôle ;
- contrôle, métrage, machine et production : `/staff/atelier/pilotage/` ;
- sélection manuelle ou bouton « Imprimer tous les OF non imprimés » (20 max., plus récentes d'abord).

## Règles métier

- affichage : `production_job.of_document_issued_at` est vide et statut ≠ terminé ;
- impression lot : commande soumise, OF non émis (validation Atelier non requise) ;
- émission PDF : horodatage `of_document_issued_at` + audit `production.manufacturing_orders_marked_issued` ;
- limite serveur : 20 OF par lot ;
- un OF terminé n'apparaît plus dans la file.

## Fichiers principaux

- `backend/apps/production/models.py` — `of_document_issued_at`
- `backend/apps/production/services/manufacturing_order_batch.py`
- `backend/apps/production/services/dashboard.py`
- `backend/templates/portal/staff/dashboard.html`
- `tests/production/test_dashboard_and_batch.py`

## Hors périmètre

- confirmation impression machine DTF (pilotage) ;
- génération asynchrone ou archivage permanent des lots PDF.
