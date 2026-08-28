# Sprint 48 — Shell clair homogène (Operate Impeccable)

## Objectif

Homogénéiser toutes les vues Prenium DTF autour d’un shell cohérent : header produit (logo corail, nav pills), fil d’Ariane uppercase, cartes blanches sur fond crème `#f4f0e6`, formulaires `ui-*`, alerts sémantiques — en remplacement du pivot sombre documenté dans les sprints 46–47.

## Direction

**« Atelier clair et chaleureux »** — voir `DESIGN.md` (North Star). Le corail `#ff8775` signale l’action ; le violet `#770176` porte le focus clavier. Les fiches staff « focus » (commande, compte, accès) conservent breadcrumb + carte synthèse comme modèle de référence.

## Architecture livrée

- **`page_head.html`** : partial canonique (`breadcrumb_template`, `lead_template`, `actions_template`, `head_class`).
- **`client_trail.html` / `staff_trail.html`** : fils d’Ariane DRY avec wrappers par section.
- **`portal.css`** : alias `--product-*` → tokens globaux clairs (unlayered, post-`product-shell.css`).
- **`shell.css`** : overrides runtime (breadcrumbs corail, ombres neutralisées, cartes arrondies, tunnel prospect, toasts `alert--*`).
- **Templates** : migration `dui-*` → `ui-input`, `ui-field-group`, `alert alert--*` sur checkout, vues client, staff (inspection, e-mails), tunnel prospect, toasts Alpine.

## Vues migrées

- Portail : listes staff/client, settings, checkout, commande, projet B2B, dashboard, profil, équipe, bibliothèque planches DTF.
- Partials : breadcrumbs dédiés (dont `staff_order_project_detail`), `page_head_leads/*`, `page_head_actions/*`, `upload_support_color.html`, pagination partagée.
- Marketing : header landing aligné sur `product-header` / `ui-foundation-nav`.
- Tunnel prospect : steps 1–3, invitation accept.

## Dette connue (hors purge physique)

- `product-shell.css` conserve des fallbacks brutalistes (`#0b0b0b`, ombres dures) — neutralisés à runtime via `shell.css` + alias tokens.
- `product-polish.css` / `prospect-journey.css` : hooks legacy `checkout-dui-input` conservés dans les CSS sources (Impeccable) ; templates tunnel utilisent `product-field-input` + overrides runtime dans `entries/portal.css`.
- Studio gang sheet : header production dédié (métriques live) ; breadcrumb extrait en partial DRY.
- Purge physique des fichiers CSS legacy bloquée par le hook Impeccable sans approbation explicite fichier entier.

## Validation

- [x] Build CSS (`npm run build:assets`).
- [x] **Docker** : `cd backend && npm run build:css:docker` (collectstatic dans le volume `django_static` servi par nginx).
- [x] **Redémarrage web** après changement de cache-bust templates : `docker compose restart web` (Gunicorn ne recharge pas toujours les templates HTML à chaud).
- [x] Overrides boutons portail (`box-shadow: none`, états hover) dans `entries/portal.css` — écrase `app-legacy.css` `.btn` lime + ombre décalée.
- [x] Cache-bust surface CSS : `?v=20260823-brand-light-v8` (`portal.css`, `marketing.css`, `studio.css`).
- [x] Tests fondations / polish / cohérence portail.
- [x] Suite complète — **809 passed, 1 skipped**.
- [x] Vérification navigateur (recette Docker `localhost:8080`, hard refresh) :
  - Client : `/client/` (breadcrumb Accueil client), commandes, fiche commande, planches DTF, studio gang sheet (`portal.css` + `studio.css` v8), profil, équipe, formulaire nouvelle commande.
  - Staff (`staff.ops@prenium.local`) : `/staff/`, `/staff/orders/`, `/staff/machines/` — header pills, fil d’Ariane, fond crème, pas d’ombre `8px 8px` sur boutons.
  - Auth / marketing : `/login/`, `/`, `/demande-acces/etape-1/`.
  - CSS servi : `portal.css?v=20260823-brand-light-v8` contient 41 blocs `body.landing-saas.portal-shell.product-shell` + override `tr.ui-row-warning` (plus de fond lime).
- [x] `/staff/settings/branding/` : template migré ; accès 403 pour `staff.ops` (permission `branding.view_brandthemesettings`) — hors périmètre shell.
- [x] `DESIGN.md` — thème clair documenté.
- [ ] Revue Impeccable complète post-purge physique `product-shell.css` (optionnel, P3).

## Micro-lot — modal de contrôle visuel client (26 août 2026)

La modal de validation des visuels est ramenée à une seule surface Operate : aperçu dominant,
contrôles techniques compacts et action primaire unique. Les cadres imbriqués du nuancier,
des dimensions et de la confirmation sont supprimés ; l’action `Supprimer` devient tertiaire
et le scroll interne de la colonne latérale est remplacé par l’unique scroll vertical du dialogue
aux petites hauteurs.

- [x] Aucun endpoint, permission, règle métier ou contrat HTMX modifié.
- [x] Fermeture par icône SVG accessible et cibles tactiles de 44 px.
- [x] Colonne latérale non scrollable à partir de 960 px ; aucun overflow horizontal attendu.
- [x] Aperçu placé avant les champs et les actions sur mobile afin de préserver la séquence de contrôle.
- [x] Build des bundles, 133 tests B2B/portail et 98 tests UI ciblés.
- [x] Recette authentifiée clavier + largeurs 375 / 768 / 1440 px.
- [x] Détecteur Impeccable sans alerte et `graphify update .`.

## Micro-lot — fiche commande transmise client (26 août 2026)

La fiche de suivi conserve la surface claire actuelle mais rétablit une identité métier stable :
le numéro `CMD-…` remplace le suffixe UUID, le fil d’Ariane HTMX garde le nom de la commande
et les informations transmises ne répètent plus le titre. Les onglets restent tous visibles sur
mobile et les fichiers utilisent une ligne plate plutôt qu’une carte imbriquée.

- [x] Aucun endpoint, permission, modèle ou transition métier modifié.
- [x] Référence, note et date demandée présentées depuis les données déjà scopées de la commande.
- [x] Onglets utilisables au clavier et visibles sans overflow à 375 px.
- [ ] Build, tests portail/UI et recette authentifiée 375 / 768 / 1440 px.
- [ ] Détecteur Impeccable et `graphify update .`.

## Micro-lot — références commande et numérotation unifiée (26 août 2026)

Centralisation des règles d’affichage des références commande et unification du numéro métier
`CMD-YYYY-NNNNNN` pour **tous** les modes (fichiers individuels, gang-sheet prête, réassort).

### Affichage par surface

| Surface | UUID court | N° CMD | Réf. client |
|---------|:----------:|:------:|:-----------:|
| Client | Non | Oui | Oui |
| Staff / listes OPS | Oui | Oui | Oui |
| Atelier | Oui | Oui | Oui |

Helpers : `backend/apps/orders/references.py` (`order_business_number`, `order_uuid_short`,
`order_client_reference`). Documentation complète :
[`docs/architecture/ORDER_REFERENCE_DISPLAY.md`](../architecture/ORDER_REFERENCE_DISPLAY.md).

### Numérotation gang-sheet → CMD

- `numbering.py` : préfixe unique `CMD` ; séquence annuelle partagée.
- Migration `0011_unify_project_number_cmd_prefix` : renommage rétroactif des projets
  `ready_gang_sheet` encore en `GANG-SHEET-*`.
- Checkout : note commande `Commande CMD-…` pour tous les modes.

- [x] Helpers centralisés + templates listes / fiches client / staff / Atelier.
- [x] Tests anti-régression (`test_references`, `test_client_order_presentation`, cohérence UI).
- [x] Unification préfixe `CMD-` (code + migration + tests).
- [x] Documentation architecture `ORDER_REFERENCE_DISPLAY.md`.
- [ ] Commit + push sur branche PR #13.

## Micro-lot — Studio desktop canvas prioritaire (27 août 2026)

Le Studio client retrouve sa largeur dédiée au-dessus de 980 px malgré la contrainte `1180px`
du shell partagé. La grille réserve 16rem à la galerie, 18rem à l’inspecteur et donne le reste au
canvas ; sa hauteur reste contenue dans le viewport aux largeurs desktop. Les outils visibles
atteignent 44 px et l’état « Utilisé » de la galerie n’est plus exposé comme un faux bouton.

- [x] Aucun endpoint, permission, état métier ou contrat HTMX modifié.
- [x] Largeur Studio dédiée, canvas prioritaire et absence d’overflow horizontal global.
- [x] Cibles toolbar 44 px et statut de galerie non interactif.
- [x] Cache-bust partagé porté à `20260827-studio-desktop-v35`.
- [x] Build, tests ciblés, recette 884 / 1024 / 1440 px et contrôle clavier.
- [x] Détecteur Impeccable et `graphify update .`.

## Micro-lot — Studio prix au point de décision (28 août 2026)

L'estimation quitte le bandeau supérieur pour devenir un résumé financier unique et permanent
dans le panneau « Finaliser ». Le total HT inclut explicitement l'impression et la préparation,
reste visible pendant la composition et se recalcule avec la quantité après validation. Le CTA
de commande n'apparaît que lorsqu'il devient disponible.

- [x] Aucun calcul métier, endpoint, permission ou contrat HTMX modifié.
- [x] Une seule occurrence visuelle du prix, placée avant l'action de confirmation.
- [x] Prix annoncé en région live et décomposition impression + préparation.
- [x] Cache-bust CSS `20260828-studio-price-v36` et JS Studio `20260828-studio-price-v22`.
- [x] Build, tests ciblés et recette 884 / 1024 / 1440 px avec contrôle clavier.
- [x] Détecteur Impeccable et `graphify update .`.

## Micro-lot — rail d'outils centré sur le canvas (28 août 2026)

Au-dessus de 1408 px, la barre quitte la largeur complète du Studio pour occuper uniquement la
colonne du canvas. « Texte » et « Auto-imposer » partagent un groupe unique ; historique,
sélection, zoom et enregistrement restent séparés par fonction et conservent leurs cibles de 44 px.
Sous ce seuil, le rail reprend la largeur complète afin de ne masquer aucune commande.

- [x] Aucun gestionnaire, raccourci clavier, endpoint ou permission modifié.
- [x] Barre alignée sur le canvas et groupes de commandes consolidés.
- [x] Repli pleine largeur sous 1408 px sans overflow global.
- [x] Cache-bust CSS partagé `20260828-studio-toolbar-v37` ; cache JS Studio inchangé.
- [x] Build, tests ciblés et recette 884 / 1024 / 1280 / 1440 px avec contrôle clavier.
- [x] Détecteur Impeccable et `graphify update .`.

## Micro-lot — rail de pilotage Studio sur une ligne (28 août 2026)

À partir de 1408 px, l'identité de la planche, les quatre étapes, les trois métriques et l'état
d'enregistrement partagent un seul rail. L'ordre visuel suit la tâche — contexte, progression,
mesure, état — tandis que l'ordre sémantique et les cibles clavier restent inchangés. Sous ce
seuil, le bandeau conserve ses deux lignes afin de préserver les libellés et les cibles tactiles.

- [x] Aucun gestionnaire, endpoint, permission ou état métier modifié.
- [x] Un seul cadre et une seule ligne de pilotage sur desktop large.
- [x] Repli lisible sur deux lignes sous 1408 px, sans masquage ni overflow global.
- [x] Cache-bust CSS partagé `20260828-studio-overview-v39` ; cache JS Studio inchangé.
- [x] Build, tests ciblés et recette 884 / 1024 / 1280 / 1408 / 1440 px avec contrôle clavier.
- [x] Détecteur Impeccable et `graphify update .`.

## Micro-lot — rythme et bordures du rail Studio (28 août 2026)

Le rail desktop large conserve un seul contour périphérique. Les séparateurs et rayons internes
sont supprimés ; un espace constant de 8 px distingue les quatre groupes, et leurs contenus
emploient le même retrait horizontal de 12 px. La zone métriques gagne sa largeur minimale pour
préserver le rythme sans tronquer les libellés.

- [x] Aucun gestionnaire, endpoint, permission ou état métier modifié.
- [x] Un seul contour perceptible ; état actif conservé comme repère fonctionnel.
- [x] Échelle d'espacement partagée : 8 px entre groupes, 12 px dans les sections.
- [x] Cache-bust CSS partagé `20260828-studio-rail-v40` ; cache JS Studio inchangé.
- [x] Build, tests ciblés et recette 1408 / 1440 px avec contrôle clavier.
- [x] Détecteur Impeccable et `graphify update .`.

## Micro-lot — action de groupe contextuelle (28 août 2026)

L'inspecteur et la barre flottante partagent une même règle : une sélection entièrement libre
propose seulement « Grouper » ; dès qu'elle contient un objet déjà groupé, elle propose seulement
« Dissocier ». Une sélection mixte doit donc libérer ses groupes existants avant d'être regroupée,
ce qui évite de scinder silencieusement une association mémorisée.

- [x] Aucun endpoint, permission, format de sauvegarde ou contrat métier modifié.
- [x] Source d'état unique pour l'inspecteur, la barre flottante et les fonctions d'action.
- [x] Un seul choix réalisable exposé à la souris, au clavier et aux technologies d'assistance.
- [x] Cache partagé `20260828-studio-groups-v41` et module Studio `20260828-studio-groups-v23`.
- [x] Tests ciblés et recette sélection libre / groupée / mixte.
- [x] Détecteur Impeccable, contrôle statique et `graphify update .`.

## Liens

- Supersedes visuellement : [Sprint 46](sprint-46-design-system-sombre-impeccable.md), complète [Sprint 47](sprint-47-coherence-tables-actions-partials.md).
- Contrat : `DESIGN.md`, `.impeccable/design.json`.
