# Frontend

Le frontend actif est intégré au monolithe Django :

- templates : `backend/templates/` ;
- sources CSS/JS : `backend/static_src/` ;
- TailwindCSS + DaisyUI préfixé `dui-` ;
- HTMX et Alpine.js auto-hébergés via le pipeline npm.
- DM Sans et Space Grotesk auto-hébergées via `@fontsource-variable` ;
- runtime marketing allégé (`marketing.js`) sans HTMX/Alpine sur les pages publiques.

Ce dossier ne contient pas une application frontend séparée. Il est conservé uniquement comme repère
d’architecture afin d’éviter la création accidentelle d’un second frontend concurrent.
