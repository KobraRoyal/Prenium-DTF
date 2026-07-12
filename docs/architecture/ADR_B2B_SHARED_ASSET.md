# ADR — Asset partagé projets B2B / commandes

## Statut

Accepté pour le Sprint 22.

## Contexte

`OrderUpload` stocke aujourd'hui directement le fichier et exige une commande. Un projet B2B doit
conserver les originaux, versionner les remplacements et exister avant `Order`.

## Décision

Ajouter dans l'app `uploads` :

- `Asset` : identité tenant-scoped et version courante ;
- `AssetVersion` : fichier original immuable, hash et numéro de version ;
- `AssetAnalysis` : résultat technique et miniature ;
- un lien nullable `OrderUpload.asset_version` ;
- un lien nullable `B2BOrderProjectItem.asset`.

Le backfill crée un asset/version pour chaque `OrderUpload` existant en réutilisant le nom de
stockage actuel. Aucun fichier n'est déplacé ou recopié pendant la migration.

## Conséquences

- Les nouveaux fichiers projet utilisent `/assets/<customer_uuid>/<asset_uuid>/vN/`.
- Un remplacement ajoute une version et conserve toutes les versions précédentes.
- Les téléchargements restent médiés par le backend.
- L'analyse est asynchrone via Celery et idempotente par version.
- `OrderUpload` reste compatible ; ses champs historiques ne sont pas supprimés dans ce sprint.

## Alternatives refusées

- rendre `OrderUpload.order` nullable : mélange des agrégats et risque de régression ;
- créer `ProjectUpload` : duplication du stockage, des contrôles et du versioning ;
- déplacer les fichiers existants en migration : rollback et déploiement trop risqués.

## Rollback

Les nouveaux liens sont nullable. Le code précédent peut ignorer les tables Asset ; les fichiers
historiques restent à leur emplacement initial. Aucun rollback ne doit supprimer les fichiers avant
vérification des références.
