---
name: skill-portal-shell
description: Shell portail Prenium DTF — header Alpine, padding `ui-shell-main`, indicateur HTMX.
---

# Portal shell

- Gabarit : `templates/portal/layout.html` inclut `components/nav/portal_header.html`.
- Main : classes `app-main app-content ui-shell-main` (tokens `--ui-page-pad-x` dans `tokens.css`).
- Menu mobile : `x-data="{ mobileNav: false }"`, bouton `dui-btn` uniquement `< md`.
- Après edit CSS : `cd backend && npm run build:css`.
