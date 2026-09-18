# Paiements en ligne (PayPal + Stripe) — hors facturation différée / mensuelle

## Objectif

Permettre aux clients **hors facturation classique différée** (`Order.billing_mode = immediate`)
de régler une commande via **PayPal** ou **Stripe Checkout**, tout en gardant le flux B2B
mensuel / bi-mensuel (`deferred` + `BillingStatement`) sans paiement en ligne.

## Règles métier

| Situation | Comportement |
|-----------|--------------|
| `billing_mode = deferred` | Paiement en ligne **refusé** |
| Commande `immediate` | Le **client choisit** parmi les providers **installés** (credentials présents) |
| Providers affichés | PayPal / Stripe **activés** dans l’Atelier avec credentials (DB chiffrée ou env) |
| `preferred_settlement_method` | Pré-sélection / indication atelier uniquement, **pas un verrou** |
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
- `POST /api/backend/paypal/webhook/` — vérification `/v1/notifications/verify-webhook-signature`
- `POST /api/backend/stripe/webhook/` — signature `Stripe-Signature`

## Configuration

Les moyens PayPal et Stripe se connectent et s’activent depuis
**Atelier → Réglages → Paiements en ligne** (`/portal/staff/settings/payments/`).
Un administrateur peut activer les deux, un seul, ou aucun.

Sans ligne de réglages Atelier, le comportement reste compatible avec les variables
d’environnement (`.env.example`) : un provider apparaît au checkout dès que ses
credentials env sont présents.

Quand une ligne Atelier existe :

- le toggle **Activer** commande l’affichage au checkout ;
- un secret vide conserve la valeur déjà chiffrée ;
- si le champ Atelier est vide, le backend retombe sur l’env.

Le chiffrement des secrets saisis dans l’Atelier utilise
`PAYMENT_SECRET_ENCRYPTION_KEYS` (sinon `WEB_PUSH_ENCRYPTION_KEYS`).

Voir aussi `.env.example` :

- PayPal : `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_INTERNAL_CONFIRM_TOKEN`,
  `PAYPAL_WEBHOOK_ID`, …
- Stripe : `STRIPE_SECRET_KEY` (clé secrète `sk_` ou de préférence restricted `rk_`),
  `STRIPE_PUBLISHABLE_KEY` (optionnel, Checkout hébergé), `STRIPE_WEBHOOK_SECRET`,
  `STRIPE_API_VERSION` (défaut `2026-07-29.dahlia`).

### Brancher Stripe (runbook)

1. Créer un compte / sandbox Stripe et une **restricted API key** (paiements + Checkout).
2. Renseigner `STRIPE_SECRET_KEY` et `STRIPE_WEBHOOK_SECRET` dans `.env` (Compose les
   injecte via `env_file`).
3. Dashboard Stripe → Developers → Webhooks → endpoint  
   `{PUBLIC_BASE_URL}/api/backend/stripe/webhook/`  
   Événements : `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.async_payment_failed`.
4. Recréer / relancer `web` + `worker` pour prendre les variables.
5. Dans le portail client, une commande `immediate` tarifée affiche **Carte bancaire**.

Webhook Stripe à enregistrer :  
`{PUBLIC_BASE_URL}/api/backend/stripe/webhook/`

Webhook PayPal (recommandé, en plus du retour navigateur) :  
`{PUBLIC_BASE_URL}/api/backend/paypal/webhook/`  
Événements : `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.COMPLETED`.  
Copier l’ID du webhook dans `PAYPAL_WEBHOOK_ID`.

Fallback PayPal sans webhook : retour `?token=` + endpoint interne
`POST /api/backend/paypal/capture/` (`X-Internal-Token`).

## Documents post-paiement

Après capture PayPal/Stripe, Prenium génère un **justificatif de paiement** (PDF, préfixe `JP-`).
Ce document atteste l’encaissement ; il **n’est pas** la facture fiscale.

La **facture fiscale / comptable** est émise hors plateforme via l’outil **RCA**.

## Checklist validation

- [ ] Client immédiat + PayPal : CTA → redirect → return **ou webhook** → justificatif PDF
- [ ] Client immédiat + Stripe : CTA → Checkout → webhook (`completed` / async) ou return → justificatif PDF
- [ ] Client `deferred` : initiate → 400 / pas de CTA
- [ ] Client A ne peut pas initier / confirmer la commande de B
- [ ] Webhook Stripe signature invalide → 403 + audit
- [ ] Webhook PayPal signature invalide → 403 + audit
- [ ] Capture PayPal / Stripe idempotente (pas de double facture)
- [ ] Retour Stripe non payé (async) ne passe **pas** le paiement en failed
- [ ] Staff voit provider + refs PayPal/Stripe dans panneau facturation / admin
- [ ] Atelier active PayPal seul, Stripe seul, les deux, ou aucun
- [ ] Client ne voit au checkout que les moyens activés et connectés
- [ ] Secrets saisis dans l’Atelier masqués (••••) et absents des audits
- [ ] Staff lecture seule : GET OK, POST 403

## Notification post-tarification

Après calcul atelier d’une commande `billing_mode = immediate`, l’événement
`order_awaiting_payment` envoie un e-mail client (et copie interne) avec le lien
vers le panneau Facture (`action.url`), où le CTA Stripe/PayPal apparaît.
L’événement `order_priced` reste réservé à l’encours (`deferred`).

La production atelier (`in_progress`) est **bloquée** jusqu’à capture du paiement
(`apps.billing.services.production_payment_gate`).

### UX portail client (comptant CB)

- Un seul CTA primaire **Payer maintenant** dans l’onglet Règlement, avec les
  moyens PayPal / carte visibles en tuiles (pas de dialogue). PayPal affiche le
  logo officiel ; Stripe affiche les marques Visa, Mastercard et CB.
- La bannière fiche commande pointe vers le règlement (`Ouvrir le règlement`)
  sans dupliquer le bouton primaire.
- Une reprise sur le même moyen réutilise le checkout ouvert (pas de nouvelle
  session provider).
- Après paiement : justificatif + suite **Voir la production**.
- Dashboard + liste commandes : pastille **Paiement non finalisé** + action vers
  `?panel=billing&pay=1#client-billing-pay`.
- Studio Gang Sheet (planche validée) : le client confirme les visuels, choisit la
  couleur du support et paie **sur la même vue**
  (`POST /portal/client/.../gang-sheets/<id>/checkout/`). Le TTC détaillé
  (impression, préparation, livraison, TVA) se met à jour au choix du transport
  sans défiler l’inspecteur (`GET .../quote/`). Pas de hop vers la fiche
  projet B2B.

## Fichiers clés

- `backend/apps/billing/services/gateways.py`
- `backend/apps/billing/services/gateway_settings.py`
- `backend/apps/billing/services/secret_crypto.py`
- `backend/apps/billing/services/paypal.py`
- `backend/apps/billing/services/stripe_gateway.py`
- `backend/apps/billing/services/payments.py`
- `backend/apps/billing/services/production_payment_gate.py`
- `backend/apps/billing/forms.py`
- `backend/apps/billing/views.py`
- `backend/apps/portal/views_payments.py`
- `backend/apps/portal/views_staff_payments.py`
- `backend/templates/portal/staff/settings/payments.html`
- `backend/templates/portal/client/panels/billing.html`
- `backend/apps/notifications/services/transactional.py`
- `tests/billing/test_billing_api.py`
- `tests/billing/test_stripe_payments.py`
- `tests/billing/test_payment_gateway_settings.py`
