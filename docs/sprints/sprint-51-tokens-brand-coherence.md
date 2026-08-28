# Sprint 51 — Cohérence tokens et identité Atelier

## Objectif

Une seule vérité couleur pour le shell Operate, sans régression du look corail, pour que la vue Atelier **Identité visuelle** (`/staff/settings/branding/`) pilote vraiment primaire et secondaire.

Pas de labb. Pas de nouvelle surface. Pas de changement métier, permission ou isolation.

## Livré

- [x] `tokens.css` : alias `--ui-brand: var(--brand)` ; commentaire trois couches.
- [x] `tailwind.config.js` : `brand` → `var(--brand)` ; thème Daisy `prenium` aligné DESIGN.md (corail / violet, plus le brun `#8f3d1f`).
- [x] `app-legacy.css` : plus de `--brand` brun sur `:root` ; hex morts `#8f3d1f` / `#6f2f17` remplacés par les variables.
- [x] Fallbacks workflow / tunnel prospect : `var(--brand)`.
- [x] Tests `tests/ui/test_brand_token_contract.py`.
- [x] Contrat `docs/product-design/TOKEN_BRAND_CONTRACT.md`.
- [x] Skill frontend : `ui-btn` est le DS ; `dui-*` = filet.

## Hors lot (prochaine feature)

Enrichir la vue Identité visuelle existante (aperçu Atelier, contraste live) — **pas** un second écran.

## Recette

- Défauts : bouton primaire toujours corail `#ff8775`, pas de brun.
- Atelier Identité visuelle : changer primaire → recharger une fiche Client / Atelier → `ui-btn-primary` suit.
- Restaurer la palette claire → retour aux défauts.
- Staff sans permission écriture : lecture seule.
- 375px / 1440px inchangés sur le shell.

## Checklist

- [x] Code
- [x] Tests contrat tokens
- [x] Permissions inchangées (vues branding existantes)
- [x] Documentation
- [x] Rebuild CSS (`cd backend && npm run build:css`) + pytest ciblé
