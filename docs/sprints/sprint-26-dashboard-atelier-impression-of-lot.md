# Sprint 26 - Dashboard Atelier et impression des OF en lot

## Objectif

Remplacer le dashboard générique par une file de travail orientée production et permettre l'impression sécurisée de plusieurs ordres de fabrication depuis les dernières commandes reçues.

## Audit avant refonte

- l'autorisation Commandes était répétée dans le hero, une carte et un KPI ;
- les cartes `Contrats permissions` et `Signal atelier` n'apportaient aucune décision opérationnelle ;
- les KPI comptaient les lignes affichées au lieu des commandes à traiter ;
- la table affichait prix et statut commercial, mais pas la validation humaine des fichiers ;
- aucun téléchargement multi-OF n'était disponible.

## Parcours livré

- quatre KPI utiles : à contrôler, corrections client, OF prêts, en production ;
- douze dernières commandes soumises, triées de la plus récente à la plus ancienne ;
- affichage compact de la commande, du numéro OF, du client, des fichiers et de la production ;
- prochaine action contextualisée vers Contrôle, Production ou Expédition ;
- sélection manuelle des OF éligibles ;
- action directe `Imprimer les 5 derniers OF prêts` ;
- fusion dans un PDF unique, un OF complet par commande ;
- limite serveur de 20 OF par lot.

## Règles métier

- un OF n'est imprimable en lot que si la commande est soumise ;
- la commande doit contenir au moins un fichier ;
- tous les fichiers doivent être approuvés par l'Atelier ;
- un OF terminé n'est pas réimprimable depuis la sélection de masse ;
- l'action automatique prend uniquement les cinq commandes approuvées encore en file Atelier ;
- les contrôles sont répétés côté serveur, indépendamment de l'état des cases à cocher.

## Sécurité et audit

- accès staff obligatoire ;
- permissions `orders.view_order` et `production.view_productionjob` obligatoires ;
- aucune route client ni URL publique ajoutée ;
- identifiants UUID validés, dédupliqués et limités ;
- chaque téléchargement crée l'événement d'audit `production.manufacturing_orders_batch_downloaded` ;
- réponse PDF privée avec `Cache-Control: private, no-store`.

## Fichiers principaux

- `backend/apps/production/services/dashboard.py`
- `backend/apps/production/services/manufacturing_order_batch.py`
- `backend/apps/portal/views_staff_dashboard.py`
- `backend/apps/portal/views_staff_documents.py`
- `backend/templates/portal/staff/dashboard.html`
- `backend/static_src/css/components/product-shell.css`
- `tests/production/test_dashboard_and_batch.py`

## Checklist

- [x] logique dashboard centralisée dans un service ;
- [x] règles d'éligibilité et fusion PDF centralisées dans un service ;
- [x] permissions et audit ajoutés ;
- [x] tests ciblés service, PDF, audit, permissions et UI ;
- [x] contrôle visuel desktop et mobile ;
- [x] rendu des deux pages du PDF multi-OF exemple ;
- [x] Ruff, Django, migrations et suite globale : 384 tests réussis.

## Hors périmètre

- impression automatique sans validation Atelier ;
- modification de la numérotation OF ;
- génération asynchrone ou archivage permanent des lots PDF.
