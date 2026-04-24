# Sprint 11 — Tunnel produit final + polish UX

> Ce sprint complete la surface portail client/staff avant hardening final et release prep,
> sans ouvrir de nouveau domaine metier ni changer l'architecture front.

## Objectif
Ameliorer la lisibilite et la fluidite du tunnel produit sur les surfaces client et staff:
- dashboard, liste commandes, detail commande;
- panneaux uploads, inspection, production, shipping, scan et billing/facture;
- etats loading/empty/error/confirmation plus clairs en HTMX.

## Perimetre livre
- [x] hierarchy visuelle renforcee (breadcrumbs, en-tetes, cartes/panneaux)
- [x] composants UI reutilisables dans `app.css` (`alert`, `panel-head`, `step-chip`)
- [x] tabs HTMX plus lisibles (etat actif coherent au clic)
- [x] feedback HTMX plus explicite sur actions staff (`hx-indicator`, prevention double submit)
- [x] panneau client `Facture` ajoute sans logique metier dupliquee
- [x] panneau staff `Billing` ajoute avec permissions backend dediees
- [x] libelles de statuts harmonises et plus lisibles
- [x] etats vide/erreur/succes modernises sur panneaux critiques

## Hors perimetre confirme
- nouvelle integration externe
- refonte architecture front
- nouveau domaine metier paiement/facturation
- migration vers SPA

## Exigences securite appliquees
- separation client/staff strictement conservee
- permissions backend conservees comme source de verite
- nouveau panneau billing staff protege par `billing.view_payment` + `billing.view_invoice`
- routes client scopees par `ScopedCustomerMixin` et `Order -> Customer`

## Tests executes
- [x] extension des tests UI portail (nouveau panneau billing client/staff)
- [x] test d'acces croise client (403/404 selon surface)
- [x] test de refus staff sans permissions billing

## Validation executee
- [x] `python -m ruff check backend/apps/portal backend/apps/billing tests/ui/test_portal_ui.py`
- [x] `python -m pytest tests/ui/test_portal_ui.py -q`
- [x] `python backend/manage.py check`

## Checklist de cloture
- [x] code implemente
- [x] tests ajoutes
- [x] permissions verifiees
- [x] logs/audit impactes: non, inchanges (lecture + UI)
- [x] documentation mise a jour
- [x] checklist du sprint mise a jour
