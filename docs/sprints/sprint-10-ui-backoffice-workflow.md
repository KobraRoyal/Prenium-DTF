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
