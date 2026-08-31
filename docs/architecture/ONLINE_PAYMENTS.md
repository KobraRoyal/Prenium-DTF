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
| Providers affichés | PayPal si `PAYPAL_*` configuré ; carte / Stripe si `STRIPE_SECRET_KEY` configuré |
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
  - `POST /client/.../payments/initiate/`
  - `POST /client/.../payments/capture/` — capture serveur après approbation Smart Buttons
  - `GET /client/.../payments/return/` — retour de secours / providers avec redirection

### Backend

- `POST /api/backend/paypal/capture/` — jeton interne `X-Internal-Token` (existant)
- `POST /api/backend/stripe/webhook/` — signature `Stripe-Signature`

## Configuration

Voir `.env.example` :

- PayPal : `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`, `PAYPAL_INTERNAL_CONFIRM_TOKEN`, …
- Stripe : `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, …

Webhook Stripe à enregistrer : `checkout.session.completed` →  
`{PUBLIC_BASE_URL}/api/backend/stripe/webhook/`

## Flux PayPal du portail

1. Le panneau règlement ouvre un dialogue et charge une seule instance de
   `paypal.Buttons()`. Le SDK décide quels moyens éligibles afficher.
2. `createOrder` appelle le backend Prenium, qui crée la tentative locale puis
   la commande PayPal. Une relance concurrente réutilise la même tentative et
   la même clé d'idempotence. Aucun montant n'est construit dans le navigateur.
3. PayPal ouvre son parcours standard dans une fenêtre sécurisée.
4. `onApprove` transmet uniquement l'identifiant de commande PayPal au backend.
5. Le backend capture, vérifie le statut, le montant total et la devise, puis
   génère le justificatif et débloque la production.

Garde-fous appliqués :

- `Cross-Origin-Opener-Policy: same-origin-allow-popups` pour conserver le flux
  popup PayPal sans affaiblir l'isolation de la page principale ;
- aucun attribut `data-popups-disabled` sur le script SDK ;
- clé stable `PayPal-Request-Id` distincte pour la création et la capture ;
- ordre de verrouillage transactionnel unique `Order → Payment` lors de la
  création provider et de la capture ;
- refus d'une tentative `cancelled` / `failed`, d'un identifiant d'un autre
  provider ou d'une autre commande, et de toute seconde capture financière ;
- contrainte PostgreSQL conditionnelle garantissant au plus un statut financier
  (`captured` ou `captured_review`) par commande ;
- comparaison du snapshot local avec le montant courant de la commande avant
  l'appel provider, puis de l'identifiant de capture, du montant et de la devise
  renvoyés par PayPal ou Stripe ;
- réponse provider `COMPLETED` incohérente placée en `captured_review` : aucun
  nouveau paiement, aucune facture et aucun déblocage production avant contrôle ;
- timeout ou réponse de capture indéterminée marquant la tentative comme non
  remplaçable : seul un retry idempotent ou un rapprochement peut la résoudre ;
- état `captured` et audit financier validés avant la génération du PDF et les
  effets métier, afin qu'une panne documentaire ne masque jamais un débit ;
- routes du portail et API historiques réservées au propriétaire du client,
  avec CSRF, et recherche de la
  tentative dans la commande demandée ;
- retour d'annulation modifiant l'état uniquement avec un identifiant provider
  exact ; un GET générique reste sans effet ;
- audit des initiations, réutilisations, annulations, rejets, captures ambiguës,
  captures à vérifier et confirmations idempotentes.

## Documents post-paiement

Après capture PayPal/Stripe, Prenium génère un **justificatif de paiement** (PDF, préfixe `JP-`).
Ce document atteste l’encaissement ; il **n’est pas** la facture fiscale.

La **facture fiscale / comptable** est émise hors plateforme via l’outil **RCA**.

## Checklist validation

- [x] Client immédiat + PayPal : dialogue → Smart Buttons → create/capture serveur (tests automatisés)
- [ ] Client immédiat + PayPal : transaction sandbox complète → facture PDF (recette manuelle)
- [x] Client immédiat + Stripe : CTA → Checkout → webhook ou return → facture PDF (tests automatisés)
- [x] Client `deferred` : initiate → 400 / pas de CTA
- [x] Client A ne peut pas initier / confirmer la commande de B
- [x] Webhook Stripe signature invalide → 403 + audit
- [x] Capture PayPal / Stripe idempotente (pas de double facture)
- [x] Deux initiations / captures concurrentes sérialisées sur PostgreSQL
- [x] Tentative annulée ou identifiant Stripe refusé avant appel PayPal
- [x] Capture PayPal/Stripe incohérente mise en revue sans facture, production ni retry
- [x] Timeout après débit provider : aucun changement de moyen ni second checkout
- [x] SDK PayPal : popup standard activée et boutons éligibles montés une seule fois
- [ ] Staff voit provider + refs PayPal/Stripe dans panneau facturation

## Notification post-tarification

Après calcul atelier d’une commande `billing_mode = immediate`, l’événement
`order_awaiting_payment` envoie un e-mail client (et copie interne) avec le lien
vers le panneau Facture (`action.url`), où le CTA Stripe/PayPal apparaît.
L’événement `order_priced` reste réservé à l’encours (`deferred`).

La production atelier (`in_progress`) est **bloquée** jusqu’à capture du paiement
(`apps.billing.services.production_payment_gate`).

### UX portail client (comptant CB)

- Un seul CTA **Payer maintenant** (dialogue d’initiation) — pas de boutons
  « Reprendre » / « Relancer » en parallèle.
- Dashboard + liste commandes : pastille **Paiement non finalisé** + action **Payer**
  vers `?panel=billing&pay=1` (`attach_awaits_client_payment`).

## Fichiers clés

- `backend/apps/billing/services/gateways.py`
- `backend/apps/billing/services/paypal.py`
- `backend/apps/billing/services/stripe_gateway.py`
- `backend/apps/billing/services/payments.py`
- `backend/apps/billing/migrations/0009_payment_single_settlement.py`
- `backend/apps/billing/services/production_payment_gate.py`
- `backend/apps/billing/views.py`
- `backend/apps/portal/views_payments.py`
- `backend/static_src/js/client-billing-pay.js`
- `backend/templates/portal/client/panels/billing.html`
- `backend/apps/notifications/services/transactional.py`
- `tests/billing/test_billing_api.py`
- `tests/billing/test_client_payment_popup.py`
- `tests/billing/test_stripe_payments.py`
