# Micro-lot 11.5 — Frontend P3 (landing proof, tables, skeletons, iconography)

> Ce micro-lot finalise le polish frontend après P1 et P2,
> sans changement de logique métier ni de permissions.

## Objectif
Renforcer la finition perçue du produit :
- landing plus crédible commercialement ;
- tables plus confortables et plus lisibles ;
- skeletons réellement visibles sur les zones HTMX ;
- langage iconographique plus homogène.

## Périmètre livré
- [x] landing enrichie par des signaux B2B et de preuve premium plus concrets
- [x] process landing rendu plus tangible et plus crédible
- [x] tables commandes / uploads / inspection affinées (densité, emphasis, anomalies)
- [x] skeletons visibles sur les panneaux HTMX via `order_tabs`
- [x] cohérence iconographique renforcée sur les onglets workflow

## Hors périmètre confirmé
- nouveau domaine métier
- changement de logique métier backend
- modification des permissions
- refonte complète de la landing ou du portail
- déplacement de la sécurité côté frontend

## Exigences sécurité appliquées
- aucune nouvelle donnée exposée
- aucune logique critique déplacée côté frontend
- aucun changement de routes, de permissions ou de contrats métier
- skeletons purement visuels, sans faux état métier détaillé

## Tests exécutés
- [x] tests UI landing/services ajustés
- [x] tests UI portail ajustés

## Validation exécutée
- [x] `npm --prefix backend run build:css`
- [x] `cd backend && set -a && source ../.env && set +a && DJANGO_SETTINGS_MODULE=config.settings.test ../.venv/bin/python -m pytest ../tests/ui/test_portal_ui.py ../tests/ui/test_shop_checkout_ui.py ../tests/ui/test_prospect_tunnel_ui.py -q`
- [x] `cd backend && set -a && source ../.env && set +a && ../.venv/bin/python manage.py check`

## Checklist de clôture
- [x] code implémenté
- [x] tests ajustés
- [x] permissions vérifiées (inchangées)
- [x] logique métier inchangée
- [x] documentation micro-lot ajoutée
