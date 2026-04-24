# Sprint 08 — Expédition Sendcloud

> Ce sprint ouvre le domaine expédition sur une base sécurisée et staff-only,
> sans automatiser encore le polling tracking, le portail client riche ni le
> multi-colis avancé.

## Objectif
Livrer une base sécurisée pour :
- créer une expédition Sendcloud liée à `Order` ;
- stocker un `Shipment` minimal avec statut, tracking, label et références Sendcloud ;
- récupérer et stocker l’étiquette côté backend ;
- exposer une consultation staff dédiée de l’expédition ;
- exposer une création staff dédiée de l’expédition ;
- journaliser les lectures, créations et échecs API.

## Périmètre
- app Django dédiée `shipping`
- modèle `Shipment` lié en `OneToOne` à `Order`
- service d’intégration Sendcloud centralisé et injectable
- création synchrone d’expédition Sendcloud
- récupération et stockage du label PDF en média protégé
- stockage `tracking_number`, `tracking_url`, statut Sendcloud et erreur simple
- permissions staff dédiées `shipping.view_shipment` et `shipping.create_shipment`
- route staff de consultation
- route staff de création
- audit minimal de lecture, succès et échec

## Hors périmètre
- portail client d’expédition riche
- polling tracking automatique
- multi-colis avancé
- fulfillment Shopify
- paiement et facturation
- relances automatiques complexes

## Tâches
- [x] créer l’app `shipping` et la brancher au projet
- [x] ajouter `Shipment` et sa migration initiale
- [x] ajouter la configuration Sendcloud par variables d’environnement uniquement
- [x] implémenter le gateway/service Sendcloud centralisé
- [x] implémenter le service métier staff de création et consultation
- [x] exposer une route staff de consultation
- [x] exposer une route staff de création
- [x] ajouter les permissions staff dédiées
- [x] couvrir succès, doublon, erreurs mockées, permissions et non-régression
- [x] mettre à jour décisions, risques et statut projet

## Hypothèses
- une commande porte au plus une expédition MVP dans ce sprint ;
- la création d’expédition reste manuelle côté staff ;
- la création exige un `ProductionJob` en état `ready_to_ship` ;
- l’adresse expéditeur est fournie par configuration serveur et jamais exposée via secret ;
- l’étiquette est stockée côté backend ; aucun chemin disque ni URL brute de stockage n’est sérialisé.

## Implémentation livrée
- `Shipment` porte l’état d’expédition MVP, les références Sendcloud, le tracking, l’étiquette et un snapshot sûr de la requête staff.
- `SendcloudGateway` encapsule :
  - l’authentification Basic Sendcloud via variables d’environnement ;
  - l’appel `POST /api/v3/shipments/announce` ;
  - le téléchargement du label PDF ;
  - la normalisation d’erreurs API sans fuite de credential.
- `ShipmentService` encapsule :
  - la résolution staff de la commande ;
  - le garde-fou `ready_to_ship` ;
  - le refus de doublon d’expédition créée ;
  - la persistance du label, du tracking et des statuts ;
  - l’audit des lectures, créations et échecs.
- les routes staff dédiées sont :
  - `GET /api/staff/shipping/orders/<order_public_id>/`
  - `POST /api/staff/shipping/orders/<order_public_id>/create/`
- aucune route client n’expose le domaine shipping dans ce sprint.

## Validations attendues
- [x] création shipment staff autorisé : OK
- [x] staff non autorisé refusé
- [x] client refusé
- [x] erreur API Sendcloud mockée : statut cohérent
- [x] label récupéré et stocké : OK
- [x] tracking stocké : OK
- [x] non-régression `production / scan / orders / uploads / accounts / customers`

## Validations exécutées
- [x] `./.venv/bin/python -m ruff check backend/apps/accounts/permissions.py backend/apps/shipping tests/shipping`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py makemigrations shipping`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py makemigrations --check --dry-run`
- [x] `DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ./.venv/bin/python backend/manage.py check`
- [x] `cd backend && DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/shipping -q`
- [x] `cd backend && DJANGO_SETTINGS_MODULE=config.settings.test DJANGO_SECRET_KEY=test-secret POSTGRES_PASSWORD=test ../.venv/bin/python -m pytest ../tests/orders ../tests/uploads ../tests/accounts ../tests/customers ../tests/production ../tests/shipping -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés
- [x] permissions vérifiées
- [x] logs / audit ajoutés si nécessaire
- [x] documentation mise à jour
- [x] checklist du sprint mise à jour
