# Sprint 05 — Synchronisation Google Drive des fichiers de commande

> Ce sprint prolonge les lots uploads et contrôle fichier avec une première
> synchronisation documentaire vers un Shared Drive, sans ouvrir encore le
> workflow atelier, le partage public ni l'édition distante.

## Objectif
Livrer une base sécurisée pour :
- créer un dossier Drive par commande ;
- synchroniser les fichiers de commande vers Google Drive ;
- stocker les références Drive en base ;
- suivre un statut simple de synchronisation ;
- préparer la suite sans implémenter encore le workflow atelier.

## Périmètre
- mapping DB minimal pour dossier commande et sync fichier
- arborescence Drive créée par le backend uniquement
- synchronisation d'un fichier uploadé vers `00_source_client`
- statut simple `pending` / `synced` / `failed`
- gestion minimale des erreurs et idempotence de base
- consultation staff séparée de l'état de sync
- audit minimal de création dossier et de sync

## Hors périmètre
- partage public Drive
- lien Drive brut exposé au client
- édition ou suppression distante avancée
- workflow production
- Sendcloud
- paiement
- facturation

## Tâches
- [x] créer le document sprint et le maintenir à jour
- [x] ajouter le mapping dossier commande Drive
- [x] ajouter le mapping de sync Drive par upload
- [x] encapsuler l'API Google Drive dans un service dédié
- [x] créer l'arborescence Shared Drive par commande
- [x] synchroniser le fichier uploadé vers Drive
- [x] brancher une tâche asynchrone minimale et idempotente
- [x] exposer un état de sync côté staff avec permission dédiée
- [x] couvrir les erreurs API mockées et les non-régressions
- [x] mettre à jour décisions, risques et statut projet

## Hypothèses
- un Shared Drive dédié existe déjà et son identifiant est fourni via variable d'environnement
- les credentials du compte de service sont injectés via variable d'environnement uniquement
- le backend reste la source de vérité ; Google Drive n'est qu'une projection documentaire
- l'identifiant `GOOGLE_DRIVE_ROOT_FOLDER_ID` cible le dossier racine métier sous lequel créer l'arborescence `Commandes/AAAA/MM/...`

## Implémentation livrée
- `OrderDriveFolder` mappe la commande vers l'arborescence Drive créée par le backend
- `OrderUploadDriveSync` stocke le statut `pending` / `synced` / `failed`, les références Drive utiles et l'erreur de dernier essai
- `OrderUploadDriveSyncService` encapsule la création d'arborescence, l'upload idempotent minimal et l'audit
- `sync_order_upload_to_drive_task` déclenche la synchronisation en tâche Celery quand `GOOGLE_DRIVE_SYNC_ENABLED=true`
- la route staff `drive-sync/` exige la permission dédiée `uploads.view_orderuploaddrivesync`
- aucune route client ne renvoie d'ID Drive, de lien brut Drive ni de détail sensible

## Validations exécutées
- [x] `./.venv/bin/python -m ruff check backend/apps/uploads backend/apps/accounts tests/uploads`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py makemigrations --check --dry-run`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py check`
- [x] `cd backend && DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/uploads/test_drive_sync.py ../tests/uploads/test_upload_service.py ../tests/uploads/test_upload_api.py -q`
- [x] `cd backend && DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/orders ../tests/customers ../tests/accounts ../tests/uploads -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] logs/audit ajoutés si nécessaire
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour
