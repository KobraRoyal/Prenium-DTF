# Sprint 03 — Uploads sécurisés rattachés à la commande

> Ce sprint opérationnel ouvre le lot uploads après le mini Sprint 02.1 de hardening.
> Le stub historique [sprint-04-uploads-et-fichiers.md](/Users/kobrasolution/Library/CloudStorage/Dropbox/KBR_Python_Project/prenium-dtf.com-via-IDS-supply/docs/sprints/sprint-04-uploads-et-fichiers.md) reste conservé pour la continuité documentaire.

## Objectif
Livrer une base sécurisée pour l'upload de fichiers rattachés à une commande,
avec stockage protégé, accès client scoped, accès staff séparé, validation
serveur et audit minimal.

## Périmètre
- modèle `OrderUpload` rattaché à `Order`
- plusieurs fichiers par commande
- upload mono-fichier par requête
- liste, détail et téléchargement sécurisé client
- lecture et téléchargement sécurisé staff
- validation centralisée taille / MIME / fichier vide
- permission staff dédiée
- audit minimal upload / download

## Hors périmètre
- Google Drive
- workflow production
- paiement et facturation
- preview complexe
- OCR
- analyse avancée de contenu

## Tâches
- [x] créer l'app `uploads`
- [x] ajouter le modèle `OrderUpload`
- [x] centraliser validation et scoping dans `OrderUploadService`
- [x] exposer les endpoints client sécurisés
- [x] exposer les endpoints staff sécurisés avec permission dédiée
- [x] brancher l'audit minimal upload / download
- [x] couvrir les tests positifs, négatifs et non-régression
- [x] mettre à jour décisions, risques et statut projet

## Validations attendues
- [x] aucun fichier exposé publiquement
- [x] scope client dérivé strictement de `Order -> Customer`
- [x] aucune FK directe vers `Customer`
- [x] aucune logique métier critique dans les vues
- [x] aucun `file.url` exposé en API
- [x] refus par défaut

## Tests attendus
- [x] client upload sur sa commande
- [x] client refusé sur commande d'un autre client
- [x] client refusé en liste/détail/download cross-tenant
- [x] anonyme refusé
- [x] client refusé sur route staff
- [x] staff sans permission dédiée refusé
- [x] type interdit refusé
- [x] taille interdite refusée
- [x] non-régression des routes commandes et permissions existantes

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] audit minimal ajouté
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour
