# Sprint 45 — Design system arrondi cohérent

## Objectif

Clôturer la refonte UI/UX de la branche `codex/octostitch-ui-redesign` : une direction inspirée d’Octostitch sans copie, cohérente entre marketing, tunnel, login, portail client, Atelier et Studio, sans dérive métier.

## Périmètre et fichiers

Refonte visuelle de la landing narrative, du shell partagé, du tunnel, du login, du dashboard client, de la fiche commande, de la File Atelier, de la bibliothèque et de l’éditeur Studio. Architecture CSS DRY : `tokens.css`, `buttons.css`, `forms.css`, `shell.css`, `landing-conversion.css`, `product-polish.css`, `studio-polish.css`, bundles marketing/portal/studio en layers. Les routes, permissions, modèles, multi-tenant et logique métier restent inchangés.

## Décisions

- Palette ivoire chaud / encre quasi noire / corail : `#fff7e9`, `#171513`, `#f0644f`, avec surfaces et états documentés dans `DESIGN.md`.
- Space Grotesk pour les titres, DM Sans pour le corps et l’UI.
- Arrondis `14px`, `16px`, `18px` et pills `999px`; ombres courtes et molles.
- Aucune ombre dure ni gradient décoratif dans les nouvelles couches ; une seule action primaire par vue.
- Suppression des eyebrows décoratifs et des CTA/tracking redondants ; contenu visible par défaut.
- Landing narrative : promesse → besoins → process → preuves → cas → FAQ → CTA.

## Définition de terminé

- [x] Direction visuelle et contrat de tokens documentés.
- [x] Surfaces marketing, produit, Atelier et Studio harmonisées.
- [x] Shell, tunnel, login, dashboard, commande, bibliothèque et éditeur couverts.
- [x] Architecture CSS DRY et bundles en layers finalisés.
- [x] Routes, permissions, modèles, isolation multi-tenant et logique métier inchangés.
- [x] États, accessibilité, responsive et contenu visible par défaut vérifiés.
- [x] `npm run build:css` — OK.
- [x] `make check` — OK.
- [x] Migrations dry-run — OK.
- [x] `agents-check` — OK.
- [x] `ruff check` / `ruff format` — OK.
- [x] Suite ciblée — 152 passed.
- [x] Suite complète — 786 passed, 1 skipped.
- [x] Playwright desktop/mobile validé sur landing, tunnel, login, client, commande, Atelier, bibliothèque et éditeur.
- [x] Overflow vérifié : 1440 = 1440 et 375 = 375.
- [x] Impeccable statique exécuté en mode dégradé faute de dépendances parseur/Puppeteer ; ses deux side-tabs ont été corrigés et le faux positif `img` caché est documenté.
- [x] Reviewer final — PASS sans constat.
- [x] Captures finales : `output/playwright/landing-desktop-20260822-final.png`, `output/playwright/landing-mobile-20260822-final.png`, `output/playwright/landing-mobile-process-20260822-final.png`.

## Validation et preuve

La recette finale couvre les parcours desktop et mobile et confirme l’absence de débordement. L’analyse Impeccable a été menée en mode dégradé, sans dépendances parseur/Puppeteer ; le rapport distingue le faux positif sur l’image masquée des deux side-tabs effectivement corrigés. Aucun constat ne subsiste dans la revue finale.
