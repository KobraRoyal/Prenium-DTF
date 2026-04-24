# Sprint 17 — Logistique Sendcloud avancée

## Objectif
Rapprocher le suivi colis de l’expérience e-commerce : état, multi-colis si besoin, visibilité client contrôlée.

## Périmètre
- Synchronisation du suivi via **GET** `/parcels/{id}` (méthode `SendcloudGateway.fetch_parcel`).
- `ShipmentService.sync_shipment_tracking_from_sendcloud` + tâche Celery `shipping.sync_stale_shipments_tracking` (expéditions `created` avec colis, dernière sync > 45 min).
- API client **GET** `api/client/.../shipment/` : tracking + statut transporteur **sans** IDs Sendcloud ni `request_snapshot`.
- Staff : **POST** `api/staff/shipping/orders/<uuid>/sync-tracking/` + bouton HTMX portail.
- Beat Celery (dev) : toutes les **30 min** (`config/settings/dev.py`).
- Multi-colis (1 commande → N expéditions) : **hors périmètre** — le modèle reste **OneToOne** `Order` ↔ `Shipment`.

## Hors périmètre
- Transporteurs hors Sendcloud.
- Étiquettes retour automatiques.
- Webhooks Sendcloud signés (itération ultérieure).

## Définition de done
- [x] Service + Celery + tests mock / isolation client.
- [x] Pas d’exposition de secrets Sendcloud dans les réponses JSON client.
