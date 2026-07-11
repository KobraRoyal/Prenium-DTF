# Premium DTF — Feature prise de commande B2B

Ce dossier contient le prompt à utiliser avec Codex pour développer la nouvelle fonctionnalité de projet de commande B2B dans le projet Premium DTF existant.

## Utilisation

1. Copier ce dossier à la racine du dépôt Premium DTF.
2. Ouvrir le fichier `CODEX_PROMPT.md`.
3. Donner son contenu à Codex depuis la racine du dépôt.
4. Laisser Codex auditer le projet avant toute modification.
5. Vérifier le rapport final, les migrations et les tests avant de fusionner.

## Objectif

Ajouter une couche `B2BOrderProject` avant la création de la commande définitive, sans casser le workflow de production actuel.

## Premier sprint inclus

- Audit du dépôt
- Modèle `B2BOrderProject`
- Modèle `B2BOrderProjectItem`
- Statuts et transitions
- Feature flag
- Permissions B2B
- CRUD API
- Liste et détail des projets
- Sauvegarde automatique
- Audit minimal
- Migrations
- Tests

## Non inclus dans ce premier sprint

- Analyse d'image
- Calcul DPI
- Estimation de métrage
- Nesting
- Workflow OPS complet
- Conversion en commande
- Notifications réelles
- Connexion RIP
