# Sprint 29 - Consignes support et dimensions dans le contrôle et l’OF

## Objectif

Garantir que les informations confirmées par le client dans le configurateur DTF suivent le visuel jusqu’au contrôle Atelier et à l’ordre de fabrication : taille finale en millimètres et couleur du support.

## Audit avant évolution

- la couleur unie était copiée dans le fichier de commande mais absente du contrôle et de l’OF ;
- la sélection `Multicolore` était perdue lors de la conversion en commande ;
- largeur et hauteur restaient uniquement dans la préparation B2B ;
- l’Atelier voyait les dimensions techniques en pixels, pas la taille finale demandée par le client ;
- l’OF affichait le fichier, la quantité et les statuts sans les consignes de pose.

## Parcours livré

- chaque `OrderUpload` conserve un instantané nullable `width_mm` / `height_mm` ;
- la couleur support accepte une valeur HEX ou `Multicolore` ;
- la conversion d’une préparation B2B copie dimensions, quantité et couleur ;
- une migration rétroactive récupère ces données pour les commandes déjà converties ;
- le panneau `Contrôle` affiche `Taille demandée` et `Couleur du support` pour chaque visuel ;
- un échantillon de couleur accompagne le code HEX dans l’interface ;
- l’OF affiche les mêmes consignes sous le nom du fichier, sans nouvelle section redondante ;
- les anciennes commandes sans information affichent explicitement `Non renseignée`.

## Architecture et sécurité

- `OrderUploadProductionSpecService` fournit un contrat commun au panneau et au PDF ;
- les dimensions sont figées sur la commande et ne dépendent plus d’une lecture mutable du projet source ;
- les contraintes DB imposent une paire largeur/hauteur complète et strictement positive ;
- le backfill rapproche uniquement une commande convertie et sa version d’asset confirmée ;
- aucune route ni permission supplémentaire ;
- aucune donnée n’est exposée hors du scope commande existant ;
- aucun audit supplémentaire : la copie intervient dans la conversion déjà auditée et ne constitue pas une action opérateur distincte.

## Fichiers principaux

- `backend/apps/uploads/models.py`
- `backend/apps/uploads/migrations/0016_orderupload_production_specs.py`
- `backend/apps/uploads/services/production_specs.py`
- `backend/apps/b2b_order_projects/services/checkout.py`
- `backend/apps/portal/views_staff_reviews.py`
- `backend/templates/portal/staff/panels/inspection.html`
- `backend/apps/production/services/workflow.py`
- `backend/apps/production/services/manufacturing_order_pdf.py`
- `tests/uploads/test_production_specs.py`
- `tests/uploads/test_order_upload_reviews.py`
- `tests/b2b_order_projects/test_checkout.py`
- `tests/production/test_workflow_api.py`

## Checklist

- [x] modèle et contraintes DB ajoutés ;
- [x] migration et backfill des commandes converties ;
- [x] copie des dimensions et couleurs lors des nouvelles conversions ;
- [x] couleur multicolore préservée ;
- [x] contrat de présentation partagé entre Contrôle et OF ;
- [x] affichage desktop et mobile validé ;
- [x] rendu PDF A4 contrôlé visuellement ;
- [x] permissions et isolation existantes conservées ;
- [x] Ruff, Django, migrations et suite globale validés (`391 passed`).

## Hors périmètre

- modification des dimensions depuis la fiche Atelier ;
- recalcul automatique des dimensions client à partir des pixels ;
- modification de la couleur du support après transmission de la commande.
