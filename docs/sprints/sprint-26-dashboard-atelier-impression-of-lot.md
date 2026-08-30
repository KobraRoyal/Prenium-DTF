# Sprint 26 - Dashboard Atelier et impression des OF en lot

## Objectif

Tour de contrôle Atelier : émettre les PDF OF des commandes soumises, puis contrôler et produire dans le pilotage.

## Parcours livré

- quatre KPI filtrants et exclusifs : OF non imprimés, à contrôler, corrections client,
  fichiers validés ;
- **pas de bandeau « Prochain geste »** sur la tour de contrôle (supprimé du template + masqué en CSS v55 sur `.atelier-dashboard`) ;
- file limitée aux commandes soumises dont le PDF OF n'a pas encore été émis ;
- impression groupée possible même si les visuels sont encore à contrôler ;
- après émission PDF, la commande quitte la file d'impression et rejoint le KPI correspondant
  à son contrôle fichier ;
- contrôle, métrage, machine et production : `/staff/atelier/pilotage/` ;
- une seule action d'impression visible à la fois : « Imprimer le lot » sans sélection,
  remplacée par « Imprimer la sélection (n) » dès qu'un OF est coché ;
- lot limité à 20 OF, plus récentes d'abord ;
- dans l'étape « Contrôle fichiers » du Pilotage, lien staff vers le fichier HD synchronisé
  sur Drive et demande de correction client (motif, commentaire, e-mail transactionnel).
- le Pilotage n'affiche plus le rail « Contrôle / Production / Expédition / Facturation » :
  le parcours opérateur séquentiel constitue l'unique repère d'avancement ; la fiche complète
  reste accessible par « Ouvrir le dossier ».

## Règles métier

- affichage : `production_job.of_document_issued_at` est vide et statut ≠ terminé ;
- impression lot : commande soumise, OF non émis (validation Atelier non requise) ;
- émission PDF, en lot ou à l'unité : horodatage `of_document_issued_at` + audit
  `production.manufacturing_orders_marked_issued` ;
- contrôle Atelier : impossible tant que `of_document_issued_at` est vide ;
- le lien HD Drive est affiché uniquement aux utilisateurs autorisés à consulter les uploads et
  uniquement lorsque la synchronisation du fichier est terminée ;
- la demande de correction réutilise `OrderUploadReviewService`, reste bornée à la commande et
  déclenche la notification client via la file transactionnelle existante ;
- `À contrôler`, `Corrections client` et `Fichiers validés` portent uniquement sur les OF émis ;
- les compteurs du dashboard et les filtres `/staff/orders/` utilisent la même règle métier
  centralisée ;
- limite serveur : 20 OF par lot ;
- un OF terminé n'apparaît plus dans la file.

## Fichiers principaux

- `backend/apps/production/models.py` — `of_document_issued_at`
- `backend/apps/production/services/manufacturing_order_batch.py`
- `backend/apps/production/services/dashboard.py`
- `backend/apps/portal/views_staff_reviews.py` — contexte contrôle, permission et lien HD Drive
- `backend/templates/portal/staff/dashboard.html`
- `backend/templates/portal/staff/operations/_operator_workflow.html`
- `backend/templates/portal/staff/components/upload_correction_form.html`
- `tests/production/test_dashboard_and_batch.py`
- `tests/production/test_atelier_operations.py`

## Hors périmètre

- confirmation impression machine DTF (pilotage) ;
- génération asynchrone ou archivage permanent des lots PDF.
