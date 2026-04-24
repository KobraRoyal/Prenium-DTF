# Micro-lot 11.4 — Frontend P2 (prospects, staff forms, hierarchy, HTMX local states, services)

> Ce micro-lot prolonge le P1 avec un polish structurel ciblé côté templates/UI,
> sans changement de logique métier ni de permissions.

## Objectif
Améliorer la cohérence visuelle et la lisibilité opérationnelle :
- tunnel prospect homogène de bout en bout ;
- formulaires staff normalisés ;
- fiche commande staff mieux hiérarchisée ;
- feedbacks HTMX locaux plus explicites ;
- page services plus utile à la conversion B2B.

## Périmètre livré
- [x] `step2/3/4` du tunnel prospect alignés sur le niveau qualitatif de `step1`
- [x] aides, feedbacks, boutons et panneaux prospect harmonisés
- [x] formulaires staff production / shipping / scan / billing mieux normalisés
- [x] hiérarchie de la fiche commande staff clarifiée par couches de lecture
- [x] états locaux HTMX améliorés (loading local, feedback local, succès bref)
- [x] page `/services/` enrichie par bénéfices, cas d’usage, réassurance et CTA mieux hiérarchisés

## Hors périmètre confirmé
- nouveau domaine métier
- changement de logique métier backend
- modification des permissions
- refonte complète du portail
- déplacement de la sécurité côté frontend

## Exigences sécurité appliquées
- services backend existants inchangés
- permissions staff/client inchangées
- aucun élargissement de surface ou de données
- feedback HTMX purement visuel, sans nouvelle source de vérité frontend

## Tests exécutés
- [x] tests UI portail ajustés
- [x] tests UI landing/services ajustés
- [x] nouveau test UI prospect tunnel

## Validation exécutée
- [x] `npm --prefix backend run build:css`
- [x] `cd backend && set -a && source ../.env && set +a && DJANGO_SETTINGS_MODULE=config.settings.test ../.venv/bin/python -m pytest ../tests/ui/test_portal_ui.py ../tests/ui/test_shop_checkout_ui.py ../tests/ui/test_prospect_tunnel_ui.py -q`
- [x] `cd backend && set -a && source ../.env && set +a && ../.venv/bin/python manage.py check`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajoutés / ajustés
- [x] permissions vérifiées (inchangées)
- [x] logique métier inchangée
- [x] documentation micro-lot ajoutée
