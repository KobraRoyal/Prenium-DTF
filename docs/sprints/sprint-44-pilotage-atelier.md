# Sprint 44 — Pilotage Atelier rapide

## Objectif

Sortir les scans et transitions courantes des fiches commande afin qu'un opérateur puisse piloter
les OF en série, comprendre immédiatement les blocages et déclencher Sendcloud sans navigation
répétitive.

## Livré

- nouvelle console staff `/staff/atelier/pilotage/` avec recherche OF/client autofocus et usage douchette ;
- files `À traiter`, `À expédier`, `Terminés` et `Tous`, paginées par 25 OF ;
- transitions autorisées rendues en actions directes, avec note optionnelle repliée ;
- feedback inline, zone `aria-live` et toast après succès ou refus ;
- prérequis paiement/tarification expliqués sur la ligne avec accès direct à leur résolution ;
- déclaration Sendcloud préremplie et synchronisation du suivi dans la file d'expédition ;
- onglet Scan supprimé de la fiche commande et ancienne route conservée par redirection ;
- dashboard Atelier relié au Pilotage pour les prochaines actions de production et d'expédition ;
- helper formulaire Sendcloud mutualisé entre la fiche et la nouvelle console ;
- aucune migration de données.

## Contrats métier et sécurité

- les transitions passent exclusivement par `ProductionWorkflowService` ;
- l'expédition passe exclusivement par `ShipmentService` ;
- accès staff, permissions commande/production/scan et permissions de mutation contrôlés avant lookup ;
- permissions Sendcloud vérifiées séparément pour lecture et création ;
- refus de permission et mutations métier restent audités ;
- les notifications client existantes restent déclenchées aux jalons `En production` et `Prêt à expédier` ;
- aucun nom de machine, état interne ou historique d'impression ajouté aux vues client.

## Validation

- [x] 83 tests ciblés Pilotage, portail et cohérence UI ;
- [x] 41 tests de contrat d'architecture portail ;
- [x] suite globale : **769 réussis, 1 ignoré** ;
- [x] Django `check` et `makemigrations --check --dry-run` ;
- [x] Ruff et `git diff --check` ;
- [x] build CSS complet ;
- [x] recette authentifiée desktop 1440/1512 px et mobile 375 px, sans overflow ni erreur console ;
- [x] détecteur Impeccable exécuté une fois ; side-tab signalé puis remplacé par une bordure pleine ;
- [x] revue de finition Impeccable : `disposition: ship` ;
- [x] graphe Graphify rafraîchi.

## Checklist opérateur

- scanner ou rechercher un OF sans quitter la page ;
- voir le statut, la machine et la preuve d'impression utile ;
- lancer uniquement une transition autorisée ;
- comprendre un démarrage bloqué avant de cliquer ;
- déclarer une commande prête dans Sendcloud ;
- récupérer l'étiquette, ouvrir le suivi ou synchroniser son statut ;
- ouvrir la fiche seulement pour un contrôle détaillé ou une exception.
