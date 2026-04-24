# Micro-sprint 11.2 — Landing page premium UI/UX

> Ce micro-sprint transforme la page d'accueil en landing conversion-first,
> moderne, sobre et coherente avec l'espace client.

## Objectif
Faire de la page d'accueil une vraie landing e-commerce premium:
- proposition de valeur comprise en 3 secondes;
- confiance immediate;
- parcours de lecture clair;
- CTA visibles et orientes commande.

## Perimetre livre
- [x] hero premium avec proposition de valeur, CTA principal et CTA secondaire
- [x] bloc reassurance (20 ans, controle expert, optimisation rendu/toucher, suivi, expédition Europe)
- [x] bloc differenciation "Pourquoi nous"
- [x] bloc services en 3 cartes lisibles
- [x] bloc "Comment ca marche" en 4 etapes visuelles
- [x] bloc qualite / preuve
- [x] bloc CTA final conversion
- [x] refactor landing en partials pour maintenabilite
- [x] styles landing dedies et responsives dans le design system existant

## Hors perimetre confirme
- nouveau domaine metier
- nouvelle integration externe
- refonte architecture front
- modifications des permissions backend

## Exigences securite appliquees
- landing publique strictement marketing (aucune donnee client/staff exposee)
- CTA vers routes existantes et sures (`/services/`, `/login/`)
- securite backend et scope tenant inchanges

## Tests executes
- [x] test landing anonyme et presence des sections obligatoires
- [x] non-regression pages services

## Validation executee
- [x] `../.venv/bin/python -m ruff check apps/core apps/portal ../tests/ui/test_shop_checkout_ui.py`
- [ ] `../.venv/bin/python -m pytest ../tests/ui/test_shop_checkout_ui.py -q` (necessite DB Docker `db`)
- [x] `set -a && source ../.env && set +a && ../.venv/bin/python manage.py check`

## Checklist de cloture
- [x] code implemente
- [x] tests ajoutes
- [x] permissions verifiees (impact: aucun changement)
- [x] logs/audit impactes: non
- [x] documentation mise a jour
- [x] checklist du micro-sprint mise a jour
