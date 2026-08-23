# Sprint 46 — Design system sombre Impeccable

> **Note (2026-08-23)** — Ce sprint a été livré sur la branche `codex/octostitch-ui-redesign` puis **supplanté visuellement** par le pivot clair « Atelier clair et chaleureux » (`DESIGN.md`, [Sprint 48](sprint-48-shell-clair-homogene-impeccable.md)). Les preuves et checklists ci-dessous restent l’historique du lot sombre ; ne pas les réutiliser comme contrat actif.

## Objectif

Faire évoluer la refonte de `codex/octostitch-ui-redesign` vers une interface sombre, épurée et ultra intuitive sur toutes les surfaces : landing, tunnel, login, portail client, Atelier et Studio. Le chantier reste strictement visuel et ne modifie ni routes, ni permissions, ni modèles, ni isolation multi-tenant, ni logique métier.

## Direction

La métaphore retenue est le **Banc de contrôle nocturne** : graphite mat, plateaux charbon superposés, texte ivoire chaud, corail réservé aux actions et marques d’inspection, lignes fines et arrondis `14px`, `16px`, `18px` ou pill `999px`. Chaque vue expose d’abord l’état, puis une prochaine action ; les preuves et informations secondaires reculent dans la hiérarchie.

Le canevas du Studio reste volontairement clair pour préserver la fidélité prépresse. Ses contrôles, panneaux, poignées de recadrage, guides et sélections appartiennent néanmoins au même langage sombre et corail.

## Architecture et périmètre

- Tokens partagés : `tokens.css`.
- Primitives DRY : `buttons.css`, `forms.css`, `shell.css`.
- Landing : `landing-conversion.css`.
- Portails client et Atelier : `product-polish.css`.
- Studio et recadrage : `studio-polish.css`.
- Bundles régénérés : `app.css`, `marketing.css`, `portal.css`, `studio.css`.
- Contrat machine et humain : `DESIGN.md` et `.impeccable/design.json`.

## Correctifs UI/UX

- Fond racine, overscroll, login et champs harmonisés en sombre.
- Contrastes des titres, textes secondaires, tableaux, lignes d’attention et cartes mobiles corrigés.
- FAQ mobile remise sur une colonne pleine largeur ; CTA et contrôles alignés sur les pills partagées.
- Ombres dures, gradients hérités et marqueurs décoratifs redondants neutralisés.
- File Atelier, fiche opérateur, fiche client et Studio rendus cohérents sur desktop et mobile.
- Onglet Studio mobile actif, états de validation et champs numériques rendus lisibles.
- Recadrage Studio : cadre, poignées, mode actif, focus, guides et sélection convertis du lime/bleu vers le corail, avec contrôles charbon.

## Définition de terminé

- [x] Contrat visuel sombre appliqué aux surfaces marketing, client, Atelier et Studio.
- [x] Architecture CSS DRY conservée et bundles de surface régénérés.
- [x] Aucun changement de domaine, modèle, route, permission ou isolation tenant.
- [x] Recette Playwright réelle à `1440px` et `375px`, sans overflow horizontal.
- [x] Landing, login, dashboard client, fiche client, File Atelier, fiche Atelier et Studio inspectés visuellement.
- [x] État de recadrage Studio contrôlé avec un fichier local sans soumettre d’import.
- [x] `make test-ui` — 83 passed.
- [x] Tests fondations/polish/Studio ciblés — 11 passed.
- [x] Test Studio post-review — 3 passed.
- [x] Suite complète finale — 786 passed, 1 skipped.
- [x] `make check` — aucun problème.
- [x] `make migrations-plan` — aucune migration.
- [x] `make lint` — OK.
- [x] `make format` — 338 fichiers conformes.
- [x] `make agents-check` — 6 contrats valides.
- [x] `make health` — base et cache opérationnels.
- [x] Détecteur Impeccable exécuté une fois ; mode dégradé faute de parseurs locaux, warning typographique accepté.
- [x] Reviewer final Impeccable — disposition initiale `fix`, P1 recadrage corrigé, verdict final `ship`.
- [x] `DESIGN.md`, sidecar Impeccable et graphe Graphify actualisés.

## Preuves

Les captures finales sont regroupées dans `.impeccable/review/`. Les références principales sont `desktop.png`, `mobile.png`, `client-desktop.png`, `atelier-desktop.png`, `studio-desktop.png`, `studio-crop-desktop.png` et leurs variantes mobiles.

Le détecteur Impeccable a fonctionné en fallback regex car `htmlparser2`, `css-select`, `css-tree` et `domutils` ne sont pas disponibles. Il sous-compte donc les constats ; la validation s’appuie en complément sur les styles calculés dans un navigateur réel, les captures multi-écrans, les tests et une revue indépendante.

`graphify update .` a reconstruit le graphe sans LLM. L’outil signale uniquement `pyproject.toml` sans nœud AST et recommande un futur relabel des communautés ; ces avertissements n’affectent pas le graphe de navigation du code.
