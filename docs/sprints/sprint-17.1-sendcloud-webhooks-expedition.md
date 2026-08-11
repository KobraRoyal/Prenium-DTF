# Sprint 17.1 — Webhooks Sendcloud + notification expédition

## Objectif
Remonter automatiquement le statut colis Sendcloud dans Prenium DTF dès qu’un colis est expédié, pour notifier le client (email + suivi commande) avec numéro et lien de tracking.

## Décision d’architecture (production)
- **Déclaration de commande depuis Prenium** via Orders API `POST /orders` (Incoming Orders) — **sans génération d’étiquette**.
- **Génération d’étiquette par un opérateur** dans le panneau Sendcloud.
- **Retour d’état via webhook** `parcel status changed` (HMAC `Sendcloud-Signature`), avec **polling Celery** en filet de secours.
- Matching local : `sendcloud_parcel_id` **ou** `order_number` / `order.public_id` / `sendcloud_order_id`.
- Hors périmètre : Shopify, multi-colis, étiquettes retour, génération automatique d’étiquette via `shipments/announce`.

## Périmètre livré
- Endpoint `POST /api/backend/sendcloud/webhook/`
  - vérification HMAC stricte avec `SENDCLOUD_WEBHOOK_SECRET` sur le body brut
  - validation rapide puis mise en file Celery avec réponse HTTP 202
  - tâche Celery `shipping.process_sendcloud_parcel_status_webhook` avec retry exponentiel
  - idempotence persistante par client via `SendcloudWebhookEvent`
  - clé de déduplication : identifiant fournisseur, sinon hash SHA-256 du JSON canonique
  - aucun payload brut conservé ou journalisé
  - parsing du format officiel `action` + `data.parcel`
  - ignore des événements périmés (timestamp < `last_api_sync_at`)
  - colis inconnu → audit dans la tâche sans retry infini
  - signature invalide → 403 + audit sécurité
  - payload signé mais invalide → 400 + audit
  - timestamp ISO ou Unix millisecondes et blocage des régressions après handoff
- Factorisation `_apply_tracking_update` partagée sync manuelle / polling / webhook
- Premier statut « handoff transporteur » → `shipped_at` + email unique `order_shipped` (tracking + lien)
- Staff portail : bouton **Déclarer dans Sendcloud** (pas « Générer l’étiquette »)
- Polling Celery existant conservé en filet de secours (résolution colis par `order_number` si besoin)

## Configuration
Voir `.env.example` :
- `SENDCLOUD_PUBLIC_KEY` / `SENDCLOUD_SECRET_KEY`
- `SENDCLOUD_INTEGRATION_ID` (intégration API, ex. PreniumDTF)
- `SENDCLOUD_WEBHOOK_SECRET` obligatoire ; aucun fallback implicite sur le secret API
- L’adresse **expéditeur** est gérée dans Sendcloud (pas dans Prenium)
- Dans Sendcloud : Settings → Integrations → webhook URL = `https://<domaine>/api/backend/sendcloud/webhook/`

## Données poussées à la déclaration
- Destinataire (adresse de livraison)
- Produits / lignes commande
- N° de commande (`order_number` = référence courte Prenium) comme référence d’expédition
- Poids estimé (indicatif)

## Tests
- `tests/shipping/test_sendcloud_webhook.py`
  - signature invalide → 403 + audit
  - secret API refusé comme fallback HMAC
  - payload officiel `action` + `data.parcel`
  - payload invalide → 400 + audit
  - webhook IN_TRANSIT → tracking + email une seule fois
  - même événement reçu deux fois → un seul traitement métier
  - même clé d’événement autorisée pour deux clients différents
  - matching par `order_number` si `parcel_id` local absent
  - colis inconnu → 202 + audit
  - événement stale ignoré
  - statut post-handoff ne revenant pas à `READY_TO_SEND`
- `tests/shipping/test_sendcloud_service.py` / `test_shipment_*` : déclaration sans label

## Checklist de validation
- [ ] Clés + `SENDCLOUD_INTEGRATION_ID` + adresse expéditeur renseignés dans `.env`
- [ ] `SENDCLOUD_WEBHOOK_SECRET` renseigné et distinctement géré
- [ ] Worker Celery actif et connecté au broker Redis
- [ ] Webhook URL configurée sur l’intégration API PreniumDTF
- [ ] Déclarer une commande `READY_TO_SHIP` depuis le panneau staff
- [ ] Vérifier l’apparition de la commande Incoming dans Sendcloud
- [ ] Générer l’étiquette manuellement dans Sendcloud
- [ ] Faire passer le colis à un statut expédié (ou webhook de test)
- [ ] Vérifier email client + panneau suivi commande
