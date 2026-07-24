# Paiements en ligne (PayPal + Stripe) — hors facturation différée / mensuelle

## Objectif

Permettre aux clients **hors facturation classique différée** (`Order.billing_mode = immediate`)
de régler une commande via **PayPal** ou **Stripe Checkout**, tout en gardant le flux B2B
mensuel / bi-mensuel (`deferred` + `BillingStatement`) sans paiement en ligne.

## Règles métier

| Situation | Comportement |
|-----------|--------------|
| `billing_mode = deferred` | Paiement en ligne **refusé** |
| `preferred_settlement_method = wire_transfer` | Pas de CTA portail ; rapprochement manuel facture |
| `preferred_settlement_method = paypal` | Checkout PayPal |
| `preferred_settlement_method = stripe` | Checkout Stripe (carte / méthodes dynamiques Dashboard) |
| Montant ≤ 0 | Refus |

## Architecture

```
PaymentService
  ├── resolve_online_provider()
  ├── get_payment_gateway(provider)
  │     ├── PayPalGateway  (Orders API + capture)
  │     └── StripeGateway  (Checkout Sessions + webhook HMAC)
  └── InvoiceService (facture PDF après capture)
```

- Logique métier dans `apps/billing/services/` uniquement.
- Isolation client via `public_id` + `HasScopedCustomerAccess`.
- Audit sur initiation, capture, échec, rejet webhook.

## Endpoints

### Client

- `POST /api/client/customers/<customer>/orders/<order>/payments/initiate/`  
  Body optionnel : `{ "provider": "paypal" | "stripe" }`
- `POST .../payments/paypal/initiate/` — compat historique (force PayPal)
- Portail :
  - `POST /portal/client/.../payments/initiate/`
  - `GET /portal/client/.../payments/return/`

### Backend

- `POST /api/backend/paypal/capture/` — jeton interne `X-Internal-Token` (existant)
- `POST /api/backend/stripe/webhook/` — signature `Stripe-Signature`

## Configuration

Voir `.env.example` :

- PayPal : `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_INTERNAL_CONFIRM_TOKEN`, …
- Stripe : `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, …

Webhook Stripe à enregistrer : `checkout.session.completed` →  
`{PUBLIC_BASE_URL}/api/backend/stripe/webhook/`

## Checklist validation

- [ ] Client immédiat + PayPal : CTA → redirect → return → facture PDF
- [ ] Client immédiat + Stripe : CTA → Checkout → webhook ou return → facture PDF
- [ ] Client `deferred` : initiate → 400 / pas de CTA
- [ ] Client A ne peut pas initier / confirmer la commande de B
- [ ] Webhook Stripe signature invalide → 403 + audit
- [ ] Capture PayPal / Stripe idempotente (pas de double facture)
- [ ] Staff voit provider + refs PayPal/Stripe dans panneau facturation

## Fichiers clés

- `backend/apps/billing/services/gateways.py`
- `backend/apps/billing/services/paypal.py`
- `backend/apps/billing/services/stripe_gateway.py`
- `backend/apps/billing/services/payments.py`
- `backend/apps/billing/views.py`
- `backend/apps/portal/views_payments.py`
- `tests/billing/test_billing_api.py`
- `tests/billing/test_stripe_payments.py`
