# Micro-lot 11.8 — Signature UI 2026 (landing + dashboards)

> Ce micro-lot pousse le frontend vers une lecture plus éditoriale et plus premium,
> sans toucher aux règles métier, aux permissions ni aux contrats backend.

## Objectif
Donner au produit une signature plus contemporaine et plus crédible :
- landing plus orientée résultats et conversion B2B ;
- dashboards client et staff avec une hiérarchie plus nette ;
- KPI et tables plus lisibles, avec des actions mieux mises en avant ;
- cohérence marketing → portail renforcée.

## Périmètre livré
- [x] hero landing reconstruit autour d’un message orienté bénéfice et d’un mockup narratif
- [x] sections `Services`, `Pourquoi nous`, `Preuves` et CTA final réécrites dans une logique plus commerciale
- [x] navigation landing/portal enrichie par des signaux de contexte plus premium
- [x] dashboards client et staff recomposés avec cartes de signal, page heads éditoriaux et headers de sections clarifiés
- [x] cartes KPI et tableau des commandes raffinés visuellement sans modifier les données affichées
- [x] styles partagés ajoutés dans `input.css` pour porter la nouvelle signature visuelle
- [x] shells de composition landing et tunnel prospect réintroduits pour supprimer l'effet bord a bord, recadrer les sections et réaligner la hiérarchie visuelle avec le reste du site

## Hors périmètre confirmé
- nouveau domaine métier
- nouvelle route backend
- modification de permissions
- changement des services applicatifs
- génération d’assets externes ou refonte JS lourde

## Exigences sécurité appliquées
- aucune donnée supplémentaire exposée en landing publique
- aucune logique critique déplacée côté frontend
- permissions client/staff inchangées
- mêmes routes et mêmes scopes serveur qu’avant le lot

## Validation exécutée
- [x] `npm --prefix backend run build:css`
- [x] `cd backend && ../.venv/bin/python -m ruff check .`
- [x] `cd backend && set -a && source ../.env && set +a && DJANGO_SETTINGS_MODULE=config.settings.test ../.venv/bin/python -m pytest ../tests/ui/test_portal_ui.py ../tests/ui/test_shop_checkout_ui.py -q`
- [x] `cd backend && set -a && source ../.env && set +a && DJANGO_SETTINGS_MODULE=config.settings.test ../.venv/bin/python -m pytest ../tests -q`

## Checklist de clôture
- [x] code implémenté
- [x] tests exécutés
- [x] permissions vérifiées (inchangées)
- [x] logique métier inchangée
- [x] documentation micro-lot ajoutée
