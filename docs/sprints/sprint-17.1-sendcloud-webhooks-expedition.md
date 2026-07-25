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
  - vérification HMAC (`SENDCLOUD_WEBHOOK_SECRET` ou fallback `SENDCLOUD_SECRET_KEY`)
  - traitement synchrone (comme Stripe) pour ACK fiable côté Sendcloud
  - tâche Celery `shipping.process_sendcloud_parcel_status_webhook` disponible pour rejeu
  - ignore des événements périmés (timestamp < `last_api_sync_at`)
  - colis inconnu → 202 + audit (pas de retry infini)
  - signature invalide → 403 + audit sécurité
- Factorisation `_apply_tracking_update` partagée sync manuelle / polling / webhook
- Premier statut « handoff transporteur » → `shipped_at` + email unique `order_shipped` (tracking + lien)
- Staff portail : bouton **Déclarer dans Sendcloud** (pas « Générer l’étiquette »)
- Polling Celery existant conservé en filet de secours (résolution colis par `order_number` si besoin)

## Configuration
Voir `.env.example` :
- `SENDCLOUD_PUBLIC_KEY` / `SENDCLOUD_SECRET_KEY`
- `SENDCLOUD_INTEGRATION_ID` (intégration API, ex. PreniumDTF)
- `SENDCLOUD_WEBHOOK_SECRET` (recommandé ; sinon secret API)
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
  - webhook IN_TRANSIT → tracking + email une seule fois
  - matching par `order_number` si `parcel_id` local absent
  - colis inconnu → 202 + audit
  - événement stale ignoré
- `tests/shipping/test_sendcloud_service.py` / `test_shipment_*` : déclaration sans label

## Checklist de validation
- [ ] Clés + `SENDCLOUD_INTEGRATION_ID` + adresse expéditeur renseignés dans `.env`
- [ ] Webhook URL configurée sur l’intégration API PreniumDTF
- [ ] Déclarer une commande `READY_TO_SHIP` depuis le panneau staff
- [ ] Vérifier l’apparition de la commande Incoming dans Sendcloud
- [ ] Générer l’étiquette manuellement dans Sendcloud
- [ ] Faire passer le colis à un statut expédié (ou webhook de test)
- [ ] Vérifier email client + panneau suivi commande
