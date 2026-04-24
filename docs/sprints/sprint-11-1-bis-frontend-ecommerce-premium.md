# Micro-sprint 11.1 bis — Frontend e-commerce premium + tunnel moderne

> Ce micro-sprint etend le Sprint 11 UX avec une couche front-office e-commerce premium
> et un tunnel client moderne, sans ouvrir de nouveau domaine metier.

## Objectif
Donner une experience frontend plus premium et orientee conversion:
- homepage moderne et rassurante;
- selection service claire;
- tunnel commande client en etapes;
- upload fluide et lisible;
- coherence de navigation avec l'espace client.

## Perimetre livre
- [x] homepage premium (`/`) avec hero, CTA, services et "comment ca marche"
- [x] page services (`/services/`) orientee selection visuelle
- [x] tunnel client en 4 etapes sous scope customer:
  - configuration commande
  - upload de fichiers
  - resume sticky
  - confirmation avant paiement
- [x] CTA "Commander" ajoutes dans dashboard client et navigation portail
- [x] composants CSS reutilisables pour hero, cards services, dropzone, resume sticky
- [x] partials HTMX de tunnel (uploads + resume) pour une UX plus dynamique

## Hors perimetre confirme
- nouveau domaine metier (panier serveur, guest checkout, nouvelle adresse shipping)
- nouvelle integration externe
- migration SPA/front separe
- deplacement de logique metier vers le frontend

## Exigences securite appliquees
- tunnel strictement scope via `customer_public_id` + `ScopedCustomerMixin`
- resolution commande via `OrderService.get_customer_order`
- upload via `OrderUploadService` existant (validation et audit centralises)
- refus cross-tenant valide sur resume tunnel

## Tests executes
- [x] pages marketing accessibles en anonyme
- [x] creation commande depuis tunnel client scope
- [x] upload HTMX dans tunnel avec rafraichissement liste
- [x] refus d'acces cross-tenant sur resume checkout

## Validation executee
- [x] `../.venv/bin/python -m ruff check apps/core apps/portal tests/ui/test_shop_checkout_ui.py`
- [x] `../.venv/bin/python -m pytest tests/ui/test_shop_checkout_ui.py tests/ui/test_portal_ui.py -q`
- [x] `../.venv/bin/python manage.py check`

## Checklist de cloture
- [x] code implemente
- [x] tests ajoutes
- [x] permissions verifiees
- [x] logs/audit impactes: inchanges (services existants reutilises)
- [x] documentation mise a jour
- [x] checklist du micro-sprint mise a jour
