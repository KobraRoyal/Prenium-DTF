# Sprint 18 — Pricing avancé & B2B (facturation différée)

## Objectif
Compléter les règles tarifaires et le mode B2B décrit dans `docs/architecture/B2B_DEFERRED_BILLING.md` là où le code est encore partiel.

## Périmètre
- Grilles `price_per_sqm_eur` + métrage serveur (`OrderPricingService`) — déjà centralisé ; complété par **tests d’encours** et **email client** lorsque le prix est calculé.
- Garde-fous crédit : `evaluate_credit_hold` + tests `blocked` / `warning` / solde ouvert (hors brouillons).
- `BillingStatement` auto et cycles de facturation : **hors sprint** (cf. évolutions doc métier).

## Hors périmètre
- ERP comptable externe.
- Abonnements récurrents génériques.
- Émission automatique de relevé `BillingStatement`.

## Définition de done
- [x] Règles dans `OrderPricingService` + tests (encours, persistance tarif, refus commande non différée).
- [x] Email `order_priced` + doc `B2B_DEFERRED_BILLING.md` alignée.
