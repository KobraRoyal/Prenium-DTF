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
| Commande `immediate` non capturée | Chiffrage et suivi administratif possibles ; aucun OF visible à l'Atelier, scan, affectation, PDF de production, notification Atelier, expédition ou revenu encaissé |
| Checkout ouvert | Une seule tentative active par commande, tous prestataires confondus ; tarif figé |
| Capture confirmée | Référence, montant et devise vérifiés ; paiement enregistré avant justificatif et déblocage Atelier |

## Architecture

```
PaymentService
  ├── resolve_online_provider()
  ├── get_payment_gateway(provider)
  │     ├── PayPalGateway  (Orders API + capture)
  │     └── StripeGateway  (Checkout Sessions + webhook HMAC)
  └── InvoiceService (justificatif PDF après capture)
```

- Logique métier dans `apps/billing/services/` uniquement.
- Isolation client via `public_id` + `HasScopedCustomerAccess`.
- Audit sur initiation, capture, expiration vérifiée, échec, rejet webhook et déblocage Atelier.
- Clés d'idempotence stables pour la création Stripe/PayPal et la capture PayPal.
- Les erreurs API sans preuve d'échec terminal gardent la tentative active. Un retour navigateur
  « annuler » ne suffit pas à autoriser un second paiement.
- Stripe : une session expirée est remplacée après vérification distante ; lors d'un changement
  de moyen, une session encore ouverte est expirée côté Stripe avant création de la suivante.
  Les nouvelles sessions n'acceptent que `card`, conformément au moyen « Carte bancaire »
  annoncé dans le portail ; les modes à règlement différé ne sont pas proposés.
  PayPal : une commande encore payable reste active jusqu'à son état `VOIDED` constaté ;
  l'abandon du navigateur ne permet pas d'ouvrir un checkout concurrent.
- Les webhooks signés inconnus répondent `503`, pour que le prestataire réessaie après
  l'enregistrement de la référence distante. Les métadonnées de tentative permettent de
  rattacher un webhook reçu tôt.
- Un webhook Stripe d'échec asynchrone relit la session distante avant de marquer la
  tentative échouée. Si Stripe la déclare déjà payée, la capture est enregistrée et
  l'ancien événement d'échec ne ferme pas un paiement réussi. Si elle est encore
  `complete/unpaid`, la tentative reste active pour empêcher un second checkout :
  cette valeur ne prouve pas la fin du traitement. Seul `expired` libère la tentative.
  Une ancienne session différée qui reste `complete/unpaid` exige un rapprochement
  opérateur avec Stripe avant toute nouvelle tentative ; ne pas la fermer sur la seule
  absence de fonds à l'instant de la lecture.
- Un checkout avec référence distante connue reprend son URL par lecture chez le
  prestataire. Sans référence, la même clé est rejouée pendant moins de 23 h (Stripe)
  ou 5 h (PayPal) ; ensuite la tentative reste bloquée pour rapprochement manuel.
- Celery Beat exécute `billing.recover_incomplete_captures` toutes les cinq minutes
  par défaut (`PAYMENT_RECOVERY_INTERVAL_SECONDS`). Il termine les justificatifs et
  la notification Atelier manquants pour les captures déjà enregistrées.
- La même cadence exécute `billing.reconcile_active_payments` : les tentatives encore
  actives avec référence distante sont vérifiées chez le prestataire. Une capture
  confirmée à distance est enregistrée même si le retour client et le webhook ont échoué.
  Les échecs de rapprochement produisent `billing.payment_reconciliation_failed`.
- Avant toute capture PayPal, les références, le montant et la devise de l'ordre distant
  sont comparés à la tentative locale. Les webhooks Stripe reçus avant l'enregistrement
  de la session vérifient aussi la commande, le client, la tentative, le montant et la devise.
- Une session Stripe ancienne déjà enregistrée localement peut manquer de métadonnée
  `payment_public_id` : sa confirmation reste possible uniquement si l'ID de session
  est déjà lié à cette tentative et que commande, client, montant et devise concordent.
  Un webhook précoce sans ID local reste soumis au contrôle strict de la tentative.

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

1. Créer un compte / sandbox Stripe et une **restricted API key** adaptée aux opérations
   Checkout (création, lecture, expiration), aux paiements et à la lecture des événements.
2. Renseigner `STRIPE_SECRET_KEY` et `STRIPE_WEBHOOK_SECRET` dans `.env` (Compose les
   injecte via `env_file`).
3. Dashboard Stripe → Developers → Webhooks → endpoint  
   `{PUBLIC_BASE_URL}/api/backend/stripe/webhook/`  
   Événements : `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
   `checkout.session.async_payment_failed`.
4. Recréer / relancer `web`, `worker` et `beat` pour prendre les variables et les
   nouvelles tâches périodiques.
5. Dans le portail client, une commande `immediate` tarifée affiche **Carte bancaire**.

### Contrôle obligatoire avant bascule live

1. Sauvegarder la base, puis exécuter la migration `billing.0011` sur une copie récente.
   Elle refuse explicitement les commandes avec plusieurs paiements encore payables ou
   capturés, y compris un paiement capturé et une ancienne session encore active.
   Rapprocher ces cas avec les tableaux de bord PayPal/Stripe avant toute correction manuelle ;
   ne jamais supprimer un encaissement pour faire passer la migration.
2. Configurer `PUBLIC_BASE_URL` en HTTPS, `PAYPAL_API_BASE_URL=https://api-m.paypal.com`,
   identifiants PayPal live, clé Stripe `sk_live_` ou `rk_live_`, secrets et identifiants webhook.
3. Exécuter `python backend/manage.py payment_preflight --live` dans l'environnement de
   production. La commande échoue si les deux prestataires ne sont pas prêts, si un webhook
   manque, si PayPal pointe vers sandbox, si Stripe utilise une clé test, si l'URL publique
   n'est pas HTTPS, si la base contient des paiements historiques ambigus, ou si une
   tentative sans référence distante dépasse sa fenêtre de retry sûre. Elle exige aussi
   que `billing.0011` soit appliquée et que son index unique existe réellement sur la
   base contrôlée. Quand ces contrôles passent, elle demande un jeton OAuth à PayPal et
   lit une session Checkout Stripe afin de vérifier les identifiants et la permission de
   lecture sans créer de paiement. Elle vérifie aussi, par une requête GET sans effet
   métier, que chaque URL publique de webhook répond `405` avec `POST` dans l'en-tête
   `Allow`. Un `404`, une redirection ou un échec réseau bloque la bascule : le code
   déployé ou le routage public peut être obsolète. Une clé Stripe restreinte peut
   autoriser la lecture et refuser la création ; ces sondes ne vérifient donc pas les
   droits d'écriture ni la livraison effective des webhooks. Les tentatives Stripe et
   PayPal actives, ainsi que les anciennes tentatives fermées avec référence, sont
   relues chez le prestataire. Une tentative Stripe active doit être `open/unpaid` avec
   `card` seul ; une tentative locale fermée doit être `expired/unpaid` à distance.
   Une commande PayPal fermée localement doit être `VOIDED` à distance. Absence de
   référence pour une tentative active, ancienne tentative `failed/cancelled` sans
   référence ni preuve de rapprochement, différence de commande/montant ou état
   incompatible bloquent la bascule. Le contrôle parcourt toutes les tentatives
   concernées par lots.
4. Vérifier depuis les consoles PayPal et Stripe que les deux endpoints HTTPS reçoivent
   leurs événements et répondent `2xx`. Faire un achat réel de faible montant avec chaque
   moyen, contrôler **paiement capturé → justificatif → file Atelier**, puis rembourser selon
   la procédure financière. Tester aussi échec, annulation, webhook répété et retour sans
   webhook. Garder la migration et l'activation séparées pour permettre un retour arrière.
5. Vérifier que les conteneurs `worker` et `beat` sont sains et que les tâches
   `billing.recover_incomplete_captures` et `billing.reconcile_active_payments`
   sont enregistrées par le worker et planifiées par Beat. Un ancien processus Celery
   ne recharge pas automatiquement les nouvelles tâches après une mise à jour du code.
   Surveiller `billing.payment_recovery_failed` et
   `billing.payment_reconciliation_failed`.

### Tentative sans référence distante hors fenêtre de retry

Après 23 h pour Stripe ou 5 h pour PayPal, une réponse de création perdue ne peut
plus être rejouée sans risque de créer un second checkout. Rechercher la tentative
dans la console du prestataire par son `payment_public_id` (clé d'idempotence et
métadonnée) et vérifier qu'aucun paiement n'a été capturé ni checkout encore payable.
Si une commande distante existe, la rapprocher ou la fermer côté prestataire avant
toute intervention locale. Conserver la référence de recherche et sa conclusion.

Un opérateur ayant l'accès administrateur au conteneur applicatif peut ensuite fermer
une tentative locale sans référence ni URL, en documentant la preuve et le motif.
Cela inclut les anciennes tentatives `failed/cancelled` créées avant le durcissement,
si aucune preuve de rapprochement n'a encore été enregistrée :

```sh
python backend/manage.py resolve_unknown_payment PAYMENT_PUBLIC_ID \
  --resolution no_remote_checkout \
  --evidence "Recherche Stripe dashboard du 2026-09-19, référence ABC" \
  --reason "Aucune session créée ou capture trouvée pour cette tentative"
```

`--resolution remote_closed` correspond à un checkout distant retrouvé puis fermé,
avec sa référence dans `--evidence`. La commande refuse les tentatives trop récentes,
avec référence distante, déjà terminales ou déjà réglées. L'événement
`billing.unknown_checkout_manually_closed` conserve les éléments de rapprochement.
En ligne de commande, l'auteur applicatif est volontairement nul :
l'accès au conteneur doit être journalisé par l'infrastructure et ne peut pas être
attribué à un compte staff choisi par argument. Ne pas exécuter cette commande sans
preuve externe vérifiée.

Ces étapes live nécessitent les comptes, secrets, DNS et données de production. Les tests
locaux ne prouvent pas la livraison des webhooks ni l'encaissement sur les comptes réels.

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

- [x] Tests locaux : un checkout actif / une capture par commande et changement provider sécurisé
- [x] Tests locaux : paiement comptant non capturé exclu de toutes les surfaces Atelier opérationnelles
- [x] Tests locaux : échec du stockage PDF après débit préserve la capture et permet la reprise
- [x] Tests locaux : reprise périodique du justificatif et de la notification Atelier
- [x] Tests locaux : retry de création borné par la fenêtre d'idempotence prestataire
- [x] Tests locaux : webhook signé précoce ou inconnu ne perd pas une capture
- [x] Tests locaux : paiement différé et permissions inter-clients préservés
- [ ] Production : migration `billing.0011` vérifiée sur copie et doublons rapprochés
- [ ] Production : `payment_preflight --live` réussi
- [ ] Production : parcours réels Stripe et PayPal + webhooks et déblocage Atelier vérifiés
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

La production Atelier entière est **bloquée** jusqu’à capture du paiement comptant :
diffusion/consultation de l'OF, files opérationnelles, PDF de lot, scan, affectation,
transitions et notification push (`apps.billing.services.production_payment_gate`).
Les files « À tarifer » et « En attente de paiement » restent administratives et exigent
`orders.change_order`. Les commandes `deferred` conservent leur fonctionnement.

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
