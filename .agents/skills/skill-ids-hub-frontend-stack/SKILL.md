---
name: ids-hub-frontend-stack
description: Stack Tailwind + DaisyUI (préfixe dui-) + Alpine + HTMX pour IDS Hub / Prenium DTF. Utiliser lors de nouveaux écrans, refacto UI ou conventions CSS.
---

# Frontend stack (Prenium DTF / IDS Hub)

## Build CSS
- Source : `backend/static_src/css/input.css` (Tailwind + import `legacy/app-legacy.css`).
- Sortie servie par Django : `backend/static_src/css/app.css` (généré, minifié).
- Commande : `cd backend && npm install && npm run build:css` (dev : `npm run watch:css`).
- **Ordre obligatoire dans `input.css`** : `@import "./tokens.css"` puis **`@import "./legacy/app-legacy.css"` avant** les directives `@tailwind`. Si le legacy est placé après `@tailwind`, PostCSS peut produire un `app.css` sans les règles legacy (~14 Ko au lieu de ~36 Ko) : la page ressemble à du HTML nu malgré un 200 sur le CSS.
- **Preflight Tailwind désactivé** pour ne pas casser les styles sémantiques existants (`.btn`, `.card`, etc.).

## DaisyUI
- Préfixe **`dui-`** pour éviter les collisions avec les classes historiques (ex. `.btn` legacy ≠ `dui-btn`).
- Thème **`prenium`** : `data-theme="prenium"` sur `<html>` (voir `base.html`). Snapshot hex des défauts DESIGN.md ; la palette **live** Atelier passe par `--brand` / `--accent`, pas par Daisy.
- Markup produit : **`ui-btn`**, `ui-card` n’existe pas — cartes via chrome `ui-*` / product-shell. Ne pas introduire `dui-btn` dans les gabarits. `.dui-btn` n’est qu’un alias CSS de `.ui-btn`.

## Tokens et identité Atelier
- Source : `tokens.css`. Surcharge runtime : `base.html` + `BrandThemeSettings` (`/staff/settings/branding/`).
- Contrat : `docs/product-design/TOKEN_BRAND_CONTRACT.md`. Test : `tests/ui/test_brand_token_contract.py`.
- Nouveaux styles d’action : `var(--brand)` / `var(--ui-action-*)`, jamais un hex recopié.

## Alpine.js
- Chargé en **defer** après HTMX dans `base.html`.
- Cas d’usage : menus mobile, drawers légers, états UI locaux (sans logique métier).

## HTMX
- Indicateur global `#portal-htmx-indicator` ; conserver `hx-indicator` sur les actions.
- Après swap : mettre à jour les états actifs (tabs/chips) via `htmx:afterSwap` ou classes dans le HTML partiel si besoin.

## DRY
- Factoriser les barres d’onglets HTMX répétées (staff/client order detail) via inclusion ou templatetag avec liste d’entrées `{ label, url }`.
- Ne pas dupliquer les attributs `hx-target` / `hx-swap` : un partial par contexte (staff vs client) si les URLs diffèrent.

## Responsive
- Breakpoints Tailwind par défaut ; compléter avec utilitaires `max-md:`, `md:` sur le shell (header déjà pattern menu mobile).
