# Sprint 10 — Paiement PayPal + facturation automatique

> Ce sprint livre une base paiement/facturation securisee, scopee client/staff
> et auditable, sans traiter les abonnements ni la comptabilite avancee.

## Objectif
Livrer un socle backend securise pour :
- initier un paiement PayPal depuis une commande client ;
- confirmer/capturer le paiement cote backend ;
- stocker les references de paiement sans exposer de secret ;
- generer automatiquement une facture simple apres capture valide ;
- exposer la facture au client dans son scope ;
- exposer la lecture paiement/facture au staff autorise.

## Perimetre livre
- [x] nouvelle app `billing`
- [x] modele `Payment` lie a `Order`
- [x] modele `Invoice` lie a `Order`
- [x] service PayPal centralise (`PayPalGateway`)
- [x] service paiement centralise (`PaymentService`)
- [x] service facture centralise (`InvoiceService`)
- [x] route client d'initiation PayPal
- [x] route backend de confirmation/capture
- [x] route client scopee de lecture facture (+ download)
- [x] route staff dediee de lecture paiement/facture
- [x] audit minimal sur initiation/echec/capture/facture/lecture staff

## Hors perimetre confirme
- abonnements
- avoirs
- remboursements avances
- relances complexes
- comptabilite avancee

## Exigences de securite appliquees
- credentials PayPal via variables d'environnement uniquement
- aucun secret PayPal serialise ou expose
- routes client scopees via `Order -> Customer`
- routes staff separees avec permission dediee
- idempotence minimale sur confirmation capture
- logique paiement centralisee en service
- logique facture centralisee en service

## Routes livrees
- `POST /api/client/customers/<customer_public_id>/orders/<order_public_id>/payments/paypal/initiate/`
- `POST /api/backend/paypal/capture/` (token interne requis)
- `GET /api/client/customers/<customer_public_id>/orders/<order_public_id>/invoice/`
- `GET /api/client/customers/<customer_public_id>/orders/<order_public_id>/invoice/download/`
- `GET /api/staff/billing/orders/<order_public_id>/`

## Tests minimums couverts
- [x] client peut initier un paiement sur sa commande
- [x] client A ne peut pas initier le paiement de B
- [x] client peut lire sa facture
- [x] client A ne peut pas lire la facture de B
- [x] client refuse sur route staff
- [x] staff non autorise refuse
- [x] erreur PayPal mockee -> statut coherent (`failed`)
- [x] facture generee apres confirmation valide
- [x] idempotence minimale capture (pas de doublon facture)

## Validations executees
- [x] `python backend/manage.py makemigrations billing`
- [x] `python backend/manage.py makemigrations --check --dry-run`
- [x] `python backend/manage.py check`
- [x] `python -m ruff check backend/apps/billing tests/billing`
- [x] `python -m pytest tests/billing tests/orders tests/uploads tests/production tests/shipping tests/ui -q`

## Stabilisation QA Sprint 10.1
- [x] diagnostic reserve QA: 3 echecs `tests/shipping/test_shipment_service.py`
- [x] cause: tests obsoletes (ancien contrat payload/champs), pas de regression metier `shipping`
- [x] correctif minimal: realignement des tests service `shipping` sur le contrat actuel
- [x] revalidation:
  - [x] `python -m pytest tests/billing -q`
  - [x] `python -m pytest tests/shipping -q`
  - [x] `python -m pytest tests/orders tests/uploads tests/production tests/shipping tests/ui -q`

## Checklist de cloture
- [x] code implemente
- [x] tests ajoutes
- [x] permissions verifiees
- [x] logs / audit ajoutes si necessaire
- [x] documentation mise a jour
- [x] checklist du sprint mise a jour

## Correctif PayPal — 2026-08-31

### Cause et correction

- [x] cause reproduite sur la fiche commande : le SDK etait charge avec
  `data-popups-disabled="true"`, ce qui bloquait le parcours popup standard et
  laissait des tentatives locales annulees / en attente ;
- [x] une seule instance Smart Buttons laisse PayPal afficher les moyens
  eligibles, sans forcer des boutons PayPal et carte concurrents ;
- [x] cache des assets incremente pour livrer le correctif aux navigateurs deja
  passes sur la page ;
- [x] creation et capture executees cote serveur avec des cles d'idempotence
  distinctes et stables ;
- [x] initiations concurrentes reutilisant la meme tentative ; verrouillage
  `Order -> Payment` et refus des tentatives obsoletes avant appel PayPal ;
- [x] contrainte base garantissant un seul reglement financier par commande ;
- [x] montant total et devise renvoyes par PayPal verifies avant facture et
  deblocage de la production ;
- [x] capture provider incoherente placee en `captured_review`, sans nouveau
  paiement, facture ou deblocage avant controle manuel ;
- [x] timeout apres debit provider : tentative rendue non remplacable et retry
  limite a la meme cle d'idempotence ;
- [x] identifiant de capture, montant et devise verifies pour PayPal, retour
  Stripe et webhook Stripe ;
- [x] etat capture et audit financier persistes avant le PDF et les effets
  metier, y compris si la generation du justificatif echoue ;
- [x] confusion d'identifiant Stripe / PayPal et commande voisine refusees ;
- [x] isolation inter-client, acces owner-only et CSRF verifies sur le portail
  et les deux API historiques d'initiation ;
- [x] annulation GET sans identifiant provider exact rendue non mutante ;
- [x] en-tete COOP conserve en `same-origin-allow-popups`.

### Validation

- [x] suite paiement, notifications et contrats UI cibles : 105 passes, 3 ignores
  (tests de concurrence reserves a PostgreSQL dans ce run SQLite) ;
- [x] tests PostgreSQL de double initiation et double capture : 2 passes ;
- [x] migration `0009_payment_single_settlement` appliquee et contrainte unique
  partielle verifiee dans PostgreSQL ; gardes historiques propres, doublons et
  captures ambigues couverts par tests ;
- [x] `makemigrations --check --dry-run billing` : aucun changement ;
- [x] Ruff cible : conforme ;
- [x] `python manage.py check` : aucune erreur ;
- [x] revue securite independante finale : approuvee, aucun finding P0-P3 ;
- [x] controle navigateur sur la commande signalee : dialogue ouvert, SDK charge,
  etat `ready`, aucun `data-popups-disabled` ;
- [ ] recette sandbox de bout en bout avec compte PayPal test et verification du
  justificatif — non declenchee automatiquement pour ne pas creer de transaction.

La suite avec migrations SQLite reste bloquee par la migration POD locale
`0007_restore_shopify_webhook_secret.py`, qui interroge `information_schema`.
Les validations de ce correctif ont donc utilise `--nomigrations` ; ce blocage
est independant du paiement PayPal.
