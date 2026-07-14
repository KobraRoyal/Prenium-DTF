# Sprint 25 - PDF OF Atelier sans redondance

## Objectif

Rendre l'ordre de fabrication immédiatement exploitable par l'Atelier, distinguer sans ambiguïté le numéro d'OF de la référence commande et supprimer les informations imprimées en double.

## Audit avant refonte

- les uploads sans ligne de commande étaient affichés dans `Lignes & fichiers`, puis répétés dans `Fichiers client` ;
- le total TTC et la synchronisation Drive occupaient de la place sans aider la production ;
- le diagnostic automatique `ok` pouvait être compris comme une validation Atelier ;
- la référence commande n'était pas visible à côté du numéro d'OF ;
- les statuts et dates techniques étaient imprimés avec leurs valeurs brutes.

## Décisions

- conserver le numéro unique existant `OF-AAAAMMJJ-XXXXXXXX` ;
- afficher la commande avec sa référence publique courte `#XXXXXXXXXXXX` ;
- garder un seul numéro lisible d'OF dans le corps du document, associé au code-barres ;
- n'imprimer qu'une table de fichiers lorsque les lignes sont un fallback des uploads ;
- séparer visuellement `Diagnostic auto` et `Décision Atelier` ;
- retirer le prix et l'état Drive du PDF Atelier ;
- conserver une note client et une checklist de contrôle final compactes ;
- ne modifier ni les permissions, ni le modèle, ni la numérotation persistée.

## Sécurité et isolation

- le téléchargement reste médiatisé par la route staff et `view_productionjob` ;
- aucun chemin de stockage, identifiant Drive ou URL publique n'est ajouté au PDF ;
- la projection documentaire est chargée depuis la commande autorisée côté serveur ;
- aucun nouvel accès client ou inter-tenant n'est introduit.

## Fichiers du lot

- `backend/apps/production/services/workflow.py`
- `backend/apps/production/services/manufacturing_order_pdf.py`
- `tests/production/test_workflow_service.py`
- `tests/production/test_workflow_api.py`

## Checklist de validation

- [x] numéro d'OF distinct de la référence commande et identique au code de scan ;
- [x] décision Atelier intégrée à la projection documentaire ;
- [x] uploads fallback non imprimés une seconde fois comme prestations ;
- [x] prix et synchronisation Drive absents du PDF ;
- [x] téléchargement toujours refusé sans permission production ;
- [x] tests production ciblés : 23 réussis ;
- [x] rendu PNG de chaque page contrôlé visuellement ;
- [x] Ruff, suite globale (374 tests), `check` Django et migrations vérifiés.

## Hypothèse

Le numéro d'OF reste dérivé de la date de création de la commande et du premier segment de son UUID. Il est unique et différent de la référence courte affichée pour la commande, mais ce n'est pas une séquence métier indépendante de type `OF-2026-000123`. Une telle séquence demanderait une décision métier et une migration séparées.
