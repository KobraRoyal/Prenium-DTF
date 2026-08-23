# Sprint 47 — Cohérence tables, actions et partials

> **Note (2026-08-23)** — Les primitives DRY (tables `ui-data-table`, `form_actions.html`, pagination partagée) restent valides. Le contrat « design system sombre » décrit ci-dessous est remplacé par le shell clair du [Sprint 48](sprint-48-shell-clair-homogene-impeccable.md).

## Objectif

Supprimer les dernières divergences visibles du design system sombre : tables staff hors contrat, variantes secondaires concurrentes, cartes mobiles carrées, textes secondaires illisibles et partials répétés. Le lot reste strictement présentatif : aucune route, permission, donnée, transition métier ou isolation tenant n’est modifiée.

## Audit initial

Score Impeccable initial : **66/100**.

- P1 : pagination presque noire sur fond graphite.
- P1 : tables staff rendues avec l’ancien composant `.table` et des couleurs héritées.
- P1 : règles legacy de boutons et tables concurrentes dans `product-shell.css`.
- P1 : finition Studio encapsulée dans une couche moins prioritaire que des règles historiques.
- P2 : secondaire et ghost visuellement fusionnés.
- P2 : cartes staff mobiles jointives, carrées et imbriquées dans une card.
- P2 : quatre paginations et deux blocs d’actions formulaire dupliqués.

## Architecture livrée

- `buttons.css` possède les variantes primaire, secondaire et ghost ainsi que les adaptateurs `.btn-*`, `.btn-saas-*` et `.dui-btn-*`.
- `shell.css` possède les tables, cartes responsive, pagination et présentation de couleur support.
- `product-shell.css` conserve uniquement les adaptations structurelles et métier ; les anciens propriétaires couleur/table/bouton ont été retirés.
- `product-polish.css` conserve les surfaces spécifiques et la finition checkout, sans reprendre la propriété des primitives.
- `studio-polish.css` est chargé après le composant éditeur et reste prioritaire sur ses règles legacy.
- Les palettes produit et Studio aliasent les tokens globaux ; aucune copie hexadécimale n’est nécessaire dans les couches de finition.
- Les badges acceptent les conventions historiques `badge-*` et réelles `badge is-*`, avec un rendu sémantique identique.
- `components/portal/pagination.html`, `components/forms/form_actions.html` et `components/tables/upload_support_color.html` portent les répétitions de présentation.

## Vues migrées

- Commandes client et Atelier.
- Comptes clients, demandes d’accès et projets B2B staff.
- Détail compte client et table des utilisateurs rattachés.
- Uploads checkout, panneau client et panneau Atelier.
- Studio desktop/mobile, y compris navigation mobile à trois sections.

## Validation

- [x] Build des quatre bundles CSS.
- [x] 68 tests source fondations/polish/cohérence ciblés.
- [x] Rendu de la pagination partagé couvert avec conservation de `q`, `status` et des attributs HTMX.
- [x] Pagination HTMX client exercée de la page 1 à la page 2.
- [x] États secondaire default/hover/focus contrôlés dans le navigateur.
- [x] Rendus authentifiés vérifiés à 1440px, 768px et 375px.
- [x] Aucun overflow horizontal sur listes, panneau uploads et Studio.
- [x] `git diff --check` conforme.
- [x] Suite QA technique indépendante : 155 tests réussis, aucune régression fonctionnelle P0–P2.
- [x] Suite globale finale : 791 tests réussis, 1 ignoré.
- [x] Détecteur Impeccable final exécuté (fallback regex dégradé, aucun motif) et revue visuelle indépendante sans P0/P1 ; les deux P2 et la dette P3 relevés ont été corrigés.
- [x] Graphe Graphify actualisé (`graphify update .`).

## Hors périmètre

- Aucun modèle, service, migration ou permission.
- Aucun changement des URLs ni des actions métier.
- Le canevas Studio reste volontairement clair pour la fidélité prépresse.
